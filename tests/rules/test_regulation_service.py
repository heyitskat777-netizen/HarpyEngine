import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_punishment_service import ended, submit

from girlframe.database import tables as t
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_regulations import RegulationService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, disclosed=False):
    discipline, missions, game, mission, work = ended(store)
    submit(
        discipline,
        ADMIN,
        work,
        Details(kind="strict_regulations", regulation="PRIVATE_RULE_TEXT", disclosed=disclosed),
        "impose-rule",
    )
    return RegulationService(missions), discipline, game, mission, state(game).regulations[0].id


def record(svc, identity, due="next_off_duty", key=None):
    data = svc.get(ADMIN, identity)
    return svc.record(
        ADMIN, key or str(uuid4()), identity, data["game_revision"], "PRIVATE_OBSERVED_BREACH", due
    )


def complete_original(svc, discipline, mission):
    remaining = svc.missions.get(ADMIN, mission["id"])["work"]
    for work in remaining:
        submit(discipline, ADMIN, work["id"], Details(kind="stimulant_injection"), str(uuid4()))
    svc.missions.complete(ADMIN, str(uuid4()), mission["id"], mission["revision"])


def test_concealed_rule_does_not_leak_to_subject_sheet_mission_inbox_or_generic_audit(ledger):
    from girlframe.services.inbox import InboxService

    svc, _, game, mission, identity = ready(ledger)
    assert svc.get(ADMIN, identity)["rule"] == "PRIVATE_RULE_TEXT"
    assert not svc.list(OTHER) and not svc.list(PLAYER)
    for viewer in (OTHER, PLAYER):
        with pytest.raises(WorkflowError):
            svc.get(viewer, identity)
        assert "PRIVATE_RULE" not in str(game.sheet(viewer))
        assert "PRIVATE_RULE" not in str(svc.missions.get(viewer, mission["id"]))
        assert "PRIVATE_RULE" not in str(InboxService(ledger).page(viewer))
    record(svc, identity)
    with ledger.engine.connect() as c:
        for column in (t.events.c.payload_json, t.commands.c.outcome_json):
            values = str(list(c.scalars(sa.select(column))))
            assert "PRIVATE_RULE" not in values and "PRIVATE_OBSERVED" not in values


def test_disclosed_rule_is_read_only_for_subject_and_remains_after_restart_and_rebuild(ledger):
    svc, _, game, _, identity = ready(ledger, disclosed=True)
    assert svc.list(OTHER) and not svc.get(OTHER, identity)["may_record"]
    with pytest.raises(WorkflowError):
        svc.record(
            OTHER, "forge", identity, state(game).revision, "Forged occurrence", "next_off_duty"
        )
    before = svc.get(OTHER, identity)
    assert RegulationService(svc.missions).get(OTHER, identity) == before
    game.rebuild()
    assert svc.get(OTHER, identity) == before


def test_concealed_consultation_hides_text_from_subject_and_preserves_author_and_handler_review(
    ledger,
):
    discipline, missions, game, _, work = ended(ledger)
    submit(discipline, ADMIN, work, Details(kind="passing_responsibility", delegate=2))
    choice = Details(kind="strict_regulations", regulation="PRIVATE_CONSULT_RULE", disclosed=False)
    data = discipline.get(PLAYER, work)
    asked = discipline.consult(
        PLAYER, "ask-secret-rule", work, data["revision"], data["game_revision"], choice
    )
    assert "PRIVATE_CONSULT_RULE" in str(discipline.get(ADMIN, asked["id"]))
    assert "disclosed: False" in discipline.get(ADMIN, asked["id"])["summary"]
    assert "PRIVATE_CONSULT_RULE" in str(discipline.get(PLAYER, asked["id"]))
    assert "PRIVATE_CONSULT_RULE" not in str(discipline.get(OTHER, asked["id"]))
    discipline.answer_consultation(ADMIN, "approve-secret", asked["id"], 1, True)
    submit(discipline, PLAYER, work, choice, "apply-secret")
    svc = RegulationService(missions)
    identity = state(game).regulations[0].id
    assert svc.get(PLAYER, identity)["rule"] == "PRIVATE_CONSULT_RULE"
    assert not svc.list(OTHER)


