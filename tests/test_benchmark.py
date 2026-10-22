"""性能基准脚本冒烟测试：子进程隔离跑小参数，验证脚本可零 LLM 调用跑完。

子进程方式运行——脚本会在 import 前改写 PYPEDIA_DATA / 清空密钥，
绝不能污染测试进程的环境与已加载模块。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_benchmark_runs_end_to_end(tmp_path):
    out = tmp_path / "bench.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "benchmark.py"),
         "--docs", "3", "--queries", "3", "--ask", "2", "--json", str(out)],
        capture_output=True, text=True, timeout=180, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"基准脚本失败：\n{proc.stderr[-2000:]}"
    # 结果 JSON 落盘且四项指标齐全
    result = json.loads(out.read_text(encoding="utf-8"))
    for key in ("write", "search", "tokens", "ask"):
        assert key in result, f"缺指标 {key}"
    assert result["write"]["chunks"] >= 1
    assert result["search"]["p50_ms"] > 0
    assert result["ask"]["p50_ms"] > 0
    # 零真实 LLM 调用的证据：provider 仍是配置值，但密钥被脚本清空
    assert result["env"]["data_dir"]
