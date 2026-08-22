from __future__ import annotations

import copy
import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = AGENT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from osekkai_freebusy import load_freebusy  # noqa: E402
from osekkai_opportunity_sync import load_opportunities  # noqa: E402
from osekkai_profile import parse_datetime, seed_demo_profile  # noqa: E402


USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
NOW = parse_datetime("2019-02-23T10:00:00+09:00")


def ready_profile(user_id: str = USER_ID):
    profile = seed_demo_profile(user_id, NOW)
    profile["socialBattery"] = 20
    profile["maxSocialIntensity"] = 1
    profile["currentSignals"] = {
        "interventionHint": "consider_push",
        "currentReceptivity": 0.8,
        "safety": {"level": "normal", "requiresHumanSupport": False},
        "observedAt": NOW.isoformat(),
    }
    return profile


def demo_inputs():
    return copy.deepcopy(load_freebusy("demo")), copy.deepcopy(load_opportunities("demo"))
