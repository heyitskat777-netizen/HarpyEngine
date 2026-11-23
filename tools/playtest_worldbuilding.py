"""Reviewed fixture worldbuilding inside the persistent 112-input Director rehearsal.

Run with ``.venv/bin/python tools/playtest_worldbuilding.py --directory var/NAME``.
The directory must be new. All judgments and replies are handwritten fixtures;
no model provider, live campaign, Activity installation or external spending runs.
"""

import argparse
import json
from pathlib import Path

from p2_trial_runtime import Trial
from playtest_connected_director import (
    BARRACKS,
    ConnectedTrial,
    NaturalFixtureHandler,
    private_json,
)

DETAIL = "The maintenance archive contains a public index of drill recordings."
DETAIL_QUESTION = "Handler, what does the maintenance archive contain?"
SCHEDULE_COMPLICATION = (
    "Two maintenance schedules disagree; which one applies remains an unanswered question."
)
SCHEDULE_KEEP = (
    "GM, I declare Keep Your Head to compare the conflicting maintenance schedules "
    "methodically without rushing."
)
SCHEDULE_NARRATION = (
    "The pilot compares the conflicting maintenance schedules methodically without rushing. "
    "Which schedule applies remains unresolved."
)
NPC_GOAL = (
    "PRIVATE_NPC_AGENDA: Ilex wants to compare the procurement ledgers "
    "before discussing their contents."
)
REVISED_NPC_GOAL = (
    "PRIVATE_NPC_AGENDA: Ilex wants to identify unanswered archive questions "
    "before asking to inspect the procurement ledgers."
)
FACTION_GOAL = (
    "PRIVATE_FACTION_AGENDA: the Copper Bureau wants to present its own "
    "maintenance proposal before its competitors do."
)
PRIVATE_MARKERS = ("PRIVATE_NPC_AGENDA", "PRIVATE_FACTION_AGENDA")


def native_counts(trial):
    import sqlalchemy as sa

    from girlframe.database import tables as t

    with trial.store.engine.connect() as c:
        return {
            kind: c.scalar(
                sa.select(sa.func.count())
                .select_from(t.events)
                .where(t.events.c.campaign_id == trial.store.campaign_id, t.events.c.kind == kind)
            )
            for kind in (
                "m3.npc_introduced",
                "m3.faction_introduced",
                "m3.world_development_recorded",
            )
        }


class WorldFixtureHandler:
    """Request-only specialization; it cannot read world canon or private GM packets."""

    def __init__(self, audit):
        self.audit = audit
        self.fallback = NaturalFixtureHandler()

    def respond(self, request):
        from girlframe.ai.conversation import ConversationReply
        from girlframe.ai.knowledge import fact_text

        self.audit(request, generated=True)
        if "maintenance archive" not in request.question.casefold():
            return self.fallback.respond(request)
        references = tuple(
            reference
            for reference in request.context.references
            if reference.classification == "established_world" and fact_text(reference) == DETAIL
        )
        if not references:
            return ConversationReply(
                route="handler",
                disposition="clarification",
                text="I have no established archive contents to repeat. Ask for that information.",
                provider="reviewed-handler-v1",
            )
        return ConversationReply(
            route="handler",
            disposition="answer",
            text=DETAIL + " This index grants no new access or permission to force entry.",
            source_refs=(references[0].id,),
            provider="reviewed-handler-v1",
        )


