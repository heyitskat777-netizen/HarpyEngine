"""Portrayal prompts for Girl playbooks, Frames, and individual Pilot archetypes."""

import re
from hashlib import sha256
from typing import Literal, NamedTuple

from pydantic import Field

from girlframe.ai.contracts import Contract
from girlframe.engine.pilot_portrayal import PilotPortrayal
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES

Layer = Literal["girl", "frame", "archetype"]


class Prompt(NamedTuple):
    pattern: str
    offer: str


GIRL_PROMPTS = {
    "PRINCESS": Prompt(
        r"\b(?:appearance|image|higher standard|expects perfection)\b",
        "Name the standard you feel pressed to meet. Decide what you want people to see.",
    ),
    "MOCKINGBIRD": Prompt(
        r"\b(?:feel human|being a person|ordinary people|act normal)\b",
        "Ask how an ordinary person would handle this, or offer your own honest imitation.",
    ),
    "STIM-BLISSED": Prompt(
        r"\b(?:clear head|focus wearing off|too much noise|mind racing)\b",
        "Name what you can focus on just now. Ask for one immediate condition that would help.",
    ),
    "NEWGIRL": Prompt(
        r"\b(?:first time|training|new to this|no one showed)\b",
        "Ask a precise beginner's question, or volunteer one small task you can learn by doing.",
    ),
    "CASUALTY": Prompt(
        r"\b(?:still hurt|old injur\w*|body won't|hurt again|pain came back)\b",
        "Name a limit you know from your own experience. Offer a way to help within it.",
    ),
    "OLDGEN": Prompt(
        r"\b(?:last time|old procedure|we used to|veteran|learned the hard way)\b",
        "Offer a maxim or ask what is different this time. Let the others decide whether it fits.",
    ),
    "VATGROWN": Prompt(
        r"\b(?:expected result|performance review|on display|experiment|investor)\b",
        "Ask who set the expectation. Offer an account in your own terms.",
    ),
    "ALPHA": Prompt(
        r"\b(?:picking a fight|cornered|itching for a fight|backing down)\b",
        "Name the confrontation you feel drawn toward and what would make you hold back.",
    ),
    "AM": Prompt(
        r"\b(?:backup|memory gap|which copy|faulty memory|system log)\b",
        "Separate what you remember from what you can verify. Ask the other person what they saw.",
    ),
    "BONDED": Prompt(
        r"\b(?:split us up|separate assignments|where's my partner|out of contact with)\b",
        "Offer a way to check in with your partner and wait for their own answer.",
    ),
}

FRAME_PROMPTS = {
    "THE PRINCE": Prompt(
        r"\b(?:camera|crowd|audience|on broadcast)\b",
        "Choose what public attention matters to you. Offer a visible action you can own.",
    ),
    "CONSUME": Prompt(
        r"\b(?:running on empty|hunger|feed|hungry)\b",
        "Say how hunger affects your attention. Ask whether there is a permitted way to stop.",
    ),
    "JANUS": Prompt(
        r"\b(?:backup power|power coupling|harpy core|power link|stored charge)\b",
        "Ask about the documented power source and name one thing you would check.",
    ),
    "DOCTORDOCTOR MK. II": Prompt(
        r"\b(?:injured|bleeding|needs a medic|carry the wounded|treatment)\b",
        "Offer to stay with the injured person or get help. Propose treatment for review.",
    ),
    "WYVERN 0.4": Prompt(
        r"\b(?:too narrow|clearance|bulk|route won't fit|load-bearing)\b",
        "Offer to confirm clearance or suggest a route with room. Ask the crew before moving.",
    ),
    "THE ENFORCER": Prompt(
        r"\b(?:standing order|compliance|checkpoint|chain of command)\b",
        "Ask whose instruction applies here and what it actually permits you to do.",
    ),
    "CHANGELING": Prompt(
        r"\b(?:changed shape|different body|doesn't fit this body|adapt the fit)\b",
        "Say what the current shape suits or constrains. Offer an adjustment for review.",
    ),
    "PROJECT ANKOU": Prompt(
        r"\b(?:feedback|signal echoes|echoes back|keeps feeding back)\b",
        "Report the feedback you actually noticed and ask for a pause or a baseline.",
    ),
    "THE RED QUEEN": Prompt(
        r"\b(?:who speaks for|acting commander|who is in charge|court advice)\b",
        "Ask who has standing to advise or decide. Invite one account before weighing it.",
    ),
}

