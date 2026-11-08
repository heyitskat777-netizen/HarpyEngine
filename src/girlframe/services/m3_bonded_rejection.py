"""Actual basic Plays and original-owner findings for source-only Tag rejection."""

import hashlib
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_rejection as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_bonded import _contact, _man_reject_allowed, _man_resolution, prove
from girlframe.services.m3_dose_up import _audit, _roll_source
from girlframe.services.m3_girl_insurance import _before
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(bonded.SEX)


def _source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> tuple[bonded.Source, dict[str, Any]]:
    value = prove(game, c, state, identity)
    status = _man_resolution(game, c, state, value)
    if (
        value.action is not None
        or value.route != "seven"
        or status is None
        or status["decision"] is None
        or status["decision"].decision != "reject"
    ):
        raise WorkflowError("Recover the original source-only Man Tag rejection")
    return value, status


def _current(
    game: GameService, c: Connection, state: GameState, request: rules.Request
) -> bonded.Source:
    source, status = _source(game, c, state, request.source)
    if source.phase != "results" or status["performance"] is not None or not status["pending"]:
        raise WorkflowError("This actual Tag rejection is no longer pending")
    if current_ref(state, request.controller) != request.owner:
        raise WorkflowError("Only the original rejecting person can perform this action")
    _contact(game, c, state, source)
    tag = next((x for x in state.sheets[request.owner.entity].tags if x.id == request.tag), None)
    if (
        tag is None
        or not tag.rejection_pending
        or not _man_reject_allowed(state, request.owner, tag)
    ):
        raise WorkflowError("Preserve the actual pending Tag and its rejection restrictions")
    from girlframe.services.m2_choices import ChoiceEngine

    ChoiceEngine(game).prove_tag_setter(c, state, request.controller, tag)
    return source


def _family(
    game: GameService,
    c: Connection,
    state: GameState,
    owner: ActorRef,
    play: str,
    target: ActorRef | None,
) -> None:
    from girlframe.services.m3_battle import _visible

    bound = profiles(c, game.store.campaign_id)
    acting = resolve(state, owner, bound, require_current_profile=False)
    if play in ("flirt", "engage"):
        if target is None or target == owner:
            raise WorkflowError("This actual Play needs its distinct real source-scene target")
        if not _visible(state, target, int(owner.entity)):
            raise WorkflowError("Use a source target actually known to the rejecting owner")
        opposing = resolve(state, target, bound, require_current_profile=False)
        if opposing.offstage_source:
            raise WorkflowError("The actual source target is offstage")
    elif target is not None:
        raise WorkflowError("This actual basic Play has no source target selector")
    if play == "flirt":
        if target is None or target.kind not in ("pilot", "npc"):
            raise WorkflowError(
                "FLIRT_TARGET_ADAPTER_REQUIRED: use an actual native Pilot or ordinary NPC"
            )
        if target.kind == "npc":
            from girlframe.services.m3_npc_flirt import _npc

            _npc(state, target)
            if not _visible(state, target, int(owner.entity)):
                raise WorkflowError("Use an actual NPC already known to this rejecting owner")
        elif resolve(state, target, bound, require_current_profile=False).rules != "girl_frame":
            raise WorkflowError("Use the actual native Pilot Flirt source, not a proxy body")
    if play == "engage" and not any(not asset.damaged for asset in acting.assets):
        raise WorkflowError("Actual Engage requires an available owned Asset")
    if play == "check_sensors" and acting.piloting is not True:
        raise WorkflowError(
            "SOURCE_FRAME_REQUIRED: Check Your Sensors needs your actual piloted Frame"
        )


def _latest(state: GameState, source: str) -> rules.Request | None:
    return next(
        (x for x in reversed(rules.records(state, rules.Request)) if x.source == source), None
    )


