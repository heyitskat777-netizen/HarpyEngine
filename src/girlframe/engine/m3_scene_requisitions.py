"""Paid Privacy and Visiting Home keep actual scenes, roles and human decisions."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import SceneReceipt

Kind = Literal["privacy", "visiting_home"]
PRICES: dict[Kind, int] = {"privacy": 1, "visiting_home": 2}


def supervisor_eligible(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "handler":
        return str(state.handler) == actor.entity
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        return bool(
            sheet and int(actor.entity) in state.order and sheet.character_id == actor.incarnation
        )
    if state.world and actor.kind == "npc":
        npc = next((x for x in state.world.npcs if x.id == actor.entity and x.alive), None)
        return bool(
            npc
            and (
                npc.employment == "foundation"
                or any(x.id == npc.faction and x.kind == "foundation" for x in state.world.factions)
            )
        )
    if state.world and actor.kind == "external_pilot":
        pilot = next((x for x in state.world.pilots if x.id == actor.entity and x.alive), None)
        return bool(pilot and pilot.kind == "foundation")
    return False


class Scene(Model):
    id: str = Field(min_length=1)
    channel: int = Field(gt=0)
    cast_revision: int = Field(ge=1)
    roles: tuple[CastRole, ...] = Field(min_length=2)
    account: str = Field(min_length=1, max_length=1200)
    supervisor: ActorRef | None = None
    home: str = Field(default="", max_length=1200)
    present: tuple[int, ...] = ()
    entered_event: str | None = None
    physical_origin: str | None = None
    closed_by: int | None = Field(default=None, gt=0)
    career_end: str | None = None
    ended_actor: ActorRef | None = None
    close_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def owned_attendance(self) -> "Scene":
        humans = {x.controller for x in self.roles}
        if (
            len({x.actor for x in self.roles}) != len(self.roles)
            or not self.account.strip()
            or len(set(self.present)) != len(self.present)
            or not set(self.present) <= humans
            or (self.closed_by is not None and self.closed_by not in humans)
            or (
                (self.closed_by is not None or self.career_end is not None)
                != bool(self.close_account.strip())
            )
            or (self.career_end is None) != (self.ended_actor is None)
            or (
                self.ended_actor is not None
                and self.ended_actor not in {x.actor for x in self.roles}
            )
        ):
            raise ValueError(
                "An actual scene retains distinct roles and each human's own decisions"
            )
        return self


class Benefit(Model):
    purchase: str = Field(min_length=1)
    kind: Kind
    actor: ActorRef
    companion: ActorRef | None = None
    period: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    qualification_event: str = Field(min_length=1)
    action: str | None = None
    total: int | None = None
    scene: Scene | None = None
    declined: bool = False
    decline_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def source_specific(self) -> "Benefit":
        if self.actor.kind != "pilot":
            raise ValueError("Only the original Girl can receive this scene benefit")
        if self.kind == "privacy":
            if (
                self.companion is None
                or self.companion.kind != "pilot"
                or self.companion == self.actor
            ):
                raise ValueError("Privacy retains its original other Girl")
            if self.action is not None or self.total is not None:
                raise ValueError("Privacy is a next-period benefit, not an eight-plus roll reward")
            if self.scene and (
                {x.actor for x in self.scene.roles} != {self.actor, self.companion}
                or self.scene.supervisor is not None
                or self.scene.home
            ):
                raise ValueError("Privacy has exactly the two original Girls, without an observer")
        else:
            if (
                self.companion is not None
                or not self.action
                or self.total is None
                or self.total < 8
            ):
                raise ValueError("Visiting Home needs its actual eight-plus ordinary Off-Duty roll")
            if self.scene and (
                not self.scene.home.strip()
                or self.scene.supervisor is None
                or self.scene.supervisor == self.actor
                or self.scene.supervisor not in {x.actor for x in self.scene.roles}
            ):
                raise ValueError("The actual visit needs its pre-Piloting home and supervisor")
        if self.declined and (self.scene is not None or not self.decline_account.strip()):
            raise ValueError("Explicitly decline the optional scene before setting it")
        return self


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    kind: Kind,
    companion: ActorRef | None,
    account: str,
    identity: str,
    event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    owner = resolve(state, actor, bindings)
    if owner.ref.kind != "pilot" or owner.rules != "girl_frame" or owner.source_sha256 != expected:
        raise ValueError("STALE_REQUISITION: confirm your actual Girl and available Permissions")
    if any(x.id == identity or x.source_event == event for x in state.requisitions):
        raise ValueError("This paid Requisition source is already recorded")
    if companion is not None:
        other = resolve(state, companion, bindings, require_current_profile=False)
        if other.rules != "girl_frame" or other.ref.kind != "pilot":
            raise ValueError("Privacy names another actual Girl")
    receipt = SceneReceipt(
        id=identity,
        kind=kind,
        actor=actor,
        companion=companion,
        price=1 if kind == "privacy" else 2,
        account=account,
        source_event=event,
    )
    sheet = state.sheets[actor.entity]
    if sheet.permissions < receipt.price:
        raise ValueError(
            "This Requisition needs its printed or campaign-priced available Permissions"
        )
    sheet.permissions -= receipt.price
    sheet.revision += 1
    state.requisitions.append(receipt)
    return state


def propose(
    benefit: Benefit,
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    cast: SceneCast,
    account: str,
    human: int,
    *,
    supervisor: ActorRef | None = None,
    home: str = "",
) -> Benefit:
    if (
        str(human) != benefit.actor.entity
        or benefit.scene is not None
        or benefit.declined
        or suspended(state, benefit.purchase)
    ):
        raise ValueError("Only the original purchaser can set this unspent active scene")
    resolve(state, benefit.actor, bindings, require_current_profile=False)
    if benefit.kind == "privacy":
        if {x.actor for x in cast.roles} != {benefit.actor, benefit.companion}:
            raise ValueError("Privacy requires exactly the two original Girls; no third role")
    elif (
        supervisor is None
        or not any(x.actor == supervisor for x in cast.roles)
        or not supervisor_eligible(state, supervisor)
    ):
        raise ValueError("Choose the actual supervisor explicitly present in this cast")
    for role in cast.roles:
        actor = resolve(state, role.actor, bindings, require_current_profile=False)
        if not actor.alive or actor.controller != role.controller:
            raise ValueError("Use the actual current living cast and its current human controllers")
    if not cast.open or not any(x.actor == benefit.actor for x in cast.roles):
        raise ValueError("The original Girl must actually be in the open scene")
    scene = Scene(
        id=cast.id,
        channel=cast.channel,
        cast_revision=cast.revision,
        roles=cast.roles,
        account=account,
        supervisor=supervisor,
        home=home,
        present=(human,),
    )
    return Benefit.model_validate_json(
        benefit.model_copy(update={"scene": scene}).model_dump_json()
    )


def active(benefit: Benefit) -> bool:
    scene = benefit.scene
    return bool(
        scene
        and scene.entered_event
        and scene.closed_by is None
        and scene.career_end is None
        and not benefit.declined
        and set(scene.present) == {x.controller for x in scene.roles}
    )


def enter(benefit: Benefit, human: int, event: str, origin: str | None = None) -> Benefit:
    scene = benefit.scene
    if (
        scene is None
        or scene.entered_event is not None
        or scene.closed_by is not None
        or scene.career_end is not None
        or human != int(benefit.actor.entity)
        or set(scene.present) != {x.controller for x in scene.roles}
        or not event
    ):
        raise ValueError("The original Girl enters only after each actual human's owned agreement")
    if (benefit.kind == "visiting_home") != (origin is not None):
        raise ValueError("A real supervised visit retains its original physical placement")
    updated = scene.model_copy(update={"entered_event": event, "physical_origin": origin})
    return Benefit.model_validate_json(
        benefit.model_copy(update={"scene": updated}).model_dump_json()
    )


def attest(benefit: Benefit, human: int) -> Benefit:
    scene = benefit.scene
    if (
        scene is None
        or scene.closed_by is not None
        or scene.career_end is not None
        or human in scene.present
        or human not in {x.controller for x in scene.roles}
    ):
        raise ValueError("Each actual human confirms only their own participation or supervision")
    updated = scene.model_copy(update={"present": (*scene.present, human)})
    return Benefit.model_validate_json(
        benefit.model_copy(update={"scene": updated}).model_dump_json()
    )


def close(benefit: Benefit, human: int, account: str) -> Benefit:
    scene = benefit.scene
    if (
        scene is None
        or scene.closed_by is not None
        or scene.career_end is not None
        or human not in {x.controller for x in scene.roles}
        or not account.strip()
    ):
        raise ValueError("An actual participant explicitly ends their own scene participation")
    if benefit.kind == "visiting_home" and human != int(benefit.actor.entity):
        raise ValueError("The visiting Girl closes her actual visit after supervision is recorded")
    if benefit.kind == "visiting_home" and not active(benefit):
        raise ValueError("Complete actual owned supervision before finishing the visit")
    updated = scene.model_copy(update={"closed_by": human, "close_account": account.strip()})
    return Benefit.model_validate_json(
        benefit.model_copy(update={"scene": updated}).model_dump_json()
    )


def decline(benefit: Benefit, human: int, account: str) -> Benefit:
    if (
        str(human) != benefit.actor.entity
        or benefit.scene is not None
        or benefit.declined
        or not account.strip()
    ):
        raise ValueError("The original buyer may explicitly decline the unused optional scene")
    return Benefit.model_validate_json(
        benefit.model_copy(
            update={
                "declined": True,
                "decline_account": account.strip(),
            }
        ).model_dump_json()
    )


def reset(benefit: Benefit, human: int) -> Benefit:
    if (
        benefit.scene is None
        or benefit.scene.entered_event is not None
        or benefit.scene.career_end is not None
        or benefit.scene.closed_by is not None
        or str(human) != benefit.actor.entity
    ):
        raise ValueError(
            "Only the purchaser may revise an unentered scene and clear its agreements"
        )
    return Benefit.model_validate_json(benefit.model_copy(update={"scene": None}).model_dump_json())
