"""Owned Jackdaw response choices use the original range, roll and private Pilot sheet."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_hallucinations as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_jackdaw import Interference
from girlframe.engine.m3_janus_storage import alter, ids
from girlframe.engine.m3_void import FINAL
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_jackdaw import catatonic, isolation
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

HEAT = "gorgon_hallucinations_heat"
OUTCOME = "gorgon_hallucinations_outcome"
THRESHOLD = "gorgon_hallucinations_void"


def eligible(
    c: Connection, campaign: str, state: GameState, source: ActorRef, girl: ActorView, scene: str
) -> Interference | None:
    if (
        girl.ref.kind != "pilot"
        or girl.rules != "girl_frame"
        or not girl.alive
        or catatonic(c, campaign, state, girl)
    ):
        return None
    return next((x for x in isolation(c, campaign, state, girl, scene) if x.actor == source), None)


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["gorgon_play"]
    declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
    assert declared.target is not None
    girl = resolve(
        state, declared.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    original = eligible(c, game.store.campaign_id, state, declared.actor, girl, action["scene_id"])
    if original is None:
        raise WorkflowError("The actual Girl must still be Isolated by this original Jackdaw")
    meta["hallucinations"] = dict(girl=girl.controller, isolation=original.event)
    game.request(c, action, girl.controller, HEAT)


def _target(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> tuple[ActorView, ActorRef, dict[str, Any]]:
    meta = action["data"]["gorgon_play"]
    value = meta["hallucinations"]
    source = ActorRef.model_validate(meta["actor"])
    subject = ActorRef.model_validate(meta["target"])
    girl = resolve(
        state, subject, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    source_cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    original = eligible(c, game.store.campaign_id, state, source, girl, action["scene_id"])
    if (
        original is None
        or original.event != value["isolation"]
        or girl.controller != value["girl"]
        or str(girl.controller) != row["actor_id"]
        or not any(
            r.actor == subject and r.controller == girl.controller for r in source_cast.roles
        )
        or not any(
            current.id == source_cast.id and current.open and current.roles == source_cast.roles
            for current in state.scene_casts
        )
    ):
        raise WorkflowError(
            "Recover the original scene, Girl and active Isolation before responding"
        )
    return girl, source, value


def _identities(state: GameState, girl: ActorRef) -> dict[str, str]:
    sheet = state.sheets[girl.entity]
    return {
        x.id: x.name
        for x in sheet.identities
        if not (x.protected or x.paired or x.obsession_sources or x.id in sheet.sedation_locked)
    }


def _assets(state: GameState, girl: ActorView) -> dict[str, str]:
    sheet = state.sheets[girl.ref.entity]
    stored = ids(state, girl.ref)
    return {
        x.id: x.name
        for x in sheet.assets
        if not x.void
        and x.id not in stored
        and (x.family == "girl" or girl.piloting is True and not sheet.frame_scrapped)
    }


def project(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    if row["kind"] == THRESHOLD:
        return dict(kind="hallucinations_void", work=json.loads(row["body_json"])["work_id"])
    girl, _, value = _target(game, c, state, action, row)
    if row["kind"] == HEAT:
        return dict(kind="hallucinations_heat", heat=girl.heat)
    roll = rules.Roll.model_validate_json(json.dumps(value["roll"]))
    return dict(
        kind="hallucinations_outcome",
        roll=roll.model_dump(mode="json"),
        tier=roll.result,
        identities=_identities(state, girl.ref) if roll.result == "low" else {},
        assets=_assets(state, girl) if roll.result == "low" else {},
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if row["kind"] == THRESHOLD:
        raise WorkflowError("Resolve the actual Void source in your private consequence controls")
    girl, source, value = _target(game, c, state, action, row)
    if answer.denied or answer.flag is not None or answer.member is not None:
        raise WorkflowError("Use only the original owned Hallucinations choice")
    event = action["data"]["response_event"]
    sheet = state.sheets[girl.ref.entity]
    if row["kind"] == HEAT:
        if (
            answer.number is None
            or not 0 <= answer.number <= sheet.heat
            or answer.options
            or answer.text
            or answer.fields
            or "roll" in value
        ):
            raise WorkflowError("Choose Heat from this actual Girl before rolling")
        roll = rules.Roll(faces=game.dice.roll(), heat=answer.number, event=event)
        sheet.heat -= roll.heat
        if roll.heat:
            sheet.revision += 1
        value["roll"] = roll.model_dump(mode="json")
        game.request(c, action, girl.controller, OUTCOME)
        return

    roll = rules.Roll.model_validate_json(json.dumps(value["roll"]))
    label = answer.text.strip()
    if answer.number is not None or not 1 <= len(label) <= 120 or "effect" in value:
        raise WorkflowError("Describe the actual Hallucination as an owned Tag or Identity")
    removed: tuple[str, ...] = ()
    identity = None
    void_asset = None
    work: tuple[str, ...] = ()
    if roll.result == "low":
        if (
            len(answer.options) != 3
            or not set(answer.options) <= set(_identities(state, girl.ref))
            or set(answer.fields) != {"asset", "void_description"}
            or answer.fields["asset"] not in _assets(state, girl)
            or not answer.fields["void_description"].strip()
            or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
        ):
            raise WorkflowError(
                "Resolve the current identity or Void conflict before applying the low result"
            )
        removed = answer.options
        identity = "hallucinations:" + event
        slots = [x.slot for x in sheet.identities if x.id in removed and x.slot is not None]
        sheet.identities = [x for x in sheet.identities if x.id not in removed]
        sheet.identities.append(
            IdentityState(id=identity, name=label, slot=min(slots) if slots else None)
        )
        sheet.revision += 1
        selected = answer.fields["asset"]
        family = next(x.family for x in sheet.assets if x.id == selected)
        changed, followups = alter(
            state,
            girl.ref,
            selected,
            answer.fields["void_description"].strip(),
            action["id"],
            event,
            piloting=girl.piloting is True,
        )
        for name in GameState.model_fields:
            setattr(state, name, getattr(changed, name))
        void_asset = (
            selected
            if next(x.void for x in state.sheets[girl.ref.entity].assets if x.id == selected)
            else None
        )
        if any(
            x.kind == f"{family}_void_threshold"
            or family == "frame"
            and x.kind == "mockingbird_resist"
            for x in followups
        ):
            work = (f"{action['id']}:hallucinations:void:{family}",)
            meta = action["data"]["gorgon_play"]
            meta["followups"].extend(work)
    elif answer.options or answer.fields:
        raise WorkflowError("Only the original Girl authors the Hallucination Tag")
    tag = ChoiceEngine(game).add_tag(
        state,
        {"data": {"participants": (girl.controller, action["data"]["gorgon_play"]["controller"])}},
        girl.controller,
        action["data"]["gorgon_play"]["controller"],
        "Isolated" if roll.result == "low" else label,
    )
    tag.giver_actor = source
    effect = rules.Effect(
        action=action["id"],
        scene=action["scene_id"],
        source=source,
        girl=girl.ref,
        interference=value["isolation"],
        roll=roll,
        tag=tag.id,
        event=event,
        identities_erased=removed,
        identity=identity,
        void_asset=void_asset,
        void_work=work,
    )
    state.facts.append(dict(kind=rules.KIND, id=effect.action, body=effect.model_dump_json()))
    value["effect"] = effect.event
    action["data"]["result"]["hallucinations_resolved"] = True


def prove_threshold(
    game: "GameService",
    c: Connection,
    historical: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    girl: ActorRef,
) -> None:
    """Check the actual owned low-result response, canonical event and saved damage source."""
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, body["source_action"])
    meta = GorgonPlayService(game).source(c, action)
    event = row["event_id"]
    effect = next((x for x in rules.records(historical) if x.action == action["id"]), None)
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    answer = c.scalar(
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
            responses.c.actor_id == girl.entity,
            choices.c.kind == OUTCOME,
            choices.c.action_id == action["id"],
        )
    )
    if (
        meta["kind"] != "jackdaw_hallucinations"
        or effect is None
        or effect.roll.result != "low"
        or effect.girl != girl
        or effect.event != event
        or effect.scene != row["scene_id"]
        or row["id"] not in effect.void_work
        or answer is None
        or json.loads(answer).get("fields", {}).get("asset") != effect.void_asset
    ):
        raise WorkflowError("Recover the original Hallucinations roll, response and Void gain")


def materialize(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    current = next(
        (x for x in rules.records(state) if x.action == action["id"] and x.event == event), None
    )
    if current is None or not current.void_work:
        return
    actual = t.m3["m3_required_work"]
    for identity in current.void_work:
        if c.scalar(
            sa.select(actual.c.id).where(
                actual.c.campaign_id == game.store.campaign_id, actual.c.id == identity
            )
        ):
            continue
        owner = int(current.girl.entity)
        related(
            c,
            game.store,
            action,
            identity,
            owner,
            owner,
            "void_threshold",
            dict(
                owner=current.girl.model_dump(mode="json"),
                character=current.girl.incarnation,
                source_action=action["id"],
                source_pdf=19,
                reason=rules.KIND,
                details=dict(family=identity.rsplit(":", 1)[-1]),
            ),
            event,
        )
        game.request(c, action, owner, THRESHOLD, dict(work_id=identity))


def complete_void(
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
        if x["kind"] == THRESHOLD and json.loads(x["body_json"]).get("work_id") == identity
    ]
    if len(owned) != 1:
        raise WorkflowError("Recover the actual Hallucinations Void consequence")
    row = owned[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
        .values(state="completed_by_work", revision=row["revision"] + 1)
    )
    GorgonPlayService(game).synchronize(c, action, event, viewer, key)
