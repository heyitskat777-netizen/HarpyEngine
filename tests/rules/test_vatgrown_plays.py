"""Remaining Vatgrown printed normals with actual source actors and consumers."""

import asyncio
import json
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
from girlframe.engine.creation_details import DESIRES, GirlDetails, StandardChoice
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
        elif chosen.girl_playbook == "PRINCESS":
            chosen = chosen.model_copy(
                update={"girl_details": GirlDetails(own_standard=StandardChoice(slot=0))}
            )
        return chosen

    monkeypatch.setattr(creation_fixture, "seed", seed_actual)
    monkeypatch.setattr(game_fixture, "selected", selected_actual)
    if teacher == "PRINCESS":
        original_rank = creation_fixture.HandlerService.rank
        original_ready = game_fixture.ready
        initial_rank_done = False

        def princess_rank(handler, viewer, key, expected, order):
            nonlocal initial_rank_done
            # This is the actual initial Handler proposal, before any activation.
            if not initial_rank_done:
                result = original_rank(
                    handler,
                    viewer,
                    key,
                    expected,
                    tuple(sorted(order, key=lambda ref: ref.user_id != OTHER.user_id)),
                )
                initial_rank_done = True
                return result
            return original_rank(handler, viewer, key, expected, order)

        def princess_ready(actual_store, *args, **kwargs):
            result = original_ready(actual_store, *args, **kwargs)
            coordinated = creation_fixture.CoordinationService(actual_store)
            for actor, role, slot in ((PLAYER, "princess_peer", 1), (ADMIN, "princess_handler", 2)):
                request = coordinated.propose(
                    actor,
                    "actual-teacher-" + role,
                    OTHER.user_id,
                    role,
                    coordinated.prepare(actor, OTHER.user_id, role),
                    StandardChoice(slot=slot),
                )
                coordinated.decide(
                    OTHER, "actual-teacher-accept-" + role, request["id"], 1, "accept"
                )
            return result

        monkeypatch.setattr(creation_fixture.HandlerService, "rank", princess_rank)
        monkeypatch.setattr(game_fixture, "ready", princess_ready)
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


def test_actual_newgirl_teacher_learned_easy_target_native_request_real_keep_and_judgment(
    ledger, tmp_path, monkeypatch
):
    """Deferred: genuine Mentor/callsign and Vatgrown creation, no post-activation label swap."""
    from m3_policy_scenario import configure_m3_fixture
    from test_creation import selected
    from test_creation_review import ready as creation_ready
    from test_easy_target import child, finish_keep
    from test_m2_game import Dice

    from girlframe.discord_adapter.m3_easy_target import open_choice as target_choice
    from girlframe.discord_adapter.m3_easy_target import open_easy_target
    from girlframe.engine import m3_easy_target as target_rules
    from girlframe.engine.creation_details import DesireChoice, NpcInvestor
    from girlframe.engine.m2 import ReleaseApproval
    from girlframe.engine.m2_registry import registry_digest
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_mentorship import active_mentors
    from girlframe.services.creation_coordination import CoordinationService
    from girlframe.services.creation_review import CreationReviewService
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_easy_target import EasyTargetService, prove
    from girlframe.services.m3_learned_plays import available, prove_consumed

    review, creation, _ = creation_ready(
        ledger, girl="NEWGIRL", frame="THE ENFORCER", other_girl="VATGROWN"
    )
    selected_learner = selected("VATGROWN", "JANUS-B")
    coordination = CoordinationService(ledger)
    request = coordination.propose(
        ADMIN,
        str(uuid4()),
        3,
        "vatgrown_handler",
        coordination.prepare(ADMIN, 3, "vatgrown_handler"),
        DesireChoice(slots=(1,)),
    )
    coordination.decide(OTHER, str(uuid4()), request["id"], 1, "accept")
    current_draft = creation.get(OTHER)
    selected_learner = selected_learner.model_copy(
        update={
            "shared_tokens": current_draft.draft.shared_tokens,
            "girl_details": GirlDetails(
                investors=tuple(
                    NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                    for x in selected_learner.npc_bonds
                )
            ),
        }
    )
    creation.save(
        OTHER, "actual-vatgrown-learner-build", current_draft.revision, 1, selected_learner
    )
    other_review = CreationReviewService(ledger)
    incoming = next(x for x in other_review.get(OTHER).sheet.bonds if not x.outgoing)
    current_draft = creation.get(OTHER)
    other_review.select_bond(
        OTHER,
        "actual-vatgrown-mutual-bond",
        current_draft.revision,
        1,
        current_draft.draft,
        incoming.id,
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    game = GameService(ledger, dice=Dice((5, 5)))
    for viewer in (PLAYER, OTHER):
        saved = review.get(viewer)
        review.save(
            viewer,
            "actual-learning-review-" + str(viewer.user_id),
            saved.saved_revision,
            saved.fingerprint,
        )
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review
        game.activate(viewer, "actual-learning-active-" + str(viewer.user_id), saved.fingerprint)
    teacher, learner = current_ref(state(game), 2), current_ref(state(game), 3)
    assert state(game).sheets["2"].girl == "NEWGIRL"
    assert state(game).sheets["2"].callsign == "MENTOR_NAME"
    assert active_mentors(state(game), teacher) == (learner,)
    assert state(game).sheets["3"].girl == "VATGROWN"
    assert state(game).sheets["3"].review.creation.dna_basis
    configure_m3_fixture(ledger)
    acquired = approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, target_rules.RULE),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            ),
        }
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        actual.sheets["3"].heat = 4
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.original_learning_bodies_and_heat", actual)
    game.bind_scene(ADMIN, "actual-easy-learning-scene", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, "actual-easy-learning-join-" + str(viewer.user_id), 900)
    world = WorldService(MissionService(ledger, acquired.registry))
    investor = Npc(
        id="actual-learner-investor",
        name="Original learner scientist",
        jobs=("scientist",),
        controller=1,
        cell=(0, 0),
        revealed=True,
        detail="The genuine saved starting Investor of the actual Vatgrown learner",
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, investor)
    slot = state(game).sheets["3"].review.creation.npc_bonds[0].slot
    world.import_starting_npc(OTHER, str(uuid4()), state(game).revision, slot, investor.id)
    worker, gateway = GameWorker(game), Gateway()
    controls = VatgrownPlaysService(game)
    session = controls.invite(
        OTHER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "My own actual voluntary source with this original native Newgirl teacher",
    )["id"]
    controls.respond(
        PLAYER,
        str(uuid4()),
        session,
        state(game).revision,
        True,
        "The actual original Newgirl confirms only her own voluntary source",
    )
    lesson_action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=session,
            heat=1,
            trigger_confirmed=True,
            context="Our actual original confirmed Vatgrown learning source",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    before = state(game)
    native_choice(
        game,
        PLAYER,
        "vat_sex_learn",
        identities=(before.sheets["2"].identities[1].id,),
        replacements=(before.sheets["3"].identities[0].id,),
        play=(target_rules.RULE,),
        account="The actual Newgirl teacher selects her own Easy Target for one use",
    )
    assert game.inspect(OTHER, lesson_action)["state"] == "complete"
    learned = rules.records(state(game), rules.LearnedPlay)[-1]
    assert (
        learned.actor == learner
        and learned.teacher == teacher
        and learned.rule_id == target_rules.RULE
    )
    controls.send_away(
        PLAYER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual counterpart ends the learner's required stay after the lesson",
    )
    tick(worker, gateway, 6)
    target_controls = EasyTargetService(game)
    teacher_before = state(game).sheets["2"].model_copy(deep=True)
    before_play = state(game)
    calls = game.dice.calls

    def interaction(user=3, channel=900):
        value = current(user, uuid4().int % 1000000000)
        value.channel_id = channel
        return value

    async def native_start():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, target_controls)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("start",)
        selected = interaction()
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("1",), context="I actually misjudge the real live-fire drill")
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    assert target_controls.menu(OTHER, 900)["can_start"]
    asyncio.run(native_start())
    with ledger.engine.connect() as c:
        action = game.action(c, game.lock(c, 900)["action_id"])
    assert action["data"]["learned_play"]["id"] == learned.id
    action_id = action["id"]
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(OTHER, action_id)["receipt"] is None:
        game.roll(OTHER, str(uuid4()), action_id)
    pass_tags(game)
    assert game.dice.calls == calls + 1
    assert state(game).sheets["3"].heat == before_play.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == teacher_before.heat
    assert state(game).sheets["2"].identities == teacher_before.identities
    assert state(game).sheets["2"].assets == teacher_before.assets

    async def owned_choice(viewer, kind, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await target_choice(opened, game, game.decision(viewer, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(4))
        form.values.update(values)
        submitted = interaction(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(
        owned_choice(
            OTHER,
            "easy_target_select",
            select=(teacher.token,),
            account="I choose this actual original other person",
        )
    )
    asyncio.run(owned_choice(PLAYER, "easy_target_tag", account="Underprepared learner"))
    actual_tag = next(x for x in state(game).sheets["3"].tags if x.label == "Underprepared learner")
    assert actual_tag.giver_actor == teacher
    task_context = "The actual incoming drill fire requires the learner to keep her head and evade"
    account = "PRIVATE_LEARNED_REQUEST I request the actual live-fire evasion task"
    asyncio.run(
        owned_choice(
            PLAYER,
            "easy_target_react:" + teacher.token,
            urge=("request",),
            play=("keep_your_head",),
            context=task_context,
            account=account,
        )
    )
    work_id = target_rules.identity(action_id, teacher)
    asyncio.run(
        owned_choice(
            ADMIN,
            "easy_target_validate:" + teacher.token,
            yes=("yes",),
            account="The actual incoming fire has a genuine Keep trigger and real source",
        )
    )
    child_id = child(game, worker, gateway, work_id, viewer=OTHER)
    finish_keep(game, viewer=OTHER)
    assert game.inspect(OTHER, child_id)["state"] == "complete"
    assert game.inspect(OTHER, action_id)["state"] != "complete"
    with ledger.engine.connect() as c:
        work = prove(game, c, state(game), work_id)
        assert work.performance_event and work.child == child_id
        source = target_rules.get(state(game), target_rules.Session, action_id)
        bound = game.action(c, action_id)
        assert source.actor == learner and source.total == 8
        assert prove_consumed(game, c, state(game), bound, target_rules.RULE, source.roll_event)
        assert available(game, c, state(game), learner, target_rules.RULE) is None
    rank = state(game).order.index(3)
    asyncio.run(
        owned_choice(
            PLAYER,
            "easy_target_judge:" + teacher.token,
            yes=("yes",),
            account="The original requester judges the actual completed evasion task done well",
        )
    )
    assert state(game).order.index(3) == max(0, rank - 1)
    assert game.inspect(OTHER, action_id)["state"] == "complete"
    assert not target_controls.menu(OTHER, 900)["can_start"]
    assert state(game).sheets["3"].girl == "VATGROWN"
    assert active_mentors(state(game), teacher) == (learner,)
    assert has_rule(state(game).sheets["2"], target_rules.RULE, "NEWGIRL")
    assert not has_rule(state(game).sheets["3"], target_rules.RULE, "NEWGIRL")
    assert game.dice.calls == calls + 2

    async def private_reopen():
        opened = interaction(channel=999)
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, EasyTargetService(game), work_id)
        content = opened.edit_original_response.call_args.kwargs["content"]
        assert "PRIVATE_LEARNED_REQUEST" in content and "well" in content

    asyncio.run(private_reopen())
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), work_id).completed_event
        assert (
            len(
                [
                    x
                    for x in target_rules.records(state(game), target_rules.Reaction)
                    if x.session == action_id
                ]
            )
            == 1
        )


