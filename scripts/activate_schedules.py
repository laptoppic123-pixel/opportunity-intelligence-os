"""Prepare scheduler YAML only after owner activation; never pushes or changes account settings."""

import argparse
from pathlib import Path
from opportunity_intelligence.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--confirm-activation", action="store_true", required=True)
args = parser.parse_args()
settings = Settings.load()
settings.require_live()
root = Path(__file__).resolve().parents[1]
source = root / ".github/workflows/research-scheduled.yml.disabled"
(root / ".github/workflows/research-scheduled.yml").write_text(
    source.read_text(encoding="utf-8"), encoding="utf-8"
)
print(
    "Prepared scheduler locally. Enable OI_SCHEDULES_ENABLED only after approved integration tests, then review/push."
)
