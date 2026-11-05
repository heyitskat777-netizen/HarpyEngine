"""One actual Strain introduction consumes its mandatory NPC death once, including roles."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_ledger import ADMIN, OTHER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_strain_effects import DependentForm, open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def introduction_source(store, *, director=False):
    strain, game = ready(store, face=4)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    victim = Npc(
        id="actual-city-person",
        name="Actual resident",
        jobs=("director",) if director else ("civilian",),
        detail="The actual original City resident",
        controller=3 if director else 1,
        cell=(0, 4),
        revealed=True,
    )
    if director:
        roles = NpcRoleService(worlds)
        offer = roles.offer(ADMIN, str(uuid4()), state(game).revision, victim)
        roles.respond(OTHER, str(uuid4()), offer["id"], state(game).revision, "accept")
    else:
        worlds.npc(ADMIN, str(uuid4()), state(game).revision, victim)
    cast = CastService(ActorService(strain.missions))
    actor = ActorRef(kind="npc", entity=victim.id)
    change(cast, OTHER if director else ADMIN, "join", actor)
    with store.transaction() as c:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        event = str(uuid4())
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_source_facts", canon, event_id=event)
    period = prepared(strain, game)
    request = next(x for x in state(game).strain.requests if x.track == "void")
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 1)
    service = EffectService(strain)
    identity = request.id + ":effect"
    assert service.get(ADMIN, identity)["rule_id"] == "strain.void.low.4.1"
    return service, game, period, identity, actor


@pytest.mark.parametrize("director", [False, True])
def test_actual_native_introduction_kills_selected_original_once_and_consumes_printed_followup(
    ledger, director
):
    service, game, _, identity, actor = introduction_source(ledger, director=director)
    original_pc = state(game).sheets["3"].model_dump_json()
    prior_context = state(game).director_contexts[-1] if state(game).director_contexts else None

    async def run():
        caller = current(1)
        await caller.response.defer(ephemeral=True)
        await open_effect(caller, service, identity)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, DependentForm) and not await form.interaction_check(current(3))
        chosen = ASSETS["incubus"][:6]
        form.values.update(
            {
                "class": ("aggressive",),
                "type": ("incubus",),
                "assets": chosen,
                "core": (chosen[0],),
                "weakness": "A real source opening while it feeds",
                "name": "Actual emerging Aggressive",
                "cell": ("0,4",),
                "revealed": ("yes",),
                "victim": (actor.entity,),
                "account": "The actual emerging Gorgon kills this resident",
            }
        )
        form.controls()
        victim = next(x for x in form.fields if x.key == "victim")
        assert (actor.entity, "Actual resident") in victim.options
        await form.confirm.callback(current(1, 988881))
        assert form.completed
        await form.confirm.callback(current(1, 988881))

    asyncio.run(run())
    after = state(game)
    assert not next(x for x in after.world.npcs if x.id == actor.entity).alive
    assert after.sheets["3"].model_dump_json() == original_pc
    assert not any(role.actor == actor for cast in after.scene_casts for role in cast.roles)
    consumed = [x for x in after.facts if x.get("kind") == "aggressive_introduction_consumed"]
    assert len(consumed) == 1 and consumed[0]["source_work"] == identity
    assert json.loads(consumed[0]["original_body"])["alive"]
    assert service.get(ADMIN, identity)["state"] == "resolved"
    with ledger.engine.connect() as c:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.event_id == consumed[0]["source_event"]
            )
        )
        assert consumed[0] in json.loads(raw)["facts"]
        assert not c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "aggressive_introduction_npc_death"
            )
        )
    if director:
        assert any(x.get("kind") == "director_body_ended" for x in after.facts)
        assert not after.handler_archives
    if prior_context:
        context = next(x for x in after.director_contexts if x.id == prior_context.id)
        assert not context.active and context.termination_reason == "director_death"
        assert context.identities == prior_context.identities
        assert not after.handler_archives
        assert any(x.get("kind") == "director_body_ended" for x in after.facts)


def test_two_actual_successful_collateral_plays_destroy_same_city_once_with_real_budget(
    ledger, monkeypatch
):
    from test_gorgon_runtime import candidate_source_gate
    from test_m2_game import Gateway, answer, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m3_gorgon_play_state import Declaration
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    # Candidate source availability is isolated to this test; production review stays gated.
    candidate_source_gate.__wrapped__(monkeypatch)
    effects, game, _, identity, _ = introduction_source(ledger)
    data = effects.get(ADMIN, identity)
    from test_world import gorgon

    from girlframe.engine.m3_strain_effects import Choice

    effects.apply(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        Choice(
            rule_id="strain.void.low.4.1",
            account="Actual source Aggressive introduction",
            gorgon=gorgon("aggressive", "actual-city-threat", (0, 4), revealed=True),
            victim="actual-city-person",
        ),
    )
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    world = WorldService(effects.strain.missions)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="unconfirmed-resident",
            name="Other actual resident",
            jobs=("civilian",),
            detail="Known person whose individual fate is not confirmed by the population event",
            controller=1,
            cell=(0, 4),
            revealed=True,
        ),
    )
    actor = ActorRef(kind="gorgon", entity="actual-city-threat")
    cast = CastService(ActorService(effects.strain.missions))
    change(cast, ADMIN, "join", actor)
    driver = GorgonPlayService(game)
    worker, gateway = GameWorker(game), Gateway()
    originals = state(game).sheets.copy()
    roots = []
    for ordinal, effect in enumerate(("electronics", "environment"), start=1):
        data = driver.preview(ADMIN, 900)
        own = next(x for x in data["actors"] if x["ref"] == actor.model_dump(mode="json"))
        root = driver.begin(
            ADMIN,
            str(uuid4()),
            900,
            data["revision"],
            Declaration(
                kind="collateral",
                actor=actor,
                assets=(own["assets"][0]["id"],),
                actor_sha256=own["source_sha256"],
                account="Actual destructive source at this City",
                reach_confirmed=True,
            ),
        )["action_id"]
        roots.append(root)
        tick(worker, gateway, 3)
        answer(
            game,
            ADMIN,
            "gorgon_collateral",
            options=(effect,),
            text="The actual radio is fried"
            if ordinal == 1
            else "Actual terrain buckles violently",
        )
        after = state(game)
        threat = next(x for x in after.world.gorgons if x.id == actor.entity)
        assert threat.collateral_successes == ordinal
        assert next(x for x in after.world.locations if x.id == "city0").condition == (
            "intact" if ordinal == 1 else "destroyed"
        )
        assert game.roll(ADMIN, str(uuid4()), root)["receipt"] is None
        tick(worker, gateway, 5)
    after = state(game)
    assert len(after.world.territory) == 9 and game.dice.calls == 0
    assert after.sheets == originals
    assert next(x for x in after.world.npcs if x.id == "unconfirmed-resident").alive
    destroyed = [
        x
        for x in after.facts
        if x.get("kind") == "structure_destroyed_source" and x.get("entity") == "city0"
    ]
    assert len(destroyed) == 1
    assert len([x for x in after.facts if x.get("kind") == "city_population_casualties"]) == 1
    assert len([x for x in after.facts if x.get("kind") == "gorgon_city_collateral_counted"]) == 2
    assert any(
        x.kind == "structure_destroyed" and x.entity == "city0" for x in after.strain.triggers
    )
