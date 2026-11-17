"""Four sustained synthetic scenes over the actual P2 session and native consumers."""

import argparse
import json
from collections import Counter
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from p2_trial_runtime import ROOT, Trial

SCENARIOS = (
    dict(
        id="barracks",
        title="Barracks readiness and calibration",
        fixture="handler_barracks.txt",
        keep=(41, (4, 5), "in_control", "hold the calibration needle steady"),
        second="sensors",
    ),
    dict(
        id="hallway",
        title="Hallway meeting and a cold service passage",
        fixture="p2_hallway.txt",
        keep=(41, (2, 3), "tough", "endure the cold service vent until the handover ends"),
        second="sensors",
    ),
    dict(
        id="simulation",
        title="Pilot–Handler simulated relay mission",
        fixture="handler_simulation.txt",
        keep=(
            41,
            (6, 6),
            "in_control",
            "hold the tracking needle precisely while the cockpit shakes",
        ),
        second="engage",
    ),
    dict(
        id="relay",
        title="Relay tactical exercise and shared GM outcome",
        fixture="p2_relay.txt",
        keep=None,
        second="assault",
    ),
)


class SceneTrial:
    def __init__(self, trial):
        self.trial, self.rows, self.actions, self.findings = trial, [], [], []
        self.number = 0
        self.proposals = 0
        self.review_id = None
        self.input_text = ""

    def append(self, speaker, origin, text, **extra):
        self.rows.append(
            dict(
                number=len(self.rows) + 1,
                input_number=self.number,
                speaker=speaker,
                origin=origin,
                text=text,
                **extra,
            )
        )

    def native_answer(self, owner, kind, **fields):
        from girlframe.engine.m2 import ChoiceAnswer

        game = self.trial.game
        row = next(x for x in game.choices(owner) if x["kind"] == kind)
        value, key = ChoiceAnswer(**fields), str(uuid4())
        result = game.respond(owner, key, row["id"], row["revision"], value)
        assert game.respond(owner, key, row["id"], row["revision"], value) == result
        self.append(
            "Controller",
            "fixture_owner_choice",
            f"Owner {owner.user_id} supplies {kind}.",
            action_id=row["action_id"],
            choice_id=row["id"],
        )
        return result

    def start(self, play, text, faces=(4, 5), **details):
        from test_ledger import ADMIN, OTHER, PLAYER
        from test_m2_game import state

        from girlframe.engine.m2 import PlayInput

        trial = self.trial
        trial.dice.faces = faces
        before = trial.dice.calls
        identity = trial.game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(trial.game).sheets["2"].revision,
            PlayInput(
                play=play,
                context=self.input_text or text,
                trigger_confirmed=True,
                heat=0,
                **details,
            ),
        )["action_id"]
        assert self.review_id is not None
        trial.session.bind_action(ADMIN, str(uuid4()), trial.scene, self.review_id, identity)
        assert trial.dice.calls == before
        trial.tick()
        for owner in (PLAYER, OTHER, ADMIN):
            self.native_answer(owner, "tag_window", options=("pass",))
        if any(x["kind"] == "mockingbird_risk" for x in trial.game.choices(PLAYER)):
            self.native_answer(PLAYER, "mockingbird_risk")
        receipt = trial.game.inspect(PLAYER, identity)["receipt"]
        assert trial.dice.calls == before + 1
        self.append(
            "Engine",
            "native_receipt",
            f"{play}: actual roll {receipt['faces']}.",
            action_id=identity,
            receipt_id=receipt["id"],
        )
        return identity

    def consume(self, kind, identity, decision, *, frame=None, stale=False):
        from test_ledger import ADMIN, PLAYER
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import OutcomeProposal
        from girlframe.services.onboarding import WorkflowError

        trial, service = self.trial, self.trial.session.outcomes
        request = service.open(ADMIN, str(uuid4()), trial.scene, kind, identity, frame)
        packet = service.packet(ADMIN, trial.scene, request["id"])
        proposal = OutcomeProposal(
            request_id=packet.request_id,
            decision=decision,
            cited_evidence=("source", "native"),
            private_reasoning="SYNTHETIC_SESSION_GM_PRIVATE_REASON",
        )
        before = state(trial.game).model_dump_json()
        saved = service.propose(ADMIN, str(uuid4()), trial.scene, request["id"], proposal)
        assert state(trial.game).model_dump_json() == before
        self.proposals += 1
        owner = next(v for v in trial.viewers().values() if str(v.user_id) == packet.owner_id)
        self.append(
            "GM",
            "fixture_authored_proposal",
            json.dumps(service.owner_review(owner, trial.scene, saved["id"])["decision"]),
            proposal_id=saved["id"],
            source_kind=kind,
            source_id=identity,
        )
        if stale:
            reference = next(
                x
                for x in trial.context.build(ADMIN, trial.scene).references
                if x.topic == "general"
            )
            trial.context.archive(
                ADMIN,
                str(uuid4()),
                trial.scene,
                trial.context.build(ADMIN, trial.scene).revision,
                (reference.id,),
                "Retire exercise staging note",
            )
            try:
                service.confirm(owner, str(uuid4()), trial.scene, saved["id"])
            except WorkflowError:
                pass
            else:
                raise AssertionError("Stale proposal committed")
            assert state(trial.game).model_dump_json() == before
            self.findings.append(
                "Changed reference context rejected a pending ruling; fresh proposal required."
            )
            return self.consume(kind, identity, decision, frame=frame)
        if owner != PLAYER:
            try:
                service.confirm(PLAYER, str(uuid4()), trial.scene, saved["id"])
            except WorkflowError:
                pass
            else:
                raise AssertionError("Non-owner confirmed GM outcome")
        key = str(uuid4())
        result = service.confirm(owner, key, trial.scene, saved["id"])
        assert service.confirm(owner, key, trial.scene, saved["id"]) == result
        self.append(
            "Controller",
            "native_confirmation",
            f"Owner {owner.user_id} confirms {decision.kind}.",
            proposal_id=saved["id"],
        )
        return result

    def narrate(self, identity, text):
        from test_ledger import PLAYER
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import OutcomeNarration

        self.trial.tick()
        assert self.trial.game.inspect(PLAYER, identity)["state"] == "complete"
        before = state(self.trial.game).model_dump_json()
        result = self.consume(
            "completed", identity, OutcomeNarration(text=text, effect_refs=("tier",))
        )
        self.trial.role = "gm"
        self.trial.remember(result["id"], ("handler", "lark", "kite"), "status")
        public = self.trial.session.outcomes.contribution(PLAYER, self.trial.scene, result["id"])
        assert state(self.trial.game).model_dump_json() == before
        assert "SYNTHETIC_SESSION_GM_PRIVATE_REASON" not in json.dumps(public)
        self.append(
            "GM",
            "approved_completion_readback",
            public["text"],
            action_id=identity,
            contribution_id=result["id"],
        )
        self.actions.append(identity)

    def keep(self, spec, *, stale=False):
        from test_ledger import ADMIN, PLAYER

        from girlframe.ai.gm_outcomes import KeepOutcome
        from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim

        _, faces, trait, goal = spec
        identity = self.start("keep_your_head", goal, faces)
        if faces == (6, 6):
            self.native_answer(PLAYER, "actor_keep", text="Overclocked")
        elif faces == (2, 3):
            self.native_answer(PLAYER, "actor_keep", options=("tough",))
        else:
            self.native_answer(
                PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",)
            )
        row = next(
            x
            for x in self.trial.session.work(ADMIN, self.trial.scene, gm=True)["outcome_sources"]
            if x["operation"] == "keep"
        )
        with self.trial.store.engine.connect() as c:
            result = self.trial.game.action(c, identity)["data"]["result"]
        sufficient = trait in result["positive"]
        assert sufficient or trait in result["negative"]
        frame = TaskFrame(
            stakes=goal,
            demands=(Demand(id="goal", question="Does the chosen response meet this goal?"),),
        )
        decision = KeepOutcome(
            verdict="enough" if sufficient else "not_enough",
            assessments=(
                Assessment(
                    demand_id="goal",
                    sufficient=sufficient,
                    evidence_ids=("traits", "source", "native"),
                    traits=(TraitClaim(trait=trait, polarity="are" if sufficient else "are_not"),),
                    private_reason="Fixture facilitator interprets the trait against this goal.",
                ),
            ),
            narration="The pilot maintains the stated goal."
            if sufficient
            else "The pilot cannot maintain the stated precision.",
        )
        self.consume("choice", row["source_id"], decision, frame=frame, stale=stale)
        self.narrate(identity, decision.narration)
        return sufficient

    def sensors(self):
        from test_ledger import ADMIN, PLAYER

        from girlframe.ai.gm_outcomes import SensorAnswers

        identity = self.start("check_sensors", "Inspect the accessible approach in this exercise.")
        self.native_answer(
            PLAYER, "actor_sensors", options=("foundation_destination", "foundation_avoid")
        )
        row = next(x for x in self.trial.game.choices(ADMIN) if x["kind"] == "handler_sensors")
        self.consume(
            "choice",
            row["id"],
            SensorAnswers(
                answers={
                    "a1": "No further Foundation destination is established in this briefing.",
                    "a2": "Scope prohibits forced entry; personal disclosures remain voluntary.",
                }
            ),
        )
        self.narrate(
            identity,
            "The scan answers the two selected questions; an unstated destination remains unknown.",
        )

    def engage(self):
        from test_ledger import PLAYER
        from test_m2_game import state

        from girlframe.engine.m3_actor_bonds import current_ref

        identity = self.start(
            "engage",
            "Pin the actual training opponent and advance.",
            target_actor=current_ref(state(self.trial.game), 3),
        )
        asset = next(x for x in state(self.trial.game).sheets["2"].assets if not x.damaged)
        self.native_answer(
            PLAYER,
            "engage_maneuvers",
            options=("pin", "advance"),
            fields={"pin": asset.id, "advance": asset.id},
            text="The selected Asset pins the training opponent while the pilot advances.",
        )
        self.narrate(
            identity,
            "The committed maneuvers pin the training opponent and advance the pilot.",
        )

    def assault(self):
        from test_ledger import ADMIN, PLAYER
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import BattleFacts, HandlerOutcome, TableOutcome
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_battle_state import Declaration
        from girlframe.engine.m3_handler_play_state import Effect
        from girlframe.services.m3_battle import BattleService
        from girlframe.services.m3_handler_plays import HandlerPlayService

        trial = self.trial
        battle = BattleService(trial.store)
        preview = battle.preview(PLAYER, 900)
        actor = next(x for x in preview["actors"] if x["ref"]["entity"] == "2")
        target = next(x for x in preview["actors"] if x["ref"]["entity"] == "3")
        declaration = Declaration.model_validate_json(
            json.dumps(
                dict(
                    play="all_out_assault",
                    actor=actor["ref"],
                    target=target["ref"],
                    attacking_asset=actor["assets"][0]["id"],
                    target_asset=target["assets"][0]["id"],
                    actor_sha256=actor["sha256"],
                    target_sha256=target["sha256"],
                    account="Actual training opponent within the established opening and reach",
                )
            )
        )
        offered = battle.propose(PLAYER, str(uuid4()), preview["revision"], 900, declaration)
        self.consume(
            "battle",
            offered["id"],
            BattleFacts(
                opening=True,
                reach=True,
                evidence="Fixture GM establishes opening and reach for this training target.",
            ),
        )
        identity = self.start(
            "all_out_assault",
            declaration.account,
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=offered["id"],
            piloting=True,
        )
        row = next(x for x in trial.game.choices(ADMIN) if x["kind"] == "battle_gm_table")
        self.consume(
            "choice",
            row["id"],
            TableOutcome(
                vast_advantage=False,
                account="The GM establishes no overwhelming advantage here.",
            ),
        )
        assert next(
            x for x in state(trial.game).sheets["3"].assets if x.id == declaration.target_asset
        ).damaged
        self.narrate(
            identity,
            "The assault damages the declared opposing Asset after the GM ruling.",
        )
        trial.tick()
        grant = HandlerPlayService(trial.store).start(
            ADMIN, str(uuid4()), state(trial.game).revision, (current_ref(state(trial.game), 2),)
        )
        self.consume(
            "handler_grant",
            grant["id"],
            HandlerOutcome(
                play="escalate",
                effect=Effect(
                    kind="escalate",
                    detail="An established training signal approaches the relay.",
                    stakes="The observation window is closing.",
                    account="The original Handler adds this bounded exercise complication.",
                ),
            ),
        )

    def run(self, scenario):
        from test_ledger import ADMIN, PLAYER
        from test_m2_game import state

        trial = self.trial
        lines = (ROOT / "tools" / "fixtures" / scenario["fixture"]).read_text().splitlines()
        assert len(lines) == 100 and all(lines)
        if scenario["keep"]:
            lines[scenario["keep"][0] - 1] = (
                "GM, I call Keep Your Head to " + scenario["keep"][3] + "."
            )
        second = scenario["second"]
        index = 41 if second == "assault" else 71
        lines[index - 1] = {
            "sensors": "GM, I choose Check Sensors to inspect the accessible approach.",
            "engage": "GM, I choose Engage to pin the training opponent and advance.",
            "assault": "GM, I choose All Out Assault against the declared training opponent.",
        }[second]
        self.trial.role = "handler"
        seed = trial.message(
            "The exercise staging note marks an empty bench beside the shared display.", route=False
        )
        trial.role = "gm"
        trial.remember(seed["source_id"], ("lark", "kite", "handler"))
        handler_decisions, gm_visible, verdict = Counter(), 0, None
        for number, text in enumerate(lines, 1):
            self.number = number
            trial.role = "lark" if number % 2 else "kite"
            before = state(trial.game).model_dump_json()
            result = trial.message(text)
            assert trial.retry() == result
            assert state(trial.game).model_dump_json() == before
            conversation = result["conversation"]
            self.review_id = conversation["gm"].get("play_review_id")
            self.input_text = text
            self.append(
                trial.role.title(), "scripted_player", text, source_id=result["input"]["source_id"]
            )
            decision = conversation["handler_decision"]["decision"]
            handler_decisions[decision["action"]] += 1
            gm = conversation["gm"]["reply"]
            if gm["gm_decision"]["action"] == "RESPOND":
                gm_visible += 1
                self.append(
                    "GM", "engine_conversation", gm["text"], reason=gm["gm_decision"]["reason"]
                )
            if conversation["handler"]:
                self.append(
                    "Handler",
                    "engine_gated_handler",
                    conversation["handler"]["reply"]["text"],
                    reason=decision["reason"],
                )
            if self.review_id and number not in (41, index):
                review = trial.session.reviews.gm(ADMIN, trial.scene, self.review_id)
                trial.session.reviews.review(
                    ADMIN,
                    str(uuid4()),
                    trial.scene,
                    self.review_id,
                    review["fingerprint"],
                    review["candidates"][0]["play_id"],
                    "needs_clarification",
                    "Fixture GM retains this options question for clarification.",
                )
            if scenario["keep"] and number == scenario["keep"][0]:
                verdict = self.keep(scenario["keep"], stale=scenario["id"] == "barracks")
            if number == index:
                getattr(self, second)()
            if number == 50:
                trial.restart_services()
                self.findings.append(
                    "Reopen retained native work, scoped references and warning memory."
                )
            if number == 90:
                trial.store.safety(
                    PLAYER, str(uuid4()), trial.store.status(PLAYER)["revision"], pause=True
                )
                try:
                    trial.session.work(ADMIN, trial.scene, gm=True)
                except Exception as error:
                    from girlframe.services.onboarding import WorkflowError

                    assert isinstance(error, WorkflowError)
                else:
                    raise AssertionError("Paused session exposed optional work")
                trial.store.safety(
                    PLAYER, str(uuid4()), trial.store.status(PLAYER)["revision"], pause=False
                )
            trial.clock.now += 5
        work = trial.session.work(ADMIN, trial.scene, gm=True)
        assert not work["native"]["choices"] and not work["native"]["required_work"]
        assert not work["native"]["handler_grants"]
        assert not work["outcome_sources"], (scenario["id"], work["outcome_sources"])
        assert sum(x["status"] == "native_complete" for x in work["declarations"]) == len(
            self.actions
        )
        own = trial.session.contributions(PLAYER, trial.scene)
        assert len(own) == len(self.actions)
        assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in json.dumps(self.rows)
        assert "SYNTHETIC_SESSION_GM_PRIVATE_REASON" not in json.dumps(self.rows)
        assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in json.dumps(own)
        with trial.store.engine.connect() as c:
            request, _ = trial.session.conversation._requests(
                c, trial.viewer, trial.scene, trial.last_message["source_id"], "gm"
            )
        assert len(request.scene_inputs) == 100 and request.scene_inputs_omitted > 0
        assert any(x.classification == "approved_outcome" for x in request.context.references)
        assert trial.dice.calls == len(self.actions)
        return {
            "id": scenario["id"],
            "title": scenario["title"],
            "player_inputs": 100,
            "handler_decisions": dict(handler_decisions),
            "visible_gm_turns": gm_visible,
            "native_plays": len(self.actions),
            "dice_rolls": trial.dice.calls,
            "gm_proposals": self.proposals,
            "keep_enough": verdict,
            "pending_native_work": 0,
            "declaration_statuses": dict(Counter(x["status"] for x in work["declarations"])),
            "raw_history_omitted": request.scene_inputs_omitted,
            "retained_references": len(request.context.references),
            "findings": self.findings,
            "rows": self.rows,
            "external_tokens": 0,
            "external_cost": 0,
        }


