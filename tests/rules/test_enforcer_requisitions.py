"""Actual owned Enforcer acquisition sources and post-roll/Keep passive effects."""

import json
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_off_duty_roll_service import active, saved
from test_personal_firearm import reviewed_registry
from test_requisition_service import ready

from girlframe.engine import m3_enforcer_requisitions as rules
from girlframe.engine import m3_privileges as privileges
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest
from girlframe.services.m3_enforcer_requisitions import EnforcerRequisitionService, proof
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def approved(store, game, tmp_path, monkeypatch, extra=()):
    data = reviewed_registry().model_dump(mode="json")
    source = next(x for x in data["entries"] if x["id"] == "frame.enforcer.personal-firearm")
    for entry in data["entries"]:
        if entry["id"] in (*rules.RULES, *extra):
            for field in (
                "implementation",
                "source_audit",
                "independent_review",
                "reviewer",
                "review_reference",
                "contract",
                "test_evidence",
            ):
                entry[field] = source[field]
    registry = Registry.model_validate_json(json.dumps(data))
    path = tmp_path / "synthetic-enforcer-requisitions-only.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    previous = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": previous.model_copy(
                update={
                    "registry_sha256": digest(registry),
                    "subsystems": previous.subsystems | {"plays", "economy"},
                }
            ),
        }
    )
    return EnforcerRequisitionService(game, registry)


def personal_bond(game):
    with game.store.transaction() as c:
        original = state(game)
        event = str(uuid4())
        changed = set_depth(original, current_ref(original, 2), active_handler(original), 1, event)
        game.event(
            c, 1, str(uuid4()), "synthetic.existing_personal_handler_bond", changed, event_id=event
        )


def buy(service, rule, kind="ability_unlock", *, key=None):
    data = service.acquisition_view(PLAYER, kind)
    return service.buy_rule(
        PLAYER,
        key or str(uuid4()),
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        kind,
        rule,
        "Actual owned acquired rule",
    )


@pytest.mark.parametrize(
    "frame,kind,cost", [("THE ENFORCER", "ability_unlock", 2), ("JANUS-B", "frame_grafting", 3)]
)
def test_master_actual_paid_acquisition_once_and_temporary_removal_preserves_earned_bond(
    ledger, tmp_path, monkeypatch, frame, kind, cost
):
    _, game = ready(ledger, frame=frame)
    service = approved(ledger, game, tmp_path, monkeypatch)
    personal_bond(game)
    initial = state(game)
    data = service.acquisition_view(PLAYER, kind)
    actor = ActorRef.model_validate(data["actor"])
    key = str(uuid4())
    args = (PLAYER, key, actor, data["source_sha256"], kind, rules.MASTER, "Actual acquisition")
    result = service.buy_rule(*args)
    assert service.buy_rule(*args) == result
    actual = state(game)
    grant = rules.held(actual, actor, rules.MASTER)
    assert grant is not None and grant.counterpart == active_handler(actual)
    assert actual.sheets["2"].permissions == initial.sheets["2"].permissions - cost
    assert depth(actual, actor, grant.counterpart) == 2
    assert rules.room(actual, actor) == grant.counterpart
    assert actual.sheets["3"] == initial.sheets["3"] and game.dice.calls == 0
    with ledger.engine.connect() as c:
        proof(c, game, grant)
    with pytest.raises(WorkflowError, match="duplicate"):
        buy(service, rules.MASTER, kind)
    chars = {int(k): x.character_id for k, x in actual.sheets.items()}
    removed = privileges.revoke(
        actual,
        2,
        1,
        result["id"],
        "Actual restoration condition",
        "actual-revocation",
        "actual-infliction",
        chars,
    )
    assert rules.held(removed, actor, rules.MASTER) is None
    assert rules.room(removed, actor) is None and depth(removed, actor, grant.counterpart) == 2
    gate = removed.obligations[-1]
    gate.details["restoration_allowed"] = "true"
    restored = privileges.restore(removed, gate.id, actor.incarnation, None)
    assert rules.room(restored, actor) == grant.counterpart
    assert depth(restored, actor, grant.counterpart) == 2
    assert restored.sheets["2"].heat == actual.sheets["2"].heat


@pytest.mark.parametrize("amount,faces,total", [(2, (1, 1), 8), (-2, (2, 3), 7), (0, (2, 3), 9)])
def test_master_actual_known_roll_owned_adjustment_finishes_one_period_total(
    ledger, tmp_path, monkeypatch, amount, faces, total
):
    periods, game, worker, gateway, period = active(ledger, faces)
    service = approved(ledger, game, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.prior_permissions", canon)
    personal_bond(game)
    buy(service, rules.MASTER, "frame_grafting")
    action = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    pass_tags(game)
    assert saved(periods, period).progress["2"].roll.stage == "tag_window"
    current = next(x for x in game.choices(PLAYER) if x["kind"] == "enforcer_master_dog")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            current["id"],
            current["revision"],
            ChoiceAnswer(number=amount),
        )
    answer(game, PLAYER, "enforcer_master_dog", number=amount)
    after = saved(periods, period).progress["2"].roll
    assert after.total == total and after.faces == faces and after.stage == "choices"
    assert after.adjustments[-1].source == rules.MASTER and after.adjustments[-1].amount == amount
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


