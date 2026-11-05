"""Actual already-knowing NPC maintenance with one real Just Code receipt."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am as scrutiny
from girlframe.engine import m3_am_code as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    actual = Access(game.store)
    actual.authorize(c, viewer, "plays", director_response=True)
    assert actual.registry is not None
    actual.registry.require_available(rules.RULE)


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Maintenance:
    from girlframe.services.m3_am_scrutinized import (
        _history,
        _prove_effect,
    )
    from girlframe.services.m3_am_scrutinized import (
        source as discovery_source,
    )

    value = rules.session(state, identity)
    old = rules.session(_history(game, c, value.proposed_event), identity)
    stable = (
        "id",
        "actor",
        "operator",
        "owner",
        "controller",
        "discovery",
        "cast",
        "registry",
        "proposed_event",
        "proposal",
        "position",
        "vessel",
        "frame",
        "cell",
        "order_scope",
        "records_access",
    )
    if any(getattr(value, x) != getattr(old, x) for x in stable):
        raise WorkflowError("Recover the actual original maintenance participants/body source")
    known = discovery_source(game, c, state, value.discovery)
    _prove_effect(game, c, known)
    if known.actor != value.actor or known.discoverer != value.operator or not known.effect_event:
        raise WorkflowError("Use only this actual operator's already-proved adjustment knowledge")
    events = t.events
    for event, kind, human in (
        (value.proposed_event, "m3.am_code_proposed", value.owner),
        (value.confirmed_event, "m3.am_code_confirmed", value.controller),
    ):
        if event is None:
            continue
        row = c.execute(
            sa.select(events.c.kind, events.c.actor_id).where(
                events.c.campaign_id == game.store.campaign_id, events.c.id == event
            )
        ).first()
        if row is None or row.kind != kind or row.actor_id != str(human):
            raise WorkflowError("Only the original real human source answers establish contact")
    if value.confirmed_event:
        confirmed = rules.session(_history(game, c, value.confirmed_event), identity)
        if confirmed.root != value.root or confirmed.confirmation != value.confirmation:
            raise WorkflowError("Keep the original actually confirmed circuit access/source root")
    if value.order:
        if not value.order_event:
            raise WorkflowError("Recover the actual original operator's Order event")
        issued = rules.session(_history(game, c, value.order_event), identity)
        issuer = c.execute(
            sa.select(events.c.kind, events.c.actor_id).where(
                events.c.campaign_id == game.store.campaign_id, events.c.id == value.order_event
            )
        ).first()
        if (
            issued.order != value.order
            or issued.instruction != value.instruction
            or issued.spoken_words != value.spoken_words
            or issuer is None
            or issuer.kind != "m3.choice_resolved"
            or issuer.actor_id != str(value.controller)
        ):
            raise WorkflowError("Recover the actual original NPC's immutable Order")
    if value.records_access:
        from girlframe.services.m3_am_records import prove as prove_records

        record = prove_records(game, c, state, value.records_access)
        if record.maintenance != value.id or record.learner != value.operator:
            raise WorkflowError("Keep this original operator's actual record source")
    return value


def actual(game: GameService, c: Connection, state: GameState, value: rules.Maintenance) -> None:
    bound = profiles(c, game.store.campaign_id)
    actor, operator = resolve(state, value.actor, bound), resolve(state, value.operator, bound)
    sheet = state.sheets[value.actor.entity]
    physical = next((x for x in state.placements if x.actor == value.actor), None)
    cast = _cast(game, c, state, value.cast.channel)
    if (
        actor.girl != "AM"
        or value.actor.kind != "pilot"
        or value.operator.kind != "npc"
        or operator.rules != "npc"
        or operator.controller != value.controller
        or state.handler != value.controller
        or any(x.active for x in state.director_contexts)
        or game.store.policy.m3_approval is None
        or value.registry != game.store.policy.m3_approval.registry_sha256
        or cast.adjudicator is not None
        or fingerprint(cast) != fingerprint(value.cast)
        or actor.cell != value.cell
        or operator.cell != value.cell
        or actor.inside_frame is not False
        or actor.piloting
        or actor.custody
        or operator.custody
        or actor.vessel_id != value.vessel
        or actor.frame_instance != value.frame
        or actor.position_sha256 != value.position
        or physical is None
        or not physical.vitals_active
        or physical.incapacitated
        or not has_rule(sheet, rules.RULE, "AM")
        or sheet.medical_state != "fit"
    ):
        raise WorkflowError(
            "SOURCE_CONTACT_REQUIRED: use the actual unchanged free bodies/circuit access"
        )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    access(game, c, viewer)
    state = load_state(c, game.store.campaign_id)
    meta = action["data"]["am_code"]
    value = source(game, c, state, meta["maintenance"])
    actual(game, c, state, value)
    if viewer.user_id not in meta["table"] or value.action != action["id"]:
        raise WorkflowError("Only the actual original maintenance table owns this source")


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    access(game, c, viewer)
    value = source(game, c, state, prepared.source_work or "")
    actual(game, c, state, value)
    if (
        value.phase != "ready"
        or viewer.user_id != value.owner
        or channel != value.cast.channel
        or prepared.parent != value.root
        or prepared.target_actor != value.operator
        or prepared.target is not None
        or prepared.order_id
        or prepared.off_duty_id
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError("Use the actual owner-confirmed identity-maintenance source only")
    from girlframe.services.m3_am_records import ready as records_ready

    records_ready(game, c, state, value)
    return dict(
        maintenance=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.operator.model_dump(mode="json"),
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {value.controller}),
        phase="unrolled",
    )


def bind(state: GameState, action: dict[str, Any]) -> None:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    if value.phase != "ready" or value.action:
        raise WorkflowError("This real maintenance already has its original source roll")
    rules.put(state, value.model_copy(update=dict(phase="active", action=action["id"])))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    tier = action["data"]["result"]["tier"]
    if tier == "high":
        shift_status(state, value.owner, -1)
    game.request(
        c,
        action,
        value.controller,
        "am_code_order"
        if tier == "low"
        else "am_code_options"
        if value.records_access
        else "am_code_edit",
    )


def finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    if game.pending(c, action["id"]):
        return
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    if value.records_access:
        from girlframe.engine.m3_am_records import access as record_access
        from girlframe.services.m3_am_records import unselected

        if "records" in value.selected_options and action["data"]["result"]["tier"] != "low":
            if record_access(state, value.records_access).phase != "answered":
                raise WorkflowError(
                    "The actual selected Foundation question still requires its answer"
                )
        else:
            unselected(state, value, event)
        rules.put(
            state,
            value.model_copy(
                update=dict(phase="complete", effect_event=value.effect_event or event)
            ),
        )
    ChoiceEngine(game).finish(c, state, action)


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_am_scrutinized import _copy

    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    event = action["data"]["response_event"]
    if request["kind"].startswith("am_code_records_"):
        from girlframe.services.m3_am_records import apply as apply_records

        apply_records(game, c, state, action, request, answer)
        finish(game, c, state, action, event)
        return
    if (
        answer.denied
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use the actual original operator/recipient's concrete source response")
    if request["kind"] == "am_code_options":
        options = {"records"} | ({"identities"} if rules.choices(state, value.actor) else set())
        if (
            not value.records_access
            or len(answer.options) > 2
            or len(set(answer.options)) != len(answer.options)
            or not set(answer.options) <= options
            or answer.fields
            or answer.text
        ):
            raise WorkflowError("The actual operator chooses up to two available printed options")
        value = value.model_copy(update=dict(selected_options=answer.options))
        rules.put(state, value)
        if "identities" in answer.options:
            game.request(c, action, value.controller, "am_code_edit")
        if "records" in answer.options:
            from girlframe.services.m3_am_records import grant

            grant(state, value, event)
            game.request(c, action, value.controller, "am_code_records_question")
        finish(game, c, state, action, event)
        return
    if request["kind"] == "am_code_edit":
        if answer.options != ("edit",) or not answer.text.strip():
            raise WorkflowError("Choose the actual rewrite (or zero replacements) and describe it")
        _copy(state, rules.rewrite(state, value.id, answer.fields, event))
    elif request["kind"] == "am_code_order":
        if answer.options or answer.fields or not answer.text.strip() or len(answer.text) > 1180:
            raise WorkflowError("The actual operator chooses the real words to be spoken")
        command = "Say exactly: " + answer.text.strip()
        identity = str(uuid4())
        c.execute(
            t.m2["m2_orders"]
            .insert()
            .values(
                campaign_id=game.store.campaign_id,
                id=identity,
                issuer_id=value.operator.entity,
                target_id=str(value.owner),
                channel_id=str(value.cast.channel),
                state="awaiting_response",
                body_json=json.dumps(
                    dict(
                        text=command,
                        spoken_words=answer.text.strip(),
                        order_scope=value.order_scope,
                        am_code=value.id,
                        issuer=value.operator.model_dump(mode="json"),
                        target=value.actor.model_dump(mode="json"),
                        source_action=action["id"],
                        source_event=event,
                        irresistible=True,
                    )
                ),
            )
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    order=identity,
                    order_event=event,
                    instruction=command,
                    spoken_words=answer.text.strip(),
                )
            ),
        )
        action["data"]["order_id"] = identity
        game.request(c, action, value.owner, "am_code_obey")
        return
    elif request["kind"] == "am_code_obey":
        if (
            len(answer.options) != 1
            or answer.options[0] not in rules.FOLLOW
            or answer.fields
            or answer.text.strip() != value.spoken_words
        ):
            raise WorkflowError(
                "Disobey is unavailable: record your own actual matching spoken words and behavior"
            )
        order = t.m2["m2_orders"]
        row = (
            c.execute(
                sa.select(order).where(
                    order.c.campaign_id == game.store.campaign_id, order.c.id == value.order
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["state"] != "awaiting_response"
            or row["issuer_id"] != value.operator.entity
            or row["target_id"] != str(value.owner)
            or json.loads(row["body_json"]).get("source_action") != action["id"]
            or json.loads(row["body_json"]).get("source_event") != value.order_event
            or json.loads(row["body_json"]).get("text") != value.instruction
            or json.loads(row["body_json"]).get("am_code") != value.id
            or json.loads(row["body_json"]).get("spoken_words") != value.spoken_words
            or json.loads(row["body_json"]).get("order_scope") != "spoken_statement"
        ):
            raise WorkflowError("Recover the actual original irresistible NPC Order")
        c.execute(
            order.update()
            .where(order.c.campaign_id == game.store.campaign_id, order.c.id == value.order)
            .values(state="followed")
        )
        state.facts.append(
            dict(
                kind="am_code_actual_spoken_statement",
                maintenance=value.id,
                actor=value.actor.model_dump_json(),
                order=value.order or "",
                event=event,
                behavior=answer.options[0],
                account=answer.text,
            )
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(phase="complete", performance=answer.text, effect_event=event)
            ),
        )
    else:
        raise WorkflowError("Complete the exact actual circuit-maintenance source")
    finish(game, c, state, action, event)


def projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    value = rules.session(state, action["data"]["am_code"]["maintenance"])
    details: dict[str, Any] = {}
    if request["kind"].startswith("am_code_records_"):
        from girlframe.services.m3_am_records import projection as project_records

        details["records"] = project_records(game, c, state, value, request["kind"])
        details["records_id"] = value.records_access
    return dict(
        **details,
        available_options=("identities", "records")
        if rules.choices(state, value.actor)
        else ("records",),
        maintenance=value.id,
        identities=[x.model_dump(mode="json") for x in rules.choices(state, value.actor)],
        instruction=value.instruction,
        spoken_words=value.spoken_words,
        actor=state.sheets[value.actor.entity].callsign,
        behavior=rules.FOLLOW,
    )


class CodeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        discovery: str,
        expected: int,
        account: str,
        *,
        records_subject: ActorRef | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe actual identity-only circuit maintenance")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_am_scrutinized import _prove_effect
            from girlframe.services.m3_am_scrutinized import source as known_source

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            known = known_source(self.game, c, state, discovery)
            _prove_effect(self.game, c, known)
            cast = _cast(self.game, c, state, known.cast.channel)
            bound = profiles(c, self.store.campaign_id)
            actor, operator = (
                resolve(state, known.actor, bound),
                resolve(state, known.discoverer, bound),
            )
            physical = next((x for x in state.placements if x.actor == known.actor), None)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or viewer.user_id != known.caster
                or actor.girl != "AM"
                or known.discoverer.kind != "npc"
                or operator.rules != "npc"
                or operator.controller != state.handler
                or cast.adjudicator is not None
                or any(x.active for x in state.director_contexts)
                or actor.cell is None
                or actor.cell != operator.cell
                or actor.inside_frame is not False
                or actor.custody
                or operator.custody
                or not actor.position_sha256
                or not actor.vessel_id
                or not actor.frame_instance
                or physical is None
                or not physical.vitals_active
                or physical.incapacitated
                or (not rules.choices(state, known.actor) and records_subject is None)
                or not has_rule(state.sheets[known.actor.entity], rules.RULE, "AM")
            ):
                raise WorkflowError(
                    "Use the actual already-knowing NPC and co-present free AM body"
                )
            assert self.store.policy.m3_approval is not None
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Maintenance(
                id=identity,
                actor=known.actor,
                operator=known.discoverer,
                owner=viewer.user_id,
                controller=operator.controller,
                discovery=discovery,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account,
                position=actor.position_sha256,
                vessel=actor.vessel_id,
                frame=actor.frame_instance,
                cell=actor.cell,
            )
            if records_subject is not None:
                from girlframe.services.m3_am_records import request as request_records

                pointer = request_records(self.game, c, state, value, records_subject, event)
                value = value.model_copy(update=dict(records_access=pointer, selected_options=()))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_proposed",
                state,
                event_id=event,
                maintenance=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_proposed",
            dict(discovery=discovery, expected=expected, account=account)
            | (
                dict(records_subject=records_subject.model_dump(mode="json"))
                if records_subject
                else {}
            ),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        account: str,
        *,
        records_document: str | None = None,
        records_reference: str | None = None,
        records_complete: bool = False,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Confirm actual physical circuit access and identity-only maintenance"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            actual(self.game, c, state, value)
            if (
                state.revision != expected
                or value.phase != "proposed"
                or viewer.user_id != value.controller
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Only the original real operator confirms actual circuit access"
                )
            event, identity_root = str(uuid4()), str(uuid4())
            if value.records_access:
                from girlframe.services.m3_am_records import prepare as prepare_records

                prepare_records(
                    self.game,
                    c,
                    state,
                    value,
                    event,
                    records_document,
                    records_reference,
                    records_complete,
                )
            elif records_document is not None or records_reference is not None or records_complete:
                raise WorkflowError("This actual maintenance has no records request")
            scene = self.game.scene(c, value.cast.channel)
            lock = self.game.lock(c, value.cast.channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: finish the actual pending Play")
            table = sorted({x.controller for x in value.cast.roles} | {value.controller})
            data = dict(
                play="am_code_maintenance",
                am_code_source=dict(
                    maintenance=value.id, target=value.operator.model_dump(mode="json")
                ),
                participants=table,
                handler=state.handler,
                character_ids={
                    str(x.controller): x.actor.incarnation
                    for x in value.cast.roles
                    if x.actor.kind == "pilot"
                },
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
            )
            from girlframe.services.m3_recovery import enable

            enable(self.game, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity_root,
                    actor_id=str(value.owner),
                    channel_id=str(value.cast.channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            locks = t.m2["m2_locks"]
            changes = dict(
                action_id=identity_root,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            if lock:
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == str(value.cast.channel),
                    )
                    .values(**changes)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id,
                        channel_id=str(value.cast.channel),
                        **changes,
                    )
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        root=identity_root,
                        phase="ready",
                        confirmed_event=event,
                        confirmation=account,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_confirmed",
                state,
                event_id=event,
                maintenance=value.id,
            )
            return dict(id=value.id, action_id=identity_root)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_confirmed",
            dict(id=identity, expected=expected, account=account)
            | (
                dict(
                    records_document=records_document,
                    records_reference=records_reference,
                    records_complete=records_complete,
                )
                if records_document is not None or records_reference is not None or records_complete
                else {}
            ),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        from girlframe.engine.m3_alpha import current

        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                kind="am_code_source",
                label="Confirm actual identity-only circuit maintenance",
                actionable=True,
            )
            for x in rules.sessions(state)
            if x.phase == "proposed"
            and x.controller == viewer.user_id
            and current(state, x.actor)
            and current(state, x.operator)
        ]

    def source_channel(self, viewer: GuildViewer, identity: str) -> int:
        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            value = source(self.game, c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id not in (value.owner, value.controller):
                raise WorkflowError("This actual maintenance belongs to its original humans")
            return value.cast.channel

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.engine.m3_am_records import access as record_access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            known = [
                dict(id=x.id, label=resolve(state, x.discoverer, ()).label)
                for x in scrutiny.discoveries(state)
                if x.caster == viewer.user_id
                and x.cast.channel == channel
                and x.effect_event
                and x.phase in ("complete", "limited")
                and x.discoverer.kind == "npc"
                and state.world
                and any(n.id == x.discoverer.entity and n.alive for n in state.world.npcs)
            ]
            values = [
                dict(
                    id=x.id,
                    phase=x.phase,
                    owner=x.owner,
                    controller=x.controller,
                    proposal=x.proposal,
                    root=x.root,
                    records=x.records_access,
                    records_subject=(
                        record_access(state, x.records_access).label if x.records_access else None
                    ),
                )
                for x in rules.sessions(state)
                if viewer.user_id in (x.owner, x.controller) and x.cast.channel == channel
            ]
            from girlframe.engine.m3_am_records import records as saved_records
            from girlframe.services.m3_am_records import subjects

            documents = []
            for record in saved_records(state):
                if record.granted_event:
                    learner = resolve(
                        state,
                        record.learner,
                        profiles(c, self.store.campaign_id),
                        require_alive=False,
                    )
                    if learner.controller == viewer.user_id:
                        documents.append(dict(id=record.id, label=record.label))
            return dict(
                revision=state.revision,
                known=known,
                sessions=values,
                subjects=subjects(self.game, c, state),
                documents=documents,
            )
