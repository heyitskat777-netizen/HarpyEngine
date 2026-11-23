"""The Mercenary's actual original NPC sponsor, loss, and replacement agreement."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.mercenary.patron"
KIND = "mercenary_patron"


class Sponsorship(Model):
    mercenary: ActorRef
    owner: int
    patron: ActorRef
    source: str
    loss: str | None = None
    old: ActorRef | None = None
    proposal: str | None = None
    prospect: ActorRef | None = None
    prospect_owner: int | None = None
    channel: int | None = None
    scene: str | None = None
    invitation: str | None = None


def records(state: GameState) -> tuple[Sponsorship, ...]:
    return tuple(
        Sponsorship.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def sponsorship(state: GameState, actor: ActorRef) -> Sponsorship | None:
    saved = next((x for x in records(state) if x.mercenary == actor), None)
    if saved is not None:
        return saved
    role = ancillary.find(state, actor)
    if (
        role is None
        or not isinstance(role.draft, ancillary.Draft)
        or role.draft.book != "MERCENARY"
        or role.draft.patron is None
    ):
        return None
    return Sponsorship(
        mercenary=actor, owner=role.controller, patron=role.draft.patron, source=role.event
    )


class MercenaryPatronService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        gate = Access(self.store)
        gate.require_specialist_rule(RULE)
        assert gate.registry is not None
        gate.registry.require_available(ancillary.STARTERS["MERCENARY"].rule)

    def _source(self, state: GameState, actor: ActorRef) -> tuple[Sponsorship, ActorView]:
        actual = resolve(state, actor, (), require_current_profile=False)
        value = sponsorship(state, actor)
        if (
            actual.rules != "ancillary"
            or actual.girl != "MERCENARY"
            or value is None
            or actual.controller != value.owner
            or actual.offstage_source
            or actual.cell is None
        ):
            raise WorkflowError("Recover the original actual Mercenary and patronage")
        return value, actual

    def _patron(self, state: GameState, ref: ActorRef) -> Npc:
        npc = (
            next((x for x in state.world.npcs if x.id == ref.entity), None) if state.world else None
        )
        if ref.kind != "npc" or npc is None or "patron" not in npc.jobs:
            raise WorkflowError("Use the actual original Patron NPC")
        return npc

    def _scene(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actual: ActorView,
    ) -> SceneCast:
        cast = _cast(self.game, c, state, channel)
        if not any(x.actor == actual.ref and x.controller == actual.controller for x in cast.roles):
            raise WorkflowError("Join the original scene as the actual Mercenary")
        return cast

    def _prospects(
        self,
        state: GameState,
        cast: SceneCast,
        actual: ActorView,
    ) -> dict[str, Npc]:
        people = {}
        for member in cast.roles:
            if member.actor.kind != "npc" or member.controller == actual.controller:
                continue
            try:
                npc = self._patron(state, member.actor)
                view = resolve(state, member.actor, (), require_current_profile=False)
            except (ValueError, WorkflowError):
                continue
            if (
                npc.alive
                and npc.revealed
                and npc.controller == member.controller
                and not view.offstage_source
                and view.cell == actual.cell
            ):
                people[member.actor.token] = npc
        return people

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        value: Sponsorship,
        event: str,
        kind: str,
    ) -> dict[str, Any]:
        identity = value.mercenary.token
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, identity)]
        state.facts.append(dict(kind=KIND, id=identity, body=value.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.mercenary_patron_" + kind,
            state,
            event_id=event,
        )
        return dict(id=identity, event=event, funding=value.loss is None)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.mercenary_patron",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def menu(
        self,
        viewer: GuildViewer,
        channel: int,
        actor: ActorRef,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, actual = self._source(state, actor)
            cast = self._scene(c, state, channel, actual)
            if actual.controller != viewer.user_id:
                raise WorkflowError("Patronage belongs to the original actual Mercenary")
            npc = self._patron(state, value.patron)
            return dict(
                revision=state.revision,
                patron=npc.name,
                funded=value.loss is None,
                pending=value.proposal is not None,
                prospects={key: x.name for key, x in self._prospects(state, cast, actual).items()}
                if value.loss and not value.proposal
                else {},
            )

    def withdrawal(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        npc_ref: ActorRef,
    ) -> dict[str, str]:
        body = self._patron(state, npc_ref)
        if not body.alive or body.controller != viewer.user_id:
            raise WorkflowError("Only the living original Patron controller may withdraw patronage")
        people = {}
        for original in ancillary.records(state):
            value = sponsorship(state, original.actor)
            if value is None or value.patron != npc_ref or value.loss is not None:
                continue
            try:
                _, actual = self._source(state, value.mercenary)
                cast = self._scene(c, state, channel, actual)
                patron_view = resolve(state, npc_ref, (), require_current_profile=False)
            except (ValueError, WorkflowError):
                continue
            if (
                actual.cell == patron_view.cell
                and not patron_view.offstage_source
                and any(x.actor == npc_ref and x.controller == viewer.user_id for x in cast.roles)
            ):
                people[value.mercenary.token] = actual.label
        return people

    def withdrawal_menu(
        self,
        viewer: GuildViewer,
        channel: int,
        npc: ActorRef,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(
                revision=state.revision,
                people=self.withdrawal(c, state, viewer, channel, npc),
            )

    def withdraw(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        patron: ActorRef,
        revision: int,
        subject: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            people = self.withdrawal(c, state, viewer, channel, patron)
            if (
                state.revision != revision
                or subject not in people
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Confirm the actual sponsorship and its ending")
            actor = next(x.actor for x in ancillary.records(state) if x.actor.token == subject)
            value, _ = self._source(state, actor)
            return self._lose(c, state, viewer, key, value, account.strip(), "withdrawn")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                patron=patron.model_dump(mode="json"),
                revision=revision,
                subject=subject,
                account=account,
            ),
            operation,
        )

    def _lose(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        value: Sponsorship,
        reason: str,
        kind: str,
    ) -> dict[str, Any]:
        event = str(uuid4())
        state.facts.append(
            dict(
                kind="mercenary_funding_loss",
                id=value.mercenary.token,
                patron=value.patron.model_dump_json(),
                event=event,
                account=reason,
            ),
        )
        return self._save(
            c, state, viewer, key, value.model_copy(update=dict(loss=event)), event, kind
        )

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        patron: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            value, actual = self._source(state, actor)
            cast = self._scene(c, state, channel, actual)
            npc = self._prospects(state, cast, actual).get(patron)
            if (
                state.revision != revision
                or viewer.user_id != value.owner
                or value.loss is None
                or value.proposal is not None
                or npc is None
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Choose an actual sponsor for your unsupported Mercenary")
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    proposal=event,
                    prospect=ActorRef(kind="npc", entity=npc.id),
                    prospect_owner=npc.controller,
                    channel=channel,
                    scene=cast.id,
                    invitation=account.strip(),
                )
            )
            return self._save(c, state, viewer, key, value, event, "requested")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                patron=patron,
                account=account,
            ),
            operation,
        )

    def _offer(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[Sponsorship, ActorView]:
        value = next((x for x in records(state) if x.proposal == identity), None)
        if (
            value is None
            or value.prospect is None
            or value.prospect_owner != viewer.user_id
            or value.channel is None
            or value.loss is None
        ):
            raise WorkflowError("This original Patron offer is unavailable")
        saved, actual = self._source(state, value.mercenary)
        cast = self._scene(c, state, value.channel, actual)
        npc = self._prospects(state, cast, actual).get(value.prospect.token)
        if (
            saved != value
            or cast.id != value.scene
            or npc is None
            or npc.controller != viewer.user_id
        ):
            raise WorkflowError("Recover the actual original invitee and scene")
        return value, actual

    def _dead(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        actor: ActorRef,
    ) -> tuple[Sponsorship, ActorView, Npc]:
        if MedicalService(self.store)._handler(c)[0] != viewer.user_id:
            raise WorkflowError("Only the original human GM verifies the actual loss")
        value, actual = self._source(state, actor)
        patron = self._patron(state, value.patron)
        if value.loss is not None or patron.alive:
            raise WorkflowError("Recover the actual deceased original Patron")
        return value, actual, patron

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        people = [x for x in ancillary.records(state) if x.draft.book == "MERCENARY"]
        if not people:
            return ()
        try:
            self._gate(c, viewer)
            gm = MedicalService(self.store)._handler(c)[0]
        except (ValueError, WorkflowError):
            return ()
        result = []
        for role in people:
            value = sponsorship(state, role.actor)
            if value is None:
                continue
            if value.proposal and value.prospect_owner == viewer.user_id:
                result.append((value.proposal, "offer"))
            if value.loss is not None and value.owner == viewer.user_id:
                result.append((value.loss, "loss"))
            if viewer.user_id == gm:
                try:
                    self._dead(c, state, viewer, value.mercenary)
                except (ValueError, WorkflowError):
                    continue
                result.append((value.mercenary.token, "death"))
        return tuple(result)

    def loss(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = next(
                (x for x in records(state) if x.owner == viewer.user_id and x.loss == identity),
                None,
            )
            if value is None:
                raise WorkflowError("This original loss of sponsorship is unavailable")
            self._source(state, value.mercenary)
            return dict(patron=self._patron(state, value.patron).name)

    def death(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            target = next(
                (x.actor for x in ancillary.records(state) if x.actor.token == identity), None
            )
            if target is None:
                raise WorkflowError("Recover the original actual Mercenary")
            _, actual, patron = self._dead(c, state, viewer, target)
            return dict(revision=state.revision, person=actual.label, patron=patron.name)

    def verify_death(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            target = next(
                (x.actor for x in ancillary.records(state) if x.actor.token == identity), None
            )
            if target is None or state.revision != revision or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError("Confirm the original actual Patron’s death")
            value, _, _ = self._dead(c, state, viewer, target)
            return self._lose(c, state, viewer, key, value, account.strip(), "death_verified")

        return self._write(
            viewer, key, dict(id=identity, revision=revision, account=account), operation
        )

    def offer(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, actual = self._offer(c, state, viewer, identity)
            return dict(
                revision=state.revision, mercenary=actual.label, invitation=value.invitation
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, actual = self._offer(c, state, viewer, identity)
            assert value.channel is not None and value.prospect is not None
            require_scene_clear(self.game, c, value.channel)
            if state.revision != revision or type(accept) is not bool:
                raise WorkflowError("Reopen the actual original Patron offer")
            event = str(uuid4())
            if accept:
                if depth(state, actual.ref, value.prospect) == 0:
                    state = set_depth(state, actual.ref, value.prospect, 1, event)
                changed = Sponsorship(
                    mercenary=value.mercenary,
                    owner=value.owner,
                    patron=value.prospect,
                    source=event,
                    old=value.patron,
                )
            else:
                changed = value.model_copy(
                    update=dict(
                        proposal=None,
                        prospect=None,
                        prospect_owner=None,
                        channel=None,
                        scene=None,
                        invitation=None,
                    )
                )
            return self._save(
                c, state, viewer, key, changed, event, "accepted" if accept else "declined"
            )

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, accept=accept),
            operation,
        )
