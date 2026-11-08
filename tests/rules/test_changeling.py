"""Changeling printed normals; deferred until final P1 except one released source smoke."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import ChoiceAnswer, IdentityState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_changeling import ChangelingService, prove_fingers, prove_node
from girlframe.services.m3_changeling_body import current_appearance
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="OLDGEN", frame=rules.FRAME)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.BLANK, rules.STRINGS, rules.FINGERS, *rules.REQUISITIONS),
    )
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(place(canon, 2, mode="piloting"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 20
        canon.sheets["2"].heat = 1
        canon.order = (3, 2)
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_changeling_bodies_and_initial_resources", canon
        )
    controls = ChangelingService(game)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    controls.body_fact(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        actor,
        "girl",
        "My actual original Girl body has this original brain in its proved vessel",
    )
    controls.body_fact(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        "girl",
        "My actual original Girl brain belongs to my actual outside-Frame body",
    )
    return game, GameWorker(game), Gateway(), controls


def define(game, controls):
    return controls.speak(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 3),
        current_ref(state(game), 2),
        "definition",
        "You are the quiet expert I trust with the next difficult job.",
    )["id"]


def roll(game, worker, gateway, *, play="changeling_blank_slate", source=None, faces=(3, 4)):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=play,
            context="I allow the actual source to adjust who I am",
            trigger_confirmed=True,
            heat=1,
            source_work=source,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    return identity


def respond(game, viewer, kind, answer):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    return game.respond(viewer, str(uuid4()), row["id"], row["revision"], answer)


def buy(game, controls, rule):
    return controls.purchase(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        rule,
        "I voluntarily spend my actual two Permission on this printed source",
    )


def test_actual_definition_mid_deepen_then_string_question_real_answer_and_owned_counter(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    before = depth(state(game), actor, target)
    action = roll(game, worker, gateway, source=define(game, controls))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert depth(state(game), actor, target) == min(2, before + 1)
    nodes = [x for x in rules.records(state(game), rules.String) if x.origin == "deepen"]
    assert len(nodes) == 1 and nodes[0].subject.actor == target
    tick(worker, gateway, 5)
    wrong_revision = state(game).revision - 1
    unchanged = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.fingers(
            PLAYER,
            str(uuid4()),
            wrong_revision,
            900,
            nodes[0].id,
            "question",
            "Actual attempt",
            question="What are you worried about?",
        )
    assert state(game).model_dump_json() == unchanged
    payload = (
        PLAYER,
        "one-actual-psychic-question",
        state(game).revision,
        900,
        nodes[0].id,
        "question",
        "I consume my actual String to ask the original person a question",
    )
    result = controls.fingers(*payload, question="What are you worried about?")
    assert controls.fingers(*payload, question="What are you worried about?") == result
    use = rules.get(state(game), result["id"])
    assert use.question and use.completed_event is None
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, use.id)
    controls.answer(
        OTHER,
        str(uuid4()),
        state(game).revision,
        use.question,
        "I am worried we will leave someone behind.\n  I need a real plan.",
    )
    controls.counter(OTHER, str(uuid4()), state(game).revision, use.id, "tag", text="Careful")
    canon = state(game)
    assert rules.get(canon, use.id).completed_event
    assert next(x for x in canon.sheets["2"].tags if x.label == "Careful").giver_actor == target
    assert rules.record(canon, rules.String, nodes[0].id).spent_by == use.id
    question = rules.record(canon, rules.Question, use.question)
    assert question.answer.endswith("\n  I need a real plan.")
    assert controls.view(OTHER, use.question)["body"]["answer"] == question.answer
    with ledger.engine.connect() as c:
        assert prove_node(game, c, canon, nodes[0].id).spent_event
        assert prove_fingers(game, c, canon, use.id).counter == "tag"
    with pytest.raises(WorkflowError):
        controls.fingers(
            PLAYER,
            str(uuid4()),
            canon.revision,
            900,
            nodes[0].id,
            "question",
            "No second use",
            question="A second question?",
        )
    assert game.dice.calls == 1


def test_high_exact_held_batch_preserves_protection_then_copies_actual_disclosed_identity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].identities.append(
            IdentityState(id="actual-protected-extra", name="Protected source", protected=True)
        )
        game.event(c, 1, str(uuid4()), "synthetic.existing_actual_protected_identity", canon)
    held = tuple(x.id for x in state(game).sheets["2"].identities)
    action = roll(game, worker, gateway, source=define(game, controls), faces=(6, 6))
    source = rules.session(state(game), action)
    assert source.identities == held
    assert not any(x["kind"] == "changeling_all_erase" for x in game.choices(PLAYER))
    grant = rules.record(state(game), rules.BlankSlate, source.blank)
    blank = next(x for x in state(game).sheets["2"].identities if x.id == grant.identity)
    assert {x.id for x in state(game).sheets["2"].identities} == {
        "actual-protected-extra",
        grant.identity,
    }
    tick(worker, gateway, 5)
    actor, other = current_ref(state(game), 2), current_ref(state(game), 3)
    first = controls.speak(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        actor,
        other,
        "conversation",
        "Tell me what matters to you in this moment.",
    )["id"]
    second = controls.speak(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        other,
        actor,
        "conversation",
        "I am showing you something true about who I am.",
    )["id"]
    possessed = state(game).sheets["3"].identities[0]
    disclosure = controls.disclose_identity(
        OTHER, str(uuid4()), state(game).revision, second, possessed.id
    )["id"]
    controls.copy_blank(
        PLAYER, str(uuid4()), state(game).revision, grant.id, other, disclosure, (first, second)
    )
    copied = next(x for x in state(game).sheets["2"].identities if x.id == blank.id)
    assert copied.name == possessed.name and copied.marked == blank.marked
    assert (copied.protected, copied.paired, copied.am_limiter, copied.slot) == (
        blank.protected,
        blank.paired,
        blank.am_limiter,
        blank.slot,
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_actual_one_erasure_then_original_handler_recent_window(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    statement = define(game, controls)
    speech = rules.record(state(game), rules.Speech, statement)
    action = roll(game, worker, gateway, source=statement, faces=(1, 1))
    original = tuple(x.id for x in state(game).sheets["2"].identities)
    chosen = original[0]
    respond(
        game,
        PLAYER,
        "changeling_low_erase",
        ChoiceAnswer(denied=(chosen,), text="I lose this real Identity"),
    )
    assert {x.id for x in state(game).sheets["2"].identities} == set(original) - {chosen}
    respond(
        game,
        ADMIN,
        "changeling_recent",
        ChoiceAnswer(
            fields={"start_event": speech.event},
            text="The statement began the actual last few fictional minutes; "
            "preserve OOC history and owed work",
        ),
    )
    source = rules.session(state(game), action)
    assert source.recent_event and source.erased_event and source.blank is None
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert controls.view(OTHER, speech.id)["body"]["text"] == speech.text


def test_mid_clay_two_actual_facets_then_true_handler_taste_status(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(game, controls, rules.CLAY)
    actor = current_ref(state(game), 2)
    legal = state(game).sheets["2"].girl
    action = roll(game, worker, gateway, play="changeling_body_of_clay")
    respond(
        game,
        PLAYER,
        "changeling_clay_owner",
        ChoiceAnswer(
            options=("features", "voice"),
            fields={
                "features": "Actual silver hair and a narrow face",
                "voice": "A warm low speaking voice",
            },
            text="My actual two changes",
        ),
    )
    respond(
        game,
        ADMIN,
        "changeling_taste",
        ChoiceAnswer(flag=True, text="Those actual changes suit my tastes"),
    )
    brain = rules.session(state(game), action).brain
    appearance = current_appearance(state(game), actor, brain.vessel)
    assert appearance["voice"] == "A warm low speaking voice" and "silver" in appearance["features"]
    assert state(game).order == (2, 3) and state(game).sheets["2"].girl == legal
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_high_clay_three_then_independent_handler_patch_and_real_tag(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(game, controls, rules.CLAY)
    action = roll(game, worker, gateway, play="changeling_body_of_clay", faces=(6, 6))
    respond(
        game,
        PLAYER,
        "changeling_clay_owner",
        ChoiceAnswer(
            options=("features", "age", "voice"),
            fields={
                "features": "Short dark hair",
                "age": "An adult apparent age",
                "voice": "My chosen high voice",
            },
            text="My three actual changes",
        ),
    )
    respond(
        game,
        ADMIN,
        "changeling_clay_handler",
        ChoiceAnswer(
            options=("voice",),
            fields={"voice": "The Handler's later separately authored voice change"},
            text="My actual one facet",
        ),
    )
    respond(game, ADMIN, "changeling_taste", ChoiceAnswer(flag=False, text="Unsettling"))
    source = rules.session(state(game), action)
    assert current_appearance(state(game), source.actor, source.brain.vessel)["voice"].startswith(
        "The Handler's later"
    )
    assert source.owner_change_event and source.handler_change_event and source.taste_event
    assert any(
        x.label == "Unsettling" and x.giver_actor == source.handler
        for x in state(game).sheets["2"].tags
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_low_clay_actual_handler_subset_then_taste_without_owner_proxy(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(game, controls, rules.CLAY)
    action = roll(game, worker, gateway, play="changeling_body_of_clay", faces=(1, 1))
    assert not any(x["kind"] == "changeling_clay_owner" for x in game.choices(PLAYER))
    respond(
        game,
        ADMIN,
        "changeling_clay_handler",
        ChoiceAnswer(
            options=("body",),
            fields={"body": "The original Handler's actual change to a broad-shouldered build"},
            text="The one facet I actually change",
        ),
    )
    respond(
        game, ADMIN, "changeling_taste", ChoiceAnswer(flag=True, text="These changes fit my tastes")
    )
    source = rules.session(state(game), action)
    assert source.owner_change_event is None and source.handler_change_event
    assert current_appearance(state(game), source.actor, source.brain.vessel)["body"].endswith(
        "build"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