def test_actual_mockingbird_teacher_learned_person_native_trigger_cancel_receipt_tag_and_end(
    ledger, tmp_path, monkeypatch
):
    """Deferred: one real conversation source; no Mockingbird body or passive copied."""
    from girlframe.discord_adapter.m3_mockingbird_plays import open_book, open_request
    from girlframe.discord_adapter.m3_mockingbird_plays import open_choice as person_choice
    from girlframe.engine import m3_mockingbird as mockingbird
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_mockingbird_state import PERSON
    from girlframe.services.m3_learned_plays import available, prove_consumed
    from girlframe.services.m3_mockingbird_plays import MockingbirdService, prove_learned_trigger
    from girlframe.services.m3_recovery import RecoveryService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, mockingbird.PERSON),
    )
    session, source_action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="My own original Mockingbird confirms only this voluntary source",
    )
    before = state(game)
    learner, teacher = current_ref(before, 2), current_ref(before, 3)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(before.sheets["3"].identities[1].id,),
        replacements=(before.sheets["2"].identities[0].id,),
        play=(mockingbird.PERSON,),
        account="The actual native Mockingbird teaches her actual Person Play for one use",
    )
    assert game.inspect(PLAYER, source_action)["state"] == "complete"
    learned = rules.records(state(game), rules.LearnedPlay)[-1]
    assert learned.rule_id == mockingbird.PERSON and learned.teacher == teacher
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual counterpart ends the required stay after this real lesson",
    )
    tick(worker, gateway, 6)
    person = MockingbirdService(game)
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert state(game).sheets["3"].girl == "MOCKINGBIRD"
    assert not has_rule(state(game).sheets["2"], mockingbird.RISK, "MOCKINGBIRD")
    assert not has_rule(state(game).sheets["2"], mockingbird.CALL, "MOCKINGBIRD")
    teacher_before = state(game).sheets["3"].model_copy(deep=True)

    def interaction(user=2, channel=900):
        value = current(user, uuid4().int % 1000000000)
        value.channel_id = channel
        return value

    account = "My actual conversation attempt.\n  PRIVATE_LEARNED_PERSON_SOURCE"

    async def propose_native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_book(opened, game, actor_ref=learner)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(3))
        form.values.update(play=(PERSON,), targets=(teacher.token,), account=account)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    async def prepare_native(trigger):
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_request(opened, person, trigger.id, continue_source=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("1",), gain=("0",))
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    assert person.preview(PLAYER, 900, learner)["plays"] == [PERSON]
    assert person.preview(PLAYER, 900, learner)["learned_person"]
    asyncio.run(propose_native())
    first = state(game).mockingbird.triggers[-1]
    assert first.learned_source == learned.id and first.actor == learner
    assert first.play == PERSON and first.state == "ready"
    assert first.bonded_source is None and first.changeling_source is None
    assert person.get(PLAYER, first.id)["body"]["account"] == account
    with pytest.raises(WorkflowError):
        person.get(ADMIN, first.id)
    asyncio.run(prepare_native(first))
    with ledger.engine.connect() as c:
        abandoned = game.action(c, game.lock(c, 900)["action_id"])
    assert abandoned["data"]["learned_play"]["id"] == learned.id
    assert abandoned["data"]["mockingbird"]["learned_source"] == learned.id
    calls, initial_heat = game.dice.calls, state(game).sheets["2"].heat
    game.abort(ADMIN, str(uuid4()), abandoned["id"])
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned["id"])
    assert saved["cancellable"] and not saved["rolled"]
    key = str(uuid4())
    restored = recovery.recover(PLAYER, key, abandoned["id"], saved["revision"], cancel=True)
    assert (
        recovery.recover(PLAYER, key, abandoned["id"], saved["revision"], cancel=True) == restored
    )
    assert game.dice.calls == calls and state(game).sheets["2"].heat == initial_heat
    assert not state(game).mockingbird.conversations
    with ledger.engine.connect() as c:
        original = available(game, c, state(game), learner, mockingbird.PERSON)
        assert original and original.id == learned.id and original.claimed_action is None
    person.withdraw(PLAYER, str(uuid4()), first.id)
    assert person.get(PLAYER, first.id)["body"]["state"] == "withdrawn"
    asyncio.run(propose_native())
    current_trigger = state(game).mockingbird.triggers[-1]
    assert current_trigger.id != first.id and current_trigger.learned_source == learned.id
    asyncio.run(prepare_native(current_trigger))
    with ledger.engine.connect() as c:
        action = game.action(c, game.lock(c, 900)["action_id"])
    action_id = action["id"]
    game.dice.faces = (6, 6)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action_id)["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action_id)
    pass_tags(game)
    assert game.dice.calls == calls + 1
    assert state(game).sheets["2"].heat == initial_heat - 1
    assert state(game).sheets["3"].heat == teacher_before.heat
    assert state(game).sheets["3"].assets == teacher_before.assets
    assert state(game).sheets["3"].identities == teacher_before.identities
    assert not person.preview(PLAYER, 900, learner)["plays"]

    async def own_choice(viewer, kind, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await person_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(1))
        form.values.update(values)
        submitted = interaction(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    capabilities = ("words", "sentences", "eye_contact", "deception")
    asyncio.run(own_choice(PLAYER, "mockingbird_person_capabilities", options=capabilities))
    assert game.inspect(PLAYER, action_id)["state"] != "complete"
    asyncio.run(own_choice(OTHER, "mockingbird_person_tag", tag="Actual frozen expression"))
    assert game.inspect(PLAYER, action_id)["state"] == "complete"
    conversation = state(game).mockingbird.conversations[-1]
    assert conversation.actor == learner and conversation.action == action_id
    assert conversation.selected == capabilities and not conversation.low
    assert "expressions" in conversation.unavailable
    tag = next(x for x in state(game).sheets["2"].tags if x.id == conversation.tag)
    assert tag.label == "Actual frozen expression" and tag.giver_actor == teacher
    with ledger.engine.connect() as c:
        latest = next(x for x in state(game).mockingbird.triggers if x.id == current_trigger.id)
        bound = game.action(c, action_id)
        assert prove_learned_trigger(game, c, state(game), latest, bound)
        runtime = state(game).sheets["2"].girl_runtime
        spent = next(x for x in runtime.learned_plays if x.id == learned.id)
        assert prove_consumed(game, c, state(game), bound, mockingbird.PERSON, spent.rolled_event)
        assert available(game, c, state(game), learner, mockingbird.PERSON) is None
    assert not has_rule(state(game).sheets["2"], mockingbird.PERSON, "MOCKINGBIRD")
    assert has_rule(state(game).sheets["3"], mockingbird.PERSON, "MOCKINGBIRD")
    assert state(game).sheets["2"].girl == "VATGROWN"
    tick(worker, gateway, 5)

    async def native_end_and_private_replay():
        opened = interaction(channel=999)
        await opened.response.defer(ephemeral=True)
        await open_request(opened, MockingbirdService(game), current_trigger.id)
        assert (
            "PRIVATE_LEARNED_PERSON_SOURCE"
            in opened.edit_original_response.call_args.kwargs["content"]
        )
        await open_request(opened, MockingbirdService(game), conversation.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "Human words" in form.text()
        form.values["end"] = ("yes",)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native_end_and_private_replay())
    assert person.get(PLAYER, conversation.id)["body"]["ended_event"]
    assert person.get(OTHER, conversation.id)["body"]["allowed"] == list(capabilities)
    with pytest.raises(WorkflowError):
        person.get(ADMIN, conversation.id)
    assert game.dice.calls == calls + 1
    assert len(state(game).mockingbird.conversations) == 1


def test_actual_casualty_lesson_native_high_assault_extra_maneuver_costs_once_and_readback(
    ledger, tmp_path, monkeypatch
):
    """Deferred: actual rolled Assault rider; no Casualty anatomy or independent roll."""
    from girlframe.discord_adapter.m3_battle import open_context
    from girlframe.discord_adapter.m3_engage import open_engage
    from girlframe.engine import m3_casualty as casualty
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_battle import BattleService
    from girlframe.services.m3_learned_plays import available, consumed_no_one_better
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_recovery import RecoveryService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="CASUALTY")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.EXPERIMENT,
            rules.INVESTMENT,
            rules.SEX,
            casualty.BETTER,
        ),
    )
    session, lesson_action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="The actual Casualty teacher voluntarily confirms this source",
    )
    before = state(game)
    learner, teacher = current_ref(before, 2), current_ref(before, 3)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(before.sheets["3"].identities[1].id,),
        replacements=(before.sheets["2"].identities[0].id,),
        play=(casualty.BETTER,),
        account="I teach No One Better once, not my reconstructed body or parts",
    )
    lesson = rules.records(state(game), rules.LearnedPlay)[-1]
    assert (
        lesson.actor == learner and lesson.teacher == teacher and lesson.rule_id == casualty.BETTER
    )
    assert game.inspect(PLAYER, lesson_action)["state"] == "complete"
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The original counterpart actually ends the required stay",
    )
    tick(worker, gateway, 6)
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert not has_rule(state(game).sheets["2"], casualty.GOD, "CASUALTY")
    assert not has_rule(state(game).sheets["2"], casualty.BARELY, "CASUALTY")

    # Genuine cockpit operations retain each original Frame and actual body.
    physical = PhysicalService(ledger)
    for viewer, actor in ((PLAYER, learner), (OTHER, teacher)):
        with ledger.engine.connect() as c:
            pose = resolve(state(game), actor, profiles(c, ledger.campaign_id)).position_sha256
        physical.operate(
            viewer,
            str(uuid4()),
            state(game).revision,
            CockpitAction(
                actor=actor,
                operation="pilot",
                expected_position=pose,
                confirmed=True,
                account="I actually enter and pilot my own original Frame for this battlefield",
            ),
            channel=900,
        )
    battle = BattleService(ledger)

    def declaration():
        data = battle.preview(PLAYER, 900)
        acting = next(x for x in data["actors"] if x["ref"] == learner.model_dump(mode="json"))
        target = next(x for x in data["actors"] if x["ref"] == teacher.model_dump(mode="json"))
        actual = state(game)
        own_frames = {
            x.id for x in actual.sheets["2"].assets if x.family == "frame" and not x.damaged
        }
        other_frames = {
            x.id for x in actual.sheets["3"].assets if x.family == "frame" and not x.damaged
        }
        own = next(x for x in acting["assets"] if x["id"] in own_frames)
        opposing = next(x for x in target["assets"] if x["id"] in other_frames)
        value = Declaration.model_validate_json(
            json.dumps(
                dict(
                    play="all_out_assault",
                    actor=acting["ref"],
                    target=target["ref"],
                    attacking_asset=own["id"],
                    target_asset=opposing["id"],
                    actor_sha256=acting["sha256"],
                    target_sha256=target["sha256"],
                    account="I take this real opening with my own existing Frame Asset",
                )
            )
        )
        offered = battle.propose(PLAYER, str(uuid4()), data["revision"], 900, value)
        battle.confirm(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            offered["id"],
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence="Actual declared opening and reach in this battlefield",
        )
        return offered["id"], own["id"], opposing["id"]

    async def start_native(context):
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_context(opened, battle, context)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, uuid4().int % 1000000000))
        form.values.update(identity=("none",), gain=("0",), pair_share=("0",), heat=("1",))
        submitted = current(2, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    context, _, _ = declaration()
    asyncio.run(start_native(context))
    with ledger.engine.connect() as c:
        abandoned = game.action(c, game.lock(c, 900)["action_id"])
    assert abandoned["data"]["learned_no_one_better"]["id"] == lesson.id
    calls, heat = game.dice.calls, state(game).sheets["2"].heat
    game.abort(ADMIN, str(uuid4()), abandoned["id"])
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned["id"])
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), abandoned["id"], saved["revision"], cancel=True)
    assert game.dice.calls == calls and state(game).sheets["2"].heat == heat
    with ledger.engine.connect() as c:
        value = available(game, c, state(game), learner, casualty.BETTER)
        assert value and value.id == lesson.id and value.claimed_action is None

    context, own_asset, opposing_asset = declaration()
    asyncio.run(start_native(context))
    with ledger.engine.connect() as c:
        action = game.action(c, game.lock(c, 900)["action_id"])
    assert "learned_play" not in action["data"]
    assert action["data"]["learned_no_one_better"]["id"] == lesson.id
    game.dice.faces = (5, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), action["id"])
    pass_tags(game)
    assert state(game).sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    extra = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_assault_extra")
    assert "spent lesson" in game.decision(PLAYER, extra["id"])["engage"]["learned_rider"]

    async def maneuver():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_engage(opened, game, extra["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            maneuvers=("cover",),
            asset_cover=(own_asset,),
            text="Actual cover established with my own existing Frame Asset",
        )
        submitted = current(2, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(maneuver())

    def finish_assault(identity, paid_asset, *, expect_defeat=False):
        for viewer in (ADMIN, PLAYER, OTHER):
            answer(
                game,
                viewer,
                "battle_assault_table",
                flag=False,
                text="This actual opposing Asset has no vast advantage",
            )
        answer(game, ADMIN, "battle_handler", options=("damage_actor_asset",))
        answer(game, PLAYER, "battle_actor_damage", fields={"asset": paid_asset})
        if expect_defeat:
            assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
            owed = [
                row
                for viewer in (PLAYER, OTHER)
                for row in game.choices(viewer)
                if row["kind"] == "battle_defeat" and row["action_id"] == identity
            ]
            assert {row["actor_id"] for row in owed} == {"2", "3"}
            assert len(owed) == 2
            with ledger.engine.connect() as c:
                assert game.lock(c, 900)["action_id"] == identity
            return
        assert game.inspect(PLAYER, identity)["state"] == "complete"
        tick(worker, gateway, 5)

    finish_assault(action["id"], own_asset)
    actual = state(game)
    assert next(x for x in actual.sheets["2"].assets if x.id == own_asset).damaged
    assert next(x for x in actual.sheets["3"].assets if x.id == opposing_asset).damaged
    maneuvers = [json.loads(x["body"]) for x in actual.facts if x.get("kind") == "engage_maneuver"]
    assert any(x["kind"] == "cover" and x["source_action"] == action["id"] for x in maneuvers)
    with ledger.engine.connect() as c:
        completed = game.action(c, action["id"])
        assert consumed_no_one_better(game, c, actual, completed)
        assert available(game, c, actual, learner, casualty.BETTER) is None
        spent = next(x for x in actual.sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
        assert spent.rolled_event == completed["data"]["learned_no_one_better"]["resolved_event"]
    assert not has_rule(actual.sheets["2"], casualty.BETTER, "CASUALTY")
    receipt = game.inspect(PLAYER, action["id"])["receipt"]

    async def private_reopen():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await open_context(opened, battle, context)
        assert "spent once" in str(opened.edit_original_response.call_args)

    asyncio.run(private_reopen())
    with pytest.raises(WorkflowError):
        battle.context(OTHER, context)
    second_context, second_asset, _ = declaration()
    asyncio.run(start_native(second_context))
    with ledger.engine.connect() as c:
        second = game.action(c, game.lock(c, 900)["action_id"])
    assert "learned_no_one_better" not in second["data"]
    game.dice.faces = (5, 5)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, second["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), second["id"])
    pass_tags(game)
    assert not any(x["kind"] == "engage_assault_extra" for x in game.choices(PLAYER))
    # Both real two-Asset Frames are now exhausted. Their actual Defeat work
    # remains owed; a reuse check must not invent resources or skip those Plays.
    finish_assault(second["id"], second_asset, expect_defeat=True)
    assert game.inspect(PLAYER, action["id"])["receipt"] == receipt
    assert game.dice.calls == calls + 2 and state(game).sheets["2"].girl == "VATGROWN"


def test_actual_princess_two_lessons_native_selected_keep_then_winning_self_flirt_tag(
    ledger, tmp_path, monkeypatch
):
    """Deferred: explicit one-lesson activation; no passive or multiple-use grant."""
    from girlframe.discord_adapter.m2_ui import open_choice, open_play
    from girlframe.engine.m3_girl_runtime_state import has_rule, keep_automatic
    from girlframe.engine.m3_mockingbird import give_tag
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_learned_plays import (
        BEAUTIFUL,
        ELDER,
        ITCHING,
        active_keep_rider_rule,
        keep_rider_rule,
        prepare_keep_riders,
    )

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="PRINCESS")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.EXPERIMENT,
            rules.INVESTMENT,
            rules.SEX,
            BEAUTIFUL,
            ITCHING,
            ELDER,
        ),
    )
    learner, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    lessons = []
    for _ in range(2):
        session, action = sex(
            game,
            worker,
            gateway,
            controls,
            (5, 5),
            counterpart_account="The actual Princess confirms this distinct voluntary lesson",
        )
        actual = state(game)
        replacement = actual.sheets["2"].identities[0]
        remaining = {
            x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id
        }
        taught = next(
            x for x in actual.sheets["3"].identities if x.name.casefold() not in remaining
        )
        native_choice(
            game,
            OTHER,
            "vat_sex_learn",
            identities=(taught.id,),
            replacements=(replacement.id,),
            play=(BEAUTIFUL,),
            account="I teach my actual Objectively Beautiful Play once through this real source",
        )
        lessons.append(rules.records(state(game), rules.LearnedPlay)[-1])
        assert game.inspect(PLAYER, action)["state"] == "complete"
        controls.send_away(
            OTHER,
            str(uuid4()),
            session,
            state(game).revision,
            "The actual original Princess sends her away after this lesson",
        )
        tick(worker, gateway, 6)
    assert lessons[0].id != lessons[1].id
    assert all(
        x.actor == learner and x.teacher == teacher and x.rule_id == BEAUTIFUL for x in lessons
    )
    actual = state(game)
    assert actual.sheets["2"].girl == "VATGROWN" and actual.sheets["3"].girl == "PRINCESS"
    assert not has_rule(actual.sheets["2"], BEAUTIFUL, "PRINCESS")
    assert keep_automatic(actual.sheets["2"]) == frozenset()
    assert "sexy" in keep_automatic(actual.sheets["3"])
    with ledger.engine.connect() as c:
        menu = prepare_keep_riders(game, c, actual, learner, "keep_your_head")
        assert {x["id"] for x in menu} == {x.id for x in lessons}

    def interaction(user=2):
        shown = current(user, uuid4().int % 1000000000)
        shown.channel_id = 900
        return shown

    async def begin_native(play, lesson, heat):
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(3))
        form.values.update(
            play=(play,),
            heat=(str(heat),),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            learned_keep_rider=(lesson.id,),
            context="My actual selected one-use lesson with my own original resources",
            trigger=("yes",),
        )
        if play == "flirt":
            form.values["target"] = ("3",)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.response.send_message.call_args_list,
            submitted.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved
        with ledger.engine.connect() as c:
            return game.action(c, game.lock(c, 900)["action_id"])

    async def reply_native(viewer, row, **values):
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = interaction(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.response.send_message.call_args_list,
            submitted.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    heat, calls = actual.sheets["2"].heat, game.dice.calls
    keep = asyncio.run(begin_native("keep_your_head", lessons[0], 1))
    assert keep["data"]["learned_keep_rider"]["id"] == lessons[0].id
    assert "learned_play" not in keep["data"] and "learned_no_one_better" not in keep["data"]
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, keep["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), keep["id"])
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    assert game.decision(PLAYER, row["id"])["learned_keep_rule"] == BEAUTIFUL
    asyncio.run(reply_native(PLAYER, row, options=("tough", "in_control"), denied=("vicious",)))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
    asyncio.run(
        reply_native(ADMIN, row, flag=("yes",), text="The real displayed traits are enough")
    )
    with ledger.engine.connect() as c:
        completed = game.action(c, keep["id"])
        assert keep_rider_rule(game, c, state(game), completed) == BEAUTIFUL
        assert "sexy" in completed["data"]["result"]["positive"]
        runtime = state(game).sheets["2"].girl_runtime
        assert next(x for x in runtime.learned_plays if x.id == lessons[0].id).rolled_event
        assert next(x for x in runtime.learned_plays if x.id == lessons[1].id).rolled_event is None
    assert game.inspect(PLAYER, keep["id"])["state"] == "complete"
    keep_receipt = game.inspect(PLAYER, keep["id"])["receipt"]
    assert state(game).sheets["2"].heat == heat - 1 and game.dice.calls == calls + 1
    tick(worker, gateway, 6)

    tag_id, tag_event = str(uuid4()), str(uuid4())
    with ledger.transaction() as c:
        tagged = give_tag(
            state(game),
            profiles(c, ledger.campaign_id),
            learner,
            teacher,
            "Actual owned attractive composure",
            tag_id,
            tag_event,
            (1, 2, 3),
        )
        game.event(
            c, 3, str(uuid4()), "synthetic.actual_original_giver_tag", tagged, event_id=tag_event
        )
    flirt = asyncio.run(begin_native("flirt", lessons[1], 0))
    assert flirt["data"]["learned_keep_rider"]["id"] == lessons[1].id
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, flirt["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), flirt["id"])
    with ledger.engine.connect() as c:
        held = game.action(c, flirt["id"])
        assert active_keep_rider_rule(game, c, state(game), held) == BEAUTIFUL
    own = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    asyncio.run(
        reply_native(
            PLAYER,
            own,
            options=("tag",),
            denied=(tag_id,),
            number=("1",),
            text="My actual attractive composure is relevant to this real Flirt",
        )
    )
    # A real proposal has not won or marked anything while the table is still replying.
    assert not next(x for x in state(game).sheets["2"].tags if x.id == tag_id).marked
    assert (
        next(
            x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lessons[1].id
        ).rolled_event
        is None
    )
    for viewer in (OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    actual = state(game)
    assert next(x for x in actual.sheets["2"].tags if x.id == tag_id).marked
    with ledger.engine.connect() as c:
        applied = game.action(c, flirt["id"])
        assert keep_rider_rule(game, c, actual, applied) == BEAUTIFUL
        assert active_keep_rider_rule(game, c, actual, applied) is None
        assert applied["data"]["learned_keep_rider"]["tag"] == tag_id
        assert applied["data"]["result"]["total"] == 8
        assert any(
            x.get("tag") == tag_id and x["actor"] == 2 and x["amount"] == 1
            for x in applied["data"]["modifiers"]
        )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt")
    asyncio.run(reply_native(PLAYER, row, options=("name",)))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
    asyncio.run(reply_native(OTHER, row, text="The original Princess gives her own actual answer"))
    assert game.inspect(PLAYER, flirt["id"])["state"] == "complete"
    assert game.inspect(PLAYER, keep["id"])["receipt"] == keep_receipt
    assert game.dice.calls == calls + 2 and state(game).sheets["2"].heat == heat - 1
    with ledger.engine.connect() as c:
        assert prepare_keep_riders(game, c, state(game), learner, "keep_your_head") == ()
        assert prepare_keep_riders(game, c, state(game), learner, "flirt") == ()
        assert keep_rider_rule(game, c, state(game), game.action(c, keep["id"])) == BEAUTIFUL
        assert keep_rider_rule(game, c, state(game), game.action(c, flirt["id"])) == BEAUTIFUL
    assert keep_automatic(state(game).sheets["2"]) == frozenset()
    tick(worker, gateway, 5)


def test_actual_alpha_hound_lesson_native_status_mark_then_real_rank_clear(
    ledger, tmp_path, monkeypatch
):
    """Deferred: true initial Dog, an actual Status cost, and a source-backed clear."""
    from girlframe.discord_adapter.m2_ui import open_choice, open_play
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_intracadre_marriage import is_dog
    from girlframe.engine.m3_learned_play_state import active_hound_status, hound_status_uses
    from girlframe.services.m3_learned_plays import HOUND, available, prove_hound_status

    original_rank = creation_fixture.HandlerService.rank
    ranked = False

    def initial_dog(handler, viewer, key, expected, order):
        nonlocal ranked
        if not ranked:
            result = original_rank(
                handler,
                viewer,
                key,
                expected,
                tuple(sorted(order, key=lambda x: x.user_id != OTHER.user_id)),
            )
            ranked = True
            return result
        return original_rank(handler, viewer, key, expected, order)

    monkeypatch.setattr(creation_fixture.HandlerService, "rank", initial_dog)
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="ALPHA")
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, HOUND),
    )
    learner, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    assert state(game).order == (3, 2) and is_dog(state(game), 2)
    session, source_action = sex(game, worker, gateway, controls, (5, 5))
    actual = state(game)
    replacement = actual.sheets["2"].identities[0]
    remaining = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(x for x in actual.sheets["3"].identities if x.name.casefold() not in remaining)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(HOUND,),
        account="The actual Alpha teaches her Status-marking Play once",
    )
    lesson = rules.records(state(game), rules.LearnedPlay)[-1]
    assert lesson.actor == learner and lesson.teacher == teacher and lesson.rule_id == HOUND
    assert game.inspect(PLAYER, source_action)["state"] == "complete"
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The original Alpha releases the actual learner after this lesson",
    )
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], HOUND, "ALPHA")
    assert has_rule(state(game).sheets["3"], HOUND, "ALPHA")

    def interaction(user=2):
        shown = current(user, uuid4().int % 1000000000)
        shown.channel_id = 900
        return shown

    async def begin_native(play, heat):
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=(play,),
            trigger=("yes",),
            heat=(str(heat),),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="My actual original Girl performs this real source with her own resources",
        )
        if play == "put_someone_beneath_you":
            form.values["target"] = ("3",)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.response.send_message.call_args_list,
            submitted.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved
        with ledger.engine.connect() as c:
            return game.action(c, game.lock(c, 900)["action_id"])

    async def native_answer(viewer, row, **values):
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = interaction(viewer.user_id)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.response.send_message.call_args_list,
            submitted.edit_original_response.call_args_list,
        )
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    heat, calls = state(game).sheets["2"].heat, game.dice.calls
    keep = asyncio.run(begin_native("keep_your_head", 1))
    assert "learned_play" not in keep["data"] and "learned_hound_status" not in keep["data"]
    game.dice.faces = (3, 3)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, keep["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), keep["id"])
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    assert game.decision(PLAYER, row["id"])["learned_hound_available"]
    with ledger.engine.connect() as c:
        assert available(game, c, state(game), learner, HOUND).id == lesson.id
    asyncio.run(native_answer(PLAYER, row, options=("pass",), **{"fields.status": ("1",)}))
    actual = state(game)
    mark = active_hound_status(actual, learner)
    assert actual.sheets["2"].status_marked and mark and mark.lesson == lesson.id
    assert is_dog(actual, 2) and actual.order == (3, 2)
    with ledger.engine.connect() as c:
        action = game.action(c, keep["id"])
        assert prove_hound_status(game, c, actual, action) == 1
        assert action["data"]["modifiers"] == [dict(source="alpha_status", amount=1)]
        assert available(game, c, actual, learner, HOUND) is None
    for viewer in (OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    asyncio.run(native_answer(PLAYER, row, options=("tough", "in_control"), denied=("vicious",)))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
    asyncio.run(
        native_answer(ADMIN, row, flag=("yes",), text="The real adjusted mid result is enough")
    )
    assert game.inspect(PLAYER, keep["id"])["state"] == "complete"
    assert game.inspect(PLAYER, keep["id"])["result"]["total"] == 8
    receipt = game.inspect(PLAYER, keep["id"])["receipt"]
    assert receipt["pre_total"] == 7 and state(game).sheets["2"].heat == heat - 1
    assert state(game).sheets["2"].status_marked and game.dice.calls == calls + 1
    tick(worker, gateway, 6)

    # A genuine ordinary source lowers the former Ace; no rank setter or fake
    # Punishment is used merely to clear the learned mark.
    beneath = asyncio.run(begin_native("put_someone_beneath_you", 0))
    game.dice.faces = (4, 4)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, beneath["id"])["receipt"] is None:
        game.roll(PLAYER, str(uuid4()), beneath["id"])
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "Actually put beneath the former Dog"},
        text="The original Girl actually puts this counterpart beneath her",
    )
    actual = state(game)
    assert game.inspect(PLAYER, beneath["id"])["state"] == "complete"
    assert actual.order == (2, 3) and not is_dog(actual, 2)
    assert not actual.sheets["2"].status_marked and active_hound_status(actual, learner) is None
    ended = next(x for x in hound_status_uses(actual) if x.id == mark.id)
    assert ended.clear_reason == "rank" and ended.cleared_event
    with ledger.engine.connect() as c:
        assert prove_hound_status(game, c, actual, game.action(c, keep["id"])) == 1
        assert available(game, c, actual, learner, HOUND) is None
    # An uncommitted projection checks that a later independent boolean could
    # not revive this ended source; it grants or writes no campaign resource.
    projection = actual.model_copy(deep=True)
    projection.sheets["2"].status_marked = True
    assert active_hound_status(projection, learner) is None
    assert game.inspect(PLAYER, keep["id"])["receipt"] == receipt
    assert game.dice.calls == calls + 2 and actual.sheets["2"].girl == "VATGROWN"
    tick(worker, gateway, 5)


