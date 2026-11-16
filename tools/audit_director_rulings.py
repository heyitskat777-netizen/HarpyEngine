"""Curated native-Play experiment. Records judgment failures; never makes them green."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "rules"))
TITLES = {
    "keep_your_head": "Keep Your Head",
    "check_sensors": "Check Your Sensors",
    "engage": "Engage",
    "disobey_orders": "Disobey Orders",
    "flirt": "Flirt",
}


def classify(case, verdict):
    if verdict in ("native_outcome", "pending_choices"):
        return (
            "native_adapter_complete" if verdict == "native_outcome" else "native_adapter_pending"
        )
    if verdict == "requires_play_adapter":
        return "adapter_missing"
    if verdict == "source_guard":
        return "lineage_adapter_missing"
    if verdict == "native_guard":
        return "native_guard_expected" if case["desired"] == verdict else "unexpected_native_guard"
    if verdict == case["desired"]:
        return "expected_ruling"
    if verdict in case["acceptable"]:
        return "safe_review_coverage_gap"
    if verdict in ("success", "failure"):
        return "poorly_grounded_ruling"
    return "unexpected_review" if verdict == "needs_clarification" else "unexpected_error"


def run_case(case, *, protocol=False, provider=None, frame_definition=None, confirm_proposal=None):
    import pytest
    from test_director_conversation import GMProbe, HandlerProbe
    from test_director_observation import observed, send
    from test_ledger import ADMIN, OTHER, PLAYER, ledger
    from test_m2_game import answer, pass_tags, start, state, tick

    from girlframe.ai.adjudication import SyntheticAdjudicator
    from girlframe.engine.m2 import QUESTIONS, PlayInput
    from girlframe.services.director_adjudication import DirectorAdjudicationService
    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_conversation import DirectorConversationService
    from girlframe.services.onboarding import WorkflowError

    class Trace(SyntheticAdjudicator):
        calls = 0
        last = None

        def adjudicate(self, request):
            self.calls += 1
            self.last = request
            # Review expectations are never passed to the provider.
            assert "expected_verdicts" not in request.model_dump_json()
            return super().adjudicate(request)

    row = {
        "case": case,
        "gm_verdict": "not_called",
        "provider_calls": 0,
        "dice_calls": 0,
        "native_complete": False,
        "native_rejection": None,
        "gm_source_rejection": None,
        "ruling": None,
        "native": {},
        "external_tokens": 0,
        "external_cost": 0,
    }
    with TemporaryDirectory(prefix="harpy-ruling-audit-") as directory:
        patch = pytest.MonkeyPatch()
        fixture = ledger.__wrapped__(Path(directory), patch)
        store = next(fixture)
        try:
            observer, scene, clock, game, worker, gateway, dice = observed.__wrapped__(store)
            context = DirectorContextService(observer)
            with store.engine.connect() as c:
                actors = tuple(
                    observer._authorize_input(c, viewer, scene, role)[2]
                    for viewer, role in ((ADMIN, "handler"), (PLAYER, "pilot"), (OTHER, "pilot"))
                )
            with store.transaction() as c:
                canon = state(game)
                canon.facts.append({"kind": "gm_only", "body": "SYNTHETIC_AUDIT_GM_CANARY"})
                if case.get("gm_condition"):
                    canon.facts.append(
                        {
                            "kind": "scene_condition",
                            "visibility": "gm_only",
                            "body": case["gm_condition"],
                        }
                    )
                game.event(
                    c, ADMIN.user_id, "audit-background", "synthetic.audit_background", canon
                )
            _, background = send(
                observer,
                scene,
                "environment",
                viewer=ADMIN,
                text="Synthetic scene framing: " + case["environment"],
            )
            context.record(
                ADMIN, "environment-reference", scene, background.source_id, 0, known_by=actors
            )
            clock.now += 120
            batch = observer.claim_review(scene)
            assert batch is not None
            observer.acknowledge_review(batch.run_id, batch.lease_token, success=True)
            text = f"GM, I declare {TITLES[case['play']]} to {case['goal']}."
            _, source = send(observer, scene, "attempt", text=text)
            gm, handler = GMProbe(), HandlerProbe()
            conversation = DirectorConversationService(context, gm=gm, handler=handler)
            before = state(game).model_dump_json()
            bundle = conversation.process_message(PLAYER, "route", scene, source.source_id, 1)
            assert state(game).model_dump_json() == before and dice.calls == 0
            assert bundle["handler"] is None and len(handler.requests) == 0
            row["gm_routing"] = {
                key: bundle["gm"]["reply"][key] for key in ("play_id", "disposition", "gm_decision")
            }
            row["optional_handler_spoke"] = False
            dice.faces = tuple(case["faces"])
            native = None
            root = None
            try:
                if case["play"] == "disobey_orders" and not case.get("missing_order"):
                    root = game.issue_order(
                        ADMIN,
                        "actual-order",
                        900,
                        PLAYER.user_id,
                        "Synthetic superior order: hold the assigned position.",
                    )
                    tick(worker, gateway)
                    answer(game, PLAYER, "order_response", options=("disobey",))
                    native = game.begin(
                        PLAYER,
                        "refusal",
                        900,
                        state(game).sheets["2"].revision,
                        PlayInput(
                            play="disobey_orders",
                            context=text,
                            trigger_confirmed=True,
                            heat=0,
                            order_id=root["order_id"],
                            parent=root["action_id"],
                            witnessed=True,
                        ),
                    )["action_id"]
                else:
                    extra = (
                        {"target": OTHER.user_id}
                        if case["play"] == "flirt" and not case.get("missing_target")
                        else {}
                    )
                    native = start(game, play=case["play"], context=text, **extra)
            except WorkflowError as error:
                assert dice.calls == 0
                row["gm_verdict"] = "native_guard"
                row["native_rejection"] = str(error)
            if native:
                assert dice.calls == 0
                tick(worker, gateway)
                assert dice.calls == 1
                pass_tags(game)
                with store.engine.connect() as c:
                    rolled = game.action(c, native)["data"]["result"]
                level = rolled["tier"]
                count = {"low": 1, "mid": 2, "high": 3}[level]
                trace = Trace()
                adjudicator = DirectorAdjudicationService(conversation, trace)
                if protocol:
                    from gm_protocol_fixture import ProtocolAudit

                    trace = ProtocolAudit(
                        context, case["id"], provider=provider, definition=frame_definition
                    )
                    adjudicator = trace

                def probe():
                    before = state(game).model_dump_json()
                    try:
                        record = adjudicator.adjudicate(
                            PLAYER, "judgment", scene, source.source_id, 1, native
                        )
                        assert (
                            adjudicator.adjudicate(
                                PLAYER, "judgment", scene, source.source_id, 1, native
                            )
                            == record
                        )
                        row["gm_verdict"] = record["proposal"]["verdict"]
                        row["ruling"] = record["proposal"]
                        row["proposal_id"] = record["id"]
                    except WorkflowError as error:
                        row["gm_source_rejection"] = str(error)
                        row["gm_verdict"] = "source_guard"
                    assert state(game).model_dump_json() == before and dice.calls == 1

                play = case["play"]
                leave_pending = False
                if play == "keep_your_head":
                    choices = {
                        "options": tuple(
                            case.get(
                                "positive", ["tough"] if level == "low" else ["tough", "in_control"]
                            )
                        )
                    }
                    if level == "mid":
                        choices["denied"] = tuple(case.get("negative", ["desperate"]))
                    if level == "high":
                        choices = {"text": "SYNTHETIC_AUDIT_HIGH_TAG"}
                    answer(game, PLAYER, "actor_keep", **choices)
                    probe()
                    status = classify(case, row["gm_verdict"])
                    proposal = row["ruling"]
                    if proposal and proposal["enough"] is not None and status == "expected_ruling":
                        owner_flag = proposal["enough"]
                        owner_text = proposal["reasoning"] + "\n" + proposal["narration"]
                        row["completion_authority"] = "test_controller_confirms_computed_gm_ruling"
                    else:
                        owner_flag, owner_text = (
                            False,
                            "Explicit fixture-controller completion; "
                            "not endorsement of the GM proposal.",
                        )
                        row["completion_authority"] = (
                            "manual_fixture_completion_without_endorsement"
                        )
                    if protocol and confirm_proposal is not None:
                        accept = proposal and proposal["enough"] is not None
                        accept = bool(accept and confirm_proposal(proposal))
                        row["completion_authority"] = (
                            "manual_offline_original_controller_confirmation"
                            if accept
                            else "left_pending_without_controller_confirmation"
                        )
                        if accept:
                            trace.confirm(ADMIN, scene, row["proposal_id"])
                        else:
                            leave_pending = True
                    elif (
                        protocol
                        and proposal
                        and proposal["enough"] is not None
                        and status == "expected_ruling"
                    ):
                        trace.confirm(ADMIN, scene, row["proposal_id"])
                    else:
                        answer(game, ADMIN, "handler_keep", flag=owner_flag, text=owner_text)
                elif play == "check_sensors":
                    if case.get("off_list"):
                        answer(
                            game,
                            PLAYER,
                            "actor_sensors",
                            options=(QUESTIONS[0],),
                            fields={
                                "q1": "Which training lane is open?",
                                "q2": "What is the relay code?",
                            },
                        )
                    else:
                        answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:count])
                    probe()
                    answers = {
                        f"a{i + 1}": f"Explicit synthetic controller answer {i + 1}"
                        for i in range(count)
                    }
                    answer(
                        game,
                        ADMIN,
                        "handler_sensors",
                        fields=answers,
                        options=("incomplete_information",) if case.get("off_list") else (),
                    )
                    row["completion_authority"] = "scripted_handler_answers_not_gm_generated"
                elif play == "engage":
                    maneuvers = tuple(case.get("maneuvers", ["pin", "advance", "protect"][:count]))
                    answer(
                        game,
                        PLAYER,
                        "actor_engage",
                        options=maneuvers,
                        fields={x: "girl:0" for x in maneuvers},
                        denied=() if level == "mid" else ("girl:0",),
                    )
                    probe()
                    row["completion_authority"] = "printed_maneuvers_and_damage_from_owner_choices"
                elif play == "disobey_orders":
                    if level == "mid":
                        answer(
                            game,
                            PLAYER,
                            "actor_disobey",
                            options=("tag_heat",),
                            number=2,
                            text="SYNTHETIC_DEFIANT",
                        )
                    elif level == "high":
                        answer(game, PLAYER, "actor_disobey", flag=True)
                    probe()
                    answer(game, ADMIN, "handler_disobey", flag=case.get("punishment", False))
                    row["completion_authority"] = "printed_order_child_and_original_owner_choices"
                else:
                    if level != "low":
                        answer(
                            game,
                            PLAYER,
                            "actor_flirt",
                            options=("name",),
                            fields={"extra": "owe"} if level == "high" else {},
                            text="Explicit synthetic overstep" if level == "high" else "",
                        )
                    answer(game, OTHER, "target_flirt", text="SYNTHETIC_AUDIT_TARGET_PRIVATE")
                    if level == "high":
                        answer(game, OTHER, "flirt_owe_tag", text="SYNTHETIC_OWED")
                    probe()
                    row["completion_authority"] = "scripted_target_owned_response_not_gm_generated"
                tick(worker, gateway, 5)
                complete = game.inspect(PLAYER, native)
                assert (complete["state"] == "complete") == (not leave_pending)
                assert dice.calls == 1
                replay = game.roll(PLAYER, "m2.confirmed_roll:" + native, native)
                assert game.roll(PLAYER, "m2.confirmed_roll:" + native, native) == replay
                assert dice.calls == 1
                row["native_complete"] = complete["state"] == "complete"
                result = complete["result"] or {}
                row["native"] = {
                    key: result[key]
                    for key in (
                        "total",
                        "tier",
                        "positive",
                        "negative",
                        "can_disobey",
                        "off_list",
                        "maneuvers",
                        "damaged",
                        "consequence",
                    )
                    if key in result
                }
                row["native"]["question_count"] = len(result.get("questions", []))
                row["native"]["target_answer_recorded"] = "target_answer" in result
                row["native"]["parent_completed"] = (
                    game.inspect(PLAYER, root["action_id"])["state"] == "complete" if root else None
                )
                row["native"]["pending_obligation_kinds"] = [
                    x.kind for x in state(game).obligations if x.state == "pending"
                ]
                row["provider_calls"] = trace.calls
                if trace.last:
                    assert "SYNTHETIC_AUDIT_GM_CANARY" in trace.last.model_dump_json()
                    row["gm_received_scene_condition"] = bool(
                        case.get("gm_condition")
                        and case["gm_condition"] in trace.last.model_dump_json()
                    )
                    row["gm_received_private_target_answer"] = (
                        "SYNTHETIC_AUDIT_TARGET_PRIVATE" in trace.last.model_dump_json()
                    )
                try:
                    if protocol:
                        row["completed_review"] = trace.readback(PLAYER, scene, source, native)
                    else:
                        review = conversation.review_play(PLAYER, "completed-review", scene, native)
                        row["completed_review"] = {
                            "supported": True,
                            "confirmed_gm_verdict": review.get("verdict"),
                            "text": review["reply"]["text"],
                        }
                except WorkflowError as error:
                    row["completed_review"] = {"supported": False, "reason": str(error)}
            with store.engine.connect() as c:
                handler_context = context._handler_for_request(c, PLAYER, scene)
            assert all(
                canary not in handler_context.model_dump_json()
                for canary in ("SYNTHETIC_AUDIT_GM_CANARY", "SYNTHETIC_AUDIT_TARGET_PRIVATE")
            )
            assert all(
                canary not in json.dumps(row.get("ruling"))
                for canary in ("SYNTHETIC_AUDIT_GM_CANARY", "SYNTHETIC_AUDIT_TARGET_PRIVATE")
            )
            row["handler_projection_private_data_separated"] = True
            row["dice_calls"] = dice.calls
            row["status"] = classify(case, row["gm_verdict"])
            row["observation_pending"] = observer.status(PLAYER, scene).pending_messages
            return row
        finally:
            fixture.close()
            patch.undo()


def render(rows, output, summary):
    statuses = summary["statuses"]
    followups = sum(bool(row.get("native", {}).get("pending_obligation_kinds")) for row in rows)
    html = [
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Director ruling audit</title>"
        "<style>body{max-width:1150px;margin:35px auto;padding:0 20px;font:16px/1.5 system-ui;"
        "background:#f7f5f0;color:#242424}td,th{padding:9px;border:1px solid #bbb;text-align:left}"
        "table{border-collapse:collapse;width:100%}article{margin:28px 0;border-top:1px solid #aaa}"
        ".bad{background:#f7dfd1}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#285974}</style>"
        f"<h1>{len(rows)} native Play attempts: GM ruling audit</h1>"
        "<p>Actual native engine rolls and choices. GM setup: "
        + escape(summary.get("judgment_setup", "Legacy local stand-in"))
        + ". "
        "Expected review criteria are independent inputs to the audit, never provider inputs. "
        "These checks assess the prototype, not a real AI model. No paid calls or live changes.</p>"
        "<h2>Reviewed findings</h2>"
        f"<p>The engine executed {summary['native_complete']} immediate Play resolutions and "
        f"blocked {statuses.get('native_guard_expected', 0)} invalid requests before rolling. "
        f"The local GM produced {statuses.get('poorly_grounded_ruling', 0)} poorly grounded "
        "Keep rulings under the curated case assumptions. This is a judgment-quality finding, "
        "not a claim that 10 printed-rule checks failed.</p>"
        "<ul><li><b>Context review:</b> inspect highlighted cases for negated/quoted words, "
        "multiple demands, blocked access and missing life-support prerequisites.</li>"
        f"<li><b>Adapter gaps:</b> {statuses.get('adapter_missing', 0)} cases need Play-specific "
        f"GM adapters; {statuses.get('lineage_adapter_missing', 0)} legitimate Disobey Orders "
        "cases need a parent/child source adapter.</li>"
        "<li><b>Keep engine checks:</b> invalid requests consumed no dice, replays did "
        "not reroll, and Handler views excluded private GM/target data.</li></ul>"
        + (
            "<p><b>Protocol v2:</b> facilitator-authored demands and trait relevance feed a "
            "fixture provider. Outcomes demonstrate structured binding, validation and native "
            "adapter coverage. They do not establish autonomous language understanding or "
            "independent narrative judgment. All five native adapters and original "
            "Disobey parent lineage are exercised; other Plays retain native outcomes.</p>"
            if summary.get("protocol") == 2
            else "<p>Recommended next work: structured AI-GM requests, explicit "
            "goals/prerequisites/stakes, Play-specific outcomes and lineage-aware hooks. "
            "Do not extend the keyword stand-in into the final GM.</p>"
        )
        + "<p>Review expectations are authored synthetic judgments, not an independent rules "
        "certification. Environments here are narrative framing and GM test facts; no "
        "physical-location or environmental-damage automation is certified.</p>"
        f"<p>Immediate action completion leaves {followups} cases with separate required "
        "follow-ups. Inspect their native outcome records.</p>"
        "<details><summary>Source and complete summary</summary><pre>"
        + escape(json.dumps(summary, indent=2))
        + "</pre></details>"
        "<table><tr><th>Case</th><th>Play / environment</th><th>Native total</th>"
        "<th>GM result</th><th>Review</th></tr>"
    ]
    for row in rows:
        case = row["case"]
        html.append(
            f"<tr class='{'bad' if row['status'] == 'poorly_grounded_ruling' else ''}'>"
            f"<td><a href='#{case['id']}'>{escape(case['id'])}</a></td>"
            f"<td>{escape(TITLES[case['play']])}<br>{escape(case['environment'])}</td>"
            f"<td>{row['native'].get('total', 'no roll')}</td>"
            f"<td>{escape(row['gm_verdict'])}</td><td>{escape(row['status'])}</td></tr>"
        )
    html.append("</table>")
    for row in rows:
        case = row["case"]
        html.append(
            f"<article id='{case['id']}'><h2>{escape(case['id'])}</h2>"
            f"<p><b>Goal:</b> {escape(case['goal'])}</p>"
            f"<p><b>Review criterion:</b> {escape(case['hypothesis'])}</p>"
            "<details><summary>Complete sanitized case/result</summary><pre>"
            + escape(json.dumps(row, indent=2))
            + "</pre></details></article>"
        )
    (output / "index.html").write_text("\n".join(html) + "</html>\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        action="store_true",
        help="Exercise structured v2 frames and provider validation",
    )
    args = parser.parse_args()
    cases = json.loads((ROOT / "tools/fixtures/director_ruling_audit.json").read_text())["cases"]
    output = (
        ROOT / "var" / ("director-protocol-audit" if args.protocol else "director-ruling-audit")
    )
    output.mkdir(parents=True, exist_ok=True)
    paths = [
        "src/girlframe/ai/adjudication.py",
        "src/girlframe/services/director_adjudication.py",
        "src/girlframe/services/director_conversation.py",
        "src/girlframe/services/m2_game.py",
        "src/girlframe/services/m2_choices.py",
        "tools/fixtures/director_ruling_audit.json",
    ]
    if args.protocol:
        paths.extend(
            [
                "src/girlframe/ai/gm_protocol.py",
                "src/girlframe/ai/play_names.py",
                "src/girlframe/ai/conversation.py",
                "src/girlframe/services/director_native.py",
                "src/girlframe/services/gm_adapter.py",
                "tools/gm_protocol_fixture.py",
                "tools/fixtures/director_gm_frames.json",
                "tools/audit_director_rulings.py",
            ]
        )
    rows = []
    for case in cases:
        try:
            row = run_case(case, protocol=args.protocol)
        except Exception as error:
            row = {
                "case": case,
                "gm_verdict": "experiment_error",
                "status": "unexpected_error",
                "error_type": type(error).__name__,
                "native": {},
            }
            (output / (case["id"] + ".error.txt")).write_text(str(error) + "\n")
        rows.append(row)
        (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(case["id"], row["status"], flush=True)
    summary = {
        "protocol": 2 if args.protocol else 1,
        "judgment_setup": "Explicit facilitator frames and fixture provider; "
        "no autonomous language comprehension"
        if args.protocol
        else "Legacy keyword stand-in",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "attempts": len(rows),
        "native_complete": sum(x.get("native_complete", False) for x in rows),
        "native_rolls": sum(x.get("dice_calls", 0) for x in rows),
        "statuses": dict(Counter(x["status"] for x in rows)),
        "by_play": dict(Counter(x["case"]["play"] for x in rows)),
        "external_tokens": 0,
        "external_cost": 0,
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    render(rows, output, summary)
    print(json.dumps(summary, indent=2))
    print("Readable audit:", output / "index.html")
    return int(any(x["status"] == "unexpected_error" for x in rows))


if __name__ == "__main__":
    raise SystemExit(main())
