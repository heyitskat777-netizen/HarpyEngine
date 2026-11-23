"""Addressed NPCs and peer replies take their turn on the existing Activity floor."""

from uuid import uuid4

import pytest
from test_activity_npc_api import call
from test_activity_shadow_readiness import consent, opt, publish_opening, review, submission
from test_ai_npc_reactions import NPC, FakeGateway, enable, working_scene
from test_cast_service import change
from test_director_activity_scene import P2Scene
from test_director_observation import Clock
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_m5_activity_pilots import LocalModel
from test_session_zero import FACILITATOR

from girlframe.activity.npc import ActivityNpcApi
from girlframe.ai.director_dossiers import DossierProfile, DossierState, Personnel
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.ai_npc_reactions import NpcReactionService
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.onboarding import WorkflowError


def test_address_owns_exact_turn_and_keeps_other_dialogue_eligible(ledger):
    _, game, _, cast, scene = working_scene(ledger)
    state_before = state(game)
    handler = ActorRef(kind="handler", entity=str(ADMIN.user_id))
    if not any(role.actor == handler for entry in state_before.scene_casts for role in entry.roles):
        change(cast, ADMIN, "join", handler)
    enable(ledger)
    clock = ledger.clock = Clock()
    gateway = FakeGateway()
    npc = ActivityNpcApi(NpcReactionService(ledger, gateway))
    observer = DirectorObservationService(ledger, synthetic=True, activity_shadow=True)
    observer.game = game
    model = LocalModel()
    app = P2Scene.model_fixture(DirectorContextService(observer), model.client, batch=model.client)
    opt(app, scene)
    app.write(ADMIN, "configure", scene, "configure", {"revision": 0})
    for person in (ADMIN, PLAYER, OTHER):
        consent(app, scene, person)
    publish_opening(app, scene, FACILITATOR)
    dossiers = app.session.dossiers
    portrayal = dossiers.propose(
        ADMIN,
        "clerk-portrait",
        scene,
        ActorRef(kind="npc", entity=NPC),
        0,
        DossierProfile(background="PRIVATE_CLERK_BIO"),
        DossierState(),
        personnel=Personnel(mannerisms="Ask for the entry number before promising anything."),
    )
    dossiers.confirm(ADMIN, "confirm-clerk-portrait", scene, portrayal["id"])
    original = state(game)

    def address(turn, text, *, viewer=PLAYER, submission_id=None):
        target = call(npc, viewer, scene, "overview")["targets"]
        return call(
            npc,
            viewer,
            scene,
            "address",
            submission_id=submission_id or str(uuid4()),
            window=target["window"],
            npc_id=NPC,
            statement=text,
            source_turn={"source_id": turn["source_id"], "revision": turn["source_revision"]},
        )

    _, first = submission(app, scene, PLAYER, "find-crate", "Clerk, did the crate come in?")
    with pytest.raises(WorkflowError, match="NPC_TURN_UNAVAILABLE"):
        address(first, "Clerk, did the crate come in?", viewer=OTHER)
    key = str(uuid4())
    owed = address(first, "Clerk, did the crate come in?", submission_id=key)
    assert address(first, "Clerk, did the crate come in?", submission_id=key) == owed
    with pytest.raises(WorkflowError, match="NPC_HAS_FLOOR"):
        address(first, "Clerk, did the crate come in?")
    clock.now += 120
    assert review(app, scene)["model_outcome"]["status"] == "wait" and model.calls == []
    draft = call(npc, ADMIN, scene, "draft", submission_id=str(uuid4()), address_id=owed["id"])
    packet = gateway.calls[-1][1].model_dump()
    assert packet["public_manner"] == "Ask for the entry number before promising anything."
    assert "PRIVATE_CLERK_BIO" not in str(packet)
    preview = call(npc, FACILITATOR, scene, "overview")["requests"][0]["review_audience"]
    call(
        npc,
        FACILITATOR,
        scene,
        "review",
        submission_id=str(uuid4()),
        request_id=draft["id"],
        result_id=draft["result_id"],
        approve=True,
        expected_audience=preview["receipt"],
    )
    [delivered] = call(npc, PLAYER, scene, "overview")["feed"]
    assert delivered["speech"] == gateway.speech

    # The NPC lock is source-scoped. A later normal question gets reviewed.
    model.answer = lambda packet: {
        "kind": "NPC_DIALOGUE",
        "reason": "response_need",
        "text": "Tell me what you can see at the corner.",
        "source_refs": [],
        "report_ids": [packet["reports"][-1]["source_id"]],
        "intended_recipients": [packet["reports"][-1]["speaker"]],
    }
    text = "Handler, can you see the corner?"
    _, second = submission(app, scene, PLAYER, "another-turn", text)
    clock.now += 120
    shadow = review(app, scene)["model_outcome"]
    assert shadow["status"] == "draft" and len(model.calls) == 1
    second_address = address(second, text)
    assert app.read(ADMIN, scene, "handler-draft", shadow["draft_id"])["status"] == (
        "stale_reopen_source"
    )
    assert not any(row["kind"] == "handler" for row in app.timeline(PLAYER, scene)["entries"])
    pending = call(
        npc, ADMIN, scene, "draft", submission_id=str(uuid4()), address_id=second_address["id"]
    )
    _, third = submission(app, scene, PLAYER, "resolved-turn", text)
    clock.now += 120
    completed = review(app, scene)["model_outcome"]["draft_id"]
    listener = model.calls[-1]["reports"][-1]["speaker"]
    app.write(
        ADMIN,
        "approve-ordinary-answer",
        scene,
        "handler-approve",
        {"draft": completed, "reason": "Current audible reply.", "recipients": [listener]},
    )
    app.write(ADMIN, "deliver-ordinary-answer", scene, "handler-deliver", {"draft": completed})
    with pytest.raises(WorkflowError, match="NPC_TURN_ANSWERED"):
        address(third, text)

    consent(app, scene, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="STALE_REACTION"):
        call(
            npc,
            FACILITATOR,
            scene,
            "review",
            submission_id=str(uuid4()),
            request_id=pending["id"],
            result_id=pending["result_id"],
            approve=True,
        )
    assert len(call(npc, PLAYER, scene, "overview")["feed"]) == 1
    assert state(game) == original
