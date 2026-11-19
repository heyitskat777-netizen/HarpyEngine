"""Use the actual Advocate choice for one Asset, Tag and Status shift."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_handler_private_scene import PrivateScene
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m3_battle import damage_actor
from girlframe.services.onboarding import WorkflowError


def eligible(state: GameState, value: PrivateScene) -> tuple[tuple[str, str], ...]:
    sheet = state.sheets.get(value.girl.entity)
    if sheet is None or sheet.character_id != value.girl.incarnation:
        return ()
    return tuple(
        (x.id, x.name)
        for x in sheet.assets
        if x.family == "girl" and not x.concealed and not x.damaged
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    value: PrivateScene,
    event: str,
    step: str,
    asset: str,
    label: str,
) -> dict[str, Any]:
    if step not in ("advocate_lower", "advocate_raise") or asset not in dict(
        eligible(state, value)
    ):
        raise WorkflowError("Choose a current original Girl Asset available to this Advocate")
    if not 1 <= len(label.strip()) <= 120:
        raise WorkflowError("Name the actual Tag")
    owner, handler = int(value.girl.entity), int(value.handler.entity)
    changed, work = damage_actor(
        game,
        c,
        state,
        target=value.girl,
        asset_id=asset,
        source_action=None,
        source_work=value.id,
        event=event,
        actor=value.handler,
        chooser_controller=handler,
        occurrence="advocate-private:" + value.id,
        physical_blow=False,
    )
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))
    tag = ChoiceEngine(game).add_tag(
        state, {"data": {"participants": (handler, owner)}}, owner, handler, label.strip()
    )
    tag.giver_actor = value.handler
    lower = step == "advocate_lower"
    shift_status(state, owner, -1 if lower else 1)
    return dict(
        phase="advocate_followup" if work else "complete",
        outcome="advocate_lowered" if lower else "advocate_raised",
        damaged_asset=asset,
        tag=tag.id,
        required_work=work,
    )


def pending(game: GameService, c: Connection, value: PrivateScene) -> bool:
    work = t.m3["m3_required_work"]
    for identity in value.required_work:
        status = c.scalar(
            sa.select(work.c.state)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == identity,
            )
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        if status != "resolved":
            return True
    return False
