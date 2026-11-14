"""Two actual appearance choices on every ordinary Go-OffDuty result source."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current
from test_off_duty_cycle import call, roll_for
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine import m3_show_dog as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_show_dog import ShowDogService, prove
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch, faces):
    _, game = service(store, girl="PRINCESS", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial().model_copy(
            update={
                "npcs": (
                    Npc(
                        id="actual-spectator",
                        name="Actual audience member",
                        jobs=("civilian",),
                        detail="PRIVATE_NPC_DETAIL",
                        controller=3,
                        cell=(0, 0),
                        revealed=True,
                    ),
                )
            }
        )
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_appearance_context", actual)
    cycle, period = real_period(MissionService(store), game)
    action = roll_for(cycle, game, period, PLAYER, faces)
    controls = ShowDogService(game)
    with store.engine.connect() as c:
        work = next(x for x in controls._tasks(c, PLAYER) if x["pending"])
    return game, cycle, period, action, controls, work["id"]


def first(controls, viewer, identity, kind, **kwargs):
    data = controls.view(viewer, identity)
    return controls.first(
        viewer, str(uuid4()), identity, data["revision"], data["game_revision"], kind, **kwargs
    )


def second(controls, identity, npc, desire):
    data = controls.view(PLAYER, identity)
    return controls.second(
        PLAYER,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        npc,
        desire,
        "PRIVATE_ACTUAL_APPEARANCE This actual NPC watched my performed public appearance",
    )


def risk(controls, identity, punish):
    data = controls.view(ADMIN, identity)
    return controls.risk(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        punish,
        "The actual original Handler adjudicates this performed choice",
    )


@pytest.mark.parametrize(
    "branch,desire,faces",
    [
        ("trend", "sex", (1, 1)),
        ("public", "own", (2, 2)),
        ("message", "kill", (4, 4)),
        ("quiet", "emulate", (2, 2)),
    ],
)
def test_actual_two_choices_all_first_branches_real_risk_npc_bond_and_private_message(
    ledger, tmp_path, monkeypatch, branch, desire, faces
):
    game, cycle, period, action, controls, identity = setup(ledger, tmp_path, monkeypatch, faces)
    original = state(game)
    assert cycle.review(PLAYER, period)["own"]["roll"]["total"] == sum(faces) + 4
    assert game.inspect(PLAYER, action)["state"] == "complete"
    npc = ActorRef(kind="npc", entity="actual-spectator")
    with pytest.raises(WorkflowError):
        first(controls, OTHER, identity, "quiet", account="Cannot choose another Princess's source")
    data = controls.view(PLAYER, identity)
    with pytest.raises(WorkflowError):
        controls.first(
            PLAYER,
            str(uuid4()),
            identity,
            data["revision"],
            data["game_revision"] - 1,
            "quiet",
            account="Stale source cannot choose",
        )
    assert state(game) == original
    if branch == "quiet":
        call(cycle, game, PLAYER, period, "scene", None, (), "")
        with pytest.raises(WorkflowError):
            call(cycle, game, PLAYER, period, "recover", RecoveryChoice())

        creation_revision = state(game).revision

        async def new_npc():
            from girlframe.discord_adapter.m3_show_dog import open_show_dog

            interaction = current(2, 99351)
            await interaction.response.defer(ephemeral=True)
            await open_show_dog(interaction, controls, identity)
            menu = interaction.edit_original_response.call_args.kwargs["view"]
            menu.values["action"] = ("create",)
            opened = current(2, 99352)
            await menu.confirm.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                name="Actual newly created spectator",
                detail="A real introduced civilian",
                location=("base0",),
            )
            response = current(2, 99353)
            await form.confirm.callback(response)
            assert form.completed, response.edit_original_response.call_args_list

        asyncio.run(new_npc())
        created = state(game).world.npcs[-1]
        npc = ActorRef(kind="npc", entity=created.id)
        saved_creation = state(game)
        replay = WorldService(MissionService(ledger)).npc(
            PLAYER, "99353", creation_revision, created, show_dog=identity
        )
        assert replay["id"] == created.id and state(game) == saved_creation
        # The independent second choice can be genuinely selected first.
        second(controls, identity, npc, desire)
        assert not controls.view(PLAYER, identity)["complete"]
        first(
            controls,
            PLAYER,
            identity,
            branch,
            account="I actually smile and obey without taking a risk",
        )
        assert controls.view(PLAYER, identity)["complete"]
        call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    else:
        target = npc if branch == "trend" else current_ref(state(game), 3)
        prior = state(game)
        original_event = game.event
        if branch == "message":

            def fail(*args, **kwargs):
                original_event(*args, **kwargs)
                raise RuntimeError("synthetic rollback")

            monkeypatch.setattr(game, "event", fail)
            with pytest.raises(RuntimeError):
                first(
                    controls,
                    PLAYER,
                    identity,
                    branch,
                    target=target,
                    message="PRIVATE_ADDRESSED_MESSAGE",
                    account="I actually send an addressed communication",
                )
            assert state(game) == prior
            monkeypatch.setattr(game, "event", original_event)
        data = controls.view(PLAYER, identity)
        key = str(uuid4())
        args = (PLAYER, key, identity, data["revision"], data["game_revision"], branch)
        kwargs = dict(
            target=target,
            tag="PRIVATE_ACTUAL_APPEARANCE_TAG" if branch != "message" else "",
            message="PRIVATE_ADDRESSED_MESSAGE" if branch == "message" else "",
            account="I actually perform this source's public appearance choice",
        )
        applied = controls.first(*args, **kwargs)
        assert controls.first(*args, **kwargs) == applied
        assert not controls.view(PLAYER, identity)["complete"]
        second(controls, identity, npc, desire)
        assert not controls.view(PLAYER, identity)["complete"]
        consequence = risk(controls, identity, branch == "trend")
        if branch == "trend":
            assert not controls.view(PLAYER, identity)["complete"]
            role = RolePunishmentService(game)
            case = consequence["punishment"]

            def change(viewer, **values):
                return role.change(
                    viewer, str(uuid4()), case, role.get(viewer, case)["revision"], **values
                )

            details = Details(kind="stimulant_injection")
            change(
                ADMIN,
                instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
            )
            change(
                ADMIN, scene="The actual original Handler performs the chosen injection Punishment"
            )
            change(PLAYER, attest=True)
            change(ADMIN, execute=True, account="The actual chosen Punishment is administered")
            assert controls.view(PLAYER, identity)["complete"]
            assert (
                next(x for x in state(game).world.npcs if x.id == npc.entity).tags[-1].label
                == "PRIVATE_ACTUAL_APPEARANCE_TAG"
            )
        elif branch == "public":
            assert state(game).sheets["3"].tags[-1].giver_actor == current_ref(state(game), 2)
            assert rules.records(state(game), rules.Exposure)[-1].target == target
        else:
            message = rules.records(state(game), rules.Message)[-1]
            assert controls.view_message(OTHER, message.id)["text"] == "PRIVATE_ADDRESSED_MESSAGE"
            with pytest.raises(WorkflowError):
                controls.view_message(ADMIN, message.id)
            assert "PRIVATE_ADDRESSED_MESSAGE" not in str(controls.view(ADMIN, identity))
    actual = state(game)
    assert controls.view(PLAYER, identity)["complete"]
    assert depth(actual, current_ref(actual, 2), npc) == 1
    interest = rules.records(actual, rules.Interest)[-1]
    assert interest.npc == npc and interest.desire == desire
    assert controls.view_interest(PLAYER, interest.id)["desire"] == desire
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, identity).interest == interest.id
        assert "PRIVATE_ACTUAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    saved = state(game)

    async def reopen():
        from girlframe.discord_adapter.m3_show_dog import open_show_dog

        interaction = current(2, 99358)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await open_show_dog(interaction, ShowDogService(game), identity)
        assert "complete" in interaction.edit_original_response.call_args.kwargs["content"]

    asyncio.run(reopen())
    assert state(game) == saved
