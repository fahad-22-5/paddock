"""Start PadDock: `python run.py` (see `python run.py --help`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.main import main  # noqa: E402

main()
