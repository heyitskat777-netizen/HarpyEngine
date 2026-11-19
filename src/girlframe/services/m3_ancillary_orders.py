"""Actual NPC authorities issue and receive optional character Orders."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actor_plays as plays
from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import CapturedDraft, find
from girlframe.engine.m3_cast import validate_role
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_revolutionary_identity import personal_handler
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

ILLEGAL = "ancillary.revolutionary-idealist.illegal-girl"
SERVICE = "ancillary.angel-wife.made-for-service"
KIND = "ancillary_npc_order"
ADDRESS = "wife_address_directive"


class Address(Model):
    subject: ActorRef
    label: str
    pronouns: Literal["he", "she"]


class Order(Model):
    id: str
    owner: CastRole
    target: CastRole
    channel: int
    scene: str
    gm: int
    appointment: str
    source: str
    instruction: str
    isolation: str | None = None
    mercenary: str | None = None
    address: Address | None = None
    stage: Literal["respond", "tag", "outcome", "review", "held", "closed"] = "respond"
    faces: tuple[int, int] | None = None
    rng_source: str | None = None
    heat: int = 0
    base_modifier: int = 0
    good_soldier: str | None = None
    warboy_low: str | None = None
    modifier: int = 0
    tag: str | None = None
    total: int | None = None
    roll_event: str | None = None
    consequence: str | None = None
    account: str | None = None


def records(state: GameState) -> tuple[Order, ...]:
    return tuple(Order.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def _available(game: GameService, rule: str) -> bool:
    try:
        Access(game.store).require_specialist_rule(rule)
    except (ValueError, WorkflowError):
        return False
    return True


def _independent(state: GameState, ref: ActorRef) -> bool:
    if state.world is None:
        return False
    return any(
        x.id == ref.entity and x.kind == "rebel" and x.alive and x.custody in ("free", "converted")
        for x in state.world.pilots
    )


def _historically_foundation(c: Connection, game: GameService, actor: ActorRef) -> bool:
    history = t.m2["m2_state_history"]
    pilots = sa.func.json_each(history.c.body_json, "$.world.pilots").table_valued(
        "value",
        joins_implicitly=True,
    )
    return bool(
        c.scalar(
            sa.select(history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                sa.func.json_extract(pilots.c.value, "$.id") == actor.entity,
                sa.or_(
                    sa.func.json_extract(pilots.c.value, "$.kind") == "foundation",
                    sa.and_(
                        sa.func.json_extract(pilots.c.value, "$.custody").in_(
                            ("captured", "transported")
                        ),
                        sa.func.json_extract(pilots.c.value, "$.custodian")
                        == sa.func.json_extract(history.c.body_json, "$.handler"),
                    ),
                ),
            )
            .limit(1)
        )
    )


def illegal(
    c: Connection,
    game: GameService,
    state: GameState,
    actor: ActorRef,
) -> bool:
    original = find(state, actor)
    return bool(
        original is not None
        and original.draft.book == "REVOLUTIONARY IDEALIST"
        and _available(game, ILLEGAL)
        and _independent(state, actor)
        and not _historically_foundation(c, game, actor)
    )


def pronoun_setting(
    c: Connection,
    game: GameService,
    state: GameState,
    actor: ActorRef,
) -> str | None:
    if not illegal(c, game, state, actor):
        return None
    return next(
        (
            x["value"]
            for x in state.facts
            if x.get("kind") == "illegal_girl_pronouns" and x.get("actor") == actor.token
        ),
        None,
    )


def _wife_spouse(state: GameState, game: GameService, actor: ActorRef) -> ActorRef | None:
    role = find(state, actor)
    if role is None or role.draft.book != "ANGEL-WIFE" or not _available(game, SERVICE):
        return None
    identity = (
        role.event + ":identity"
        if isinstance(role.draft, CapturedDraft)
        else actor.entity + ":identity:0"
    )
    if not any(x.id == identity and x.name == "Wife" for x in role.identities):
        return None
    return role.draft.handler if isinstance(role.draft, CapturedDraft) else role.draft.bond


def address_directives(
    game: GameService, state: GameState, actor: ActorRef
) -> tuple[dict[str, str], ...]:
    if _wife_spouse(state, game, actor) is None:
        return ()
    return tuple(
        dict(subject=x["subject"], label=x["label"], pronouns=x["pronouns"])
        for x in state.facts
        if x.get("kind") == ADDRESS and x.get("wife") == actor.token
    )


def _rules(
    game: GameService,
    c: Connection,
    state: GameState,
    issuer: ActorRef,
    target: ActorRef,
    *,
    npc: bool,
) -> tuple[bool, bool] | None:
    role = find(state, target)
    if role is None:
        return None
    successor = personal_handler(game, state, target)
    if successor is not None:
        return (False, illegal(c, game, state, target)) if successor == issuer else None
    if role.draft.book == "SOLDIER":
        from girlframe.services.m3_ancillary_intimacy import SOLDIER

        cadre = rank.current(state, target)
        if cadre is not None and cadre.handler == issuer and _available(game, SOLDIER):
            return False, False
    if role.draft.book == "WARBOY":
        from girlframe.services.m3_ancillary_intimacy import WARBOY

        cadre = rank.current(state, target)
        if cadre is not None and _available(game, WARBOY):
            people = rank.actual_members(state, cadre)
            if issuer in people[: people.index(target)]:
                return False, False
    if not npc or not _independent(state, target):
        return None
    if _wife_spouse(state, game, target) == issuer:
        return True, False
    if illegal(c, game, state, target):
        original = role.draft.handler if isinstance(role.draft, CapturedDraft) else role.draft.bond
        cadre = rank.current(state, target)
        if (cadre.handler if cadre is not None else original) == issuer:
            return False, True
    return None


class AncillaryOrderService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)

    def _person(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorRef,
    ) -> tuple[CastRole, ActorView]:
        actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        role = validate_role(cast, actual)
        if (
            actual.cell is None
            or actual.offstage_source
            or actual.custody not in (None, "free", "converted")
            or not knowledge_allowed(state, actor)
        ):
            raise WorkflowError("Recover the actual available original person.")
        return role, actual

    def _scene(self, c: Connection, state: GameState, channel: int) -> tuple[SceneCast, int, str]:
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        if cast.facilitator != gm:
            raise WorkflowError("Recover the actual source facilitator.")
        return cast, gm, appointment

    def options(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        issuer: ActorRef,
    ) -> dict[str, str]:
        self._gate(c, viewer)
        cast, _, _ = self._scene(c, state, channel)
        owner, actual = self._person(c, state, cast, issuer)
        if owner.controller != viewer.user_id:
            raise WorkflowError("Use your actual original Order authority.")
        people = {}
        blocked = {
            x.target.actor for x in records(state) if x.stage != "closed" and x.owner == owner
        }
        for member in cast.roles:
            if (
                member.actor in blocked
                or member.controller == viewer.user_id
                or _rules(self.game, c, state, issuer, member.actor, npc=actual.rules == "npc")
                is None
            ):
                continue
            try:
                _, body = self._person(c, state, cast, member.actor)
            except (ValueError, WorkflowError):
                continue
            if body.cell == actual.cell:
                people[member.actor.token] = body.label
        return people

    def menu(self, viewer: GuildViewer, channel: int, issuer: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            people = self.options(c, state, viewer, channel, issuer)
            cast, _, _ = self._scene(c, state, channel)
            owner, issuer_body = self._person(c, state, cast, issuer)
            references = {}
            for role in cast.roles:
                if (
                    role.actor.token in people
                    and _wife_spouse(state, self.game, role.actor) == issuer
                ):
                    references.update(
                        self._address_references(c, state, cast, owner, role, issuer_body)
                    )
            return dict(revision=state.revision, people=people, references=references)

    def _address_references(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        owner: CastRole,
        target: CastRole,
        issuer: ActorView,
    ) -> dict[str, str]:
        options = {}
        for role in cast.roles:
            if role.actor not in (owner.actor, target.actor) and not (
                _visible(state, role.actor, owner.controller)
                and _visible(state, role.actor, target.controller)
            ):
                continue
            try:
                _, actual = self._person(c, state, cast, role.actor)
            except (ValueError, WorkflowError):
                continue
            if actual.cell == issuer.cell:
                options[role.actor.token] = actual.label
        return options

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
                "m3.ancillary_npc_order",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        order: Order,
        event: str,
    ) -> dict[str, Any]:
        self._put(state, order)
        if order.isolation is not None and order.stage == "closed":
            from girlframe.services.m3_chained_isolation import complete_order

            complete_order(state, order.isolation, order.id, event)
        elif order.mercenary is not None and order.stage == "closed":
            from girlframe.services.m3_ancillary_intimacy import prove_high_order, settle_high_order

            case = prove_high_order(self.game, c, state, order)
            settle_high_order(state, case, order)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.ancillary_npc_order_" + order.stage,
            state,
            event_id=event,
            scene_id=order.scene,
        )
        if order.isolation is not None and order.stage == "closed":
            from girlframe.services.m3_role_punishments import synchronize

            synchronize(self.game, c, None, event)
        return dict(id=order.id, event=event, stage=order.stage, total=order.total)

    def _put(self, state: GameState, order: Order) -> None:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, order.id)]
        state.facts.append(dict(kind=KIND, id=order.id, body=order.model_dump_json()))

    def isolation_roles(
        self,
        c: Connection,
        state: GameState,
        case: RolePunishment,
        channel: int,
    ) -> tuple[SceneCast, int, str, CastRole, CastRole]:
        cast, gm, appointment = self._scene(c, state, channel)
        owner, _ = self._person(c, state, cast, case.executor)
        recipient, _ = self._person(c, state, cast, case.subject)
        return cast, gm, appointment, owner, recipient

    def isolation_order(
        self,
        c: Connection,
        state: GameState,
        case: RolePunishment,
        channel: int,
        event: str,
    ) -> None:
        self._guard(c, channel)
        cast, gm, appointment, owner, recipient = self.isolation_roles(c, state, case, channel)
        self._put(
            state,
            Order(
                id=event,
                owner=owner,
                target=recipient,
                channel=channel,
                scene=cast.id,
                gm=gm,
                appointment=appointment,
                source=event,
                isolation=case.id,
                instruction="Come to my side.",
            ),
        )

    def issue(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        issuer: ActorRef,
        revision: int,
        target: str,
        instruction: str,
        *,
        reference: str | None = None,
        pronouns: Literal["he", "she"] | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._guard(c, channel)
            state = load_state(c, self.store.campaign_id)
            if (
                state.revision != revision
                or target not in self.options(c, state, viewer, channel, issuer)
                or len(instruction.strip()) > 1200
            ):
                raise WorkflowError("Use your actual authority to give the original scoped order.")
            cast, gm, appointment = self._scene(c, state, channel)
            owner = next(x for x in cast.roles if x.actor == issuer)
            recipient = next(x for x in cast.roles if x.actor.token == target)
            message = instruction.strip()
            address = None
            if reference is not None and pronouns in ("he", "she") and not message:
                if _wife_spouse(state, self.game, recipient.actor) != owner.actor:
                    raise WorkflowError("Only this original spouse can give an address directive.")
                _, body = self._person(c, state, cast, issuer)
                allowed = self._address_references(c, state, cast, owner, recipient, body)
                if reference not in allowed:
                    raise WorkflowError("Refer only to a known and co-present original character.")
                subject = next(x.actor for x in cast.roles if x.actor.token == reference)
                address = Address(subject=subject, label=allowed[reference], pronouns=pronouns)
                message = f"Refer to {address.label} as {address.pronouns}."
            elif not message or reference is not None or pronouns is not None:
                raise WorkflowError("Give a direct Order or one complete address directive.")
            event = str(uuid4())
            order = Order(
                id=event,
                owner=owner,
                target=recipient,
                channel=channel,
                scene=cast.id,
                gm=gm,
                appointment=appointment,
                source=event,
                instruction=message,
                address=address,
            )
            return self._save(c, state, viewer, key, order, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                issuer=issuer.token,
                revision=revision,
                target=target,
                instruction=instruction,
            )
            | (dict(reference=reference, pronouns=pronouns) if reference or pronouns else {}),
            operation,
        )

    def _guard(self, c: Connection, channel: int) -> None:
        self.game.unpaused(c)
        MedicalService(self.store)._idle(c)
        require_clear(self.game, c, channel)
        require_scene_clear(self.game, c, channel)

    def _recipient(self, order: Order) -> int | None:
        if order.stage == "closed":
            return None
        return order.gm if order.stage in ("review", "held") else order.target.controller

    def _source(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        order: Order,
    ) -> tuple[ActorView, ActorView, tuple[bool, bool]]:
        if self._recipient(order) != viewer.user_id:
            raise WorkflowError("This original private order is unavailable.")
        cast, gm, appointment = self._scene(c, state, order.channel)
        owner, actor = self._person(c, state, cast, order.owner.actor)
        recipient, target = self._person(c, state, cast, order.target.actor)
        port: tuple[bool, bool] | None
        if order.isolation is not None:
            from girlframe.services.m3_chained_isolation import prove_order

            prove_order(self.game, c, state, order.isolation, order.id, owner, recipient)
            port = (order.consequence == "cannot_disobey", False)
        elif order.mercenary is not None:
            from girlframe.services.m3_ancillary_intimacy import prove_high_order

            prove_high_order(self.game, c, state, order)
            port = (order.consequence == "cannot_disobey", False)
        else:
            port = _rules(
                self.game, c, state, owner.actor, recipient.actor, npc=actor.rules == "npc"
            )
        if (
            (cast.id, gm, appointment, owner, recipient)
            != (order.scene, order.gm, order.appointment, order.owner, order.target)
            or port is None
            or (order.isolation is None and actor.cell != target.cell)
        ):
            raise WorkflowError("Recover the original current scene and Order authority.")
        if order.address is not None and (
            not port[0]
            or order.address.subject.token
            not in self._address_references(c, state, cast, owner, recipient, actor)
        ):
            raise WorkflowError("Recover the original known character and spouse directive.")
        return actor, target, port

    def _order(self, state: GameState, identity: str) -> Order:
        found = next((x for x in records(state) if x.id == identity), None)
        if found is None:
            raise WorkflowError("This original private order is unavailable.")
        return found

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        options = tuple(x for x in records(state) if self._recipient(x) == viewer.user_id)
        if not options:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        allowed = []
        for order in options:
            try:
                self._source(c, state, viewer, order)
            except (ValueError, WorkflowError):
                continue
            allowed.append((order.id, order.stage))
        return tuple(allowed)

    def _tags(self, state: GameState, order: Order) -> dict[str, str]:
        return {
            x.id: x.label
            for x in plays.tags(state, order.target.actor)
            if not x.marked and x.scene_used != order.scene
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = self._order(state, identity)
            issuer, target, (forbidden, self_tag) = self._source(c, state, viewer, value)
            return dict(
                revision=state.revision,
                stage=value.stage,
                issuer=issuer.label,
                instruction=value.instruction,
                isolation=value.isolation is not None,
                address=value.address is not None,
                forbidden=forbidden,
                heat=target.heat,
                tags=self._tags(state, value) if self_tag and value.stage == "tag" else {},
                total=value.total,
                level=tier(value.total) if value.total is not None else None,
                good_soldier=value.good_soldier is not None
                and viewer.user_id == value.target.controller,
                warboy_low=value.warboy_low is not None
                and viewer.user_id == value.target.controller,
            )

    def pronoun_menu(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            role = find(state, actor)
            if (
                role is None
                or role.controller != viewer.user_id
                or not illegal(c, self.game, state, actor)
            ):
                raise WorkflowError("This original character does not own the pronoun choice.")
            return dict(
                revision=state.revision, current=pronoun_setting(c, self.game, state, actor)
            )

    def set_pronouns(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        revision: int,
        value: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            role = find(state, actor)
            if (
                state.revision != revision
                or role is None
                or role.controller != viewer.user_id
                or not illegal(c, self.game, state, actor)
                or not 0 < len(value.strip()) <= 48
                or not value.strip().isprintable()
            ):
                raise WorkflowError("Reopen your actual available pronoun choice.")
            event = str(uuid4())
            state.facts = [
                x
                for x in state.facts
                if (x.get("kind"), x.get("actor")) != ("illegal_girl_pronouns", actor.token)
            ]
            state.facts.append(
                dict(
                    kind="illegal_girl_pronouns",
                    actor=actor.token,
                    value=value.strip(),
                    event=event,
                )
            )
            self.game.event(
                c, viewer.user_id, key, "m3.illegal_girl_pronouns", state, event_id=event
            )
            return dict(event=event)

        return self._write(
            viewer,
            key,
            dict(
                actor=actor.token,
                revision=revision,
                value=value,
            ),
            operation,
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
        tag: str | None = None,
        direction: int = 0,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            order = self._order(state, identity)
            issuer, actor, (forbidden, self_tag) = self._source(c, state, viewer, order)
            self._guard(c, order.channel)
            if (
                state.revision != revision
                or type(heat) is not int
                or heat < 0
                or len(account) > 1200
                or order.stage != "tag"
                and (tag or direction)
            ):
                raise WorkflowError("Reopen your exact original Order and available resources.")
            event = str(uuid4())
            role = find(state, actor.ref)
            assert role is not None
            update: dict[str, Any]
            if order.stage == "respond":
                if choice == "follow" and not heat and account.strip():
                    if order.isolation is not None and (
                        actor.cell != issuer.cell
                        or bool(actor.inside_frame) != bool(issuer.inside_frame)
                        or (
                            actor.inside_frame
                            and actor.occupied_frame_instance != issuer.occupied_frame_instance
                        )
                    ):
                        raise WorkflowError("Use physical movement to come to the Handler's side.")
                    if order.address is not None:
                        address = order.address
                        state.facts = [
                            x
                            for x in state.facts
                            if not (
                                x.get("kind") == ADDRESS
                                and x.get("wife") == actor.ref.token
                                and x.get("subject") == address.subject.token
                            )
                        ]
                        state.facts.append(
                            dict(
                                kind=ADDRESS,
                                wife=actor.ref.token,
                                subject=address.subject.token,
                                label=address.label,
                                pronouns=address.pronouns,
                                event=event,
                                order=order.id,
                            )
                        )
                    update = dict(
                        stage="closed", consequence="chosen_follow", account=account.strip()
                    )
                elif choice == "disobey" and not forbidden and not account and not order.faces:
                    from girlframe.services.m3_ancillary_intimacy import (
                        SOLDIER,
                        WARBOY,
                        good_soldier_tag,
                        warboy_refusal,
                    )

                    soldier = (
                        good_soldier_tag(state, actor.ref)
                        if _available(self.game, SOLDIER)
                        else None
                    )
                    warboy = (
                        warboy_refusal(state, actor.ref, issuer.ref)
                        if _available(self.game, WARBOY)
                        else None
                    )
                    state = commit(
                        state,
                        actor.ref,
                        profiles(c, self.store.campaign_id),
                        Commitment(heat=heat),
                        actor.source_sha256,
                    ).state
                    faces = self.game.dice.roll()
                    if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                        raise ValueError("Dice source returned invalid faces.")
                    update = dict(
                        stage="tag",
                        faces=faces,
                        heat=heat,
                        base_modifier=-1 if soldier is not None else 0,
                        good_soldier=soldier,
                        warboy_low=warboy,
                        roll_event=event,
                        rng_source=self.game.rng_source,
                    )
                else:
                    raise WorkflowError("Choose an actual allowed original response to this Order.")
            elif order.stage == "tag" and order.faces is not None and not heat:
                if choice == "pass" and tag is None and not direction and not account:
                    modifier = 0
                elif (
                    choice == "mark"
                    and self_tag
                    and tag in self._tags(state, order)
                    and type(direction) is int
                    and direction in (-1, 1)
                    and account.strip()
                ):
                    assert tag is not None
                    plays.mark(state, actor.ref, tag, order.scene)
                    modifier = direction
                else:
                    raise WorkflowError("Pass or use one eligible original own Tag.")
                total = sum(order.faces) + order.heat + order.base_modifier + modifier
                if order.warboy_low is not None:
                    total = min(total, 7)
                update = dict(
                    stage="review" if tier(total) == "low" else "outcome",
                    tag=tag,
                    modifier=modifier,
                    total=total,
                    consequence="cannot_disobey" if tier(total) == "low" else None,
                    account=account.strip() or None,
                )
            elif order.stage == "outcome" and order.total is not None and choice == "act":
                level = tier(order.total)
                if level == "mid" and heat in (1, 2) and 0 < len(account.strip()) <= 120:
                    plays.add_tag(state, actor.ref, account, (actor.controller,))
                elif level != "high" or heat != 2 or not account.strip():
                    raise WorkflowError("Choose the original printed result and permitted Heat.")
                role = find(state, actor.ref)
                assert role is not None
                from girlframe.engine.m3_ancillary import put
                from girlframe.engine.m3_leviathan_obsession import allowed_gain

                put(
                    state,
                    role.model_copy(
                        update=dict(
                            heat=role.heat
                            + allowed_gain(state, actor.ref, heat, "Disobey Orders", event),
                        )
                    ),
                )
                update = dict(stage="review", consequence="owned_refusal", account=account.strip())
            elif (
                order.stage == "review"
                and choice in ("unheard", "hold")
                and not heat
                and account.strip()
            ):
                stage = "closed" if choice == "unheard" else "held"
                if (
                    (order.isolation is not None or order.mercenary is not None)
                    and stage == "closed"
                    and order.total is not None
                ):
                    if tier(order.total) == "low":
                        stage = "respond"
                update = dict(stage=stage)
                state.facts.append(
                    dict(
                        kind="ancillary_order_notice",
                        order=order.id,
                        event=event,
                        account=account.strip(),
                    )
                )
            else:
                raise WorkflowError("Recover the actual pending original Order consequence.")
            return self._save(c, state, viewer, key, order.model_copy(update=update), event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                choice=choice,
                heat=heat,
                tag=tag,
                direction=direction,
                account=account,
            ),
            operation,
        )
