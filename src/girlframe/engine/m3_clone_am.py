"""One artificial person in the original Frame; one actual shared Heat authority."""

from uuid import NAMESPACE_URL, uuid4, uuid5

from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, TagState, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_class_grafts import held
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.autocrat.clone-am"


class CloneAM(Model):
    id: str
    original: ActorRef
    frame: str
    receipt: str
    source_event: str
    revision: int = 1
    identity: IdentityState
    tags: tuple[TagState, ...] = ()

    @property
    def ref(self) -> ActorRef:
        return ActorRef(kind="clone_am", entity=self.id)


def copies(state: GameState) -> tuple[CloneAM, ...]:
    return tuple(
        CloneAM.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "clone_am"
    )


def put(state: GameState, value: CloneAM) -> None:
    if value.identity.protected or value.identity.paired or value.identity.slot is not None:
        raise ValueError("The copy has one ordinary, separate replaceable Identity")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "clone_am" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="clone_am", id=value.id, body=value.model_dump_json()))


def create(state: GameState, receipt: FrameRuleReceipt) -> CloneAM:
    if receipt.rule_id != RULE or any(x.receipt == receipt.id for x in copies(state)):
        raise ValueError("Create only one copy from the actual original Clone AM purchase")
    identity = str(uuid5(NAMESPACE_URL, "clone-am:" + receipt.id))
    value = CloneAM(
        id=receipt.id,
        original=receipt.actor,
        frame=receipt.frame_instance,
        receipt=receipt.id,
        source_event=receipt.source_event,
        identity=IdentityState(id=identity, name="Perfect Copy"),
    )
    put(state, value)
    return value


def find(state: GameState, ref: ActorRef) -> CloneAM | None:
    return next((x for x in copies(state) if ref == x.ref), None)


def current(state: GameState, ref: ActorRef) -> CloneAM:
    value = find(state, ref)
    if value is None:
        raise ValueError("Recover the actual original Frame-resident copy")
    paid = held(state, value.original, RULE)
    if paid is None or (paid.id, paid.frame_instance, paid.source_event) != (
        value.receipt,
        value.frame,
        value.source_event,
    ):
        raise ValueError("Restore the original copy's actual Frame entitlement")
    return value


def owner(state: GameState, ref: ActorRef) -> PilotSheet:
    value = current(state, ref)
    sheet = state.sheets.get(value.original.entity)
    if sheet is None or sheet.character_id != value.original.incarnation:
        raise ValueError("Recover the original copy's actual shared Heat owner")
    return sheet


def additional_identities(state: GameState, owner: int) -> tuple[IdentityState, ...]:
    result = []
    for value in copies(state):
        if value.original.entity == str(owner):
            try:
                current(state, value.ref)
            except ValueError:
                continue
            result.append(value.identity)
    return tuple(result)


def mark_additional(
    state: GameState, sheet: PilotSheet, entry: str, gain: int, share: int = 0
) -> int | None:
    value = next(
        (
            x
            for x in copies(state)
            if x.identity.id == entry and x.original.entity == str(sheet.owner)
        ),
        None,
    )
    if value is None:
        return None
    actual = owner(state, value.ref)
    if (
        actual.character_id != sheet.character_id
        or value.identity.marked
        or not 1 <= gain <= 3
        or share
    ):
        raise ValueError("Mark the original unmarked copy Identity for one to three shared Heat")
    from girlframe.engine.m3_leviathan_obsession import require_identity_gain

    require_identity_gain(state, value.original, entry)
    put(
        state,
        value.model_copy(
            update=dict(
                identity=value.identity.model_copy(update=dict(marked=True)),
                revision=value.revision + 1,
            )
        ),
    )
    sheet.heat += gain
    return 0


