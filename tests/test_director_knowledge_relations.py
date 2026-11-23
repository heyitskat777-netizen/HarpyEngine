"""Competing accounts retain history without disclosing relationships to hidden reports."""

import json

import pytest
from test_director_adjudication import prepare
from test_director_continuity import carry, new_scene, roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_knowledge_contract_revision import commit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.ai.director import KnowledgeRelation
from girlframe.ai.gm_outcomes import OutcomeNarration, OutcomeProposal
from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


def claim(service, scene, key, text, recipients, *, viewer=PLAYER, relations=()):
    _, source = send(
        service.observer, scene, key, text=text, viewer=viewer, fictional_channel="comms"
    )
    result = commit(
        service,
        scene,
        source.source_id,
        key + ":learn",
        (
            Acquisition(
                basis="testimony",
                quote=text,
                recipients=recipients,
                relations=relations,
                topic="tactical",
            ),
        ),
    )
    return result["references"][0], source


def test_competing_and_correcting_claims_preserve_authors_and_hide_unknown_relationships(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    service = DirectorKnowledgeService(context)
    before = state(game).model_dump_json()
    old, _ = claim(
        service,
        scene,
        "old",
        "A scout is inside the east relay. PRIVATE_REPORT_DETAIL",
        (handler, pilot),
    )
    rival, _ = claim(
        service,
        scene,
        "rival",
        "The east relay is clear; I saw a loose shield.",
        (handler, other),
        viewer=OTHER,
        relations=(KnowledgeRelation(kind="competes_with", reference_id=old),),
    )
    correction, _ = claim(
        service,
        scene,
        "correction",
        "I withdraw my enemy identification; it was a shield.",
        (handler, pilot, other),
        relations=(KnowledgeRelation(kind="corrects", reference_id=old),),
    )
    gm = {ref.id: ref for ref in context.build(ADMIN, scene).references}
    assert gm[rival].relations == (KnowledgeRelation(kind="competes_with", reference_id=old),)
    assert gm[correction].relations == (KnowledgeRelation(kind="corrects", reference_id=old),)
    assert gm[old].reported_by == pilot and gm[rival].reported_by == other
    assert gm[correction].reported_by == pilot
    assert all(
        gm[identity].classification == "reported_claim" for identity in (old, rival, correction)
    )
    assert gm[old].text.endswith("PRIVATE_REPORT_DETAIL")
    assert state(game).model_dump_json() == before
    visible = {ref.id: ref for ref in context.build(OTHER, scene, actor=other).references}
    assert old not in visible
    assert visible[rival].relations == () and visible[correction].relations == ()
    assert old not in visible[rival].dependencies and old not in visible[correction].dependencies
    assert "PRIVATE_REPORT_DETAIL" not in json.dumps(
        [ref.model_dump(mode="json") for ref in visible.values()]
    )
    assert old not in json.dumps([ref.model_dump(mode="json") for ref in visible.values()])
    assert "relations" not in visible[rival].model_dump(mode="json")
    with observer.store.engine.connect() as c:
        handler_refs = {
            ref.id: ref for ref in context._handler_for_request(c, PLAYER, scene).references
        }
    assert handler_refs[rival].relations[0].reference_id == old
    assert handler_refs[correction].relations[0].kind == "corrects"


def test_relation_dependencies_keep_current_roots_and_remap_across_scene_handoffs(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    old, _ = claim(service, scene, "old", "The relay hatch is jammed.", (handler, pilot))
    correction, _ = claim(
        service,
        scene,
        "corrected",
        "I checked again: the relay hatch is open.",
        (handler, pilot),
        relations=(KnowledgeRelation(kind="corrects", reference_id=old),),
    )
    current = context.build(ADMIN, scene)
    with pytest.raises(WorkflowError, match="ACTIVE_DEPENDENCY"):
        context.archive(
            ADMIN, "keep-related-history", scene, current.revision, (old,), "Retire old account"
        )
    _, source = send(
        observer, scene, "bad-relation", text="Another account.", fictional_channel="comms"
    )
    request = service.open(ADMIN, "bad-relation:open", scene, source.source_id)
    with pytest.raises(WorkflowError, match="STALE_RELATION"):
        service.propose(
            ADMIN,
            "bad-relation:propose",
            scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                updates=(
                    Acquisition(
                        basis="testimony",
                        quote="Another account.",
                        recipients=(handler,),
                        relations=(KnowledgeRelation(kind="corrects", reference_id="missing"),),
                    ),
                ),
            ),
        )
    second = new_scene(observer)
    with pytest.raises(WorkflowError, match="CONTINUITY_DEPENDENCY"):
        carry(context, scene, second, (correction,), "incomplete-relationship")
    copied = carry(context, scene, second, (old, correction), "first-handoff")
    old2, correction2 = copied["references"][old], copied["references"][correction]
    refs = {ref.id: ref for ref in context.build(ADMIN, second, actor=handler).references}
    assert refs[correction2].relations == (KnowledgeRelation(kind="corrects", reference_id=old2),)
    third = new_scene(observer, 902, 901)
    again = carry(context, second, third, (old2, correction2), "second-handoff")
    refs = {ref.id: ref for ref in context.build(ADMIN, third, actor=handler).references}
    final = refs[again["references"][correction2]]
    assert final.relations[0].reference_id == again["references"][old2]
    assert final.origin_scene == scene and final.origin_reference == correction
    assert final.reported_by == pilot and final.classification == "reported_claim"
    observer.set_consent(PLAYER, "withdraw-original", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="STALE_CONTINUITY"):
        context.build(ADMIN, third, actor=handler)


def test_native_approved_outcome_can_correct_a_report_without_rewriting_either(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    old, _ = claim(
        service, scene, "unverified", "The calibration needle might not hold.", (handler, pilot)
    )
    _, _, native, worker, gateway = prepare(
        routed, "Hold the calibration needle steady.", "native-result"
    )
    answer(game, ADMIN, "handler_keep", flag=True, text="The needle stays on its mark.")
    tick(worker, gateway, 5)
    session = DirectorSessionService(context)
    request = session.outcomes.open(ADMIN, "narration:open", scene, "completed", native)
    packet = session.outcomes.packet(ADMIN, scene, request["id"])
    text = "The calibration needle holds steady."
    proposal = session.outcomes.propose(
        ADMIN,
        "narration:propose",
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=OutcomeNarration(text=text, effect_refs=("tier",)),
            cited_evidence=("source", "native"),
            private_reasoning="Synthetic source review.",
        ),
    )
    session.outcomes.confirm(ADMIN, "narration:confirm", scene, proposal["id"])
    source = session.contributions(PLAYER, scene)[-1]
    before = state(game).model_dump_json()
    learned = commit(
        service,
        scene,
        source["id"],
        "native-knowledge",
        (
            Acquisition(
                basis="outcome",
                quote=text,
                recipients=(handler, pilot),
                relations=(KnowledgeRelation(kind="corrects", reference_id=old),),
            ),
        ),
    )
    refs = {ref.id: ref for ref in context.build(ADMIN, scene).references}
    latest = refs[learned["references"][0]]
    assert latest.classification == "approved_outcome" and latest.reported_by is None
    assert latest.relations == (KnowledgeRelation(kind="corrects", reference_id=old),)
    assert refs[old].classification == "reported_claim" and refs[old].reported_by == pilot
    assert refs[old].text == "Reported claim: The calibration needle might not hold."
    assert state(game).model_dump_json() == before
