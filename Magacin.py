"""Compatibility launcher. All active writes use the central web backend."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().with_name("launch_web.py")), run_name="__main__")
