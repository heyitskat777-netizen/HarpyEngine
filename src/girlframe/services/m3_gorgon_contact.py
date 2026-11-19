"""Private consent and original consequences for the out-of-Frame Gorgon Play."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_leviathan import layers_clear
from girlframe.engine.m3_world import update
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

PLAY = "intimate_contact"
RULE = "gorgon.gorgon.gorgons-fucking-girls"
CONSENT = "gorgon_contact_consent"
REVIEW = "gorgon_contact_review"
CONCLUSION = "gorgon_contact_conclusion"
FINAL = "gorgon_contact_final"


def eligible(state: GameState, gorgon: ActorView, girl: ActorView) -> bool:
    if state.world is None or girl.ref.kind != "pilot" or girl.rules != "girl_frame":
        return False
    body = next((x for x in state.world.gorgons if x.id == gorgon.ref.entity), None)
    sheet = state.sheets[girl.ref.entity]
    placement = next((x for x in state.placements if x.actor == girl.ref), None)
    return bool(
        body
        and body.alive
        and body.gorgon_class not in ("benevolent", "dormant")
        and layers_clear(body)
        and girl.alive
        and girl.vitals_active is not False
        and placement is not None
        and placement.vitals_active
        and not (placement.incapacitated or placement.subsumed)
        and girl.inside_frame is False
        and girl.custody in (None, "free")
        and sheet.medical_state == "fit"
        and not is_helpless(state, girl.ref)
        and gorgon.controller != girl.controller
        and girl.cell is not None
        and gorgon.cell == girl.cell
        and not (gorgon.offstage_source or girl.offstage_source)
    )


def _current(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorView, ActorView]:
    meta = action["data"]["gorgon_play"]
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    bound = profiles(c, game.store.campaign_id)
    gorgon = resolve(
        state, ActorRef.model_validate(meta["actor"]), bound, require_current_profile=False
    )
    girl = resolve(
        state, ActorRef.model_validate(meta["target"]), bound, require_current_profile=False
    )
    if (
        not eligible(state, gorgon, girl)
        or not any(x.id == cast.id and x.open and x.roles == cast.roles for x in state.scene_casts)
        or not any(x.actor == girl.ref and x.controller == girl.controller for x in cast.roles)
        or gorgon.controller != meta["controller"]
    ):
        raise WorkflowError("Recover the actual free, present original participants and source")
    from girlframe.services.m3_jackdaw import require_action

    require_action(c, game.store.campaign_id, state, girl)
    return gorgon, girl


def start(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    _, girl = _current(game, c, state, action)
    game.request(c, action, girl.controller, CONSENT)


def _prove_contact(
    game: "GameService", c: Connection, action: dict[str, Any], gorgon: ActorView, girl: ActorView
) -> None:
    meta = action["data"]["gorgon_play"]
    expected = {
        CONSENT: (meta["contact_consent"], girl.controller),
        REVIEW: (meta["contact_review"], meta["procedural_gm"]),
        CONCLUSION: (meta["contact_conclusion"], gorgon.controller),
    }
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    actual = c.execute(
        sa.select(
            choices.c.kind, responses.c.event_id, responses.c.actor_id, responses.c.answer_json
        )
        .join(
            responses,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.action_id == action["id"],
            choices.c.kind.in_(tuple(expected)),
            choices.c.state == "answered",
        )
    )
    verified = {
        row.kind: ChoiceAnswer.model_validate_json(row.answer_json)
        for row in actual
        if expected[row.kind] == (row.event_id, int(row.actor_id))
    }
    expected_tag = meta["contact_tag"]
    if (
        set(verified) != set(expected)
        or verified[CONSENT].flag is not True
        or verified[REVIEW].flag is not True
        or verified[CONCLUSION].flag is not bool(expected_tag)
        or verified[CONCLUSION].text.strip() != expected_tag
    ):
        raise WorkflowError("Recover the original owned consent, review and optional Tag receipts")


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    gorgon, girl = _current(game, c, state, action)
    event = action["data"]["response_event"]
    meta = action["data"]["gorgon_play"]
    result = action["data"]["result"]
    owner = {
        CONSENT: girl.controller,
        REVIEW: meta["procedural_gm"],
        CONCLUSION: gorgon.controller,
        FINAL: girl.controller,
    }[row["kind"]]
    if (
        str(owner) != row["actor_id"]
        or answer.flag is None
        or answer.options
        or answer.fields
        or answer.denied
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use the original role's exact private consequence choice")

    if row["kind"] == CONSENT:
        if answer.text:
            raise WorkflowError("Choose whether to consent in the private control")
        if answer.flag:
            meta["contact_consent"] = event
            game.request(c, action, meta["procedural_gm"], REVIEW)
        else:
            result["contact"] = "declined"
        return
    if row["kind"] == REVIEW:
        if not meta.get("contact_consent") or not answer.text.strip():
            raise WorkflowError("Verify the actual trigger after the original Girl's consent")
        if answer.flag:
            meta["contact_review"] = event
            game.request(c, action, gorgon.controller, CONCLUSION)
        else:
            result["contact"] = "unconfirmed"
        return

    if not meta.get("contact_review") or not meta.get("contact_consent"):
        raise WorkflowError("The actual original consent and factual confirmation are required")
    if row["kind"] == CONCLUSION:
        label = answer.text.strip()
        if (answer.flag and not 1 <= len(label) <= 120) or (not answer.flag and label):
            raise WorkflowError("Choose one optional Tag or continue without one")
        meta["contact_conclusion"] = event
        meta["contact_tag"] = label
        game.request(c, action, girl.controller, FINAL)
        return

    if answer.text or "contact_tag" not in meta:
        raise WorkflowError("Only the Girl confirms the actual irreversible outcome")
    if not answer.flag:
        result["contact"] = "withdrawn"
        return
    _prove_contact(game, c, action, gorgon, girl)
    label = meta["contact_tag"]
    if label:
        tag = ChoiceEngine(game).add_tag(
            state,
            {"data": {"participants": meta["private_audience"]}},
            girl.controller,
            gorgon.controller,
            label,
        )
        tag.giver_actor = gorgon.ref
    assert state.world is not None
    state.world = update(
        state.world,
        gorgons=tuple(
            x.model_copy(update=dict(exposed=True)) if x.id == gorgon.ref.entity else x
            for x in state.world.gorgons
        ),
    )
    # The original completed contact is the printed exceptional exposure.
    ended = end_in_transaction(
        c,
        game,
        state,
        girl.ref,
        reason="death",
        source_event=event,
        account="Original private Gorgon contact finalized with consent and factual review",
        archive_id=action["id"],
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(ended, field))
    meta["contact_ending"] = event
    result["contact"] = "resolved"


def synchronize(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["gorgon_play"]
    if meta.get("contact_ending") != event:
        return
    archive = next(
        (x for x in state.career_archives if x.id == action["id"] and x.source_event == event), None
    )
    if archive is None:
        raise WorkflowError("Recover the actual original career ending")
    synchronize_end(c, game, archive)
