import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_off_duty_cycle import activate
from test_strain_effect_service import pending, selected

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_play_support import cancel_unrolled, resume
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


class Selector:
    def __init__(self, index=0):
        self.index, self.calls, self.sizes = index, 0, []

    def choose(self, size):
        self.calls += 1
        self.sizes.append(size)
        return self.index


def prepared(store, index=0):
    effects, game, period, first = pending(store)
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    selector = Selector(index)
    effects = EffectService(effects.strain, selector=selector)
    effects.apply(ADMIN, "actual-void-source", first, 1, state(game).revision, selected())
    for track, face, column in (("rebellion", 1, 1), ("budget", 3, 2)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        effects.strain.dice.face = face
        effects.strain.roll(ADMIN, "actual-d6-" + track, request.id, 1, state(game).revision)
        effects.strain.choose(
            ADMIN, "actual-column-" + track, request.id, 2, state(game).revision, column
        )
        if track == "rebellion":
            effects.apply(
                ADMIN,
                "actual-rebel-source",
                request.id + ":effect",
                1,
                state(game).revision,
                Choice(
                    rule_id="strain.rebellion.low.1.1",
                    account="Actual local organization",
                    target="city0",
                    faction=Faction(
                        id="group",
                        name="Local group",
                        kind="rebel",
                        cells=((0, 4),),
                        description="Local organizing",
                    ),
                ),
            )
    identity = request.id + ":effect"
    return effects, CycleService(effects.strain.periods), game, period, identity, selector


def apply(effects, game, identity, key="assign-actual-supply", **fields):
    values = dict(
        rule_id="strain.budget.low.3.2",
        account="An actual shipment did not arrive",
        missing_resource="PRIVATE_MISSING_RESOURCE",
    )
    values.update(fields)
    return effects.apply(ADMIN, key, identity, 1, state(game).revision, Choice(**values))


def ready(store, index=0):
    effects, cycle, game, period, identity, selector = prepared(store, index)
    apply(effects, game, identity)
    activate(cycle, game, period)
    return effects, cycle, game, period, identity, selector


def test_actual_uniform_assignment_is_one_committed_draw_and_hides_population_from_generic_views(
    ledger,
):
    effects, cycle, game, period, identity, selector = prepared(ledger)
    rev = state(game).revision
    choice = Choice(
        rule_id="strain.budget.low.3.2",
        account="Actual shipment loss",
        missing_resource="PRIVATE_MISSING_RESOURCE",
    )
    result = effects.apply(ADMIN, "one-draw", identity, 1, rev, choice)
    assert effects.apply(ADMIN, "one-draw", identity, 1, rev, choice) == result
    loss = state(game).supply_losses[0]
    assert selector.calls == 1 and selector.sizes == [2]
    assert tuple(x.entity for x in loss.population) == ("2", "3")
    assert loss.owner.incarnation == state(game).sheets["2"].character_id
    assert effects.get(ADMIN, identity)["supply_outcome"]["resource"] == "PRIVATE_MISSING_RESOURCE"
    assert "PRIVATE_MISSING_RESOURCE" in str(cycle.review(PLAYER, period))
    assert "PRIVATE_MISSING_RESOURCE" not in str(cycle.review(OTHER, period))
    with pytest.raises(WorkflowError):
        effects.get(PLAYER, identity)
    with ledger.engine.connect() as c:
        text = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        text += str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
        assert "PRIVATE_MISSING_RESOURCE" not in text and "population" not in text
    with pytest.raises(WorkflowError):
        apply(effects, game, identity, key="no-redraw")
    assert selector.calls == 1


@pytest.mark.parametrize("index", (-1, 2, True))
def test_invalid_selector_output_cannot_commit_an_assignment(ledger, index):
    effects, _, game, _, identity, selector = prepared(ledger, index)
    before = state(game)
    with pytest.raises(WorkflowError):
        apply(effects, game, identity)
    assert state(game) == before and not before.supply_losses and selector.calls == 1


def test_missing_resource_forged_target_pause_and_revocation_are_rejected_before_drawing(ledger):
    effects, _, game, _, identity, selector = prepared(ledger)
    for fields in ({"missing_resource": None}, {"target": "2"}, {"missing_resource": " "}):
        with pytest.raises(WorkflowError):
            apply(effects, game, identity, **fields)
    ledger.safety(OTHER, "pause-supply", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        apply(effects, game, identity)
    ledger.safety(OTHER, "resume-supply", ledger.status(OTHER)["revision"], pause=False)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        apply(effects, game, identity)
    assert selector.calls == 0 and not state(game).supply_losses


@pytest.mark.parametrize(
    "faces,total,level", [((1, 1), 4, "low"), ((3, 3), 8, "mid"), ((5, 5), 12, "high")]
)
def test_supply_penalty_is_separate_from_status_and_tags_at_every_tier(ledger, faces, total, level):
    _, cycle, game, period, _, selector = ready(ledger)
    game.dice = Dice(faces)
    action = start(game, play="go_off_duty", off_duty_id=period)
    assert state(game).supply_losses[0].action is None and game.dice.calls == 0
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["base_modifier"] == 4 and receipt["pre_total"] == total
    assert receipt["pre_modifiers"] == [{"source": "missed_supply", "amount": -2}]
    pass_tags(game)
    saved = cycle.review(PLAYER, period)["own"]["roll"]
    assert saved["modifier"] == 4 and saved["total"] == total
    assert [x["amount"] for x in saved["adjustments"]] == [-2]
    assert game.inspect(PLAYER, action)["result"]["tier"] == level
    assert state(game).supply_losses[0].action == action and selector.calls == game.dice.calls == 1
    tick(worker, gateway, 5)
    assert "PRIVATE_MISSING_RESOURCE" not in str(gateway.messages) and "population" not in str(
        receipt
    )


def test_void_observation_keeps_the_same_pre_roll_loss_and_uses_final_tier(ledger):
    from girlframe.services.m3_observation import ObservationService

    _, cycle, game, period, _, _ = ready(ledger)
    data = cycle.review(ADMIN, period)
    ObservationService(cycle.periods).order(
        ADMIN,
        "actual-observation",
        period,
        data["revision"],
        data["game_revision"],
        2,
        False,
        "Actual suspicion",
    )
    game.dice = Dice((4, 4))
    action = start(game, play="void_observation", off_duty_id=period)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    pass_tags(game)
    assert receipt["modifier_source"] == "Void Assets" and receipt["base_modifier"] == 0
    assert receipt["pre_total"] == 6 and game.inspect(PLAYER, action)["result"]["tier"] == "low"
    assert cycle.review(PLAYER, period)["own"]["roll"]["adjustments"][0]["amount"] == -2


def test_post_roll_personal_bond_adjustment_preserves_the_pre_roll_supply_penalty(ledger):
    from girlframe.engine.m2 import TagState, pair_key

    _, cycle, game, period, _, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(id="known", label="Known resolve", giver=3, observers=(1, 2, 3))
        )
        canon.sheets["2"].revision += 1
        canon.bonds[pair_key(2, 3)] = 1
        game.event(c, 1, "actual-known-tag", "synthetic.fixture_tag", canon)
    game.dice = Dice((4, 4))
    action = start(game, play="go_off_duty", off_duty_id=period)
    tick(GameWorker(game), Gateway())
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("known",),
        number=1,
        text="Relevant resolve",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 10
    assert game.inspect(PLAYER, action)["result"]["total"] == 12
    saved = cycle.review(PLAYER, period)["own"]["roll"]
    assert saved["modifier"] == 4 and saved["total"] == 12
    assert [x["amount"] for x in saved["adjustments"]] == [-2, 2]


def test_known_roll_resume_retains_assignment_penalty_and_prior_human_response(ledger):
    _, cycle, game, period, _, selector = ready(ledger)
    game.dice = Dice((3, 3))
    action = start(game, play="go_off_duty", off_duty_id=period)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(game, OTHER, "tag_window", options=("pass",))
    game.abort(ADMIN, "abort-supply-roll", action)
    tick(worker, gateway, 5)
    resume(game, PLAYER, "resume-supply-roll", action, game.inspect(PLAYER, action)["revision"])
    tick(worker, gateway, 2)
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    assert (
        game.inspect(PLAYER, action)["receipt"] == receipt
        and game.dice.calls == selector.calls == 1
    )
    assert game.inspect(PLAYER, action)["result"]["total"] == 8
    assert state(game).supply_losses[0].action == action
    game.rebuild()
    assert cycle.review(PLAYER, period)["own"]["roll"]["total"] == 8


def test_unrolled_cancellation_does_not_consume_or_redraw_the_assigned_loss(ledger):
    _, _, game, period, _, selector = ready(ledger)
    first = start(game, play="go_off_duty", off_duty_id=period)
    game.abort(ADMIN, "abort-before-supply-roll", first)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 5)
    cancel_unrolled(
        game, PLAYER, "cancel-before-supply-roll", first, game.inspect(PLAYER, first)["revision"]
    )
    assert state(game).supply_losses[0].action is None and selector.calls == 1
    second = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway)
    assert second != first and state(game).supply_losses[0].action == second
    assert game.dice.calls == 1 and selector.calls == 1


