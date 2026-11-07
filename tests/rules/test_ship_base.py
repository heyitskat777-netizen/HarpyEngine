"""Four printed ram outcomes with actual carrier facts, armour, pins and consequences."""

import asyncio
from uuid import uuid4

import pytest
from handler_award_scenario import ordinary_pr_award
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_strain_service import D6
from test_world import gorgon

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireShipBase, open_advancement
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_ship_base as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world import Movement, end_off_duty, update
from girlframe.engine.m3_world_state import Goal, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_ship_base import ShipBaseService, paid, ram_proof
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def interaction(uid=1):
    own = current(uid, int(uuid4().int % 1000000000))
    own.channel_id = 900
    return own


async def submit(own, **values):
    form = own.edit_original_response.call_args.kwargs["view"]
    form.values.update(values)
    confirmed = interaction(own.user.id)
    await form.confirm.callback(confirmed)
    assert form.completed, confirmed.edit_original_response.call_args
    return confirmed


def acquire(service, game):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def run():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_advancement(own, HandlerAdvancementService(service.store), award.id)
        parent = own.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in parent.children if isinstance(x, AcquireShipBase))
        step = interaction()
        await step.response.defer(ephemeral=True)
        await button.callback(step)
        await submit(
            step, base=("base0",), account="My actual held award converts this existing Base"
        )

    asyncio.run(run())
    receipt = rules.acquisitions(state(game))[0]
    assert receipt.base == "base0" and awards.awards(state(game))[0].acquisition == receipt.id
    return receipt


