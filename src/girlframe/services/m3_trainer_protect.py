"""A source-owned Protect continuation for actual incoming battlefield Asset damage."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle import intact_assets, owned_asset
from girlframe.engine.m3_trainer_phrases import Protection, protections
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_trainer_phrases import PROTECT, protected_pair
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

CHOICE = "battle_trainer_protect"


def defer(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    target: ActorRef,
    asset: str,
    foe: ActorRef,
    chooser: int | None,
    occurrence: str,
    event: str,
    stamp: str,
    indirect: bool,
) -> bool:
    active = []
    for record in protections(state).values():
        if record.protected != target or record.scene != action["scene_id"] or record.girl == foe:
            continue
        pair = protected_pair(
            game, c, state, record.girl, target, int(action["channel_id"]), record.scene
        )
        if pair and pair[0].cell == pair[1].cell:
            active.append((record, pair[0].controller))
    if not active:
        return False
    if len(active) > 1:
        raise WorkflowError(
            "GM review is required for simultaneous Protect orders against this blow"
        )
    from girlframe.engine.m3_doctor import require_harm_allowed

    owned_asset(state, target, asset, profiles(c, game.store.campaign_id))
    require_harm_allowed(state, target, foe)
    record, owner = active[0]
    body = dict(
        protection=record.model_dump(mode="json"),
        foe=foe.model_dump(mode="json"),
        chooser=chooser,
        occurrence=occurrence,
        blow_event=event,
        stamp=stamp,
        original_asset=asset,
        indirect=indirect,
    )
    if any(x.get("kind") == "trainer_protect_blow" and x.get("id") == stamp for x in state.facts):
        raise WorkflowError("Resume this blow's original Protect response")
    choice = game.request(c, action, owner, CHOICE, body)
    state.facts.append(
        dict(
            kind="trainer_protect_blow",
            id=stamp,
            action=action["id"],
            choice=choice,
            body=json.dumps(body, sort_keys=True),
            event=event,
        )
    )
    return True


def _proof(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> tuple[Protection, dict[str, Any]]:
    body = json.loads(request["body_json"])
    record = Protection.model_validate(body["protection"])
    pair = protected_pair(
        game, c, state, record.girl, record.protected, int(action["channel_id"]), record.scene
    )
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    activated = c.scalar(
        sa.select(responses.c.event_id)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == record.choice,
            responses.c.event_id == record.event,
            responses.c.actor_id == record.girl.entity,
            choices.c.kind == PROTECT,
        )
    )
    if (
        not activated
        or record.scene != action["scene_id"]
        or record != protections(state).get(record.girl)
        or pair is None
        or pair[0].cell != pair[1].cell
        or str(pair[0].controller) != request["actor_id"]
        or not any(
            x.get("kind") == "trainer_protect_blow"
            and x.get("id") == body["stamp"]
            and x.get("action") == action["id"]
            and x.get("choice") == request["id"]
            and x.get("body") == request["body_json"]
            for x in state.facts
        )
    ):
        raise WorkflowError("Recover the original Protector, target and saved blow")
    return record, body


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    record, _ = _proof(game, c, state, action, request)
    return dict(
        assets=[
            dict(id=x.id, name=x.name)
            for x in intact_assets(state, record.girl, profiles(c, game.store.campaign_id))
        ]
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_battle import _copy, _strict, damage_actor

    _strict(answer, {"fields"})
    record, body = _proof(game, c, state, action, request)
    selected = answer.fields.get("asset")
    if set(answer.fields) != {"asset"} or selected is None:
        raise WorkflowError("Pay the redirected blow with your own undamaged Asset")
    foe = ActorRef.model_validate(body["foe"])
    event = action["data"]["response_event"]
    changed, followups = damage_actor(
        game,
        c,
        state,
        target=record.girl,
        asset_id=selected,
        source_action=action["id"],
        source_work=None,
        event=event,
        actor=foe,
        chooser_controller=body["chooser"],
        occurrence="trainer_protect:" + request["id"],
        indirect=body["indirect"],
        physical_blow=True,
        allow_sprite=False,
    )
    changed.facts.append(
        dict(
            kind="trainer_protect_resolved",
            original=body["stamp"],
            choice=request["id"],
            event=event,
        )
    )
    _copy(state, changed)
    action["data"]["battle"]["followups"].extend(followups)
