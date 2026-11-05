"""A real Starry gift persists across actual Director context ending, never a successor body."""

from types import SimpleNamespace
from uuid import uuid4

from test_battle_director import source
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird_state import PERSON, SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService


def test_actual_mid_starry_keeps_exact_tag_capability_after_original_director_dies(
    ledger, monkeypatch
):
    game, _, _, _, director_service, damage_work, director = source(ledger)
    game.dice, game.rng_source = Dice((4, 5)), "test_injected"
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    assert plays.sex_ready()
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, OTHER, "join", director)
    change(cast, OTHER, "adjudicate", director)
    context = ActorRef(kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id)
    change(cast, ADMIN, "join", context)
    actor = current_ref(state(game), 2)
    book = plays.MockingbirdService(game)
    trigger = book.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        SEX,
        (context,),
        "Actual source interaction with this same Handler body",
    )
    book.attest(ADMIN, str(uuid4()), trigger["id"], context, True)
    worker, gateway = GameWorker(game), Gateway()

    def start(play, identity):
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=play,
                source_work=identity,
                context="Actual owned source",
                trigger_confirmed=True,
                heat=0,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return action

    first = start(SEX, trigger["id"])
    answer(
        game,
        PLAYER,
        "mockingbird_sex_select",
        options=("starry",),
        fields={"capability": "deception"},
    )
    assert game.inspect(PLAYER, first)["state"] == "complete"
    tag = next(x for x in state(game).handler_tags if x.label == "Starry-Eyed")
    assert rules.starry_capabilities(state(game), actor, context) == ("deception",)
    tick(worker, gateway, 6)
    director_service.respond(
        OTHER,
        str(uuid4()),
        damage_work,
        director_service.get(OTHER, damage_work)["revision"],
        "death",
        "The actual original Director dies from her source injury",
    )
    handler = active_handler(state(game))
    assert not state(game).director_contexts[-1].active and not state(game).handler_archives
    assert any(x.id == tag.id for x in state(game).handler_tags)
    assert rules.starry_capabilities(state(game), actor, handler) == ("deception",)
    assert all(role.actor != context for scene in state(game).scene_casts for role in scene.roles)
    assert any(role.actor == handler for scene in state(game).scene_casts for role in scene.roles)
    trigger = book.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        PERSON,
        (handler,),
        "Actual later conversation with the same body",
    )
    second = start(PERSON, trigger["id"])
    answer(
        game,
        PLAYER,
        "mockingbird_person_capabilities",
        options=("words", "sentences", "eye_contact"),
    )
    assert "deception" in rules.conversation_capabilities(
        state(game), state(game).mockingbird.conversations[-1]
    )
    assert game.inspect(PLAYER, second)["state"] == "complete" and game.dice.calls == 2
