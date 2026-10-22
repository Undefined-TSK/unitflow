"""P6 市场 v1：三类货架（plugin/agent/team）+ 模板/成品双形态 + 上传导入 + 版本门禁。

对齐 master plan §8 / §11(P6) / D4 / D6：
- **安装方式 = 应用内上传导入**（D4）：用户上传 unit 包（``plugin.json`` 裸文件，
  或含 ``plugin.json`` 与资源文件的 zip），解析校验后导入装载；无需联网、
  无需中心注册表，先跑通「上传→装载→运行→卸载」全链路；
- **版本门禁**：安装时校验 ``min_platform``（平台版本）与 ``dependencies``
  （依赖 unit id + 版本区间），不符则拒收并提示，不落盘；
- **模板/成品双形态**（D6）：由 manifest 的 ``form`` 字段声明
  （template=模板/类，instance=成品对象），货架视图原样呈现；
- **可回滚资产管理**：安装目录 ``market/installed/<id>/`` + ``units.lock``
  记录账本；卸载仅允许账本内的 unit（内置/示例 unit 不在账本 → 拒卸，
  防止把内核卸没了）。

安全边界（v1）：
- 防 Zip Slip（解包逐条校验目标路径必须位于安装目录内）+ 拒绝符号链接；
- 上传体积/文件数上限（``MAX_UPLOAD_BYTES`` / ``MAX_UPLOAD_FILES``）；
- manifest 必须过 unit.schema.json 校验（含 ``form``）；
- **不执行上传内容**：装载只注册 manifest 与解析入口（与 UnitLoader 语义一致），
  Python 入口的沙箱化属后续（§7 Docker），v1 记录在案。
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import LoaderError, ManifestError
from .loader import UnitLoader
from .manifest import Manifest
from .registry import UnitRegistry

log = logging.getLogger("pypedia.units.market")

# 平台版本单一真值源（app.py 的 FastAPI version 亦引用此处）
PLATFORM_VERSION = "0.2.0"

LOCK_SCHEMA = 1                 # units.lock 结构版本（不兼容时拒读并提示重建）
MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 上传包体积上限 10MB
MAX_UPLOAD_FILES = 200                 # 上传包文件数上限
MANIFEST_NAME = "plugin.json"


class MarketError(ValueError):
    """市场操作失败（门禁不过/包非法/账目不符），端点层转 4xx。"""


# ---------- 版本比较（零依赖：x.y.z → 元组比较；区间支持 *, >=, >, <=, <, ==） ---------- #
def parse_version(version: str) -> tuple[int, ...]:
    """``"1.2.3"`` → ``(1, 2, 3)``；非 semver 抛 MarketError。"""
    parts = str(version).strip().split(".")
    if not 1 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
        raise MarketError(f"不是合法的 x.y.z 版本号：{version!r}")
    return tuple(int(p) for p in parts)


def version_ge(a: str, b: str) -> bool:
    return parse_version(a) >= parse_version(b)


_OPS = (">=", "<=", "==", ">", "<")


def _match_clause(have: tuple[int, ...], clause: str) -> bool:
    """单个比较式：``>=1.0.0`` / ``1.0.0``（无比较符=精确匹配）。"""
    for op in _OPS:
        if clause.startswith(op):
            bound = parse_version(clause[len(op):].strip())
            if op == ">=":
                return have >= bound
            if op == "<=":
                return have <= bound
            if op == "==":
                return have == bound
            if op == ">":
                return have > bound
            return have < bound
    return have == parse_version(clause)


def version_satisfies(version: str, spec: str) -> bool:
    """版本区间匹配：``*`` 恒真；否则逗号分段（AND），每段一个比较式。"""
    spec = (spec or "*").strip()
    if spec in ("", "*"):
        return True
    have = parse_version(version)
    for clause in spec.split(","):
        if not clause.strip():
            raise MarketError(f"版本区间含空段：{spec!r}")
        if not _match_clause(have, clause.strip()):
            return False
    return True


def check_platform_gate(manifest: Manifest) -> None:
    """min_platform 门禁：平台版本低于要求 → 拒收（缺省 0.0.0 不门禁）。"""
    required = manifest.min_platform or "0.0.0"
    if not version_ge(PLATFORM_VERSION, required):
        raise MarketError(
            f"平台版本不满足：本 unit 要求 min_platform>={required}，"
            f"当前平台 {PLATFORM_VERSION}，请升级平台后重试")


def check_dependencies(manifest: Manifest, registry: UnitRegistry) -> None:
    """dependencies 门禁：依赖 unit 未注册或版本不满足区间 → 拒收。"""
    for dep in manifest.dependencies:
        dep_id = dep.get("id", "")
        spec = dep.get("version", "*") or "*"
        unit = registry.get_unit(dep_id)
        if unit is None:
            raise MarketError(f"依赖的 unit 未安装：{dep_id}")
        if not version_satisfies(unit.version, spec):
            raise MarketError(
                f"依赖版本不满足：{dep_id} 需要 {spec}，"
                f"已安装 {unit.version}")


# ---------- 上传包解析（zip / 裸 json；Zip Slip 防护） ---------- #
@dataclass(frozen=True, slots=True)
class UploadPackage:
    """解析后的上传包：manifest 原始数据 + 资源文件（相对路径 → 字节）。"""

    manifest_raw: dict[str, Any]
    resources: dict[str, bytes]

    @property
    def unit_id(self) -> str:
        return str(self.manifest_raw.get("id", ""))


def parse_upload(data: bytes, filename: str = "") -> UploadPackage:
    """上传字节 → 校验形状的 UploadPackage（不注册、不落盘）。"""
    if not data:
        raise MarketError("上传文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise MarketError(
            f"上传包超过体积上限：{len(data) / 1024 / 1024:.1f}MB "
            f"> {MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    name = (filename or "").lower()
    if name.endswith(".json"):
        return _parse_bare_json(data)
    if name.endswith(".zip"):
        return _parse_zip(data)
    # 扩展名缺失/不认识：按内容嗅探（zip 魔数 PK\x03\x04）
    if data[:4] == b"PK\x03\x04":
        return _parse_zip(data)
    if data.lstrip()[:1] in (b"{",):
        return _parse_bare_json(data)
    raise MarketError("不支持的上传格式：仅支持 .zip 包或 .json manifest")


def _parse_bare_json(data: bytes) -> UploadPackage:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketError(f"manifest 不是合法 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise MarketError("manifest 顶层必须是对象")
    return UploadPackage(manifest_raw=raw, resources={})


def _parse_zip(data: bytes) -> UploadPackage:
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise MarketError(f"zip 包损坏或不是合法 zip：{exc}") from exc
    with zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        if not names:
            raise MarketError("zip 包内没有文件")
        if len(names) > MAX_UPLOAD_FILES:
            raise MarketError(
                f"zip 包文件数超限：{len(names)} > {MAX_UPLOAD_FILES}")
        manifest_name = _locate_manifest(names)
        # 嵌套布局（<dir>/plugin.json）：整包剥掉顶层目录，装出来是平铺的
        prefix = manifest_name.rsplit("/", 1)[0] + "/" if "/" in manifest_name else ""
        resources = _read_zip_resources(zf, prefix)
    if MANIFEST_NAME not in resources:
        raise MarketError(f"包内未找到 {MANIFEST_NAME}")
    try:
        raw_manifest = json.loads(resources.pop(MANIFEST_NAME).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketError(f"manifest 不是合法 JSON：{exc}") from exc
    if not isinstance(raw_manifest, dict):
        raise MarketError("manifest 顶层必须是对象")
    return UploadPackage(manifest_raw=raw_manifest, resources=resources)


def _read_zip_resources(zf: zipfile.ZipFile, prefix: str) -> dict[str, bytes]:
    """逐个读取 zip 条目为「相对路径 → 字节」（体积累计上限 + Zip Slip 防护）。"""
    resources: dict[str, bytes] = {}
    total = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = _safe_relname(info.filename)
        if prefix:
            if not rel.startswith(prefix):
                continue  # 顶层散落文件与 unit 目录无关，忽略
            rel = rel[len(prefix):]
        total += info.file_size
        if total > MAX_UPLOAD_BYTES:
            raise MarketError("zip 包解压后超过体积上限")
        try:
            resources[rel] = zf.read(info)
        except (zipfile.BadZipFile, RuntimeError) as exc:
            # 条目级 CRC/加密损坏：转 400，不让异常裸奔成 500
            raise MarketError(f"zip 条目读取失败（损坏或加密）：{rel}：{exc}") from exc
    return resources


def _locate_manifest(names: list[str]) -> str:
    """定位 plugin.json：根目录优先，否则唯一的一层子目录；歧义/缺失 → 拒收。"""
    if MANIFEST_NAME in names:
        return MANIFEST_NAME
    candidates = sorted({n.split("/", 1)[0] for n in names
                         if "/" in n and n.endswith(MANIFEST_NAME)})
    nested = [f"{c}/{MANIFEST_NAME}" for c in candidates]
    nested = [n for n in nested if n in names]
    if len(nested) == 1:
        return nested[0]
    if not nested:
        raise MarketError(f"包内未找到 {MANIFEST_NAME}")
    raise MarketError(f"包内有多个 {MANIFEST_NAME}，无法确定入口：{nested}")


def _safe_relname(name: str) -> str:
    """Zip Slip 防护：规整为相对路径，越界/绝对路径 → 拒收。"""
    pure = Path(name)
    if pure.is_absolute() or ".." in pure.parts or name.startswith("/"):
        raise MarketError(f"上传包含越界路径，已拒绝：{name}")
    return pure.as_posix()


# ---------- 账本（units.lock） ---------- #
@dataclass(frozen=True, slots=True)
class InstallResult:
    """一次安装的结果（货架视图/端点响应的数据形状）。"""

    unit_id: str
    name: str
    version: str
    type: str
    form: str
    path: str


class MarketStore:
    """市场存储：上传导入 → 装载注册；卸载仅限账本内 unit。

    ``runtime_registry``（P6 双注册）：平台存在两个注册表单例——
    ``unit_registry``（内核/账本主表）与 ``plugin_registry``（运行态门控表，
    agent 工具循环 / 提示词规约 / is_enabled 消费方的唯一真值源）。
    市场 unit 只进主表会「装得上但看不见」（工具/规约不注入），故安装 /
    恢复 / 卸载对两张表同步操作；门控查询（enabled/env_blocked）也以
    运行态表为准，防止两个视图对同一开关各说各话。
    """

    def __init__(self, registry: UnitRegistry, loader: UnitLoader, *,
                 runtime_registry: UnitRegistry | None = None,
                 installed_dir: str | Path, lock_path: str | Path) -> None:
        self.registry = registry
        self.loader = loader
        self.runtime_registry = runtime_registry or registry
        self._registries: list[UnitRegistry] = (
            [registry] if runtime_registry is None or runtime_registry is registry
            else [registry, runtime_registry])
        # 装载器的安装目录即市场的安装目录：loader.install 以自身
        # installed_dir 为复制目标，不同步会导致「注册了但文件没落盘」。
        self.installed_dir = Path(installed_dir)
        self.loader.installed_dir = self.installed_dir
        self.lock_path = Path(lock_path)
        self.installed_dir.mkdir(parents=True, exist_ok=True)

    # —— 双注册辅助（幂等）—— #
    def _register_everywhere(self, manifest: Manifest) -> None:
        """把 unit 注册进全部目标表（主表 + 运行态表；已注册则跳过）。"""
        for reg in self._registries:
            if reg.get_unit(manifest.id) is not None:
                continue  # 已注册（loader.install 已写主表 / 重复恢复），幂等
            reg.register(manifest, quiet=True)

    def _unregister_everywhere(self, unit_id: str) -> None:
        for reg in self._registries:
            reg.unregister(unit_id)

    # —— 账本读写 —— #
    def load_lock(self) -> dict[str, Any]:
        """读 units.lock；损坏/版本过新 → MarketError（提示手动处理，不静默重建）。"""
        if not self.lock_path.exists():
            return {"schema": LOCK_SCHEMA, "units": []}
        try:
            raw = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MarketError(f"units.lock 损坏，请手动修复或删除：{exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema") != LOCK_SCHEMA:
            raise MarketError(
                f"units.lock 结构版本不兼容（schema={raw.get('schema')}，"
                f"期望 {LOCK_SCHEMA}），请手动迁移")
        units = raw.get("units")
        if not isinstance(units, list):
            raise MarketError("units.lock 的 units 必须是数组")
        return raw

    def _save_lock(self, entries: list[dict[str, Any]]) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.lock_path.with_suffix(".lock.tmp")
        tmp.write_text(json.dumps({"schema": LOCK_SCHEMA, "units": entries},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.lock_path)  # 原子替换，避免写一半损坏

    def lock_entries(self) -> list[dict[str, Any]]:
        return list(self.load_lock()["units"])

    # —— 查询：三类货架（lock 账目 + 注册态合并） —— #
    def list_installed(self) -> list[dict[str, Any]]:
        """已安装 unit 清单（含启用态/部署态拦截——与设置页同一门控来源）。"""
        out: list[dict[str, Any]] = []
        for entry in self.lock_entries():
            uid = entry.get("id", "")
            unit = self.registry.get_unit(uid)
            row = dict(entry)
            row["registered"] = unit is not None
            if unit is not None:
                # 门控真值源取运行态表（plugin_registry）：与 agent 工具循环 /
                # 提示词规约消费的是同一判据，不再读主表可能陈旧的用户态。
                row["enabled"] = self.runtime_registry.is_enabled(uid)
                row["env_blocked"] = self.runtime_registry.env_blocked(uid)
            out.append(row)
        return out

    # —— 安装（上传导入全链路） —— #
    def install_upload(self, data: bytes, filename: str = "") -> InstallResult:
        pkg = parse_upload(data, filename)
        # 1. schema 校验（含 form 双形态）
        try:
            manifest = Manifest.from_dict(pkg.manifest_raw)
        except ManifestError as exc:
            raise MarketError(f"manifest 不满足契约：{exc}") from exc
        # 2. 版本门禁（平台 + 依赖），不过不落盘
        check_platform_gate(manifest)
        check_dependencies(manifest, self.registry)
        # 3. 重复安装防护（任一注册表或账本已存在同 id → 冲突）
        for reg in self._registries:
            if reg.get_unit(manifest.id) is not None:
                raise MarketError(
                    f"unit「{manifest.id}」已在注册表中（可能是内置/示例或已安装），"
                    f"如为重装请先卸载")
        if any(e.get("id") == manifest.id for e in self.lock_entries()):
            raise MarketError(
                f"unit「{manifest.id}」已在账本中但未注册（异常态），"
                f"请先卸载再重装")
        # 4. 落盘到暂存目录 → 门禁全过才进 installed_dir（loader.install 复制+注册）
        tmp_dir = Path(tempfile.mkdtemp(prefix="pypedia-market-"))
        try:
            _materialize(tmp_dir, pkg)
            installed = self.loader.install(tmp_dir)
        except LoaderError as exc:
            raise MarketError(f"装载失败：{exc}") from exc
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        # 4.5 双注册运行态表：装上即可被 agent 工具循环/提示词规约看到
        self._register_everywhere(installed)
        # 5. 记账（写入失败则整体回滚，不留「装了没记账」的残迹）
        try:
            entries = [e for e in self.lock_entries() if e.get("id") != manifest.id]
            entries.append({
                "id": installed.id,
                "version": installed.version,
                "type": installed.type,
                "form": installed.form,
                "name": installed.name,
                "source": filename or "upload",
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            self._save_lock(entries)
        except OSError as exc:
            self._unregister_everywhere(installed.id)
            shutil.rmtree(self.installed_dir / installed.id, ignore_errors=True)
            raise MarketError(f"账本写入失败，已回滚本次安装：{exc}") from exc
        return InstallResult(unit_id=installed.id, name=installed.name,
                             version=installed.version, type=installed.type,
                             form=installed.form, path=str(self.installed_dir))

    # —— 卸载（仅账本内；内置/示例拒卸） —— #
    def uninstall(self, unit_id: str) -> None:
        entries = self.lock_entries()
        if not any(e.get("id") == unit_id for e in entries):
            raise MarketError(
                f"unit「{unit_id}」不是市场安装的（不在 units.lock 账本），拒绝卸载")
        self.loader.uninstall(unit_id)        # 删目录 + 注销主表
        self._unregister_everywhere(unit_id)  # 运行态表注销（幂等）
        self._save_lock([e for e in entries if e.get("id") != unit_id])

    # —— 启动恢复：扫描 installed_dir 重新注册（幂等；坏包 warning 跳过） —— #
    def restore_installed(self) -> list[str]:
        """进程重启后把已安装 unit 重新注册进各注册表（不复制、只扫描）。"""
        restored: list[str] = []
        for manifest_path in sorted(self.installed_dir.glob("*/plugin.json")):
            try:
                manifests = self.loader.scan(manifest_path.parent)
            except (LoaderError, ManifestError) as exc:
                # 单条坏包不阻断启动（用户可卸载重装）
                log.warning("跳过无法恢复的市场 unit（%s）：%s",
                            manifest_path.parent.name, exc)
                continue
            for m in manifests:
                self._register_everywhere(m)  # 主表 loader 已写；运行态表补齐
            restored.append(manifest_path.parent.name)
        return restored


def _materialize(dest: Path, pkg: UploadPackage) -> None:
    """把上传包写到暂存目录（loader.install 以此为源复制进 installed_dir）。"""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / MANIFEST_NAME).write_text(
        json.dumps(pkg.manifest_raw, ensure_ascii=False, indent=2),
        encoding="utf-8")
    for rel, blob in sorted(pkg.resources.items()):
        target = dest / rel
        if target.resolve().parent != dest.resolve() and \
                dest.resolve() not in target.resolve().parents:
            raise MarketError(f"资源路径越界，已拒绝：{rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)


def default_paths() -> tuple[Path, Path]:
    """installed_dir 与 lock_path 的缺省位置（数据目录下）。"""
    import os

    base = Path(os.getenv("PYPEDIA_DATA",
                          str(Path.home() / ".pypedia")))
    return base / "market" / "installed", base / "units.lock"
