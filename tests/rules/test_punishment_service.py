import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ended(store):
    missions, game = service(store)
    offered = missions.offer(ADMIN, "offer", "SECRET_MISSION", (2, 3))
    missions.respond(PLAYER, "yes-2", offered["id"], 1, "accept")
    missions.respond(OTHER, "yes-3", offered["id"], 2, "accept")
    missions.start(ADMIN, "start", offered["id"], 3)
    result = missions.end(ADMIN, "end", offered["id"], 4, False)
    discipline = PunishmentService(store, missions.access.registry)
    work = missions.get(ADMIN, offered["id"])["work"]
    identity = next(x["id"] for x in work if x["subject"] == 3)
    return discipline, missions, game, result, identity


def submit(svc, viewer, identity, choice, key="punish"):
    current = svc.get(viewer, identity)
    return svc.apply(viewer, key, identity, current["revision"], current["game_revision"], choice)


def test_one_actual_punishment_resolves_both_causes_once_and_mission_can_complete(ledger):
    svc, missions, game, mission, identity = ended(ledger)
    current = svc.get(ADMIN, identity)
    assert set(current["causes"]) == {"mission_failure", "dog_mission_end"}
    choice = Details(kind="stimulant_injection")
    result = svc.apply(
        ADMIN, "punish", identity, current["revision"], current["game_revision"], choice
    )
    assert result["cause_count"] == 2 and state(game).sheets["3"].heat == 7
    restarted = PunishmentService(ledger, missions.access.registry)
    assert (
        restarted.apply(
            ADMIN, "punish", identity, current["revision"], current["game_revision"], choice
        )
        == result
    )
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 1
    other_work = missions.get(ADMIN, mission["id"])["work"][0]
    submit(svc, ADMIN, other_work["id"], choice, "punish-other")
    assert (
        missions.complete(ADMIN, "complete", mission["id"], mission["revision"])["phase"]
        == "complete"
    )
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        resolved = (
            c.execute(
                sa.select(work.c.body_json).where(
                    work.c.state == "resolved", work.c.subject_id == "3"
                )
            )
            .scalars()
            .all()
        )
    assert len(resolved) == 2
    assert len({json.loads(x)["applied_event"] for x in resolved}) == 1


def test_inflictor_chooses_details_but_no_unrelated_private_state_is_exposed(ledger):
    svc, _, game, _, identity = ended(ledger)
    current = svc.get(ADMIN, identity)
    assert "choices" in current and "choices" not in svc.get(OTHER, identity)
    assert all(
        x not in str(current)
        for x in ("SECRET_MISSION", "source_fingerprint", "description", "review")
    )
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="decision owner"):
        svc.apply(
            OTHER,
            "unauthorized",
            identity,
            1,
            current["game_revision"],
            Details(kind="sedation", identities=("identity:0", "identity:1")),
        )
    submit(svc, ADMIN, identity, Details(kind="sedation", identities=("identity:2", "identity:3")))
    assert [x.marked for x in state(game).sheets["3"].identities] == [False, False, True, True]


def test_delegation_transfers_both_causes_without_resolving_or_imposing_a_punishment(ledger):
    svc, missions, game, mission, identity = ended(ledger)
    old_state = state(game)
    result = submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))
    assert result["state"] == "delegated" and state(game) == old_state
    assert svc.get(PLAYER, identity)["owner_id"] == "2"
    assert len(svc.get(PLAYER, identity)["causes"]) == 2
    with pytest.raises(WorkflowError, match="other participants"):
        svc.get(ADMIN, identity)
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 3


