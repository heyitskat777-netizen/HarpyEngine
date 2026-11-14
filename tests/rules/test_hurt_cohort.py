"""Printed NPC hurt cohorts retain actual injury, original choices and scoped consequences."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_easy_target
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_easy_target import EasyTargetService
from girlframe.services.m3_easy_target_hurt_cohort import prove
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@pytest.mark.parametrize("participate", [True, False])
def test_native_actual_hurt_cohorts_injury_and_owned_nonparticipation(
    ledger, tmp_path, monkeypatch, participate
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc, helper = (ActorRef(kind="npc", entity=x) for x in ("bystander", "cohort"))
    identity = source(game, worker, gateway, faces=(5, 5), selected=npc)
    work, helper_work = (rules.identity(identity, x) for x in (npc, helper))
    early, late = current_ref(state(game), 3), current_ref(state(game), 1)

    def row(viewer, actor, kind="easy_target_child"):
        return next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + actor.token)

    def submit(viewer, actor, values, number, kind="easy_target_child"):
        asyncio.run(
            _npc_protection_native(game, viewer.user_id, row(viewer, actor, kind), values, number)
        )

    submit(
        OTHER,
        npc,
        dict(
            urge=("hurt",),
            context="I strike her actual exposed body with my fists",
            account="My actual NPC chooses bodily hurt",
        ),
        98700,
        "easy_target_react",
    )
    for viewer, actor in ((OTHER, helper), (OTHER, early), (ADMIN, late)):
        choose(game, viewer, actor, "cohort", primary=work)
    validate(game, npc)
    before = state(game)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]
    submit(
        OTHER,
        helper,
        dict(
            outcome=("participate" if participate else "decline",),
            account="PRIVATE_HURT_COHORT My own actual bodily participation decision",
        ),
        98710,
    )
    submit(OTHER, early, dict(outcome=("decline",), account="I decline to go along"), 98720)
    participating = state(game)
    follower = rules.get(participating, rules.Reaction, helper_work)
    assert bool(follower.performance_event) is participate
    assert bool(follower.exemption) is participate
    assert bool(follower.completed_event) is not participate
    assert not rules.records(participating, rules.NpcHurt)
    assert not rules.records(participating, rules.Harm)
    assert participating.sheets == before.sheets
    late_choice = row(ADMIN, late)
    submit(OTHER, npc, dict(account="My NPC actually performs the original bodily strike"), 98730)
    performed = state(game)
    hurt = rules.records(performed, rules.NpcHurt)[-1]
    assert not hurt.damage_event
    assert not rules.get(performed, rules.Reaction, work).performance_event
    assert not any(x.source_work == work for x in performed.role_punishments)
    assert not any(x.damaged for x in performed.sheets["2"].assets if x.family == "girl")
    with pytest.raises(WorkflowError, match="already performed"):
        game.respond(
            ADMIN,
            "late-hurt-cohort-participation",
            late_choice["id"],
            late_choice["revision"],
            ChoiceAnswer(options=("participate",), text="Too late for this original blow"),
        )
    assert state(game) == performed
    submit(
        ADMIN,
        late,
        dict(outcome=("missed",), account="I did not participate before the actual blow"),
        98740,
    )
    missed = rules.get(state(game), rules.Reaction, rules.identity(identity, late))
    assert missed.completed_event and not missed.exemption and not missed.performance_event
    assert missed.consequence == "hurt-cohort-missed"
    # Injury remains the original Newgirl's actual owned selection, not immunity or a free roll.
    injury = next(x for x in game.choices(PLAYER) if x["kind"] == "battle_target_damage")
    with pytest.raises(WorkflowError):
        game.decision(OTHER, injury["id"])
    asset = game.decision(PLAYER, injury["id"])["battle"]["assets"][0]["id"]
    asyncio.run(_npc_protection_native(game, PLAYER.user_id, injury, dict(asset=(asset,)), 98750))
    actual = state(game)
    primary = rules.get(actual, rules.Reaction, work)
    follower = rules.get(actual, rules.Reaction, helper_work)
    assert next(x for x in actual.sheets["2"].assets if x.id == asset).damaged
    assert primary.harm and primary.performance_event and not primary.child and not follower.child
    assert actual.sheets["3"] == before.sheets["3"]
    cases = [x for x in actual.role_punishments if x.source_work == work]
    if participate:
        assert not cases
        assert primary.exemption == helper_work and follower.exemption == work
        assert primary.consequence == follower.consequence == "cohort-exempt"
        assert primary.completed_event == follower.completed_event
        assert follower.performance_event != follower.completed_event
    else:
        assert len(cases) == 1 and not primary.exemption
        case = cases[0]
        assert case.subject == npc and case.chooser == current_ref(actual, 2)
        role = RolePunishmentService(game)

        def change(viewer, **values):
            return role.change(
                viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
            )

        details = Details(kind="quality_time", tag="The actual Newgirl's retained consequence")
        change(
            PLAYER,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(ADMIN, scene="The Handler carries out the actual chosen NPC quality time")
        change(OTHER, attest=True)
        change(ADMIN, execute=True, account="I carry out the Newgirl's actual selected consequence")
    actual = state(game)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    records = rules.records(actual, rules.HurtCohort)
    assert len(records) == 3
    with game.store.engine.connect() as c:
        for outcome in records:
            assert prove(game, c, actual, outcome.id) == outcome
        assert "PRIVATE_HURT_COHORT" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(9, 200, True, False), helper_work)
    assert controls.view(OTHER, helper_work)["hurt_cohort"][0]["account"].startswith(
        "PRIVATE_HURT_COHORT"
    )
    # Reopening after a genuine new scene uses the immutable source snapshot, not current cast.
    tick(worker, gateway, 6)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical proof must use original snapshot profiles")

    with monkeypatch.context() as historical:
        historical.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
        historical.setattr("girlframe.services.m3_dose_up.profiles", no_live_profiles)
        with game.store.engine.connect() as c:
            for outcome in records:
                assert prove(game, c, later, outcome.id) == outcome
        assert EasyTargetService(game).view(OTHER, helper_work)["hurt_cohort"]

    async def reopen():
        interaction = current(OTHER.user_id, 98790)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_easy_target(interaction, EasyTargetService(game), helper_work)
        text = str(interaction.edit_original_response.call_args)
        assert "PRIVATE_HURT_COHORT" in text
        assert ("participated" if participate else "declined") in text

    asyncio.run(reopen())
