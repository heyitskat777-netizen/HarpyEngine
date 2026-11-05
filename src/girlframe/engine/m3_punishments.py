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
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_identity_slots import replacement_slot

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
SUPPORTED = frozenset(KINDS)


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
    regulation: str = Field(default="", max_length=1200)
    requisition: str | None = Field(default=None, max_length=100)
    restoration: str = Field(default="", max_length=1200)
    disclosed: bool = True
    surgery: str | None = Field(default=None, max_length=100)


class Followup(Model):
    kind: Literal[
        "helpless", "ankou_feedback", "paired_identity_heat", "void_threshold_check", "frame_loss"
    ]
    owner: int
    source_pdf: int
    details: dict[str, str] = Field(default_factory=dict)


class Applied(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


def last_girl_asset_context(
    original: GameState,
    subject: int,
    inflictor: int,
    *,
    inside_frame: bool,
    source_event: str,
    removal_proven: bool = False,
    foe: ActorRef | None = None,
) -> GameState:
    from girlframe.engine.m3_actor_bonds import current_ref, make_helpless

    if type(inside_frame) is not bool:
        raise ValueError("Record whether the original body was actually inside a Frame")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(str(subject))
    if (
        sheet is None
        or any(x.family == "girl" and not x.damaged for x in sheet.assets)
        or not any(x.family == "girl" for x in sheet.assets)
        and not removal_proven
    ):
        raise ValueError("Recover the actual last-Girl-Asset damage or proved removal source")
    if not inside_frame:
        state = make_helpless(
            state, current_ref(state, subject), foe or current_ref(state, inflictor), source_event
        )
    state.facts.append(
        {
            "kind": "last_girl_asset_frame_context",
            "owner": str(subject),
            "inside_frame": str(inside_frame),
        }
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
        "revoked_privileges": {"requisition", "restoration"},
        "beating": {"asset", "tag"},
        "reduced_socialization": {"bond_with"},
        "quality_time": {"tag"},
        "passing_responsibility": {"delegate"},
        "correctional_programming": {"identities", "embrace_tag"},
        "frame_disassembly": {"asset"},
        "compliance_surgery": {"asset", "replacement_name", "replacement_description"},
        "strict_regulations": {"regulation", "disclosed"},
        "lobotomization": {"surgery"},
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
    off_duty_period: str | None = None,
    allow_duplicate_labels: bool = False,
    source_event: str | None = None,
    character_ids: dict[int, str] | None = None,
    profile_context: dict[int, tuple[str, int]] | None = None,
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
    if off_duty_period is not None and (not off_duty or not off_duty_period.strip()):
        raise ValueError("A Sedation period requires an actual current Off-Duty context")
    required: list[Followup] = []
    kind = details.kind
    from girlframe.engine.m3_girl_runtime_state import has_rule

    if kind != "passing_responsibility" and has_rule(
        sheet, "girl.alpha.nothing-more-than-a-hound", "ALPHA"
    ):
        sheet.status_marked = False
    if kind == "lobotomization":
        from girlframe.engine.m3_lobotomy import apply as apply_surgery

        if details.surgery is None or source_event is None:
            raise ValueError("Prepare the actual source-bound experimental surgery first")
        return Applied(
            state=apply_surgery(
                state, details.surgery, source_event, allow_duplicate_labels=allow_duplicate_labels
            )
        )
    if kind in ("execution", "indefinite_imprisonment", "link_surgery_reversal"):
        from girlframe.engine import m3_careers as careers
        from girlframe.engine.m3_actor_state import ActorRef

        character = (character_ids or {}).get(subject, sheet.character_id)
        if character is None or not source_event:
            raise ValueError("Record the original character and actual severe Punishment source")
        actor = ActorRef(kind="pilot", entity=str(subject), incarnation=character)
        if kind == "link_surgery_reversal":
            return Applied(
                state=careers.unlink(
                    state,
                    actor,
                    source_event=source_event,
                    account="Handler-imposed Link Surgery Reversal",
                )
            )
        current = careers.binding(state, subject)
        profile_id, profile_revision = (profile_context or {}).get(
            subject,
            (
                current.profile_id if current else character,
                sheet.source_profile_revision,
            ),
        )
        ended = careers.end(
            state,
            actor,
            reason="execution" if kind == "execution" else "imprisonment",
            source_event=source_event,
            account="Handler-imposed " + KINDS[kind][0],
            archive_id=entity_id,
            profile_id=profile_id,
            profile_revision=profile_revision,
        )
        return Applied(state=ended)
    if kind == "passing_responsibility":
        raise ValueError("Delegation transfers pending work; it does not apply a Punishment")
    if kind == "revoked_privileges":
        from girlframe.engine.m3_privileges import revoke

        state = revoke(
            state,
            subject,
            inflictor,
            details.requisition,
            details.restoration,
            entity_id,
            source_event or "",
            character_ids or {},
        )
        sheet = state.sheets[str(subject)]
        lost_girl = [
            x
            for x in original.sheets[str(subject)].assets
            if x.family == "girl" and not any(y.id == x.id for y in sheet.assets)
        ]
        if lost_girl and not any(x.family == "girl" and not x.damaged for x in sheet.assets):
            required.append(
                Followup(
                    kind="helpless",
                    owner=subject,
                    source_pdf=15,
                    details={
                        "inflictor": str(inflictor),
                        "requires_outside_frame": "true",
                        "removed_asset": lost_girl[0].id,
                        "removal_source": source_event or "",
                    },
                )
            )
        if (
            any(x.family == "frame" and not x.void for x in original.sheets[str(subject)].assets)
            and any(x.family == "frame" for x in sheet.assets)
            and all(x.void for x in sheet.assets if x.family == "frame")
        ):
            required.append(Followup(kind="void_threshold_check", owner=subject, source_pdf=19))
    elif kind == "strict_regulations":
        from girlframe.engine.m3_regulations import impose

        state.regulations.append(
            impose(
                state,
                subject,
                inflictor,
                details.regulation,
                details.disclosed,
                entity_id,
                source_event or "",
                character_ids,
            )
        )
    elif kind == "sedation":
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
            if off_duty_period is not None and (
                sheet.sedation_locked and sheet.sedation_period != off_duty_period
            ):
                raise ValueError("Resolve existing Sedation scope before applying another period")
            sheet.sedation_locked = tuple(
                sorted(set(sheet.sedation_locked) | set(details.identities))
            )
            if off_duty_period is not None:
                sheet.sedation_period = off_duty_period
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
            if not allow_duplicate_labels and tag.label.casefold() in {
                x.name.casefold() for x in sheet.identities
            }:
                raise ValueError("The embraced Tag would duplicate an Identity")
            sheet.tags.remove(tag)
            locked = bool(set(details.identities) & set(sheet.sedation_locked))
            sheet.identities.append(
                IdentityState(
                    id=entity_id,
                    name=tag.label,
                    marked=locked,
                    slot=replacement_slot(
                        sheet, details.identities[0] if details.identities else None
                    ),
                )
            )
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
            if details.embrace_tag and sheet.identities[-1].marked:
                sheet.sedation_locked += (entity_id,)
    elif kind == "libido_inhibitor":
        sheet.libido_inhibited = True
    if kind in ("beating", "quality_time"):
        if not details.tag.strip():
            raise ValueError("Write the inflicted Tag")
        sheet.tags.append(TagState(id=entity_id, label=details.tag.strip(), giver=inflictor))
    removed_frame = {x.id for x in original.sheets[str(subject)].assets if x.family == "frame"} - {
        x.id for x in sheet.assets if x.family == "frame"
    }
    if removed_frame and not any(x.family == "frame" and not x.damaged for x in sheet.assets):
        character = (character_ids or {}).get(subject, sheet.character_id)
        details_at_loss = {
            "character": character or "",
            "frame": sheet.frame_runtime.id
            if sheet.frame_runtime
            else "initial:" + (character or ""),
        }
        placement = next(
            (
                x
                for x in original.placements
                if x.actor.kind == "pilot"
                and x.actor.entity == str(subject)
                and x.actor.incarnation == character
                and x.frame_instance == details_at_loss["frame"]
            ),
            None,
        )
        if placement is not None:
            details_at_loss["piloting"] = str(placement.mode == "piloting")
        required.append(
            Followup(kind="frame_loss", owner=subject, source_pdf=29, details=details_at_loss)
        )
    sheet.revision += 1
    return Applied(
        state=GameState.model_validate_json(state.model_dump_json()), followups=tuple(required)
    )
