"""The Warboy's private results act on the original Bond and Orders."""

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_intimacy import WARBOY, AncillaryIntimacyService, records
from girlframe.services.m3_ancillary_orders import AncillaryOrderService
from girlframe.services.m3_ancillary_orders import records as order_records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService


@pytest.mark.parametrize("tier", ("high", "low"), ids=("original-high", "automatic-low"))
def test_warboy_private_outcomes_use_actual_bonds(ledger, tmp_path, monkeypatch, tier):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(WARBOY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN,
        "private-warboy-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
    )
    victim = current_ref(state(game), OTHER.user_id)
    peer = current_ref(state(game), PLAYER.user_id)
    handler = active_handler(state(game))

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Actual original gear.")

    draft = ancillary.Draft(
        name="Original independent Warboy",
        book="WARBOY",
        wanted=victim,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["WARBOY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("WARBOY", "JANUS")[:2]),
    )
    created = creation.respond(
        PLAYER,
        "private-original-warboy",
        invitation["id"],
        state(game).revision,
        draft,
    )
    actor = ActorRef.model_validate(created["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    placement = ChainedPlacementService(game)
    initial = placement.propose(
        PLAYER,
        "warboy-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my own Frame.",
    )
    placement.decide(ADMIN, "confirmed-warboy", initial["id"], state(game).revision, True)
    if tier == "low":
        invitation = creation.invite(
            ADMIN,
            "ace-invite",
            state(game).revision,
            OTHER.user_id,
            "city0",
            "group",
            contacts=(REBEL,),
        )
        book = "REVOLUTIONARY IDEALIST"
        ace_draft = ancillary.Draft(
            name="Current independent Ace",
            book=book,
            bond=REBEL,
            frame_catalogue="JANUS",
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
        )
        invited = creation.respond(
            OTHER, "ace-created", invitation["id"], state(game).revision, ace_draft
        )
        ace = ActorRef.model_validate(invited["actor"])
        change(cast, ADMIN, "join", REBEL)
        change(cast, OTHER, "join", ace)
        positioned = placement.propose(
            OTHER, "ace-pose", 900, ace, state(game).revision, "outside_frame", "I step out."
        )
        placement.decide(ADMIN, "confirmed-ace", positioned["id"], state(game).revision, True)
        cadres = AncillaryCadreService(game)
        source = cadres.propose(
            ADMIN, "actual-cadre", 900, state(game).revision, REBEL.token, (ace.token, actor.token)
        )
        for viewer, who in ((ADMIN, "handler"), (OTHER, ace.token), (PLAYER, actor.token)):
            cadres.approve(viewer, who, source["id"], state(game).revision, who, True)
        plays = AncillaryIntimacyService(game)
        game.dice = Dice((2, 3))
        identity = plays.offer(PLAYER, "actual-low", 900, actor, state(game).revision, ace.token)[
            "id"
        ]
        for viewer, choice in (
            (OTHER, "yes"),
            (ADMIN, "yes"),
            (PLAYER, "roll"),
            (PLAYER, "apply"),
            (OTHER, "pass"),
        ):
            plays.act(viewer, choice + str(viewer.user_id), identity, state(game).revision, choice)
        assert depth(state(game), actor, ace) == 1

        orders = AncillaryOrderService(game)
        issued = orders.issue(
            OTHER, "ace-order", 900, ace, state(game).revision, actor.token, "Stay put."
        )["id"]
        game.dice = Dice((6, 6))
        orders.act(PLAYER, "actual-disobey", issued, state(game).revision, "disobey")
        assert orders.get(PLAYER, issued)["warboy_low"]
        result = orders.act(PLAYER, "finalize-roll", issued, state(game).revision, "pass")
        assert result["total"] == 7 and result["stage"] == "review"
        assert not orders.get(ADMIN, issued)["warboy_low"]
        (order,) = order_records(state(game))
        assert order.faces == (6, 6) and game.dice.calls == 1
        return
    MovementService(game).move(
        OTHER,
        "warboy-counterpart-arrives",
        state(game).revision,
        900,
        victim,
        (0, 4),
        frame=True,
        account="I arrive in the same square.",
    )
    physical = PhysicalService(ledger)
    position = physical.preview(OTHER)["position_sha256"]
    physical.operate(
        OTHER,
        "warboy-counterpart-exits",
        state(game).revision,
        CockpitAction(
            actor=victim,
            operation="exit",
            expected_position=position,
            account="I step outside nearby.",
            confirmed=True,
        ),
        channel=900,
    )
    with ledger.transaction() as c:
        canon = state(game)
        for first, second, amount in (
            (victim, peer, 2),
            (victim, actor, 1),
            (victim, handler, 1),
            (peer, actor, 1),
        ):
            canon = set_depth(canon, first, second, amount, "original-fictional-bonds")
        game.event(c, 1, "seed-existing-relationships", "synthetic.relationship_history", canon)
    service = AncillaryIntimacyService(game)
    encounter = service.offer(
        PLAYER, "actual-private-play", 900, actor, state(game).revision, victim.token
    )
    game.dice = Dice((6, 6))
    for viewer, choice, account in (
        (OTHER, "yes", ""),
        (ADMIN, "yes", ""),
        (PLAYER, "roll", ""),
        (PLAYER, "tag", "Too sure of their allies"),
    ):
        service.act(
            viewer,
            choice + str(viewer.user_id),
            encounter["id"],
            state(game).revision,
            choice,
            account=account,
        )
    final = state(game)
    (result,) = records(final)
    assert result.roll.faces == (6, 6) and result.disposition == "counterpart_bonds_weakened"
    assert depth(final, victim, peer) == 1 and depth(final, victim, handler) == 0
    assert depth(final, victim, actor) == 0 and depth(final, peer, actor) == 1
    (tag,) = final.sheets[victim.entity].tags
    assert tag.label == "Too sure of their allies" and tag.giver_actor == actor
    assert set(tag.observers) == {2, 3}
