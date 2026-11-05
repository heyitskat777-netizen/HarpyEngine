"""Printed Put Someone Beneath You choices over actual original Pilot resources."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, Obligation, TagState, higher, pair_key, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import damage

BASE = ("tag", "status", "bond")
EXTRA = ("lock_tag", "pin", "punish")
PLAY = "put_someone_beneath_you"


class Decision(Model):
    options: tuple[str, ...]
    text: str = Field(min_length=1, max_length=1200)
    tag: str = Field(default="", max_length=120)
    locked_tag: str | None = None
    bond: ActorRef | None = None
    asset: str | None = None


class Authority(Model):
    order_id: str = Field(min_length=1)
    issuer: int = Field(gt=0)
    recipient: ActorRef


class Followup(Model):
    kind: Literal["pin_response", "punishment", "defeat"]
    owner: ActorRef
    target: ActorRef


class Outcome(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def rejection_blocked(state: GameState, owner: int, tag: str) -> bool:
    sheet = state.sheets.get(str(owner))
    return bool(
        sheet
        and any(
            x.kind == "tag_rejection_permission"
            and x.state == "pending"
            and x.target == owner
            and x.details.get("tag") == tag
            and (
                sheet.character_id is None
                or x.details.get("target_character") == sheet.character_id
            )
            for x in state.obligations
        )
    )


def choices(level: str, selected: tuple[str, ...]) -> None:
    if len(set(selected)) != len(selected):
        raise ValueError("Choose distinct printed options")
    base, extra = set(selected) & set(BASE), set(selected) & set(EXTRA)
    valid = (
        level == "mid"
        and len(selected) == 2
        and len(base) == 2
        or level == "high"
        and len(selected) == 2
        and len(base) == len(extra) == 1
        or level == "low"
        and len(selected) == 1
        and selected[0] in (*BASE, *EXTRA, "damage")
    )
    if not valid:
        raise ValueError(
            "Choose two base options at 8–10, one base then one extra at 11+, or one counter at 7−"
        )


def apply(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    target: ActorRef,
    level: str,
    decision: Decision,
    action: str,
    choice: str,
    participants: tuple[int, ...],
    *,
    authority: Authority | None = None,
    actor_piloting: bool = False,
) -> Outcome:
    state = GameState.model_validate_json(original.model_dump_json())
    decision = Decision.model_validate_json(decision.model_dump_json())
    choices(level, decision.options)
    if not action or not choice or not decision.text.strip() or actor == target:
        raise ValueError("Record the actual distinct characters, source decision and action")
    if type(actor_piloting) is not bool:
        raise ValueError("Record the actual acting Girl's Frame context")
    if any(
        x.get("kind") == "beneath_choice"
        and x.get("action") == action
        and x.get("choice") == choice
        for x in state.facts
    ):
        raise ValueError("This actual source choice has already been applied")
    for ref in (actor, target):
        actual = resolve(state, ref, bindings, require_current_profile=False)
        if (
            ref.kind != "pilot"
            or actual.rules != "girl_frame"
            or actual.controller not in participants
        ):
            raise ValueError("Use actual original Pilot roles participating in this scene")
    setter, victim = (target, actor) if level == "low" else (actor, target)
    owner, subject = int(setter.entity), int(victim.entity)
    options = set(decision.options)
    if (
        bool(decision.tag.strip()) != ("tag" in options)
        or (decision.bond is not None) != ("bond" in options)
        or (decision.locked_tag is not None) != ("lock_tag" in options)
        or (decision.asset is not None) != ("damage" in options)
    ):
        raise ValueError("Supply only the actual details required by these chosen effects")
    sheet = state.sheets[victim.entity]
    followups: list[Followup] = []
    # High results explicitly perform the base choice before the extra choice.
    new_tag = None
    if "tag" in options:
        new_tag = action + ":tag:" + choice
        if any(x.id == new_tag for x in sheet.tags):
            raise ValueError("This source Tag was already applied")
        sheet.tags.append(
            TagState(id=new_tag, label=decision.tag.strip(), giver=owner, observers=participants)
        )
    if "status" in options:
        shift_status(state, subject, -1)
    if "bond" in options:
        peer = decision.bond
        assert peer is not None
        if peer == victim:
            raise ValueError("Choose an actual Bond to another character")
        actual_peer = resolve(
            state, peer, bindings, require_alive=False, require_current_profile=False
        )
        if peer.kind in ("pilot", "handler"):
            key = pair_key(subject, actual_peer.controller)
            depth = state.bonds.get(key, 0)
            if depth < 1:
                raise ValueError("Choose an existing actual Bond belonging to the affected Girl")
            if depth == 1:
                del state.bonds[key]
            else:
                state.bonds[key] = depth - 1
        elif peer.kind == "npc" and state.world:
            npc = next(x for x in state.world.npcs if x.id == peer.entity)
            key = "pilot:" + victim.entity
            depth = npc.bonds.get(key, 0)
            if depth < 1:
                raise ValueError("Choose an existing linked NPC Bond")
            bonds = dict(npc.bonds)
            if depth == 1:
                del bonds[key]
            else:
                bonds[key] = 1
            state.world = state.world.model_copy(
                update={
                    "npcs": tuple(
                        x.model_copy(update={"bonds": bonds}) if x.id == npc.id else x
                        for x in state.world.npcs
                    )
                }
            )
        else:
            raise ValueError("UNSUPPORTED_RULE: this actual Bond port is not implemented")
    if "lock_tag" in options:
        identity = new_tag if decision.locked_tag == "new" else decision.locked_tag
        tag = next((x for x in sheet.tags if x.id == identity), None)
        if tag is None or (owner not in tag.observers and owner != subject):
            raise ValueError("Choose a Tag actually known to this decision owner")
        state.obligations.append(
            Obligation(
                id=action + ":consent:" + choice,
                kind="tag_rejection_permission",
                owner=owner,
                target=subject,
                action=action,
                details={
                    "tag": tag.id,
                    "label": tag.label,
                    "owner_character": str(setter.incarnation),
                    "target_character": str(victim.incarnation),
                    "source_choice": choice,
                },
            )
        )
    if "pin" in options:
        state.facts.append(
            {
                "kind": "physical_pin",
                "action": action,
                "owner": setter.entity,
                "owner_character": str(setter.incarnation),
                "target": victim.entity,
                "target_character": str(victim.incarnation),
                "text": decision.text,
            }
        )
        followups.append(Followup(kind="pin_response", owner=victim, target=setter))
    if "punish" in options:
        permitted = higher(state, owner, subject)
        if authority is not None:
            permitted = permitted or (
                authority.recipient == setter and higher(state, authority.issuer, subject)
            )
        if not permitted:
            raise ValueError(
                "Punishment requires higher Status or an actual order from the victim's superior"
            )
        followups.append(Followup(kind="punishment", owner=setter, target=victim))
    elif authority is not None:
        raise ValueError("An order authority applies only to the selected Punishment")
    if "damage" in options:
        assert decision.asset is not None
        damaged = damage(sheet, decision.asset, piloting=actor_piloting)
        sheet = damaged.sheet
        for consequence in damaged.followups:
            if consequence.kind == "helpless":
                sheet.helpless_against = tuple(sorted(set(sheet.helpless_against) | {owner}))
            elif consequence.kind == "defeat":
                followups.append(Followup(kind="defeat", owner=victim, target=setter))
    sheet.revision += 1
    state.sheets[victim.entity] = sheet
    state.facts.append(
        {
            "kind": "beneath_choice",
            "action": action,
            "choice": choice,
            "owner": setter.entity,
            "owner_character": str(setter.incarnation),
            "target": victim.entity,
            "target_character": str(victim.incarnation),
            "options": ",".join(decision.options),
            "text": decision.text,
        }
    )
    return Outcome(state=state, followups=tuple(followups))
