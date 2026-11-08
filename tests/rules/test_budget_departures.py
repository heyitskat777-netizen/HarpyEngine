"""Actual mixed NPC departures, original sources and genuine later leader-death consumer."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain import facts
from test_strain_service import ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_departures import Departure
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_budget_departures import DepartureService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_rebel_leader import LeaderService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_genuine_budget_endgame_mixed_departures_and_later_actual_leader_death(ledger):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    from girlframe.services.m3_npc_roles import NpcRoleService

    roles = NpcRoleService(worlds)
    for i, job in enumerate(("journalist", "doctor", "mechanic", "civilian")):
        npc = Npc(
            id="person" + str(i),
            name="Actual person " + str(i),
            controller=3 if i == 0 else 1,
            jobs=(job,),
            detail="A real prior NPC",
            cell=(0, 4) if i == 0 else (0, 0),
            employment="foundation",
        )
        if i == 0:
            invitation = roles.offer(ADMIN, "invite-npc", state(game).revision, npc)
            roles.respond(OTHER, "accept-npc", invitation["id"], state(game).revision, "accept")
        else:
            worlds.npc(ADMIN, "npc" + str(i), state(game).revision, npc)
    worlds.faction(
        ADMIN,
        "group",
        state(game).revision,
        Faction(id="group", name="Actual group", kind="rebel", cells=((0, 4),), leader="person0"),
    )
    with ledger.transaction() as c:
        prior = state(game)
        for i, person in enumerate((2, 1, 3)):
            prior = set_depth(
                prior,
                current_ref(prior, person),
                ActorRef(kind="npc", entity="person" + str(i)),
                1,
                str(uuid4()),
            )
        game.event(c, 1, "prior-actual-bonds", "synthetic.prior_relationships", prior)
    actors = ActorService(strain.missions)
    casts = CastService(actors)
    change(casts, OTHER, "join", ActorRef(kind="npc", entity="person0"))
    strain.configure(
        ADMIN,
        "scenario",
        state(game).revision,
        "barely_hanging_on",
        frozenset({"budget", "rebellion"}),
    )
    period = strain.periods.begin(ADMIN, "begin")
    from girlframe.engine.m3_janus_storage import effective_assets

    baseline = state(game)
    with_void = sum(
        any(x.void for x in effective_assets(baseline, current_ref(baseline, uid)))
        for uid in baseline.order
    )
    strain.prepare(
        ADMIN,
        "prepare",
        period["id"],
        1,
        state(game).revision,
        facts(
            no_girl_void=with_void == 0,
            at_least_half_have_void=2 * with_void >= len(baseline.order),
            all_gorgons_dormant_or_benevolent=True,
            girl_leaked_information=True,
        ),
    )
    work_ids = {}
    for track, option in (("rebellion", 1), ("budget", 7)):
        while True:
            request = next(
                x
                for x in state(game).strain.requests
                if x.track == track and (x.kind == "endgame" or x.severity == "high")
            )
            if request.kind == "endgame":
                break
            strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
            strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
        strain.choose(
            ADMIN,
            str(uuid4()),
            request.id,
            1,
            state(game).revision,
            option,
            endgame=True,
            faction="group" if track == "rebellion" else None,
        )
        work_ids[track] = request.id + ":effect"
    leader = LeaderService(ledger)
    leader.act(
        ADMIN,
        "actual-opportunity",
        work_ids["rebellion"],
        state(game).revision,
        "identify",
        "Real opportunity for this original leader",
        leader="person0",
    )
    service = DepartureService(ledger)
    identity = work_ids["budget"]
    original = state(game)
    old_work = service.view(ADMIN, identity)
    assert {x["id"] for x in old_work["candidates"]} == {"person0", "person1", "person2"}
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)
    selected = tuple(
        Departure(
            actor=ActorRef(kind="npc", entity="person" + str(i)),
            outcome="die" if i == 0 else "quit",
            jobs=() if i == 0 else ("civilian",) if i == 1 else ("mechanic",),
        )
        for i in range(3)
    )
    with pytest.raises(WorkflowError):
        service.apply(
            ADMIN,
            "no-two-person-substitute",
            identity,
            old_work["revision"],
            old_work["work_revision"],
            selected[:2],
            "Not enough actual people",
        )
    assert state(game) == original
    calls = strain.dice.calls, game.dice.calls

    async def native():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        assert item.task == "m3_budget_departures"
        interaction = current(1, 31500)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(interaction, item)
        selector = interaction.edit_original_response.call_args.kwargs["view"]
        assert selector.fields[0].minimum == 3 and selector.fields[0].maximum == 3
        selector.values["people"] = ("person0", "person1", "person2")
        choose = current(1, 31501)
        await selector.confirm.callback(choose)
        assert selector.completed and state(game) == original
        form = choose.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            {
                "outcome:0": ("die",),
                "outcome:1": ("quit",),
                "jobs:1": ("civilian",),
                "outcome:2": ("quit",),
                "jobs:2": ("mechanic",),
                "account": "PRIVATE DEPARTURE ACCOUNT",
            }
        )
        await form.confirm.callback(current(1, 31502))
        assert form.completed

    asyncio.run(native())
    after = state(game)
    npcs = {x.id: x for x in after.world.npcs}
    assert (
        not npcs["person0"].alive
        and npcs["person1"].employment == npcs["person2"].employment == "unemployed"
    )
    assert npcs["person1"].jobs == ("civilian",) and npcs["person2"].jobs == ("mechanic",)
    assert npcs["person3"] == next(x for x in original.world.npcs if x.id == "person3")
    assert after.sheets == original.sheets and after.actor_bonds == original.actor_bonds
    assert depth(after, ActorRef(kind="npc", entity="person0"), current_ref(after, 2)) == 1
    assert after.scene_casts[0].roles == tuple(
        x for x in original.scene_casts[0].roles if x.actor.entity != "person0"
    )
    with pytest.raises(WorkflowError):
        actors.inspect(OTHER, ActorRef(kind="npc", entity="person0"))
    assert (strain.dice.calls, game.dice.calls) == calls
    assert service.apply(
        ADMIN,
        "31502",
        identity,
        old_work["revision"],
        old_work["work_revision"],
        selected,
        "PRIVATE DEPARTURE ACCOUNT",
    ) == dict(id=identity, state="resolved")
    assert state(game) == after
    with ledger.engine.connect() as c:
        assert "PRIVATE DEPARTURE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        work = t.m3["m3_required_work"]
        assert (
            c.scalar(
                sa.select(work.c.state)
                .where(work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            == "resolved"
        )

    async def reopen():
        from girlframe.discord_adapter.m3_budget_departures import open_departures

        card = current(1, 31503)
        await card.response.defer(ephemeral=True)
        await open_departures(card, service, identity)
        data = card.edit_original_response.call_args.kwargs
        assert (
            len(data["embeds"]) == 2
            and data["embeds"][1].description == "PRIVATE DEPARTURE ACCOUNT"
        )
        assert all("Actual person " + str(i) in data["embeds"][0].description for i in range(3))
        assert data["view"] is None

    asyncio.run(reopen())
    assert state(game) == after
    # Actual Endgame death is consumed as a genuine post-opportunity leader death.
    leader.act(
        ADMIN,
        "actual-group-destruction",
        work_ids["rebellion"],
        after.revision,
        "destroy",
        "The actual leader has died",
    )
    assert not next(x for x in state(game).world.factions if x.id == "group").active
