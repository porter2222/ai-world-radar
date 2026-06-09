from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from worker.llm_client import LLMClient


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke check local LLMClient config.")
    parser.add_argument("--call", action="store_true", help="Actually call the configured LLM provider.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    client = LLMClient()
    print(f"provider={client.provider}")
    print(f"model={client.model}")
    print(f"base_url={client.base_url}")
    print(f"api_key_present={bool(client.api_key)}")

    if args.call:
        print(client.chat("Please reply with exactly: pong"))
    else:
        print("config_ok=true")
        print("real_call=false")
        print("Use --call to send a real LLM request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
