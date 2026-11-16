"""Two disposable 100-input scenes: engine-selected Handler replies, no model calls."""

import argparse
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

SCENARIOS = (
    {
        "id": "barracks",
        "title": "Barracks readiness and a hallway conversation",
        "brief": {
            "objective": "Discuss personal equipment readiness and record concerns each Pilot "
            "chooses to raise before a voluntary simulation.",
            "scope": "Administrative readiness discussion only; no deployment, locker search "
            "or compelled medical disclosure is authorised.",
            "status": "No deployment order has been issued. This is a readiness conversation, "
            "not mission acceptance.",
        },
    },
    {
        "id": "simulation",
        "title": "Pilot–Handler simulated relay mission and debrief",
        "brief": {
            "objective": "Observe the simulated relay beacon, record external conditions and "
            "report established observations. No findings have yet been resolved.",
            "scope": "Simulation observation only. Remain outside the sealed relay; forced "
            "entry is not authorised. Risky action requires actual GM/engine adjudication.",
            "status": "Simulated planning only; no real mission has been accepted and no "
            "mission outcome has been resolved.",
        },
    },
)


def run_scene(scenario, output, *, plays=False):
    import pytest
    from test_director_conversation import GMProbe, HandlerProbe
    from test_director_observation import observed, send
    from test_ledger import ADMIN, OTHER, PLAYER, ledger
    from test_m2_game import state

    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_conversation import DirectorConversationService

    suffix = "_plays" if plays else ""
    lines = (
        (ROOT / "tools" / "fixtures" / f"handler_{scenario['id']}{suffix}.txt")
        .read_text()
        .splitlines()
    )
    assert len(lines) == 100 and all(lines)
    with TemporaryDirectory(prefix="harpy-handler-trial-") as directory:
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
                canonical = state(game)
                canonical.facts.append(
                    {"kind": "synthetic_gm_only", "body": "SYNTHETIC_LONG_SCENE_GM_CANARY"}
                )
                game.event(c, ADMIN.user_id, "gm-seed", "synthetic.gm_seed", canonical)
            for order, (topic, text) in enumerate(scenario["brief"].items()):
                _, source = send(observer, scene, f"seed:{order}", text=text, viewer=ADMIN)
                context.record(
                    ADMIN,
                    f"reference:{order}",
                    scene,
                    source.source_id,
                    order,
                    known_by=actors,
                    topic=topic,
                )
            _, private = send(
                observer,
                scene,
                "pilot-private-seed",
                viewer=PLAYER,
                text="SYNTHETIC_LONG_SCENE_PC_CANARY",
            )
            context.record(
                ADMIN, "pilot-private-reference", scene, private.source_id, 3, known_by=(actors[1],)
            )
            clock.now += 120
            seed_batch = observer.claim_review(scene)
            assert seed_batch is not None
            observer.acknowledge_review(seed_batch.run_id, seed_batch.lease_token, success=True)
            before = state(game).model_dump_json()
            gm, handler = GMProbe(), HandlerProbe()
            service = DirectorConversationService(context, gm=gm, handler=handler)
            chat, decisions, gm_diagnostics, interventions = [], [], [], []
            play_records = []
            for number, text in enumerate(lines, start=1):
                viewer = PLAYER if number % 2 else OTHER
                speaker = "Lark" if viewer == PLAYER else "Kite"
                _, source = send(observer, scene, f"message:{number}", viewer=viewer, text=text)
                # No address selector, expected response, quota, or scripted Handler line.
                before_message = state(game).model_dump_json()
                bundle = service.process_message(
                    viewer, f"process:{number}", scene, source.source_id, 1
                )
                assert state(game).model_dump_json() == before_message
                decision = bundle["handler_decision"]["decision"]
                chat.append(
                    {
                        "number": len(chat) + 1,
                        "speaker": speaker,
                        "origin": "scripted_player",
                        "input_number": number,
                        "text": text,
                    }
                )
                trigger_chat_number = len(chat)

                def append(
                    speaker,
                    origin,
                    reason,
                    text,
                    *,
                    input_number=number,
                    trigger_number=trigger_chat_number,
                    **extra,
                ):
                    chat.append(
                        {
                            "number": len(chat) + 1,
                            "speaker": speaker,
                            "origin": origin,
                            "input_number": input_number,
                            "trigger_chat_number": trigger_number,
                            "reason": reason,
                            "text": text,
                            "source_refs": [],
                            "disposition": "workflow",
                            **extra,
                        }
                    )

                if plays and bundle["gm"]["reply"]["gm_decision"]["action"] == "RESPOND":
                    gm_reply = bundle["gm"]["reply"]
                    append(
                        "GM",
                        "engine",
                        gm_reply["gm_decision"]["reason"],
                        gm_reply["text"],
                        source_refs=gm_reply["source_refs"],
                        disposition=gm_reply["disposition"],
                    )
                decisions.append(
                    {"input_number": number, "chat_number": trigger_chat_number, **decision}
                )
                gm_diagnostics.append({"input_number": number, "reply": bundle["gm"]["reply"]})
                if bundle["handler"]:
                    assert decision["action"] == "RESPOND"
                    reply = bundle["handler"]["reply"]
                    entry = {
                        "number": len(chat) + 1,
                        "speaker": "Handler",
                        "origin": "engine",
                        "input_number": number,
                        "trigger_chat_number": trigger_chat_number,
                        "reason": decision["reason"],
                        "reply_id": bundle["handler"]["id"],
                        **reply,
                    }
                    chat.append(entry)
                    interventions.append(entry)
                else:
                    assert decision["action"] == "WAIT"
                calls = len(gm.requests) + len(handler.requests)
                assert (
                    service.process_message(viewer, f"process:{number}", scene, source.source_id, 1)
                    == bundle
                )
                assert len(gm.requests) + len(handler.requests) == calls
                if plays and bundle["gm"]["reply"]["gm_decision"]["reason"] == "play_request":
                    from director_play_trial import resolve_keep_trial

                    play_records.append(
                        resolve_keep_trial(
                            service,
                            game,
                            worker,
                            gateway,
                            dice,
                            viewer,
                            scene,
                            number,
                            len(play_records),
                            append,
                            source_id=source.source_id,
                            source_revision=source.source_revision,
                            narration=text,
                        )
                    )
                clock.now += 1
            assert len(gm.requests) == 100 and len(handler.requests) == len(interventions)
            assert all("SYNTHETIC_LONG_SCENE_GM_CANARY" in x.model_dump_json() for x in gm.requests)
            assert all(
                "SYNTHETIC_LONG_SCENE_GM_CANARY" not in x.model_dump_json()
                for x in handler.requests
            )
            assert all(
                "SYNTHETIC_LONG_SCENE_PC_CANARY" not in x.model_dump_json()
                for x in handler.requests
            )
            assert "SYNTHETIC_LONG_SCENE_GM_CANARY" not in json.dumps(chat)
            assert "SYNTHETIC_LONG_SCENE_PC_CANARY" not in json.dumps(interventions)
            assert gm.requests[-1].scene_inputs_omitted == 4 + len(play_records)
            assert len(gm.requests[-1].scene_inputs) == 100
            assert "SYNTHETIC_PRIVATE_REQUIRED_HANDLER_OUTCOME" not in json.dumps(chat)
            assert all(
                "SYNTHETIC_PRIVATE_REQUIRED_HANDLER_OUTCOME" not in x.model_dump_json()
                for x in handler.requests
            )
            if plays:
                assert {x["proof"]["tier"] for x in play_records} == {"low", "mid", "high"}
                assert dice.calls == len(play_records) == 3
                assert state(game).model_dump_json() != before
            else:
                assert state(game).model_dump_json() == before and dice.calls == 0
            assert observer.status(PLAYER, scene).pending_messages == 0
            summary = {
                "id": scenario["id"],
                "title": scenario["title"],
                "player_messages": 100,
                "visible_messages": len(chat),
                "engine_handler_replies": len(interventions),
                "wait_decisions": sum(x["action"] == "WAIT" for x in decisions),
                "reasons": dict(Counter(x["reason"] for x in interventions)),
                "dispositions": dict(Counter(x["disposition"] for x in interventions)),
                "intervention_chat_numbers": [x["number"] for x in interventions],
                "trigger_input_numbers": [x["input_number"] for x in interventions],
                "gm_reviews": len(gm.requests),
                "gm_history_omitted_at_end": gm.requests[-1].scene_inputs_omitted,
                "external_tokens": 0,
                "external_cost": 0,
                "dice_calls": dice.calls,
                "mechanical_state_unchanged": not plays,
                "native_plays_completed": len(play_records),
                "gm_ruling_verdicts": dict(
                    Counter(x["adjudication"]["verdict"] for x in play_records)
                ),
                "gm_interventions": sum(
                    x["origin"] == "engine" and x["speaker"] == "GM" for x in chat
                ),
                "required_handler_rulings": sum(
                    x.get("reason") == "required_handler_ruling" for x in chat
                ),
                "private_canaries_separated": True,
                "retry_did_not_regenerate": True,
                "pending_inputs": 0,
            }
            result = {
                "summary": summary,
                "background": scenario["brief"],
                "chat": chat,
                "decisions": decisions,
                "gm_diagnostics": gm_diagnostics,
                "plays": play_records,
            }
            (output / f"{scenario['id']}.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        finally:
            fixture.close()
            patch.undo()


def render(results, output, commit):
    has_plays = any(result.get("plays") for result in results)
    title = "Two long scenes: GM, Handler and actual Plays" if has_plays else "Long Handler scenes"
    html = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        f"<title>{title}</title><style>"
        "body{max-width:960px;margin:35px auto;padding:0 20px;background:#f7f5f0;"
        "color:#242424;font:17px/1.6 system-ui}article{padding:10px 16px;margin:8px 0}"
        ".handler{background:#e0edf2;border-left:5px solid #37627c}"
        ".gm{background:#e3e8fb;border-left:5px solid #435d9b}"
        ".workflow{background:#e8e8e8;border-left:5px solid #777}"
        ".choice{background:#fff0d3;border-left:5px solid #987638}"
        "small{display:block;color:#45555e}table{border-collapse:collapse;width:100%}"
        "td,th{padding:8px;text-align:left;border:1px solid #bbb}a{color:#285974}"
        f"</style><h1>{title}</h1>"
        "<p>100 scripted Pilot messages per disposable scene, plus engine-selected "
        "interventions. No response quota, paid inference or live publication. "
        "Routine private GM reviews are not visible interventions.</p>"
        "<p>Blue: GM. Teal: optional Handler speech, generated only after RESPOND. "
        "Grey: actual engine workflow. Gold: explicitly scripted owner choices, "
        "including required Handler adjudication. These are not AI-chosen player decisions.</p>"
        "<p>Both role policies are deterministic and bounded. No general narrative "
        "intelligence is claimed. Prose and setting changes alone commit no actions.</p>"
        f"<p>Engine base: {escape(commit)}. "
        "Fixtures seed role-known background before dialogue.</p>",
    ]
    text = [
        title.upper(),
        "100 scripted Pilot messages per scene; engine-selected GM/Handler interventions.",
        "Workflow choices are explicitly scripted owner inputs. External tokens/cost: 0.",
        "",
    ]
    for result in results:
        summary = result["summary"]
        html.append(
            f"<section><h2>{escape(summary['title'])}</h2>"
            f"<p>{summary['player_messages']} Pilot messages; "
            f"{summary['engine_handler_replies']} Handler replies; "
            f"{summary['wait_decisions']} Handler WAIT decisions. "
            f"{summary.get('gm_interventions', 0)} visible GM interventions; "
            f"{summary.get('native_plays_completed', 0)} actual native Plays; "
            f"{summary.get('required_handler_rulings', 0)} required Handler owner rulings.</p>"
            "<h3>Intervention index</h3><table><tr><th>Chat message</th>"
            "<th>Player input</th><th>Role</th><th>Reason</th><th>Result</th></tr>"
        )
        for entry in (
            x
            for x in result["chat"]
            if x["origin"] == "engine" or x.get("reason") == "required_handler_ruling"
        ):
            role = entry["speaker"] + (
                " (test owner)" if entry["origin"] == "scripted_choice" else ""
            )
            html.append(
                f"<tr><td><a href='#{summary['id']}-{entry['number']}'>"
                f"#{entry['number']}</a></td><td>#{entry['input_number']}</td>"
                f"<td>{escape(role)}</td><td>{escape(entry['reason'])}</td>"
                f"<td>{escape(entry['disposition'])}</td></tr>"
            )
        html.append(
            "</table><details><summary>Seeded role-known briefing</summary><ul>"
            + "".join(f"<li>{escape(v)}</li>" for v in result["background"].values())
            + "</ul></details>"
        )
        if result.get("plays"):
            html.append(
                "<h3>Actual native Keep Your Head receipts</h3><table><tr>"
                "<th>Dice</th><th>Total / tier</th><th>GM ruling on stated goal</th>"
                "<th>Receipt</th></tr>"
            )
            for play in result["plays"]:
                proof = play["proof"]
                verdict = play.get("adjudication", {}).get("verdict", "not assessed")
                html.append(
                    f"<tr><td>{escape(str(proof['faces']))}</td>"
                    f"<td>{proof['total']} / {escape(proof['tier'])}</td>"
                    f"<td>{escape(verdict)}</td>"
                    f"<td>{escape(proof['receipt_id'])}</td></tr>"
                )
            html.append(
                "</table><p>All three actual Plays use Heat=0. Each consumes one "
                "deterministic test roll and changes only the disposable campaign. "
                "The high-tier Pilot chooses a real test Tag. The GM assesses the actual "
                "traits against the declared goal before the Handler controller confirms. "
                "Neither verdict nor confirmation is chosen from the tier alone. "
                "This bounded local judgment covers supported precision/endurance situations; "
                "unclear situations ask for clarification and other Plays need "
                "their own adapters.</p>"
            )
        text.extend([summary["title"], json.dumps(summary), ""])
        for entry in result["chat"]:
            origin = entry["origin"]
            if origin == "engine":
                label = "ENGINE " + entry["speaker"].upper() + " INTERVENTION"
                style = "gm" if entry["speaker"] == "GM" else "handler"
            elif origin == "engine_workflow":
                label, style = "ENGINE PLAY WORKFLOW", "workflow"
            elif origin == "scripted_choice":
                label, style = entry["speaker"] + " (explicit test-owner choice)", "choice"
            else:
                label, style = entry["speaker"] + " (scripted)", "player"
            note = (
                (
                    f"Trigger: chat #{entry['trigger_chat_number']}, player input "
                    f"#{entry['input_number']}. Reason: {entry['reason']}. "
                    f"Result: {entry['disposition']}."
                )
                if origin != "scripted_player"
                else ""
            )
            html.append(
                f"<article id='{summary['id']}-{entry['number']}' "
                f"class='{style}'>"
                f"<b>#{entry['number']} {escape(label)}</b>"
                f"<small>{escape(note)}</small><p>{escape(entry['text'])}</p>"
                + (
                    "<small>Sources: " + escape(", ".join(entry["source_refs"])) + "</small>"
                    if entry.get("source_refs")
                    else ""
                )
                + "</article>"
            )
            text.extend(
                [f"#{entry['number']:03d} {label}: {entry['text']}", note]
                if note
                else [f"#{entry['number']:03d} {label}: {entry['text']}"]
            )
        html.append("</section>")
    (output / "index.html").write_text("\n".join(html) + "</html>\n")
    (output / "transcripts.txt").write_text("\n".join(text) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plays", action="store_true", help="Include actual native Keep workflows")
    args = parser.parse_args()
    output = ROOT / "var" / ("gm-handler-play-scenes" if args.plays else "handler-long-scenes")
    output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    results = [run_scene(scenario, output, plays=args.plays) for scenario in SCENARIOS]
    render(results, output, commit)
    (output / "summary.json").write_text(
        json.dumps([x["summary"] for x in results], indent=2) + "\n"
    )
    for result in results:
        print(json.dumps(result["summary"]))
    print(f"Readable transcript: {output / 'index.html'}")


if __name__ == "__main__":
    main()
