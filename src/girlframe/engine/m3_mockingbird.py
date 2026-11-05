"""Owned Mockingbird mechanics act on real original resources, preserving raw dice."""

from typing import TYPE_CHECKING

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup, corrupt
from girlframe.engine.m3_girl_runtime_state import has_rule

if TYPE_CHECKING:
    from girlframe.engine.m2 import TagState
    from girlframe.engine.m3_mockingbird_state import Conversation, Party
    from girlframe.engine.m3_void_state import HarpyTag
    from girlframe.engine.m3_world_state import AdversaryPilot, Gorgon, Npc, WorldTag

RISK = "girl.mockingbird.risk-factor"
CALL = "girl.mockingbird.call-of-the-void"
PERSON = "girl.mockingbird.bad-at-being-a-person"
SEX = "girl.mockingbird.sex-play"


class RiskPayment(Model):
    action: str = Field(min_length=1)
    actor: ActorRef
    event: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    family: str = Field(min_length=1)
    total_before: int
    total_after: int = Field(ge=8, le=10)
    account: str = Field(min_length=1, max_length=1200)


def owns(state: GameState, actor: ActorRef, identity: str) -> bool:
    if identity not in (RISK, CALL, PERSON, SEX):
        return False
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        return bool(
            sheet
            and sheet.character_id == actor.incarnation
            and has_rule(sheet, identity, "MOCKINGBIRD")
        )
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        return identity in getattr(harpy(state, actor), "plays", ())
    return False


def risk(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    action: str,
    event: str,
    asset: str,
    description: str,
    before: int,
    after: int,
    *,
    piloting: bool,
) -> tuple[GameState, tuple[Followup, ...], RiskPayment]:
    """The player pays real Void to choose an actual 8, 9 or 10 after modifiers."""
    from girlframe.engine.m3_dive import _harpy_assets, resources

    if not owns(original, actor, RISK) or any(
        x.get("kind") == "mockingbird_risk_paid" and x.get("action") == action
        for x in original.facts
    ):
        raise ValueError("Use this actual original person's currently owned unused Risk Factor")
    view = resolve(original, actor, bindings, require_current_profile=False)
    if (
        not view.alive
        or not action.strip()
        or not event.strip()
        or type(after) is not int
        or after not in (8, 9, 10)
    ):
        raise ValueError("Choose an actual 8, 9 or 10 for this real original roll")
    actual, _ = resources(original, actor)
    selected = next((x for x in actual if x.id == asset and not x.void), None)
    if selected is None or not description.strip() or len(description) > 1200:
        raise ValueError("Risk Factor requires an actual uncorrupted owned Asset's Void alteration")
    if actor.kind == "pilot":
        own_frame = (
            view.inside_frame is True and view.occupied_frame_instance == view.frame_instance
        )
        context = own_frame if view.inside_frame is not None else piloting
        paid = corrupt(original.sheets[actor.entity], asset, description, piloting=context)
        changed = GameState.model_validate_json(original.model_dump_json())
        changed.sheets[actor.entity] = paid.sheet
        followups = paid.followups
    else:
        from girlframe.engine.m3_harpy_defeat import assets

        changed = _harpy_assets(
            GameState.model_validate_json(original.model_dump_json()),
            actor,
            tuple(
                x.model_copy(update={"void": True, "description": description})
                if x.id == asset
                else x
                for x in assets(original, actor)
            ),
            event=event,
        )
        followups = ()
    payment = RiskPayment(
        action=action,
        actor=actor,
        event=event,
        asset=asset,
        family=selected.family,
        total_before=before,
        total_after=after,
        account=description,
    )
    changed.facts.append(
        dict(
            kind="mockingbird_risk_paid",
            action=action,
            event=event,
            actor=actor.model_dump_json(),
            body=payment.model_dump_json(),
        )
    )
    return changed, followups, payment


