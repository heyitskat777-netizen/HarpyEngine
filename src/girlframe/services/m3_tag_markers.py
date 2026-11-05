"""Frozen cast and current source-resource proof for Pilot shared-Play Tag windows."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_tag_markers as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def context(action: dict[str, Any]) -> dict[str, Any] | None:
    data = action["data"]
    actor_basic = data.get("actor_basic")
    frozen = data.get("tag_context")
    if isinstance(actor_basic, dict) and frozen is not None:
        # A rule's adjudicator can be a Director NPC; the frozen Tag context
        # separately records the original main Handler body and actual cast.
        try:
            if not isinstance(frozen, dict):
                raise ValueError()
            actor = ActorRef.model_validate_json(json.dumps(actor_basic["ref"]))
            cast = SceneCast.model_validate_json(json.dumps(frozen["cast"]))
            if (
                frozen["actor"] != actor.model_dump(mode="json")
                or frozen["cast_sha256"] != fingerprint(cast)
                or actor_basic["cast_revision"] != cast.revision
                or set(frozen["table"]) != set(data["participants"])
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise WorkflowError("Recover the actual original role's frozen Tag context.") from None
        value = frozen
    else:
        value = data.get("dive") or data.get("enforcement") or data.get("void_keep") or frozen
    if value is None:
        return None
    if not isinstance(value, dict):
        raise WorkflowError("Recover the actual source Tag context.")
    result = dict(value)
    if data.get("enforcement") is value and "marker_handler" in result:
        result["handler"] = result["marker_handler"]
    if data.get("dive") is value and "marker_handler" in result:
        result["handler"] = result["marker_handler"]
    if "cast_sha256" not in result and action["data"].get("void_keep") is value:
        result["cast_sha256"] = fingerprint(
            SceneCast.model_validate_json(json.dumps(result["cast"]))
        )
    return result


def roller(state: GameState, action: dict[str, Any]) -> ActorRef:
    source = context(action)
    if source:
        return ActorRef.model_validate_json(json.dumps(source["actor"]))
    return current_ref(state, int(action["actor_id"]))


def _original_handler(
    game: "GameService", c: Connection, action: dict[str, Any]
) -> tuple[ActorRef | None, str]:
    event = c.execute(
        sa.select(t.events.c.seq, t.events.c.id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.play_confirmed", "m3.play_confirmed")),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
        )
        .order_by(t.events.c.seq)
        .limit(1)
    ).first()
    if event is None:
        raise ValueError("SOURCE_TAG_HANDLER_MISSING: recover the actual original Play")
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.seq <= event.seq,
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise ValueError("SOURCE_TAG_HANDLER_MISSING: recover the actual original Handler context")
    original = GameState.model_validate_json(body)
    if original.handler != action["data"]["handler"]:
        raise ValueError("Recover this actual Play's original human GM")
    return active_handler(original), str(event.id)


def current(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> tuple[rules.Marker, ...]:
    if owner not in action["data"]["participants"]:
        raise WorkflowError("Only an original table human owns a Tag window response.")
    source = context(action)
    try:
        if source is None:
            if (
                owner == action["data"]["handler"]
                and owner == state.handler
                and state.handler_archives
            ):
                original_handler, binding = _original_handler(game, c, action)
                if original_handler != active_handler(state) or original_handler is None:
                    if original_handler is not None and not any(
                        x.actor == original_handler for x in state.handler_archives
                    ):
                        raise ValueError(
                            "STALE_TAG_MARKER: recover the actual original Handler body"
                        )
                    return (
                        rules.ooc_marker(
                            owner,
                            binding,
                            binding
                            + ":"
                            + ":".join(x.source_event for x in state.handler_archives),
                        ),
                    )
            ref = current_ref(state, owner)
            if owner == state.handler:
                active_context = next(
                    (x for x in state.director_contexts if x.active and x.handler == owner), None
                )
                if active_context is not None:
                    ref = ActorRef(kind="handler", entity=str(owner), incarnation=active_context.id)
            view = resolve(
                state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
            )
            expected = action["data"].get("character_ids", {}).get(str(owner))
            if ref.kind == "pilot" and expected is not None and ref.incarnation != expected:
                raise ValueError("STALE_TAG_MARKER: the original character changed")
            return (rules.make_marker(state, view, action["id"], roller(state, action)),)
        original = SceneCast.model_validate_json(json.dumps(source["cast"]))
        cast, _ = CastService(ActorService(MissionService(game.store)))._current(
            c, state, int(action["channel_id"])
        )
        from girlframe.services.m3_void_keep import _ended_handler_cast

        if fingerprint(original) != source["cast_sha256"]:
            raise ValueError("STALE_TAG_MARKER: recover the actual original cast")
        coordinator = original.facilitator
        from girlframe.services.m3_harpy_defeat import owned_director_procedure

        continued = owned_director_procedure(game, c, state, action)
        if fingerprint(cast) != fingerprint(original) and not (
            coordinator is not None
            and _ended_handler_cast(state, original, cast, coordinator)
            or continued is not None
        ):
            raise ValueError("STALE_TAG_MARKER: recover the actual original cast")
        handler = (
            ActorRef.model_validate_json(json.dumps(source["handler"]))
            if source.get("handler")
            else None
        )
        if handler is not None and handler != active_handler(state):
            if not any(x.actor == handler for x in state.handler_archives):
                raise ValueError("STALE_TAG_MARKER: recover the actual original Handler body")
            handler = None
        # A proven ended role is no longer a fictional candidate; the same actual human
        # facilitator can still make their printed other-player Tag proposal.
        effective = (
            cast
            if continued is not None
            else original.model_copy(
                update={
                    "roles": tuple(
                        x
                        for x in original.roles
                        if not any(x.actor == a.actor for a in state.handler_archives)
                    )
                }
            )
        )
        markers = rules.markers(
            state,
            profiles(c, game.store.campaign_id),
            effective,
            owner,
            roller(state, action),
            handler,
        )
        meta = action["data"].get("actor_basic", {})
        if (
            continued is not None
            and not markers
            and owner == meta.get("adjudicator_controller")
            and owner != continued.controller
        ):
            return (
                rules.ooc_marker(
                    owner,
                    "original-director-procedure:" + action["id"],
                    source["cast_sha256"] + ":" + fingerprint(cast) + ":" + continued.source_sha256,
                ).model_copy(update={"label": "Original OOC scene human (no fictional body)"}),
            )
        return markers
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def select(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    token: str | None,
) -> rules.Marker:
    values = current(game, c, state, action, owner)
    if token is None and len(values) == 1:
        return values[0]
    actual = next((x for x in values if x.token == token), None)
    if actual is None:
        raise WorkflowError(
            "STALE_TAG_MARKER: choose one of your actual original roles; refresh changed resources."
        )
    return actual


def capture(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    marker: rules.Marker,
) -> rules.Marker:
    # Recompute the known role after this same response's explicit Status effect, if any.
    actual = next(
        (
            x
            for x in current(game, c, state, action, marker.controller)
            if x.actor == marker.actor and x.source_binding == marker.source_binding
        ),
        None,
    )
    if actual is None:
        raise WorkflowError("STALE_TAG_MARKER: recover the actual original role.")
    action["data"].setdefault("tag_markers", {})[str(marker.controller)] = actual.model_dump(
        mode="json"
    )
    return actual


def saved(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> rules.Marker:
    data = action["data"].get("tag_markers", {}).get(str(owner))
    if data is None:
        # Existing legacy saved responses retain the original source character checks.
        if context(action) is not None:
            raise WorkflowError("STALE_TAG_MARKER: reopen the original source role proposal.")
        return select(game, c, state, action, owner, None)
    actual = rules.Marker.model_validate_json(json.dumps(data))
    return select(game, c, state, action, owner, actual.token)


def projection(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> list[dict[str, str]]:
    return [dict(token=x.token, label=x.label) for x in current(game, c, state, action, owner)]


def reopen(game: "GameService", c: Connection, action: dict[str, Any], owner: int) -> None:
    """Ask the actual human again when committed role resources changed; preserve the dice."""
    action["data"]["choices"].pop("tag_window:" + str(owner), None)
    action["data"].get("tag_markers", {}).pop(str(owner), None)
    action["data"].pop("tag_marker_discussion", None)
    game.request(
        c,
        action,
        owner,
        "tag_window",
        dict(reason="Review your actual changed source role and Tag proposal"),
    )


def begin_discussion(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    entries: list[tuple[int, Any, rules.Marker]],
) -> None:
    from uuid import NAMESPACE_URL, uuid5

    ruling = game.store.policy.owner_m3_rulings
    if ruling is None or ruling.actor_tag_disputes != "scene_unanimous_discussion":
        raise WorkflowError(
            "UNRESOLVED_RULING: mixed-role Tag disputes need owned table discussion."
        )
    source = context(action)
    if source is None:
        raise WorkflowError("Recover the actual frozen mixed-role table first.")
    judge = (
        source.get("gm_controller")
        or source.get("facilitator")
        or (source.get("handler") or {}).get("entity")
    )
    if judge is None:
        original = SceneCast.model_validate_json(json.dumps(source["cast"]))
        judge = original.facilitator
    if judge is None or int(judge) not in action["data"]["participants"]:
        raise WorkflowError("Recover the actual original human coordinator")
    judge = int(judge)
    action["data"]["tag_marker_discussion"] = dict(
        proposals=[
            dict(
                id=str(uuid5(NAMESPACE_URL, action["id"] + ":" + str(owner))),
                controller=owner,
                marker=marker.model_dump(mode="json"),
                answer=answer.model_dump(mode="json"),
            )
            for owner, answer, marker in entries
        ],
        judge=judge,
        revision=0,
        agreements={},
    )
    game.request(c, action, judge, "tag_marker_selection")


def discussion_projection(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> dict[str, Any]:
    discussion = action["data"]["tag_marker_discussion"]
    subject = roller(state, action)
    sheet = state.sheets[subject.entity]
    items = []
    for index, item in enumerate(discussion["proposals"]):
        marker = rules.Marker.model_validate_json(json.dumps(item["marker"]))
        tag = next((x for x in sheet.tags if x.id == item["answer"]["denied"][0]), None)
        observed = tag is not None and (owner == int(subject.entity) or owner in tag.observers)
        visible = (
            marker.actor is None
            or marker.actor.kind in ("pilot", "handler")
            or marker.controller == owner
        )
        if state.world and marker.actor is not None and marker.actor.kind == "npc":
            visible |= any(x.id == marker.actor.entity and x.revealed for x in state.world.npcs)
        label = marker.label if visible else "Original private role"
        amount = marker.bonus * (1 if item["answer"]["number"] == 1 else -1)
        items.append(
            dict(
                id=item["id"],
                label=f"Proposal{index + 1}: {label} ({amount:+d})",
                tag=tag.label if observed and tag else "Private observed Tag",
                account=item["answer"]["text"]
                if observed
                else "Relevance remains private to its actual witnesses.",
                amount=amount,
            )
        )
    return dict(
        proposals=items, candidate=discussion.get("candidate"), revision=discussion["revision"]
    )


def apply_discussion(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: Any,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    discussion = action["data"]["tag_marker_discussion"]
    owner = int(row["actor_id"])
    if owner not in action["data"]["participants"]:
        raise WorkflowError("This actual source table owns the Tag discussion.")
    if row["kind"] == "tag_marker_selection":
        if (
            owner != discussion["judge"]
            or len(answer.options) != 1
            or answer.denied
            or answer.fields
            or answer.number is not None
            or answer.member is not None
            or answer.flag is not None
        ):
            raise WorkflowError("The actual coordinator selects one original saved Tag proposal.")
        proposal = next((x for x in discussion["proposals"] if x["id"] == answer.options[0]), None)
        if proposal is None:
            raise WorkflowError("Choose an actual original proposal for discussion.")
        marker = rules.Marker.model_validate_json(json.dumps(proposal["marker"]))
        try:
            select(game, c, state, action, proposal["controller"], marker.token)
        except WorkflowError:
            reopen(game, c, action, proposal["controller"])
            return
        discussion["revision"] += 1
        discussion["candidate"] = proposal["id"]
        discussion["agreements"] = {}
        for uid in action["data"]["participants"]:
            game.request(
                c,
                action,
                uid,
                "tag_marker_agreement",
                dict(proposal=proposal["id"], revision=discussion["revision"]),
            )
        return
    body = json.loads(row["body_json"])
    if (
        row["kind"] != "tag_marker_agreement"
        or answer.flag is None
        or answer.options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
        or body.get("proposal") != discussion.get("candidate")
        or body.get("revision") != discussion["revision"]
    ):
        raise WorkflowError("Agree or reject only the exact current original Tag proposal.")
    discussion["agreements"][str(owner)] = answer.flag
    if any(x["kind"] == "tag_marker_agreement" for x in game.pending(c, action["id"])):
        return
    if not all(discussion["agreements"].values()):
        game.request(c, action, discussion["judge"], "tag_marker_selection")
        return
    discussion["ready"] = True
    ChoiceEngine(game).close_tag_window(c, state, action)
