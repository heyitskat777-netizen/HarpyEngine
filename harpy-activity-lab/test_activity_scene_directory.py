"""Check saved scene locations and private handover metadata."""

from types import SimpleNamespace

import pytest
from activity_records import RELAY, ActivityRecords, scene_locations

from girlframe.services.onboarding import WorkflowError


@pytest.fixture
def directory(tmp_path):
    host = SimpleNamespace(user_id=1)
    visitor = SimpleNamespace(user_id=2)
    return ActivityRecords(tmp_path / "records.sqlite3", host.user_id), host, visitor


def test_optional_locations_reuse_names_and_preserve_legacy_ids(directory):
    records, host, _ = directory
    assert scene_locations(records.directory(host, {})) == []
    old = records.create_room(host, "old", {"name": "Old relay", "location": "hangar"})
    assert (
        records.create_room(host, "old", {"name": "Old relay", "location": " Hangar DECK "}) == old
    )
    first = records.create_room(
        host, "first", {"name": "Supply inspection", "location": "  Loading   Dock  "}
    )
    second = records.create_room(
        host, "second", {"name": "Shift briefing", "location": "loading dock"}
    )
    for key, form in (
        ("omitted", {}),
        ("null", {"location": None}),
        ("blank", {"location": " \t "}),
    ):
        receipt = records.create_room(host, key, {"name": key} | form)
        assert records.create_room(host, key, {"name": key, "location": ""}) == receipt

    reopened = ActivityRecords(records.path, host.user_id)
    rooms = reopened.directory(host, {})
    by_id = {room["id"]: room for room in rooms}
    assert by_id[old["room"]]["location"] == "hangar"
    assert by_id[old["room"]]["location_name"] == "Hangar Deck"
    dock = by_id[first["room"]]["location"]
    assert dock.startswith("location-")
    assert by_id[second["room"]]["location"] == dock
    assert by_id[second["room"]]["location_name"] == "Loading Dock"
    assert [room["location_name"] for room in rooms if room["location"] is None] == [None] * 3
    assert scene_locations([RELAY, *rooms]) == [
        {"id": "hangar", "name": "Hangar Deck", "area": "Foundation"},
        {"id": dock, "name": "Loading Dock", "area": ""},
    ]
    with pytest.raises(WorkflowError, match="different result"):
        records.create_room(host, "first", {"name": "Supply inspection", "location": "North gate"})
    with pytest.raises(WorkflowError, match="at most 80"):
        records.create_room(host, "long", {"name": "Long", "location": "x" * 81})
    with pytest.raises(ValueError):
        records.create_room(host, "wrong type", {"name": "Invalid", "location": []})


def test_archived_room_keeps_its_location_outside_active_list(directory):
    records, host, visitor = directory
    archive = records.create_room(
        host, "archive", {"name": "Retired scene", "location": "Outpost K-12"}
    )["room"]
    records.archive(host, archive, lambda *_: ({}, {}))
    (room,) = records.directory(host, {})
    assert room["location"] == "outpost"
    assert room["location_name"] == "Outpost K-12"
    assert room["archived_at"] is not None
    assert scene_locations([room]) == []
    assert records.directory(visitor, {}) == []


def test_handover_dialogue_is_limited_and_never_exposes_private_transcripts(directory):
    records, host, visitor = directory
    active = records.create_room(host, "active", {"name": "Joined"})["room"]
    other = records.create_room(visitor, "other", {"name": "Unjoined"})["room"]
    archived = records.create_room(host, "archived", {"name": "Ended"})["room"]
    entries = [
        records.post_dialogue(
            host, f"active-{index}", "Pilot", active, f"Private {index}", character=None
        )["entry"]
        for index in range(76)
    ]
    records.post_dialogue(visitor, "other-post", "Other", other, "Other pilot only", character=None)
    records.post_dialogue(host, "old-post", "Pilot", archived, "Archived only", character=None)
    records.post_dialogue(host, "relay-post", "Pilot", RELAY["id"], "Relay", character=None)
    records.archive(host, archived, lambda *_: ({}, {}))
    requested = [active, other, RELAY["id"], archived, active]

    projected = records.handover_dialogue(host, requested)
    assert set(projected) == {active}
    assert [record["id"] for record in projected[active]] == entries[1:]
    assert all(
        set(record) == {"id", "callsign", "created", "portrait"} for record in projected[active]
    )
    assert set(records.handover_dialogue(host, requested, relay_joined=True)) == {
        active,
        RELAY["id"],
    }
    assert set(records.handover_dialogue(visitor, requested)) == {other}
    assert records.handover_dialogue(host, []) == {}