def same_person(state: GameState, original: ActorRef, current: ActorRef) -> bool:
    if original == current:
        return True
    if original.kind == current.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, original) and same_handler_body(state, current)
    if current.kind != "external_pilot":
        return False
    from girlframe.engine.m3_tag_permissions import conversion

    try:
        body, _ = conversion(state, current)
    except ValueError:
        return False
    return body.origin == original


def actor_tags(state: GameState, actor: ActorRef) -> tuple["TagState | HarpyTag | WorldTag", ...]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Use this actual original person's current Tags")
        return tuple(sheet.tags)
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, actor):
            raise ValueError("Use the actual current Handler body, never a successor")
        return tuple(state.handler_tags)
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        try:
            return tuple(harpy(state, actor).tags)
        except ValueError:
            pass
    if state.world:
        groups: dict[str, tuple[Npc | AdversaryPilot | Gorgon, ...]] = {
            "npc": state.world.npcs,
            "external_pilot": state.world.pilots,
            "gorgon": state.world.gorgons,
        }
        rows = groups.get(actor.kind, ())
        entity = next((x for x in rows if x.id == actor.entity and x.alive), None)
        if entity:
            return tuple(entity.tags)
    raise ValueError("Recover the actual Tag holder's living original body")


def give_tag(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    recipient: ActorRef,
    giver: ActorRef,
    label: str,
    identity: str,
    event: str,
    observers: tuple[int, ...],
) -> GameState:
    from girlframe.engine.m2 import TagState
    from girlframe.engine.m3_harpy_defeat import update
    from girlframe.engine.m3_void_state import HarpyTag
    from girlframe.engine.m3_world_state import WorldTag

    if not label.strip() or len(label) > 120 or not event or not identity:
        raise ValueError("An actual Tag needs its owned label and immutable source event")
    state = GameState.model_validate_json(original.model_dump_json())
    setter = resolve(state, giver, bindings, require_current_profile=False)
    target = resolve(state, recipient, bindings, require_current_profile=False)
    if (
        not setter.alive
        or not target.alive
        or any(x.id == identity for x in actor_tags(state, recipient))
    ):
        raise ValueError("Use the actual living source giver, recipient and new Tag identity")
    if recipient.kind in ("pilot", "handler"):
        value = TagState(
            id=identity,
            label=label,
            giver=setter.controller,
            giver_actor=giver,
            observers=observers,
        )
        if recipient.kind == "pilot":
            state.sheets[recipient.entity].tags.append(value)
            state.sheets[recipient.entity].revision += 1
        else:
            state.handler_tags.append(value)
    elif recipient.kind == "external_pilot" and target.girl == "harpy":
        state = update(
            state,
            recipient,
            tags=(
                *actor_tags(state, recipient),
                HarpyTag(
                    id=identity,
                    label=label,
                    giver=setter.controller,
                    giver_ref=giver,
                    observers=observers,
                ),
            ),
        )
    else:
        assert state.world is not None
        field = {"npc": "npcs", "external_pilot": "pilots", "gorgon": "gorgons"}[recipient.kind]
        rows = getattr(state.world, field)
        state.world = state.world.model_copy(
            update={
                field: tuple(
                    row.model_copy(
                        update={
                            "tags": (
                                *row.tags,
                                WorldTag(
                                    id=identity, label=label, giver_entity=giver.model_dump_json()
                                ),
                            )
                        }
                    )
                    if row.id == recipient.entity
                    else row
                    for row in rows
                )
            }
        )
    state.facts.append(
        dict(
            kind="mockingbird_tag",
            actor=recipient.model_dump_json(),
            giver=giver.model_dump_json(),
            tag=identity,
            event=event,
        )
    )
    return state


