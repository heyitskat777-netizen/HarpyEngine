"""Pure mission/playbook reactions, before the final Status/reward snapshot."""

from typing import Literal

from girlframe.engine.m2 import GameState, Model, PilotSheet, shift_status
from girlframe.engine.m3_girl_runtime_state import has_rule

DoctorTrigger = Literal[
    "nanobot_injection", "mission_failure", "cadre_death", "high_budget", "adrenal"
]
AceCheck = Literal["after_promotion", "before_promotion"]


class DoctorResult(Model):
    sheet: PilotSheet
    replacement_required: bool


def mark_obsolescence(sheet: PilotSheet, trigger: DoctorTrigger) -> DoctorResult:
    if trigger not in (
        "nanobot_injection",
        "mission_failure",
        "cadre_death",
        "high_budget",
        "adrenal",
    ):
        raise ValueError("Use a printed Planned Obsolescence trigger")
    if (
        sheet.frame != "DOCTORDOCTOR MK. II"
        or sheet.frame_scrapped
        or sheet.obsolescence_marked >= 8
    ):
        raise ValueError("A current, unscrapped DoctorDoctor Frame is required")
    updated = PilotSheet.model_validate_json(sheet.model_dump_json())
    updated.obsolescence_marked += 1
    updated.frame_scrapped = updated.obsolescence_marked == 8
    updated.revision += 1
    return DoctorResult(sheet=updated, replacement_required=updated.frame_scrapped)


def princess_mission_end(
    original: GameState,
    owner: int,
    *,
    upheld: bool,
    ace_check: AceCheck | None,
) -> GameState:
    if type(upheld) is not bool:
        raise ValueError("Record whether the standards were upheld")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(str(owner))
    if (
        sheet is None
        or not has_rule(sheet, "girl.princess.to-a-higher-standard", "PRINCESS")
        or owner not in state.order
    ):
        raise ValueError("A current owner of To a Higher Standard in the Status roster is required")
    if not upheld:
        return state
    if ace_check not in ("after_promotion", "before_promotion"):
        raise ValueError(
            "UNRESOLVED_RULING: the Princess Permission timing needs a campaign ruling"
        )
    was_ace = state.order[0] == owner
    shift_status(state, owner, 1)
    if was_ace or (ace_check == "after_promotion" and state.order[0] == owner):
        sheet.permissions += 1
    sheet.revision += 1
    return state
