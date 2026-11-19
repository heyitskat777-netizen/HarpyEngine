"""A Soldier's private results apply the original Cadre and refusal consequences."""

import json

import pytest
from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_intimacy import SOLDIER, AncillaryIntimacyService, records
from girlframe.services.m3_ancillary_orders import AncillaryOrderService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService


@pytest.mark.parametrize("tier", ("mid", "low"), ids=("original-middle", "actual-low"))
def test_soldier_private_outcomes_in_actual_cadre(
    ledger,
    tmp_path,
    monkeypatch,
    tier,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(SOLDIER,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    cast_service = CastService(ActorService(missions))
    partner = current_ref(state(game), OTHER.user_id)

    def create(viewer, book, name, bond):
        invitation = creation.invite(
            ADMIN,
            "invite-" + name,
            state(game).revision,
            viewer.user_id,
            "base0",
        )

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original actual gear.")

        frame = "SOLDIER_3" if book == "SOLDIER" else "JANUS"
        data = ancillary.Draft(
            book=book,
            name=name,
            bond=bond,
            frame_catalogue=frame,
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, frame)[:2]),
        )
        created = creation.respond(
            viewer, "create-" + name, invitation["id"], state(game).revision, data
        )
        actor = ActorRef.model_validate(created["actor"])
        change(cast_service, viewer, "join", actor)
        return actor

    soldier = create(PLAYER, "SOLDIER", "Original Soldier", partner)
    prodigy = create(OTHER, "PRODIGY", "Original Prodigy", current_ref(state(game), PLAYER.user_id))
    third = (
        create(OTHER, "SOLDIER", "Original Third", current_ref(state(game), PLAYER.user_id))
        if tier == "low"
        else None
    )
    ranks = AncillaryCadreService(game)
    handler = active_handler(state(game))
    group = ranks.propose(
        ADMIN,
        "formation",
        900,
        state(game).revision,
        handler.token,
        (prodigy.token, soldier.token) + ((third.token,) if third else ()),
    )
    for viewer, actor in ((OTHER, prodigy), (PLAYER, soldier)):
        ranks.approve(
            viewer, "join-" + actor.token, group["id"], state(game).revision, actor.token, True
        )
    if third is not None:
        ranks.approve(OTHER, "join-third", group["id"], state(game).revision, third.token, True)

    placement = ChainedPlacementService(game)
    draft = placement.propose(
        PLAYER,
        "soldier-outside",
        900,
        soldier,
        state(game).revision,
        "outside_frame",
        "I am outside my Frame.",
    )
    placement.decide(ADMIN, "actual-placement", draft["id"], state(game).revision, True)
    if tier == "low":
        placed = placement.propose(
            OTHER,
            "prodigy-outside",
            900,
            prodigy,
            state(game).revision,
            "outside_frame",
            "I meet her outside my own Frame.",
        )
        placement.decide(ADMIN, "actual-prodigy", placed["id"], state(game).revision, True)
        private = AncillaryIntimacyService(game)
        game.dice = Dice((2, 3))
        work = private.offer(
            PLAYER, "actual-low", 900, soldier, state(game).revision, prodigy.token
        )["id"]
        for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
            private.act(viewer, choice + str(viewer.user_id), work, state(game).revision, choice)
        private.act(PLAYER, "go-dog", work, state(game).revision, "apply")
        ranked = state(game)
        assert cadre.actual_members(ranked, cadre.current(ranked, soldier)) == (
            prodigy,
            third,
            soldier,
        )
        (tag,) = ancillary.find(ranked, soldier).tags
        assert tag.label == "Good Soldier" and records(ranked)[0].tag == tag.id

        with ledger.transaction() as c:
            body = state(game)
            body.facts.append(
                dict(
                    kind="recorded_handler_recovery_position",
                    actor=handler.model_dump_json(),
                    cell=json.dumps([0, 0]),
                )
            )
            game.event(
                c, ADMIN.user_id, "handler-present", "synthetic.actual_handler_position", body
            )
        change(cast_service, ADMIN, "join", handler)
        orders = AncillaryOrderService(game)
        order = orders.issue(
            ADMIN, "original-order", 900, handler, state(game).revision, soldier.token, "Stand by."
        )["id"]
        game.dice = Dice((4, 4))
        orders.act(PLAYER, "actual-refusal", order, state(game).revision, "disobey")
        assert orders.get(PLAYER, order)["good_soldier"]
        settled = orders.act(PLAYER, "no-tag-mark", order, state(game).revision, "pass")
        assert settled["total"] == 7 and settled["stage"] == "review"
        assert game.dice.calls == 1
        return

    physical = PhysicalService(ledger)
    physical.operate(
        OTHER,
        "other-exits",
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
    game.dice = Dice((4, 4))
    actual = service.offer(PLAYER, "middle", 900, soldier, state(game).revision, partner.token)[
        "id"
    ]
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll"), (PLAYER, "deepen")):
        service.act(viewer, choice + str(viewer.user_id), actual, state(game).revision, choice)
    final = state(game)
    assert depth(final, soldier, partner) == 2
    assert cadre.actual_members(final, cadre.current(final, soldier)) == (soldier, prodigy)
    assert records(final)[0].disposition == "soldier_advanced"
