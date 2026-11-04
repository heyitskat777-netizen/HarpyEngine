"""Printed Frame Off-Duty bonuses; factual claims do not invent custody or consent."""

from pydantic import Field

from girlframe.engine.m2 import GameState, Model, PilotSheet
from girlframe.engine.m3_world_state import World

PAGES = {
    "THE PRINCE": 61,
    "CONSUME": 65,
    "JANUS": 68,
    "DOCTORDOCTOR MK. II": 71,
    "WYVERN 0.4": 74,
    "THE ENFORCER": 78,
    "CHANGELING": 81,
    "PROJECT ANKOU": 84,
    "THE RED QUEEN": 88,
}


def official(frame: str) -> str:
    return "JANUS" if frame == "JANUS-B" else frame


def incarnation(sheet: PilotSheet) -> str:
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial"


def queen(sheet: PilotSheet) -> int:
    if official(sheet.frame) != "THE RED QUEEN":
        raise ValueError("The Queen choice needs its actual Red Queen Frame")
    if sheet.frame_runtime is not None:
        current = sheet.frame_runtime.court.get("The Queen")
        if current is None:
            raise ValueError("Resolve the current Frame's actual Court allocation")
        return current
    initial = [x for x in sheet.review.shared if x.kind == "court" and x.source_id == sheet.owner]
    if len(initial) != 1:
        raise ValueError("Resolve the saved initial Court allocation, without assuming a holder")
    return initial[0].allocation["The Queen"]


class Claim(Model):
    fulfilled: bool
    account: str = Field(min_length=1, max_length=1200)
    prisoner: str | None = Field(default=None, min_length=1, max_length=160)
    official: str | None = Field(default=None, min_length=1, max_length=160)
    offering: str = Field(default="", max_length=1200)
    influenced_pilot: int | None = Field(default=None, gt=0)
    evidence: str = Field(default="", max_length=1200)


def prisoner(
    world: World,
    entity: str,
    owner: int,
    handler: int,
    *,
    rebel: bool,
    cadre: frozenset[int] = frozenset(),
) -> str:
    category, separator, identity = entity.partition(":")
    bases = {
        x.cell
        for x in world.locations
        if x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
    }
    if not separator:
        raise ValueError("Select an actual saved prisoner")
    if category == "npc":
        target = next((x for x in world.npcs if x.id == identity and x.alive), None)
        if (
            target is None
            or "prisoner" not in target.jobs
            or target.captive_of is not None
            or target.cell not in bases
            or not target.custody_event
        ):
            raise ValueError("This NPC is not a current prisoner brought back to a Foundation base")
        if rebel and not any(x.id == target.faction and x.kind == "rebel" for x in world.factions):
            raise ValueError("This NPC needs an actual public Rebel affiliation")
        assert target.custody_event is not None
        return target.custody_event
    elif category == "pilot":
        pilot = next((x for x in world.pilots if x.id == identity and x.alive), None)
        if (
            pilot is None
            or pilot.custody not in ("captured", "transported")
            or pilot.custodian not in cadre | {owner, handler}
            or pilot.cell not in bases
            or not pilot.custody_event
        ):
            raise ValueError("This Pilot needs actual custody and delivery to a Foundation base")
        if rebel and pilot.kind != "rebel":
            raise ValueError("The Enforcer needs an actual Rebel prisoner for this branch")
        assert pilot.custody_event is not None
        return pilot.custody_event
    else:
        raise ValueError("Choose an actual NPC or Pilot prisoner")


