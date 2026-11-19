"""A Prodigy's high result includes an actual scoped Tag and original NPC reaction."""

import pytest
from test_ancillary_creation import PATRON, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m3_actor_bonds import current_ref, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
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


def test_middle_prodigy_with_actual_ace_moves_from_dog_to_ace(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(PRODIGY,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    cast = CastService(ActorService(missions))

    def create(viewer, book, name, bond):
        invite = creation.invite(ADMIN, name, state(game).revision, viewer.user_id, "base0")

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Actual starting equipment.")

        frame = "SOLDIER_3" if book == "SOLDIER" else "JANUS"
        draft = ancillary.Draft(
            name=name,
            book=book,
            bond=bond,
            frame_catalogue=frame,
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, frame)[:2]),
        )
        made = creation.respond(viewer, name + "-ok", invite["id"], state(game).revision, draft)
        actor = ActorRef.model_validate(made["actor"])
        change(cast, viewer, "join", actor)
        return actor

    soldier_bond = current_ref(state(game), PLAYER.user_id)
    ace = create(OTHER, "SOLDIER", "Actual Ace", soldier_bond)
    other = create(OTHER, "SOLDIER", "Actual Second", soldier_bond)
    actor = create(PLAYER, "PRODIGY", "Actual Dog", current_ref(state(game), OTHER.user_id))
    cadres = AncillaryCadreService(game)
    proposed = cadres.propose(
        ADMIN,
        "actual-cadre",
        900,
        state(game).revision,
        active_handler(state(game)).token,
        (ace.token, other.token, actor.token),
    )
    for viewer, member in ((OTHER, ace), (OTHER, other), (PLAYER, actor)):
        cadres.approve(
            viewer, member.token, proposed["id"], state(game).revision, member.token, True
        )
    assert rank.actual_members(state(game), rank.current(state(game), actor)) == (ace, other, actor)
    placement = ChainedPlacementService(game)
    for viewer, member in ((OTHER, ace), (PLAYER, actor)):
        reading = placement.propose(
            viewer,
            "pose-" + member.token,
            900,
            member,
            state(game).revision,
            "outside_frame",
            "I am outside my original Frame.",
        )
        placement.decide(ADMIN, "see-" + member.token, reading["id"], state(game).revision, True)

    private = AncillaryIntimacyService(game)
    case = private.offer(PLAYER, "with-ace", 900, actor, state(game).revision, ace.token)["id"]
    game.dice = Dice((4, 5))
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
        private.act(viewer, choice + str(viewer.user_id), case, state(game).revision, choice)
    with pytest.raises(WorkflowError, match="unavailable"):
        private.get(OTHER, case)
    assert private.get(ADMIN, case)["become_ace"]
    private.act(ADMIN, "apply-actual-ace", case, state(game).revision, "raise")
    final = state(game)
    assert rank.actual_members(final, rank.current(final, actor)) == (actor, ace, other)
    assert records(final)[0].disposition == "became_ace" and game.dice.calls == 1
