"""Normal Brutalize outcomes use actual originals, resources and counter Plays."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_alpha import RULE, conditions


def ready(store, tmp_path, monkeypatch, faces):
    _, game = service(store, girl="ALPHA", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(RULE,))
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(canon, 2, mode="outside_frame")
        canon = place(canon, 3, mode="outside_frame")
        canon.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.actual_alpha_prior_context", canon)
    game.dice.faces = faces
    return game, GameWorker(game), Gateway()


def rolled(store, tmp_path, monkeypatch, faces):
    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    canon = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=current_ref(canon, 3),
            heat=0,
            context="Actual Alpha tears into the other Girl with words, fists and teeth",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    return game, worker, gateway, action


def test_mid_damage_broken_relative_status_and_real_mid_disobey_removal(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, action = rolled(ledger, tmp_path, monkeypatch, (4, 5))
    original = state(game)
    asset = next(x for x in original.sheets["3"].assets if x.family == "girl" and not x.damaged)
    assert not higher(original, 2, 3)
    answer(game, PLAYER, "alpha_damage", options=(asset.id,))
    actual = state(game)
    assert next(x for x in actual.sheets["3"].assets if x.id == asset.id).damaged
    assert conditions(actual, current_ref(actual, 3), current_ref(actual, 2))
    assert higher(actual, 2, 3) and not higher(actual, 3, 2)
    assert game.sheet(OTHER)["broken_against"] == [current_ref(actual, 2).model_dump(mode="json")]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    order = game.issue_order(PLAYER, str(uuid4()), 900, 3, "Actual direct order from the inflictor")
    tick(worker, gateway, 2)
    answer(game, OTHER, "order_response", options=("disobey",))
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            parent=order["action_id"],
            order_id=order["order_id"],
            heat=0,
            context="Actual refusal against this same original inflictor",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", options=("remove_broken",))
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert not conditions(state(game), current_ref(state(game), 3), current_ref(state(game), 2))
    assert not higher(state(game), 2, 3) and game.dice.calls == 2


def test_high_native_damage_applies_actual_helplessness_without_broken(
    ledger, tmp_path, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_alpha import open_alpha_choice

    game, _, _, action = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_damage")
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)

    async def run():
        interaction = current(2, 98201)
        await interaction.response.defer(ephemeral=True)
        await open_alpha_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values["asset"] = (asset.id,)
        await form.confirm.callback(current(2, 98202))
        assert form.completed

    asyncio.run(run())
    canon = state(game)
    assert is_helpless(canon, current_ref(canon, 3), current_ref(canon, 2))
    assert not conditions(canon, current_ref(canon, 3), current_ref(canon, 2))
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_waits_real_owned_counter_before_conditional_broken(ledger, tmp_path, monkeypatch):
    game, worker, gateway, action = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    before = state(game)
    assert not conditions(before, current_ref(before, 2), current_ref(before, 3))
    assert game.inspect(PLAYER, action)["state"] != "complete"
    game.dice.faces = (2, 3)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        before.sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            parent=action,
            heat=0,
            context="I actually keep composed against the Alpha's pressure",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", options=("sexy",))
    assert game.inspect(PLAYER, action)["state"] != "complete"
    answer(
        game, ADMIN, "handler_keep", flag=True, text="Actual adjudication of this counter response"
    )
    actual = state(game)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert conditions(actual, current_ref(actual, 2), current_ref(actual, 3))
    assert game.dice.calls == 2


def guard_rolled(store, tmp_path, monkeypatch, faces):
    from test_enforcement_initiative import cast_target

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_npc_guard import GuardService
    from girlframe.services.m3_world import WorldService

    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    approved(store, game, tmp_path, monkeypatch, extra=(RULE, "npc.npc.guard"))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(store))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-alpha-guard",
            name="Actual Guard",
            jobs=("guard",),
            detail="Actual on-scene ordinary Guard",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    npc = ActorRef(kind="npc", entity="actual-alpha-guard")
    cast_target(game, npc)
    guard = GuardService(game)
    guard.assess(
        ADMIN,
        str(uuid4()),
        900,
        npc,
        current_ref(state(game), 2),
        state(game).revision,
        True,
        "The actual Guard has no weapon on their body",
    )
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=npc,
            heat=0,
            context="Actual Alpha tears into this co-present Guard",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, guard, npc, action, worker, gateway


def test_guard_low_actual_weapon_review_native_counter_then_optional_unarmed_kill(
    ledger, tmp_path, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_alpha import open_alpha_choice

    game, guard, npc, action, _, _ = guard_rolled(ledger, tmp_path, monkeypatch, (1, 1))
    answer(game, ADMIN, "alpha_low", options=("counter_broken",))
    assert not conditions(state(game), current_ref(state(game), 2), npc)
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_counter_play")

    async def native():
        opening = current(1, 9060)
        await opening.response.defer(ephemeral=True)
        await open_alpha_choice(opening, game, choice["id"])
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(move=("interpose",), account="I step into the actual Alpha's way")
        await form.confirm.callback(current(1, 9061))

    asyncio.run(native())
    assert conditions(state(game), current_ref(state(game), 2), npc)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert next(x for x in state(game).world.npcs if x.id == npc.entity).alive
    answer(game, PLAYER, "alpha_npc_mercy", options=("kill",))
    assert not next(x for x in state(game).world.npcs if x.id == npc.entity).alive
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


@pytest.mark.parametrize("faces,option", [((4, 5), "injure"), ((6, 6), "kill")])
def test_guard_printed_mid_injury_and_high_death(ledger, tmp_path, monkeypatch, faces, option):
    game, _, npc, action, _, _ = guard_rolled(ledger, tmp_path, monkeypatch, faces)
    answer(
        game,
        PLAYER,
        "alpha_npc_damage",
        options=(option,),
        text="Actual torn shoulder" if option == "injure" else "",
    )
    actual = state(game)
    person = next(x for x in actual.world.npcs if x.id == npc.entity)
    assert person.alive == (option == "injure")
    if option == "injure":
        assert person.tags[-1].label == "Actual torn shoulder"
        assert conditions(actual, npc, current_ref(actual, 2))
    else:
        assert not any(x.actor == npc for cast in actual.scene_casts for x in cast.roles)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
