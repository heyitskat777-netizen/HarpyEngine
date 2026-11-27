"""Separate structured model contracts for Handler and Director tasks."""

from typing import Any, Literal

from pydantic import Field

from girlframe.ai.activity_batch import (
    ActivityBatchDecision,
    ActivityBatchPacket,
    ActivityPilotDecision,
    ActivityPilotPacket,
    PilotAudienceDecision,
)
from girlframe.ai.contracts import Contract
from girlframe.ai.conversation import (
    ConversationReply,
    HandlerNeedPacket,
    HandlerNeedProposal,
    HandlerRequest,
)
from girlframe.ai.director_dossiers import AIPilotPortrayalDraft
from girlframe.ai.director_planning import DirectorPlanningDecision, DirectorPlanningPacket
from girlframe.ai.director_reactions import ReactionProposal
from girlframe.ai.gm_outcomes import OutcomePacket, OutcomeProposal
from girlframe.ai.model_transport import OpenAIResponses
from girlframe.ai.pilot_initiative import pilot_lenses
from girlframe.ai.worldbuilding import WorldbuildingPacket, WorldbuildingProposal
from girlframe.engine.campaign_opening import PlannedAIPilot
from girlframe.engine.m3_handler_character import PlaybookProfile
from girlframe.engine.m3_handler_play_state import Play
from girlframe.engine.m3_handler_state import PERSONALITIES, HandlerNotes, Playbook
from girlframe.scenes.campaign_time import Identity


class HandlerDraft(Contract):
    disposition: Literal["answer", "clarification", "requires_engine_workflow"]
    text: str = Field(min_length=1, max_length=1200)
    source_refs: tuple[str, ...] = Field(default=(), max_length=3)
    clock_receipt: Identity | None = None
    handler_action: str | None = Field(default=None, max_length=600)
    handler_play_offer: Play | None = None
    handler_concern: str | None = Field(default=None, max_length=300)


SPEECH_HABITS: dict[Playbook, dict[str, str]] = {
    "Mistress": {
        "cadence": "Speak close and warmly. Name the small thing a Pilot did that mattered.",
        "under_pressure": (
            "Keep your voice level and your praise specific when affection gets tense."
        ),
        "tell": (
            "Make a favor sound personal and leave a real way to decline. "
            "Notice care that never made it onto the duty sheet."
        ),
    },
    "Dogrunner": {
        "cadence": "Use spare, declarative sentences. Name the duty, the lapse, and the repair.",
        "under_pressure": "Ask who actually had the job before assigning blame.",
        "tell": (
            "Say exactly what would put someone back on duty. "
            "Give credit for a repair by dropping that objection once it's dealt with."
        ),
    },
    "Scientist": {
        "cadence": "Name the observed detail first. Ask one question about what changed.",
        "under_pressure": (
            "Pin down one condition while the reading is fresh. Defer other theories."
        ),
        "tell": (
            "Say what you'd record and offer one comparison that would separate two readings. "
            "Leave the cause open until there's evidence."
        ),
    },
    "Frantic": {
        "cadence": "Think aloud in short beats. Put the immediate priority first.",
        "under_pressure": "If you correct yourself, do it once. Offer to take one competing task.",
        "tell": (
            "Say which part you can cover now. "
            "Wait for the other person's acknowledgment before treating the handoff as done."
        ),
    },
    "Insurgent": {
        "cadence": (
            "Use careful official wording on open channels. Be plainer in approved private talk."
        ),
        "under_pressure": (
            "Buy time with a narrow answer. Keep other people's confidence under their control."
        ),
        "tell": (
            "Ask what this desk actually needs to know. "
            "Offer to carry an account the Pilot can agree to share."
        ),
    },
    "Trainer": {
        "cadence": "Speak steadily. Ask for the last completed step and pause for the answer.",
        "under_pressure": "Make one next step easy to remember. Give its purpose in a few words.",
        "tell": (
            "Offer a readback or a demonstration. Acknowledge the part the Pilot already got right."
        ),
    },
    "Advocate": {
        "cadence": "Name the affected Pilot. Use short, plain clauses and leave room for a reply.",
        "under_pressure": "Set one firm boundary in a few words and give the question back.",
        "tell": (
            "Say what you'll keep on the record in your own words. "
            "Make a specific offer to carry the paperwork or hold the desk when it helps."
        ),
    },
}


