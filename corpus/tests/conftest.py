"""Put the repo root and engine/ on sys.path, as the other suites do."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for candidate in (ROOT, ROOT / "engine"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