def test_current_mission_breach_is_a_separate_real_cause_and_not_bundled_with_failure_dog(ledger):
    svc, discipline, game, mission, identity = ready(ledger)
    data = svc.get(ADMIN, identity)
    result = svc.record(
        ADMIN,
        "breach-once",
        identity,
        data["game_revision"],
        "PRIVATE_OBSERVED_BREACH",
        "mission:" + mission["id"],
    )
    assert (
        svc.record(
            ADMIN,
            "breach-once",
            identity,
            data["game_revision"],
            "PRIVATE_OBSERVED_BREACH",
            "mission:" + mission["id"],
        )
        == result
    )
    with ledger.engine.connect() as c:
        work = next(
            x
            for x in svc.missions._pending(c, mission["id"])
            if json.loads(x["body_json"]).get("obligation_id") == result["cause"]
        )
    pending = svc.missions.get(ADMIN, mission["id"])["pending_count"]
    assert pending == 2
    submit(discipline, ADMIN, work["id"], Details(kind="stimulant_injection"), "punish-breach")
    assert state(game).obligations[-1].state == "fulfilled"
    assert svc.missions.get(ADMIN, mission["id"])["pending_count"] == pending - 1
    assert len(state(game).regulations[0].breaches) == 1


def test_future_breach_binds_to_next_actual_period_once_and_further_punishment_fulfills_source(
    ledger,
):
    svc, discipline, game, mission, identity = ready(ledger)
    result = record(svc, identity)
    complete_original(svc, discipline, mission)
    periods = OffDutyService(svc.missions)
    period = periods.begin(ADMIN, "begin-after-rule-breach")
    with ledger.engine.connect() as c:
        pending = [x for x in periods._pending(c, period["id"]) if x["kind"] == "punishment"]
    assert len(pending) == 1
    assert json.loads(pending[0]["body_json"])["obligation_id"] == result["cause"]
    assert json.loads(pending[0]["body_json"])["source_pdf"] == 17
    # A real current context exists, but pre-roll Punishment still needs on-screen proof.
    data = discipline.get(ADMIN, pending[0]["id"])
    with pytest.raises(WorkflowError, match="on-screen"):
        discipline.apply(
            ADMIN,
            "not-offscreen",
            pending[0]["id"],
            data["revision"],
            data["game_revision"],
            Details(kind="stimulant_injection"),
        )
    with ledger.transaction() as c:
        game.event(c, 1, "later-no-duplicate-breach", "synthetic.refresh", state(game))
    with ledger.engine.connect() as c:
        assert len([x for x in periods._pending(c, period["id"]) if x["kind"] == "punishment"]) == 1


def test_next_period_deferral_does_not_bind_into_current_period(ledger):
    svc, discipline, game, mission, identity = ready(ledger)
    complete_original(svc, discipline, mission)
    periods = OffDutyService(svc.missions)
    current = periods.begin(ADMIN, "current-before-breach")
    result = record(svc, identity)
    assert state(game).obligations[-1].details["after_period"] == current["id"]
    with ledger.engine.connect() as c:
        assert not [x for x in periods._pending(c, current["id"]) if x["kind"] == "punishment"]
    assert result["cause"] == state(game).obligations[-1].id


