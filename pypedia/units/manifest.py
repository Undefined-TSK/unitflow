"""Manifest（plugin.json）加载与契约校验。

P0 冻结的 ``unit.schema.json`` 是唯一真值源。本模块负责：
- 从文件 / 字典加载 manifest；
- 用 JSON Schema 校验（无 jsonschema 时退化为关键字段校验）；
- 解析为 :class:`Manifest` 数据类，供内核其余模块消费。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ManifestError

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "units" / "schema" / "unit.schema.json"
)


def _load_schema() -> dict[str, Any] | None:
    if _SCHEMA_PATH.exists():
        try:
            return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
            raise ManifestError(f"读取契约 schema 失败: {exc}") from exc
    return None


def validate_raw(data: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """校验原始 manifest 字典。优先 JSON Schema，缺失时退化校验关键字段。"""
    schema = schema or _load_schema()
    if schema is not None:
        try:
            from jsonschema import Draft7Validator
        except ImportError:  # pragma: no cover - 环境通常已装
            schema = None
        else:
            errors = sorted(
                Draft7Validator(schema).iter_errors(data),
                key=lambda e: list(e.path),
            )
            if errors:
                msgs = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
                raise ManifestError(f"manifest 不满足契约: {msgs}")
    # 退化校验：保证核心字段存在且类型正确
    for key in ("id", "type", "name", "version"):
        if key not in data:
            raise ManifestError(f"manifest 缺少必填字段: {key}")
    if data["type"] not in ("plugin", "agent", "team"):
        raise ManifestError(f"type 非法: {data['type']}")
    if data["type"] == "agent" and "agent_def" not in data:
        raise ManifestError("type=agent 必须含 agent_def")
    if data["type"] == "team" and "team_def" not in data:
        raise ManifestError("type=team 必须含 team_def")


@dataclass(slots=True)
class Manifest:
    """解析后的 Unit 清单。

    统一承载 plugin / agent / team 三种形态；``form`` 区分模板(类)与成品(对象)。
    """

    id: str
    type: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    min_platform: str | None = None
    engines: dict[str, Any] = field(default_factory=dict)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    default_enabled: bool = False
    switchable: bool = True
    env_gate: str = ""
    apply: str = "immediate"
    form: str = "instance"
    contributions: dict[str, Any] = field(default_factory=dict)
    agent_def: dict[str, Any] | None = None
    team_def: dict[str, Any] | None = None
    node_graph: dict[str, Any] | None = None
    source_path: Path | None = None

    @property
    def is_template(self) -> bool:
        return self.form == "template"

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: Path | None = None) -> "Manifest":
        validate_raw(data)
        known = {
            "id", "type", "name", "version", "description", "author", "license",
            "min_platform", "engines", "dependencies", "default_enabled",
            "switchable", "env_gate", "apply", "form", "contributions",
            "agent_def", "team_def", "node_graph",
        }
        kwargs = {k: data[k] for k in known if k in data}
        return cls(source_path=source_path, **kwargs)

    @classmethod
    def from_file(cls, path: str | Path) -> "Manifest":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"读取 manifest 失败 {p}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestError(f"manifest 顶层必须是对象: {p}")
        return cls.from_dict(raw, source_path=p)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "version": self.version,
            "form": self.form,
        }
        for key in (
            "description", "author", "license", "min_platform", "engines",
            "dependencies", "default_enabled", "switchable", "env_gate",
            "apply", "contributions", "agent_def", "team_def", "node_graph",
        ):
            val = getattr(self, key)
            if val is not None and val != {} and val != []:
                out[key] = val
        return out
