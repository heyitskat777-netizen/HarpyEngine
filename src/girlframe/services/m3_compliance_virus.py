"""Actual cockpit infection, factual touch review and honest printed fixed11 purge."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_compliance_virus as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_compliance_virus_state import FrameRef, InfectedPerson, Purge, Strain
from girlframe.engine.m3_enforcer_requisitions import VIRUS
from girlframe.engine.m3_enforcer_requisitions import held as historical_held
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.engine.m3_role_punishments import bond_ref
from girlframe.engine.m3_role_punishments import view as person_view
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_enforcer_requisitions import owned
from girlframe.services.m3_enforcer_requisitions import proof as grant_proof
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KIND = "compliance_virus_purge"


def _history(c: Connection, game: "GameService", event: str | None) -> GameState:
    if not event:
        raise WorkflowError("Actual source event is required.")
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the immutable actual Virus source history.")
    return GameState.model_validate_json(raw)


def _audit(c: Connection, game: "GameService", event: str | None, human: int, kind: str) -> None:
    row = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if row is None or str(row.actor_id) != str(human) or row.kind != kind:
        raise WorkflowError("Recover the actual authenticated human Virus source event.")


def _cast(game: "GameService", c: Connection, state: GameState, channel: int) -> SceneCast:
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_missions import MissionService

    return CastService(ActorService(MissionService(game.store)))._current(c, state, channel)[0]


def _copy(destination: GameState, source: GameState) -> None:
    for name in GameState.model_fields:
        setattr(destination, name, getattr(source, name))


def prove_strain(c: Connection, game: "GameService", state: GameState, identity: str) -> Strain:
    strain = rules.record(state, Strain, identity)
    first = rules.record(_history(c, game, strain.source_event), Strain, identity)
    if first != strain.model_copy(update={"purged_event": None}):
        raise WorkflowError("A virus strain cannot change its original creator, grant or Frame.")
    _audit(c, game, strain.source_event, strain.controller, "m3.compliance_virus_infected")
    source = _history(c, game, strain.source_event)
    actual = historical_held(source, strain.creator, VIRUS)
    if actual is not None:
        grant_proof(c, game, actual)
        if strain.creator.kind == "external_pilot":
            from girlframe.services.m3_tag_permissions import prove_birth

            prove_birth(c, game, source, strain.creator)
    position = rules.cockpit(source, strain.creator)
    if (
        actual is None
        or actual.id != strain.grant
        or position is None
        or not rules.same_frame(source, position[0], strain.target)
        or position[1] != strain.cockpit_source
    ):
        raise WorkflowError(
            "Recover actual owned ability and actual occupied cockpit at infection."
        )
    return strain


def prove_person(
    c: Connection, game: "GameService", state: GameState, identity: str
) -> InfectedPerson:
    person = rules.record(state, InfectedPerson, identity)
    first = rules.record(_history(c, game, person.source_event), InfectedPerson, identity)
    strain = prove_strain(c, game, state, person.strain)
    source = _history(c, game, person.source_event)
    if (
        first != person.model_copy(update={"purged_event": None})
        or (person.actor, person.link_source) not in rules.linked(source, strain.target)
        and not _past_link_proof(c, game, state, person)
    ):
        raise WorkflowError(
            "Actual infection needs its original linked person and actual link source."
        )
    return person


def _past_link_proof(
    c: Connection, game: "GameService", state: GameState, person: InfectedPerson
) -> bool:
    from girlframe.engine.m3_compliance_virus_state import PastLinkExposure
    from girlframe.services.m3_virus_exposure import prove_exposure

    exposure = next(
        (
            x
            for x in rules.records(state, PastLinkExposure)
            if x.strain == person.strain
            and x.actor == person.actor
            and x.reviewed_event == person.link_source
            and x.phase == "approved"
        ),
        None,
    )
    if exposure is None or exposure.reviewed_event != person.source_event:
        return False
    prove_exposure(c, game, exposure)
    return True


def _row(c: Connection, game: "GameService", work: str, *, first: bool = False) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work)
            .order_by(table.c.revision.asc() if first else table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != KIND:
        raise WorkflowError("Recover the actual source purge work.")
    return dict(row)


def source(c: Connection, game: "GameService", identity: str) -> tuple[GameState, Purge]:
    state = load_state(c, game.store.campaign_id)
    value = rules.record(state, Purge, identity)
    first = rules.record(_history(c, game, value.source_event), Purge, identity)
    stable = (
        "id",
        "kind",
        "strain",
        "creator",
        "creator_controller",
        "creator_frame",
        "grant",
        "target_frame",
        "person_infection",
        "scope",
        "channel",
        "judge",
        "judge_controller",
        "appointment",
        "registry",
        "cast_json",
        "cast_sha256",
        "source_event",
        "account",
        "operational_action",
        "frame_controller",
    )
    if any(getattr(first, k) != getattr(value, k) for k in stable):
        raise WorkflowError("Recover the actual original purge cause and human roles.")
    _audit(
        c, game, value.source_event, value.creator_controller, "m3.compliance_virus_purge_started"
    )
    row = _row(c, game, identity, first=True)
    if (
        row["event_id"] != value.source_event
        or json.loads(row["body_json"]).get("purge") != value.id
    ):
        raise WorkflowError("This required work is not the actual canonical purge source.")
    strain = prove_strain(c, game, state, value.strain)
    if value.kind == "girl" and (
        value.target != first.target or value.target_controller != first.target_controller
    ):
        raise WorkflowError("Original touch-purge recipient cannot change bodies.")
    if value.kind == "frame" and value.target is not None:
        effect_state = _history(c, game, value.effect_event)
        effect = rules.record(effect_state, Purge, value.id)
        if (
            effect.target != value.target
            or effect.target_controller != value.target_controller
            or not any(
                actor == value.target for actor, _ in rules.linked(effect_state, strain.target)
            )
        ):
            raise WorkflowError("Remote pain needs actual original linked at post-lock effect.")
    if value.kind == "frame" and value.phase == "complete" and value.role_case is None:
        from girlframe.services.m3_virus_operations import prove_vacancy

        prove_vacancy(game, c, value)
    if value.person_infection:
        prove_person(c, game, state, value.person_infection)
    return state, value


def _authority(
    c: Connection, game: "GameService", state: GameState, value: Purge, *, creator: bool = True
) -> None:
    _, appointment = MedicalService(game.store)._handler(c)
    approval = game.store.policy.m3_approval
    if (
        appointment != value.appointment
        or approval is None
        or approval.registry_sha256 != value.registry
    ):
        raise WorkflowError("Recover the original actual source appointment and reviewed rules.")
    if creator:
        grant = owned(c, game, state, value.creator, VIRUS)
        actual = resolve(
            state, value.creator, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            grant is None
            or grant.id != value.grant
            or actual.controller != value.creator_controller
            or actual.frame_instance != value.creator_frame
        ):
            raise WorkflowError(
                "A successor body or new Frame cannot use the original Virus purge."
            )
    if value.phase not in ("complete", "ended", "queued"):
        from girlframe.services.m3_virus_operations import held

        held(game, c, value)
    original = SceneCast.model_validate_json(value.cast_json)
    current = _cast(game, c, state, value.channel)
    if fingerprint(original) != value.cast_sha256:
        raise WorkflowError("Recover the original source cast fingerprint.")
    if current != original:
        from girlframe.services.m3_harpy_defeat import ended_director_judge

        if value.judge is None or not ended_director_judge(
            game, c, state, original, current, value.judge, value.judge_controller
        ):
            raise WorkflowError("SOURCE_TABLE_CHANGED: recover the original purge cast.")


def role_scope(c: Connection, game: "GameService", case: RolePunishment) -> WorkScope:
    _, value = source(c, game, case.source_work or "")
    return value.scope


def validate_role_case(
    c: Connection, game: "GameService", state: GameState, case: RolePunishment
) -> None:
    _, value = source(c, game, case.source_work or "")
    if case.ended_event is not None:
        from girlframe.services.m3_harpy_defeat import ended_actor_source

        if (
            case.ended_actor is None
            or value.phase != "ended"
            or value.completion_event != case.ended_event
            or case.ended_actor not in (value.creator, value.target)
            or case.effect_event is not None
            or case.completion_event is not None
            or ended_actor_source(game, c, state, case.ended_actor) != case.ended_event
        ):
            raise WorkflowError("Only actual original ending can close unperformed source case.")
        proof = rules.record(_history(c, game, case.ended_event), Purge, value.id)
        if proof.phase != "ended" or proof.role_case != case.id:
            raise WorkflowError("Recover the original canonical source-case ending.")
        return
    if value.target is None:
        raise WorkflowError("A real Punishment needs its actual original affected person.")
    # Already-completed historical reads preserve exact source rather than demand a living body.
    if case.completion_event is None:
        _authority(c, game, state, value, creator=case.completion_event is None)
    if (
        value.role_case != case.id
        or value.phase not in ("punishment", "complete")
        or case.source_kind != "compliance_virus"
        or case.action is not None
        or case.executor != value.punishment_executor
        or case.executor_frame != value.punishment_executor_frame
        or case.subject != bond_ref(state, value.target)
        or case.subject_controller != value.target_controller
        or case.chooser != value.judge
        or case.chooser_controller != value.judge_controller
        or case.source_event != value.effect_event
    ):
        raise WorkflowError(
            "This exact original purge cannot authorize another Punishment or body."
        )
    expected_controller = (
        value.creator_controller if value.kind == "frame" else value.judge_controller
    )
    if case.executor_controller != expected_controller:
        raise WorkflowError("Use the actual source original executor's human.")
    proof = rules.record(_history(c, game, value.effect_event), Purge, value.id)
    if proof.role_case != case.id or proof.phase != "punishment":
        raise WorkflowError("Recover genuine canonical Punishment cause.")
    if value.kind == "frame":
        from girlframe.services.m3_virus_operations import prove_effect

        prove_effect(game, c, value)
        if value.punishment_executor != value.creator:
            raise WorkflowError("Only actual Virus owner inflicts its printed fixed11 Punishment.")
    else:
        from girlframe.services.m3_virus_orders import prove_discovery

        prove_discovery(game, c, value)


def _write_work(c: Connection, game: "GameService", value: Purge, event: str) -> None:
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, **value.scope.model_dump()),
        value.id,
        value.creator_controller,
        value.target_controller or value.frame_controller,
        KIND,
        dict(
            purge=value.id,
            owner=value.creator.model_dump(mode="json"),
            target=value.target.model_dump(mode="json") if value.target else None,
            source_action=value.operational_action,
            source_event=value.source_event,
            immediate=True,
        ),
        event,
    )


def _resolve_work(c: Connection, game: "GameService", value: Purge, event: str) -> None:
    row = _row(c, game, value.id)
    if row["state"] == "resolved":
        from girlframe.services.m3_virus_operations import finish

        finish(game, c, value, event)
        return
    table = t.m3["m3_required_work"]
    body = json.loads(row["body_json"]) | dict(
        completed_by_purge=value.id,
        completion_event=event,
        original_target_ended=value.phase == "ended",
    )
    c.execute(
        table.insert().values(
            **(
                {
                    k: row[k]
                    for k in table.c.keys()
                    if k not in ("revision", "state", "body_json", "event_id")
                }
                | dict(
                    revision=row["revision"] + 1,
                    state="resolved",
                    body_json=json.dumps(body, sort_keys=True),
                    event_id=event,
                )
            )
        )
    )

    from girlframe.services.m3_virus_operations import finish

    finish(game, c, value, event)


def complete_role_case(
    c: Connection, game: "GameService", case: RolePunishment, event: str
) -> None:
    state, value = source(c, game, case.source_work or "")
    validate_role_case(c, game, state, case)
    if value.phase == "complete":
        return
    if not case.completion_event or not case.effect_event:
        raise WorkflowError("Finish actual Punishment and its immediate source descendants first.")
    proof = _history(c, game, case.completion_event)
    actual = next((x for x in proof.role_punishments if x.id == case.id), None)
    if actual is None or actual.completion_event != case.completion_event:
        raise WorkflowError("A label cannot replace actual original Punishment completion.")
    changed = rules.complete(state, value.id, event)
    source_event = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.command_key).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if source_event is None:
        raise WorkflowError("Recover actual authenticated completion source.")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == source_event.command_key,
        )
    )
    completed = game.event(
        c,
        str(source_event.actor_id),
        str(source_event.command_key),
        "m3.compliance_virus_completed",
        changed,
        event_index=int(index or 0) + 1,
        purge=value.id,
        source_event=event,
    )
    if value.kind == "girl":
        from girlframe.services.m3_virus_orders import complete_disobey_punishment

        complete_disobey_punishment(game, c, rules.record(changed, Purge, value.id), completed)
    else:
        _resolve_work(c, game, rules.record(changed, Purge, value.id), completed)


def after_link_transition(
    game: "GameService", c: Connection, state: GameState, event: str
) -> GameState:
    """Pre-event hook ONLY real canonical physical/link writes; no transmission on mere read."""
    actors = tuple(
        place.actor
        for place in state.placements
        if place.source_event == event and place.mode == "piloting"
    )
    return (
        rules.spread(state, profiles(c, game.store.campaign_id), event, actors=actors)
        if actors
        else state
    )


class VirusService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        registry = access.registry
        if registry is None:
            raise WorkflowError("Recover reviewed Compliance Virus source registry.")
        registry.require_available(VIRUS)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                body,
                operation,
                auto_audit=False,
                authorize=lambda c: self._authorize(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def preview(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            cast = _cast(self.game, c, state, channel)
            grant = owned(c, self.game, state, actor, VIRUS)
            if (
                grant is None
                or actual.controller != viewer.user_id
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
            ):
                raise WorkflowError("Select your actual source-owned Compliance Virus role.")
            strains = [
                x
                for x in rules.records(state, Strain)
                if x.grant == grant.id and x.purged_event is None
            ]
            people = [
                x
                for x in rules.records(state, InfectedPerson)
                if x.purged_event is None
                and any(
                    y.id == x.strain for y in rules.records(state, Strain) if y.grant == grant.id
                )
            ]
            for strain in strains:
                prove_strain(c, self.game, state, strain.id)
            current_people = []
            for person in people:
                prove_person(c, self.game, state, person.id)
                try:
                    current = person_view(state, person.actor, profiles(c, self.store.campaign_id))
                except ValueError:
                    continue
                if current.rules in ("girl_frame", "handler_girl") or current.girl == "harpy":
                    current_people.append(person)
            people = current_people
            from girlframe.services.m3_battle import _visible

            cockpit = rules.cockpit(state, actor)
            return dict(
                actor=actor.model_dump(mode="json"),
                source_sha256=actual.source_sha256,
                cockpit=cockpit[0].model_dump(mode="json")
                if cockpit
                and not any(rules.same_frame(state, x.target, cockpit[0]) for x in strains)
                else None,
                frames=[
                    dict(id=x.id, label="Actual infected Frame " + x.target.instance)
                    for x in strains
                ],
                people=[
                    dict(
                        id=x.id,
                        label=person_view(state, x.actor, profiles(c, self.store.campaign_id)).label
                        if _visible(state, x.actor, viewer.user_id)
                        else "Source-infected original (identity unrevealed)",
                    )
                    for x in people
                ],
            )

    def _can_act(self, c: Connection, viewer: GuildViewer) -> bool:
        try:
            self._authorize(c, viewer)
            self.game.unpaused(c)
        except (WorkflowError, ValueError):
            return False
        return True

    def infect(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        target: FrameRef,
        expected: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            cast = _cast(self.game, c, state, channel)
            if (
                actual.controller != viewer.user_id
                or actual.source_sha256 != expected
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
            ):
                raise WorkflowError(
                    "Confirm your actual original cockpit and reviewed Virus ability."
                )
            if self.game.pending_actions(c):
                raise WorkflowError("SCENE_BUSY: new infection cannot jump an owned pending Play.")
            if owned(c, self.game, state, actor, VIRUS) is None:
                raise WorkflowError("Only the actual current owner can infect this cockpit.")
            event = str(uuid4())
            changed = rules.infect(
                state, actor, target, profiles(c, self.store.campaign_id), event, account
            )
            self.game.event(
                c, viewer.user_id, key, "m3.compliance_virus_infected", changed, event_id=event
            )
            strain = next(x for x in rules.records(changed, Strain) if x.source_event == event)
            return dict(id=strain.id)

        return self._write(
            viewer,
            key,
            "m3.compliance_virus_infected",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                target=target.model_dump(mode="json"),
                expected=expected,
                account=account,
            ),
            operation,
        )

    def begin_purge(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        infection: str,
        kind: Literal["girl", "frame"],
        account: str,
    ) -> dict[str, Any]:
        from girlframe.engine.m3_handler_consequences import active_handler
        from girlframe.services.m3_battle import _scene_judge
        from girlframe.services.m3_virus_operations import reserve

        if kind not in ("girl", "frame") or not account.strip():
            raise WorkflowError("Choose one actual infection and describe the actual purge.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if self.game.pending_actions(c):
                raise WorkflowError("SCENE_BUSY: new purge cannot jump a pending Play.")
            cast = _cast(self.game, c, state, channel)
            grant = owned(c, self.game, state, actor, VIRUS)
            own = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                grant is None
                or own.frame_instance is None
                or own.controller != viewer.user_id
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
            ):
                raise WorkflowError("Only actual source-owned Virus role may begin this purge.")
            person = prove_person(c, self.game, state, infection) if kind == "girl" else None
            strain = prove_strain(c, self.game, state, person.strain if person else infection)
            if (
                strain.grant != grant.id
                or (person and person.purged_event)
                or (not person and strain.purged_event)
            ):
                raise WorkflowError("Select this original source's actual unpurged infection.")
            target = person.actor if person else None
            other = (
                person_view(state, target, profiles(c, self.store.campaign_id)) if target else None
            )
            if kind == "girl" and (
                other is None
                or other.rules not in ("girl_frame", "handler_girl")
                and other.girl != "harpy"
            ):
                raise WorkflowError("Only actual Girl-side infection has this direct-order port.")
            if other and own.cell is not None and other.cell is not None and own.cell != other.cell:
                raise WorkflowError("Actual known positions contradict touching this Girl.")
            frame_owner = person_view(
                state, rules.frame_actor(state, strain.target), profiles(c, self.store.campaign_id)
            )
            judge, human, _ = _scene_judge(self.game, c, state, cast)
            if judge is None:
                judge = active_handler(state)
            _, appointment = MedicalService(self.store)._handler(c)
            approval = self.store.policy.m3_approval
            if approval is None:
                raise WorkflowError("Actual source operation requires reviewed policy.")
            event, identity, operational = str(uuid4()), str(uuid4()), str(uuid4())
            value = Purge(
                id=identity,
                kind=kind,
                strain=strain.id,
                creator=actor,
                creator_controller=own.controller,
                creator_frame=own.frame_instance,
                grant=grant.id,
                target=target,
                target_controller=other.controller if other else None,
                frame_controller=frame_owner.controller,
                operational_action=operational,
                target_frame=strain.target if kind == "frame" else None,
                person_infection=person.id if person else None,
                scope=WorkScope(scene_id=cast.id),
                channel=channel,
                judge=judge,
                judge_controller=human,
                appointment=appointment,
                registry=approval.registry_sha256,
                cast_json=cast.model_dump_json(),
                cast_sha256=fingerprint(cast),
                source_event=event,
                account=account,
                phase="queued",
            )
            rules.put(state, value)
            reserve(self.game, c, state, value, own.label)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.compliance_virus_purge_started",
                state,
                event_id=event,
                purge=identity,
                action_id=operational,
                method="confirmed_diceless_operation_pending_chat_lock",
            )
            _write_work(c, self.game, value, event)
            return dict(id=identity, phase="queued", action_id=operational)

        return self._write(
            viewer,
            key,
            "m3.compliance_virus_purge_started",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                infection=infection,
                kind=kind,
                account=account,
            ),
            operation,
        )

    def review_contact(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        confirmed: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = source(c, self.game, identity)
            _authority(c, self.game, state, value)
            if (
                viewer.user_id != value.judge_controller
                or value.phase != "contact_review"
                or value.revision != revision
                or type(confirmed) is not bool
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only actual frozen judge factually reviews this original touch."
                )
            event = str(uuid4())
            updated = value.model_copy(
                update=dict(
                    review_event=event,
                    contact_confirmed=confirmed,
                    phase="order" if confirmed else "contact_review",
                    revision=value.revision + 1,
                )
            )
            if confirmed:
                state = rules.touch_purge(state, updated, event)
            else:
                rules.put(state, updated)
            if confirmed and value.target == value.creator:
                updated = updated.model_copy(
                    update=dict(
                        phase="complete", effect_event=event, completion_event=event, order_text=""
                    )
                )
                rules.put(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.compliance_virus_contact_reviewed",
                state,
                event_id=event,
                purge=identity,
                confirmed=confirmed,
                account=account,
                self_purge_no_order=confirmed and value.target == value.creator,
            )
            from girlframe.services.m3_virus_operations import advance

            advance(self.game, c, updated, event)
            if updated.phase == "complete":
                _resolve_work(c, self.game, updated, event)
            return dict(id=identity, phase=updated.phase)

        return self._write(
            viewer,
            key,
            "m3.compliance_virus_contact_reviewed",
            dict(id=identity, revision=revision, confirmed=confirmed, account=account),
            operation,
        )

    def issue_order(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, text: str
    ) -> dict[str, Any]:
        from girlframe.services.m3_virus_orders import create_order

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = source(c, self.game, identity)
            _authority(c, self.game, state, value)
            if (
                viewer.user_id != value.creator_controller
                or value.revision != revision
                or value.phase != "order"
                or not text.strip()
                or len(text) > 1200
            ):
                raise WorkflowError("Original Virus owner gives this actual one-shot direct order.")
            return create_order(self.game, c, state, value, viewer, key, text)

        return self._write(
            viewer,
            key,
            "m3.compliance_virus_order_issued",
            dict(id=identity, revision=revision, text=text),
            operation,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, value = source(c, self.game, identity)
            if viewer.user_id not in (
                value.creator_controller,
                value.target_controller,
                value.frame_controller,
                value.judge_controller,
            ):
                raise WorkflowError(
                    "This actual source purge is private to its original human roles."
                )
            return dict(
                id=value.id,
                revision=value.revision,
                phase=value.phase,
                kind=value.kind,
                creator=value.creator_controller,
                target=value.target_controller,
                judge=value.judge_controller,
                immune=value.immune,
                case=value.role_case,
                order_action=value.order_action,
                vacancy_kind=value.vacancy_kind,
                can_act=self._can_act(c, viewer)
                and (
                    viewer.user_id == value.frame_controller
                    if value.phase == "vacancy_proposal"
                    else viewer.user_id == value.judge_controller
                    if value.phase in ("vacancy_review", "contact_review")
                    else viewer.user_id == value.creator_controller
                    if value.phase == "order"
                    else viewer.user_id
                    in (value.creator_controller, value.target_controller, value.judge_controller)
                    if value.phase == "punishment"
                    else False
                ),
                method="PRINTED FIXED11 / NO ROLL"
                if value.kind == "frame"
                else "ACTUAL TOUCH / ONE-SHOT ORDER",
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, Purge):
            owner = (
                value.frame_controller
                if value.phase == "vacancy_proposal"
                else value.judge_controller
                if value.phase in ("contact_review", "vacancy_review")
                else value.creator_controller
            )
            if viewer.user_id != owner or value.phase not in (
                "contact_review",
                "order",
                "vacancy_proposal",
                "vacancy_review",
            ):
                continue
            source(c, self.game, value.id)
            result.append(
                dict(
                    id=value.id,
                    kind="compliance_virus",
                    state=value.phase,
                    can_act=self._can_act(c, viewer),
                    label="Review actual touching facts"
                    if value.phase == "contact_review"
                    else "Give actual one-shot direct order",
                )
            )
        return result


def prepare_transmission(
    game: "GameService", c: Connection, previous: GameState, state: GameState, event: str
) -> GameState:
    """Canonical prewrite bridge: only a new actual source-proved link or actual infection.

    No invocation on a read, missing legacy pose, assigned Frame, mere scene presence,
    unchanged link or arbitrary event can transmit to an invented person.
    """
    changed = rules.clone(state)
    bound = profiles(c, game.store.campaign_id)
    for strain in rules.records(state, Strain):
        if strain.purged_event is not None:
            continue
        previous_links = rules.linked(previous, strain.target)
        for actor, link_event in rules.linked(state, strain.target):
            if (actor, link_event) in previous_links or link_event != event:
                continue
            physical = any(
                x.get("kind") == "physical_operation"
                and x.get("source_event") == event
                and x.get("actor") == actor.model_dump_json()
                and x.get("operation") in ("cockpit_enter", "initial_placement")
                for x in state.facts
            )
            birth = actor.kind == "external_pilot" and any(
                x.resulting_actor == actor and x.stage == "converted" and x.response_event == event
                for x in state.void_thresholds
            )
            native = actor.kind == "external_pilot" and any(
                x.id == actor.entity and x.source_event == event and x.linked
                for x in state.native_harpies
            )
            reviewed_link = False
            for purge in rules.records(state, Purge):
                if (
                    purge.target == actor
                    and purge.vacancy_kind == "owner_linked"
                    and purge.vacancy_reviewed_event == event
                ):
                    _audit(
                        c,
                        game,
                        purge.vacancy_proposed_event,
                        purge.frame_controller,
                        "m3.virus_frame_occupancy_proposed",
                    )
                    _audit(
                        c, game, event, purge.judge_controller, "m3.virus_frame_occupancy_reviewed"
                    )
                    reviewed_link = True
            if not (physical or birth or native or reviewed_link):
                raise WorkflowError(
                    "Recover actual source-proved link transition before Virus transmission."
                )
            if any(
                x.actor == actor and x.strain == strain.id and x.purged_event is None
                for x in rules.records(changed, InfectedPerson)
            ):
                continue
            actual = resolve(state, actor, bound, require_current_profile=False)
            rules.put(
                changed,
                InfectedPerson(
                    id=rules.identity("person", strain.id, actor.token, event),
                    strain=strain.id,
                    actor=actor,
                    controller=actual.controller,
                    source_event=event,
                    link_source=event,
                ),
            )
    return changed


def end_actor(original: GameState, actor: ActorRef, event: str) -> GameState:
    """Exact-body impossibility record only; actual completed Punishment callbacks take priority."""
    from girlframe.engine.m3_compliance_virus_state import PainRestraint

    state = rules.clone(original)
    for value in rules.records(state, Purge):
        if value.phase in ("complete", "ended") or actor not in (value.creator, value.target):
            continue
        # Actual applied effects and immediate descendants retain their existing completion.
        if value.phase == "punishment":
            case = next((x for x in state.role_punishments if x.id == value.role_case), None)
            if case is None or case.effect_event is not None:
                continue
            state.role_punishments = [
                x.model_copy(update=dict(ended_event=event, ended_actor=actor))
                if x.id == case.id
                else x
                for x in state.role_punishments
            ]
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    phase="ended",
                    completion_event=event,
                    end_reason="actual_original_ended",
                    revision=value.revision + 1,
                )
            ),
        )
        for pain in rules.records(state, PainRestraint):
            if pain.purge == value.id and pain.active:
                rules.put(state, pain.model_copy(update=dict(active=False, ended_event=event)))
    return state


def synchronize_endings(game: "GameService", c: Connection, event: str) -> None:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    state = load_state(c, game.store.campaign_id)
    for value in rules.records(state, Purge):
        if value.phase != "ended" or value.completion_event != event:
            continue
        if value.end_reason == "cancelled_before_effect":
            if value.cancelled_by is None:
                raise WorkflowError("Cancellation needs actual human actor.")
            _audit(c, game, event, value.cancelled_by, "m3.compliance_virus_cancelled")
            if value.effect_event is not None or value.role_case is not None:
                raise WorkflowError("Cancellation cannot waive an actual effect or Punishment.")
            _resolve_work(c, game, value, event)
            continue
        if not any(
            ended_actor_source(game, c, state, actor) == event
            for actor in (value.creator, value.target)
            if actor is not None
        ):
            raise WorkflowError("No actual original career/body ending proves this source closure.")
        case = next((x for x in state.role_punishments if x.id == value.role_case), None)
        if case is not None and case.ended_event == event and case.pc_work:
            table = t.m3["m3_required_work"]
            work_row = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == game.store.campaign_id, table.c.id == case.pc_work
                    )
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if work_row is not None and work_row["state"] != "resolved":
                body = json.loads(work_row["body_json"])
                if body.get("role_case") != case.id:
                    raise WorkflowError("Recover exact original unperformed Punishment source.")
                c.execute(
                    table.insert().values(
                        **(
                            {
                                k: work_row[k]
                                for k in table.c.keys()
                                if k not in ("revision", "state", "body_json", "event_id")
                            }
                            | dict(
                                revision=work_row["revision"] + 1,
                                state="resolved",
                                body_json=json.dumps(
                                    body
                                    | dict(actual_original_ended=event, no_punishment_applied=True)
                                ),
                                event_id=event,
                            )
                        )
                    )
                )
        if value.order_action:
            action = game.action(c, value.order_action)
            choices = t.m2["m2_choices"]
            if action["data"].get("disobey_child"):
                child = game.action(c, action["data"]["disobey_child"])
                if (
                    child["parent_id"] != action["id"]
                    or child["data"].get("virus_disobey", {}).get("purge") != value.id
                ):
                    raise WorkflowError("Recover exact original impossible Disobey child.")
                for row in game.pending(c, child["id"]):
                    c.execute(
                        choices.update()
                        .where(
                            choices.c.campaign_id == game.store.campaign_id,
                            choices.c.id == row["id"],
                        )
                        .values(
                            state="completed_original_ended",
                            revision=row["revision"] + 1,
                            body_json=json.dumps(
                                json.loads(row["body_json"]) | dict(actual_ending=event)
                            ),
                        )
                    )
                child["state"] = "complete"
                child["data"]["result"]["original_ended"] = event
                game.save_action(c, child)
                game.queue(
                    c,
                    child,
                    "outcome",
                    dict(
                        play="disobey_orders",
                        callsign=child["data"]["actor_basic"]["label"],
                        receipt=child["data"].get("receipt"),
                        total=child["data"]["result"].get("total"),
                        tier=child["data"]["result"].get("tier"),
                        original_ended=True,
                    ),
                )
            for row in game.pending(c, action["id"]):
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"]
                    )
                    .values(
                        state="completed_original_ended",
                        revision=row["revision"] + 1,
                        body_json=json.dumps(
                            json.loads(row["body_json"]) | dict(actual_ending=event)
                        ),
                    )
                )
            action["state"] = "complete"
            action["data"]["result"]["original_ended"] = event
            game.save_action(c, action)
            game.queue(
                c,
                action,
                "outcome",
                dict(
                    play="receive_orders",
                    callsign=action["data"]["label"],
                    receipt=None,
                    total=None,
                    tier=None,
                    original_ended=True,
                ),
            )
        _resolve_work(c, game, value, event)


def prepare_endings(previous: GameState, state: GameState, event: str) -> GameState:
    ended = []
    ended += [
        x.actor
        for x in state.career_archives
        if x.source_event == event and not any(y.id == x.id for y in previous.career_archives)
    ]
    ended += [
        x.actor
        for x in state.handler_archives
        if x.source_event == event and not any(y.id == x.id for y in previous.handler_archives)
    ]
    ended += [
        ActorRef(kind="external_pilot", entity=x.id)
        for x in state.harpy_states
        if not x.alive and x.condition_event == event
    ]
    if state.world and previous.world:
        ended += [
            ActorRef(kind="external_pilot", entity=x.id)
            for x in state.world.pilots
            if not x.alive
            and any(y.id == x.id and y.alive for y in previous.world.pilots if previous.world)
        ]
    changed = state
    for actor in ended:
        changed = end_actor(changed, actor, event)
    return changed
