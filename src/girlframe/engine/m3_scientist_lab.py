"""Printed Scientist Project entry and the ordinary Girl Asset installation."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import AssetState, GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_core import install
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_janus_storage import ids as stored_ids

LAB = "handler-playbook.scientist.head-to-the-lab"
PROJECT = "handler-playbook.scientist.the-big-picture"


class LabProposal(Model):
    node: Literal["install_void_asset"] = "install_void_asset"
    additional_effect: Literal["remove_void"] = "remove_void"
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_asset(self) -> "LabProposal":
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Name and describe the new Void Asset")
        return self


class LabAnswer(Model):
    remove_void: str = Field(min_length=1, max_length=100)
    replace: str | None = Field(default=None, min_length=1, max_length=100)


class ProjectStep(Model):
    handler: ActorRef
    target: ActorRef
    period: str
    event: str
    node: Literal["install_void_asset"]
    installed: str
    removed_void_from: str
    replaced: str | None = None


def steps(state: GameState, handler: ActorRef) -> tuple[ProjectStep, ...]:
    return tuple(
        step
        for row in state.facts
        if row.get("kind") == "scientist_project_step"
        and (step := ProjectStep.model_validate_json(row["body"])).handler == handler
    )


def apply_assets(
    state: GameState,
    *,
    target: ActorRef,
    event: str,
    proposal: LabProposal,
    answer: LabAnswer,
) -> tuple[PilotSheet, str]:
    sheet = state.sheets.get(target.entity)
    if target.kind != "pilot" or sheet is None or sheet.character_id != target.incarnation:
        raise ValueError("Choose the actual original Girl attending the laboratory")
    # Stored Void is an independent source. The lab can clear an Asset's own Void.
    stored = stored_ids(state, target)
    altered = next(
        (
            x
            for x in sheet.assets
            if x.id == answer.remove_void and x.family == "girl" and x.void and x.id not in stored
        ),
        None,
    )
    if altered is None or answer.replace == altered.id:
        raise ValueError("Choose an actual separate Void-touched Girl Asset to restore")
    asset = AssetState(
        id=event + ":lab-void-asset",
        family="girl",
        name=proposal.name.strip(),
        description=proposal.description.strip(),
        void=True,
        classification_event=event,
    )
    result = install(sheet, asset, replace=answer.replace, effective_void=stored, state=state)
    restored = next(x for x in result.sheet.assets if x.id == altered.id)
    restored.void = False
    restored.concealed = False
    restored.classification_event = None
    checked = state.model_copy(
        deep=False, update=dict(sheets=state.sheets | {target.entity: result.sheet})
    )
    if all(x.void for x in effective_assets(checked, target) if x.family == "girl"):
        raise ValueError("The actual Void threshold must resolve before this branch can complete")
    return result.sheet, asset.id


def complete(
    state: GameState,
    *,
    actor: ActorRef,
    target: ActorRef,
    period: str,
    event: str,
    proposal: LabProposal,
    answer: LabAnswer,
) -> ProjectStep:
    if actor.kind != "handler" or steps(state, actor):
        raise ValueError("Use the original Scientist and an available printed Project node")
    sheet, asset = apply_assets(state, target=target, event=event, proposal=proposal, answer=answer)
    state.sheets[target.entity] = sheet
    value = ProjectStep(
        handler=actor,
        target=target,
        period=period,
        event=event,
        node=proposal.node,
        installed=asset,
        removed_void_from=answer.remove_void,
        replaced=answer.replace,
    )
    state.facts.append(dict(kind="scientist_project_step", body=value.model_dump_json()))
    return value
