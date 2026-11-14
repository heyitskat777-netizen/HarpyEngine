"""Doctor effects are proved before death fallout, never reconstructed afterward."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m3_doctor import owned, replacement_work
from girlframe.services.m3_doctor_care import prove
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prepare(
    game: "GameService", c: Connection, previous: GameState, state: GameState, event: str
) -> None:
    # An unadapted NPC death producer must stop before committing its fallout,
    # just like the existing protected Pilot career-ending guard below.
    for npc in previous.world.npcs if previous.world else ():
        patient = ActorRef(kind="npc", entity=npc.id)
        if (
            npc.alive
            and rules.saving_care(previous, patient) is not None
            and not any(
                x.id == npc.id and x.alive for x in (state.world.npcs if state.world else ())
            )
        ):
            raise WorkflowError(
                "This protected NPC death producer must apply Metal Angel before death fallout"
            )
    for care in rules.values(state, "doctor_care", rules.Care):
        if care.phase not in ("proposal", "active", "recovery"):
            continue
        patient_sheet = state.sheets.get(care.patient.entity)
        try:
            current = rules.frame_id(state, care.doctor) == care.frame
        except ValueError:
            current = False
        patient_current = (
            (patient_sheet is not None and patient_sheet.character_id == care.patient.incarnation)
            if care.patient.kind == "pilot"
            else (
                care.patient.kind == "npc"
                and state.world is not None
                and any(x.id == care.patient.entity and x.alive for x in state.world.npcs)
            )
        )
        if not current or not patient_current:
            rules.put(
                state,
                "doctor_care",
                care.model_copy(update=dict(phase="ended", completion_event=event)),
            )
    for protection in rules.values(state, "doctor_protection", rules.Protection):
        if protection.phase != "protecting":
            continue
        protector = state.sheets.get(protection.protector.entity)
        try:
            current = rules.frame_id(state, protection.doctor) == protection.frame
        except ValueError:
            current = False
        protector_current = (
            protector is not None and protector.character_id == protection.protector.incarnation
            if protection.protector.kind == "pilot"
            else protection.protector.kind == "npc"
            and state.world is not None
            and any(x.id == protection.protector.entity and x.alive for x in state.world.npcs)
        )
        if not current or not protector_current:
            rules.put(
                state,
                "doctor_protection",
                protection.model_copy(update=dict(phase="ended", end_event=event)),
            )
    previous_receipts = {x.id for x in previous.requisitions}
    for receipt in state.requisitions:
        if (
            not isinstance(receipt, FrameRuleReceipt)
            or receipt.id in previous_receipts
            or receipt.source_event != event
            or receipt.rule_id not in rules.REQUISITIONS
        ):
            continue
        try:
            frame = rules.frame_id(state, receipt.actor)
        except ValueError:
            continue
        if receipt.frame_instance == frame and receipt.donor_frame == rules.BOOK:
            sheet = state.sheets[receipt.actor.entity]
            sheet.obsolescence_marked = max(0, sheet.obsolescence_marked - 1)
            state.facts.append(
                dict(kind="doctor_requisition_unmark", receipt=receipt.id, event=event)
            )
    for protection in rules.values(previous, "doctor_protection", rules.Protection):
        if protection.phase != "protecting":
            continue
        old = previous.sheets.get(protection.doctor.entity)
        new = state.sheets.get(protection.doctor.entity)
        if old is None or old.character_id != protection.doctor.incarnation:
            continue
        actually_dead = any(
            x.actor == protection.doctor
            and x.source_event == event
            and x.ending in ("death", "execution")
            for x in state.career_archives
        )
        newly_hurt = actually_dead or (
            new is not None
            and new.character_id == old.character_id
            and any(
                x.damaged and any(y.id == x.id and not y.damaged for y in old.assets)
                for x in new.assets
            )
        )
        if newly_hurt and not any(
            x.get("kind") == "doctor_protector_harm"
            and x.get("event") == event
            and x.get("patient") == protection.doctor.model_dump_json()
            and x.get("protector") == protection.protector.model_dump_json()
            for x in state.facts
        ):
            raise WorkflowError(
                "Stop actual protection first or use its source-proved protector harm port"
            )
    new_deaths = [
        x
        for x in state.career_archives
        if x.source_event == event and x.ending in ("death", "execution")
    ]
    for archive in new_deaths:
        if rules.saving_care(previous, archive.actor) or rules.held(
            previous, archive.actor, rules.ADRENAL
        ):
            raise WorkflowError(
                "This protected death producer must apply Doctor prevention before career fallout"
            )
    for fact in state.facts:
        if fact.get("kind") != "doctor_prevented_death" or fact.get("event") != event:
            continue
        patient = ActorRef.model_validate_json(fact["patient"])
        if fact["source"] == "metal_angel":
            saving = rules.saving_care(previous, patient)
            if (
                saving is None
                or saving.id != fact["care"]
                or not owned(game, c, previous, saving.doctor, rules.ANGEL)
            ):
                raise WorkflowError(
                    "Recover the actual preexisting Metal Angel care and entitlement"
                )
            prove(game, c, saving)
        elif not owned(game, c, previous, patient, rules.ADRENAL):
            raise WorkflowError(
                "Recover the actual native Adrenal Injectors before preventing death"
            )
    if new_deaths:
        for uid, sheet in list(state.sheets.items()):
            if sheet.frame != rules.BOOK or sheet.frame_scrapped or sheet.character_id is None:
                continue
            actor = ActorRef(kind="pilot", entity=uid, incarnation=sheet.character_id)
            if not owned(game, c, previous, actor, rules.TRACK):
                continue
            # One immutable source records each actually dead original Cadre member.
            for archive in new_deaths:
                if (
                    int(archive.actor.entity) in previous.order
                    and not state.sheets[uid].frame_scrapped
                ):
                    rules.mark(state, actor, "cadre_death", event, cause=archive.id)


def synchronize(game: "GameService", c: Connection, state: GameState, event: str) -> None:
    actors = {
        ActorRef.model_validate_json(x["actor"])
        for x in state.facts
        if x.get("kind") == "doctor_track_mark"
        and (x.get("event") == event or str(x.get("event", "")).startswith(event + ":"))
    }
    for actor in actors:
        replacement_work(
            game,
            c,
            state,
            actor,
            event,
            dict(campaign_id=game.store.campaign_id, campaign_context=True),
        )
