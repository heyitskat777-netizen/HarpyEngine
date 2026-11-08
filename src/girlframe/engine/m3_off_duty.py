"""Explicit Off-Duty periods, source-specific rolls, scenes and bounded recovery.

Preparation and required-work resolution belong to typed services, never a timer
or a client's claim that a Strain/requisition/Punishment consequence was handled.
"""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import GameState, Model, PilotSheet, tier
from girlframe.engine.m3_adjudication_state import Decision
from girlframe.engine.m3_choices import OFF_DUTY, off_duty_modifier
from girlframe.engine.m3_core import Recovery, RepairSelection, recover_off_duty
from girlframe.engine.m3_modular import Replacement
from girlframe.engine.m3_observation_state import Observation
from girlframe.engine.rolls import Face


class Adjustment(Model):
    source: str
    amount: int
    actor: Snowflake | None = None
    tag: str | None = None


class Roll(Model):
    faces: tuple[Face, Face] | None = None
    adjudication: Decision | None = None
    modifier: int = Field(ge=0)
    total: int
    source: Literal["status", "void_assets"]
    stage: Literal["tag_window", "choices"] = "choices"
    adjustments: tuple[Adjustment, ...] = ()

    @model_validator(mode="after")
    def summed(self) -> "Roll":
        if self.adjudication is not None:
            if (
                self.faces is not None
                or self.modifier != 0
                or (
                    self.adjudication.required.play
                    != ("void_observation" if self.source == "void_assets" else "go_off_duty")
                )
            ):
                raise ValueError("Manual adjudication has no dice or hidden numeric base")
            base = self.adjudication.total
        elif self.faces is not None:
            base = sum(self.faces) + self.modifier
        else:
            raise ValueError("Retain exactly actual dice or owned manual adjudication proof")
        if base + sum(x.amount for x in self.adjustments) != self.total:
            raise ValueError("The receipt must retain the actual dice and modifier")
        return self


class Scene(Model):
    kind: str
    participants: tuple[Snowflake, ...]
    acknowledgements: tuple[Snowflake, ...] = ()
    summary: str = Field(min_length=1, max_length=1200)
    character_ids: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def distinct(self) -> "Scene":
        if (
            len(set(self.participants)) != len(self.participants)
            or len(set(self.acknowledgements)) != len(self.acknowledgements)
            or not set(self.acknowledgements) <= set(self.participants)
            or not self.summary.strip()
            or not set(self.character_ids) <= {str(uid) for uid in self.participants}
        ):
            raise ValueError("A scene needs distinct participants and their own acknowledgements")
        return self


class Progress(Model):
    roll: Roll | None = None
    scene: Scene | None = None
    scene_declined: bool = False
    recovered: bool = False
    action_id: str | None = None
    reward_source_event: str | None = None
    observation: Observation | None = None
    career_ended: str | None = None


class HandlerContext(Model):
    entity: str | None = None
    operation: Literal["hire", "fire", "chastise", "request", "deprogram"] | None = None
    deprogram_tags: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def deprogram_scope(self) -> "HandlerContext":
        if (self.operation == "deprogram") != bool(self.deprogram_tags):
            raise ValueError("Only deprogramming selects actual work-affecting NPC Tags")
        if len(set(self.deprogram_tags)) != len(self.deprogram_tags):
            raise ValueError("Choose distinct real NPC Tags")
        return self


