"""Actual human comparison sources; saved DNA is private, never a guessed new actor."""

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_dna as rules
from girlframe.engine.m2 import GameState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _text(value: str, maximum: int = 1200) -> str:
    if not value.strip() or len(value) > maximum:
        raise WorkflowError("Provide the actual source account within its saved limit")
    return value


def _event(game: GameService, c: Connection, identity: str) -> Any:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == identity
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the original factual source event")
    return row


def _same_original(game: GameService, c: Connection, sheet: PilotSheet, actor: ActorRef) -> bool:
    if sheet.character_id is not None:
        return sheet.character_id == actor.incarnation
    # A legacy activation may predate cached CIDs. Its exact immutable profile snapshot
    # can prove the original person; today's account/profile is never substituted.
    snapshot = c.scalar(
        sa.select(t.snapshots.c.character_id).where(
            t.snapshots.c.campaign_id == game.store.campaign_id,
            t.snapshots.c.user_id == actor.entity,
            t.snapshots.c.revision == sheet.source_profile_revision,
        )
    )
    return snapshot is not None and snapshot == actor.incarnation


def basis(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> rules.BasisProof:
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actor.kind != "pilot" or actual.girl != rules.BOOK:
        raise WorkflowError("Use the actual original native Vatgrown baseline")
    sheet = state.sheets[actor.entity]
    runtime = sheet.girl_runtime
    setup = runtime.setup if runtime else None
    if setup is not None and (runtime is None or not runtime.baseline_event):
        raise WorkflowError("SOURCE_BASELINE_SETUP_REQUIRED: recover the actual baseline epoch")
    if runtime and runtime.baseline_event:
        if setup is None or setup.book != rules.BOOK or setup.epoch != runtime.baseline_event:
            raise WorkflowError(
                "SOURCE_BASELINE_SETUP_REQUIRED: finish the actual current Girl setup"
            )
        source = _event(game, c, setup.source_event)
        saved = _history(c, game, setup.source_event).sheets.get(actor.entity)
        if (
            source["kind"] != "m3.girl_transition_completed"
            or source["actor_id"] != actor.entity
            or saved is None
            or not _same_original(game, c, saved, actor)
            or saved.girl != rules.BOOK
            or saved.girl_runtime is None
            or saved.girl_runtime.setup != setup
        ):
            raise WorkflowError("Recover the immutable current native DNA setup")
        text, event, epoch = setup.dna_basis, setup.source_event, setup.epoch
    else:
        table = t.events
        rows = c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.kind == "m2.character_activated",
                table.c.actor_id == actor.entity,
            )
            .order_by(table.c.seq)
        ).mappings()
        original = None
        for row in rows:
            saved = _history(c, game, row["id"]).sheets.get(actor.entity)
            if saved and _same_original(game, c, saved, actor) and saved.girl == rules.BOOK:
                original = (saved, row["id"])
                break
        if original is None:
            raise WorkflowError("Recover the original native Vatgrown creation source")
        saved, event = original
        text, epoch = saved.review.creation.dna_basis, event
    if not text.strip():
        raise WorkflowError("SOURCE_DNA_BASIS_REQUIRED: recover the actual saved native basis")
    return rules.BasisProof(
        actor=actor,
        source=event,
        epoch=epoch,
        text=text,
        digest=hashlib.sha256(text.encode()).hexdigest(),
    )


def _prove_basis(game: GameService, c: Connection, value: rules.BasisProof) -> None:
    # Historical source proof deliberately does not require today's profile/controller/book.
    row = _event(game, c, value.source)
    saved = _history(c, game, value.source).sheets.get(value.actor.entity)
    if saved is None or not _same_original(game, c, saved, value.actor) or saved.girl != rules.BOOK:
        raise WorkflowError("Preserve the original Vatgrown person and native source")
    if row["kind"] == "m2.character_activated":
        text, epoch = saved.review.creation.dna_basis, row["id"]
    elif (
        row["kind"] == "m3.girl_transition_completed"
        and saved.girl_runtime
        and saved.girl_runtime.setup
    ):
        setup = saved.girl_runtime.setup
        if (
            setup.book != rules.BOOK
            or setup.source_event != value.source
            or saved.girl_runtime.baseline_event != setup.epoch
        ):
            raise WorkflowError("Preserve the real completed Vatgrown baseline")
        text, epoch = setup.dna_basis, setup.epoch
    else:
        raise WorkflowError("Use a genuine native creation or completed baseline source")
    if (
        row["actor_id"] != value.actor.entity
        or value.text != text
        or value.epoch != epoch
        or value.digest != hashlib.sha256(text.encode()).hexdigest()
    ):
        raise WorkflowError("Preserve the exact private original DNA source")