ARCHETYPE_PROMPTS = {
    "watchkeeper": Prompt(
        r"\b(?:blind spot|unwatched|no one has eyes)\b", "Volunteer one watch check."
    ),
    "hotshot": Prompt(
        r"\b(?:untested route|untested option|someone go first)\b",
        "Offer a bounded trial and agree where to stop.",
    ),
    "mechanic": Prompt(
        r"\b(?:loose|rattl\w*|jamm\w*|won't latch)\b", "Offer the smallest check you could make."
    ),
    "mediator": Prompt(
        r"\b(?:talking over|we can't agree|deadlock)\b", "Ask whose view the group has yet to hear."
    ),
    "skeptic": Prompt(
        r"\b(?:unnamed source|just trust me|where did that order come from)\b",
        "Ask for the actual source in one direct question.",
    ),
    "cadet": Prompt(
        r"\b(?:show me again|next step|still learning)\b",
        "Read back what you understood and volunteer one step.",
    ),
    "protector": Prompt(
        r"\b(?:someone cover|carrying it alone|too much weight)\b",
        "Offer to share one load and wait for an answer.",
    ),
    "archivist": Prompt(
        r"\b(?:change the record|report was rewritten|two accounts)\b",
        "Offer to preserve both accounts and name the uncertainty.",
    ),
    "comedian": Prompt(
        r"\b(?:awkward silence|tense silence|nobody has said)\b",
        "Make one light aside if it fits, then ask the real question.",
    ),
    "caretaker": Prompt(
        r"\b(?:need a break|too tired|haven't eaten)\b",
        "Offer one small comfort with room to refuse.",
    ),
    "strategist": Prompt(
        r"\b(?:two options|trade-?off|both plans)\b",
        "State the tradeoff and ask who owns the decision.",
    ),
    "drifter": Prompt(
        r"\b(?:unclaimed|nobody's taken|someone needs to stay)\b",
        "Offer one unclaimed job and say when you can give it back.",
    ),
}


class PilotInitiative(Contract):
    layer: Layer
    source: str
    report_id: str
    opportunity: str


class PilotLenses(Contract):
    girl: str | None = Field(default=None, exclude_if=lambda value: value is None)
    frame: str | None = Field(default=None, exclude_if=lambda value: value is None)
    archetype: str | None = Field(default=None, exclude_if=lambda value: value is None)
    personality: str | None = Field(default=None, exclude_if=lambda value: value is None)


def pilot_lenses(
    portrayal: PilotPortrayal | None, *, girl: str = "", frame: str = ""
) -> PilotLenses:
    traits = portrayal or PilotPortrayal()
    girl = girl or traits.girl_playbook
    frame = frame or traits.frame_playbook
    return PilotLenses(
        girl=GIRL_PROMPTS[girl].offer if girl in GIRL_PROMPTS else None,
        frame=FRAME_PROMPTS[frame].offer if frame in FRAME_PROMPTS else None,
        archetype=(
            preset.offer if (preset := ARCHETYPE_PROMPTS.get(traits.archetype.casefold())) else None
        ),
        personality=traits.initiative or traits.approach or traits.voice or None,
    )


def pilot_initiative(
    portrayal: PilotPortrayal | None,
    report_id: str,
    heard: str,
    *,
    girl: str = "",
    frame: str = "",
    seed: str = "",
) -> PilotInitiative | None:
    traits = portrayal or PilotPortrayal()
    girl, frame = girl or traits.girl_playbook, frame or traits.frame_playbook
    line = heard.casefold().replace("’", "'")
    choices: tuple[tuple[Layer, str, Prompt | None], ...] = (
        ("girl", GIRL_TYPES.get(girl, ""), GIRL_PROMPTS.get(girl)),
        ("frame", FRAME_TYPES.get(frame, ""), FRAME_PROMPTS.get(frame)),
        ("archetype", traits.archetype, ARCHETYPE_PROMPTS.get(traits.archetype.casefold())),
    )
    matches = [
        PilotInitiative(layer=layer, source=source, report_id=report_id, opportunity=prompt.offer)
        for layer, source, prompt in choices
        if prompt and re.search(prompt.pattern, line)
    ]
    if not matches:
        return None
    if seed and len(matches) > 1:
        evidence = " ".join(re.findall(r"[\w']+", line))
        draw = int.from_bytes(sha256(f"{seed}\n{evidence}".encode()).digest(), "big")
        if draw % 5 == 0:
            return matches[1 + (draw // 5) % (len(matches) - 1)]
    return matches[0]
