"""New absent lifecycle metadata never changes an old signed source serialization."""

import hashlib
import json

from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_harpy_defeat_state import DefeatEffect, Travel


def raw(value):
    return json.dumps(value, separators=(",", ":"))


def test_genuine_legacy_travel_bytes_and_source_fingerprint_round_trip_without_new_defaults():
    legacy = dict(
        id="actual-old-route",
        actor=dict(kind="pilot", entity="2", incarnation="original-girl"),
        controller=2,
        source_event="actual-old-proposal",
        source_sha256="a" * 64,
        rift="actual-old-rift",
        escape_effect=None,
        frame_instance=None,
        travels_frame=False,
        destination=None,
        account="Actual previous crossing",
        navigation="Actual previous navigation",
        judge=1,
        adjudicator=None,
        appointment="actual-original-appointment",
        state="offstage",
        response_event="actual-old-review",
        review="Actual original reviewed crossing",
        return_of=None,
    )
    encoded = raw(legacy)
    loaded = Travel.model_validate_json(encoded)
    assert loaded.off_duty_action is None and loaded.ended_event is None
    assert loaded.model_dump_json() == encoded
    assert fingerprint(loaded) == hashlib.sha256(encoded.encode()).hexdigest()
    assert Travel.model_validate_json(loaded.model_dump_json()) == loaded


def test_genuine_legacy_defeat_bytes_exclude_new_absent_postcareer_and_ending_metadata():
    actor = dict(kind="external_pilot", entity="actual-old-harpy", incarnation=None)
    cast = dict(
        id="actual-old-scene",
        channel=900,
        revision=1,
        open=True,
        roles=[],
        facilitator=1,
        facilitator_source="actual-old-facilitator",
        adjudicator=None,
    )
    legacy = dict(
        id="actual-old-effect",
        departed=[],
        action="actual-old-play",
        work="actual-old-work",
        actor=actor,
        frame_instance="actual-old-frame",
        source_event="actual-old-choice",
        tier="low",
        choice="shutdown",
        account="Actual previous unlinked body",
        girl=None,
        rescuer=None,
        killer=None,
        captor=None,
        phase="awaiting_physical",
        response_event=None,
        response="",
        escaped=False,
        cut_link=True,
        tag=None,
        tag_id=None,
        factual_source=None,
        source_cast=cast,
    )
    encoded = raw(legacy)
    loaded = DefeatEffect.model_validate_json(encoded)
    assert not loaded.archived_tag and loaded.ended_event is None
    assert loaded.model_dump_json() == encoded
    assert fingerprint(loaded) == hashlib.sha256(encoded.encode()).hexdigest()
