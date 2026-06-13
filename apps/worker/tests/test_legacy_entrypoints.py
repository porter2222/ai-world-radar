import subprocess
import sys


def test_old_hn_pipeline_entrypoint_fails_fast_with_legacy_message():
    """验证旧 HN pipeline 入口不会继续误跑旧主链路。

    输入：直接执行 scripts/run_hn_pipeline.py。
    输出：脚本非 0 退出，并提示改用 scripts/run_event_pipeline.py。
    """
    result = subprocess.run(
        [sys.executable, "scripts/run_hn_pipeline.py", "--days", "7", "--limit", "1"],
        check=False,
        text=True,
        capture_output=True,
    )

    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "legacy" in output.lower()
    assert "run_event_pipeline.py" in output
