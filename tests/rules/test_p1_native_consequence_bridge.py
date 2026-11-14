"""Native consequence handoffs through select/modal callbacks, not live Discord."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, roll_for
from test_strain_service import ready
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import FormSelect, NarrativeModal, NativeForm
from girlframe.discord_adapter.m3_missions import open_mission
from girlframe.discord_adapter.m3_off_duty import open_period
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.discord_adapter.m3_punishments import open_details
from girlframe.discord_adapter.m3_strain import FACT_LABELS, open_work
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService

ledger = ledger_fixture


def confirm_native(viewer, opener, values):
    async def run():
        interaction = current(viewer.user_id, int(uuid4()))
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await opener(interaction)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(999))
        for index, field in enumerate(form.fields):
            assert form.index == index
            if field.key in values:
                choice = current(viewer.user_id, int(uuid4()))
                choice.channel_id = 900
                if field.options:
                    selector = next(x for x in form.children if isinstance(x, FormSelect))
                    assert set(values[field.key]) <= {x.value for x in selector.options}
                    selector._values = list(values[field.key])
                    await selector.callback(choice)
                else:
                    modal = NarrativeModal(form, field)
                    modal.input._value = values[field.key]
                    await modal.on_submit(choice)
            if index + 1 < len(form.fields):
                navigation = current(viewer.user_id, int(uuid4()))
                navigation.channel_id = 900
                await form.next.callback(navigation)
        confirmation = current(viewer.user_id, int(uuid4()))
        confirmation.channel_id = 900
        await form.confirm.callback(confirmation)
        assert form.completed, interaction.edit_original_response.call_args_list

    asyncio.run(run())


def mission_choice(service, viewer, identity, action):
    confirm_native(
        viewer,
        lambda interaction: open_mission(interaction, service, identity),
        {"action": (action,)},
    )
    return service.get(viewer, identity)["mission"]


def test_native_discipline_and_strain_selectors_bridge_mission_to_recovery(ledger, monkeypatch):
    # No provider key or live service is needed by the human-operated path.
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DiscordBot",
        "DISCORD_BOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    strain, game = ready(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    missions = strain.missions
    WorldService(missions).initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    # Legal synthetic starting condition, before the journey and its source histories.
    with ledger.transaction() as c:
        baseline = state(game)
        for sheet in baseline.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.initial_nonvoid_condition", baseline)
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())

    offered = missions.offer(ADMIN, str(uuid4()), "PRIVATE_P1_FIRST_OBJECTIVE", (2, 3))
    mission_choice(missions, PLAYER, offered["id"], "accept")
    mission_choice(missions, OTHER, offered["id"], "accept")
    mission_choice(missions, ADMIN, offered["id"], "start")

    game.dice = Dice((4, 5))
    worker, gateway = GameWorker(game), Gateway()
    action = start(game)
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_keep",
        options=("tough", "in_control"),
        denied=("desperate",),
    )
    answer(game, ADMIN, "handler_keep", flag=True, text="PRIVATE_P1_ENOUGH_TO_PROCEED")
    tick(worker, gateway, 8)
    saved_receipt = game.inspect(PLAYER, action)["receipt"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1

    mission_choice(missions, ADMIN, offered["id"], "end_success")
    discipline = PunishmentService(ledger, missions.access.registry)
    pending = missions.get(ADMIN, offered["id"])["work"]
    assert len(pending) == 1 and pending[0]["kind"] == "punishment" and pending[0]["subject"] == 3
    confirm_native(
        ADMIN,
        lambda interaction: open_details(
            interaction, discipline, pending[0]["id"], "stimulant_injection"
        ),
        {"confirm": ("yes",)},
    )
    complete = mission_choice(missions, ADMIN, offered["id"], "advance")
    assert complete["phase"] == "complete"
    assert state(game).sheets["2"].permissions == 2 and state(game).sheets["3"].permissions == 1

    confirm_native(
        ADMIN,
        lambda interaction: open_period(interaction, strain.periods),
        {"confirm": ("begin",)},
    )
    period = strain.periods.current(ADMIN)
    assert period is not None
    confirm_native(
        ADMIN,
        lambda interaction: open_work(
            interaction, strain, period["id"] + ":off_duty_strain_start:1"
        ),
        {**{key: ("no",) for key in FACT_LABELS}, "account": "Reviewed actual session triggers"},
    )
    choices = (
        (
            "void",
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="Actual next map threat",
                gorgon=gorgon("directed", "p1-next-threat", (10, 0)),
            ),
        ),
        (
            "rebellion",
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual local dissent",
                target="city0",
                faction=Faction(
                    id="p1-local-group",
                    name="Local group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Synthetic local dissent",
                ),
            ),
        ),
        (
            "budget",
            5,
            Choice(
                rule_id="strain.budget.low.5.2",
                account="Actual shared accommodation",
                rooms=((2, 3),),
            ),
        ),
    )
    effects = EffectService(strain)
    for track, face, choice in choices:
        request = next(
            x
            for x in state(game).strain.requests
            if x.period_id == period["id"] and x.track == track
        )
        strain.dice.face = face
        confirm_native(
            ADMIN,
            lambda interaction, identity=request.id: open_work(interaction, strain, identity),
            {"confirm": ("roll",)},
        )
        confirm_native(
            ADMIN,
            lambda interaction, identity=request.id: open_work(interaction, strain, identity),
            {"option": ("2" if track == "budget" else "1",)},
        )
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)

    cycle = CycleService(strain.periods)
    activate(cycle, game, period["id"])
    inbox = InboxService(ledger)
    for viewer, faces in ((PLAYER, (2, 2)), (OTHER, (4, 4))):
        assert any(item.task == "m3_off_duty" for item in inbox.items(viewer))
        # Real worker rolls and Tag choices, then actual native scene/recovery forms.
        roll_for(cycle, game, period["id"], viewer, faces)
        confirm_native(
            viewer,
            lambda interaction: open_action(interaction, cycle, period["id"], "scene"),
            {"kind": ("decline",)},
        )
        confirm_native(
            viewer,
            lambda interaction: open_action(interaction, cycle, period["id"], "recover"),
            {"repairs": ("yes",)},
        )
        assert CycleService(strain.periods).review(viewer, period["id"])["own"]["recovered"]
    finish_routine(cycle, game, period["id"])
    assert call(cycle, game, ADMIN, period["id"], "finish", movement(game))["phase"] == "complete"
    assert CycleService(strain.periods).review(PLAYER, period["id"])["own"]["recovered"]
    assert game.inspect(PLAYER, action)["receipt"] == saved_receipt

    restarted = MissionService(ledger, missions.access.registry)
    second = restarted.offer(ADMIN, str(uuid4()), "PRIVATE_P1_NEXT_OBJECTIVE", (2, 3))
    for viewer in (PLAYER, OTHER):
        second = mission_choice(restarted, viewer, second["id"], "accept")
    assert mission_choice(restarted, ADMIN, second["id"], "start")["phase"] == "active"
    assert state(game).world.completed_off_duty == (period["id"],)
    with ledger.engine.connect() as c:
        assert strain.periods._pending(c, period["id"]) == []
        public = str(list(c.scalars(sa.select(t.events.c.payload_json)))) + str(
            list(c.scalars(sa.select(t.commands.c.outcome_json)))
        )
    for secret in (
        "PRIVATE_P1_FIRST_OBJECTIVE",
        "PRIVATE_P1_NEXT_OBJECTIVE",
        "PRIVATE_P1_ENOUGH_TO_PROCEED",
        "PRIVATE_HANDLER_SCENE",
        "PRIVATE_PERFORMANCE_ACCOUNT",
    ):
        assert secret not in public
