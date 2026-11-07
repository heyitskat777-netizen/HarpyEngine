"""Actual Cadre sphere aid, political Strings and three source-bound cash-outs."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_politician_bribery as rules
from girlframe.engine import m3_strain as strain_rules
from girlframe.engine import m3_world as world_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services import m3_advancement_acquisition as acquisition
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _scene_judge
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return acquisition.prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the original Politician Bribery Fund acquisition",
        failure="Recover the exact original political award and receipt",
    )


def current(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    source = paid(game, c, state, identity)
    HandlerAdvancementService(game.store)._current(c, state, source.handler, source.appointment)
    return source


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original political source record")
    return value


def _born(game: GameService, c: Connection, value: Model, kind: str, human: int) -> GameState:
    data = value.model_dump()
    source = _history(c, game, data["event"])
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == data["event"]
        )
    ).first()
    if value not in rules.records(source, type(value)) or audit != (kind, str(human)):
        raise WorkflowError("Recover the original human's immutable political source")
    return source


def assignment(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Assignment:
    value = _record(state, rules.Assignment, identity)
    source = paid(game, c, state, value.acquisition)
    born = _born(game, c, value, "m3.bribery_assigned", int(value.actor.entity))
    npc = ActorRef(kind="npc", entity=value.npc)
    if (
        value.actor not in source.cadre
        or value.sphere not in rules.SPHERES
        or value.npc not in {x.npc.id for x in source.politicians}
        or depth(born, value.actor, npc) < 1
    ):
        raise WorkflowError("Recover the actual Cadre-authored sphere and NPC Bond")
    return value


def cause_action(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Acquisition,
    kind: str,
    identity: str,
) -> str:
    if kind == "handler_play":
        from girlframe.services.m3_handler_plays import _source

        _, grant = _source(c, game, identity)
        if (
            grant.state != "complete"
            or grant.chooser_actor != source.handler
            or not grant.completed_event
        ):
            raise WorkflowError("Use the actual completed original Handler Play")
        return grant.completed_event
    if kind != "pilot_play":
        raise WorkflowError("Use an actual source-owned Handler or Cadre action")
    action = game.action(c, identity)
    game.action_characters(c, action, state)
    actor = current_ref(state, int(action["actor_id"]))
    actor_source = action["data"].get("actor_basic")
    actual_actor = (
        ActorRef.model_validate(actor_source["ref"]) if actor_source is not None else None
    )
    if actor_source is None and action["data"].get("tag_context") is not None:
        actual_actor = ActorRef.model_validate(action["data"]["tag_context"]["actor"])
    if actual_actor is not None and actual_actor != actor:
        raise WorkflowError("Use the actual original Cadre actor, not a controlled NPC/copy alias")
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == identity,
            )
        )
        .mappings()
        .first()
    )
    if (
        action["state"] != "complete"
        or actor not in source.cadre
        or receipt is None
        or action["data"].get("receipt") is None
    ):
        raise WorkflowError("Use a genuine completed original Cadre action and real receipt")
    rolled = c.execute(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == actor.entity,
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == identity,
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == receipt["id"],
        )
    ).first()
    if rolled is None or json.loads(receipt["body_json"]) != action["data"]["receipt"]:
        raise WorkflowError("Recover the genuine original action's canonical roll receipt")
    return str(rolled.id)


def prove_aid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Aid:
    value = _record(state, rules.Aid, identity)
    source = paid(game, c, state, value.acquisition)
    assigned = assignment(game, c, state, value.assignment)
    born = _born(game, c, value, "m3.bribery_aid_performed", int(value.actor.entity))
    cast = next((x for x in born.scene_casts if x.id == value.cast.id), None)
    judge, human, judge_source = _scene_judge(game, c, born, value.cast)
    if (
        cast != value.cast
        or human != value.judge
        or judge_source != value.judge_source
        or value.actor not in source.cadre
        or assigned.npc != value.npc
        or not any(
            x.actor == value.actor and x.controller == int(value.actor.entity)
            for x in value.cast.roles
        )
        or not any(x.actor == ActorRef(kind="npc", entity=value.npc) for x in value.cast.roles)
    ):
        raise WorkflowError("Recover the actual performed aid, original people and source judge")
    if value.action:
        cause_action(game, c, born, source, "pilot_play", value.action)
        if game.action(c, value.action)["actor_id"] != value.actor.entity:
            raise WorkflowError("This aid cannot claim another person's action")
    return value


def prove_string(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Earned:
    value = _record(state, rules.Earned, identity)
    aid = prove_aid(game, c, state, value.aid)
    born = _born(game, c, value, "m3.bribery_aid_benefit", value.judge)
    if (
        value.judge != aid.judge
        or value.npc != aid.npc
        or value.acquisition != aid.acquisition
        or value.id != "bribery-string:" + aid.id
        or value not in rules.records(born, rules.Earned)
    ):
        raise WorkflowError("Recover the actual source-adjudicated benefit and earned String")
    return value


def _work(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    rows = list(
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision)
        ).mappings()
    )
    if not rows:
        raise WorkflowError("Recover the actual pending job-loss source")
    first, last = rows[0], rows[-1]
    body = json.loads(first["body_json"])
    born = _history(c, game, first["event_id"])
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
        )
    ).first()
    original = (
        next((x for x in born.strain.events if x.id == body.get("source_work")), None)
        if born.strain
        else None
    )
    if (
        first["kind"] != "strain_event"
        or body.get("rule_id") != rules.JOB_LOSS
        or original is None
        or original.rule_id != rules.JOB_LOSS
        or original.period_id != first["off_duty_id"]
        or event is None
        or event.kind != "m3.strain_option_saved"
        or event.actor_id != str(born.handler)
        or json.loads(event.payload_json).get("work_id") != original.id
        or any(first[k] != last[k] for k in ("owner_id", "off_duty_id", "kind"))
    ):
        raise WorkflowError(
            "Recover the actual selected Budget job-loss outcome, not unrelated work"
        )
    return dict(last)


def prove_cause(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Causation:
    value = _record(state, rules.Causation, identity)
    source = paid(game, c, state, value.acquisition)
    born = _born(game, c, value, "m3.bribery_causation", int(source.handler.entity))
    row = _work(game, c, value.work)
    bound = (
        c.execute(
            sa.select(t.m3["m3_required_work"]).where(
                t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_required_work"].c.id == value.work,
                t.m3["m3_required_work"].c.revision == value.work_revision,
            )
        )
        .mappings()
        .first()
    )
    if (
        bound is None
        or bound["state"] != "pending"
        or bound["event_id"] != value.work_event
        or json.loads(bound["body_json"]).get("rule_id") != rules.JOB_LOSS
    ):
        raise WorkflowError("Recover the original pending consequence revision")
    if (
        value.cause_event != cause_action(game, c, born, source, value.cause_kind, value.cause)
        or json.loads(value.choice_json).get("target") != value.original.id
        or row["owner_id"] != source.handler.entity
    ):
        raise WorkflowError(
            "Recover the actual action-to-consequence source and original affected NPC"
        )
    return value


def redirect(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    choice: Choice,
    event: str,
) -> Choice:
    """Called only after the real Strain effect's original owner/rule/revision checks."""
    reservations = [
        x
        for x in rules.records(state, rules.Reservation)
        if prove_cause(game, c, state, x.cause).work == row["id"]
    ]
    if not reservations:
        return choice
    if len(reservations) != 1:
        raise WorkflowError("Recover this original consequence's one actual political cash-out")
    reservation = reservations[0]
    source = current(game, c, state, reservation.acquisition)
    _born(game, c, reservation, "m3.bribery_reserved", int(source.handler.entity))
    cause = prove_cause(game, c, state, reservation.cause)
    original = (
        next((x for x in state.world.npcs if x.id == cause.original.id), None)
        if state.world
        else None
    )
    politician = (
        next((x for x in state.world.npcs if x.id == reservation.politician), None)
        if state.world
        else None
    )
    string = prove_string(game, c, state, reservation.string)
    if (
        choice.model_dump_json() != cause.choice_json
        or row["revision"] != cause.work_revision
        or row["event_id"] != cause.work_event
        or original != cause.original
        or politician is None
        or not politician.alive
        or string.npc != politician.id
        or string.acquisition != source.id
        or any(reservation.string in x.strings for x in rules.records(state, rules.Cashout))
    ):
        raise WorkflowError(
            "Preserve the exact original consequence and one genuine reserved String"
        )
    rules.put(
        state,
        rules.Cashout(
            id="bribery-cashout:" + event,
            acquisition=source.id,
            politician=politician.id,
            kind="scapegoat",
            strings=(string.id,),
            event=event,
            account=cause.account,
            target=politician.id,
            reservation=reservation.id,
        ),
    )
    return choice.model_copy(update={"target": politician.id})


