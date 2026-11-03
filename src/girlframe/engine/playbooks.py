"""Creation labels, not mechanics. JANUS-B is the owner's server variant of JANUS."""

GIRL_TYPES: dict[str, str] = {
    "PRINCESS": "Princess",
    "MOCKINGBIRD": "Mockingbird",
    "STIM-BLISSED": "Stim-Blissed",
    "NEWGIRL": "Newgirl",
    "CASUALTY": "Casualty",
    "OLDGEN": "Oldgen",
    "VATGROWN": "Vatgrown",
    "ALPHA": "Alpha",
    "AM": "AM (Artificial Mind)",
    "BONDED": "Bonded",
}
FRAME_TYPES: dict[str, str] = {
    "THE PRINCE": "The Prince",
    "CONSUME": "CONSUME",
    "JANUS": "JANUS",
    "JANUS-B": "JANUS-B (server variant)",
    "DOCTORDOCTOR MK. II": "DoctorDoctor Mk. II",
    "WYVERN 0.4": "Wyvern 0.4",
    "THE ENFORCER": "The Enforcer",
    "CHANGELING": "CHANGELING",
    "PROJECT ANKOU": "Project Ankou",
    "THE RED QUEEN": "The Red Queen",
}


def canonical_girl(value: str) -> str:
    key = value.strip().upper()
    if key == "AM (ARTIFICIAL MIND)":
        key = "AM"
    if key not in GIRL_TYPES:
        raise ValueError("Select a listed Girl type")
    return key


def canonical_frame(value: str) -> str:
    key = value.strip().upper()
    if key not in FRAME_TYPES:
        raise ValueError("Select a listed Frame type")
    return key
