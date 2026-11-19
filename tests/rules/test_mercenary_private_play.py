"""The Mercenary may give the actual original participant a Tag after a refused favour."""

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_intimacy import MERCENARY, AncillaryIntimacyService, records
from girlframe.services.m3_ancillary_orders import AncillaryOrderService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_items import ItemService, prove_transfer
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    "tier",
    ("mid", "low", "high", "fee"),
    ids=("original-mid", "pocket-money", "high-refusal", "high-fee"),
)
def test_mercenary_original_private_outcome(ledger, tmp_path, monkeypatch, tier):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(MERCENARY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN, "mercenary-invite", state(game).revision, PLAYER.user_id, "base0", contacts=(PATRON,)
    )
    partner = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Original equipment.")

    draft = ancillary.Draft(
        name="Original Mercenary",
        book="MERCENARY",
        bond=partner,
        patron=PATRON,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["MERCENARY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("MERCENARY", "JANUS")[:2]),
    )
    response = creation.respond(
        PLAYER, "mercenary-create", invitation["id"], state(game).revision, draft
    )
    actor = ActorRef.model_validate(response["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    placement = ChainedPlacementService(game)
    source = placement.propose(
        PLAYER,
        "mercenary-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my Frame.",
    )
    placement.decide(ADMIN, "confirm-prodigy", source["id"], state(game).revision, True)
    physical = PhysicalService(ledger)
    physical.operate(
        OTHER,
        "mercenary-counterpart-exits",
        state(game).revision,
        CockpitAction(
            actor=partner,
            operation="exit",
            expected_position=physical.preview(OTHER)["position_sha256"],
            account="I join her nearby.",
            confirmed=True,
        ),
        channel=900,
    )
    service = AncillaryIntimacyService(game)
    if tier in ("high", "fee"):
        game.dice = Dice((6, 6))
        source = service.offer(
            PLAYER, "actual-high", 900, actor, state(game).revision, partner.token
        )["id"]
        for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
            service.act(viewer, choice + str(viewer.user_id), source, state(game).revision, choice)
        request = "Give me that notebook."
        service.act(OTHER, "actual-request", source, state(game).revision, "ask", account=request)
        if tier == "fee":
            items = ItemService(game)
            cash = items.propose(OTHER, "pledged-cash", partner, "My cash", "A folded note.")["id"]
            items.confirm(
                ADMIN,
                "actual-note",
                cash,
                items.get(ADMIN, cash)["revision"],
                exists=True,
                account="This is actual fictional cash.",
            )
            service.act(
                PLAYER,
                "fee-demand",
                source,
                state(game).revision,
                "recompense",
                account="Pay me one note if I give it to you.",
            )
            service.act(OTHER, "pledge-note", source, state(game).revision, cash)
            with pytest.raises(WorkflowError, match="unavailable"):
                service.get(OTHER, source)
            service.act(
                ADMIN,
                "approve-note",
                source,
                state(game).revision,
                "confirm",
                account="The note is genuine and meets the request.",
            )
        service.act(PLAYER, "open-order", source, state(game).revision, "open_order")
        current = records(state(game))[0]
        orders = AncillaryOrderService(game)
        with pytest.raises(WorkflowError, match="unavailable"):
            orders.get(OTHER, current.high_order)
        assert orders.get(PLAYER, current.high_order)["instruction"] == request
        if tier == "fee":
            orders.act(
                PLAYER,
                "owned-completion",
                current.high_order,
                state(game).revision,
                "follow",
                account="I hand the original notebook over.",
            )
            mid = state(game)
            assert mid.held_items[0].holder == partner and not mid.item_transfers
            assert orders.get(ADMIN, current.high_order)["payment_pending"]
            orders.act(
                ADMIN,
                "settle-fee",
                current.high_order,
                mid.revision,
                "confirm_follow",
                account="The original notebook and agreed cash have changed hands.",
            )
            final = state(game)
            assert final.held_items[0].holder == actor
            assert final.item_transfers[0].source_kind == "mercenary_recompense"
            assert records(final)[0].disposition == "mercenary_order_followed"
            assert game.dice.calls == 1
            return
        game.dice = Dice((4, 5))
        orders.act(PLAYER, "refuse", current.high_order, state(game).revision, "disobey")
        orders.act(PLAYER, "pass-modifiers", current.high_order, state(game).revision, "pass")
        orders.act(
            PLAYER,
            "apply-mid",
            current.high_order,
            state(game).revision,
            "act",
            heat=1,
            account="Keeps her secrets",
        )
        assert records(state(game))[0].step == "mercenary_high_order"
        orders.act(
            ADMIN,
            "review-witnesses",
            current.high_order,
            state(game).revision,
            "unheard",
            account="No relevant authority noticed the refusal.",
        )
        final = state(game)
        assert records(final)[0].disposition == "mercenary_order_refused"
        assert ancillary.find(final, actor).tags[0].label == "Keeps her secrets"
        assert game.dice.calls == 1
        return
    if tier == "low":
        added = creation.invite(ADMIN, "cadre-peer", state(game).revision, OTHER.user_id, "base0")
        peer_draft = ancillary.Draft(
            name="Original second member",
            book="SOLDIER",
            bond=current_ref(state(game), PLAYER.user_id),
            frame_catalogue="SOLDIER_3",
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS["SOLDIER"].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets("SOLDIER", "SOLDIER_3")[:2]),
        )
        joined = creation.respond(
            OTHER, "other-accepts", added["id"], state(game).revision, peer_draft
        )
        peer = ActorRef.model_validate(joined["actor"])
        change(cast, OTHER, "join", peer)
        cadres = AncillaryCadreService(game)
        group = cadres.propose(
            ADMIN,
            "funded-cadre",
            900,
            state(game).revision,
            active_handler(state(game)).token,
            (actor.token, peer.token),
        )
        for viewer, role in ((PLAYER, actor), (OTHER, peer)):
            cadres.approve(viewer, role.token, group["id"], state(game).revision, role.token, True)
        items = ItemService(game)
        money = items.propose(OTHER, "my-cash", partner, "An envelope of cash", "Original cash.")[
            "id"
        ]
        items.confirm(
            ADMIN,
            "confirm-cash",
            money,
            items.get(ADMIN, money)["revision"],
            exists=True,
            account="The original envelope contains actual fictional cash.",
        )

        game.dice = Dice((2, 3))
        work = service.offer(
            PLAYER, "actual-paid-low", 900, actor, state(game).revision, partner.token
        )["id"]
        for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
            service.act(viewer, choice + str(viewer.user_id), work, state(game).revision, choice)
        assert service.get(OTHER, work)["cash"] == {money: "An envelope of cash"}
        service.act(
            OTHER,
            "my-terms",
            work,
            state(game).revision,
            money,
            account="Bring the original notebook here.",
            picks=("Works for scraps",),
        )
        with pytest.raises(WorkflowError, match="unavailable"):
            service.act(
                OTHER, "act-for-other", work, state(game).revision, "done", account="She did it."
            )
        service.act(
            PLAYER, "my-action", work, state(game).revision, "done", account="I bring it over."
        )
        waiting = state(game)
        assert waiting.held_items[0].holder == partner and not ancillary.find(waiting, actor).tags
        service.act(
            ADMIN,
            "verify-payment",
            work,
            waiting.revision,
            "confirm",
            account="I verified the notebook and the actual cash exchanged hands.",
        )
        final = state(game)
        assert rank.actual_members(final, rank.current(final, actor)) == (peer, actor)
        assert final.held_items[0].holder == actor
        assert ancillary.find(final, actor).tags[0].label == "Works for scraps"
        with ledger.engine.connect() as c:
            _, _, transfer = prove_transfer(c, game, final.item_transfers[0].id)
        assert transfer.source_kind == "mercenary_pocket_money" and transfer.action == work
        assert records(final)[0].disposition == "pocket_money_paid" and game.dice.calls == 1
        return
    game.dice = Dice((4, 5))
    identity = service.offer(
        PLAYER,
        "actual-mid",
        900,
        actor,
        state(game).revision,
        partner.token,
    )["id"]
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
        service.act(viewer, choice + str(viewer.user_id), identity, state(game).revision, choice)
    service.act(
        PLAYER,
        "actual-small-favour",
        identity,
        state(game).revision,
        "ask",
        account="Bring me my bag from the other end of the room.",
    )
    assert service.get(OTHER, identity)["step"] == "mercenary_reply"
    with pytest.raises(WorkflowError, match="unavailable"):
        service.act(PLAYER, "refuse-for-other", identity, state(game).revision, "decline")
    service.act(OTHER, "actual-refusal", identity, state(game).revision, "decline")
    assert not state(game).sheets[partner.entity].tags
    service.act(
        PLAYER, "tag-refusal", identity, state(game).revision, "tag", account="Never reciprocates"
    )
    final = state(game)
    assert records(final)[0].disposition == "favour_refused"
    tag = final.sheets[partner.entity].tags[0]
    assert tag.label == "Never reciprocates" and tag.giver_actor == actor
    assert set(tag.observers) == {2, 3}
