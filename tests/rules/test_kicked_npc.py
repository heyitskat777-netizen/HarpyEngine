"""Paid Kicked Puppy follows an actual NPC giver, damage basis and care answer."""

from uuid import uuid4

from test_ankou import ready
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_npc_flirt import finish_roll, native_choice

from girlframe.engine import m3_kicked_puppy as rules
from girlframe.engine import m3_npc_flirt as npc_rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_kicked_puppy import KickedPuppyService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService


def test_actual_npc_gift_and_damage_feed_kicked_care_flirt(ledger, tmp_path, monkeypatch):
    # Prior world, cockpit and resources are explicit synthetic setup in ready.
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.RULE,
            npc_rules.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
            "npc.npc.public-relations",
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
    game.dice = Dice((1, 2))
    damage = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=1,
            piloting=True,
            target_actor=current_ref(state(game), 3),
            context="Actual cover damages my Girl hardware",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover",),
        fields={"cover": asset.id},
        denied=(asset.id,),
        text="Actual maneuver cost",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, damage)["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).damaged
    source = KickedPuppyService(game)
    menu = source.menu(PLAYER)
    source.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        current_ref(state(game), 2),
        menu["frame"],
        "Actual paid Kicked Puppy",
    )
    mission = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-kicked-counterpart")
    WorldService(mission).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("public_relations",),
            controller=1,
            detail="PRIVATE_ACTUAL_NPC",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(mission)), ADMIN, "join", npc)
    game.dice = Dice((6, 6))
    gift = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target_actor=npc,
            heat=0,
            context="Actual ordinary NPC Flirt after buying Kicked Puppy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish_roll(game, worker, gateway, gift)
    answer(
        game,
        PLAYER,
        "npc_flirt_actor",
        options=("name",),
        fields={"extra": "owe"},
        text="I go too far and owe this actual person",
    )
    answer(game, ADMIN, "npc_flirt_target", text="My original name", flag=True)
    answer(game, ADMIN, "npc_flirt_owe", text="Actual NPC gift")
    assert game.inspect(PLAYER, gift)["state"] == "complete"
    tick(worker, gateway, 5)
    tag = next(x for x in state(game).sheets["2"].tags if x.label == "Actual NPC gift")
    assert tag.giver_actor == npc
    before = state(game)
    game.dice = Dice((3, 3))
    care = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="flirt",
            target_actor=npc,
            heat=0,
            kicked_puppy_basis=True,
            context="I ask my actual gift giver for care",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(tag.id,),
        number=1,
        text="Their actual gift describes my appeal for care",
    )
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(
            row["kind"] == "tag_window" and row["action_id"] == care for row in game.choices(viewer)
        ):
            answer(game, viewer, "tag_window", options=("pass",))
    native_choice(game, PLAYER, "npc_flirt_actor", question=(rules.QUESTION,), unmark=())
    answer(game, ADMIN, "npc_flirt_target", text="I offer actual care and rest", flag=True)
    final = game.inspect(PLAYER, care)
    assert final["state"] == "complete"
    assert final["receipt"]["heat"] == 0 and final["receipt"]["base_modifier"] == 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 1
    assert final["result"]["question"] == rules.QUESTION
    assert final["result"]["target_answer"] == "I offer actual care and rest"
    assert next(x for x in state(game).sheets["2"].tags if x.id == tag.id).marked
