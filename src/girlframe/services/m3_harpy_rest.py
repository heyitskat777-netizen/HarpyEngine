"""Owned Harpy Off-Duty hide, honest receipt, factual navigation and actual recovery."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_harpy_defeat import fight_required, harpy, offstage_travel
from girlframe.engine.m3_harpy_defeat_state import Travel
from girlframe.engine.m3_harpy_resources import assets, set_assets
from girlframe.engine.m3_harpy_rest_state import Rest
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    cast: SceneCast,
    prepared: PlayInput,
    actor: ActorRef,
) -> dict[str, Any]:
    from girlframe.services.m3_actor_plays import ActorPlayService
    from girlframe.services.m3_medical import MedicalService

    body = harpy(state, actor)
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        prepared.play != "go_off_duty"
        or actor.kind != "external_pilot"
        or actual.controller != viewer.user_id
        or prepared.parent
        or prepared.source_work
        or prepared.heat
        or prepared.identity
        or prepared.gain
        or prepared.pair_share
        or body.body_incapacitated
        or (body.subsumed or not body.vitals_active)
        and actual.piloting is not True
        or body.frame_shutdown
        or body.custody != "free"
        or fight_required(state, actor)
        or actual.inside_frame is True
        and actual.piloting is not True
    ):
        raise WorkflowError(
            "Use this actual free Harpy's own Off-Duty hide without Heat or Identity spend."
        )
    if offstage_travel(state, actor) is not None or any(
        x.active and actor in (x.traveler, x.supervisor) for x in state.escort_journeys
    ):
        raise WorkflowError("Finish the original body's actual existing journey before a new hide.")
    judge = ActorPlayService(game)._judge(c, state, cast, actor)
    _, appointment = MedicalService(game.store)._handler(c)
    return dict(
        actor=actor.model_dump(mode="json"),
        controller=viewer.user_id,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        judge=judge.controller,
        adjudicator=judge.ref.model_dump(mode="json") if judge.ref else None,
        appointment=appointment,
        source_sha256=actual.source_sha256,
    )


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"]["play"] != "go_off_duty" or not action["data"].get("harpy_off_duty"):
        raise WorkflowError("Recover the actual Harpy Off-Duty source.")
    game.request(c, action, int(action["actor_id"]), "harpy_off_duty_hide")


def respond(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["harpy_off_duty"]
    actor = ActorRef.model_validate(meta["actor"])
    if row["kind"] != "harpy_off_duty_hide" or row["actor_id"] != str(meta["controller"]):
        raise WorkflowError("Only the actual original Harpy chooses her hide and Identities.")
    if (
        answer.flag is not True
        or not answer.text.strip()
        or set(answer.fields) != {"identities", "navigation"}
        or answer.options
        or answer.denied
        or answer.member
        or answer.number is not None
    ):
        raise WorkflowError("Confirm the actual Voidspace hide, navigation and chosen Identities.")
    try:
        names = json.loads(answer.fields["identities"])
    except (ValueError, TypeError):
        raise WorkflowError("Supply the actual owned ordinary Identity names.") from None
    if (
        not isinstance(names, list)
        or any(not isinstance(x, str) or not x.strip() or len(x) > 120 for x in names)
        or len(names) != len(set(x.casefold().strip() for x in names))
    ):
        raise WorkflowError("Each chosen ordinary Identity needs a distinct actual name.")
    body = harpy(state, actor)
    protected = tuple(
        x.model_copy(update={"marked": False}) for x in body.identities if x.protected
    )
    if any(name.strip().casefold() in {x.name.casefold() for x in protected} for name in names):
        raise WorkflowError(
            "Protected retained Identities remain; do not duplicate them as new ones."
        )
    prior = {x.name.casefold(): x for x in body.identities if not x.protected}
    identities = protected + tuple(
        prior[name.strip().casefold()].model_copy(update={"marked": False})
        if name.strip().casefold() in prior
        else HarpyIdentity(id=str(uuid4()), name=name.strip())
        for name in names
    )
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        body.body_incapacitated
        or (body.subsumed or not body.vitals_active)
        and actual.piloting is not True
        or body.frame_shutdown
        or body.custody != "free"
        or fight_required(state, actor)
        or offstage_travel(state, actor) is not None
        or any(x.active and actor in (x.traveler, x.supervisor) for x in state.escort_journeys)
    ):
        raise WorkflowError(
            "Resolve the actual original body's physical constraints before hiding."
        )
    source = action["data"]["response_event"]
    route = Travel(
        id=str(uuid4()),
        actor=actor,
        controller=actual.controller,
        source_event=source,
        source_sha256=actual.source_sha256,
        off_duty_action=action["id"],
        frame_instance=actual.frame_instance,
        travels_frame=actual.piloting is True,
        destination=None,
        account=answer.text.strip(),
        navigation=answer.fields["navigation"],
        judge=meta["judge"],
        adjudicator=ActorRef.model_validate(meta["adjudicator"]) if meta["adjudicator"] else None,
        appointment=meta["appointment"],
    )
    state.harpy_travels.append(route)
    state.harpy_rests.append(
        Rest(
            action=action["id"],
            actor=actor,
            controller=actual.controller,
            source_event=source,
            identities=identities,
            route=route.id,
        )
    )
    game.request(c, action, meta["judge"], "harpy_off_duty_route", dict(route=route.id))


def complete_route(
    game: "GameService",
    c: Connection,
    state: GameState,
    route: Travel,
    event: str,
) -> None:
    if route.off_duty_action is None or route.return_of is not None:
        return
    rest = next((x for x in state.harpy_rests if x.route == route.id), None)
    if rest is None or rest.phase != "proposed" or rest.actor != route.actor:
        raise WorkflowError("Recover the actual uncompleted Harpy hide source.")
    action = game.action(c, rest.action)
    request = next(
        (
            x
            for x in game.pending(c, rest.action)
            if x["kind"] == "harpy_off_duty_route"
            and json.loads(x["body_json"]).get("route") == route.id
            and x["actor_id"] == str(route.judge)
        ),
        None,
    )
    if request is None:
        raise WorkflowError("Recover this exact real navigation review continuation.")
    if route.state not in ("offstage", "rejected"):
        raise WorkflowError("The actual judge must first review this hide route.")
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == request["id"])
        .values(
            state="completed_by_work",
            revision=request["revision"] + 1,
            body_json=json.dumps(json.loads(request["body_json"]) | {"route_event": event}),
        )
    )
    if route.state == "rejected":
        state.harpy_rests = [
            x.model_copy(update={"phase": "rejected"}) if x == rest else x
            for x in state.harpy_rests
        ]
        game.request(c, action, rest.controller, "harpy_off_duty_hide")
    else:
        from girlframe.engine.m3_harpy_defeat import update

        changed = set_assets(
            state,
            rest.actor,
            tuple(x.model_copy(update={"damaged": False}) for x in assets(state, rest.actor)),
            event=event,
        )
        changed = update(changed, rest.actor, identities=rest.identities)
        for key in GameState.model_fields:
            setattr(state, key, getattr(changed, key))
        state.harpy_rests = [
            x.model_copy(update={"phase": "complete", "completion_event": event})
            if x == rest
            else x
            for x in state.harpy_rests
        ]
        if game.pending(c, rest.action):
            raise WorkflowError("Actual owned recovery follow-ups remain pending.")
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    game.save_action(c, action)


def projection(state: GameState, action: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    actor = ActorRef.model_validate(action["data"]["harpy_off_duty"]["actor"])
    body = harpy(state, actor)
    return dict(
        harpy_off_duty=True,
        ordinary_identities=[x.name for x in body.identities if not x.protected],
        protected_identities=[x.name for x in body.identities if x.protected],
        route=json.loads(row["body_json"]).get("route"),
    )


def synchronize_endings(game: "GameService", c: Connection, event: str) -> None:
    """Close only an impossible exact-original hide, with death proof and no human answer."""
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m2_state import load_state

    raw = c.scalar(
        t.m2["m2_state_history"]
        .select()
        .with_only_columns(t.m2["m2_state_history"].c.body_json)
        .where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Commit the actual original body ending before closing its hide.")
    proof = GameState.model_validate_json(raw)
    canon = load_state(c, game.store.campaign_id)
    actions = t.m2["m2_actions"]
    for row in c.execute(
        actions.select().where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.state.not_in(("complete", "aborted")),
        )
    ).mappings():
        data = json.loads(row["body_json"])
        meta = data.get("harpy_off_duty")
        if not meta:
            continue
        actor = ActorRef.model_validate(meta["actor"])
        body = harpy(proof, actor)
        if body.condition_event != event:
            continue
        view = resolve(
            proof,
            actor,
            profiles(c, game.store.campaign_id),
            require_alive=False,
            require_current_profile=False,
        )
        if view.alive or view.controller != int(row["actor_id"]):
            continue
        action = game.action(c, row["id"])
        for request in game.pending(c, action["id"]):
            if request["kind"] not in (
                "tag_window",
                "actor_tag_selection",
                "actor_tag_agreement",
                "tag_resolution",
                "harpy_off_duty_hide",
                "harpy_off_duty_route",
            ):
                raise WorkflowError("Preserve an unrecognized real original-owned consequence.")
            choices = t.m2["m2_choices"]
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == game.store.campaign_id, choices.c.id == request["id"]
                )
                .values(
                    state="completed_original_ended",
                    revision=request["revision"] + 1,
                    body_json=json.dumps(
                        json.loads(request["body_json"]) | {"original_ended_event": event}
                    ),
                )
            )
        action["data"]["result"]["original_ended"] = dict(
            actor=actor.model_dump(mode="json"), event=event
        )
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, canon, action)
        game.save_action(c, action)