def test_actual_learned_risk_paid_last_frame_void_holds_real_keep_resistance_and_private_replay(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m2_ui import open_choice, open_play
    from girlframe.discord_adapter.m3_void_keep import open_keep
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_learned_play_state import risk_lesson_uses
    from girlframe.engine.m3_mockingbird import RISK
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_learned_plays import available, prove_risk_lesson, prove_risk_ward
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, RISK),
    )
    learner = current_ref(state(game), 2)

    # Actual ordinary Dive effects produce every prior Void component. The
    # final component stays uncorrupted for the later real Risk payment.
    frames = [x.id for x in state(game).sheets["2"].assets if x.family == "frame"]
    assert len(frames) >= 2
    for asset in frames[:-1]:
        game.dice.faces = (3, 3)
        dive = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="dive_deep",
                heat=0,
                trigger_confirmed=True,
                context="Actual communion through my original nearby Frame link",
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        chooser = next(
            viewer
            for viewer in (PLAYER, ADMIN)
            if any(row["kind"] == "dive_select" for row in game.choices(viewer))
        )
        answer(
            game,
            chooser,
            "dive_select",
            options=("void_and_unmark_all",),
            text="The actual Dive changes this original component",
        )
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"asset": asset},
            text="Real linked Frame housing becomes flesh-threaded Void",
        )
        assert game.inspect(PLAYER, dive)["state"] == "complete"
        assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
        tick(worker, gateway, 6)

    session, lesson_action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="My actual Mockingbird voluntarily teaches this printed whole Play",
    )
    before = state(game)
    replacement = before.sheets["2"].identities[0]
    remaining = {x.name.casefold() for x in before.sheets["2"].identities if x.id != replacement.id}
    taught = next(x for x in before.sheets["3"].identities if x.name.casefold() not in remaining)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(RISK,),
        account="I teach one Risk Factor use, including its own printed protection",
    )
    lesson = rules.records(state(game), rules.LearnedPlay)[-1]
    assert game.inspect(PLAYER, lesson_action)["state"] == "complete"
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual teacher ends the printed required stay",
    )
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], RISK, "MOCKINGBIRD")
    with ledger.engine.connect() as c:
        assert available(game, c, state(game), learner, RISK).id == lesson.id
        position = resolve(state(game), learner, profiles(c, ledger.campaign_id)).position_sha256
    PhysicalService(ledger).operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=learner,
            operation="sit",
            expected_position=position,
            confirmed=True,
            account="I actually enter my co-located original Frame",
        ),
        channel=900,
    )

    def interaction(user=2):
        opened = current(user, uuid4().int % 1000000000)
        opened.channel_id = 900
        return opened

    async def start_keep():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("keep_your_head",),
            trigger=("yes",),
            heat=("0",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="I actually keep control inside my almost entirely Void Frame",
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args_list,
            sent.edit_original_response.call_args_list,
        )
        with ledger.engine.connect() as c:
            return game.lock(c, 900)["action_id"]

    game.dice.faces = (1, 2)
    parent = asyncio.run(start_keep())
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, parent)["receipt"]
    calls, heat = game.dice.calls, state(game).sheets["2"].heat
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_risk")

    async def pay():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "one-use lesson" in form.text()
        assert not await form.interaction_check(interaction(3))
        form.values.update(
            total=("9",),
            asset=(frames[-1],),
            description="PRIVATE_LEARNED_RISK The last actual housing becomes Void",
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(pay())
    actual = state(game)
    use = risk_lesson_uses(actual)[-1]
    assert use.lesson == lesson.id and use.actor == learner and use.work
    assert all(x.void for x in actual.sheets["2"].assets if x.family == "frame")
    assert actual.sheets["2"].girl == "VATGROWN" and not has_rule(
        actual.sheets["2"], RISK, "MOCKINGBIRD"
    )
    assert game.inspect(PLAYER, parent)["receipt"] == raw and game.dice.calls == calls
    assert actual.sheets["2"].heat == heat
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The original real defense is enough")
    work = use.work[0]
    void = VoidService(ledger)
    assert void.get(PLAYER, work)["stage"] == "resist_pending"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    with ledger.engine.connect() as c:
        assert prove_risk_lesson(game, c, state(game), game.action(c, parent)) == use
        threshold = next(x for x in state(game).void_thresholds if work in x.source_works)
        assert prove_risk_ward(game, c, state(game), threshold) == use
        assert available(game, c, state(game), learner, RISK) is None

    async def resist():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_keep(opened, game, work)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            heat=("0",), account="My real resistance to this payment's original Frame"
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list

    game.dice.faces = (4, 4)
    asyncio.run(resist())
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER))
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The genuine linked resistance is enough")
    assert void.get(PLAYER, work)["stage"] == "prevented"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == raw and game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        assert prove_risk_lesson(game, c, state(game), game.action(c, parent)) == use
    assert "PRIVATE_LEARNED_RISK" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)


