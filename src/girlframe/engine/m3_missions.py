"""Pure mission lifecycle; no implicit time advancement, player answers or live writes."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m2 import Model

Response = Literal["accept", "decline"]
AcePolicy = Literal["current_ace", "participants_only"]


class Mission(Model):
    id: str = Field(min_length=1, max_length=80)
    revision: int = Field(default=1, ge=1)
    handler: Snowflake
    objective: str = Field(min_length=1, max_length=1200)
    offered_to: tuple[Snowflake, ...]
    responses: dict[str, Response] = Field(default_factory=dict)
    participants: tuple[Snowflake, ...] = ()
    phase: Literal[
        "offered", "active", "ending", "awaiting_consequences", "complete", "cancelled"
    ] = "offered"
    success: bool | None = None
    consequence_ids: tuple[str, ...] = ()
    offered_characters: dict[str, str] = Field(default_factory=dict)
    character_ids: dict[str, str] = Field(default_factory=dict)
    ended_participants: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistency(self) -> "Mission":
        if (
            not self.offered_to
            or len(set(self.offered_to)) != len(self.offered_to)
            or self.handler in self.offered_to
        ):
            raise ValueError("Offer to a distinct nonempty Pilot set, excluding the Handler")
        if not set(self.responses) <= {str(x) for x in self.offered_to}:
            raise ValueError("Only offered players may respond")
        if (
            not set(self.offered_characters) <= {str(x) for x in self.offered_to}
            or not set(self.character_ids) <= {str(x) for x in self.participants}
            or not set(self.ended_participants) <= {str(x) for x in self.participants}
            or any(
                self.character_ids.get(uid, character) != character
                for uid, character in self.ended_participants.items()
            )
        ):
            raise ValueError("Mission identity records must match its actual original participants")
        accepted = {int(uid) for uid, value in self.responses.items() if value == "accept"}
        if (
            len(set(self.participants)) != len(self.participants)
            or not set(self.participants) <= accepted
        ):
            raise ValueError("Mission participants require their own acceptance")
        return self


def changed(mission: Mission, **values: object) -> Mission:
    result = mission.model_copy(update={"revision": mission.revision + 1, **values})
    return Mission.model_validate_json(result.model_dump_json())


def revision(mission: Mission, expected: int) -> None:
    if mission.revision != expected:
        raise ValueError("STALE_MISSION: refresh before changing this mission")


def respond(mission: Mission, actor: Snowflake, expected: int, response: Response) -> Mission:
    revision(mission, expected)
    if (
        mission.phase != "offered"
        or actor not in mission.offered_to
        or str(actor) in mission.responses
    ):
        raise ValueError("Only an invited player with a pending offer can answer it")
    if response not in ("accept", "decline"):
        raise ValueError("Choose acceptance or decline")
    return changed(mission, responses={**mission.responses, str(actor): response})


def handler(mission: Mission, actor: Snowflake, current_handler: Snowflake) -> None:
    if actor != mission.handler or actor != current_handler:
        raise ValueError("Only the current appointed Handler may advance this mission")


def dispatch(
    mission: Mission,
    actor: Snowflake,
    current_handler: Snowflake,
    expected: int,
    current_pilots: frozenset[Snowflake],
) -> Mission:
    revision(mission, expected)
    handler(mission, actor, current_handler)
    if mission.phase != "offered" or set(mission.responses) != {str(x) for x in mission.offered_to}:
        raise ValueError("Every offered player must answer; absence is not acceptance")
    people = tuple(x for x in mission.offered_to if mission.responses[str(x)] == "accept")
    if not people or not set(people) <= current_pilots:
        raise ValueError("Dispatch requires accepted, currently active Pilots")
    return changed(mission, participants=people, phase="active")


class PermissionGrant(Model):
    owner: Snowflake
    amount: int = Field(ge=1)
    reason: Literal["mission_completed", "ace_bonus"]


class Consequence(Model):
    id: str
    owner: Snowflake
    decision_owner: Snowflake
    reason: Literal["mission_failure", "dog_mission_end"]
    source_pdf: int


class EndPlan(Model):
    mission: Mission
    grants: tuple[PermissionGrant, ...]
    consequences: tuple[Consequence, ...]
    # Frame triggers and other end-of-mission reactions require their own source-specific steps.
    additional_trigger_audit_required: Literal[True] = True


def end(
    mission: Mission,
    actor: Snowflake,
    current_handler: Snowflake,
    expected: int,
    *,
    success: bool,
    status_order: tuple[Snowflake, ...],
    ace_policy: AcePolicy | None,
    ended_participants: dict[str, str] | None = None,
) -> EndPlan:
    revision(mission, expected)
    handler(mission, actor, current_handler)
    if (
        mission.phase not in ("active", "ending")
        or (mission.phase == "ending" and mission.success != success)
        or len(set(status_order)) != len(status_order)
        or current_handler in status_order
    ):
        raise ValueError("End an active mission with a valid current Status roster")
    departed = ended_participants or {}
    if not set(departed) <= {str(uid) for uid in mission.participants} or any(
        mission.character_ids.get(uid, character) != character
        for uid, character in departed.items()
    ):
        raise ValueError("Departures must identify the original dispatched characters")
    living = tuple(uid for uid in mission.participants if str(uid) not in departed)
    if not set(living) <= set(status_order):
        raise ValueError("Mission roster changes require explicit resolution before rewards")
    ace, dog = (status_order[0], status_order[-1]) if status_order else (None, None)
    if ace is not None and ace_policy is None and ace not in living:
        raise ValueError("UNRESOLVED_RULING: absent Ace bonus policy is required")
    grants = [PermissionGrant(owner=uid, amount=1, reason="mission_completed") for uid in living]
    if ace is not None and (ace in living or ace_policy == "current_ace"):
        grants.append(PermissionGrant(owner=ace, amount=1, reason="ace_bonus"))
    consequences = (
        [
            Consequence(
                id=mission.id + ":failure:" + str(uid),
                owner=uid,
                decision_owner=current_handler,
                reason="mission_failure",
                source_pdf=16,
            )
            for uid in living
        ]
        if not success
        else []
    )
    if dog is not None:
        consequences.append(
            Consequence(
                id=mission.id + ":dog",
                owner=dog,
                decision_owner=current_handler,
                reason="dog_mission_end",
                source_pdf=17,
            )
        )
    updated = changed(
        mission,
        phase="awaiting_consequences",
        success=success,
        consequence_ids=tuple(x.id for x in consequences),
        ended_participants=departed,
    )
    return EndPlan(mission=updated, grants=tuple(grants), consequences=tuple(consequences))


def complete(
    mission: Mission,
    expected: int,
    *,
    resolved_consequences: frozenset[str],
    all_other_mandatory_work_resolved: bool,
) -> Mission:
    revision(mission, expected)
    if (
        mission.phase != "awaiting_consequences"
        or not all_other_mandatory_work_resolved
        or not set(mission.consequence_ids) <= resolved_consequences
    ):
        raise ValueError(
            "Required consequences cannot be waived or expired by marking a mission complete"
        )
    return changed(mission, phase="complete")
