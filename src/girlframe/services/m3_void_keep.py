"""Real source-bound Mockingbird resistance and held-chat Void continuations."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_lobotomy import blocked_play
from girlframe.engine.m3_void_state import VoidThreshold
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _child(c: Connection, game: "GameService", threshold: str) -> dict[str, Any] | None:
    actions = t.m2["m2_actions"]
    identity = c.scalar(
        sa.select(actions.c.id)
        .where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.state.not_in(("complete", "aborted")),
            sa.func.json_extract(actions.c.body_json, "$.void_keep.threshold") == threshold,
        )
        .limit(1)
    )
    return game.action(c, identity) if identity else None


def _current(
    game: "GameService",
    c: Connection,
    state: GameState,
    meta: dict[str, Any],
    *,
    pending: bool = True,
) -> VoidThreshold:
    actor = ActorRef.model_validate_json(json.dumps(meta["actor"]))
    if game.character_binding(c, state, int(actor.entity), require_current_profile=False) != (
        actor.incarnation
    ):
        raise WorkflowError("This resistance belongs to its actual original Mockingbird.")
    value = rules.threshold(state, meta["threshold"])
    approval = game.store.policy.m3_approval
    if (
        value.actor != actor
        or value.frame_instance != meta["frame"]
        or (approval is None or approval.registry_sha256 != meta["registry"])
    ):
        raise WorkflowError("Recover the original Frame, threshold and resistance approval.")
    controller = meta.get("gm_controller") or (meta.get("handler") or {}).get("entity")
    if state.handler is None or str(controller) != str(state.handler):
        raise WorkflowError("Recover the actual Handler who joined this resistance.")
    from girlframe.services.m3_medical import MedicalService

    if MedicalService(game.store)._handler(c)[1] != meta["appointment"]:
        raise WorkflowError("Recover this resistance's actual original Handler appointment.")
    if meta["work"] not in value.source_works:
        raise WorkflowError("Recover this threshold's actual original resistance source.")
    if pending and value.stage != "resist_pending":
        raise WorkflowError("Resume the actual current Void stage instead of another resistance.")
    view = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    if pending and (
        view.frame_instance != value.frame_instance
        or view.inside_frame is not True
        or view.occupied_frame_instance != value.frame_instance
    ):
        raise WorkflowError("Recover this original Girl's actual corrupt-Frame occupancy.")
    return value


def prepare_keep(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    channel: int,
) -> tuple[dict[str, Any], GameState]:
    from girlframe.services.m3_void import prepare_threshold, source

    Access(game.store).authorize(c, viewer, "plays")
    if (
        prepared.play != "keep_your_head"
        or not prepared.source_work
        or prepared.target
        or prepared.target_actor
        or prepared.order_id
        or prepared.off_duty_id
        or prepared.witnessed
    ):
        raise WorkflowError("Use only the actual source's optional Keep Your Head resistance.")
    row, body, actor = source(game, c, prepared.source_work)
    if (
        row["state"] != "pending"
        or row["owner_id"] != str(viewer.user_id)
        or actor.entity != (str(viewer.user_id))
        or prepared.parent != body["source_action"]
    ):
        raise WorkflowError("The actual original player must use this source's exact resistance.")
    if blocked_play(state.sheets[actor.entity], "keep_your_head") is not None:
        raise WorkflowError(
            "Surgery removed this optional Keep Your Head roll; no ability is restored."
        )
    updated, value = prepare_threshold(c, game, prepared.source_work, state)
    if _child(c, game, value.id) is not None:
        raise WorkflowError("Resume the actual saved resistance Play; do not roll a second one.")
    approval = game.store.policy.m3_approval
    assert approval is not None and updated.handler is not None
    from girlframe.services.m3_medical import MedicalService

    handler_body = active_handler(updated)
    meta = dict(
        work=row["id"],
        work_revision=row["revision"],
        threshold=value.id,
        actor=actor.model_dump(mode="json"),
        frame=value.frame_instance,
        registry=approval.registry_sha256,
        parent=body["source_action"],
        handler=handler_body.model_dump(mode="json") if handler_body else None,
        gm_controller=updated.handler,
        appointment=MedicalService(game.store)._handler(c)[1],
        resolution_done=False,
    )
    _current(game, c, updated, meta)
    scene = game.scene(c, channel)
    if viewer.user_id not in scene["participants"] or updated.handler not in scene["participants"]:
        raise WorkflowError("The original Girl and actual Handler must join this bound scene.")
    if prepared.parent:
        parent = game.action(c, prepared.parent)
        if parent["channel_id"] != str(channel) or not any(
            x["kind"] in ("defeat_void_threshold", "dive_void_threshold")
            and x["actor_id"] == actor.entity
            and json.loads(x["body_json"]).get("work_id") == row["id"]
            for x in game.pending(c, parent["id"])
        ):
            raise WorkflowError("Use the actual held corruption source's resistance request.")
    return meta, updated


def authorize_keep(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["void_keep"]
    _current(game, c, state, meta)
    if meta.get("cast") is not None:
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_cast import CastService
        from girlframe.services.m3_missions import MissionService

        cast, _ = CastService(ActorService(MissionService(game.store)))._current(
            c, state, int(action["channel_id"])
        )
        original_cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
        if fingerprint(cast) != fingerprint(original_cast) and not _ended_handler_cast(
            state, original_cast, cast, int(meta.get("gm_controller") or meta["handler"]["entity"])
        ):
            raise WorkflowError(
                "SOURCE_TABLE_CHANGED: recover the actual original resistance table."
            )
    from girlframe.services.m3_void import source

    row, body, actor = source(game, c, meta["work"])
    if (
        row["state"] != "pending"
        or row["revision"] != meta["work_revision"]
        or (
            actor.model_dump(mode="json") != meta["actor"]
            or body["source_action"] != meta["parent"]
        )
    ):
        raise WorkflowError("Recover the exact pending source of this resistance.")
    if blocked_play(state.sheets[action["actor_id"]], "keep_your_head") is not None:
        raise WorkflowError("The actual original Girl no longer has this optional rolled ability.")


def _ended_handler_cast(
    state: GameState, original: SceneCast, current: SceneCast, controller: int
) -> bool:
    """Only the proved death's exact role removal may preserve its human GM rulings."""
    for archive in state.handler_archives:
        if archive.actor.entity != str(controller):
            continue
        for saved in json.loads(archive.links_json).get("casts", ()):
            previous = SceneCast.model_validate_json(json.dumps(saved))
            if fingerprint(previous) != fingerprint(original):
                continue
            retained = tuple(
                x
                for x in previous.roles
                if not (x.actor.kind == "handler" and x.actor.entity == str(controller))
            )
            if retained == previous.roles:
                continue
            predicted = previous.model_copy(
                update={"roles": retained, "revision": previous.revision + 1}
            )
            if fingerprint(predicted) == fingerprint(current):
                return True
    return False