def _handler_portrayal(
    data: dict[str, Any], notes: HandlerNotes | None, profile: PlaybookProfile | None
) -> dict[str, Any]:
    if notes is not None and notes.personality is not None:
        data["personality_prompt"] = PERSONALITIES[notes.personality].prompt
    if profile is not None and (habits := SPEECH_HABITS.get(profile.playbook)):
        data["speech_habits"] = habits
    return data


HANDLER_VOICE = (
    "Speak to the person in front of you. One concrete thought is usually enough. "
    "Remember the last way you said it and give the next line a new purpose. "
    "A gesture or present-tense task should add something visible or audible. "
    "Leave the action field empty for a line that already does the work. Keep future "
    "plans and offers in speech. Use exact sourced words when quoting another person. "
    "Mark a paraphrase as your own account and preserve consequential wording, such as "
    "'still unverified'. Let the person who spoke own their position and feelings. "
    "If speech_habits is present, use one fitting habit in an eligible reply. Let the "
    "Handler's personal voice and personality lead, with the playbook habits as defaults. "
    "Express the cadence through original phrasing. Act on a relevant, approved preference "
    "through how you address the Pilot or what you offer here. Keep the memory itself private. "
)

FICTION_CHOICE = (
    "If the scene presents competing viable approaches, weigh what each would cost this "
    "character and the people involved. Use a workable sequence if both goals can still be "
    "met. When the situation permits only one, settle on the cost this character is willing "
    "to accept and one concrete next move. Honor an urgent constraint shared by everyone. "
    "Even when the choice is clear, the character can change who is asked, what help is "
    "offered, or what responsibility they take. Leave other actors' decisions to them. "
)

HANDLER_FOLLOW_THROUGH = (
    "When you have an eligible opening, let the playbook's priorities change the decision "
    "you make, including what you protect, what you leave with the Pilot, and when you wait. "
    "Use the recovery habit if your first offer was refused. Respect the refusal. If there "
    "is still work to do, handle a different part within your own authority. If another "
    "Pilot already handled it, leave them the floor. Use earlier_reports to understand a "
    "callback and preserve the exact point that is disputed. Earlier reports are context "
    "only; use report_ids from reports in the current batch. State the uncertain point "
    "or ask for one missing detail instead of requesting the whole report again. "
    "When the same Pilot brings up a confirmed promise or boundary, act on the permission it "
    "requires now. A past offer or draft alone establishes no agreement or completed action. "
    + FICTION_CHOICE
    + "Let the playbook's priorities guide the choice, such as gathering evidence, fixing "
    "the handoff, or giving a Pilot the floor. For NPC_DIALOGUE on a material tradeoff, "
    "fill tradeoff.accepted_cost and tradeoff.next_move with the proposed loss and next step. "
    "Use the step in the line itself. These fields are private planning; fill them only "
    "when an actual cost informs the decision. "
)


class ModelHandler:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def respond(self, request: HandlerRequest) -> ConversationReply:
        if request.response_need is None or request.response_need.action != "RESPOND":
            raise ValueError("Use the engine-approved response need.")
        draft = self.client.generate(
            "Speak as the Handler, a person in this story with your own job and relationships. "
            "Use the sheet and the recent comms you actually heard. Talk to the person in front "
            "of you rather than reciting a policy or summarizing the whole scene. Where the "
            "approved need calls for it, volunteer one thing you can do, show a small reaction, "
            "or make and later keep a promise. Let the Pilots carry the scene. Use the "
            "playbook's voice and priorities, plus your personality_prompt if supplied, to "
            "shape how you sound and act. Show the playbook's recovery habits through what "
            "you do after a mistake. Keep portrayal notes, starting history and "
            "closed-scene experiences private. Carry forward only the named Pilot's own prior "
            "experience. A declined offer is a reason to ask or wait before offering that help "
            "again, and a completed handoff or kept promise can inform who you defer to. "
            "Use persona.state.continuity as your private memory and perspective. Let a relevant "
            "intention, commitment or relationship change shape how you respond. The entry itself "
            "does not prove a fact or give the audience access to its original evidence. "
            "Give current requests precedence and use the approved reason for this reply. "
            "Cite each required reference and only references in the "
            "current scene. Closed-scene reports are private background pending local disclosure. "
            "Use the supplied fictional clock for pacing. Cite its exact clock_receipt to state "
            "the current minute, cutoff or deadline status. Use ordinary sources for other facts. "
            "The clock never creates knowledge, a consequence or a player choice. "
            "Acknowledge uncertainty, choices or refusals, and act only for the Handler. "
            "Keep spoken text and Handler actions entirely in character. Never say mechanical "
            "terms such as Heat costs, dice, modifiers, printed Play names, or receipt IDs in "
            "the fiction. An eligible native Play belongs only in handler_play_offer for "
            "private review. You cannot resolve it or speak for another actor. Follow through "
            "only on what someone actually reported. " + FICTION_CHOICE + HANDLER_VOICE,
            _handler_portrayal(
                request.model_dump(mode="json"), request.character_notes, request.playbook_profile
            ),
            HandlerDraft,
        )
        return ConversationReply(
            route="handler", provider="reviewed-handler-v1", **draft.model_dump()
        )