def test_actual_unused_risk_defense_other_dive_source_native_keep_and_original_completion(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_void import open_void
    from girlframe.discord_adapter.m3_void_keep import open_keep
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_learned_play_state import defensive_risk_uses, risk_lesson_uses
    from girlframe.engine.m3_mockingbird import RISK
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_learned_plays import available, prove_risk_ward
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, RISK),
    )
    session, lesson_action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="My actual Mockingbird voluntarily teaches this whole one-use Play",
    )
    actual = state(game)
    learner = current_ref(actual, 2)
    replacement = actual.sheets["2"].identities[0]
    retained = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(x for x in actual.sheets["3"].identities if x.name.casefold() not in retained)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(RISK,),
        account="I teach Risk Factor once, including deliberate defensive use",
    )
    lesson = rules.records(state(game), rules.LearnedPlay)[-1]
    assert game.inspect(PLAYER, lesson_action)["state"] == "complete"
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The original teacher actually ends the required stay",
    )
    tick(worker, gateway, 6)
    frames = [x.id for x in state(game).sheets["2"].assets if x.family == "frame"]
    assert len(frames) >= 2
    physical = PhysicalService(ledger)
    for index, asset in enumerate(frames):
        if index == len(frames) - 1:
            with ledger.engine.connect() as c:
                pose = resolve(
                    state(game), learner, profiles(c, ledger.campaign_id)
                ).position_sha256
            physical.operate(
                PLAYER,
                str(uuid4()),
                state(game).revision,
                CockpitAction(
                    actor=learner,
                    operation="sit",
                    expected_position=pose,
                    account="I actually enter my original co-located Frame",
                    confirmed=True,
                ),
                channel=900,
            )
        game.dice.faces = (3, 3)
        dive = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="dive_deep",
                heat=0,
                trigger_confirmed=True,
                context="I actually commune through my original Frame link",
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        # The offered numeric shift is explicitly declined. It neither pays
        # Void nor spends the separate defensive-only source entitlement.
        answer(game, PLAYER, "mockingbird_risk")
        with ledger.engine.connect() as c:
            assert available(game, c, state(game), learner, RISK).id == lesson.id
        chooser = next(
            viewer
            for viewer in (PLAYER, ADMIN)
            if any(row["kind"] == "dive_select" for row in game.choices(viewer))
        )
        answer(
            game,
            chooser,
            "dive_select",
            options=("void_and_unmark_all",),
            text="This genuine Dive result alters the actual original component",
        )
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"asset": asset},
            text="Actual Frame component becomes flesh-threaded Void through communion",
        )
        assert next(x for x in state(game).sheets["2"].assets if x.id == asset).void
        if index < len(frames) - 1:
            assert game.inspect(PLAYER, dive)["state"] == "complete"
            tick(worker, gateway, 6)
    assert not risk_lesson_uses(state(game))
    assert not has_rule(state(game).sheets["2"], RISK, "MOCKINGBIRD")
    assert game.inspect(PLAYER, dive)["state"] != "complete"
    with ledger.engine.connect() as c:
        rows = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                    t.m3["m3_required_work"].c.kind == "void_threshold",
                    t.m3["m3_required_work"].c.state == "pending",
                )
            )
            .mappings()
            .all()
        )
        work = next(
            x["id"] for x in rows if json.loads(x["body_json"]).get("source_action") == dive
        )
    void = VoidService(ledger)
    before = void.get(PLAYER, work)
    assert before["stage"] == "enclosed" and before["defensive_risk_lessons"][0]["id"] == lesson.id
    assert "defensive_risk_lessons" not in void.get(ADMIN, work)
    raw = game.inspect(PLAYER, dive)["receipt"]
    calls, heat = game.dice.calls, state(game).sheets["2"].heat
    cause = before["threshold"]

    def interaction(user=2):
        opened = current(user, uuid4().int % 1000000000)
        opened.channel_id = 900
        return opened

    async def defend():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_void(opened, void, work)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(interaction(3))
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_void(opened, void, work, operation="use_risk_lesson")
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "adds no Void payment or dice" in form.text()
        form.values.update(
            lesson=(lesson.id,),
            account="PRIVATE_RISK_DEFENSE I use this lesson only for this real Dive source",
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(defend())
    actual = state(game)
    use = defensive_risk_uses(actual)[-1]
    after = void.get(PLAYER, work)
    assert use.lesson == lesson.id and use.actor == learner and use.cause_action == dive
    assert after["stage"] == "resist_pending" and after["learned_risk_ward"]
    assert not after["defensive_risk_lessons"]
    for name in (
        "id",
        "actor",
        "frame_instance",
        "family",
        "source_event",
        "source_action",
        "source_works",
    ):
        assert after["threshold"][name] == cause[name]
    assert game.dice.calls == calls and actual.sheets["2"].heat == heat
    assert game.inspect(PLAYER, dive)["receipt"] == raw and not risk_lesson_uses(actual)
    with ledger.engine.connect() as c:
        assert available(game, c, actual, learner, RISK) is None
        threshold = next(x for x in actual.void_thresholds if x.id == use.threshold)
        assert prove_risk_ward(game, c, actual, threshold) == use
        spent = next(x for x in actual.sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
        assert spent.claimed_action is None and spent.rolled_event == use.event
    with pytest.raises(WorkflowError):
        void.respond(
            PLAYER,
            str(uuid4()),
            work,
            before["revision"],
            before["game_revision"],
            before["expected"],
            "use_risk_lesson",
            dict(lesson=lesson.id, account="No duplicate"),
        )

    async def resist():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_keep(opened, game, work)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            heat=("0",), account="My actual resistance to this original Void consequence"
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list

    game.dice.faces = (4, 4)
    asyncio.run(resist())
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER))
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="This genuine defensive Keep is enough")
    assert void.get(PLAYER, work)["stage"] == "prevented"
    assert game.inspect(PLAYER, dive)["state"] == "complete"
    assert game.inspect(PLAYER, dive)["receipt"] == raw and game.dice.calls == calls + 1
    assert not has_rule(state(game).sheets["2"], RISK, "MOCKINGBIRD")
    with ledger.engine.connect() as c:
        threshold = next(x for x in state(game).void_thresholds if x.id == use.threshold)
        assert prove_risk_ward(game, c, state(game), threshold) == use
    assert "PRIVATE_RISK_DEFENSE" not in json.dumps(gateway.messages)

    async def reopen():
        from girlframe.discord_adapter.ledger import clean

        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_void(opened, void, work)
        assert clean(use.account) in opened.edit_original_response.call_args.kwargs["content"]

    asyncio.run(reopen())
    assert "defensive_risk_use" not in void.get(ADMIN, work)
    tick(worker, gateway, 6)


