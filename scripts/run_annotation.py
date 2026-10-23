"""Launch annotation only, without Ollama or model downloads."""

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(root / "amc/web/annotate.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "18502",
                "--browser.gatherUsageStats",
                "false",
                *sys.argv[1:],
            ],
            cwd=root,
            env={**os.environ, "PYTHONPATH": str(root)},
        )
    )
