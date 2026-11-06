"""A paid actual Secretary performs all four Plays and holds an unrolled continuation."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_handler_ordinary import finish_keep, session_native, setup
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_physical_operations import place

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_secretary import open_secretary
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine import m3_secretary as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_world_state import Location
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_items import ItemService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_secretary import SecretaryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    from girlframe.services.m3_handler_pr import HandlerPRService

    game, ordinary, worker, gateway = setup(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE, rules.RULE))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world", "discipline"}}
            )
        }
    )
    with store.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.world = canon.world.model_copy(
            update=dict(
                locations=(
                    Location(id="base0", name="Actual briefing room", cell=(0, 0), kind="base"),
                    Location(id="base1", name="Actual personnel office", cell=(1, 0), kind="base"),
                ),
                npcs=(canon.world.npcs[0].model_copy(update=dict(cell=(1, 0))),),
            )
        )
        game.event(c, 1, "actual-secretary-initial-facts", "synthetic.initial_facts", canon)
    session_native(ordinary, "Actual Secretary advancement Session", 41000)
    pr = HandlerPRService(store)
    event = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual Foundation media fundraiser",
        "Real Foundation photoshoot and public interview",
        (current_ref(state(game), 2),),
    )["id"]
    for viewer, hosting, account in (
        (ADMIN, True, "I actually hosted the Foundation presentation"),
        (PLAYER, False, "I actually posed and spoke in the public Foundation feature"),
    ):
        pr.activity(viewer, str(uuid4()), event, state(game).revision, account, hosting=hosting)
    pr.submit_result(ADMIN, str(uuid4()), event, state(game).revision, "Actual event is performed")
    pr.resolve(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        True,
        "The actual Foundation fundraiser and public feature succeeded",
    )
    return game, SecretaryService(store), worker, gateway


def form(service, identity=None, **values):
    async def run():
        own = current(1, int(uuid4().int % 1000000000))
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_secretary(own, service, identity)
        view = own.edit_original_response.call_args.kwargs["view"]
        view.values.update(values)
        next_step = current(1, int(uuid4().int % 1000000000))
        next_step.channel_id = 900
        await next_step.response.defer(ephemeral=True)
        await view.confirm.callback(next_step)
        assert view.completed, next_step.edit_original_response.call_args
        return next_step

    return asyncio.run(run())


def play(service, identity, operation, **values):
    step = form(service, identity, play=(operation,))

    async def finish():
        view = step.edit_original_response.call_args.kwargs["view"]
        view.values.update(values)
        result = current(1, int(uuid4().int % 1000000000))
        result.channel_id = 900
        await view.confirm.callback(result)
        assert view.completed, result.edit_original_response.call_args

    asyncio.run(finish())


def reply(game, viewer, kind, response, account):
    async def run():
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        own = current(viewer.user_id, int(uuid4().int % 1000000000))
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        view = own.edit_original_response.call_args.kwargs["view"]
        view.values.update(response=(response,), account=account)
        confirmed = current(viewer.user_id, int(uuid4().int % 1000000000))
        await view.confirm.callback(confirmed)
        assert view.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def acquire(service, game, *, create=False):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    revision = state(game).revision
    form(service, award=(award.id,), account="Actual held advancement buys my personal Secretary")
    receipt = rules.acquisitions(state(game))[0]
    assert awards.awards(state(game))[0].phase == "spent"
    with pytest.raises(WorkflowError):
        service.buy(ADMIN, str(uuid4()), award.id, revision, "Cannot spend this same award twice")
    if create:
        form(
            service,
            receipt.id,
            branch=("create",),
            style=("military",),
            name="Actual new Secretary",
            detail="A newly introduced competent Foundation person",
            place=("base1",),
        )
    else:
        form(service, receipt.id, branch=("promote",), style=("competent",), npc=("actual-npc",))
    return rules.secretaries(state(game))[0]


def hostile(game, worker, gateway):
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=current_ref(state(game), 1),
            context="I actually go after the original Handler in this room",
            trigger_confirmed=True,
        ),
    )["action_id"]
    return identity


def hold(service, game, secretary, action, weapon):
    assert any(x["action"] == action for x in service.menu(ADMIN)["opportunities"]), (
        game.inspect(PLAYER, action),
        state(game).held_items,
        state(game).placements,
    )
    play(
        service,
        secretary.id,
        "gunpoint",
        action=(action,),
        weapon=(weapon,),
        firearm=("firearm",),
        account="The actual Secretary raises its carried ordinary gun at the would-be attacker",
    )
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="GUNPOINT"):
        game.roll(PLAYER, str(uuid4()), action)
    assert game.dice.calls == calls


def test_actual_promoted_secretary_all_plays_withdraw_child_continuation_history(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    original_npc = state(game).world.npcs[0]
    secretary = acquire(service, game)
    promoted = state(game).world.npcs[0]
    assert promoted.id == original_npc.id and promoted.controller == original_npc.controller
    assert promoted.jobs == original_npc.jobs and promoted.bonds == original_npc.bonds
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, ADMIN, "join", current_ref(state(game), 1))
    play(
        service,
        secretary.id,
        "appear",
        scene=("900",),
        place=("base0",),
        account="The actual Secretary arrives in the briefing room where it is needed",
    )
    assert state(game).world.npcs[0].cell == (0, 0)
    play(
        service,
        secretary.id,
        "authority",
        scene=("900",),
        target=("2",),
        text="Stand down and listen to the original Handler's actual delegated instruction",
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 5)
    authority = next(x for x in rules.performances(state(game)) if x.play == "authority")
    assert authority.actor == secretary.actor and authority.principal == secretary.handler
    mission = MissionService(ledger).offer(
        ADMIN, str(uuid4()), "Find the actual missing courier through the east Base", (2, 3)
    )["id"]
    play(
        service,
        secretary.id,
        "competence",
        mission=(mission,),
        account="I deliver the actual courier objective and Base route dossier to the offered team",
    )
    dossier = next(x for x in rules.performances(state(game)) if x.play == "competence")
    assert dossier.mission == mission and dossier.mission_json and len(dossier.recipients) == 2
    items = ItemService(game)
    proposal = items.propose(
        ADMIN,
        str(uuid4()),
        secretary.actor,
        "Ordinary carried gun",
        "The actual ordinary firearm this person is carrying",
        weapon=True,
    )["id"]
    weapon = items.confirm(
        ADMIN,
        str(uuid4()),
        proposal,
        items.get(ADMIN, proposal)["revision"],
        exists=True,
        account="Actual original holder and GM confirm the carried gun exists",
    )["id"]
    game.dice = Dice((4, 5))
    before = state(game).sheets["2"]
    first = hostile(game, worker, gateway)
    hold(service, game, secretary, first, weapon)
    tick(worker, gateway, 1)
    reply(
        game,
        PLAYER,
        "secretary_gunpoint",
        "withdraw",
        "I actually back down and stop going after him",
    )
    assert game.inspect(PLAYER, first)["state"] == "complete"
    assert state(game).sheets["2"] == before and game.dice.calls == 0
    tick(worker, gateway, 5)
    second = hostile(game, worker, gateway)
    hold(service, game, secretary, second, weapon)
    tick(worker, gateway, 1)
    reply(
        game,
        PLAYER,
        "secretary_gunpoint",
        "respond",
        "I actually keep my composure under the real gun",
    )
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I actually face down the Secretary's gunpoint before continuing",
            trigger_confirmed=True,
            parent=second,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    finish_keep(game, worker, gateway, child)
    assert game.inspect(PLAYER, second)["state"] == "awaiting_choices"
    with pytest.raises(WorkflowError, match="GUNPOINT"):
        game.roll(PLAYER, str(uuid4()), second)
    reply(
        game,
        ADMIN,
        "secretary_gunpoint_resolution",
        "proceed",
        "The actual completed response gets past gunpoint and permits the original continuation",
    )
    game.roll(PLAYER, str(uuid4()), second)
    pass_tags(game)
    asset = next(x.id for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset, "advance": asset},
        text="I actually advance behind cover after resolving the gunpoint",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, second)["state"] == "complete" and game.dice.calls == 2
    assert {x.phase for x in rules.gunpoints(state(game))} == {"withdrawn", "proceeded"}

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.task == "m3_secretary" and x.identity == dossier.id
        )
        own = current(2, 41200)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(own, item)
        assert "courier" in str(own.edit_original_response.call_args)

    asyncio.run(history())


def test_actual_new_secretary_is_real_npc_not_extra_pc_or_free_assets(
    ledger, tmp_path, monkeypatch
):
    game, service, _, _ = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    secretary = acquire(service, game, create=True)
    after = state(game)
    npc = next(x for x in after.world.npcs if x.id == secretary.actor.entity)
    assert secretary.branch == "created" and npc.controller == 1 and npc.cell == (1, 0)
    assert npc.name == "Actual new Secretary" and npc.alive and npc.employment == "foundation"
    assert after.sheets == before.sheets and after.held_items == before.held_items
    assert len(after.world.npcs) == len(before.world.npcs) + 1
