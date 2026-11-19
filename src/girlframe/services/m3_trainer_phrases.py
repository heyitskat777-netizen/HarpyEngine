"""An original installed phrase alters its exact native order and refusal."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, higher, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import Conditioning
from girlframe.engine.m3_leviathan_obsession import allowed_gain
from girlframe.engine.m3_off_duty import Period
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.trainer.conditioning-phrases"
SPEAK = "trainer_speak_answer"
HEAR = "trainer_speak_heard"


def _installation(
    game: "GameService", c: Connection, state: GameState, target: ActorRef, phrase: str
) -> str | None:
    persona = state.handler_persona
    if persona is None or active_book(game, c, state, book="Trainer", rule=RULE) is None:
        return None
    matches = [x for x in persona.conditioning if x.pilot == target and phrase in x.phrases]
    if len(matches) != 1:
        return None
    history = t.m2["m2_state_history"]
    saved = matches[0]
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == saved.source_event,
        )
    )
    original = GameState.model_validate_json(body).handler_persona if body else None
    if original is None or original.id != persona.id or saved not in original.conditioning:
        return None
    if saved.source_event == persona.source_event:
        return saved.source_event
    periods = t.m3["m3_off_duty_history"]
    source = c.scalar(
        sa.select(periods.c.body_json)
        .join(t.events, t.events.c.id == periods.c.event_id)
        .where(
            periods.c.campaign_id == game.store.campaign_id,
            periods.c.event_id == saved.source_event,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.off_duty_scene_attested",
        )
    )
    period = Period.model_validate_json(source) if source else None
    if (
        period is None
        or period.handler_scene is None
        or period.handler != persona.owner
        or period.handler_scene.kind != "trainer_conditioning"
        or period.handler_scene.conditioning_phrase != phrase
        or period.handler_scene.character_ids.get(target.entity) != target.incarnation
        or not (
            set(period.handler_scene.participants)
            == set(period.handler_scene.acknowledgements)
            == {period.handler, int(target.entity)}
        )
    ):
        return None
    return saved.source_event


def training_target(
    game: "GameService",
    c: Connection,
    state: GameState,
    period: Period,
    participants: tuple[int, ...],
    phrase: str | None,
) -> ActorRef:
    owned = active_book(game, c, state, book="Trainer", rule=RULE)
    if (
        owned is None
        or owned[0].entity != str(period.handler)
        or phrase != "speak"
        or len(participants) != 2
        or period.handler not in participants
    ):
        raise WorkflowError("The original Trainer and one original Girl own this Speak scene")
    target = current_ref(state, next(x for x in participants if x != period.handler))
    persona = state.handler_persona
    assert persona is not None
    if target.kind != "pilot" or target.incarnation != period.character_ids.get(target.entity):
        raise WorkflowError("Use the actual original Girl from this Off-Duty period")
    if any(x.pilot == target and phrase in x.phrases for x in persona.conditioning):
        raise WorkflowError("This actual Girl already has Speak installed")
    return target


def complete_training(
    game: "GameService", c: Connection, state: GameState, period: Period, event: str
) -> None:
    scene = period.handler_scene
    if scene is None or set(scene.participants) != set(scene.acknowledgements):
        raise WorkflowError("Both original participants must attest to the training scene")
    target = training_target(game, c, state, period, scene.participants, scene.conditioning_phrase)
    persona = state.handler_persona
    assert persona is not None and scene.conditioning_phrase is not None
    installed = Conditioning(pilot=target, phrases=(scene.conditioning_phrase,), source_event=event)
    state.handler_persona = persona.model_copy(
        update=dict(conditioning=(*persona.conditioning, installed))
    )


def stage(
    game: "GameService",
    c: Connection,
    state: GameState,
    issuer: int,
    target: int,
    phrase: str,
    order: str,
    event: str,
) -> dict[str, Any]:
    girl = current_ref(state, target)
    installation = _installation(game, c, state, girl, phrase)
    if phrase != "speak" or installation is None or not higher(state, issuer, target):
        raise WorkflowError("Use an installed Speak phrase and its actual higher-Status issuer")
    return dict(
        phrase=phrase,
        order=order,
        event=event,
        installation=installation,
        target=girl.model_dump(mode="json"),
        issuer=current_ref(state, issuer).model_dump(mode="json"),
    )


def _original(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    data = action["data"]
    root = action
    if data.get("play") == "disobey_orders":
        if not action["parent_id"] or not data.get("prepared", {}).get("order_id"):
            return None
        root = game.action(c, action["parent_id"])
    saved = root["data"].get("conditioning_phrase")
    if saved is None:
        return None
    table = t.m2["m2_orders"]
    order = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == saved["order"],
            table.c.channel_id == action["channel_id"],
            table.c.target_id == saved["target"]["entity"],
            table.c.issuer_id == saved["issuer"]["entity"],
        )
    )
    event = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == saved["event"],
            t.events.c.kind == "m2.order_issued",
        )
    ).first()
    girl = ActorRef.model_validate(saved["target"])
    speaker = ActorRef.model_validate(saved["issuer"])
    people = (int(girl.entity), int(speaker.entity))
    scene = game.scene(c, action["channel_id"])
    campaign = HandlerService(game.store)
    if (
        root["data"]["order_id"] != saved["order"]
        or order is None
        or json.loads(order).get("conditioning_phrase") != saved
        or event is None
        or event.actor_id != speaker.entity
        or json.loads(event.payload_json).get("action_id") != root["id"]
        or root["actor_id"] != girl.entity
        or action["actor_id"] != girl.entity
        or scene["id"] != root["scene_id"]
        or not set(people) <= set(scene["participants"])
        or not all(campaign._member(c, owner) for owner in people)
        or current_ref(state, people[0]) != girl
        or current_ref(state, people[1]) != speaker
        or _installation(game, c, state, girl, saved["phrase"]) != saved["installation"]
    ):
        raise WorkflowError("Recover the original installed phrase, order, issuer and Girl")
    game.pilot_cast(c, state, scene, owners=people)
    return root, saved


def high_refusal(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    original = _original(game, c, state, action)
    if original is None:
        return False
    _, saved = original
    actor = ActorRef.model_validate(saved["target"])
    sheet = state.sheets[actor.entity]
    heat = allowed_gain(state, actor, 2, RULE, action["data"]["response_event"])
    sheet.heat += heat
    sheet.revision += 1
    shift_status(state, sheet.owner, 1)
    action["data"]["result"].update(can_disobey=False, conditioning=True, conditioning_heat=heat)
    return True


def offer_speak(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    original = _original(game, c, state, action)
    if original is None:
        return False
    _, saved = original
    game.request(
        c,
        action,
        int(saved["target"]["entity"]),
        SPEAK,
        dict(source=saved),
    )
    return True


def choose(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    original = _original(game, c, state, action)
    body = json.loads(request["body_json"])
    if original is None or original[1] != body["source"]:
        raise WorkflowError("Recover the actual source of this private Speak response")
    _, saved = original
    if (
        answer.options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only the original Speak response fields")
    if request["kind"] == SPEAK:
        if not answer.text.strip() or answer.flag is not None:
            raise WorkflowError("Only the Girl chooses what answer she actually gives")
        reply = dict(source=saved, answer=answer.text.strip())
        action["data"]["trainer_spoken"] = reply
        game.request(c, action, int(saved["issuer"]["entity"]), HEAR, dict(source=saved))
        return
    spoken = action["data"].get("trainer_spoken", {})
    if (
        request["kind"] != HEAR
        or answer.text.strip()
        or answer.flag is not True
        or spoken.get("source") != saved
    ):
        raise WorkflowError("Only the original issuer confirms hearing the exact actual answer")
    action["data"]["trainer_heard_event"] = action["data"]["response_event"]


def display(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> str:
    original = _original(game, c, state, action)
    if original is None or original[1] != json.loads(request["body_json"])["source"]:
        raise WorkflowError("Recover this original private Conditioning Phrase")
    root, saved = original
    if request["kind"] == SPEAK:
        return str(root["data"]["order_text"])
    spoken = action["data"].get("trainer_spoken", {})
    if spoken.get("source") != saved:
        raise WorkflowError("Only the original recipient can recover this actual answer")
    return str(spoken["answer"])