def finish_keep(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    """Called only from the real owned Keep pipeline, before ordinary action completion."""
    meta = action["data"]["void_keep"]
    if meta.get("resolution_done"):
        return True
    if meta.get("resistance_resolved"):
        return False
    authorize_keep(game, c, state, action)
    if action["data"]["play"] != "keep_your_head" or not action["data"].get("receipt"):
        raise WorkflowError("Only the actual source-bound rolled Keep Your Head can resist.")
    handler = str(action["data"]["handler"])
    if state.handler != int(handler):
        raise WorkflowError("Recover the actual Handler before resolving this resistance.")
    choices = action["data"]["choices"]
    own = choices.get("actor_keep:" + action["actor_id"])
    ruling = choices.get("handler_keep:" + handler)
    if own is None or ruling is None or not action["data"].get("response_event"):
        raise WorkflowError("The original player and actual Handler must supply their own choices.")
    answer = ChoiceAnswer.model_validate_json(json.dumps(ruling))
    result = action["data"]["result"]
    if answer.flag is None or not answer.text.strip() or result.get("enough") != answer.flag:
        raise WorkflowError("Use the actual Handler's sufficient-result decision and explanation.")
    controlled = "in_control" in result.get("positive", ()) and "in_control" not in (
        result.get("negative", ())
    )
    updated = rules.resolve_mockingbird(
        state,
        meta["threshold"],
        action["data"]["response_event"],
        child_action=action["id"],
        in_control=controlled,
        handler_enough=answer.flag,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(updated, field))
    value = rules.threshold(state, meta["threshold"])
    meta["resistance_resolved"] = True
    meta["resolution_done"] = value.stage in rules.FINAL
    result["void_resolution"] = value.stage
    if value.stage in rules.FINAL:
        return True
    game.request(
        c,
        action,
        int(action["actor_id"]),
        "void_keep_threshold",
        dict(work_id=meta["work"], threshold=value.id, actor=meta["actor"]),
    )
    action["state"] = "awaiting_choices"
    return False


def synchronize_keep(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    meta = action["data"]["void_keep"]
    if not meta.get("resistance_resolved"):
        return
    state = load_state(c, game.store.campaign_id)
    value = rules.threshold(state, meta["threshold"])
    if value.stage in rules.FINAL:
        from girlframe.services.m3_void import complete

        complete(c, game, value, event, viewer, key)


def complete_keep_continuations(
    game: "GameService",
    c: Connection,
    value: VoidThreshold,
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    if value.stage not in rules.FINAL:
        return
    child = _child(c, game, value.id)
    if child is None:
        return
    meta = child["data"]["void_keep"]
    if meta["actor"] != value.actor.model_dump(mode="json") or not meta.get("resistance_resolved"):
        raise WorkflowError(
            "Recover the actual nested resistance before completing its Void source."
        )
    pending = game.pending(c, child["id"])
    owned = [
        x
        for x in pending
        if x["kind"] == "void_keep_threshold"
        and json.loads(x["body_json"]).get("threshold") == value.id
    ]
    if len(owned) != 1 or len(pending) != 1:
        raise WorkflowError("The actual failed resistance's owned continuation changed.")
    row = owned[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
        .values(
            state="completed_by_work",
            revision=row["revision"] + 1,
            body_json=json.dumps(
                json.loads(row["body_json"])
                | {"completed_event": event, "resolution": value.stage},
                sort_keys=True,
            ),
        )
    )
    meta["resolution_done"] = True
    child["data"]["result"]["void_resolution"] = value.stage
    from girlframe.services.m2_choices import ChoiceEngine

    ChoiceEngine(game).finish(c, load_state(c, game.store.campaign_id), child)
    game.save_action(c, child)


def start_view(game: "GameService", viewer: GuildViewer, identity: str) -> dict[str, Any]:
    from girlframe.services.m3_void import prepare_threshold, source

    with game.store.engine.connect() as c:
        Access(game.store).authorize(c, viewer, "plays")
        row, body, actor = source(game, c, identity)
        if row["owner_id"] != str(viewer.user_id) or row["state"] != "pending":
            raise WorkflowError("Only the original Girl resumes this actual Void resistance.")
        state, value = prepare_threshold(c, game, identity)
        child = _child(c, game, value.id)
        owned = (
            next(
                (x["id"] for x in game.pending(c, child["id"]) if x["actor_id"] == actor.entity),
                None,
            )
            if child
            else None
        )
        if body["source_action"]:
            channels = [int(game.action(c, body["source_action"])["channel_id"])]
        else:
            scenes = t.m2["m2_scenes"]
            channels = []
            for saved in c.execute(
                sa.select(scenes).where(scenes.c.campaign_id == game.store.campaign_id)
            ).mappings():
                people = json.loads(saved["participants_json"])
                if int(actor.entity) in people and state.handler in people:
                    try:
                        from girlframe.services.m3_actors import ActorService
                        from girlframe.services.m3_cast import CastService
                        from girlframe.services.m3_missions import MissionService

                        CastService(ActorService(MissionService(game.store)))._current(
                            c, state, int(saved["channel_id"])
                        )
                    except WorkflowError:
                        continue
                    channels.append(int(saved["channel_id"]))
        return dict(
            work=identity,
            parent=body["source_action"],
            stage=value.stage,
            child=child["id"] if child else None,
            choice=owned,
            channels=channels,
            heat=state.sheets[actor.entity].heat,
            sheet_revision=state.sheets[actor.entity].revision,
        )