def test_concurrent_assignments_do_not_draw_again_and_failure_rolls_back_effect(
    ledger, monkeypatch
):
    effects, _, game, _, identity, selector = prepared(ledger)
    before = state(game)
    original = effects.strain._save

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic after-draw failure")

    monkeypatch.setattr(effects.strain, "_save", fail)
    with pytest.raises(RuntimeError):
        apply(effects, game, identity)
    assert state(game) == before and selector.calls == 1
    monkeypatch.setattr(effects.strain, "_save", original)

    def run(i):
        try:
            effects.apply(
                ADMIN,
                "race-" + str(i),
                identity,
                1,
                before.revision,
                Choice(
                    rule_id="strain.budget.low.3.2",
                    account="Actual shipment",
                    missing_resource="Supplies",
                ),
            )
            return True
        except WorkflowError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]
    assert len(state(game).supply_losses) == 1 and selector.calls == 2


def test_native_supply_input_has_no_recipient_picker_and_owner_sees_penalty_before_confirm(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_off_duty_cycle import open_action
    from girlframe.discord_adapter.m3_strain_effects import open_effect

    effects, cycle, game, period, identity, selector = prepared(ledger)

    async def run():
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_effect(handler, effects, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"missing_resource", "account"}
        form.values = {
            "missing_resource": "PRIVATE_NATIVE_RESOURCE",
            "account": "Actual missing delivery",
        }
        await form.confirm.callback(current(1, 17201))
        assert form.completed and selector.calls == 1
        activate(cycle, game, period)
        owner = current(2)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_action(owner, cycle, period, "play")
        confirm = owner.edit_original_response.call_args.kwargs["view"]
        assert "-2 missed supply" in confirm.text() and "PRIVATE_NATIVE_RESOURCE" in confirm.text()
        assert game.dice.calls == 0

    asyncio.run(run())


@pytest.mark.parametrize("phase", ("before", "after"))
def test_changed_character_cannot_enter_the_draw_or_inherit_an_assigned_loss(ledger, phase):
    from test_actor_service import replace_profile_id

    if phase == "before":
        effects, _, game, _, identity, selector = prepared(ledger)
        replace_profile_id(ledger, 2)
        before = state(game)
        with pytest.raises(WorkflowError):
            apply(effects, game, identity)
        assert selector.calls == 0 and state(game) == before
    else:
        _, _, game, period, _, selector = ready(ledger)
        replace_profile_id(ledger, 2)
        before = state(game)
        with pytest.raises(WorkflowError):
            start(game, play="go_off_duty", off_duty_id=period)
        assert selector.calls == 1 and game.dice.calls == 0 and state(game) == before


def test_rolled_resource_failure_restores_unconsumed_loss_but_never_redraws_recipient(
    ledger, monkeypatch
):
    _, _, game, period, _, selector = ready(ledger)
    action = start(game, play="go_off_duty", off_duty_id=period)
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    before = state(game)
    original = game.event

    def fail(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(args) > 3 and args[3] == "m3.rolled":
            raise RuntimeError("synthetic after-receipt failure")
        return result

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        game.roll(PLAYER, "retry-supply-roll", action)
    assert state(game) == before and state(game).supply_losses[0].action is None
    assert game.inspect(PLAYER, action)["receipt"] is None and selector.calls == 1
    monkeypatch.setattr(game, "event", original)
    game.roll(PLAYER, "retry-supply-roll", action)
    assert state(game).supply_losses[0].action == action and selector.calls == 1
