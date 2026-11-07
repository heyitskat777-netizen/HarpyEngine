"""Actual prisoner execution, persistent group condition and real ordinary Tag resolution."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_reign_terror as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, IdentityState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_resources import save_rebel_inventory
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_frame_rewards import prisoner as prisoner_proof
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles, prove_rebel_inventory
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual Reign of Terror acquisition")
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquisition != value.id
        or award.acquired_rule != rules.RULE
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover the original actual award and Reign purchase")
    return value


def execution(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Execution:
    value = next((x for x in rules.executions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original prisoner execution")
    paid(game, c, state, value.acquisition)
    born = _history(c, game, value.event)
    actual = next((x for x in rules.executions(born) if x.id == identity), None)
    dead = (
        next((x for x in born.world.npcs if x.id == value.prisoner.entity), None)
        if born.world
        else None
    )
    original = Npc.model_validate_json(value.prisoner_json)
    if (
        actual != value
        or dead is None
        or dead.alive
        or original.id != dead.id
        or not original.alive
        or original.custody_event != value.custody_event
    ):
        raise WorkflowError("Preserve the genuine custody/person and actual NPC death event")
    return value


def member(game: GameService, c: Connection, state: GameState, identity: str) -> rules.MemberTag:
    value = next((x for x in rules.member_tags(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual enemy Girl's Underfunded Tag")
    condition = next((x for x in rules.conditions(state) if x.id == value.condition), None)
    if condition is None:
        raise WorkflowError("Recover this actual group's funding condition")
    execution(game, c, state, condition.execution)
    born = next(
        (x for x in rules.member_tags(_history(c, game, value.event)) if x.id == identity), None
    )
    if (
        born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "condition", "group", "target", "event")
        )
        or any(
            getattr(born.tag, k) != getattr(value.tag, k)
            for k in ("id", "label", "giver_actor", "observers")
        )
        or value.group != condition.group
    ):
        raise WorkflowError("Preserve the original subject, source and ordinary Tag ownership")
    return value


def target(action: dict[str, Any]) -> ActorRef | None:
    meta = action["data"].get("engage") or action["data"].get("battle")
    return ActorRef.model_validate(meta["target"]) if meta else None


def candidates(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[TagState]:
    subject = target(action)
    pilot = (
        next(
            (
                x
                for x in state.world.pilots
                if subject and subject.kind == "external_pilot" and x.id == subject.entity
            ),
            None,
        )
        if state.world
        else None
    )
    if pilot is None or pilot.kind != "rebel" or not pilot.alive:
        return []
    assert state.world is not None and subject is not None
    condition = next(
        (
            x
            for x in state.world.factions
            if x.id == pilot.faction and x.kind == "rebel" and x.active and x.underfunded
        ),
        None,
    )
    if condition is None:
        return []
    values = [
        member(game, c, state, x.id)
        for x in rules.member_tags(state)
        if x.target == subject
        and x.group == pilot.faction
        and x.phase in ("live", "reject_pending")
    ]
    if values:
        prove_rebel_inventory(game, c, state, subject)
    return [x.tag for x in values]


def propose(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    tag: TagState,
) -> bool:
    if not tag.id.startswith("reign-underfunded:"):
        return False
    value = member(game, c, state, tag.id)
    actual = resolve(state, value.target, profiles(c, game.store.campaign_id))
    if (
        tag not in candidates(game, c, state, action)
        or actual.controller == owner
        or owner not in tag.observers
        or tag.scene_used == action["scene_id"]
    ):
        raise WorkflowError(
            "Only another actual player marks this original enemy Girl's relevant Tag"
        )
    return True


def mark(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    tag_id: str,
    person: int,
    marker: Any,
    answer: ChoiceAnswer,
) -> bool:
    if not tag_id.startswith("reign-underfunded:"):
        return False
    from girlframe.engine.m3_tag_markers import modifier
    from girlframe.services.m2_choices import ChoiceEngine

    value = member(game, c, state, tag_id)
    propose(game, c, state, action, person, value.tag)
    old = value.tag.marked
    changed = value.tag.model_copy(update=dict(marked=True, scene_used=action["scene_id"]))
    rules.put(
        state,
        value.model_copy(update=dict(tag=changed, mark_event=action["data"]["response_event"])),
    )
    amount = modifier(state, value.target, marker, 1 if answer.number == 1 else -1)
    action["data"]["modifiers"].append(
        dict(source="reign_underfunded", tag=value.id, actor=person, amount=amount)
    )
    action["data"]["tag_marker_applied"] = dict(
        actor=marker.actor.model_dump(mode="json") if marker.actor else None,
        controller=person,
        tag=value.id,
        amount=amount,
        source_actor_sha256=marker.source_actor_sha256,
    )
    ChoiceEngine(game).set_total(action)
    if old:
        actor = resolve(state, value.target, profiles(c, game.store.campaign_id))
        game.request(c, action, actor.controller, "reign_group_tag_resolution", dict(tag=value.id))
    else:
        ChoiceEngine(game).results(c, state, action)
    return True


def resolution(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    value = member(game, c, state, json.loads(row["body_json"])["tag"])
    inventory = prove_rebel_inventory(game, c, state, value.target)
    actual = resolve(state, value.target, profiles(c, game.store.campaign_id))
    if (
        row["actor_id"] != str(actual.controller)
        or value.phase not in ("live", "reject_pending")
        or not value.tag.marked
        or value.tag.scene_used != action["scene_id"]
        or len(answer.options) != 1
    ):
        raise WorkflowError(
            "Only the original actual Rebel Girl controller resolves this marked Tag"
        )
    event = action["data"]["response_event"]
    if answer.options == ("embrace",):
        values = list(inventory.identities)
        replace = answer.fields.get("replace")
        if set(answer.fields) - {"replace"}:
            raise WorkflowError("Choose only the actual owned Identity slot")
        old = next((x for x in values if x.id == replace), None)
        if len(values) >= 4 and old is None:
            raise WorkflowError("Choose a real replaceable owned Identity at capacity")
        if old is not None:
            values.remove(old)
        if not ChoiceEngine(game).duplicate_labels() and any(
            x.name.casefold() == value.tag.label.casefold() for x in values
        ):
            raise WorkflowError("Duplicate Identity labels need their approved owner policy")
        slot = old.slot if old else next(x for x in range(4) if x not in {i.slot for i in values})
        identity = IdentityState(id=str(uuid4()), name=value.tag.label, slot=slot)
        values.append(identity)
        save_rebel_inventory(state, inventory.model_copy(update=dict(identities=tuple(values))))
        updated = value.model_copy(
            update=dict(phase="embraced", identity=identity.id, resolution_event=event)
        )
        for item in state.obligations:
            if (
                item.kind == "reign_reject_tag"
                and item.details.get("tag") == value.id
                and item.state == "pending"
            ):
                item.state = "fulfilled"
    elif answer.options == ("reject",):
        if answer.fields:
            raise WorkflowError("Rejection does not also rewrite an Identity")
        changed = value.tag.model_copy(update=dict(rejection_pending=True))
        updated = value.model_copy(
            update=dict(phase="reject_pending", tag=changed, resolution_event=event)
        )
        if not any(
            x.kind == "reign_reject_tag"
            and x.details.get("tag") == value.id
            and x.state == "pending"
            for x in state.obligations
        ):
            game.obligation(
                state,
                action,
                "reign_reject_tag",
                actual.controller,
                tag=value.id,
                actor=value.target.model_dump_json(),
            )
    else:
        raise WorkflowError("Embrace into an actual Identity or take real action to reject")
    rules.put(state, updated)
    ChoiceEngine(game).results(c, state, action)


def project_resolution(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> dict[str, Any]:
    value = member(game, c, state, json.loads(row["body_json"])["tag"])
    inventory = prove_rebel_inventory(game, c, state, value.target)
    return dict(
        tag=value.tag.model_dump(mode="json"),
        actor=value.target.model_dump(mode="json"),
        identities=[x.model_dump(mode="json") for x in inventory.identities],
    )


def complete_rejection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    """Worker owns normal lock; this exact actual external-role action erases its owed Tag."""
    meta = action["data"]["reign_rejection"]
    value = member(game, c, state, meta["tag"])
    inventory = prove_rebel_inventory(game, c, state, value.target)
    birth = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.reign_rejection_started",
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
        )
    ).first()
    if (
        birth is None
        or birth.actor_id != str(inventory.controller)
        or json.loads(birth.payload_json).get("actor_ref") != value.target.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the actual original controller-owned rejection action source")
    obligation = next((x for x in state.obligations if x.id == meta["obligation"]), None)
    if (
        action["state"] != "acquiring"
        or obligation is None
        or obligation.state != "pending"
        or obligation.kind != "reign_reject_tag"
        or obligation.details.get("actor") != value.target.model_dump_json()
        or inventory.controller != int(action["actor_id"])
        or value.phase != "reject_pending"
        or not action["data"]["context"].strip()
    ):
        raise WorkflowError("Perform only this actual original enemy Girl's owed rejection action")
    rules.put(state, value.model_copy(update=dict(phase="rejected", resolution_event=event)))
    obligation.state = "fulfilled"
    action["state"] = "complete"
    action["data"]["result"] = dict(
        rejected_tag=value.id, actor=value.target.model_dump(mode="json")
    )
    actual = resolve(state, value.target, profiles(c, game.store.campaign_id))
    game.queue(
        c,
        action,
        "outcome",
        dict(
            play="reign_reject_tag",
            callsign=actual.label,
            receipt=None,
            total=None,
            tier=None,
            actor=value.target.model_dump(mode="json"),
            rejected_tag=value.id,
        ),
    )


class ReignTerrorService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        return self.store._write(
            viewer,
            key,
            kind,
            body,
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError("Spend one genuine held award on unowned Reign of Terror")
            event = str(uuid4())
            value = rules.Acquisition(
                id="reign:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            awards.put(
                state,
                awards.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=value.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
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
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.reign_buy",
            dict(award=award_id, revision=revision, account=account),
            operation,
        )

    def execute(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        prisoner: str,
        choice: Literal["rebellion_low", "underfunded", "girl_tag"],
        account: str,
        *,
        actual: bool,
        target: ActorRef | None = None,
        label: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            receipt = paid(self.game, c, state, identity)
            if (
                state.revision != revision
                or viewer.user_id != int(receipt.handler.entity)
                or not same_handler_body(state, receipt.handler)
                or HandlerCreationService(self.store)._appointment_source(c, viewer.user_id)
                != receipt.appointment
                or self.game.pending_actions(c)
                or not actual
                or not account.strip()
                or state.world is None
            ):
                raise WorkflowError(
                    "Only the original current Handler performs this actual execution"
                )
            custody = prisoner_proof(
                state.world,
                "npc:" + prisoner,
                viewer.user_id,
                viewer.user_id,
                rebel=choice == "underfunded",
                cadre=frozenset(state.order),
            )
            npc = next(x for x in state.world.npcs if x.id == prisoner)
            prior = _history(c, self.game, custody)
            old = (
                next((x for x in prior.world.npcs if x.id == npc.id), None) if prior.world else None
            )
            audit = c.execute(
                sa.select(t.events.c.kind, t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == custody
                )
            ).first()
            if (
                old is None
                or old.custody_event != custody
                or not old.alive
                or "prisoner" not in old.jobs
                or old.controller != npc.controller
                or audit is None
                or audit.kind != "m3.npc_introduced"
                or json.loads(audit.payload_json).get("entity_id") != npc.id
            ):
                raise WorkflowError(
                    "Prove actual Foundation prisoner custody from its server event, not a label"
                )
            actor = resolve(
                state,
                receipt.handler,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                actor.offstage_source
                or actor.custody not in (None, "free")
                or actor.cell is not None
                and actor.cell != npc.cell
            ):
                raise WorkflowError(
                    "Actual execution requires the original Handler's real available co-presence"
                )
            event, identity2 = str(uuid4()), "reign-execution:" + str(uuid4())
            if actor.cell is None:
                state.facts.append(
                    dict(
                        kind="reign_terror_actual_position",
                        actor=receipt.handler.model_dump_json(),
                        cell=json.dumps(npc.cell),
                        event=event,
                        execution=identity2,
                        account=account.strip(),
                    )
                )
            group = condition_id = tag_id = None
            rebellion_before = None
            if choice == "rebellion_low":
                if state.strain is None:
                    raise WorkflowError("Configure actual Strain before this reduction")
                rebellion_before = state.strain.levels["rebellion"]
                state.strain = state.strain.model_copy(
                    update=dict(levels=state.strain.levels | {"rebellion": "low"})
                )
            elif choice == "underfunded":
                faction = next(
                    (
                        x
                        for x in state.world.factions
                        if x.id == npc.faction and x.kind == "rebel" and x.active
                    ),
                    None,
                )
                if faction is None or old.faction != npc.faction:
                    raise WorkflowError("Prove the prisoner's actual original public Rebel Group")
                group = faction.id
                existing = (
                    next((x for x in reversed(rules.conditions(state)) if x.group == group), None)
                    if faction.underfunded
                    else None
                )
                if existing:
                    condition_id = existing.id
                else:
                    condition = rules.Condition(
                        id="reign-condition:" + event, execution=identity2, group=group, event=event
                    )
                    condition_id = condition.id
                    rules.put(state, condition)
                    for enemy in state.world.pilots:
                        if enemy.kind == "rebel" and enemy.faction == group and enemy.alive:
                            ref = ActorRef(kind="external_pilot", entity=enemy.id)
                            tag_id2 = "reign-underfunded:" + condition.id + ":" + enemy.id
                            rules.put(
                                state,
                                rules.MemberTag(
                                    id=tag_id2,
                                    condition=condition.id,
                                    group=group,
                                    target=ref,
                                    event=event,
                                    tag=TagState(
                                        id=tag_id2,
                                        label="Underfunded",
                                        giver=viewer.user_id,
                                        giver_actor=receipt.handler,
                                        observers=tuple(
                                            sorted(
                                                set(state.order)
                                                | {viewer.user_id, enemy.controller}
                                            )
                                        ),
                                    ),
                                ),
                            )
                state.world = state.world.model_copy(
                    update=dict(
                        factions=tuple(
                            x.model_copy(update=dict(underfunded=True)) if x.id == group else x
                            for x in state.world.factions
                        )
                    )
                )
            elif choice == "girl_tag":
                if (
                    target is None
                    or target.kind != "pilot"
                    or target != current_ref(state, int(target.entity))
                    or not label.strip()
                ):
                    raise WorkflowError(
                        "Choose your actual current native Girl and human-authored Tag"
                    )
                tag_id = "reign-girl-tag:" + event
                state.sheets[target.entity].tags.append(
                    TagState(
                        id=tag_id,
                        label=label.strip(),
                        giver=viewer.user_id,
                        giver_actor=receipt.handler,
                        observers=tuple(sorted(set(state.order) | {viewer.user_id})),
                    )
                )
                state.sheets[target.entity].revision += 1
            else:
                raise WorkflowError("Choose one printed execution effect")
            value = rules.Execution(
                id=identity2,
                acquisition=receipt.id,
                handler=receipt.handler,
                prisoner=ActorRef(kind="npc", entity=npc.id),
                custody_event=custody,
                prisoner_json=npc.model_dump_json(),
                event=event,
                account=account.strip(),
                choice=choice,
                group=group,
                condition=condition_id,
                target=target if choice == "girl_tag" else None,
                tag=tag_id,
                rebellion_before=rebellion_before,
            )
            rules.put(state, value)
            state = end_actor_casts(state, value.prisoner, event)
            assert state.world is not None
            state.world = state.world.model_copy(
                update=dict(
                    npcs=tuple(
                        x.model_copy(update=dict(alive=False)) if x.id == npc.id else x
                        for x in state.world.npcs
                    )
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.reign_prisoner_executed",
                state,
                event_id=event,
                execution=value.id,
                prisoner=npc.id,
            )
            return dict(id=value.id, choice=choice)

        return self._write(
            viewer,
            key,
            "m3.reign_execute",
            dict(
                id=identity,
                revision=revision,
                prisoner=prisoner,
                choice=choice,
                account=account,
                actual=actual,
                target=target.model_dump(mode="json") if target else None,
                label=label,
            ),
            operation,
        )

    def reject(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        account: str,
        *,
        actual: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = member(self.game, c, state, identity)
            inventory = prove_rebel_inventory(self.game, c, state, value.target)
            scene = self.game.scene(c, channel)
            cast = _cast(self.game, c, state, channel)
            item = next(
                (
                    x
                    for x in state.obligations
                    if x.kind == "reign_reject_tag"
                    and x.details.get("tag") == value.id
                    and x.state == "pending"
                ),
                None,
            )
            lock = self.game.lock(c, channel)
            if (
                state.revision != revision
                or inventory.controller != viewer.user_id
                or item is None
                or not actual
                or not account.strip()
                or value.phase != "reject_pending"
                or self.game.pending_actions(c)
                or lock
                and lock["state"] != "released"
                or not any(
                    x.actor == value.target and x.controller == viewer.user_id for x in cast.roles
                )
            ):
                raise WorkflowError(
                    "Perform your actual original Rebel Girl's owed rejection in its real scene"
                )
            identity2 = str(uuid4())
            data = dict(
                play="reign_reject_tag",
                character_ids={
                    str(uid): self.game.character_binding(
                        c, state, uid, require_current_profile=False
                    )
                    for uid in scene["participants"]
                    if str(uid) in state.sheets
                },
                context=account.strip(),
                participants=scene["participants"],
                handler=state.handler,
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                reign_rejection=dict(
                    tag=value.id, obligation=item.id, actor=value.target.model_dump(mode="json")
                ),
            )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity2,
                    scene_id=scene["id"],
                    channel_id=str(channel),
                    actor_id=str(viewer.user_id),
                    state="acquiring",
                    revision=1,
                    parent_id=None,
                    body_json=json.dumps(data),
                )
            )
            locks = t.m2["m2_locks"]
            values = dict(
                action_id=identity2,
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
                        locks.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.reign_rejection_started",
                action_id=identity2,
                actor_ref=value.target.model_dump(mode="json"),
                tag=value.id,
            )
            return dict(action_id=identity2)

        return self._write(
            viewer,
            key,
            "m3.reign_reject",
            dict(id=identity, revision=revision, channel=channel, account=account, actual=actual),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            owned = (
                [
                    x
                    for x in state.world.pilots
                    if x.kind == "rebel" and x.controller == viewer.user_id
                ]
                if state.world
                else []
            )
            if identity and identity.startswith("reign-inventory:"):
                ref = ActorRef(
                    kind="external_pilot", entity=identity.removeprefix("reign-inventory:")
                )
                actor = ActorService(MissionService(self.store))._actor(
                    c, viewer, state, ref, require_current_profile=False
                )
                return dict(
                    kind="inventory",
                    revision=state.revision,
                    actor=ref.model_dump(mode="json"),
                    label=actor.label,
                    known=next(
                        x.rebel_resources_json is not None for x in owned if x.id == ref.entity
                    ),
                )
            tag = next(
                (
                    member(self.game, c, state, x.id)
                    for x in rules.member_tags(state)
                    if x.id == identity
                ),
                None,
            )
            if tag:
                actual = resolve(state, tag.target, profiles(c, self.store.campaign_id))
                if actual.controller != viewer.user_id:
                    raise WorkflowError(
                        "Only this actual enemy Girl's controller owns its deferred Tag action"
                    )
                return dict(
                    kind="tag",
                    revision=state.revision,
                    body=tag.model_dump(mode="json"),
                    channels=[
                        int(x)
                        for x in c.scalars(
                            sa.select(t.m2["m2_scenes"].c.channel_id).where(
                                t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                                t.m2["m2_scenes"].c.open.is_(True),
                            )
                        )
                    ],
                )
            record = next(
                (
                    execution(self.game, c, state, x.id)
                    for x in rules.executions(state)
                    if x.id == identity
                ),
                None,
            )
            if record:
                if record.handler.entity != str(viewer.user_id) and (
                    record.target is None or record.target.entity != str(viewer.user_id)
                ):
                    raise WorkflowError(
                        "This private execution record belongs to its original source people"
                    )
                return dict(
                    kind="execution", revision=state.revision, body=record.model_dump(mode="json")
                )
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
            ]
            if identity and identity not in {x.id for x in receipts}:
                raise WorkflowError("This acquired advancement belongs to its original Handler")
            return dict(
                kind="acquisition",
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in awards.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
                prisoners=[
                    dict(id=x.id, label=x.name)
                    for x in state.world.npcs
                    if x.alive and x.custody_event and "prisoner" in x.jobs
                ]
                if state.world
                else [],
                girls=[
                    dict(
                        ref=current_ref(state, uid).model_dump(mode="json"),
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                ],
                inventories=[
                    dict(id="reign-inventory:" + x.id, label=x.name)
                    for x in owned
                    if x.rebel_resources_json is None
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Reign of Terror",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        result.extend(
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual prisoner execution",
                phase=x.choice,
                pending=False,
            )
            for x in rules.executions(state)
            if x.handler.entity == str(viewer.user_id)
            or x.target is not None
            and x.target.entity == str(viewer.user_id)
        )
        if state.world:
            result.extend(
                dict(
                    id="reign-inventory:" + x.id,
                    revision=state.revision,
                    label="Actual Rebel Girl inventory",
                    phase="inventory",
                    pending=False,
                )
                for x in state.world.pilots
                if x.kind == "rebel"
                and x.controller == viewer.user_id
                and x.rebel_resources_json is None
            )
        result.extend(
            dict(
                id=x.id,
                revision=state.revision,
                label="Rebel Girl owed Tag rejection",
                phase=x.phase,
                pending=True,
            )
            for x in rules.member_tags(state)
            if x.phase == "reject_pending"
            and resolve(state, x.target, profiles(c, self.store.campaign_id)).controller
            == viewer.user_id
        )
        return result