def prove_request(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Request:
    request = rules.get(state, rules.Request, identity)
    birth = _history(c, game, request.event)
    source, status = _source(game, c, birth, request.source)
    _audit(game, c, request.event, ("m3.bonded_rejection_requested",), request.controller)
    if (
        request not in rules.records(birth, rules.Request)
        or request.id != rules.identity("request", request.source, request.event)
        or request.resolution != status["work"].id
        or request.decision != status["decision"].id
        or status["performance"] is not None
        or request.tag != status["work"].tag
        or request.owner != status["work"].partner
        or request.controller != status["work"].controller
        or request.cast != source.cast
        or not request.account.strip()
        or len(request.account) > 1200
        or request.play not in rules.PLAYS
        or request.target is not None
        and not any(x.actor == request.target for x in request.cast.roles)
        or request.play == "flirt"
        and (request.target is None or request.target == request.owner)
    ):
        raise WorkflowError("Preserve the actual original rejection context, owner and source")
    _family(game, c, birth, request.owner, request.play, request.target)
    return request


def _action(request: rules.Request, attempt: rules.Attempt, action: dict[str, Any]) -> None:
    meta = action["data"].get("bonded_rejection_child", {})
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    if (
        action["id"] != attempt.action
        or str(action["actor_id"]) != request.owner.entity
        or action["scene_id"] != request.cast.id
        or int(action["channel_id"]) != request.cast.channel
        or action.get("parent_id") is not None
        or action["data"]["play"] != request.play
        or prepared.source_work != request.id
        or prepared.context != request.account
        or prepared.play != request.play
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or prepared.target_actor != request.target
        or prepared.target
        not in (
            None,
            int(request.target.entity)
            if request.target and request.target.kind == "pilot"
            else None,
        )
        or action["data"].get("character_ids", {}).get(request.owner.entity)
        != request.owner.incarnation
        or meta.get("request") != request.id
        or meta.get("source") != request.source
        or meta.get("attempt") != attempt.id
        or meta.get("actor") != request.owner.model_dump(mode="json")
        or meta.get("cast") != request.cast.model_dump(mode="json")
        or meta.get("cast_sha256") != fingerprint(request.cast)
    ):
        raise WorkflowError("Recover the exact real rejection Play and its original person")


def prove_attempt(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Attempt:
    attempt = rules.get(state, rules.Attempt, identity)
    request = prove_request(game, c, state, attempt.request)
    birth = _history(c, game, attempt.event)
    _audit(game, c, attempt.event, ("m2.play_confirmed", "m3.play_confirmed"), request.controller)
    if (
        attempt not in rules.records(birth, rules.Attempt)
        or attempt.owner != request.owner
        or attempt.id != rules.identity("attempt", request.id, attempt.action)
    ):
        raise WorkflowError("Preserve the genuine confirmed rejection attempt")
    _action(request, attempt, game.action(c, attempt.action))
    return attempt


def _released(game: GameService, c: Connection, state: GameState, attempt: rules.Attempt) -> bool:
    releases = [x for x in rules.records(state, rules.Release) if x.attempt == attempt.id]
    if len(releases) > 1:
        raise WorkflowError("Release this unrolled attempt only once")
    if not releases:
        return False
    release = releases[0]
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == release.event
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(event["payload_json"]) if event else {}
    request = rules.get(state, rules.Request, attempt.request)
    action = game.action(c, attempt.action)
    if (
        release not in rules.records(_history(c, game, release.event), rules.Release)
        or release.id != attempt.id + ":release"
        or release.action != attempt.action
        or event is None
        or event["kind"] != "m3.shared_play_recovered"
        or event["actor_id"] != str(request.controller)
        or payload.get("action_id") != attempt.action
        or payload.get("cancelled_unrolled") is not True
        or action["state"] != "aborted"
        or action["data"].get("receipt")
        or c.scalar(
            sa.select(t.m2["m2_receipts"].c.id).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == attempt.action,
            )
        )
        is not None
    ):
        raise WorkflowError("Preserve the real owner cancellation and every known receipt")
    return True


def _attempts(state: GameState, request: rules.Request) -> list[rules.Attempt]:
    return [x for x in rules.records(state, rules.Attempt) if x.request == request.id]


def _pending_work(game: GameService, c: Connection, action: dict[str, Any]) -> bool:
    table = t.m3["m3_required_work"]
    versions = c.execute(
        sa.select(table)
        .where(table.c.campaign_id == game.store.campaign_id)
        .order_by(table.c.id, table.c.revision.desc())
    ).mappings()
    seen = set()
    required_ids = {
        x["id"] for x in action["data"].get("dive", {}).get("followups", ()) if "continuation" in x
    }
    for row in versions:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        body = json.loads(row["body_json"])
        if (
            row["id"] in required_ids
            or body.get("source_action") == action["id"]
            or body.get("action") == action["id"]
        ):
            required_ids.discard(row["id"])
            if row["state"] != "resolved":
                return True
    return bool(required_ids)


def completion_ready(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("bonded_rejection_child"):
        return False
    actual = game.action(c, action["id"])
    attempt = prove_attempt(game, c, state, actual["data"]["bonded_rejection_child"]["attempt"])
    if (
        _released(game, c, state, attempt)
        or actual["state"] != "complete"
        or not actual["data"].get("receipt")
    ):
        return False
    if game.pending(c, actual["id"]) or _pending_work(game, c, actual):
        return False
    lock = game.lock(c, int(actual["channel_id"]))
    if lock and lock["action_id"] == actual["id"] and lock["state"] != "released":
        return False
    _roll_source(game, c, actual)
    return True


def prove_finding(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Finding:
    finding = rules.get(state, rules.Finding, identity)
    request = prove_request(game, c, state, finding.request)
    attempt = prove_attempt(game, c, state, finding.attempt)
    action = game.action(c, attempt.action)
    birth = _history(c, game, finding.event)
    before = _before(game, c, finding.event)
    source, status = _source(game, c, before, request.source)
    _audit(
        game,
        c,
        finding.event,
        ("m3.bonded_man_tag_rejected",) if finding.achieved else ("m3.bonded_rejection_outcome",),
        request.controller,
    )
    roll_event, _ = _roll_source(game, c, action)
    if (
        finding not in rules.records(birth, rules.Finding)
        or finding.id != attempt.id + ":finding"
        or finding.owner != request.owner
        or finding.controller != request.controller
        or finding.action != action["id"]
        or attempt.request != request.id
        or finding.action_sha256 != _hash(action)
        or finding.receipt_sha256 != _hash(action["data"]["receipt"])
        or finding.roll_event != roll_event
        or not finding.account.strip()
        or not completion_ready(game, c, state, action)
        or status["performance"] is not None
        or source.phase != "results"
    ):
        raise WorkflowError(
            "Preserve the true completed Play, original receipt and owner-authored outcome"
        )
    if finding.achieved:
        performance = next(
            (
                x
                for x in bonded.records(birth, bonded.ManTagRejection)
                if x.work == request.resolution
            ),
            None,
        )
        if (
            performance is None
            or performance.id != request.resolution + ":performed"
            or performance.controller != request.controller
            or performance.event != finding.event
            or performance.partner != request.owner
            or performance.account != finding.account
            or any(x.id == request.tag for x in birth.sheets[request.owner.entity].tags)
        ):
            raise WorkflowError("Preserve the actual performed rejection and exact Tag consumption")
    else:
        old_tag = next(
            (x for x in before.sheets[request.owner.entity].tags if x.id == request.tag), None
        )
        new_tag = next(
            (x for x in birth.sheets[request.owner.entity].tags if x.id == request.tag), None
        )
        if (
            old_tag is None
            or new_tag != old_tag
            or any(
                x.work == request.resolution for x in bonded.records(birth, bonded.ManTagRejection)
            )
        ):
            raise WorkflowError("An unsuccessful actual outcome cannot erase the Tag")
    return finding


def _finding(
    game: GameService, c: Connection, state: GameState, attempt: rules.Attempt
) -> rules.Finding | None:
    found = [x for x in rules.records(state, rules.Finding) if x.attempt == attempt.id]
    if len(found) > 1:
        raise WorkflowError("Record this actual outcome once")
    return prove_finding(game, c, state, found[0].id) if found else None


def require_no_child(game: GameService, c: Connection, state: GameState, source: str) -> None:
    request = _latest(state, source)
    if request is not None:
        prove_request(game, c, state, request.id)
        raise WorkflowError(
            "REQUIRED_REJECTION_PLAY: use the original actual Play and owned finding"
        )


def source_for_play(
    game: GameService,
    c: Connection,
    state: GameState,
    prepared: PlayInput | None = None,
    action: dict[str, Any] | None = None,
) -> str | None:
    if prepared and any(x.id == prepared.source_work for x in rules.records(state, rules.Request)):
        return prove_request(game, c, state, prepared.source_work or "").source
    token = action["id"] if action else prepared.parent if prepared else None
    seen = set()
    while token and token not in seen:
        seen.add(token)
        actual = game.action(c, token)
        meta = actual["data"].get("bonded_rejection_child")
        if meta:
            attempt = prove_attempt(game, c, state, meta["attempt"])
            request = prove_request(game, c, state, attempt.request)
            if _released(game, c, state, attempt):
                raise WorkflowError("A cancelled child cannot admit another source's action")
            return request.source
        token = actual.get("parent_id")
    return None


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not any(x.id == prepared.source_work for x in rules.records(state, rules.Request)):
        return None
    _access(game, c, viewer)
    request = prove_request(game, c, state, prepared.source_work or "")
    source = _current(game, c, state, request)
    attempts = _attempts(state, request)
    if attempts:
        previous = prove_attempt(game, c, state, attempts[-1].id)
        found = _finding(game, c, state, previous)
        if not _released(game, c, state, previous) and (found is None or found.achieved):
            raise WorkflowError("Resume the original actual attempt, its recovery or owned outcome")
    if (
        _latest(state, source.id) != request
        or request.owner != current_ref(state, viewer.user_id)
        or viewer.user_id != request.controller
        or channel != request.cast.channel
        or prepared.play != request.play
        or prepared.context != request.account
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or prepared.target_actor != request.target
        or prepared.target
        not in (
            None,
            int(request.target.entity)
            if request.target and request.target.kind == "pilot"
            else None,
        )
    ):
        raise WorkflowError("Use only the actual rejecting owner's finite original Play context")
    from girlframe.services.p1_source_pause import require_ready

    require_ready(game, c, state, source.id)
    _family(game, c, state, request.owner, request.play, request.target)
    if request.play == "check_sensors" and not prepared.piloting:
        raise WorkflowError("Use the actual piloted Frame for this Frame Play")
    return dict(
        request=request.id,
        source=source.id,
        actor=request.owner.model_dump(mode="json"),
        cast=request.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(request.cast),
        table=sorted(
            {x.controller for x in request.cast.roles}
            | ({request.cast.facilitator} if request.cast.facilitator else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["bonded_rejection_child"]
    request = prove_request(game, c, state, meta["request"])
    attempt = rules.Attempt(
        id=rules.identity("attempt", request.id, action["id"]),
        request=request.id,
        action=action["id"],
        owner=request.owner,
        event=event,
    )
    meta["attempt"] = attempt.id
    _action(request, attempt, action)
    rules.put(state, attempt)


def pre_roll_child(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    attempt = prove_attempt(game, c, state, action["data"]["bonded_rejection_child"]["attempt"])
    request = prove_request(game, c, state, attempt.request)
    _current(game, c, state, request)
    _family(game, c, state, request.owner, request.play, request.target)
    if (
        viewer.user_id != request.controller
        or _released(game, c, state, attempt)
        or _finding(game, c, state, attempt)
    ):
        raise WorkflowError("Roll only the original owner's actual live attempt")


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    meta = action["data"].get("bonded_rejection_child")
    if not meta:
        return False
    attempt = prove_attempt(game, c, state, meta["attempt"])
    if (
        not event
        or action["state"] != "aborted"
        or not action["data"].get("shared_recovery")
        or action["data"].get("receipt")
        or _finding(game, c, state, attempt)
        or c.scalar(
            sa.select(t.m2["m2_receipts"].c.id).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        is not None
    ):
        raise WorkflowError("Release only this genuinely cancelled unrolled attempt")
    rules.put(
        state,
        rules.Release(
            id=attempt.id + ":release", attempt=attempt.id, action=action["id"], event=event
        ),
    )
    return True


class BondedRejectionService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        source: str,
        revision: int,
        play: str,
        account: str,
        *,
        target: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value, status = _source(self.game, c, state, source)
            owner = status["work"].partner
            if (
                state.revision != revision
                or value.phase != "results"
                or not status["pending"]
                or status["performance"] is not None
                or owner != current_ref(state, viewer.user_id)
                or status["work"].controller != viewer.user_id
                or play not in rules.PLAYS
                or not account.strip()
                or len(account.strip()) > 1200
                or target is not None
                and not any(x.actor == target for x in value.cast.roles)
                or play == "flirt"
                and (target is None or target == owner)
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Declare only your real pending rejection and actual legal basic Play"
                )
            previous = _latest(state, source)
            if previous:
                attempts = _attempts(state, previous)
                last = _finding(self.game, c, state, attempts[-1]) if attempts else None
                if last is None or last.achieved:
                    raise WorkflowError("Resume your original declared actual attempt")
            event = str(uuid4())
            request = rules.Request.model_validate(
                dict(
                    id=rules.identity("request", source, event),
                    source=source,
                    resolution=status["work"].id,
                    decision=status["decision"].id,
                    tag=status["work"].tag,
                    owner=owner,
                    controller=viewer.user_id,
                    cast=value.cast,
                    play=play,
                    account=account.strip(),
                    target=target,
                    event=event,
                )
            )
            _current(self.game, c, state, request)
            _family(self.game, c, state, owner, play, target)
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, source)
            rules.put(state, request)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_rejection_requested",
                state,
                event_id=event,
                source=source,
                request=request.id,
            )
            return dict(id=request.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bonded_rejection_requested",
            dict(
                source=source,
                revision=revision,
                play=play,
                account=account,
                target=target.model_dump(mode="json") if target else None,
            ),
            operation,
        )

    def conclude(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        attempt_id: str,
        achieved: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            request = prove_request(self.game, c, state, identity)
            source = _current(self.game, c, state, request)
            attempt = prove_attempt(self.game, c, state, attempt_id)
            action = self.game.action(c, attempt.action)
            if (
                state.revision != revision
                or _latest(state, source.id) != request
                or viewer.user_id != request.controller
                or current_ref(state, viewer.user_id) != request.owner
                or type(achieved) is not bool
                or attempt.request != request.id
                or _finding(self.game, c, state, attempt) is not None
                or not completion_ready(self.game, c, state, action)
                or not account.strip()
                or len(account.strip()) > 1200
            ):
                raise WorkflowError(
                    "Only the actual owner assesses its truly completed performed action"
                )
            event = str(uuid4())
            roll_event, _ = _roll_source(self.game, c, action)
            finding = rules.Finding(
                id=attempt.id + ":finding",
                request=request.id,
                attempt=attempt.id,
                owner=request.owner,
                controller=request.controller,
                action=action["id"],
                action_sha256=_hash(action),
                roll_event=roll_event,
                receipt_sha256=_hash(action["data"]["receipt"]),
                achieved=achieved,
                account=account.strip(),
                event=event,
            )
            if achieved:
                from girlframe.services.m2_choices import ChoiceEngine

                sheet = state.sheets[request.owner.entity]
                sheet.tags = [x for x in sheet.tags if x.id != request.tag]
                sheet.revision += 1
                ChoiceEngine(self.game).tag_resolved(state, request.controller, request.tag)
                bonded.put(
                    state,
                    bonded.ManTagRejection(
                        id=request.resolution + ":performed",
                        work=request.resolution,
                        partner=request.owner,
                        controller=request.controller,
                        account=account.strip(),
                        event=event,
                    ),
                )
            rules.put(state, finding)
            kind = "m3.bonded_man_tag_rejected" if achieved else "m3.bonded_rejection_outcome"
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                source=source.id,
                action_id=action["id"],
                bonded_rejection_finding=finding.id,
            )
            return dict(
                id=request.id, finding=finding.id, achieved=achieved, revision=state.revision
            )

        return self._write(
            viewer,
            key,
            "m3.bonded_rejection_outcome",
            dict(
                id=identity,
                revision=revision,
                attempt=attempt_id,
                achieved=achieved,
                account=account,
            ),
            operation,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            request = prove_request(self.game, c, state, identity)
            source = bonded.get(_history(c, self.game, request.event), request.source)
            if viewer.user_id not in source.controllers.values():
                raise WorkflowError(
                    "Only original source participants read this private action history"
                )
            attempts = []
            for record in _attempts(state, request):
                attempt = prove_attempt(self.game, c, state, record.id)
                action = self.game.action(c, attempt.action)
                finding = _finding(self.game, c, state, attempt)
                released = _released(self.game, c, state, attempt)
                attempts.append(
                    dict(
                        id=attempt.id,
                        action=attempt.action,
                        state=action["state"],
                        released=released,
                        receipt=action["data"].get("receipt"),
                        ready=completion_ready(self.game, c, state, action),
                        finding=finding.model_dump(mode="json") if finding else None,
                        recoverable=bool(action["data"].get("shared_recovery")),
                    )
                )
            last = attempts[-1] if attempts else None
            own = viewer.user_id == request.controller
            if not own:
                for item in attempts:
                    item["receipt"] = {"recorded": True} if item["receipt"] else None
                    if item["finding"]:
                        item["finding"] = {
                            key: item["finding"][key] for key in ("achieved", "account", "event")
                        }
            latest = _latest(state, source.id) == request
            active = latest and not any(x["finding"] and x["finding"]["achieved"] for x in attempts)
            return dict(
                id=request.id,
                revision=state.revision,
                source=request.source,
                play=request.play,
                account=request.account,
                actor=request.owner.model_dump(mode="json"),
                target=request.target.model_dump(mode="json") if request.target else None,
                channel=request.cast.channel,
                attempts=attempts,
                can_start=own
                and active
                and (
                    last is None
                    or last["released"]
                    or bool(last["finding"] and not last["finding"]["achieved"])
                ),
                can_conclude=own
                and active
                and bool(last and last["ready"] and not last["finding"]),
                descriptor=dict(
                    kind="bonded_rejection_child",
                    actor=request.owner.model_dump(mode="json"),
                    parent=None,
                    channel=request.cast.channel,
                    body=dict(
                        allowed=[request.play],
                        source_work=request.id,
                        play=request.play,
                        context=request.account,
                        target_actor=request.target.model_dump(mode="json")
                        if request.target
                        else None,
                        target=int(request.target.entity)
                        if request.play == "flirt"
                        and request.target
                        and request.target.kind == "pilot"
                        else None,
                    ),
                ),
            )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.services.m3_battle import _visible

        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            sources = []
            for value in bonded.records(state, bonded.Source):
                if (
                    value.target is None
                    or value.target.entity != str(viewer.user_id)
                    or value.phase != "results"
                ):
                    continue
                status = _man_resolution(self.game, c, state, value)
                if (
                    status
                    and status["pending"]
                    and status["decision"]
                    and status["decision"].decision == "reject"
                ):
                    sources.append(
                        dict(
                            id=value.id,
                            label="Your actual pending Tag rejection",
                            targets=[
                                dict(
                                    ref=x.actor.model_dump(mode="json"),
                                    token=x.actor.token,
                                    label="Actual scene role: " + x.actor.token,
                                )
                                for x in value.cast.roles
                                if x.actor != value.target
                                and _visible(state, x.actor, viewer.user_id)
                            ],
                        )
                    )
            return dict(revision=state.revision, sources=sources, history=self._tasks(c, viewer))

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for request in rules.records(state, rules.Request):
            birth = _history(c, self.game, request.event)
            source = bonded.get(birth, request.source)
            if viewer.user_id not in source.controllers.values():
                continue
            prove_request(self.game, c, state, request.id)
            achieved = any(
                x.request == request.id and x.achieved for x in rules.records(state, rules.Finding)
            )
            pending = _latest(state, request.source) == request and not achieved
            result.append(
                dict(
                    id=request.id,
                    revision=state.revision,
                    label="Actual rejection Play: " + rules.PLAYS[request.play],
                    phase="pending" if pending else "resolved",
                    pending=pending and viewer.user_id == request.controller,
                )
            )
        return result
