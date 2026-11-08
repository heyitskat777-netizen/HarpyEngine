"""Pure compulsory replacement. Girl state and Permissions are never reset/charged."""

from girlframe.engine.frame_setup import HarpyCore
from girlframe.engine.m2 import AssetState, GameState, IdentityState, TagState, pair_key
from girlframe.engine.m3_frame_state import FrameRuntime, Package, Preferences
from girlframe.engine.playbooks import FRAME_TYPES, canonical_frame
from girlframe.engine.rules_registry import Registry
from girlframe.engine.shared_setup import AM_ROLES


def different_frame(current: str, selected: str) -> str:
    frame = canonical_frame(selected)
    frame = "JANUS-B" if frame == "JANUS" else frame
    previous = canonical_frame(current)
    previous = "JANUS-B" if previous == "JANUS" else previous
    if frame not in FRAME_TYPES or frame == previous:
        raise ValueError("Choose a different official core Frame playbook")
    return frame


def preferences(
    current: str, selected: Preferences, owner: int, people: frozenset[int]
) -> Preferences:
    frame = different_frame(current, selected.frame)
    if frame == "THE PRINCE":
        if selected.fanbase is None or selected.fanbase.missing():
            raise ValueError("The Prince requires the player's complete fanbase choices")
    elif selected.fanbase is not None:
        raise ValueError("Fanbase choices belong to The Prince only")
    if frame == "THE RED QUEEN":
        if (
            selected.court_role is None
            or selected.court_target not in people
            or selected.court_target == owner
        ):
            raise ValueError("Choose an external Court role and another current character")
    elif selected.court_role is not None or selected.court_target is not None:
        raise ValueError("Court choices belong to The Red Queen only")
    return selected.model_copy(update={"frame": frame})


def package(
    state: GameState, owner: int, selected: Preferences, supplied: Package, registry: Registry
) -> None:
    frame = selected.frame
    if not supplied.explanation.strip():
        raise ValueError("The Handler must describe the exact replacement package")
    if len(set(supplied.additional_rules)) != len(supplied.additional_rules):
        raise ValueError("Additional rules must be distinct")
    for identity in supplied.additional_rules:
        entry = registry.require_available(identity)
        if entry.scope != "frame" or entry.kind not in ("mechanic", "play"):
            raise ValueError("A replacement package may only grant specific supported Frame rules")
    intrinsic = 1 if frame == "WYVERN 0.4" else 0
    if len(supplied.assets) > 5:
        raise ValueError("The ordinary package must fit the five-Asset cap; Enormous is additional")
    if intrinsic and any(x.name.strip().casefold() == "enormous" for x in supplied.assets):
        raise ValueError("Enormous is already supplied as the printed intrinsic Asset")
    if (supplied.consume_hunger is not None) != (frame == "CONSUME"):
        raise ValueError("The Handler must explicitly set hunger for CONSUME only")
    if (supplied.obsolescence_marked is not None) != (frame == "DOCTORDOCTOR MK. II"):
        raise ValueError("The Handler must explicitly set the DoctorDoctor track only")
    if frame != "CHANGELING" and supplied.psych_strings:
        raise ValueError("Psych Strings belong to CHANGELING only")
    if len(set(supplied.psych_strings)) != len(supplied.psych_strings):
        raise ValueError("Choose distinct Psych String targets")
    for target in supplied.psych_strings:
        if target == owner or not state.bonds.get(pair_key(owner, target)):
            raise ValueError("Initial Psych Strings must reference actual current Bonds")


def replace(
    original: GameState,
    owner: int,
    selected: Preferences,
    supplied: Package,
    registry: Registry,
    *,
    work_id: str,
    frame_id: str,
    court_accepted: bool,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(str(owner))
    if sheet is None or not sheet.frame_scrapped:
        raise ValueError("A current compulsory replacement requirement is needed")
    people = frozenset(int(uid) for uid in state.sheets) | (
        frozenset({state.handler}) if state.handler else frozenset()
    )
    selected = preferences(sheet.frame, selected, owner, people)
    package(state, owner, selected, supplied, registry)
    if selected.frame == "THE RED QUEEN" and not court_accepted:
        raise ValueError("The external Court recipient must explicitly accept its assignment")
    generation = sheet.frame_runtime.generation + 1 if sheet.frame_runtime else 1
    court: dict[str, int] = {}
    if selected.frame == "THE RED QUEEN":
        if selected.court_target is None:
            raise ValueError("An explicit external Court recipient is required")
        court = {
            role: selected.court_target if role == selected.court_role else owner
            for role in AM_ROLES
        }
    runtime = FrameRuntime(
        id=frame_id,
        generation=generation,
        source_work=work_id,
        frame_name=selected.frame_name,
        frame_appearance=selected.frame_appearance,
        core_id=frame_id + ":core" if selected.frame == "JANUS-B" else None,
        harpy_core=HarpyCore() if selected.frame == "JANUS-B" else None,
        fanbase=selected.fanbase,
        court=court,
        consume_hunger=supplied.consume_hunger,
        psych_strings=supplied.psych_strings,
        acquired_rules=supplied.additional_rules,
    )
    sheet.assets = [x for x in sheet.assets if x.family == "girl"]
    sheet.assets.extend(
        AssetState(id=frame_id + ":asset:" + str(index), family="frame", **asset.model_dump())
        for index, asset in enumerate(supplied.assets)
    )
    if selected.frame == "WYVERN 0.4":
        sheet.assets.append(
            AssetState(
                id=frame_id + ":intrinsic",
                family="frame",
                name="Enormous",
                intrinsic="wyvern_enormous",
            )
        )
    if selected.fanbase:
        sheet.identities.extend(
            IdentityState(id=frame_id + ":fan:" + str(i), name=name, protected=True)
            for i, name in enumerate(selected.fanbase.additional_identities)
        )
    if selected.court_target == state.handler and selected.court_role:
        state.handler_tags.append(
            TagState(id=frame_id + ":handler-am", label=selected.court_role, giver=owner)
        )
    sheet.frame = selected.frame
    sheet.frame_runtime = runtime
    sheet.obsolescence_marked = supplied.obsolescence_marked or 0
    sheet.frame_scrapped = False
    sheet.revision += 1
    return GameState.model_validate_json(state.model_dump_json())
