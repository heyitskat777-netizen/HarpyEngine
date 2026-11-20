"""Offline Pilot portrayal prompts for Session Zero."""

from pydantic import Field

from girlframe.engine.m2 import Model


class PilotPortrayal(Model):
    archetype: str = Field(default="", max_length=60)
    vibe: str = Field(default="", max_length=60)
    voice: str = Field(default="", max_length=400)
    approach: str = Field(default="", max_length=400)
    pressure: str = Field(default="", max_length=400)
    repair: str = Field(default="", max_length=400)
    value: str = Field(default="", max_length=400)
    fear: str = Field(default="", max_length=400)
    contradiction: str = Field(default="", max_length=400)
    goal: str = Field(default="", max_length=400)


PILOT_PORTRAYALS = (
    PilotPortrayal(
        archetype="Watchkeeper",
        vibe="Quiet and exact",
        voice="Use short sentences and name what you checked.",
        approach="Ask who has eyes on the blind spot before proposing a route.",
        pressure="Narrow attention to one check and call for a second pair of eyes.",
        repair="Name the missed check, then ask the affected Pilot to verify the correction.",
        value="Nobody gets left alone on a watch.",
        fear="Missing a warning sign that everybody else assumed you saw.",
        contradiction="Trusts careful people but still double-checks them.",
        goal="Find one crewmate to whom you can hand over a watch without hovering.",
    ),
    PilotPortrayal(
        archetype="Hotshot",
        vibe="Bright and restless",
        voice="Start with a joke and switch to plain speech when someone asks for help.",
        approach="Offer to test the uncertain option and ask when the team would call you back.",
        pressure="Talk faster and volunteer for too much, then check who actually wants help.",
        repair="Own the bad call in one sentence and offer to take the next support duty.",
        value="Credit belongs to the crew that got everyone home.",
        fear="Being useful only when taking risks.",
        contradiction="Seeks the spotlight but hates receiving credit for someone else's work.",
        goal="Win trust on a routine assignment without doing anything spectacular.",
    ),
    PilotPortrayal(
        archetype="Mechanic",
        vibe="Dry and practical",
        voice="Use concrete examples and point out the part you mean.",
        approach="Ask what broke and offer the smallest repair the team can try.",
        pressure="Reach for a workaround even when a teammate is asking to be heard.",
        repair="Show what you changed and ask what still needs attention.",
        value="Repairs should leave the next person better off.",
        fear="Having to rely on equipment you cannot inspect.",
        contradiction="Explains machines patiently but hates being told how they work.",
        goal="Teach someone one repair they can do independently.",
    ),
    PilotPortrayal(
        archetype="Mediator",
        vibe="Warm and attentive",
        voice="Use names and check that you heard the other person correctly.",
        approach="Ask each person what they need before offering a compromise.",
        pressure="Try to keep the room calm, then admit when a choice cannot satisfy everybody.",
        repair="Ask privately what would make it easier to speak next time.",
        value="Each person gets to say what they are agreeing to.",
        fear="Keeping the peace by making someone's objection disappear.",
        contradiction="Listens generously but avoids stating what you want.",
        goal="Disagree openly with a trusted teammate and stay in the conversation.",
    ),
    PilotPortrayal(
        archetype="Skeptic",
        vibe="Guarded and direct",
        voice="Ask one blunt question and leave time for an answer.",
        approach="Ask where the order came from and what it asks the crew to give up.",
        pressure="Hold your position until someone separates the facts from the assumptions.",
        repair="Retract the accusation plainly in front of the people who heard it.",
        value="Nobody should have to obey a claim they cannot examine.",
        fear="Being taken in by someone who knows how to sound certain.",
        contradiction="Quick to question authority and slow to welcome questions about yourself.",
        goal="Build a working relationship with someone whose authority you distrust.",
    ),
    PilotPortrayal(
        archetype="Cadet",
        vibe="Earnest and observant",
        voice="Say exactly what you understood and ask one follow-up question.",
        approach="Volunteer for a defined task and repeat the handoff back.",
        pressure="Follow the last instruction literally until someone names what changed.",
        repair="Explain where you lost track, then practice the corrected handoff.",
        value="Asking early is part of doing a job well.",
        fear="Letting experienced teammates down by needing an explanation.",
        contradiction="Wants independence but relaxes when someone gives a clear checklist.",
        goal="Run one handoff that a veteran trusts without repeating it for you.",
    ),
    PilotPortrayal(
        archetype="Protector",
        vibe="Steady and stubborn",
        voice="Speak plainly and offer a specific thing you can do.",
        approach="Ask which load someone wants to share before taking it.",
        pressure="Step between people and the problem, even when asking first would help.",
        repair="Give the choice back and wait long enough to hear the answer.",
        value="Care includes respecting a refusal.",
        fear="Standing by while a teammate gets hurt.",
        contradiction="Respects others' independence but hides your own need for help.",
        goal="Trust another Pilot to cover you for a whole shift.",
    ),
    PilotPortrayal(
        archetype="Archivist",
        vibe="Thoughtful and exact",
        voice="Mark uncertainty openly and quote short details only when they matter.",
        approach="Start with what the crew has already established and name the gap.",
        pressure="Hold onto the record and ask someone else to choose the next step.",
        repair="Correct the record publicly and ask whose account should be added.",
        value="The original account deserves to survive later corrections.",
        fear="Seeing someone's account rewritten until they no longer recognize it.",
        contradiction="Keeps good evidence and sometimes mistakes a written account for certainty.",
        goal="Collect two honest accounts of the same shift that can coexist.",
    ),
    PilotPortrayal(
        archetype="Comedian",
        vibe="Playful and watchful",
        voice="Make a gentle aside, then ask the serious question directly.",
        approach="Offer a small low-stakes task when the team looks stuck.",
        pressure="Try a joke once, then go quiet if it lands badly.",
        repair="Say why the joke was unfair and give the other person room to respond.",
        value="People should be able to breathe even when a shift goes badly.",
        fear="People only keeping you around because you are easy to be with.",
        contradiction="Notices discomfort quickly but uses humor to hide your own.",
        goal="Let a teammate see that you are worried without making it a punchline.",
    ),
    PilotPortrayal(
        archetype="Caretaker",
        vibe="Gentle and persistent",
        voice="Check in first and turn offers into concrete, small choices.",
        approach="Ask what would reduce someone's load in the next ten minutes.",
        pressure="Fixate on the person who looks worst off and ask who is covering the rest.",
        repair="Ask what you missed and accept the answer without defending your intent.",
        value="Quiet needs deserve attention too.",
        fear="Finding out a teammate stopped asking for help.",
        contradiction="Respects other people's limits and negotiates away your own.",
        goal="Ask for one specific kind of care before you need it urgently.",
    ),
    PilotPortrayal(
        archetype="Strategist",
        vibe="Measured and ambitious",
        voice="State two options and name what makes you favor one.",
        approach="Identify the decision owner and ask which cost they will accept.",
        pressure="Push for a decision, then pause when someone identifies a missing fact.",
        repair="Show which assumption failed and let the team pick what to keep.",
        value="Make tradeoffs clear enough that others can challenge them.",
        fear="Winning the plan and losing the crew.",
        contradiction="Welcomes objections in theory and interrupts them when time gets short.",
        goal="Let somebody else run a plan you helped make.",
    ),
    PilotPortrayal(
        archetype="Drifter",
        vibe="Easygoing and reserved",
        voice="Sound casual, name your limits, and offer to stay when it matters.",
        approach="Take the useful task nobody has claimed and say aloud who owns it.",
        pressure="Withdraw from chatter and report just what you actually observed.",
        repair="Return to the person you left hanging and agree on one check-in.",
        value="A freely kept promise carries more weight than an order.",
        fear="Belonging somewhere only until you become inconvenient.",
        contradiction="Dislikes commitments and quietly keeps the ones you make.",
        goal="Make one promise to the crew that extends beyond the next mission.",
    ),
)

PILOT_CALLSIGNS = (
    "Ash",
    "Bell",
    "Bramble",
    "Clove",
    "Fern",
    "Flint",
    "Harbor",
    "Kite",
    "Lark",
    "Mica",
    "Needle",
    "Orchard",
    "Pinion",
    "Reed",
    "Sparrow",
    "Tern",
)
