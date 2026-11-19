"""Saved rank-based Frantic roll and its separately owned printed outcomes."""

from typing import Any, Literal
from uuid import uuid4

from girlframe.engine.m2 import GameState, TagState, shift_status, tier
from girlframe.engine.m3_actor_bonds import change
from girlframe.engine.m3_handler_private_scene import RULES, FranticRoll, PrivateScene
from girlframe.engine.m3_intracadre_marriage import credit, is_ace, is_dog
from girlframe.engine.m3_leviathan_obsession import require_unlocked
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


def _deepen(state: GameState, value: PrivateScene, event: str) -> None:
    changed = change(state, value.handler, value.girl, 1, event)
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))


def _handler_tag(state: GameState, value: PrivateScene, label: str) -> str:
    tag = TagState(
        id=str(uuid4()),
        label=label,
        giver=int(value.girl.entity),
        giver_actor=value.girl,
        observers=(int(value.handler.entity), int(value.girl.entity)),
    )
    state.handler_tags.append(tag)
    return tag.id


def respond(
    game: GameService,
    state: GameState,
    value: PrivateScene,
    step: str,
    text: str,
    effects: tuple[str, ...],
    event: str,
) -> dict[str, Any]:
    owner, handler = int(value.girl.entity), int(value.handler.entity)
    sheet = state.sheets[value.girl.entity]
    if step == "frantic_roll":
        modifier: Literal[-1, 1, 3] = (
            -1 if is_ace(state, owner) else 3 if is_dog(state, owner) else 1
        )
        roll = FranticRoll(faces=game.dice.roll(), modifier=modifier)
        outcome = tier(roll.total)
        if outcome == "high":
            _deepen(state, value, event)
        return dict(
            roll=roll,
            phase={"low": "frantic_care", "mid": "frantic_comfort", "high": "frantic_high"}[
                outcome
            ],
        )
    if value.roll is None:
        raise WorkflowError("Recover the original saved Frantic roll")
    if step == "frantic_comfort":
        credit(state, value.girl, 1, event=event, source="frantic-comfort:" + value.id)
        shift_status(state, owner, -1)
        sheet.revision += 1
        return dict(phase="complete", outcome="frantic_comforted")
    if step == "frantic_decline_comfort":
        return dict(phase="frantic_girl_tag")
    if step in ("frantic_girl_tag", "frantic_handler_tag", "frantic_bond_tag"):
        if not 1 <= len(text.strip()) <= 120:
            raise WorkflowError("Name the actual Tag you give")
        if step == "frantic_handler_tag":
            tag = ChoiceEngine(game).add_tag(
                state, {"data": {"participants": (handler, owner)}}, owner, handler, text.strip()
            )
            tag.giver_actor = value.handler
            return dict(phase="complete", outcome="frantic_mutual_tags", tag=tag.id)
        tag_id = _handler_tag(state, value, text.strip())
        return (
            dict(phase="frantic_handler_tag", handler_tag=tag_id)
            if step == "frantic_girl_tag"
            else dict(phase="complete", outcome="frantic_bond", handler_tag=tag_id)
        )
    if step == "frantic_high":
        if not set(effects) <= {"unmark", "printed_tag"} or len(effects) != len(set(effects)):
            raise WorkflowError("Choose the original Girl's printed optional effects")
        if "unmark" in effects:
            marked = {x.id for x in sheet.identities if x.marked}
            require_unlocked(sheet.identities, marked)
            if marked & set(sheet.sedation_locked):
                raise WorkflowError("Resolve locked Identity marks before this choice")
            for identity in sheet.identities:
                identity.marked = False
            if marked:
                sheet.revision += 1
        return dict(
            phase="complete",
            outcome="frantic_bond",
            effects=effects,
            handler_tag=_handler_tag(state, value, "Dogfucker")
            if "printed_tag" in effects
            else None,
        )
    if step == "frantic_care":
        if not 1 <= len(text.strip()) <= 1200:
            raise WorkflowError("The original Girl writes her own answer")
        return dict(phase="frantic_verdict", account=text.strip())
    if step == "frantic_believe":
        _deepen(state, value, event)
        return dict(phase="frantic_bond_tag")
    if step == "frantic_no_tag":
        return dict(phase="complete", outcome="frantic_bond")
    character = value.girl.incarnation
    if step != "frantic_doubt" or character is None:
        raise WorkflowError("Recover the actual original Girl and Frantic response")
    debt = game.obligation(
        state,
        {"id": value.id},
        "punishment",
        owner,
        handler,
        cause=RULES["Frantic"],
        source_pdf="133",
        character_id=character,
    )
    return dict(phase="frantic_discipline", outcome="frantic_punishment", discipline=debt)