def test_actual_learned_call_native_classification_guest_and_gorgon_keep_original_sources(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m2_ui import open_choice, open_play
    from girlframe.discord_adapter.m3_mockingbird_communion import open_call
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_learned_play_state import call_lesson_uses
    from girlframe.engine.m3_mockingbird import CALL
    from girlframe.engine.m3_physical_state import CockpitAction
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_learned_plays import prepare_call_lessons, prove_call_lesson
    from girlframe.services.m3_mockingbird_communion import CallService
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_recovery import RecoveryService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, CALL),
    )
    world = WorldService(MissionService(ledger))
    world.reveal(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "secret",
        "The actual original Cadre encounters the nearby original Gorgon",
    )
    learner = current_ref(state(game), 2)
    teacher = current_ref(state(game), 3)

    def learn():
        session, source = sex(
            game,
            worker,
            gateway,
            controls,
            (5, 5),
            counterpart_account="The real Mockingbird voluntarily offers this one-use Call lesson",
        )
        before = state(game)
        replacement = before.sheets["2"].identities[0]
        retained = {
            x.name.casefold() for x in before.sheets["2"].identities if x.id != replacement.id
        }
        identity = next(
            x for x in before.sheets["3"].identities if x.name.casefold() not in retained
        )
        native_choice(
            game,
            OTHER,
            "vat_sex_learn",
            identities=(identity.id,),
            replacements=(replacement.id,),
            play=(CALL,),
            account="I teach the whole Call of the Void once, not my body or Frame",
        )
        lesson = rules.records(state(game), rules.LearnedPlay)[-1]
        assert game.inspect(PLAYER, source)["state"] == "complete"
        controls.send_away(
            OTHER,
            str(uuid4()),
            session,
            state(game).revision,
            "The real teacher ends the actual source stay",
        )
        tick(worker, gateway, 6)
        assert not has_rule(state(game).sheets["2"], CALL, "MOCKINGBIRD")
        return lesson

    def interaction(user=2):
        opened = current(user, uuid4().int % 1000000000)
        opened.channel_id = 900
        return opened

    async def begin(lesson):
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("dive_deep",),
            learned_call=(lesson.id,),
            trigger=("yes",),
            heat=("0",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="I explicitly offer this lesson for my actual Dive",
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args_list,
            sent.edit_original_response.call_args_list,
        )
        with ledger.engine.connect() as c:
            return game.lock(c, 900)["action_id"]

    async def choose(viewer, kind, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = interaction(viewer.user_id)
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args_list,
            sent.edit_original_response.call_args_list,
        )
        return row

    first = learn()
    # A true unrolled cancellation releases only the reservation, not a spent
    # source. The real new confirmation below selects that same lesson again.
    calls = game.dice.calls
    abandoned = asyncio.run(begin(first))
    game.abort(ADMIN, str(uuid4()), abandoned)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == abandoned)
    recovery.recover(PLAYER, str(uuid4()), abandoned, saved["revision"], cancel=True)
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert prepare_call_lessons(game, c, state(game), learner, "dive_deep")[0]["id"] == first.id
    tick(worker, gateway, 5)
    first_dive = asyncio.run(begin(first))
    game.dice.faces = (4, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    original = state(game).sheets["2"].model_copy(deep=True)
    girl = next(x for x in original.assets if x.family == "girl")
    frame = next(x for x in original.assets if x.family == "frame")
    raw = game.inspect(PLAYER, first_dive)["receipt"]
    asyncio.run(
        choose(
            PLAYER,
            "dive_select",
            option=("call_reclassify_assets",),
            account="I move these original components between their real source families",
        )
    )
    asyncio.run(choose(PLAYER, "dive_effect", moves=(girl.id, frame.id)))
    after = state(game).sheets["2"]
    assert next(x.family for x in after.assets if x.id == girl.id) == "frame"
    assert next(x.family for x in after.assets if x.id == frame.id) == "girl"
    assert [(x.id, x.void, x.damaged, x.description) for x in after.assets] == [
        (x.id, x.void, x.damaged, x.description) for x in original.assets
    ]
    assert game.inspect(PLAYER, first_dive)["state"] == "complete"
    assert game.inspect(PLAYER, first_dive)["receipt"] == raw and game.dice.calls == calls + 1
    with ledger.engine.connect() as c:
        assert (
            prove_call_lesson(game, c, state(game), game.action(c, first_dive)).lesson == first.id
        )
        assert not prepare_call_lessons(game, c, state(game), learner, "dive_deep")
    tick(worker, gateway, 6)

    second = learn()
    assert second.id != first.id
    with ledger.engine.connect() as c:
        pose = resolve(state(game), learner, profiles(c, ledger.campaign_id)).position_sha256
    PhysicalService(ledger).operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=learner,
            operation="sit",
            expected_position=pose,
            confirmed=True,
            account="I actually enter my original co-located cockpit",
        ),
        channel=900,
    )
    second_dive = asyncio.run(begin(second))
    game.dice.faces = (6, 6)
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, second_dive)["receipt"]
    calls = game.dice.calls
    asyncio.run(
        choose(
            PLAYER,
            "dive_select",
            option=("call_cockpit_guest",),
            account="I invite this actual original person into my actual cockpit",
        )
    )
    asyncio.run(
        choose(
            PLAYER,
            "dive_effect",
            target=(teacher.token,),
            account="My invitation is voluntary and refers to our real co-located bodies",
        )
    )
    communion = CallService(game)
    guest_call = state(game).mockingbird.calls[-1]
    assert guest_call.actor == learner and guest_call.guest == teacher
    assert game.inspect(PLAYER, second_dive)["state"] != "complete"

    async def reply(viewer, identity, **values):
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_call(opened, communion, identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(interaction(2 if viewer == OTHER else 3))
        form.values.update(values)
        sent = interaction(viewer.user_id)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        return form

    asyncio.run(
        reply(
            OTHER,
            guest_call.id,
            decision=("accept",),
            account="I actually accept and board this original cockpit",
        )
    )
    with ledger.engine.connect() as c:
        aboard = resolve(state(game), teacher, profiles(c, ledger.campaign_id))
        carrier = resolve(state(game), learner, profiles(c, ledger.campaign_id))
    assert aboard.inside_frame and aboard.occupied_frame_instance == carrier.frame_instance
    cost = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.void)
    communion.respond(
        OTHER,
        str(uuid4()),
        guest_call.id,
        communion.get(OTHER, guest_call.id)["revision"],
        "effect",
        dict(
            option="void_and_unmark_all",
            asset=cost.id,
            description="The real guest chooses her own actual Void cost",
            account="My own choice uses my resources, not the learner's",
        ),
    )
    assert next(x for x in state(game).sheets["3"].assets if x.id == cost.id).void
    # The genuine high Dive's Handler choice uses the same held lesson, not
    # another lesson or an invented permission from the Gorgon.
    asyncio.run(
        choose(
            ADMIN,
            "dive_select",
            option=("call_gorgon_relay",),
            account="The actual Frame relays communion to the actual nearby Gorgon",
        )
    )
    gorgon = ActorRef(kind="gorgon", entity="secret")
    asyncio.run(
        choose(
            PLAYER,
            "dive_effect",
            target=(gorgon.token,),
            account="PRIVATE_LEARNED_CALL What do you actually want from this place?",
        )
    )
    relay = state(game).mockingbird.calls[-1]
    assert relay.source_action == second_dive and relay.guest == gorgon
    assert communion.get(OTHER, relay.id)["message"] == ""
    asyncio.run(
        reply(
            ADMIN,
            relay.id,
            decision=("accept",),
            account="PRIVATE_GORGON_REPLY The real controller authors this reply",
        )
    )
    assert game.inspect(PLAYER, second_dive)["state"] == "complete"
    assert game.inspect(PLAYER, second_dive)["receipt"] == raw and game.dice.calls == calls
    uses = call_lesson_uses(state(game))
    assert [x.lesson for x in uses] == [first.id, second.id] and all(x.used for x in uses)
    assert communion.get(PLAYER, relay.id)["answer"].startswith("PRIVATE_GORGON_REPLY")
    with ledger.engine.connect() as c:
        assert (
            prove_call_lesson(game, c, state(game), game.action(c, first_dive)).lesson == first.id
        )
        assert (
            prove_call_lesson(game, c, state(game), game.action(c, second_dive)).lesson == second.id
        )
        assert not prepare_call_lessons(game, c, state(game), learner, "dive_deep")
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert not has_rule(state(game).sheets["2"], CALL, "MOCKINGBIRD")
    assert "PRIVATE_LEARNED_CALL" not in json.dumps(gateway.messages)
    assert "PRIVATE_GORGON_REPLY" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)


