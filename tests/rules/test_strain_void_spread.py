"""High table source preparation and private actor disclosures."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_rebel_escape_offer import EscapeOfferService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def high_source(ledger, face, track="void", column=1):
    strain, game = ready(ledger, face=face)
    policy = ledger.policy
    approval = policy.m3_approval
    ledger.policy = policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, "map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    period = prepared(strain, game, high=frozenset({track}))
    request = next(x for x in state(game).strain.requests if x.track == track)
    strain.roll(ADMIN, "high-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "high-column", request.id, 2, state(game).revision, column)
    return strain, game, world, period, request.id + ":effect"


def test_spread_area_dice_reopen_without_a_fake_void_consequence(ledger):
    strain, game, world, period, identity = high_source(ledger, 2)
    service = EffectService(strain)
    strain.dice.face = 1
    assert any(
        x.identity == identity and x.task == "m3_strain_effect"
        for x in InboxService(ledger).items(ADMIN)
    )
    with pytest.raises(WorkflowError):
        service.prepare_spread(PLAYER, "wrong-owner", identity, 1, state(game).revision)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.prepare_spread(ADMIN, "paused", identity, 1, state(game).revision)
    assert strain.dice.calls == 1
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    revision = state(game).revision
    roll = service.prepare_spread(ADMIN, "roll", identity, 1, revision)
    assert roll["spread"]["faces"] == [1, 1]
    reopened = EffectService(strain)
    assert reopened.prepare_spread(ADMIN, "roll", identity, 1, revision) == roll
    assert strain.dice.calls == 3
    with pytest.raises(WorkflowError, match="already saved"):
        reopened.prepare_spread(ADMIN, "reroll", identity, 2, revision)
    with pytest.raises(WorkflowError, match="connected squares"):
        reopened.prepare_spread(ADMIN, "disjoint", identity, 2, revision, cells=((0, 0), (4, 4)))
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        reopened.prepare_spread(ADMIN, "stale", identity, 2, revision - 1, cells=((0, 0), (0, 1)))
    chosen = reopened.prepare_spread(ADMIN, "scope", identity, 2, revision, cells=((0, 0), (0, 1)))
    assert chosen["spread"]["cells"] == [[0, 0], [0, 1]]
    assert reopened.get(ADMIN, identity)["spread"] == chosen["spread"]
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        reopened.apply(
            ADMIN,
            "claim-void",
            identity,
            3,
            state(game).revision,
            Choice(
                rule_id="strain.void.high.2.1", account="The source still needs an exposure ruling"
            ),
        )
    assert reopened.get(ADMIN, identity)["state"] == "pending"
    assert strain.periods.get(ADMIN, period)["phase"] == "preparing"
    assert state(game).world == world


@pytest.mark.parametrize("play", ["recontextualize_void", "reveal_near_disaster"])
def test_revelation_creates_one_notice_for_the_actual_original_audience(ledger, play):
    strain, game, world, _, identity = high_source(ledger, 5)
    service = EffectService(strain)
    game.leave_scene(OTHER, "other-leaves", 900)
    revision = state(game).revision
    effect = Choice(
        rule_id="strain.void.high.5.1",
        account="PRIVATE_REVELATION_FIXTURE",
        revelation_channel=900,
        revelation_play=play,
    )
    with pytest.raises(WorkflowError):
        service.apply(PLAYER, "wrong-revealer", identity, 1, revision, effect)
    answer = service.apply(ADMIN, "reveal", identity, 1, revision, effect)
    assert answer["state"] == "resolved"
    assert service.apply(ADMIN, "reveal", identity, 1, revision, effect) == answer
    reopened = EffectService(strain)
    assert reopened.revelation(PLAYER, identity) == {
        "play": play,
        "account": "PRIVATE_REVELATION_FIXTURE",
    }
    with pytest.raises(WorkflowError, match="original audience"):
        reopened.revelation(OTHER, identity)
    assert any(
        x.identity == identity and x.task == "m3_strain_revelation"
        for x in InboxService(ledger).items(PLAYER)
    )
    assert not any(x.identity == identity for x in InboxService(ledger).items(OTHER))
    assert state(game).world == world


def test_rebel_controller_sends_private_offer_to_one_original_girl(ledger):
    strain, game, _, _, identity = high_source(ledger, 2, "rebellion", 2)
    world = WorldService(strain.missions)
    world.faction(
        ADMIN,
        "rebel-faction",
        state(game).revision,
        Faction(id="rebel", name="Rebel group", kind="rebel", cells=((0, 4),)),
    )
    cast = NpcRoleService(world)
    invited = cast.offer(
        ADMIN,
        "role-offer",
        state(game).revision,
        Npc(
            id="rebel-handler",
            name="Original Rebel Handler",
            jobs=("handler",),
            detail="A separate actor",
            controller=OTHER.user_id,
            cell=(0, 4),
            faction="rebel",
        ),
    )
    cast.respond(OTHER, "role-accept", invited["id"], state(game).revision, "accept")
    effects = EffectService(strain)
    staged = effects.apply(
        ADMIN,
        "stage",
        identity,
        1,
        state(game).revision,
        Choice(
            rule_id="strain.rebellion.high.2.2",
            target="rebel-handler",
            account="A Rebel Handler is ready to contact a Girl in private.",
        ),
    )
    assert staged["state"] == "pending" and effects.get(ADMIN, identity)["awaiting_rebel_offer"]
    svc = EscapeOfferService(strain)
    for viewer in (PLAYER, ADMIN):
        with pytest.raises(WorkflowError, match="original rebel and recipient"):
            svc.get(viewer, identity)
    before = state(game)

    async def send_from_inbox():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(OTHER) if x.task == "m3_rebel_escape_offer")
        click = current(OTHER.user_id, 95640)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, OTHER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(recipient=("2",), account="PRIVATE_ESCAPE_OFFER")
        await form.confirm.callback(current(OTHER.user_id, 95641))
        assert form.completed

    asyncio.run(send_from_inbox())
    reopened = EscapeOfferService(strain)
    assert reopened.send(OTHER, "95641", identity, before.revision, "2", "PRIVATE_ESCAPE_OFFER")[
        "delivered"
    ]
    assert reopened.get(PLAYER, identity)["account"] == "PRIVATE_ESCAPE_OFFER"
    with pytest.raises(WorkflowError):
        reopened.get(ADMIN, identity)
    assert not any(x.task == "m3_rebel_escape_offer" for x in InboxService(ledger).items(ADMIN))
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    after = state(game)
    assert after.sheets == before.sheets and after.world == before.world
