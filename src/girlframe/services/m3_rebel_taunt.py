"""Actual off-screen delivery, owned Tag and first recorded Cadre interaction."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_taunt as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_intracadre_marriage import allocation_fields
from girlframe.engine.m3_rebel_escape_offer import speaker
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_intracadre_marriage import allocate_punishment
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

Action = Literal["radio", "tag", "interact"]
EVENT = "m3.rebel_taunt"


def pending(state: GameState, handler: ActorRef | None) -> bool:
    return handler is not None and any(
        x.handler == handler and x.tag_event is not None and x.interaction_event is None
        for x in rules.taunts(state)
    )


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    event: str,
    rebel: str | None,
    account: str,
) -> None:
    actual = speaker(state, rebel)
    handler = active_handler(state)
    if (
        handler is None
        or not HandlerService(strain.store)._member(c, actual.controller)
        or any(x.id == row["id"] for x in rules.taunts(state))
    ):
        raise WorkflowError("Recover the original Rebel radio speaker and Handler")
    rules.save(
        state,
        rules.Taunt(
            id=row["id"],
            source=event,
            period=row["off_duty_id"],
            handler=handler,
            rebel=actual.id,
            controller=actual.controller,
            account=account,
        ),
    )


def bind_interaction(
    game: "GameService",
    c: Connection,
    state: GameState,
    handler: ActorRef | None,
    girl: ActorRef,
    event: str,
) -> tuple[tuple[str, int, dict[str, Any]], ...]:
    if handler is None or girl.kind != "pilot" or girl != current_ref(state, int(girl.entity)):
        return ()
    periods = t.m3["m3_off_duty"]
    period = c.scalar(
        sa.select(periods.c.id).where(
            periods.c.campaign_id == game.store.campaign_id,
            periods.c.handler_id == handler.entity,
            periods.c.phase.in_(("preparing", "active")),
        )
    )
    results = []
    for case in rules.taunts(state):
        if case.handler != handler or not case.tag_event or case.interaction_event is not None:
            continue
        work = str(uuid5(NAMESPACE_URL, "girlframe:rebel-taunt-punishment:" + case.id))
        allocation = allocate_punishment(
            game, c, state, girl, source_event=event, source_id=work, work_id=work
        )
        subject = allocation.subject if allocation else girl
        rules.save(
            state,
            case.model_copy(
                update=dict(
                    girl=girl, work=work, interaction_event=event, interaction_period=period
                )
            ),
        )
        results.append(
            (
                work,
                int(subject.entity),
                dict(
                    reason=rules.KIND,
                    tag_case=case.id,
                    interaction_period=period,
                    original=girl.model_dump(mode="json"),
                    character=subject.incarnation,
                    source_pdf=147,
                    **allocation_fields(state, work),
                ),
            )
        )
    return tuple(results)


def materialize(
    game: "GameService",
    c: Connection,
    owner: int,
    event: str,
    works: tuple[tuple[str, int, dict[str, Any]], ...],
) -> None:
    for identity, subject, body in works:
        period = body["interaction_period"]
        related(
            c,
            game.store,
            dict(
                campaign_id=game.store.campaign_id,
                off_duty_id=period,
                campaign_context=period is None,
            ),
            identity,
            owner,
            subject,
            "punishment",
            body,
            event,
        )


def prove(c: Connection, game: "GameService", row: dict[str, Any]) -> None:
    body = json.loads(row["body_json"])
    work, history = t.m3["m3_required_work"], t.m2["m2_state_history"]
    original = c.execute(
        sa.select(work.c.event_id, work.c.body_json).where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id == row["id"],
            work.c.revision == 1,
        )
    ).one_or_none()
    raw = (
        c.scalar(
            sa.select(history.c.body_json)
            .join(
                t.events,
                (t.events.c.campaign_id == history.c.campaign_id)
                & (t.events.c.id == history.c.event_id),
            )
            .where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == original.event_id,
                t.events.c.actor_id == row["owner_id"],
                t.events.c.kind.in_((EVENT, "m2.order_issued", "m3.handler_play_applied")),
            )
        )
        if original
        else None
    )
    source = GameState.model_validate_json(raw) if raw else None
    case = (
        next((x for x in rules.taunts(source) if x.id == body.get("tag_case")), None)
        if source
        else None
    )
    if (
        original is None
        or case is None
        or case.work != row["id"]
        or case.interaction_event != original.event_id
        or not case.tag_event
        or not case.radio_event
        or case.girl is None
        or case.girl.model_dump(mode="json") != body.get("original")
        or case.handler.entity != row["owner_id"]
        or row["mission_id"] is not None
        or case.interaction_period != row["off_duty_id"]
        or any(body.get(key) != val for key, val in json.loads(original.body_json).items())
    ):
        raise WorkflowError("Recover the actual original interaction requiring this Punishment")


class TauntService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _owned(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Taunt:
        case = next((x for x in rules.taunts(state) if x.id == identity), None)
        if case is None or (
            viewer.user_id != case.controller
            and (str(viewer.user_id) != case.handler.entity or not case.radio_event)
        ):
            raise WorkflowError("Only the actual radio speaker and recipient can read the taunt")
        return case

    def get(self, viewer: GuildViewer, identity: str, channel: int | None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            mode = None
            people: tuple[tuple[str, str], ...] = ()
            if viewer.user_id == case.controller and not case.radio_event:
                mode = "radio"
            if str(viewer.user_id) == case.handler.entity and same_handler_body(
                state, case.handler
            ):
                if not case.tag_event:
                    mode = "tag"
                elif not case.interaction_event and channel is not None:
                    try:
                        cast, _ = CastService(ActorService(self.strain.missions))._current(
                            c, state, channel
                        )
                    except WorkflowError:
                        pass
                    else:
                        if any(
                            x.actor == case.handler and x.controller == viewer.user_id
                            for x in cast.roles
                        ):
                            people = tuple(
                                (x.actor.entity, state.sheets[x.actor.entity].callsign)
                                for x in cast.roles
                                if x.actor.kind == "pilot"
                                and x.actor.entity in state.sheets
                                and current_ref(state, int(x.actor.entity)) == x.actor
                            )
                            if people:
                                mode = "interact"
            return dict(
                revision=state.revision, mode=mode, account=case.radio or case.account, girls=people
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: Action,
        account: str,
        *,
        tag: str | None = None,
        channel: int | None = None,
        girl: int | None = None,
    ) -> dict[str, Any]:
        if (
            action not in ("radio", "tag", "interact")
            or not 0 < len(account.strip()) <= 1200
            or (tag is not None) != (action == "tag")
            or (channel is not None) != (action == "interact")
            or (girl is not None) != (action == "interact")
            or tag is not None
            and not 0 < len(tag.strip()) <= 120
        ):
            raise WorkflowError("Record the actual transmission, Tag or in-character interaction")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            if not same_handler_body(state, case.handler) or (
                action == "radio"
                and (
                    case.controller != viewer.user_id
                    or speaker(state, case.rebel).controller != viewer.user_id
                )
                or action != "radio"
                and case.handler.entity != str(viewer.user_id)
            ):
                raise WorkflowError("Only the original radio speaker or Handler makes this choice")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            case = self._owned(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                row["off_duty_id"] != case.period
                or body["rule_id"] != rules.RULE
                or body.get("taunt_requested") != case.source
                or case.interaction_event
            ):
                raise WorkflowError("Recover the actual original taunt and its pending consequence")
            event = str(uuid4())
            works: tuple[tuple[str, int, dict[str, Any]], ...] = ()
            if action == "radio":
                if row["state"] != "pending" or case.radio_event:
                    raise WorkflowError("Transmit the original taunt only once")
                rules.save(
                    state, case.model_copy(update=dict(radio=account.strip(), radio_event=event))
                )
            elif action == "tag":
                if (
                    row["state"] != "pending"
                    or not case.radio_event
                    or case.tag_event
                    or tag is None
                ):
                    raise WorkflowError("Keep the original transmitted taunt and one owned Tag")
                identity_tag = str(uuid5(NAMESPACE_URL, "girlframe:rebel-taunt-tag:" + case.id))
                state.handler_tags.append(
                    TagState(
                        id=identity_tag,
                        label=tag.strip(),
                        giver=viewer.user_id,
                        giver_actor=case.handler,
                    )
                )
                rules.save(state, case.model_copy(update=dict(tag=identity_tag, tag_event=event)))
            else:
                assert channel is not None and girl is not None
                if row["state"] != "resolved" or not case.tag_event or girl not in state.order:
                    raise WorkflowError("Recover the original armed next-interaction consequence")
                cast, _ = CastService(ActorService(self.strain.missions))._current(
                    c, state, channel
                )
                target = current_ref(state, girl)
                if not {(case.handler, viewer.user_id), (target, girl)} <= {
                    (x.actor, x.controller) for x in cast.roles
                }:
                    raise WorkflowError(
                        "The Handler and original Girl must actually share this scene"
                    )
                works = bind_interaction(self.game, c, state, case.handler, target, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                work_id=identity,
                action=action,
            )
            materialize(self.game, c, viewer.user_id, event, works)
            if action == "tag":
                self.strain._save(c, row, event, body | {"taunt_armed": event}, resolved=True)
            return dict(id=identity, state=action)

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity,
                expected=expected,
                action=action,
                account=account,
                tag=tag,
                channel=channel,
                girl=girl,
            ),
            operation,
            authorize,
        )
