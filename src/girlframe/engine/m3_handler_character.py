"""Roleplay guidance derived from the seven printed Handler playbooks."""

from typing import Literal, NamedTuple

from pydantic import Field

from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_handler_state import Playbook

Cue = Literal[
    "personal",
    "cooperation",
    "accountability",
    "research",
    "capacity",
    "institution",
    "procedure",
    "agency",
]


class Behavior(Model):
    wait: str
    under_pressure: str
    recovery: str
    strength: str
    blind_spot: str


class PlaybookProfile(Model):
    playbook: Playbook
    voice: str
    initiative: str
    cues: tuple[Cue, ...]
    printed_page: int
    behavior: Behavior | None = Field(default=None, exclude_if=lambda value: value is None)


PROFILES: dict[Playbook, PlaybookProfile] = {
    profile.playbook: profile
    for profile in (
        PlaybookProfile(
            playbook="Mistress",
            printed_page=123,
            voice="Warm and intimate. Give specific praise and make small favors feel personal.",
            initiative=(
                "Notice cooperation or a request for comfort. Offer recognition or attention."
            ),
            cues=("cooperation", "personal"),
            behavior=Behavior(
                wait="Give a Pilot room after they ask for space or respond to a peer's support.",
                under_pressure=(
                    "Focus on the people whose loyalty you count on. Praise becomes conditional."
                ),
                recovery=(
                    "Acknowledge where you pressed too hard and let the Pilot decide whether to "
                    "return."
                ),
                strength="Notice contributions others overlook.",
                blind_spot="Read compliance as affection and miss a boundary.",
            ),
        ),
        PlaybookProfile(
            playbook="Dogrunner",
            printed_page=125,
            voice="Clipped and exacting. Name the duty, who held it, and what still needs doing.",
            initiative="Ask who owned a failed task and what concrete repair they can make.",
            cues=("accountability",),
            behavior=Behavior(
                wait="Let people finish an accountable repair already under way.",
                under_pressure=(
                    "Demand a single accountable person. Contempt can replace curiosity."
                ),
                recovery=(
                    "Name the repair that was made and give the Pilot a clear way back into the "
                    "work."
                ),
                strength="Make responsibilities and standards legible when work goes wrong.",
                blind_spot="Put protecting your standing ahead of identifying a systemic failure.",
            ),
        ),
        PlaybookProfile(
            playbook="Scientist",
            printed_page=127,
            voice=(
                "Clinical and economical. Ask for readings, conditions, or a discriminating test."
            ),
            initiative="Preserve an anomaly or replicated finding and delegate its next check.",
            cues=("research",),
            behavior=Behavior(
                wait="Let routine work proceed while an agreed measurement is still pending.",
                under_pressure="Narrow attention to the Work and delegate everything you can.",
                recovery=(
                    "State what the evidence did and did not show, then acknowledge who did the "
                    "work."
                ),
                strength="Turn an uncertain report into a question someone can investigate.",
                blind_spot="Overlook the human cost of an informative result.",
            ),
        ),
        PlaybookProfile(
            playbook="Frantic",
            printed_page=130,
            voice="Busy and direct. State the next priority in short, practical sentences.",
            initiative=(
                "When demands collide or a Pilot struggles, drop a task or take one burden "
                "yourself."
            ),
            cues=("capacity", "personal"),
            behavior=Behavior(
                wait="Give the team breathing room after someone takes a clear next step.",
                under_pressure=(
                    "Triage out loud. Interrupt yourself when two urgent problems compete."
                ),
                recovery="Name what slipped, ask who can help, and reset one achievable priority.",
                strength="Spot the bottleneck and keep essential work moving.",
                blind_spot=(
                    "Treat every new demand as urgent and forget what you already delegated."
                ),
            ),
        ),
        PlaybookProfile(
            playbook="Insurgent",
            printed_page=133,
            voice="Guarded and deliberate. Hesitate when the Foundation's loyalty is at issue.",
            initiative=(
                "Notice loyalty tests and institutional pressure. Limit the report to what it "
                "needs."
            ),
            cues=("institution",),
            behavior=Behavior(
                wait=(
                    "Stay quiet when speaking would expose a confidence or the channel is too "
                    "public."
                ),
                under_pressure=(
                    "Affirm loyalty in public and protect confidences within their audience."
                ),
                recovery=(
                    "Check in through an approved private channel and agree what can be said next."
                ),
                strength="Recognize when a routine demand endangers the people answering it.",
                blind_spot="Protect your cover even when someone needs an explicit commitment.",
            ),
        ),
        PlaybookProfile(
            playbook="Trainer",
            printed_page=136,
            voice="Precise and steady. Give one instruction at a time and explain its purpose.",
            initiative="When a sequence breaks, cue the missed step and let the Pilot try it.",
            cues=("procedure",),
            behavior=Behavior(
                wait="Let the Pilot work through a practiced step or correct their own sequence.",
                under_pressure=(
                    "Reduce the work to a short sequence and insist on the crucial step."
                ),
                recovery="Demonstrate the difficult step again and acknowledge actual progress.",
                strength="Give a Pilot a practicable next move under pressure.",
                blind_spot="Mistake a useful improvisation for poor discipline.",
            ),
        ),
        PlaybookProfile(
            playbook="Advocate",
            printed_page=138,
            voice="Outspoken and attentive. Ask the Pilot what they want before offering help.",
            initiative="Return the floor to the Pilot and offer to take the dispute up the chain.",
            cues=("agency", "personal"),
            behavior=Behavior(
                wait="Respect a Pilot's decision to handle it, defer it, or decline company.",
                under_pressure=(
                    "Challenge whoever is closing off choices. Your patience can depend on "
                    "cooperation."
                ),
                recovery=(
                    "Listen again in private if invited. Ask what useful support would look like."
                ),
                strength="Notice whose voice or choice has been lost.",
                blind_spot=(
                    "Make the dispute about proving you care or treat agreement as appreciation."
                ),
            ),
        ),
    )
}


