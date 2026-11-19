"""An actual later rebellion includes original insurgents without disclosing the sponsor."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_rebel_funding import RULE, fundings, influences
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_rebel_funding import FundingService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_future_saved_rebellion_uses_actual_insurgents_with_private_sponsorship(ledger):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"}),
            )
        )
    )
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN, "funding-world", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    for group in ("assimilated", "actual-insurgents"):
        worlds.faction(
            ADMIN,
            group,
            state(game).revision,
            Faction(id=group, name=group, kind="rebel", cells=((0, 4),)),
        )
    npc = ActorRef(kind="npc", entity="insurgent-speaker")
    roles = NpcRoleService(worlds)
    offer = roles.offer(
        ADMIN,
        "rebel-controller",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Insurgent original",
            jobs=("guard",),
            controller=3,
            cell=(0, 0),
            detail="An original insurgent",
            faction="actual-insurgents",
            revealed=True,
        ),
    )
    roles.respond(OTHER, "accept-own-insurgent", offer["id"], state(game).revision, "accept")
    prepared(strain, game, high=frozenset({"rebellion"}))
    number = 0
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, f"funding-roll-{number}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"funding-cascade-{number}", request.id, 2, state(game).revision, 2)
        number += 1
    selected = strain.choose(
        ADMIN,
        "funding-endgame",
        request.id,
        1,
        state(game).revision,
        5,
        endgame=True,
        faction="assimilated",
    )
    assert selected["rule_id"] == RULE
    endgame = request.id + ":effect"
    inbox = InboxService(ledger)
    effects = EffectService(strain)

    async def native(viewer, number, identity, task, **values):
        click = current(viewer.user_id, number)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        if task == "effect":
            await open_effect(click, effects, identity)
        else:
            card = next(x for x in inbox.items(viewer) if x.identity == identity and x.task == task)
            await InboxView(inbox, viewer.user_id).route(click, card)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm), click.edit_original_response.call_args
        form.values.update(values)
        submitted = current(viewer.user_id, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.followup.send.call_args,
            submitted.edit_original_response.call_args,
        )
        return form.instructions

    asyncio.run(
        native(
            ADMIN,
            43100,
            endgame,
            "m3_rebel_assimilation",
            funded_group=("actual-insurgents",),
            account="SECRET_FUNDING_ACCOUNT",
        )
    )
    after = state(game)
    assert fundings(after)[0].group == "actual-insurgents" and not influences(after)
    assert next(x for x in after.world.factions if x.id == "assimilated").kind == "foundation"
    pending = next(
        x for x in after.strain.requests if x.track == "rebellion" and x.severity == "low"
    )
    strain.dice.face = 1
    strain.roll(ADMIN, "first-funded-roll", pending.id, 1, state(game).revision)
    chosen = strain.choose(ADMIN, "first-funded-choice", pending.id, 2, state(game).revision, 2)
    assert chosen["rule_id"] == "strain.rebellion.low.1.2"
    effect = pending.id + ":effect"
    assert [x.id for x in influences(state(game))] == [pending.id]
    choice = Choice(
        rule_id=chosen["rule_id"], account="The recorded event shows the actual control slip."
    )
    with pytest.raises(WorkflowError, match="actual participation"):
        effects.apply(ADMIN, "cannot-skip-insurgents", effect, 1, state(game).revision, choice)
    asyncio.run(native(ADMIN, 43110, effect, "effect", nominee=(npc.token,)))
    funding = FundingService(strain)
    with pytest.raises(WorkflowError, match="original parties"):
        funding.get(PLAYER, pending.id)
    assert "SECRET_FUNDING_ACCOUNT" not in str(funding.get(OTHER, pending.id))
    with pytest.raises(WorkflowError, match="actual event scene"):
        funding.act(
            OTHER,
            "only-real-scene",
            pending.id,
            state(game).revision,
            900,
            "participate",
            account="Wrong cast",
        )
    change(CastService(ActorService(strain.missions)), OTHER, "join", npc)
    initial_revision = state(game).revision
    account = "PRIVATE_INSURGENT_ACTION"
    lines = asyncio.run(
        native(
            OTHER, 43120, pending.id, "m3_rebel_funding", choice=("participate",), account=account
        )
    )
    assert "sponsor" not in lines and "funding" not in lines
    assert (
        funding.act(
            OTHER, "43121", pending.id, initial_revision, 900, "participate", account=account
        )["decision"]
        == "participate"
    )
    assert funding.get(OTHER, pending.id)["account"] == account
    assert funding.get(ADMIN, pending.id)["account"] == ""
    ledger.engine.dispose()
    assert (
        effects.apply(ADMIN, "actual-control-slip", effect, 1, state(game).revision, choice)[
            "state"
        ]
        == "resolved"
    )
    canon = state(game)
    assert influences(canon)[0].participation and len(canon.refusal_bonuses) == 1