def render(results, output):
    output.mkdir(parents=True, exist_ok=True)
    links, transcripts = [], []
    for result in results:
        name = result["id"]
        (output / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
        body = "".join(
            f'<article class="{escape(row["origin"])}"><b>{row["number"]}. '
            f"{escape(row['speaker'])} · input {row['input_number']} · {escape(row['origin'])}</b>"
            f"<p>{escape(row['text'])}</p></article>"
            for row in result["rows"]
        )
        (output / (name + ".html")).write_text(
            '<!doctype html><meta charset="utf-8"><title>'
            + escape(result["title"])
            + "</title><style>body{max-width:960px;margin:2rem auto;font:16px system-ui;"
            "background:#171c24;color:#e5eaf1}article{padding:12px;margin:12px 0;"
            "border-left:4px solid #68798c;background:#222c38}p{white-space:pre-wrap}"
            ".engine_gated_handler{border-color:#50c6b4}.fixture_authored_proposal,"
            ".approved_completion_readback,.engine_conversation{border-color:#9c9df5}"
            ".fixture_owner_choice,.native_confirmation{border-color:#ddbd72}</style><h1>"
            + escape(result["title"])
            + "</h1><p>Synthetic player input; engine-gated Handler. "
            "GM rulings are explicit fixture interpretations validated by native consumers. "
            "No real model, travel or deployment.</p>" + body
        )
        links.append(f'<li><a href="{name}.html">{escape(result["title"])}</a></li>')
        transcripts.append(
            result["title"]
            + "\n"
            + "\n".join(
                f"{r['number']}. [{r['speaker']}; {r['origin']}; "
                f"input {r['input_number']}] {r['text']}"
                for r in result["rows"]
            )
        )
    (output / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>P2 session trials</title>'
        "<h1>Four synthetic 100-input sessions</h1><ul>" + "".join(links) + "</ul>"
    )
    (output / "transcripts.txt").write_text("\n\n".join(transcripts) + "\n")
    summary = [{k: v for k, v in x.items() if k != "rows"} for x in results]
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=[x["id"] for x in SCENARIOS])
    parser.add_argument("--output", type=Path, default=ROOT / "var" / "p2-session-trials")
    args = parser.parse_args()
    results = []
    for scenario in SCENARIOS:
        if args.case and scenario["id"] != args.case:
            continue
        with TemporaryDirectory(prefix="harpy-p2-session-") as directory:
            trial = Trial(Path(directory) / "campaign", create=True)
            try:
                results.append(SceneTrial(trial).run(scenario))
                print("Completed", scenario["id"], flush=True)
                render(results, args.output)
            finally:
                trial.close()
    print(json.dumps(render(results, args.output), indent=2))
    print("Readable synthetic transcripts:", args.output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
