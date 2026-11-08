"""A genuine high Assault causes concrete destruction, Budget and finite owned aftermath."""

import asyncio
from uuid import uuid4

import pytest
from test_battle_pipeline import rolled, table
from test_handler_creation import complete
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_battle import open_battle
from girlframe.engine.m3_collateral import Selection, loss
from girlframe.engine.m3_world import destroy
from girlframe.services.m3_collateral import CollateralService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_quadrant_loss import LossService, require_aftermath_clear
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError


def collateral(store, monkeypatch):
    game, worker, gateway, action, _ = rolled(store, monkeypatch, (6, 6))
    table(game)
    answer(
        game,
        ADMIN,
        "battle_handler",
        options=("collateral_damage",),
        text="The real strike destroys reachable structures",
    )
    with store.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "battle_collateral")
    service = CollateralService(store)
    identity = __import__("json").loads(request["body_json"])["work_id"]
    return service, game, worker, gateway, action, identity, request["id"]


def apply(service, game, identity, structures):
    data = service.get(ADMIN, identity)
    return service.submit(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        Selection(
            structures=structures,
            account="The selected real structures collapse",
            reach="The real adjudicator confirms the bombardment reaches these structures",
        ),
    )


def test_actual_high_collateral_native_structure_destruction_and_budget_survive_replay(
    ledger, monkeypatch
):
    service, game, worker, gateway, action, identity, choice = collateral(ledger, monkeypatch)
    before = state(game)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_battle(interaction, game, choice)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and "structures" in {x.key for x in form.fields}
        form.values.update(
            structures=("base0",),
            account="The bombardment collapses North Base",
            reach="The strike actually reaches this Base",
        )
        await form.confirm.callback(current(1, 7401))
        assert form.completed

    asyncio.run(run())
    after = state(game)
    assert next(x for x in after.world.locations if x.id == "base0").condition == "destroyed"
    assert after.world.territory == before.world.territory
    assert after.sheets == before.sheets
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert len([x for x in after.facts if x.get("kind") == "structure_destroyed_source"]) == 1
    tick(worker, gateway, 5)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update=dict(
            m3_approval=policy.m3_approval.model_copy(
                update=dict(subsystems=policy.m3_approval.subsystems | {"world", "strain"})
            )
        )
    )
    strain = StrainService(OffDutyService(MissionService(ledger)))
    strain.configure(ADMIN, str(uuid4()), after.revision, "business_as_usual", frozenset())
    trigger = state(game).strain.triggers[-1]
    assert (
        trigger.entity == "base0"
        and trigger.kind == "structure_destroyed"
        and trigger.consumed_by is None
    )
    with pytest.raises(WorkflowError):
        service.submit(
            OTHER,
            "forged-collateral",
            identity,
            1,
            before.revision,
            Selection(
                ordinary=("Other user's thing",), account="No permission", reach="Not my choice"
            ),
        )
    assert len(state(game).strain.triggers) == 1