def unmark_additional(
    state: GameState, owner: int, selected: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    available = {x.id for x in additional_identities(state, owner)}
    if selected is not None and (len(set(selected)) != len(selected) or set(selected) - available):
        raise ValueError("Choose only this original copy's actual Identity IDs")
    changed = []
    for value in copies(state):
        if (
            value.original.entity != str(owner)
            or selected is not None
            and value.identity.id not in selected
        ):
            continue
        try:
            current(state, value.ref)
        except ValueError:
            if selected is not None:
                raise
            continue
        if selected is not None and not value.identity.marked:
            raise ValueError("Unmark only this copy's actual marked Identity")
        if value.identity.marked:
            put(
                state,
                value.model_copy(
                    update=dict(
                        identity=value.identity.model_copy(update=dict(marked=False)),
                        revision=value.revision + 1,
                    )
                ),
            )
            changed.append(value.identity.id)
    return tuple(changed)


def commit(
    state: GameState, ref: ActorRef, identity: str | None, gain: int, heat: int, share: int
) -> None:
    value = current(state, ref)
    sheet = owner(state, ref)
    if identity:
        if (
            identity != value.identity.id
            or mark_additional(state, sheet, identity, gain, share) is None
        ):
            raise ValueError("Use this copy's own actual Identity")
    elif gain or share:
        raise ValueError("Gain Heat only from this copy's actual Identity")
    spend_heat(sheet, heat)
    sheet.revision += 1


def tags(state: GameState, ref: ActorRef) -> tuple[TagState, ...]:
    return current(state, ref).tags


def tag(state: GameState, ref: ActorRef, identity: str, **changes: object) -> None:
    value = current(state, ref)
    if not any(x.id == identity for x in value.tags):
        raise ValueError("Use the original copy's actual Tag")
    put(
        state,
        value.model_copy(
            update=dict(
                tags=tuple(
                    x.model_copy(update=changes) if x.id == identity else x for x in value.tags
                ),
                revision=value.revision + 1,
            )
        ),
    )


def add_tag(
    state: GameState,
    ref: ActorRef,
    label: str,
    participants: tuple[int, ...],
    *,
    giver: ActorRef | None = None,
) -> None:
    value = current(state, ref)
    put(
        state,
        value.model_copy(
            update=dict(
                tags=(
                    *value.tags,
                    TagState(
                        id=str(uuid4()),
                        label=label.strip(),
                        giver=int(value.original.entity) if giver is None else int(giver.entity),
                        giver_actor=giver or ref,
                        observers=participants,
                    ),
                ),
                revision=value.revision + 1,
            )
        ),
    )


def embrace(state: GameState, ref: ActorRef, identity: str, replaced: tuple[str, ...]) -> None:
    value = current(state, ref)
    selected = next((x for x in value.tags if x.id == identity and x.marked), None)
    if selected is None or replaced != (value.identity.id,):
        raise ValueError("Embrace the actual marked Tag by replacing the copy's sole Identity")
    put(
        state,
        value.model_copy(
            update=dict(
                identity=IdentityState(id=str(uuid4()), name=selected.label),
                tags=tuple(x for x in value.tags if x.id != identity),
                revision=value.revision + 1,
            )
        ),
    )
    clear_tag_debt(state, ref, identity)


def reject(state: GameState, ref: ActorRef, identity: str) -> None:
    value = current(state, ref)
    if not any(x.id == identity and x.rejection_pending for x in value.tags):
        raise ValueError("Take the actual owed action to reject this copy's Tag")
    put(
        state,
        value.model_copy(
            update=dict(
                tags=tuple(x for x in value.tags if x.id != identity), revision=value.revision + 1
            )
        ),
    )
    clear_tag_debt(state, ref, identity)


def clear_tag_debt(state: GameState, ref: ActorRef, identity: str) -> None:
    for item in state.obligations:
        if (
            item.kind == "clone_cannot_refuse_until_tag_resolved"
            and item.state == "pending"
            and item.details.get("actor") == ref.model_dump_json()
            and item.details.get("tag") == identity
        ):
            item.state = "fulfilled"


def cannot_refuse(state: GameState, ref: ActorRef, other: ActorRef) -> bool:
    return any(
        item.kind == "clone_cannot_refuse_until_tag_resolved"
        and item.state == "pending"
        and item.details.get("actor") == ref.model_dump_json()
        and item.details.get("target_actor") == other.model_dump_json()
        for item in state.obligations
    )


def require_play(ref: ActorRef, play: str) -> None:
    if ref.kind == "clone_am" and play == "dive_deep":
        raise ValueError("Clone AM cannot Dive Deep")
