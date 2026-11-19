"""High Rebellion's saved draw leads to a genuine interception or the same Frame's recovery."""

import asyncio

import pytest
from test_bunk_harpy import SecondGirl
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_physical_state import CockpitAction, InitialPlacement
from girlframe.engine.m3_rebel_frame_theft import RULE, thefts
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import AdversaryPilot, Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_rebel_frame_theft import TheftService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@pytest.mark.parametrize("outcome", ("stop", "lose"))
def test_high_rebellion_theft_preserves_random_original_and_actual_outcome(ledger, outcome):
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    controller = GuildViewer(4, 200, True, False)
    ledger.join(controller, "actual-thief-controller")
    group = Faction(id="theft-cell", kind="rebel", name="Rebel Cell", cells=((0, 0),))
    enemy = ActorRef(kind="external_pilot", entity="original-thief")
    world_pilot = AdversaryPilot(
        id=enemy.entity,
        name="Rebel Foot Scout",
        kind="rebel",
        girl="MOCKINGBIRD",
        frame="JANUS",
        assets=(),
        controller=4,
        faction=group.id,
        cell=(2, 0),
        revealed=True,
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial().model_copy(update=dict(pilots=(world_pilot,), factions=(group,)))
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        canon = install_external_pose(
            canon,
            enemy,
            (0, 0),
            (2, 0),
            "outside_frame",
            "foot-scout-position",
            "The original Scout is on foot at the base.",
            owner=4,
            judge=1,
        )
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "real-original-frame-occupancy", "synthetic.physical_setup", canon)
    cast = CastService(ActorService(strain.missions))
    change(cast, controller, "join", enemy)
    period = prepared(strain, game, high=frozenset({"rebellion"}))
    index = SecondGirl()
    effects = EffectService(strain, selector=index)
    for track, face, column, choice in (
        (
            "void",
            2,
            1,
            Choice(
                rule_id="strain.void.low.2.1",
                account="A Gorgon arrives.",
                gorgon=gorgon("dormant", "theft-perimeter", (0, 1)),
            ),
        ),
        (
            "budget",
            5,
            2,
            Choice(rule_id="strain.budget.low.5.2", account="Rooms reassigned.", rooms=((2, 3),)),
        ),
        ("rebellion", 6, 1, None),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, "theft-die-" + track, request.id, 1, state(game).revision)
        selected = strain.choose(
            ADMIN, "theft-column-" + track, request.id, 2, state(game).revision, column
        )
        work = request.id + ":effect"
        if choice:
            effects.apply(ADMIN, "theft-other-" + track, work, 1, state(game).revision, choice)
    assert selected["rule_id"] == RULE
    inbox = InboxService(ledger)

    async def native(viewer, number, *, stage=False, **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        if stage:
            await open_effect(click, effects, work)
        else:
            entry = next(x for x in inbox.items(viewer) if x.task == "m3_rebel_frame_theft")
            await InboxView(inbox, viewer.user_id).route(click, entry)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submit = current(viewer.user_id, number + 1)
        await form.confirm.callback(submit)
        assert form.completed, (
            submit.edit_original_response.call_args,
            submit.followup.send.call_args,
        )

    revision = state(game).revision
    account = "The original Scout makes an attempt to steal a Frame."
    asyncio.run(
        native(
            ADMIN,
            40700,
            stage=True,
            theft_base=("base0",),
            frame_thief=(enemy.entity,),
            account=account,
        )
    )
    assert (
        effects.apply(
            ADMIN,
            "40701",
            work,
            1,
            revision,
            Choice(
                rule_id=RULE,
                target="base0",
                victim=enemy.entity,
                account=account,
            ),
        )["state"]
        == "pending"
    )
    (draw,) = thefts(state(game))
    assert draw.frame.owner.entity == "3" and index.population_sizes == [2]
    service = TheftService(strain)
    assert service.get(ADMIN, work)["frame"] is None
    with pytest.raises(WorkflowError, match="original participants"):
        service.get(OTHER, work)
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="original person"):
        service.act(
            ADMIN, "wrong-thief-author", work, revision, 900, "attempt", account="Fake attempt"
        )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.act(
            controller, "stale-theft", work, revision - 1, 900, "attempt", account="Actual attempt"
        )
    asyncio.run(native(controller, 40710, choice=("attempt",), account="PRIVATE_ATTEMPT"))
    assert service.get(OTHER, work)["frame"] == draw.frame.instance
    assert service.get(PLAYER, work)["account"] == "PRIVATE_ATTEMPT"
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="Strain"):
        activate(cycle, game, period)

    def physical_frame():
        return next(x for x in state(game).placements if x.actor == draw.frame.owner)

    if outcome == "stop":
        asset = next(x.id for x in state(game).sheets["2"].assets if x.family == "girl")
        game.dice.faces = (4, 5)
        action = game.begin(
            PLAYER,
            "intercept-original-thief",
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="engage",
                heat=0,
                target_actor=enemy,
                context="I drive back the thief.",
                trigger_confirmed=True,
                piloting=False,
            ),
        )["action_id"]
        worker, gateway = GameWorker(game), Gateway()
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, controller, "tag_window", options=("pass",))
        answer(
            game,
            PLAYER,
            "engage_maneuvers",
            options=("drive_back", "protect"),
            fields={"drive_back": asset, "protect": asset},
            text="I drive the original thief back and protect the actual cockpit.",
        )
        assert game.inspect(PLAYER, action)["state"] == "complete"
        with pytest.raises(WorkflowError, match="original Girl"):
            service.act(
                ADMIN,
                "cannot-claim-interception",
                work,
                state(game).revision,
                900,
                "stop",
                action=action,
            )
        asyncio.run(native(PLAYER, 40720, stop=(action,)))
        tick(worker, gateway, 5)
        assert thefts(state(game))[0].stopped_by and physical_frame().frame_cell == (0, 0)
        assert activate(cycle, game, period)["phase"] == "active"
    else:
        asyncio.run(native(PLAYER, 40730, choice=("pass",), account="I have no way to intercept."))
        with pytest.raises(WorkflowError, match="original person"):
            service.act(
                ADMIN,
                "owner-still-chooses",
                work,
                state(game).revision,
                900,
                "lose",
                account="Premature.",
            )
        asyncio.run(native(OTHER, 40740, choice=("pass",), account="I let the thief leave."))
        asyncio.run(
            native(
                ADMIN, 40750, choice=("lose",), account="The original Frame is now out of reach."
            )
        )
        missing = physical_frame()
        assert (
            missing.girl_cell == (0, 0)
            and missing.frame_cell is None
            and missing.frame_instance == draw.frame.instance
        )
        assert activate(cycle, game, period)["phase"] == "active"
        physical = PhysicalService(ledger)
        menu = physical.preview(OTHER)
        assert menu["stolen_frame"] and not menu["can_record_unknown"]
        with pytest.raises(WorkflowError, match="Recover the stolen original Frame"):
            physical.propose(
                OTHER,
                "no-new-setup-for-stolen-frame",
                menu["game_revision"],
                InitialPlacement(
                    actor=draw.frame.owner,
                    frame_instance=draw.frame.instance,
                    mode="outside_frame",
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    account="I report the original Frame back without its custodian.",
                    facts_confirmed=True,
                ),
            )
        with pytest.raises(WorkflowError, match="same known cell"):
            physical.operate(
                OTHER,
                "lost-frame-unavailable",
                menu["game_revision"],
                CockpitAction(
                    actor=draw.frame.owner,
                    operation="pilot",
                    expected_position=menu["position_sha256"],
                    account="I try to activate the missing Frame.",
                    confirmed=True,
                ),
            )
        asyncio.run(
            native(controller, 40760, choice=("return",), account="I bring this exact Frame back.")
        )
        ledger.engine.dispose()
        asyncio.run(
            native(OTHER, 40770, choice=("recover",), account="I recover my actual Frame here.")
        )
        assert (
            physical_frame().frame_instance == draw.frame.instance
            and physical_frame().frame_cell == (0, 0)
        )
        assert physical_frame().girl_cell == missing.girl_cell and thefts(state(game))[0].returned
        assert not physical.preview(OTHER)["stolen_frame"]
