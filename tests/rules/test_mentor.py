"""Actual original Mentor names and required human-attested companion scenes."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import call, roll_for
from test_physical_operations import place
from test_trainee import ready as trainee_ready
from test_world import initial

from girlframe.engine import m3_mentor as rules
from girlframe.engine import m3_trainee as trainee
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.services.m3_mentor import MentorService, prove_naming, required_companions
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    game, _, _, _ = trainee_ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, trainee.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    return game, MentorService(game)


def period(store, game):
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_off_duty_bodies", actual)
    return real_period(MissionService(store), game)


def test_actual_mentor_callsign_without_fictional_veto_and_separate_owner_cosmetic_request(
    ledger, tmp_path, monkeypatch
):
    game, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    learner = current_ref(before, 2)
    sync_before = ledger.sync_job(PLAYER)
    profile_revision = before.sheets["2"].source_profile_revision
    with pytest.raises(WorkflowError):
        controls.name(PLAYER, str(uuid4()), learner, before.revision, "Not my choice")
    with pytest.raises(WorkflowError):
        controls.name(OTHER, str(uuid4()), learner, before.revision - 1, "Stale source")
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic rollback")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        controls.name(OTHER, "97684", learner, before.revision, "NEW CALLSIGN")
    assert state(game) == before and ledger.sync_job(PLAYER) == sync_before
    monkeypatch.setattr(game, "event", original)

    async def mentor_name():
        from girlframe.discord_adapter.m3_mentor import open_mentor

        interaction = current(3, 97681)
        await interaction.response.defer(ephemeral=True)
        await open_mentor(interaction, controls)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("name:" + learner.token,)
        opened = current(3, 97682)
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["callsign"] = "NEW CALLSIGN"
        response = current(3, 97684)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(mentor_name())
    named = rules.records(state(game))[-1]
    result = dict(id=named.id, callsign=named.callsign)
    assert (
        MentorService(game).name(OTHER, "97684", learner, before.revision, "NEW CALLSIGN") == result
    )
    after = state(game)
    assert after.sheets["2"].callsign == "NEW CALLSIGN"
    assert after.sheets["2"].source_profile_revision == profile_revision
    assert after.sheets["2"].model_dump(exclude={"callsign", "revision"}) == before.sheets[
        "2"
    ].model_dump(exclude={"callsign", "revision"})
    assert ledger.sync_job(PLAYER) == sync_before
    assert not game.choices(PLAYER)  # No forged Newgirl answer or fictional approval veto.
    with ledger.engine.connect() as c:
        assert prove_naming(game, c, after, result["id"]).mentor == current_ref(before, 3)
        changed = after.model_copy(deep=True)
        changed.sheets["3"].character_id = "unrelated-replacement-person"
        replacement = current_ref(changed, 3)
        with pytest.raises(WorkflowError):
            required_companions(game, c, changed, (3,), present_actors=(replacement,))
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, result["id"])

    async def own_sync():
        from girlframe.discord_adapter.m3_mentor import open_mentor

        interaction = current(2, 97691)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_mentor(interaction, MentorService(game), result["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "NEW CALLSIGN" in form.instructions
        form.values["sync"] = ("queue",)
        response = current(2, 97692)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(own_sync())
    assert json.loads(ledger.sync_job(PLAYER)["desired_json"])["callsign"] == "NEW CALLSIGN"
    assert state(game) == after


def test_real_mentor_off_duty_scene_includes_original_companion_and_requires_actual_attendance(
    ledger, tmp_path, monkeypatch
):
    game, _ = ready(ledger, tmp_path, monkeypatch)
    cycle, identity = period(ledger, game)
    roll_for(cycle, game, identity, OTHER, (6, 6))
    call(
        cycle,
        game,
        OTHER,
        identity,
        "scene",
        "nearby_city",
        (3, 1),
        "PRIVATE_MENTOR_SCENE We actually visit the nearby city",
    )
    invited = cycle.review(PLAYER, identity)["invitations"]
    scene = next(x for x in invited if x["owner"] == 3)
    assert set(scene["participants"]) == {1, 2, 3} and not scene["acknowledgements"]
    assert scene["character_ids"]["2"] == state(game).sheets["2"].character_id
    call(cycle, game, OTHER, identity, "acknowledge", 3)
    call(cycle, game, ADMIN, identity, "acknowledge", 3)
    with pytest.raises(WorkflowError, match="required on-screen"):
        call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
    assert (
        2
        not in next(x for x in cycle.review(PLAYER, identity)["invitations"] if x["owner"] == 3)[
            "acknowledgements"
        ]
    )
    call(cycle, game, PLAYER, identity, "acknowledge", 3)
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
    assert cycle.review(OTHER, identity)["own"]["recovered"]


def test_routine_no_scene_does_not_invent_attendance_but_actual_handler_scene_adds_companion(
    ledger, tmp_path, monkeypatch
):
    game, _ = ready(ledger, tmp_path, monkeypatch)
    cycle, identity = period(ledger, game)
    roll_for(cycle, game, identity, OTHER, (4, 4))
    call(cycle, game, OTHER, identity, "scene", None, (), "")
    assert not cycle.review(PLAYER, identity)["invitations"]
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "routine",
        (1, 3),
        "PRIVATE_HANDLER_SCENE The actual Mentor attends the Handler's scene",
    )
    scene = cycle.review(PLAYER, identity)["handler_scene"]
    assert set(scene["participants"]) == {1, 2, 3} and not scene["acknowledgements"]
    for viewer in (ADMIN, OTHER, PLAYER):
        call(cycle, game, viewer, identity, "acknowledge", None)
    assert set(cycle.review(PLAYER, identity)["handler_scene"]["acknowledgements"]) == {1, 2, 3}