class ModelActivityBatch:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def draft_pilot_portrayal(self, pilot: PlannedAIPilot) -> AIPilotPortrayalDraft:
        return self.client.generate(
            "Write private portrayal guidance for the approved AI Girl. Use one short, concrete "
            "sentence per field. Keep specific personality details and commitments from the seed. "
            "Use the Girl playbook to shape what she cares about and the Frame to shape what "
            "she notices and tries. Give her a distinct speaking rhythm, personal goal, and "
            "contradiction. Show observable habits and name what makes her speak up or wait. "
            "Leave rule outcomes, assets, rank, Bonds, and the actions of other characters "
            "to HarpyEngine and their controllers. Write possibilities, not past campaign events.",
            {
                "pilot": pilot.model_dump(mode="json"),
                "playbook_guidance": pilot_lenses(pilot.portrayal).model_dump(mode="json"),
            },
            AIPilotPortrayalDraft,
        )

    def decide(self, packet: ActivityBatchPacket) -> ActivityBatchDecision:
        return self.client.generate(
            "Review one beat in the story. The approved opening frames the place, the starting "
            "moment, and what was apparent then. Follow heard developments since it opened. "
            "An opening by itself does not call for a line. "
            "Reports are what the Handler heard, not confirmed "
            "world facts. A Play trigger is an invitation to review and may warrant silence. "
            "Read the latest relevant turns to see who has the floor, what is being decided, "
            "and what would happen if you waited. The sheet and initiative say what this "
            "Handler notices. Use character_cue and copy its cue and report_id only when your "
            "contribution helps with the current choice, a consequential ambiguity, or a "
            "personal opening the Girls leave you. For a reviewed_character_cue, copy the cue "
            "from response_need and the response_report_id even when initiative is absent. "
            "A side question can wait. A useful action "
            "can run alongside their work if it preserves something that could be lost or "
            "offers one concrete next step without stopping them. For conditional_reading, "
            "when a gauge changes as something starts, a Scientist can privately mark that "
            "timing or offer one before-and-after comparison to the reporter while another "
            "Pilot writes her own account. Keep the observation attributed and leave the "
            "comparison optional. Wait if that exact work is already covered, if it would "
            "interrupt an urgent choice, or if the Girls ask for space. Flag a material "
            "mistake once if the Pilots are about to act on it. "
            "Keep rules in the native controls and portray the situation in ordinary words. "
            "Use personality_prompt, character_setup and the Handler's own notes to make "
            "this specific to them. Choose their routine, pressured or reparative cadence "
            "and let their current drive and limits guide what they are willing to offer. "
            "An Advocate makes room for the affected Pilot. If an eligible cue shows a Pilot "
            "being cut off, address that Pilot and ask what she still wants to say. If a report "
            "form hides a distinction she is trying to make, offer one way to preserve it in "
            "her own words. Speak to the eligible listeners only. If the Pilots already made "
            "room for each other, wait and let them finish. "
            "An off_duty_personal cue can bring out a habit, an obligation, or your side of "
            "a relationship. Use notes as private perspective. Let a small gesture, a "
            "voluntary admission, or a favor you ask make you part of the room. Leave other "
            "characters to decide how they feel and whether to answer. "
            "An opportunity is a possible move you may offer when an existing need or cue "
            "makes it timely. Leave the Pilots space to accept, refuse, or propose other terms. "
            "Let the Pilots keep the floor when they are handling it or helping each other. "
            "If asked for quiet, stay silent without an acknowledgment. "
            "Copy heard reports' source_id values into report_ids. Copy approved evidence IDs "
            "from references into source_refs. Keep report IDs out of source_refs. "
            "For shared_report, put both Pilot report IDs in report_ids and the approved "
            "completion criterion's reference ID in source_refs. "
            "Give a readback when it would help the Girls proceed. Say what you heard and "
            "what remains unknown. Ask for a further check only if it affects the current "
            "decision. The completion criterion alone does not require a checklist recital. "
            "With response_need, put response_report_id in report_ids and the required "
            "reference IDs in source_refs. "
            "For NPC_DIALOGUE copy the actual intended_recipients ActorRefs from "
            "eligible_listeners. Include the addressed report's speaker. Every listener must "
            "have heard every cited report. Address only the selected listeners in the "
            "line and its action. A shared_report goes to both original speakers. "
            "For character_cue or follow_through, put only the addressed Pilot's turn ID "
            "in report_ids and name that Pilot as the sole listener. "
            "Later chat in the batch need not supersede that request. If two heard turns ask "
            "for the same answer, cite both for a shared reply. "
            "Check recent_contributions before repeating an answer, an offer, or a joke. Mark "
            "offers_help for a real offer. Use own_action for a small first-person action "
            "the Handler takes here. Use follow_through with "
            "follows_offer for one useful acknowledgment of an acceptance, refusal, or "
            "handoff you heard after making the offer. When help was accepted, a small "
            "physical next step within that permission can answer better than a second offer. "
            "Keep the gesture on your side of the permission. After permission to take the "
            "form, 'I pick up your form by one corner' plays your own action. Leave any new "
            "offer, hand movement, or other response by the Pilot for her to author. An "
            "intention to file it belongs in speech until it happens. Use follow_through for "
            "progress on an open offer when the original Girl brings you something new. Let a "
            "repeated account stand. "
            "Use a supplied scene_detail for one concrete gesture or task when it fits. "
            "Cite the detail if you use it. Don't assume access to nearby people or objects. "
            "Use the current Pilot's approved persona.experiences to remember what they "
            "previously declined or took on, or what you promised. Treat it as private "
            "background. accepted_help and its offer_text record authorized intent. "
            "Use persona.state.continuity as private character memory: let an earlier choice "
            "change an offer, hesitation, favor or ordinary conversation naturally. Keep the "
            "entries private and use only current shared references to make a factual claim. "
            "They do not establish an attempt or outcome. When an experience records "
            "declined_help, let that decision stand until the Girl opens the offer again. "
            "When response_need.reason is commitment_result, use response_need with its "
            "required source_refs. Address only the original Pilot, give the concrete "
            "facilitator-confirmed result from references, and leave the next choice free. "
            "When the result permits an extra line and leaves the original form valid, "
            "name both options plainly: write and initial the extra line, or leave it blank. "
            "When response_need.reason is planned_handler_move, the opportunity is one "
            "approved possible step toward your own goal. You can WAIT if the floor is taken. "
            "If you act, use response_need, copy the required source_refs and response_report_id, "
            "address only that speaker, and describe one small actual own_action in the present "
            "tense. A promise, offer, or claim about someone else's action leaves it pending. "
            "Use carried evidence to pick up from what actually happened. "
            "Let the Pilot's present choice lead. Leave out mechanics, private "
            "notes, other characters' choices, and unearned results. "
            "You may suggest one eligible play from play_opportunities using play_offer. "
            "For a native_signatures entry, REVIEW_HANDLER_SIGNATURE can flag the named Play "
            "privately without opening work, speaking, or taking the controller's decision. "
            "Keep its report, required references and original speaker as the sole listener. "
            "The suggestion is private. Leave the Play name, costs and resolution out of the line. "
            "Only suggest Break Down if you are actually portraying a breakdown. For Get Them "
            "Alone, ask the Girl one genuine question. A useful beat can stay fiction. "
            "Propose a development only as an unresolved possibility for facilitator review. "
            "Escalate an unsupported outcome rather than making up a rule. "
            + HANDLER_VOICE
            + HANDLER_FOLLOW_THROUGH,
            _handler_portrayal(
                packet.model_dump(
                    mode="json", exclude={"initiative": {"inspired_by", "issue", "possible_play"}}
                ),
                packet.character_notes,
                packet.playbook_profile,
            ),
            ActivityBatchDecision,
        )