@pytest.mark.parametrize(
    "faces,extras",
    [
        ((1, 1), {"pavlov_good_soldier": "yes"}),
        ((4, 5), {"pavlov_bliss": "yes"}),
        ((6, 6), {"pavlov_good_soldier": "yes", "pavlov_bliss": "yes"}),
    ],
)
def test_pavlov_real_owned_keep_extras_leave_normal_tier_choices_and_original_ruling(
    ledger, tmp_path, monkeypatch, faces, extras
):
    _, game = ready(ledger, frame="THE ENFORCER")
    service = approved(ledger, game, tmp_path, monkeypatch)
    buy(service, rules.PAVLOV)
    game.dice.faces = faces
    action = start(
        game, obeying_orders=True, order_account="I am actually following the evacuation order"
    )
    from girlframe.delivery.m2_worker import GameWorker

    tick(GameWorker(game), Gateway())
    pass_tags(game)
    if faces == (1, 1):
        answer(game, PLAYER, "actor_keep", options=("tough",), fields=extras)
    elif faces == (4, 5):
        answer(
            game,
            PLAYER,
            "actor_keep",
            options=("tough", "in_control"),
            denied=("desperate",),
            fields=extras,
        )
    else:
        answer(game, PLAYER, "actor_keep", text="Actual high result Tag", fields=extras)
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual enough ruling")
    result = game.inspect(PLAYER, action)["result"]
    assert (
        "good_soldier" in result["positive"]
        if "pavlov_good_soldier" in extras
        else "good_soldier" not in result["positive"]
    )
    assert (
        "feels_as_good_as_sex" in result["positive"]
        if "pavlov_bliss" in extras
        else "feels_as_good_as_sex" not in result["positive"]
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_pending_master_can_decline_actual_optional_modifier_after_temporary_removal(
    ledger, tmp_path, monkeypatch
):
    periods, game, worker, gateway, period = active(ledger, (2, 3))
    service = approved(ledger, game, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.prior_permissions", canon)
    personal_bond(game)
    purchase = buy(service, rules.MASTER, "frame_grafting")
    action = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway)
    pass_tags(game)
    assert any(x["kind"] == "enforcer_master_dog" for x in game.choices(PLAYER))
    with ledger.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon = privileges.revoke(
            canon,
            2,
            1,
            purchase["id"],
            "Actual condition remains owed",
            str(uuid4()),
            event,
            {int(k): x.character_id for k, x in canon.sheets.items()},
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_known_source_revocation", canon, event_id=event
        )
    answer(game, PLAYER, "enforcer_master_dog", number=0)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert saved(periods, period).progress["2"].roll.total == 9 and game.dice.calls == 1
    assert privileges.suspended(state(game), purchase["id"])


def test_actual_free_compulsory_package_explicit_enforcer_rules_have_source_not_paid_receipts(
    ledger, tmp_path, monkeypatch
):
    from test_replacement import supplied
    from test_replacement_service import accept, pending, propose, quote

    replacement, game, _, work = pending(ledger)
    acquisition = approved(ledger, game, tmp_path, monkeypatch)
    replacement.missions.access.registry = acquisition.registry
    personal_bond(game)
    before = state(game)
    proposed = propose(replacement, work)
    quote(
        replacement, proposed["package_id"], supplied(additional_rules=(rules.MASTER, rules.PAVLOV))
    )
    current = replacement.get(PLAYER, work)
    applied = accept(replacement, work)
    assert (
        replacement.apply(
            PLAYER,
            "replace-confirm",
            work,
            current["revision"],
            current["game_revision"],
            current["package_revision"],
        )
        == applied
    )
    actual = state(game)
    actor = current_ref(actual, 2)
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions
    assert actual.requisitions == before.requisitions
    grants = [x for x in rules.grants(actual) if x.source_kind == "replacement"]
    assert len(grants) == 2 and all(x.purchase is None and x.source_work == work for x in grants)
    for grant in grants:
        assert rules.held(actual, actor, grant.rule) == grant
        with ledger.engine.connect() as c:
            proof(c, game, grant)
    assert depth(actual, actor, rules.held(actual, actor, rules.MASTER).counterpart) == 2
    assert rules.room(actual, actor) == rules.held(actual, actor, rules.MASTER).counterpart
    assert actual.sheets["2"].heat == before.sheets["2"].heat