def ready(store, tmp_path, monkeypatch, faces):
    game, worker, gateway = ordinary_pr_award(store, tmp_path, monkeypatch)
    approved(
        store, game, tmp_path, monkeypatch, extra=(rules.RULE, "gorgon.gorgon.collateral-damage")
    )
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=store.policy.m3_approval.subsystems | {"world", "plays", "strain"}
                )
            )
        )
    )
    world = WorldService(MissionService(store))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-crew",
            name="PRIVATE_CREW_PERSON",
            jobs=("guard",),
            detail="Actual existing crew member",
            controller=1,
            cell=(0, 0),
        ),
    )
    threat = gorgon("directed", "actual-ram-threat", cell=(2, 1), revealed=True)
    threat = threat.model_copy(
        update=dict(
            goal=Goal(kind="location", entity_id="base1"),
            assets=tuple(
                x.model_copy(update=dict(damaged=True)) if x.id == threat.protected_asset else x
                for x in threat.assets
            ),
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(canon.world, gorgons=(threat,))
        game.event(c, 1, str(uuid4()), "synthetic.preexisting_threat", canon)
    strain = StrainService(OffDutyService(MissionService(store)), dice=D6(1))
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    service = ShipBaseService(store, dice=Dice(faces))
    receipt = acquire(service, game)
    original = state(game)
    members = [
        (ADMIN, current_ref(original, 1), "body"),
        (PLAYER, current_ref(original, 2), "both"),
        (ADMIN, ActorRef(kind="npc", entity="actual-crew"), "body"),
    ]
    for viewer, actor, parts in members:
        service.board(
            viewer,
            str(uuid4()),
            receipt.id,
            state(game).revision,
            actor,
            parts,
            "My actual original body/owned Frame physically boards this Base",
        )
    before = state(game)
    service.fly(
        ADMIN,
        str(uuid4()),
        receipt.id,
        before.revision,
        (2, 1),
        True,
        "I control the actual ship's fast flight with only its true boarded cargo",
    )
    after = state(game)
    assert rules.base(after, receipt.base).cell == (2, 1)
    assert after.sheets == before.sheets and after.bonds == before.bonds
    girl = next(x for x in after.placements if x.actor.entity == "2")
    bystander = next(x for x in after.placements if x.actor.entity == "3")
    assert girl.girl_cell == girl.frame_cell == (2, 1)
    assert bystander == next(x for x in before.placements if x.actor.entity == "3")
    assert next(x for x in after.world.npcs if x.id == "actual-crew").cell == (2, 1)
    assert next(x for x in after.world.npcs if x.id == "actual-npc").cell == (1, 0)
    with store.engine.connect() as c:
        actual = resolve(
            after,
            current_ref(after, 1),
            profiles(c, store.campaign_id),
            require_current_profile=False,
        )
    assert actual.cell == (2, 1)
    public = world.get(OTHER)
    assert "PRIVATE_CREW_PERSON" not in str(public) and "ship_sources" not in str(public)
    assert "acquisition" not in str(public["world"]["locations"])
    return (
        game,
        service,
        worker,
        gateway,
        receipt,
        ActorRef(kind="gorgon", entity=threat.id),
        strain,
    )


def create_opportunity(game, worker, gateway, store, threat):
    casts = CastService(ActorService(MissionService(store)))
    change(casts, ADMIN, "join", threat)
    game.dice = Dice((4, 4))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=threat,
            trigger_confirmed=True,
            context="My actual Cadre Girl lures this actual threat into the ship's path",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER)):
        answer(game, PLAYER, "mockingbird_risk")
    asset = next(x.id for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("lure", "cover"),
        fields={"lure": asset, "cover": asset},
        text="I actually create the ram opening at the ship",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    return next(x["event"] for x in state(game).facts if x.get("kind") == "engage_maneuver")


def deal_with_ship(game, store, worker, gateway, threat, ship):
    casts = CastService(ActorService(MissionService(store)))
    if not any(r.actor == threat for cast in state(game).scene_casts for r in cast.roles):
        change(casts, ADMIN, "join", threat)
    source = GorgonPlayService(game)
    view = source.preview(ADMIN, 900)
    actual = next(x for x in view["actors"] if x["ref"] == threat.model_dump(mode="json"))
    declaration = Declaration(
        kind="collateral",
        actor=threat,
        assets=(actual["assets"][-1]["id"],),
        actor_sha256=actual["source_sha256"],
        account="The actual pinned threat deals with this ship or wreck",
        reach_confirmed=True,
    )
    root = source.begin(ADMIN, str(uuid4()), 900, view["revision"], declaration)["action_id"]
    tick(worker, gateway, 3)
    with store.engine.connect() as c:
        started = game.action(c, root)["data"]["gorgon_play"]["started"]
    if not started:
        game.roll(ADMIN, str(uuid4()), root)
    if any(x["kind"] == "gorgon_asset_capability" for x in game.choices(ADMIN)):
        answer(
            game,
            ADMIN,
            "gorgon_asset_capability",
            flag=True,
            text="The actual threat has real physical capability and reaches the pinning ship",
        )
    answer(
        game,
        ADMIN,
        "gorgon_collateral",
        options=("structure",),
        fields={"structure": ship},
        text="The actual threat physically deals with the exact pinning ship or wreck",
    )
    tick(worker, gateway, 5)
    assert game.inspect(ADMIN, root)["state"] == "complete"
    assert all(x.released_event for x in state(game).world.ship_pins)


@pytest.mark.parametrize(
    "basis,faces,tier,destroyed",
    [
        ("plain", (2, 3), "low", False),
        ("opportunity", (3, 4), "mid", False),
        ("plain", (6, 6), "high", False),
        ("armoured", (4, 4), "high", True),
    ],
    ids=[
        "low-real-handler-play",
        "cadre-opening-mid-pin",
        "high-armour-loss",
        "spent-armour-high-wreck",
    ],
)
def test_actual_ship_transport_and_distinct_printed_ram_outcome(
    ledger, tmp_path, monkeypatch, basis, faces, tier, destroyed
):
    game, service, worker, gateway, receipt, threat, strain = ready(
        ledger, tmp_path, monkeypatch, faces
    )
    opening = (
        create_opportunity(game, worker, gateway, ledger, threat)
        if basis == "opportunity"
        else None
    )
    before = state(game)
    asset = next(x.id for x in before.world.gorgons[0].assets if not x.damaged)
    key = str(uuid4())
    args = (
        ADMIN,
        key,
        receipt.id,
        before.revision,
        threat,
        basis,
        asset,
        "My actual original Handler rams this threat from the true flying ship controls",
    )
    if basis == "armoured":

        class FailedDice:
            def roll(self):
                raise RuntimeError("actual RNG failure before commit")

        service.dice = FailedDice()
        with pytest.raises(RuntimeError, match="RNG failure"):
            service.ram(*args, opening=opening)
        assert state(game) == before and rules.base(state(game), receipt.base).ship.armoured
        service.dice = Dice(faces)
    result = service.ram(*args, opening=opening)
    rolled = state(game)
    value = next(x for x in rules.records(rolled, rules.Ram) if x.id == result["id"])
    assert (
        value.tier == tier
        and value.modifier == {"plain": 0, "opportunity": 2, "armoured": 4}[basis]
    )
    assert service.dice.calls == 1
    assert (
        service.ram(*args, opening=opening) == result
        and state(game) == rolled
        and service.dice.calls == 1
    )
    with ledger.engine.connect() as c:
        assert paid(game, c, rolled, receipt.id) == receipt
        assert ram_proof(game, c, rolled, value.id) == value
    with pytest.raises(WorkflowError):
        service.menu(OTHER, value.id)
    hull = rules.base(rolled, receipt.base)
    assert (hull.condition == "destroyed") == destroyed
    if tier == "low":
        assert not hull.ship.armoured and value.phase == "awaiting_play"
        plays = HandlerPlayService(ledger)
        source = plays.get(ADMIN, value.low_grant)
        assert source["grant"]["chooser_actor"] is None and source["grant"]["source"] == "required"
        target = current_ref(rolled, 2)
        plays.submit(
            ADMIN,
            str(uuid4()),
            value.low_grant,
            rolled.revision,
            "mess",
            Effect(
                kind="tag",
                target=target,
                tag="Actually shaken by the failed ram",
                account="The actual procedural GM makes this real Play against the original Cadre",
            ),
        )
        completed = next(x for x in rules.records(state(game), rules.Ram) if x.id == value.id)
        assert completed.phase == "complete" and completed.completed_event
        assert any(
            x.label == "Actually shaken by the failed ram" for x in state(game).sheets["2"].tags
        )
    else:
        assert rolled.world.gorgons[0].exposed
        assert next(x for x in rolled.world.gorgons[0].assets if x.id == asset).damaged == (
            tier == "high"
        )
        with pytest.raises(ValueError, match="pinning ship"):
            end_off_duty(
                rolled.world,
                "cannot-depart-pinned",
                (Movement(gorgon=threat.entity, destination=(1, 0)),),
                (),
            )
        deal_with_ship(game, ledger, worker, gateway, threat, receipt.base)
    after = state(game)
    if not destroyed and tier != "high":
        assert rules.base(after, receipt.base).condition == "intact"
        assert not any(
            x.get("kind") == "structure_destroyed_source" and x.get("entity") == receipt.base
            for x in after.facts
        )
        assert not any(
            x.kind == "structure_destroyed" and x.entity == receipt.base
            for x in after.strain.triggers
        )
        old_damage = rules.base(after, receipt.base).ship.damage_count
        period = strain.periods.begin(ADMIN, str(uuid4()))
        rearmed = rules.base(state(game), receipt.base).ship
        assert (
            rearmed.armoured
            and rearmed.rearm_period == period["id"]
            and rearmed.damage_count == old_damage
        )
    else:
        assert not rules.base(after, receipt.base).ship.airborne
        assert any(
            x.kind == "structure_destroyed" and x.entity == receipt.base
            for x in after.strain.triggers
        )
        assert state(game).placements == before.placements and state(game).sheets == before.sheets

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_ship_base" and x.identity == value.id
        )
        own = interaction()
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        assert "Actual Ship-Base ram" in str(own.edit_original_response.call_args)

    asyncio.run(history())
