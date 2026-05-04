from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTO_SRC = ROOT / "prototypes" / "flowweaver_phase3" / "src"
if str(PROTO_SRC) not in sys.path:
    sys.path.insert(0, str(PROTO_SRC))
