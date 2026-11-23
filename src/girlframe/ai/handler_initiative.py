"""Source-bound opportunities for a Handler to initiate a small fictional beat."""

import re
from hashlib import sha256
from typing import NamedTuple

from pydantic import Field

from girlframe.ai.contracts import Contract
from girlframe.engine.m3_handler_character import BOOK_RULES, PROFILES, Cue, PlaybookProfile
from girlframe.engine.m3_handler_state import (
    PERSONALITIES,
    HandlerNotes,
    HandlerPersonality,
    Playbook,
)
from girlframe.scenes.opening import SceneOpening


class PlayLead(Contract):
    title: str
    trigger: str


class HandlerInitiative(Contract):
    report_id: str
    support_report_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    cue: Cue
    prompt: str
    issue: str
    opportunity: str
    inspired_by: Playbook | None = Field(default=None, exclude_if=lambda value: value is None)
    possible_play: PlayLead | None = Field(default=None, exclude_if=lambda value: value is None)


class Signal(NamedTuple):
    prompt: str
    pattern: str
    opportunity: str
    signature: bool = False


# The archetype signals use each profile's specialist cue. Personal support remains
# available to profiles that already allow it, as a fallback when no specialist signal fits.
SIGNALS: dict[Playbook, tuple[Signal, ...]] = {
    "Mistress": (
        Signal(
            "unseen_care",
            r"\b(?:stayed (?:behind )?to finish|covered (?:her|their) shift|"
            r"no one noticed (?:i|we)|nobody (?:noticed|thanked))\b",
            "Name the care or extra work you heard about. Offer credit the Girl can accept freely.",
        ),
        Signal(
            "kindness_as_debt",
            r"\b(?:owe (?:her|them|you) (?:for helping|a favor|a favour)|"
            r"(?:her|the) kindness (?:feels|sounds) like a debt)\b",
            "Offer a personal kindness the Girl can accept or decline without owing you a return.",
        ),
        Signal(
            "conditional_praise",
            r"\b(?:only (?:praised|thanked) me (?:when|while)|"
            r"praise (?:came|comes) with strings attached)\b",
            "Give specific recognition to something the Girl actually chose to do.",
        ),
        Signal(
            "immediate_obedience",
            r"\b(?:chose|decided) to (?:obey|follow (?:the|your) order)\b"
            r"[^.!?]{0,48}\b(?:right away|immediately|without waiting)\b",
            "Acknowledge the choice. Offer a small favor without assuming affection or loyalty.",
            True,
        ),
    ),
    "Dogrunner": (
        Signal(
            "missed_duty",
            r"\b(?:initiall?ed|signed) (?:a|the) blank\b|"
            r"\b(?:missed|skipped|left) (?:my|the) (?:assigned |agreed )?(?:watch|handoff|duty)\b",
            "Name the duty and the repair. Offer to hold the desk while the Girl corrects it.",
        ),
        Signal(
            "ambiguous_ownership",
            r"\b(?:both thought\b[^.!?]{0,55}\b(?:sign(?:ing)? off|sign-?off|assigned duty)|"
            r"(?:no one|nobody) (?:signed off|took responsibility))\b",
            "Read back the ownership mix-up and offer to make the next assignment explicit.",
        ),
        Signal(
            "blame_after_repair",
            r"\b(?:fixed|repaired|corrected)\b[^.!?]{0,65}"
            r"\b(?:still (?:blaming|blame)|passing (?:the )?blame)\b",
            "Name the actual repair and offer the Girl a clear way back into the work.",
        ),
        Signal(
            "direct_reckoning",
            r"\b(?:ignored|broke) (?:the |an? )?(?:clear |standing )?"
            r"(?:safety rule|agreed standard)\b",
            "State the standard and the reported lapse. Leave the Girl room to give her account.",
            True,
        ),
    ),
    "Scientist": (
        Signal(
            "conditional_reading",
            r"\b(?:pulsed|flickered|spiked) (?:twice|again|only|after|when)\b|"
            r"\b(?:reading|signal|gauge) (?:changed|jumped|drifted)\b",
            "Preserve the reported condition while it is fresh. A short aside to the reporter "
            "can offer one comparison across that condition or capture the timing while the "
            "Pilots keep working. Leave explanations and extra checks for later.",
        ),
        Signal(
            "conflicting_observations",
            r"\b(?:(?:two|both) (?:gauges|sensors|readings) (?:disagree|don't agree)|"
            r"(?:your|her|my) reading differs from (?:yours|hers|mine))\b",
            "Preserve both observations and offer one check that could distinguish them.",
        ),
        Signal(
            "evidence_losing_context",
            r"\b(?:move|moving|moved|discard|discarding|reset|resetting|zero|zeroing)\b"
            r"[^.!?]{0,45}\b(?:sample|specimen|gauge|sensor)\b"
            r"[^.!?]{0,45}\b(?:before|without)\b[^.!?]{0,35}\b(?:log|mark|label|write)\w*",
            "Offer to label the sample or record the conditions while those details are known.",
        ),
        Signal(
            "lab_comparison",
            r"\b(?:lab|bench|sample|samples|specimen)\b[^.!?]{0,65}"
            r"\b(?:compare|test|reproduce|repeat|isolate)\b|"
            r"\b(?:compare|test|reproduce|repeat|isolate)\b[^.!?]{0,65}\b(?:lab|bench)\b",
            "Offer bench time or name what a lab comparison could establish.",
            True,
        ),
    ),
    "Frantic": (
        Signal(
            "split_attention",
            r"\b(?:can(?:not|'t) (?:do|manage|keep up with) both|can(?:not|'t) count and grip)\b",
            "Volunteer to take one job now. Make the handoff explicit and wait before taking it.",
        ),
        Signal(
            "colliding_deadlines",
            r"\b(?:two calls at once|both (?:radios|lines) (?:are|keep) (?:going|calling)|"
            r"both (?:jobs|calls|checks) (?:are due|need doing) (?:right now|at once|before))\b",
            "Say which job needs attention now and offer to hold the other line.",
        ),
        Signal(
            "unanswered_handoff",
            r"\b(?:no one|nobody) (?:has )?(?:called back|answered (?:the |my )?handoff)\b|"
            r"\b(?:urgent |time-sensitive )?handoff (?:is |went )unanswered\b",
            "Name what slipped and volunteer one callback or a quick check on who has the job.",
        ),
        Signal(
            "handler_overload",
            r"\b(?:handler\s*[:,]\s*you (?:are|look|sound)|"
            r"(?:our|the) handler (?:is|looks|sounds)) (?:about to break|overloaded|"
            r"at (?:your|their) limit|like (?:you're|they're) coming apart)\b",
            "Own the overload in your own voice. Ask for help with one immediate responsibility.",
            True,
        ),
    ),
    "Insurgent": (
        Signal(
            "demand_for_names",
            r"\b(?:asked|demanded|wanted) (?:for )?(?:our |their |the )?names?\b"
            r"[^.!?]{0,75}\b(?:before|for (?:the|their) file|or else)\b",
            "Offer to take the institutional call and ask what the Girls want shared.",
        ),
        Signal(
            "unsafe_channel",
            r"\b(?:(?:this|the) (?:channel|line|frequency) is (?:being )?(?:recorded|monitored)|"
            r"(?:they|someone) (?:are|is) listening (?:in|on this channel))\b",
            "Offer to stop the public exchange and check in on an authorized private channel.",
        ),
        Signal(
            "exposing_request",
            r"\b(?:request|form|order|inspection)\b[^.!?]{0,45}"
            r"\b(?:would|will) (?:expose|identify|give away|name) (?:a|an|the|our|their)\b",
            "Offer to carry a narrower account. Leave disclosure to the people affected.",
        ),
        Signal(
            "witnessed_dissent",
            r"\b(?:witnessed|heard|saw)\b[^.!?]{0,75}\b(?:speak out|spoke out|dissent)\b",
            "Ask what was actually witnessed and who else heard it. Protect confidences.",
            True,
        ),
    ),
    "Trainer": (
        Signal(
            "broken_sequence",
            r"\b(?:checklist|checks|steps)\b[^.!?]{0,45}\bout of order\b|"
            r"\b(?:skipped|missed|forgot) (?:the|a) (?:first |second |next )?(?:row|step|check)\b",
            "Ask for the last step the Girl actually completed and offer one readback from there.",
        ),
        Signal(
            "drill_does_not_transfer",
            r"\b(?:drill|practice|training|rehearsal)\b[^.!?]{0,55}"
            r"\b(?:doesn't work here|can't apply it here|can't do it here|different here)\b",
            "Offer to demonstrate the physical difference between practice and this setup.",
        ),
        Signal(
            "instruction_keeps_failing",
            r"\b(?:same instruction|same directions|same drill)\b[^.!?]{0,50}"
            r"\b(?:same mistake|keep missing|still get it wrong)\b",
            "Teach it differently. Offer a slower demonstration or let the Girl locate the snag.",
        ),
        Signal(
            "spoken_cue_rehearsal",
            r"\b(?:practice|practise|rehearse)\b[^.!?]{0,50}"
            r"\b(?:a|the|our) (?:new )?(?:phrase|verbal cue|spoken cue)\b",
            "Offer to rehearse the spoken cue with permission. Let the Girl set the pace.",
            True,
        ),
    ),
    "Advocate": (
        Signal(
            "cut_off",
            r"\b(?:answered for me|spoke for me|cut me off|wouldn(?:'t| not) let me finish)\b",
            "Keep the conversation open so the Girl can finish in her own words.",
        ),
        Signal(
            "record_erases_nuance",
            r"\b(?:form|report) (?:has|gives (?:me|us)) (?:only )?one box\b|"
            r"\b(?:form|report) (?:leaves|left) no room (?:to|for)\b",
            "Offer to get another line or carry the distinction as stated. Leave the wording "
            "with the Girl.",
        ),
        Signal(
            "decision_already_made",
            r"\bdecided\b[^.!?]{0,60}\bbefore i (?:got to |could )?finish\b|"
            r"\b(?:said|told me) (?:i'd|i had|i) already (?:agreed|accepted|decided)\b",
            "Ask what the Girl wants and offer to buy her time to say it.",
        ),
        Signal(
            "room_to_speak_privately",
            r"\b(?:i(?:'d| would) (?:rather |feel freer to )?(?:talk|speak|tell you) "
            r"(?:in private|alone)|i could (?:say more|speak freely) (?:in private|alone))\b",
            "Offer a private check-in the Girl can decline.",
            True,
        ),
    ),
}

