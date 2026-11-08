"""Remaining Vatgrown printed normals with actual source actors and consumers."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_creation_review as creation_fixture
import test_m2_game as game_fixture
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_off_duty_cycle import call, roll_for
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.creation_details import DESIRES, GirlDetails
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_vatgrown_plays import (
    VatgrownPlaysService,
    investors,
    prove_learned_play,
    side_condition,
)
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, *, teacher="ALPHA"):
    original_seed, original_selected = creation_fixture.seed, game_fixture.selected

    def seed_actual(actual_store, viewer=PLAYER, callsign="SYNTH_A", notes="PRIVATE_CANARY"):
        if viewer != OTHER:
            return original_seed(actual_store, viewer, callsign, notes)
        actual_store.join(viewer, "join-3")
        return actual_store.save_draft(
            viewer,
            "draft-3",
            0,
            DraftInput(
                callsign="ACTUAL_" + teacher.replace("-", "_"),
                girl_playbook=teacher,
                frame_playbook="JANUS-B",
                notes=notes,
            ),
        )

    def selected_actual(girl="MOCKINGBIRD", frame="JANUS-B"):
        chosen = original_selected(teacher if girl == "MOCKINGBIRD" else girl, frame)
        if chosen.girl_playbook == "OLDGEN":
            chosen = chosen.model_copy(update={"girl_details": GirlDetails(maxims=(0, 1))})
        return chosen

    monkeypatch.setattr(creation_fixture, "seed", seed_actual)
    monkeypatch.setattr(game_fixture, "selected", selected_actual)
    _, game = service(store, girl="VATGROWN", frame="THE ENFORCER")
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE)
        + (("girl.stim-blissed.dose-up",) if teacher == "STIM-BLISSED" else ())
        + (
            ("girl.oldgen.old-dog-new-pups", "girl.oldgen.just-the-way-it-is")
            if teacher == "OLDGEN"
            else ()
        ),
    )
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
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["2"].heat = 4
        actual.sheets["3"].permissions = 3
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_bodies_map_and_resources", actual)
    world = WorldService(MissionService(store))
    npc = Npc(
        id="original-investor",
        name="Actual starting scientist",
        jobs=("scientist",),
        detail="The actual original personal project scientist",
        controller=1,
        cell=(0, 0),
        revealed=True,
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, npc)
    slot = state(game).sheets["2"].review.creation.npc_bonds[0].slot
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, slot, npc.id)
    return game, GameWorker(game), Gateway(), VatgrownPlaysService(game)


def sex(game, worker, gateway, controls, faces, *, counterpart_account=None):
    target = current_ref(state(game), 3)
    identity = controls.invite(
        PLAYER,
        str(uuid4()),
        900,
        target,
        state(game).revision,
        "PRIVATE_VOLUNTARY_SOURCE Our actual original people voluntarily confirm this interaction",
    )["id"]
    assert not any(
        x["id"] == rules.identity("sex-attempt", identity) for x in controls.tasks(ADMIN)
    )
    controls.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        counterpart_account or "My actual original Alpha confirms only this source",
    )
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            heat=1,
            context="Our actual accepted source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return identity, action


def native_choice(game, viewer, kind, **values):
    from girlframe.discord_adapter.m3_vatgrown_plays import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    data = game.decision(viewer, row["id"])

    async def submit():
        interaction = current(viewer.user_id, uuid4().int % 1000000000)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, data)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = current(viewer.user_id, uuid4().int % 1000000000)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())


def test_actual_mid_source_questions_bond_original_answers_private_violation_and_retry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3))
    identity, action = sex(game, worker, gateway, controls, (3, 4))
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        effects=("plans", "good"),
        plans="What do you actually plan?",
        good="How can I be good for you?",
        account="I ask both actual questions",
    )
    answer(game, OTHER, "vat_sex_plans", text="PRIVATE_ACTUAL_PLAN My actual human-authored plan")
    answer(game, OTHER, "vat_sex_good", text="My actual human-authored answer")
    assert depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3)) == min(
        2, before + 1
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    violation = rules.identity("sex-attempt", identity)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, violation)
    saved = state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic rollback")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        controls.disclose(
            PLAYER,
            "vat-disclosure-once",
            violation,
            saved.revision,
            "I actually disclose my own attempt",
        )
    assert state(game) == saved
    monkeypatch.setattr(game, "event", original)
    payload = (
        PLAYER,
        "vat-disclosure-once",
        violation,
        saved.revision,
        "I actually disclose my own attempt",
    )
    result = controls.disclose(*payload)
    assert controls.disclose(*payload) == result
    controls.judge_violation(
        ADMIN,
        str(uuid4()),
        violation,
        state(game).revision,
        False,
        "I actually know the disclosed evidence and choose no Punishment",
    )
    with ledger.engine.connect() as c:
        assert "PRIVATE_ACTUAL_PLAN" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_actual_high_counterpart_copy_one_use_brutalize_and_original_release(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity, action = sex(game, worker, gateway, controls, (5, 5))
    original = state(game)
    teacher = original.sheets["3"].identities[1]
    replaced = original.sheets["2"].identities[0]
    with pytest.raises(WorkflowError):
        row = next(x for x in game.choices(OTHER) if x["kind"] == "vat_sex_learn")
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("identity", "play"), text="Not my source choice"),
        )
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(teacher.id,),
        replacements=(replaced.id,),
        play=(rules.BRUTALIZE,),
        account="The original Alpha makes the actual learning selections",
    )
    learned = rules.records(state(game), rules.LearnedPlay)[-1]
    assert any(
        x.name == teacher.name and x.id != teacher.id for x in state(game).sheets["2"].identities
    )
    assert state(game).sheets["2"].girl == "VATGROWN"
    with ledger.engine.connect() as c:
        assert prove_learned_play(game, c, state(game), learned.id).teacher == current_ref(
            original, 3
        )
        assert side_condition(game, c, state(game), current_ref(original, 2))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    game.dice.faces = (1, 1)
    use = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Actual physical intimidation using the genuinely learned Alpha Play",
            trigger_confirmed=True,
        ),
    )["action_id"]
    from girlframe.services.m3_recovery import RecoveryService

    before_use_rolls = game.dice.calls
    game.abort(ADMIN, str(uuid4()), use)
    recovery = RecoveryService(game)
    interrupted = next(x for x in recovery.saved(PLAYER) if x["id"] == use)
    tick(worker, gateway, 4)
    cancelled = recovery.recover(PLAYER, str(uuid4()), use, interrupted["revision"], cancel=True)
    assert cancelled["cancelled_unrolled"] and game.dice.calls == before_use_rolls
    use = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Actual physical intimidation using the genuinely learned Alpha Play",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, use)["receipt"] is None:
        game.roll(PLAYER, "m2.confirmed_roll:" + use, use)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "alpha_low",
        options=("pass",),
    )
    assert (
        game.inspect(PLAYER, use)["state"] == "complete"
        and state(game).sheets["2"].girl == "VATGROWN"
    )
    tick(worker, gateway, 6)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="brutalize",
                target_actor=current_ref(state(game), 3),
                heat=0,
                context="No second use was granted",
                trigger_confirmed=True,
            ),
        )
    with pytest.raises(WorkflowError):
        controls.send_away(
            PLAYER, str(uuid4()), identity, state(game).revision, "I cannot release myself"
        )
    controls.send_away(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        "The actual original counterpart sends her away",
    )
    with ledger.engine.connect() as c:
        assert side_condition(game, c, state(game), current_ref(state(game), 2)) is None


@pytest.mark.parametrize("punish", (False, True))
def test_actual_low_owned_question_optional_real_punishment_departure_and_one_learning(
    ledger, tmp_path, monkeypatch, punish
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity, action = sex(game, worker, gateway, controls, (1, 1))
    answer(game, OTHER, "vat_sex_question", text="What do you actually think of me?")
    answer(game, PLAYER, "vat_sex_answer", text="My actual human-authored honest fictional answer")
    answer(
        game,
        OTHER,
        "vat_sex_judge",
        options=("punish" if punish else "accept",),
        text="The actual counterpart owns this judgment",
    )
    if punish:
        value = controls.view(OTHER, identity)["session"]
        discipline = rules.find(state(game), rules.Discipline, value["discipline"])
        role = RolePunishmentService(game)

        def change(viewer, **values):
            return role.change(
                viewer,
                str(uuid4()),
                discipline.case,
                role.get(viewer, discipline.case)["revision"],
                **values,
            )

        details = Details(kind="quality_time", tag="Actual source consequence")
        change(
            OTHER,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(OTHER, scene="The actual counterpart performs the chosen Quality Time")
        change(PLAYER, attest=True)
        change(OTHER, execute=True, account="Actual performed source Punishment")
    controls.depart(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        "The actual counterpart now leaves this source scene",
    )
    assert not any(
        r.actor == current_ref(state(game), 3) for x in state(game).scene_casts for r in x.roles
    )
    answer(
        game,
        PLAYER,
        "vat_sex_learn",
        options=("plans",),
        fields={"plans": "What are you planning as you actually leave?"},
        text="I own my one actual learning choice",
    )
    answer(game, OTHER, "vat_sex_plans", text="My actual departing answer")
    assert (
        game.inspect(PLAYER, action)["state"] == "complete"
        and controls.view(PLAYER, identity)["session"]["departed_event"]
    )


@pytest.mark.parametrize("faces,branch", [((3, 3), "mid"), ((5, 5), "high"), ((1, 1), "low")])
def test_actual_prime_period_scene_desire_favour_or_real_offered_requisition(
    ledger, tmp_path, monkeypatch, faces, branch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    cycle, period = real_period(MissionService(ledger), game)
    roll_for(cycle, game, period, PLAYER, faces)
    actor = current_ref(state(game), 2)
    identity = rules.identity("investment", period, actor.token)
    handler = current_ref(state(game), 1)
    if branch == "low":
        controls.low_investor(
            PLAYER,
            str(uuid4()),
            identity,
            state(game).revision,
            handler,
            DESIRES[1],
            "The original Handler's actual interest wanes",
        )
        controls.low_tag(
            ADMIN, str(uuid4()), identity, state(game).revision, "Original Investor interest waned"
        )
        current_period = cycle.periods._get
        with ledger.engine.connect() as c:
            from girlframe.services.m3_vatgrown_plays import require_scene_allowed

            with pytest.raises(WorkflowError):
                require_scene_allowed(
                    game, c, state(game), current_period(c, period), 2, (actor, handler)
                )
        assert controls.view(PLAYER, identity)["investment"]["completed_event"]
        return
    data = cycle.review(PLAYER, period)
    cycle.scene(
        PLAYER,
        str(uuid4()),
        period,
        data["revision"],
        state(game).revision,
        "prime_" + branch,
        (2, 1),
        "The actual Investor uses the original Vatgrown toward their actual desire",
        investor=handler,
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    call(cycle, game, ADMIN, period, "acknowledge", 2)
    if branch == "mid":
        controls.judge_scene(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "What opportunity can you offer me?",
            "The original Investor factually judges actual good work",
        )
        favour = rules.records(state(game), rules.Favour)[-1]
        controls.favour_reply(
            ADMIN,
            str(uuid4()),
            favour.id,
            state(game).revision,
            True,
            "The actual Investor explicitly backs down from the promised answer",
        )
        controls.favour_tag(
            PLAYER,
            str(uuid4()),
            favour.id,
            state(game).revision,
            True,
            "Backed down from real promise",
        )
        assert state(game).handler_tags[-1].giver_actor == actor
        return
    controls.new_desire(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "A controlled endurance demonstration",
        "The actual Investor authors a genuinely new desire",
    )
    game.dice.faces = (4, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=identity,
            heat=0,
            context="I endure the actual dangerous drill requested by this Investor",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(
        game, ADMIN, "handler_keep", flag=True, text="The real endurance demonstration is enough"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    controls.fulfil(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The actual completed demonstration fulfilled my new desire; Creature Comforts is suitable",
    )
    offer = rules.records(state(game), rules.RequisitionOffer)[-1]
    from girlframe.services.m3_vatgrown_support import accept_offer

    before = state(game).sheets["2"].permissions
    key = str(uuid4())
    payload = (
        game,
        PLAYER,
        key,
        offer.id,
        state(game).revision,
        "I accept the actual offered Creature Comforts",
    )
    receipt = accept_offer(*payload)
    assert accept_offer(*payload) == receipt and state(game).sheets["2"].permissions == before
    assert any(x.kind == "creature_comforts" and x.actor == actor for x in state(game).requisitions)


def test_real_initial_investor_lineage_exact_positive_quote_and_voluntary_permissions(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls = ready(ledger, tmp_path, monkeypatch)
    actor, alpha = current_ref(state(game), 2), current_ref(state(game), 3)
    with ledger.engine.connect() as c:
        actual = investors(game, c, state(game), actor)
        assert {x.actor.kind for x in actual} == {"handler", "npc"}
        assert all(x.source == "creation" for x in actual)
    proposal = controls.propose_investor(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        alpha,
        (DESIRES[2],),
        "I propose this actual other Girl as an Investor",
    )["id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.quote_investor(
            ADMIN, str(uuid4()), proposal, before.revision, 0, "No silent/free price"
        )
    assert state(game) == before
    controls.quote_investor(
        ADMIN,
        str(uuid4()),
        proposal,
        before.revision,
        2,
        "The actual Handler offers exact positive price two",
    )
    with pytest.raises(WorkflowError):
        controls.accept_investor(
            PLAYER,
            str(uuid4()),
            proposal,
            state(game).revision,
            "I cannot spend the other person's Permissions",
        )
    saved = state(game)
    payload = (
        OTHER,
        "actual-investor-payment",
        proposal,
        saved.revision,
        "I voluntarily confirm exactly two of my actual Permissions",
    )
    result = controls.accept_investor(*payload)
    assert (
        controls.accept_investor(*payload) == result
        and state(game).sheets["3"].permissions == saved.sheets["3"].permissions - 2
    )


def test_actual_stim_teacher_learned_once_native_self_dose_uses_only_learner_resources(
    ledger, tmp_path, monkeypatch
):
    """Deferred P1 normal: genuine learning source, native dose, consumed-source readback."""
    from test_dose_up import native_choice as dose_choice

    from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
    from girlframe.engine import m3_dose_up as dosing
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_dose_up import DoseUpService
    from girlframe.services.m3_dose_up import prove as prove_dose
    from girlframe.services.m3_learned_plays import prove_consumed

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED")
    session, source_action = sex(game, worker, gateway, controls, (5, 5))
    before_learning = state(game)
    teacher_identity = before_learning.sheets["3"].identities[1]
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(teacher_identity.id,),
        replacements=(before_learning.sheets["2"].identities[0].id,),
        play=(dosing.RULE,),
        account="The actual original Stim teacher selects her own Dose Up for one use",
    )
    assert game.inspect(PLAYER, source_action)["state"] == "complete"
    learned = rules.records(state(game), rules.LearnedPlay)[-1]
    assert learned.rule_id == dosing.RULE and learned.teacher == current_ref(before_learning, 3)
    assert controls.view(PLAYER, session)["learned"][0]["can_dose"]
    assert not controls.view(OTHER, session)["learned"][0]["can_dose"]
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, session)
    # The high source still owns its departure controls until the actual counterpart releases it.
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The original Stim teacher actually sends the learner away after the lesson",
    )
    tick(worker, gateway, 6)
    before = state(game)
    teacher = before.sheets["3"].model_copy(deep=True)
    before_rolls = game.dice.calls

    async def use_native():
        def interaction():
            value = current(2, uuid4().int % 1000000000)
            value.channel_id = 900
            return value

        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_vatgrown_plays(opened, controls, session)
        learned_form = opened.edit_original_response.call_args.kwargs["view"]
        assert learned_form.title == "Actual learned Dose Up"
        learned_form.values["action"] = ("dose",)
        menu_response = interaction()
        await learned_form.confirm.callback(menu_response)
        assert learned_form.completed, menu_response.edit_original_response.call_args_list
        menu = menu_response.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("self",)
        form_response = interaction()
        await menu.confirm.callback(form_response)
        form = form_response.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("1",), account="I inject the real cocktail into my own body")
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        # The exact native retry retains the known Action, without another reservation.
        await form.confirm.callback(submitted)

    asyncio.run(use_native())
    with ledger.engine.connect() as c:
        action = c.scalar(
            sa.select(t.m2["m2_actions"].c.id).where(
                t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                sa.func.json_extract(t.m2["m2_actions"].c.body_json, "$.play") == "dose_up",
            )
        )
    assert action is not None and game.dice.calls == before_rolls
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    pass_tags(game)
    dose_choice(game, PLAYER, ("quick", "strong"))
    actual = state(game)
    value = dosing.records(actual, dosing.Dose)[-1]
    assert value.id == action and value.actor == value.target == current_ref(before, 2)
    assert value.total == 8 and value.heat == 1 and value.duration == 2
    assert {x for selected in value.selections for x in selected.components} == {"quick", "strong"}
    assert len(dosing.drug_tags(actual, value.actor)) == 2
    assert actual.sheets["2"].girl == "VATGROWN"
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["2"].identities == before.sheets["2"].identities
    assert actual.sheets["3"] == teacher
    assert not has_rule(actual.sheets["2"], dosing.RULE, "STIM-BLISSED")
    assert not has_rule(actual.sheets["2"], dosing.SELF_RULE, "STIM-BLISSED")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert prove_consumed(game, c, actual, saved, dosing.RULE, value.roll_event)
        assert prove_dose(game, c, actual, action) == value
    dose_service = DoseUpService(ledger, game)
    assert set(dose_service.view(PLAYER, action)["components"]) == {
        dosing.LABELS["quick"],
        dosing.LABELS["strong"],
    }
    with pytest.raises(WorkflowError):
        dose_service.view(OTHER, action)
    assert not controls.view(PLAYER, session)["learned"][0]["can_dose"]
    assert game.dice.calls == before_rolls + 1
    tick(worker, gateway, 6)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="dose_up", heat=0, trigger_confirmed=True, context="No second use was granted"
            ),
        )
    assert game.dice.calls == before_rolls + 1


def test_actual_oldgen_teacher_learned_advice_cancel_retry_status_maxim_listen_and_once_use(
    ledger, tmp_path, monkeypatch
):
    """Deferred group normal: actual learning source, owned advice and real maxim consumer."""
    from girlframe.discord_adapter.m3_oldgen import open_choice as advice_choice
    from girlframe.discord_adapter.m3_oldgen import open_oldgen
    from girlframe.engine import m3_oldgen as oldgen
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_learned_plays import available, prove_consumed
    from girlframe.services.m3_oldgen import OldgenService, prove_advice
    from girlframe.services.m3_recovery import RecoveryService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="OLDGEN")
    with ledger.transaction() as c:
        actual = state(game)
        actual.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.original_lower_rank_learning_recipient", actual)
    assert state(game).sheets["3"].girl == "OLDGEN"
    assert len(oldgen.base_maxims(state(game), 3)) == 2
    session, source_action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="My own actual original Oldgen confirms only this voluntary source",
    )
    before_learning = state(game)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(before_learning.sheets["3"].identities[1].id,),
        replacements=(before_learning.sheets["2"].identities[0].id,),
        play=(oldgen.ADVICE,),
        account="The original Oldgen teacher chooses her actual advice Play for one use",
    )
    assert game.inspect(PLAYER, source_action)["state"] == "complete"
    learned = rules.records(state(game), rules.LearnedPlay)[-1]
    assert learned.rule_id == oldgen.ADVICE
    assert learned.teacher == current_ref(before_learning, 3)
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert not oldgen.base_maxims(state(game), 2)
    assert not has_rule(state(game).sheets["2"], oldgen.RULE, "OLDGEN")
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual counterpart ends the required stay after the real lesson",
    )
    tick(worker, gateway, 6)
    advice = OldgenService(game)
    target = current_ref(state(game), 3)

    def interaction(user=2, channel=900):
        value = current(user, uuid4().int % 1000000000)
        value.channel_id = channel
        return value

    async def prepare_native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_oldgen(opened, advice)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("advice",)
        selected = interaction()
        await menu.confirm.callback(selected)
        assert menu.completed, selected.edit_original_response.call_args_list
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(target.token,),
            heat=("1",),
            account="My actual learned advice to this original other Girl",
        )
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    def start():
        assert advice.menu(PLAYER, 900)["learned_advice"]
        asyncio.run(prepare_native())
        with ledger.engine.connect() as c:
            action = game.action(c, game.lock(c, 900)["action_id"])
        assert action["data"]["learned_play"]["id"] == learned.id
        assert action["data"]["prepared"]["play"] == oldgen.PLAY
        return action["id"]

    before = state(game)
    abandoned = start()
    calls = game.dice.calls
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    result = recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True)
    assert recovery.recover(PLAYER, key, abandoned, saved["revision"], cancel=True) == result
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        value = available(game, c, state(game), current_ref(state(game), 2), oldgen.ADVICE)
        assert value and value.id == learned.id and value.claimed_action is None
    teacher = state(game).sheets["3"].model_copy(deep=True)
    action = start()
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    assert game.dice.calls == calls + 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    assert state(game).order.index(2) == max(0, before.order.index(2) - 1)
    assert state(game).sheets["3"].heat == teacher.heat
    assert state(game).sheets["3"].assets == teacher.assets
    assert state(game).sheets["3"].identities == teacher.identities
    with ledger.engine.connect() as c:
        assert available(game, c, state(game), current_ref(state(game), 2), oldgen.ADVICE) is None
    text = "Trust the partner who actually listened.\n  PRIVATE_ONE_USE_ADVICE"

    async def answer_owned(viewer, kind, account):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await advice_choice(opened, game, game.decision(viewer, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(1))
        form.values["account"] = account
        submitted = interaction(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(answer_owned(PLAYER, "oldgen_write_maxim", text))
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert any(x["kind"] == "oldgen_listen" for x in game.choices(OTHER))
    asyncio.run(answer_owned(OTHER, "oldgen_listen", "I actually listen to this original advice"))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        original = prove_advice(game, c, state(game), action)
        bound = game.action(c, action)
        assert original.total == 8 and original.heat == 1
        assert prove_consumed(game, c, state(game), bound, oldgen.ADVICE, original.roll_event)
    maxim = oldgen.get(state(game), original.maxim)
    assert maxim.owner == current_ref(state(game), 2) and maxim.subject == target
    assert maxim.text == text and oldgen.available(state(game), maxim)
    assert not advice.menu(PLAYER, 900)["can_advise"]
    with pytest.raises(WorkflowError):
        advice.view(ADMIN, maxim.id)
    tick(worker, gateway, 5)

    async def use_maxim_native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_oldgen(opened, advice, maxim.id)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["effect"] = ("reinforce",)
        selected = interaction()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(target.token,), account="The actual original subject reinforces it"
        )
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved
        # Completed private history survives reopening outside any bound scene.
        reopened = interaction(channel=999)
        await reopened.response.defer(ephemeral=True)
        await open_oldgen(reopened, OldgenService(game), maxim.id)
        content = reopened.edit_original_response.call_args.kwargs["content"]
        assert "PRIVATE_ONE_USE_ADVICE" in content and content.endswith("— used.")

    asyncio.run(use_maxim_native())
    assert state(game).sheets["3"].heat == teacher.heat + 2
    assert not oldgen.available(state(game), maxim)
    assert len([x for x in oldgen.records(state(game), oldgen.Use) if x.maxim == maxim.id]) == 1
    with pytest.raises((WorkflowError, ValueError)):
        advice.use(
            PLAYER,
            str(uuid4()),
            maxim.id,
            ActorRef.model_validate(target.model_dump()),
            "reinforce",
            900,
            state(game).revision,
            "No second use of the same maxim",
        )
    assert state(game).sheets["3"].heat == teacher.heat + 2
    assert not oldgen.base_maxims(state(game), 2)
    assert game.dice.calls == calls + 1
