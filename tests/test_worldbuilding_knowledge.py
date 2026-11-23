"""Only native-backed, explicitly scoped world disclosures become actor knowledge."""

import pytest
from rules.m3_policy_scenario import configure_m3_fixture
from rules.test_world import initial
from test_director_continuity import carry, new_scene, roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_knowledge_contract_revision import commit
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
from girlframe.ai.worldbuilding import DevelopmentAction, WorldbuildingProposal
from girlframe.engine.m3_world_development import DevelopmentDraft, Subject
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

VISIBLE = "A brass key hangs beside the relay panel."
HIDDEN = "PRIVATE_WORLD_PLAN_TO_TAKE_KEY"


def established(routed):
    observer, context, scene, game, _ = routed
    configure_m3_fixture(observer.store)
    approval = observer.store.policy.m3_approval
    observer.store.policy = observer.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(observer.store))
    starting = initial()
    world.initialize(
        ADMIN,
        "world-init",
        state(game).revision,
        starting.board,
        starting.locations,
        starting.gorgons[0],
    )
    _, source = send(
        observer, scene, "world-source", text="GM, establish the relay's surroundings."
    )
    service = DirectorWorldbuildingService(context)
    request = service.open(ADMIN, "world-open", scene, source.source_id)
    saved = service.propose(
        ADMIN,
        "world-propose",
        scene,
        request["id"],
        WorldbuildingProposal(
            request_id=request["id"],
            action=DevelopmentAction(
                development=DevelopmentDraft(
                    key="relay-key",
                    kind="detail",
                    subject=Subject(kind="location", id="base0"),
                    title="Relay key",
                    text=VISIBLE + " " + HIDDEN,
                )
            ),
            cited_evidence=("source", "native"),
            private_reasoning="Private fixture world review.",
        ),
    )
    service.review(ADMIN, "world-review", scene, saved["id"], "approve", "Bounded location detail.")
    committed = service.confirm(ADMIN, "world-confirm", scene, saved["id"])
    return service, committed


def test_committed_world_stays_hidden_until_selected_exact_disclosure_and_survives_handoff(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    service, committed = established(routed)
    assert VISIBLE not in context.build(ADMIN, scene, actor=handler).model_dump_json()
    assert VISIBLE not in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    assert HIDDEN in state(game).model_dump_json()
    knowledge = DirectorKnowledgeService(context)
    with pytest.raises(WorkflowError):
        knowledge.open(ADMIN, "cannot-disclose-commit", scene, committed["id"])
    before = state(game).model_dump_json()
    args = (ADMIN, "disclose-key", scene, committed["id"], VISIBLE, (handler,))
    disclosed = service.disclose(*args, topic="briefing")
    assert service.disclose(*args, topic="briefing") == disclosed
    ref = next(
        x
        for x in context.build(ADMIN, scene, actor=handler).references
        if x.id in disclosed["reference_ids"]
    )
    assert ref.classification == "established_world" and ref.reported_by is None
    assert ref.text == "Established world: " + VISIBLE
    assert HIDDEN not in ref.model_dump_json() and committed["id"] not in ref.model_dump_json()
    assert ref.id not in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    assert state(game).model_dump_json() == before
    observer.store.engine.dispose()
    context = DirectorContextService(observer)
    second = new_scene(observer)
    copied = carry(context, scene, second, (ref.id,))
    recalled = next(
        x
        for x in context.build(ADMIN, second, actor=handler).references
        if x.id == copied["references"][ref.id]
    )
    assert recalled.classification == "established_world" and recalled.text == ref.text
    assert VISIBLE not in context.build(PLAYER, second, actor=pilot).model_dump_json()
    observer.set_consent(PLAYER, "withdraw-world-origin", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="CONTINUITY|CONSENT|OBSERVATION"):
        context.build(ADMIN, second, actor=handler)


def test_world_acquisition_cannot_widen_recipients_change_quote_or_launder_player_prose(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    service, committed = established(routed)
    disclosed = service.disclose(ADMIN, "disclose-key", scene, committed["id"], VISIBLE, (handler,))
    knowledge = DirectorKnowledgeService(context)
    request = knowledge.open(ADMIN, "world-knowledge-open", scene, disclosed["id"])
    packet = knowledge.packet(ADMIN, scene, request["id"])
    assert packet.source.kind == "approved_world" and packet.source.text == VISIBLE
    assert packet.recipients == (handler,) and HIDDEN not in packet.source.model_dump_json()
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    with pytest.raises(WorkflowError, match="INVALID_RECIPIENT"):
        context.record(
            ADMIN, "widen-direct-world", scene, disclosed["id"], order, known_by=(pilot,)
        )
    with pytest.raises(WorkflowError, match="INVALID_RECIPIENT"):
        knowledge.propose(
            ADMIN,
            "widen-world",
            scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                updates=(Acquisition(basis="world", quote=VISIBLE, recipients=(pilot,)),),
            ),
        )
    with pytest.raises(WorkflowError, match="UNPROVEN_WORLD"):
        knowledge.propose(
            ADMIN,
            "trim-world",
            scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                updates=(Acquisition(basis="world", quote="A brass key", recipients=(handler,)),),
            ),
        )
    accepted = commit(
        knowledge,
        scene,
        disclosed["id"],
        "learn-world",
        (Acquisition(basis="world", quote=VISIBLE, recipients=(handler,)),),
    )
    ref = next(x for x in context.build(ADMIN, scene).references if x.id in accepted["references"])
    assert ref.classification == "established_world" and ref.reported_by is None
    _, relay = send(
        observer, scene, "handler-relay", viewer=ADMIN, text=VISIBLE, fictional_channel="comms"
    )
    relayed = commit(
        knowledge,
        scene,
        relay.source_id,
        "relay-world",
        (Acquisition(basis="report", quote=VISIBLE, recipients=(pilot,), prior_reference=ref.id),),
    )
    heard = next(
        x
        for x in context.build(PLAYER, scene, actor=pilot).references
        if x.id in relayed["references"]
    )
    assert heard.classification == "reported_claim" and heard.reported_by == handler
    assert heard.text == "Reported claim: " + VISIBLE and not heard.dependencies
    _, message = send(
        observer,
        scene,
        "unapproved-world",
        text="There is an unrestricted armoury.",
        fictional_channel="comms",
    )
    raw = knowledge.open(ADMIN, "unapproved-open", scene, message.source_id)
    with pytest.raises(WorkflowError, match="UNPROVEN_WORLD"):
        knowledge.propose(
            ADMIN,
            "unapproved-propose",
            scene,
            raw["id"],
            KnowledgeProposal(
                request_id=raw["id"],
                updates=(
                    Acquisition(
                        basis="world",
                        quote="There is an unrestricted armoury.",
                        recipients=(handler,),
                    ),
                ),
            ),
        )
