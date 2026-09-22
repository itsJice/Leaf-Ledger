"""Make `schedule`, `rules` and `validate` importable without real client data.

What importing those modules touches, and how it is neutralised here:

* `schedule.py` calls `client_config_loader.load()` at import time, which
  reads `scheduler/client_config.json` (gitignored: real client names) and
  raises SystemExit when it is missing. The loader resolves the file through
  its module-level `PATH`, so before anything imports `schedule` we point
  `client_config_loader.PATH` at a SYNTHETIC config written to a temp dir.
  The real loader code still runs; it just never sees real data.
* `schedule.py` derives the season from today's date unless `TBDG_SEASON`
  is set, and only has a SEASON_CONFIG block for 2026. The tests pin
  `TBDG_SEASON=2026` (an override schedule.py already supports) so the
  calendar they assert against is deterministic.
* Nothing else is read at import: `schedule.load()` / `load_overrides()`
  (cache/*.json, overrides.json) only run from `main()`, which tests never
  call, and `validate` no longer reads cache/schedule.json on import.

Every name below is invented. Keys are exactly the ones read at import time
by schedule.py (drop_clients, clubs) and rules.py (same_day_groups,
force_first, pins, no_install), plus single_crew_priority for validate R5.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile

SCHEDULER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCHEDULER_DIR not in sys.path:
    sys.path.insert(0, SCHEDULER_DIR)

os.environ["TBDG_SEASON"] = "2026"

SYNTHETIC_CLIENT_CONFIG = {
    "drop_clients": {"Test Client Dropped": "synthetic: no install this year"},
    "clubs": {
        "nicklaus": "Test Club N",
        "outdoor": "Test Club O",
        "fazio": "Test Club F",
        "wcc_nov30": ["Test Club W1", "Test Club W2"],
        "wcc_players": "Test Club P",
        "royal": "Test Club R",
    },
    "same_day_groups": [
        {"label": "Test Group AB", "names": ["Test Client A", "Test Client B"],
         "first": "Test Client A", "min_crews": 1},
    ],
    "force_first": {"Test Client A": "synthetic: boxes stored here"},
    "pins": {"Test Client C": "2026-11-17"},
    "no_install": ["Test Client Dropped"],
    "single_crew_priority": {"client_name": "Test Client Priority",
                             "category": "Test Priority"},
}

_tmpdir = tempfile.mkdtemp(prefix="tbdg-synthetic-config-")
atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)
_cfg_path = os.path.join(_tmpdir, "client_config.json")
with open(_cfg_path, "w") as _f:
    json.dump(SYNTHETIC_CLIENT_CONFIG, _f)

import client_config_loader  # noqa: E402

assert "schedule" not in sys.modules, "schedule imported before the config stub"
client_config_loader.PATH = _cfg_path
