"""Source-bound Punishment effects. Unsupported branches never count as applied."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import (
    AssetState,
    GameState,
    IdentityState,
    Model,
    TagState,
    pair_key,
    shift_status,
)

KINDS = {
    "sedation": ("Sedation", "minor"),
    "beating": ("Beating", "minor"),
    "revoked_privileges": ("Revoked Privileges", "minor"),
    "reduced_socialization": ("Reduced Socialization", "minor"),
    "quality_time": ("Quality Time", "minor"),
    "demotion": ("Demotion", "minor"),
    "stimulant_injection": ("Stimulant Injection", "minor"),
    "passing_responsibility": ("Passing Responsibility", "minor"),
    "correctional_programming": ("Correctional Programming", "moderate"),
    "frame_disassembly": ("Frame Disassembly", "moderate"),
    "compliance_surgery": ("Compliance Surgery", "moderate"),
    "strict_regulations": ("Strict Regulations", "moderate"),
    "libido_inhibitor": ("Libido Inhibitor", "moderate"),
    "execution": ("Execution", "severe"),
    "lobotomization": ("Lobotomization", "severe"),
    "indefinite_imprisonment": ("Indefinite Imprisonment", "severe"),
    "link_surgery_reversal": ("Link Surgery Reversal", "severe"),
}
SUPPORTED = frozenset(KINDS) - {
    "revoked_privileges",
    "strict_regulations",
    "execution",
    "lobotomization",
    "indefinite_imprisonment",
    "link_surgery_reversal",
}


class Details(Model):
    kind: str = Field(max_length=80)
    identities: tuple[str, ...] = Field(default=(), max_length=2)
    asset: str | None = Field(default=None, max_length=100)
    tag: str = Field(default="", max_length=120)
    bond_with: int | None = Field(default=None, gt=0)
    replacement_name: str = Field(default="", max_length=120)
    replacement_description: str = Field(default="", max_length=1200)
    embrace_tag: str | None = Field(default=None, max_length=100)
    delegate: int | None = Field(default=None, gt=0)


class Followup(Model):
    kind: Literal["helpless", "ankou_feedback", "paired_identity_heat", "void_threshold_check"]
    owner: int
    source_pdf: int
    details: dict[str, str] = Field(default_factory=dict)


class Applied(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def last_girl_asset_context(
    original: GameState, subject: int, inflictor: int, *, piloting: bool
) -> GameState:
    if type(piloting) is not bool:
        raise ValueError("Record the actual Frame context when the Asset was damaged")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(str(subject))
    if (
        sheet is None
        or not any(x.family == "girl" for x in sheet.assets)
        or any(x.family == "girl" and not x.damaged for x in sheet.assets)
    ):
        raise ValueError("Resolve the changed Girl Asset state before this follow-up")
    if not piloting:
        sheet.helpless_against = tuple(sorted(set(sheet.helpless_against) | {inflictor}))
        sheet.revision += 1
    state.facts.append(
        {"kind": "beating_frame_context", "owner": str(subject), "piloting": str(piloting)}
    )
    return state


def validate(details: Details) -> str:
    details = Details.model_validate_json(details.model_dump_json())
    if details.kind not in KINDS:
        raise ValueError("Choose a printed Punishment type")
    if details.kind not in SUPPORTED:
        raise ValueError("UNSUPPORTED_RULE: this Punishment needs its remaining runtime mechanics")
    allowed = {
        "sedation": {"identities"},
        "beating": {"asset", "tag"},
        "reduced_socialization": {"bond_with"},
        "quality_time": {"tag"},
        "passing_responsibility": {"delegate"},
        "correctional_programming": {"identities", "embrace_tag"},
        "frame_disassembly": {"asset"},
        "compliance_surgery": {"asset", "replacement_name", "replacement_description"},
    }.get(details.kind, set())
    defaults = Details(kind=details.kind)
    for field in Details.model_fields:
        if (
            field != "kind"
            and field not in allowed
            and getattr(details, field) != getattr(defaults, field)
        ):
            raise ValueError("This Punishment includes unrelated choices")
    return KINDS[details.kind][1]


def apply(
    original: GameState,
    subject: int,
    inflictor: int,
    details: Details,
    *,
    entity_id: str,
    off_duty: bool,
    handler_consulted: bool = False,
) -> Applied:
    severity = validate(details)
    if inflictor != original.handler and str(inflictor) not in original.sheets:
        raise ValueError("A current Handler or Pilot must inflict the Punishment")
    if severity == "severe" and inflictor != original.handler:
        raise ValueError("Only the Handler can inflict Severe Punishments")
    if severity == "moderate" and inflictor != original.handler and not handler_consulted:
        raise ValueError("HANDLER_CONSULT_REQUIRED: consult the current Handler first")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(str(subject))
    if sheet is None:
        raise ValueError("Punishment requires a current canonical Pilot")
    required: list[Followup] = []
    kind = details.kind
    if kind == "passing_responsibility":
        raise ValueError("Delegation transfers pending work; it does not apply a Punishment")
    if kind == "sedation":
        chosen = [x for x in sheet.identities if x.id in details.identities]
        count = min(2, len(sheet.identities))
        if len(details.identities) != count or len(chosen) != count:
            raise ValueError(
                "Sedation: select two distinct current Identities, or all remaining if fewer"
            )
        was_full = all(x.marked for x in sheet.identities)
        sheet.heat = 0
        for identity in chosen:
            if identity.paired and not identity.marked:
                required.append(Followup(kind="paired_identity_heat", owner=subject, source_pdf=58))
            identity.marked = True
        if off_duty:
            sheet.sedation_locked = tuple(
                sorted(set(sheet.sedation_locked) | set(details.identities))
            )
        if (
            sheet.frame == "PROJECT ANKOU"
            and not was_full
            and all(x.marked for x in sheet.identities)
        ):
            required.append(Followup(kind="ankou_feedback", owner=subject, source_pdf=84))
    elif kind in ("beating", "frame_disassembly", "compliance_surgery"):
        asset = next((x for x in sheet.assets if x.id == details.asset), None)
        family = "frame" if kind == "frame_disassembly" else "girl"
        if asset is None or asset.family != family or (kind == "beating" and asset.damaged):
            raise ValueError(
                "Choose a current Asset of the required family; damage needs an undamaged Asset"
            )
        if kind == "beating":
            asset.damaged = True
            if all(x.damaged for x in sheet.assets if x.family == "girl"):
                required.append(
                    Followup(
                        kind="helpless",
                        owner=subject,
                        source_pdf=15,
                        details={"inflictor": str(inflictor), "requires_outside_frame": "true"},
                    )
                )
        else:
            sheet.assets.remove(asset)
            if kind == "compliance_surgery":
                if (
                    not details.replacement_name.strip()
                    or not details.replacement_description.strip()
                ):
                    raise ValueError("Name and describe the replacement Girl Asset")
                sheet.assets.append(
                    AssetState(
                        id=entity_id,
                        family="girl",
                        name=details.replacement_name.strip(),
                        description=details.replacement_description.strip(),
                    )
                )
            if any(x.family == family for x in sheet.assets) and all(
                x.void for x in sheet.assets if x.family == family
            ):
                required.append(Followup(kind="void_threshold_check", owner=subject, source_pdf=19))
    elif kind == "reduced_socialization":
        if details.bond_with is None or details.bond_with == subject:
            raise ValueError("Choose a current Bond counterpart")
        key = pair_key(subject, details.bond_with)
        if state.bonds.get(key, 0) < 1:
            raise ValueError("Choose a current Bond")
        state.bonds[key] -= 1
        if state.bonds[key] == 0:
            del state.bonds[key]
    elif kind == "quality_time":
        if subject == inflictor:
            raise ValueError("A self-Bond is not a legal Quality Time target")
        key = pair_key(subject, inflictor)
        depth = state.bonds.get(key, 0)
        if depth >= 2:
            other = state.sheets.get(str(inflictor))
            sheet.heat += 2
            if other is not None:
                other.heat += 2
                other.revision += 1
            else:
                state.handler_heat += 2
        else:
            state.bonds[key] = depth + 1
    elif kind == "demotion":
        shift_status(state, subject, -1)
    elif kind == "stimulant_injection":
        sheet.heat += 7
    elif kind == "correctional_programming":
        if details.embrace_tag:
            tag = next((x for x in sheet.tags if x.id == details.embrace_tag), None)
            if tag is None:
                raise ValueError("Choose a current Tag to embrace")
            ordinary = [x for x in sheet.identities if not x.protected or x.paired]
            if len(ordinary) >= 4:
                if len(details.identities) != 1:
                    raise ValueError("Choose the Identity replaced at the cap")
            elif details.identities:
                raise ValueError("Do not erase another Identity when below the cap")
            if tag.label.casefold() in {x.name.casefold() for x in sheet.identities}:
                raise ValueError("The embraced Tag would duplicate an Identity")
            sheet.tags.remove(tag)
            sheet.identities.append(IdentityState(id=entity_id, name=tag.label))
        elif len(details.identities) != 1:
            raise ValueError("Choose one Identity to remove, or a Tag to embrace")
        if details.identities:
            selected = next((x for x in sheet.identities if x.id == details.identities[0]), None)
            if selected is None or (
                selected.protected and (not selected.paired or inflictor != subject)
            ):
                raise ValueError("An inflictor cannot remove another player's protected Identity")
            if details.embrace_tag and selected.paired:
                sheet.identities[-1].paired = True
                sheet.identities[-1].protected = True
            sheet.identities.remove(selected)
            sheet.sedation_locked = tuple(x for x in sheet.sedation_locked if x != selected.id)
    elif kind == "libido_inhibitor":
        sheet.libido_inhibited = True
    if kind in ("beating", "quality_time"):
        if not details.tag.strip():
            raise ValueError("Write the inflicted Tag")
        sheet.tags.append(TagState(id=entity_id, label=details.tag.strip(), giver=inflictor))
    sheet.revision += 1
    return Applied(
        state=GameState.model_validate_json(state.model_dump_json()), followups=tuple(required)
    )
