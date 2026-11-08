"""A dead original participant cannot reward or obligate its replacement by account ID."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.engine.m2 import PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_careers import replacement
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def dispatch(store, *, legacy=False):
    missions, game = service(store)
    save = missions._save
    if legacy:

        def legacy_save(c, mission, event):
            save(
                c, mission.model_copy(update={"character_ids": {}, "offered_characters": {}}), event
            )

        missions._save = legacy_save
    offered = missions.offer(ADMIN, "original-mission", "Actual original mission", (2, 3))
    missions.respond(PLAYER, "actual-accept-2", offered["id"], 1, "accept")
    missions.respond(OTHER, "actual-accept-3", offered["id"], 2, "accept")
    started = missions.start(ADMIN, "actual-dispatch", offered["id"], 3)
    missions._save = save
    return missions, game, started


def end_career(store, game, owner=2):
    with store.transaction() as c:
        canon = state(game)
        actor = ActorRef(
            kind="pilot", entity=str(owner), incarnation=canon.sheets[str(owner)].character_id
        )
        source, archive = str(uuid4()), str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason="death",
            source_event=source,
            account="Actual career ending",
            archive_id=archive,
        )
        game.event(c, 1, str(uuid4()), "m3.synthetic_actual_ending", ended, event_id=source)
        synchronize_end(c, game, ended.career_archives[-1])
    return archive, actor


def test_one_survivor_can_end_actual_mission_and_gets_its_real_ace_and_dog_roles(ledger):
    missions, game, started = dispatch(ledger)
    archive, _ = end_career(ledger, game)
    ended = missions.end(ADMIN, "actual-mission-end", started["id"], started["revision"], True)
    assert ended["rewards_committed"] and state(game).sheets["3"].permissions == 2
    assert "2" not in state(game).sheets
    with ledger.engine.connect() as c:
        actual = missions._mission(c, started["id"])
        assert actual.participants == (2, 3) and set(actual.ended_participants) == {"2"}
        work = missions._pending(c, started["id"])
    assert len(work) == 1 and work[0]["subject_id"] == "3"
    punish = PunishmentService(ledger)
    current = punish.get(ADMIN, work[0]["id"])
    punish.apply(
        ADMIN,
        "actual-surviving-dog",
        work[0]["id"],
        current["revision"],
        current["game_revision"],
        Details(kind="stimulant_injection"),
    )
    completed = missions.complete(
        ADMIN, "complete-survivor-mission", started["id"], ended["revision"]
    )
    assert completed["phase"] == "complete"
    assert state(game).career_archives[-1].id == archive


def test_no_survivors_have_no_invented_ace_dog_or_replacement_rewards(ledger):
    missions, game, started = dispatch(ledger)
    end_career(ledger, game, 2)
    end_career(ledger, game, 3)
    ended = missions.end(ADMIN, "all-originals-ended", started["id"], started["revision"], False)
    assert not state(game).sheets and not state(game).order
    with ledger.engine.connect() as c:
        assert not missions._pending(c, started["id"])
        actual = missions._mission(c, started["id"])
        assert set(actual.ended_participants) == {"2", "3"}
    assert (
        missions.complete(ADMIN, "complete-empty-roster", started["id"], ended["revision"])["phase"]
        == "complete"
    )


def test_replacement_account_cannot_claim_original_participation_or_failure_punishment(ledger):
    missions, game, started = dispatch(ledger)
    original_sheet = state(game).sheets["2"]
    archive, actor = end_career(ledger, game, 2)
    # Synthetic activation of a distinct newcomer, explicitly placed above the survivor.
    with ledger.transaction() as c:
        canon = state(game)
        profile = (
            c.execute(
                sa.select(t.characters).where(
                    t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
                )
            )
            .mappings()
            .one()
        )
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(revision=profile["revision"] + 1)
        )
        canon = replacement(
            canon,
            archive,
            owner=2,
            new_character="actual-new-girl",
            profile_id=profile["id"],
            profile_revision=profile["revision"] + 1,
            source_event="actual-newcomer-source",
        )
        newer = PilotSheet.model_validate_json(original_sheet.model_dump_json())
        newer.character_id, newer.callsign, newer.permissions = "actual-new-girl", "NEW_GIRL", 0
        newer.source_profile_revision = profile["revision"] + 1
        canon.sheets["2"] = newer
        canon.order = (2, 3)
        game.event(c, 1, "fixture-explicit-newcomer", "synthetic.new_incarnation", canon)
    missions.end(
        ADMIN, "end-before-newcomer-participated", started["id"], started["revision"], False
    )
    # Current Ace gets only the explicit absent-Ace bonus, not its dead predecessor's completion.
    assert state(game).sheets["2"].permissions == 1
    with ledger.engine.connect() as c:
        pending = missions._pending(c, started["id"])
    assert {x["subject_id"] for x in pending} == {"3"}
    assert actor.incarnation != state(game).sheets["2"].character_id


def test_forged_current_participant_identity_cannot_replace_immutable_dispatch_source(ledger):
    missions, game, started = dispatch(ledger)
    with ledger.transaction() as c:
        actual = missions._mission(c, started["id"])
        actual.character_ids["2"] = "forged-new-identity"
        c.execute(
            t.m3["m3_missions"]
            .update()
            .where(
                t.m3["m3_missions"].c.id == started["id"],
                t.m3["m3_missions"].c.campaign_id == ledger.campaign_id,
            )
            .values(body_json=actual.model_dump_json())
        )
    with pytest.raises(WorkflowError, match="SOURCE_MISSION_CHANGED"):
        missions.end(
            ADMIN, "cannot-forge-original-dispatch", started["id"], started["revision"], True
        )
    assert state(game).sheets["2"].permissions == 0


def test_legacy_dispatch_without_explicit_cids_recovers_immutable_pre_dispatch_state(ledger):
    # Write the old-format identity defaults initially; immutable history remains untouched.
    missions, game, started = dispatch(ledger, legacy=True)
    end_career(ledger, game, 2)
    result = missions.end(
        ADMIN, "legacy-dead-participant", started["id"], started["revision"], True
    )
    assert result["rewards_committed"] and state(game).sheets["3"].permissions == 2