PERSONAL = Signal(
    "personal_support",
    r"\b(?:still in my ears|can(?:not|'t) settle|can(?:not|'t) stop shaking)\b",
    "Offer one small comfort that fits the sheet and this setting. Leave an easy way to decline.",
)
OFF_DUTY_PERSONAL = "off_duty_personal"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_RESTATEMENT = re.compile(r"^(?:again|like i said|as i said)[,\s:]+")
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?")
_BARE_CAPACITY = re.compile(r"^(?:i|we) can(?:not|'t) (?:do|manage|keep up with) both[.!?]*$")
_RECORD_LIMIT = re.compile(
    r"\b(?:form|report|debrief|record)\b[^.!?\n;]{0,64}"
    r"\b(?:(?:one|single) (?:box|field|line)|no room (?:to|for))\b"
)
_RECORD_DISTINCTION = re.compile(
    r"\b(?:two different things|both (?:parts|statuses|versions)|"
    r"(?:lose|blur|erase|hide|drop) (?:that|the) (?:distinction|difference|uncertainty))\b|"
    r"\b(?:checked|confirmed|delivered|reported|verified)\b[^.!?\n]{0,70}"
    r"\b(?:but|while|and)\b[^.!?\n]{0,45}"
    r"\b(?:unverified|unchecked|not (?:yet )?(?:verified|checked|confirmed)|"
    r"(?:haven't|hasn't) (?:verified|checked|confirmed))\b"
)


