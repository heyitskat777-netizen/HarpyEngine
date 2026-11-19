"""Abyssal refusal damage uses the original eligible Girl Assets and Helplessness."""

from test_ancillary_creation import HARPY, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import (
    ABYSSAL,
    AncillaryIntimacyService,
    records,
)
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService


def test_abyssal_high_refusal_applies_reachable_asset_damage(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(ABYSSAL,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN,
        "private-abyssal-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        contacts=(HARPY,),
    )
    victim = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Actual original gear.")

    draft = ancillary.Draft(
        name="Original Abyssal Acolyte",
        book="ABYSSAL ACOLYTE",
        bond=HARPY,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["ABYSSAL ACOLYTE"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("ABYSSAL ACOLYTE", "JANUS")[:2]),
    )
    created = creation.respond(
        PLAYER,
        "private-original-angel",
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
        "abyssal-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my own Frame.",
    )
    placement.decide(ADMIN, "confirmed-angel", initial["id"], state(game).revision, True)
    MovementService(game).move(
        OTHER,
        "abyssal-counterpart-arrives",
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
        "abyssal-counterpart-exits",
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
    service = AncillaryIntimacyService(game)
    actual = service.offer(
        PLAYER,
        "abyssal-private",
        900,
        actor,
        state(game).revision,
        victim.token,
    )["id"]
    game.dice = Dice((6, 6))
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
        service.act(viewer, choice + str(viewer.user_id), actual, state(game).revision, choice)
    service.act(
        PLAYER,
        "request",
        actual,
        state(game).revision,
        "ask",
        account="Please give me an original keepsake.",
    )
    service.act(OTHER, "original-refusal", actual, state(game).revision, "refuse")
    current_assets = service.get(PLAYER, actual)["assets"]
    before = state(game).sheets[victim.entity].assets
    assert current_assets and not any(x.damaged for x in before)
    service.act(
        PLAYER, "owned-damage", actual, state(game).revision, "damage", picks=tuple(current_assets)
    )
    final = state(game)
    after = final.sheets[victim.entity].assets
    assert {x.id for x in after if x.damaged} == set(current_assets)
    assert is_helpless(final, victim, actor)
    assert records(final)[0].disposition == "abyssal_damage_applied"
