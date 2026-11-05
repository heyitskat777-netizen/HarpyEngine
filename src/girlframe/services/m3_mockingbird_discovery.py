"""Actual witnessed discovery; backend/private knowledge never counts as finding out."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_mockingbird_state import Discovery, Exposure
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _handler(action: dict[str, Any]) -> tuple[ActorRef, int]:
    meta = action["data"]["mockingbird"]
    ref = meta.get("judge") or action["data"].get("tag_context", {}).get("handler")
    if ref is None:
        raise WorkflowError(
            "This source needs its actual original fictional Handler, not an OOC proxy"
        )
    return ActorRef.model_validate(ref), int(meta["judge_controller"])


def bind_exposures(state: GameState, action: dict[str, Any]) -> None:
    actor, controller = _handler(action)
    state.mockingbird = state.mockingbird.model_copy(
        update={
            "exposures": tuple(
                value.model_copy(update={"handler": actor, "handler_controller": controller})
                if value.source_action == action["id"] and value.handler is None
                else value
                for value in state.mockingbird.exposures
            )
        }
    )


def _living(state: GameState, ref: ActorRef) -> ActorRef:
    if ref.kind == "pilot":
        sheet = state.sheets.get(ref.entity)
        if sheet is None or sheet.character_id != ref.incarnation:
            converted = next(
                (
                    ActorRef(kind="external_pilot", entity=x.id)
                    for x in state.harpy_states
                    if x.alive
                    and rules.same_person(state, ref, ActorRef(kind="external_pilot", entity=x.id))
                ),
                None,
            )
            if converted is None:
                raise WorkflowError(
                    "This original person ended; a successor does not inherit the effect"
                )
            return converted
    return ref


class DiscoveryService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, state: GameState, identity: str
    ) -> tuple[Exposure, dict[str, Any]]:
        exposure = next((x for x in state.mockingbird.exposures if x.id == identity), None)
        if exposure is None:
            raise WorkflowError("Recover the original source-bound exposure, not a label")
        action = self.game.action(c, exposure.source_action)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == exposure.source_event,
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        original = (
            next((x for x in proof.mockingbird.exposures if x.id == identity), None)
            if proof
            else None
        )
        receipt = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        from girlframe.services.m3_mockingbird_effects import source_trigger

        if proof is None:
            raise WorkflowError("Recover the actual original source history")
        handler, handler_controller = source_trigger(self.game, c, action, proof)
        if exposure.handler is None:
            exposure = exposure.model_copy(
                update={"handler": handler, "handler_controller": handler_controller}
            )
        actor = ActorRef.model_validate(action["data"]["mockingbird"]["actor"])
        target = ActorRef.model_validate(action["data"]["mockingbird"]["parties"][0]["actor"])
        if (
            original is None
            or action["data"]["play"] != "mockingbird_sex"
            or receipt is None
            or json.loads(receipt) != action["data"]["receipt"]
            or exposure.actor != actor
            or exposure.counterpart != target
            or (exposure.handler, exposure.handler_controller) != _handler(action)
            or any(
                getattr(original, k) != getattr(exposure, k)
                for k in (
                    "id",
                    "source_action",
                    "actor",
                    "counterpart",
                    "kind",
                    "source_event",
                )
            )
        ):
            raise WorkflowError(
                "Recover the actual original intimacy exposure and immutable receipt"
            )
        expected_tier = {"low_tag": "low", "teaching": "mid", "both_risk": "high"}[exposure.kind]
        actual_receipt = json.loads(receipt)
        total = actual_receipt["pre_total"] + sum(x["amount"] for x in action["data"]["modifiers"])
        from girlframe.engine.m2 import tier

        if tier(total) != expected_tier:
            raise WorkflowError("An exposure label cannot replace its actual printed result tier")
        if exposure.kind == "low_tag" and not any(
            x.subject == actor and x.foe == target and exposure.source_event in x.source_events
            for x in proof.helpless_conditions
        ):
            raise WorkflowError("Prove the original actual low-result Helpless consequence")
        if exposure.kind == "teaching" and not any(
            x.get("kind") == "mockingbird_suppression"
            and x.get("action") == action["id"]
            and x.get("event") == exposure.source_event
            and x.get("actor") == target.model_dump_json()
            for x in proof.facts
        ):
            raise WorkflowError("Prove actual source teaching/suppression, not a risk label")
        if exposure.kind == "both_risk" and not any(
            x.get("kind")
            in (
                "mockingbird_sex_effect",
                "mockingbird_handler_void_source",
                "mockingbird_handler_girl_void_source",
                "mockingbird_already_void",
            )
            and x.get("action") == action["id"]
            and x.get("event") == exposure.source_event
            for x in proof.facts
        ):
            raise WorkflowError(
                "Prove the actual high source infection or physiological consequence"
            )
        return exposure, action

    def _case(self, c: Connection, state: GameState, identity: str) -> Discovery:
        value = next((x for x in state.mockingbird.discoveries if x.id == identity), None)
        if value is None:
            raise WorkflowError("This actual original discovery request is unavailable")
        self._source(c, state, value.exposure)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        original = (
            next((x for x in proof.mockingbird.discoveries if x.id == identity), None)
            if proof
            else None
        )
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            original is None
            or audit is None
            or audit["kind"] != "m3.mockingbird_discovery_reported"
            or audit["actor_id"] != str(value.recorder)
            or json.loads(audit["payload_json"]).get("case_id") != identity
            or any(
                getattr(original, k) != getattr(value, k)
                for k in (
                    "id",
                    "exposure",
                    "source_event",
                    "recorder",
                    "witness",
                    "witness_controller",
                    "scene",
                    "cast_sha256",
                    "account",
                )
            )
        ):
            raise WorkflowError("Recover the actual signed discovery declaration")
        return value

    def _save(self, state: GameState, value: Discovery) -> None:
        state.mockingbird = state.mockingbird.model_copy(
            update={
                "discoveries": tuple(
                    value if x.id == value.id else x for x in state.mockingbird.discoveries
                )
            }
        )

    def preview(self, viewer: GuildViewer, exposure_id: str, channel: int) -> dict[str, Any]:
        from girlframe.services.m3_battle import _cast
        from girlframe.services.m3_enforcement_initiative import _known_target

        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            exposure, action = self._source(c, state, exposure_id)
            owners = {
                int(action["actor_id"]),
                *(x["controller"] for x in action["data"]["mockingbird"]["parties"]),
            }
            if viewer.user_id not in owners:
                raise WorkflowError(
                    "Only actual source participants may propose disclosing this private source"
                )
            cast = _cast(self.game, c, state, channel)
            return dict(
                exposure=exposure.id,
                kind=exposure.kind,
                revision=state.revision,
                witnesses=[
                    dict(
                        ref=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        label=resolve(
                            state,
                            x.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        ).label,
                    )
                    for x in cast.roles
                    if _known_target(state, exposure.actor, x.actor, x.controller)
                ],
            )

    def report(
        self,
        viewer: GuildViewer,
        key: str,
        exposure_id: str,
        channel: int,
        witness: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast
            from girlframe.services.m3_enforcement_initiative import _known_target

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            exposure, action = self._source(c, state, exposure_id)
            owners = {
                int(action["actor_id"]),
                *(x["controller"] for x in action["data"]["mockingbird"]["parties"]),
            }
            if viewer.user_id not in owners or not account.strip() or len(account) > 1200:
                raise WorkflowError(
                    "Declare actual discovery of only this private source you participated in"
                )
            if any(
                x.exposure == exposure_id and x.phase not in ("declined", "ended")
                for x in state.mockingbird.discoveries
            ):
                raise WorkflowError(
                    "Resume the actual existing discovery report; do not duplicate it"
                )
            cast = _cast(self.game, c, state, channel)
            role = next((x for x in cast.roles if x.actor == witness), None)
            if role is None:
                raise WorkflowError("Use the actual witness currently present in this source scene")
            actual = resolve(
                state, witness, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                not actual.alive
                or actual.controller != role.controller
                or not _known_target(state, exposure.actor, witness, role.controller)
            ):
                raise WorkflowError("Recover the actual witness and their human controller")
            assert exposure.handler is not None and exposure.handler_controller is not None
            event, identity = str(uuid4()), str(uuid4())
            case = Discovery(
                id=identity,
                exposure=exposure.id,
                source_event=event,
                recorder=viewer.user_id,
                witness=witness,
                witness_controller=actual.controller,
                handler=exposure.handler,
                handler_controller=exposure.handler_controller,
                scene=cast.id,
                cast_sha256=fingerprint(cast),
                account=account.strip(),
            )
            state.mockingbird = state.mockingbird.model_copy(
                update={"discoveries": (*state.mockingbird.discoveries, case)}
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_discovery_reported",
                state,
                event_id=event,
                case_id=identity,
            )
            return dict(id=identity, phase=case.phase)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_discovery_reported",
            dict(
                exposure=exposure_id,
                channel=channel,
                witness=witness.model_dump(mode="json"),
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = self._case(c, state, identity)
            exposure, action = self._source(c, state, value.exposure)
            owners = {
                int(action["actor_id"]),
                *(x["controller"] for x in action["data"]["mockingbird"]["parties"]),
                value.witness_controller,
                value.handler_controller,
            }
            if viewer.user_id not in owners:
                raise WorkflowError(
                    "This source disclosure is private to its actual human participants"
                )
            return dict(
                body=value.model_dump(mode="json"),
                kind=exposure.kind,
                can_witness=value.phase == "witness" and viewer.user_id == value.witness_controller,
                can_handler=value.phase == "handler" and viewer.user_id == value.handler_controller,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
        *,
        tag: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.engine.m3_handler_tags import current as current_handler
            from girlframe.services.m3_harpy_defeat import ended_actor_source

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._case(c, state, identity)
            exposure, action = self._source(c, state, value.exposure)
            if (
                value.revision != revision
                or value.phase not in ("witness", "handler")
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual pending discovery request")
            event = str(uuid4())
            if value.phase == "witness":
                if viewer.user_id != value.witness_controller or tag:
                    raise WorkflowError(
                        "Only the actual original witness can attest actual discovery"
                    )
                actual = _living(state, value.witness)
                if (
                    resolve(
                        state,
                        actual,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                    != viewer.user_id
                ):
                    raise WorkflowError(
                        "A replacement controller cannot answer for this original witness"
                    )
                value = value.model_copy(
                    update=dict(
                        phase="handler" if accept else "declined",
                        witness_event=event,
                        revision=value.revision + 1,
                    )
                )
            else:
                if viewer.user_id != value.handler_controller:
                    raise WorkflowError(
                        "Only this original Handler's human confirms the actual finding"
                    )
                if not current_handler(state, value.handler):
                    if ended_actor_source(self.game, c, state, value.handler) is None:
                        raise WorkflowError(
                            "Prove the original Handler ending; "
                            "do not assign its power to a successor"
                        )
                    value = value.model_copy(
                        update=dict(phase="ended", handler_event=event, revision=value.revision + 1)
                    )
                elif not accept:
                    if tag:
                        raise WorkflowError("An unestablished discovery gives no Tag")
                    value = value.model_copy(
                        update=dict(
                            phase="declined", handler_event=event, revision=value.revision + 1
                        )
                    )
                else:
                    target = _living(state, exposure.counterpart)
                    target_view = resolve(
                        state,
                        target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    tag_id = None
                    if exposure.kind == "low_tag":
                        if not tag.strip() or len(tag) > 120:
                            raise WorkflowError(
                                "The actual original Handler authors the printed conditional Tag"
                            )
                        tag_id = "mock-discovery:" + value.id
                        changed = rules.give_tag(
                            state,
                            profiles(c, self.store.campaign_id),
                            target,
                            value.handler,
                            tag,
                            tag_id,
                            event,
                            tuple(
                                sorted(
                                    {
                                        viewer.user_id,
                                        value.witness_controller,
                                        target_view.controller,
                                    }
                                )
                            ),
                        )
                        for name in GameState.model_fields:
                            setattr(state, name, getattr(changed, name))
                    elif tag:
                        raise WorkflowError(
                            "Risk of Punishment is not an automatic new Tag or Punishment"
                        )
                    state.mockingbird = state.mockingbird.model_copy(
                        update={
                            "exposures": tuple(
                                x.model_copy(
                                    update=dict(
                                        disclosed_event=event,
                                        witness=value.witness,
                                        tag_event=event if tag_id else None,
                                        account=account,
                                    )
                                )
                                if x.id == exposure.id
                                else x
                                for x in state.mockingbird.exposures
                            )
                        }
                    )
                    value = value.model_copy(
                        update=dict(
                            phase="resolved",
                            handler_event=event,
                            tag=tag_id,
                            revision=value.revision + 1,
                        )
                    )
            self._save(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_discovery_answered",
                state,
                event_id=event,
                case_id=identity,
                phase=value.phase,
                accept=accept,
                account=account,
            )
            return dict(id=identity, revision=value.revision, phase=value.phase)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_discovery_answered",
            dict(id=identity, revision=revision, accept=accept, account=account, tag=tag),
            operation,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in state.mockingbird.discoveries:
            exposure, action = self._source(c, state, value.exposure)
            audience = {value.recorder, value.witness_controller, value.handler_controller}
            audience |= {
                int(action["actor_id"]),
                *(x["controller"] for x in action["data"]["mockingbird"]["parties"]),
            }
            if viewer.user_id in audience:
                result.append(
                    dict(
                        id=value.id,
                        kind="mockingbird_discovery",
                        state=value.phase,
                        actionable=value.phase == "witness"
                        and viewer.user_id == value.witness_controller
                        or value.phase == "handler"
                        and viewer.user_id == value.handler_controller,
                    )
                )
        for exposure in state.mockingbird.exposures:
            if exposure.disclosed_event:
                continue
            _, action = self._source(c, state, exposure.id)
            owners = {
                int(action["actor_id"]),
                *(x["controller"] for x in action["data"]["mockingbird"]["parties"]),
            }
            if viewer.user_id in owners:
                result.append(
                    dict(
                        id=exposure.id,
                        kind="mockingbird_exposure",
                        state="undisclosed",
                        actionable=True,
                    )
                )
        return result
