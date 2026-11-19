"""A Prodigy's high result includes an actual scoped Tag and original NPC reaction."""

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import PRODIGY, AncillaryIntimacyService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_prodigy_high_tag_and_actual_scoped_living_npc_bond_reaction(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(PRODIGY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN, "prodigy-invite", state(game).revision, PLAYER.user_id, "base0"
    )
    partner = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Original equipment.")

    draft = ancillary.Draft(
        name="Original Prodigy",
        book="PRODIGY",
        bond=partner,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["PRODIGY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("PRODIGY", "JANUS")[:2]),
    )
    response = creation.respond(
        PLAYER, "prodigy-create", invitation["id"], state(game).revision, draft
    )
    actor = ActorRef.model_validate(response["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    placement = ChainedPlacementService(game)
    source = placement.propose(
        PLAYER,
        "prodigy-outside",
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
        "prodigy-counterpart-exits",
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
    with ledger.transaction() as c:
        canon = set_depth(state(game), actor, PATRON, 1, "original-existing-npc-bond")
        game.event(c, ADMIN.user_id, "fixture-original-npc-bond", "synthetic.npc_bond", canon)

    service = AncillaryIntimacyService(game)
    game.dice = Dice((6, 5))
    encounter = service.offer(
        PLAYER, "actual-high", 900, actor, state(game).revision, partner.token
    )
    identity = encounter["id"]
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
        service.act(viewer, choice + str(viewer.user_id), identity, state(game).revision, choice)
    assert list(service.get(PLAYER, identity)["npc_bonds"]) == [PATRON.token]
    service.act(
        PLAYER,
        "tag-and-bond",
        identity,
        state(game).revision,
        PATRON.token,
        account="Nobody's reserve",
    )
    limited = service.get(ADMIN, identity)
    assert set(limited) == {"revision", "step", "known"}
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, identity)
    service.act(
        ADMIN,
        "actual-npc-reacts",
        identity,
        state(game).revision,
        "confirm",
        account="My NPC shows jealousy by holding back the usual congratulations.",
    )
    final = state(game)
    assert records(final)[0].disposition == "actual_npc_reaction"
    tag = final.sheets[partner.entity].tags[0]
    assert tag.giver_actor == actor and set(tag.observers) == {2, 3}
    assert any(
        x.get("kind") == "prodigy_jealous_bond" and x.get("npc") == PATRON.token
        for x in final.facts
    )
