#!/usr/bin/env python3
"""Run DeluxeCHD from a source checkout (also the PyInstaller entry script)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from deluxechd.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