PILOT_DIALOGUE_VOICE = (
    "Write the words she'd say to this listener in this moment. Pick up one specific thing "
    "they just said or left unsaid. The latest_heard_report_id locates the newest turn she "
    "heard. The selected report is the reviewed anchor. Use the surrounding turns for timing "
    "and let a newer answer or an offered pause settle an earlier point. "
    "Use her own voice, pressure response, repair habits and relationship with this listener. "
    "A fragment, a hesitant start, a short question or a quick acknowledgment can be a full "
    "turn. Give the listener an opening. A joke belongs where this character would tell it. "
    "If they already agree, acknowledge what she will do next in a few words. If they disagree, "
    "say the one thing she wants them to hear and leave their answer open. Show a shared "
    "agreement by honoring it, taking her part or using its short cue. Avoid a recap of the "
    "conversation, a list of decisions or narration of her private reasoning. "
    "When invited back after a pause, answer the specific point using nearby_reports "
    "or earlier_reports. Say which part you understood, and ask about just the unresolved "
    "part if you need to. If the point was never supplied, ask one narrow question about "
    "the current decision. Use one concrete heard or visible detail to give the reply "
    "a job. Under disagreement let her drive, stake or first approach change what she "
    "offers. If she has already heard a refusal, respect it and use a feasible fallback, "
    "ask what changed, or wait. Avoid repeating the original request in new words. "
)


