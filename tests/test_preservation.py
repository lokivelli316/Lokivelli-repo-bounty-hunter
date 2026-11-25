from radar.config import ensure_layout
from radar.db import connect
from radar.github_client import upsert_repository
from radar.preservation import preservation_status, set_preservation_plan


def _repo():
    return {
        "id": 9001,
        "full_name": "upstream/tool",
        "owner": {"login": "upstream"},
        "fork": False,
        "visibility": "public",
        "default_branch": "main",
        "description": "tool",
        "language": "Python",
        "topics": [],
        "archived": False,
    }


def test_preservation_plan_is_optional_and_persistent(tmp_path):
    home = tmp_path / "h"
    ensure_layout(home)
    with connect(home) as con:
        upsert_repository(con, _repo(), "starred")

    result = set_preservation_plan("upstream/tool", ["bundle", "private_mirror"], home)
    assert result["status"] == "OK"

    state = preservation_status("upstream/tool", home)
    assert state["status"] == "OK"
    assert state["preservation"]["status"] == "PLANNED"
    assert state["preservation"]["requested"] == ["bundle", "private_mirror"]


def test_unknown_preservation_action_is_hold(tmp_path):
    home = tmp_path / "h"
    ensure_layout(home)
    with connect(home) as con:
        upsert_repository(con, _repo(), "starred")

    result = set_preservation_plan("upstream/tool", ["teleport"], home)
    assert result["status"] == "HOLD"
    assert "teleport" in result["error"]
