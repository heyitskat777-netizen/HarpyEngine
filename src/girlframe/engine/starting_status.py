"""Foundation conformity recommendation for the rulebook's optional Status metric."""

from collections.abc import Mapping

from girlframe.engine.playbooks import canonical_frame, canonical_girl

# Rulebook pp. 12 and 28–88 supply the qualitative metric and archetype descriptions.
# These values express the Foundation's fictional evaluation for Session Zero.
GIRL_WEIGHTS = {
    "PRINCESS": 4,
    "OLDGEN": 3,
    "NEWGIRL": 2,
    "BONDED": 1,
    "CASUALTY": 0,
    "VATGROWN": -1,
    "STIM-BLISSED": -2,
    "MOCKINGBIRD": -3,
    "ALPHA": -3,
    "AM": -4,
}
FRAME_WEIGHTS = {
    "THE PRINCE": 3,
    "DOCTORDOCTOR MK. II": 2,
    "THE ENFORCER": 1,
    "THE RED QUEEN": 1,
    "PROJECT ANKOU": 0,
    "WYVERN 0.4": -1,
    "CONSUME": -2,
    "JANUS": -2,
    "CHANGELING": -3,
}


def recommendation(pilots: Mapping[int, tuple[str, str, str]]) -> list[dict[str, str | int]]:
    candidates = [
        (owner, name, canonical_girl(girl), canonical_frame(frame))
        for owner, (name, girl, frame) in pilots.items()
    ]
    scores = {
        owner: (GIRL_WEIGHTS[girl], FRAME_WEIGHTS[frame]) for owner, _, girl, frame in candidates
    }
    candidates.sort(
        key=lambda item: (
            item[2] != "PRINCESS",
            -sum(scores[item[0]]),
            item[1].casefold(),
            item[0],
        )
    )
    return [
        {
            "owner": str(owner),
            "callsign": name,
            "girl_weight": scores[owner][0],
            "frame_weight": scores[owner][1],
            "score": sum(scores[owner]),
        }
        for owner, name, _, _ in candidates
    ]
