#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent 自用账户状态自查脚本（不对外交付报告）。
Console 网关令牌配置后，一次性拉全：
  - 免费额度（bl usage free --all）
  - 统一概览（bl usage summary）
  - Token Plan 付费套餐（bl usage token-plan）
  - Coding Plan 付费套餐（bl usage coding-plan）
  - 各模型用量统计（bl usage stats）
未配置 Console 时退回 bl quota list（仅速率上限，无免费余量）。
重点盯：text-embedding-v3（摄入吃得多）、qwen-plus（对话主力）。
用法：python3 check_bailian_quota.py
"""
from __future__ import annotations

import json
import subprocess
from typing import Optional

PYPEDIA_MODELS = (
    "text-embedding-v3",
    "qwen-plus",
    "qwen3-rerank",
    "qwen3-coder",
    "qwen-turbo",
    "qwen-max",
)


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


def _dump(title: str, rc: int, out: str, err: str) -> None:
    print(f"\n===== {title} (rc={rc}) =====")
    if rc == 0 and out.strip():
        # 尝试只抽 PyPedia 相关模型，其余折叠
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            items = data.get("items") or data.get("models") or []
            if isinstance(items, list) and items:
                want = set(PYPEDIA_MODELS)
                shown, hidden = [], 0
                for it in items:
                    name = str(it.get("model") or it.get("name") or it.get("id") or "")
                    if name in want:
                        shown.append(it)
                    else:
                        hidden += 1
                if shown:
                    print(f"[PyPedia 关注模型 {len(shown)} 项]")
                    print(json.dumps(shown, ensure_ascii=False, indent=2))
                if hidden:
                    print(f"[其余 {hidden} 项已折叠，用 --all 可展开]")
                return
        print(out[:5000])
    else:
        print(err or "(空)")


def main() -> None:
    # 0) Console 是否可用
    rc, out, _ = _run(["bl", "auth", "status", "--output", "json"])
    console_ok = ("console" in out.lower() and "not configured" not in out.lower())
    if not console_ok:
        print("=== [Console 未配置] 退回 bl quota list（仅速率上限，无免费/付费余量）===")
        rc, out, err = _run(["bl", "quota", "list", "--output", "json"])
        _dump("quota list", rc, out, err)
        print("\n提示：在手机 Termux 跑 `bl auth login --console` 完成授权后，本脚本即可拉全免费+付费套餐。")
        return

    for title, sub in [
        ("免费额度 free --all", ["usage", "free", "--all"]),
        ("统一概览 summary", ["usage", "summary"]),
        ("Token Plan 付费套餐", ["usage", "token-plan"]),
        ("Coding Plan 付费套餐", ["usage", "coding-plan"]),
        ("各模型用量 stats", ["usage", "stats"]),
    ]:
        rc, out, err = _run(["bl", *sub, "--output", "json"])
        _dump(title, rc, out, err)


if __name__ == "__main__":
    main()
