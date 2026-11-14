"""Real NPC Nanobot removal keeps owned costs, other drug effects and original expiry."""

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_dose_up import native_choice
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_doctor import open_choice, open_roll
from girlframe.engine import m3_doctor as rules
from girlframe.engine import m3_dose_up as dose_rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_dose_up import DoseUpService, prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_dose import active_drug
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def setup(ledger, tmp_path, monkeypatch):
    _, game = service(ledger, girl="STIM-BLISSED", frame=rules.BOOK)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.NANO, rules.TRACK, dose_rules.RULE, dose_rules.SELF_RULE),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with ledger.transaction() as c:
        before = state(game)
        before.world = initial()
        before = place(before, 2, mode="outside_frame")
        before = place(before, 3, mode="outside_frame")
        before.sheets["2"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.original_doctor_context", before)
    missions = MissionService(ledger)
    patient = ActorRef(kind="npc", entity="nanobot-patient")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=patient.entity,
            name="Pat",
            jobs=("civilian",),
            controller=1,
            detail="PRIVATE_NPC_MEDICAL_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    casts = CastService(ActorService(missions))
    cast_change(casts, ADMIN, "join", patient)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        patient,
        "human_npc",
        "Actual original human body and brain here",
    )
    return game, GameWorker(game), Gateway(), patient, casts


def roll_nanobot(game, patient, heat):
    """Seed a historical pre-r267 action, then restore production admission.

    This is NOT evidence that new NPC treatment is supported.  Retained tests
    exercise recovery/choices for actions already rolled by older candidates.
    Only the new admission check is bypassed in this explicit legacy fixture;
    ownership, physical contact, dice, costs and later continuations remain real.
    """

    def legacy_results(source, c, canon, action):
        # The original pre-resource result is genuinely absent from NPC state.
        # Only creation is historical: later choices use production continuations.
        from girlframe.services.m3_doctor import effects

        meta = action["data"]["doctor"]
        level = action["data"]["result"]["tier"]
        amount = 5 if level == "high" else heat if level == "mid" else 0
        action["data"]["result"]["npc_heat"] = dict(
            printed_gain=amount, applied_gain=0, resource=None
        )
        if level == "mid" and effects(canon, patient, meta["actor_controller"]):
            source.request(c, action, meta["actor_controller"], "doctor_nanobot_benefits")
        else:
            source.request(
                c,
                action,
                meta["target_controller"],
                "doctor_patient",
                dict(unsupported="The legacy result has no actual NPC resource outcome port."),
            )

    with (
        patch("girlframe.services.m3_doctor.require_nanobot_patient"),
        patch("girlframe.services.m3_doctor.results", side_effect=legacy_results),
    ):
        action = _roll_legacy_nanobot(game, patient, heat)
        tick(GameWorker(game), Gateway(), 3)
        pass_tags(game)
        return action


def _roll_legacy_nanobot(game, patient, heat):
    source = DoctorService(game)
    assert patient.token in {x["token"] for x in source.menu(PLAYER, 900)["npc_nanobot_targets"]}

    async def begin():
        interaction = current(2, int(uuid4().int % 1000000000))
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_roll(interaction, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("nanobot_injection",),
            target=(patient.token,),
            heat=(str(heat),),
            account="PRIVATE_NANO_SOURCE I actually inject this original patient here",
        )
        await form.confirm.callback(current(2, int(uuid4().int % 1000000000)))
        assert form.completed

    asyncio.run(begin())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        return c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
        )


