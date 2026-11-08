"""Actual unrolled Ankou commitment, source-owned choices and one real reprisal."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import (
    AssetState,
    ChoiceAnswer,
    GameState,
    IdentityState,
    PlayInput,
    mark_identity,
    spend_heat,
)
from girlframe.engine.m3_actor_bonds import (
    current_ref,
    depth,
    is_helpless,
    make_helpless,
    set_depth,
)
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_identity_slots import replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_unlocked
from girlframe.engine.m3_nightmare import current
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_disposable_psyche import _before
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "ankou_feedback_choice",
    "ankou_feedback_purpose",
    "ankou_feedback_identity",
    "ankou_feedback_child",
)


def _copy(state: GameState, updated: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(updated, key))


def _gate(game: GameService) -> None:
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("M3_REVIEW_PENDING: the actual Feedback source must be available")
    registry.require_available(rules.RULE)


def _event(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual canonical Feedback event")
    return dict(row)


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Feedback:
    value = rules.get(state, identity)
    before = _before(game, c, value.mark_event)
    born = _history(c, game, value.mark_event)
    original = rules.get(born, identity)
    audit = _event(game, c, value.mark_event)
    action = game.action(c, value.action)
    immutable = (
        "id",
        "action",
        "actor",
        "frame",
        "cast",
        "registry",
        "mark_event",
        "prepared",
        "identity",
        "heat_before",
        "heat_committed",
        "committed_revision",
    )
    sheet = before.sheets.get(value.actor.entity)
    if (
        any(getattr(value, key) != getattr(original, key) for key in immutable)
        or audit["kind"] != "m3.ankou_feedback_committed"
        or audit["actor_id"] != value.actor.entity
        or json.loads(audit["payload_json"]).get("action_id") != value.action
        or sheet is None
        or sheet.character_id != value.actor.incarnation
        or sheet.frame != "PROJECT ANKOU"
        or (
            sheet.frame_runtime.id
            if sheet.frame_runtime
            else "initial:" + str(value.actor.incarnation)
        )
        != value.frame
        or not rules.final_mark(before, sheet, value.prepared.identity)
        or value.prepared != PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
        or action["actor_id"] != value.actor.entity
        or action["data"].get("ankou_feedback") != value.id
        or value.identity != next(x for x in sheet.identities if x.id == value.prepared.identity)
        or not any(x.actor != value.actor for x in value.cast.roles)
    ):
        raise WorkflowError("Preserve the actual last mark, original Frame and initiating Play")
    expected = GameState.model_validate_json(before.model_dump_json())
    changed = expected.sheets[value.actor.entity]
    mark_identity(
        changed,
        value.identity.id,
        value.prepared.gain,
        value.prepared.pair_share,
        state=expected,
        disposable_heat=value.prepared.disposable_heat,
    )
    spend_heat(changed, value.prepared.heat)
    actual = born.sheets[value.actor.entity]
    if (
        changed.identities != actual.identities
        or changed.heat != actual.heat
        or actual.heat != value.heat_committed
        or sheet.heat != value.heat_before
        or actual.revision != value.committed_revision
    ):
        raise WorkflowError("Recover the genuine mark/removal and exact single Heat commitment")
    for event, fields, author in (
        (
            value.choice_event,
            ("choice", "target", "target_controller", "lost_asset", "request"),
            value.actor.entity,
        ),
        (value.purpose_event, ("purpose", "purpose_given"), str(value.target_controller)),
        (
            value.resolved_event,
            ("phase", "resume_revision", "new_identity", "archive", "prevention"),
            None,
        ),
    ):
        if event:
            staged = rules.get(_history(c, game, event), identity)
            record = _event(game, c, event)
            if (
                record["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
                or author is not None
                and record["actor_id"] != author
                or any(getattr(value, key) != getattr(staged, key) for key in fields)
            ):
                raise WorkflowError(
                    "Keep every genuine Feedback choice and its actual human author"
                )
    if value.child:
        child = game.action(c, value.child)
        if (
            child["parent_id"] != value.action
            or child["actor_id"] != value.actor.entity
            or child["data"].get("ankou_feedback_child", {}).get("source") != value.id
            or child["data"]["prepared"]["target"]
            != int(value.target.entity if value.target else 0)
        ):
            raise WorkflowError("Retain the real source-bound reprisal against the selected person")
    if value.rolled_event:
        record = _event(game, c, value.rolled_event)
        body = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == value.action,
            )
        )
        if (
            record["kind"] not in ("m2.rolled", "m3.rolled")
            or record["actor_id"] != value.actor.entity
            or json.loads(record["payload_json"]).get("receipt_id") != value.receipt
            or body is None
            or json.loads(body) != action["data"].get("receipt")
            or json.loads(body)["id"] != value.receipt
        ):
            raise WorkflowError(
                "Bind only the actual later roll; never fabricate pre-Feedback dice"
            )
    return value


def hold_before_roll(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    key: str,
) -> dict[str, Any] | None:
    if action["data"].get("ankou_feedback"):
        raise WorkflowError("Resume the actual saved Feedback source instead of remarking")
    sheet = state.sheets[str(action["actor_id"])]
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if not rules.final_mark(state, sheet, prepared.identity):
        return None
    cast = _cast(game, c, state, int(action["channel_id"]))
    actor = current_ref(state, sheet.owner)
    if not any(x.actor != actor for x in cast.roles):
        return None
    Access(game.store).authorize(c, viewer, "plays")
    _gate(game)
    if not any(x.actor != actor and x.actor.kind == "pilot" for x in cast.roles):
        raise WorkflowError(
            "SOURCE_ANKOU_PERSON_REQUIRED: this scene needs its actual counterpart adapter"
        )
    if (
        viewer.user_id != sheet.owner
        or action.get("parent_id") is not None
        or prepared.play not in ("keep_your_head", "check_sensors", "flirt")
        or any(
            action["data"].get(x)
            for x in (
                "actor_basic",
                "m3",
                "janus",
                "princess_child",
                "nightmare_core",
                "dampener",
                "disobey",
                "battle",
                "engage",
                "beneath",
                "doctor",
                "enforcement",
            )
        )
        or prepared.pair_share
        or prepared.disposable_heat
        and sheet.girl != "STIM-BLISSED"
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_MARK_PORT_REQUIRED: preserve this specialised marking source"
        )
    _, frame = current(state, actor)
    original = GameState.model_validate_json(state.model_dump_json())
    entry = next(x for x in sheet.identities if x.id == prepared.identity)
    event = str(uuid4())
    heat_before = sheet.heat
    from girlframe.services.m3_disposable_psyche import prepare_disposal, record_committed_disposal

    prepare_disposal(game, c, state, sheet.owner, prepared)
    mark_identity(
        sheet, entry.id, prepared.gain, state=state, disposable_heat=prepared.disposable_heat
    )
    spend_heat(sheet, prepared.heat)
    sheet.revision += 1
    assert game.store.policy.m3_approval is not None
    value = rules.Feedback(
        id=action["id"] + ":feedback",
        action=action["id"],
        actor=actor,
        frame=frame,
        cast=cast,
        registry=game.store.policy.m3_approval.registry_sha256,
        mark_event=event,
        prepared=prepared,
        identity=entry.model_copy(deep=True, update={"marked": False}),
        heat_before=heat_before,
        heat_committed=sheet.heat,
        committed_revision=sheet.revision,
    )
    rules.put(state, value)
    action["data"]["ankou_feedback"] = value.id
    record_committed_disposal(game, c, state, action, original, event)
    game.request(c, action, sheet.owner, "ankou_feedback_choice", dict(source=value.id))
    game.save_action(c, action, state="awaiting_choices")
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.ankou_feedback_committed",
        state,
        event_id=event,
        action_id=action["id"],
        source=value.id,
    )
    return dict(action_id=action["id"], receipt=None, ankou_feedback=value.id)


def resume_inputs(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.CommittedInputs | None:
    identity = action["data"].get("ankou_feedback")
    if not identity:
        return None
    value = prove(game, c, state, identity)
    sheet, frame = current(state, value.actor)
    if (
        value.phase != "resolved"
        or value.resume_revision != sheet.revision
        or frame != value.frame
        or is_helpless(state, value.actor)
        or game.pending(c, action["id"])
        or value.rolled_event
    ):
        raise WorkflowError(
            "Resolve the actual Feedback and recover its exact current unrolled source"
        )
    assert value.resume_revision is not None
    return rules.CommittedInputs(
        source=value.id,
        commit_event=value.mark_event,
        actor=value.actor,
        prepared=value.prepared,
        resume_revision=value.resume_revision,
        heat_committed=value.heat_committed,
    )


def record_roll(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
    receipt: dict[str, Any],
) -> None:
    identity = action["data"].get("ankou_feedback")
    if identity:
        value = prove(game, c, state, identity)
        if (
            value.rolled_event
            or value.phase != "resolved"
            or action["data"].get("receipt") != receipt
        ):
            raise WorkflowError("Record this single genuine post-Feedback receipt only once")
        rules.put(state, value.model_copy(update=dict(rolled_event=event, receipt=receipt["id"])))


def _ready(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: rules.Feedback,
    event: str,
) -> None:
    revision = state.sheets[value.actor.entity].revision
    rules.put(
        state,
        value.model_copy(
            update=dict(phase="resolved", resolved_event=event, resume_revision=revision)
        ),
    )
    action["data"]["sheet_revision"] = revision
    game.save_action(c, action, state="ready_to_roll")


def _blocked(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: rules.Feedback,
    event: str,
    reason: str,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    rules.put(state, value.model_copy(update=dict(phase="ended", resolved_event=event)))
    action["data"]["result"] = dict(blocked_before_roll=True, blocked_reason=reason)
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def _person(value: rules.Feedback, token: str) -> tuple[ActorRef, int]:
    role = next(
        (x for x in value.cast.roles if x.actor.token == token and x.actor != value.actor), None
    )
    if role is None or role.actor.kind != "pilot":
        raise WorkflowError("SOURCE_ANKOU_PERSON_REQUIRED: select the actual present original Girl")
    return role.actor, role.controller


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = prove(game, c, state, action["data"]["ankou_feedback"])
    event, kind = action["data"]["response_event"], row["kind"]
    if kind == "ankou_feedback_child":
        raise WorkflowError("Complete the actual selected reprisal, not an acknowledgment")
    if answer.denied or answer.number is not None or answer.member is not None:
        raise WorkflowError("Use the actual Feedback source controls")
    if kind == "ankou_feedback_choice":
        if (
            value.phase != "choice"
            or row["actor_id"] != value.actor.entity
            or len(answer.options) != 1
        ):
            raise WorkflowError("The original Ankou Pilot owns this actual Feedback choice")
        choice = answer.options[0]
        if choice == "die":
            if answer.fields or answer.flag is not None or not answer.text.strip():
                raise WorkflowError("Record the actual source ending, without invented targets")
            before = GameState.model_validate_json(state.model_dump_json())
            updated = end_in_transaction(
                c,
                game,
                state,
                value.actor,
                reason="death",
                source_event=event,
                account=answer.text,
                archive_id="ankou-death:" + value.id,
            )
            _copy(state, updated)
            archive = next((x for x in state.career_archives if x.actor == value.actor), None)
            value = value.model_copy(
                update=dict(
                    choice="die",
                    choice_event=event,
                    archive=archive.id if archive else None,
                    prevention=archive is None,
                )
            )
            if archive:
                _blocked(
                    game,
                    c,
                    state,
                    action,
                    value,
                    event,
                    "Actual Ankou Feedback death before the original roll",
                )
            elif before == state:
                raise WorkflowError(
                    "Prove the actual death prevention; do not waive the source ending"
                )
            else:
                _ready(game, c, state, action, value, event)
            return
        if choice not in ("bond", "purpose", "tear") or not answer.text.strip():
            raise WorkflowError("Choose one actual printed Feedback effect, or the source death")
        target, controller = _person(value, answer.fields.get("target", ""))
        resolve(state, target, profiles(c, game.store.campaign_id))
        value = value.model_copy(
            update=dict(
                choice=choice, target=target, target_controller=controller, choice_event=event
            )
        )
        if choice == "purpose":
            if set(answer.fields) != {"target"} or answer.flag is not None:
                raise WorkflowError("Beg this actual person; their own controller answers")
            rules.put(state, value.model_copy(update=dict(phase="purpose", request=answer.text)))
            game.request(c, action, controller, "ankou_feedback_purpose", dict(source=value.id))
        elif choice == "bond":
            if set(answer.fields) - {"target", "replace", "name"} or answer.flag is not None:
                raise WorkflowError(
                    "Rewrite this actual Bond as one owned psychological Girl Asset"
                )
            if depth(state, value.actor, target) < 1:
                raise WorkflowError("Cut off a real current Bond with the actual scene person")
            from girlframe.engine.m3_intracadre_marriage import marriage_for

            if marriage_for(state, value.actor) is not None:
                raise WorkflowError(
                    "SOURCE_MARRIAGE_BOND_REQUIRED: preserve the actual marriage source"
                )
            if not answer.fields.get("name", "").strip():
                raise WorkflowError("Name the actual rewritten Bond Asset")
            sheet = state.sheets[value.actor.entity]
            installed = install(
                sheet,
                AssetState(
                    id=value.id + ":bond",
                    family="girl",
                    name=answer.fields.get("name", "").strip(),
                    description=answer.text,
                ),
                replace=answer.fields.get("replace"),
                state=state,
            )
            state.sheets[value.actor.entity] = installed.sheet
            _copy(state, set_depth(state, value.actor, target, 0, event))
            _ready(game, c, state, action, value, event)
        else:
            if set(answer.fields) - {"target", "asset"} or answer.flag is not None:
                raise WorkflowError("Select the actual Asset physically torn off")
            from girlframe.engine.m3_budget_removal import blocked

            sheet = state.sheets[value.actor.entity]
            asset = next((x for x in sheet.assets if x.id == answer.fields.get("asset")), None)
            if asset is None or asset.id in blocked(state, value.actor):
                raise WorkflowError(
                    "SOURCE_ANKOU_ASSET_REQUIRED: preserve this linked actual Asset"
                )
            from girlframe.engine.m3_janus_storage import ids
            from girlframe.engine.m3_leviathan_obsession import allowed_gain

            view = resolve(state, value.actor, profiles(c, game.store.campaign_id))
            if asset.family == "frame" and (
                view.cell is None
                or view.cell != view.frame_cell
                or view.frame_instance != value.frame
            ):
                raise WorkflowError(
                    "Be physically present at the actual original Frame before tearing it"
                )
            remaining = [x for x in sheet.assets if x.family == asset.family and x.id != asset.id]
            stored = ids(state, value.actor)
            if (
                asset.void
                or asset.id in stored
                or not any(not x.damaged for x in remaining)
                or not any(not x.void and x.id not in stored for x in remaining)
            ):
                raise WorkflowError(
                    "SOURCE_ANKOU_LOSS_REQUIRED: attach actual last-Asset/Void continuations first"
                )
            sheet.assets = [x for x in sheet.assets if x.id != asset.id]
            sheet.heat += allowed_gain(state, value.actor, 5, "Ankou Feedback tear", event)
            sheet.revision += 1
            rules.put(state, value.model_copy(update=dict(phase="child", lost_asset=asset.id)))
            game.request(
                c, action, int(value.actor.entity), "ankou_feedback_child", dict(source=value.id)
            )
    elif kind == "ankou_feedback_purpose":
        if value.phase != "purpose" or int(row["actor_id"]) != value.target_controller:
            raise WorkflowError("Only the actual begged person's controller authors their response")
        if (
            answer.options
            or answer.fields
            or type(answer.flag) is not bool
            or not answer.text.strip()
        ):
            raise WorkflowError("Give an actual purpose or your own explicit refusal")
        value = value.model_copy(
            update=dict(purpose_given=answer.flag, purpose=answer.text, purpose_event=event)
        )
        if answer.flag:
            rules.put(state, value.model_copy(update=dict(phase="purpose_identity")))
            game.request(
                c, action, int(value.actor.entity), "ankou_feedback_identity", dict(source=value.id)
            )
        else:
            assert value.target is not None
            _copy(state, make_helpless(state, value.actor, value.target, event))
            _blocked(
                game,
                c,
                state,
                action,
                value,
                event,
                "Purpose explicitly refused: actual Helpless; original Play not performed",
            )
    elif kind == "ankou_feedback_identity":
        if value.phase != "purpose_identity" or row["actor_id"] != value.actor.entity:
            raise WorkflowError("Only the original Pilot places their actual newly given purpose")
        if (
            answer.options
            or answer.text
            or answer.flag is not None
            or set(answer.fields) - {"replace"}
        ):
            raise WorkflowError("Use the actual purpose and only a cap-required ordinary slot")
        sheet = state.sheets[value.actor.entity]
        ordinary = [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
        replace = answer.fields.get("replace")
        if len(ordinary) >= 4:
            old = next((x for x in ordinary if x.id == replace), None)
            if (
                old is None
                or old.protected
                or old.paired
                or old.am_limiter
                or old.id in sheet.sedation_locked
            ):
                raise WorkflowError("Replace an eligible actual ordinary Identity at the cap")
            require_unlocked(sheet.identities, (old.id,))
        elif replace is not None:
            raise WorkflowError("Do not erase an Identity when its actual slot is available")
        slot = replacement_slot(sheet, replace)
        sheet.identities = [x for x in sheet.identities if x.id != replace]
        entry = IdentityState(id=value.id + ":purpose", name=value.purpose or "", slot=slot)
        from girlframe.services.m2_choices import ChoiceEngine

        if not ChoiceEngine(game).duplicate_labels() and any(
            x.name.casefold() == entry.name.casefold() for x in sheet.identities
        ):
            raise WorkflowError("The actual owner policy requires distinct Identity labels")
        sheet.identities.append(entry)
        sheet.revision += 1
        _ready(game, c, state, action, value.model_copy(update=dict(new_identity=entry.id)), event)
    else:
        raise WorkflowError("Use this exact actual Feedback choice")


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.parent:
        return None
    parent = game.action(c, prepared.parent)
    identity = parent["data"].get("ankou_feedback")
    if not identity:
        return None
    value = prove(game, c, state, identity)
    if (
        value.phase != "child"
        or value.child
        or value.target is None
        or viewer.user_id != int(value.actor.entity)
        or channel != int(parent["channel_id"])
        or prepared.play != "flirt"
        or prepared.target != int(value.target.entity)
        or prepared.target_actor is not None
        or prepared.source_work != value.id
        or prepared.identity is not None
        or prepared.gain
        or prepared.disposable_heat
        or prepared.heat != state.sheets[value.actor.entity].heat
        or not game.pending(c, parent["id"])
    ):
        raise WorkflowError(
            "Make this actual source-owned Flirt against the selected original person"
        )
    return dict(
        source=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json"),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("ankou_feedback_child")
    if meta:
        value = prove(game, c, state, meta["source"])
        if (
            value.child
            or action.get("parent_id") != value.action
            or action["actor_id"] != value.actor.entity
        ):
            raise WorkflowError("Bind only this actual source's one original reprisal")
        rules.put(state, value.model_copy(update=dict(child=action["id"], child_event=event)))


def complete_child(
    game: GameService, c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    meta = child["data"].get("ankou_feedback_child")
    if not meta:
        return False
    value = prove(game, c, state, meta["source"])
    if (
        value.child != child["id"]
        or child["state"] != "complete"
        or not child["data"].get("receipt")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError("Complete the actual targeted reprisal and all its immediate choices")
    parent = game.action(c, value.action)
    for row in game.pending(c, value.action):
        if row["kind"] != "ankou_feedback_child" or row["actor_id"] != value.actor.entity:
            raise WorkflowError("Retain the actual original reprisal requirement")
        c.execute(
            t.m2["m2_choices"]
            .update()
            .where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == row["id"],
            )
            .values(
                state="answered",
                revision=row["revision"] + 1,
                body_json=json.dumps(
                    dict(source=value.id, child=child["id"], completed_event=event)
                ),
            )
        )
    _ready(game, c, state, parent, value, event)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = prove(game, c, state, action["data"]["ankou_feedback"])
    sheet = state.sheets.get(value.actor.entity)
    owns_resources = row["actor_id"] == value.actor.entity
    people = []
    for role in value.cast.roles:
        if owns_resources and role.actor != value.actor and role.actor.kind == "pilot":
            actor = resolve(state, role.actor, profiles(c, game.store.campaign_id))
            people.append(
                dict(
                    ref=role.actor.model_dump(mode="json"),
                    token=role.actor.token,
                    label=actor.label,
                    bond=depth(state, value.actor, role.actor),
                )
            )
    return dict(
        id=value.id,
        phase=value.phase,
        purpose=value.purpose,
        request=value.request,
        people=people,
        assets=[x.model_dump(mode="json") for x in sheet.assets]
        if sheet and owns_resources
        else [],
        identities=[
            dict(id=x.id, name=x.name, protected=x.protected, marked=x.marked)
            for x in sheet.identities
        ]
        if sheet and owns_resources
        else [],
        heat=sheet.heat if sheet and owns_resources else None,
        sheet_revision=sheet.revision if sheet and owns_resources else None,
        target=value.target.model_dump(mode="json") if value.target else None,
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    identity = action["data"].get("ankou_feedback") or action["data"].get(
        "ankou_feedback_child", {}
    ).get("source")
    if identity:
        value = prove(game, c, state, identity)
        if value.choice == "tear" and value.choice_event == event:
            from girlframe.services.m3_asset_loss import create_loss_work, snapshots

            before, after = snapshots(game, c, event)
            children = create_loss_work(
                game,
                c,
                before,
                after,
                scope=dict(campaign_id=game.store.campaign_id, scene_id=value.cast.id),
                actor=value.actor,
                event=event,
                reason="ankou_feedback",
                source_id=value.id,
                in_battle=None,
            )
            if children:
                raise WorkflowError(
                    "SOURCE_ANKOU_LOSS_CONTINUATION_REQUIRED: preserve actual mandatory children"
                )
        if value.archive and value.resolved_event == event:
            archive = next(x for x in state.career_archives if x.id == value.archive)
            synchronize_end(c, game, archive)


def prove_loss_source(
    game: GameService,
    c: Connection,
    after: GameState,
    event: str,
    source_id: str,
    actor: ActorRef,
) -> dict[str, Any]:
    value = prove(game, c, after, source_id)
    before, born = _before(game, c, event), _history(c, game, event)
    stage = rules.get(born, source_id)
    if (
        value.actor != actor
        or stage.choice != "tear"
        or stage.choice_event != event
        or value.lost_asset != stage.lost_asset
        or stage.target is None
    ):
        raise WorkflowError("Recover the actual owned Feedback tear and original selected person")
    old, new = before.sheets[actor.entity], born.sheets[actor.entity]
    asset = next((x for x in old.assets if x.id == value.lost_asset), None)
    from girlframe.engine.m3_leviathan_obsession import allowed_gain

    if (
        asset is None
        or new.assets != [x for x in old.assets if x.id != asset.id]
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
        or new.heat != old.heat + allowed_gain(before, actor, 5, "Ankou Feedback tear", event)
    ):
        raise WorkflowError("Prove the exact actual Asset disappearance and five Heat source")
    view = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if asset.family == "frame" and (
        view.cell is None or view.cell != view.frame_cell or view.frame_instance != value.frame
    ):
        raise WorkflowError("Recover the original body's actual presence at the torn Frame")
    return dict(piloting=view.piloting, in_battle=None, source_action=value.action)


class FeedbackService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Ankou Feedback — " + x.phase,
                phase=x.phase,
                pending=any(
                    row["actor_id"] == str(viewer.user_id)
                    and row["kind"].startswith("ankou_feedback_")
                    for row in self.game.pending(c, x.action)
                ),
            )
            for x in rules.sources(state)
            if viewer.user_id in (int(x.actor.entity), x.target_controller)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (int(value.actor.entity), value.target_controller):
                raise WorkflowError(
                    "Only the actual original Feedback participants read this private source"
                )
            if viewer.user_id != int(value.actor.entity):
                return dict(
                    id=value.id,
                    action=value.action,
                    phase=value.phase,
                    actor=value.actor.model_dump(mode="json"),
                    purpose=value.purpose,
                    request=value.request,
                    purpose_given=value.purpose_given,
                )
            return value.model_dump(mode="json", exclude={"registry", "cast"})
