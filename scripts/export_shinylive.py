#!/usr/bin/env python3
"""Export the Barfbow app with only its intentional ShinyLive inputs."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_FILES = (
    Path("app.py"),
    Path("barfbow.py"),
    Path("color_names_meodai.csv"),
    Path("requirements.txt"),
    Path("docs/barfbow_logo1.png"),
    Path("docs/barfbow_logo2.png"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a static, browser-side Barfbow site with ShinyLive."
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="_site",
        type=Path,
        help="empty or nonexistent output directory (default: _site)",
    )
    return parser.parse_args()


def main() -> None:
    output = parse_args().output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite nonempty output directory: {output}")

    missing = [str(path) for path in APP_FILES if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"Missing ShinyLive app files: {', '.join(missing)}")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="barfbow-shinylive-") as temp_dir:
        app_dir = Path(temp_dir)
        for relative_path in APP_FILES:
            destination = app_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative_path, destination)

        subprocess.run(
            ["shinylive", "export", str(app_dir), str(output)],
            check=True,
        )


if __name__ == "__main__":
    main()
