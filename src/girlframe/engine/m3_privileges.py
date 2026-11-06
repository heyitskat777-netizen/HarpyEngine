"""Temporary removal keeps the original purchased resource and character attached."""

from girlframe.engine.m2 import AssetState, GameState, Obligation
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_core import install
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_requisition_state import FrameRuleReceipt, Requisition, SceneReceipt

KIND = "revoked_requisition"


def native_class_receipt(state: GameState, receipt: FrameRuleReceipt) -> bool:
    from girlframe.engine.frame_classes import frame_class

    parts = receipt.rule_id.split(".")
    sheet = state.sheets.get(receipt.actor.entity)
    if (
        receipt.actor.kind != "pilot"
        or receipt.kind != "ability_unlock"
        or len(parts) != 4
        or parts[:2] != ["frame", "class"]
        or not parts[3]
        or sheet is None
        or sheet.character_id != receipt.actor.incarnation
        or sheet.frame_scrapped
        or receipt.donor_frame != sheet.frame
        or receipt.frame != sheet.frame
        or receipt.frame_instance
        != (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id))
    ):
        return False
    try:
        return frame_class(sheet.frame) == parts[2]
    except KeyError:
        return False


def suspended(state: GameState, purchase: str) -> bool:
    return any(
        x.kind == KIND and x.state == "pending" and x.details.get("purchase") == purchase
        for x in state.obligations
    )