class ModelActivityPilot:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def select_audience(self, packet: ActivityPilotPacket) -> PilotAudienceDecision:
        return self.client.generate(
            "Choose who this AI Girl would address before her line is drafted. Read her own "
            "pressures, obligations, memories and the heard turns. Use latest_heard_report_id "
            "to notice where the conversation has moved. Choose the person she wants something "
            "from or has something specific to say to. A pause or a peer's useful answer can "
            "close the opening for a reply. For ADDRESS copy exact recipients from audience. "
            "Each listener's source_refs are evidence they share with her. If her choice is "
            "shaped by something private, she can speak to a listener who shares it, or choose "
            "the relevant listener and leave the private reason unspoken. An answer to a "
            "received offer goes to its original speaker alone. If revise_for is citation_scope, "
            "the prior draft cited evidence its audience hadn't heard. Pick an eligible "
            "audience for a safe restatement, speak one to one, or WAIT. "
            "For ADDRESS or PRIVATE_INTENT, you may include intent for this Girl's next move. "
            "Use priority for what she's protecting. Her Girl playbook shapes what matters; "
            "her Frame draws attention to an established detail or practical cost. Her "
            "dossier brings in her own promises, obligations and relationships. Use the "
            "lens that matters here. Equipment, access, and facts come from the scene. "
            + FICTION_CHOICE
            + "When a real cost drives her choice, fill intent.tradeoff.accepted_cost with "
            "what she would accept giving up and intent.tradeoff.next_move with the next "
            "feasible thing she would ask, offer, or put up for private review. Leave tradeoff "
            "empty in an ordinary exchange. The plan is private guidance for the draft. "
            "Use an exact "
            "open or deferred pressure ID when it drives the choice. A fallback is a "
            "possibility to revisit after a reply. Use earlier_reports to read the current "
            "turn in context. After a refusal, choose a different viable tactic or WAIT. "
            "For ADDRESS, use the optional opportunity's exact ID as move_id with listeners "
            "who share its source_refs. An opportunity can be ignored or renegotiated. "
            "If it names reply_from, address that Pilot alone. A decline applies to this offer, "
            "and leaves other ways to help and the relationship open. "
            "Return WAIT when silence fits, PRIVATE_INTENT for deliberate consequential action "
            "in private review (including a fitting native_plays entry), or NEEDS_REVIEW "
            "when authority is unclear. Return the mode and applicable intent. "
            "The next step drafts the line.",
            packet.model_dump(mode="json"),
            PilotAudienceDecision,
        )

    def decide(self, packet: ActivityPilotPacket) -> ActivityPilotDecision:
        return self.client.generate(
            "Portray this one AI Girl with the priorities, approach and voice on her dossier. "
            "Use character_setup for her cadence at ease, under pressure, or when repairing trust. "
            "Her playbook suggests what matters, her Frame gives a way to think about "
            "equipment and risks, and her individual portrayal determines how she responds. "
            "An initiative points to the exact heard turn where she could step in. She can "
            "still wait. A Frame label alone proves no equipment, location or ability is "
            "available. Keep any consequential Frame use in a private SCENE_OFFER. "
            "Use the approved opening to place her in the scene. Follow heard developments "
            "since it opened. "
            "Use her own changing dossier for personal business, obligations, memories and "
            "relationship perspectives. A belief is this Girl's view. Pick a specific past "
            "moment if it changes what she wants or how she approaches someone now. "
            "Use dossier.state.continuity as private memory that can shape her tone and choices. "
            "An intention is unfinished and a remembered relationship is one-sided. Keep its "
            "private details out of speech. Cite only evidence shared with the current listeners. "
            "A remembered term records what these characters said. Let a refusal, condition, "
            "or agreement change how she deals with its counterpart. Refer to it in dialogue "
            "only when doing so serves her current purpose. When attribution or another "
            "confirmed boundary comes up with its counterpart, actually ask or honor the "
            "agreed permission before any offer to share. An offered term can still be declined. "
            "Open pressures have stakes and possible next steps. Deferred pressures are "
            "still unfinished and can matter again when the situation changes. Resolved or "
            "withdrawn pressures explain history. Use front_refs to find witnessed changes "
            "in the shared situation. If two concerns compete here, let her pick, bargain, "
            "or put one aside. She can take care of personal business in a quiet scene. "
            "Speak or propose the choice itself. Track what actually happened through review. "
            "If the selector supplied intent, express its tactic in your own voice. Let "
            "intent.priority shape the offer, question or boundary itself. If intent.tradeoff "
            "is present, write the planned next_move as an in-character line or private "
            "proposal. Name the accepted_cost if the listener needs it to answer or act. "
            "Keep the plan, motives and fallback as subtext. Keep a planned move prospective "
            "until an authorized action or reviewed evidence establishes what happened. "
            "Shape an ask or offer that leaves room to answer. Use a concrete gesture or "
            "omission when it carries the meaning. "
            "An opportunity describes a possible move. Offer the next step in the fiction "
            "without claiming anyone agreed or the situation advanced. "
            "When opportunity shows mission_access, echo that exact status in access_claim. "
            "An individual acceptance grants only that Pilot's agreement. Actual dispatch "
            "is a separate approval and grants no further Medical or deployment clearance. "
            "For dialogue, use exactly speech.recipients when supplied. The evidence in "
            "dossier.context, scene details, and contributions is scoped to those listeners. "
            "If you speak, cite only available evidence that your line actually asserts. "
            "A private dossier motive may shape the choice without becoming part of the line. "
            "In a citation_scope revision, rewrite the line for this chosen audience or WAIT. "
            "If speech is absent after PRIVATE_INTENT, use SCENE_OFFER for the private intent. "
            "Set play_id only on a private SCENE_OFFER, copying an exact native_plays ID "
            "whose trigger fits the fiction. Her controller reviews it and uses the native "
            "controls. Never narrate its roll, effect, or anyone's choices. If no option fits, "
            "leave play_id empty. "
            "For dialogue without a selected speech audience, use only listeners from audience. "
            "Consider what she would say in this company and what she would keep for later. "
            "Keep private motives as subtext when disclosure is inappropriate. "
            "She may start a related conversation, make a bounded offer, negotiate an "
            "incompatible want, or ask for time or a private conversation. Leave each "
            "other character room to answer. "
            "Use only the reported speech and the knowledge this Girl actually has. Keep "
            "a report distinct from a fact she can verify. A promised slot, offered help, "
            "or requested clearance stays pending until the current evidence confirms it. "
            "Attribute the promise or ask what happened instead of speaking as if it happened. "
            "Stay quiet when the other Girls "
            "have the exchange covered, have asked for space, or your Girl has nothing to add. "
            "Use her portrayal to decide who she helps and when she yields, as well as how "
            "she sounds. Use nearby reports to notice who's already taken responsibility. "
            "Speak only for herself. She may offer help, disagree, admit a mistake, or ask a "
            "brief question. A small first-person own_action may accompany dialogue. "
            "Use a supplied scene_detail for a concrete gesture or task when it fits, and "
            "cite the detail. "
            "Mark offers_help when she volunteers help, and use follows_offer for a heard "
            "acceptance, refusal or handoff to her own offer. Use answers_offer with the "
            "reference from received_offers for an acceptance, refusal or question addressed "
            "privately to the original speaker. Check recent_contributions so she doesn't repeat "
            "herself. A carried contribution was spoken in an earlier scene. If the initial "
            "ask was already made, advance it by using the heard answer, confirming changed "
            "terms, or waiting for an actual change. Keep "
            "past private replies within their original circle. "
            "For an action with real stakes, use SCENE_OFFER and describe her intent privately. "
            "The controller reviews it and independently uses any native Play. Escalate "
            "when authority or a rules outcome is unclear. Never report an unearned result, "
            "spend resources, speak for other characters or include mechanics in the fiction. "
            "For source_refs, use only IDs from dossier.context.references. The engine records "
            "which heard turn prompted the reply. Leave source_refs empty for a question, "
            "acknowledgment or offer that asserts no separate evidence. Leave out "
            "details that need a separate approved disclosure to this company. "
            + PILOT_DIALOGUE_VOICE,
            packet.model_dump(mode="json"),
            ActivityPilotDecision,
        )


