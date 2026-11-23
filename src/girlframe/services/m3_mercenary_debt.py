"""An actual fictional cash offer and a Mercenary's private Order response."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_actor_plays as plays
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.mercenary.debt"
KIND = "mercenary_debt"
CONTACT_KIND = "mercenary_debt_contact"
DEBT_MODIFIER = -2


class Contact(Model):
    issuer: CastRole
    recipient: CastRole
    scene: str
    event: str
    active: bool


def contacts(state: GameState) -> tuple[Contact, ...]:
    return tuple(
        Contact.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == CONTACT_KIND
    )


class Roll(Model):
    faces: tuple[int, int]
    heat: int
    event: str
    rng_source: str

    @property
    def total(self) -> int:
        return sum(self.faces) + self.heat + DEBT_MODIFIER


class Debt(Model):
    id: str
    issuer: CastRole
    recipient: CastRole
    channel: int
    scene: str
    gm: int
    appointment: str
    item: str
    item_event: str
    instruction: str
    event: str
    step: Literal["verify", "respond", "result", "witness", "referred", "closed"]
    review_event: str | None = None
    review_account: str | None = None
    roll: Roll | None = None
    outcome: str | None = None
    outcome_event: str | None = None
    account: str | None = None
    witness_event: str | None = None
    witness_account: str | None = None


def records(state: GameState) -> tuple[Debt, ...]:
    return tuple(Debt.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class DebtService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        gate = Access(self.store)
        gate.require_specialist_rule(RULE)
        assert gate.registry is not None
        gate.registry.require_available(ancillary.STARTERS["MERCENARY"].rule)

    def _person(
        self, c: Connection, state: GameState, cast: SceneCast, ref: ActorRef
    ) -> tuple[CastRole, ActorView]:
        role = next((x for x in cast.roles if x.actor == ref), None)
        actual = resolve(state, ref, profiles(c, self.store.campaign_id))
        if (
            role is None
            or role.controller != actual.controller
            or not actual.alive
            or actual.cell is None
            or actual.offstage_source
            or actual.custody not in (None, "free")
        ):
            raise WorkflowError("Use an available original character in the actual scene.")
        return role, actual

    def _scene(self, c: Connection, state: GameState, channel: int) -> tuple[SceneCast, int, str]:
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        if cast.facilitator != gm:
            raise WorkflowError("Recover the human facilitator of the original scene.")
        return cast, gm, appointment

    def _cash(
        self, c: Connection, state: GameState, ref: ActorRef, item_id: str
    ) -> tuple[str, str]:
        item = prove_item(c, self.game, state, item_id)
        if (
            item.holder != ref
            or item.location_mode != "carried"
            or item.condition != "intact"
            or item.weapon
            or item.asset_json is not None
            or item.confirmed_event is None
        ):
            raise WorkflowError(
                "An offer needs an actual carried, confirmed fictional cash object."
            )
        return item.name, item.confirmed_event

    def _local(self, state: GameState, issuer: ActorView, subject: ActorView) -> bool:
        from girlframe.services.m3_consume_support import knowledge_allowed

        role = ancillary.find(state, subject.ref)
        return bool(
            role is not None
            and role.draft.book == "MERCENARY"
            and role.controller == subject.controller != issuer.controller
            and issuer.cell == subject.cell
            and _visible(state, issuer.ref, subject.controller)
            and knowledge_allowed(state, issuer.ref)
            and knowledge_allowed(state, subject.ref)
        )

    def _eligible(
        self, state: GameState, cast: SceneCast, issuer: ActorView, subject: ActorView
    ) -> bool:
        return self._local(state, issuer, subject) and (
            _visible(state, subject.ref, issuer.controller)
            or any(
                x.active
                and x.scene == cast.id
                and x.issuer in cast.roles
                and x.recipient in cast.roles
                and x.issuer.actor == issuer.ref
                and x.recipient.actor == subject.ref
                for x in contacts(state)
            )
        )

    def contact_options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        subject: ActorRef,
    ) -> dict[str, tuple[str, bool]]:
        self._gate(c, viewer)
        cast, _, _ = self._scene(c, state, channel)
        recipient, actual = self._person(c, state, cast, subject)
        if recipient.controller != viewer.user_id:
            raise WorkflowError("The original Mercenary controls who she approaches.")
        authorized = {
            x.issuer
            for x in contacts(state)
            if x.active and x.recipient == recipient and x.scene == cast.id
        }
        people = {}
        for role in cast.roles:
            if role.controller == viewer.user_id or not _visible(state, role.actor, viewer.user_id):
                continue
            try:
                _, issuer = self._person(c, state, cast, role.actor)
            except (ValueError, WorkflowError):
                continue
            if self._local(state, issuer, actual):
                people[role.actor.token] = (issuer.label, role in authorized)
        return people

    def contact_menu(self, viewer: GuildViewer, channel: int, subject: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            people = self.contact_options(c, state, viewer, channel, subject)
            return dict(revision=state.revision, people=people)

    def contact(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        revision: int,
        contact: str,
        active: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            available = self.contact_options(c, state, viewer, channel, subject)
            if (
                state.revision != revision
                or contact not in available
                or available[contact][1] == active
            ):
                raise WorkflowError("STALE_DEBT: reopen the actual scene contact.")
            cast, _, _ = self._scene(c, state, channel)
            recipient, _ = self._person(c, state, cast, subject)
            issuer = next(x for x in cast.roles if x.actor.token == contact)
            identity = ":".join((cast.id, recipient.source_event, issuer.source_event))
            event = str(uuid4())
            value = Contact(
                issuer=issuer, recipient=recipient, scene=cast.id, event=event, active=active
            )
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (CONTACT_KIND, identity)
            ]
            state.facts.append(dict(kind=CONTACT_KIND, id=identity, body=value.model_dump_json()))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.debt_contact_changed",
                state,
                event_id=event,
                scene_id=cast.id,
            )
            return dict(active=active)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                subject=subject.token,
                revision=revision,
                contact=contact,
                active=active,
            ),
            operation,
        )

    def options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        ref: ActorRef,
    ) -> tuple[dict[str, str], dict[str, str]]:
        self._gate(c, viewer)
        cast, _, _ = self._scene(c, state, channel)
        _, issuer = self._person(c, state, cast, ref)
        if issuer.controller != viewer.user_id:
            raise WorkflowError("The actual offer belongs to the holder's controller.")
        items = {}
        reserved = {
            x.item for x in records(state) if x.step != "closed" or x.review_event is not None
        }
        for item in state.held_items:
            if item.holder != ref or item.id in reserved:
                continue
            try:
                items[item.id], _ = self._cash(c, state, ref, item.id)
            except (ValueError, WorkflowError):
                continue
        people = {}
        if items:
            for role in ancillary.records(state):
                if role.draft.book != "MERCENARY":
                    continue
                try:
                    _, person = self._person(c, state, cast, role.actor)
                except (ValueError, WorkflowError):
                    continue
                if self._eligible(state, cast, issuer, person):
                    people[role.actor.token] = person.label
        return items, people

    def menu(self, viewer: GuildViewer, channel: int, ref: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            items, people = self.options(c, state, viewer, channel, ref)
            return dict(revision=state.revision, items=items, people=people)

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        debt: Debt,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, debt.id)]
        state.facts.append(dict(kind=KIND, id=debt.id, body=debt.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.mercenary_debt_" + debt.step,
            state,
            event_id=event,
            scene_id=debt.scene,
        )
        return dict(
            id=debt.id,
            step=debt.step,
            event=event,
            outcome=debt.outcome,
            total=debt.roll.total if debt.roll else None,
        )

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
                "m3.mercenary_debt",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        issuer: ActorRef,
        revision: int,
        item: str,
        target: str,
        instruction: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            items, people = self.options(c, state, viewer, channel, issuer)
            if state.revision != revision or item not in items or target not in people:
                raise WorkflowError("STALE_DEBT: reopen the scene's actual offer.")
            if not instruction.strip() or len(instruction) > 1200:
                raise WorkflowError("Record your character's actual order.")
            cast, gm, appointment = self._scene(c, state, channel)
            subject = next(x.actor for x in cast.roles if x.actor.token == target)
            owner, _ = self._person(c, state, cast, issuer)
            recipient, _ = self._person(c, state, cast, subject)
            _, item_event = self._cash(c, state, issuer, item)
            event = str(uuid4())
            debt = Debt(
                id=event,
                issuer=owner,
                recipient=recipient,
                channel=channel,
                scene=cast.id,
                gm=gm,
                appointment=appointment,
                item=item,
                item_event=item_event,
                instruction=instruction.strip(),
                event=event,
                step="verify",
            )
            return self._save(c, state, viewer, key, debt, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                issuer=issuer.token,
                revision=revision,
                item=item,
                target=target,
                instruction=instruction,
            ),
            operation,
        )

    def _check(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        debt: Debt,
    ) -> tuple[str, ActorView]:
        if debt.step == "closed" or viewer.user_id != (
            debt.gm if debt.step in ("verify", "witness", "referred") else debt.recipient.controller
        ):
            raise WorkflowError("This original order response is unavailable.")
        cast, gm, appointment = self._scene(c, state, debt.channel)
        if (cast.id, gm, appointment) != (debt.scene, debt.gm, debt.appointment):
            raise WorkflowError("Recover the original scene and its facilitator.")
        owner, issuer = self._person(c, state, cast, debt.issuer.actor)
        recipient, subject = self._person(c, state, cast, debt.recipient.actor)
        if (owner, recipient) != (debt.issuer, debt.recipient) or not self._eligible(
            state, cast, issuer, subject
        ):
            raise WorkflowError("Recover the original parties to this cash offer.")
        item = ""
        if debt.step == "verify":
            item, event = self._cash(c, state, issuer.ref, debt.item)
            if event != debt.item_event:
                raise WorkflowError("Recover the original fictional cash source.")
        return item, issuer

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        result = []
        candidates = tuple(
            x
            for x in records(state)
            if (x.step in ("verify", "witness", "referred") and x.gm == viewer.user_id)
            or (x.step in ("respond", "result") and x.recipient.controller == viewer.user_id)
        )
        if not candidates:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        for debt in candidates:
            try:
                self._check(c, state, viewer, debt)
            except (ValueError, WorkflowError):
                continue
            result.append((debt.id, debt.step))
        return tuple(result)

    def _find(self, state: GameState, identity: str) -> Debt:
        value = next((x for x in records(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("This original order response is unavailable.")
        return value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            debt = self._find(state, identity)
            item, issuer = self._check(c, state, viewer, debt)
            actual = ancillary.find(state, debt.recipient.actor)
            assert actual is not None
            return dict(
                revision=state.revision,
                step=debt.step,
                instruction=debt.instruction,
                issuer=issuer.label,
                item=item,
                current_heat=actual.heat,
                total=debt.roll.total if debt.roll else None,
                tier=tier(debt.roll.total) if debt.roll else None,
                outcome=debt.outcome,
                witness_account=debt.witness_account
                if debt.step in ("witness", "referred")
                else None,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        *,
        heat: int = 0,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            debt = self._find(state, identity)
            self._check(c, state, viewer, debt)
            require_scene_clear(self.game, c, debt.channel)
            if state.revision != revision:
                raise WorkflowError("STALE_DEBT: reopen the original private order.")
            if type(heat) is not int or heat < 0 or len(account) > 1200:
                raise WorkflowError("Use the original response and an allowed Heat amount.")
            actual = ancillary.find(state, debt.recipient.actor)
            assert actual is not None
            event = str(uuid4())
            if debt.step == "verify":
                if choice not in ("verify", "dismiss") or heat or not account.strip():
                    raise WorkflowError(
                        "The human GM must verify the actual cash offer or dismiss it."
                    )
                if choice == "verify":
                    debt = debt.model_copy(
                        update=dict(
                            step="respond",
                            review_event=event,
                            review_account=account.strip(),
                        )
                    )
                else:
                    debt = debt.model_copy(
                        update=dict(
                            step="closed",
                            outcome="dismissed",
                            outcome_event=event,
                            review_account=account.strip(),
                        )
                    )
            elif debt.step in ("witness", "referred"):
                if (
                    debt.step == "referred"
                    or choice not in ("unnoticed", "refer")
                    or heat
                    or not account.strip()
                ):
                    raise WorkflowError("Record what the original scene establishes about notice.")
                debt = debt.model_copy(
                    update=dict(
                        step="closed" if choice == "unnoticed" else "referred",
                        witness_event=event,
                        witness_account=account.strip(),
                    )
                )
            elif debt.step == "respond":
                if choice == "follow" and not heat and account.strip():
                    debt = debt.model_copy(
                        update=dict(
                            step="closed",
                            outcome="chose_to_follow",
                            outcome_event=event,
                            account=account.strip(),
                        )
                    )
                elif choice == "disobey" and not account:
                    subject = resolve(state, actual.actor, (), require_current_profile=False)
                    if heat:
                        from girlframe.engine.m3_sentinel_shell import holds

                        if holds(state, actual.actor, "trapped"):
                            raise WorkflowError("This original Girl cannot spend Heat until freed.")
                    from girlframe.services.m3_wyvern_combat import require_free

                    require_free(self.game, c, state, actual.actor)
                    state = commit(
                        state,
                        actual.actor,
                        (),
                        Commitment(heat=heat),
                        subject.source_sha256,
                        require_current_profile=False,
                    ).state
                    faces = self.game.dice.roll()
                    if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                        raise ValueError("Dice source returned invalid faces.")
                    roll = Roll(
                        faces=faces, heat=heat, event=event, rng_source=self.game.rng_source
                    )
                    outcome = (
                        dict(step="witness", outcome="cannot_disobey", outcome_event=event)
                        if tier(roll.total) == "low"
                        else dict(step="result")
                    )
                    debt = debt.model_copy(update=dict(roll=roll, **outcome))
                else:
                    raise WorkflowError("Choose your response to this original cash-backed order.")
            else:
                assert debt.roll is not None
                level = tier(debt.roll.total)
                if choice != "act" or not account.strip():
                    raise WorkflowError("Only the original Mercenary confirms her actual response.")
                if level == "mid" and heat in (1, 2) and len(account.strip()) <= 120:
                    plays.add_tag(state, actual.actor, account, (debt.recipient.controller,))
                elif level != "high" or heat != 2:
                    raise WorkflowError("Use the verified result choice and printed Heat.")
                actual = ancillary.find(state, actual.actor)
                assert actual is not None
                from girlframe.engine.m3_leviathan_obsession import allowed_gain

                gained = allowed_gain(state, actual.actor, heat, "Disobey Orders", event)
                ancillary.put(state, actual.model_copy(update=dict(heat=actual.heat + gained)))
                debt = debt.model_copy(
                    update=dict(
                        step="witness",
                        outcome="chose_to_disobey",
                        outcome_event=event,
                        account=account.strip(),
                    )
                )
            return self._save(c, state, viewer, key, debt, event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                choice=choice,
                heat=heat,
                account=account,
            ),
            operation,
        )
