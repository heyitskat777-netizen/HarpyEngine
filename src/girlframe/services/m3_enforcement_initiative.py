"""Source-bound Enforcement Initiative: one actual roll and owned physical consequences."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_enforcer as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState, shift_status
from girlframe.engine.m3_actor_bonds import current_ref, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_handler_consequence_state import HandlerConsequence
from girlframe.engine.m3_handler_consequences import active_handler, body_original
from girlframe.engine.m3_harpy_defeat import controller
from girlframe.engine.m3_role_punishments import bond_ref, view
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_items import available_items, new_void_families, take_in_transaction
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import open_case, supported
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

LOW = ("escape", "item", "tag", "disapproval", "hesitate")


def _low_options(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> list[str]:
    return [
        x
        for x in LOW
        if (x != "disapproval" or actor.kind == "pilot")
        and (x != "item" or available_items(c, game, state, actor))
    ]


def _prove_harpy(c: Connection, game: "GameService", state: GameState, actor: ActorRef) -> None:
    if actor.kind not in ("pilot", "external_pilot"):
        raise WorkflowError("Initiative requires its actual original Pilot or Harpy source.")
    from girlframe.services.m3_enforcer_requisitions import owned

    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.services.m3_tag_permissions import prove_birth

        prove_birth(c, game, state, actor)
        native = getattr(harpy(state, actor), "original_frame", None) == "THE ENFORCER"
    else:
        native = state.sheets[actor.entity].frame == "THE ENFORCER"
    if not native and owned(c, game, state, actor, rules.INITIATIVE) is None:
        raise WorkflowError("Recover the original actually acquired or retained Initiative source.")


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def _refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["enforcement"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def _cast(game: "GameService", c: Connection, state: GameState, channel: int) -> SceneCast:
    return CastService(ActorService(MissionService(game.store)))._current(c, state, channel)[0]


def _judge(
    game: "GameService", c: Connection, state: GameState, cast: SceneCast
) -> tuple[ActorRef, int, str | None]:
    from girlframe.services.m3_battle import _scene_judge

    ref, controller, source = _scene_judge(game, c, state, cast)
    if ref is None:
        if any(x.active for x in state.director_contexts):
            raise WorkflowError(
                "SOURCE_JUDGE_REQUIRED: select the actual present Director's instruction role."
            )
        ref = active_handler(state)
        if ref is None:
            raise WorkflowError("The actual source Handler's instruction role is unavailable.")
    return ref, controller, source


def instruction_authority(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorRef, int]:
    meta = action["data"]["enforcement"]
    actual = ActorRef.model_validate(meta["handler"])
    if actual.kind == "npc":
        selected, controller, source = _judge(
            game, c, state, _cast(game, c, state, int(action["channel_id"]))
        )
        if (
            selected != actual
            or controller != meta["handler_controller"]
            or source != meta.get("judge_source")
        ):
            raise WorkflowError("Recover the original selected Director's instruction source.")
    elif active_handler(state) != actual:
        raise WorkflowError("Recover the original fictional Handler's instruction source.")
    return actual, int(meta["handler_controller"])


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    access = Access(game.store)
    # Existing actual table responses are not a new Handler Play. The same human
    # retains its frozen Tag/target/administrative choices during Director presence.
    source_response = bool(
        action is not None and viewer.user_id in action["data"]["enforcement"].get("table", ())
    )
    access.authorize(c, viewer, "plays", director_response=source_response)
    assert access.registry is not None
    access.registry.require_available(rules.INITIATIVE)
    if action is None:
        return
    meta = action["data"]["enforcement"]
    approval = game.store.policy.m3_approval
    if approval is None or approval.registry_sha256 != meta["registry"]:
        raise WorkflowError("Recover this actual Play's original release approval.")
    handler, appointment = MedicalService(game.store)._handler(c)
    if (
        handler != meta.get("procedural_gm", meta["handler_controller"])
        or appointment != meta["appointment"]
    ):
        raise WorkflowError(
            "Recover the original appointed Handler's actual instruction authority."
        )
    state = load_state(c, game.store.campaign_id)
    if fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]:
        raise WorkflowError("SOURCE_TABLE_CHANGED: recover this actual original cast.")
    instruction_authority(game, c, state, action)
    actor, target = _refs(action)
    _prove_harpy(c, game, state, actor)
    bound = profiles(c, game.store.campaign_id)
    if not rules.initiative(state, actor):
        raise WorkflowError("Recover the original Enforcer and its actually owned ability.")
    view(state, actor, bound)
    # An actual Handler replacement choice may end its original body. The exact callback
    # closes that outcome without silently transferring the grip/Punishment to a new persona.
    if target.kind != "handler" or not meta.get("target_ended"):
        view(state, target, bound)


def _contact(
    state: GameState, actor: ActorRef, target: ActorRef, bound: Any, piloting: bool
) -> dict[str, Any]:
    own, other = view(state, actor, bound), view(state, target, bound)
    if own.piloting is not None and own.piloting != piloting:
        raise WorkflowError("Use the original Girl's actual linked/unlinked Frame context.")
    acting_cell = own.frame_cell if piloting else own.cell
    if acting_cell is not None and other.cell is not None and acting_cell != other.cell:
        raise WorkflowError(
            "Actual known positions contradict taking hold; establish real contact first."
        )
    return dict(
        actor_cell=list(acting_cell) if acting_cell is not None else None,
        target_cell=list(other.cell) if other.cell is not None else None,
        piloting=piloting,
    )


def _known_target(state: GameState, actor: ActorRef, target: ActorRef, controller: int) -> bool:
    from girlframe.engine.m3_harpy_defeat import controller as actual_controller

    if target.kind in ("pilot", "handler") or controller == actual_controller(state, actor):
        return True
    if target.kind == "external_pilot" and any(
        x.id == target.entity and x.revealed for x in state.harpy_states
    ):
        return True
    if state.world is None:
        return False
    collection = {
        "npc": state.world.npcs,
        "gorgon": state.world.gorgons,
        "external_pilot": state.world.pilots,
    }[target.kind]
    if any(x.id == target.entity and bool(getattr(x, "revealed", False)) for x in collection):
        return True
    original = actor
    if actor.kind == "external_pilot" and any(x.id == actor.entity for x in state.harpy_states):
        from girlframe.engine.m3_tag_permissions import conversion

        original = conversion(state, actor)[0].origin
    return target.kind == "npc" and any(
        original.kind == "pilot"
        and x.owner == int(original.entity)
        and x.character_id == original.incarnation
        and x.npc == target.entity
        for x in state.world.starting_npc_links
    )


def preview(
    game: "GameService", viewer: GuildViewer, channel: int, *, actor_ref: ActorRef | None = None
) -> dict[str, Any]:
    try:
        with game.store.engine.connect() as c:
            authorize(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = actor_ref or current_ref(state, viewer.user_id)
            _prove_harpy(c, game, state, actor)
            bound = profiles(c, game.store.campaign_id)
            if not rules.initiative(state, actor):
                return dict(available=False, targets=[])
            cast = _cast(game, c, state, channel)
            _judge(game, c, state, cast)
            if actor not in {bond_ref(state, x.actor) for x in cast.roles}:
                return dict(available=False, targets=[])
            targets = []
            for role in cast.roles:
                target = bond_ref(state, role.actor)
                if (
                    target == actor
                    or not _known_target(state, actor, target, role.controller)
                    or not supported(state, target, actor, bound)
                ):
                    continue
                if any(x.held and x.target == target for x in state.enforcer_grasps):
                    continue
                actual = view(state, target, bound)
                targets.append(
                    dict(ref=target.model_dump(mode="json"), token=target.token, label=actual.label)
                )
            actual = view(state, actor, bound)
            if actual.controller != viewer.user_id:
                return dict(available=False, targets=[])
            return dict(
                available=bool(targets),
                targets=targets,
                actor=actor.model_dump(mode="json"),
                sheet_revision=state.sheets[actor.entity].revision
                if actor.kind == "pilot"
                else state.revision,
                identities=[x.model_dump(mode="json") for x in actual.identities],
                heat=actual.heat,
                piloting=view(state, actor, bound).piloting,
            )
    except (ValueError, WorkflowError):
        return dict(available=False, targets=[])


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
    actor_ref: ActorRef | None = None,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.target is not None
        or prepared.off_duty_id
        or prepared.order_id
        or prepared.source_work
    ):
        raise WorkflowError("Choose the actual typed person in this on-screen taking-hold scene.")
    actor = actor_ref or current_ref(state, viewer.user_id)
    _prove_harpy(c, game, state, actor)
    target = prepared.target_actor
    bound = profiles(c, game.store.campaign_id)
    if (
        target is None
        or not rules.initiative(state, actor)
        or not supported(state, target, actor, bound)
    ):
        raise WorkflowError(
            "Select an actual source-supported target with a legal mandatory Punishment."
        )
    # A Director-presence reference names the same proved current physical Handler.
    # Freeze that body identity, as the cast and later resource consumers do.
    target = bond_ref(state, target)
    cast = _cast(game, c, state, channel)
    actual_roles = {bond_ref(state, x.actor): x.controller for x in cast.roles}
    if actor not in actual_roles or target not in actual_roles:
        raise WorkflowError(
            "Cast the actual participants before taking hold; casting alone is not contact."
        )
    if any(x.held and x.target == target for x in state.enforcer_grasps):
        raise WorkflowError("Resolve this actual original person's existing grasp first.")
    own, other = view(state, actor, bound), view(state, target, bound)
    if not _known_target(state, actor, target, other.controller):
        raise WorkflowError("Choose an actually known visible cast target, not a hidden reference.")
    if own.controller != viewer.user_id or actual_roles[target] != other.controller:
        raise WorkflowError("Recover the actual original cast controllers.")
    contact = _contact(state, actor, target, bound, prepared.piloting)
    handler, appointment = MedicalService(game.store)._handler(c)
    handler_ref, instruction_controller, judge_source = _judge(game, c, state, cast)
    main_handler = active_handler(state)
    assert game.store.policy.m3_approval is not None
    table = {x.controller for x in cast.roles}
    if cast.facilitator is not None:
        table.add(cast.facilitator)
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        target_controller=other.controller,
        actor_controller=own.controller,
        handler=handler_ref.model_dump(mode="json"),
        marker_handler=main_handler.model_dump(mode="json") if main_handler is not None else None,
        handler_controller=instruction_controller,
        procedural_gm=handler,
        judge_source=judge_source,
        appointment=appointment,
        registry=game.store.policy.m3_approval.registry_sha256,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(table),
        contact=contact,
        selected=[],
        done=[],
        started=False,
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    authorize(game, c, viewer, action)
    actor, target = _refs(action)
    meta = action["data"]["enforcement"]
    if (
        _contact(
            state, actor, target, profiles(c, game.store.campaign_id), meta["contact"]["piloting"]
        )
        != meta["contact"]
    ):
        raise WorkflowError(
            "Physical contact facts changed; recover this unrolled Play before spending Heat."
        )
    if not supported(state, target, actor, profiles(c, game.store.campaign_id)):
        raise WorkflowError("The actual target no longer has a legal mandatory Punishment.")


def _event(action: dict[str, Any]) -> str:
    return str(action["data"].get("response_event") or action["data"]["enforcement"]["roll_event"])


def _request(
    game: "GameService", c: Connection, action: dict[str, Any], owner: int, kind: str, **body: Any
) -> None:
    game.request(c, action, owner, "enforcer_" + kind, body)


def _next(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["enforcement"]
    if game.pending(c, action["id"]):
        return
    actor, target = _refs(action)
    if meta.get("target_ended"):
        action["data"]["result"]["original_target_ended"] = True
        _finish(game, c, state, action)
        return
    level = action["data"]["result"]["tier"]
    if level == "high" and not meta.get("punishment_completed"):
        if not meta.get("punishment"):
            identity = str(uuid4())
            changed, _ = open_case(
                state,
                profiles(c, game.store.campaign_id),
                actor=actor,
                target=target,
                chooser=ActorRef.model_validate(meta["handler"]),
                source_kind="enforcement_initiative",
                action=action["id"],
                source_event=_event(action),
                identity=identity,
            )
            _copy(state, changed)
            meta["punishment"] = identity
        _request(
            game, c, action, meta["handler_controller"], "punishment", case_id=meta["punishment"]
        )
        return
    if level == "low":
        if not meta["selected"]:
            _request(
                game, c, action, meta.get("actor_controller", int(action["actor_id"])), "select"
            )
            return
        remaining = [x for x in meta["selected"] if x not in meta["done"]]
        if remaining:
            option = remaining[0]
            _request(
                game,
                c,
                action,
                meta["handler_controller"]
                if option == "disapproval"
                else meta["target_controller"],
                option,
            )
            return
    _finish(game, c, state, action)


def _finish(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    else:
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).finish(c, state, action)


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["enforcement"]
    if meta["started"]:
        raise WorkflowError("This actual Initiative result already began its consequences.")
    actor, target = _refs(action)
    meta["started"] = True
    if action["data"]["result"]["tier"] in ("mid", "high"):
        _copy(
            state,
            rules.grasp(
                state,
                actor,
                target,
                profiles(c, game.store.campaign_id),
                action["id"],
                _event(action),
                piloting=meta["contact"]["piloting"],
            ),
        )
        meta["grasp"] = _event(action)
        if view(state, target, profiles(c, game.store.campaign_id)).rules == "director":
            from girlframe.services.m3_battle import require_director_helpless

            changed, work = require_director_helpless(
                game,
                c,
                state,
                target=target,
                opponent=actor,
                source_action=action["id"],
                event=_event(action),
            )
            _copy(state, changed)
            if len(work) != 1:
                raise WorkflowError("Keep the exact original Director Helpless consequence.")
            meta["director_consequence"] = work[0]
            return
        if (
            target.kind == "handler"
            and view(state, target, profiles(c, game.store.campaign_id)).rules != "handler_girl"
        ):
            from girlframe.services.m3_handler_consequences import require

            changed, identity = require(
                game,
                c,
                state,
                target,
                trigger="helpless",
                source_action=action["id"],
                source_event=_event(action),
                opponent=actor,
                choice_kind="enforcer_handler_consequence",
            )
            _copy(state, changed)
            meta["handler_consequence"] = identity
    _next(game, c, state, action)


def projection(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    meta = action["data"]["enforcement"]
    actor, target = _refs(action)
    kind = request["kind"]
    body = json.loads(request["body_json"])
    data = dict(actor=meta["actor"], target=meta["target"], kind=kind)
    if kind == "enforcer_select":
        data["options"] = _low_options(game, c, state, actor)
    if kind in ("enforcer_item", "enforcer_hesitate"):
        data["items"] = available_items(
            c,
            game,
            state,
            actor if kind == "enforcer_item" else target,
            weapons_only=kind == "enforcer_hesitate",
        )
    if kind == "enforcer_item_context":
        data["item"] = body["item"]
    if kind == "enforcer_receive":
        data["item"] = body["item"]
        data["replacements"] = [
            dict(id=x.id, label=x.name)
            for x in (state.sheets[target.entity].assets if target.kind == "pilot" else [])
            if x.family == "girl"
        ]
    if kind == "enforcer_punishment":
        data["case_id"] = body["case_id"]
    if kind == "enforcer_handler_consequence":
        data["consequence"] = body["consequence"]
    if kind == "enforcer_director_consequence":
        data["work_id"] = body["work_id"]
    if kind == "enforcer_void_threshold":
        data["work_id"] = body["work_id"]
    return data


def _take(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    selection: str,
    account: str,
    replace: str | None,
    inside: bool | None,
) -> None:
    actor, target = _refs(action)
    changed = take_in_transaction(
        c,
        game,
        state,
        source=actor,
        recipient=target,
        selection=selection,
        action=action["id"],
        event=_event(action),
        account=account,
        replace=replace,
        inside_frame=inside,
    )
    thresholds = new_void_families(state, changed)
    _copy(state, changed)
    meta = action["data"]["enforcement"]
    transfer = state.item_transfers[-1]
    for owner in thresholds:
        identity = str(uuid4())
        meta.setdefault("item_void", []).append(
            dict(
                id=identity,
                owner=owner.model_dump(mode="json"),
                transfer=transfer.id,
                event=transfer.event,
            )
        )
        _request(game, c, action, int(owner.entity), "void_threshold", work_id=identity)


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["enforcement"]
    actor, target = _refs(action)
    kind = request["kind"].removeprefix("enforcer_")
    body = json.loads(request["body_json"])
    if kind in ("punishment", "handler_consequence", "void_threshold"):
        raise WorkflowError(
            "Complete the actual owned consequence; an acknowledgment cannot fulfill it."
        )
    if kind == "select":
        choices = _low_options(game, c, state, actor)
        if len(answer.options) != 2 or not set(answer.options) <= set(choices):
            raise WorkflowError("Choose exactly two distinct printed applicable low outcomes.")
        meta["selected"] = list(answer.options)
    elif kind == "item":
        selection = answer.fields.get("item", "")
        if (
            selection not in {x["id"] for x in available_items(c, game, state, actor)}
            or not answer.text.strip()
        ):
            raise WorkflowError(
                "The original target chooses one actual held object and describes its taking."
            )
        inside = view(state, actor, profiles(c, game.store.campaign_id)).inside_frame
        from girlframe.engine.m3_harpy_resources import assets as harpy_assets

        actual_assets = (
            state.sheets[actor.entity].assets
            if actor.kind == "pilot"
            else harpy_assets(state, actor)
        )
        chosen_item = next((x for x in state.held_items if x.id == selection), None)
        excluded = (
            selection.removeprefix("asset:")
            if selection.startswith("asset:")
            else chosen_item.asset_id
            if chosen_item
            else None
        )
        remaining = [
            x for x in actual_assets if x.family == "girl" and not x.damaged and excluded != x.id
        ]
        if inside is None and not remaining:
            _request(
                game,
                c,
                action,
                controller(state, actor),
                "item_context",
                item=selection,
                account=answer.text,
            )
        else:
            _request(
                game,
                c,
                action,
                meta["target_controller"],
                "receive",
                item=selection,
                account=answer.text,
                inside_frame=inside,
            )
        return
    elif kind == "item_context":
        raw = answer.fields.get("inside_frame")
        if raw not in ("yes", "no") or not answer.text.strip():
            raise WorkflowError(
                "The original Enforcer records actual physical inside/outside Frame facts."
            )
        _request(
            game,
            c,
            action,
            meta["target_controller"],
            "receive",
            item=body["item"],
            account=body["account"],
            inside_frame=raw == "yes",
        )
        meta["item_inside_account"] = dict(account=answer.text, event=_event(action))
        return
    elif kind == "receive":
        _take(
            game,
            c,
            state,
            action,
            body["item"],
            body["account"],
            answer.fields.get("replace") or None,
            body.get("inside_frame"),
        )
        meta["done"].append("item")
    elif kind in ("escape", "disapproval", "tag", "hesitate"):
        if not answer.text.strip():
            raise WorkflowError(
                "Record the actual printed response; do not acknowledge it generically."
            )
        if kind == "escape":
            state.facts.append(
                dict(
                    kind="enforcer_low_escape",
                    action=action["id"],
                    actor=target.model_dump_json(),
                    holder=actor.model_dump_json(),
                    source_event=_event(action),
                    account=answer.text,
                    effect=(
                        "The actual target slipped free of this attempted grip; "
                        "positions unchanged."
                    ),
                )
            )
        elif kind == "tag":
            actual = view(state, target, profiles(c, game.store.campaign_id))
            if actor.kind == "external_pilot":
                from girlframe.engine.m3_harpy_defeat import give_tag

                _copy(
                    state,
                    give_tag(
                        state,
                        actor,
                        target,
                        answer.text.strip(),
                        _event(action),
                        str(uuid4()),
                        tuple(meta["table"]),
                    ),
                )
            else:
                state.sheets[actor.entity].tags.append(
                    TagState(
                        id=str(uuid4()),
                        label=answer.text.strip(),
                        giver=actual.controller,
                        giver_actor=target,
                        observers=tuple(meta["table"]),
                    )
                )
        elif kind == "disapproval":
            shift_status(state, int(actor.entity), -1)
        elif kind == "hesitate" and answer.flag is None:
            raise WorkflowError(
                "The actual target explicitly chooses whether to use a weapon on hand."
            )
        elif kind == "hesitate" and answer.flag:
            weapon = answer.fields.get("weapon")
            if weapon not in {
                x["id"] for x in available_items(c, game, state, target, weapons_only=True)
            }:
                raise WorkflowError(
                    "Use an actual proved weapon on hand; no weapon or harm is invented."
                )
            _copy(state, make_helpless(state, actor, target, _event(action)))
        meta.setdefault("responses", []).append(
            dict(
                option=kind,
                owner=int(request["actor_id"]),
                response=answer.text,
                weapon=answer.fields.get("weapon"),
                accepted=answer.flag,
                event=_event(action),
            )
        )
        meta["done"].append(kind)
    else:
        raise WorkflowError("Use this actual source Initiative decision.")
    _next(game, c, state, action)


def _battle_finished(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    if action["state"] != "complete" or not action["data"].get("battle_counter_source"):
        return
    audit = c.execute(
        sa.select(t.events.c.command_key).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if audit is None:
        raise WorkflowError("Recover the actual completed counter's effect audit source.")
    from girlframe.services.m3_battle import complete_counter_play

    complete_counter_play(game, c, action, event, None, str(audit.command_key))


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    if action["data"]["enforcement"].get("director_consequence"):
        from girlframe.services.m3_battle import synchronize_damage

        synchronize_damage(game, c, event)
    from girlframe.services.m3_role_punishments import synchronize as sync_role

    sync_role(game, c, action, event)
    from girlframe.services.m3_work import related

    for threshold in action["data"]["enforcement"].get("item_void", []):
        table = t.m3["m3_required_work"]
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == threshold["id"])
            .limit(1)
        ):
            continue
        owner = ActorRef.model_validate(threshold["owner"])
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            threshold["id"],
            int(owner.entity),
            int(owner.entity),
            "void_threshold",
            dict(
                reason="item_transfer",
                owner=threshold["owner"],
                character=owner.incarnation,
                source_action=action["id"],
                source_pdf=19,
                immediate=True,
                transfer=threshold["transfer"],
                details=dict(family="girl"),
            ),
            threshold["event"],
        )
        from girlframe.services.m3_void import _append, prepare_threshold

        updated, value = prepare_threshold(c, game, threshold["id"])
        actual_actor = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if actual_actor is None:
            raise WorkflowError("Recover the actual item-removal source audit.")
        opened = game.event(
            c,
            actual_actor,
            str(uuid4()),
            "m3.item_void_threshold_opened",
            updated,
            source_event=event,
            work_id=threshold["id"],
        )
        if value.stage == "prevented":
            # Mockingbird's printed exception is an actual automatic consequence. No
            # human response/Keep roll is forged when the corrupt-Frame trigger is absent.
            row = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == game.store.campaign_id, table.c.id == threshold["id"]
                    )
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .one()
            )
            _append(
                c,
                dict(row),
                opened,
                json.loads(row["body_json"])
                | dict(threshold=value.id, resolution=value.stage, actual_actor=None),
                resolved=True,
            )
            game.save_action(c, action)
            complete_item_void(game, c, threshold["id"], opened)
            action.update(game.action(c, action["id"]))
    game.save_action(c, action)
    _battle_finished(game, c, action, event)


def complete_director_consequence(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    meta = action["data"].get("enforcement") or {}
    body = json.loads(row["body_json"])
    _, target = _refs(action)
    if (
        row["id"] != meta.get("director_consequence")
        or row["kind"] != "director_helpless"
        or row["state"] != "resolved"
        or body.get("effect_event") != event
        or body.get("source_action") != action["id"]
        or body.get("requirement", {}).get("target") != target.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the actual original Director Helpless response and source.")
    state = load_state(c, game.store.campaign_id)
    from girlframe.services.m3_battle_director import DirectorService

    actual, _ = DirectorService(game.store)._source(c, row)
    if actual != target:
        raise WorkflowError("Do not transfer this original Director consequence to another body.")
    if body.get("choice") == "death":
        if not any(
            x.get("kind") == "director_body_ended"
            and x.get("event") == event
            and x.get("actor") == target.model_dump_json()
            for x in state.facts
        ):
            raise WorkflowError("Recover this actual Director body's source death proof.")
        meta["target_ended"] = True
        meta["unperformed_punishment_reason"] = "original_director_ended_by_printed_replacement"
    meta["director_consequence_completed"] = event
    next_event = str(uuid4())
    action["data"]["response_event"] = next_event
    _next(game, c, state, action)
    human = (
        viewer.user_id
        if viewer is not None
        else c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
    )
    if human is None:
        raise WorkflowError("Recover the genuine Director response's command principal.")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        human,
        key,
        "m3.enforcement_director_continued",
        state,
        event_id=next_event,
        event_index=index + 1 if index is not None else 0,
        action_id=action["id"],
        source_event=event,
        work_id=row["id"],
    )
    synchronize(game, c, action, next_event)


def complete_handler_consequence(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    record: HandlerConsequence,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    meta = action["data"].get("enforcement")
    if (
        not meta
        or record.id != meta.get("handler_consequence")
        or record.state not in ("resolved", "ended")
        or record.effect_event != event
    ):
        raise WorkflowError("Recover the exact actual source Handler consequence continuation.")
    state = load_state(c, game.store.campaign_id)
    ended = record.choice == "death"
    if record.state == "ended":
        archive = next(
            (
                x
                for x in state.handler_archives
                if x.body == body_original(state, record.actor)
                and x.source_event == event
                and x.consequence == record.ended_by
            ),
            None,
        )
        if archive is None:
            raise WorkflowError("Recover the actual forced-ending archive and source consequence.")
        ended = True
    if ended:
        meta["target_ended"] = True
        meta["unperformed_punishment_reason"] = (
            "original_target_body_ended_by_printed_handler_replacement"
        )
    new_event = str(uuid4())
    action["data"]["response_event"] = new_event
    _next(game, c, state, action)
    audit_actor = (
        viewer.user_id
        if viewer is not None
        else c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
    )
    if audit_actor is None:
        raise WorkflowError("Recover the actual source ending audit actor.")
    game.event(
        c,
        audit_actor,
        str(uuid4()),
        "m3.enforcement_handler_continued",
        state,
        event_id=new_event,
        action_id=action["id"],
        source_event=event,
    )
    synchronize(game, c, action, new_event)


def continue_punishment(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("enforcement")
    if not meta or not meta.get("punishment") or action["state"] == "complete":
        return
    state = load_state(c, game.store.campaign_id)
    case = next((x for x in state.role_punishments if x.id == meta["punishment"]), None)
    if case is None or case.completion_event is None:
        return
    requests = [
        x
        for x in game.pending(c, action["id"])
        if x["kind"] == "enforcer_punishment"
        and json.loads(x["body_json"]).get("case_id") == case.id
    ]
    if len(requests) != 1:
        raise WorkflowError("Recover the exact actual source Punishment continuation.")
    request = requests[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == request["id"],
            choices.c.state == "pending",
        )
        .values(
            state="answered",
            revision=request["revision"] + 1,
            body_json=json.dumps(
                json.loads(request["body_json"])
                | dict(
                    completed_by_work=case.id,
                    actual_effect_event=case.effect_event,
                    completion_source=event,
                )
            ),
        )
    )
    meta["punishment_completed"] = True
    _next(game, c, state, action)
    game.save_action(c, action)
    _battle_finished(game, c, action, event)


def complete_item_void(game: "GameService", c: Connection, identity: str, event: str) -> None:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["state"] != "resolved":
        raise WorkflowError("Complete the actual original item-removal Void outcome first.")
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    meta = action["data"].get("enforcement")
    if meta is None or identity not in {x["id"] for x in meta.get("item_void", [])}:
        raise WorkflowError("Recover the exact item-removal source continuation.")
    requests = [
        x
        for x in game.pending(c, action["id"])
        if x["kind"] == "enforcer_void_threshold"
        and json.loads(x["body_json"]).get("work_id") == identity
    ]
    if len(requests) != 1:
        raise WorkflowError("Recover the exact owned item-removal Void continuation.")
    request = requests[0]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == request["id"])
        .values(
            state="answered",
            revision=request["revision"] + 1,
            body_json=json.dumps(
                json.loads(request["body_json"]) | dict(actual_outcome_event=event)
            ),
        )
    )
    state = load_state(c, game.store.campaign_id)
    actor, target = _refs(action)
    if any(x.actor in (actor, target) and x.source_event == event for x in state.career_archives):
        meta["target_ended"] = True
        meta["unperformed_remaining_outcomes"] = [
            x for x in meta["selected"] if x not in meta["done"]
        ]
        for pending in game.pending(c, action["id"]):
            if pending["kind"].startswith("enforcer_"):
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.id == pending["id"],
                    )
                    .values(
                        state="ended_with_original",
                        revision=pending["revision"] + 1,
                        body_json=json.dumps(
                            json.loads(pending["body_json"]) | dict(original_body_ended=event)
                        ),
                    )
                )
    _next(game, c, state, action)
    game.save_action(c, action)
    _battle_finished(game, c, action, event)
