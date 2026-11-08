"""One actual same-NPC control handover; broader lineage stays deferred to P1."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_body_facts import ready, record
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter import m3_changeling as native
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.onboarding import WorkflowError


def test_real_npc_claim_hands_pending_question_to_current_role_without_rewriting_history(
    ledger, tmp_path, monkeypatch
):
    game, bodies, world, casts = ready(ledger, tmp_path, monkeypatch)
    owner = current_ref(state(game), 2)
    starting = state(game).sheets["2"].review.creation.npc_bonds[0]
    npc = Npc(
        id="original-question-subject",
        name=starting.name or "Original starting person",
        jobs=("civilian",),
        controller=1,
        cell=(0, 0),
        revealed=True,
        detail="Actual original starting counterpart",
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, npc)
    world.claim_npc(OTHER, str(uuid4()), state(game).revision, npc.id)
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, starting.slot, npc.id)
    target = ActorRef(kind="npc", entity=npc.id)
    shown = casts.view(OTHER, 900)
    casts.change(
        OTHER, str(uuid4()), 900, shown["game_revision"], shown["cast_revision"], "join", target
    )
    bodies.record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        "human_npc",
        "Witnessed original human brain in this actual NPC body",
    )
    record(game, bodies, PLAYER)
    bodies.establish_npc_original(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        owner,
        starting.slot,
        "This is the genuine original person from the saved starting relationship",
    )
    offered = bodies.menu(PLAYER, 900)["imports"][0]
    bodies.import_starting(
        PLAYER, str(uuid4()), state(game).revision, owner, offered["source_event"]
    )
    node = next(x for x in rules.records(state(game), rules.String) if x.subject.actor == target)
    controls = ChangelingService(game)
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        node.id,
        "question",
        "Consume the actual original String",
        question="What do you need from us?",
    )
    use = rules.get(state(game), used["id"])
    assert use.question and not rules.reciprocal(use.subject)
    original = rules.record(state(game), rules.Question, use.question)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, original.id)  # Handler privilege does not disclose it.
    world.claim_npc(ADMIN, str(uuid4()), state(game).revision, npc.id)
    with pytest.raises(WorkflowError):
        controls.answer(OTHER, str(uuid4()), state(game).revision, original.id, "Old controller")
    with pytest.raises(WorkflowError, match="Join"):
        controls.answer(ADMIN, str(uuid4()), state(game).revision, original.id, "Before joining")
    prior_cast = casts.view(OTHER, 900)
    casts.change(
        OTHER,
        str(uuid4()),
        900,
        prior_cast["game_revision"],
        prior_cast["cast_revision"],
        "withdraw",
        target,
    )
    shown = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, shown["game_revision"], shown["cast_revision"], "join", target
    )
    with ledger.engine.connect() as c:
        assert any(x["id"] == original.id and x["pending"] for x in controls._tasks(c, ADMIN))
        assert not any(x["id"] == original.id for x in controls._tasks(c, OTHER))
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: ADMIN)

    async def answer_native():
        opened = current(1, 813001)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await native.open_changeling(opened, controls, original.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["answer"] = "A genuine plan.\n  PRIVATE_CURRENT_NPC_ANSWER"
        submitted = current(1, 813002)
        await form.confirm.callback(submitted)
        assert form.completed
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(answer_native())
    answered = rules.record(state(game), rules.Question, original.id)
    assert answered.model_copy(update={"answer": None, "answer_event": None}) == original
    assert answered.answerer.controller == OTHER.user_id
    assert rules.get(state(game), use.id).completed_event
    assert controls.view(ADMIN, original.id)["body"]["answer"] == answered.answer
    assert controls.view(PLAYER, original.id)["body"]["answer"] == answered.answer
    with pytest.raises(WorkflowError):
        controls.view(OTHER, original.id)
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == answered.answer_event))
            == "1"
        )
    assert rules.record(state(game), rules.String, node.id).spent_by == use.id


def test_actual_am_fourth_limiter_reset_preserves_original_strings_question_and_counter(
    ledger, tmp_path, monkeypatch
):
    """Deferred P1: real AM creation and genuine CHANGELING, never a relabeled sheet."""
    from m3_policy_scenario import configure_m3_fixture
    from test_creation import selected
    from test_creation_review import ready as creation_ready
    from test_enforcement_initiative import cast_target
    from test_enforcer_requisitions import approved
    from test_m2_game import Dice, Gateway, answer, pass_tags, tick
    from test_world import initial

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine import m3_am as am
    from girlframe.engine import m3_am_reset as reset
    from girlframe.engine.m2 import PlayInput, ReleaseApproval
    from girlframe.engine.m2_registry import registry_digest
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.creation_review import CreationReviewService
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_am_reset import FactoryResetService
    from girlframe.services.m3_am_scrutinized import ScrutinyService
    from girlframe.services.m3_body_facts import BodyFactsService
    from girlframe.services.m3_changeling import prove_fingers, prove_node
    from girlframe.services.m3_changeling_lineage import current_subject
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_physical import PhysicalService
    from girlframe.services.m3_world import WorldService

    review, creation, _ = creation_ready(
        ledger, girl="AM", frame="THE ENFORCER", other_frame=rules.FRAME
    )
    current_draft = creation.get(OTHER)
    draft = selected("MOCKINGBIRD", rules.FRAME).model_copy(
        update={"shared_tokens": current_draft.draft.shared_tokens}
    )
    creation.save(OTHER, "actual-other-changeling-build", 0, 1, draft)
    other_review = CreationReviewService(ledger)
    incoming = next(x for x in other_review.get(OTHER).sheet.bonds if not x.outgoing)
    current_draft = creation.get(OTHER)
    other_review.select_bond(
        OTHER,
        "actual-other-starting-bond",
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
    game = GameService(ledger, dice=Dice((1, 1)))
    for viewer in (PLAYER, OTHER):
        saved = review.get(viewer)
        review.save(
            viewer,
            "actual-reviewed-" + str(viewer.user_id),
            saved.saved_revision,
            saved.fingerprint,
        )
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review
        game.activate(viewer, "actual-active-" + str(viewer.user_id), saved.fingerprint)
    game.bind_scene(ADMIN, "actual-reset-scene", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, "actual-join-" + str(viewer.user_id), 900)
    configure_m3_fixture(ledger)
    acquisition = approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(am.RULE, rules.STRINGS, rules.BLANK, rules.FINGERS),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    missions = MissionService(ledger, acquisition.registry)
    world, physical = WorldService(missions), PhysicalService(ledger)
    original_world = initial()
    world.initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        original_world.board,
        original_world.locations,
        original_world.gorgons[0],
    )
    for viewer in (PLAYER, OTHER):
        preview = physical.preview(viewer)
        placed = physical.propose(
            viewer,
            str(uuid4()),
            preview["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(preview["actor"]),
                frame_instance=preview["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                facts_confirmed=True,
                account="The original actual native body and its first placement",
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            placed["id"],
            1,
            "accept",
            "I witness the original bodies and actual hardware",
        )
    caster, original = current_ref(state(game), 3), current_ref(state(game), 2)
    assert state(game).sheets["3"].frame == rules.FRAME
    assert state(game).sheets["2"].girl == "AM"
    bodies, controls = BodyFactsService(game), ChangelingService(game)
    for viewer in (PLAYER, OTHER):
        bodies.record(
            viewer,
            str(uuid4()),
            state(game).revision,
            900,
            current_ref(state(game), viewer.user_id),
            "girl",
            "My actual original brain in its proved original hardware",
        )
    offered = bodies.menu(OTHER, 900)["imports"][0]
    bodies.import_starting(
        OTHER, str(uuid4()), state(game).revision, caster, offered["source_event"]
    )
    # Earn a second real String through a genuine mid Blank Slate Bond-deepening.
    speech = controls.speak(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        original,
        caster,
        "definition",
        "You are the expert I trust with my original mind",
    )["id"]
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["3"].heat = 3
        game.event(c, 1, str(uuid4()), "synthetic.initial_changeling_heat", actual)
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (3, 4)
    blank = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="changeling_blank_slate",
            source_work=speech,
            heat=1,
            context="I accept the actual defining statement",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(OTHER, blank)["state"] == "complete"
    tick(worker, gateway, 5)
    nodes = [
        x
        for x in rules.records(state(game), rules.String)
        if x.actor == caster and x.subject.actor == original and not x.spent_event
    ]
    assert len(nodes) == 2
    scrutiny = ScrutinyService(game)
    game.dice.faces = (1, 1)
    discovery = None
    for index, (freedom, _) in enumerate(am.FREEDOMS):
        npc = ActorRef(kind="npc", entity="true-reset-discoverer-" + str(index))
        world.npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=npc.entity,
                name="Actual discoverer " + str(index),
                jobs=("guard",),
                controller=1,
                cell=(0, 0),
                revealed=True,
                detail="A genuinely different original person newly notices the adjustment",
            ),
        )
        cast_target(game, npc)
        discovery = scrutiny.propose(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            state(game).revision,
            "This actual distinct NPC newly recognizes my adjusted code",
        )["id"]
        root = scrutiny.confirm(
            ADMIN,
            str(uuid4()),
            discovery,
            state(game).revision,
            True,
            True,
            True,
            "My own actual NPC confirms the new realization",
        )["action_id"]
        tick(worker, gateway, 3)
        remaining = am.identities(state(game), original)
        extra = dict(gain=1, identity=remaining[0].id, heat=1) if index == 1 else dict(heat=0)
        child = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=am.PLAY,
                parent=root,
                source_work=discovery,
                target_actor=npc,
                context="My genuine response to this original new discovery",
                trigger_confirmed=True,
                **extra,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(
            game,
            ADMIN,
            "am_limiter",
            options=(am.identities(state(game), original)[0].id,),
            fields={"freedom": freedom},
            text="The actual discoverer installs this Limiter",
        )
        if index < 3:
            assert game.inspect(PLAYER, child)["state"] == "complete"
            tick(worker, gateway, 5)
    assert len(am.limiters(state(game), original)) == 4
    # A real already-owed question is created after the final roll, before genuine reset.
    owed = controls.fingers(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[0].id,
        "question",
        "I consume the original brain-bound String before the pending reset",
        question="What promise do you want us to keep?",
    )["id"]
    old_use = rules.get(state(game), owed)
    old_question = rules.record(state(game), rules.Question, old_use.question)
    assert rules.reciprocal(old_use.subject)
    assert discovery is not None
    reset_service = FactoryResetService(game)
    reset_service.complete(
        ADMIN,
        str(uuid4()),
        discovery,
        state(game).revision,
        "ex_pilot",
        "The fourth-Limited original becomes this actual NPC",
    )
    tick(worker, gateway, 5)
    actual_reset = reset.records(state(game))[0]
    assert actual_reset.original == original and "2" not in state(game).sheets
    if not any(
        role.actor == actual_reset.actor
        for scene in state(game).scene_casts
        if scene.channel == 900 and scene.open
        for role in scene.roles
    ):
        cast_target(game, actual_reset.actor)
    bodies.record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        actual_reset.actor,
        "other",
        "This is the canonical reset's same original brain and physical hardware",
    )
    with ledger.engine.connect() as c:
        current_brain = current_subject(game, c, state(game), old_use.subject)
        assert current_brain.actor == actual_reset.actor and current_brain.controller == 1
        assert (
            current_brain.id == old_use.subject.id
            and current_brain.vessel == old_use.subject.vessel
        )
        assert not rules.same_brain(current_brain, old_use.subject)
        assert prove_fingers(game, c, state(game), owed).subject == old_use.subject
        assert any(x["id"] == old_question.id and x["pending"] for x in controls._tasks(c, ADMIN))
    with pytest.raises(WorkflowError):
        controls.answer(PLAYER, str(uuid4()), state(game).revision, old_question.id, "Old account")
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: ADMIN)

    async def answer_current_native():
        opened = current(1, 814001)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await native.open_changeling(opened, controls, old_question.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "Current actual subject: npc:" in form.text()
        form.values["answer"] = "Keep my actual promise.\n  PRIVATE_SAME_BRAIN_AFTER_RESET"
        response = current(1, 814002)
        await form.confirm.callback(response)
        assert form.completed
        saved = state(game)
        await form.confirm.callback(response)
        assert state(game) == saved

    asyncio.run(answer_current_native())
    controls.counter(ADMIN, str(uuid4()), state(game).revision, owed, "tag", text="Trustworthy")
    assert rules.get(state(game), owed).completed_event
    actual_tag = next(x for x in state(game).sheets["3"].tags if x.label == "Trustworthy")
    assert actual_tag.giver_actor == actual_reset.actor
    preserved = rules.record(state(game), rules.Question, old_question.id)
    assert preserved.answerer == old_question.answerer and preserved.asker == old_question.asker
    assert preserved.answer_event and "PRIVATE_SAME_BRAIN" in preserved.answer
    fresh = controls.fingers(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[1].id,
        "question",
        "Use the other original unspent String against the actual same reset brain",
        question="What do you need now?",
    )["id"]
    fresh_use = rules.get(state(game), fresh)
    assert fresh_use.target == actual_reset.actor and fresh_use.subject.kind == "other"
    assert not rules.reciprocal(fresh_use.subject) and fresh_use.counter_closed_event
    with ledger.engine.connect() as c:
        prove_fingers(game, c, state(game), fresh)
        assert prove_node(game, c, state(game), nodes[1].id).spent_by == fresh
    controls.answer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        fresh_use.question,
        "A real plan for the same original mind",
    )
    assert rules.get(state(game), fresh).completed_event
    assert len([x for x in rules.records(state(game), rules.String) if x.actor == caster]) == 2
