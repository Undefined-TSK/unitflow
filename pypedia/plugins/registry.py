"""插件注册表：Unit 内核的**兼容适配层**（P1 迁移后 plugin_registry 即内核）。

架构（P1 收尾）：门控与工具汇总的唯一实现已上移到 ``pypedia.units.registry``
的 :class:`UnitRegistry`；本类的 ``PluginRegistry`` 是它的子类——

- **manifest 真值源**：``pypedia/units/builtins.py``（23 项 Unit manifest），
  经 ``pypedia.plugins.manifests`` 投影为旧 Plugin 视图；
- **state 文件**：沿用 ``<数据目录>/plugins/state.json``（``state_dir="plugins"``），
  既有部署的用户启停态零迁移；
- **API 兼容**：``is_enabled / env_blocked / set_enabled / list_plugins /
  summary / describe / enabled_agent_tools`` 形状与旧版逐字段一致，
  异常契约保留（未知 id → KeyError、非 bool → TypeError、空壳 → ValueError），
  日志事件名保留（plugin_state_corrupt / plugin_unknown_id /
  plugin_state_entry_ignored / plugin_state_set）。

核心语义（与内核一致，用户拍板「万物皆插件、空壳也留入口」）：
- **双层门控 AND**：is_enabled = 用户态（state.json）AND 部署态
  （settings.env_gate **实时** getattr）。实时读是硬约束——多处测试
  monkeypatch settings 单例句柄，缓存 env 值会让那些测试静默回归；
- **未知 id fail-open**：is_enabled 返回 True + warning——未登记 id 的行为
  不退回到插件化之前（宁可多给，不可因登记遗漏砍掉能力）；
- **空壳入口**（switchable=False）：is_enabled 恒 True，set_enabled 拒绝
  （ValueError）——预留挂载点，不造假开关；
- **数据卫生**：state.json 损坏 → 改名隔离 + 默认值 + log.error（复刻
  evolution 的数据损坏教训：静默返回空会让下次写入覆盖损坏文件）；
  未知 id / 非 bool 条目加载时忽略并留痕；
- **缺省用户态跟随部署态**（重要）：无显式用户态时 is_enabled 直接等于 env 门控，
  而不是 manifest.default_enabled——插件化之前 effective 就是 env 门控，若缺省取
  default_enabled，则本机 .env 打开过的开关（如 ENABLE_WEB_FETCH=true）会被静默
  关掉，构成行为回退。default_enabled 仅作「出厂缺省」文档位（单测锁定等于
  Settings 字段默认值），供 UI 展示参考。

state.json 形状：{"<plugin_id>": true/false, ...}（只存用户显式改过的项）。

**import 零副作用**：模块级只 import 内核；数据目录与 state.json 均懒加载
（首次 is_enabled/set_enabled/list_plugins 才读盘）——import 插件系统不产生
任何文件、不读 ~/.pypedia。
"""
from __future__ import annotations

from collections.abc import Iterable

from .manifests import BUILTIN_PLUGINS, get_manifest
from ..units.builtins import register_builtins
from ..units.registry import UnitRegistry

# state.json 落在 <数据目录>/plugins/ 下：与插件化以来的部署路径一致，
# 用户历史启停态零迁移（内核默认目录是 units/，由适配层显式指定）。
_STATE_DIR = "plugins"


