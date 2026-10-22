"""命令行入口：ask（单次）/ chat（多轮交互）/ status（配置）。基于 typer。"""
from __future__ import annotations

import json

import typer

from .config import settings
from .engine import PyPediaEngine
from .levels import ensure_level
from .memory import Session

app = typer.Typer(help="PyPedia 核心引擎 CLI", no_args_is_help=True,
                 pretty_exceptions_show_locals=False)


def _print_result(r: dict) -> None:
    lv = r["level"]
    conf = r["confidence"]
    typer.echo("=" * 64)
    typer.echo(f"问题：{r['query']}")
    typer.echo(f"等级：{lv['n']}（{lv['t']}） · 模型通道：{r['provider']}"
               + (" · 多轮" if r["multi_turn"] else ""))
    typer.echo("-" * 64)
    typer.echo(f"置信度：{conf['score']}/100 — {conf['level_label']}")
    typer.echo("  拆解：主源命中 {primary_hit} + 跨源一致 {cross_source} + 新鲜度 {freshness}".format(
        **conf["breakdown"]))
    if conf.get("reason"):
        typer.echo(f"  · {conf['reason']}")
    typer.echo("-" * 64)
    ctx = r.get("context") or {}
    if ctx.get("compressed"):
        typer.echo(f"上下文压缩：{ctx['total_tokens']} → {ctx['kept_tokens']} tokens"
                   f"（折叠 {ctx['dropped_turns']} 轮为摘要）")
    if r.get("reasoning_plan"):
        typer.echo("分步思路：\n" + r["reasoning_plan"])
        typer.echo("-" * 64)
    typer.echo("检索级联：")
    for st in r["cascade"].stages:
        hits = "、".join(f"{c.title}({c.score})" for c in st.chunks) or "（无命中）"
        typer.echo(f"  {st.name}  [{st.role_label}]：{hits}")
    typer.echo("-" * 64)
    typer.echo("回答：")
    typer.echo(r["answer"])
    review = r.get("review") or {}
    if review.get("verdict") == "revise":
        typer.echo("-" * 64)
        typer.echo("【二审意见】" + "；".join(review.get("notes", [])))
        if review.get("revised"):
            typer.echo("【修订版】\n" + review["revised"])
    typer.echo("=" * 64)


@app.command(help="单次问答")
def ask(
    question: str = typer.Argument(..., help="你的问题"),
    level: int = typer.Option(3, "--level", min=1, max=5, help="用户等级 1~5（默认 3）"),
    provider: str = typer.Option(None, "--provider", help="mock | bailian | ollama"),
) -> None:
    eng = PyPediaEngine(provider=provider)
    lv = ensure_level(level)
    sess = Session(level=lv)
    _print_result(eng.ask(question, level=lv, session=sess))


@app.command(help="多轮交互问答")
def chat(
    level: int = typer.Option(3, "--level", min=1, max=5, help="用户等级 1~5（默认 3）"),
    provider: str = typer.Option(None, "--provider", help="mock | bailian | ollama"),
) -> None:
    eng = PyPediaEngine(provider=provider)
    lv = ensure_level(level)
    sess = Session(level=lv)
    typer.echo(f"PyPedia 多轮问答（等级 L{lv}）。输入 exit/quit 结束。\n")
    while True:
        try:
            q = typer.prompt("你", prompt_suffix="> ").strip()
        except (EOFError, KeyboardInterrupt, typer.Abort):
            typer.echo("\n再见。")
            break
        if not q:
            continue
        if q.lower() in {"exit", "quit", "q"}:
            typer.echo("再见。")
            break
        r = eng.ask(q, level=lv, session=sess)
        typer.echo(f"\n[置信度 {r['confidence']['score']}/100 · {r['provider']}]")
        typer.echo(r["answer"])
        typer.echo()


@app.command(help="查看运行配置")
def status() -> None:
    typer.echo(json.dumps(settings.describe(), ensure_ascii=False, indent=2))


@app.command(help="迁移旧版 chroma 记忆数据到 qdrant 本地库（一次性，幂等）")
def memory_migrate() -> None:
    from .memory_migrate import migrate

    r = migrate()
    typer.echo(f"[{r['status']}] {r['detail']}")
    if r["status"] == "error":
        raise typer.Exit(1)


@app.command(help="导出数据备份为 zip（知识库索引/记忆/画像/自进化；不含令牌与日志）")
def backup_export(
    path: str = typer.Argument(None, help="导出路径；缺省为数据目录 backups/ 下带时间戳的文件"),
) -> None:
    from .backup import export

    r = export(path)
    if r.get("ok"):
        typer.echo(f"已导出 {len(r['items'])} 项 → {r['path']}（{r['size_kb']}KB）")
        for i in r["items"]:
            typer.echo(f"  · {i}")
    else:
        typer.echo(f"导出失败：{r.get('error')}", err=True)
        raise typer.Exit(1)


@app.command(help="从备份 zip 恢复数据（替换语义；恢复前自动快照，可回滚）")
def backup_import(path: str = typer.Argument(..., help="备份 zip 路径")) -> None:
    from .backup import import_backup

    r = import_backup(path)
    if r.get("ok"):
        typer.echo(f"已恢复 {r['restored']} 个文件；恢复项：{', '.join(r['items'])}")
        typer.echo(f"原数据快照（可回滚）：{r['rollback']}")
        typer.echo("建议重启服务使索引生效。")
    else:
        typer.echo(f"恢复失败：{r.get('error')}", err=True)
        raise typer.Exit(1)


@app.command(help="列出预置权威资料源清单（Python 官方文档 / CPython / 官方论坛）")
def preset_list() -> None:
    from .ingest import load_preset_sources

    srcs = load_preset_sources()
    if not srcs:
        typer.echo("清单为空或不可读：pypedia/data/preset_sources.json", err=True)
        raise typer.Exit(1)
    typer.echo(f"预置资料源 {len(srcs)} 项（联网抓取开关 ENABLE_WEB_FETCH="
               f"{settings.ENABLE_WEB_FETCH}）：")
    for s in srcs:
        typer.echo(f"  [{s['role']:<13}] {s['kind']:<6} {s['title']}")
        typer.echo(f"      {s['target']}")


@app.command(help="导入预置权威资料源（幂等；--force 强制重抓）")
def preset_import(force: bool = typer.Option(False, "--force", help="忽略已存在记录，强制重新抓取")) -> None:
    from .ingest import ingest_preset_sources

    r = ingest_preset_sources(force=force)
    if r.get("disabled"):
        typer.echo("已关闭（PRESET_SOURCES_ENABLE=false），未执行。", err=True)
        raise typer.Exit(1)
    typer.echo(f"清单 {r['total']} 项 → 入库 {r['added']} · 跳过(已存在) {r['skipped']} "
               f"· 未成功 {r['failed']}")
    if r["failed"] and not r["web_fetch"]:
        typer.echo("提示：未开启联网抓取（.env 设 ENABLE_WEB_FETCH=true 后重试），"
                   "当前已登记为 pending，离线语料仍可用。")


if __name__ == "__main__":
    app()