@pytest.mark.parametrize("spent_heat", [0, 1])
def test_npc_nanobot_removes_real_dose_tag_after_owned_confirmation_preserves_expiry(
    ledger, tmp_path, monkeypatch, spent_heat
):
    game, worker, gateway, patient, casts = setup(ledger, tmp_path, monkeypatch)
    controls = DoseUpService(ledger, game)
    contact = controls.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        patient,
        state(game).revision,
        "PRIVATE_CONTACT My hand actually reaches the patient's exposed vein",
    )["id"]
    game.dice.faces = (6, 6)
    dose = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=dose_rules.PLAY,
            target_actor=patient,
            source_work=contact,
            heat=1,
            context="Actual original patient dosing",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(game, PLAYER, ("quick", "calm"))
    native_choice(game, ADMIN, ("sense",))
    tick(worker, gateway, 8)
    drugs = [x for x in dose_rules.records(state(game), dose_rules.NpcDrugTag) if x.dose == dose]
    selected = next(x for x in drugs if x.component == "quick")
    with ledger.engine.connect() as c:
        original_dose = prove(game, c, state(game), dose)
    before = state(game)
    controller_sheet = before.sheets["3"].model_copy(deep=True)
    game.dice.faces = (4, 4) if spent_heat == 0 else (3, 4)
    action = roll_nanobot(game, patient, spent_heat)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.dice.calls == 2
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - spent_heat
    assert state(game).sheets["2"].obsolescence_marked == 1
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "doctor_nanobot_benefits")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("repair",),
            ),
        )

    async def select_and_confirm():
        own = current(2, 998901)
        await own.response.defer(ephemeral=True)
        await open_choice(own, DoctorService(game), row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(choices=("remove",), effect=("tag:" + selected.id,))
        await form.confirm.callback(current(2, 998902))
        assert form.completed
        assert selected.tag in actor_tags(state(game), patient)
        assert game.inspect(PLAYER, action)["state"] != "complete"
        response = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                response["id"],
                response["revision"],
                ChoiceAnswer(
                    options=("confirm",),
                ),
            )
        controller = current(1, 998903)
        await controller.response.defer(ephemeral=True)
        await open_choice(controller, DoctorService(game), response["id"])
        form = controller.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("confirm",))
        submit = current(1, 998904)
        await form.confirm.callback(submit)
        assert form.completed
        await form.confirm.callback(submit)

    asyncio.run(select_and_confirm())
    actual = state(game)
    assert selected.id not in {x.id for x in actor_tags(actual, patient)}
    assert {x.id for x in actor_tags(actual, patient)} == {x.id for x in drugs} - {selected.id}
    assert actual.sheets["3"] == controller_sheet
    assert patient.entity not in actual.sheets
    assert (game.inspect(PLAYER, action)["state"] == "complete") == (spent_heat == 0)
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["data"]["result"]["npc_heat"] == dict(
            printed_gain=spent_heat, applied_gain=0, resource=None
        )
        assert active_drug(game, c, actual, patient) is not None
    assert len([x for x in actual.facts if x.get("kind") == "doctor_npc_effect_removed"]) == 1
    assert game.dice.calls == 2 and actual.sheets["2"].obsolescence_marked == 1
    if spent_heat:
        from girlframe.services.p1_facilitator import FacilitatorService

        pending = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
        receipt = game.inspect(PLAYER, action)["receipt"]
        with pytest.raises(WorkflowError, match="mandatory Nanobot Heat award remains pending"):
            game.respond(ADMIN, str(uuid4()), pending["id"], pending["revision"], ChoiceAnswer())

        async def show_pending():
            interaction = current(1, 998905)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_choice(interaction, DoctorService(game), pending["id"])
            assert (
                "Human adjudication"
                in interaction.edit_original_response.call_args.kwargs["content"]
            )

        asyncio.run(show_pending())
        tasks = FacilitatorService(game).tasks(ADMIN)
        assert len(tasks) == 1
        packet = FacilitatorService(game).view(ADMIN, tasks[0]["id"])
        assert packet["request"]["source"] == action
        assert packet["request"]["mandatory"]
        assert game.inspect(PLAYER, action)["receipt"] == receipt
        assert state(game).sheets == actual.sheets and game.dice.calls == 2
        assert state(game).facts == actual.facts
        assert len([x for x in actual.facts if x.get("kind") == "doctor_npc_effect_removed"]) == 1
        with ledger.engine.connect() as c:
            assert prove(game, c, actual, dose) == original_dose
        return
    tick(worker, gateway, 8)
    for number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        assert dose_rules.expired(state(game), dose) == (number == 2)
        if number == 1:
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (ADMIN, PLAYER, OTHER):
                game.join_scene(human, str(uuid4()), 900)
            cast_change(casts, ADMIN, "join", patient)
    final = state(game)
    assert not any(x.id in {drug.id for drug in drugs} for x in actor_tags(final, patient))
    with ledger.engine.connect() as c:
        assert prove(game, c, final, dose) == original_dose
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert "PRIVATE_" not in str(gateway.messages)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == final