class Period(Model):
    id: str = Field(min_length=1, max_length=80)
    revision: int = Field(default=1, ge=1)
    handler: Snowflake
    pilots: tuple[Snowflake, ...]
    phase: Literal["preparing", "active", "complete"] = "preparing"
    progress: dict[str, Progress] = Field(default_factory=dict)
    credit_recorded: tuple[Snowflake, ...] = ()
    handler_scene: Scene | None = None
    status_review: tuple[Snowflake, ...] | None = None
    status_review_game_revision: int | None = None
    character_ids: dict[str, str] = Field(default_factory=dict)
    ended_characters: dict[str, str] = Field(default_factory=dict)
    handler_recipient: Snowflake | None = None
    handler_work: str | None = None
    handler_context: HandlerContext | None = None

    @model_validator(mode="after")
    def roster(self) -> "Period":
        if (
            not self.pilots
            or len(set(self.pilots)) != len(self.pilots)
            or self.handler in self.pilots
            or not set(self.progress) <= {str(x) for x in self.pilots}
            or len(set(self.credit_recorded)) != len(self.credit_recorded)
            or not set(self.credit_recorded) <= set(self.pilots)
            or (self.character_ids and set(self.character_ids) != {str(x) for x in self.pilots})
            or len(set(self.character_ids.values())) != len(self.character_ids)
            or not set(self.ended_characters) <= {str(x) for x in self.pilots}
            or any(
                self.character_ids.get(uid) != character
                for uid, character in self.ended_characters.items()
            )
        ):
            raise ValueError("Use the distinct canonical Pilot roster and its appointed Handler")
        return self


class RecoveryChoice(Model):
    unmark_identity: str | None = None
    embrace_tag: str | None = None
    replace_identity: str | None = None
    repair_assets: bool = True
    repairs: RepairSelection | None = None
    modular_replacements: tuple[Replacement, ...] = Field(default=(), exclude_if=lambda x: not x)


HANDLER_SCENES = ("punish", "permission", "npc_employment", "prisoner", "exploit", "routine")


def handler_scene(
    period: Period,
    expected: int,
    actor: int,
    kind: str,
    participants: tuple[int, ...],
    summary: str,
    *,
    extra_participants: frozenset[int] = frozenset(),
) -> Period:
    current(period, expected)
    if (
        actor != period.handler
        or period.handler_scene is not None
        or kind not in HANDLER_SCENES
        or actor not in participants
        or not set(participants) <= set(period.pilots) | {actor} | extra_participants
        or not (set(participants) & set(period.pilots))
    ):
        raise ValueError(
            "The current Handler sets one printed scene with at least one current Girl"
        )
    result = clone(period)
    result.handler_scene = Scene(kind=kind, participants=participants, summary=summary)
    result.revision += 1
    return result


def acknowledge_handler_scene(period: Period, expected: int, actor: int) -> Period:
    current(period, expected)
    scene = period.handler_scene
    if scene is None or actor not in scene.participants or actor in scene.acknowledgements:
        raise ValueError("Each actual Handler-scene participant confirms it for themselves")
    result = clone(period)
    assert result.handler_scene is not None
    result.handler_scene.acknowledgements += (actor,)
    result.revision += 1
    return result


def clone(period: Period) -> Period:
    return Period.model_validate_json(period.model_dump_json())


def current(period: Period, expected: int, *, active: bool = True) -> None:
    if period.revision != expected:
        raise ValueError("STALE_OFF_DUTY: reopen the period")
    if period.phase != ("active" if active else "preparing"):
        raise ValueError("Finish the required period preparation before this action")


def activate(period: Period, expected: int, *, pending_preparation: frozenset[str]) -> Period:
    current(period, expected, active=False)
    if pending_preparation:
        raise ValueError("Resolve actual Strain/start triggers before Off-Duty rolls")
    result = clone(period)
    result.phase = "active"
    result.revision += 1
    return result


