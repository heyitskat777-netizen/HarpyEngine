"""The Warboy's private high result weakens actual counterpart Bonds."""

from test_ancillary_creation import enable, scenario
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
from girlframe.services.m3_ancillary_intimacy import WARBOY, AncillaryIntimacyService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService


def test_warboy_private_high_weakens_actual_bonds_and_applies_scoped_tag(
    ledger, tmp_path, monkeypatch
):
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
