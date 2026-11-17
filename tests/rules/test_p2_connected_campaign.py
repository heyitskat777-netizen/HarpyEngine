"""One persisted campaign: source damage/Defeat, replacement, Keep, scene handoffs."""

import json
from pathlib import Path

import pytest
from test_defeat_replacement import destroyed
from test_director_continuity import carry, new_scene, reference, roles
from test_director_observation import observed as observed
from test_director_session import command
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick
from test_replacement_service import accept, propose, quote

from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeNarration, OutcomeProposal
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.ai.observation import ObservationPolicy
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_frame_state import Preferences
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m3_replacement import DEFEAT_ROOT, ReplacementService
from girlframe.services.onboarding import WorkflowError


def narrate(session, scene, action, key, text):
    request = session.outcomes.open(ADMIN, key + ":open", scene, "completed", action)
    packet = session.outcomes.packet(ADMIN, scene, request["id"])
    proposal = session.outcomes.propose(
        ADMIN,
        key + ":propose",
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=OutcomeNarration(text=text, effect_refs=("tier",)),
            cited_evidence=("source", "native"),
            private_reasoning="PRIVATE_CONNECTED_GM",
        ),
    )
    session.outcomes.confirm(ADMIN, key + ":confirm", scene, proposal["id"])
    return session.contributions(PLAYER, scene)[-1]