def _role(scene: SceneCast, actor: ActorRef, controller: int) -> None:
    if not any(value.actor == actor and value.controller == controller for value in scene.roles):
        raise WorkflowError("Use the actual controlled role in this comparison scene")


def prove_disclosure(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Disclosure:
    value = rules.get(state, rules.Disclosure, identity)
    row = _event(game, c, value.event)
    born = _history(c, game, value.event)
    if (
        row["kind"] != "m3.vatgrown_dna_disclosed"
        or row["actor_id"] != str(value.controller)
        or json.loads(row["payload_json"]).get("id") != value.id
        or rules.get(born, rules.Disclosure, identity) != value
        or value.controller != int(value.basis.actor.entity)
        or not value.account.strip()
    ):
        raise WorkflowError("Recover the actual owner's addressed DNA disclosure")
    _prove_basis(game, c, value.basis)
    _role(value.cast, value.basis.actor, value.controller)
    _role(value.cast, value.recipient, value.recipient_controller)
    return value


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Comparison:
    value = rules.get(state, rules.Comparison, identity)
    row = _event(game, c, value.event)
    born = rules.get(_history(c, game, value.event), rules.Comparison, identity)
    if (
        row["kind"] != "m3.vatgrown_dna_compared"
        or row["actor_id"] != str(value.controller)
        or json.loads(row["payload_json"]).get("id") != identity
        or identity != rules.identity(game.store.campaign_id, value.basis.actor.token)
        or value.owner_controller != int(value.basis.actor.entity)
        or not value.account.strip()
        or born.outcome != "pending"
    ):
        raise WorkflowError("Recover the actual first campaign comparison")
    immutable = (
        "id",
        "basis",
        "comparer",
        "controller",
        "owner_controller",
        "cast",
        "account",
        "event",
    )
    if any(getattr(born, name) != getattr(value, name) for name in immutable):
        raise WorkflowError("Preserve the original comparison and actual comparer")
    _prove_basis(game, c, value.basis)
    _role(value.cast, value.basis.actor, value.owner_controller)
    _role(value.cast, value.comparer, value.controller)
    if value.outcome != "pending":
        completion = _event(game, c, value.completed_event or "")
        saved = _history(c, game, value.completed_event or "")
        if (
            completion["kind"] != "m3.vatgrown_dna_resolved"
            or completion["actor_id"] != str(value.controller)
            or json.loads(completion["payload_json"]).get("id") != identity
            or rules.get(saved, rules.Comparison, identity) != value
        ):
            raise WorkflowError("Recover the actual comparer-authored optional Tag decision")
        if value.outcome == "given":
            tag = next(
                (tag for tag in actor_tags(saved, value.basis.actor) if tag.id == value.tag), None
            )
            if (
                not isinstance(tag, TagState)
                or tag.label != value.label
                or tag.giver_actor != value.comparer
                or tag.giver != value.controller
            ):
                raise WorkflowError("Preserve the actual source Tag and original giver")
    return value


class VatgrownDNAService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "plays", director_response=True)
        if gate.registry is None:
            raise WorkflowError("Recover the actual reviewed DNA comparison rule")
        gate.registry.require_available(rules.RULE)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], str],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_recovery import pending

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("Reopen the current actual DNA source before changing it")
            if self.game.pending_actions(c) or pending(self.game, c, include_unrolled=True):
                raise WorkflowError("Finish held source work before changing the actual DNA source")
            event = str(uuid4())
            identity = operation(c, state, event)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, id=identity)
            return dict(id=identity, revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(revision=revision, **request),
                run,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        vatgrown: ActorRef,
        recipient: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        account = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> str:
            source = basis(self.game, c, state, vatgrown)
            actual = resolve(
                state, vatgrown, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            other = resolve(
                state, recipient, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError(
                    "Only the actual original owner discloses this saved private basis"
                )
            scene = _cast(self.game, c, state, channel)
            _role(scene, vatgrown, viewer.user_id)
            _role(scene, recipient, other.controller)
            value = rules.Disclosure(
                id=str(uuid4()),
                basis=source,
                recipient=recipient,
                controller=viewer.user_id,
                recipient_controller=other.controller,
                cast=scene,
                account=account,
                event=event,
            )
            rules.put(state, value)
            return value.id

        return self._write(
            viewer,
            key,
            revision,
            "m3.vatgrown_dna_disclosed",
            dict(
                channel=channel,
                vatgrown=vatgrown.model_dump(mode="json"),
                recipient=recipient.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def compare(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        vatgrown: ActorRef,
        comparer: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        account = _text(account)

        def operation(c: Connection, state: GameState, event: str) -> str:
            source = basis(self.game, c, state, vatgrown)
            actual = resolve(
                state, comparer, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            owner = resolve(
                state, vatgrown, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError("The actual comparer authors their own performed comparison")
            scene = _cast(self.game, c, state, channel)
            _role(scene, comparer, viewer.user_id)
            _role(scene, vatgrown, owner.controller)
            return rules.compare(
                state,
                self.store.campaign_id,
                source,
                comparer,
                viewer.user_id,
                owner.controller,
                scene,
                account,
                event,
            ).id

        return self._write(
            viewer,
            key,
            revision,
            "m3.vatgrown_dna_compared",
            dict(
                channel=channel,
                vatgrown=vatgrown.model_dump(mode="json"),
                comparer=comparer.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def resolve(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        comparison: str,
        tag: str | None,
        account: str,
    ) -> dict[str, Any]:
        account = _text(account)
        if tag is not None:
            tag = _text(tag, 120)

        def operation(c: Connection, state: GameState, event: str) -> str:
            value = prove(self.game, c, state, comparison)
            actual = resolve(
                state,
                value.comparer,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if value.controller != viewer.user_id or actual.controller != viewer.user_id:
                raise WorkflowError("Only the actual original comparer chooses Tag or decline")
            if value.outcome != "pending":
                raise WorkflowError("The actual first comparison was already settled")
            tag_id = rules.identity("tag", value.id) if tag is not None else None
            if tag is not None:
                changed = give_tag(
                    state,
                    profiles(c, self.store.campaign_id),
                    value.basis.actor,
                    value.comparer,
                    tag,
                    tag_id or "",
                    event,
                    tuple(sorted({value.controller, value.owner_controller})),
                )
                for field in GameState.model_fields:
                    setattr(state, field, getattr(changed, field))
            rules.complete(state, value, event, account, tag=tag_id, label=tag)
            return value.id

        return self._write(
            viewer,
            key,
            revision,
            "m3.vatgrown_dna_resolved",
            dict(comparison=comparison, tag=tag, account=account),
            operation,
        )

    def _shared(
        self,
        c: Connection,
        state: GameState,
        source: rules.BasisProof,
        viewer: GuildViewer,
        comparer: ActorRef,
    ) -> bool:
        if viewer.user_id == int(source.actor.entity):
            return True
        for value in rules.records(state, rules.Disclosure):
            if (
                value.basis == source
                and value.recipient_controller == viewer.user_id
                and value.recipient == comparer
            ):
                prove_disclosure(self.game, c, state, value.id)
                return True
        return False

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, rules.Comparison):
            if viewer.user_id in (value.controller, value.owner_controller):
                result.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        label="First actual DNA comparison",
                        phase="pending" if value.outcome == "pending" else "resolved",
                        pending=value.outcome == "pending" and viewer.user_id == value.controller,
                    )
                )
        result.extend(
            dict(
                id=value.id,
                revision=state.revision,
                label="Addressed DNA disclosure",
                phase="resolved",
                pending=False,
            )
            for value in rules.records(state, rules.Disclosure)
            if viewer.user_id in (value.controller, value.recipient_controller)
        )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            disclosed = next(
                (value for value in rules.records(state, rules.Disclosure) if value.id == identity),
                None,
            )
            if disclosed is not None:
                if viewer.user_id not in (disclosed.controller, disclosed.recipient_controller):
                    raise WorkflowError(
                        "Only the actual addressed source participants read this disclosure"
                    )
                value = prove_disclosure(self.game, c, state, identity)
                return dict(
                    id=identity,
                    revision=state.revision,
                    kind="disclosure",
                    account=value.account,
                    vatgrown=value.basis.actor.model_dump(mode="json"),
                    recipient=value.recipient.model_dump(mode="json"),
                    basis=value.basis.text,
                    source=value.basis.source,
                    event=value.event,
                )
            compared = prove(self.game, c, state, identity)
            if viewer.user_id not in (compared.controller, compared.owner_controller):
                raise WorkflowError("Only the actual comparison participants read this source")
            result = dict(
                id=identity,
                revision=state.revision,
                kind="comparison",
                vatgrown=compared.basis.actor.model_dump(mode="json"),
                comparer=compared.comparer.model_dump(mode="json"),
                account=compared.account,
                outcome=compared.outcome,
                tag=compared.tag,
                label=compared.label,
                resolution_account=compared.resolution_account,
                event=compared.event,
                can_resolve=compared.outcome == "pending" and viewer.user_id == compared.controller,
            )
            if self._shared(c, state, compared.basis, viewer, compared.comparer):
                result["basis"] = compared.basis.text
            return result

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            result: dict[str, Any] = dict(
                revision=state.revision,
                roles=[],
                targets=[],
                recipients=[],
                own_basis=[],
                tasks=self._tasks(c, viewer),
                gaps=[],
            )
            # Owner private setup remains readable independently of an active source scene.
            for sheet in state.sheets.values():
                if sheet.owner != viewer.user_id or sheet.girl != rules.BOOK:
                    continue
                try:
                    from girlframe.services.m3_incarnations import proof as original_person

                    character = (
                        sheet.character_id
                        or original_person(
                            c,
                            self.store.campaign_id,
                            state,
                            sheet.owner,
                            require_current_profile=False,
                        ).character
                    )
                    actor = ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=character)
                    source = basis(self.game, c, state, actor)
                except (ValueError, WorkflowError) as error:
                    result["gaps"].append(str(error))
                    continue
                result["own_basis"].append(
                    dict(
                        actor=actor.model_dump(mode="json"), basis=source.text, source=source.source
                    )
                )
            try:
                self._access(c, viewer)
                scene = _cast(self.game, c, state, channel or 0)
            except (ValueError, WorkflowError):
                return result
            for role in scene.roles:
                try:
                    actual = resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                except ValueError:
                    continue
                # An unrevealed NPC does not become public merely by being in this cast.
                if (
                    role.actor.kind == "npc"
                    and state.world
                    and any(
                        npc.id == role.actor.entity and not npc.revealed for npc in state.world.npcs
                    )
                    and viewer.user_id not in (actual.controller, state.handler)
                ):
                    continue
                row = dict(
                    actor=role.actor.model_dump(mode="json"),
                    label=actual.label,
                    id=role.actor.token,
                )
                result["recipients"].append(row)
                if actual.controller == viewer.user_id:
                    result["roles"].append(row)
                if role.actor.kind == "pilot" and actual.girl == rules.BOOK:
                    if any(
                        value.basis.actor == role.actor
                        for value in rules.records(state, rules.Comparison)
                    ):
                        continue
                    try:
                        basis(self.game, c, state, role.actor)
                    except (ValueError, WorkflowError):
                        continue
                    result["targets"].append(row)  # No saved basis text, hash or inferred donor.
            return result