def ordinary_roll(
    period: Period,
    expected: int,
    actor: int,
    state: GameState,
    faces: tuple[int, int] | None,
    *,
    adjudication: Decision | None = None,
) -> Period:
    current(period, expected)
    if actor not in period.pilots or str(actor) not in state.sheets or actor not in state.order:
        raise ValueError("Only a current Pilot in this period can make its own Off-Duty roll")
    if period.progress.get(str(actor), Progress()).roll is not None:
        raise ValueError(
            "This period already has a saved roll; resume it rather than rolling again"
        )
    sheet = state.sheets[str(actor)]
    if str(actor) in period.ended_characters or (
        period.character_ids
        and sheet.character_id is not None
        and period.character_ids.get(str(actor)) != sheet.character_id
    ):
        raise ValueError("This period belongs to its original living Girl")
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_careers import can_pilot

    unlinked = sheet.character_id is not None and not can_pilot(
        state, ActorRef(kind="pilot", entity=str(actor), incarnation=sheet.character_id)
    )
    if sheet.frame_scrapped and not unlinked:
        raise ValueError("Resolve the compulsory Frame replacement first")
    if any(
        x.kind == "void_observation" and x.owner == actor and x.state == "pending"
        for x in state.obligations
    ):
        raise ValueError("Void Observation replaces the ordinary Off-Duty Play")
    from girlframe.engine.m3_intracadre_marriage import is_ace, is_dog

    status: Literal["Ace", "Wings", "Dog"] = (
        "Ace" if is_ace(state, actor) else "Dog" if is_dog(state, actor) else "Wings"
    )
    modifier = off_duty_modifier(status)
    if adjudication is not None and (
        adjudication.required.actor.entity != str(actor)
        or adjudication.required.actor.incarnation != sheet.character_id
        or adjudication.required.source_id != period.id
    ):
        raise ValueError("The manual decision belongs to the original period's actual Girl")
    receipt = Roll(
        faces=faces,
        adjudication=adjudication,
        modifier=0 if adjudication else modifier,
        total=adjudication.total if adjudication else sum(faces or ()) + modifier,
        source="status",
    )
    result = clone(period)
    result.progress[str(actor)] = Progress(roll=receipt)
    result.revision += 1
    return result


def choose_scene(
    period: Period,
    expected: int,
    actor: int,
    *,
    kind: str | None,
    participants: tuple[int, ...] = (),
    summary: str = "",
    available_pilots: frozenset[int] | None = None,
) -> Period:
    current(period, expected)
    progress = period.progress.get(str(actor))
    if (
        progress is None
        or progress.roll is None
        or progress.roll.source != "status"
        or progress.roll.stage != "choices"
    ):
        raise ValueError("Resume a saved ordinary Off-Duty roll before choosing its scene")
    if progress.scene is not None or progress.scene_declined:
        raise ValueError("The scene choice is already saved")
    level = tier(progress.roll.total)
    if kind is None:
        if level != "mid" or participants or summary:
            raise ValueError("Only the routine result can decline its optional scene")
    else:
        people = set(period.pilots) if available_pilots is None else set(available_pilots)
        other = set(participants) - {actor}
        if (
            kind not in OFF_DUTY[level]
            or actor not in participants
            or not other
            or not set(participants) <= people | {period.handler}
            or (level == "mid" and not other <= people)
        ):
            raise ValueError("Choose a source-legal scene with the required other Girls or Handler")
    result = clone(period)
    if kind is None:
        result.progress[str(actor)].scene_declined = True
    else:
        result.progress[str(actor)].scene = Scene(
            kind=kind, participants=participants, summary=summary
        )
    result.revision += 1
    return result


def acknowledge_scene(period: Period, expected: int, actor: int, scene_owner: int) -> Period:
    current(period, expected)
    progress = period.progress.get(str(scene_owner))
    scene = progress.scene if progress else None
    if scene is None or actor not in scene.participants or actor in scene.acknowledgements:
        raise ValueError("Each participating human must confirm the played scene for themselves")
    result = clone(period)
    saved = result.progress[str(scene_owner)].scene
    assert saved is not None
    saved.acknowledgements += (actor,)
    result.revision += 1
    return result


