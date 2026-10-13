"""Launch the browser interface from Python."""

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    environment = {**os.environ, "PYTHONPATH": str(root)}
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(root / "amc/web/app.py"),
                "--server.address",
                "127.0.0.1",
                "--browser.gatherUsageStats",
                "false",
                *sys.argv[1:],
            ],
            cwd=root,
            env=environment,
        )
    )