class WorldbuildingTrial(ConnectedTrial):
    def __init__(self, trial):
        from girlframe.services.director_conversation import DirectorConversationService
        from girlframe.services.director_session import DirectorSessionService

        super().__init__(trial)
        self.world_commits, self.world_replays, self.world_disclosures = {}, [], []
        self.world_blind, self.world_prompt_checks, self.generated_prompt_checks = [], [], []
        self.install = lambda: DirectorSessionService(
            trial.context,
            conversation=DirectorConversationService(
                trial.context,
                handler=WorldFixtureHandler(self.audit),
                handler_mode="reviewed",
            ),
        )
        trial.session = self.install()

    def audit(self, request, *, generated=False):
        encoded = request.model_dump_json()
        assert all(marker not in encoded for marker in PRIVATE_MARKERS)
        assert "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY" not in encoded
        for name in ("npc_goal", "faction_goal", "npc_goal_revision"):
            commit = self.world_commits.get(name)
            if commit:
                assert commit["native"]["id"] not in encoded
        destination = self.generated_prompt_checks if generated else self.world_prompt_checks
        destination.append(
            {"input_number": self.number, "request": request.model_dump(mode="json")}
        )

    def acquire(self, source, text):
        super().acquire(source, text)
        trial = self.trial
        event = next(x for x in reversed(self.events) if x["kind"] == "player_input")
        viewer = trial.viewers()[event["fixture_persona"]]
        with trial.store.engine.connect() as c:
            request, _ = trial.session.conversation._requests(
                c, viewer, trial.scene, source, "handler"
            )
        self.audit(request)

    def commit(self, source, name, action):
        from test_m2_game import state

        from girlframe.ai.worldbuilding import WorldbuildingProposal

        trial, gm = self.trial, self.trial.viewers()["gm"]
        service, key = trial.session.worldbuilding, "world-fixture:" + name
        before, before_dice = state(trial.game), trial.dice.calls
        with trial.store.engine.connect() as c:
            assert not trial.game.pending_actions(c)
        opened = service.open(gm, key + ":open", trial.scene, source)
        packet = service.packet(gm, trial.scene, opened["id"])
        if self.number in (1, 3, 7):
            self.world_blind.append(
                {"sample_id": f"world-{self.number:03}", "packet": packet.model_dump(mode="json")}
            )
            # Export before any fixture proposal or expected response exists.
            private_json(
                trial.directory / "worldbuilding-blind.json", {"packets": self.world_blind}
            )
        proposed = WorldbuildingProposal(
            request_id=packet.request_id,
            action=action,
            cited_evidence=("source", "native"),
            private_reasoning="Handwritten fixture world interpretation: ordinary maintenance "
            "background, private NPC/faction intentions and unresolved questions only. "
            "No automatic mechanical effect, player reaction or time advance.",
        )
        saved = service.propose(gm, key + ":propose", trial.scene, opened["id"], proposed)
        assert not proposed.action.model_dump().get("effects")
        service.review(
            gm,
            key + ":review",
            trial.scene,
            saved["id"],
            "approve",
            "Fixture GM reviews current subjects, continuity, NPC authority and prose limits; "
            "all added canon remains undisclosed until an exact recipient-scoped disclosure.",
        )
        owner = next(v for v in trial.viewers().values() if str(v.user_id) == packet.owner_id)
        result = service.confirm(owner, key + ":confirm", trial.scene, saved["id"])
        assert service.confirm(owner, key + ":confirm", trial.scene, saved["id"]) == result
        self.world_commits[name] = result
        self.world_replays.append(
            {"key": key + ":confirm", "proposal_id": saved["id"], "result": result}
        )
        after = state(trial.game)
        assert after.model_dump(exclude={"revision", "facts", "world"}) == before.model_dump(
            exclude={"revision", "facts", "world"}
        )
        assert after.world.model_dump(exclude={"npcs", "factions"}) == before.world.model_dump(
            exclude={"npcs", "factions"}
        )
        if action.kind == "development":
            assert after.world == before.world
        assert trial.dice.calls == before_dice
        self.log(
            "reviewed_world_canon_commit",
            name=name,
            fixture_action=action.model_dump(mode="json"),
            proposal_id=saved["id"],
            result=result,
            original_native_owner=packet.owner_id,
            disclosure="none",
        )

    def establish(self, source):
        from girlframe.ai.worldbuilding import DevelopmentAction, FactionAction, NpcAction
        from girlframe.engine.m3_world_development import DevelopmentDraft, Subject
        from girlframe.engine.m3_world_state import Faction, Npc

        action, name = None, None
        if self.number == 1:
            name, action = (
                "npc",
                NpcAction(
                    npc=Npc(
                        id="world-fixture-ilex",
                        name="Ilex",
                        jobs=("mechanic",),
                        detail="A contracted mechanic who keeps careful maintenance notes.",
                        controller=self.trial.viewers()["handler"].user_id,
                        cell=(0, 0),
                    )
                ),
            )
        elif self.number == 2:
            name, action = (
                "faction",
                FactionAction(
                    faction=Faction(
                        id="world-fixture-copper-bureau",
                        name="Copper Bureau",
                        kind="foundation",
                        cells=((0, 0),),
                        leader="world-fixture-ilex",
                        description="An ordinary maintenance contracting organisation.",
                    )
                ),
            )
        plans = {
            3: (
                "npc_goal",
                "npc.archive-goal",
                "goal",
                "npc",
                "world-fixture-ilex",
                "Ilex's private agenda",
                NPC_GOAL,
            ),
            4: (
                "faction_goal",
                "faction.contract-goal",
                "goal",
                "faction",
                "world-fixture-copper-bureau",
                "The Bureau's private agenda",
                FACTION_GOAL,
            ),
            5: (
                "detail",
                "base.archive-detail",
                "detail",
                "location",
                "base0",
                "The maintenance archive",
                DETAIL,
            ),
            7: (
                "complication",
                "base.schedule-question",
                "complication",
                "location",
                "base0",
                "Conflicting maintenance schedules",
                SCHEDULE_COMPLICATION,
            ),
            8: (
                "npc_goal_revision",
                "npc.archive-goal",
                "goal",
                "npc",
                "world-fixture-ilex",
                "Ilex's revised private agenda",
                REVISED_NPC_GOAL,
            ),
        }
        if self.number in plans:
            name, key, kind, subject_kind, subject_id, title, text = plans[self.number]
            action = DevelopmentAction(
                development=DevelopmentDraft(
                    key=key,
                    kind=kind,
                    subject=Subject(kind=subject_kind, id=subject_id),
                    title=title,
                    text=text,
                    supersedes=self.world_commits["npc_goal"]["native"]["id"]
                    if self.number == 8
                    else None,
                )
            )
        if action is not None:
            self.commit(source, name, action)

    def disclose_detail(self, roles):
        trial, gm = self.trial, self.trial.viewers()["gm"]
        recipients = tuple(self.actors[role] for role in roles)
        key = "world-disclose:" + ":".join(roles)
        commit = self.world_commits["detail"]["id"]
        result = trial.session.worldbuilding.disclose(
            gm, key, trial.scene, commit, DETAIL, recipients, topic="general"
        )
        self.world_disclosures.append(
            {
                "key": key,
                "commit_id": commit,
                "quote": DETAIL,
                "recipients": [actor.model_dump(mode="json") for actor in recipients],
                "result": result,
            }
        )
        expected = {"handler"} | set(roles)
        for role in ("handler", "lark", "kite"):
            context = trial.context.build(
                trial.viewers()[role], trial.scene, actor=self.actors[role]
            )
            encoded = context.model_dump_json()
            assert (DETAIL in encoded) == (role in expected)
            assert all(marker not in encoded for marker in PRIVATE_MARKERS)
        self.log(
            "exact_world_detail_disclosure",
            recipient_roles=list(roles),
            quote=DETAIL,
            reference_ids=result["reference_ids"],
            other_world_goals="private",
        )

    def disclose_complication(self):
        trial, gm = self.trial, self.trial.viewers()["gm"]
        key = "world-disclose:schedule-complication:lark"
        commit = self.world_commits["complication"]["id"]
        recipients = (self.actors["lark"],)
        result = trial.session.worldbuilding.disclose(
            gm, key, trial.scene, commit, SCHEDULE_COMPLICATION, recipients, topic="general"
        )
        self.schedule_reference = result["reference_ids"][0]
        self.world_disclosures.append(
            {
                "key": key,
                "commit_id": commit,
                "quote": SCHEDULE_COMPLICATION,
                "recipients": [actor.model_dump(mode="json") for actor in recipients],
                "result": result,
            }
        )
        for role in ("handler", "lark", "kite"):
            context = trial.context.build(
                trial.viewers()[role], trial.scene, actor=self.actors[role]
            )
            assert (SCHEDULE_COMPLICATION in context.model_dump_json()) == (role == "lark")
        self.log(
            "exact_world_complication_disclosure",
            recipient_roles=["lark"],
            quote=SCHEDULE_COMPLICATION,
            reference_ids=result["reference_ids"],
            native_outcome="unresolved",
        )

    def input(self, text, role, segment):
        # One quiet line becomes an explicit question about the new setting detail.
        if text == BARRACKS[10]:
            text = DETAIL_QUESTION
        elif text == BARRACKS[20]:
            text = SCHEDULE_KEEP
        route = super().input(text, role, segment)
        event = next(x for x in reversed(self.events) if x["kind"] == "player_input")
        self.establish(event["source_id"])
        if self.number == 9:
            self.disclose_detail(("handler",))
        elif self.number == 10:
            self.disclose_detail(("lark",))
        elif self.number == 12:
            self.disclose_complication()
        if text == DETAIL_QUESTION:
            assert route["handler_decision"]["decision"]["action"] == "RESPOND"
            reply = next(x for x in reversed(self.events) if x["kind"] == "handler_intervention")
            assert DETAIL in reply["reply"]["text"]
            assert reply["reply"]["source_refs"]
        return route

    def play(self, play, text, route, *, other=False):
        if text != BARRACKS[20]:
            return super().play(play, text, route, other=other)
        assert play == "keep_your_head" and not other
        self.schedule_keep(route)

    def schedule_keep(self, route):
        """Use actual new-world evidence for a bounded comparison, not a truth ruling."""
        from test_m2_game import state

        from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeNarration
        from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
        from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
        from girlframe.engine.m2 import PlayInput

        trial = self.trial
        gm, pilot, kite = (trial.viewers()[role] for role in ("gm", "lark", "kite"))
        key = f"connected:{self.number}:native"
        trial.dice.faces = (4, 5)
        before = trial.dice.calls
        revision = state(trial.game).sheets["2"].revision
        value = PlayInput(
            play="keep_your_head", context=SCHEDULE_KEEP, trigger_confirmed=True, heat=0
        )
        started = trial.game.begin(pilot, key, 900, revision, value)
        assert trial.game.begin(pilot, key, 900, revision, value) == started
        native = started["action_id"]
        trial.session.bind_action(
            gm, key + ":bind", trial.scene, route["gm"]["play_review_id"], native
        )
        assert trial.dice.calls == before
        trial.tick()
        for owner in (pilot, kite, gm):
            self.answer(owner, "tag_window", options=("pass",))
        if any(choice["kind"] == "mockingbird_risk" for choice in trial.game.choices(pilot)):
            self.answer(pilot, "mockingbird_risk")
        self.answer(pilot, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        choice = next(
            choice for choice in trial.game.choices(gm) if choice["kind"] == "handler_keep"
        )
        world_evidence = "reference:" + self.schedule_reference
        opened = trial.session.outcomes.open(
            gm,
            key + ":open",
            trial.scene,
            "choice",
            choice["id"],
            TaskFrame(
                stakes=SCHEDULE_KEEP,
                demands=(
                    Demand(
                        id="methodical_comparison",
                        question="Can the pilot compare these conflicting records methodically "
                        "without establishing which schedule applies?",
                    ),
                ),
                response_scope="self",
            ),
        )
        packet = trial.session.outcomes.packet(gm, trial.scene, opened["id"])
        assert packet.native["action"]["data"]["prepared"]["context"] == SCHEDULE_KEEP
        evidence = next(item for item in packet.evidence if item.id == world_evidence)
        assert SCHEDULE_COMPLICATION in json.dumps(evidence.value)
        self.proposal(
            opened,
            KeepOutcome(
                verdict="enough",
                narration=SCHEDULE_NARRATION,
                assessments=(
                    Assessment(
                        demand_id="methodical_comparison",
                        sufficient=True,
                        evidence_ids=("traits", "source", "native", world_evidence),
                        traits=(TraitClaim(trait="in_control", polarity="are"),),
                        private_reason="Actual control supports careful comparison of the "
                        "disclosed conflicting records. This does not establish either schedule "
                        "as correct or resolve the underlying complication.",
                    ),
                ),
            ),
            extra=(world_evidence,),
        )
        trial.tick()
        inspected = trial.game.inspect(pilot, native)
        assert inspected["state"] == "complete"
        opened = trial.session.outcomes.open(
            gm, key + ":readback", trial.scene, "completed", native
        )
        readback = self.proposal(
            opened, OutcomeNarration(text=SCHEDULE_NARRATION, effect_refs=("tier",))
        )
        request = trial.session.knowledge.open(gm, key + ":learn", trial.scene, readback["id"])
        saved = trial.session.knowledge.propose(
            gm,
            key + ":learn-propose",
            trial.scene,
            request["id"],
            KnowledgeProposal(
                request_id=request["id"],
                updates=(
                    Acquisition(
                        basis="outcome",
                        quote=SCHEDULE_NARRATION,
                        recipients=tuple(self.actors.values()),
                        topic="status",
                    ),
                ),
                private_reasoning="Original native owner approved this methodical comparison "
                "readback; schedule applicability remains unresolved.",
            ),
        )
        trial.session.knowledge.confirm(gm, key + ":learn-confirm", trial.scene, saved["id"])
        assert trial.dice.calls == before + 1
        event = next(item for item in reversed(self.events) if item["kind"] == "player_input")
        with trial.store.engine.connect() as c:
            assert trial.observer._latest_source(c, event["source_id"]).text == SCHEDULE_KEEP
        self.actions.append(native)
        self.log(
            "world_complication_motivated_native_play",
            source_id=event["source_id"],
            action_id=native,
            context=SCHEDULE_KEEP,
            cited_world_reference=world_evidence,
            approved_narration=SCHEDULE_NARRATION,
            complication="still_unresolved",
        )
        self.log(
            "native_play_complete",
            action_id=native,
            play="keep_your_head",
            receipt=inspected["receipt"],
            result=inspected["result"],
        )
        trial.save()

    def run(self):
        from test_m2_game import state

        from girlframe.engine.m3_world_development import current, records

        summary = super().run()
        trial = self.trial
        history = records(state(trial.game))
        goals = tuple(record for record in history if record.key == "npc.archive-goal")
        assert len(history) == 5 and len(current(state(trial.game))) == 4
        assert len(goals) == 2 and goals[0].text == NPC_GOAL
        assert goals[1].text == REVISED_NPC_GOAL and goals[1].supersedes == goals[0].id
        complication = next(
            record
            for record in current(state(trial.game))
            if record.key == "base.schedule-question"
        )
        assert complication.text == SCHEDULE_COMPLICATION and complication.supersedes is None
        assert (
            sum(
                event["kind"] == "world_complication_motivated_native_play" for event in self.events
            )
            == 1
        )
        assert len(self.world_prompt_checks) == 112
        assert len(self.world_commits) == len(self.world_replays) == 7
        assert summary["native_plays"] == summary["dice_rolls"] == 3
        assert summary["target_controller_handoffs"] == 1
        assert not summary["pending_native_choices"]
        before, before_counts = state(trial.game).model_dump_json(), native_counts(trial)
        for saved in self.world_replays:
            assert (
                trial.session.worldbuilding.confirm(
                    trial.viewers()["handler"], saved["key"], trial.scene, saved["proposal_id"]
                )
                == saved["result"]
            )
        assert (
            state(trial.game).model_dump_json() == before and native_counts(trial) == before_counts
        )
        summary.update(
            worldbuilding_native_commits=7,
            introduced_npcs=1,
            introduced_factions=1,
            development_history_records=5,
            active_developments=4,
            selected_world_disclosures=len(self.world_disclosures),
            world_complication_motivated_native_plays=1,
            schedule_applicability="unresolved",
            world_handler_prompts_checked=len(self.world_prompt_checks),
            world_generated_handler_prompts_checked=len(self.generated_prompt_checks),
            blind_world_packets=len(self.world_blind),
            private_agendas_in_handler_prompts=0,
            world_writes_on_service_replay=0,
            native_world_event_counts=before_counts,
            fixture_changes="One quiet barracks line asks about the disclosed archive detail; "
            "the first Keep attempts methodical comparison of the new schedule complication.",
        )
        private_json(trial.directory / "worldbuilding-summary.json", summary)
        private_json(
            trial.directory / "worldbuilding-results.json",
            {"summary": summary, "events": self.events},
        )
        private_json(
            trial.directory / "worldbuilding-prompts.json",
            {
                "all_input_projections": self.world_prompt_checks,
                "actual_generation_requests": self.generated_prompt_checks,
            },
        )
        private_json(
            trial.directory / "worldbuilding-replay.json",
            {"confirmations": self.world_replays, "disclosures": self.world_disclosures},
        )
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, required=True, help="New synthetic trial directory"
    )
    args = parser.parse_args()
    trial = Trial(args.directory, create=True)
    try:
        # Explicit approval belongs only to this disposable synthetic fixture.
        approval = trial.store.policy.m3_approval
        trial.store.policy = trial.store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world"}}
                )
            }
        )
        trial.save()
        summary = WorldbuildingTrial(trial).run()
    finally:
        trial.close()
    replay = Trial(args.directory)
    try:
        from test_m2_game import state

        from girlframe.engine.m3_actor_state import ActorRef

        saved = json.loads((replay.directory / "worldbuilding-replay.json").read_text())
        before, before_counts = state(replay.game).model_dump_json(), native_counts(replay)
        before_dice = replay.dice.calls
        for item in saved["confirmations"]:
            assert (
                replay.session.worldbuilding.confirm(
                    replay.viewers()["handler"], item["key"], replay.scene, item["proposal_id"]
                )
                == item["result"]
            )
        for item in saved["disclosures"]:
            assert (
                replay.session.worldbuilding.disclose(
                    replay.viewers()["gm"],
                    item["key"],
                    replay.scene,
                    item["commit_id"],
                    item["quote"],
                    tuple(ActorRef.model_validate_json(json.dumps(x)) for x in item["recipients"]),
                    topic="general",
                )
                == item["result"]
            )
        assert state(replay.game).model_dump_json() == before
        assert native_counts(replay) == before_counts and replay.dice.calls == before_dice
        summary["world_writes_on_database_reopen_replay"] = 0
        summary["rerolls_on_database_reopen_replay"] = 0
        private_json(replay.directory / "worldbuilding-summary.json", summary)
        results = json.loads((replay.directory / "worldbuilding-results.json").read_text())
        results["summary"] = summary
        private_json(replay.directory / "worldbuilding-results.json", results)
        print(json.dumps(summary, indent=2))
    finally:
        replay.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
