"""Temporary removal keeps the original purchased resource and character attached."""

from girlframe.engine.m2 import AssetState, GameState, Obligation
from girlframe.engine.m3_core import install
from girlframe.engine.m3_requisition_state import Requisition

KIND = "revoked_requisition"


def suspended(state: GameState, purchase: str) -> bool:
    return any(
        x.kind == KIND and x.state == "pending" and x.details.get("purchase") == purchase
        for x in state.obligations
    )


def available(state: GameState, subject: int, character: str) -> list[Requisition]:
    sheet = state.sheets[str(subject)]
    frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + character
    return [
        x
        for x in state.requisitions
        if x.actor.entity == str(subject)
        and x.actor.incarnation == character
        and not suspended(state, x.id)
        and (
            (
                x.kind == "asset_installment"
                and x.frame_instance == frame
                and any(
                    a.id == x.asset_id and a.family == "frame" and a.intrinsic is None
                    for a in sheet.assets
                )
            )
            or (
                x.kind == "creature_comforts"
                and not any(
                    fact.get("kind") == "creature_comforts_asset" and fact.get("purchase") == x.id
                    for fact in state.facts
                )
                and not any(
                    fact.get("kind") == "comforts_declined" and fact.get("purchase") == x.id
                    for fact in state.facts
                )
            )
        )
    ]


def revoke(
    original: GameState,
    subject: int,
    inflictor: int,
    purchase: str | None,
    condition: str,
    identity: str,
    source: str,
    characters: dict[int, str],
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    character = characters.get(subject)
    if not character or not source or not condition.strip() or not identity:
        raise ValueError(
            "Record the original character, source and temporary restoration condition"
        )
    receipt = next((x for x in available(state, subject, character) if x.id == purchase), None)
    if receipt is None:
        raise ValueError(
            "Choose an actual currently held Requisition, not an already spent benefit"
        )
    if any(x.id == identity for x in state.obligations):
        raise ValueError("This revocation source already exists")
    details = {
        "purchase": receipt.id,
        "character": character,
        "source_event": source,
        "condition": condition.strip(),
        "kind": receipt.kind,
        "inflictor_character": characters.get(inflictor, "handler"),
        "restoration_allowed": "false",
    }
    sheet = state.sheets[str(subject)]
    if receipt.kind == "asset_installment":
        asset = next(x for x in sheet.assets if x.id == receipt.asset_id)
        details.update(
            asset=asset.model_dump_json(), frame=receipt.frame_instance, label=asset.name
        )
        sheet.assets.remove(asset)
    else:
        details["label"] = "Creature Comforts"
    state.obligations.append(
        Obligation(
            id=identity,
            kind=KIND,
            owner=inflictor,
            target=subject,
            action="revoked_privileges",
            details=details,
        )
    )
    return state


def restore(original: GameState, identity: str, character: str, replace: str | None) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    gate = next((x for x in state.obligations if x.id == identity and x.kind == KIND), None)
    if (
        gate is None
        or gate.state != "pending"
        or gate.details["character"] != character
        or gate.details["restoration_allowed"] != "true"
        or gate.target is None
    ):
        raise ValueError("The original inflictor must first confirm the restoration condition")
    sheet = state.sheets[str(gate.target)]
    if gate.details["kind"] == "asset_installment":
        frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + character
        if frame != gate.details["frame"] or sheet.frame_scrapped:
            raise ValueError("Recover the original Frame before restoring its suspended Asset")
        asset = AssetState.model_validate_json(gate.details["asset"])
        state.sheets[str(gate.target)] = install(sheet, asset, replace=replace).sheet
    elif replace is not None:
        raise ValueError("This restoration does not replace an Asset")
    gate.state = "fulfilled"
    return state
