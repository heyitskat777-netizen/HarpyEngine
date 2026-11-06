"""Actual recursive Rebel Endgame -> native source group -> real world merger."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain import open_work
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Faction, Npc, NpcRecruitment
from girlframe.services.inbox import InboxService
from girlframe.services.m3_rebel_merge import MergerService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_endgame_source_native_merger_memberships_recruitment_and_replay(ledger):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    for identity, cell in (("original-rebels", (0, 4)), ("receiving-rebels", (0, 5))):
        worlds.faction(
            ADMIN,
            identity,
            state(game).revision,
            Faction(id=identity, name=identity, kind="rebel", cells=(cell,)),
        )
    # Synthetic established campaign members, custody and queued city recruitment.
    # Merger must preserve all person/body/hardware facts while redirecting affiliation.
    with ledger.transaction() as c:
        baseline = state(game)
        baseline.world = update(
            baseline.world,
            npcs=(
                Npc(
                    id="member",
                    name="Actual original member",
                    cell=(0, 4),
                    controller=1,
                    jobs=("guard",),
                    detail="An actual original member",
                    faction="original-rebels",
                    secret_factions=("original-rebels",),
                    revealed=True,
                ),
            ),
            pilots=(
                AdversaryPilot(
                    id="rebel-pilot",
                    name="Existing Rebel Pilot",
                    kind="rebel",
                    girl="MOCKINGBIRD",
                    frame="JANUS-B",
                    assets=(),
                    controller=1,
                    cell=(0, 4),
                    faction="original-rebels",
                ),
            ),
            npc_recruitment=(
                NpcRecruitment(
                    id="prior-recruitment",
                    source_work="prior-city-source",
                    city="city0",
                    faction="original-rebels",
                ),
            ),
        )
        game.event(c, 1, "synthetic-established-members", "synthetic.baseline", baseline)
    prepared(strain, game, high=frozenset({"rebellion"}))
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    before = state(game)
    with pytest.raises(WorkflowError, match="active Rebel Group"):
        strain.choose(
            ADMIN, "no-invented-source-group", request.id, 1, before.revision, 2, endgame=True
        )
    assert state(game) == before

    async def select_source():
        interaction = current(1, 29900)
        await interaction.response.defer(ephemeral=True)
        await open_work(interaction, strain, request.id)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert {f.key for f in form.fields} == {"option", "faction"}
        form.values.update(option=("2",), faction=("original-rebels",))
        await form.confirm.callback(current(1, 29901))
        assert form.completed

    asyncio.run(select_source())
    assert state(game).strain.endgames[-1].faction == "original-rebels"
    identity = request.id + ":effect"
    service = MergerService(ledger)
    data = service.view(ADMIN, identity)
    assert data["source"] == "original-rebels"
    before = state(game)
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)
    with pytest.raises(WorkflowError, match="distinct"):
        service.apply(
            ADMIN,
            "not-self-merger",
            identity,
            data["revision"],
            before.revision,
            "original-rebels",
            "Cannot merge with itself",
        )
    assert state(game) == before
    inbox = InboxService(ledger)
    item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
    assert item.task == "m3_rebel_merge"
    account = "Funding was throttled; both actual groups merge into the receiving organization"

    async def native_merge():
        interaction = current(1, 29910)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(interaction, item)
        assert interaction.channel_id == 999
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(receiving=("receiving-rebels",), account=account)
        await form.confirm.callback(current(1, 29911))
        assert form.completed

    asyncio.run(native_merge())
    actual = state(game)
    groups = {x.id: x for x in actual.world.factions}
    assert not groups["original-rebels"].active and groups["original-rebels"].underfunded
    assert groups["receiving-rebels"].active
    assert set(groups["receiving-rebels"].cells) == {(0, 4), (0, 5)}
    assert actual.world.npcs[0] == before.world.npcs[0].model_copy(
        update={"faction": "receiving-rebels", "secret_factions": ("receiving-rebels",)}
    )
    assert actual.world.pilots[0] == before.world.pilots[0].model_copy(
        update={"faction": "receiving-rebels"}
    )
    assert actual.sheets == before.sheets and actual.actor_bonds == before.actor_bonds
    assert actual.world.npc_recruitment[0].faction == "receiving-rebels"
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
            )
            .mappings()
            .first()
        )
        assert row["state"] == "resolved"
    assert (
        service.apply(
            ADMIN, "29911", identity, data["revision"], before.revision, "receiving-rebels", account
        )["state"]
        == "resolved"
    )
    assert state(game) == actual
    worlds.npc(
        ADMIN,
        "actual-next-city-npc",
        actual.revision,
        Npc(
            id="next-city-npc",
            name="Next actual city NPC",
            cell=(0, 4),
            controller=1,
            jobs=("guard",),
            detail="The next introduced NPC from the city",
            revealed=True,
        ),
    )
    final = state(game)
    assert final.world.npcs[-1].secret_factions == ("receiving-rebels",)
    assert not final.world.npc_recruitment
    public = worlds.get(PLAYER, private=False)
    assert "npcs" not in public["world"]
    assert "secret_factions" not in str(public)
