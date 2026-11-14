"""Actual Call guests and nearby Gorgon correspondence, under the original Dive receipt."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_dive as dive
from girlframe.engine import m3_mockingbird as mockingbird
from girlframe.engine import m3_passengers as physical
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_dive_state import Effect, NpcVoid
from girlframe.engine.m3_mockingbird_state import CallSession
from girlframe.engine.m3_passenger_state import Passenger
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

BOARD = "call_cockpit_guest"
RELAY = "call_gorgon_relay"


def _copy(target: GameState, source: GameState) -> None:
    for name in GameState.model_fields:
        setattr(target, name, getattr(source, name))


def _save(state: GameState, value: CallSession) -> None:
    state.mockingbird = state.mockingbird.model_copy(
        update={"calls": tuple(x for x in state.mockingbird.calls if x.id != value.id) + (value,)}
    )


def _cast_npcs(action: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        x["actor"]["entity"]
        for x in action["data"]["dive"]["cast"]["roles"]
        if x["actor"]["kind"] == "npc"
    )


def candidates(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], kind: str
) -> list[dict[str, Any]]:
    from girlframe.services.m3_enforcement_initiative import _known_target

    actor = ActorRef.model_validate(action["data"]["dive"]["actor"])
    bound = profiles(c, game.store.campaign_id)
    carrier = resolve(state, actor, bound, require_current_profile=False)
    if kind == BOARD and (
        not carrier.frame_instance
        or not physical.body_ready(state, actor)
        or carrier.inside_frame is not True
        or carrier.occupied_frame_instance not in (None, carrier.frame_instance)
        or carrier.frame_scrapped
        or carrier.subsumed
    ):
        return []
    cast = action["data"]["dive"]["cast"]
    refs = [ActorRef.model_validate(x["actor"]) for x in cast["roles"]]
    if kind == RELAY and state.world:
        refs += [ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons if x.alive]
    result = []
    for ref in dict.fromkeys(refs):
        if ref == actor or kind == RELAY and ref.kind != "gorgon":
            continue
        try:
            guest = resolve(state, ref, bound, require_current_profile=False)
        except ValueError:
            continue
        nearby = guest.cell is not None and carrier.cell is not None and guest.cell == carrier.cell
        source_present = any(ActorRef.model_validate(x["actor"]) == ref for x in cast["roles"])
        if (
            not _known_target(state, actor, ref, guest.controller)
            or not (nearby or source_present)
            or guest.offstage_source
            or guest.cell is not None
            and carrier.cell is not None
            and guest.cell != carrier.cell
        ):
            continue
        if kind == BOARD and (
            guest.subsumed
            or not physical.body_ready(state, ref)
            or guest.vitals_active is False
            or guest.custody not in (None, "free")
            or physical.passenger_view(state, ref)
            or ref.kind == "external_pilot"
            and guest.girl != "harpy"
            or ref.kind == "pilot"
            and not any(x.actor == ref for x in state.placements)
        ):
            continue
        result.append(
            dict(
                ref=ref.model_dump(mode="json"),
                token=ref.token,
                label=guest.label,
                controller=guest.controller,
            )
        )
    return result


def start(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    step: int,
    request: dict[str, Any],
    target: str,
    account: str,
) -> None:
    selected = action["data"]["dive"]["steps"][step]
    kind = selected["option"]
    candidate = next(
        (x for x in candidates(game, c, state, action, kind) if x["token"] == target), None
    )
    if candidate is None or not account.strip() or len(account) > 1200:
        raise WorkflowError(
            "Choose one actual nearby source guest/Gorgon and describe your own action"
        )
    actor = ActorRef.model_validate(action["data"]["dive"]["actor"])
    other = ActorRef.model_validate(candidate["ref"])
    event = action["data"]["response_event"]
    session = CallSession(
        id="call:" + action["id"] + ":" + str(step),
        source_action=action["id"],
        source_choice=request["id"],
        source_event=event,
        step=step,
        actor=actor,
        controller=int(action["actor_id"]),
        kind="guest" if kind == BOARD else "relay",
        phase="invite",
        guest=other,
        guest_controller=candidate["controller"],
        table=tuple(sorted(set(action["data"]["dive"]["table"]) | {candidate["controller"]})),
        message=account if kind == RELAY else "",
        account=account,
    )
    if kind == BOARD:
        bound = profiles(c, game.store.campaign_id)
        carrier = resolve(state, actor, bound, require_current_profile=False)
        guest = resolve(state, other, bound, require_current_profile=False)
        passenger = Passenger(
            id=session.id,
            actor=other,
            controller=guest.controller,
            carrier=actor,
            frame=carrier.frame_instance or "",
            source_action=action["id"],
            step=step,
            source_event=event,
            position_sha256=guest.position_sha256 or guest.source_sha256,
            carrier_sha256=carrier.source_sha256,
            account=account,
        )
        state.passengers.append(passenger)
        session = session.model_copy(update={"passenger": passenger.id})
    _save(state, session)
    selected["call_session"] = session.id
    selected["effect"] = dict(target=other.model_dump(mode="json"), account=account)
    game.request(
        c, action, candidate["controller"], "dive_call", dict(step=step, session=session.id)
    )


class CallService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, state: GameState, identity: str
    ) -> tuple[CallSession, dict[str, Any]]:
        value = next((x for x in state.mockingbird.calls if x.id == identity), None)
        if value is None:
            raise WorkflowError("Recover the actual original Call source")
        action = self.game.action(c, value.source_action)
        meta = action["data"].get("dive", {})
        selected = (
            meta.get("steps", [])[value.step] if len(meta.get("steps", [])) > value.step else {}
        )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        response = (
            c.execute(
                sa.select(t.m2["m2_responses"]).where(
                    t.m2["m2_responses"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_responses"].c.choice_id == value.source_choice,
                )
            )
            .mappings()
            .first()
        )
        source_choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_choices"].c.id == value.source_choice,
                )
            )
            .mappings()
            .first()
        )
        if (
            not action["data"].get("receipt")
            or source is None
            or response is None
            or source_choice is None
            or source_choice["action_id"] != action["id"]
            or source_choice["kind"] != "dive_effect"
            or json.loads(source_choice["body_json"]).get("step") != value.step
            or value.actor.model_dump(mode="json") != meta.get("actor")
            or value.controller != int(action["actor_id"])
            or selected.get("call_session") != value.id
            or selected.get("option") != (BOARD if value.kind == "guest" else RELAY)
            or not any(
                x.id == value.id and x.source_event == value.source_event
                for x in source.mockingbird.calls
            )
            or not self._call_owned(c, source, action, value.actor)
            or int(response["actor_id"]) != value.controller
        ):
            raise WorkflowError(
                "SOURCE_CALL_MISSING: prove the actual owned Dive choice and receipt"
            )
        return value, action

    def _call_owned(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        actor: ActorRef,
    ) -> bool:
        if mockingbird.owns(state, actor, mockingbird.CALL):
            return True
        from girlframe.services.m3_learned_plays import prove_call_lesson

        use = prove_call_lesson(self.game, c, state, action)
        return bool(use is not None and use.used and use.actor == actor)

    def _roles(self, c: Connection, state: GameState, value: CallSession) -> dict[int, ActorRef]:
        result = {value.controller: value.actor}
        if value.guest is not None and value.guest_controller is not None:
            result[value.guest_controller] = value.guest
        for owner, actor in result.items():
            if (
                resolve(
                    state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                ).controller
                != owner
            ):
                raise WorkflowError("Recover the original source person and actual controller")
        return result

    def _view(
        self,
        c: Connection,
        viewer: GuildViewer,
        state: GameState,
        value: CallSession,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        if viewer.user_id not in set(value.table) | {value.controller, value.guest_controller}:
            raise WorkflowError("This actual source correspondence belongs to its original humans")
        result = dict(
            id=value.id,
            revision=value.revision,
            kind=value.kind,
            phase=value.phase,
            source_action=value.source_action,
            account=value.account
            if viewer.user_id in (value.controller, value.guest_controller)
            else "",
            guest=value.guest.model_dump(mode="json") if value.guest else None,
            can_act=self._can_act(value, action, viewer.user_id),
            own=value.controller == viewer.user_id,
            guest_owner=value.guest_controller == viewer.user_id,
            message=value.message
            if viewer.user_id in (value.controller, value.guest_controller)
            else "",
            answer=value.answer
            if viewer.user_id in (value.controller, value.guest_controller)
            else "",
            option=value.option,
            replies=json.loads(value.replies_json),
            table=list(value.table),
        )
        if (
            value.phase == "effect"
            and value.guest is not None
            and viewer.user_id == value.guest_controller
        ):
            assets, identities = self._resources(state, value.guest)
            result.update(
                options=self._options(state, value, action),
                assets=[dict(id=x.id, label=x.name) for x in assets if not x.void],
                identities=[dict(id=x.id, label=x.name) for x in identities if not x.protected],
            )
            from girlframe.services.m3_janus_storage import available as storage_available

            result["storage_available"] = storage_available(self.game, c, state, value.guest)
        if value.phase == "npc" and value.guest is not None:
            result["npcs"] = (
                [
                    dict(id=x.id, label=x.name)
                    for x in state.world.npcs
                    if x.id in dive.nearby(state, value.guest, _cast_npcs(action))
                ]
                if state.world
                else []
            )
        if value.effect_json and (
            viewer.user_id == value.guest_controller
            or value.phase == "table"
            and viewer.user_id in value.table
        ):
            result["effect"] = json.loads(value.effect_json)
        return result

    @staticmethod
    def _can_act(value: CallSession, action: dict[str, Any], owner: int) -> bool:
        if value.phase == "complete":
            return False
        if value.phase in ("invite", "effect"):
            return owner == value.guest_controller
        if value.phase == "table":
            return owner in value.table and str(owner) not in json.loads(value.replies_json)
        if value.phase == "npc":
            return owner == int(action["data"]["dive"]["handler_controller"])
        return False

    @staticmethod
    def _resources(state: GameState, actor: ActorRef) -> tuple[Any, Any]:
        if actor.kind == "pilot" or actor.kind == "external_pilot":
            return dive.resources(state, actor)
        if actor.kind == "handler":
            context = next(
                (x for x in state.director_contexts if x.active and x.id == actor.incarnation), None
            )
            if context is not None:
                from girlframe.engine.m3_mockingbird_sex import assets

                return tuple(
                    x for x in assets(state, actor) if x.family == "girl"
                ), context.identities
        return (), ()

    def _options(self, state: GameState, value: CallSession, action: dict[str, Any]) -> list[str]:
        assert value.guest is not None
        assets, identities = self._resources(state, value.guest)
        result = []
        # Every choice uses that guest's actual existing mechanical resources.
        if any(not x.void for x in assets):
            result.append("void_and_unmark_all")
        if any(not x.protected for x in identities):
            result += ["erase_identity_and_table_question", "table_replaces_identity"]
        if dive.nearby_all(
            state,
            value.guest,
            tuple(
                x["actor"]["entity"]
                for x in action["data"]["dive"]["cast"]["roles"]
                if x["actor"]["kind"] == "npc"
            ),
        ):
            result.append("nearby_npcs_gain_void")
        if value.passenger and physical.passenger_view(state, value.guest):
            result.append("locked_cockpit_extraction_requires_frame_consent")
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value, action = self._source(c, state, identity)
            return self._view(c, viewer, state, value, action)

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        def write(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, action = self._source(c, state, identity)
            self._roles(c, state, value)
            from girlframe.services.m3_dive import authorize

            authorize(self.game, c, viewer, action)
            if value.revision != revision or not self._can_act(value, action, viewer.user_id):
                raise WorkflowError("Reopen your own current original Call response")
            if action["state"] == "aborted":
                raise WorkflowError("Recover the original held Dive before continuing this Call")
            event = str(uuid4())
            allowed_fields = {
                "invite": {"account"},
                "effect": {
                    "account",
                    "option",
                    "asset",
                    "description",
                    "identity",
                    "question",
                    "replacement",
                },
                "npc": {"account", "manifestations"},
                "table": {"account", "accepted"},
            }.get(value.phase, set())
            if set(data) - allowed_fields or (
                "accepted" in data and type(data["accepted"]) is not bool
            ):
                raise WorkflowError("Supply only your actual current owned Call choice fields")
            account = str(data.get("account", "")).strip()
            if not account or len(account) > 1200:
                raise WorkflowError("Describe only your own actual source choice")
            if value.phase == "invite":
                if operation not in ("accept", "decline"):
                    raise WorkflowError("Accept or decline only this actual invitation")
                if operation == "decline":
                    value = value.model_copy(
                        update={"phase": "complete", "answer": account, "completed_event": event}
                    )
                    if value.passenger:
                        state.passengers = [
                            x.model_copy(update={"state": "declined"})
                            if x.id == value.passenger
                            else x
                            for x in state.passengers
                        ]
                elif value.kind == "relay":
                    value = value.model_copy(
                        update={"phase": "complete", "answer": account, "completed_event": event}
                    )
                else:
                    passenger = next(x for x in state.passengers if x.id == value.passenger)
                    passenger = passenger.model_copy(update={"accepted_event": event})
                    state = physical.board(
                        state, profiles(c, self.store.campaign_id), passenger, event, account
                    )
                    value = value.model_copy(update={"phase": "effect"})
            elif value.phase == "effect":
                value, state = self._effect(
                    c, state, action, value, viewer, operation, data, event, account
                )
            elif value.phase == "npc":
                if operation != "npc" or not isinstance(data.get("manifestations"), dict):
                    raise WorkflowError("The actual source Handler chooses each NPC manifestation")
                effect = Effect(
                    account=account,
                    npcs=tuple(
                        NpcVoid(npc=k, manifestation=v) for k, v in data["manifestations"].items()
                    ),
                )
                value = value.model_copy(update={"effect_json": effect.model_dump_json()})
                state = self._apply(c, state, action, value, event)
                value = value.model_copy(update={"phase": "complete", "completed_event": event})
            elif value.phase == "table":
                responses = json.loads(value.replies_json)
                if operation != "table":
                    raise WorkflowError("Answer only the actual original table question/proposal")
                responses[str(viewer.user_id)] = dict(
                    accepted=bool(data.get("accepted")), account=account
                )
                value = value.model_copy(
                    update={"replies_json": json.dumps(responses, sort_keys=True)}
                )
                if len(responses) == len(value.table):
                    if value.option == "table_replaces_identity" and not all(
                        x["accepted"] for x in responses.values()
                    ):
                        value = value.model_copy(
                            update={
                                "phase": "effect",
                                "option": None,
                                "effect_json": None,
                                "replies_json": "{}",
                            }
                        )
                    else:
                        if value.option == "table_replaces_identity":
                            state = self._apply(c, state, action, value, event)
                        value = value.model_copy(
                            update={"phase": "complete", "completed_event": event}
                        )
            value = value.model_copy(update={"revision": value.revision + 1})
            _save(state, value)
            action["data"]["response_event"] = event
            if value.phase == "complete":
                self._finish(c, state, action, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.call_response",
                state,
                event_id=event,
                session_id=value.id,
                source_action=action["id"],
                operation=operation,
            )
            self.game.save_action(c, action)
            from girlframe.services.m3_dive import synchronize

            synchronize(self.game, c, action, event)
            synchronize_guest_girl(self.game, c, action, event, viewer, key)
            self._source_callbacks(c, action, event, viewer, key)
            return self._view(c, viewer, state, value, action)

        return self.store._write(
            viewer,
            key,
            "m3.call_response",
            dict(id=identity, revision=revision, operation=operation, data=data),
            write,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )

    def _effect(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        value: CallSession,
        viewer: GuildViewer,
        operation: str,
        data: dict[str, Any],
        event: str,
        account: str,
    ) -> tuple[CallSession, GameState]:
        if operation == "decline_effect":
            # Printed p33 makes the boarded guest's extra choice optional. This is
            # not invitation refusal: keep the real passenger and their resources.
            # Only the unapplied effect phase reaches here through guest ownership.
            if set(data) != {"account"} or value.option is not None or value.effect_json:
                raise WorkflowError("Decline only an unapplied optional guest choice")
            return value.model_copy(
                update={
                    "phase": "complete",
                    "answer": account,
                    "choice_event": event,
                    "completed_event": event,
                }
            ), state
        if operation != "effect" or data.get("option") not in self._options(state, value, action):
            raise WorkflowError("Choose one actually available original guest consequence")
        option = str(data["option"])
        assert value.guest is not None
        effect = Effect(
            account=account,
            asset=data.get("asset"),
            description=str(data.get("description", "")),
            identity=data.get("identity"),
            question=str(data.get("question", "")),
            replacement=str(data.get("replacement", "")),
        )
        value = value.model_copy(
            update={
                "option": option,
                "effect_json": effect.model_dump_json(),
                "choice_event": event,
                "store_void": data.get("storage") is True,
            }
        )
        if option == "table_replaces_identity":
            # Preview pure validation first, then actual table-owned agreement before commit.
            self._apply(c, state, action, value, event)
            return value.model_copy(
                update={"phase": "table", "proposal_revision": value.proposal_revision + 1}
            ), state
        if option == "nearby_npcs_gain_void":
            return value.model_copy(update={"phase": "npc"}), state
        state = self._apply(c, state, action, value, event)
        pending_threshold = any(
            x.get("call_session") == value.id for x in action["data"]["dive"]["followups"]
        )
        return value.model_copy(
            update={
                "phase": "threshold"
                if pending_threshold
                else "table"
                if option == "erase_identity_and_table_question"
                else "complete",
                "completed_event": None if option == "erase_identity_and_table_question" else event,
            }
        ), state

    def _apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        value: CallSession,
        event: str,
    ) -> GameState:
        assert value.guest is not None and value.option is not None and value.effect_json
        effect = Effect.model_validate_json(value.effect_json)
        from girlframe.services.m3_janus_storage import gain_source

        storage = gain_source(
            self.game, c, state, value.guest, value.id, "call_guest", value.store_void
        )
        if value.option == "locked_cockpit_extraction_requires_frame_consent":
            return physical.subsume(state, value.passenger or "", event, effect.account)
        if value.guest.kind not in ("pilot", "external_pilot"):
            if value.option == "void_and_unmark_all" and value.guest.kind == "handler":
                from girlframe.engine.m3_mockingbird_sex import update_assets

                actual, _ = self._resources(state, value.guest)
                chosen = next((x for x in actual if x.id == effect.asset and not x.void), None)
                if chosen is None or not effect.description.strip():
                    raise WorkflowError("Rewrite your own actual uncorrupted Girl Asset")
                from girlframe.engine.m3_mockingbird_sex import assets as all_assets

                changed = update_assets(
                    state,
                    value.guest,
                    tuple(
                        x.model_copy(update={"void": True, "description": effect.description})
                        if x.id == chosen.id
                        else x
                        for x in all_assets(state, value.guest)
                    ),
                    event,
                )
                girl_context = next(
                    x
                    for x in changed.director_contexts
                    if x.active and x.id == value.guest.incarnation
                )
                girl_context.identities = [
                    x.model_copy(update={"marked": False}) for x in girl_context.identities
                ]
                girls, _ = self._resources(changed, value.guest)
                if girls and all(x.void for x in girls):
                    stage_guest_girl(self.game, c, changed, action, value, event, chosen.id)
                return changed
            if value.option in ("erase_identity_and_table_question", "table_replaces_identity"):
                from girlframe.engine.m3_leviathan_obsession import require_identity_change

                require_identity_change(state, value.guest, (effect.identity or "",))
                context = next(
                    (
                        x
                        for x in state.director_contexts
                        if x.active and x.id == value.guest.incarnation
                    ),
                    None,
                )
                identity = (
                    next(
                        (
                            x
                            for x in context.identities
                            if x.id == effect.identity and not x.protected
                        ),
                        None,
                    )
                    if context
                    else None
                )
                if (
                    identity is None
                    or (
                        value.option == "table_replaces_identity" and not effect.replacement.strip()
                    )
                    or (
                        value.option == "erase_identity_and_table_question"
                        and not effect.question.strip()
                    )
                ):
                    raise WorkflowError(
                        "Choose an actual ordinary guest Identity and source table detail"
                    )
                assert context is not None
                changed = GameState.model_validate_json(state.model_dump_json())
                target = next(x for x in changed.director_contexts if x.id == context.id)
                target.identities = [
                    x.model_copy(update={"name": effect.replacement.strip()})
                    if x.id == identity.id
                    else x
                    for x in target.identities
                    if x.id != identity.id or value.option != "erase_identity_and_table_question"
                ]
                changed.facts.append(
                    dict(
                        kind="call_guest_identity",
                        session=value.id,
                        event=event,
                        actor=value.guest.model_dump_json(),
                        option=value.option,
                    )
                )
                return changed
            if value.option == "nearby_npcs_gain_void":
                from girlframe.engine.m3_mockingbird_sex import npc_void

                expected = dive.nearby(state, value.guest, _cast_npcs(action))
                if (
                    not expected
                    and not dive.nearby_directors(state, value.guest, _cast_npcs(action))
                ) or {x.npc for x in effect.npcs} != set(expected):
                    raise WorkflowError("Choose one actual manifestation for every real nearby NPC")
                changed = state
                for entry in effect.npcs:
                    changed = npc_void(
                        changed,
                        ActorRef(kind="npc", entity=entry.npc),
                        entry.manifestation,
                        None,
                        action["data"]["dive"]["handler_controller"],
                        action["id"],
                        event,
                    )
                self._stage_directors(c, changed, action, value, event)
                return changed
            raise WorkflowError("Use an actual available guest-owned resource consequence")
        outcome = dive.apply(
            state,
            value.guest,
            profiles(c, self.store.campaign_id),
            value.option,
            effect,
            action["id"],
            1000 + value.step,
            event,
            piloting=False,
            handler=ActorRef.model_validate(action["data"]["dive"]["handler"])
            if action["data"]["dive"]["handler"]
            else None,
            cast_npcs=_cast_npcs(action),
            handler_controller=action["data"]["dive"].get(
                "judge_controller", action["data"]["dive"].get("handler_controller")
            ),
            storage=storage,
        )
        if value.option == "nearby_npcs_gain_void":
            self._stage_directors(c, outcome.state, action, value, event)
        if outcome.followups:
            outcome.state.facts.append(
                dict(
                    kind="call_guest_void",
                    session=value.id,
                    event=event,
                    actor=value.guest.model_dump_json(),
                    option=value.option,
                )
            )
            for index, followup in enumerate(outcome.followups):
                family = "girl" if followup.kind == "girl_void_threshold" else "frame"
                work_id = "call-void:" + value.id + ":" + str(index)
                item = dict(
                    id=work_id,
                    owner=value.guest.model_dump(mode="json"),
                    character=value.guest.incarnation,
                    source_action=action["id"],
                    source_choice=value.source_choice,
                    step=value.step,
                    details=dict(family=family),
                    source_pdf=19,
                    reason="call_guest",
                    call_session=value.id,
                    source_event=event,
                    immediate=True,
                )
                self.game.request(
                    c,
                    action,
                    value.guest_controller,
                    "dive_void_threshold",
                    dict(step=value.step, work_id=work_id, owner=item["owner"]),
                )
                item["continuation"] = next(
                    x["id"]
                    for x in self.game.pending(c, action["id"])
                    if x["kind"] == "dive_void_threshold"
                    and json.loads(x["body_json"])["work_id"] == work_id
                )
                action["data"]["dive"]["followups"].append(item)
        return outcome.state

    def _stage_directors(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        value: CallSession,
        event: str,
    ) -> None:
        assert value.guest is not None
        actual = dive.nearby_directors(state, value.guest, _cast_npcs(action))
        if not actual:
            return
        from girlframe.services.m3_dive_handler_void import stage

        state.facts.append(
            dict(
                kind="call_guest_director_void",
                session=value.id,
                event=event,
                actor=value.guest.model_dump_json(),
                choice_event=value.choice_event or "",
            )
        )
        stage(
            self.game,
            c,
            state,
            action,
            source_choice=value.source_choice,
            step=1000 + value.step,
            actor=value.guest,
            candidates=actual,
            event=event,
        )

    def _source_callbacks(
        self,
        c: Connection,
        action: dict[str, Any],
        event: str,
        viewer: GuildViewer | None,
        key: str,
    ) -> None:
        if action["state"] != "complete":
            return
        if action["data"].get("dormant_dive_source"):
            from girlframe.services.m3_battle_dormant import complete_dive

            complete_dive(self.game, c, action, event, viewer, key)
        if action["data"].get("battle_counter_source"):
            from girlframe.services.m3_battle import complete_counter_play

            complete_counter_play(self.game, c, action, event, viewer, key)
        if action["data"].get("gorgon_counter_source"):
            from girlframe.services.m3_gorgon_play import complete_response

            complete_response(self.game, c, action, event, viewer, key)

    def _finish(
        self, c: Connection, state: GameState, action: dict[str, Any], value: CallSession
    ) -> None:
        rows = [
            x
            for x in self.game.pending(c, action["id"])
            if x["kind"] == "dive_call" and json.loads(x["body_json"]).get("session") == value.id
        ]
        if len(rows) != 1:
            raise WorkflowError("Recover the exact actual held Call continuation")
        choices = t.m2["m2_choices"]
        c.execute(
            choices.update()
            .where(choices.c.campaign_id == self.store.campaign_id, choices.c.id == rows[0]["id"])
            .values(state="completed_by_work")
        )
        from girlframe.services.m3_dive import _complete_step

        _complete_step(self.game, c, state, action, value.step)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in state.mockingbird.calls:
            if value.phase == "complete" or (
                viewer.user_id not in (value.controller, value.guest_controller)
                and not (value.phase == "table" and viewer.user_id in value.table)
                and not (value.phase == "npc" and viewer.user_id in value.table)
            ):
                continue
            value, action = self._source(c, state, value.id)
            result.append(
                dict(
                    id=value.id,
                    state=value.phase,
                    actionable=self._can_act(value, action, viewer.user_id),
                )
            )
        return result


GIRL_KIND = "call_guest_handler_girl_void"


def stage_guest_girl(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: CallSession,
    event: str,
    asset: str,
) -> None:
    from girlframe.engine.m3_handler_girl_void import require
    from girlframe.services.m3_medical import MedicalService

    assert value.guest is not None and value.guest_controller is not None
    work = "call-girl-void:" + value.id
    meta = action["data"]["dive"]
    _, appointment = MedicalService(game.store)._handler(c)
    judge = ActorRef.model_validate(meta["handler"]) if meta["handler"] else None
    changed, episode = require(
        state,
        value.guest,
        work=work,
        event=event,
        appointment=appointment,
        judge=meta["handler_controller"],
        judge_actor=judge,
        caster=value.guest,
        caster_controller=value.guest_controller,
    )
    _copy(state, changed)
    continuation = game.request(c, action, value.guest_controller, GIRL_KIND, dict(work_id=work))
    body = dict(
        id=work,
        kind=GIRL_KIND,
        owner=value.guest.model_dump(mode="json"),
        character=value.guest.incarnation,
        controller=value.guest_controller,
        caster=value.guest.model_dump(mode="json"),
        caster_controller=value.guest_controller,
        source_action=action["id"],
        source_choice=value.source_choice,
        source_event=event,
        source_pdf=19,
        call_session=value.id,
        step=value.step,
        appointment=appointment,
        context_source=next(x.context_source for x in state.handler_girl_void if x.id == episode),
        judge=meta["handler_controller"],
        judge_actor=meta["handler"],
        continuation=continuation,
        asset=asset,
        immediate=True,
    )
    meta.setdefault("guest_girl_followups", []).append(body)
    state.facts.append(
        dict(
            kind=GIRL_KIND,
            session=value.id,
            event=event,
            owner=value.guest.model_dump_json(),
            asset=asset,
            body=json.dumps(body, sort_keys=True),
        )
    )


def synchronize_guest_girl(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None = None,
    key: str | None = None,
) -> None:
    from girlframe.services.m3_work import related

    works = t.m3["m3_required_work"]
    for body in action["data"]["dive"].get("guest_girl_followups", ()):
        if c.scalar(
            sa.select(works.c.id).where(
                works.c.campaign_id == game.store.campaign_id, works.c.id == body["id"]
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            body["id"],
            body["controller"],
            body["controller"],
            GIRL_KIND,
            body,
            body["source_event"],
        )
        from girlframe.services.m3_handler_girl_void import finish_initial_allure

        finish_initial_allure(game, c, body["id"], body["source_event"], viewer, key or event)


def prove_guest_girl_void(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    state = GameState.model_validate_json(raw) if raw else None
    if state is None:
        raise WorkflowError("Recover the actual original guest's Girl Void effect")
    value, action = CallService(game)._source(c, state, body["call_session"])
    actual = next(
        (
            x
            for x in action["data"]["dive"].get("guest_girl_followups", ())
            if x["id"] == first["id"]
        ),
        None,
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .first()
    )
    episode = next((x for x in state.handler_girl_void if x.work == first["id"]), None)
    fact = next(
        (
            x
            for x in state.facts
            if x.get("kind") == GIRL_KIND
            and x.get("session") == value.id
            and x.get("event") == first["event_id"]
        ),
        None,
    )
    if (
        first["kind"] != GIRL_KIND
        or first["revision"] != 1
        or first["owner_id"] != str(value.guest_controller)
        or first["subject_id"] != str(value.guest_controller)
        or actual is None
        or actual != body
        or fact is None
        or json.loads(fact["body"]) != body
        or event is None
        or event["kind"] != "m3.call_response"
        or event["actor_id"] != str(value.guest_controller)
        or value.guest != actor
        or value.option != "void_and_unmark_all"
        or value.choice_event != first["event_id"]
        or episode is None
        or episode.actor != actor
        or episode.caster != actor
        or episode.phase != "allure"
        or episode.corruption_event != first["event_id"]
        or episode.assigned_frame is not None
    ):
        raise WorkflowError(
            "SOURCE_GUEST_GIRL_VOID_MISSING: actual self-chosen existing Asset "
            "and real source allure required"
        )
    from girlframe.engine.m3_handler_girl_void import girl_assets

    assets = girl_assets(state, actor)
    effect = Effect.model_validate_json(value.effect_json or "{}")
    if (
        not assets
        or not all(x.void for x in assets)
        or effect.asset != body["asset"]
        or not any(x.id == effect.asset and x.description == effect.description for x in assets)
    ):
        raise WorkflowError("Prove the guest's actual selected corruption and sole Asset authority")


def complete_guest_girl_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services.m3_handler_girl_void import completed_effect

    completed_effect(game, c, identity, event)
    state = load_state(c, game.store.campaign_id)
    works = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(works)
            .where(works.c.campaign_id == game.store.campaign_id, works.c.id == identity)
            .order_by(works.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    choices = t.m2["m2_choices"]
    updated = c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == body["continuation"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    if not updated.rowcount:
        return
    from girlframe.services.m3_dive import _next

    _next(game, c, state, action)
    game.save_action(c, action)
    author = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    previous = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    if author is None:
        raise WorkflowError("Recover the actual completing guest physiology event")
    saved = game.event(
        c,
        viewer.user_id if viewer else int(author),
        key,
        "m3.call_guest_allure_completed",
        state,
        event_index=0 if previous is None else previous + 1,
        work_id=identity,
        source_action=action["id"],
    )
    CallService(game)._source_callbacks(c, action, saved, viewer, key)


def prove_director_guest_source(
    game: "GameService",
    c: Connection,
    source_action: str,
    source_choice: str,
    step: int,
    event: str,
    actor: ActorRef,
    target: ActorRef,
) -> None:
    def snapshot(source_event: str) -> GameState:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source_event,
            )
        )
        if not raw:
            raise WorkflowError("Recover the actual guest-owned choice source")
        return GameState.model_validate_json(raw)

    source = snapshot(event)
    value = next(
        (
            x
            for x in source.mockingbird.calls
            if x.source_action == source_action
            and x.source_choice == source_choice
            and 1000 + x.step == step
            and x.guest == actor
        ),
        None,
    )
    if value is None or not value.choice_event:
        raise WorkflowError("Prove the actual original guest and chosen NPC consequence")
    _, action = CallService(game)._source(c, source, value.id)
    selected = snapshot(value.choice_event)
    prior = next((x for x in selected.mockingbird.calls if x.id == value.id), None)
    audit = {
        x["id"]: x
        for x in c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id.in_((event, value.choice_event)),
            )
        ).mappings()
    }
    chosen, effect = audit.get(value.choice_event), audit.get(event)
    if (
        prior is None
        or prior.phase != "npc"
        or prior.option != "nearby_npcs_gain_void"
        or prior.choice_event != value.choice_event
        or value.option != prior.option
        or chosen is None
        or chosen["kind"] != "m3.call_response"
        or chosen["actor_id"] != str(value.guest_controller)
        or effect is None
        or effect["kind"] != "m3.call_response"
        or effect["actor_id"] != str(action["data"]["dive"]["handler_controller"])
        or target not in dive.nearby_directors(source, actor, _cast_npcs(action))
        or not any(
            x.get("kind") == "call_guest_director_void"
            and x.get("session") == value.id
            and x.get("event") == event
            and x.get("actor") == actor.model_dump_json()
            for x in source.facts
        )
    ):
        raise WorkflowError(
            "SOURCE_GUEST_DIRECTOR_MISSING: actual guest chooses; "
            "original judge records actual changes"
        )


def prove_call_guest_void(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    if source is None:
        raise WorkflowError("Recover the actual guest-owned Void source effect")
    value, action = CallService(game)._source(c, source, body["call_session"])
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .first()
    )
    actual = next((x for x in action["data"]["dive"]["followups"] if x["id"] == first["id"]), None)
    fact = next(
        (
            x
            for x in source.facts
            if x.get("kind") == "call_guest_void"
            and x.get("session") == value.id
            and x.get("event") == first["event_id"]
            and x.get("actor") == actor.model_dump_json()
        ),
        None,
    )
    if (
        event is None
        or event["kind"] != "m3.call_response"
        or event["actor_id"] != str(value.guest_controller)
        or value.guest != actor
        or value.kind != "guest"
        or value.option != "void_and_unmark_all"
        or value.phase != "threshold"
        or actual is None
        or fact is None
        or body != actual
        or first["event_id"] != body["source_event"]
        or first["owner_id"] != str(value.guest_controller)
        or first["subject_id"] != str(value.guest_controller)
        or first["scene_id"] != action["scene_id"]
        or first["campaign_context"]
    ):
        raise WorkflowError(
            "SOURCE_CALL_VOID_MISSING: prove the original guest's actual chosen corruption"
        )


def complete_call_guest_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.engine.m3_void import FINAL

    works = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(works)
            .where(works.c.campaign_id == game.store.campaign_id, works.c.id == identity)
            .order_by(works.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["state"] != "resolved":
        raise WorkflowError("Complete the actual guest Void consequence first")
    body = json.loads(row["body_json"])
    state = load_state(c, game.store.campaign_id)
    service = CallService(game)
    value, action = service._source(c, state, body["call_session"])
    threshold = next(
        (
            x
            for x in state.void_thresholds
            if identity in x.source_works and x.actor == value.guest and x.stage in FINAL
        ),
        None,
    )
    actual = next((x for x in action["data"]["dive"]["followups"] if x["id"] == identity), None)
    if threshold is None or actual is None or actual["continuation"] != body["continuation"]:
        raise WorkflowError("Recover the exact original guest's actual completed threshold")
    if actual.get("completed_event"):
        return
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == actual["continuation"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    actual["completed_event"] = event
    if all(
        x.get("completed_event")
        for x in action["data"]["dive"]["followups"]
        if x.get("call_session") == value.id
    ):
        value = value.model_copy(
            update={"phase": "complete", "completed_event": event, "revision": value.revision + 1}
        )
        _save(state, value)
        action["data"]["response_event"] = event
        service._finish(c, state, action, value)
    game.save_action(c, action)
    previous = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    from girlframe.services.m3_janus_storage import continuation_actor

    saved = game.event(
        c,
        continuation_actor(game, c, event, viewer),
        key,
        "m3.call_void_completed",
        state,
        event_index=0 if previous is None else previous + 1,
        session_id=value.id,
        work_id=identity,
        source_action=action["id"],
    )
    service._source_callbacks(c, action, saved, viewer, key)