class BriberyService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "playbooks")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _owner(
        self, c: Connection, viewer: GuildViewer, identity: str, revision: int
    ) -> tuple[GameState, rules.Acquisition]:
        state = load_state(c, self.store.campaign_id)
        source = current(self.game, c, state, identity)
        if state.revision != revision or viewer.user_id != int(source.handler.entity):
            raise WorkflowError("Use the original Handler's current political source")
        return state, source

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        revision: int,
        politicians: tuple[rules.Politician, ...],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, handler, appointment, award = acquisition.held(
                self.game,
                c,
                viewer,
                award_id,
                revision,
                account,
                failure="Spend a genuine held political advancement",
            )
            cities = (
                {x.id: x for x in state.world.locations if x.kind == "city"} if state.world else {}
            )
            if (
                not cities
                or len(politicians) < 6
                or len({x.npc.id for x in politicians}) != len(politicians)
                or {x.city for x in politicians} != set(cities)
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Name six or more actual politicians, at least one for every current City"
                )
            assert state.world is not None
            for choice in politicians:
                existing = next((x for x in state.world.npcs if x.id == choice.npc.id), None)
                if (
                    not choice.npc.alive
                    or not choice.npc.revealed
                    or (existing is not None and existing != choice.npc)
                ):
                    raise WorkflowError(
                        "Preserve each actual politician, original controller and actual City"
                    )
                if existing is None:
                    if (
                        choice.npc.controller != viewer.user_id
                        or choice.npc.tags
                        or choice.npc.bonds
                    ):
                        raise WorkflowError(
                            "Name a real new source-owned politician without invented Bonds/Tags"
                        )
                    state.world = world_rules.introduce_npc(state.world, choice.npc)
            event = str(uuid4())
            value = rules.Acquisition(
                id="bribery-acquisition:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
                cadre=tuple(current_ref(state, x) for x in state.order),
                politicians=politicians,
                cities=tuple(sorted(cities)),
            )
            rules.put(state, value)
            acquisition.record_spend(state, award, value, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_acquired",
            dict(
                award=award_id,
                revision=revision,
                politicians=[x.model_dump(mode="json") for x in politicians],
                account=account,
            ),
            operation,
        )

    def assign(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        npc: str,
        sphere: str,
        feelings: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = current(self.game, c, state, identity)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or actor not in source.cadre
                or sphere not in rules.SPHERES
                or npc not in {x.npc.id for x in source.politicians}
                or any(
                    x.acquisition == identity and x.npc == npc
                    for x in rules.records(state, rules.Assignment)
                )
            ):
                raise WorkflowError(
                    "The actual Cadre assigns each politician one sphere and "
                    "authors its own NPC Bond"
                )
            event = str(uuid4())
            ref = ActorRef(kind="npc", entity=npc)
            if depth(state, actor, ref) < 1:
                state = set_depth(state, actor, ref, 1, event)
            value = rules.Assignment(
                id="bribery-assignment:" + identity + ":" + npc,
                acquisition=identity,
                npc=npc,
                sphere=sphere,
                actor=actor,
                feelings=feelings.strip(),
                event=event,
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.bribery_assigned", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_assigned",
            dict(id=identity, revision=revision, npc=npc, sphere=sphere, feelings=feelings),
            operation,
        )

    def record_aid(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        npc: str,
        channel: int,
        activity: str,
        benefit: str,
        *,
        action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = current(self.game, c, state, identity)
            actor = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            assigned = next(
                (
                    x
                    for x in rules.records(state, rules.Assignment)
                    if x.acquisition == identity and x.npc == npc
                ),
                None,
            )
            _, judge, judge_source = _scene_judge(self.game, c, state, cast)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            recipient = resolve(state, ActorRef(kind="npc", entity=npc), ())
            if (
                state.revision != revision
                or actor not in source.cadre
                or not rules.complete_assignments(state, source)
                or assigned is None
                or actual.cell is None
                or actual.cell != recipient.cell
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
                or not any(x.actor == recipient.ref for x in cast.roles)
                or (action and any(x.action == action for x in rules.records(state, rules.Aid)))
            ):
                raise WorkflowError(
                    "Perform actual sphere aid for this original politician in the real scene"
                )
            if any(
                x.actor == actor
                and x.npc == npc
                and x.cast.id == cast.id
                and x.activity == activity.strip()
                and x.benefit == benefit.strip()
                for x in rules.records(state, rules.Aid)
            ):
                raise WorkflowError("This same performed aid/benefit source was already recorded")
            assignment(self.game, c, state, assigned.id)
            if action:
                cause_action(self.game, c, state, source, "pilot_play", action)
                if self.game.action(c, action)["actor_id"] != actor.entity:
                    raise WorkflowError("Use your own actual completed aid action")
            event = str(uuid4())
            value = rules.Aid(
                id="bribery-aid:" + event,
                acquisition=identity,
                assignment=assigned.id,
                actor=actor,
                npc=npc,
                cast=cast,
                activity=activity.strip(),
                benefit=benefit.strip(),
                action=action,
                judge=judge,
                judge_source=judge_source,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c, viewer.user_id, key, "m3.bribery_aid_performed", state, event_id=event
            )
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_aid_performed",
            dict(
                id=identity,
                revision=revision,
                npc=npc,
                channel=channel,
                activity=activity,
                benefit=benefit,
                action=action,
            ),
            operation,
        )

    def confirm_aid(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            aid = prove_aid(self.game, c, state, identity)
            cast = _cast(self.game, c, state, aid.cast.channel)
            _, judge, source = _scene_judge(self.game, c, state, cast)
            if (
                state.revision != revision
                or viewer.user_id != aid.judge
                or (judge, source) != (aid.judge, aid.judge_source)
                or cast != aid.cast
                or any(x.aid == identity for x in rules.records(state, rules.Earned))
            ):
                raise WorkflowError(
                    "The actual source judge records the already performed factual NPC benefit once"
                )
            event = str(uuid4())
            value = rules.Earned(
                id="bribery-string:" + identity,
                acquisition=aid.acquisition,
                aid=identity,
                npc=aid.npc,
                judge=viewer.user_id,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.bribery_aid_benefit", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_aid_benefit",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def cash(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        politician: str,
        kind: Literal["budget", "tag"],
        account: str,
        *,
        target: str | None = None,
        label: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, source = self._owner(c, viewer, identity, revision)
            if not state.world or not any(x.id == politician and x.alive for x in state.world.npcs):
                raise WorkflowError("Use the actual living political contact")
            strings = rules.available(state, identity, politician)
            cost = 3 if kind == "budget" else 1
            if kind not in ("budget", "tag") or len(strings) < cost:
                raise WorkflowError("Spend actual unspent Strings on this one politician")
            for string in strings[:cost]:
                prove_string(self.game, c, state, string.id)
            event = str(uuid4())
            tag_id = None
            if kind == "budget":
                if target is not None or label is not None or state.strain is None:
                    raise WorkflowError("Use actual Budget Strain without unrelated target choices")
                state.strain = strain_rules.copy(
                    state.strain,
                    levels=state.strain.levels | {"budget": "low"},
                    requests=tuple(
                        x.model_copy(update={"severity": "low"})
                        if x.track == "budget" and x.kind == "roll"
                        else x
                        for x in state.strain.requests
                    ),
                )
            else:
                npc = (
                    next((x for x in state.world.npcs if x.id == target and x.alive), None)
                    if state.world
                    else None
                )
                if npc is None or not label or not label.strip():
                    raise WorkflowError("Inflict a real Tag on an actual NPC")
                tag_id = "bribery-tag:" + event
                assert state.world is not None
                tag = WorldTag(
                    id=tag_id, label=label.strip(), giver_entity=source.handler.model_dump_json()
                )
                state.world = world_rules.update(
                    state.world,
                    npcs=tuple(
                        x.model_copy(update={"tags": (*x.tags, tag)}) if x.id == npc.id else x
                        for x in state.world.npcs
                    ),
                )
            value = rules.Cashout(
                id="bribery-cashout:" + event,
                acquisition=identity,
                politician=politician,
                kind=kind,
                strings=tuple(x.id for x in strings[:cost]),
                event=event,
                account=account.strip(),
                target=target,
                tag=tag_id,
            )
            rules.put(state, value)
            self.game.event(
                c, viewer.user_id, key, "m3.bribery_cashed", state, event_id=event, cashout=kind
            )
            if kind == "budget":
                from girlframe.services.m3_missions import MissionService
                from girlframe.services.m3_off_duty import OffDutyService
                from girlframe.services.m3_strain import StrainService

                strain = StrainService(OffDutyService(MissionService(self.store)))
                assert state.strain is not None
                for request in state.strain.requests:
                    if request.track == "budget" and request.kind == "roll":
                        row = strain._row(c, request.id)
                        body = json.loads(row["body_json"])
                        if row["state"] != "pending" or body.get("stage") != "die":
                            raise WorkflowError("Preserve the real already-rolled Budget source")
                        strain._save(c, row, event, body | {"severity": "low"})
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_cashed",
            dict(
                id=identity,
                revision=revision,
                politician=politician,
                kind=kind,
                account=account,
                target=target,
                label=label,
            ),
            operation,
        )

    def record_cause(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        work: str,
        choice: Choice,
        cause_kind: Literal["pilot_play", "handler_play"],
        cause_id: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, source = self._owner(c, viewer, identity, revision)
            row = _work(self.game, c, work)
            source_event = cause_action(self.game, c, state, source, cause_kind, cause_id)
            source_sequence = c.scalar(
                sa.select(t.events.c.seq).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == source_event
                )
            )
            work_sequence = c.scalar(
                sa.select(t.events.c.seq).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == row["event_id"],
                )
            )
            if source_sequence is None or work_sequence is None or source_sequence >= work_sequence:
                raise WorkflowError("The actual cause must precede this pending consequence")
            from girlframe.engine.m3_strain_effects import fields

            fields(choice, {"target", "npc_jobs"})
            original = (
                next((x for x in state.world.npcs if x.id == choice.target and x.alive), None)
                if state.world
                else None
            )
            if (
                row["state"] != "pending"
                or row["owner_id"] != str(viewer.user_id)
                or choice.rule_id != rules.JOB_LOSS
                or original is None
                or original.employment == "unemployed"
                or not choice.npc_jobs
                or original.jobs == choice.npc_jobs
                or any(x.work == work for x in rules.records(state, rules.Causation))
            ):
                raise WorkflowError(
                    "Bind the completed action to its specific pending job-loss "
                    "consequence before cash-out"
                )
            event = str(uuid4())
            value = rules.Causation(
                id="bribery-cause:" + event,
                acquisition=identity,
                work=work,
                work_event=row["event_id"],
                work_revision=row["revision"],
                original=original,
                choice_json=choice.model_dump_json(),
                cause_kind=cause_kind,
                cause=cause_id,
                cause_event=source_event,
                account=account.strip(),
                event=event,
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.bribery_causation", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_causation",
            dict(
                id=identity,
                revision=revision,
                work=work,
                choice=choice.model_dump(mode="json"),
                cause_kind=cause_kind,
                cause_id=cause_id,
                account=account,
            ),
            operation,
        )

    def reserve_scapegoat(
        self, viewer: GuildViewer, key: str, cause_id: str, revision: int, politician: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            cause = prove_cause(self.game, c, state, cause_id)
            _, source = self._owner(c, viewer, cause.acquisition, revision)
            row = _work(self.game, c, cause.work)
            strings = rules.available(state, source.id, politician)
            if (
                row["state"] != "pending"
                or not strings
                or politician == cause.original.id
                or state.world is None
                or not any(x.id == politician and x.alive for x in state.world.npcs)
                or any(x.cause == cause_id for x in rules.records(state, rules.Reservation))
            ):
                raise WorkflowError("Reserve one real String for this original pending consequence")
            prove_string(self.game, c, state, strings[0].id)
            event = str(uuid4())
            value = rules.Reservation(
                id="bribery-reservation:" + event,
                acquisition=source.id,
                cause=cause_id,
                politician=politician,
                string=strings[0].id,
                event=event,
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.bribery_reserved", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.bribery_reserved",
            dict(cause=cause_id, revision=revision, politician=politician),
            operation,
        )

    def finish_scapegoat(
        self, viewer: GuildViewer, key: str, cause_id: str, revision: int
    ) -> dict[str, Any]:
        from girlframe.services.m3_missions import MissionService
        from girlframe.services.m3_off_duty import OffDutyService
        from girlframe.services.m3_strain import StrainService
        from girlframe.services.m3_strain_effects import EffectService

        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cause = prove_cause(self.game, c, state, cause_id)
            _work(self.game, c, cause.work)
        return EffectService(StrainService(OffDutyService(MissionService(self.store)))).apply(
            viewer,
            key,
            cause.work,
            cause.work_revision,
            revision,
            Choice.model_validate_json(cause.choice_json),
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            sources = rules.acquisitions(state)
            source = next((x for x in sources if identity == x.id or identity is None), None)
            if source is None:
                if viewer.user_id != state.handler:
                    raise WorkflowError("Use your actual original political source")
                return dict(
                    id=identity,
                    revision=state.revision,
                    acquisition=None,
                    awards=[
                        dict(id=x.id, label="Actual held advancement")
                        for x in awards.awards(state)
                        if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                    ],
                    cities=[
                        dict(id=x.id, name=x.name, cell=x.cell)
                        for x in state.world.locations
                        if x.kind == "city"
                    ]
                    if state.world
                    else [],
                )
            source = paid(self.game, c, state, source.id)
            owner = viewer.user_id == int(source.handler.entity)
            actor = current_ref(state, viewer.user_id)
            if not owner and actor not in source.cadre:
                raise WorkflowError("This political source belongs to its original participants")
            assignments = [
                x for x in rules.records(state, rules.Assignment) if x.acquisition == source.id
            ]
            aids = [
                x
                for x in rules.records(state, rules.Aid)
                if x.acquisition == source.id
                and (owner or x.actor == actor or x.judge == viewer.user_id)
            ]
            causes = [
                x
                for x in rules.records(state, rules.Causation)
                if owner and x.acquisition == source.id
            ]
            for assigned in assignments:
                assignment(self.game, c, state, assigned.id)
            for aid in aids:
                prove_aid(self.game, c, state, aid.id)
            for cause in causes:
                prove_cause(self.game, c, state, cause.id)
            for cashout in rules.records(state, rules.Cashout):
                if cashout.acquisition == source.id:
                    _born(
                        self.game,
                        c,
                        cashout,
                        "m3.strain_effect_applied"
                        if cashout.kind == "scapegoat"
                        else "m3.bribery_cashed",
                        int(source.handler.entity),
                    )
                    for string_id in cashout.strings:
                        prove_string(self.game, c, state, string_id)
            return dict(
                id=source.id,
                revision=state.revision,
                acquisition=source.id,
                owner=owner,
                politicians=[
                    dict(
                        id=x.npc.id,
                        name=x.npc.name,
                        city=x.city,
                        balance=len(rules.available(state, source.id, x.npc.id)) if owner else None,
                    )
                    for x in source.politicians
                ],
                assignments=[
                    x.model_dump(mode="json", exclude=set() if x.actor == actor else {"feelings"})
                    for x in assignments
                    if owner or x.actor == actor
                ],
                unassigned=[
                    x.npc.id
                    for x in source.politicians
                    if not any(a.npc == x.npc.id for a in assignments)
                ],
                aid=[
                    x.model_dump(mode="json")
                    | dict(earned=any(e.aid == x.id for e in rules.records(state, rules.Earned)))
                    for x in aids
                ],
                causes=[
                    x.model_dump(mode="json")
                    | dict(
                        reserved=any(
                            r.cause == x.id for r in rules.records(state, rules.Reservation)
                        ),
                        complete=any(
                            o.reservation == r.id
                            for r in rules.records(state, rules.Reservation)
                            if r.cause == x.id
                            for o in rules.records(state, rules.Cashout)
                        ),
                    )
                    for x in causes
                ],
                cashouts=[
                    x.model_dump(mode="json")
                    for x in rules.records(state, rules.Cashout)
                    if owner and x.acquisition == source.id
                ],
                scenes=[
                    dict(id=str(x.channel), label=str(x.channel))
                    for x in state.scene_casts
                    if x.open
                ],
                npcs=[dict(id=x.id, name=x.name) for x in state.world.npcs if x.alive]
                if owner and state.world
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        rows = []
        for source in rules.acquisitions(state):
            owner = viewer.user_id == int(source.handler.entity)
            if owner or any(x.entity == str(viewer.user_id) for x in source.cadre):
                pending = (
                    not rules.complete_assignments(state, source)
                    if not owner
                    else any(
                        x.judge == viewer.user_id
                        and not any(e.aid == x.id for e in rules.records(state, rules.Earned))
                        for x in rules.records(state, rules.Aid)
                    )
                )
                if owner and any(
                    not any(o.reservation == r.id for o in rules.records(state, rules.Cashout))
                    for r in rules.records(state, rules.Reservation)
                    if r.acquisition == source.id
                ):
                    pending = True
                rows.append(
                    dict(
                        id=source.id,
                        revision=state.revision,
                        label="Political contacts / Strings / actual consequences",
                        phase="active",
                        pending=pending,
                    )
                )
        return rows