def _learn_daily_source(game, worker, gateway, controls, rule):
    session, action = sex(
        game,
        worker,
        gateway,
        controls,
        (5, 5),
        counterpart_account="My actual original person teaches this printed source voluntarily",
    )
    actual = state(game)
    replacement = actual.sheets["2"].identities[0]
    retained = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(x for x in actual.sheets["3"].identities if x.name.casefold() not in retained)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(rule,),
        account="The original teacher chooses this actual one-use lesson",
    )
    lesson = rules.records(state(game), rules.LearnedPlay)[-1]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual original counterpart ends the required source stay",
    )
    tick(worker, gateway, 6)
    return lesson


def _native_daily_roll(game, cycle, period, field, lesson):
    from girlframe.discord_adapter.m3_off_duty_cycle import open_action

    async def begin():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_action(opened, cycle, period, "play")
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(x.key == field for x in form.fields)
        form.values.update(
            context="My actual original time at this real Foundation base",
            gain=("0",),
            share=("0",),
            confirm=("yes",),
            **{field: (lesson.id,)},
        )
        if any(x.key == "disposable_heat" for x in form.fields):
            form.values["disposable_heat"] = ("0",)
        sent = current(2, uuid4().int % 1000000000)
        sent.channel_id = 900
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args_list,
            sent.edit_original_response.call_args_list,
        )
        with game.store.engine.connect() as c:
            return game.lock(c, 900)["action_id"]

    return asyncio.run(begin())