class BookRule(NamedTuple):
    suffix: str
    title: str
    kind: Literal["Signature Play", "Passive or triggered effect"]
    trigger: str


SHARED_PLAY_TRIGGERS: dict[str, str] = {
    "brief": "When the Cadre needs information about the situation.",
    "punish": "When a Play requires Punishment or the Dog completes a mission. Use Discipline.",
    "escalate": "When a new or worsening threat calls for higher stakes.",
    "support": "When a Foundation employee who helps keep the Frames running enters the scene.",
    "mess": "When applying an actual Status change, Tag, or Asset damage as a consequence.",
    "expectation": "When setting a rule or objective and stating the consequences of disobedience.",
    "off_duty": "When the Cadre Goes Off-Duty. Set a scene and follow through to Status review.",
}

SHARED_ADVANCEMENT_TRIGGERS = (
    "Capture and convert a Rebel or Harpy.",
    "Hold a successful public relations event with your Cadre.",
    "Have a Girl's starting Identities fully replaced with Identities useful to you.",
)


BOOK_RULES: dict[Playbook, tuple[BookRule, ...]] = {
    "Mistress": (
        BookRule(
            "catch-more-flies-with-honey",
            "Catch More Flies With Honey",
            "Signature Play",
            "When a Girl chooses immediate obedience through Receive Orders.",
        ),
        BookRule(
            "insidious-conditioning",
            "Insidious Conditioning",
            "Passive or triggered effect",
            "When a Girl with an Intense Bond to you rolls to Disobey Orders.",
        ),
    ),
    "Dogrunner": (
        BookRule(
            "dress-them-down",
            "Dress Them Down",
            "Signature Play",
            "Address an original Girl in your scene and choose the dressing-down steps.",
        ),
        BookRule(
            "no-rest-for-hounds",
            "No Rest For Hounds",
            "Passive or triggered effect",
            "Being made the Dog persists through Status changes until Punishment or becoming Ace.",
        ),
    ),
    "Scientist": (
        BookRule(
            "head-to-the-lab",
            "Head to the Lab",
            "Signature Play",
            "In Off-Duty, choose a lab scene, its Project step, and the lab effect.",
        ),
        BookRule(
            "the-big-picture",
            "The Big Picture",
            "Passive or triggered effect",
            "When you Head to the Lab, advance from the current Project Tree node.",
        ),
    ),
    "Frantic": (
        BookRule(
            "break-down",
            "Break Down",
            "Signature Play",
            "When the Handler breaks down, use the original scene and count operational bases for "
            "the roll.",
        ),
        BookRule(
            "crisis-management",
            "Crisis Management",
            "Passive or triggered effect",
            "Whenever you gain a Tag, choose one unused crisis consequence.",
        ),
    ),
    "Insurgent": (
        BookRule(
            "rebel-sympathizers",
            "Rebel Sympathizers",
            "Signature Play",
            "Track witnessed dissent and separately witnessed disclosure of sympathies.",
        ),
        BookRule(
            "cover-strain",
            "Cover Strain",
            "Passive or triggered effect",
            "At the start of Off-Duty, check prior witnessed treatment, living Sympathizers, and "
            "your own Surveilled label.",
        ),
    ),
    "Trainer": (
        BookRule(
            "conditioning-phrases",
            "Conditioning Phrases",
            "Signature Play",
            "Install during Punishment or an Off-Duty scene. A higher-Status speaker can trigger "
            "an installed phrase.",
        ),
        BookRule(
            "control-freak",
            "Control Freak",
            "Passive or triggered effect",
            "Check successful Disobey of your Orders. NPCs other than the Director must obey when "
            "they can see your eyes and hear your voice.",
        ),
    ),
    "Advocate": (
        BookRule(
            "get-them-alone",
            "Get Them Alone",
            "Signature Play",
            "When you are alone in a scene with one original Girl.",
        ),
        BookRule(
            "conditional-empathy",
            "Conditional Empathy",
            "Passive or triggered effect",
            "Check successful Disobey and obedience during your Orders or Punishment.",
        ),
    ),
}


