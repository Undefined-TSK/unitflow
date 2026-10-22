"""P4 diagram-render 测试：图表渲染插件化 + 前端懒加载。

验收口径（master plan §11 P4：开启渲染、关闭不加载）：
1. manifest 契约：diagram-render（P4 新增内置）过 unit.schema.json 校验；
   default_enabled 与 Settings.DIAGRAM_RENDER_ENABLE 一一对应（防漂移）；
2. 门控语义：用户态开关 + 部署态（env_blocked）四组合，与既有插件同一套内核；
3. 提示词贡献：启用时 build_system_prompt 注入「图表渲染规约」、关闭时不注入
   （文案单一真值源在 manifest 的 system_prompt_sections，build.py 只按名取值；
   注意引擎基础段的「可视化输出规范」是输出格式总目录、不受门控，故断言用
   diagram-render 独有标记，不断言 "mermaid" 消失）；
4. ui_panels 贡献：assets 含 mermaid/echarts 且 lazy=True（关闭→零下载的前端依据）；
5. 端点：/api/plugins 与 /api/units 均含 diagram-render；/api/units 列表携带
   contributions.ui_panels（plugins.js 懒加载的数据来源——列表视图不带
   contributions 会让前端永远拿不到资产清单，本测试是回归裁判）；
   toggle 回写带 contributions（settings.js 热刷新依据）；
6. 静态契约：index.html 无 mermaid/echarts 硬编码 script；md.js 无顶层
   mermaid.initialize；plugins.js/settings.js/app.js 懒加载接线标记在位。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pypedia.config import Settings, settings
from pypedia.plugins import BUILTIN_PLUGINS, plugin_registry
from pypedia.units.builtins import BUILTIN_UNIT_MANIFESTS
from pypedia.units.manifest import validate_raw

ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_ID = "diagram-render"
MERMAID_ASSET = "/static/vendor/mermaid.min.js"
ECHARTS_ASSET = "/static/vendor/echarts.min.js"


def _raw_manifest() -> dict:
    for m in BUILTIN_UNIT_MANIFESTS:
        if m["id"] == DIAGRAM_ID:
            return m
    raise AssertionError(f"{DIAGRAM_ID} 不在内置 Unit manifest 中")


# ---------- 1. manifest 契约 ---------- #
def test_manifest_validates_and_registered():
    """diagram-render manifest 过 schema 校验，且已注册进兼容内核。"""
    raw = _raw_manifest()
    validate_raw(raw)  # 不抛 ManifestError 即过 schema 校验
    assert len(BUILTIN_UNIT_MANIFESTS) == 23  # P4 新增 diagram-render、P5 新增 rule-engine
    assert plugin_registry.get_unit(DIAGRAM_ID) is not None
    # 投影视图（设置页消费）与 Unit manifest 同源（form 是 Unit 契约独有字段）
    p = next(p for p in BUILTIN_PLUGINS if p.id == DIAGRAM_ID)
    assert p.env_gate == "DIAGRAM_RENDER_ENABLE"
    assert p.switchable and p.apply == "instant"
    assert _raw_manifest()["form"] == "instance"


def test_default_enabled_matches_settings():
    """default_enabled 与 Settings.DIAGRAM_RENDER_ENABLE 默认值防漂移。"""
    raw = _raw_manifest()
    assert raw["env_gate"] == "DIAGRAM_RENDER_ENABLE"
    field = Settings.model_fields.get("DIAGRAM_RENDER_ENABLE")
    assert field is not None, "DIAGRAM_RENDER_ENABLE 不是 Settings 字段"
    assert raw["default_enabled"] == field.default


# ---------- 2. 门控语义 ---------- #
def test_gating_user_and_env_matrix(monkeypatch):
    """用户态开关 + 部署态拦截：关→不开、用户开+部署关→env_blocked。"""
    reg = plugin_registry
    assert reg.is_enabled(DIAGRAM_ID) is True  # 默认开（测试环境部署态未关）
    reg.set_enabled(DIAGRAM_ID, False)
    assert reg.is_enabled(DIAGRAM_ID) is False
    reg.set_enabled(DIAGRAM_ID, True)
    assert reg.is_enabled(DIAGRAM_ID) is True
    # 部署态（.env）关闭：即使用户态显式开，也不可用
    monkeypatch.setattr(settings, "DIAGRAM_RENDER_ENABLE", False)
    assert reg.env_blocked(DIAGRAM_ID) is True
    assert reg.is_enabled(DIAGRAM_ID) is False


# ---------- 3. 提示词贡献 ---------- #
def test_system_prompt_section_gated():
    """启用注入「图表渲染规约」；关闭不注入（单一真值源=manifest 贡献）。"""
    from pypedia.agent.build import build_system_prompt

    sp = build_system_prompt(3, "画一个流程图")
    assert "图表渲染规约" in sp and "diagram-render" in sp
    plugin_registry.set_enabled(DIAGRAM_ID, False)
    try:
        sp_off = build_system_prompt(3, "画一个流程图")
    finally:
        plugin_registry.set_enabled(DIAGRAM_ID, True)
    assert "图表渲染规约" not in sp_off


def test_prompt_text_is_manifest_single_source():
    """注入文案逐字等于 manifest 的 system_prompt_sections.text（不复制）。"""
    from pypedia.agent.build import _diagram_addendum

    text = _raw_manifest()["contributions"]["system_prompt_sections"][0]["text"]
    assert _diagram_addendum().strip() == text


# ---------- 4. ui_panels 贡献形状 ---------- #
def test_ui_panels_contribution_shape():
    panels = _raw_manifest()["contributions"]["ui_panels"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["slot"] == "render.hook"
    assert panel["entry"] == "diagram-render:frontend"
    assert panel["lazy"] is True
    assert panel["assets"] == [MERMAID_ASSET, ECHARTS_ASSET]
    sections = _raw_manifest()["contributions"]["system_prompt_sections"]
    assert [s["name"] for s in sections] == ["diagram-render:guide"]
    assert sections[0]["order"] == 80 and sections[0]["text"]


# ---------- 5. 端点契约 ---------- #
class TestDiagramEndpoints:
    def test_units_list_carries_ui_panels(self, client):
        """/api/units 列表带 contributions.ui_panels——plugins.js 懒加载数据来源。"""
        r = client.get("/api/units")
        assert r.status_code == 200
        u = next(u for u in r.json()["units"] if u["id"] == DIAGRAM_ID)
        assert u["enabled"] is True and u["env_blocked"] is False
        panels = u["contributions"]["ui_panels"]
        assert panels[0]["assets"] == [MERMAID_ASSET, ECHARTS_ASSET]
        assert panels[0]["lazy"] is True

    def test_plugins_view_and_toggle_roundtrip(self, client):
        """/api/plugins 含 diagram-render；toggle 回写带 contributions（热刷新依据）。"""
        r = client.get("/api/plugins")
        p = next(p for p in r.json()["plugins"] if p["id"] == DIAGRAM_ID)
        assert p["env_gate"] == "DIAGRAM_RENDER_ENABLE"
        assert p["switchable"] is True
        # 关 → 回写带 ui_panels 贡献；再开恢复
        r2 = client.post(f"/api/plugins/{DIAGRAM_ID}", json={"enabled": False})
        assert r2.status_code == 200
        dd = r2.json()["plugin"]
        assert dd["enabled"] is False
        assert dd["contributions"]["ui_panels"][0]["assets"] == [MERMAID_ASSET, ECHARTS_ASSET]
        r3 = client.post(f"/api/plugins/{DIAGRAM_ID}", json={"enabled": True})
        assert r3.json()["plugin"]["enabled"] is True

    def test_units_gate_view_matches_plugins(self, client):
        """内置 id 两视图门控一致（P1 合并口径对 diagram-render 同样成立）。"""
        p = next(p for p in client.get("/api/plugins").json()["plugins"]
                 if p["id"] == DIAGRAM_ID)
        u = next(u for u in client.get("/api/units").json()["units"]
                 if u["id"] == DIAGRAM_ID)
        assert u["enabled"] == p["enabled"] and u["env_blocked"] == p["env_blocked"]


# ---------- 6. 静态契约（前端懒加载接线） ---------- #
def test_index_html_has_no_hardcoded_vendor_scripts():
    """index.html 不再硬编码 mermaid/echarts script（懒加载接管），但挂 plugins.js。"""
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "vendor/mermaid.min.js" not in html
    assert "vendor/echarts.min.js" not in html
    assert 'src="/static/js/plugins.js"' in html


def test_md_js_has_no_toplevel_mermaid_initialize():
    """md.js 无顶层 mermaid.initialize（改由 plugins.js 就绪后条件调用），
    渲染分支按 DiagramRender 门控（关闭→降级普通高亮）。"""
    src = (ROOT / "static" / "js" / "md.js").read_text(encoding="utf-8")
    toplevel = [ln for ln in src.splitlines() if ln.startswith("mermaid.initialize")]
    assert not toplevel, f"仍有顶层 mermaid.initialize：{toplevel}"
    assert "function initMermaid" in src
    assert "DiagramRender" in src  # mermaid/chart 分支按门控降级


def test_frontend_lazy_loading_wiring():
    """plugins.js（loader）/ settings.js（热刷新）/ app.js（分享页竞态兜底）接线在位。"""
    plugins = (ROOT / "static" / "js" / "plugins.js").read_text(encoding="utf-8")
    for marker in ("window.DiagramRender", "window.PluginsBoot", "/api/units",
                   "sweepPending", "ui_panels"):
        assert marker in plugins, f"plugins.js 缺少接线标记：{marker}"
    settings_js = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    assert "DiagramRender.refresh" in settings_js
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "PluginsBoot" in app_js
