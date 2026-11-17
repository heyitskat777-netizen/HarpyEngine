"""Compile typed GM decisions to the original consumer's exact input shape."""

from typing import Any

from girlframe.ai.gm_outcomes import (
    BattleConsequences,
    CollateralOutcome,
    FactOutcome,
    GorgonJudgment,
    HandlerOutcome,
    KeepOutcome,
    OutcomeNarration,
    OutcomePacket,
    OutcomeProposal,
    PandoraOutcome,
    SensorAnswers,
    TableOutcome,
    WarpOutcome,
    WraithOutcome,
)
from girlframe.ai.gm_protocol import GMPacket, GMProposal, validate_proposal
from girlframe.engine.m2 import ChoiceAnswer, sensors_off_list

CHOICES = {
    "handler_keep": "keep",
    "handler_sensors": "sensors",
    "harpy_sensor_answers": "sensors",
    "battle_handler": "battle_consequences",
    "gorgon_asset_capability": "gorgon_judgment",
    "gorgon_contest_judge": "gorgon_judgment",
    "gorgon_attack_judge": "gorgon_judgment",
    "gorgon_collateral_reach": "gorgon_judgment",
    "gorgon_collateral": "collateral",
    "gorgon_warp": "warp",
    "janus_pandora_child": "pandora",
    "wyvern_wraith_rules": "wraith",
    "snoop_object_fact": "source_fact",
    "battle_gm_table": "table",
    "wyvern_gm_outcome": "table",
}


