"""Real rolled conversation, printed tier counts and actual interlocutor Tag ownership."""

from types import SimpleNamespace

import pytest
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird_state import PERSON
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.onboarding import WorkflowError


def rolled(store, monkeypatch, faces):
    # Only this focused book unit's source lookup is synthetically reviewed.
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    game, worker, gateway = ready(store, faces)
    source = plays.MockingbirdService(game)
    actor = ActorRef(kind="pilot", entity="2", incarnation=state(game).sheets["2"].character_id)
    other = ActorRef(kind="pilot", entity="3", incarnation=state(game).sheets["3"].character_id)
    trigger = source.propose(
        PLAYER, "actual-person-trigger", 900, actor, PERSON, (other,), "Actual attempt to converse"
    )
    identity = game.begin(
        PLAYER,
        "actual-person",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=PERSON,
            source_work=trigger["id"],
            context="Actual conversation",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, identity, source, actor, other


@pytest.mark.parametrize(
    "faces,choices,tag",
    [
        ((4, 5), ("words", "sentences", "eye_contact"), False),
        ((6, 6), ("words", "sentences", "eye_contact", "deception"), True),
        ((1, 2), (), True),
    ],
)
def test_actual_all_tiers_capabilities_source_owned_tag_and_durable_low_permission(
    ledger, monkeypatch, faces, choices, tag
):
    game, worker, gateway, identity, source, actor, other = rolled(ledger, monkeypatch, faces)
    before = game.inspect(PLAYER, identity)["receipt"]
    with pytest.raises(WorkflowError):
        answer(
            game,
            PLAYER,
            "mockingbird_person_capabilities",
            options=(
                "words",
                "sentences",
                "eye_contact",
                "deception",
                "expressions",
                "body_language",
            ),
        )
    answer(game, PLAYER, "mockingbird_person_capabilities", options=choices)
    if tag:
        row = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_person_tag")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                "wrong-author",
                row["id"],
                row["revision"],
                ChoiceAnswer(text="Cannot author their Tag"),
            )
        answer(game, OTHER, "mockingbird_person_tag", text="Actual frozen expression")
        applied = state(game).sheets["2"].tags[-1]
        assert applied.giver_actor == other and applied.giver == 3
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["receipt"] == before and game.dice.calls == 1
    conversation = state(game).mockingbird.conversations[-1]
    assert conversation.allowed == tuple(
        x
        for x in ("words", "sentences", "body_language", "expressions", "eye_contact", "deception")
        if x in choices
    )
    if faces == (1, 2):
        with pytest.raises(ValueError, match="allow"):
            rules.require_departure(state(game), actor)
        with pytest.raises(WorkflowError):
            source.release(ADMIN, "wrong-release", conversation.id, other, True)
        source.release(OTHER, "owned-release", conversation.id, other, True)
        rules.require_departure(state(game), actor)
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_native_low_capability_and_actual_interlocutor_tag_and_permission(ledger, monkeypatch):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.discord_adapter.m3_mockingbird_plays import open_request

    game, _, _, identity, source, actor, other = rolled(ledger, monkeypatch, (1, 2))
    capability = next(
        x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_person_capabilities"
    )

    async def run():
        owner = current(2, 880101)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, capability["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 880102))
        await form.confirm.callback(current(2, 880103))
        assert form.completed
        target = current(3, 880104)
        await target.response.defer(ephemeral=True)
        row = next(x for x in game.choices(OTHER) if x["kind"] == "mockingbird_person_tag")
        await open_choice(target, game, row["id"])
        tagform = target.edit_original_response.call_args.kwargs["view"]
        tagform.values["tag"] = "Actual unnerving gaze"
        await tagform.confirm.callback(current(3, 880105))
        assert tagform.completed
        conversation = state(game).mockingbird.conversations[-1]
        await open_request(target, source, conversation.id)
        permission = target.edit_original_response.call_args.kwargs["view"]
        permission.values.update(party=("0",), allow=("yes",))
        await permission.confirm.callback(current(3, 880106))
        assert permission.completed

    asyncio.run(run())
    rules.require_departure(state(game), actor)
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_actual_low_conversation_requires_owned_permission_then_native_end_before_new_roll(
    ledger, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_mockingbird_plays import open_request

    game, _, _, _, source, actor, other = rolled(ledger, monkeypatch, (1, 2))
    answer(game, PLAYER, "mockingbird_person_capabilities", options=())
    answer(game, OTHER, "mockingbird_person_tag", text="Actual ongoing expression")
    value = state(game).mockingbird.conversations[-1]
    with pytest.raises(WorkflowError, match="ongoing conversation"):
        source.propose(
            PLAYER, "cannot-reroll", 900, actor, PERSON, (other,), "Still this conversation"
        )
    with pytest.raises(ValueError, match="allow"):
        source.end(PLAYER, "cannot-leave", value.id, actor)
    source.release(OTHER, "actual-end-permission", value.id, other, True)

    async def finish():
        owner = current(2, 880201)
        await owner.response.defer(ephemeral=True)
        await open_request(owner, source, value.id)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 880202))
        form.values["end"] = ("yes",)
        await form.confirm.callback(current(2, 880203))
        assert form.completed

    asyncio.run(finish())
    assert state(game).mockingbird.conversations[-1].ended_event
    source.propose(
        PLAYER, "genuine-next-conversation", 900, actor, PERSON, (other,), "A new conversation"
    )
    assert game.dice.calls == 1