def off_duty_initiative(
    notes: HandlerNotes | None, opening: SceneOpening, report_id: str, heard: str
) -> HandlerInitiative | None:
    """Offer a personal beat only when the Handler's cue has a current shared source."""
    if not opening.off_duty or notes is None or not notes.off_duty_cue:
        return None
    if not any((notes.personal_habit, notes.obligation, notes.relationship_tension)):
        return None
    phrase = " ".join(_WORD.findall(notes.off_duty_cue.casefold()))
    if not phrase:
        return None
    surroundings = (opening.location, opening.intro, *(detail.text for detail in opening.details))
    if not any(
        f" {phrase} " in f" {' '.join(_WORD.findall(text.casefold()))} "
        for text in (heard, *surroundings)
    ):
        return None
    return HandlerInitiative(
        report_id=report_id,
        cue="personal",
        prompt=OFF_DUTY_PERSONAL,
        issue=sha256(f"{OFF_DUTY_PERSONAL}\n{phrase}".encode()).hexdigest(),
        opportunity=(
            "The heard turn or shared setting touches something personal. If the Pilots have "
            "left room, share one small habit, own concern, or honest ask as a person. "
            "Leave the Girls' relationships and decisions with them. Wait if the moment is theirs."
        ),
    )


def _record_distinction(
    sentences: list[str], earlier_comms: tuple[tuple[str, str], ...]
) -> tuple[tuple[int, str], str | None] | None:
    support = next(
        (
            report_id
            for report_id, text in reversed(earlier_comms)
            if _RECORD_LIMIT.search(text.casefold())
        ),
        None,
    )
    own_limit = False
    for index, sentence in enumerate(sentences):
        own_limit = own_limit or bool(_RECORD_LIMIT.search(sentence))
        if (own_limit or support is not None) and _RECORD_DISTINCTION.search(sentence):
            return (index, sentence), None if own_limit else support
    return None