def available(state: GameState, subject: int, character: str) -> list[Requisition]:
    from girlframe.engine.m3_class_grafts import eligible as implemented_class_receipt
    from girlframe.engine.m3_enforcer_requisitions import binding, grants, held
    from girlframe.engine.m3_janus_requisitions import held as janus_held
    from girlframe.engine.m3_nightmare import receipt_eligible as nightmare_receipt
    from girlframe.engine.m3_physiotherapist import receipt_eligible as physiotherapist_receipt

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
            or (
                isinstance(x, SceneReceipt)
                and not any(
                    fact.get("kind") == "scene_requisition_consumed"
                    and fact.get("purchase") == x.id
                    for fact in state.facts
                )
            )
            or (isinstance(x, FrameRuleReceipt) and native_class_receipt(state, x))
            or (isinstance(x, FrameRuleReceipt) and nightmare_receipt(state, x))
            or (isinstance(x, FrameRuleReceipt) and physiotherapist_receipt(state, x))
            or (isinstance(x, FrameRuleReceipt) and implemented_class_receipt(state, x))
            or (
                isinstance(x, FrameRuleReceipt)
                and x.donor_frame == "JANUS"
                and janus_held(state, x.actor, x.rule_id) == x
            )
            or (
                isinstance(x, FrameRuleReceipt)
                and any(
                    grant.purchase == x.id
                    and grant.actor == x.actor
                    and grant.frame_instance == frame
                    for grant in state.personal_firearms
                )
            )
            or (
                isinstance(x, FrameRuleReceipt)
                and any(
                    grant.purchase == x.id
                    and grant.actor == x.actor
                    and binding(state, grant)[1] == frame
                    and grant.rule == x.rule_id
                    and held(state, x.actor, grant.rule) is not None
                    for grant in grants(state)
                )
            )
            or isinstance(x, SwapReceipt)
            and x.new_frame == frame
            and held(state, x.actor, x.selection.retained_rule) is not None
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
    elif (
        isinstance(receipt, FrameRuleReceipt)
        and receipt.rule_id == "frame.class.priestess.nightmare-core"
    ):
        from girlframe.engine.m3_nightmare import receipt_eligible

        if not receipt_eligible(state, receipt):
            raise ValueError("Recover the actual original Nightmare Core source and Frame")
        details.update(
            nightmare_receipt=receipt.model_dump_json(),
            frame=receipt.frame_instance,
            rule_id=receipt.rule_id,
            label="Nightmare Core",
        )
    elif (
        isinstance(receipt, FrameRuleReceipt)
        and receipt.rule_id == "frame.class.priestess.void-physiotherapist"
    ):
        from girlframe.engine.m3_physiotherapist import receipt_eligible

        if not receipt_eligible(state, receipt):
            raise ValueError("Recover the actual original Physiotherapist source and Frame")
        details.update(
            physiotherapist_receipt=receipt.model_dump_json(),
            frame=receipt.frame_instance,
            rule_id=receipt.rule_id,
            label="Void Physiotherapist",
        )
    elif isinstance(receipt, FrameRuleReceipt) and receipt.rule_id in (
        "frame.class.autocrat.untouchable-frame",
        "frame.class.autocrat.martyr",
        "frame.class.legion.dampener-link",
        "frame.class.legion.kicked-puppy",
        "frame.class.legion.modular-build",
    ):
        from girlframe.engine.m3_class_grafts import eligible

        if not eligible(state, receipt):
            raise ValueError("Recover the actual original implemented Class source and Frame")
        details.update(
            implemented_class_receipt=receipt.model_dump_json(),
            frame=receipt.frame_instance,
            rule_id=receipt.rule_id,
            label=receipt.rule_id.rsplit(".", 1)[1].replace("-", " ").title(),
        )
    elif isinstance(receipt, FrameRuleReceipt) and native_class_receipt(state, receipt):
        details.update(
            native_class_receipt=receipt.model_dump_json(),
            frame=receipt.frame_instance,
            rule_id=receipt.rule_id,
            label=receipt.rule_id.rsplit(".", 1)[1].replace("-", " ").title(),
        )
    elif isinstance(receipt, FrameRuleReceipt) and receipt.donor_frame == "JANUS":
        from girlframe.engine.m3_janus_requisitions import TITLES as JANUS_TITLES

        details.update(
            janus_receipt=receipt.model_dump_json(),
            frame=receipt.frame_instance,
            label=JANUS_TITLES[receipt.rule_id],
            rule_id=receipt.rule_id,
        )
    elif isinstance(receipt, (FrameRuleReceipt, SwapReceipt)):
        from girlframe.engine.m3_enforcer_requisitions import TITLES, frame, grants, held

        acquired = (
            held(state, receipt.actor, receipt.selection.retained_rule)
            if isinstance(receipt, SwapReceipt)
            else next((x for x in grants(state) if x.purchase == receipt.id), None)
        )
        if acquired is not None:
            details.update(
                enforcer_grant=acquired.model_dump_json(),
                frame=frame(state, receipt.actor) or "",
                label=TITLES[acquired.rule],
                rule_id=acquired.rule,
            )
        else:
            if not isinstance(receipt, FrameRuleReceipt):
                raise ValueError("This paid exchange has no removable retained rule source")
            grant = next(
                x
                for x in state.personal_firearms
                if x.purchase == receipt.id and x.actor == receipt.actor
            )
            details.update(
                grant=grant.id,
                grant_issues=json_dump_issues(grant),
                frame=grant.frame_instance,
                label="Personal Firearm",
                rule_id=receipt.rule_id,
            )
            pistol = next((x for x in sheet.assets if x.id == grant.issues[-1].asset), None)
            if pistol is not None:
                details["asset"] = pistol.model_dump_json()
                sheet.assets.remove(pistol)
    elif isinstance(receipt, SceneReceipt):
        details["label"] = "Privacy" if receipt.kind == "privacy" else "Visiting Home"
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
    if gate.details["kind"] in (
        "asset_installment",
        "ability_unlock",
        "frame_grafting",
        "frame_swap",
    ):
        frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + character
        if frame != gate.details["frame"] or sheet.frame_scrapped:
            raise ValueError("Recover the original Frame before restoring its suspended Asset")
        if "nightmare_receipt" in gate.details:
            from girlframe.engine.m3_nightmare import receipt_eligible

            source_receipt = FrameRuleReceipt.model_validate_json(gate.details["nightmare_receipt"])
            if source_receipt not in state.requisitions or not receipt_eligible(
                state, source_receipt
            ):
                raise ValueError("Recover the original Nightmare Core receipt and actual Frame")
            if replace is not None:
                raise ValueError(
                    "Nightmare restoration adds no purchase, Asset or acquisition effect"
                )
        elif "physiotherapist_receipt" in gate.details:
            from girlframe.engine.m3_physiotherapist import receipt_eligible

            source_receipt = FrameRuleReceipt.model_validate_json(
                gate.details["physiotherapist_receipt"]
            )
            if source_receipt not in state.requisitions or not receipt_eligible(
                state, source_receipt
            ):
                raise ValueError("Recover the original Physiotherapist receipt and actual Frame")
            if replace is not None:
                raise ValueError("Physiotherapist restoration adds no purchase, Bond or scene")
        elif "implemented_class_receipt" in gate.details:
            from girlframe.engine.m3_class_grafts import eligible

            source_receipt = FrameRuleReceipt.model_validate_json(
                gate.details["implemented_class_receipt"]
            )
            if source_receipt not in state.requisitions or not eligible(state, source_receipt):
                raise ValueError("Recover the original implemented Class receipt and actual Frame")
            if replace is not None:
                raise ValueError("Restoration adds no purchase, Asset or acquisition effect")
        elif "native_class_receipt" in gate.details:
            source_receipt = FrameRuleReceipt.model_validate_json(
                gate.details["native_class_receipt"]
            )
            if source_receipt not in state.requisitions or not native_class_receipt(
                state, source_receipt
            ):
                raise ValueError("Recover the original native Class receipt and actual Frame")
            if replace is not None:
                raise ValueError("Class restoration adds no purchase, Asset or acquisition effect")
        elif "janus_receipt" in gate.details:
            source_receipt = FrameRuleReceipt.model_validate_json(gate.details["janus_receipt"])
            if source_receipt not in state.requisitions or source_receipt.frame_instance != frame:
                raise ValueError("Recover the exact original suspended JANUS entitlement")
            if replace is not None:
                raise ValueError("Restoration creates no new purchase, Asset or acquisition effect")
        elif "enforcer_grant" in gate.details:
            from girlframe.engine.m3_enforcer_requisitions import Grant, binding, grants

            original_grant = Grant.model_validate_json(gate.details["enforcer_grant"])
            if original_grant not in grants(state) or binding(state, original_grant)[1] != frame:
                raise ValueError("Recover the exact original suspended Enforcer entitlement")
            if replace is not None:
                raise ValueError("Restoring this rule grants no new Asset or acquisition effect")
        elif gate.details["kind"] != "asset_installment":
            grant = next(
                (x for x in state.personal_firearms if x.id == gate.details["grant"]), None
            )
            if (
                grant is None
                or grant.actor.entity != str(gate.target)
                or grant.actor.incarnation != character
                or grant.frame_instance != frame
                or json_dump_issues(grant) != gate.details["grant_issues"]
            ):
                raise ValueError(
                    "Recover the exact original suspended Frame rule and issued-item source"
                )
        if "asset" in gate.details:
            asset = AssetState.model_validate_json(gate.details["asset"])
            from girlframe.engine.m3_janus_storage import ids as stored_ids

            state.sheets[str(gate.target)] = install(
                sheet,
                asset,
                replace=replace,
                effective_void=stored_ids(
                    state, ActorRef(kind="pilot", entity=str(gate.target), incarnation=character)
                ),
                state=state,
            ).sheet
        elif replace is not None:
            raise ValueError(
                "Restoring a lost-pistol entitlement does not issue or remove an Asset"
            )
    elif replace is not None:
        raise ValueError("This restoration does not replace an Asset")
    gate.state = "fulfilled"
    return state


def json_dump_issues(grant: object) -> str:
    from girlframe.engine.m3_acquisition_state import PersonalFirearmGrant

    if not isinstance(grant, PersonalFirearmGrant):
        raise ValueError("Use the actual Personal Firearm entitlement")
    return "|".join(issue.model_dump_json() for issue in grant.issues)