class PluginRegistry(UnitRegistry):
    """插件启停态 + 门控查询（UnitRegistry 兼容子类；模块级单例即唯一实例）。"""

    # 日志事件名 / id 字段名：保留插件化以来的事件契约（单测与日志消费方锁定）
    _corrupt_event = "plugin_state_corrupt"
    _entry_ignored_event = "plugin_state_entry_ignored"
    _state_set_event = "plugin_state_set"
    _unknown_event = "plugin_unknown_id"
    _id_field = "plugin"

    def __init__(self) -> None:
        super().__init__(state_dir=_STATE_DIR)
        register_builtins(self, quiet=True)

    # —— 门控查询（异常契约与旧版一致）—— #
    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        """写用户启停态（原子落盘）。

        - 未知 id → KeyError（端点映射 404）；
        - 空壳入口（switchable=False）→ ValueError（不造假开关）；
        - enabled 非 bool → TypeError（端点层 pydantic 已先行 422，这里是纵深防御）；
        - env_blocked（.env 关了）时**允许写入**并如实返回——用户先打开开关，
          部署态恢复即生效，UI 同步展示「.env 中已关闭」说明。
        """
        manifest = self.get_unit(plugin_id)
        if manifest is None:
            raise KeyError(f"未知插件：{plugin_id}")
        if not manifest.switchable:
            raise ValueError(f"插件 {plugin_id} 暂无独立开关（入口预留）")
        if not isinstance(enabled, bool):
            raise TypeError("enabled 必须是 bool")
        super().set_enabled(plugin_id, enabled)

    # —— 全量视图（旧形状逐字段保留）—— #
    def list_plugins(self) -> list[dict]:
        """全量插件 + 运行时状态（设置页面板与 /api/plugins 的数据源）。"""
        out = []
        for p in BUILTIN_PLUGINS:
            out.append({
                "id": p.id, "name": p.name, "version": p.version,
                "description": p.description, "default_enabled": p.default_enabled,
                "env_gate": p.env_gate, "switchable": p.switchable, "apply": p.apply,
                "enabled": self.is_enabled(p.id), "env_blocked": self.env_blocked(p.id),
            })
        return out

    def summary(self) -> dict:
        """汇总计数（端点契约 summary 字段）。"""
        items = self.list_plugins()
        return {
            "total": len(items),
            "enabled": sum(1 for i in items if i["enabled"]),
            "env_blocked": sum(1 for i in items if i["env_blocked"]),
        }

    def describe(self, plugin_id: str) -> dict | None:
        """单插件运行时视图（含 enabled / env_blocked / contributions）；未知 id 返回 None。

        与 list_plugins 单条同构——端点写回时复用，避免形状漂移。
        contributions 附赠：前端据 ui_panels 资产贡献决定开关后是否重跑懒加载。
        """
        manifest = get_manifest(plugin_id)
        if manifest is None:
            return None
        unit = self.get_unit(manifest.id)
        return {
            "id": manifest.id, "name": manifest.name, "version": manifest.version,
            "description": manifest.description, "default_enabled": manifest.default_enabled,
            "env_gate": manifest.env_gate, "switchable": manifest.switchable,
            "apply": manifest.apply,
            "enabled": self.is_enabled(manifest.id),
            "env_blocked": self.env_blocked(manifest.id),
            "contributions": unit.contributions if unit else {},
        }

    # —— agent 工具汇总（内核实现 + 旧签名）—— #
    def enabled_agent_tools(self, *, include_delegate: bool = True,
                            active_only: Iterable[str] | None = None) -> list:
        """按插件 id 懒加载拼装 agent 工具列表（browser 工具不在此列——不门控）。

        - 顺序 memory → skills → delegate：默认全开时与历史
          BROWSER_TOOLS+SERVER_TOOLS+DELEGATE_TOOLS 恒等（11 工具断言是裁判）；
        - include_delegate=False：子代理专用（禁嵌套委派保留）——子代理只拿
          memory/skills 工具，不拿 delegate_task 自身；
        - active_only：P5 规则引擎的确定性路由（fail-closed）——非 None 时
          仅激活集内的插件贡献工具；None 时不过滤（规则引擎关闭的兼容路径）。
        """
        excluded = frozenset() if include_delegate else {"agent-delegate"}
        return super().enabled_agent_tools(exclude_unit_ids=excluded,
                                           active_only=active_only)


plugin_registry = PluginRegistry()
"""模块级单例：全项目统一入口（from pypedia.plugins import plugin_registry）。"""
