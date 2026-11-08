"""Prince ordinary source normals; only the named minimal smoke runs before final P1."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_off_duty_cycle import roll_for
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_prince import open_choice, open_prince
from girlframe.engine import m3_prince as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_prince import (
    PrinceService,
    prove_grant,
    prove_mark,
    prove_override,
    prove_performance,
)
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, frame="THE PRINCE")
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.FANBASE, rules.PERFORMER, *rules.RULES, "frame.prince.permission-trigger"),
    )
    policy = store.policy
    store.policy = policy.model_copy(
        update=dict(
            m3_approval=policy.m3_approval.model_copy(
                update=dict(
                    subsystems=policy.m3_approval.subsystems | {"world", "strain", "playbooks"}
                )
            )
        )
    )
    with store.transaction() as c:
        actual = state(game)
        actual.order = (3, 2)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].permissions = 30
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_prior_Prince_positions_status_balance", actual
        )
    return game, GameWorker(game), Gateway(), PrinceService(game)


def native_source(controls, viewer, identity=None, number=75000):
    async def show():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_prince(interaction, controls, identity)
        return interaction.edit_original_response.call_args.kwargs["view"]

    return asyncio.run(show())


def native_submit(form, viewer, number, values):
    async def submit():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        form.values.update(values)
        await form.confirm.callback(interaction)
        assert form.completed, interaction.edit_original_response.call_args_list
        return interaction.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(submit())


def native_choice(game, viewer, kind, number=75100, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def show():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = current(viewer.user_id, number + 1)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(show())


def action_for(game, key):
    with game.store.engine.connect() as c:
        return json.loads(
            c.scalar(
                sa.select(t.commands.c.outcome_json).where(
                    t.commands.c.campaign_id == game.store.campaign_id,
                    t.commands.c.interaction_key == str(key),
                )
            )
        )["action_id"]


def perform(
    game,
    worker,
    gateway,
    controls,
    faces,
    *,
    following=True,
    account="The actual part follows the current Fanbase demands",
    exception=None,
):
    source = controls.perform(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "The composed public hero",
        following,
        account,
    )["id"]
    game.dice.faces = faces
    prepared = PlayInput.model_validate(
        dict(
            play=rules.PLAY,
            source_work=source,
            heat=state(game).sheets["2"].heat,
            context="I actually play this declared part for the original other Girl",
            trigger_confirmed=True,
            prince_demands="following" if following else "against",
            prince_demand_account=account,
            prince_exception=exception,
        )
    )
    action = game.begin(PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, prepared)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    pass_tags(game)
    return source, action


def buy(controls, game, rule):
    return controls.buy(
        PLAYER, str(uuid4()), state(game).revision, rule, "Actual source-priced Prince Requisition"
    )


def test_native_mid_performer_real_demographic_mark_two_owners_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    menu = native_source(controls, PLAYER)
    declaration = native_submit(menu, PLAYER, 75001, dict(source=("perform",)))
    target = current_ref(state(game), 3)
    native_submit(
        declaration,
        PLAYER,
        75002,
        dict(
            target=(target.token,),
            part="The composed public hero",
            following=("yes",),
            account="PRIVATE_PRINCE_ACCOUNT: this actual part follows my actual fan demands",
        ),
    )
    value = rules.records(state(game), rules.Performance)[-1]
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, value.id)
    assert state(game) == before
    form = native_source(controls, PLAYER, value.id, 75003)
    demographic = next(x for x in before.sheets["2"].identities if x.id.startswith("fan:"))
    game.dice.faces = (4, 4)
    native_submit(
        form,
        PLAYER,
        75004,
        dict(identity=(demographic.id,), gain=("1",), share=("0",), heat=("1",), piloting=("no",)),
    )
    action = action_for(game, 75004)
    assert not next(x for x in state(game).sheets["2"].identities if x.id == demographic.id).marked
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "prince_choose_actor")
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("status",))
        )
    assert state(game) == unchanged
    native_choice(
        game,
        PLAYER,
        "prince_choose_actor",
        option=("status",),
        account="My actual public performance raises my Status",
    )
    native_choice(
        game,
        OTHER,
        "prince_choose_target",
        75110,
        option=("bond",),
        account="My actual response deepens the performer's Bond with me",
    )
    final = state(game)
    actor = current_ref(final, 2)
    assert higher(final, 2, 3) and depth(final, actor, target) == min(
        depth(before, actor, target) + 1, 2
    )
    assert next(x for x in final.sheets["2"].identities if x.id == demographic.id).marked
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        prove_mark(game, c, final, actual)
        assert prove_performance(game, c, final, value.id).completed_event
        assert "PRIVATE_PRINCE_ACCOUNT" not in " ".join(
            c.scalars(sa.select(t.events.c.payload_json))
        )
    assert controls.view(PLAYER, value.id)["record"]["account"].startswith("PRIVATE_PRINCE_ACCOUNT")
    assert "account" not in controls.view(OTHER, value.id)["record"]
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_high_actual_demand_exception_performer_conforms_and_only_one_break_is_dismissed(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    account = "I actually act contrary to these named Fanbase demands in this performance"
    source = controls.exception_attempt(PLAYER, str(uuid4()), state(game).revision, 900, account)[
        "id"
    ]
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput.model_validate(
            dict(
                play="keep_your_head",
                source_work=source,
                heat=0,
                context=account,
                trigger_confirmed=True,
                prince_demands="against",
                prince_demand_account=account,
            )
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", text="I actually keep my nerve for this contrary part")
    answer(game, ADMIN, "handler_keep", flag=True, text="The real danger was met")
    tick(worker, gateway, 5)
    exception = rules.records(state(game), rules.DemandException)[-1]
    assert exception.action == action
    identity, action = perform(
        game,
        worker,
        gateway,
        controls,
        (6, 6),
        following=False,
        account=account,
        exception=exception.id,
    )
    answer(
        game,
        PLAYER,
        "prince_conform",
        text="I actually revise this part to follow the named current demands",
    )
    answer(game, PLAYER, "prince_choose_actor", options=("dismiss",))
    answer(game, OTHER, "prince_choose_target", options=("bond",))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    controls.break_character(
        PLAYER, str(uuid4()), state(game).revision, identity, "My actual first temporary break"
    )
    assert rules.presentation(
        state(game),
        current_ref(state(game), 2),
        controls.view(PLAYER, identity)["record"]["cast"]["id"],
    )
    controls.break_character(
        PLAYER, str(uuid4()), state(game).revision, identity, "My actual second break"
    )
    assert not rules.presentation(
        state(game),
        current_ref(state(game), 2),
        controls.view(PLAYER, identity)["record"]["cast"]["id"],
    )


def test_mid_counterpart_erase_choice_keeps_tag_selection_with_original_private_owner(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    _, action = perform(game, worker, gateway, controls, (1, 1))
    answer(game, OTHER, "prince_falter", options=("tag",), text="Unreliable")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    original_tag = state(game).sheets["2"].tags[-1]
    tick(worker, gateway, 5)
    _, action = perform(game, worker, gateway, controls, (4, 4))
    answer(game, PLAYER, "prince_choose_actor", options=("bond",))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "prince_choose_target")
    assert game.decision(OTHER, row["id"])["prince"]["tags"] == []
    answer(
        game,
        OTHER,
        "prince_choose_target",
        options=("erase",),
        text="Erase the actual Tags conflicting with this reliable part",
    )
    assert any(x["kind"] == "prince_erase_tags" for x in game.choices(PLAYER))
    answer(
        game,
        PLAYER,
        "prince_erase_tags",
        denied=(original_tag.id,),
        text="Unreliable conflicts with my actual dependable hero act",
    )
    assert not any(x.id == original_tag.id for x in state(game).sheets["2"].tags)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_low_performer_actual_other_person_tag_then_real_punishment_closes_original_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    _, action = perform(game, worker, gateway, controls, (1, 1))
    answer(game, OTHER, "prince_falter", options=("tag",), text="Your mask slipped")
    assert state(game).sheets["2"].tags[-1].giver_actor == current_ref(state(game), 3)
    assert game.inspect(PLAYER, action)["state"] == "complete"

    tick(worker, gateway, 5)
    _, action = perform(game, worker, gateway, controls, (1, 1))
    answer(game, OTHER, "prince_falter", options=("punish",))
    case = state(game).role_punishments[-1]
    discipline = RolePunishmentService(game)

    def change(viewer, **values):
        return discipline.change(
            viewer, str(uuid4()), case.id, discipline.get(viewer, case.id)["revision"], **values
        )

    change(
        OTHER,
        instruction=Instruction(
            kind="stimulant_injection",
            details_json=Details(kind="stimulant_injection").model_dump_json(),
        ),
    )
    change(
        OTHER, scene="The actual original counterpart performs the source-owned minor Punishment"
    )
    change(PLAYER, attest=True)
    change(OTHER, execute=True, account="Actual source stimulant injection")
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_low_performer_counterpart_can_decline_optional_tag_or_punishment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    _, action = perform(game, worker, gateway, controls, (1, 1))
    original = state(game)
    answer(game, OTHER, "prince_falter", options=("pass",))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets == original.sheets and not state(game).role_punishments


def test_actual_hero_paid_pronouns_bad_girl_low_order_conversion_and_handler_plan(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    first = buy(controls, game, rules.HERO)
    buy(controls, game, rules.BAD)
    actor = current_ref(state(game), 2)
    assert rules.official_pronouns(state(game), actor) == dict(girl="he/him", frame="he/him")
    assert higher(state(game), 2, 3)
    order = game.issue_order(
        ADMIN, str(uuid4()), 900, 2, "An actual direct Handler order contrary to this source's fans"
    )
    tick(worker, gateway, 1)
    answer(game, PLAYER, "order_response", options=("disobey",))
    game.dice.faces = (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput.model_validate(
            dict(
                play="disobey_orders",
                order_id=order["order_id"],
                parent=order["action_id"],
                heat=0,
                context="Actual refusal follows the current fans' demands",
                trigger_confirmed=True,
                prince_demands="following",
                prince_demand_account="The real refusal follows my actual current Fanbase demands",
            )
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, action)["receipt"]
    answer(
        game,
        PLAYER,
        "prince_bad_girl",
        options=("use",),
        text="This actual refusal follows my actual current Fanbase demands",
    )
    answer(game, PLAYER, "actor_disobey", flag=True)
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert game.inspect(PLAYER, action)["result"]["total"] >= 11
    assert game.inspect(PLAYER, action)["receipt"] == raw
    with ledger.engine.connect() as c:
        assert prove_override(game, c, state(game), game.action(c, action)) == 11
    tick(worker, gateway, 6)
    plan = rules.records(state(game), rules.PlanGrant)[-1]
    controls.reveal_plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        plan.id,
        "I actually reveal to the original scene how that refusal advanced my plan",
    )
    assert controls.view(PLAYER, plan.id)["record"]["used_event"]
    buy(controls, game, rules.HERO)
    assert higher(state(game), 2, 3)
    with ledger.engine.connect() as c:
        prove_grant(
            game,
            c,
            state(game),
            next(x for x in rules.records(state(game), rules.Grant) if x.id == first["id"]),
        )


def test_power_imbalance_real_lower_status_flirt_and_source_authored_fan_membership(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, game, rules.HERO)
    buy(controls, game, rules.POWER)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    fans = controls.menu(PLAYER, 900)["fanbase"]
    controls.member(
        OTHER,
        str(uuid4()),
        state(game).revision,
        actor,
        target,
        fans["demographics"][0]["id"],
        "My actual original Girl is really a member of this fan demographic",
    )
    game.dice.faces = (3, 3)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="Actual interaction with the original lower-Status fan",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    with ledger.engine.connect() as c:
        modifiers = [
            x for x in game.action(c, action)["data"]["modifiers"] if x["source"] == rules.POWER
        ]
        assert len(modifiers) == 1 and modifiers[0]["amount"] == 2
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="An actually authored name")
    assert game.inspect(PLAYER, action)["state"] == "complete"


@pytest.mark.parametrize("branch", ("predecessor", "mission", "secret"))
def test_immortal_actual_legacy_choice_owned_answer_comparing_tag_bond_or_expression(
    ledger, tmp_path, monkeypatch, branch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, game, rules.IMMORTAL)
    identity = controls.recognize(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        "This actual other Girl appears to know my Frame's real legacy",
    )["id"]
    original_depth = depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3))
    controls.legacy(
        OTHER,
        str(uuid4()),
        state(game).revision,
        identity,
        branch,
        "The actual original witness authors the selected real relationship",
    )
    if branch == "predecessor":
        controls.legacy(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            identity,
            "ask",
            "My actual question",
            "What did she protect?",
        )
        controls.legacy(
            OTHER,
            str(uuid4()),
            state(game).revision,
            identity,
            "answer",
            "She protected the actual people I described",
            "Kinder than your predecessor",
        )
        assert state(game).sheets["2"].tags[-1].giver_actor == current_ref(state(game), 3)
    elif branch == "secret":
        controls.legacy(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            identity,
            "answer",
            "A brief actual look of recognition flashes across her face",
        )
    else:
        assert depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3)) == max(
            original_depth, 1
        )
    assert controls.view(PLAYER, identity)["record"]["completed_event"]


@pytest.mark.parametrize("option", ("adjust", "replace", "fan"))
def test_tv_actual_go_off_duty_demands_demographic_or_foundation_fan_with_bond(
    ledger, tmp_path, monkeypatch, option
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, game, rules.TV)
    cycle, period = real_period(MissionService(ledger), game)
    roll_for(cycle, game, period, PLAYER, (4, 4))
    task = next(x for x in rules.records(state(game), rules.OffDutyTask) if x.rule == rules.TV)
    before = controls.view(PLAYER, task.id)["fanbase"]
    controls.off_duty(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        task.id,
        option,
        "The actual printed interview effect was performed",
        demanded=("Kind", "Intelligent"),
        rejected=("Dangerous", "Girly"),
        demographic=before["demographics"][0]["id"] if option == "fan" else "Foundation workers",
        lose=before["demographics"][0]["id"],
        name="Actual introduced fan",
        cell=(0, 0),
    )
    final = state(game)
    assert controls.view(PLAYER, task.id)["record"]["completed_event"]
    if option == "adjust":
        assert rules.current_fanbase(final, current_ref(final, 2)).demanded == (
            "Kind",
            "Intelligent",
        )
    elif option == "replace":
        assert not any(
            x.id == before["demographics"][0]["identity"] for x in final.sheets["2"].identities
        )
        assert any(
            x.name == "Foundation workers" and x.protected for x in final.sheets["2"].identities
        )
    else:
        fan = next(x for x in final.world.npcs if x.name == "Actual introduced fan")
        assert (
            fan.employment == "foundation"
            and depth(final, current_ref(final, 2), ActorRef(kind="npc", entity=fan.id)) == 1
        )


def test_growing_fanbase_actual_next_off_duty_concert_adds_real_protected_identity_and_fame_asset(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    paid = buy(controls, game, rules.GROWING)
    cycle, period = real_period(MissionService(ledger), game)
    roll_for(cycle, game, period, PLAYER, (4, 4))
    task = next(x for x in rules.records(state(game), rules.OffDutyTask) if x.grant == paid["id"])
    controls.off_duty(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        task.id,
        "perform",
        "The actual funded concert is wildly successful",
        demographic="Foundation workers",
        asset_name="Near-worldwide fame",
        asset_description="The actual audience recognizes this original Girl's live performance",
    )
    final = state(game)
    assert any(
        x.name == "Near-worldwide fame" and x.family == "girl" for x in final.sheets["2"].assets
    )
    assert len(rules.current_fanbase(final, current_ref(final, 2)).demographics) == 3
    assert controls.view(PLAYER, task.id)["record"]["completed_event"]
