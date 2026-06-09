import subprocess
import sys
from pathlib import Path

from scripts.run_hn_pipeline import build_arg_parser


def test_run_hn_pipeline_parser_accepts_days_limit_and_force():
    parser = build_arg_parser()

    args = parser.parse_args(["--days", "7", "--limit", "100", "--force"])

    assert args.days == 7
    assert args.limit == 100
    assert args.force is True


def test_run_hn_pipeline_script_can_be_invoked_directly_with_help():
    script_path = Path(__file__).parents[1] / "scripts" / "run_hn_pipeline.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run the backend P1 Hacker News event pipeline" in result.stdout