def starry_capabilities(
    state: GameState, speaker: ActorRef, counterpart: ActorRef
) -> tuple[str, ...]:
    if counterpart.kind == "pilot" and (
        counterpart.entity not in state.sheets
        or state.sheets[counterpart.entity].character_id != counterpart.incarnation
    ):
        converted = next(
            (
                ActorRef(kind="external_pilot", entity=body.id)
                for body in state.harpy_states
                if body.alive
                and same_person(state, counterpart, ActorRef(kind="external_pilot", entity=body.id))
            ),
            None,
        )
        if converted is not None:
            counterpart = converted
    result = []
    ids = {x.id for x in actor_tags(state, counterpart)}
    for grant in state.mockingbird.starry:
        if (
            same_person(state, grant.speaker, speaker)
            and same_person(state, grant.holder, counterpart)
            and grant.tag in ids
        ):
            if counterpart != grant.holder and counterpart.kind == "external_pilot":
                from girlframe.engine.m3_tag_permissions import conversion

                _, proof = conversion(state, counterpart)
                if grant.tag not in proof["retained_tag_ids"]:
                    continue
            result.append(grant.capability)
    return tuple(dict.fromkeys(result))


def choose_capabilities(
    original: GameState,
    actor: ActorRef,
    action: str,
    event: str,
    level: str,
    choices: tuple[str, ...],
    counterparts: tuple["Party", ...],
) -> tuple[GameState, "Conversation"]:
    from uuid import NAMESPACE_URL, uuid5

    from girlframe.engine.m3_mockingbird_state import CAPABILITIES, Conversation

    count = {"mid": 3, "high": 4, "low": 2}[level]
    if (
        len(set(choices)) != len(choices)
        or not set(choices) <= set(CAPABILITIES)
        or (not 0 <= len(choices) <= count if level == "low" else len(choices) != count)
        or not counterparts
        or any(x.actor == actor for x in counterparts)
    ):
        raise ValueError("Choose the printed number of distinct conversation capabilities")
    state = GameState.model_validate_json(original.model_dump_json())
    if any(x.action == action for x in state.mockingbird.conversations):
        raise ValueError("This original conversation already has its actual capability choice")
    # A Starry grant is counterpart-specific. Common extras apply to every actual interlocutor;
    # an individual grant remains shown to that holder separately by the UI projection.
    common = set(CAPABILITIES)
    for party in counterparts:
        common &= set(starry_capabilities(state, actor, party.actor))
    allowed = tuple(x for x in CAPABILITIES if x in set(choices) | common)
    value = Conversation(
        id=str(uuid5(NAMESPACE_URL, "girlframe:conversation:" + action)),
        actor=actor,
        counterparts=counterparts,
        action=action,
        source_event=event,
        allowed=allowed,
        selected=tuple(x for x in CAPABILITIES if x in choices),
        unavailable=tuple(x for x in CAPABILITIES if x not in allowed),
        low=level == "low",
    )
    state.mockingbird = state.mockingbird.model_copy(
        update={"conversations": (*state.mockingbird.conversations, value)}
    )
    return state, value


def conversation_capabilities(
    state: GameState, conversation: "Conversation", counterpart: ActorRef | None = None
) -> tuple[str, ...]:
    """Actual current Tag grants never become permanent native capabilities."""
    from girlframe.engine.m3_mockingbird_state import CAPABILITIES

    selected = conversation.selected if conversation.selected is not None else conversation.allowed
    counterparts = (
        (counterpart,)
        if counterpart is not None
        else tuple(x.actor for x in conversation.counterparts)
    )
    if counterpart is not None and not any(
        same_person(state, party.actor, counterpart) for party in conversation.counterparts
    ):
        raise ValueError("Use one actual original conversation counterpart")
    common = set(CAPABILITIES)
    for party in counterparts:
        common &= set(starry_capabilities(state, conversation.actor, party))
    return tuple(x for x in CAPABILITIES if x in set(selected) | common)


def require_departure(
    state: GameState, actor: ActorRef, conversation_id: str | None = None
) -> None:
    for conversation in state.mockingbird.conversations:
        if conversation_id is not None and conversation.id != conversation_id:
            continue
        if (
            conversation.low
            and not conversation.ended_event
            and same_person(state, conversation.actor, actor)
        ):
            if not all(x.actor in conversation.released for x in conversation.counterparts):
                raise ValueError(
                    "The original interlocutors must actually allow you to leave this conversation"
                )
