import subprocess
import sys
from pathlib import Path

from scripts.run_hn_pipeline import build_arg_parser


def test_run_hn_pipeline_parser_accepts_days_limit_and_force():
    """验证本地入口脚本参数解析。

    输入：`--days 7 --limit 100 --force`。
    输出：断言 argparse 解析结果正确。
    """
    parser = build_arg_parser()

    args = parser.parse_args(["--days", "7", "--limit", "100", "--force"])

    assert args.days == 7
    assert args.limit == 100
    assert args.force is True


def test_run_hn_pipeline_script_can_be_invoked_directly_with_help():
    """验证脚本可以被文件路径直接运行。

    输入：`python scripts/run_hn_pipeline.py --help`。
    输出：断言进程返回 0 且输出帮助文本。
    """
    script_path = Path(__file__).parents[1] / "scripts" / "run_hn_pipeline.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run the backend P1 Hacker News event pipeline" in result.stdout