def review(
    state: GameState,
    owner: int,
    claim: Claim,
    source: str,
    *,
    eligibility: GameState | None = None,
    handler_interested: bool | None = None,
    character_id: str | None = None,
) -> GameState:
    claim = Claim.model_validate_json(claim.model_dump_json())
    facts = eligibility if eligibility is not None else state
    sheet = facts.sheets.get(str(owner))
    if (
        sheet is None
        or owner not in state.order
        or str(owner) not in state.sheets
        or sheet.frame_scrapped
        or not source.strip()
        or facts.handler is None
    ):
        raise ValueError("Review the actual current Frame and source event")
    frame = official(sheet.frame)
    if frame not in PAGES or frame in ("DOCTORDOCTOR MK. II", "THE RED QUEEN"):
        raise ValueError("This Frame has a separate source-owned reward decision")
    allowed = {
        "THE PRINCE": set(),
        "CONSUME": {"prisoner"},
        "JANUS": {"official"},
        "WYVERN 0.4": {"offering"},
        "THE ENFORCER": {"prisoner", "evidence"},
        "CHANGELING": {"influenced_pilot"},
        "PROJECT ANKOU": set(),
    }[frame]
    defaults = Claim(fulfilled=claim.fulfilled, account=claim.account)
    for field in type(claim).model_fields:
        if field not in {"fulfilled", "account"} | (
            allowed if claim.fulfilled else set()
        ) and getattr(claim, field) != getattr(defaults, field):
            raise ValueError("This trigger review includes unrelated or contradictory choices")
    if not claim.account.strip():
        raise ValueError("Record the actual trigger or no-trigger account")
    if frame != "WYVERN 0.4" and handler_interested is not None:
        raise ValueError("Only Wyvern's offering takes the Handler's interest decision")
    if frame == "WYVERN 0.4" and claim.fulfilled and type(handler_interested) is not bool:
        raise ValueError("The actual Handler must record its own interest in this offering")
    if any(
        x.get("source_work") == source and x.get("kind") == "frame_permission_trigger"
        for x in state.facts
    ):
        raise ValueError("This actual reward review is already saved")
    custody_source = None
    character_key = character_id or "user:" + str(owner)
    if claim.fulfilled:
        if frame in ("CONSUME", "THE ENFORCER") and claim.prisoner:
            if facts.world is None:
                raise ValueError("A prisoner reward needs the actual world and custody record")
            custody_source = prisoner(
                facts.world,
                claim.prisoner,
                owner,
                facts.handler,
                rebel=frame == "THE ENFORCER",
                cadre=frozenset(facts.order),
            )
            if any(
                x.get("kind") == "frame_permission_trigger"
                and x.get("character_id") == character_key
                and x.get("custody_source") == custody_source
                for x in state.facts
            ):
                raise ValueError(
                    "That custody/delivery record already earned this character's bonus; "
                    "record a new delivery"
                )
        if frame == "CONSUME" and claim.prisoner is None:
            raise ValueError("Select the actual prisoner brought back for your Handler")
        if frame == "THE ENFORCER" and bool(claim.prisoner) == bool(claim.evidence.strip()):
            raise ValueError(
                "Choose one actual Rebel prisoner or describe actual disobedience evidence"
            )
        if frame == "JANUS":
            valid = claim.official == "handler:" + str(facts.handler)
            if facts.world is not None:
                valid |= any(
                    "npc:" + x.id == claim.official
                    and (
                        x.employment == "foundation"
                        or set(x.jobs)
                        & {"handler", "director", "guard", "scientist", "doctor", "base_personnel"}
                    )
                    for x in facts.world.npcs
                )
            if not valid:
                raise ValueError("Choose the actual Foundation official who saw the demonstration")
        if frame == "THE PRINCE" and not (
            sheet.frame_runtime.fanbase if sheet.frame_runtime else sheet.review.creation.fanbase
        ):
            raise ValueError("Review the actual Fanbase and its demands first")
        if frame == "WYVERN 0.4" and not claim.offering.strip():
            raise ValueError("Describe the actual thing brought to your Handler")
        if frame == "CHANGELING" and (
            claim.influenced_pilot not in facts.order or claim.influenced_pilot == owner
        ):
            raise ValueError("Choose another actual Girl whose behaviour your adjustments affected")
    updated = GameState.model_validate_json(state.model_dump_json())
    qualified = claim.fulfilled and (frame != "WYVERN 0.4" or handler_interested is True)
    if qualified:
        updated.sheets[str(owner)].permissions += 1
        updated.sheets[str(owner)].revision += 1
    receipt = {
        "kind": "frame_permission_trigger",
        "source_work": source,
        "frame": frame,
        "owner": str(owner),
        "qualified": str(qualified),
        "character_id": character_key,
    }
    if custody_source is not None:
        receipt["custody_source"] = custody_source
    updated.facts.append(receipt)
    return updated


def queen_award(
    state: GameState,
    frame_owner: int,
    actor: int,
    recipient: int,
    source: str,
    *,
    eligibility: GameState | None = None,
) -> GameState:
    frame = (eligibility if eligibility is not None else state).sheets.get(str(frame_owner))
    if (
        frame is None
        or frame_owner not in state.order
        or str(frame_owner) not in state.sheets
        or frame.frame_scrapped
        or queen(frame) != actor
    ):
        raise ValueError("Only the actual Queen AM holder chooses this reward")
    if recipient not in state.order or str(recipient) not in state.sheets:
        raise ValueError("Choose an actual current Girl who served your purposes best")
    if recipient == actor and state.order[-1] == recipient:
        raise ValueError("The Queen holder cannot award itself while it is the Dog")
    if not source.strip() or any(
        x.get("source_work") == source and x.get("kind") == "frame_permission_trigger"
        for x in state.facts
    ):
        raise ValueError("Resume this actual source reward instead of granting it again")
    updated = GameState.model_validate_json(state.model_dump_json())
    updated.sheets[str(recipient)].permissions += 1
    updated.sheets[str(recipient)].revision += 1
    updated.facts.append(
        {
            "kind": "frame_permission_trigger",
            "source_work": source,
            "frame": "THE RED QUEEN",
            "owner": str(frame_owner),
            "recipient": str(recipient),
            "chooser": str(actor),
        }
    )
    return updated