def test_moderate_proposal_requires_current_handler_and_exact_unchanged_choices(ledger):
    svc, _, game, _, identity = ended(ledger)
    submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))
    choice = Details(kind="frame_disassembly", asset="frame:0")
    with pytest.raises(WorkflowError, match="CONSULT_REQUIRED"):
        submit(svc, PLAYER, identity, choice, "no-consult")
    current = svc.get(PLAYER, identity)
    consultation = svc.consult(
        PLAYER, "consult", identity, current["revision"], current["game_revision"], choice
    )
    assert svc.get(ADMIN, consultation["id"])["proposal"]["asset"] == "frame:0"
    with pytest.raises(WorkflowError):
        svc.answer_consultation(PLAYER, "forged-approval", consultation["id"], 1, True)
    svc.answer_consultation(ADMIN, "approved", consultation["id"], 1, True)
    with pytest.raises(WorkflowError, match="CONSULT_REQUIRED"):
        submit(
            svc,
            PLAYER,
            identity,
            Details(kind="frame_disassembly", asset="frame:1"),
            "changed-proposal",
        )
    submit(svc, PLAYER, identity, choice, "apply-approved")
    assert not any(x.id == "frame:0" for x in state(game).sheets["3"].assets)


def test_stale_consultation_must_be_rejected_and_reproposed_without_resolving_causes(ledger):
    svc, missions, game, mission, identity = ended(ledger)
    submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))
    current = svc.get(PLAYER, identity)
    proposal = Details(kind="frame_disassembly", asset="frame:0")
    request = svc.consult(
        PLAYER, "consult", identity, current["revision"], current["game_revision"], proposal
    )
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].heat += 1
        game.event(c, 2, "synthetic-unrelated-change", "synthetic.change", saved)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.answer_consultation(ADMIN, "stale-approve", request["id"], 1, True)
    svc.answer_consultation(ADMIN, "decline", request["id"], 1, False)
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 3


def test_duplicate_concurrent_submissions_cannot_double_apply(ledger):
    svc, _, game, _, identity = ended(ledger)
    current = svc.get(ADMIN, identity)

    def submit_once(key):
        try:
            return svc.apply(
                ADMIN,
                key,
                identity,
                current["revision"],
                current["game_revision"],
                Details(kind="stimulant_injection"),
            )
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit_once, ("first", "second")))
    assert sum(x is not None for x in results) == 1
    assert state(game).sheets["3"].heat == 7


def test_partial_failure_rolls_back_sheet_and_both_cause_records(ledger, monkeypatch):
    svc, missions, game, mission, identity = ended(ledger)
    before = state(game)

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic persistence failure")

    monkeypatch.setattr(svc, "_save", fail)
    with pytest.raises(RuntimeError):
        submit(svc, ADMIN, identity, Details(kind="stimulant_injection"))
    assert state(game) == before
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 3


def test_gate_pause_and_revoked_membership_prevent_application(ledger):
    svc, _, game, _, identity = ended(ledger)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        submit(svc, ADMIN, identity, Details(kind="stimulant_injection"))
    assert svc.get(OTHER, identity)["state"] == "pending"
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": frozenset({"missions"})}
            )
        }
    )
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        submit(svc, ADMIN, identity, Details(kind="stimulant_injection"))
    assert state(game).sheets["3"].heat == 0


def test_paired_heat_remains_owned_pending_and_blocks_new_plays_until_split_once(ledger):
    from girlframe.engine.m2 import PlayInput

    svc, missions, game, mission, identity = ended(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["3"].identities[0].paired = True
        saved.sheets["3"].pair = 2
        game.event(c, 3, "synthetic-pair", "synthetic.pair", saved)
    result = submit(
        svc, ADMIN, identity, Details(kind="sedation", identities=("identity:0", "identity:1"))
    )
    assert result["followups"] == 1
    work = next(
        x for x in missions.owned_work(OTHER) if x["kind"] == "punishment_paired_identity_heat"
    )
    current = svc.get(OTHER, work["id"])
    with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
        game.begin(
            OTHER,
            "too-early",
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head", context="Synthetic danger", trigger_confirmed=True, heat=0
            ),
        )
    with pytest.raises(WorkflowError):
        svc.split_paired_heat(ADMIN, "forged-split", work["id"], 1, current["game_revision"], 3)
    result = svc.split_paired_heat(OTHER, "share", work["id"], 1, current["game_revision"], 3)
    assert state(game).sheets["2"].heat == 3 and state(game).sheets["3"].heat == 2
    assert (
        svc.split_paired_heat(OTHER, "share", work["id"], 1, current["game_revision"], 3) == result
    )
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 1


