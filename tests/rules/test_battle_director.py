"""The actual Director uses Handler rules and never inherits the main Handler's body."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_handler_plays import ready
from test_items import carried_asset, transfer
from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_battle_director as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_director import DirectorService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def source(store):
    handler, game = ready(store)
    roles = NpcRoleService(WorldService(MissionService(store)))
    npc = Npc(
        id="actual-director",
        name="Original Director",
        jobs=("director",),
        detail="A real separately played Director",
        controller=3,
        cell=(0, 0),
        revealed=True,
    )
    offer = roles.offer(ADMIN, "actual-director-offer", state(game).revision, npc)
    roles.respond(OTHER, "actual-director-accept", offer["id"], state(game).revision, "accept")
    asset = next(x for x in state(game).sheets["3"].assets if x.family == "girl")
    carried_asset(game, OTHER, asset)
    actor = ActorRef(kind="npc", entity=npc.id)
    item = transfer(game, current_ref(state(game), 3), actor, "asset:" + asset.id)
    grant = handler.start(ADMIN, "actual-director-hit", state(game).revision, (actor,))["id"]
    handler.submit(
        ADMIN,
        "actual-director-damage",
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="Actual source strike against the Director-owned object",
            target=actor,
            asset=item.asset_id,
        ),
    )
    with store.transaction() as c:
        canon = state(game)
        event = str(uuid4())
        canon = enter(canon, 1, npc.id, "actual-presence-source", ("Nervous", "Composed"), event)
        canon.handler_heat = 3
        canon.director_contexts[0].identities[0].marked = True
        game.event(
            c, 1, "actual-presence", "synthetic.actual_director_presence", canon, event_id=event
        )
    with store.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "director_damage"
            )
        )
    return game, handler, roles, grant, DirectorService(store), work, actor


def test_source_director_owner_injury_replaces_damage_without_aliasing_main_handler_or_player_sheet(
    ledger,
):
    game, handler, _, grant, svc, work, actor = source(ledger)
    before = state(game)
    data = svc.get(OTHER, work)
    with pytest.raises(WorkflowError):
        svc.get(ADMIN, work)
    svc.respond(
        OTHER,
        "actual-owned-director-injury",
        work,
        data["revision"],
        "injury",
        "The actual Director suffers a broken arm and survives",
    )
    after = state(game)
    assert after.handler_heat == before.handler_heat == 3 and after.sheets == before.sheets
    assert after.handler_archives == before.handler_archives == []
    assert after.world.npcs[-1].alive
    assert svc.get(OTHER, work)["injuries"] == [
        "The actual Director suffers a broken arm and survives"
    ]
    assert handler.get(ADMIN, grant)["grant"]["state"] == "complete"


def test_real_director_death_retains_handler_resources_and_requires_real_new_role_acceptance(
    ledger,
):
    game, handler, roles, grant, svc, work, actor = source(ledger)
    before = state(game)
    svc.respond(
        OTHER,
        "actual-director-death",
        work,
        svc.get(OTHER, work)["revision"],
        "death",
        "The actual original Director dies from this source strike",
    )
    after = state(game)
    assert not next(x for x in after.world.npcs if x.id == actor.entity).alive
    context = after.director_contexts[0]
    assert not context.active and context.termination_reason == "director_death"
    assert context.identities == before.director_contexts[0].identities
    assert after.handler_heat == 3 and after.sheets == before.sheets and not after.handler_archives
    assert not any(x.get("kind") == "director_departed" for x in after.facts)
    with ledger.engine.connect() as c:
        replacement = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "director_replacement"
            )
        )
    pending = svc.get(ADMIN, replacement)
    new = Npc(
        id="actual-next-director",
        name="Distinct next Director",
        jobs=("director",),
        detail="Actual separately accepted replacement",
        controller=3,
        cell=(2, 0),
    )
    offered = svc.offer(ADMIN, "actual-next-offer", replacement, pending["revision"], new)
    assert not any(x.id == new.id for x in state(game).world.npcs)
    roles.respond(
        OTHER, "actual-next-human-accept", offered["role_offer"], state(game).revision, "accept"
    )
    assert svc.get(ADMIN, replacement)["state"] == "resolved"
    saved = state(game)
    assert next(x for x in saved.world.npcs if x.id == new.id).alive
    assert saved.handler_heat == 3 and not saved.director_contexts[0].active
    assert handler.get(ADMIN, grant)["grant"]["state"] == "complete"


def test_actual_other_living_director_preserves_existing_context_without_granting_new_identities(
    ledger,
):
    game, _, _, _, _, _, actor = source(ledger)
    canon = state(game)
    npc = Npc(
        id="other-real-director",
        name="Other Director",
        jobs=("director",),
        detail="Actual second body",
        controller=2,
        cell=(0, 0),
    )
    canon.world = canon.world.model_copy(update={"npcs": canon.world.npcs + (npc,)})
    canon = enter(canon, 1, npc.id, "other-actual-presence", (), "other-actual-source")
    before = canon.director_contexts[0].model_dump_json()
    changed = rules.die(canon, actor, "real-death", "The original Director actually dies")
    assert changed.director_contexts[0].active
    assert changed.director_contexts[0].directors == (npc.id,)
    assert changed.director_contexts[0].identities == canon.director_contexts[0].identities
    assert canon.director_contexts[0].model_dump_json() == before


def director_battle_source(store, monkeypatch, faces=(6, 6)):
    from test_m2_game import Gateway, pass_tags, tick
    from test_physical_operations import place

    import girlframe.services.m2_game as shared
    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_cast import CastService

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    game, handler, _, _, director, work, target = source(store)
    director.respond(
        OTHER,
        "first-owned-injury",
        work,
        director.get(OTHER, work)["revision"],
        "injury",
        "The original source hit injures this actual Director",
    )
    with store.transaction() as c:
        canon = place(state(game), 2)
        game.event(c, 1, "actual-battle-body", "synthetic.state", canon)
    casting = CastService(ActorService(MissionService(store)))
    view = casting.view(OTHER, 900)
    casting.change(
        OTHER,
        "director-enters-source-scene",
        900,
        view["game_revision"],
        view["cast_revision"],
        "join",
        target,
    )
    view = casting.view(OTHER, 900)
    casting.change(
        OTHER,
        "director-owned-adjudication",
        900,
        view["game_revision"],
        view["cast_revision"],
        "adjudicate",
        target,
    )
    battle = BattleService(store)
    data = battle.preview(__import__("test_ledger").PLAYER, 900)
    actor = next(
        x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    opposing = next(x for x in data["actors"] if x["ref"] == target.model_dump(mode="json"))
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=target,
        attacking_asset=actor["assets"][0]["id"],
        target_asset=opposing["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=opposing["sha256"],
        account="The actual source opening against the Director-held object",
    )
    from test_ledger import PLAYER

    offered = battle.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        offered["id"],
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Procedural GM confirms the real opening and range",
    )
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=offered["id"],
            context=declaration.account,
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, action, target, director


def test_actual_selected_director_owns_fiction_choice_and_scoped_tag_not_procedural_gm(
    ledger, monkeypatch
):
    from test_battle_pipeline import table
    from test_ledger import PLAYER
    from test_m2_game import answer

    game, _, _, action, _, director = director_battle_source(ledger, monkeypatch)
    table(game)
    request = next(x for x in game.choices(OTHER) if x["kind"] == "battle_handler")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            "no-gm-proxy",
            request["id"],
            request["revision"],
            __import__("girlframe.engine.m2", fromlist=["ChoiceAnswer"]).ChoiceAnswer(
                options=("handler_play",)
            ),
        )
    answer(game, OTHER, "battle_handler", options=("handler_play",))
    canon = state(game)
    grant = next(x for x in canon.handler_plays if x.source_action == action)
    assert grant.chooser_controller == 3 and grant.chooser_actor is None
    handler = __import__(
        "girlframe.services.m3_handler_plays", fromlist=["HandlerPlayService"]
    ).HandlerPlayService(ledger)
    handler.submit(
        OTHER,
        "actual-scoped-director-tag",
        grant.id,
        canon.revision,
        "mess",
        Effect(
            kind="tag",
            account="Actual printed scoped Director consequence",
            target=current_ref(canon, 2),
            tag="Director noticed",
        ),
    )
    tagged = next(x for x in state(game).sheets["2"].tags if x.label == "Director noticed")
    assert tagged.giver == 3 and tagged.gm_setter_grant == grant.id and tagged.giver_actor is None
    with ledger.engine.connect() as c:
        required = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.kind == "director_damage")
                .order_by(t.m3["m3_required_work"].c.revision.desc())
            )
            .mappings()
            .all()
        )
        latest = {}
        for row in required:
            if row["id"] not in latest or latest[row["id"]]["revision"] < row["revision"]:
                latest[row["id"]] = row
        pending = next(x for x in latest.values() if x["state"] == "pending")
    director.respond(
        OTHER,
        "second-source-injury",
        pending["id"],
        pending["revision"],
        "injury",
        "The actual opposing Asset hit causes another injury",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
