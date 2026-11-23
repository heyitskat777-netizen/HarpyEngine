"""Owned in-Frame Gorgon rolls, damage, private resistance and rebirth."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gorgon_frame_contact as frame
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_janus_storage import alter, effective_assets, ids
from girlframe.engine.m3_void_state import VoidThreshold
from girlframe.services.m3_gorgon_contact import _current, _expose, _prove_contact
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

FRAME_ROLL = "gorgon_contact_frame_roll"
FRAME_DAMAGE = "gorgon_contact_frame_damage"
FRAME_CONSEQUENCE = "gorgon_contact_frame_consequence"
FRAME_VOID = "gorgon_contact_frame_void"
FRAME_REBIRTH = "gorgon_frame_contact_rebirth"


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
    gorgon: ActorView,
    girl: ActorView,
) -> None:
    from girlframe.services.m3_gorgon_runtime import _damage

    meta = action["data"]["gorgon_play"]
    event = action["data"]["response_event"]
    if row["kind"] == FRAME_ROLL:
        if (
            row["actor_id"] != str(gorgon.controller)
            or answer.flag is not True
            or answer.options
            or answer.fields
            or answer.text
            or answer.denied
            or answer.number is not None
            or answer.member is not None
            or "frame_contact_roll" in meta
            or girl.frame_instance is None
        ):
            raise WorkflowError("Only the original Gorgon rolls after the verified contact")
        _prove_contact(game, c, action, gorgon, girl)
        raw = frame.Roll(
            faces=game.dice.roll(),
            void_assets=frame.frame_void(state, girl.ref),
            event=event,
            frame=girl.frame_instance,
        )
        meta["frame_contact_roll"] = raw.model_dump(mode="json")
        state.facts.append(
            dict(
                kind="gorgon_frame_contact_roll",
                action=action["id"],
                event=event,
                body=raw.model_dump_json(),
            )
        )
        if raw.result != "high":
            game.request(c, action, girl.controller, FRAME_DAMAGE)
        else:
            game.request(c, action, meta["procedural_gm"], FRAME_CONSEQUENCE)
        return
    if row["kind"] == FRAME_VOID:
        raise WorkflowError("This saved result is waiting for its actual rule consequence")
    raw = frame.Roll.model_validate_json(json.dumps(meta["frame_contact_roll"]))
    if not any(
        x.get("kind") == "gorgon_frame_contact_roll"
        and x.get("action") == action["id"]
        and x.get("event") == raw.event
        and x.get("body") == raw.model_dump_json()
        for x in state.facts
    ):
        raise WorkflowError("Recover the original saved Gorgon roll before applying damage")
    if row["kind"] == FRAME_CONSEQUENCE:
        if answer.options == ("intervene",):
            from girlframe.services.m3_gorgon_runtime import _response

            if (
                row["actor_id"] != str(meta["procedural_gm"])
                or not answer.text.strip()
                or answer.flag is not None
                or answer.denied
                or answer.fields
                or answer.member is not None
                or answer.number is not None
                or meta.get("frame_intervention")
                or raw.result != "high"
            ):
                raise WorkflowError("Use the original GM's single immediate intervention")
            meta["frame_intervention"] = event
            _response(game, c, state, action, girl.ref)
        else:
            _approve_rebirth(state, action, girl, raw, row, answer, event)
        return
    if (
        raw.result == "high"
        or raw.frame != girl.frame_instance
        or row["actor_id"] != str(girl.controller)
        or len(answer.options) != 1
        or answer.options[0] not in _available(girl)
        or answer.text
        or answer.denied
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError("Choose one actual intact Asset of this original Girl and Frame")
    damage_asset = answer.options[0]
    void_asset = work = None
    if raw.result == "mid":
        if answer.flag is None or set(answer.fields) != {"void_asset", "void_description"}:
            raise WorkflowError("Resolve the actual Void gain and optional Core exposure")
        void_asset, work = _frame_void_gain(state, action, girl, answer.fields, event)
    elif answer.fields or answer.flag is not None:
        raise WorkflowError("The low result requires its own damage only")
    _damage(game, c, state, action, girl.ref, damage_asset, occurrence=row["id"])
    expose = raw.result == "low" or answer.flag is True
    if expose:
        _expose(state, gorgon.ref)
    outcome = frame.Consequence(
        action=action["id"],
        scene=action["scene_id"],
        event=event,
        source=gorgon.ref,
        girl=girl.ref,
        roll=raw,
        damaged_asset=damage_asset,
        void_asset=void_asset,
        void_work=work,
        core_exposed=expose,
        punishment_if_discovered=raw.result == "mid",
    )
    state.facts.append(dict(kind=frame.KIND, id=action["id"], body=outcome.model_dump_json()))
    action["data"]["result"]["contact"] = "resolved"


def _approve_rebirth(
    state: GameState,
    action: dict[str, Any],
    girl: ActorView,
    raw: frame.Roll,
    row: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> None:
    from girlframe.engine.m3_void import FINAL as STABLE_VOID

    meta = action["data"]["gorgon_play"]
    if (
        raw.result != "high"
        or raw.frame != girl.frame_instance
        or row["actor_id"] != str(meta["procedural_gm"])
        or answer.flag is not True
        or not answer.text.strip()
        or answer.options
        or answer.fields
        or answer.denied
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError(
            "The actual original high consequence requires a verified immediate outcome"
        )
    if any(x.actor == girl.ref and x.stage not in STABLE_VOID for x in state.void_thresholds):
        raise WorkflowError("Resolve the actual original prior threshold before opening rebirth")
    work = f"{action['id']}:contact:rebirth"
    state.void_thresholds.append(
        VoidThreshold(
            id="void:" + work,
            actor=girl.ref,
            frame_instance=raw.frame,
            family="frame",
            source_event=event,
            source_action=action["id"],
            source_works=(work,),
            sheet_json=state.sheets[girl.ref.entity].model_dump_json(),
            stage="rebirth",
            enclosed=True,
            forced_by="gorgon_frame_contact",
        )
    )
    meta["frame_rebirth"] = event
    meta["followups"].append(work)


def _frame_void_assets(state: GameState, girl: ActorView) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if not x.void and (x.family == "girl" or girl.piloting is True)
    }


def _frame_void_gain(
    state: GameState, action: dict[str, Any], girl: ActorView, fields: dict[str, str], event: str
) -> tuple[str | None, str | None]:
    from girlframe.engine.m3_void import FINAL as STABLE_VOID

    identity, description = fields["void_asset"], fields["void_description"].strip()
    if (
        identity not in _frame_void_assets(state, girl)
        or not description
        or any(x.actor == girl.ref and x.stage not in STABLE_VOID for x in state.void_thresholds)
    ):
        raise WorkflowError(
            "Choose your current uncorrupted Asset after resolving any active threshold"
        )
    original = next(x for x in state.sheets[girl.ref.entity].assets if x.id == identity)
    changed, effects = alter(
        state,
        girl.ref,
        identity,
        description,
        action["id"],
        event,
        piloting=girl.piloting is True,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    if identity not in ids(state, girl.ref) and not next(
        x.void for x in state.sheets[girl.ref.entity].assets if x.id == identity
    ):
        return None, None
    family = original.family
    work = (
        f"{action['id']}:contact:void:{family}"
        if any(
            x.kind == f"{family}_void_threshold"
            or family == "frame"
            and x.kind == "mockingbird_resist"
            for x in effects
        )
        else None
    )
    if work:
        action["data"]["gorgon_play"]["followups"].append(work)
    return identity, work


def _available(girl: ActorView) -> dict[str, str]:
    return {x.id: x.name for x in girl.assets if not x.damaged}


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    kind = row["kind"].removeprefix("gorgon_")
    detail = dict(kind=kind, in_frame=action["data"]["gorgon_play"]["kind"] == frame.PLAY)
    if row["kind"] == FRAME_VOID:
        detail["work"] = json.loads(row["body_json"])["work_id"]
    if row["kind"] in (FRAME_DAMAGE, FRAME_CONSEQUENCE):
        raw = frame.Roll.model_validate_json(
            json.dumps(action["data"]["gorgon_play"]["frame_contact_roll"])
        )
        detail.update(faces=raw.faces, bonus=len(raw.void_assets), tier=raw.result)
        if row["kind"] == FRAME_CONSEQUENCE:
            detail["can_intervene"] = not action["data"]["gorgon_play"].get("frame_intervention")
        if row["kind"] == FRAME_DAMAGE:
            _, girl = _current(game, c, state, action)
            detail["assets"] = _available(girl)
            if raw.result == "mid":
                detail["void_assets"] = _frame_void_assets(state, girl)
    return detail


def materialize(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if action["data"]["gorgon_play"].get("frame_rebirth") == event:
        value = next(
            (
                x
                for x in state.void_thresholds
                if x.forced_by == "gorgon_frame_contact"
                and x.source_action == action["id"]
                and x.source_event == event
            ),
            None,
        )
        if value is None:
            raise WorkflowError("Recover the original high result's pending rebirth")
        _materialize_void_work(
            game,
            c,
            action,
            value.actor,
            value.source_works[0],
            event,
            FRAME_REBIRTH,
        )
        return
    result = next((x for x in frame.results(state) if x.action == action["id"]), None)
    if result is None or not result.void_work or result.event != event:
        return
    _materialize_void_work(game, c, action, result.girl, result.void_work, event, frame.KIND)


def _materialize_void_work(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    girl: ActorRef,
    identity: str,
    event: str,
    reason: str,
) -> None:
    work = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(work.c.id).where(
            work.c.campaign_id == game.store.campaign_id, work.c.id == identity
        )
    ):
        return
    owner = int(girl.entity)
    related(
        c,
        game.store,
        action,
        identity,
        owner,
        owner,
        "void_threshold",
        dict(
            owner=girl.model_dump(mode="json"),
            character=girl.incarnation,
            source_action=action["id"],
            source_pdf=19,
            reason=reason,
            details=dict(
                family="frame" if reason == FRAME_REBIRTH else identity.rsplit(":", 1)[-1]
            ),
        ),
        event,
    )
    game.request(c, action, owner, FRAME_VOID, dict(work_id=identity))


def prove_frame_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    girl: ActorRef,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, body["source_action"])
    original = GorgonPlayService(game).source(c, action)
    proof = next((x for x in frame.results(state) if x.action == action["id"]), None)
    if (
        original["kind"] != frame.PLAY
        or proof is None
        or proof.roll.result != "mid"
        or proof.event != row["event_id"]
        or proof.girl != girl
        or proof.scene != row["scene_id"]
        or proof.void_work != row["id"]
        or proof.void_asset is None
        or proof.void_asset not in {x.id for x in effective_assets(state, girl) if x.void}
    ):
        raise WorkflowError("Recover the actual original mid result and source-owned Void gain")


def prove_frame_rebirth(
    game: "GameService",
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    girl: ActorRef,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, body["source_action"])
    original = GorgonPlayService(game).source(c, action)
    meta = action["data"]["gorgon_play"]
    saved = frame.Roll.model_validate_json(json.dumps(meta["frame_contact_roll"]))
    event = row["event_id"]
    value = next(
        (
            x
            for x in state.void_thresholds
            if x.forced_by == "gorgon_frame_contact"
            and x.source_event == event
            and x.source_action == action["id"]
        ),
        None,
    )
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    review = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == event,
            responses.c.actor_id == str(original["procedural_gm"]),
            choices.c.action_id == action["id"],
            choices.c.kind == FRAME_CONSEQUENCE,
        )
    )
    if (
        original["kind"] != frame.PLAY
        or value is None
        or value.stage != "rebirth"
        or value.actor != girl
        or value.frame_instance != saved.frame
        or value.source_works != (row["id"],)
        or row["scene_id"] != action["scene_id"]
        or body["details"]["family"] != "frame"
        or saved.result != "high"
        or review is None
        or json.loads(review).get("flag") is not True
        or not any(
            x.get("kind") == "gorgon_frame_contact_roll"
            and x.get("action") == action["id"]
            and x.get("event") == saved.event
            and x.get("body") == saved.model_dump_json()
            for x in state.facts
        )
    ):
        raise WorkflowError("Recover the original rolled high result and verified rebirth source")


def complete_frame_void(
    game: "GameService",
    c: Connection,
    identity: str,
    parent: str,
    event: str,
    viewer: Any,
    key: str,
) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, parent)
    owned = [
        x
        for x in game.pending(c, parent)
        if x["kind"] == FRAME_VOID and json.loads(x["body_json"]).get("work_id") == identity
    ]
    if len(owned) != 1:
        raise WorkflowError("Recover the actual Gorgon contact Void consequence")
    choice = owned[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == choice["id"],
        )
        .values(state="completed_by_work", revision=choice["revision"] + 1)
    )
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)


def finish_intervention(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: dict[str, Any],
    child: dict[str, Any],
    event: str,
) -> None:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    meta = parent["data"]["gorgon_play"]
    source = ActorRef.model_validate(meta["actor"])
    girl = ActorRef.model_validate(meta["target"])
    raw = frame.Roll.model_validate_json(json.dumps(meta["frame_contact_roll"]))
    events = t.events
    minimum = c.scalar(
        sa.select(events.c.seq).where(
            events.c.campaign_id == game.store.campaign_id, events.c.id == raw.event
        )
    )
    candidates = [ended_actor_source(game, c, state, source)]
    if any(x.actor == girl and x.ending == "death" for x in state.career_archives):
        candidates.append(ended_actor_source(game, c, state, girl))
    ended = c.scalar(
        sa.select(events.c.id)
        .where(
            events.c.campaign_id == game.store.campaign_id,
            events.c.id.in_([x for x in candidates if x is not None]),
            events.c.seq > minimum if minimum is not None else sa.false(),
        )
        .limit(1)
    )
    meta["intervention_receipt"] = dict(child=child["id"], event=event, ended=ended)
    if ended:
        parent["data"]["result"]["contact"] = "interrupted"
    else:
        game.request(c, parent, meta["procedural_gm"], FRAME_CONSEQUENCE)
    game.save_action(c, parent)