def test_followup_and_punishment_history_survive_backup_restore_and_rebuild(ledger, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.onboarding import OnboardingStore

    svc, missions, game, _, identity = ended(ledger)
    submit(svc, ADMIN, identity, Details(kind="stimulant_injection"))
    backup = tmp_path / "discipline-backup.db"
    copy_database(Path(ledger.engine.url.database), backup)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(backup)))
    try:
        store = OnboardingStore(engine, ledger.policy)
        restored = PunishmentService(store, missions.access.registry)
        restored.game.rebuild()
        assert restored.get(OTHER, identity)["state"] == "resolved"
        assert state(restored.game).sheets["3"].heat == state(game).sheets["3"].heat == 7
    finally:
        engine.dispose()


def test_other_campaign_and_revoked_inflictor_cannot_read_or_apply_work(ledger):
    from uuid import uuid4

    from girlframe.services.onboarding import OnboardingStore
    from girlframe.services.read_only_bot import GuildViewer

    svc, missions, _, _, identity = ended(ledger)
    policy = ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201})
    other_store = OnboardingStore(ledger.engine, policy)
    stranger = GuildViewer(1, 201, True, True)
    other_store.join(stranger, "other-campaign")
    other = PunishmentService(other_store, missions.access.registry)
    with pytest.raises(WorkflowError, match="unavailable"):
        other.get(stranger, identity)
    submit(svc, ADMIN, identity, Details(kind="passing_responsibility", delegate=2))
    current = svc.get(PLAYER, identity)
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        svc.apply(
            PLAYER,
            "revoked",
            identity,
            current["revision"],
            current["game_revision"],
            Details(kind="stimulant_injection"),
        )


def test_absent_dogs_punishment_applies_without_exposing_the_mission(ledger):
    from test_mission_service import launched

    missions, game = service(ledger)
    identity, revision = launched(missions)  # Only Player 2 explicitly participates.
    result = missions.end(ADMIN, "end", identity, revision, True)
    discipline = PunishmentService(ledger, missions.access.registry)
    work = missions.owned_work(OTHER)[0]
    current = discipline.get(OTHER, work["id"])
    assert "PRIVATE_OBJECTIVE" not in str(current)
    assert current["causes"] == ["dog_mission_end"]
    submit(discipline, ADMIN, work["id"], Details(kind="stimulant_injection"))
    assert state(game).sheets["3"].heat == 7
    assert missions.complete(ADMIN, "complete", identity, result["revision"])["phase"] == "complete"


@pytest.mark.parametrize("inside_frame", [False, True])
def test_last_girl_asset_requires_handler_context_and_applies_helplessness_conditionally(
    ledger, inside_frame
):
    svc, missions, game, mission, identity = ended(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        next(x for x in saved.sheets["3"].assets if x.id == "girl:1").damaged = True
        game.event(c, 1, "synthetic-earlier-damage", "synthetic.damage", saved)
    submit(svc, ADMIN, identity, Details(kind="beating", asset="girl:0", tag="Bruised"))
    row = next(x for x in missions.owned_work(ADMIN) if x["kind"] == "punishment_helpless")
    current = svc.get(ADMIN, row["id"])
    assert row["owner_id"] == "1" and not state(game).sheets["3"].helpless_against
    with pytest.raises(WorkflowError):
        svc.resolve_helpless(
            OTHER,
            "forged-context",
            row["id"],
            1,
            current["game_revision"],
            inside_frame=True,
            evidence="Unverified",
        )
    result = svc.resolve_helpless(
        ADMIN,
        "context",
        row["id"],
        1,
        current["game_revision"],
        inside_frame=inside_frame,
        evidence="Synthetic observed Frame context",
    )
    assert result["helpless"] is (not inside_frame)
    from girlframe.engine.m3_actor_bonds import current_ref, is_helpless

    assert is_helpless(state(game), current_ref(state(game), 3), current_ref(state(game), 1)) is (
        not inside_frame
    )
    assert (
        svc.resolve_helpless(
            ADMIN,
            "context",
            row["id"],
            1,
            current["game_revision"],
            inside_frame=inside_frame,
            evidence="Synthetic observed Frame context",
        )
        == result
    )
    assert missions.get(ADMIN, mission["id"])["pending_count"] == 1
