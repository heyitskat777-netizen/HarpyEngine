"""Original Newgirl teaching, actual erased/acted-on responses and mentor discipline."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_trainee as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_trainee import TraineeService, prove
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, frame="THE ENFORCER"):
    _, game = service(store, girl="NEWGIRL", frame=frame)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    return game, GameWorker(game), Gateway(), TraineeService(game)


def teach(controls, game, *, native=False):
    if not native:
        return controls.record_teaching(
            PLAYER,
            str(uuid4()),
            900,
            state(game).revision,
            "PRIVATE_TEACHING My original Mentor shows how controlled movement avoids danger",
        )["id"]
    from girlframe.discord_adapter.m3_trainee import open_trainee

    async def source():
        interaction = current(2, 97901)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_trainee(interaction, controls)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("teaching",)
        opened = current(2, 97902)
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["mentor"] = (current_ref(state(game), 3).token,)
        form.values["account"] = (
            "PRIVATE_TEACHING My Mentor demonstrates patient controlled movement"
        )
        response = current(2, 97903)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(source())
    return rules.records(state(game), rules.Teaching)[-1].id


def native_select(controls, viewer, source, operation, **values):
    from girlframe.discord_adapter.m3_trainee import open_trainee

    async def select():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await open_trainee(interaction, controls, source)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = (operation,)
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        await menu.confirm.callback(opened)
        if operation == "punish":
            return
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(select())


def discipline(game, identity, executor, subject):
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), identity, role.get(viewer, identity)["revision"], **values
        )

    details = Details(kind="stimulant_injection")
    change(
        executor, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(
        executor, scene="Original source participants actually administer the immediate discipline"
    )
    change(subject, attest=True)
    before = state(game).sheets[str(subject.user_id)].heat
    change(executor, execute=True, account="I actually administer the chosen stimulant injection")
    final = state(game)
    assert final.sheets[str(subject.user_id)].heat == before + 7
    case = next(x for x in final.role_punishments if x.id == identity)
    assert case.effect_event and case.completion_event


@pytest.mark.parametrize("frame", ("THE ENFORCER", "PROJECT ANKOU"))
def test_erase_real_contradiction_and_mandatory_original_mentor_tag_atomic_private_reopen(
    ledger, tmp_path, monkeypatch, frame
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, frame=frame)
    # Real ordinary Flirt has its original Mentor human author the actual Tag.
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="I actually flirt with my original Mentor",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="I actually go too far with the personal question",
    )
    answer(game, OTHER, "target_flirt", text="My actual preferred name")
    answer(game, OTHER, "flirt_owe_tag", text="Patient and methodical")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    identity = teach(controls, game, native=True)
    before = state(game)
    tag = next(x for x in before.sheets["2"].tags if x.label == "Patient and methodical")
    assert tag.giver_actor == current_ref(before, 3)
    old = before.sheets["2"].identities[0]
    args = (PLAYER, str(uuid4()), identity, before.revision, "erase")
    with pytest.raises(WorkflowError):
        controls.choose(
            *args, identity_id=old.id, account="My old recklessness contradicts patience"
        )
    assert state(game) == before
    native_select(
        controls,
        PLAYER,
        identity,
        "erase",
        identity=(old.id,),
        tag=(tag.id,),
        account="PRIVATE_CONTRADICTION My old impulse contradicts her demonstrated patience",
    )
    actual = state(game)
    assert all(x.id != old.id for x in actual.sheets["2"].identities)
    assert all(x.id != tag.id for x in actual.sheets["2"].tags)
    embraced = next(x for x in actual.sheets["2"].identities if x.name == tag.label)
    assert not embraced.marked and embraced.slot == old.slot
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    assert actual.sheets["3"] == before.sheets["3"]
    assert (
        next(
            x
            for x in actual.obligations
            if x.kind == "cannot_refuse_until_tag_resolved" and x.details.get("tag") == tag.id
        ).state
        == "fulfilled"
    )
    assert next(x for x in actual.obligations if x.kind == "flirt_followthrough").state == "pending"
    assert controls.view(OTHER, identity)["selected_account"] is None
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, identity).mentor == current_ref(before, 3)
        assert "PRIVATE_CONTRADICTION" not in " ".join(
            c.scalars(sa.select(t.events.c.payload_json))
        )

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.identity == identity and x.task == "m3_trainee"
        )
        interaction = current(2, 97910)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        text = interaction.edit_original_response.call_args.kwargs["content"]
        assert "Patient and methodical" in text and "PRIVATE_CONTRADICTION" in text

    asyncio.run(reopen())


def test_act_on_actual_teaching_real_completed_play_heat_once_stale_wrong_owner_and_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = teach(controls, game)
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.choose(
            OTHER,
            str(uuid4()),
            identity,
            before.revision,
            "act",
            heat=3,
            account="Cannot fabricate the learner's performed response",
        )
    with pytest.raises(WorkflowError):
        controls.choose(
            PLAYER,
            str(uuid4()),
            identity,
            before.revision - 1,
            "act",
            heat=3,
            account="Actual performed movement",
        )
    assert state(game) == before and game.dice.calls == 0
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I use her controlled movement in actual danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual evasive response adjudication")
    tick(worker, gateway, 5)
    original = state(game)
    key = str(uuid4())
    args = (PLAYER, key, identity, original.revision, "act")
    result = controls.choose(
        *args, heat=3, account="I actually used her precise movement to evade", source_action=action
    )
    assert (
        controls.choose(
            *args,
            heat=3,
            account="I actually used her precise movement to evade",
            source_action=action,
        )
        == result
    )
    assert state(game).sheets["2"].heat == original.sheets["2"].heat + 3
    assert state(game).sheets["2"].identities == original.sheets["2"].identities
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), identity).learner == current_ref(original, 2)


def test_challenge_actual_immediate_mentor_punishment_real_effect_and_source_work_closure(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    identity = teach(controls, game)
    native_select(
        controls,
        PLAYER,
        identity,
        "challenge",
        account="Your teaching is foolish; I actually challenge its premise",
    )
    data = controls.view(OTHER, identity)
    assert data["phase"] == "mentor" and data["actionable"]
    with pytest.raises(WorkflowError):
        controls.punish(PLAYER, str(uuid4()), identity, data["revision"])
    native_select(controls, OTHER, identity, "punish")
    case = controls.view(OTHER, identity)["case"]
    original = state(game)
    actual = next(x for x in original.role_punishments if x.id == case)
    assert actual.source_kind == "trainee" and actual.action is None
    assert actual.executor == current_ref(original, 3) and actual.subject == current_ref(
        original, 2
    )
    discipline(game, case, OTHER, PLAYER)
    assert controls.view(PLAYER, identity)["phase"] == "complete"
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        work = (
            c.execute(
                sa.select(table)
                .where(table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert work["state"] == "resolved" and game.dice.calls == 0


def test_actual_shirking_report_original_handler_punishes_mentor_not_newgirl_and_saved_history(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    identity = teach(controls, game)
    controls.choose(
        PLAYER,
        str(uuid4()),
        identity,
        state(game).revision,
        "challenge",
        account="I actually call her teaching foolish and demonstrate my disagreement",
    )
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, identity)
    with ledger.engine.connect() as c:
        assert not controls._tasks(c, ADMIN)
    native_select(
        controls,
        PLAYER,
        identity,
        "report",
        account="PRIVATE_SHIRK My actual Mentor walks away instead of administering discipline",
    )
    data = controls.view(ADMIN, identity)
    assert "PRIVATE_TEACHING" not in str(data)
    assert "PRIVATE_SHIRK" in data["report"]
    assert data["phase"] == "reported" and data["actionable"]
    with pytest.raises(WorkflowError):
        controls.resolve_report(OTHER, str(uuid4()), identity, data["revision"], "No Handler alias")
    native_select(
        controls,
        ADMIN,
        identity,
        "review",
        account="I factually establish this original Mentor abandoned her immediate duty",
    )
    original = state(game)
    case = controls.view(ADMIN, identity)["case"]
    actual = next(x for x in original.role_punishments if x.id == case)
    assert actual.executor == current_ref(original, 1) and actual.subject == current_ref(
        original, 3
    )
    discipline(game, case, ADMIN, OTHER)
    assert state(game).sheets["2"] == original.sheets["2"]
    assert controls.view(ADMIN, identity)["phase"] == "complete"
    assert "PRIVATE_SHIRK" in controls.view(PLAYER, identity)["report"]
    with ledger.engine.connect() as c:
        forged = state(game)
        forged.sheets["3"].character_id = "same-account-different-original-person"
        with pytest.raises((WorkflowError, ValueError)):
            controls._current(
                c, forged, prove(game, c, state(game), identity), OTHER, current_ref(original, 3)
            )
    assert game.dice.calls == 0
