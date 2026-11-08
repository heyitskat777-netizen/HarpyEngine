"""Real Go-OffDuty Show Dog work, actual NPC Bonds and original Handler risk."""

import json
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_show_dog as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _native
from girlframe.services.m3_frame_rewards import eligibility
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_malleable import _audit
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "show_dog"


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Show Dog outcome")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _latest(game: GameService, c: Connection) -> dict[str, dict[str, Any]]:
    table = t.m3["m3_required_work"]
    return {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.kind == KIND)
            .order_by(table.c.revision)
        ).mappings()
    }


def synchronize(
    game: GameService, c: Connection, state: GameState, period: Period, event: str
) -> None:
    existing = _latest(game, c)
    for owner in period.pilots:
        progress = period.progress.get(str(owner))
        if progress is None or progress.roll is None or progress.action_id is None:
            continue
        action = game.action(c, progress.action_id)
        if action["data"]["prepared"]["play"] != "go_off_duty":
            continue
        original, source = eligibility(c, game.store, state, period, owner)
        sheet = original.sheets.get(str(owner))
        if (
            sheet is None
            or sheet.character_id != period.character_ids.get(str(owner))
            or not has_rule(sheet, rules.RULE, "PRINCESS")
            or source is None
        ):
            continue
        actor = current_ref(original, owner)
        handler = active_handler(original)
        if handler is None:
            raise WorkflowError("Recover Show Dog's actual original Handler source")
        identity = str(uuid5(NAMESPACE_URL, "show-dog:" + period.id + ":" + actor.token))
        if identity in existing:
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, off_duty_id=period.id),
            identity,
            owner,
            owner,
            KIND,
            dict(
                actor=actor.model_dump(mode="json"),
                handler=handler.model_dump(mode="json"),
                source_action=action["id"],
                source_event=source,
                due_stage="active",
                source_pdf=33,
            ),
            event,
        )


def _source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> tuple[dict[str, Any], Period, rules.Show]:
    row = _latest(game, c).get(identity)
    if row is None:
        raise WorkflowError("Recover your genuine actual Go-OffDuty Show Dog work")
    body = json.loads(row["body_json"])
    period = OffDutyService(MissionService(game.store))._get(c, row["off_duty_id"])
    actor = ActorRef.model_validate(body["actor"])
    original, event = eligibility(c, game.store, state, period, int(actor.entity))
    action = game.action(c, body["source_action"])
    if (
        event is None
        or event != body["source_event"]
        or action["data"]["prepared"]["play"] != "go_off_duty"
        or period.progress[str(actor.entity)].action_id != action["id"]
        or actor != current_ref(original, int(actor.entity))
        or not has_rule(original.sheets[actor.entity], rules.RULE, "PRINCESS")
        or ActorRef.model_validate(body["handler"]) != active_handler(original)
    ):
        raise WorkflowError("Prove the actual original Go-OffDuty character, rule and receipt")
    base = rules.Show(
        id=identity,
        period=period.id,
        actor=actor,
        controller=int(actor.entity),
        handler=ActorRef.model_validate(body["handler"]),
        source_action=body["source_action"],
        source_event=event,
    )
    value = next((x for x in rules.records(state, rules.Show) if x.id == identity), base)
    if any(
        getattr(base, k) != getattr(value, k)
        for k in ("id", "period", "actor", "controller", "handler", "source_action", "source_event")
    ):
        raise WorkflowError("Preserve the immutable original Show Dog trigger")
    return row, period, value