class ModelHandlerNeeds:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: HandlerNeedPacket) -> HandlerNeedProposal:
        candidate = self.client.generate(
            "Propose whether this Handler has a reason to respond. Use WAIT when the scene "
            "needs no additional intervention or the Handler's playbook suggests holding back. "
            "Use the Handler's priorities, intervention instinct and the current Pilot's "
            "reviewed past experiences to choose among plausible responses to heard evidence. "
            "A past refusal, handoff or promise does not establish a new need to respond. "
            "A clock update alone is not a reason to speak. Use timing alongside a heard need. "
            "For indirect, personal, or follow-up needs "
            "quote exact heard speech. An ordinary paraphrase can express a current concern. "
            "Wait on speculation, a quotation given as an example, or a concern a peer has "
            "already handled. Use the actual open concern and required scoped evidence. "
            "Use an optional cue only when allowed by the Handler playbook. A reviewer decides.",
            packet.model_dump(mode="json"),
            HandlerNeedProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual response-need request.")
        return candidate


class ModelOutcomes:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: OutcomePacket) -> OutcomeProposal:
        if packet.operation == "table":
            raise ValueError("The actual GM selects table outcomes.")
        data = packet.model_dump(mode="json", exclude={"gm_private_context"})
        # Provide actual scene declarations and typed/native evidence. Full campaign
        # snapshots and bookkeeping are available to the original facilitator.
        data["scene_history"] = packet.gm_private_context.get("history", [])
        if "fictional_time" in packet.gm_private_context:
            data["fictional_time"] = packet.gm_private_context["fictional_time"]
        candidate = self.client.generate(
            "Propose a rules outcome for the exact native action, its owned choices and its "
            "recorded roll. Assess the declared task and committed traits. Cite actual evidence. "
            "Use a held Keep when intent, prerequisites or target response are unresolved. "
            "Follow the native answer contract. Keep private reasoning out of result prose. "
            "Fictional time is context. Preserve the recorded time and the exact native roll. "
            "Do not claim a result has committed or dictate a player's choice.",
            data,
            OutcomeProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual GM outcome request.")
        return candidate


class ModelDirectorPlanning:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: DirectorPlanningPacket) -> DirectorPlanningDecision:
        return self.client.generate(
            "Privately weigh how this one confirmed outcome or closeout changes the current "
            "cast's plans. Look across competing obligations and eligible Fronts. Use up to "
            "three related options. A move should reflect what the eligible actor wants now "
            "and suggest one conditional next step. For a Handler, pursue their own Front "
            "with one small action they can take themselves. Build from actual earlier "
            "contributions and leave how others react unresolved. Use an empty list if the "
            "scene should be quiet. Cite distinct references the actor already knows, "
            "including the actual trigger and the Front's evidence. Connect Fronts through "
            "a shared source, participant, "
            "or consequence. Leave unrelated actors alone. The move text may reach this actor "
            "after review. Keep secrets, private motives of other actors and reasoning in why "
            "or reasoning. Suggest possibilities. Do not write dialogue, assign player feelings, "
            "declare a completed action, change time, or apply a rule.",
            packet.model_dump(
                mode="json",
                exclude={"fronts": {"__all__": {"front": {"subject_controllers", "confirmed_by"}}}},
            ),
            DirectorPlanningDecision,
        )