def test_npc_nanobot_high_keeps_original_cost_and_result_pending_without_fake_resources(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    game.dice.faces = (6, 6)
    action = roll_nanobot(game, patient, 1)
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
    with pytest.raises(WorkflowError, match="remains pending"):
        game.respond(ADMIN, str(uuid4()), row["id"], row["revision"], ChoiceAnswer())
    actual = state(game)
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["2"].obsolescence_marked == 1 and game.dice.calls == 1
    assert actual.sheets["3"] == before.sheets["3"] and actual.world == before.world
    assert patient.entity not in actual.sheets
    assert game.inspect(PLAYER, action)["state"] != "complete"


def test_actual_frame_wraith_cannot_receive_nanobots_or_pay_doctor_cost(
    ledger, tmp_path, monkeypatch
):
    import test_m2_game
    from test_m2_game import answer
    from test_wyvern import buy, free_chat, ready, roll

    from girlframe.engine import m3_wyvern as wyvern
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    # The second player genuinely creates a Doctor through normal reviewed
    # activation; the first player retains the original Wyvern source.
    choose_starting = test_m2_game.selected
    creation_ready = test_m2_game.ready
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda store, girl, frame: creation_ready(store, girl, frame, other_frame=rules.BOOK),
    )
    monkeypatch.setattr(
        test_m2_game,
        "selected",
        lambda girl, frame: choose_starting(girl, rules.BOOK if frame == "JANUS-B" else frame),
    )
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            wyvern.BEAST,
            wyvern.BURDEN,
            wyvern.CHASSIS,
            *wyvern.REQUISITIONS,
            rules.NANO,
            rules.TRACK,
        ),
    )
    assert state(game).sheets["3"].frame == rules.BOOK
    buy(controls, wyvern.WRAITH)
    source = roll(game, worker, gateway, play="wyvern_wraith", faces=(6, 6))
    answer(game, PLAYER, "wyvern_wraith", options=("captain",), fields={"name": "Real mind"})
    answer(
        game,
        ADMIN,
        "wyvern_wraith_rules",
        options=("frame_bound_npc",),
        fields={"tag": "Still here"},
        text="The genuine source creates a Frame-bound NPC mind",
    )
    assert game.inspect(PLAYER, source)["state"] == "complete"
    free_chat(worker, gateway)
    mind = wyvern.records(state(game), wyvern.Wraith)[-1]
    casts = CastService(ActorService(MissionService(ledger)))
    with ledger.engine.connect() as c:
        actual = resolve(state(game), mind.persona, profiles(c, ledger.campaign_id))
    controller = next(
        human for human in (PLAYER, OTHER, ADMIN) if human.user_id == actual.controller
    )
    cast_change(casts, controller, "join", mind.persona)
    before = state(game)
    calls = game.dice.calls
    with ledger.engine.connect() as c:
        actual = resolve(before, mind.persona, profiles(c, ledger.campaign_id))
    assert actual.rules == "npc" and actual.inside_frame is True
    assert actual.vessel_id == "wyvern-mind:" + mind.id
    assert actor_tags(before, mind.persona)
    assert mind.persona.token not in {
        row["token"] for row in DoctorService(game).menu(OTHER, 900)["npc_nanobot_targets"]
    }
    with pytest.raises(WorkflowError, match="Wraith is not a biological brain"):
        game.begin(
            OTHER,
            str(uuid4()),
            900,
            before.sheets["3"].revision,
            PlayInput(
                play="nanobot_injection",
                target_actor=mind.persona,
                heat=0,
                context="An NPC rules label is not a physical patient",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == before and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert not game.pending_actions(c)
