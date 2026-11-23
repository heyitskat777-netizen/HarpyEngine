"""Source-bound discovery and ordinary NPC corruption from Low Void."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_npc_interest as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    event: str,
    npc: str,
    girl_owner: int,
    timing: rules.Timing,
    account: str,
    manifestation: str | None,
) -> None:
    period = strain.periods._get(c, row["off_duty_id"])
    handler = active_handler(state)
    if (
        handler is None
        or girl_owner not in period.pilots
        or any(x.id == row["id"] for x in rules.interests(state))
        or (manifestation is not None) != (timing == "after")
    ):
        raise WorkflowError("Choose the original NPC, Girl and timing for this discovery")
    girl = current_ref(state, girl_owner)
    if period.character_ids.get(girl.entity) != girl.incarnation:
        raise WorkflowError("Choose the original Girl from this Off-Duty roster")
    case = rules.Interest(
        id=row["id"],
        event=event,
        period=period.id,
        npc=ActorRef(kind="npc", entity=npc),
        girl=girl,
        handler=handler,
        timing=timing,
        account=account,
    )
    rules.ordinary_npc(state, case)
    if manifestation is not None:
        case = rules.gain(state, case, manifestation, event)
    rules.save(state, case)


class InterestService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _owned(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Interest:
        case = next((x for x in rules.interests(state) if x.id == identity), None)
        if case is None or str(viewer.user_id) not in (case.handler.entity, case.girl.entity):
            raise WorkflowError("Only the original Handler and discovering Girl see this case")
        return case

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            handler = case.handler.entity == str(viewer.user_id)
            girl = case.girl.entity == str(viewer.user_id)
            return dict(
                revision=state.revision,
                account=case.account if handler else case.seen_account,
                seen_tag=case.seen_tag if girl else None,
                discover=girl and not case.seen_event,
                gain=handler and case.seen_event is not None and not case.gain_event,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        *,
        channel: int | None = None,
        account: str | None = None,
        manifestation: str | None = None,
    ) -> dict[str, Any]:
        if manifestation is None and (
            channel is None or account is None or not 0 < len(account.strip()) <= 1200
        ):
            raise WorkflowError("Describe the actual discovery in its existing scene")
        if manifestation is not None and (channel is not None or account is not None):
            raise WorkflowError("Choose one actual NPC manifestation")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            owner = case.handler.entity if manifestation is not None else case.girl.entity
            if owner != str(viewer.user_id):
                raise WorkflowError("Only the actual owner can make this discovery or Void choice")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            case = self._owned(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                row["state"] != "pending"
                or row["off_duty_id"] != case.period
                or body.get("interest_requested") != case.event
                or body["rule_id"] != rules.RULE
                or self.strain.periods._get(c, case.period).phase != "preparing"
                or case.complete
            ):
                raise WorkflowError("Recover the pending original discovery")
            event = str(uuid4())
            npc = rules.ordinary_npc(state, case)
            if manifestation is not None:
                case = rules.gain(state, case, manifestation, event)
            else:
                assert channel is not None and account is not None
                if case.seen_event is not None or current_ref(state, viewer.user_id) != case.girl:
                    raise WorkflowError("Only the original Girl can discover this NPC once")
                cast, _ = CastService(ActorService(self.strain.missions))._current(
                    c, state, channel
                )
                roles = {(x.actor, x.controller) for x in cast.roles}
                bindings = profiles(c, self.store.campaign_id)
                girl = resolve(state, case.girl, bindings, require_current_profile=False)
                other = resolve(state, case.npc, bindings, require_current_profile=False)
                if (
                    (case.girl, viewer.user_id) not in roles
                    or (case.npc, npc.controller) not in roles
                    or girl.cell is not None
                    and other.cell is not None
                    and girl.cell != other.cell
                ):
                    raise WorkflowError(
                        "Join the original Girl and NPC in the actual discovery scene"
                    )
                observed = next((x.label for x in npc.tags if x.id == case.tag), None)
                if case.timing == "after" and observed is None:
                    raise WorkflowError("Recover the actual original Void manifestation")
                case = case.model_copy(
                    update=dict(
                        seen_event=event,
                        seen_scene=cast.id,
                        seen_account=account.strip(),
                        seen_tag=observed,
                    )
                )
            rules.save(state, case)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_void_interest",
                state,
                event_id=event,
                work_id=identity,
            )
            if case.complete:
                self.strain._save(
                    c, row, event, body | {"interest_completed": event}, resolved=True
                )
            return dict(id=identity, state="resolved" if case.complete else "pending")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.npc_void_interest",
            dict(
                id=identity,
                expected=expected,
                channel=channel,
                account=account,
                manifestation=manifestation,
            ),
            operation,
            authorize,
        )
