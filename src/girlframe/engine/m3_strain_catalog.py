"""Short UI paraphrases for choosing table columns; source pages live in m3_strain.

These labels do not execute or waive the event's complete printed mechanics.
"""

from girlframe.engine.m3_strain_state import Severity, Track

ROWS: dict[tuple[Track, Severity], tuple[tuple[str, str], ...]] = {
    ("void", "low"): (
        (
            "A Directed Gorgon targets a city",
            "A Girl's next Frame entry forces a modified Dive Deep",
        ),
        ("A quiet Gorgon appears near a base", "The next arriving Gorgon brings Sprites"),
        ("A patrol encounters a Harpy", "Public appearance, with consequences for failure"),
        ("A city faces an Aggressive Gorgon", "A Benevolent Gorgon offers a favour or interest"),
        ("A Sprite has already caught an NPC", "A Girl discovers an NPC's Void interest"),
        ("An orbital Gorgon threatens a location", "The Cadre faces a Void medical examination"),
    ),
    ("void", "high"): (
        ("A Harpy attacks the Cadre's base", "An NPC Bond is a Doppleganger Gorgon"),
        ("Void spreads across connected map squares", "An unnoticed Harpy enters a Girl's bunk"),
        (
            "An altered defeated Gorgon returns",
            "A cult occupies a location around its Harpy messiah",
        ),
        (
            "A Frame's next activation causes a Gorgon crisis",
            "Directors demand action on Pilot fears",
        ),
        ("The Handler makes a new Void revelation Play", "A Gorgon forces contact or grants Void"),
        (
            "An opening in the sky brings repeated threats",
            "Roll both severity tables or choose an Endgame",
        ),
    ),
    ("rebellion", "low"): (
        ("A city hides a new Rebel Group", "The next Disobey Orders gets a bonus"),
        ("A Rebel Pilot flies past the base", "A Girl may keep smuggled contraband as an Asset"),
        (
            "The Director orders a protest dealt with",
            "A leak requires killing its authors or an apology",
        ),
        ("A Rebel Handler taunts; Tag and future Punishment", "A prisoner attempts escape"),
        ("A Rebel Pilot plans a capture attack", "A Girl secretly contacts a nearby NPC"),
        ("Rebels establish a distant base", "An NPC Bond faces a defection deadline"),
    ),
    ("rebellion", "high"): (
        ("Rebel Pilots attack the Handler or Ace", "A protest threatens control of a city"),
        ("Rebels overrun an unattended base", "A Rebel Handler offers a Girl an escape"),
        ("An NPC Bond attempts an assassination", "The Director orders a show of rebel sympathy"),
        ("A Rebel Pilot targets a Girl every mission", "Disobedience may create a Control Ritual"),
        (
            "A Rebel Handler imitates the Handler's orders",
            "A backstory Tag can make the Handler Helpless",
        ),
        ("A Rebel Pilot attempts Frame theft", "Roll both severity tables or choose an Endgame"),
    ),
    ("budget", "low"): (
        ("A publicity shoot gives each Girl a Tag", "A rich patron bonds with a Girl"),
        ("The Cadre attends a patron's event", "Two Assets conceal future equipment failures"),
        ("Scientists demand Void Observation", "A supply shortage penalizes one Off-Duty roll"),
        (
            "Mission-site cleanup or Void exposure",
            "Limit free repairs after this or the next mission",
        ),
        ("A visiting official may demand reparations", "Shared rooms deepen the occupants' Bonds"),
        ("The Cadre must assassinate a politician", "An NPC Bond loses their job"),
    ),
    ("budget", "high"): (
        (
            "Director meeting with another player; Handler Heat",
            "Fuel delays cause an unavoidable loss",
        ),
        ("The next mission must capture a new Pilot", "Supply delays give everyone a Tag"),
        (
            "A Girl must face potential Severe Punishment",
            "A new political faction imposes sanctions",
        ),
        ("Two Girls must fight on television", "The table defines a Pilot Candidate's assessment"),
        ("A city falls into anarchy", "A Foundation Pilot attacks to frame the Handler"),
        ("A Frame must enter storage", "Roll both severity tables or choose an Endgame"),
    ),
}

ENDGAMES = {
    "void": (
        "Leave outside the Quadrant and discuss continuing",
        "Open a stable laboratory portal",
        "Handler retires and is replaced",
        "Offer one Girl retirement",
        "The Handler's next Void gain is unnoticed",
        "Handler advancement, first slot",
        "Handler advancement, second slot",
    ),
    "rebellion": (
        "An opportunity to eliminate a rebel leader",
        "Rebel funding collapse and merger",
        "Ancillary lesson (disabled)",
        "Rebels reshape Foundation operations",
        "Secretly fund the new rebel opposition",
        "Become an outright rebel Handler",
        "Handler execution and a new compliant Handler",
        "A more dangerous group replaces them",
    ),
    "budget": (
        "Warcrime trials and a possible rescue",
        "Handler demoted; another player takes over",
        "Two major locations fall to ruin",
        "Every Girl loses a Girl and a Frame Asset",
        "A Girl gives the Handler a persistent Tag",
        "Collective off-duty Tags on the Handler",
        "Several NPC Bonds leave or die",
    ),
}
