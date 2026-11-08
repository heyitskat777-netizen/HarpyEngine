"""Real Doll tiers, source-owned consequences and canonical scene exit/re-entry."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_vatgrown as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_vatgrown import DollService, prove
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, *, handler=False):
    _, game = service(store, girl="VATGROWN", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with store.transaction() as c:
        original = state(game)
        original.world = initial()
        original = place(original, 2, mode="outside_frame")
        original = place(original, 3, mode="outside_frame")
        original.sheets["2"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_Doll_body_scene", original)
    if handler:
        cast = CastService(ActorService(MissionService(store)))
        data = cast.view(ADMIN, 900)
        cast.change(
            ADMIN,
            str(uuid4()),
            900,
            data["game_revision"],
            data["cast_revision"],
            "join",
            current_ref(state(game), 1),
        )
    return game, GameWorker(game), Gateway(), DollService(game)


def choose(game, viewer, kind, options=(), text="", *, native=False):
    if not native:
        return answer(game, viewer, kind, options=options, text=text)
    from girlframe.discord_adapter.m3_vatgrown import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def submit():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=options, text=text)
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())


def roll(game, worker, gateway, *, faces=(4, 5), heat=0, native=False):
    game.dice.faces = faces
    before = state(game)
    if native:
        from girlframe.discord_adapter.m3_vatgrown import open_vatgrown

        async def start():
            interaction = current(2, 97801)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_vatgrown(interaction, DollService(game))
            menu = interaction.edit_original_response.call_args.kwargs["view"]
            menu.values["source"] = ("play",)
            opened = current(2, 97802)
            await menu.confirm.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                target=(current_ref(before, 3).token,),
                identity=(),
                gain=("0",),
                heat=(str(heat),),
                account="I actually remain quiet beside the workbench",
            )
            response = current(2, 97803)
            await form.confirm.callback(response)
            assert form.completed, response.edit_original_response.call_args_list

        asyncio.run(start())
        with game.store.engine.connect() as c:
            action = c.scalar(sa.select(t.m2["m2_actions"].c.id))
    else:
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            before.sheets["2"].revision,
            PlayInput(
                play=rules.PLAY,
                target_actor=current_ref(before, 3),
                heat=heat,
                context="I actually fade into the background",
                trigger_confirmed=True,
            ),
        )["action_id"]
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    tick(worker, gateway, 3)
    pass_tags(game)
    return action


def target_attempt(game):
    return game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="flirt", target=2, heat=0, context="I address her directly", trigger_confirmed=True
        ),
    )


def test_mid_quiet_real_offered_secret_private_history_and_exact_source_integrity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    action = roll(game, worker, gateway, native=True, heat=1)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "vat_doll_benefits")
    frozen = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("quiet", "information")),
        )
    assert state(game).model_dump_json() == frozen
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"] - 1,
            ChoiceAnswer(options=("quiet", "information")),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("quiet", "unsupported")),
        )
    assert state(game).model_dump_json() == frozen
    choose(game, PLAYER, "vat_doll_benefits", ("quiet", "information"), native=True)
    choose(
        game,
        OTHER,
        "vat_doll_information",
        text="PRIVATE_DOLL_SECRET the vault is unguarded",
        native=True,
    )
    saved = controls.view(PLAYER, action)
    assert saved["quiet"] and saved["information"]["answer"].startswith("PRIVATE_DOLL_SECRET")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    assert state(game).sheets["3"] == before.sheets["3"]
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, action)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), action).complete
        payload = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_DOLL_SECRET" not in payload
        forged = state(game)
        value = rules.source(forged, action)
        rules.put(forged, value.model_copy(update={"target": value.actor}))
        with pytest.raises(WorkflowError):
            prove(game, c, forged, action)
    tick(worker, gateway, 5)
    revision, calls = state(game).revision, game.dice.calls
    with pytest.raises(WorkflowError, match="attention"):
        target_attempt(game)
    assert state(game).revision == revision and game.dice.calls == calls

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.identity == action and x.task == "m3_vatgrown_doll"
        )
        interaction = current(2, 97810)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        assert (
            "PRIVATE_DOLL_SECRET" in interaction.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(reopen())


def test_high_real_object_expectation_departure_return_and_fresh_source_after_old_acts(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, handler=True)
    action = roll(game, worker, gateway, faces=(6, 6))
    choose(game, PLAYER, "vat_doll_benefits", ("leave",), native=True)
    tick(worker, gateway, 5)
    assert controls.view(PLAYER, action)["object"]
    handler = HandlerPlayService(ledger)
    grant = handler.start(
        ADMIN, str(uuid4()), state(game).revision, (current_ref(state(game), 2),)
    )["id"]
    frozen = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="attention"):
        handler.submit(
            ADMIN,
            str(uuid4()),
            grant,
            state(game).revision,
            "expectation",
            Effect(
                kind="expectation",
                account="Actual addressed expectation",
                detail="Guard the door",
                stakes="A real review",
            ),
        )
    assert state(game).model_dump_json() == frozen

    async def move(operation, account):
        from girlframe.discord_adapter.m3_vatgrown import open_vatgrown

        interaction = current(2, int(uuid4().int % 1000000000))
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await open_vatgrown(interaction, controls, action)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = (operation,)
        opened = current(2, int(uuid4().int % 1000000000))
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = account
        response = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    before = state(game)
    asyncio.run(move("leave", "PRIVATE_DOLL_EXIT I leave the room unopposed"))
    left = state(game)
    source = rules.source(left, action)
    assert all(
        x.actor != source.actor
        for x in next(x for x in left.scene_casts if x.id == source.cast.id).roles
    )
    assert left.sheets == before.sheets and left.placements == before.placements
    assert not controls.view(PLAYER, action)["object"]
    asyncio.run(move("return", "PRIVATE_DOLL_RETURN I re-enter the same nearby room"))
    assert controls.view(PLAYER, action)["returned"]
    assert controls.view(OTHER, action)["departure_account"] is None
    assert state(game).placements == before.placements
    cast = CastService(ActorService(MissionService(ledger)))
    data = cast.view(ADMIN, 900)
    cast.change(
        ADMIN,
        str(uuid4()),
        900,
        data["game_revision"],
        data["cast_revision"],
        "withdraw",
        current_ref(state(game), 1),
    )
    # Old acts/departures must never consume effects born from a fresh source.
    fresh = roll(game, worker, gateway, faces=(6, 6))
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",))
    tick(worker, gateway, 5)
    assert controls.view(PLAYER, fresh)["quiet"] and controls.view(PLAYER, fresh)["object"]
    with pytest.raises(WorkflowError, match="attention"):
        target_attempt(game)
    game.dice.faces = (6, 6)
    keep = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I actually evade falling machinery",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert controls.view(PLAYER, fresh)["quiet"]
    tick(worker, gateway, 3)
    assert not controls.view(PLAYER, fresh)["quiet"]
    assert not controls.view(PLAYER, fresh)["object"]
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", text="I dodge the actual falling beam")
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual danger adjudication")
    assert game.inspect(PLAYER, keep)["state"] == "complete"


def test_low_actual_observer_tag_then_owned_question_and_substantive_answer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = roll(game, worker, gateway, faces=(1, 1))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "vat_doll_attention")
    key = str(uuid4())
    args = (
        OTHER,
        key,
        row["id"],
        row["revision"],
        ChoiceAnswer(options=("tag",), text="Quiet little ornament"),
    )
    reply = game.respond(*args)
    assert game.respond(*args) == reply
    tag = next(x for x in state(game).sheets["2"].tags if x.id.startswith("vatgrown-doll-tag:"))
    assert tag.giver_actor == current_ref(state(game), 3)
    choose(
        game,
        PLAYER,
        "vat_doll_benefits",
        ("information",),
        "What did you actually see at the gate?",
        native=True,
    )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(game, OTHER, "vat_doll_information", text="I saw the delivery crew leave", native=True)
    assert controls.view(PLAYER, action)["information"]["answer"] == "I saw the delivery crew leave"
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_actual_observer_punishment_real_effect_then_benefit_and_parent_chat_closure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = roll(game, worker, gateway, faces=(1, 1))
    choose(game, OTHER, "vat_doll_attention", ("punish",), native=True)
    original = state(game)
    case = original.role_punishments[-1]
    assert case.source_kind == "vatgrown_doll" and case.executor == current_ref(original, 3)
    assert case.subject == current_ref(original, 2)
    assert not any(x["kind"] == "vat_doll_benefits" for x in game.choices(PLAYER))
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="stimulant_injection")
    change(
        OTHER, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(OTHER, scene="The actual observer administers her chosen discipline")
    change(PLAYER, attest=True)
    change(OTHER, execute=True, account="I administer the genuine stimulant injection")
    assert state(game).sheets["2"].heat == original.sheets["2"].heat + 7
    actual = next(x for x in state(game).role_punishments if x.id == case.id)
    assert actual.effect_event and actual.completion_event
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choose(game, PLAYER, "vat_doll_benefits", ("quiet",), native=True)
    assert controls.view(PLAYER, action)["quiet"]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
