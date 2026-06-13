from __future__ import annotations

import sys


def main() -> int:
    """提示旧 HN pipeline 已被新版 P1-2 入口替代。

    输入：命令行参数，当前不再解析旧参数。
    输出：向 stderr 输出 legacy 提示，并返回非 0 状态码。
    """
    print(
        "legacy entrypoint: scripts/run_hn_pipeline.py is not part of the P1-2 event dossier pipeline. "
        "Use scripts/run_event_pipeline.py instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
