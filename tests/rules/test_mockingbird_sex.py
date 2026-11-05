"""Genuine owned trigger and shared rolled source reach actual original body consequences."""

from types import SimpleNamespace

from test_beneath_service import ready
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird_state import PERSON, SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService


def high_handler(store, monkeypatch):
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    monkeypatch.setattr(plays, "sex_ready", lambda: True)
    game, worker, gateway = ready(store, (6, 6))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    handler = active_handler(state(game))
    cast = CastService(ActorService(MissionService(store)))
    change(cast, ADMIN, "join", handler)
    from girlframe.engine.m3_actor_state import ActorRef

    actor = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    source = plays.MockingbirdService(game)
    trigger = source.propose(
        PLAYER,
        "actual-sex-handler-trigger",
        900,
        actor,
        SEX,
        (handler,),
        "Actual player-authored interaction already occurred",
    )
    source.attest(ADMIN, "actual-handler-counterpart-facts", trigger["id"], handler, True)
    identity = game.begin(
        PLAYER,
        "actual-sex-high-handler",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual owned printed interaction",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "mockingbird_sex_high_commit", flag=True)
    return game, worker, gateway, identity, state(game).handler_void[-1].work


def test_actual_high_handler_void_has_held_original_source_and_three_real_choices(
    ledger, monkeypatch
):
    from girlframe.services.m3_handler_void import HandlerVoidService

    game, _, _, identity, work = high_handler(ledger, monkeypatch)
    service = HandlerVoidService(ledger, game)
    view = service.get(ADMIN, work)
    assert view
    assert game.inspect(PLAYER, identity)["state"] != "complete" and game.dice.calls == 1


def test_real_mid_starry_tag_grants_actual_later_person_capability_only_while_tag_exists(
    ledger, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.engine import m3_mockingbird as rules
    from girlframe.engine.m2 import GameState

    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    monkeypatch.setattr(plays, "sex_ready", lambda: True)
    game, worker, gateway = ready(ledger, (4, 5))
    source = plays.MockingbirdService(game)
    actor = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    other = ActorRef(kind="pilot", entity="3", incarnation=state(game).sheets["3"].character_id)
    trigger = source.propose(
        PLAYER, "actual-starry-trigger", 900, actor, SEX, (other,), "Actual source interaction"
    )
    source.attest(OTHER, "actual-starry-counterpart", trigger["id"], other, True)

    def start(play, trigger_id, key):
        action = game.begin(
            PLAYER,
            key,
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=play,
                source_work=trigger_id,
                context="Actual source interaction",
                trigger_confirmed=True,
                heat=0,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return action

    action = start(SEX, trigger["id"], "actual-starry-roll")

    async def choose():
        interaction = current(2, 880301)
        await interaction.response.defer(ephemeral=True)
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_sex_select")
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 880302))
        form.values.update(option=("starry",), capability=("deception",))
        await form.confirm.callback(current(2, 880303))
        assert form.completed

    asyncio.run(choose())
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tag = next(x for x in state(game).sheets["3"].tags if x.label == "Starry-Eyed")
    assert tag.giver_actor == actor and tag.giver == 2
    assert rules.starry_capabilities(state(game), actor, other) == ("deception",)
    tick(worker, gateway, 5)
    next_trigger = source.propose(
        PLAYER, "actual-later-person", 900, actor, PERSON, (other,), "Later actual conversation"
    )
    later = start(PERSON, next_trigger["id"], "actual-later-person-roll")
    answer(
        game,
        PLAYER,
        "mockingbird_person_capabilities",
        options=("words", "sentences", "eye_contact"),
    )
    assert "deception" in state(game).mockingbird.conversations[-1].allowed
    assert game.inspect(PLAYER, later)["state"] == "complete" and game.dice.calls == 2
    marked = GameState.model_validate_json(state(game).model_dump_json())
    marked.sheets["3"].tags = [
        x.model_copy(update={"marked": True}) if x.id == tag.id else x
        for x in marked.sheets["3"].tags
    ]
    assert rules.starry_capabilities(marked, actor, other) == ("deception",)
    marked.sheets["3"].tags = [x for x in marked.sheets["3"].tags if x.id != tag.id]
    assert rules.starry_capabilities(marked, actor, other) == ()
    assert "deception" not in rules.conversation_capabilities(
        marked, marked.mockingbird.conversations[-1]
    )
    assert "deception" in rules.conversation_capabilities(
        state(game), state(game).mockingbird.conversations[-1]
    )
