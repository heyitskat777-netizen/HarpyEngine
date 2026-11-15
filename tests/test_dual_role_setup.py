"""One human can own separate Handler authority and an ordinary native Pilot."""

import pytest
from test_creation import selected
from test_creation_review import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_actor_bonds as bonds
from girlframe.engine.creation_details import DesireChoice, StandardChoice
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput, ReleaseApproval, higher
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.m2_game import GameService


def appointed_pilot(store, girl="MOCKINGBIRD"):
    review, creation, handler = ready(store, girl)
    previous = handler.appointment_preview(ADMIN)
    handler.appoint(ADMIN, "dual-appoint", previous["revision"], PLAYER.user_id)
    current = handler.roster(PLAYER)
    assert set(current["pilots"]) == {PLAYER.user_id, OTHER.user_id}
    order = (
        (PLAYER.user_id, OTHER.user_id) if girl == "PRINCESS" else (OTHER.user_id, PLAYER.user_id)
    )
    handler.rank(
        PLAYER,
        "dual-status",
        current["revision"],
        tuple(
            PilotRef(user_id=uid, character_revision=current["pilots"][uid]["revision"])
            for uid in order
        ),
    )
    handler.rulings(PLAYER, "dual-rulings", handler.roster(PLAYER)["revision"], CreationRulings())
    return review, creation, handler


def test_handler_pilot_activation_owned_bond_and_actual_flirt_keep_roles_separate(ledger):
    review, creation, handler = appointed_pilot(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic dual-role regression only",
                reference="fixture; no live campaign approval",
            ),
        }
    )
    current = creation.get(OTHER)
    creation.save(
        OTHER,
        "dual-peer-build",
        current.revision,
        current.character_revision,
        selected().model_copy(update={"shared_tokens": current.draft.shared_tokens}),
    )
    incoming = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    current = creation.get(OTHER)
    review.select_bond(
        OTHER,
        "dual-peer-bond",
        current.revision,
        current.character_revision,
        current.draft,
        incoming.id,
    )
    dice = Dice((2, 3))
    game = GameService(ledger, dice=dice)
    for viewer in (PLAYER, OTHER):
        current = review.get(viewer)
        assert current.sheet.ready_for_rules_review
        assert all(x.code != "pilot" for x in current.sheet.issues)
        assert "/character activate" in current.sheet.issues[-1].message
        review.save(
            viewer,
            "dual-review-" + str(viewer.user_id),
            current.saved_revision,
            current.fingerprint,
        )
        game.activate(viewer, "dual-activate-" + str(viewer.user_id), current.fingerprint)
    actual = state(game)
    assert actual.handler == PLAYER.user_id == handler.view(PLAYER)["handler_id"]
    assert actual.order == (OTHER.user_id, PLAYER.user_id)
    assert actual.sheets["2"].callsign == "SYNTH"
    assert actual.handler_heat == 0 and actual.handler_tags == [] and actual.handler_persona is None
    first, second = bonds.current_ref(actual, 2), bonds.current_ref(actual, 3)
    assert first.kind == second.kind == "pilot"
    assert bonds.depth(actual, first, second) == 1 and "2:3" not in actual.bonds
    assert len(actual.actor_bonds) == 1
    assert higher(actual, 3, 2) and not higher(actual, 2, 3)
    from girlframe.services.shared_setup import SharedSetupService

    assert SharedSetupService(ledger).effective_status(PLAYER, OTHER.user_id) == {
        "higher": False,
        "basis": "current Status",
    }
    # The actual typed Pilot relationship grants the normal Intense benefit.
    elevated = actual.model_copy(deep=True)
    elevated = bonds.change(elevated, first, second, 1, "synthetic-only-intense-native-bond")
    from girlframe.services.m2_choices import ChoiceEngine

    with ledger.engine.connect() as c:
        assert ChoiceEngine(game).flirt_intense(c, elevated, 2, 3)

    game.bind_scene(ADMIN, "dual-bind", 900)
    game.join_scene(PLAYER, "dual-join-own-pilot", 900)
    game.join_scene(OTHER, "dual-join-peer", 900)
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    with ledger.engine.connect() as c:
        cast, legacy = CastService(ActorService(MissionService(ledger)))._current(
            c, state(game), 900
        )
    assert legacy and cast.facilitator == PLAYER.user_id
    assert {x.actor for x in cast.roles} == {first, second}
    action = game.begin(
        PLAYER,
        "dual-pilot-flirt",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            heat=0,
            target=3,
            context="Actual Pilot speaks to the other Girl",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    original = game.inspect(PLAYER, action)["receipt"]
    answer(game, OTHER, "target_flirt", text="The actual other Girl answers privately")
    completed = game.inspect(PLAYER, action)
    assert completed["state"] == "complete" and completed["receipt"] == original
    assert dice.calls == 1
    after = state(game)
    assert bonds.depth(after, first, second) == 0 and "2:3" not in after.bonds
    assert after.handler == 2 and after.handler_heat == 0 and after.handler_tags == []


@pytest.mark.parametrize(
    "girl,role", [("PRINCESS", "princess_handler"), ("VATGROWN", "vatgrown_handler")]
)
def test_dual_role_handler_setup_still_needs_explicit_pilot_acceptance(ledger, girl, role):
    review, _, _ = appointed_pilot(ledger, girl)
    service = CoordinationService(ledger)
    choice = DesireChoice(slots=(1,)) if girl == "VATGROWN" else StandardChoice(slot=1)
    proposal = service.propose(
        PLAYER,
        "dual-role-actual-handler-choice",
        PLAYER.user_id,
        role,
        service.prepare(PLAYER, PLAYER.user_id, role),
        choice,
    )
    assert proposal["state"] == "pending"
    issue = "handler_investor" if girl == "VATGROWN" else role
    assert issue in {x.code for x in review.get(PLAYER).sheet.issues}
    accepted = service.decide(PLAYER, "dual-role-owned-pilot-accepts", proposal["id"], 1, "accept")
    assert accepted == service.decide(
        PLAYER, "dual-role-owned-pilot-accepts", proposal["id"], 1, "accept"
    )
    current = review.get(PLAYER)
    assert current.sheet.ready_for_rules_review
    actual = next(x for x in current.sheet.coordination if x.role == role)
    assert actual.author == actual.owner == PLAYER.user_id
