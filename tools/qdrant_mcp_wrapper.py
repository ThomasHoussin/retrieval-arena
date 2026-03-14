"""Wrapper that reads search_bench config and launches mcp-server-qdrant with the right env vars."""

import argparse
import atexit
import os
import signal
import subprocess
import sys

from config import load_config


def main():
    parser = argparse.ArgumentParser(description="Qdrant MCP wrapper (config-driven)")
    parser.add_argument("--config", help="Path to search_bench.json config file")
    args = parser.parse_args()

    cfg = load_config(args.config)

    env = os.environ.copy()
    env["QDRANT_URL"] = cfg["qdrant_url"]
    env["COLLECTION_NAME"] = cfg["qdrant_collection_name"]
    env["EMBEDDING_MODEL"] = cfg["embedding_model"]

    proc = subprocess.Popen(
        ["uvx", "mcp-server-qdrant"],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )

    # Forward signals and ensure cleanup
    def _cleanup():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    atexit.register(_cleanup)

    def _signal_handler(signum, _frame):
        if proc.poll() is None:
            proc.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _signal_handler)

    sys.exit(proc.wait())


if __name__ == "__main__":
    main()
