"""Two disposable 100-input scenes: engine-selected Handler replies, no model calls."""

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


def run_scene(scenario, output):
    import pytest
    from test_director_conversation import GMProbe, HandlerProbe
    from test_director_observation import observed, send
    from test_ledger import ADMIN, OTHER, PLAYER, ledger
    from test_m2_game import state

    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_conversation import DirectorConversationService

    lines = (ROOT / "tools" / "fixtures" / f"handler_{scenario['id']}.txt").read_text().splitlines()
    assert len(lines) == 100 and all(lines)
    with TemporaryDirectory(prefix="harpy-handler-trial-") as directory:
        patch = pytest.MonkeyPatch()
        fixture = ledger.__wrapped__(Path(directory), patch)
        store = next(fixture)
        try:
            observer, scene, clock, game, _, _, dice = observed.__wrapped__(store)
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
            for number, text in enumerate(lines, start=1):
                viewer = PLAYER if number % 2 else OTHER
                speaker = "Lark" if viewer == PLAYER else "Kite"
                _, source = send(observer, scene, f"message:{number}", viewer=viewer, text=text)
                # No address selector, expected response, quota, or scripted Handler line.
                bundle = service.process_message(
                    viewer, f"process:{number}", scene, source.source_id, 1
                )
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
            assert gm.requests[-1].scene_inputs_omitted == 4
            assert len(gm.requests[-1].scene_inputs) == 100
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
                "gm_history_omitted_at_end": 4,
                "external_tokens": 0,
                "external_cost": 0,
                "dice_calls": 0,
                "mechanical_state_unchanged": True,
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
            }
            (output / f"{scenario['id']}.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        finally:
            fixture.close()
            patch.undo()


def render(results, output, commit):
    html = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Long Handler scene trials</title><style>"
        "body{max-width:960px;margin:35px auto;padding:0 20px;background:#f7f5f0;"
        "color:#242424;font:17px/1.6 system-ui}article{padding:10px 16px;margin:8px 0}"
        ".handler{background:#e0edf2;border-left:5px solid #37627c}"
        "small{display:block;color:#45555e}table{border-collapse:collapse;width:100%}"
        "td,th{padding:8px;text-align:left;border:1px solid #bbb}a{color:#285974}"
        "</style><h1>Two long scenes: engine-selected Handler interventions</h1>"
        "<p>100 scripted Pilot messages in each disposable scene, plus only the Handler "
        "replies selected by the engine. No response quota, scripted Handler dialogue, "
        "paid inference or live publication. GM processing is separate from the chat.</p>"
        "<p>The deterministic need policy responds to direct Handler questions and one "
        "supported scope contradiction. Ordinary conversation produces WAIT. This is "
        "a bounded synthetic policy, not a general narrative intelligence test. "
        "Player prose and setting changes do not commit game actions or travel.</p>"
        f"<p>Engine base: {escape(commit)}. "
        "Fixtures seed role-known background before dialogue.</p>",
    ]
    text = [
        "LONG HANDLER SCENE TRIALS",
        "100 scripted Pilot messages per scene; engine-selected replies.",
        "GM processing is separate. External tokens/cost: 0. No mechanical changes.",
        "",
    ]
    for result in results:
        summary = result["summary"]
        html.append(
            f"<section><h2>{escape(summary['title'])}</h2>"
            f"<p>{summary['player_messages']} Pilot messages; "
            f"{summary['engine_handler_replies']} Handler replies; "
            f"{summary['wait_decisions']} WAIT decisions.</p>"
            "<h3>Intervention index</h3><table><tr><th>Chat message</th>"
            "<th>Player input</th><th>Engine reason</th><th>Result</th></tr>"
        )
        for entry in (x for x in result["chat"] if x["origin"] == "engine"):
            html.append(
                f"<tr><td><a href='#{summary['id']}-{entry['number']}'>"
                f"#{entry['number']}</a></td><td>#{entry['input_number']}</td>"
                f"<td>{escape(entry['reason'])}</td><td>{escape(entry['disposition'])}</td></tr>"
            )
        html.append(
            "</table><details><summary>Seeded role-known briefing</summary><ul>"
            + "".join(f"<li>{escape(v)}</li>" for v in result["background"].values())
            + "</ul></details>"
        )
        text.extend([summary["title"], json.dumps(summary), ""])
        for entry in result["chat"]:
            engine = entry["origin"] == "engine"
            label = "ENGINE HANDLER INTERVENTION" if engine else entry["speaker"] + " (scripted)"
            note = (
                (
                    f"Trigger: chat #{entry['trigger_chat_number']}, player input "
                    f"#{entry['input_number']}. Reason: {entry['reason']}. "
                    f"Result: {entry['disposition']}."
                )
                if engine
                else ""
            )
            html.append(
                f"<article id='{summary['id']}-{entry['number']}' "
                f"class='{'handler' if engine else 'player'}'>"
                f"<b>#{entry['number']} {escape(label)}</b>"
                f"<small>{escape(note)}</small><p>{escape(entry['text'])}</p>"
                + (
                    "<small>Sources: " + escape(", ".join(entry["source_refs"])) + "</small>"
                    if engine
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
    output = ROOT / "var" / "handler-long-scenes"
    output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    results = [run_scene(scenario, output) for scenario in SCENARIOS]
    render(results, output, commit)
    (output / "summary.json").write_text(
        json.dumps([x["summary"] for x in results], indent=2) + "\n"
    )
    for result in results:
        print(json.dumps(result["summary"]))
    print(f"Readable transcript: {output / 'index.html'}")


if __name__ == "__main__":
    main()
