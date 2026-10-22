"""Unit 注册表（进程级单例）：启停态持久化 + 部署态门控 + 工具汇总。

门控语义与既有 ``plugins/registry.py`` 对齐（用户拍板「万物皆插件、空壳也留入口」）：
- **双层门控 AND**：``is_enabled = 用户态(state.json) AND 部署态(env_gate)``。
  部署态实时解析（不缓存），保证 monkeypatch 测试不静默回归；
- **缺省跟随部署态**：无显式用户态时等于 env 门控，而非 manifest.default_enabled
  ——避免本机 .env 已开的开关被静默关掉（行为回退）；
- **未知 id fail-open**：返回 True + warning，未登记 id 不退回到插件化之前；
- **空壳入口**（switchable=False）：is_enabled 恒 True，set_enabled 拒绝(RegistryError)；
- **数据卫生**：state.json 损坏 → 改名隔离 + 默认值 + 日志；未登记 id / 非 bool 条目忽略。

P1 迁移：本类是**门控与工具汇总的唯一实现**；旧 ``plugins/registry.py`` 的
``PluginRegistry`` 现为本类的子类（适配层，保留旧 API/异常/日志/state 路径）。
- ``state_dir``：state.json 所在子目录（内核默认 ``units``；插件桥接传 ``plugins``
  保持既有部署的 state 文件不漂移）；
- 日志事件名/id 字段名为类属性钩子（``_corrupt_event`` 等），子类覆盖以保留旧事件契约。
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from .exceptions import RegistryError
from .manifest import Manifest

# 挂在 pypedia 层级下：日志文件 handler（setup_logging 挂在 "pypedia"）才能收到，
# 同时不 import logging_setup——保持内核对 config/日志体系的零依赖。
log = logging.getLogger("pypedia.units.registry")

_STATE_FILE = "state.json"


def _default_env_resolver(name: str) -> bool:
    """部署态解析：优先读平台 settings 字段，回退读环境变量。

    缺省 True（与「未知 id fail-open」同一哲学：登记了 env_gate 但平台无此字段时
    放行，宁可多给、不可因配置缺项静默砍掉能力）。环境变量回退识别常见真值，
    避免 ``bool("false") is True`` 的字符串陷阱。
    """
    if not name:
        return True
    try:  # 解耦 config：内核可在无 settings 环境单测
        from ..config import settings  # type: ignore

        return bool(getattr(settings, name, True))
    except Exception:
        return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


class UnitRegistry:
    """Unit 启停态 + 门控查询（单例；模块级 ``unit_registry`` 即唯一实例）。"""

    # 日志事件名 / id 字段名：兼容层（PluginRegistry）覆盖以保留旧事件契约
    _corrupt_event = "unit_state_corrupt"
    _entry_ignored_event = "unit_state_entry_ignored"
    _state_set_event = "unit_state_set"
    _unknown_event = "unit_unknown_id"
    _id_field = "unit"

    def __init__(
        self,
        env_resolver: Callable[[str], bool] | None = None,
        state_dir: str = "units",
    ) -> None:
        self._units: dict[str, Manifest] = {}
        self._state: dict[str, bool] | None = None  # None=未加载（懒加载标记）
        self._lock = threading.RLock()
        self.env_resolver = env_resolver or _default_env_resolver
        self.state_dir = state_dir

    # —— 注册 —— #
    def register(self, manifest: Manifest, *, quiet: bool = False) -> None:
        """登记一个 unit（``quiet=True`` 走 debug 日志，批量注册防刷屏）。"""
        if manifest.id in self._units:
            raise RegistryError(f"重复注册 unit: {manifest.id}")
        self._units[manifest.id] = manifest
        msg = "已注册 unit: %s (type=%s, form=%s)"
        args = (manifest.id, manifest.type, manifest.form)
        (log.debug if quiet else log.info)(msg, *args)

    def get_unit(self, unit_id: str) -> Manifest | None:
        return self._units.get(unit_id)

    def unregister(self, unit_id: str) -> None:
        self._units.pop(unit_id, None)

    def all_units(self) -> list[Manifest]:
        return list(self._units.values())

    # —— 持久化 —— #
    def _state_path(self) -> Path:
        base = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))
        return Path(base) / self.state_dir / _STATE_FILE

    def _load(self) -> dict[str, bool]:
        if self._state is not None:
            return self._state
        with self._lock:
            if self._state is not None:
                return self._state
            path = self._state_path()
            state: dict[str, bool] = {}
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(raw, dict):
                        raise ValueError("顶层非对象")
                    for k, v in raw.items():
                        # 只认「已登记 id + bool 值」：防手改文件把状态带歪
                        if k in self._units and isinstance(v, bool):
                            state[k] = v
                        else:
                            log.warning(self._entry_ignored_event,
                                        extra={self._id_field: k, "value": repr(v)})
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    # 损坏隔离：改名保留证据 + 默认值，避免静默覆盖
                    self._quarantine_state(path, exc)
            self._state = state
            return state

    def _quarantine_state(self, path: Path, exc: Exception) -> None:
        """state.json 损坏隔离：带时间戳改名留存原件 + error 日志。"""
        quarantined = path.with_name(f"{path.stem}.corrupt-{int(time.time())}{path.suffix}")
        try:
            path.rename(quarantined)
            log.error(self._corrupt_event, extra={
                "path": str(path), "quarantined": str(quarantined), "error": str(exc)})
        except OSError as rename_err:
            log.error(self._corrupt_event, extra={"path": str(path), "error": str(exc)})
            log.warning("unit_quarantine_failed", extra={"error": str(rename_err)})

    def _save(self) -> None:
        """原子写 state.json（同目录唯一临时文件 + os.replace，跨平台原子替换）。"""
        assert self._state is not None
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, path)  # 同文件系统内原子替换，断电/崩溃不留半文件
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # —— 门控 —— #
    def _env_blocked(self, manifest: Manifest) -> bool:
        if not manifest.env_gate:
            return False
        return not self.env_resolver(manifest.env_gate)

    def is_enabled(self, unit_id: str) -> bool:
        manifest = self._units.get(unit_id)
        if manifest is None:
            log.warning(self._unknown_event, extra={self._id_field: unit_id})
            return True  # 未知 id fail-open：行为不退回到插件化之前
        if not manifest.switchable:
            return True  # 空壳入口恒开
        state = self._load()
        if unit_id in state:  # 用户显式改过 → 跟随用户态 AND 部署态
            return state[unit_id] and not self._env_blocked(manifest)
        return not self._env_blocked(manifest)  # 缺省跟随部署态

    def env_blocked(self, unit_id: str) -> bool:
        """是否因部署态（.env）关闭而不可用（未知 id 返回 False）。"""
        manifest = self._units.get(unit_id)
        if manifest is None:
            return False
        return self._env_blocked(manifest)

    def set_enabled(self, unit_id: str, enabled: bool) -> None:
        manifest = self._units.get(unit_id)
        if manifest is None:
            raise RegistryError(f"未知 unit id: {unit_id}")
        if not manifest.switchable:
            raise RegistryError(f"空壳入口不可开关: {unit_id}")
        with self._lock:
            state = self._load()
            state[unit_id] = bool(enabled)
            self._save()
        log.info(self._state_set_event,
                 extra={self._id_field: unit_id, "enabled": bool(enabled)})

    # —— 查询 —— #
    def list_units(self) -> list[dict[str, Any]]:
        """全部 unit 的运行时视图（含 contributions——前端资产加载器消费）。

        contributions 是 manifest 静态数据（ui_panels/agent_tools/…），
        随列表下发，避免前端为拿资产清单对每个 unit 再打一次详情（N+1）。
        """
        out = []
        for m in self._units.values():
            enabled = self.is_enabled(m.id)
            out.append({
                "id": m.id, "type": m.type, "name": m.name, "version": m.version,
                "form": m.form, "enabled": enabled,
                "switchable": m.switchable, "env_blocked": self._env_blocked(m),
                "default_enabled": m.default_enabled, "env_gate": m.env_gate,
                "apply": m.apply, "contributions": m.contributions,
            })
        return out

    def describe(self, unit_id: str) -> dict[str, Any] | None:
        m = self._units.get(unit_id)
        if m is None:
            return None
        return {
            "id": m.id, "type": m.type, "name": m.name, "version": m.version,
            "form": m.form, "description": m.description, "enabled": self.is_enabled(m.id),
            "switchable": m.switchable, "env_blocked": self._env_blocked(m),
            "default_enabled": m.default_enabled, "env_gate": m.env_gate,
            "apply": m.apply, "dependencies": m.dependencies,
            "contributions": m.contributions, "node_graph": m.node_graph,
            "agent_def": m.agent_def, "team_def": m.team_def,
        }

    def summary(self) -> dict[str, Any]:
        units = self.list_units()
        return {
            "total": len(units),
            "enabled": sum(1 for u in units if u["enabled"]),
            "env_blocked": sum(1 for u in units if u["env_blocked"]),
            "by_type": {
                t: sum(1 for u in units if u["type"] == t)
                for t in ("plugin", "agent", "team")
            },
        }

    # —— 工具汇总（供 graph 引擎 / agent 组装）—— #
    def enabled_tools(self) -> list[dict[str, Any]]:
        """汇总所有「已启用」unit 的 contributions.tools（懒 import module:attr）。"""
        tools: list[dict[str, Any]] = []
        for m in self._units.values():
            if not self.is_enabled(m.id):
                continue
            for entry in m.contributions.get("tools", []):
                try:
                    tools.append(self._resolve_tool_entry(entry))
                except Exception as exc:  # 单点故障不应阻断整体
                    log.warning("解析 tool 入口失败 %s: %s", entry, exc)
        return tools

    @staticmethod
    def _resolve_tool_entry(entry: str) -> dict[str, Any]:
        module_path, _, attr = entry.partition(":")
        if not attr:
            raise RegistryError(f"tool 入口格式应为 module:attr: {entry}")
        module = importlib.import_module(module_path)
        obj = getattr(module, attr)
        # 入口返回 (tools, disposer) 或直接的 handler 字典/列表
        result = obj() if callable(obj) else obj
        if isinstance(result, tuple):
            tool_list, _disposer = result
        else:
            tool_list = result
        if isinstance(tool_list, dict):
            tool_list = [tool_list]
        return {"source": entry, "tools": tool_list}

    def enabled_agent_tools(
        self, *, exclude_unit_ids: Iterable[str] = frozenset(),
        active_only: Iterable[str] | None = None,
    ) -> list[Any]:
        """汇总已启用 unit 的 contributions.agent_tools（**裸可调用**，供 agent 工具循环）。

        - 按注册顺序装配（manifest 声明序 = 工具序，与插件化前恒等）；
        - ``exclude_unit_ids``：排除指定 unit（如子代理场景排除 agent-delegate，
          禁嵌套委派）；
        - ``active_only``：P5 规则引擎的确定性路由（fail-closed）——非 None 时
          仅 id 在该集合内的 unit 贡献工具；None 时不过滤（规则引擎关闭的
          兼容路径：插件启用即可见）；
        - 单点解析失败不阻断整体（warning 留痕）。
        """
        excluded = set(exclude_unit_ids)
        active = None if active_only is None else set(active_only)
        tools: list[Any] = []
        for m in self._units.values():
            if m.id in excluded or not self.is_enabled(m.id):
                continue
            if active is not None and m.id not in active:
                continue  # fail-closed：未进本轮激活集 → 工具不可见
            for entry in m.contributions.get("agent_tools", []):
                try:
                    tools.append(self._resolve_callable(entry))
                except Exception as exc:  # 单点故障不应阻断整体
                    log.warning("解析 agent_tools 入口失败 %s: %s", entry, exc)
        return tools

    @staticmethod
    def _resolve_callable(entry: str) -> Any:
        """把 ``module:attr`` 入口解析为裸可调用对象（agent 工具函数）。"""
        module_path, _, attr = entry.partition(":")
        if not attr:
            raise RegistryError(f"callable 入口格式应为 module:attr: {entry}")
        module = importlib.import_module(module_path)
        obj = getattr(module, attr)
        if not callable(obj):
            raise RegistryError(f"agent_tools 入口不是可调用对象: {entry}")
        return obj


# 模块级唯一实例
unit_registry = UnitRegistry()
