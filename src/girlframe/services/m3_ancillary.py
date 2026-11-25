"""Human-sponsored, owner-accepted optional Ancillary characters."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as rules
from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Location
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

OFFERED = "m3.ancillary_invited"
RESPONDED = "m3.ancillary_invitation_answered"


class AncillaryService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        for subsystem in ("world", "playbooks", "plays"):
            self.missions.access.authorize(c, viewer, subsystem)
        registry = self.missions.access.registry
        assert registry is not None
        try:
            registry.require_available(rules.RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _books(self, state: GameState, affiliation: rules.Affiliation) -> tuple[rules.Book, ...]:
        if state.world is None:
            return ()
        registry = self.missions.access.registry
        assert registry is not None
        return tuple(
            book
            for book, item in rules.STARTERS.items()
            if item.affiliation == affiliation and registry.entry(item.rule).verified
        )

    def invite_options(self, viewer: GuildViewer) -> dict[str, Any] | None:
        with self.store.engine.connect() as c:
            try:
                self._access(c, viewer)
                self.missions._handler(c, viewer)
            except WorkflowError:
                return None
            state = load_state(c, self.store.campaign_id)
            if state.world is None:
                return None
            world = state.world
            foundation = bool(self._books(state, "foundation"))
            rebel = bool(self._books(state, "rebel"))
            sites: list[tuple[str, str | None, str]] = []
            for location in world.locations:
                if not location.operational:
                    continue
                if location.kind == "base" and location.foundation_operational and foundation:
                    sites.append((location.id, None, location.name + " (Foundation)"))
                if rebel:
                    sites.extend(
                        (location.id, x.id, location.name + " (" + x.name + ")")
                        for x in world.factions
                        if x.active and x.kind in ("cult", "rebel") and location.cell in x.cells
                    )
            if not sites:
                return None
            contacts = tuple(
                (ActorRef(kind="npc", entity=x.id), x.name)
                for x in world.npcs
                if x.alive and any(job in x.jobs for job in ("handler", "patron"))
            ) + tuple(
                (ActorRef(kind="external_pilot", entity=x.id), x.name)
                for x in world.pilots
                if x.alive and x.kind == "harpy" and x.custody == "captured"
            )
            from girlframe.services.m3_candidate_promotion import RULE, eligible

            candidates: tuple[tuple[ActorRef, str], ...] = ()
            try:
                self.missions.access.require_specialist_rule(RULE)
            except (ValueError, WorkflowError):
                pass
            else:
                candidates = tuple(
                    (ActorRef(kind="npc", entity=npc.id), npc.name)
                    for npc in world.npcs
                    if eligible(state, npc)
                )
            return dict(
                revision=state.revision,
                sites=tuple(sites),
                contacts=contacts,
                candidates=candidates,
            )

    def _site(self, state: GameState, site: str, faction: str | None) -> Location:
        world = state.world
        location = (
            next((x for x in world.locations if x.id == site and x.operational), None)
            if world
            else None
        )
        if location is None or world is None:
            raise WorkflowError("Choose the actual operating starting site")
        if faction is None:
            if location.kind != "base" or not location.foundation_operational:
                raise WorkflowError("The Foundation invitation needs an actual operational base")
        elif not any(
            x.id == faction
            and x.active
            and x.kind in ("rebel", "cult")
            and location.cell in x.cells
            for x in world.factions
        ):
            raise WorkflowError("Choose the actual active faction operating in this square")
        return location

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        event: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            if payload.get("timeskip") or (
                event == RESPONDED
                and any(
                    x.id == payload["id"] and x.controller == viewer.user_id and x.timeskip
                    for x in rules.offers(load_state(c, self.store.campaign_id))
                )
            ):
                from girlframe.services.m3_access import Access
                from girlframe.services.m3_timeskip_electives import RULE

                Access(self.store).require_specialist_rule(RULE)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, event, payload, operation, authorize=authorize, auto_audit=False
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _state(self, c: Connection, expected: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        if state.revision != expected or self.game.pending_actions(c):
            raise WorkflowError("STALE_ANCILLARY: finish current work and reopen the invitation")
        return state

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        controller: int,
        site: str,
        faction: str | None = None,
        contacts: tuple[ActorRef, ...] = (),
        *,
        timeskip: str | None = None,
        candidate: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            self.missions._handler(c, viewer)
            sponsor = active_handler(state)
            if sponsor is None or not HandlerService(self.store)._member(c, controller):
                raise WorkflowError("Invite an actual campaign member from the original Handler")
            location = self._site(state, site, faction)
            candidate_row = None
            if candidate is not None:
                from girlframe.services.m3_candidate_promotion import RULE, source

                self.missions.access.require_specialist_rule(RULE)
                if timeskip or candidate in contacts:
                    raise WorkflowError("Use the separate original Candidate promotion invitation.")
                candidate_row = source(state, candidate, location, faction, controller)
            books = self._books(state, "foundation" if faction is None else "rebel")
            if not books:
                raise WorkflowError("No approved Ancillary book is available for this faction")
            if len(set(contacts)) != len(contacts) or len(contacts) > 20:
                raise WorkflowError("Choose distinct actual invitation contacts")
            bound = profiles(c, self.store.campaign_id)
            for contact in contacts:
                if contact.kind not in ("npc", "external_pilot"):
                    raise WorkflowError("Disclose only actual world contacts for the invitation")
                resolve(state, contact, bound, require_current_profile=False)
            if any(
                x.controller == controller and x.phase == "offered" for x in rules.offers(state)
            ):
                raise WorkflowError("Finish the actual existing invitation first")
            value = rules.Offer(
                id=str(uuid4()),
                source_event=str(uuid4()),
                sponsor=sponsor,
                controller=controller,
                site=site,
                faction=faction,
                books=books,
                contacts=contacts,
                timeskip=timeskip,
                candidate=candidate,
                candidate_name=candidate_row.name if candidate_row is not None else None,
                candidate_sha256=fingerprint(candidate_row) if candidate_row is not None else None,
            )
            if timeskip:
                from girlframe.services.m3_timeskip_electives import bind_invite

                bind_invite(self.game, c, state, value, viewer)
            rules.put_offer(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                OFFERED,
                state,
                event_id=value.source_event,
                invitation=value.id,
            )
            return dict(id=value.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            OFFERED,
            dict(
                expected=expected,
                controller=controller,
                site=site,
                faction=faction,
                contacts=tuple(x.model_dump(mode="json") for x in contacts),
            )
            | (dict(timeskip=timeskip) if timeskip is not None else {})
            | (dict(candidate=candidate.model_dump(mode="json")) if candidate is not None else {}),
            operation,
        )

    def _source(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> rules.Offer:
        value = next((x for x in rules.offers(state) if x.id == identity), None)
        if value is None or viewer.user_id != value.controller:
            raise WorkflowError(
                "This private invitation belongs to the original invited controller"
            )
        original = _history(c, self.game, value.source_event)
        if value.model_copy(update=dict(phase="offered", decision_event=None)) not in rules.offers(
            original
        ) or value.sponsor != active_handler(original):
            raise WorkflowError("Recover the original approved Ancillary invitation")
        return value

    def _bond_targets(
        self, c: Connection, state: GameState, value: rules.Offer, draft: rules.Draft
    ) -> None:
        targets = self._targets(state, value, draft.book)
        for kind, target in (
            ("bond", draft.bond),
            ("patron", draft.patron),
            ("wanted", draft.wanted),
        ):
            if target is not None:
                if target not in dict(targets[kind]):
                    raise WorkflowError("Choose an actual eligible and disclosed starting contact")
                resolve(
                    state,
                    target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, draft: rules.Draft | None
    ) -> dict[str, Any]:
        if draft is not None:
            draft = rules.Draft.model_validate_json(draft.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            value = self._source(c, state, viewer, identity)
            if value.phase != "offered":
                raise WorkflowError("Reopen the original pending invitation")
            event = str(uuid4())
            actor = None
            if draft is not None:
                registry = self.missions.access.registry
                assert registry is not None
                registry.require_available(rules.STARTERS[draft.book].rule)
                if draft.book not in value.books or active_handler(state) != value.sponsor:
                    raise WorkflowError(
                        "Use the original invitation's approved book and appointment"
                    )
                location = self._site(state, value.site, value.faction)
                promoted = None
                if value.candidate is not None:
                    from girlframe.services.m3_candidate_promotion import RULE, source

                    self.missions.access.require_specialist_rule(RULE)
                    promoted = source(
                        state,
                        value.candidate,
                        location,
                        value.faction,
                        viewer.user_id,
                    )
                    if (
                        fingerprint(promoted) != value.candidate_sha256
                        or promoted.name != draft.name.strip()
                    ):
                        raise WorkflowError("Preserve the exact original Pilot Candidate and name.")
                self._bond_targets(c, state, value, draft)
                assert state.world is not None
                actor = ActorRef(kind="external_pilot", entity="ancillary:" + identity)
                source_assets: tuple[
                    tuple[Literal["girl", "frame"], tuple[rules.NamedAsset, rules.NamedAsset]],
                    ...,
                ] = (("girl", draft.girl_assets), ("frame", draft.frame_assets))
                inventory = tuple(
                    Asset(
                        id=f"{actor.entity}:{family}:{index}",
                        family=family,
                        name=x.name,
                        description=x.description.strip(),
                    )
                    for family, group in source_assets
                    for index, x in enumerate(group)
                )
                state.world = update(
                    state.world,
                    pilots=(
                        *state.world.pilots,
                        AdversaryPilot(
                            id=actor.entity,
                            name=draft.name.strip(),
                            kind=rules.STARTERS[draft.book].affiliation,
                            cell=location.cell,
                            girl=draft.book,
                            frame="Ancillary",
                            assets=inventory,
                            faction=value.faction,
                            controller=viewer.user_id,
                            revealed=promoted.revealed if promoted is not None else False,
                        ),
                    ),
                )
                char = rules.Character(
                    actor=actor,
                    controller=viewer.user_id,
                    event=event,
                    draft=draft,
                    identities=tuple(
                        IdentityState(id=f"{actor.entity}:identity:{i}", name=name, slot=i)
                        for i, name in enumerate(rules.STARTERS[draft.book].identities)
                    ),
                )
                rules.put(state, char)
                if promoted is not None:
                    from girlframe.services.m3_candidate_promotion import activate

                    state = activate(
                        state, value, promoted, actor, event, int(value.sponsor.entity)
                    )
                for target in (draft.bond, draft.patron):
                    if target is not None and depth(state, actor, target) == 0:
                        state = set_depth(state, actor, target, 1, event)
            phase = "accepted" if draft is not None else "declined"
            rules.put_offer(state, value.model_copy(update=dict(phase=phase, decision_event=event)))
            if value.timeskip:
                from girlframe.services.m3_timeskip_electives import settle_invite

                settle_invite(self.game, c, state, value, viewer, actor, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                RESPONDED,
                state,
                event_id=event,
                invitation=identity,
                phase=phase,
            )
            return dict(
                id=identity, phase=phase, actor=actor.model_dump(mode="json") if actor else None
            )

        return self._write(
            viewer,
            key,
            RESPONDED,
            dict(
                id=identity,
                expected=expected,
                draft=draft.model_dump(mode="json") if draft else None,
            ),
            operation,
        )

    def invitation(self, viewer: GuildViewer, identity: str) -> tuple[rules.Offer, int]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return self._source(c, state, viewer, identity), state.revision

    def draft_targets(
        self, viewer: GuildViewer, identity: str, book: rules.Book
    ) -> dict[str, tuple[tuple[ActorRef, str], ...]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = self._source(c, state, viewer, identity)
            return self._targets(state, value, book)

    def _targets(
        self, state: GameState, value: rules.Offer, book: rules.Book
    ) -> dict[str, tuple[tuple[ActorRef, str], ...]]:
        if book not in value.books or state.world is None:
            raise WorkflowError("Use a book from the original invitation")
        girls = tuple(
            (current_ref(state, uid), state.sheets[str(uid)].callsign)
            for uid in state.order
            if state.sheets[str(uid)].character_id is not None
        )
        contacts = [
            (ref, npc)
            for ref in value.contacts
            if ref.kind == "npc"
            for npc in state.world.npcs
            if npc.id == ref.entity and npc.alive
        ]
        if book == "ABYSSAL ACOLYTE":
            bonds = tuple(
                (ref, pilot.name)
                for ref in value.contacts
                if ref.kind == "external_pilot"
                for pilot in state.world.pilots
                if (
                    pilot.id == ref.entity
                    and pilot.alive
                    and pilot.kind == "harpy"
                    and pilot.faction == value.faction
                    and pilot.custody == "captured"
                )
            )
        elif book in ("REVOLUTIONARY IDEALIST", "ANGEL-WIFE"):
            roles = ("handler",) if book == "REVOLUTIONARY IDEALIST" else ("handler", "patron")
            bonds = tuple(
                (ref, npc.name)
                for ref, npc in contacts
                if npc.faction == value.faction and any(role in npc.jobs for role in roles)
            )
        else:
            bonds = girls if book not in ("CHAINED DARLING", "WARBOY") else ()
        return dict(
            bond=bonds,
            patron=tuple((ref, npc.name) for ref, npc in contacts if "patron" in npc.jobs)
            if book == "MERCENARY"
            else (),
            wanted=girls if book == "WARBOY" else (),
        )