def recovery(
    period: Period,
    expected: int,
    actor: int,
    sheet: PilotSheet,
    choice: Recovery,
    *,
    pending_effects: frozenset[str],
) -> tuple[Period, PilotSheet]:
    current(period, expected)
    progress = period.progress.get(str(actor))
    if sheet.owner != actor or progress is None or progress.roll is None or progress.recovered:
        raise ValueError("Only the owner can recover once from its saved Off-Duty Play")
    if progress.roll.stage != "choices":
        raise ValueError("Finish the saved roll's Tag choices first")
    if progress.roll.source == "void_assets":
        from girlframe.engine.m3_observation import complete

        if not complete(period, actor):
            raise ValueError("Resolve the actual Observation choices, effects and scene first")
    if not progress.scene_declined and (
        progress.scene is None
        or set(progress.scene.acknowledgements) != set(progress.scene.participants)
    ):
        raise ValueError("Complete the required on-screen scene before recovery")
    if pending_effects:
        raise ValueError("Resolve the scene's actual mandatory effects before recovery")
    if sheet.sedation_locked and sheet.sedation_period != period.id:
        raise ValueError("Resolve legacy or differently scoped Sedation locks explicitly")
    result = clone(period)
    updated = recover_off_duty(sheet, choice).sheet
    result.progress[str(actor)].recovered = True
    result.revision += 1
    return result, updated


def doctor_credit(
    period: Period,
    expected: int,
    actor: int,
    state: GameState,
    recipient: int | None,
    account: str,
    *,
    event: str | None = None,
) -> tuple[Period, GameState]:
    """A player's factual credit declaration, never an invented absent-player answer."""
    current(period, expected, active=period.phase == "active")
    sheet = state.sheets.get(str(actor))
    if (
        actor not in period.pilots
        or actor in period.credit_recorded
        or sheet is None
        or sheet.frame != "DOCTORDOCTOR MK. II"
        or sheet.frame_scrapped
        or period.progress.get(str(actor), Progress()).roll is not None
        or not account.strip()
        or len(account) > 1200
    ):
        raise ValueError("The current DoctorDoctor owner must record this start trigger once")
    if recipient is not None and (
        recipient == actor or str(recipient) not in state.sheets or recipient not in state.order
    ):
        raise ValueError("Credit grants a Permission only to another current canonical Pilot")
    result, updated = clone(period), GameState.model_validate_json(state.model_dump_json())
    result.credit_recorded += (actor,)
    result.revision += 1
    if recipient is not None:
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_intracadre_marriage import acquisitions, credit, marriage_for

        beneficiary = current_ref(updated, recipient) if acquisitions(updated) else None
        if beneficiary is not None and marriage_for(updated, beneficiary) is not None:
            if event is None:
                raise ValueError(
                    "Retain the actual Doctor credit event before granting shared funds"
                )
            credit(
                updated,
                beneficiary,
                1,
                event=event,
                source="doctor-credit:" + period.id + ":" + str(actor),
            )
        else:
            updated.sheets[str(recipient)].permissions += 1
        updated.sheets[str(recipient)].revision += 1
    return result, updated


def finish(
    period: Period,
    expected: int,
    state: GameState,
    *,
    pending_work: frozenset[str],
    handler_scene_complete: bool,
    status_review_complete: bool,
) -> tuple[Period, GameState]:
    current(period, expected)
    if (
        pending_work
        or not handler_scene_complete
        or not status_review_complete
        or any(
            not period.progress.get(str(uid), Progress()).recovered
            and str(uid) not in period.ended_characters
            for uid in period.pilots
        )
        or not {uid for uid in period.pilots if str(uid) not in period.ended_characters}
        <= set(state.order)
        or state.handler != period.handler
    ):
        raise ValueError("Off-Duty ends only after recovery, actual work, Handler scene and review")
    result, updated = clone(period), GameState.model_validate_json(state.model_dump_json())
    for sheet in updated.sheets.values():
        if sheet.sedation_locked and sheet.sedation_period != period.id:
            raise ValueError("Do not silently clear legacy or differently scoped Sedation locks")
        if sheet.sedation_period == period.id:
            sheet.sedation_locked = ()
            sheet.sedation_period = None
            sheet.revision += 1
    result.phase = "complete"
    result.revision += 1
    return result, updated
