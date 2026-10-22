"""插件清单（manifest）：除 LLM/agent 框架本体外的一切能力在此登记造册。

**P1 迁移后本模块是投影视图**：22 项内置插件的唯一真值源在
``pypedia/units/builtins.py``（Unit manifest 字典，新契约）；本模块把其中与
设置页/兼容层相关的字段投影为 frozen dataclass 元 Tuple，保留既有 API：

- :data:`BUILTIN_PLUGINS` —— 22 个 :class:`Plugin`（frozen dataclass，类型安全、
  零解析、零 I/O），单测锁定防漂移；
- :data:`_TOOLS_BY_PLUGIN` —— 从 manifests 的 ``contributions.agent_tools``
  投影还原的旧分组形状（module, [工具函数名]），仅供兼容层/测试消费；
- :func:`get_manifest` / :func:`describe` —— 查询入口不变。

设计原则（2026-10 插件化改造，用户拍板「不删减、空壳也留入口」）：
- **每一项能力一个条目**——有独立开关的实插件、暂无独立开关的空壳入口
  （引擎基础设施类）一律登记；空壳 = switchable=False，UI 置灰展示、
  预留未来独立开关/装卸的挂载点，不造假开关；
- ``default_enabled`` 必须等于 Settings 里 env_gate 字段的默认值（单测锁定）；
- 第三方插件 JSON 格式在 units/schema/unit.schema.json 定档（装卸见
  UnitLoader）：与 Unit manifest 同字段 + entrypoint，放
  <PYPEDIA_DATA>/plugins/<id>/plugin.json；内置插件不走该路径。

框架本体边界（刻意不登记）：pypedia/agent/{bailian_model,transport}.py、
pypedia/llm/、pypedia/models/（LLM 通道与 agent 循环）——发动机零件。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..units.builtins import BUILTIN_UNIT_MANIFESTS

# 旧视图 apply 归一：新契约 immediate ↔ 旧视图 instant（restart 两界一致）
_APPLY_LEGACY = {"immediate": "instant", "restart": "restart"}


@dataclass(frozen=True)
class Plugin:
    """插件 manifest（内置插件声明式登记，Unit manifest 的投影视图）。

    - id：kebab-case 唯一标识（代码里 is_enabled("<id>") 引用，单测锁定闭环）；
    - default_enabled：**出厂缺省启停态**（文档位，供 UI 展示参考；运行时
      无显式用户态时跟随部署态 env 门控，见 registry._effective）。
      必须等于 Settings 里 env_gate 字段的默认值（单测锁定，防两处漂移）；
    - env_gate：.env 部署态开关名（空 = 无部署态开关）；is_enabled 时与
      用户态做 AND——两边都开才生效；
    - switchable：False = 暂无独立开关的空壳入口（is_enabled 恒 True，
      set_enabled 拒绝；UI 置灰 + 「入口预留」标注）；
    - apply：启停何时生效——instant（下次调用即生效）| restart（需重启服务，
      如 cron 调度器/MCP 连接这类进程级资源）。空壳条目恒 instant。
    """

    id: str
    name: str
    version: str
    description: str
    default_enabled: bool
    env_gate: str = ""
    switchable: bool = True
    apply: str = "instant"


def _to_plugin(raw: dict) -> Plugin:
    """Unit manifest 字典 → 旧 Plugin 视图（apply 值归一为 instant/restart）。"""
    return Plugin(
        id=raw["id"],
        name=raw["name"],
        version=raw["version"],
        description=raw.get("description", ""),
        default_enabled=raw.get("default_enabled", False),
        env_gate=raw.get("env_gate", ""),
        switchable=raw.get("switchable", True),
        apply=_APPLY_LEGACY.get(raw.get("apply", "immediate"), "instant"),
    )


BUILTIN_PLUGINS: tuple[Plugin, ...] = tuple(_to_plugin(m) for m in BUILTIN_UNIT_MANIFESTS)

_BY_ID = {p.id: p for p in BUILTIN_PLUGINS}


def _derive_tools_by_plugin() -> dict[str, tuple[str, tuple[str, ...]]]:
    """从 Unit manifest 的 ``contributions.agent_tools`` 投影旧分组形状。

    入口 ``module:attr`` 按 module 聚合为 ``(module_path, (attr, ...))``；
    一个插件当前只提供单一 module 的工具（memory/skills/delegate 皆如此），
    多 module 场景旧形状无法表达，取第一个并在注释中说明。
    """
    out: dict[str, tuple[str, tuple[str, ...]]] = {}
    for raw in BUILTIN_UNIT_MANIFESTS:
        entries = raw.get("contributions", {}).get("agent_tools", [])
        if not entries:
            continue
        by_module: dict[str, list[str]] = {}
        for entry in entries:
            module_path, _, attr = entry.partition(":")
            by_module.setdefault(module_path, []).append(attr)
        # 单 module 约定：与旧 _TOOLS_BY_PLUGIN 形状恒等
        module_path, names = next(iter(by_module.items()))
        out[raw["id"]] = (module_path, tuple(names))
    return out


# 工具提供者映射：插件 id → (模块路径, [工具函数名])。
# 从 Unit manifest 的 agent_tools 贡献投影而来（真值源在 units/builtins.py）。
# 刻意按 id 而非 provider key 分组——SERVER_TOOLS 是 memory+skill 扁平
# 合并列表，按 key 汇总会「关记忆误伤技能」。顺序即拼装顺序：
# memory → skills → delegate，默认全开时与历史恒等。
_TOOLS_BY_PLUGIN: dict[str, tuple[str, tuple[str, ...]]] = _derive_tools_by_plugin()


def get_manifest(plugin_id: str) -> Plugin | None:
    return _BY_ID.get(plugin_id)


def describe() -> list[dict]:
    """全量 manifest（不含运行时状态；运行时状态见 registry.list_plugins）。"""
    return [
        {
            "id": p.id, "name": p.name, "version": p.version,
            "description": p.description, "default_enabled": p.default_enabled,
            "env_gate": p.env_gate, "switchable": p.switchable, "apply": p.apply,
        }
        for p in BUILTIN_PLUGINS
    ]
