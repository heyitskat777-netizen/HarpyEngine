"""Actual Revolutionary departure waits for the original chosen permission."""

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import (
    REVOLUTIONARY,
    AncillaryIntimacyService,
    records,
)
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_revolutionary_high_source_holds_actual_voluntary_departure(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(REVOLUTIONARY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN,
        "private-revolutionary-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        contacts=(REBEL,),
    )
    victim = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Actual original gear.")

    draft = ancillary.Draft(
        name="Original Revolutionary",
        book="REVOLUTIONARY IDEALIST",
        bond=REBEL,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["REVOLUTIONARY IDEALIST"].assets[:2]),
        frame_assets=tuple(
            gear(x) for x in ancillary.frame_assets("REVOLUTIONARY IDEALIST", "JANUS")[:2]
        ),
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
        "revolutionary-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my own Frame.",
    )
    placement.decide(ADMIN, "confirmed-angel", initial["id"], state(game).revision, True)
    MovementService(game).move(
        OTHER,
        "revolutionary-counterpart-arrives",
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
        "revolutionary-counterpart-exits",
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
        "revolutionary-private",
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
        "original-two-options",
        actual,
        state(game).revision,
        "offer",
        picks=("tag", "remain"),
    )
    service.act(OTHER, "original-choice-of-one", actual, state(game).revision, "remain")
    assert depth(state(game), actor, victim) == 1
    assert records(state(game))[0].step == "revolutionary_release"
    with pytest.raises(WorkflowError, match="permission|permit departure"):
        MovementService(game).move(
            PLAYER,
            "physical-hold",
            state(game).revision,
            900,
            actor,
            (0, 3),
            account="Try to move to the next square.",
        )
    service.act(OTHER, "original-release", actual, state(game).revision, "release")
    actual_movement = MovementService(game).move(
        PLAYER,
        "original-departure",
        state(game).revision,
        900,
        actor,
        (0, 3),
        account="I leave for the next square.",
    )
    assert actual_movement["destination"] == [0, 3]
    assert records(state(game))[0].disposition == "released"
