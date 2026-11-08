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
from girlframe.engine.creation_details import DESIRES
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


def ready(store, tmp_path, monkeypatch):
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
                callsign="ACTUAL_ALPHA",
                girl_playbook="ALPHA",
                frame_playbook="JANUS-B",
                notes=notes,
            ),
        )

    def selected_actual(girl="MOCKINGBIRD", frame="JANUS-B"):
        return original_selected("ALPHA" if girl == "MOCKINGBIRD" else girl, frame)

    monkeypatch.setattr(creation_fixture, "seed", seed_actual)
    monkeypatch.setattr(game_fixture, "selected", selected_actual)
    _, game = service(store, girl="VATGROWN", frame="THE ENFORCER")
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.EXPERIMENT, rules.INVESTMENT, rules.SEX, rules.BRUTALIZE),
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


def sex(game, worker, gateway, controls, faces):
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
        "My actual original Alpha confirms only this source",
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
