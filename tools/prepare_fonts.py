"""Prepare pinned font assets for local development."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'backend/tools/prepare_fonts.py'), run_name='__main__')
