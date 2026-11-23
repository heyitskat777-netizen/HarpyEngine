"""Confirm the assembled Activity lab and training forms through real Off-Duty effects."""

import pytest
from off_duty_review import OffDutyReview
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate, prepared
from test_scientist_lab import create_scientist
from test_trainer_phrases import create_trainer

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_scientist_lab import steps
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("kind", ("scientist_lab", "trainer_conditioning"))
def test_handler_signature_keeps_both_original_attestations_and_files_the_effect(ledger, kind):
    science = kind == "scientist_lab"

    def during_setup(game):
        if science:
            create_scientist(ledger)
        else:
            create_trainer(ledger, start_with_speak=False)

    cycle, game, period = prepared(ledger, before_period=during_setup)
    if science:
        with ledger.transaction() as connection:
            canonical = state(game)
            asset = next(x for x in canonical.sheets["3"].assets if x.family == "girl")
            asset.void = asset.concealed = True
            game.event(connection, OTHER.user_id, "fixture-void", "synthetic.lab", canonical)
    activate(cycle, game, period)
    desk = OffDutyReview(cycle)

    def view(viewer):
        return desk.view(viewer, cycle.review(viewer, period))

    def submit(viewer, key, action, data):
        review = cycle.review(viewer, period)
        return desk.perform(
            (viewer, key, period, review["revision"], review["game_revision"]), action, data
        )

    assert kind in view(ADMIN)["scene_kinds"]
    assert view(PLAYER) is None
    options = (
        {"lab": {"name": "PRIVATE_LAB_ASSET", "description": "An original fixture."}}
        if science
        else {"conditioning_phrase": "speak"}
    )
    submit(
        ADMIN,
        "plan-off-duty-signature",
        "set_handler_scene",
        {
            "kind": kind,
            "participants": ["3"],
            "summary": "PRIVATE_SIGNED_SCENE",
            "recipient": None,
            "context": None,
            **options,
        },
    )
    assert view(PLAYER) is None
    attendance = view(OTHER)["attendance"]
    assert attendance["summary"] == "PRIVATE_SIGNED_SCENE"
    if science:
        [[old, _]] = [list(x) for x in attendance["lab_assets"]["restore"]]
        assert "lab_assets" not in view(ADMIN)["attendance"]
        owned_selection = {"lab": {"remove_void": old}}
        with pytest.raises(WorkflowError):
            submit(ADMIN, "stolen-assets", "acknowledge_handler_scene", owned_selection)
    else:
        assert attendance["phrase"] == "Speak"
        owned_selection = {}
    with pytest.raises(WorkflowError):
        submit(PLAYER, "uninvited-attest", "acknowledge_handler_scene", {})
    submit(OTHER, "first-attest", "acknowledge_handler_scene", owned_selection)
    before = state(game)
    if science:
        assert not steps(before, current_ref(before, ADMIN.user_id))
    else:
        assert not any("speak" in x.phrases for x in before.handler_persona.conditioning)
    ledger.engine.dispose()
    submit(ADMIN, "handler-attest", "acknowledge_handler_scene", {})
    final = state(game)
    if science:
        (step,) = steps(final, current_ref(final, ADMIN.user_id))
        assert step.period == period and step.removed_void_from == old
        assets = {x.id: x for x in final.sheets["3"].assets}
        assert assets[step.installed].void and assets[step.installed].name == "PRIVATE_LAB_ASSET"
        assert not assets[old].void and not assets[old].concealed
    else:
        (installation,) = [x for x in final.handler_persona.conditioning if "speak" in x.phrases]
        assert installation.pilot == current_ref(final, OTHER.user_id)
    assert view(OTHER)["attendance"]["remaining"] == 0