def validate(packet: OutcomePacket, proposal: OutcomeProposal) -> ChoiceAnswer | None:
    if proposal.request_id != packet.request_id or proposal.decision.kind != packet.operation:
        raise ValueError("Wrong source request or operation")
    citations = set(proposal.cited_evidence)
    if len(citations) != len(proposal.cited_evidence):
        raise ValueError("Use distinct evidence citations")
    if not {"source", "native"} <= citations or not citations <= {e.id for e in packet.evidence}:
        raise ValueError("Cite the frozen source and actual native evidence")
    d = proposal.decision
    native: Any = packet.native
    if isinstance(d, KeepOutcome):
        if packet.frame is None:
            raise ValueError("Keep requires an explicit framed goal")
        scope = packet.frame.response_scope
        if d.verdict != "needs_clarification":
            if scope == "unresolved" or (native.get("response_scope_required") and scope is None):
                raise ValueError("RESPONSE_OWNERSHIP: establish whose response determines success")
            if scope == "other" and not native.get("response_authorized"):
                raise ValueError(
                    "RESPONSE_OWNERSHIP: preserve the actual target controller's response"
                )
            if packet.frame.response_request is not None:
                if "target_response" not in citations:
                    raise ValueError("Cite the actual target_response evidence")
                if native.get("response_decision") == "decline" and d.verdict == "enough":
                    raise ValueError(
                        "RESPONSE_OWNERSHIP: a declined voluntary response cannot pass"
                    )
        action = native["action"]
        result = action["data"]["result"]
        # Reuse actual trait/coverage/prerequisite validation; no alternate keyword oracle.
        evidence = tuple(
            e.model_copy(update={"id": {"source": "goal", "native": "receipt"}.get(e.id, e.id)})
            for e in packet.evidence
        )
        p = GMPacket(
            request_id=packet.request_id,
            play="keep_your_head",
            source_id=packet.source_id,
            source_revision=1,
            action_id=action["id"],
            action_revision=action["revision"],
            receipt_id=(action["data"].get("receipt") or {}).get("id", "native-adjudication"),
            goal=action["data"].get("prepared", {}).get("context", "Actual native Keep"),
            frame=packet.frame,
            evidence=evidence,
            positive=tuple(result["positive"]),
            negative=tuple(result["negative"]),
            stage="awaiting_keep_ruling",
            pending_choices=(),
            native_result=result,
            followups=(),
            gm_private_context={},
        )
        validate_proposal(
            p,
            GMProposal(
                request_id=p.request_id,
                verdict=d.verdict,
                assessments=tuple(
                    a.model_copy(
                        update={
                            "evidence_ids": tuple(
                                {"source": "goal", "native": "receipt"}.get(x, x)
                                for x in a.evidence_ids
                            )
                        }
                    )
                    for a in d.assessments
                ),
                cited_evidence=tuple(
                    {"source": "goal", "native": "receipt"}.get(x, x)
                    for x in proposal.cited_evidence
                ),
                private_reasoning=proposal.private_reasoning,
            ),
        )
        if d.verdict == "needs_clarification":
            return None
        return ChoiceAnswer(flag=d.verdict == "enough", text=d.narration)
    if isinstance(d, SensorAnswers):
        result = native["action"]["data"]["result"]
        if native["choice"]["kind"] == "harpy_sensor_answers":
            if set(d.answers) != {"a1"} or d.consequence or not d.answers["a1"].strip():
                raise ValueError("Answer the actual Harpy question block honestly")
            return ChoiceAnswer(flag=True, text=d.answers["a1"])
        if set(d.answers) != {f"a{i + 1}" for i in range(len(result["questions"]))} or not all(
            0 < len(x.strip()) <= 1200 for x in d.answers.values()
        ):
            raise ValueError("Answer each actual question exactly once")
        required = result["tier"] == "high" and sensors_off_list(
            result["questions"], result["tier"]
        )
        if required != (d.consequence is not None):
            raise ValueError("Preserve the actual off-list consequence branch")
        return ChoiceAnswer(fields=d.answers, options=(d.consequence,) if d.consequence else ())
    if isinstance(d, BattleConsequences):
        if len(set(d.choices)) != len(d.choices):
            raise ValueError("Choose distinct printed consequences")
        return ChoiceAnswer(options=d.choices, text=d.account)
    if isinstance(d, GorgonJudgment):
        kind = native["choice"]["kind"]
        if kind == "gorgon_asset_capability":
            if d.verdict not in ("capable", "incapable") or d.losing_asset or d.indirect:
                raise ValueError("This source judges capability only")
            return ChoiceAnswer(flag=d.verdict == "capable", text=d.account)
        allowed = {
            "gorgon_contest_judge": ("attacker", "defender"),
            "gorgon_attack_judge": ("lands", "averted"),
            "gorgon_collateral_reach": ("reached", "unreachable"),
        }[kind]
        if d.verdict not in allowed or bool(d.losing_asset) != (kind == "gorgon_contest_judge"):
            raise ValueError("Use this actual judgment's result and losing Asset")
        body = native["choice_body"]
        if kind == "gorgon_attack_judge" and body.get("unavoidable") and d.verdict != "lands":
            raise ValueError("The actual source is unavoidable")
        if kind != "gorgon_contest_judge" and d.indirect:
            raise ValueError("Indirect approach belongs to its actual contest")
        if d.losing_asset:
            meta = native["action"]["data"]["gorgon_play"]
            assets = meta["defending_assets"] if d.verdict == "attacker" else meta["assets"]
            if d.losing_asset not in assets:
                raise ValueError("Only a genuinely pitted Asset may be lost")
        return ChoiceAnswer(
            options=(d.verdict,),
            fields={"asset": d.losing_asset} if d.losing_asset else {},
            flag=True if d.indirect else None,
            text=d.account,
        )
    if isinstance(d, CollateralOutcome):
        if (
            len(set(d.effects)) != len(d.effects)
            or ("structure" in d.effects) != bool(d.structure)
            or ("civilians" in d.effects) != bool(d.civilians)
        ):
            raise ValueError("Bind each collateral effect to its actual subjects")
        fields = {}
        if d.structure:
            fields["structure"] = d.structure
        if d.civilians:
            fields["civilians"] = ",".join(d.civilians)
        return ChoiceAnswer(options=d.effects, fields=fields, text=d.account)
    if isinstance(d, WarpOutcome):
        if (
            (d.effect == "evolve") != bool(d.name and d.description)
            or d.effect != "evolve"
            and (d.name or d.description)
        ):
            raise ValueError("Evolution alone defines the actual new Asset")
        return ChoiceAnswer(
            options=(d.effect,),
            fields={"name": d.name, "description": d.description} if d.effect == "evolve" else {},
            text=d.account,
        )
    if isinstance(d, PandoraOutcome):
        tier = native["action"]["data"]["result"]["tier"]
        if len(d.child.assets) != {"low": 1, "mid": 2, "high": 3}[tier] or len(
            d.child.descriptions
        ) != len(d.child.assets):
            raise ValueError("The child must preserve its actual tier's Asset count")
        if (
            d.child.gorgon_class
            not in {"low": ("dormant",), "mid": ("benevolent",), "high": ("aggressive", "erratic")}[
                tier
            ]
        ):
            raise ValueError("The child must preserve its actual tier's class")
        return ChoiceAnswer(fields={"child": d.child.model_dump_json()})
    if isinstance(d, WraithOutcome):
        tier = native["action"]["data"]["result"]["tier"]
        if (tier in ("low", "high")) != bool(d.tag):
            raise ValueError("Preserve the actual Wraith Tag branch")
        return ChoiceAnswer(
            options=("frame_bound_npc",), text=d.rules, fields={"tag": d.tag} if d.tag else {}
        )
    if isinstance(d, FactOutcome):
        return ChoiceAnswer(flag=d.established, text=d.account)
    if isinstance(d, HandlerOutcome):
        if d.play not in ("escalate", "support", "contaminant_warp") or d.effect.kind != d.play:
            raise ValueError("This adapter only consumes its finite world-authoring Handler grant")
    if isinstance(d, TableOutcome):
        if native["action"]["data"]["play"] == "all_out_assault":
            if d.vast_advantage is None or d.answers:
                raise ValueError("Assault has one GM advantage judgment")
            return ChoiceAnswer(flag=d.vast_advantage, text=d.account)
        if (
            d.vast_advantage is not None
            or not d.answers
            or not all(0 < len(x.strip()) <= 1200 for x in d.answers.values())
        ):
            raise ValueError("Exploration needs bounded actual question answers")
        from girlframe.engine.m3_wyvern import Session

        private: Any = packet.gm_private_context

        source = next(
            Session.model_validate_json(f["body"])
            for f in private["canonical"]["facts"]
            if f.get("kind") == "wyvern_session"
            and Session.model_validate_json(f["body"]).id == native["action"]["id"]
        )
        if set(d.answers) != set(source.questions):
            raise ValueError("Answer every actual exploration question")
        return ChoiceAnswer(fields=d.answers, text=d.account)
    if isinstance(d, OutcomeNarration):
        if (
            native["action"]["state"] != "complete"
            or not set(d.effect_refs) <= native["action"]["data"]["result"].keys()
        ):
            raise ValueError("Narrate only referenced actual completed result fields")
    return None
