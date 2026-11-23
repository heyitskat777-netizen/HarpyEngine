"""Conversation prompts for the printed NPC jobs on pages 187–189."""

PROMPTS: dict[str, tuple[str, ...]] = {
    "base_personnel": (
        "Keep the facility working.",
        "Step out of the spotlight.",
        "React to an unexpected disturbance.",
    ),
    "civilian": (
        "Avoid attracting attention.",
        "Find a reason to leave.",
        "React to something you cannot explain.",
    ),
    "creep": (
        "Make an inappropriate remark.",
        "Try to exploit somebody's vulnerability.",
        "Make an excuse that sounds plausible.",
    ),
    "doctor": (
        "Describe a procedure and its effect on the patient.",
        "Offer treatment for a concrete injury.",
        "Record an observation from the examination.",
    ),
    "ex_pilot": (
        "Go along with the plan.",
        "Flinch at something familiar.",
        "Give tired advice from experience.",
    ),
    "family": (
        "Ask for more than the Girl can give.",
        "Focus on the wrong issue.",
        "Point out a change and ask the Girl to address it.",
    ),
    "fan": (
        "Ask an intrusive question with misplaced enthusiasm.",
        "Go after a personal keepsake.",
        "Turn up somewhere you are unwelcome.",
    ),
    "guard": (
        "Step between someone and a destination.",
        "Try to restrain someone.",
        "Bring a weapon into the scene.",
    ),
    "handler": (
        "Ask a Girl to carry out your bidding.",
        "Reveal a backup plan.",
        "Gloat about an advantage.",
    ),
    "intelligence_agent": (
        "Pursue a lead somebody tried to conceal.",
        "Offer a false name, job or purpose.",
        "Get out of the spotlight.",
    ),
    "journalist": (
        "Request an interview.",
        "Put a direct question to someone.",
        "Take a picture that may cause trouble.",
    ),
    "mechanic": (
        "Tell a Girl how she mishandled her Frame.",
        "Offer to fix a concrete fault.",
        "Make a joke during a repair.",
    ),
    "patron": (
        "Indulge in a luxury.",
        "Offer something the Girl wants.",
        "Ask the Girls for an uncomfortable favor.",
    ),
    "pilot_candidate": (
        "Overestimate your readiness.",
        "Try to hide your enthusiasm.",
        "Ask to enter a Frame and pursue candidacy.",
    ),
    "prisoner": (
        "Find a small way to defy authority.",
        "Show the cost of captivity.",
        "Point out what you have in common.",
    ),
    "protestor": (
        "Gather fellow protestors.",
        "Voice an actual grievance with a slogan.",
        "Threaten to escalate the protest.",
    ),
    "psychologist": (
        "Give a directive that challenges an Identity.",
        "Ask a probing question.",
        "Consider what private information to share.",
    ),
    "public_relations": (
        "State a concrete public expectation.",
        "Suggest a change in appearance.",
        "Try to contain an embarrassing situation.",
    ),
    "scientist": (
        "Justify the work.",
        "Put the result ahead of other priorities.",
        "Propose an experiment involving Void.",
    ),
    "smuggler": (
        "Offer something outside the supply rules.",
        "React with contempt.",
        "Offer to hide a person or object.",
    ),
}
