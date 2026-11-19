"""The Scientist completes a printed Project step only after the actual lab effects."""

import asyncio

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared
from test_physical_operations import place

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_private_scene import records
from girlframe.engine.m3_scientist_lab import LabAnswer, steps
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService
from girlframe.services.onboarding import WorkflowError


def create_scientist(ledger):
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
    creation.activate(ADMIN, "lab-scientist", preview["revision"], preview["game_revision"], True)


async def submit_private(inbox, identity, viewer, sequence, decision, **values):
    click = current(viewer.user_id, sequence)
    await click.response.defer(ephemeral=True)
    item = next(x for x in inbox.items(viewer) if x.identity == identity)
    await InboxView(inbox, viewer.user_id).route(click, item)
    form = click.edit_original_response.call_args.kwargs["view"]
    form.values.update(choice=(decision,), **values)
    sent = current(viewer.user_id, sequence + 1)
    await form.confirm.callback(sent)
    assert form.completed, sent.followup.send.call_args


def test_owned_scientist_lab_installs_and_clears_actual_original_assets(ledger):
    cycle, game, period = prepared(ledger, before_period=lambda _: create_scientist(ledger))
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


def test_private_scientist_exchange_changes_one_actual_owned_void_asset(ledger):
    _, game, _ = prepared(ledger, before_period=lambda _: create_scientist(ledger))
    game.leave_scene(PLAYER, "scientist-private-lab", 900)
    service = HandlerPrivateSceneService(ledger, game)
    with pytest.raises(WorkflowError, match="operational Base laboratory"):
        service.invite(ADMIN, "no-original-lab", state(game).revision, 900, playbook="Scientist")
    with ledger.transaction() as c:
        canon = place(state(game), 3, mode="outside_frame")
        original = next(x for x in canon.sheets["3"].assets if x.family == "girl")
        original.void, original.concealed = True, True
        game.event(
            c, OTHER.user_id, "synthetic-lab-fixture", "synthetic.owned_lab_resources", canon
        )
    inbox = InboxService(ledger)

    async def invite():
        click = current(1, 49600)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, HandlerPlayService(ledger))
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "scientist_private")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(offer=("offer",))
        sent = current(1, 49601)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(invite())
    (value,) = records(state(game))
    assert value.lab == "base0" and not any(x.identity == value.id for x in inbox.items(PLAYER))

    async def submit(viewer, sequence, decision, **values):
        await submit_private(inbox, value.id, viewer, sequence, decision, **values)

    asyncio.run(submit(OTHER, 49610, "consent"))
    asyncio.run(submit(ADMIN, 49612, "attest"))
    asyncio.run(submit(OTHER, 49614, "attest"))
    replacement = "PRIVATE_REPLACEMENT_IN_LAB"
    asyncio.run(
        submit(
            ADMIN,
            49616,
            "scientist_plan_exchange",
            asset_name=replacement,
            asset_description="The actual non-Void replacement",
        )
    )
    pending = state(game)
    assert service.menu(ADMIN, value.id)["assets"] == ()
    assert service.menu(OTHER, value.id)["assets"] == ((original.id, original.name),)
    assert next(x for x in pending.sheets["3"].assets if x.id == original.id).concealed
    with pytest.raises(WorkflowError, match="your own"):
        service.respond(
            ADMIN,
            "take-ownership",
            value.id,
            pending.revision,
            "scientist_exchange",
            text=original.id,
        )
    with pytest.raises(WorkflowError, match="ordinary Void-touched"):
        service.respond(
            OTHER,
            "unowned-excision",
            value.id,
            pending.revision,
            "scientist_exchange",
            text="unknown",
        )
    ledger.engine.dispose()
    asyncio.run(submit(OTHER, 49620, "scientist_exchange", asset=(original.id,)))
    assert (
        service.respond(
            OTHER,
            "49621",
            value.id,
            pending.revision,
            "scientist_exchange",
            text=original.id,
        )["phase"]
        == "complete"
    )
    after = state(game)
    (exchanged,) = records(after)
    assert exchanged.outcome == "scientist_exchanged" and exchanged.removed_asset == original.id
    old = {x.id: x for x in pending.sheets["3"].assets if x.id != original.id}
    new = {x.id: x for x in after.sheets["3"].assets}
    inserted = new.pop(exchanged.installed_asset)
    assert new == old and inserted.name == replacement and not inserted.void
    assert not steps(after, current_ref(after, 1))


