"""Original bodies, factual brain access and current-vessel morphology; no proxy resources."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _actual(game: "GameService", c: Connection, state: GameState, actor: ActorRef) -> ActorView:
    return resolve(
        state,
        actor,
        snapshot_profiles(c, game.store.campaign_id, state),
        require_current_profile=False,
    )


def _fact(game: "GameService", c: Connection, state: GameState, actor: ActorRef) -> rules.BodyFact:
    actual = _actual(game, c, state, actor)
    if (
        actor.kind == "npc"
        and state.world
        and any(
            item.id == actor.entity and item.source_kind == "wyvern_wraith"
            for item in state.world.npcs
        )
    ):
        raise WorkflowError("SOURCE_PHYSICAL_BRAIN_REQUIRED: a Wraith is not a biological brain")
    values = [
        item
        for item in rules.records(state, rules.BodyFact)
        if item.actor == actor and (actual.vessel_id is None or item.vessel == actual.vessel_id)
    ]
    if len(values) != 1:
        raise WorkflowError(
            "SOURCE_BODY_FACT_REQUIRED: establish this original body's actual brain"
        )
    value = values[0]
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != "m3.changeling_body_proved"
        or row["actor_id"] != str(value.controller)
    ):
        raise WorkflowError("Recover the original human-authored factual body evidence")
    saved = _history(c, game, value.event)
    if rules.record(saved, rules.BodyFact, value.id) != value:
        raise WorkflowError("Preserve original brain, vessel and factual author")
    if value.reset_source or value.reset_record:
        from girlframe.engine.m3_am_reset import body as reset_body
        from girlframe.engine.m3_am_reset import prove as prove_reset

        reset = reset_body(state, actor)
        if (
            reset is None
            or value.kind != "other"
            or reset.id != value.reset_record
            or reset.source_event != value.reset_source
            or actual.vessel_id != reset.body.vessel_id
            or value.vessel != reset.body.vessel_id
        ):
            raise WorkflowError(
                "Preserve actual reset hardware; do not substitute a human or new brain"
            )
        prove_reset(state, reset)
        if reset_body(
            _history(c, game, reset.source_event), actor
        ) != reset or value.brain != rules.identity("brain", reset.original.token, value.vessel):
            raise WorkflowError(
                "Prove the canonical reset body and original physical brain reference"
            )
    return value


def prove_original_brain(
    game: "GameService", c: Connection, state: GameState, expected: rules.BrainRef
) -> rules.BodyFact:
    """Prove a historical original factual brain without resolving its ended actor now."""
    born = _history(c, game, expected.source)
    value = _fact(game, c, born, expected.actor)
    if (
        value not in rules.records(state, rules.BodyFact)
        or value.brain != expected.id
        or value.vessel != expected.vessel
        or value.event != expected.source
        or value.kind != expected.kind
    ):
        raise WorkflowError("Preserve the original canonical brain and body factual source")
    return value


def brain(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    *,
    purpose: str,
) -> rules.BrainRef:
    value = _fact(game, c, state, actor)
    actual = _actual(game, c, state, actor)
    from girlframe.engine.m3_casualty import part_state

    if part_state(state, actor, "brain") in ("destroyed", "removed"):
        raise WorkflowError("Use the actual still-present brain")
    return rules.BrainRef(
        id=value.brain,
        actor=actor,
        vessel=value.vessel,
        kind=value.kind,
        controller=actual.controller,
        source=value.event,
    )


def context(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    cast: SceneCast,
    play: str,
    target: ActorRef | None = None,
) -> dict[str, Any]:
    actual = _actual(game, c, state, actor)
    own = brain(game, c, state, actor, purpose="mental")
    if not any(role.actor == actor for role in cast.roles):
        raise WorkflowError("Use the actual role in this real source scene")
    if play == "changeling_body_of_clay" and (
        actual.inside_frame is not True or actual.frame_instance != rules.frame(state, actor)
    ):
        raise WorkflowError("Allow the actual original Frame to change the body actually inside it")
    return dict(
        brain=own.model_dump(mode="json"),
        vessel=own.vessel,
        frame=actual.frame_instance,
        inside_frame=actual.inside_frame,
        target=brain(game, c, state, target, purpose="mental").model_dump(mode="json")
        if target
        else None,
    )


def validate_access(
    game: "GameService",
    c: Connection,
    state: GameState,
    caster: ActorRef,
    target: ActorRef,
    cast: SceneCast,
    condition: str,
    account: str,
    event: str,
) -> dict[str, Any]:
    own, other = _actual(game, c, state, caster), _actual(game, c, state, target)
    if condition not in ("unconscious", "helpless", "unexpecting") or not account.strip():
        raise WorkflowError("Record the actual original Handler's finite witnessed access facts")
    if caster == target or not {caster, target} <= {role.actor for role in cast.roles}:
        raise WorkflowError("Actual access concerns distinct real co-present scene roles")
    if own.cell is None or own.cell != other.cell:
        raise WorkflowError("SOURCE_PHYSICAL_ACCESS_REQUIRED: establish actual bodily access")
    subject = brain(game, c, state, target, purpose="implant")
    placement = next((item for item in state.placements if item.actor == target), None)
    sheet = state.sheets.get(target.entity) if target.kind == "pilot" else None
    if condition == "unconscious" and not (sheet and sheet.medical_state == "unconscious_injured"):
        raise WorkflowError(
            "SOURCE_UNCONSCIOUS_PRODUCER_REQUIRED: use actual medical unconsciousness"
        )
    if condition == "helpless":
        from girlframe.engine.m3_actor_bonds import is_helpless

        # The shared query distinguishes source-qualified conditions from
        # unqualified bodily effects such as Psych Whip (printed p81).
        if not is_helpless(state, target, caster) and not (placement and placement.incapacitated):
            raise WorkflowError("Use actual current Helplessness, not a narrative substitute")
    return dict(
        caster=own.ref.model_dump(mode="json"),
        subject=subject.model_dump(mode="json"),
        cell=list(own.cell),
        cast_sha256=fingerprint(cast),
        condition=condition,
        account=account,
        event=event,
    )


def recheck_access(
    game: "GameService", c: Connection, state: GameState, value: rules.Access
) -> None:
    from girlframe.services.m3_dose_up import _cast

    current = _cast(game, c, state, value.cast.channel)
    if fingerprint(current) != fingerprint(value.cast):
        raise WorkflowError("Reopen actual original access before the scene changes")
    facts = validate_access(
        game,
        c,
        state,
        value.actor,
        value.subject.actor,
        current,
        value.condition,
        value.account,
        value.event,
    )
    if json.dumps(facts, sort_keys=True) != value.facts:
        raise WorkflowError("Preserve the original actual physical access and brain")


def current_appearance(state: GameState, actor: ActorRef, vessel: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for fact in state.facts:
        if fact.get("kind") == rules.KINDS[rules.Appearance]:
            value = rules.Appearance.model_validate_json(fact["body"])
            if value.actor == actor and value.vessel == vessel:
                values.update(value.values)
        elif fact.get("kind") == rules.KINDS[rules.FacetChange]:
            patch = rules.FacetChange.model_validate_json(fact["body"])
            if patch.actor == actor and patch.brain.vessel == vessel:
                values.update(patch.values)
    return values


def appearance_choices(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: ActorRef,
) -> list[dict[str, Any]]:
    result = []
    for value in rules.records(state, rules.AppearanceDisclosure):
        if value.addressed != owner:
            continue
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["kind"] != "m3.changeling_appearance_disclosed"
            or row["actor_id"] != str(value.controller)
        ):
            raise WorkflowError("Recover the actual original witnessed appearance disclosure")
        if (
            rules.record(_history(c, game, value.event), rules.AppearanceDisclosure, value.id)
            != value
        ):
            raise WorkflowError("Preserve the actual appearance fact and original human")
        actual = _actual(game, c, state, value.actor)
        appearance = rules.record(state, rules.Appearance, value.appearance)
        if (
            appearance.actor != value.actor
            or actual.vessel_id
            and appearance.vessel != actual.vessel_id
        ):
            continue
        values = value.values
        if set(values) != set(rules.FACETS):
            continue
        result.append(
            dict(
                id=value.id,
                label=actual.label,
                actor=value.actor.model_dump(mode="json"),
                source=value.event,
                values=values,
            )
        )
    return result


def change_body(
    game: "GameService",
    c: Connection,
    state: GameState,
    change: rules.FacetChange,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    actual = _actual(game, c, state, change.actor)
    current = brain(game, c, state, change.actor, purpose="morphology")
    source = rules.session(state, change.session)
    if (
        not rules.same_brain(current, change.brain)
        or change.event != event
        or source.actor != change.actor
        or source.frame != change.frame
        or source.play != "changeling_body_of_clay"
        or change.frame != actual.frame_instance
        or actual.inside_frame is not True
        or not set(change.values) <= set(rules.FACETS)
        or any(not text.strip() or len(text) > 1200 for text in change.values.values())
    ):
        raise WorkflowError(
            "Change only actual permitted facets of the real body inside its original Frame"
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    # The source-owned typed FacetChange is the actual current-vessel morphology producer.
    # It never rewrites legal gender, original creation, Asset inventory or brain identity.
    rules.put(changed, change)
    return changed, ()


def validate_start_brain(
    game: "GameService",
    c: Connection,
    before: GameState,
    after: GameState,
    start: rules.StartingBond,
    subject: rules.BrainRef,
    event: str,
) -> None:
    if start.subject != subject.actor or start.node or start.attached_event:
        raise WorkflowError("Bind the original starting Bond's actual person once")
    fact = _fact(game, c, after, subject.actor)
    if fact.brain != subject.id or fact.vessel != subject.vessel:
        raise WorkflowError("Preserve the original person and actual brain source")
    prior = [item for item in rules.records(before, rules.BodyFact) if item.actor == subject.actor]
    if prior and any(item.brain != subject.id or item.vessel != subject.vessel for item in prior):
        raise WorkflowError(
            "A later replacement brain cannot inherit a starting String by account alias"
        )


def reconditioning_candidates(
    game: "GameService",
    c: Connection,
    before: GameState,
    after: GameState,
    actor: ActorRef,
    asset: str,
    event: str,
    source: str,
) -> tuple[rules.Reconditioning, ...]:
    prior, actual = _actual(game, c, before, actor), _actual(game, c, after, actor)
    old = next((item for item in prior.assets if item.id == asset), None)
    new = next((item for item in actual.assets if item.id == asset), None)
    if old is None or new is None or old.damaged or not new.damaged:
        return ()
    result = []
    from girlframe.services.m3_changeling import _available, prove_acquisition

    if not _available(game, rules.RECONDITION):
        return ()
    for sheet in before.sheets.values():
        if sheet.frame != rules.FRAME or not sheet.character_id:
            continue
        owner = ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id)
        held = rules.held(before, owner, rules.RECONDITION)
        if held is None:
            continue
        prove_acquisition(game, c, before, held)
        host = _actual(game, c, before, owner)
        if host.inside_frame is not True:
            continue
        if actor != owner:
            pose = next((item for item in before.placements if item.actor == actor), None)
            if (
                pose is None
                or pose.mode != "inside_frame"
                or pose.occupied_frame_owner != owner
                or pose.occupied_frame_instance != host.frame_instance
            ):
                continue
        elif prior.inside_frame is not True:
            continue
        subject = brain(game, c, after, actor, purpose="reconditioning")
        cast = next(
            (
                item
                for item in reversed(after.scene_casts)
                if item.open and {actor, owner} <= {role.actor for role in item.roles}
            ),
            None,
        )
        if cast is None:
            # Ordinary Plays can retain a genuine legacy cast through their
            # original scene bind/join events without materializing scene_casts.
            # Recover only this damage source's exact saved Action and scene.
            actions = t.m2["m2_actions"]
            action = c.execute(
                sa.select(actions.c.channel_id, actions.c.scene_id).where(
                    actions.c.campaign_id == game.store.campaign_id,
                    actions.c.id == source,
                )
            ).first()
            if action is not None:
                from girlframe.services.m3_dose_up import _cast

                actual_cast = _cast(game, c, after, int(action.channel_id))
                if (
                    actual_cast.id == action.scene_id
                    and actual_cast.open
                    and {actor, owner} <= {role.actor for role in actual_cast.roles}
                ):
                    cast = actual_cast
        if cast is None:
            raise WorkflowError("SOURCE_RECONDITIONING_SCENE_REQUIRED: retain actual cockpit roles")
        result.append(
            rules.Reconditioning(
                id=rules.identity("reconditioning", source, event, owner.token, actor.token, asset),
                actor=owner,
                frame=rules.frame(before, owner),
                subject=subject,
                asset=asset,
                source=source,
                source_event=event,
                cast=cast,
                controller=host.controller,
                event=event,
            )
        )
    return tuple(result)
