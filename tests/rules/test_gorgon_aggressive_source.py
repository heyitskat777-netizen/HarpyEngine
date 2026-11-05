"""The actual Aggressive immediate hit precedes the original Defeat modifier and die."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world import update
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_defeat import start_work
from girlframe.services.m3_gorgon_aggressive import AggressiveService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def last_hit(store, monkeypatch):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault"))
    game, worker, gateway, _, _, _ = prepared(store)
    policy = store.policy
    store.policy = policy.model_copy(
        update=dict(
            m3_approval=policy.m3_approval.model_copy(
                update=dict(subsystems=policy.m3_approval.subsystems | {"world"})
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons + (gorgon("aggressive", "real-aggressive", revealed=True),),
        )
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[:-1]:
            asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_battle_damage", canon)
    cast = CastService(ActorService(MissionService(store)))
    foe = ActorRef(kind="gorgon", entity="real-aggressive")
    change(cast, ADMIN, "join", foe)
    battles = BattleService(store)
    data = battles.preview(PLAYER, 900)
    actor = next(
        x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    target = next(x for x in data["actors"] if x["ref"] == foe.model_dump(mode="json"))
    declared = Declaration.model_validate(
        dict(
            play="all_out_assault",
            actor=actor["ref"],
            target=foe,
            attacking_asset=actor["assets"][0]["id"],
            target_asset=target["assets"][0]["id"],
            actor_sha256=actor["sha256"],
            target_sha256=target["sha256"],
            account="Actual opening against this Aggressive Gorgon",
        )
    )
    context = battles.propose(PLAYER, str(uuid4()), data["revision"], 900, declared)
    battles.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        context["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual source battlefield opening",
    )
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            piloting=True,
            target_actor=foe,
            attacking_asset=declared.attacking_asset,
            target_asset=declared.target_asset,
            battle_context=context["id"],
            context=declared.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "battle_low_damage", fields={"asset": frames[-1].id})
    with store.engine.connect() as c:
        rows = [
            dict(x)
            for x in c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == store.campaign_id
                )
            ).mappings()
        ]
    aggressive = next(x["id"] for x in rows if x["kind"] == "aggressive_damage")
    defeat = next(x["id"] for x in rows if x["kind"] == "defeat")
    return game, worker, gateway, action, AggressiveService(store), aggressive, defeat


@pytest.mark.parametrize("take_hit", [True, False])
def test_real_optional_extra_precedes_actual_defeat_roll_and_never_spends_an_extra_rng(
    ledger, monkeypatch, take_hit
):
    game, worker, gateway, parent, service, extra, defeat = last_hit(ledger, monkeypatch)
    before = state(game)
    before_count = sum(x.family == "girl" and not x.damaged for x in before.sheets["2"].assets)
    with pytest.raises(WorkflowError, match="Aggressive|immediate"):
        start_work(game, PLAYER, str(uuid4()), defeat, 900, "The actual Frame has been exhausted")
    assert game.dice.calls == 1 and state(game) == before
    data = service.get(ADMIN, extra)
    with pytest.raises(WorkflowError):
        service.get(PLAYER, extra)
    asset = data["assets"][0]["id"] if take_hit else None
    service.respond(
        ADMIN,
        str(uuid4()),
        extra,
        data["revision"],
        data["game_revision"],
        asset,
        "The actual Gorgon takes the immediate Girl hit"
        if take_hit
        else "The actual Gorgon explicitly declines",
    )
    assert sum(
        x.family == "girl" and not x.damaged for x in state(game).sheets["2"].assets
    ) == before_count - int(take_hit)
    handlers = HandlerPlayService(ledger)
    grant = next(x for x in state(game).handler_plays if x.source_action == parent)
    handlers.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        state(game).revision,
        "brief",
        Effect(kind="brief", account="The real Handler supplies tactical information"),
    )
    modifier = before_count - int(take_hit)
    total = 8 - modifier
    game.dice.faces = (total // 2, total - total // 2)
    child = start_work(
        game, PLAYER, str(uuid4()), defeat, 900, "The actual original Girl now resolves Defeat"
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, child)["receipt"]
    assert (
        receipt["base_modifier"] == modifier and receipt["pre_total"] == 8 and game.dice.calls == 2
    )
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="The original Girl pries out and shelters on this actual battlefield",
    )
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 2
    assert next(x for x in state(game).placements if x.actor.entity == "2").mode == "outside_frame"
