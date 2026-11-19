"""The Mercenary may give the actual original participant a Tag after a refused favour."""

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import MERCENARY, AncillaryIntimacyService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_mercenary_refused_favour_gives_actual_scoped_tag(ledger, tmp_path, monkeypatch):
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
