"""Both real people use AM Sex without adding dice, charges or circuit capability."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_am as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_bonded import admit_delegation, bind_delegation, prove_delegation
from girlframe.services.m3_bonded import prove as prove_bonded
from girlframe.services.m3_dose_up import _cast, _native
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import require_ready
from girlframe.services.read_only_bot import GuildViewer


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    gate.registry.require_available(bonded.SEX)


def _parent(game: GameService, c: Connection, state: GameState, identity: str) -> bonded.Source:
    value = prove_bonded(game, c, state, identity)
    if value.target is None:
        raise WorkflowError("Use the genuine accepted original non-Pair counterpart")
    admit_delegation(game, c, state, value.actor, value.target, rules.RULE, identity)
    return value


def eligible(game: GameService, c: Connection, state: GameState, bonded_source: str) -> bool:
    value = prove_bonded(game, c, state, bonded_source)
    return bool(
        value.route == "delegated"
        and value.delegated_rule == rules.RULE
        and value.target is not None
        and value.target.kind == "pilot"
        and value.target != value.pair
        and value.phase in ("accepted", "bound", "complete")
        and value.target.entity in state.sheets
        and state.sheets[value.target.entity].character_id == value.target.incarnation
        and has_rule(state.sheets[value.target.entity], rules.RULE, "AM")
    )


def _live(game: GameService, c: Connection, state: GameState, source: rules.Source) -> None:
    parent = _parent(game, c, state, source.bonded_source)
    if not eligible(game, c, state, source.bonded_source):
        raise WorkflowError("The actual other Girl uses her genuine owned Sex Play instead")
    cast = _cast(game, c, state, source.cast.channel)
    people = [_native(game, c, state, ref) for ref in (source.actor, source.target)]
    if (
        (parent.actor, parent.target) != (source.actor, source.target)
        or cast != source.cast
        or source.cast != parent.cast
        or cast.adjudicator is not None
        or any(x.active for x in state.director_contexts)
        or any(
            current_ref(state, int(x.ref.entity)) != x.ref
            or x.inside_frame is not False
            or x.piloting
            or x.custody not in (None, "free")
            or x.offstage_source
            or x.controller != source.controllers[x.ref.token]
            or x.vessel_id != source.vessels[x.ref.token]
            or x.position_sha256 != source.positions[x.ref.token]
            or not any(r.actor == x.ref and r.controller == x.controller for r in cast.roles)
            for x in people
        )
        or people[0].cell is None
        or people[0].cell != people[1].cell
    ):
        raise WorkflowError("SOURCE_CONTACT_CHANGED: preserve actual joined original bodies")


def _event(game: GameService, c: Connection, event: str, kind: str, human: int) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != kind or row["actor_id"] != str(human):
        raise WorkflowError("Prove the actual original human's canonical performed source")
    return dict(row)


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Source:
    source = rules.source(state, identity)
    birth = _history(c, game, source.event)
    old = rules.source(birth, identity)
    if old.model_dump(
        exclude={
            "phase",
            "effect_event",
            "completed_event",
            "withdrawn_event",
            "withdrawn_by",
            "withdrawal_account",
        }
    ) != source.model_dump(
        exclude={
            "phase",
            "effect_event",
            "completed_event",
            "withdrawn_event",
            "withdrawn_by",
            "withdrawal_account",
        }
    ):
        raise WorkflowError("Preserve the actual original people, bodies and accepted source")
    audit = _event(
        game, c, source.event, "m3.bonded_am_started", source.controllers[source.actor.token]
    )
    if json.loads(audit["payload_json"]).get("source") != source.id or not eligible(
        game, c, birth, source.bonded_source
    ):
        raise WorkflowError("Prove the real source-time AM rule, never an account/body substitute")
    _parent(game, c, birth, source.bonded_source)
    prove_delegation(
        game, c, birth, source.bonded_source, source.id, source.actor, source.target, rules.RULE
    )
    born_link = next(
        x for x in bonded.records(birth, bonded.Delegation) if x.source == source.bonded_source
    )
    current_link = next(
        (x for x in bonded.records(state, bonded.Delegation) if x.id == born_link.id), None
    )
    if current_link is None or current_link.model_dump(exclude={"action", "completed_event"}) != (
        born_link.model_dump(exclude={"action", "completed_event"})
    ):
        raise WorkflowError("Preserve the original actual delegated source binding")
    if current_link.action is not None or current_link.completed_event != source.completed_event:
        raise WorkflowError("The no-roll source cannot acquire a fabricated Action or closure")
    actual = [x for x in rules.performances(state) if x.source == identity]
    if len({x.actor for x in actual}) != len(actual):
        raise WorkflowError("Keep exactly one actual performance per original person")
    for value in actual:
        performed = _history(c, game, value.event)
        event = _event(game, c, value.event, "m3.bonded_am_performed", value.controller)
        payload = json.loads(event["payload_json"])
        if (
            value.actor not in (source.actor, source.target)
            or source.controllers.get(value.actor.token) != value.controller
            or value not in rules.performances(performed)
            or payload.get("source") != source.id
            or payload.get("person") != value.actor.model_dump(mode="json")
            or value.circuits_touched is not False
        ):
            raise WorkflowError(
                "A real owned performance is not inferred consent or an acknowledgment"
            )
    if source.effect_event:
        effect = rules.source(_history(c, game, source.effect_event), identity)
        if (
            {x.actor for x in actual} != {source.actor, source.target}
            or source.effect_event not in {x.event for x in actual}
            or effect.effect_event != source.effect_event
        ):
            raise WorkflowError("Both original people actually perform before source effects")
    elif source.phase not in ("active", "withdrawn"):
        raise WorkflowError("Actual effects require both performed source events")
    if source.withdrawn_event:
        withdrawn = rules.source(_history(c, game, source.withdrawn_event), identity)
        if source.withdrawn_by not in (source.actor, source.target):
            raise WorkflowError("Keep the actual original participant's voluntary withdrawal")
        assert source.withdrawn_by is not None
        row = _event(
            game,
            c,
            source.withdrawn_event,
            "m3.bonded_am_withdrawn",
            source.controllers[source.withdrawn_by.token],
        )
        if (
            source.phase != "withdrawn"
            or source.effect_event
            or source.completed_event
            or withdrawn != source
            or not source.withdrawal_account.strip()
            or json.loads(row["payload_json"]).get("source") != identity
        ):
            raise WorkflowError(
                "Withdrawal preserves source history and creates no performed effects"
            )
    elif source.phase == "withdrawn" or source.withdrawn_by or source.withdrawal_account:
        raise WorkflowError("A withdrawal requires its real canonical original human source")
    if source.completed_event:
        completed = rules.source(_history(c, game, source.completed_event), identity)
        completed_audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == source.completed_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            completed_audit is None
            or completed_audit["kind"] != "m3.bonded_am_completed"
            or completed != source
            or source.phase != "complete"
            or json.loads(completed_audit["payload_json"]).get("source") != identity
        ):
            raise WorkflowError("Preserve the genuine completed source and its original lineage")
        cause = _cause(
            game,
            c,
            state,
            source,
            json.loads(completed_audit["payload_json"]).get("source_event", ""),
        )
        if completed_audit["actor_id"] != cause["actor_id"]:
            raise WorkflowError("Preserve the actual final source author without a proxy")
    return source


def validate_completion(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    source = prove(game, c, state, identity)
    from girlframe.services.p1_unrolled_sex import require_complete

    if source.phase not in ("effects", "complete") or not event or not source.effect_event:
        raise WorkflowError("Complete actual original performances before closing the delegation")
    require_complete(game, c, state, identity)
    from girlframe.engine.p1_unrolled_sex import gifts
    from girlframe.services.p1_unrolled_sex import prove as prove_gift

    for gift in gifts(state):
        if gift.source == identity:
            prove_gift(game, c, state, gift.id)


def _cause(
    game: GameService, c: Connection, state: GameState, source: rules.Source, event: str
) -> dict[str, Any]:
    cause = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .one()
    )
    if cause["kind"] == "m3.bonded_am_performed":
        valid = any(
            x.source == source.id and x.event == event and str(x.controller) == cause["actor_id"]
            for x in rules.performances(state)
        )
    elif cause["kind"] == "m3.unrolled_animal_tag":
        from girlframe.engine.p1_unrolled_sex import gifts
        from girlframe.services.p1_unrolled_sex import prove as prove_gift

        actual = [x for x in gifts(state) if x.source == source.id and x.tag_event == event]
        valid = len(actual) == 1 and source.controllers[actual[0].animal.token] == int(
            cause["actor_id"]
        )
        if valid:
            prove_gift(game, c, _history(c, game, event), actual[0].id)
    else:
        valid = False
    if not valid:
        raise WorkflowError("Preserve the actual source performance or completed Animal gift cause")
    return dict(cause)


def synchronize(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    source = prove(game, c, state, identity)
    if source.phase != "effects":
        return
    from girlframe.engine.p1_unrolled_sex import gifts
    from girlframe.services.m3_bonded import complete_unrolled_am

    if any(x.source == identity and x.tag is None for x in gifts(state)):
        return
    validate_completion(game, c, state, identity, event)
    cause = _cause(game, c, state, source, event)
    final = str(uuid4())
    complete_unrolled_am(game, c, state, source.bonded_source, identity, final)
    rules.put(state, source.model_copy(update=dict(phase="complete", completed_event=final)))
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == cause["command_key"],
        )
    )
    game.event(
        c,
        int(cause["actor_id"]),
        cause["command_key"],
        "m3.bonded_am_completed",
        state,
        event_id=final,
        event_index=0 if index is None else index + 1,
        source=identity,
        bonded_source=source.bonded_source,
        source_event=event,
    )


class BondedAMService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            _access(self.game, c, viewer)

        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            return operation(c, load_state(c, self.store.campaign_id), str(uuid4()))

        return self.store._write(
            viewer, key, kind, request, apply, auto_audit=False, authorize=authorize
        )

    def start(
        self, viewer: GuildViewer, key: str, bonded_source: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            parent = _parent(self.game, c, state, bonded_source)
            if (
                state.revision != revision
                or parent.actor != current_ref(state, viewer.user_id)
                or parent.phase != "accepted"
                or self.game.pending_actions(c)
                or not eligible(self.game, c, state, bonded_source)
                or not account.strip()
                or len(account) > 1200
                or any(x.bonded_source == bonded_source for x in rules.sources(state))
            ):
                raise WorkflowError("Start only this actual accepted no-roll AM source once")
            assert parent.target is not None and self.store.policy.m3_approval is not None
            people = [_native(self.game, c, state, x) for x in (parent.actor, parent.target)]
            if any(not x.vessel_id or not x.position_sha256 for x in people):
                raise WorkflowError("Record actual original bodies/positions first")
            source = rules.Source(
                id=str(uuid4()),
                bonded_source=bonded_source,
                actor=parent.actor,
                target=parent.target,
                controllers={x.ref.token: x.controller for x in people},
                vessels={x.ref.token: x.vessel_id for x in people},
                positions={x.ref.token: x.position_sha256 for x in people},
                cast=_cast(self.game, c, state, parent.cast.channel),
                registry=self.store.policy.m3_approval.registry_sha256,
                event=event,
                account=account.strip(),
            )
            _live(self.game, c, state, source)
            rules.put(state, source)
            bind_delegation(self.game, c, state, bonded_source, source.id, rules.RULE, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_am_started",
                state,
                event_id=event,
                source=source.id,
                bonded_source=bonded_source,
            )
            return dict(id=source.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bonded_am_started",
            dict(bonded_source=bonded_source, revision=revision, account=account),
            operation,
        )

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        *,
        circuits_touched: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove(self.game, c, state, identity)
            if viewer.user_id not in source.controllers.values():
                raise WorkflowError(
                    "Only actual original participants author their own performance"
                )
            require_ready(self.game, c, state, source.id)
            _live(self.game, c, state, source)
            person = current_ref(state, viewer.user_id)
            if circuits_touched is not False:
                raise WorkflowError(
                    "SOURCE_CIRCUITS_REQUIRED: use the touched person's actual Code source; "
                    "copying AM Sex provides no body, circuits or software capability"
                )
            if (
                state.revision != revision
                or source.phase != "active"
                or person not in (source.actor, source.target)
                or source.controllers.get(person.token) != viewer.user_id
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
                or any(
                    x.source == identity and x.actor == person for x in rules.performances(state)
                )
            ):
                raise WorkflowError("Record this original person's actual performed scene once")
            rules.put(
                state,
                rules.Performance(
                    id=identity + ":" + person.token,
                    source=identity,
                    actor=person,
                    controller=viewer.user_id,
                    account=account.strip(),
                    event=event,
                ),
            )
            if {x.actor for x in rules.performances(state) if x.source == identity} == {
                source.actor,
                source.target,
            }:
                source = source.model_copy(update=dict(phase="effects", effect_event=event))
                rules.put(state, source)
                from girlframe.services.p1_unrolled_sex import offer

                offer(self.game, c, state, source, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_am_performed",
                state,
                event_id=event,
                source=identity,
                person=person.model_dump(mode="json"),
            )
            synchronize(self.game, c, state, identity, event)
            return dict(id=identity, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bonded_am_performed",
            dict(
                source=identity,
                revision=revision,
                account=account,
                circuits_touched=circuits_touched,
            ),
            operation,
        )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove(self.game, c, state, identity)
            if viewer.user_id not in source.controllers.values():
                raise WorkflowError("Only original participants may withdraw their actual source")
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or source.phase != "active"
                or actor not in (source.actor, source.target)
                or source.controllers.get(actor.token) != viewer.user_id
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Withdraw only before actual joint effects; owed effects remain"
                )
            from girlframe.services.m3_bonded import withdraw_unrolled_am

            withdraw_unrolled_am(self.game, c, state, source.bonded_source, identity, event)
            rules.put(
                state,
                source.model_copy(
                    update=dict(
                        phase="withdrawn",
                        withdrawn_event=event,
                        withdrawn_by=actor,
                        withdrawal_account=account.strip(),
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_am_withdrawn",
                state,
                event_id=event,
                source=identity,
                bonded_source=source.bonded_source,
            )
            return dict(id=identity, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bonded_am_withdrawn",
            dict(source=identity, revision=revision, account=account),
            operation,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = rules.source(state, identity)
            if viewer.user_id not in source.controllers.values():
                raise WorkflowError("The original Pair is provenance, not a private participant")
            prove(self.game, c, state, identity)
            from girlframe.services.p1_source_pause import projection
            from girlframe.services.p1_unrolled_sex import tasks

            records = [x for x in rules.performances(state) if x.source == identity]
            return dict(
                id=identity,
                revision=state.revision,
                source=source.model_dump(mode="json"),
                performances=[x.model_dump(mode="json") for x in records],
                can_withdraw=source.phase == "active",
                can_perform=source.phase == "active"
                and not any(x.controller == viewer.user_id for x in records),
                pause=projection(self.game, c, source.id),
                unrolled_gender=tasks(self.game, c, state, source, viewer),
                no_additional_roll=True,
            )

    def menu(self, viewer: GuildViewer, bonded_source: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            saved = next(
                (x for x in rules.sources(state) if x.bonded_source == bonded_source), None
            )
            if saved is not None:
                if viewer.user_id not in saved.controllers.values():
                    raise WorkflowError("Only original participants may reopen their saved source")
                prove(self.game, c, state, saved.id)
                return dict(
                    bonded_source=bonded_source,
                    id=saved.id,
                    revision=state.revision,
                    can_start=False,
                )
            parent = _parent(self.game, c, state, bonded_source)
            if viewer.user_id not in parent.controllers.values():
                raise WorkflowError("Only original actual source participants may open this card")
            return dict(
                bonded_source=bonded_source,
                id=saved.id if saved else None,
                revision=state.revision,
                can_start=saved is None
                and viewer.user_id == int(parent.actor.entity)
                and parent.phase == "accepted"
                and eligible(self.game, c, state, bonded_source),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        _access(self.game, c, viewer)
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.sources(state):
            if viewer.user_id not in source.controllers.values():
                continue
            own = [
                x
                for x in rules.performances(state)
                if x.source == source.id and x.controller == viewer.user_id
            ]
            from girlframe.services.p1_unrolled_sex import tasks

            gifts = tasks(self.game, c, state, source, viewer)
            pending = source.phase == "active" and not own or any(x["pending"] for x in gifts)
            result.append(
                dict(
                    id=source.id,
                    revision=state.revision,
                    label="Actual Bonded/AM no-roll source",
                    phase=source.phase,
                    pending=bool(pending),
                    waiting=source.phase not in ("complete", "withdrawn") and not pending,
                )
            )
        return result
