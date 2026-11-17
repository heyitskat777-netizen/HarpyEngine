"""Fresh persistent living-campaign rehearsal; handwritten fixtures, no model/live calls.

Run with .venv/bin/python tools/playtest_living_campaign.py --directory var/NEW.
This agency rehearsal uses112player inputs and preserves native sheets/dice.
The separate worldbuilding rehearsal supplies native Play evidence. NPC replies
remain explicitly reviewed private candidates; no frontend delivery is invented.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from p2_trial_runtime import Trial
from playtest_connected_director import HALLWAY, LABELS, SEGMENTS, ConnectedTrial, private_json

GOAL = "PRIVATE_NPC_GOAL_CANARY: Compare the archive ledgers before promising access."
SITUATION = "Two archive appointment lists disagree; the applicable list remains unverified."
PRIVATE = ("PRIVATE_GM_DOSSIER_CANARY", "PRIVATE_FRONT_GROUP_CANARY", "PRIVATE_FRONT_HYPOTHESIS")
NPC_SELF = "PRIVATE_NPC_SELF_CANARY"
PC_SELF = "PRIVATE_PC_SELF_CANARY"


class LivingTrial(ConnectedTrial):
    def __init__(self, trial):
        from girlframe.services.director_dossiers import DirectorDossierService
        from girlframe.services.director_fronts import DirectorFrontService
        from girlframe.services.director_reactions import DirectorReactionService

        super().__init__(trial)
        self.dossiers, self.fronts = (
            DirectorDossierService(trial.context),
            DirectorFrontService(trial.context),
        )
        self.reactions = DirectorReactionService(trial.context)
        self.reaction_rows, self.role_checks, self.replay_rows = [], [], []
        self.front_drafts, self.front_heads = {}, {}
        self.seed()

    def world(self, name, action, source):
        from girlframe.ai.worldbuilding import WorldbuildingProposal

        trial, gm = self.trial, self.trial.viewers()["gm"]
        service = trial.session.worldbuilding
        opened = service.open(gm, name + ":open", trial.scene, source)
        draft = service.propose(
            gm,
            name + ":propose",
            trial.scene,
            opened["id"],
            WorldbuildingProposal(
                request_id=opened["id"],
                action=action,
                cited_evidence=("source", "native"),
                private_reasoning="Bounded synthetic fixture canon; no mechanical effects.",
            ),
        )
        service.review(
            gm,
            name + ":review",
            trial.scene,
            draft["id"],
            "approve",
            "Actual native subjects and narrative scope reviewed.",
        )
        return service.confirm(gm, name + ":confirm", trial.scene, draft["id"])

    def seed(self):
        from test_m2_game import state

        from girlframe.ai.director_dossiers import (
            DossierPerspective,
            DossierProfile,
            DossierState,
            Personnel,
        )
        from girlframe.ai.director_fronts import (
            FrontClock,
            FrontDraft,
            FrontEvidence,
            FrontHypothesis,
            FrontParticipant,
        )
        from girlframe.ai.worldbuilding import DevelopmentAction, NpcAction
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_world_development import DevelopmentDraft, Subject
        from girlframe.engine.m3_world_state import Npc
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_cast import CastService
        from girlframe.services.m3_missions import MissionService

        trial, gm = self.trial, self.trial.viewers()["gm"]
        trial.message(
            "GM, establish an ordinary archive clerk and its working context.",
            role="handler",
            route=False,
            command_key="living-setup-source",
        )
        source = trial.last_message["source_id"]
        self.world(
            "living-npc",
            NpcAction(
                npc=Npc(
                    id="living-clerk",
                    name="Maren",
                    jobs=("mechanic",),
                    detail="An ordinary archive clerk with patient manners.",
                    controller=gm.user_id,
                    cell=(0, 0),
                )
            ),
            source,
        )
        self.npc = ActorRef(kind="npc", entity="living-clerk")
        cast = CastService(ActorService(MissionService(trial.store)))
        for actor in (self.npc, self.actors["handler"]):
            view = cast.view(gm, 900)
            cast.change(
                gm,
                "living-cast:" + actor.token,
                900,
                view["game_revision"],
                view["cast_revision"],
                "join",
                actor,
            )
        self.goal = self.world(
            "living-goal",
            DevelopmentAction(
                development=DevelopmentDraft(
                    key="living.archive-goal",
                    kind="goal",
                    subject=Subject(kind="npc", id=self.npc.entity),
                    title="Clerk's private objective",
                    text=GOAL,
                )
            ),
            source,
        )
        situation = self.world(
            "living-situation",
            DevelopmentAction(
                development=DevelopmentDraft(
                    key="living.appointment-question",
                    kind="complication",
                    subject=Subject(kind="location", id="base0"),
                    title="Conflicting appointment lists",
                    text=SITUATION,
                )
            ),
            source,
        )
        self.goal_disclosure = trial.session.worldbuilding.disclose(
            gm,
            "living-goal-disclose",
            trial.scene,
            self.goal["id"],
            GOAL,
            (self.npc,),
            topic="general",
        )
        self.situation_disclosure = trial.session.worldbuilding.disclose(
            gm,
            "living-situation-disclose",
            trial.scene,
            situation["id"],
            SITUATION,
            (self.npc, self.actors["handler"], self.actors["lark"]),
            topic="general",
        )
        self.npc_profile = DossierProfile(
            presence="background",
            background="An archive clerk introduced in this fixture.",
            voice="Careful and patient; " + NPC_SELF,
            behavior="Weighs requests before answering.",
            values=("Keep promises",),
            fears=("Premature promises",),
            contradictions=("Welcomes company but guards private work",),
            reaction_tendencies=(
                "Refuse private disclosure",
                "Offer a public alternative",
                "Defer a conversation",
            ),
            limits=("No involuntary personal disclosure",),
        )
        self.npc_state = DossierState(
            objective_ref=self.goal["native"]["id"],
            pressures=(DossierPerspective(text="I feel cautious about agreeing too quickly."),),
            promises=(DossierPerspective(text="I may offer only public material for now."),),
            beliefs=(
                DossierPerspective(
                    text="I should compare the ledgers before promising access.",
                    knowledge_refs=tuple(self.goal_disclosure["reference_ids"]),
                ),
            ),
            obligations=(DossierPerspective(text="I intend to keep my own archive commitments."),),
            experiences=(
                DossierPerspective(text="I remember being careful about uncertain lists."),
            ),
            resource_refs=tuple(self.situation_disclosure["reference_ids"]),
        )
        proposal = self.dossiers.propose(
            gm,
            "living-npc-dossier",
            trial.scene,
            self.npc,
            0,
            self.npc_profile,
            self.npc_state,
            Personnel(public_summary="Archive clerk", mannerisms="Checks a small notebook"),
        )
        result = self.dossiers.confirm(
            gm, "living-npc-dossier-confirm", trial.scene, proposal["id"]
        )
        self.replay_rows.append((gm, "living-npc-dossier-confirm", proposal["id"], result))
        self.dossiers.gm_notes(gm, "living-private-note", trial.scene, self.npc, 0, PRIVATE[0])
        pc = self.dossiers.propose(
            trial.viewers()["lark"],
            "living-pc-dossier",
            trial.scene,
            self.actors["lark"],
            0,
            DossierProfile(voice=PC_SELF, values=("Choose my own response",)),
            DossierState(
                beliefs=(DossierPerspective(text="I decide whether to accept an invitation."),)
            ),
            Personnel(),
        )
        pc_result = self.dossiers.confirm(
            trial.viewers()["lark"], "living-pc-confirm", trial.scene, pc["id"]
        )
        self.replay_rows.append((trial.viewers()["lark"], "living-pc-confirm", pc["id"], pc_result))
        evidence = FrontEvidence(kind="world_development", id=situation["native"]["id"])
        goal = FrontEvidence(kind="world_development", id=self.goal["native"]["id"])
        for key in ("aversion", "redirection", "quiet-deferral"):
            draft = FrontDraft(
                key="living." + key,
                title="PRIVATE_FRONT_GROUP_CANARY:" + key,
                situation="A possible disagreement needs review; no automatic consequence.",
                fact_refs=(evidence,),
                participants=(
                    FrontParticipant(
                        subject=Subject(kind="npc", id=self.npc.entity), objective_refs=(goal,)
                    ),
                ),
                hypotheses=(
                    FrontHypothesis(
                        id="uncertain",
                        text="PRIVATE_FRONT_HYPOTHESIS: the lists may cause a disagreement.",
                        support_refs=(evidence,),
                    ),
                ),
                clock=FrontClock(limit=2),
                deadline_tick=3 if key == "quiet-deferral" else None,
            )
            saved = self.fronts.save(
                gm, "living-front:" + key, trial.scene, state(trial.game).revision, draft
            )
            self.front_drafts[key], self.front_heads[key] = draft, saved["id"]
        self.baseline = state(trial.game).model_dump(mode="json", exclude={"facts", "revision"})
        self.start_dice = trial.dice.calls
        trial.save()

    def audit(self, source):
        trial, gm = self.trial, self.trial.viewers()["gm"]
        with trial.store.engine.connect() as c:
            npc = self.dossiers._role_packet(c, trial.scene, self.npc).model_dump(mode="json")
            handler = self.dossiers._role_packet(c, trial.scene, self.actors["handler"]).model_dump(
                mode="json"
            )
            pilot = self.dossiers._role_packet(c, trial.scene, self.actors["lark"]).model_dump(
                mode="json"
            )
            npc_front = self.fronts._actor_view(c, trial.scene, self.npc)
            handler_front = self.fronts._actor_view(c, trial.scene, self.actors["handler"])
        for packet in (npc, handler, pilot, npc_front, handler_front):
            assert all(marker not in json.dumps(packet) for marker in PRIVATE)
        assert NPC_SELF in json.dumps(npc) and NPC_SELF not in json.dumps(handler)
        assert GOAL in json.dumps(npc) and GOAL not in json.dumps(handler)
        assert PC_SELF not in json.dumps(npc) and PC_SELF not in json.dumps(handler)
        if self.named.get("hidden"):
            assert self.named["hidden"] not in json.dumps(npc)
            assert "a cobalt crawler under the stairwell" not in json.dumps(npc)
        self.role_checks.append(
            {
                "input_number": self.number,
                "npc": npc,
                "handler": handler,
                "npc_front": npc_front,
                "handler_front": handler_front,
            }
        )
        assert not self.dossiers.pending(gm, trial.scene, gm=True)

    def react(self, source, kind, text):
        from girlframe.ai.director_reactions import ReactionProposal

        trial, gm = self.trial, self.trial.viewers()["gm"]
        key = f"living-reaction:{self.number}"
        opened = self.reactions.open(gm, key + ":open", trial.scene, self.npc, source)
        packet = self.reactions.packet(gm, trial.scene, opened["id"])
        assert all(marker not in json.dumps(packet) for marker in PRIVATE)
        assert PC_SELF not in json.dumps(packet)
        proposal = ReactionProposal(
            request_id=opened["id"],
            kind=kind,
            text=text,
            cited_references=tuple(self.situation_disclosure["reference_ids"])
            if kind != "WAIT"
            else (),
            rationale="Fixture interpretation of actual self state and known speech; no effects.",
        )
        saved = self.reactions.propose(gm, key + ":propose", trial.scene, opened["id"], proposal)
        review = self.reactions.owner_review(gm, trial.scene, saved["id"])
        assert "rationale" not in review["proposal"]
        approved = self.reactions.review(
            gm,
            key + ":review",
            trial.scene,
            saved["id"],
            "approve",
            "Actual NPC controller approves this voluntary private candidate.",
        )
        assert (
            self.reactions.review(
                gm,
                key + ":review",
                trial.scene,
                saved["id"],
                "approve",
                "Actual NPC controller approves this voluntary private candidate.",
            )
            == approved
        )
        self.reaction_rows.append(
            {
                "input_number": self.number,
                "request": packet,
                "proposal": proposal.model_dump(mode="json"),
                "result": approved,
            }
        )
        self.log("living_reviewed_reaction", kind_selected=kind, result=approved)
        assert approved["effects_applied"] is False

    def advance(self, branch):
        from test_m2_game import state

        from girlframe.ai.director_fronts import FrontAdvance, FrontClock

        trial, gm = self.trial, self.trial.viewers()["gm"]
        clock = self.fronts.fictional_time(
            gm,
            "living-time:" + branch,
            trial.scene,
            state(trial.game).revision,
            1,
            "Explicit fixture fictional time for " + branch,
        )
        if branch != "quiet-deferral":
            draft = self.front_drafts[branch].model_copy(
                update={
                    "supersedes": self.front_heads[branch],
                    "status": "dormant" if branch == "aversion" else "active",
                    "situation": "Private refusal candidate defers demand; delivery pending."
                    if branch == "aversion"
                    else "Private compromise redirects attention; list conflict unresolved.",
                    "clock": FrontClock(mark=0 if branch == "aversion" else 1, limit=2),
                }
            )
            saved = self.fronts.save(
                gm,
                "living-branch:" + branch,
                trial.scene,
                state(trial.game).revision,
                draft,
                advance=FrontAdvance(kind="fictional_time", id=clock["id"]),
            )
            self.front_heads[branch] = saved["id"]
        else:
            assert clock["ready"]
        self.log(
            "living_branch_review",
            branch=branch,
            fictional_time=clock,
            resolution="attention_only_no_native_resolution_or_disaster",
        )

    def run(self):
        from test_m2_game import state

        from girlframe.ai.director_dossiers import DossierPerspective

        trial, gm = self.trial, self.trial.viewers()["gm"]
        turns = {
            8: (
                "REFUSE",
                "I will not share my private ledger. You may ask about the public index.",
            ),
            18: (
                "COMPROMISE",
                "I can compare public index entries with you; private ledgers remain closed.",
            ),
            40: (
                "DELAY",
                "Let us defer this conversation until the appointment list is clarified.",
            ),
            60: ("WAIT", ""),
            76: (
                "SCENE_OFFER",
                "Would you like a later conversation about the public index? You may decline.",
            ),
            90: ("WAIT", ""),
            101: (
                "DIALOGUE",
                "I am willing to discuss the public list while leaving the conflict unresolved.",
            ),
        }
        replacements = {
            8: "Would the archive clerk share a private ledger?",
            18: "Could we compare only public index entries instead?",
            21: "I compare the desk notes at my own pace without claiming a ruling.",
            40: "The archive is quiet; could we postpone this conversation?",
            60: "I give the clerk space to return to their own work.",
            69: "I inspect my own screen and leave unanswered questions open.",
            76: "Would the clerk offer an optional public-index conversation later?",
            90: "I check my own notes without asking the clerk to intervene.",
            91: "I ask the other pilot whether they want to hear my apology; they choose.",
            101: "I am ready to discuss the public list without treating a guess as a fact.",
        }
        for label, lines in zip(LABELS, SEGMENTS, strict=True):
            for index, original in enumerate(lines):
                number = self.number + 1
                text = replacements.get(number, original)
                role = "lark" if index % 2 == 0 else "kite"
                if original in (HALLWAY[4], HALLWAY[5], HALLWAY[8], HALLWAY[13], HALLWAY[15]):
                    role = "lark"
                if original == HALLWAY[9]:
                    role = "kite"
                self.input(text, role, label)
                source = next(
                    event["source_id"]
                    for event in reversed(self.events)
                    if event["kind"] == "player_input"
                )
                self.audit(source)
                if number in turns:
                    self.react(source, *turns[number])
                if number in (20, 48, 96):
                    self.advance({20: "aversion", 48: "redirection", 96: "quiet-deferral"}[number])
                if number == 80:
                    updated = self.npc_state.model_copy(
                        update={
                            "experiences": (
                                DossierPerspective(text="I prefer public alternatives."),
                            )
                        }
                    )
                    draft = self.dossiers.propose(
                        gm,
                        "living-recurring",
                        trial.scene,
                        self.npc,
                        1,
                        self.npc_profile.model_copy(update={"presence": "recurring"}),
                        updated,
                    )
                    saved = self.dossiers.confirm(
                        gm, "living-recurring-confirm", trial.scene, draft["id"]
                    )
                    self.replay_rows.append((gm, "living-recurring-confirm", draft["id"], saved))
                assert (
                    state(trial.game).model_dump(mode="json", exclude={"facts", "revision"})
                    == self.baseline
                )
                assert trial.dice.calls == self.start_dice
        assert self.number == len(self.role_checks) == 112
        before = state(trial.game).model_dump_json()
        trial.restart_services()
        from girlframe.services.director_dossiers import DirectorDossierService

        self.dossiers = DirectorDossierService(trial.context)
        trial.session = self.install()
        for controller, key, proposal, result in self.replay_rows:
            assert self.dossiers.confirm(controller, key, trial.scene, proposal) == result
        for viewer, command, result in self.replays[-3:]:
            assert trial.session.submit(viewer, trial.scene, command) == result
        assert state(trial.game).model_dump_json() == before
        assert self.dossiers.role_packet(gm, trial.scene, self.npc).dossier_version == 2
        summary = {
            "synthetic": True,
            "player_inputs": self.number,
            "fresh_native_npcs": 1,
            "explicit_native_cast_roles": [
                self.npc.model_dump(mode="json"),
                self.actors["handler"].model_dump(mode="json"),
            ],
            "dossier_actor_count": 2,
            "npc_dossier_versions": 2,
            "role_prompt_checks": len(self.role_checks),
            "private_canary_leaks": 0,
            "reaction_candidates": dict(
                Counter(row["proposal"]["kind"] for row in self.reaction_rows)
            ),
            "reaction_controller_reviews": len(self.reaction_rows),
            "front_branches": ["aversion", "redirection", "quiet-deferral"],
            "front_snapshot": self.fronts.view(gm, trial.scene),
            "native_sheets_preserved": True,
            "dice_rolls": trial.dice.calls - self.start_dice,
            "rerolls_on_replay": 0,
            "external_cost": 0,
            "external_tokens": 0,
            "limitations": [
                "Handwritten fixtures; no autonomous model or delivery benchmark.",
                "Reviewed NPC dialogue and scene invitations remain private candidates.",
                "Front updates use explicit fictional time; no native outcome is fabricated.",
                "Native Play evidence remains in the separate connected worldbuilding trial.",
            ],
        }
        private_json(
            trial.directory / "living-results.json",
            {"summary": summary, "events": self.events, "reactions": self.reaction_rows},
        )
        private_json(trial.directory / "living-role-packets.json", {"packets": self.role_checks})
        private_json(trial.directory / "living-summary.json", summary)
        trial.save()
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    trial = Trial(args.directory, create=True)
    try:
        approval = trial.store.policy.m3_approval
        trial.store.policy = trial.store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world"}}
                )
            }
        )
        summary = LivingTrial(trial).run()
    finally:
        trial.close()
    replay = Trial(args.directory)
    try:
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.services.director_dossiers import DirectorDossierService

        npc = ActorRef(kind="npc", entity="living-clerk")
        assert (
            DirectorDossierService(replay.context)
            .role_packet(replay.viewers()["gm"], replay.scene, npc)
            .dossier_version
            == 2
        )
        assert replay.dice.calls == 0
    finally:
        replay.close()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