def _save_work(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    row, _, value = _source(game, c, state, identity)
    done = rules.complete(state, value)
    table = t.m3["m3_required_work"]
    c.execute(
        table.insert().values(
            **{k: v for k, v in row.items() if k not in ("revision", "event_id", "state")},
            revision=row["revision"] + 1,
            event_id=event,
            state="resolved" if done else "pending",
        )
    )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Show:
    _, _, value = _source(game, c, state, identity)
    if value.first_event:
        _audit(game, c, value.first_event, "m3.show_dog_first", value.controller)
        saved = rules.get(_history(c, game, value.first_event), identity)
        if any(
            getattr(saved, k) != getattr(value, k)
            for k in ("first_kind", "first_event", "target", "tag", "message", "account")
        ):
            raise WorkflowError("Recover the actual original Princess's first appearance choice")
        if value.tag and value.target:
            if not any(
                x.id == value.tag
                for x in actor_tags(_history(c, game, value.first_event), value.target)
            ):
                raise WorkflowError("Recover the actual source-created Tag")
    if value.second_event:
        _audit(game, c, value.second_event, "m3.show_dog_second", value.controller)
        born = _history(c, game, value.second_event)
        saved = rules.get(born, identity)
        interest = _record(state, rules.Interest, value.interest or "")
        actual = resolve(
            born, interest.npc, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            saved.interest != value.interest
            or interest not in rules.records(born, rules.Interest)
            or interest.controller != actual.controller
            or interest.after != max(1, interest.before)
            or depth(born, value.actor, interest.npc) != interest.after
        ):
            raise WorkflowError(
                "Recover the chosen actual witnessed NPC, motivation and gained Bond"
            )
    if value.risk_event:
        _audit(game, c, value.risk_event, "m3.show_dog_risk", int(value.handler.entity))
        saved = rules.get(_history(c, game, value.risk_event), identity)
        if (
            saved.risk_decision != value.risk_decision
            or saved.punishment != value.punishment
            or saved.risk_account != value.risk_account
            or not value.risk_account.strip()
        ):
            raise WorkflowError("Recover the actual original Handler's risk decision")
    return value


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    value = prove(game, c, state, case.source_work or "")
    actual = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if (
        case.source_kind != "show_dog"
        or value.punishment != case.id
        or value.risk_event != case.source_event
        or value.actor != actual
        or case.executor != value.handler
        or case.chooser != value.handler
        or case.action != value.source_action
    ):
        raise WorkflowError("Recover the actual original Show Dog risk Punishment source")


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if case.effect_event is None or case.completion_event != event:
        raise WorkflowError("Complete the actual Show Dog Punishment and all its followups")
    _save_work(game, c, state, case.source_work, event)


def validate_npc_introduction(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer, identity: str, npc: Npc
) -> None:
    _access(game, c, viewer)
    row, period, value = _source(game, c, state, identity)
    actual = _native(game, c, state, value.actor)
    prove(game, c, state, identity)
    prior = c.scalar(
        sa.select(t.events.c.id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.npc_introduced",
            sa.func.json_extract(t.events.c.payload_json, "$.source_work") == identity,
        )
        .limit(1)
    )
    if (
        viewer.user_id != value.controller
        or row["state"] == "resolved"
        or value.second_event is not None
        or period.phase != "active"
        or game.pending_actions(c)
        or game.action(c, value.source_action)["state"] != "complete"
        or prior is not None
        or npc.controller != viewer.user_id
        or npc.jobs != ("civilian",)
        or npc.bonds
        or npc.tags
        or npc.captive_of is not None
        or npc.custody_event is not None
        or npc.faction is not None
        or npc.secret_factions
        or npc.employment != "unrecorded"
        or not npc.alive
        or state.world is None
        or not any(
            x.kind == "base"
            and x.allegiance == "foundation"
            and x.condition != "destroyed"
            and x.control_loss is None
            and x.cell == npc.cell == actual.cell
            for x in state.world.locations
        )
    ):
        raise WorkflowError(
            "Introduce at most one ordinary actual civilian at your present permitted base "
            "for this pending original Show Dog choice"
        )


class ShowDogService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _checked(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
        revision: int,
        game_revision: int,
        *,
        handler: bool = False,
    ) -> tuple[GameState, rules.Show]:
        self.game.unpaused(c)
        state = load_state(c, self.store.campaign_id)
        row, period, value = _source(self.game, c, state, identity)
        self.game.authorize(c, viewer, game=False)
        expected = int(value.handler.entity) if handler else value.controller
        if (
            viewer.user_id != expected
            or row["revision"] != revision
            or state.revision != game_revision
            or row["state"] == "resolved"
            or period.phase != "active"
            or self.game.pending_actions(c)
            or self.game.action(c, value.source_action)["state"] != "complete"
        ):
            raise WorkflowError("Reopen your actual original pending Show Dog choice")
        if handler:
            if active_handler(state) != value.handler:
                raise WorkflowError("Only the actual original Handler adjudicates this risk")
        else:
            _native(self.game, c, state, value.actor)
        prove(self.game, c, state, identity)
        return state, value

    def _known_npc(self, state: GameState, value: rules.Show, actor: ActorRef) -> bool:
        if actor.kind != "npc" or state.world is None:
            return False
        npc = next((x for x in state.world.npcs if x.id == actor.entity and x.alive), None)
        return bool(
            npc
            and (
                npc.revealed
                or npc.controller == value.controller
                or depth(state, value.actor, actor) > 0
                or any(
                    x.npc == npc.id
                    and x.owner == value.controller
                    and x.character_id == value.actor.incarnation
                    for x in state.world.starting_npc_links
                )
            )
        )

    def first(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        kind: str,
        *,
        target: ActorRef | None = None,
        tag: str = "",
        message: str = "",
        account: str,
    ) -> dict[str, Any]:
        if (
            kind not in rules.FIRST
            or not account.strip()
            or len(account) > 1200
            or (kind in ("trend", "public")) != bool(tag.strip())
            or (kind == "message") != bool(message.strip())
            or bool(target) != (kind != "quiet")
            or len(message) > 1200
        ):
            raise WorkflowError(
                "Supply exactly your actual printed first choice and necessary source fields"
            )

        def operation(c: Connection) -> dict[str, Any]:
            state, value = self._checked(c, viewer, identity, revision, game_revision)
            if value.first_event:
                raise WorkflowError("Your original first Show Dog choice is already saved")
            actual = (
                resolve(
                    state,
                    target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if target
                else None
            )
            if target and (
                target == value.actor
                or target.kind not in ("pilot", "handler", "npc")
                or target.kind == "npc"
                and not self._known_npc(state, value, target)
                or kind == "trend"
                and target.kind != "npc"
            ):
                raise WorkflowError("Choose the actual known source-legal person or NPC")
            event, outcome = str(uuid4()), str(uuid4())
            fields: dict[str, Any] = dict(
                first_kind=kind,
                first_event=event,
                target=target,
                account=account,
                risk_decision=False if kind == "quiet" else None,
            )
            if kind in ("trend", "public"):
                assert target is not None
                state = give_tag(
                    state,
                    profiles(c, self.store.campaign_id),
                    target,
                    value.actor,
                    tag.strip(),
                    outcome,
                    event,
                    tuple(
                        sorted(
                            set(_source(self.game, c, state, identity)[1].pilots)
                            | {int(value.handler.entity)}
                        )
                    ),
                )
                fields["tag"] = outcome
                if kind == "public":
                    rules.put(
                        state,
                        rules.Exposure(
                            id=outcome,
                            show=identity,
                            actor=value.actor,
                            target=target,
                            event=event,
                            account=account,
                        ),
                    )
            elif kind == "message":
                assert target is not None and actual is not None
                rules.put(
                    state,
                    rules.Message(
                        id=outcome,
                        show=identity,
                        sender=value.actor,
                        target=target,
                        controller=actual.controller,
                        event=event,
                        text=message.strip(),
                    ),
                )
                fields["message"] = outcome
            rules.put(state, value.model_copy(update=fields))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.show_dog_first",
                state,
                event_id=event,
                show=identity,
                branch=kind,
            )
            _save_work(self.game, c, state, identity, event)
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.show_dog_first",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                kind=kind,
                target=target.model_dump(mode="json") if target else None,
                tag=tag,
                message=message,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def second(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        npc: ActorRef,
        desire: str,
        account: str,
    ) -> dict[str, Any]:
        if desire not in rules.DESIRES or not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Choose the actual witnessed NPC's printed motivation and "
                "describe its actual view of your appearance"
            )

        def operation(c: Connection) -> dict[str, Any]:
            state, value = self._checked(c, viewer, identity, revision, game_revision)
            if value.second_event or not self._known_npc(state, value, npc):
                raise WorkflowError("Choose one actual known existing or genuinely introduced NPC")
            actual = resolve(
                state, npc, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            event, outcome = str(uuid4()), str(uuid4())
            before = depth(state, value.actor, npc)
            state = set_depth(state, value.actor, npc, 2 if before == 2 else 1, event)
            rules.put(
                state,
                rules.Interest(
                    id=outcome,
                    show=identity,
                    actor=value.actor,
                    npc=npc,
                    controller=actual.controller,
                    desire=cast(rules.Desire, desire),
                    event=event,
                    appearance=account,
                    before=before,
                    after=depth(state, value.actor, npc),
                ),
            )
            rules.put(state, value.model_copy(update=dict(second_event=event, interest=outcome)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.show_dog_second",
                state,
                event_id=event,
                show=identity,
                interest=outcome,
            )
            _save_work(self.game, c, state, identity, event)
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.show_dog_second",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                npc=npc.model_dump(mode="json"),
                desire=desire,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def risk(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        punish: bool,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record the actual original Handler's risk adjudication")

        def operation(c: Connection) -> dict[str, Any]:
            state, value = self._checked(c, viewer, identity, revision, game_revision, handler=True)
            if value.first_kind in (None, "quiet") or value.risk_event:
                raise WorkflowError("Adjudicate only this original risky performed first choice")
            event = str(uuid4())
            case_id = None
            if punish:
                from girlframe.services.m3_role_punishments import open_case

                state, case_id = open_case(
                    state,
                    profiles(c, self.store.campaign_id),
                    actor=value.handler,
                    target=value.actor,
                    chooser=value.handler,
                    source_kind="show_dog",
                    action=value.source_action,
                    source_event=event,
                    identity=str(uuid4()),
                    source_work=value.id,
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        risk_event=event,
                        risk_decision=punish,
                        punishment=case_id,
                        risk_account=account,
                    )
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.show_dog_risk", state, event_id=event, show=identity
            )
            _save_work(self.game, c, state, identity, event)
            if punish:
                from girlframe.services.m3_role_punishments import synchronize as sync_punishment

                sync_punishment(self.game, c, None, event)
            return dict(id=identity, punishment=case_id)

        return self.store._write(
            viewer,
            key,
            "m3.show_dog_risk",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                punish=punish,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            row, _, value = _source(self.game, c, state, identity)
            prove(self.game, c, state, identity)
            if viewer.user_id not in (value.controller, int(value.handler.entity)):
                raise WorkflowError(
                    "Only the actual original Princess and risk Handler read this source"
                )
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                actor=value.actor.model_dump(mode="json"),
                first=value.first_kind,
                account=value.account,
                second=value.interest is not None,
                risk=value.risk_decision,
                risk_account=value.risk_account,
                punishment=value.punishment,
                complete=rules.complete(state, value),
                can_choose=viewer.user_id == value.controller and row["state"] != "resolved",
                can_risk=viewer.user_id == int(value.handler.entity)
                and value.first_kind not in (None, "quiet")
                and value.risk_event is None,
            )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        if identity is None:
            with self.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                return dict(tasks=self._tasks(c, viewer))
        data = self.view(viewer, identity)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            _, _, value = _source(self.game, c, state, identity)
            people = []
            npcs = []
            for sheet in state.sheets.values():
                if sheet.owner != value.controller and sheet.character_id:
                    ref = current_ref(state, sheet.owner)
                    people.append(dict(ref=ref.model_dump(mode="json"), label=sheet.callsign))
            if state.world:
                for npc in state.world.npcs:
                    ref = ActorRef(kind="npc", entity=npc.id)
                    if self._known_npc(state, value, ref):
                        item = dict(ref=ref.model_dump(mode="json"), label=npc.name)
                        people.append(item)
                        npcs.append(item)
            people.append(dict(ref=value.handler.model_dump(mode="json"), label="Original Handler"))
            cell = (
                resolve(state, value.actor, profiles(c, self.store.campaign_id)).cell
                if data["can_choose"]
                else None
            )
            return data | dict(
                people=people,
                npcs=npcs,
                bases=[
                    dict(id=x.id, name=x.name, cell=list(x.cell))
                    for x in state.world.locations
                    if x.kind == "base"
                    and x.condition != "destroyed"
                    and x.control_loss is None
                    and x.allegiance == "foundation"
                    and x.cell == cell
                ]
                if state.world
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for row in _latest(self.game, c).values():
            _, _, value = _source(self.game, c, state, row["id"])
            if viewer.user_id in (value.controller, int(value.handler.entity)):
                result.append(
                    dict(
                        id=value.id,
                        label="Your original Show Dog appearance choices",
                        phase=row["state"],
                        revision=row["revision"],
                        pending=row["state"] != "resolved"
                        and (
                            viewer.user_id == value.controller
                            and (value.first_event is None or value.second_event is None)
                            or viewer.user_id == int(value.handler.entity)
                            and value.first_kind not in (None, "quiet")
                            and value.risk_event is None
                        ),
                    )
                )
        return result

    def _messages(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id, label="Addressed Show Dog message", revision=state.revision, pending=False
            )
            for x in rules.records(state, rules.Message)
            if viewer.user_id in (int(x.sender.entity), x.controller)
        ]

    def _interests(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                label="Your NPC's Show Dog appearance interest",
                revision=state.revision,
                pending=False,
            )
            for x in rules.records(state, rules.Interest)
            if viewer.user_id in (int(x.actor.entity), x.controller)
        ]

    def view_message(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _record(state, rules.Message, identity)
            if viewer.user_id not in (int(value.sender.entity), value.controller):
                raise WorkflowError(
                    "This addressed message belongs only to its original sender and recipient"
                )
            prove(self.game, c, state, value.show)
            if value not in rules.records(_history(c, self.game, value.event), rules.Message):
                raise WorkflowError("Recover the actual addressed message birth")
            born = _history(c, self.game, value.event)
            return dict(
                id=value.id,
                text=value.text,
                target=value.target.model_dump(mode="json"),
                sender=born.sheets[value.sender.entity].callsign,
                recipient=born.sheets[value.target.entity].callsign
                if value.target.kind == "pilot"
                else next(
                    (x.name for x in born.world.npcs if x.id == value.target.entity),
                    value.target.entity,
                )
                if value.target.kind == "npc" and born.world
                else "Original Handler",
            )

    def view_interest(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _record(state, rules.Interest, identity)
            if viewer.user_id not in (int(value.actor.entity), value.controller):
                raise WorkflowError(
                    "This printed NPC interest belongs to its actual controller "
                    "and original Princess"
                )
            prove(self.game, c, state, value.show)
            born = _history(c, self.game, value.event)
            return dict(
                id=value.id,
                npc=value.npc.model_dump(mode="json"),
                princess=born.sheets[value.actor.entity].callsign,
                desire=value.desire,
                appearance=value.appearance,
            )
