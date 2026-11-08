"""A real no-roll Gorgon, rolled response and mandatory Defeat keep one original tree."""

import json
from uuid import uuid4

import pytest
from test_cast_service import change
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration as BattleDeclaration
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

FOURTH = GuildViewer(4, 200, True, False)


def source(store):
    game, worker, gateway, first, old = gorgon_source(store)
    answer(
        game, PLAYER, "gorgon_defend", options=("damage",), text="The first actual incoming blow"
    )
    with store.engine.connect() as c:
        request = next(x for x in game.pending(c, first) if x["kind"] == "gorgon_damage_asset")
    asset = next(
        x["id"]
        for x in game.decision(PLAYER, request["id"])["detail"]["assets"]
        if x["family"] == "girl"
    )
    answer(game, PLAYER, "gorgon_damage_asset", options=(asset,), text="Actual original Girl Asset")
    tick(worker, gateway, 4)
    store.join(FOURTH, "actual-fourth-human-membership")
    roles = NpcRoleService(WorldService(MissionService(store)))
    offered = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-fourth-human-npc",
            name="Actual source guard",
            jobs=("guard",),
            detail="An actual accepted NPC, without a controller Pilot sheet",
            controller=4,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(FOURTH, str(uuid4()), offered["id"], state(game).revision, "accept")
    cast = CastService(ActorService(MissionService(store)))
    change(cast, FOURTH, "join", ActorRef(kind="npc", entity="actual-fourth-human-npc"))
    with store.transaction() as c:
        canon = state(game)
        frame_assets = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for card in frame_assets[:-1]:
            card.damaged = True
        game.event(
            c, 1, str(uuid4()), "synthetic.established_frame_damage_before_next_attack", canon
        )
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    actor = next(x for x in preview["actors"] if x["ref"] == old.actor.model_dump(mode="json"))
    target = next(x for x in preview["actors"] if x["ref"] == old.target.model_dump(mode="json"))
    root = service.begin(
        ADMIN,
        str(uuid4()),
        900,
        preview["revision"],
        Declaration(
            kind="attack",
            actor=old.actor,
            assets=old.assets,
            actor_sha256=actor["source_sha256"],
            target=old.target,
            target_sha256=target["source_sha256"],
            account="The actual next attack against the present original Pilot",
            reach_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    answer(game, PLAYER, "gorgon_defend", options=("play",), text="My actual counter-assault")
    return game, worker, gateway, root, old.actor


def test_real_mixed_role_grandchild_defeat_restores_all_known_receipts_and_finishes_original_tree(
    ledger,
    monkeypatch,
):
    from girlframe.services import m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault"))
    game, worker, gateway, root, gorgon = source(ledger)
    battle = BattleService(ledger)
    data = battle.preview(PLAYER, 900)
    own = next(
        x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    opponent = next(x for x in data["actors"] if x["ref"] == gorgon.model_dump(mode="json"))
    asset = next(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    declaration = BattleDeclaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(own["ref"]),
        target=gorgon,
        attacking_asset=asset,
        target_asset=opponent["assets"][0]["id"],
        actor_sha256=own["sha256"],
        target_sha256=opponent["sha256"],
        account="The original Pilot responds using her last actual intact Frame Asset",
    )
    offered = battle.propose(
        PLAYER, str(uuid4()), state(game).revision, 900, declaration, parent=root
    )
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual original response opening and physical reach",
    )
    game.dice.faces = (1, 1)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            target_actor=gorgon,
            attacking_asset=asset,
            target_asset=declaration.target_asset,
            battle_context=offered["id"],
            parent=root,
            heat=0,
            piloting=True,
            context=declaration.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (ADMIN, PLAYER, OTHER, FOURTH):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, ADMIN, "battle_low_damage", fields={"asset": asset})
    work = json.loads(
        next(x for x in game.choices(PLAYER) if x["kind"] == "battle_defeat")["body_json"]
    )["work_id"]
    from girlframe.engine.m3_defeat import modifier
    from girlframe.services.m3_actors import profiles

    with ledger.engine.connect() as c:
        raw = 8 - modifier(state(game), declaration.actor, profiles(c, ledger.campaign_id))
    game.dice.faces = (raw // 2, raw - raw // 2)
    grandchild = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=child,
            source_work=work,
            heat=0,
            context="Actual final Frame loss in the response",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    receipts = [game.inspect(PLAYER, node)["receipt"] for node in (child, grandchild)]
    assert game.dice.calls == 2 and "4" not in state(game).sheets
    before = state(game).model_dump_json()
    game.abort(ADMIN, str(uuid4()), root)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(ADMIN) if x["id"] == root)
    assert saved["descendants"] == 2 and saved["rolled"] and not saved["cancellable"]
    actions = t.m2["m2_actions"]
    for changed in ({"parent_id": root}, {"channel_id": 901}):
        with ledger.transaction() as c:
            c.execute(actions.update().where(actions.c.id == grandchild).values(**changed))
        with pytest.raises(WorkflowError, match="evidence changed"):
            recovery.recover(ADMIN, str(uuid4()), root, saved["revision"])
        assert state(game).model_dump_json() == before and game.dice.calls == 2
        with ledger.transaction() as c:
            assert game.action(c, child)["state"] == "aborted"
            c.execute(
                actions.update()
                .where(actions.c.id == grandchild)
                .values(parent_id=child, channel_id=900)
            )
    recovery.recover(ADMIN, "actual-grandchild-tree-recovery", root, saved["revision"])
    tick(worker, gateway, 3)
    assert state(game).model_dump_json() == before
    assert [game.inspect(PLAYER, node)["receipt"] for node in (child, grandchild)] == receipts
    assert game.dice.calls == 2
    for viewer in (ADMIN, PLAYER, OTHER, FOURTH):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="Actual cockpit escape",
    )
    canon = state(game)
    grant = next(x for x in canon.handler_plays if x.source_action == child)
    HandlerPlayService(ledger).submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        canon.revision,
        "brief",
        Effect(kind="brief", account="Actual source tactical information after cockpit escape"),
    )
    with ledger.engine.connect() as c:
        assert game.action(c, child)["state"] == game.action(c, grandchild)["state"] == "complete"
        pending = game.pending(c, root)
    if pending:
        answer(
            game,
            ADMIN,
            "gorgon_attack_judge",
            options=("averted",),
            text="Actual source escape avoids the original attack",
        )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.action(c, root)["state"] == "complete"
        assert game.lock(c, 900)["state"] == "released"
    assert game.dice.calls == 2 and "4" not in state(game).sheets
