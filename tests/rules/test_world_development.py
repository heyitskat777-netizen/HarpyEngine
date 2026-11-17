"""Finite native narrative records preserve private history and original world authority."""

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import start, state
from test_world_service import ready, transfer_npc

from girlframe.database import tables as t
from girlframe.engine.m3_world_development import DevelopmentDraft, Subject, current, records
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.onboarding import WorkflowError


def detail(**changes):
    return DevelopmentDraft(
        **(
            {
                "key": "relay.maintenance-detail",
                "kind": "detail",
                "subject": Subject(kind="location", id="base0"),
                "title": "A maintenance archive",
                "text": "PRIVATE_WORLD_DETAIL: old maintenance recordings remain in an archive.",
            }
            | changes
        )
    )


def introduce(svc, game):
    svc.npc(
        ADMIN,
        "introduce-technician",
        state(game).revision,
        Npc(
            id="technician",
            name="Technician",
            jobs=("mechanic",),
            detail="Keeps a careful maintenance notebook.",
            controller=ADMIN.user_id,
            cell=(0, 0),
        ),
    )
    svc.faction(
        ADMIN,
        "introduce-contractors",
        state(game).revision,
        Faction(
            id="contractors",
            name="Maintenance contractors",
            kind="foundation",
            cells=((0, 0),),
            description="An ordinary contracting organisation.",
        ),
    )


def test_details_goals_and_unresolved_complications_are_private_append_only_narrative(ledger):
    svc, game = ready(ledger)
    introduce(svc, game)
    before = state(game)
    original_world = before.world.model_dump_json()
    original_sheets = {key: value.model_dump_json() for key, value in before.sheets.items()}
    drafts = (
        detail(),
        detail(
            key="technician.archive-goal",
            kind="goal",
            subject=Subject(kind="npc", id="technician"),
            title="Preserve the archive",
            text="PRIVATE_WORLD_GOAL: the technician wants to preserve the recordings.",
        ),
        detail(
            key="contractors.access-complication",
            kind="complication",
            subject=Subject(kind="faction", id="contractors"),
            title="An unanswered access question",
            text="The contractors have not explained who may inspect their archive.",
        ),
    )
    for index, draft in enumerate(drafts):
        expected = state(game).revision
        result = svc.develop(
            ADMIN,
            f"development:{index}",
            expected,
            draft,
            source_proposal=f"reviewed-proposal:{index}",
        )
        assert (
            svc.develop(
                ADMIN,
                f"development:{index}",
                expected,
                draft,
                source_proposal=f"reviewed-proposal:{index}",
            )
            == result
        )
        assert result["version"] == 1
        assert records(state(game))[-1].source_event == result["source_event"]
    after = state(game)
    assert len(records(after)) == len(current(after)) == 3
    assert after.world.model_dump_json() == original_world
    assert {key: value.model_dump_json() for key, value in after.sheets.items()} == original_sheets
    assert after.handler_heat == before.handler_heat
    assert "PRIVATE_WORLD" not in str(svc.get(PLAYER))
    with ledger.engine.connect() as c:
        assert "PRIVATE_WORLD" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert "PRIVATE_WORLD" not in str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
    game.rebuild()
    assert records(state(game)) == records(after)


def test_revision_replaces_only_the_exact_active_key_and_preserves_prior_text(ledger):
    svc, game = ready(ledger)
    original = detail()
    first = svc.develop(
        ADMIN, "first", state(game).revision, original, source_proposal="proposal:first"
    )
    with pytest.raises(WorkflowError, match="WORLD_DEVELOPMENT_DUPLICATE"):
        svc.develop(
            ADMIN, "duplicate", state(game).revision, original, source_proposal="proposal:duplicate"
        )
    revised = detail(
        text="PRIVATE_REVISED_DETAIL: one recording names an old storage room.",
        supersedes=first["id"],
    )
    second = svc.develop(
        ADMIN, "second", state(game).revision, revised, source_proposal="proposal:second"
    )
    assert second["version"] == 2
    history = records(state(game))
    assert len(history) == 2 and history[0].text == original.text
    assert current(state(game)) == (history[1],)
    for wrong in (
        revised,
        detail(supersedes=second["id"], subject=Subject(kind="location", id="base1")),
        detail(key="another-key", supersedes=second["id"]),
    ):
        with pytest.raises(WorkflowError, match="STALE_WORLD_DEVELOPMENT"):
            svc.develop(
                ADMIN,
                "wrong-prior:" + wrong.key + ":" + wrong.subject.id,
                state(game).revision,
                wrong,
                source_proposal="proposal:wrong-prior",
            )
    assert records(state(game)) == history


def test_only_actual_subjects_and_owned_npc_goals_fit_the_narrative_schema(ledger):
    svc, game = ready(ledger)
    introduce(svc, game)
    with pytest.raises(ValidationError):
        detail(kind="goal")
    with pytest.raises(ValidationError):
        Subject(kind="pilot", id="2")
    with pytest.raises(ValidationError):
        DevelopmentDraft.model_validate_json(
            detail().model_dump_json()[:-1] + ',"resource_delta":-1}'
        )
    with pytest.raises(WorkflowError, match="WORLD_SUBJECT_UNAVAILABLE"):
        svc.develop(
            ADMIN,
            "missing-subject",
            state(game).revision,
            detail(subject=Subject(kind="npc", id="not-introduced")),
            source_proposal="proposal:missing-subject",
        )
    transfer_npc(svc, ADMIN, OTHER, "technician")
    before = state(game)
    with pytest.raises(WorkflowError, match="WORLD_GOAL_NOT_OWNED"):
        svc.develop(
            ADMIN,
            "other-npc-intent",
            before.revision,
            detail(kind="goal", subject=Subject(kind="npc", id="technician")),
            source_proposal="proposal:other-intent",
        )
    assert state(game) == before


def test_native_handler_release_and_pending_play_locks_stay_required(ledger):
    svc, game = ready(ledger)
    before = state(game)
    with pytest.raises(WorkflowError):
        svc.develop(PLAYER, "wrong-owner", before.revision, detail(), source_proposal="proposal:1")
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems - {"world"}}
            )
        }
    )
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        svc.develop(ADMIN, "no-release", before.revision, detail(), source_proposal="proposal:1")
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": approval})
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        svc.develop(ADMIN, "stale", before.revision - 1, detail(), source_proposal="proposal:1")
    assert state(game) == before
    start(game)
    pending = state(game)
    with pytest.raises(WorkflowError, match="finish pending Plays"):
        svc.develop(ADMIN, "pending", pending.revision, detail(), source_proposal="proposal:1")
    assert state(game) == pending and not records(pending)


def test_native_event_failure_rolls_back_record_and_same_retry_commits_once(ledger, monkeypatch):
    svc, game = ready(ledger)
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError, match="after-event"):
        svc.develop(ADMIN, "atomic", before.revision, detail(), source_proposal="proposal:atomic")
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", original)
    svc.develop(ADMIN, "atomic", before.revision, detail(), source_proposal="proposal:atomic")
    assert len(records(state(game))) == 1
