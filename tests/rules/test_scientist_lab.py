"""The Scientist completes a printed Project step only after the actual lab effects."""

import asyncio

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared

from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_scientist_lab import LabAnswer, steps
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError


def test_owned_scientist_lab_installs_and_clears_actual_original_assets(ledger):
    def create(_):
        creation = HandlerCreationService(ledger)
        approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
        ledger.policy = ledger.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(
                    update=dict(subsystems=approval.subsystems | {"plays", "playbooks"})
                ),
                owner_m3_rulings=rulings.model_copy(
                    update=dict(handler_creation="owned_shared_choices_preserve_existing")
                ),
            )
        )
        save(creation, complete(creation, "Scientist"))
        agree(creation)
        preview = creation.view(ADMIN)
        creation.activate(
            ADMIN, "lab-scientist", preview["revision"], preview["game_revision"], True
        )

    cycle, game, period = prepared(ledger, before_period=create)
    with ledger.transaction() as c:
        original = state(game)
        patient = original.sheets["3"]
        assets = [x for x in patient.assets if x.family == "girl"]
        for i in range(len(assets), 4):
            value = AssetState(
                id="synthetic-lab-asset-" + str(i),
                family="girl",
                name="Existing gear",
                description="Actual synthetic equipment before the proposed lab",
                damaged=False,
            )
            assets.append(value)
            patient.assets.append(value)
        assets[0].void = True
        assets[0].concealed = True
        prior, discarded = assets[0].id, assets[-1].id
        game.event(c, 3, "synthetic-original-lab-condition", "synthetic.asset_fixture", original)
    activate(cycle, game, period)

    async def submit(viewer, action, sequence, **values):
        click = current(viewer.user_id, sequence)
        await click.response.defer(ephemeral=True)
        await open_action(click, cycle, period, action)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        form.controls()
        sent = current(viewer.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(
        submit(
            ADMIN,
            "handler_scene",
            47400,
            kind=("scientist_lab",),
            participants=("3",),
            asset_name="PRIVATE_NEW_IMPLANT",
            asset_description="Private synthetic implant.",
            summary="PRIVATE_LAB_ATTENDANCE",
        )
    )
    assert cycle.review(PLAYER, period)["handler_scene"] is None
    assert cycle.review(OTHER, period)["handler_scene"]["lab"]["name"] == "PRIVATE_NEW_IMPLANT"
    with pytest.raises(WorkflowError):
        call(cycle, game, PLAYER, period, "acknowledge", None, LabAnswer(remove_void=prior))
    with pytest.raises(WorkflowError, match="At the Asset cap"):
        call(cycle, game, OTHER, period, "acknowledge", None, LabAnswer(remove_void=prior))
    before = state(game).sheets["3"]
    asyncio.run(
        submit(
            OTHER,
            "ack:handler",
            47410,
            confirm=("yes",),
            remove_void=(prior,),
            replace=(discarded,),
        )
    )
    assert "lab_answer" not in cycle.review(ADMIN, period)["handler_scene"]
    assert state(game).sheets["3"] == before
    assert not steps(state(game), current_ref(state(game), 1))
    ledger.engine.dispose()
    pending = cycle.review(ADMIN, period)
    with pytest.raises(WorkflowError, match="affected Girl"):
        call(cycle, game, ADMIN, period, "acknowledge", None, LabAnswer(remove_void=prior))
    asyncio.run(submit(ADMIN, "ack:handler", 47420, confirm=("yes",)))
    cycle.acknowledge(ADMIN, "47421", period, pending["revision"], pending["game_revision"], None)
    actual = state(game)
    (step,) = steps(actual, current_ref(actual, 1))
    assert step.period == period and step.target == current_ref(actual, 3)
    assert step.removed_void_from == prior and step.replaced == discarded
    after = {x.id: x for x in actual.sheets["3"].assets if x.family == "girl"}
    assert len(after) == 4 and discarded not in after
    assert after[step.installed].void and after[step.installed].name == "PRIVATE_NEW_IMPLANT"
    assert not after[prior].void and not after[prior].concealed
    assert not cycle.review(ADMIN, period)["scientist_lab_available"]
    assert not any(
        w["kind"] == "off_duty_handler_scene" for w in cycle.periods.get(ADMIN, period)["work"]
    )
