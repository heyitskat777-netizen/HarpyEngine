"""An original installed phrase alters its exact native order and refusal."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, higher, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_state import Conditioning
from girlframe.engine.m3_leviathan_obsession import allowed_gain
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_trainer_phrases import (
    PHRASE_LABELS,
    TARGETED,
    Heel,
    Protection,
    Seated,
    pending_heel,
    protections,
    save_heel,
    save_protection,
    save_sitting,
    sitting,
)
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.trainer.conditioning-phrases"
SPEAK = "trainer_speak_answer"
HEAR = "trainer_speak_heard"
SIT = "trainer_sit"
HEEL = "trainer_heel_response"
FLIRT = "trainer_flirt_play"
HUNT = "trainer_hunt_play"
PROTECT = "trainer_protect_response"
ROUGH_OFFER = "trainer_rough_offer"
ROUGH_REPLY = "trainer_rough_reply"
ROUGH_HEARD = "trainer_rough_heard"
ROUGH_CHOICES = (ROUGH_OFFER, ROUGH_REPLY, ROUGH_HEARD)
RESPONSE_CHOICES = (SPEAK, HEAR, SIT, HEEL, PROTECT, *ROUGH_CHOICES)


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
    snapshot = GameState.model_validate_json(body) if body else None
    original = snapshot.handler_persona if snapshot else None
    if original is None or original.id != persona.id or saved not in original.conditioning:
        return None
    if saved.source_event == persona.source_event:
        return saved.source_event
    if snapshot is not None:
        work = _punishment_installation(
            game, c, snapshot, original.owner, target, phrase, saved.source_event
        )
        if work is not None:
            return saved.source_event
        from girlframe.engine.m3_handler_private_scene import records as private_scenes
        from girlframe.services.m3_handler_private_scene import TRAINER_EVENT

        record = next(
            (
                x
                for x in private_scenes(snapshot)
                if x.event == saved.source_event
                and x.playbook == "Trainer"
                and x.phase == "complete"
                and x.outcome == ("speak_installed" if phrase == "speak" else "phrase_installed")
            ),
            None,
        )
        if record is not None:
            return (
                saved.source_event
                if (
                    record.girl == target
                    and record.handler.entity == str(original.owner)
                    and record.handler.incarnation == original.id
                    and set(record.attestations) == {record.handler, target}
                    and c.scalar(
                        sa.select(t.events.c.id).where(
                            t.events.c.campaign_id == game.store.campaign_id,
                            t.events.c.id == saved.source_event,
                            t.events.c.kind == TRAINER_EVENT,
                            t.events.c.actor_id == str(original.owner),
                            sa.func.json_extract(t.events.c.payload_json, "$.step")
                            == f"install_{phrase}",
                        )
                    )
                )
                else None
            )
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


def _punishment_installation(
    game: "GameService",
    c: Connection,
    snapshot: GameState,
    handler: int,
    target: ActorRef,
    phrase: str,
    event: str,
) -> str | None:
    fact = next(
        (
            x
            for x in snapshot.facts
            if x.get("kind") == "trainer_punishment_install"
            and x.get("event") == event
            and x.get("phrase") == phrase
            and x.get("target") == target.token
        ),
        None,
    )
    if fact is None:
        return None
    work = t.m3["m3_required_work"]
    return c.scalar(
        sa.select(work.c.id)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == work.c.campaign_id,
                t.events.c.id == work.c.event_id,
            ),
        )
        .where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id == fact["work"],
            work.c.event_id == event,
            work.c.kind == "punishment",
            work.c.state == "resolved",
            work.c.subject_id == target.entity,
            t.events.c.kind == "m3.punishment_applied",
            t.events.c.actor_id == str(handler),
            sa.func.json_extract(work.c.body_json, "$.applied_event") == event,
            sa.func.json_extract(work.c.body_json, "$.character") == target.incarnation,
        )
    )


def punishment_training(
    game: "GameService",
    c: Connection,
    state: GameState,
    viewer: int,
    row: dict[str, Any],
) -> tuple[ActorRef, str, tuple[tuple[str, str], ...]] | None:
    persona = state.handler_persona
    subject = int(row["subject_id"])
    if (
        persona is None
        or viewer != state.handler
        or row["owner_id"] != str(viewer)
        or str(subject) not in state.sheets
        or active_book(game, c, state, book="Trainer", rule=RULE) is None
    ):
        return None
    target = current_ref(state, subject)
    scenes = t.m2["m2_scenes"]
    scope = sa.select(scenes.c.channel_id).where(
        scenes.c.campaign_id == game.store.campaign_id,
        scenes.c.open.is_(True),
    )
    if row["scene_id"]:
        scope = scope.where(scenes.c.id == row["scene_id"])
    shared = []
    for channel in c.scalars(scope):
        scene = game.scene(c, channel)
        if not {viewer, subject} <= set(scene["participants"]):
            continue
        try:
            game.pilot_cast(c, state, scene, owners=(viewer, subject))
        except WorkflowError:
            continue
        shared.append(scene["id"])
    if len(shared) != 1:
        return None
    installed = {
        phrase
        for entry in persona.conditioning
        if entry.pilot == target
        for phrase in entry.phrases
    }
    return (
        target,
        shared[0],
        tuple(
            (phrase, label) for phrase, label in PHRASE_LABELS.items() if phrase not in installed
        ),
    )


def install_during_punishment(
    game: "GameService",
    c: Connection,
    state: GameState,
    viewer: int,
    row: dict[str, Any],
    phrase: str,
    event: str,
) -> None:
    course = punishment_training(game, c, state, viewer, row)
    if course is None or phrase not in dict(course[2]):
        raise WorkflowError(
            "Choose an uninstalled phrase for the original Girl in this Trainer's Punishment"
        )
    target, scene, _ = course
    persona = state.handler_persona
    assert persona is not None
    installment = Conditioning(pilot=target, phrases=(phrase,), source_event=event)
    state.handler_persona = persona.model_copy(
        update=dict(conditioning=(*persona.conditioning, installment))
    )
    state.facts.append(
        dict(
            kind="trainer_punishment_install",
            event=event,
            work=row["id"],
            target=target.token,
            scene=scene,
            phrase=phrase,
        )
    )


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
        or phrase not in PHRASE_LABELS
        or len(participants) != 2
        or period.handler not in participants
    ):
        raise WorkflowError("The original Trainer and one original Girl own this phrase scene")
    target = current_ref(state, next(x for x in participants if x != period.handler))
    persona = state.handler_persona
    assert persona is not None
    if target.kind != "pilot" or target.incarnation != period.character_ids.get(target.entity):
        raise WorkflowError("Use the actual original Girl from this Off-Duty period")
    if any(x.pilot == target and phrase in x.phrases for x in persona.conditioning):
        raise WorkflowError("This actual Girl already has the chosen phrase installed")
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
    *,
    scene: dict[str, Any],
    counterpart: int | None = None,
    actor_token: str | None = None,
) -> dict[str, Any]:
    girl = current_ref(state, target)
    installation = _installation(game, c, state, girl, phrase)
    if phrase not in PHRASE_LABELS or installation is None or not higher(state, issuer, target):
        label = PHRASE_LABELS.get(phrase, "Conditioning")
        raise WorkflowError(f"Use an installed {label} phrase and its actual higher-Status issuer")
    if phrase == "sit":
        _seat_body(state, girl)
    if phrase == "heel":
        _heel_bodies(game, c, state, girl, current_ref(state, issuer))
    if (counterpart is not None) != (phrase in TARGETED):
        raise WorkflowError("Choose a nominated Girl only for a phrase that names a counterpart")
    nominated = None
    if counterpart is not None:
        if (
            counterpart == target
            or counterpart not in scene["participants"]
            or str(counterpart) not in state.sheets
            or counterpart not in state.order
        ):
            raise WorkflowError("Choose another original Girl currently in this actual scene")
        game.pilot_cast(c, state, scene, owners=(issuer, target, counterpart))
        nominated = current_ref(state, counterpart).model_dump(mode="json")
    if (actor_token is not None) != (phrase in ("hunt", "protect")):
        raise WorkflowError("Choose an actual target for Hunt or Protect")
    if actor_token is not None and phrase == "hunt":
        nominated = _hunt_target(game, c, state, scene, girl, issuer, actor_token).model_dump(
            mode="json"
        )
    if actor_token is not None and phrase == "protect":
        other = _protected_target(game, c, state, scene, girl, issuer, actor_token)
        if other is None:
            raise WorkflowError("Protect a known person or Girl at the original Girl's side")
        nominated = other.model_dump(mode="json")
    return dict(
        phrase=phrase,
        order=order,
        event=event,
        installation=installation,
        target=girl.model_dump(mode="json"),
        issuer=current_ref(state, issuer).model_dump(mode="json"),
    ) | ({"counterpart": nominated} if nominated is not None else {})


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


def offer_phrase(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    original = _original(game, c, state, action)
    if original is None:
        return False
    _, saved = original
    if saved["phrase"] == "hunt":
        game.request(
            c,
            action,
            int(saved["target"]["entity"]),
            HUNT,
            dict(source=saved, actor=saved["target"], target=saved["counterpart"]),
        )
        return True
    if saved["phrase"] in TARGETED:
        target = int(saved["counterpart"]["entity"])
        game.request(
            c,
            action,
            int(saved["target"]["entity"]),
            FLIRT if saved["phrase"] == "play_gentle" else ROUGH_OFFER,
            dict(source=saved, target=target),
        )
        return True
    game.request(
        c,
        action,
        int(saved["target"]["entity"]),
        {"sit": SIT, "heel": HEEL, "protect": PROTECT}.get(saved["phrase"], SPEAK),
        dict(source=saved),
    )
    return True


def _hunt_target(
    game: "GameService",
    c: Connection,
    state: GameState,
    scene: dict[str, Any],
    girl: ActorRef,
    issuer: int,
    token: str,
) -> ActorRef:
    from girlframe.engine.m3_battle import intact_assets
    from girlframe.services.m3_battle import _cast, _visible

    cast = _cast(game, c, state, int(scene["channel_id"]))
    bound = profiles(c, game.store.campaign_id)
    for role in cast.roles:
        other = role.actor
        if (
            other.token == token
            and other.kind in ("pilot", "gorgon", "external_pilot")
            and role.controller != int(girl.entity)
            and all(_visible(state, other, human) for human in (issuer, int(girl.entity)))
        ):
            view = resolve(state, other, bound, require_current_profile=False)
            if (
                view.controller == role.controller
                and not view.offstage_source
                and any(not x.concealed for x in intact_assets(state, other, bound))
            ):
                return other
    raise WorkflowError("Choose an actual visible opposing body with an intact Asset for Hunt")


def _protected_target(
    game: "GameService",
    c: Connection,
    state: GameState,
    scene: dict[str, Any],
    girl: ActorRef,
    issuer: int,
    token: str,
) -> ActorRef | None:
    from girlframe.services.m3_battle import _cast, _visible

    cast = _cast(game, c, state, int(scene["channel_id"]))
    for role in cast.roles:
        other = role.actor
        if (
            other != girl
            and other.token == token
            and other.kind in ("pilot", "npc", "handler", "external_pilot")
            and all(_visible(state, other, human) for human in (issuer, int(girl.entity)))
        ):
            pair = protected_pair(game, c, state, girl, other, int(scene["channel_id"]), cast.id)
            if pair and pair[0].cell == pair[1].cell:
                return other
    return None


def protected_pair(
    game: "GameService",
    c: Connection,
    state: GameState,
    girl: ActorRef,
    other: ActorRef,
    channel: int,
    scene: str,
) -> tuple[ActorView, ActorView] | None:
    from girlframe.services.m3_battle import _cast

    cast = _cast(game, c, state, channel)
    if cast.id != scene or not cast.open or not {girl, other} <= {x.actor for x in cast.roles}:
        return None
    bound = profiles(c, game.store.campaign_id)
    try:
        protector = resolve(state, girl, bound, require_current_profile=False)
        protected = resolve(state, other, bound, require_current_profile=False)
    except ValueError:
        return None
    if (
        protector.cell is None
        or protected.cell is None
        or protector.offstage_source
        or protected.offstage_source
        or protector.custody not in (None, "free")
        or not {(girl, protector.controller), (other, protected.controller)}
        <= {(x.actor, x.controller) for x in cast.roles}
    ):
        return None
    return protector, protected


def prove_hunt(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    request: dict[str, Any],
) -> tuple[ActorRef, ActorRef]:
    original = _original(game, c, state, parent)
    body = json.loads(request["body_json"])
    if (
        original is None
        or original[1]["phrase"] != "hunt"
        or request["kind"] != HUNT
        or original[1] != body.get("source")
        or original[1]["target"] != body.get("actor")
        or original[1]["counterpart"] != body.get("target")
        or request["actor_id"] != original[1]["target"]["entity"]
    ):
        raise WorkflowError("Recover the original Hunt order and its exact actors")
    saved = original[1]
    girl, target = (
        ActorRef.model_validate(saved["target"]),
        ActorRef.model_validate(saved["counterpart"]),
    )
    scene = game.scene(c, parent["channel_id"])
    if (
        _hunt_target(game, c, state, scene, girl, int(saved["issuer"]["entity"]), target.token)
        != target
    ):
        raise WorkflowError("Recover the original Hunt target in this actual scene")
    return girl, target


def prove_counterpart(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    request: dict[str, Any],
) -> int:
    original = _original(game, c, state, parent)
    body = json.loads(request["body_json"])
    if original is None or original[1] != body.get("source"):
        raise WorkflowError("Recover the original Conditioning Phrase order")
    _, saved = original
    kind = request["kind"]
    phrase = "play_gentle" if kind == FLIRT else "play_rough"
    owner = saved.get("counterpart") if kind == ROUGH_REPLY else saved["target"]
    if saved["phrase"] != phrase or owner is None or request["actor_id"] != owner["entity"]:
        raise WorkflowError("Only the original participant owns this Conditioning Phrase choice")
    other = ActorRef.model_validate(saved["counterpart"])
    target = int(other.entity)
    scene = game.scene(c, parent["channel_id"])
    if (
        target != body["target"]
        or target not in scene["participants"]
        or target not in state.order
        or current_ref(state, target) != other
        or not HandlerService(game.store)._member(c, target)
    ):
        raise WorkflowError("Recover the exact original Conditioning Phrase counterpart")
    game.pilot_cast(c, state, scene, owners=(target,))
    return target


def validate_gentle(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    request: dict[str, Any],
    prepared: PlayInput,
) -> None:
    if (
        prepared.play != "flirt"
        or prepared.target != prove_counterpart(game, c, state, parent, request)
        or prepared.target_actor is not None
    ):
        raise WorkflowError("Make the original Play Gentle Flirt with its exact counterpart")


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
        raise WorkflowError("Recover the actual source of this private phrase response")
    _, saved = original
    if (
        answer.options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only the original phrase response fields")
    if request["kind"] in ROUGH_CHOICES:
        target = prove_counterpart(game, c, state, action, request)
        _rough_response(game, c, action, request["kind"], answer, target, body)
        return
    if request["kind"] == SIT:
        if saved["phrase"] != "sit" or not answer.text.strip() or answer.flag is not None:
            raise WorkflowError("Describe how the original Girl actually sits")
        girl = ActorRef.model_validate(saved["target"])
        _seat_body(state, girl)
        save_sitting(
            state,
            Seated(
                target=girl,
                issuer=ActorRef.model_validate(saved["issuer"]),
                order=saved["order"],
                choice=request["id"],
                event=action["data"]["response_event"],
            ),
        )
        return
    if request["kind"] == PROTECT:
        if saved["phrase"] != "protect" or not answer.text.strip() or answer.flag is not None:
            raise WorkflowError("Describe how the original Girl takes her position for Protect")
        girl = ActorRef.model_validate(saved["target"])
        other = ActorRef.model_validate(saved["counterpart"])
        pair = protected_pair(
            game, c, state, girl, other, int(action["channel_id"]), action["scene_id"]
        )
        if pair is None or pair[0].cell != pair[1].cell or girl in protections(state):
            raise WorkflowError(
                "Take position beside one actual person without another active Protect"
            )
        save_protection(
            state,
            Protection(
                girl=girl,
                protected=other,
                order=saved["order"],
                choice=request["id"],
                scene=action["scene_id"],
                event=action["data"]["response_event"],
            ),
        )
        return
    if request["kind"] == HEEL:
        if saved["phrase"] != "heel" or not answer.text.strip() or answer.flag is not None:
            raise WorkflowError("Describe how the original Girl actually answers Heel")
        girl = ActorRef.model_validate(saved["target"])
        issuer = ActorRef.model_validate(saved["issuer"])
        body, caller = _heel_bodies(game, c, state, girl, issuer)
        event = action["data"]["response_event"]
        seated = sitting(state, girl)
        if seated is not None:
            save_sitting(state, seated.model_copy(update=dict(released=event)))
        protecting = protections(state).get(girl)
        if protecting is not None:
            save_protection(state, protecting.model_copy(update=dict(ended=event)))
        save_heel(
            state,
            Heel(
                target=girl,
                issuer=issuer,
                order=saved["order"],
                event=event,
                scene=action["scene_id"],
                channel=int(action["channel_id"]),
                reached=event if body.cell == caller.cell else None,
            ),
        )
        return
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


def _rough_response(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    kind: str,
    answer: ChoiceAnswer,
    target: int,
    body: dict[str, Any],
) -> None:
    if answer.flag is None or answer.text:
        raise WorkflowError("Only give your own private invitation decision")
    data, event = action["data"], action["data"]["response_event"]
    if kind == ROUGH_OFFER:
        data["trainer_rough"] = dict(invited=event) if answer.flag else dict(passed=event)
        if answer.flag:
            game.request(c, action, target, ROUGH_REPLY, body)
        return
    invitation = data.get("trainer_rough", {})
    if kind == ROUGH_REPLY and invitation.get("invited") and not invitation.get("answered"):
        invitation.update(accepted=answer.flag, answered=event)
        game.request(c, action, int(body["source"]["target"]["entity"]), ROUGH_HEARD, body)
    elif kind == ROUGH_HEARD and answer.flag is True and invitation.get("answered"):
        invitation["heard"] = event
    else:
        raise WorkflowError("Recover the original invitation and its actual response")


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
    if request["kind"] in ROUGH_CHOICES:
        target = prove_counterpart(game, c, state, action, request)
        invitation = action["data"].get("trainer_rough", {})
        if request["kind"] == ROUGH_OFFER:
            return "The original order nominates " + state.sheets[str(target)].callsign + "."
        if request["kind"] == ROUGH_REPLY and invitation.get("invited"):
            return (
                state.sheets[saved["target"]["entity"]].callsign
                + " invited you to a private scene."
            )
        if request["kind"] == ROUGH_HEARD and invitation.get("answered"):
            if invitation["accepted"]:
                return "Your counterpart accepted. Use the usual scene controls if you continue."
            return "Your counterpart declined the invitation."
        raise WorkflowError("Recover the original invitation and its actual response")
    if request["kind"] in (SPEAK, SIT, HEEL, PROTECT):
        return str(root["data"]["order_text"])
    spoken = action["data"].get("trainer_spoken", {})
    if spoken.get("source") != saved:
        raise WorkflowError("Only the original recipient can recover this actual answer")
    return str(spoken["answer"])


def _heel_bodies(
    game: "GameService", c: Connection, state: GameState, girl: ActorRef, issuer: ActorRef
) -> tuple[ActorView, ActorView]:
    bound = profiles(c, game.store.campaign_id)
    try:
        body = resolve(state, girl, bound, require_current_profile=False)
        caller = resolve(state, issuer, bound, require_current_profile=False)
    except ValueError as exc:
        raise WorkflowError("Recover the original Heel participants") from exc
    if (
        body.cell is None
        or caller.cell is None
        or body.inside_frame is not False
        or body.offstage_source
        or caller.offstage_source
        or body.custody not in (None, "free")
    ):
        raise WorkflowError("Heel requires the two original bodies with known positions")
    return body, caller


def reach_heel(
    game: "GameService", c: Connection, state: GameState, girl: ActorRef, scene: str, event: str
) -> None:
    work = pending_heel(state, girl)
    if work is None or work.scene != scene:
        return
    current = game.scene(c, work.channel)
    if current["id"] != work.scene or int(work.issuer.entity) not in current["participants"]:
        return
    try:
        body, caller = _heel_bodies(game, c, state, girl, work.issuer)
    except WorkflowError:
        return
    if body.cell == caller.cell:
        save_heel(state, work.model_copy(update=dict(reached=event)))


def heel_task(game: "GameService", viewer: GuildViewer, event: str) -> Heel:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        if viewer.user_id not in state.order:
            raise WorkflowError("Recover your own original Heel order")
        work = pending_heel(state, current_ref(state, viewer.user_id))
        if work is None or work.event != event:
            raise WorkflowError("Recover your own original Heel order")
        scene = game.scene(c, work.channel)
        if scene["id"] != work.scene or not {viewer.user_id, int(work.issuer.entity)} <= set(
            scene["participants"]
        ):
            raise WorkflowError("Recover the active original Heel scene and issuer")
        _heel_bodies(game, c, state, work.target, work.issuer)
        return work


def _seat_body(state: GameState, girl: ActorRef) -> None:
    pose = next((x for x in state.placements if x.actor == girl), None)
    if (
        pose is None
        or pose.mode != "outside_frame"
        or pose.girl_cell is None
        or pose.subsumed
        or pose.incapacitated
        or not pose.vitals_active
        or sitting(state, girl) is not None
    ):
        raise WorkflowError("Use the original Girl who can sit outside her actual Frame")


def grant_leave(
    game: "GameService", viewer: GuildViewer, key: str, channel: int, target: int
) -> dict[str, Any]:
    def authorize(c: Connection) -> None:
        Access(game.store).authorize(c, viewer, "plays")
        game.unpaused(c)

    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.services.m3_handler_plays import _ordinary_scene_idle
        from girlframe.services.m3_sentinel import require_order_communication

        _ordinary_scene_idle(c, game)
        state = load_state(c, game.store.campaign_id)
        scene = game.scene(c, channel)
        if str(target) not in state.sheets:
            raise WorkflowError("Choose the original seated Girl")
        girl = current_ref(state, target)
        record = sitting(state, girl)
        if (
            record is None
            or record.issuer.entity != str(viewer.user_id)
            or not {viewer.user_id, target} <= set(scene["participants"])
            or record.issuer != current_ref(state, viewer.user_id)
        ):
            raise WorkflowError("Only the original Sit issuer can grant leave in a shared scene")
        game.pilot_cast(c, state, scene, owners=(viewer.user_id, target))
        require_order_communication(c, game.store.campaign_id, state, viewer.user_id, target)
        responses = t.m2["m2_responses"]
        if (
            c.scalar(
                sa.select(responses.c.event_id).where(
                    responses.c.campaign_id == game.store.campaign_id,
                    responses.c.choice_id == record.choice,
                    responses.c.event_id == record.event,
                    responses.c.actor_id == girl.entity,
                )
            )
            is None
        ):
            raise WorkflowError("Recover the original Girl's performed Sit response")
        event = str(uuid4())
        save_sitting(state, record.model_copy(update=dict(released=event)))
        game.event(c, viewer.user_id, key, "m3.trainer_sit_released", state, event_id=event)
        return dict(event=event)

    return game.store._write(
        viewer,
        key,
        "m3.trainer_sit_released",
        dict(channel=channel, target=target),
        operation,
        auto_audit=False,
        authorize=authorize,
    )