def test_actual_princess_show_dog_lesson_native_off_duty_two_choices_bond_and_private_message(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_show_dog import open_show_dog
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_learned_plays import (
        SHOW_DOG,
        prepare_daily_lessons,
        prove_daily_lesson,
    )
    from girlframe.services.m3_show_dog import ShowDogService, prove

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="PRINCESS")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, SHOW_DOG),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, SHOW_DOG)
    learner, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="daily-appearance-witness",
            name="Actual local spectator",
            jobs=("civilian",),
            detail="A real existing person who can see this public appearance",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    npc = ActorRef(kind="npc", entity="daily-appearance-witness")
    assert depth(state(game), learner, npc) == 0
    assert not has_rule(state(game).sheets["2"], SHOW_DOG, "PRINCESS")
    with ledger.engine.connect() as c:
        assert (
            prepare_daily_lessons(game, c, state(game), learner, "go_off_duty")["show_dog"][0]["id"]
            == lesson.id
        )
    cycle, period = real_period(MissionService(ledger), game)
    game.dice.faces = (2, 2)
    calls = game.dice.calls
    action = _native_daily_roll(game, cycle, period, "learned_show_dog", lesson)
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, action)["receipt"]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    shows = ShowDogService(game)
    with ledger.engine.connect() as c:
        work = next(x for x in shows._tasks(c, PLAYER) if x["pending"])
        use = prove_daily_lesson(game, c, state(game), game.action(c, action), SHOW_DOG)
        assert use.lesson == lesson.id and use.mode == "off_duty"
    with pytest.raises(WorkflowError):
        shows.view(OTHER, work["id"])

    async def choose(viewer, operation, **values):
        opened = current(viewer.user_id, uuid4().int % 1000000000)
        await opened.response.defer(ephemeral=True)
        await open_show_dog(opened, shows, work["id"])
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = (operation,)
        response = current(viewer.user_id, uuid4().int % 1000000000)
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = current(viewer.user_id, uuid4().int % 1000000000)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        before = state(game)
        await form.confirm.callback(sent)
        assert state(game) == before

    asyncio.run(
        choose(
            PLAYER,
            "message",
            target=(teacher.token,),
            message="PRIVATE_LEARNED_SHOW_DOG The actual addressed message",
            account="I actually send this message during the public appearance",
        )
    )
    assert not shows.view(PLAYER, work["id"])["complete"]
    asyncio.run(
        choose(
            PLAYER,
            "second",
            npc=(npc.token,),
            desire=("emulate",),
            account="This actual original spectator saw my performed appearance",
        )
    )
    assert depth(state(game), learner, npc) == 1
    assert not shows.view(PLAYER, work["id"])["complete"]
    asyncio.run(
        choose(
            ADMIN,
            "risk",
            punish=("no",),
            account="The original Handler judges the actual performed risk; no Punishment arises",
        )
    )
    saved = shows.view(PLAYER, work["id"])
    assert saved["complete"] and not saved["punishment"]
    with ledger.engine.connect() as c:
        show = prove(game, c, state(game), work["id"])
        assert show.actor == learner and show.source_action == action
    from girlframe.engine import m3_show_dog as show_rules

    message = show_rules.records(state(game), show_rules.Message)[-1]
    assert shows.view_message(OTHER, message.id)["text"].startswith("PRIVATE_LEARNED_SHOW_DOG")
    with pytest.raises(WorkflowError):
        shows.view_message(ADMIN, message.id)
    assert game.inspect(PLAYER, action)["receipt"] == raw and game.dice.calls == calls + 1
    assert state(game).sheets["2"].girl == "VATGROWN"
    with ledger.engine.connect() as c:
        assert not prepare_daily_lessons(game, c, state(game), learner, "go_off_duty")["show_dog"]
    assert "PRIVATE_LEARNED_SHOW_DOG" not in json.dumps(gateway.messages)
    # This closes this exact borrowed rule; actual other period obligations
    # and the learner's ordinary recovery keep their existing controls.
    assert not cycle.review(PLAYER, period)["own"]["recovered"]
    tick(worker, gateway, 6)


