"""New testimony and source-bound speech classification preserve private knowledge."""

import json

import jsonschema
import pytest
from test_director_continuity import carry, new_scene, roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.knowledge import Acquisition, Disclosure, KnowledgeProposal
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.onboarding import WorkflowError


def commit(service, scene, source, key, updates=(), disclosures=()):
    request = service.open(ADMIN, key + ":open", scene, source)
    proposal = KnowledgeProposal(request_id=request["id"], updates=updates, disclosures=disclosures)
    saved = service.propose(ADMIN, key + ":propose", scene, request["id"], proposal)
    return service.confirm(ADMIN, key + ":confirm", scene, saved["id"])


def test_first_testimony_and_native_actor_directory_do_not_promote_a_report_to_truth(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    before = state(game).model_dump_json()
    service = DirectorKnowledgeService(context)
    text = "Kite said the western shape was a tarpaulin, not an enemy. I have not checked."
    _, source = send(observer, scene, "testimony", text=text, fictional_channel="comms")
    request = service.open(ADMIN, "directory", scene, source.source_id)
    packet = service.packet(ADMIN, scene, request["id"])
    directory = {entry.actor: entry for entry in packet.actor_directory}
    assert directory[pilot].name == state(game).sheets["2"].callsign
    assert directory[pilot].controller == PLAYER.user_id
    assert directory[pilot].aliases == (directory[pilot].name,)
    assert all("Kite" not in entry.aliases for entry in packet.actor_directory)
    learned = commit(
        service,
        scene,
        source.source_id,
        "first",
        (Acquisition(basis="testimony", quote=text, recipients=(handler,), topic="tactical"),),
    )
    ref = next(
        x
        for x in context.build(ADMIN, scene, actor=handler).references
        if x.id == learned["references"][0]
    )
    assert ref.classification == "reported_claim" and ref.reported_by == pilot
    assert "not an enemy" in ref.text and "I have not checked" in ref.text
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    assert text not in context.build(OTHER, scene, actor=other).model_dump_json()
    assert state(game).model_dump_json() == before


def test_mixed_narration_releases_only_classified_speech_and_private_cannot_disclose(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    enemy = "a sentry hides behind the relay"
    speech = "All clear."
    text = f'I privately see {enemy}. On comms I say "{speech}"'
    _, source = send(observer, scene, "mixed", text=text, fictional_channel="mixed")
    with observer.store.engine.connect() as c:
        assert service.heard(c, scene, source.source_id, handler) == ()
    before = state(game).model_dump_json()
    accepted = commit(
        service,
        scene,
        source.source_id,
        "mixed-learn",
        (
            Acquisition(basis="perception", quote=enemy, recipients=(pilot,)),
            Acquisition(basis="testimony", quote=speech, recipients=(handler,)),
        ),
        (Disclosure(quote=speech, recipients=(handler,)),),
    )
    assert len(accepted["references"]) == 2
    with observer.store.engine.connect() as c:
        assert service.heard(c, scene, source.source_id, handler) == (speech,)
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
        assert service.heard(c, scene, source.source_id, other) == ()
    handler_text = context.build(ADMIN, scene, actor=handler).model_dump_json()
    assert speech in handler_text and enemy not in handler_text
    assert enemy in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    assert state(game).model_dump_json() == before
    _, hidden = send(observer, scene, "hidden", text=enemy, fictional_channel="private")
    request = service.open(ADMIN, "hidden-open", scene, hidden.source_id)
    with pytest.raises(WorkflowError, match="UNPROVEN_SPEECH"):
        service.propose(
            ADMIN,
            "hidden-propose",
            scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                disclosures=(Disclosure(quote=enemy, recipients=(handler,)),),
            ),
        )
    with observer.store.engine.connect() as c:
        assert service.heard(c, scene, hidden.source_id, handler) == ()


def test_paraphrase_uses_actual_words_and_speaker_known_prior_across_scene_handoff(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    original = "a nickel-coloured sentry kneels beneath the loading gantry"
    _, private = send(
        observer, scene, "perception", text=original + " PRIVATE_GRID", fictional_channel="private"
    )
    known = commit(
        service,
        scene,
        private.source_id,
        "perception-learn",
        (Acquisition(basis="perception", quote=original, recipients=(pilot,)),),
    )
    paraphrase = "a lookout in nickel colours is crouching under that loading gantry"
    _, report = send(
        observer, scene, "paraphrase", text="Handler: " + paraphrase, fictional_channel="comms"
    )
    forwarded = commit(
        service,
        scene,
        report.source_id,
        "paraphrase-learn",
        (
            Acquisition(
                basis="paraphrase",
                quote=paraphrase,
                recipients=(handler,),
                prior_reference=known["references"][0],
                topic="tactical",
            ),
        ),
    )
    ref = next(
        x
        for x in context.build(ADMIN, scene, actor=handler).references
        if x.id == forwarded["references"][0]
    )
    assert ref.text == "Reported claim: " + paraphrase and ref.reported_by == pilot
    assert not ref.dependencies and "PRIVATE_GRID" not in ref.model_dump_json()
    target = new_scene(observer)
    carry(context, scene, target, tuple(known["references"] + forwarded["references"]))
    recalled = next(
        x for x in context.build(ADMIN, target, actor=handler).references if paraphrase in x.text
    )
    assert recalled.reported_by == pilot and original not in recalled.text


def test_schema_and_gm_private_feedback_explain_missing_links_without_echoing_input(routed):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    _, source = send(
        observer, scene, "source", text="An uncertain report.", fictional_channel="comms"
    )
    request = service.open(ADMIN, "request", scene, source.source_id)
    raw = {
        "request_id": request["id"],
        "updates": [
            {
                "basis": "report",
                "quote": "PRIVATE_UNTRUSTED_INPUT",
                "recipients": [handler.model_dump(mode="json")],
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, KnowledgeProposal.model_json_schema())
    feedback = service.feedback(ADMIN, scene, request["id"], raw)
    assert not feedback["valid"] and feedback["errors"][0]["code"] == "INVALID_CONTRACT"
    assert "PRIVATE_UNTRUSTED_INPUT" not in json.dumps(feedback)
    with pytest.raises(WorkflowError):
        service.feedback(PLAYER, scene, request["id"], raw)
    raw["updates"][0].update(basis="testimony", quote="An uncertain report.")
    jsonschema.validate(raw, KnowledgeProposal.model_json_schema())
    assert service.feedback(ADMIN, scene, request["id"], raw) == {"valid": True, "errors": []}
