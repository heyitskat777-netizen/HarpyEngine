"""Original-person Mentor lineage, shared by two explicit rule consumers."""

from typing import Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_mentorship import MentorSet, current_set, records
from girlframe.engine.m3_mentorship import active_mentors as active_mentors
from girlframe.engine.m3_mentorship import is_mentor as is_mentor
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def _creation_mentor(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    required_rule: str = "girl.newgirl.mentor",
) -> tuple[ActorRef, str]:
    sheet = state.sheets.get(learner.entity)
    if learner.kind != "pilot" or sheet is None or sheet.character_id != learner.incarnation:
        raise WorkflowError("Preserve the actual original Newgirl person")
    if not has_rule(sheet, required_rule, "NEWGIRL") or sheet.mentor is None:
        raise WorkflowError("Use the original current Newgirl and her actual assigned Mentor")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    if setup is not None and setup.mentor is not None:
        original = _history(c, game, setup.source_event).sheets.get(learner.entity)
        if (
            original is None
            or original.girl_runtime is None
            or original.girl_runtime.setup != setup
        ):
            raise WorkflowError("Recover the immutable source-owned Mentor assignment")
        mentor, source = setup.mentor, setup.source_event
    else:
        outgoing = (
            next((x for x in sheet.review.bonds if x.outgoing), None) if sheet.review else None
        )
        if outgoing is None or outgoing.counterpart != sheet.mentor:
            raise WorkflowError("Recover the original reviewed Mentor Bond and assignment")
        bond = (
            c.execute(
                sa.select(t.bond_revisions).where(
                    t.bond_revisions.c.campaign_id == game.store.campaign_id,
                    t.bond_revisions.c.id == outgoing.id,
                    t.bond_revisions.c.revision == outgoing.revision,
                )
            )
            .mappings()
            .first()
        )
        if (
            bond is None
            or bond["state"] != "accepted"
            or bond["source_id"] != learner.entity
            or bond["target_id"] != str(sheet.mentor)
            or not bond["mentor_assignment_id"]
        ):
            raise WorkflowError("Recover the genuine accepted original Mentor source")
        histories = c.execute(
            sa.select(t.m2["m2_state_history"].c.body_json)
            .join(
                t.events,
                sa.and_(
                    t.events.c.id == t.m2["m2_state_history"].c.event_id,
                    t.events.c.campaign_id == t.m2["m2_state_history"].c.campaign_id,
                ),
            )
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.character_activated",
                t.events.c.actor_id == str(sheet.mentor),
            )
            .order_by(t.events.c.seq)
        ).scalars()
        original = next(
            (
                s
                for body in histories
                if (s := GameState.model_validate_json(body).sheets.get(str(sheet.mentor)))
                is not None
                and s.source_profile_revision == bond["target_revision"]
            ),
            None,
        )
        if original is None or not original.character_id:
            raise WorkflowError(
                "Activate the actual originally assigned Mentor; never its replacement"
            )
        mentor = ActorRef(kind="pilot", entity=str(sheet.mentor), incarnation=original.character_id)
        source = bond["event_id"]
    original_mentor = state.sheets.get(mentor.entity)
    if (
        mentor == learner
        or mentor.entity != str(sheet.mentor)
        or original_mentor is None
        or original_mentor.character_id != mentor.incarnation
    ):
        raise WorkflowError("Preserve the actual distinct original Mentor person")
    return mentor, source


def original_mentors(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    required_rule: str = "girl.newgirl.mentor",
) -> tuple[tuple[ActorRef, ...], str]:
    value = current_set(state, learner)
    if value is None:
        mentor, source = _creation_mentor(game, c, state, learner, required_rule)
        return (mentor,), source
    sheet = state.sheets.get(learner.entity)
    if (
        sheet is None
        or sheet.character_id != learner.incarnation
        or not has_rule(sheet, required_rule, "NEWGIRL")
    ):
        raise WorkflowError("Use the actual current Newgirl with this rule")
    from girlframe.services.m3_newgirl_sex import prove_mentor_set

    prove_mentor_set(game, c, state, value)
    if not value.mentors or active_mentors(state, learner) != value.mentors:
        raise WorkflowError("Recover every actual original Mentor; never an account replacement")
    return value.mentors, value.source_event


def original_mentor(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    required_rule: str = "girl.newgirl.mentor",
    *,
    selected: ActorRef | None = None,
) -> tuple[ActorRef, str]:
    mentors, source = original_mentors(game, c, state, learner, required_rule)
    if selected is not None:
        if selected not in mentors:
            raise WorkflowError("Choose an actual current source-owned Mentor")
        return selected, source
    if len(mentors) != 1:
        raise WorkflowError("Choose which actual current Mentor performs this action")
    return mentors[0], source


def install_mentors(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    mentors: tuple[ActorRef, ...],
    *,
    session: str,
    event: str,
    reason: Literal["newgirl_sex_group", "newgirl_sex_replacement"],
) -> None:
    """Called by the actual completed intimacy source, inside its atomic event write."""
    value = MentorSet(
        learner=learner, mentors=mentors, source_event=event, session=session, reason=reason
    )
    if (
        not mentors
        or learner in mentors
        or len(set(mentors)) != len(mentors)
        or not event
        or not session
    ):
        raise WorkflowError("Preserve distinct actual Mentor people and their genuine source")
    if any(x.session == session for x in records(state)):
        raise WorkflowError("Preserve the immutable original Mentor-set installation")
    for actor in (learner, *mentors):
        sheet = state.sheets.get(actor.entity)
        if actor.kind != "pilot" or sheet is None or sheet.character_id != actor.incarnation:
            raise WorkflowError("Use actual current original Girl people")
    state.facts.append(dict(kind="mentor_set", id=event, body=value.model_dump_json()))
