"""Explicit offline facilitator interpretations for protocol exercises, never production NLP."""

import json
from pathlib import Path

from girlframe.ai.gm_protocol import Assessment, GMProposal, Prerequisite, TaskFrame, TraitClaim
from girlframe.services.gm_adapter import GMAdapterService


class FixtureGM:
    def __init__(self, trait_interpretation):
        self.trait_interpretation = trait_interpretation
        self.calls = 0
        self.last = None

    def propose(self, packet):
        self.calls += 1
        self.last = packet
        if packet.stage != "awaiting_keep_ruling":
            verdict = "native_outcome" if packet.stage == "complete" else "pending_choices"
            return GMProposal(
                request_id=packet.request_id,
                verdict=verdict,
                cited_evidence=("goal", "receipt"),
                private_reasoning="Retain actual printed native outcomes "
                "and outstanding owner choices.",
            )
        assessments = []
        for demand in packet.frame.demands:
            # A fixture facilitator supplied relevance; no verdict or audit expectation
            # is provided. Actual native traits determine this test provider's answer.
            trait = self.trait_interpretation[demand.id]
            positive = trait in packet.positive
            negative = trait in packet.negative
            assessments.append(
                Assessment(
                    demand_id=demand.id,
                    sufficient=True if positive else False if negative else None,
                    evidence_ids=("goal", "traits"),
                    traits=(TraitClaim(trait=trait, polarity="are" if positive else "are_not"),)
                    if positive or negative
                    else (),
                    private_reason="This is an explicit fixture GM interpretation for this demand.",
                )
            )
        constraints = {p.evidence_id: p.state for p in packet.frame.prerequisites}
        conditions = {f.id for f in packet.evidence if f.id.startswith("condition:")}
        if (
            packet.frame.intent != "established"
            or not assessments
            or conditions - constraints.keys()
            or "unknown" in constraints.values()
            or any(a.sufficient is None for a in assessments)
        ):
            verdict = "needs_clarification"
        else:
            verdict = (
                "not_enough"
                if "blocked" in constraints.values()
                or any(a.sufficient is False for a in assessments)
                else "enough"
            )
        return GMProposal(
            request_id=packet.request_id,
            verdict=verdict,
            assessments=tuple(assessments),
            cited_evidence=("goal", "receipt", "traits", *sorted(conditions)),
            private_reasoning="Each explicitly framed demand is assessed against actual choices; "
            "unknown prerequisites require review.",
        )


class ProtocolAudit:
    """Fixture-only bridge allowing the original audit driver to exercise the new API."""

    def __init__(self, context, case_id, *, provider=None, definition=None):
        from test_ledger import ADMIN

        self.gm_viewer = ADMIN  # Actual fixture facilitator, never an impersonated player.
        path = Path(__file__).resolve().parent / "fixtures/director_gm_frames.json"
        self.definition = definition or json.loads(path.read_text())["frames"][case_id]
        self.provider = (
            provider
            if provider is not None
            else FixtureGM(self.definition["fixture_trait_interpretation"])
        )
        self.adapter = GMAdapterService(context, self.provider)
        self.records = {}

    @property
    def calls(self):
        return self.provider.calls

    @property
    def last(self):
        return self.provider.last

    def adjudicate(self, actor, key, scene, source_id, source_revision, action):
        if key not in self.records:
            packet = self.adapter.evidence(
                self.gm_viewer, scene, source_id, source_revision, action
            )
            task = TaskFrame.model_validate_json(
                json.dumps({k: self.definition[k] for k in ("stakes", "demands", "intent")})
            )
            task = task.model_copy(
                update={
                    "prerequisites": tuple(
                        Prerequisite(
                            evidence_id=f.id,
                            state="unknown",
                            interpretation="This fixture scene condition needs "
                            "explicit prerequisite review.",
                        )
                        for f in packet.evidence
                        if f.id.startswith("condition:")
                    )
                }
            )
            framed = self.adapter.frame(
                self.gm_viewer, key + ":frame", scene, source_id, source_revision, action, task
            )
            self.records[key] = framed
        record = self.adapter.evaluate(
            self.gm_viewer, key + ":evaluate", scene, self.records[key]["id"]
        )
        proposal = record["proposal"]
        verdict = {"enough": "success", "not_enough": "failure"}.get(
            proposal["verdict"], proposal["verdict"]
        )
        return {
            "id": record["id"],
            "proposal": {
                "verdict": verdict,
                "enough": True if verdict == "success" else False if verdict == "failure" else None,
                "reasoning": proposal["private_reasoning"],
                "narration": "Private proposal; participant wording is constructed separately.",
                "source_refs": proposal["cited_evidence"],
            },
        }

    def confirm(self, viewer, scene, identity):
        return self.adapter.confirm_keep(viewer, "fixture-accept", scene, identity)

    def readback(self, actor, scene, source, action):
        record = self.adjudicate(
            actor, "completed-review", scene, source.source_id, source.source_revision, action
        )
        view = self.adapter.view(actor, scene, record["id"])
        from test_ledger import ADMIN

        handler_view = self.adapter.view(ADMIN, scene, record["id"])
        assert "SYNTHETIC_AUDIT_TARGET_PRIVATE" not in json.dumps(handler_view)
        assert "SYNTHETIC_AUDIT_GM_CANARY" not in json.dumps(view)
        return {
            "supported": True,
            "confirmed_gm_verdict": None,
            "text": view["text"],
            "immediate_complete": view["immediate_complete"],
            "fully_resolved": view["fully_resolved"],
        }