@pytest.mark.parametrize("combined", [False, True])
def test_scientist_owned_native_void_gain_and_actual_threshold_followup(ledger, combined):
    from test_void_service import respond as resolve_void

    from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
    from girlframe.services.m3_void import VoidService

    _, game, _ = prepared(ledger, before_period=lambda _: create_scientist(ledger))
    game.leave_scene(PLAYER, "private-void-lab", 900)
    with ledger.transaction() as connection:
        canon = place(state(game), 3, mode="outside_frame")
        sheet = canon.sheets["3"]
        target = next(x for x in sheet.assets if x.family == "frame")
        removable = next(x for x in sheet.assets if x.family == "girl")
        if combined:
            removable.void = True
            for resource in sheet.assets:
                if resource.family == "frame" and resource.id != target.id:
                    resource.void = True
        game.event(connection, 3, "lab-assets", "synthetic.private_lab_assets", canon)
    private = HandlerPrivateSceneService(ledger, game)
    inbox = InboxService(ledger)
    identity = private.invite(
        ADMIN, "consensual-void", state(game).revision, 900, playbook="Scientist"
    )["id"]

    async def prepare_experiment():
        await submit_private(inbox, identity, OTHER, 49700, "consent")
        await submit_private(inbox, identity, ADMIN, 49702, "attest")
        await submit_private(inbox, identity, OTHER, 49704, "attest")
        if combined:
            await submit_private(
                inbox,
                identity,
                ADMIN,
                49706,
                "scientist_plan_exchange",
                asset_name="Clinical replacement",
                asset_description="Original owned replacement",
                effects=("gain_void",),
            )
            await submit_private(
                inbox, identity, OTHER, 49708, "scientist_exchange", asset=(removable.id,)
            )
        else:
            await submit_private(inbox, identity, ADMIN, 49706, "scientist_cause_void")

    asyncio.run(prepare_experiment())
    assert not private.menu(ADMIN, identity)["assets"]
    assert target.id in dict(private.menu(OTHER, identity)["assets"])
    assert not any(x.identity == identity for x in inbox.items(PLAYER))
    before = state(game)
    change = dict(asset=target.id, text="PRIVATE_SYNTHETIC_LAB_CHANGE")
    with pytest.raises(WorkflowError, match="your own"):
        private.respond(
            ADMIN, "wrong-owner", identity, before.revision, "scientist_gain_void", **change
        )
    with pytest.raises(WorkflowError, match="your own"):
        private.respond(
            OTHER, "stale", identity, before.revision - 1, "scientist_gain_void", **change
        )
    ledger.safety(PLAYER, "hold-lab-experiment", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="pause"):
        private.respond(OTHER, "paused", identity, before.revision, "scientist_gain_void", **change)
    assert state(game).sheets["3"] == before.sheets["3"]
    ledger.safety(PLAYER, "resume-lab-experiment", ledger.status(PLAYER)["revision"], pause=False)
    ledger.engine.dispose()
    asyncio.run(
        submit_private(
            inbox,
            identity,
            OTHER,
            49710,
            "scientist_gain_void",
            asset=(target.id,),
            account=change["text"],
        )
    )
    after = state(game)
    result = private.respond(
        OTHER, "49711", identity, before.revision, "scientist_gain_void", **change
    )
    assert result["revision"] == after.revision == state(game).revision
    (source,) = records(after)
    assert source.void_asset == target.id and source.outcome == "scientist_void_gained"
    assert bool(source.installed_asset) == combined
    corrupted = next(x for x in after.sheets["3"].assets if x.id == target.id)
    assert corrupted.void and corrupted.description == change["text"]
    if not combined:
        assert not source.required_work
        assert private.menu(OTHER, identity)["phase"] == "complete"
        return
    (work,) = source.required_work
    assert private.menu(OTHER, identity)["phase"] == "scientist_followup"
    assert any(x.identity == work for x in inbox.items(OTHER))
    assert not any(x.identity == work for x in inbox.items(PLAYER))
    void = VoidService(ledger)
    assert void.get(OTHER, work)["stage"] == "abandoned"
    targets = tuple(x for x in after.sheets["3"].assets if x.family == "frame")
    transformed = Gorgon(
        id="actual-lab-frame-gorgon",
        name="The abandoned Frame",
        gorgon_class="benevolent",
        types=("incubus",),
        cell=(0, 0),
        core_plan=CorePlan(assets=(targets[0].id,), weakness="Open access"),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                damaged=x.damaged,
                void=x.void,
            )
            for x in targets
        ),
    )
    resolve_void(
        void,
        work,
        "abandoned",
        dict(gorgon=transformed.model_dump(mode="json"), account="Actual original abandoned Frame"),
        viewer=ADMIN,
    )
    settled = state(game)
    assert settled.sheets["3"].frame_scrapped
    assert any(x.id == transformed.id for x in settled.world.gorgons)
    assert private.menu(OTHER, identity)["phase"] == "complete"