def test_actual_stim_psyche_lessons_native_mark_removal_and_distinct_off_duty_tag_embrace(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m2_ui import open_play
    from girlframe.discord_adapter.m3_disposable_psyche import open_psyche
    from girlframe.engine import m3_disposable_psyche as psyche_rules
    from girlframe.engine import m3_malleable as malleable_rules
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_mockingbird import give_tag
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_disposable_psyche import (
        PsycheService,
        prove_conversion,
        prove_disposal,
    )
    from girlframe.services.m3_learned_plays import (
        PSYCHE,
        prepare_daily_lessons,
        prove_daily_lesson,
    )

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.EXPERIMENT,
            rules.INVESTMENT,
            rules.SEX,
            rules.BRUTALIZE,
            "girl.stim-blissed.dose-up",
            PSYCHE,
            malleable_rules.RULE,
        ),
    )
    marking = _learn_daily_source(game, worker, gateway, controls, PSYCHE)
    rebuilding = _learn_daily_source(game, worker, gateway, controls, PSYCHE)
    learner, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    before = state(game)
    identity = next(x for x in before.sheets["2"].identities if not x.marked and not x.protected)
    heat = before.sheets["2"].heat + 1 + 3
    calls = game.dice.calls

    async def mark():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_play(opened, game, _pilot=True)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(x.key == "learned_psyche" for x in form.fields)
        form.values.update(
            play=("keep_your_head",),
            learned_psyche=(marking.id,),
            identity=(identity.id,),
            gain=("1",),
            disposable_heat=("3",),
            pair_share=("0",),
            heat=(str(heat),),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="I actually mark and discard this original Identity while defending myself",
        )
        sent = current(2, uuid4().int % 1000000000)
        sent.channel_id = 900
        await form.confirm.callback(sent)
        assert form.completed, (
            sent.response.send_message.call_args_list,
            sent.edit_original_response.call_args_list,
        )
        with ledger.engine.connect() as c:
            return game.lock(c, 900)["action_id"]

    game.dice.faces = (1, 1)
    action = asyncio.run(mark())
    assert state(game).sheets["2"].identities == before.sheets["2"].identities
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual evasion result is enough")
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == calls + 1
    assert identity.id not in {x.id for x in actual.sheets["2"].identities}
    assert actual.sheets["2"].heat == 0 and len(actual.sheets["2"].identities) == 3
    assert actual.sheets["3"] == before.sheets["3"]
    raw = game.inspect(PLAYER, action)["receipt"]
    assert raw["disposable_psyche"] == action and raw["pre_total"] == 2 + heat
    with ledger.engine.connect() as c:
        disposal = prove_disposal(game, c, actual, action)
        assert disposal.identity == identity and disposal.extra == 3 and disposal.spent == heat
        assert prove_daily_lesson(game, c, actual, game.action(c, action), PSYCHE).mode == "mark"
        assert (
            prepare_daily_lessons(game, c, actual, learner, "go_off_duty")["psyche"][0]["id"]
            == rebuilding.id
        )
    assert not has_rule(actual.sheets["2"], PSYCHE, "STIM-BLISSED")
    tick(worker, gateway, 6)
    # Genuine ordinary Tag producer with the actual original human giver and
    # profile bindings; no fabricated inventory, disposable drug or choice.
    with ledger.transaction() as c:
        tag_event = str(uuid4())
        changed = give_tag(
            state(game),
            profiles(c, ledger.campaign_id),
            learner,
            teacher,
            "Actual learned Psyche rebuilding Tag",
            str(uuid4()),
            tag_event,
            (),
        )
        game.event(
            c,
            OTHER.user_id,
            str(uuid4()),
            "synthetic.actual_ordinary_tag_given",
            changed,
            event_id=tag_event,
        )
    tag = next(
        x for x in state(game).sheets["2"].tags if x.label == "Actual learned Psyche rebuilding Tag"
    )
    # The actual Stim giver's birth hook runs under this fixture's explicit
    # rule release. Ordinary Psyche/Vatgrown sources create no drug physiology.
    assert not any(
        x.id == tag.id for x in malleable_rules.records(state(game), malleable_rules.Birth)
    )
    cycle, period = real_period(MissionService(ledger), game)
    game.dice.faces = (2, 2)
    off_duty = _native_daily_roll(game, cycle, period, "learned_psyche", rebuilding)
    tick(worker, gateway, 3)
    pass_tags(game)
    psyche = PsycheService(ledger, game)
    work = next(x for x in psyche.menu(PLAYER)["tasks"] if x["pending"])
    data = psyche.view(PLAYER, work["id"])
    assert data["count"] == 3 and tag.id in {x["id"] for x in data["tags"]}
    with pytest.raises(WorkflowError):
        psyche.view(OTHER, work["id"])
    before_conversion = state(game)

    async def embrace():
        opened = current(2, uuid4().int % 1000000000)
        opened.channel_id = 901
        await opened.response.defer(ephemeral=True)
        await open_psyche(opened, psyche, work["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["tags"] = (tag.id,)
        sent = current(2, uuid4().int % 1000000000)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(embrace())
    actual = state(game)
    converted = psyche_rules.conversions(actual)[-1]
    assert converted.tags == (tag,) and not converted.replaced
    assert len(actual.sheets["2"].identities) == 4 and not actual.sheets["2"].tags
    assert actual.sheets["2"].identities[-1].name == tag.label
    assert actual.sheets["2"].heat == before_conversion.sheets["2"].heat
    assert actual.sheets["2"].assets == before_conversion.sheets["2"].assets
    with ledger.engine.connect() as c:
        assert prove_conversion(game, c, actual, work["id"]) == converted
        assert (
            prove_daily_lesson(game, c, actual, game.action(c, off_duty), PSYCHE).mode == "off_duty"
        )
        assert not prepare_daily_lessons(game, c, actual, learner, "go_off_duty")["psyche"]
    assert psyche.view(PLAYER, work["id"])["phase"] == "converted"
    assert game.inspect(PLAYER, action)["receipt"] == raw
    assert actual.sheets["2"].girl == "VATGROWN" and not has_rule(
        actual.sheets["2"], PSYCHE, "STIM-BLISSED"
    )
    assert not cycle.review(PLAYER, period)["own"]["recovered"]
    tick(worker, gateway, 6)


def test_actual_native_same_book_doll_lesson_history_does_not_stack_or_spend_on_native_use(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_vatgrown import open_choice, open_vatgrown
    from girlframe.engine import m3_vatgrown as doll_rules
    from girlframe.engine.creation_details import DesireChoice, NpcInvestor
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_learned_plays import DOLL, available
    from girlframe.services.m3_vatgrown import DollService

    # Both real public profiles are Vatgrown from their original birth. The
    # additional teacher independently receives the actual Handler proposal;
    # no activated Girl label, DNA source or investor is rewritten.
    original_selected, original_ready = game_fixture.selected, game_fixture.ready

    def selected_vatgrown(girl="MOCKINGBIRD", frame="JANUS-B"):
        draft = original_selected(girl, frame)
        if girl == "VATGROWN":
            draft = draft.model_copy(
                update={
                    "girl_details": GirlDetails(
                        investors=tuple(
                            NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                            for x in draft.npc_bonds
                        )
                    )
                }
            )
        return draft

    def ready_both_vatgrown(store, *args, **kwargs):
        result = original_ready(store, *args, **kwargs)
        coordinated = creation_fixture.CoordinationService(store)
        request = coordinated.propose(
            ADMIN,
            "doll-teacher-handler-desires",
            OTHER.user_id,
            "vatgrown_handler",
            coordinated.prepare(ADMIN, OTHER.user_id, "vatgrown_handler"),
            DesireChoice(slots=(1,)),
        )
        coordinated.decide(OTHER, "doll-teacher-accept-desires", request["id"], 1, "accept")
        return result

    monkeypatch.setattr(game_fixture, "selected", selected_vatgrown)
    monkeypatch.setattr(game_fixture, "ready", ready_both_vatgrown)
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="VATGROWN")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE, DOLL),
    )
    slot = state(game).sheets["3"].review.creation.npc_bonds[0].slot
    WorldService(MissionService(ledger)).import_starting_npc(
        OTHER,
        str(uuid4()),
        state(game).revision,
        slot,
        "original-investor",
    )
    learner, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    assert state(game).sheets["2"].girl == state(game).sheets["3"].girl == "VATGROWN"
    assert has_rule(state(game).sheets["2"], DOLL, "VATGROWN")
    lesson = _learn_daily_source(game, worker, gateway, controls, DOLL)
    with ledger.engine.connect() as c:
        assert prove_learned_play(game, c, state(game), lesson.id) == lesson
        assert available(game, c, state(game), learner, DOLL).id == lesson.id
    doll = DollService(game)

    def interaction(user=2):
        value = current(user, uuid4().int % 1000000000)
        value.channel_id = 900
        return value

    async def native_begin():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_vatgrown(opened, doll)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("play",)
        response = interaction()
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(teacher.token,),
            identity=(),
            gain=("0",),
            heat=("0",),
            account="I actually fade into the background beside this original person",
        )
        sent = interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        with ledger.engine.connect() as c:
            return game.lock(c, 900)["action_id"]

    calls = game.dice.calls
    action = asyncio.run(native_begin())
    game.dice.faces = (4, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    raw = game.inspect(PLAYER, action)["receipt"]

    async def native_answer(viewer, kind, **values):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = interaction(viewer.user_id)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, game.decision(viewer, row["id"]))
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = interaction(viewer.user_id)
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list

    asyncio.run(native_answer(PLAYER, "vat_doll_benefits", options=("quiet", "information")))
    asyncio.run(
        native_answer(
            OTHER,
            "vat_doll_information",
            text="PRIVATE_SAME_BOOK_DOLL The real observer offers this secret",
        )
    )
    saved = doll.view(PLAYER, action)
    assert saved["quiet"] and saved["information"]["answer"].startswith("PRIVATE_SAME_BOOK_DOLL")
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == calls + 1
    assert game.inspect(PLAYER, action)["receipt"] == raw
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        assert not any(
            key in actual["data"] for key in ("learned_play", "learned_show_dog", "learned_psyche")
        )
        source = doll_rules.source(state(game), action)
        assert source.actor == learner and len(source.benefits) == 2
        assert available(game, c, state(game), learner, DOLL).id == lesson.id
        runtime = next(
            x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lesson.id
        )
        assert runtime.claimed_action is None and runtime.rolled_event is None
        assert prove_learned_play(game, c, state(game), lesson.id) == lesson
    assert state(game).sheets["2"].girl == "VATGROWN"
    assert "PRIVATE_SAME_BOOK_DOLL" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)