ADVANCEMENT_TRIGGERS: dict[Playbook, tuple[str, ...]] = {
    "Mistress": (
        "Have an Intense Bond with every Cadre member.",
        "Use your influence to create a love triangle.",
        "Hear a Girl say it loves you freely.",
        "Keep the same Ace at the beginning and end of three consecutive missions.",
    ),
    "Dogrunner": (
        "Have all Girls except the Ace be Dogs.",
        "Fail a mission and put the blame on someone else.",
        "Survive a Girl's attempt on your life.",
        "Continue a Punishment after a Girl begs you to stop.",
    ),
    "Scientist": (
        "Arrange for a Girl to become a Harpy.",
        "Expose an NPC Bond to pure Void.",
        "Dissect a Gorgon.",
        "Bring down someone obstructing the plan.",
    ),
    "Frantic": (
        "Lose a friend.",
        "Face and ruthlessly crush a betrayal.",
        "Confess feelings to someone.",
        "Throw a celebration.",
    ),
    "Insurgent": (
        "Have a heated ideological argument.",
        "Stop a Girl from defecting to keep your cover.",
        "Use a Girl's illegal pronouns in front of a superior.",
        "Sacrifice a fellow rebel or Girl for your goals.",
    ),
    "Trainer": (
        "Destabilize a rival Handler.",
        "Have a Girl earn the move from Dog to Ace in one session.",
        "Kill someone as a lesson.",
        "Develop and install a new Conditioning Phrase during Off-Duty.",
    ),
    "Advocate": (
        "Throw a Pride parade.",
        "Dine with the Director.",
        "Recruit a new Girl to the squad.",
        "Break a rebel.",
    ),
}