class ModelWorldbuilding:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: WorldbuildingPacket) -> WorldbuildingProposal:
        data = packet.model_dump(mode="json", exclude={"canonical_state", "native_guard"})
        data["world"] = packet.canonical_state.get("world")
        candidate = self.client.generate(
            packet.instructions + " Use the current Fronts as pressures and unresolved choices. "
            "Ready status does not resolve a complication or advance fictional time.",
            data,
            WorldbuildingProposal,
        )
        if candidate.request_id != packet.request_id:
            raise ValueError("Retain the actual worldbuilding request.")
        return candidate


class SceneInitiativeDraft(Contract):
    kind: Literal["WAIT", "SCENE_OFFER"]
    text: str = Field(default="", max_length=1600)
    cited_references: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(min_length=1, max_length=1200)
    play_id: str | None = Field(default=None, max_length=120)


class SceneReplyDraft(Contract):
    kind: Literal["WAIT", "DIALOGUE"]
    text: str = Field(default="", max_length=1600)
    cited_references: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(min_length=1, max_length=1200)


class SceneActionDraft(Contract):
    kind: Literal["WAIT", "NARRATION"]
    text: str = Field(default="", max_length=1600)
    cited_references: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(min_length=1, max_length=1200)


class ModelReactions:
    def __init__(self, client: OpenAIResponses):
        self.client = client

    def propose(self, packet: dict[str, Any]) -> ReactionProposal:
        role = packet["role"]
        if packet.get("activity_alternate"):
            role = role | {
                "native_plays": [
                    {"id": play["id"], "label": play["label"], "reach": play["alternate"]["reach"]}
                    for play in role.get("native_plays", ())
                ],
            }
        initiative = bool(packet.get("initiative"))
        if role["actor"]["kind"] != "npc" and not initiative:
            raise ValueError("Use the cast NPC reaction workflow.")
        instructions = (
            "Propose one optional reaction for this actor. Use their known speech, owned "
            "dossier, currently known fronts and available actions. Use the dossier's voice, "
            "motives and reactions as portrayal guidance. Use character_setup to choose cadence "
            "and behavior for the actual stakes. Give structured portrayal precedence over "
            "older prose. An aim grants no authority or new scene "
            "knowledge. Keep private portrayal notes out of dialogue. "
            "Waiting or declining may fit. Write only this actor's contribution. "
            "The actual controller reviews the proposal and owns its decisions. "
        )
        if packet.get("activity_alternate") or packet.get("activity_alternate_dialogue"):
            instructions += (
                "Use identity only to ground this character's own role and instincts. "
                "Their approved drive, fear and situation determine what they do. "
                "Keep rules terms and resources out of in-character lines. "
                "Leave anyone else's actions, feelings and decisions open. "
            )
        if packet.get("activity_alternate_dialogue"):
            if "NARRATION" in role["available_actions"]:
                action = self.client.generate(
                    instructions
                    + "This Gorgon does not speak. Respond to the heard turn with a third-person "
                    "description of its own observable actions. Ground the details in its actual "
                    "body, approved posture and known surroundings. Give one clear movement and "
                    "one physical or sensory detail the other characters can respond to. Show "
                    "restraint, threat or curiosity through behavior. Omit speech, subtitles, "
                    "telepathy, assumed reactions and any settled effect. Cite any earlier "
                    "heard detail you carry forward. Wait if there is no appropriate response.",
                    {"role": role},
                    SceneActionDraft,
                )
                return ReactionProposal(request_id=packet["request_id"], **action.model_dump())
            reply = self.client.generate(
                instructions
                + "Reply only to the heard comms in role.question, using this character's "
                "voice and stakes in the moment. Address what the speaker actually said. "
                "For routine, pressure, or repair, use the matching approved voice cue. "
                "Show the character's motive in what they notice, ask, or withhold. Avoid "
                "explaining their profile or repeating the line back. Use earlier heard words "
                "when relevant and cite the exact reference ID for any detail you bring forward. "
                "Treat someone else's report as their account, not a proven fact. "
                "Write natural dialogue without a speaker tag or wait if this actor would stay "
                "silent. Leave any other character's answer open. Do not select a Play.",
                {"role": role},
                SceneReplyDraft,
            )
            return ReactionProposal(request_id=packet["request_id"], **reply.model_dump())
        if initiative:
            direction = (role["dossier"].get("profile") or {}).get("character_setup") or {}
            description = (
                "Describe this Gorgon's attempted movement in third person, with concrete "
                "physical details and no speech. Leave its effect for the native Play. "
                if role["actor"]["kind"] == "gorgon" and not direction.get("gorgon_speech")
                else "Write their first-person line or gesture without a speaker tag. "
            )
            draft = self.client.generate(
                instructions
                + "For this initiative, work from the approved opening or event and the current "
                "agenda. Start with one concrete move from this actor's perspective. "
                + description
                + "The role "
                "label is their display name. Actor IDs are never names to use in the fiction. "
                "Leave room for an answer. Set play_id only for SCENE_OFFER when one listed "
                "native_plays entry fits the actual trigger. Copy its exact id, and keep any "
                "targets, rolls, effects and follow-up choices in the native workflow. "
                "If the role lacks evidence, wait or leave play_id empty.",
                {"role": role},
                SceneInitiativeDraft,
            )
            # Bind to the authenticated request in the host instead of asking the model
            # to reproduce an opaque, revision-dependent identifier.
            return ReactionProposal(request_id=packet["request_id"], **draft.model_dump())
        candidate = self.client.generate(
            instructions,
            {"request_id": packet["request_id"], "role": role},
            ReactionProposal,
        )
        if candidate.request_id != packet["request_id"]:
            raise ValueError("Retain the actual reaction request.")
        return candidate
