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
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_items import ItemService, prove_transfer
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("tier", ("mid", "low"), ids=("original-mid", "pocket-money"))
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