def test_first_last_base_loss_releases_battle_but_real_required_employment_and_new_handler_remain(
    ledger, monkeypatch
):
    service, game, worker, gateway, action, identity, _ = collateral(ledger, monkeypatch)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update=dict(
            m3_approval=policy.m3_approval.model_copy(
                update=dict(subsystems=policy.m3_approval.subsystems | {"playbooks"})
            ),
            owner_m3_rulings=policy.owner_m3_rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    originals = state(game).sheets.copy()
    apply(service, game, identity, ("base0", "base1", "base2"))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    value = next(x for x in state(game).facts if x.get("kind") == "quadrant_loss")
    episode = loss(state(game), value["id"])
    aftermath = LossService(ledger)
    assert episode.phase == "employment" and len(aftermath.tasks(ADMIN)) == 1
    with pytest.raises(WorkflowError, match="aftermath"):
        require_aftermath_clear(state(game))
    data = aftermath.get(ADMIN, episode.id)
    with pytest.raises(WorkflowError):
        aftermath.employment(
            OTHER,
            str(uuid4()),
            episode.id,
            data["revision"],
            data["game_revision"],
            "fired",
            "I cannot make this institutional choice",
        )
    aftermath.employment(
        ADMIN,
        str(uuid4()),
        episode.id,
        data["revision"],
        data["game_revision"],
        "fired",
        "The Foundation actually dismisses this original Handler",
    )
    ended = state(game).handler_archives[-1]
    assert ended.ending == "fired" and ended.alive and ended.custody == "free"
    assert state(game).sheets == originals
    data = aftermath.get(ADMIN, episode.id)
    aftermath.outcome(
        ADMIN,
        str(uuid4()),
        episode.id,
        data["revision"],
        data["game_revision"],
        "new_handler",
        "The Cadre is assigned an actual new Handler",
    )
    tick(worker, gateway, 5)
    creator = HandlerCreationService(ledger)
    creator.start_source(ADMIN, str(uuid4()), episode.id)
    preview = creator.view(ADMIN)
    creator.save(
        ADMIN,
        str(uuid4()),
        preview["revision"],
        preview["appointment"],
        complete(creator, "Scientist"),
        generation=preview["generation"],
        source_work=episode.id,
    )
    preview = creator.view(ADMIN)
    proposals = creator.propose(
        ADMIN, str(uuid4()), preview["revision"], generation=preview["generation"]
    )
    for request in proposals["ids"]:
        proposed = creator.get_agreement(ADMIN, request)
        owner = int(proposed["proposal"]["bond"]["pilot"]["entity"])
        human = PLAYER if owner == 2 else OTHER
        creator.answer(
            human, str(uuid4()), request, creator.get_agreement(human, request)["revision"], True
        )
    preview = creator.view(ADMIN)
    creator.activate(ADMIN, str(uuid4()), preview["revision"], preview["game_revision"], True)
    assert loss(state(game), episode.id).phase == "complete"
    assert state(game).handler_persona.id != ended.actor.incarnation
    require_aftermath_clear(state(game))
    # Later destruction in the already-lost quadrant creates no duplicate job loss.
    result = destroy(state(game).world, "city0", gorgon_cause=False)
    assert [x.kind for x in result.followups] == ["budget_structure_destroyed"]


def setup_playbooks(store):
    policy = store.policy
    store.policy = policy.model_copy(
        update=dict(
            m3_approval=policy.m3_approval.model_copy(
                update=dict(subsystems=policy.m3_approval.subsystems | {"playbooks", "world"})
            ),
            owner_m3_rulings=policy.owner_m3_rulings.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )


def decide(aftermath, game, identity, method, *args, viewer=ADMIN, **kwargs):
    data = aftermath.get(viewer, identity)
    return getattr(aftermath, method)(
        viewer, str(uuid4()), identity, data["revision"], data["game_revision"], *args, **kwargs
    )


def replace_handler(store, aftermath, game, episode):
    creator = HandlerCreationService(store)
    creator.start_source(ADMIN, str(uuid4()), episode)
    data = creator.view(ADMIN)
    creator.save(
        ADMIN,
        str(uuid4()),
        data["revision"],
        data["appointment"],
        complete(creator, "Scientist"),
        generation=data["generation"],
        source_work=episode,
    )
    data = creator.view(ADMIN)
    proposals = creator.propose(
        ADMIN, str(uuid4()), data["revision"], generation=data["generation"]
    )
    for identity in proposals["ids"]:
        value = creator.get_agreement(ADMIN, identity)
        owner = int(value["proposal"]["bond"]["pilot"]["entity"])
        human = PLAYER if owner == 2 else OTHER
        creator.answer(
            human, str(uuid4()), identity, creator.get_agreement(human, identity)["revision"], True
        )
    data = creator.view(ADMIN)
    creator.activate(ADMIN, str(uuid4()), data["revision"], data["game_revision"], True)
    return state(game).handler_persona


def test_actual_foundation_agent_execution_ends_only_source_originals_after_real_sentence(
    ledger, monkeypatch
):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_npc_roles import NpcRoleService
    from girlframe.services.m3_world import WorldService

    service, game, worker, gateway, _, identity, _ = collateral(ledger, monkeypatch)
    setup_playbooks(ledger)
    apply(service, game, identity, ("base0", "base1", "base2"))
    episode = next(x["id"] for x in state(game).facts if x.get("kind") == "quadrant_loss")
    aftermath = LossService(ledger)
    tick(worker, gateway, 5)
    roles = NpcRoleService(WorldService(MissionService(ledger)))
    agent = Npc(
        id="actual-foundation-agent",
        name="Actual agent",
        jobs=("guard",),
        detail="Actual introduced Foundation execution agent",
        controller=3,
        cell=(0, 0),
        revealed=True,
    )
    proposal = roles.offer(ADMIN, str(uuid4()), state(game).revision, agent)
    roles.respond(OTHER, str(uuid4()), proposal["id"], state(game).revision, "accept")
    decide(
        aftermath,
        game,
        episode,
        "employment",
        "imprisoned",
        "The old Handler is actually imprisoned",
    )
    old_handler = state(game).handler_archives[-1]
    assert (
        old_handler.alive
        and old_handler.ending == "imprisoned"
        and old_handler.custody == "foundation_prison"
    )
    executor = ActorRef(kind="npc", entity=agent.id)
    decide(
        aftermath,
        game,
        episode,
        "outcome",
        "execution",
        "The Foundation actually sentences the original Cadre",
        executor,
    )
    before = state(game)
    with pytest.raises(WorkflowError, match="controller"):
        decide(
            aftermath, game, episode, "execute", "I am the OOC administrator, not that actual agent"
        )
    assert state(game) == before
    decide(
        aftermath,
        game,
        episode,
        "execute",
        "The actual separately played Foundation agent carries out this exact sentence here",
        viewer=OTHER,
    )
    final = state(game)
    assert loss(final, episode).phase == "complete" and not final.sheets and not final.order
    assert {x.actor for x in final.career_archives} == set(loss(before, episode).cadre)
    assert all(x.ending == "execution" for x in final.career_archives)
    assert final.world.npcs[-1].alive and final.world.npcs[-1].controller == 3
    require_aftermath_clear(final)


def test_real_reassignment_waits_for_new_handler_map_and_each_original_owner_transport(
    ledger, monkeypatch
):
    from test_world import initial

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import Board

    service, game, worker, gateway, _, identity, _ = collateral(ledger, monkeypatch)
    setup_playbooks(ledger)
    apply(service, game, identity, ("base0", "base1", "base2"))
    episode = next(x["id"] for x in state(game).facts if x.get("kind") == "quadrant_loss")
    aftermath = LossService(ledger)
    decide(
        aftermath, game, episode, "employment", "fired", "The Foundation dismisses the old Handler"
    )
    decide(
        aftermath,
        game,
        episode,
        "outcome",
        "reassigned",
        "The actual surviving Cadre is assigned to a new quadrant",
    )
    tick(worker, gateway, 5)
    persona = replace_handler(ledger, aftermath, game, episode)
    assert loss(state(game), episode).phase == "transport"
    fresh = initial()
    locations = tuple(x.model_copy(update=dict(id="new-" + x.id)) for x in fresh.locations)
    secret = fresh.gorgons[0].model_copy(update=dict(id="new-secret"))
    decide(
        aftermath,
        game,
        episode,
        "new_quadrant",
        "New quadrant",
        Board(minimum=(0, 0), maximum=(9, 9)),
        locations,
        secret,
    )
    source = state(game)
    resources = {uid: sheet.model_dump_json() for uid, sheet in source.sheets.items()}
    for human in (PLAYER, OTHER):
        actor = next(x for x in loss(state(game), episode).cadre if x.entity == str(human.user_id))
        if human == PLAYER:
            data = aftermath.get(human, episode)
            with pytest.raises(WorkflowError, match="controller"):
                aftermath.arrive(
                    ADMIN,
                    str(uuid4()),
                    episode,
                    data["revision"],
                    data["game_revision"],
                    actor,
                    (1, 1),
                    "Cannot attest someone else's body",
                    frame_arrived=True,
                    frame_cell=(1, 1),
                )
        decide(
            aftermath,
            game,
            episode,
            "arrive",
            actor,
            (human.user_id, 1),
            "My actual original Girl and owned Frame arrive by transport",
            viewer=human,
            frame_arrived=True,
            frame_cell=(human.user_id, 1),
        )
        assert state(game).world == source.world
    handler = ActorRef(kind="handler", entity="1", incarnation=persona.id)
    decide(
        aftermath,
        game,
        episode,
        "arrive",
        handler,
        (1, 1),
        "My actual new Handler arrives with the Cadre",
    )
    after = state(game)
    assert loss(after, episode).phase == "complete"
    assert {x.id for x in after.world.locations} == {x.id for x in locations}
    assert after.world.gorgons[0].id == "new-secret"
    assert {uid: sheet.model_dump_json() for uid, sheet in after.sheets.items()} == resources
    for position in after.placements:
        assert position.girl_cell == (int(position.actor.entity), 1)
        assert position.frame_cell == position.girl_cell
        old = next(x for x in source.placements if x.actor == position.actor)
        assert position.vessel_id == old.vessel_id and position.frame_instance == old.frame_instance
    assert any(
        x.get("kind") == "quadrant_world_archive" and x.get("loss") == episode for x in after.facts
    )
    assert any(
        x.get("kind") == "handler_transport_arrived" and x.get("actor") == handler.model_dump_json()
        for x in after.facts
    )
    require_aftermath_clear(after)


def test_real_off_duty_last_base_loss_holds_phase_until_actual_employment_review(ledger):
    from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, recover_both
    from test_world import gorgon

    from girlframe.engine.m3_world import update

    cycle, game, period = prepared(ledger)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    with ledger.transaction() as c:
        canon = state(game)
        bases = [
            x for x in canon.world.locations if x.kind == "base" and x.allegiance == "foundation"
        ]
        threats = tuple(
            gorgon("aggressive", "actual-existing-threat-" + str(i), cell=x.cell)
            for i, x in enumerate(bases)
        )
        canon.world = update(canon.world, gorgons=canon.world.gorgons + threats)
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_base_threats", canon)
    finish_routine(cycle, game, period)
    result = call(cycle, game, ADMIN, period, "finish", movement(game))
    assert result["phase"] != "complete" and state(game).world.completed_off_duty == (period,)
    episode = next(x["id"] for x in state(game).facts if x.get("kind") == "quadrant_loss")
    with ledger.engine.connect() as c:
        work = cycle.periods._pending(c, period)
        assert [x["kind"] for x in work] == ["quadrant_loss"]
    with pytest.raises(WorkflowError, match="aftermath"):
        call(cycle, game, ADMIN, period, "finish", ())
    aftermath = LossService(ledger)
    decide(
        aftermath,
        game,
        episode,
        "employment",
        "retained",
        "The Foundation keeps the actual Handler under explicit review",
    )
    assert loss(state(game), episode).phase == "complete" and not state(game).handler_archives
    call(cycle, game, ADMIN, period, "review_status", (3, 2), "Actual post-loss performance review")
    result = call(cycle, game, ADMIN, period, "finish", ())
    assert result["phase"] == "complete" and state(game).world.completed_off_duty == (period,)
    assert len(state(game).strain.triggers) == len(bases)
    assert all(x.kind == "structure_destroyed" for x in state(game).strain.triggers)