def initiative_for(
    profile: PlaybookProfile,
    report_id: str,
    heard: str,
    *,
    earlier_comms: tuple[tuple[str, str], ...] = (),
) -> HandlerInitiative | None:
    sentences = _SENTENCE_END.split(heard.strip().casefold().replace("’", "'"))
    # The primary cue is the specialist category on each printed-book profile.
    for signal in (*SIGNALS[profile.playbook], PERSONAL):
        cue: Cue = "personal" if signal is PERSONAL else profile.cues[0]
        if cue not in profile.cues:
            continue
        match = next(
            (
                (index, text)
                for index, text in enumerate(sentences)
                if re.search(signal.pattern, text)
            ),
            None,
        )
        support = None
        if match is None and signal.prompt == "record_erases_nuance":
            found = _record_distinction(sentences, earlier_comms)
            if found is not None:
                match, support = found
        if match is None:
            continue
        index, sentence = match
        evidence = _RESTATEMENT.sub("", sentence)
        if index and signal.prompt == "split_attention" and _BARE_CAPACITY.fullmatch(evidence):
            evidence = f"{_RESTATEMENT.sub('', sentences[index - 1])} {evidence}"
        words = " ".join(_WORD.findall(evidence))
        issue = sha256(f"{signal.prompt}\n{words}".encode()).hexdigest()
        signature = (
            next(rule for rule in BOOK_RULES[profile.playbook] if rule.kind == "Signature Play")
            if signal.signature
            else None
        )
        return HandlerInitiative(
            report_id=report_id,
            support_report_id=support,
            cue=cue,
            prompt=signal.prompt,
            issue=issue,
            opportunity=signal.opportunity,
            possible_play=PlayLead(title=signature.title, trigger=signature.trigger)
            if signature
            else None,
        )
    return None


def alternate_initiative(
    profile: PlaybookProfile,
    personality: HandlerPersonality,
    report_id: str,
    heard: str,
    *,
    seed: str,
) -> HandlerInitiative | None:
    """Allow an ordinary cue from a related style on one in five grounded issues."""
    for book in PERSONALITIES[personality].affinities:
        if book == profile.playbook:
            continue
        candidate = initiative_for(PROFILES[book], report_id, heard)
        if candidate and candidate.possible_play is None and candidate.cue != "personal":
            draw = sha256(f"{seed}\n{candidate.issue}".encode()).digest()
            if int.from_bytes(draw, "big") % 5 == 0:
                return candidate.model_copy(update={"cue": profile.cues[0], "inspired_by": book})
    return None
