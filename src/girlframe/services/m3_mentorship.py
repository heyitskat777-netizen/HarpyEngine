"""Original-person Mentor lineage, shared by two explicit rule consumers."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def original_mentor(
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
