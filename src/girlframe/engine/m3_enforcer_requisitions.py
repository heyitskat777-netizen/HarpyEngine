"""Actual acquired Enforcer rules retain original people, Frame and paid sources."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import change, depth
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.playbooks import canonical_frame
from girlframe.engine.rules_registry import Registry

MASTER = "frame.enforcer.masters-dog"
PAVLOV = "frame.enforcer.pavlovs-soldier"
FIREPOWER = "frame.enforcer.overwhelming-firepower"
VIRUS = "frame.enforcer.compliance-virus"
SNOOP = "frame.enforcer.snoop"
RULES = (MASTER, PAVLOV, FIREPOWER, VIRUS, SNOOP)
OBEDIENCE = "frame.enforcer.obedience-conditioning"
INITIATIVE = "frame.enforcer.enforcement-initiative"
PERMISSION = "frame.enforcer.permission-trigger"
BASE = (OBEDIENCE, INITIATIVE, PERMISSION)
TITLES = {
    MASTER: "Master's Dog",
    PAVLOV: "Pavlov's Soldier",
    FIREPOWER: "Overwhelming Firepower",
    VIRUS: "Compliance Virus",
    SNOOP: "Snoop",
    OBEDIENCE: "Obedience Conditioning",
    INITIATIVE: "Enforcement Initiative",
    PERMISSION: "Enforcer Permission Trigger",
}
Kind = Literal["ability_unlock", "frame_grafting"]


class Grant(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    purchase: str | None = Field(default=None, min_length=1)
    source_event: str = Field(min_length=1)
    counterpart: ActorRef | None = None
    source_kind: Literal["paid", "replacement", "frame_swap"] = "paid"
    source_work: str | None = None


def grants(state: GameState) -> tuple[Grant, ...]:
    values = tuple(
        Grant.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "enforcer_rule_acquired"
    )
    if len({x.id for x in values}) != len(values):
        raise ValueError("Recover the unique actual Enforcer acquisition sources")
    return values


def frame(state: GameState, actor: ActorRef) -> str | None:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation or sheet.frame_scrapped:
            return None
        return (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)
        )
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        body = harpy(state, actor)
        return body.frame_instance
    return None


def binding(state: GameState, grant: Grant) -> tuple[ActorRef, str, tuple[str, ...]]:
    from girlframe.engine.m3_frame_swap_state import SwapReceipt

    recipient, assigned = grant.actor, grant.frame
    receipts = [grant.purchase] if grant.purchase else []
    for fact in state.facts:
        if fact.get("kind") != "enforcer_rule_retained" or fact.get("grant") != grant.id:
            continue
        receipt = next((x for x in state.requisitions if x.id == fact.get("requisition")), None)
        if (
            not isinstance(receipt, SwapReceipt)
            or receipt.actor != recipient
            or receipt.old_frame != assigned
            or receipt.new_frame != fact.get("frame")
            or receipt.selection.retained_rule != grant.rule
            or receipt.source_event != fact.get("source_event")
            or fact.get("old_frame") != assigned
            or ActorRef.model_validate_json(fact["actor"]) != recipient
        ):
            raise ValueError("Recover the actual paid rule retention receipt chain")
        assigned = receipt.new_frame
        receipts.append(receipt.id)
    return recipient, assigned, tuple(receipts)


def held(state: GameState, actor: ActorRef, rule: str) -> Grant | None:
    from girlframe.engine.m3_privileges import suspended

    current = frame(state, actor)
    result = []
    for grant in grants(state):
        recipient, assigned, receipts = binding(state, grant)
        if actor.kind == "external_pilot":
            body = next((x for x in state.harpy_states if x.id == actor.entity and x.alive), None)
            if (
                body is not None
                and body.origin == recipient
                and body.frame_instance == assigned
                and grant.rule in body.plays
            ):
                from girlframe.engine.m3_tag_permissions import conversion

                conversion(state, actor)
                recipient = actor
        if recipient == actor and assigned == current and grant.rule == rule:
            if any(suspended(state, x) for x in receipts):
                continue
            if grant.source_kind == "replacement":
                sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
                if grant.purchase is not None or not grant.source_work:
                    raise ValueError("A free actual package is not a paid Requisition receipt")
                if (
                    actor.kind == "pilot"
                    and assigned == grant.frame
                    and (
                        sheet is None
                        or sheet.frame_runtime is None
                        or sheet.frame_runtime.source_work != grant.source_work
                        or rule not in sheet.frame_runtime.acquired_rules
                    )
                ):
                    raise ValueError("Recover the actual current replacement package rule")
                result.append(grant)
                continue
            if grant.source_kind == "frame_swap":
                from girlframe.engine.m3_frame_swap_state import SwapReceipt

                receipt = next((x for x in state.requisitions if x.id == grant.purchase), None)
                if (
                    not isinstance(receipt, SwapReceipt)
                    or receipt.actor != grant.actor
                    or receipt.new_frame != grant.frame
                    or receipt.selection.retained_rule != grant.rule
                    or receipt.source_event != grant.source_event
                ):
                    raise ValueError("Recover the original actually paid Frame rule retention")
                result.append(grant)
                continue
            receipt = next((x for x in state.requisitions if x.id == grant.purchase), None)
            if (
                not isinstance(receipt, FrameRuleReceipt)
                or receipt.grant != grant.id
                or receipt.rule_id != rule
                or receipt.actor != grant.actor
                or receipt.source_event != grant.source_event
            ):
                raise ValueError("Recover the original paid Enforcer rule receipt")
            if not suspended(state, receipt.id):
                result.append(grant)
    if len(result) > 1:
        raise ValueError("Do not stack duplicate actual Enforcer rule entitlements")
    return result[0] if result else None


def replacement_grants(
    original: GameState, actor: ActorRef, source_work: str, source_event: str, registry: Registry
) -> GameState:
    """Initialize only explicitly supplied reviewed rules, once, at actual free replacement."""
    from uuid import NAMESPACE_URL, uuid5

    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame_runtime is None
        or sheet.frame_runtime.source_work != source_work
        or not source_event
    ):
        raise ValueError("Use the actual original owner's applied compulsory replacement package")
    runtime = sheet.frame_runtime
    for rule in runtime.acquired_rules:
        if rule not in (*RULES, *BASE):
            continue
        registry.require_available(rule)
        identity = str(
            uuid5(NAMESPACE_URL, "girlframe:replacement-enforcer:" + source_work + ":" + rule)
        )
        if any(x.id == identity for x in grants(state)):
            raise ValueError("This actual replacement package rule already has its initial effect")
        handler = active_handler(state) if rule == MASTER else None
        if rule == MASTER and handler is None:
            raise ValueError("Master's Dog needs its actual fictional Handler at acquisition")
        grant = Grant(
            id=identity,
            actor=actor,
            frame=runtime.id,
            rule=rule,
            source_event=source_event,
            counterpart=handler,
            source_kind="replacement",
            source_work=source_work,
        )
        if handler is not None:
            state = change(state, actor, handler, 1, source_event)
        state.facts.append(dict(kind="enforcer_rule_acquired", body=grant.model_dump_json()))
    return state


def owned_plays(state: GameState, actor: ActorRef, registry: Registry) -> list[dict[str, str]]:
    """Only actually held acquired rules, plus actual native Enforcer base rules."""
    result: list[dict[str, str]] = []
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is not None
        and sheet.character_id == actor.incarnation
        and canonical_frame(sheet.frame) == "THE ENFORCER"
    ):
        result.extend(
            dict(id=x.id, name=x.title)
            for x in registry.entries
            if x.frame_playbook == "THE ENFORCER" and x.frame_rule == "base"
        )
    result.extend(
        dict(id=rule, name=TITLES[rule]) for rule in (*RULES, *BASE) if held(state, actor, rule)
    )
    from girlframe.engine.m3_personal_firearm import RULE as FIREARM
    from girlframe.engine.m3_personal_firearm import held as firearms

    assigned = frame(state, actor)
    if assigned and firearms(state, actor, assigned):
        result.append(dict(id=FIREARM, name="Personal Firearm"))
    return list({x["id"]: x for x in result}.values())


def room(state: GameState, actor: ActorRef) -> ActorRef | None:
    from girlframe.engine.m3_handler_consequences import body_original, same_handler_body

    grant = held(state, actor, MASTER)
    if (
        grant is not None
        and grant.counterpart is not None
        and same_handler_body(state, grant.counterpart)
    ):
        counterpart = body_original(state, grant.counterpart).actor
        if active_handler(state) == counterpart and depth(state, actor, counterpart) == 2:
            return counterpart
    return None


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    registry: Registry,
    kind: Kind,
    rule: str,
    account: str,
    identity: str,
    grant_id: str,
    event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, actor, bindings)
    entry = registry.require_available(rule)
    if (
        rule not in (*RULES, *BASE)
        or entry.frame_rule
        not in (("requisition",) if kind == "ability_unlock" else ("base", "requisition"))
        or entry.frame_playbook != "THE ENFORCER"
        or entry.scope != "frame"
        or actual.ref.kind != "pilot"
        or actual.rules != "girl_frame"
        or actual.frame_instance is None
        or actual.frame_scrapped
        or actual.source_sha256 != expected
        or not account.strip()
        or kind not in ("ability_unlock", "frame_grafting")
    ):
        raise ValueError("Acquire an actual reviewed Enforcer Requisition on this original Frame")
    own = canonical_frame(actual.frame or "") == "THE ENFORCER"
    if (kind == "ability_unlock") != own:
        raise ValueError("Unlock uses your own Frame; Grafting uses another donor Frame")
    if held(state, actor, rule) or any(
        x.actor == actor and x.frame == actual.frame_instance and x.rule == rule
        for x in grants(state)
    ):
        raise ValueError("Restore an existing entitlement; do not buy a duplicate acquired rule")
    if any(x.id == identity or x.source_event == event for x in state.requisitions):
        raise ValueError("This actual paid acquisition was already recorded")
    price: Literal[2, 3] = 2 if kind == "ability_unlock" else 3
    sheet = state.sheets[actor.entity]
    if sheet.permissions < price:
        raise ValueError("This acquisition needs its actual available Permissions")
    counterpart = active_handler(state) if rule == MASTER else None
    if rule == MASTER and counterpart is None:
        raise ValueError("Master's Dog requires the actual fictional Handler, not a staff account")
    sheet.permissions -= price
    sheet.revision += 1
    if sheet.frame_runtime is not None:
        sheet.frame_runtime = sheet.frame_runtime.model_copy(
            update={
                "acquired_rules": tuple(dict.fromkeys((*sheet.frame_runtime.acquired_rules, rule)))
            }
        )
    grant = Grant(
        id=grant_id,
        actor=actor,
        frame=actual.frame_instance,
        rule=rule,
        purchase=identity,
        source_event=event,
        counterpart=counterpart,
    )
    state.facts.append(dict(kind="enforcer_rule_acquired", body=grant.model_dump_json()))
    state.requisitions.append(
        FrameRuleReceipt(
            id=identity,
            kind=kind,
            actor=actor,
            frame_instance=actual.frame_instance,
            frame=actual.frame or "",
            donor_frame="THE ENFORCER",
            rule_id=rule,
            grant=grant_id,
            price=price,
            account=account,
            source_event=event,
        )
    )
    if counterpart is not None:
        state = change(state, actor, counterpart, 1, event)
    return state
