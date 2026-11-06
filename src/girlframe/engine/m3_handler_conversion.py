"""Finite original-Harpy repossession and actual resulting Mockingbird resources."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.creation import AssetChoice, CreationDraft
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import AssetState, GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_void_state import HarpyState
from girlframe.engine.m3_world_state import Cell

RULE = "harpy.harpy.repossession"
KIND = "handler_repossession"


class MockingbirdPackage(Model):
    assets: tuple[AssetChoice, AssetChoice]
    void_asset: str
    girl_bond: ActorRef
    npc_bonds: tuple[tuple[int, ActorRef], ...] = Field(min_length=1, max_length=2)
    appearance: str = Field(min_length=1, max_length=700)

    @model_validator(mode="after")
    def actual_choices(self) -> "MockingbirdPackage":
        if not self.appearance.strip() or not all(x.description.strip() for x in self.assets):
            raise ValueError("Describe both actual resulting Girl Assets and appearance")
        return self


class PhysicalProof(Model):
    event: str
    operation: Literal["extract", "transport"]
    performer: ActorRef
    account: str = Field(min_length=1, max_length=1200)
    destination: Cell | None = None
    review_event: str | None = None
    accepted: bool | None = None


class Repossession(Model):
    id: str
    actor: ActorRef
    handler: ActorRef
    appointment: str
    judge: int
    judge_appointment: str
    capture_event: str
    capture_effect: str
    archive_id: str
    original_frame_owner: ActorRef
    frame_instance: str
    open_event: str
    initial_harpy_json: str
    phase: Literal[
        "captured", "extracted", "transported", "treated", "package", "ready", "complete"
    ] = "captured"
    extraction_event: str | None = None
    transport_event: str | None = None
    treatment_event: str | None = None
    package_event: str | None = None
    review_event: str | None = None
    completion_event: str | None = None
    accounts: dict[str, str] = Field(default_factory=dict)
    physicals: tuple[PhysicalProof, ...] = ()
    destination: Cell | None = None
    extractor: ActorRef | None = None
    package: MockingbirdPackage | None = None
    resulting_actor: ActorRef | None = None
    final_harpy_json: str | None = None
    result_sheet_json: str | None = None
    shutdown: bool = False
    status_position: int | None = None
    award: str | None = None
    award_session: str | None = None
    award_event: str | None = None
    award_blocked: str | None = None


def records(state: GameState) -> tuple[Repossession, ...]:
    return tuple(
        Repossession.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def get(state: GameState, identity: str) -> Repossession:
    value = next((x for x in records(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Harpy repossession")
    return value


def put(state: GameState, value: Repossession) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == KIND and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def completed(state: GameState, identity: str) -> Repossession:
    value = get(state, identity)
    if (
        value.phase != "complete"
        or not value.completion_event
        or value.resulting_actor is None
        or not value.final_harpy_json
        or not value.result_sheet_json
    ):
        raise ValueError("This actual repossession has not installed a Mockingbird")
    return value


def converted_frame_owner(
    state: GameState, owner: ActorRef, instance: str | None = None
) -> ActorRef | None:
    for value in records(state):
        if (
            value.phase == "complete"
            and value.resulting_actor is not None
            and owner in (value.actor, value.original_frame_owner, value.resulting_actor)
            and (instance is None or instance == value.frame_instance)
            and value.final_harpy_json
            and value.result_sheet_json
        ):
            body = HarpyState.model_validate_json(value.final_harpy_json)
            result = PilotSheet.model_validate_json(value.result_sheet_json)
            if (
                body.frame_instance != value.frame_instance
                or body.origin != value.original_frame_owner
                or result.character_id != value.resulting_actor.incarnation
                or result.frame_runtime is None
                or result.frame_runtime.id != value.frame_instance
            ):
                raise ValueError("Preserve the exact original physical Frame conversion source")
            return value.resulting_actor
    return None


def frame_shutdown(state: GameState, actor: ActorRef, instance: str) -> bool:
    return any(
        x.phase == "complete"
        and x.resulting_actor == actor
        and x.frame_instance == instance
        and x.shutdown
        for x in records(state)
    )


def build_sheet(state: GameState, value: Repossession, profile_revision: int) -> PilotSheet:
    """Actual Girl choices replace Harpy capabilities; the physical Frame is not recreated."""
    if value.package is None or value.resulting_actor is None or not value.final_harpy_json:
        raise ValueError("Complete the original human's actual resulting Girl choices")
    body = HarpyState.model_validate_json(value.final_harpy_json)
    archive = next((x for x in state.career_archives if x.id == value.archive_id), None)
    if archive is None or body.original_archive != archive.id or archive.actor != body.origin:
        raise ValueError("Recover the actual original person's Harpy archive")
    original = PilotSheet.model_validate_json(archive.sheet_json)
    draft = CreationDraft(
        girl_playbook="MOCKINGBIRD",
        frame_playbook=original.frame,
        girl_assets=value.package.assets,
        void_asset=value.package.void_asset,
        girl_appearance=value.package.appearance,
    )
    if len(draft.girl_assets) != 2 or not draft.void_asset:
        raise ValueError("Choose two actual Mockingbird Assets, one altered by the Void")
    prefix = "repossession:" + value.id
    # Archived metadata identifies the existing Frame; only its live surviving
    # resources are authoritative. No former purchased person's rules are granted.
    runtime = original.frame_runtime
    if runtime is None:
        runtime = FrameRuntime(
            id=body.frame_instance,
            generation=1,
            source_work=value.id,
            frame_name="Existing repossessed Frame",
        )
    elif runtime.id != body.frame_instance:
        raise ValueError("Recover the same actual original Frame instance")
    frame_assets = [
        AssetState.model_validate_json(x.model_dump_json())
        for x in body.assets
        if x.family == "frame"
    ]
    return PilotSheet(
        owner=body.controller,
        character_id=value.resulting_actor.incarnation,
        revision=1,
        callsign=body.name,
        girl="MOCKINGBIRD",
        frame=original.frame,
        source_fingerprint=prefix,
        source_profile_revision=profile_revision,
        review=original.review,
        identities=[
            IdentityState(id=prefix + ":identity:" + str(i), name=name, slot=i)
            for i, name in enumerate(CATALOG["MOCKINGBIRD"]["identities"])
        ],
        assets=[
            AssetState(
                id=prefix + ":girl:" + str(i),
                family="girl",
                name=x.name,
                description=x.description,
                void=x.name == draft.void_asset,
            )
            for i, x in enumerate(draft.girl_assets)
        ]
        + frame_assets,
        tags=[
            TagState(
                **{k: v for k, v in tag.model_dump().items() if k != "giver_ref"},
                giver_actor=tag.giver_ref,
            )
            for tag in body.tags
        ],
        blocked_plays=list(body.blocked_plays),
        heat=body.heat,
        permissions=body.permissions,
        frame_runtime=runtime,
    )
