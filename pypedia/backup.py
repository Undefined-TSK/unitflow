"""数据导出 / 恢复：知识库索引 + 长期记忆 + 画像 + 自进化数据打包为单个 zip。

安全边界（备份文件可能被分享，故按「白名单 + 显式排除」双保险）：
- 白名单打包：仅 BACKUP_ITEMS 内的数据进入备份（新文件默认不进包，不泄漏）；
- 显式排除：鉴权令牌 token / 日志 logs / 锁文件 / 已废弃的旧版向量目录；
- 防 Zip Slip：解包逐条校验，目标路径必须解析后仍位于数据目录内；
- 可回滚：恢复前把现有数据整体挪入 rollback-<时间戳>/，恢复失败可手动搬回。

用法：
    python3.11 -m pypedia.cli backup-export [路径]
    python3.11 -m pypedia.cli backup-import <路径>
API：POST /api/backup/export（下载 zip） · POST /api/backup/import（上传 zip 恢复）
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .memory_store import DATA_DIR

APP_NAME = "pypedia"
SCHEMA = 1  # 备份结构版本；不兼容时 import 拒绝

# 白名单：只有这些数据会进备份包（其余一律排除）
BACKUP_ITEMS = (
    "vector_lancedb",    # RAG 向量索引（LanceDB）
    "mem0_qdrant",       # 长期记忆（qdrant 本地模式）
    "profile.json",      # 用户画像（等级/交互/卡点）
    "reflections.json",  # 自进化：反思记录
    "skills.json",       # 自进化：技能库
    "sources.json",      # 知识源登记（抓取/导入历史）
    "plugins/state.json",  # 插件管理：用户对插件的启停开关态
    "market/installed",  # 市场（P6）：上传导入的 unit 包
    "units.lock",        # 市场（P6）：安装账本
)
# 显式排除（双保险，即便未来误加入白名单也不会打包）
EXCLUDED = {"token", "logs", "mem0_chroma", "vector", ".pypedia.lock"}

MANIFEST = "manifest.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _default_export_path() -> Path:
    out = DATA_DIR / "backups"
    out.mkdir(parents=True, exist_ok=True)
    return out / f"pypedia-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"


def export(path: str | Path | None = None) -> dict:
    """导出数据为 zip。返回 {ok, path, items, size_kb}。"""
    target = Path(path) if path else _default_export_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    items: list[str] = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in BACKUP_ITEMS:
            src = DATA_DIR / name
            if not src.exists() or name in EXCLUDED:
                continue
            if src.is_dir():
                for f in sorted(src.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(DATA_DIR).as_posix())
            else:
                zf.write(src, name)
            items.append(name)
        zf.writestr(MANIFEST, json.dumps({
            "app": APP_NAME, "schema": SCHEMA, "created_at": _now(),
            "data_dir": str(DATA_DIR), "items": items,
        }, ensure_ascii=False, indent=2))
    return {"ok": True, "path": str(target), "items": items,
            "size_kb": round(target.stat().st_size / 1024, 1)}


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> list[str]:
    """防 Zip Slip 解包：只允许落在 dest 内的相对路径。"""
    dest_resolved = dest.resolve()
    written: list[str] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        target = (dest / info.filename).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise ValueError(f"备份包含越界路径，已拒绝：{info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        written.append(info.filename)
    return written


def import_backup(path: str | Path) -> dict:
    """从 zip 恢复数据（替换语义）。恢复前自动快照现有数据到 rollback-<时间戳>/。"""
    src = Path(path)
    if not src.exists():
        return {"ok": False, "error": f"备份文件不存在：{src}"}
    try:
        with zipfile.ZipFile(src) as zf:
            names = zf.namelist()
            if MANIFEST not in names:
                return {"ok": False, "error": "不是有效的 PyPedia 备份（缺 manifest.json）"}
            manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
            if manifest.get("app") != APP_NAME:
                return {"ok": False, "error": f"备份来源不是 {APP_NAME}：{manifest.get('app')}"}
            if int(manifest.get("schema", 0)) > SCHEMA:
                return {"ok": False,
                        "error": f"备份结构版本过新（schema={manifest.get('schema')}），请升级应用后再恢复"}
            payload = [n for n in names if n != MANIFEST]
            # 快照现有数据（可回滚）
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            rollback = DATA_DIR / f"rollback-{stamp}"
            rollback.mkdir(parents=True, exist_ok=True)
            for n in payload:
                cur = DATA_DIR / n
                if cur.exists():
                    dst = rollback / n
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(cur), str(dst))
            written = _safe_extract(zf, DATA_DIR)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "文件损坏或不是 zip 格式"}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "restored": len(written), "items": manifest.get("items", []),
            "rollback": str(rollback), "manifest": manifest}
