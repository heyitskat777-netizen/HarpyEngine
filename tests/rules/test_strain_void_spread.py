"""High table source preparation and private actor disclosures."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_strain_effects import effect_form
from girlframe.discord_adapter.m3_world import MapPages
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_civic_directive import CivicService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_rebel_escape_offer import EscapeOfferService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def strain_source(ledger, face, track="void", column=1, *, high=True):
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
    period = prepared(strain, game, high=frozenset({track}) if high else frozenset())
    request = next(x for x in state(game).strain.requests if x.track == track)
    strain.roll(ADMIN, "high-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "high-column", request.id, 2, state(game).revision, column)
    return strain, game, world, period, request.id + ":effect"


def test_spread_area_dice_reopen_without_a_fake_void_consequence(ledger):
    strain, game, world, period, identity = strain_source(ledger, 2)
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
    strain, game, world, _, identity = strain_source(ledger, 5)
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
    strain, game, _, _, identity = strain_source(ledger, 2, "rebellion", 2)
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


@pytest.mark.parametrize("high", [False, True], ids=["city-protest", "rebel-sympathy"])
def test_fictional_director_and_handler_complete_only_their_own_civic_actions(
    ledger, high, tmp_path
):
    strain, game, _, _, identity = strain_source(
        ledger,
        3,
        "rebellion",
        2 if high else 1,
        high=high,
    )
    world = WorldService(strain.missions)
    if high:
        world.faction(
            ADMIN,
            "rebel-faction",
            state(game).revision,
            Faction(id="rebel", name="Rebel group", kind="rebel", cells=((0, 4),)),
        )
    cast = NpcRoleService(world)
    offered = cast.offer(
        ADMIN,
        "director-role",
        state(game).revision,
        Npc(
            id="director",
            name="Original Director",
            jobs=("director",),
            detail="Independent human actor",
            controller=OTHER.user_id,
            cell=(0, 0),
        ),
    )
    cast.respond(OTHER, "accept-director", offered["id"], state(game).revision, "accept")
    service = EffectService(strain)
    build, commit, _ = effect_form(ADMIN, service, identity)
    values = dict(civic_director=("director",), account="The actual civic situation develops.")
    if not high:
        assert "protest_city" in {x.key for x in build({})}
        values["protest_city"] = ("city0",)
    assert "order is pending" in commit(ADMIN, "stage-civic", values)
    assert service.get(ADMIN, identity)["state"] == "pending"
    civic = CivicService(strain)
    with pytest.raises(WorkflowError, match="original participants"):
        civic.get(PLAYER, identity)
    revision = state(game).revision
    faction = "rebel" if high else None
    with pytest.raises(WorkflowError, match="original fictional Director"):
        civic.act(
            ADMIN, "wrong-order", identity, revision, "Not my order", issue=True, faction=faction
        )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        civic.act(
            OTHER, "stale-order", identity, revision - 1, "Old order", issue=True, faction=faction
        )
    ledger.safety(PLAYER, "pause", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        civic.act(
            OTHER, "paused-order", identity, revision, "Paused order", issue=True, faction=faction
        )
    ledger.safety(PLAYER, "resume", ledger.status(PLAYER)["revision"], pause=False)
    revision = state(game).revision

    inbox = InboxService(ledger)
    assert not any(x.task == "m3_civic_directive" for x in inbox.items(PLAYER))
    assert not any(x.task == "m3_civic_directive" for x in inbox.items(ADMIN))

    async def submit_from_inbox(viewer, number, values):
        item = next(x for x in inbox.items(viewer) if x.task == "m3_civic_directive")
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    order = "PRIVATE_ORIGINAL_ORDER"
    selection = dict(account=order)
    if high:
        selection["faction"] = (faction,)
    asyncio.run(submit_from_inbox(OTHER, 96000, selection))
    assert service.get(ADMIN, identity)["state"] == "resolved"
    assert CivicService(strain).get(ADMIN, identity)["order"] == order
    assert (
        CivicService(strain).act(
            OTHER,
            "96001",
            identity,
            revision,
            order,
            issue=True,
            faction=faction,
        )["state"]
        == "awaiting_public_action"
    )
    if high:
        # Verify clean recovery with the saved private order and pending public action.
        backup = tmp_path / "backup" / "civic.sqlite"
        restored = tmp_path / "restore" / "civic.sqlite"
        copy_database(tmp_path / "ledger.db", backup)
        copy_database(backup, restored)
        engine = create_database_engine(Settings(database_url=f"sqlite:///{restored}"))
        try:
            clean_store = OnboardingStore(engine, ledger.policy)
            clean_strain = StrainService(OffDutyService(MissionService(clean_store)))
            reopened = CivicService(clean_strain)
            assert reopened.get(ADMIN, identity)["can_act"]
            assert reopened.get(OTHER, identity)["order"] == order
            assert not any(x.identity == identity for x in InboxService(clean_store).items(PLAYER))
            with clean_store.transaction() as c:
                c.execute(
                    t.members.update()
                    .where(
                        t.members.c.campaign_id == clean_store.campaign_id,
                        t.members.c.user_id == str(OTHER.user_id),
                    )
                    .values(active=False)
                )
            with pytest.raises(WorkflowError):
                reopened.get(OTHER, identity)
            with pytest.raises(WorkflowError):
                reopened.act(OTHER, "96001", identity, revision, order, issue=True, faction=faction)
            assert reopened.get(ADMIN, identity)["order"] == order
        finally:
            engine.dispose()
    with pytest.raises(WorkflowError, match="original addressed Handler"):
        civic.act(OTHER, "wrong-act", identity, state(game).revision, "Made up", issue=False)
    before = world.get(PLAYER)["world"]["civic_conditions"]
    asyncio.run(submit_from_inbox(ADMIN, 96100, dict(account="ACTUAL_PUBLIC_ACT")))
    after = world.get(PLAYER)["world"]["civic_conditions"]
    assert after[:-1] == before
    assert after[-1]["kind"] == ("public_show_of_support" if high else "public_response_to_protest")
    assert order not in str(world.get(PLAYER))
    assert CivicService(strain).get(ADMIN, identity)["action"] == "ACTUAL_PUBLIC_ACT"

    async def see_public_map():
        page = MapPages(world, PLAYER.user_id)
        page.page = 1
        click = current(PLAYER.user_id, 96200)
        await click.response.defer(ephemeral=True)
        await page.show(click)
        contents = click.edit_original_response.call_args.kwargs["content"]
        assert ("public show of support" if high else "public response to a protest") in contents
        assert order not in contents

    asyncio.run(see_public_map())