def test_actual_cycle_can_finish_with_future_discipline_then_next_period_requires_it(ledger):
    from test_off_duty_cycle import activate, call, movement, prepared, recover_both

    from girlframe.services.m3_punishments import PunishmentService

    cycle, game, period = prepared(ledger)
    activate(cycle, game, period)
    call(
        cycle, game, ADMIN, period, "handler_scene", "punish", (1, 3), "Actual discipline scene", 3
    )
    for viewer in (ADMIN, OTHER):
        call(cycle, game, viewer, period, "acknowledge", None)
    discipline = PunishmentService(ledger)
    work = next(
        x["id"] for x in cycle.periods.get(ADMIN, period)["work"] if x["kind"] == "punishment"
    )
    submit(
        discipline,
        ADMIN,
        work,
        Details(kind="strict_regulations", regulation="An ongoing rule"),
        "impose-during-duty",
    )
    svc = RegulationService(cycle.missions)
    identity = state(game).regulations[0].id
    recorded = record(svc, identity)
    recover_both(cycle, game, period)
    call(cycle, game, ADMIN, period, "review_status", (3, 2), "Actual review")
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assert state(game).obligations[-1].state == "pending"
    following = cycle.periods.begin(ADMIN, "following-period")
    with ledger.engine.connect() as c:
        works = [x for x in cycle.periods._pending(c, following["id"]) if x["kind"] == "punishment"]
    assert (
        len(works) == 1 and json.loads(works[0]["body_json"])["obligation_id"] == recorded["cause"]
    )
    work = works[0]["id"]
    data = discipline.get(ADMIN, work)
    discipline.propose_scene(
        ADMIN,
        "actual-following-scene",
        work,
        data["revision"],
        data["game_revision"],
        "Actual subsequent Punishment scene",
    )
    for viewer in (ADMIN, OTHER):
        data = discipline.get(viewer, work)
        discipline.attest_scene(
            viewer,
            "actual-following-ack-" + str(viewer.user_id),
            work,
            data["revision"],
            data["game_revision"],
        )
    submit(
        discipline, ADMIN, work, Details(kind="stimulant_injection"), "actual-further-punishment"
    )
    assert state(game).obligations[-1].state == "fulfilled"


def test_breach_concurrency_pause_revocation_and_rollback_preserve_the_rule(ledger, monkeypatch):
    svc, _, game, _, identity = ready(ledger)
    before = state(game)
    ledger.safety(OTHER, "pause-rule", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        record(svc, identity)
    ledger.safety(OTHER, "resume-rule", ledger.status(OTHER)["revision"], pause=False)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic after-breach failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError):
        record(svc, identity, key="rule-retry")
    assert state(game) == before
    monkeypatch.setattr(svc.game, "event", original)

    def run(i):
        try:
            svc.record(
                ADMIN,
                "concurrent-" + str(i),
                identity,
                before.revision,
                "Actual observed occurrence",
                "next_off_duty",
            )
            return True
        except WorkflowError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]
    assert len(state(game).regulations[0].breaches) == 1
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        record(svc, identity)


def test_new_character_cannot_inherit_old_rule_or_receive_its_punishment(ledger):
    from test_actor_service import replace_profile_id

    svc, _, game, _, identity = ready(ledger, disclosed=True)
    before = state(game)
    replace_profile_id(ledger, 3)
    assert not svc.list(OTHER)
    with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
        record(svc, identity)
    assert state(game) == before


def test_native_regulation_choice_has_explicit_concealment_and_breach_confirmation(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_punishments import open_details
    from girlframe.discord_adapter.m3_regulations import open_regulations

    discipline, missions, game, _, work = ended(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_details(viewer, discipline, work, "strict_regulations")
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values = {"regulation": "PRIVATE_NATIVE_RULE", "disclosed": ("no",)}
        await form.confirm.callback(current(1, 15501))
        assert form.completed and not state(game).regulations[0].disclosed
        svc = RegulationService(missions)
        await open_regulations(viewer, svc)
        picker = viewer.edit_original_response.call_args.kwargs["view"]
        assert not await picker.interaction_check(current(3))
        await picker.open_item(viewer, state(game).regulations[0].id)
        breach_form = viewer.edit_original_response.call_args.kwargs["view"]
        assert not state(game).obligations
        breach_form.values = {"evidence": "Observed native breach", "due": ("next_off_duty",)}
        await breach_form.confirm.callback(current(1, 15502))
        assert breach_form.completed and len(state(game).obligations) == 1

    asyncio.run(run())