def test_connected_defeat_replacement_ruling_and_next_scene_readback(ledger):
    # This fixture executes real native source damage and a real owned Defeat roll.
    game, off_duty, replacement = destroyed(ledger)
    observer = DirectorObservationService(ledger, synthetic=True)
    with ledger.engine.connect() as c:
        first = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "trial-observe", first, 0, ObservationPolicy(mode="shadow"))
    from test_ledger import OTHER

    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, f"trial-consent:{viewer.user_id}", first, 1, consent=True)
    context = DirectorContextService(observer)
    session = DirectorSessionService(context)
    handler, pilot = roles(observer, first)
    with ledger.engine.connect() as c:
        import sqlalchemy as sa

        from girlframe.database import tables as t

        defeat = next(
            row["id"]
            for row in c.execute(sa.select(t.m2["m2_actions"])).mappings()
            if json.loads(row["body_json"]).get("play") == "defeat"
        )
    defeated = narrate(
        session,
        first,
        defeat,
        "defeat-readback",
        "The original Frame is destroyed. The Pilot chose replacement at the next Off-Duty.",
    )
    memory = context.record(
        ADMIN, "defeat-memory", first, defeated["id"], 0, known_by=(handler, pilot), topic="debrief"
    )
    private, _ = reference(context, first, "private", "PRIVATE_PILOT_RECOVERY_NOTES", (pilot,))
    first_reply = session.submit(
        PLAYER, first, command(observer, first, "report", "I report the loss.")
    )
    assert first_reply["conversation"]["handler_decision"]["decision"]["reason"] == "known_update"
    assert state(game).sheets["2"].frame_scrapped

    second = new_scene(observer)
    handoff = carry(context, first, second, (memory["id"], private), "to-workshop")
    period = off_duty.begin(ADMIN, "trial-next-period")
    original = state(game).sheets["2"]
    work = next(x for x in off_duty.missions.owned_work(PLAYER) if x["kind"] == DEFEAT_ROOT)
    assert work["off_duty_id"] == period["id"]
    current = replacement.get(ADMIN, work["id"])
    with pytest.raises(WorkflowError):
        replacement.propose(
            ADMIN,
            "no-handler-pilot-choice",
            work["id"],
            current["revision"],
            state(game).revision,
            Preferences(frame="THE ENFORCER"),
        )
    package = propose(replacement, work["id"], key="trial-propose")
    quote(replacement, package["package_id"], key="trial-quote")
    ledger.engine.dispose()
    replacement = ReplacementService(off_duty.missions)
    reviewed_install = replacement.get(PLAYER, work["id"])
    installed = accept(replacement, work["id"], key="trial-install")
    assert (
        replacement.apply(
            PLAYER,
            "trial-install",
            work["id"],
            reviewed_install["revision"],
            reviewed_install["game_revision"],
            reviewed_install["package_revision"],
        )
        == installed
    )
    restored = state(game).sheets["2"]
    assert restored.frame == "THE ENFORCER" and not restored.frame_scrapped
    assert restored.character_id == original.character_id
    assert (restored.heat, restored.permissions, restored.identities) == (
        original.heat,
        original.permissions,
        original.identities,
    )
    assert restored.frame != original.frame
    assert (
        "PRIVATE_PILOT_RECOVERY_NOTES"
        not in context.build(ADMIN, second, actor=handler).model_dump_json()
    )
    update, _ = reference(
        context,
        second,
        "installation-report",
        "The replacement Enforcer is installed. A local calibration check is next.",
        (handler, pilot),
        "tactical",
    )
    workshop = session.submit(
        PLAYER, second, command(observer, second, "workshop", "I check the new controls.")
    )
    assert workshop["conversation"]["handler"] is not None
    assert workshop["conversation"]["handler"]["reply"]["source_refs"] == [update]
    # The carried debrief was already delivered to this same roster in scene one.
    workshop_update = session.submit(
        PLAYER, second, command(observer, second, "workshop-update", "I listen.")
    )
    assert workshop_update["conversation"]["handler"] is None

    game.dice = Dice((4, 5))
    worker, gateway = GameWorker(game), Gateway()
    action = game.begin(
        PLAYER,
        "replacement-check",
        901,
        restored.revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            trigger_confirmed=True,
            context="Hold the calibration needle steadily on its mark in the replacement Frame.",
        ),
    )["action_id"]
    tick(worker, gateway)
    pass_tags(game)
    assert any(
        x["route"] == "native_owner" and x["owner_id"] == "2"
        for x in session.work(ADMIN, second, gm=True)["decision_routes"]
    )
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    source = next(
        x
        for x in session.work(ADMIN, second, gm=True)["outcome_sources"]
        if x["operation"] == "keep"
    )
    request = session.outcomes.open(
        ADMIN,
        "calibration-open",
        second,
        "choice",
        source["source_id"],
        TaskFrame(
            stakes="Keep the calibration needle on its mark.",
            demands=(Demand(id="steady", question="Can the Pilot maintain precise control?"),),
        ),
    )
    packet = session.outcomes.packet(ADMIN, second, request["id"])
    saved = session.outcomes.propose(
        ADMIN,
        "calibration-propose",
        second,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=KeepOutcome(
                verdict="enough",
                narration="The Pilot holds the calibration needle steady.",
                assessments=(
                    Assessment(
                        demand_id="steady",
                        sufficient=True,
                        evidence_ids=("source", "native", "traits"),
                        traits=(TraitClaim(trait="in_control", polarity="are"),),
                        private_reason=(
                            "Control supports precision; toughness alone would not establish it."
                        ),
                    ),
                ),
            ),
            cited_evidence=("source", "native"),
            private_reasoning="PRIVATE_CONNECTED_GM",
        ),
    )
    before = state(game).model_dump_json()
    assert game.inspect(PLAYER, action)["state"] != "complete"
    with pytest.raises(WorkflowError):
        session.outcomes.confirm(PLAYER, "not-handler-owner", second, saved["id"])
    assert state(game).model_dump_json() == before
    session.outcomes.confirm(ADMIN, "calibration-confirm", second, saved["id"])
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    readback = narrate(
        session,
        second,
        action,
        "calibration-readback",
        "The calibration check succeeds; the replacement Frame remains installed.",
    )
    assert "PRIVATE_CONNECTED_GM" not in json.dumps(readback)
    with ledger.engine.connect() as c:
        order = len(context._references(c, second))
    end_memory = context.record(
        ADMIN,
        "calibration-memory",
        second,
        readback["id"],
        order,
        known_by=(handler, pilot),
        topic="debrief",
    )
    third = new_scene(observer, 902, 901)
    ids = (
        handoff["references"][memory["id"]],
        handoff["references"][private],
        update,
        end_memory["id"],
    )
    carry(context, second, third, ids, "to-hallway")
    session = DirectorSessionService(
        DirectorContextService(DirectorObservationService(ledger, synthetic=True))
    )
    turn = session.submit(
        PLAYER, third, command(observer, third, "hallway", "Handler, what is the status?")
    )
    # Direct questions retain priority; the general status answer may ask for clarification.
    assert turn["conversation"]["handler_decision"]["decision"]["reason"] == "direct_question"
    final = session.context.build(ADMIN, third, actor=handler).model_dump_json()
    assert "calibration check succeeds" in final and "PRIVATE_PILOT_RECOVERY_NOTES" not in final
    assert "PRIVATE_CONNECTED_GM" not in final
    assert (
        off_duty.current(PLAYER)["phase"] == "preparing"
    )  # Remaining Strain/period work is explicit.
    output = Path("var/p2-connected-campaign.json")
    output.write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "external_tokens": 0,
                "external_cost": 0,
                "scenes": [first, second, third],
                "defeat_action": defeat,
                "replacement_work": work["id"],
                "frame": restored.frame,
                "calibration_action": action,
                "gm_ruling": "enough",
                "handler_responses": [
                    first_reply["conversation"]["handler"]["reply"],
                    workshop["conversation"]["handler"]["reply"],
                ],
                "remaining_work": (
                    "Off-Duty preparation/Strain; no completed period or mission is claimed."
                ),
            },
            indent=2,
        )
        + "\n"
    )
