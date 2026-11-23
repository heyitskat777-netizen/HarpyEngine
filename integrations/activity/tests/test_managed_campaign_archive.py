"""Round-trip a managed Activity campaign using the host operator's archive."""

import json
from http import HTTPStatus
from uuid import UUID
from zipfile import ZipFile

import pytest
from activity_campaign_archive import REGISTRY, export_campaign, import_campaign
from activity_records import ActivityRecords
from discord_test_host import CONFIG, IDENTITIES, MANAGED_CHANNELS
from test_artwork_activity import offline_activity, request, sign_in


def test_restore_one_campaign_preserves_session_zero_and_private_activity_history(tmp_path):
    original, restored = tmp_path / "original", tmp_path / "restored"
    archive = tmp_path / "campaign.zip"
    with offline_activity(original, "--bound-roster", "--managed-campaigns") as host:
        handler, pilot = (sign_in(host, role) for role in ("handler", "invited"))
        listing = request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", handler)
        north = listing["preferred"]
        south = next(row["id"] for row in listing["campaigns"] if row["name"] == "Southern Signal")
        base = "/api/campaign-opening/session-zero"
        query = f"?campaign={north}"
        player = f"/api/player-setup/profile{query}"
        request(host, player, pilot, {"revision": 0, "callsign": "ARCHIVE-PILOT"})
        hm, pm = (IDENTITIES[role] for role in ("handler", "invited"))
        request(host, base + "-group" + query, handler, {"revision": 0, "members": [hm, pm]})
        revision = request(host, base + query, handler)["revision"]
        profile = {
            "member": hm,
            "control": "ai",
            "name": "Archive Handler",
            "archetype": "Advocate",
            "appearance": "An old flight jacket.",
            "personality": "Patient.",
        }
        request(
            host, base + "-propose" + query, handler, {"revision": revision, "profile": profile}
        )
        proposal = request(host, base + query, handler)["proposal"]
        request(
            host, base + "-handler-vote" + query, pilot, {"proposal": proposal, "approve": True}
        )
        expected = request(host, base + query, pilot)
        request(host, f"/api/player-setup?campaign={south}", handler)

    registry = next(original.rglob("managed-fixture.sqlite3"))
    records = original / "playtest-campaigns" / f"activity-{north}" / "activity-records.sqlite3"
    peers = ("pilot-fixture", "handler-fixture")
    message = "ARCHIVE_PRIVATE_MESSAGE"
    existing = ActivityRecords(records, int(CONFIG.handler_user_id), campaign_codes=False)
    existing.send_private("private", {"id": peers[0], "label": "Pilot"}, peers[1], message)

    export_campaign(original, str(UUID(north)), archive, registry=registry)
    with ZipFile(archive) as saved:
        manifest = json.loads(saved.read("manifest.json"))
        assert manifest["binding"]["id"] == north
        assert set(saved.namelist()) == {
            "manifest.json",
            "synthetic-policy.json",
            "missions.sqlite3",
            "activity-records.sqlite3",
            "activity-delivery.sqlite3",
        }
        assert "sandbox" not in json.loads(saved.read("synthetic-policy.json"))
        assert south not in str(manifest)
    with pytest.raises(ValueError, match="new archive path"):
        export_campaign(original, north, archive, registry=registry)
    import_campaign(archive, restored)
    with pytest.raises(FileExistsError, match="new, offline"):
        import_campaign(archive, restored)
    assert not (
        restored / records.parent.relative_to(original).with_name(f"activity-{south}")
    ).exists()

    # The HTTP rehearsal uses a differently named campaign registry.
    host_registry = restored / registry.relative_to(original)
    host_registry.parent.mkdir(parents=True, exist_ok=True)
    (restored / REGISTRY).rename(host_registry)
    with offline_activity(restored, "--bound-roster", "--managed-campaigns") as host:
        request(host, base + query, pilot, status=HTTPStatus.UNAUTHORIZED)
        returned_pilot = sign_in(host, "invited")
        assert request(host, base + query, returned_pilot) == expected
        assert (
            request(host, f"/api/player-setup{query}", returned_pilot)["callsign"]
            == "ARCHIVE-PILOT"
        )
        outsider = sign_in(host, "other")
        request(host, base + query, outsider, status=HTTPStatus.FORBIDDEN)
    recovered = ActivityRecords(
        restored / records.relative_to(original), int(CONFIG.handler_user_id), campaign_codes=False
    )
    assert recovered.private_thread(*peers)["entries"][0]["body"] == message
    assert recovered.private_thread("unrelated", peers[1])["entries"] == []

    corrupt = tmp_path / "corrupt.zip"
    with ZipFile(archive) as saved, ZipFile(corrupt, "w") as damaged:
        for name in saved.namelist():
            data = saved.read(name)
            damaged.writestr(name, data + b"\n" if name == "synthetic-policy.json" else data)
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="checksum"):
        import_campaign(corrupt, rejected)
    assert not rejected.exists()
