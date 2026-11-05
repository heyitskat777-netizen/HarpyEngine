"""Original-person obsession locks and exact-source Heat restrictions."""

from collections.abc import Iterable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_leviathan_obsession_state import (
    GrantedIdentity,
    IdentityAuthority,
    Obsession,
)


def authority(state: GameState, actor: ActorRef) -> IdentityAuthority | None:
    ref = subject_ref(state, actor)
    return next((x for x in state.leviathan_identity_authorities if x.actor == ref), None)


def install_authority(
    original: GameState,
    actor: ActorRef,
    ordinary_ids: tuple[str, ...],
    event: str,
    *,
    owner: int,
    judge: int,
    identities: tuple[GrantedIdentity, ...] = (),
    mentor: ActorRef | None = None,
) -> GameState:
    """Trusted actual owner + frozen judge factual responses; no baseline/Heat is created."""
    from girlframe.engine.m3_actors import resolve

    if actor.kind != "external_pilot" or owner <= 0 or judge <= 0 or not event.strip():
        raise ValueError(
            "Review the actual existing external person's identities and source humans"
        )
    actual = resolve(original, actor, (), require_current_profile=False)
    if actual.controller != owner or len(set(ordinary_ids)) != len(ordinary_ids):
        raise ValueError("Only this actual original body's owner supplies distinct ordinary IDs")
    state = GameState.model_validate_json(original.model_dump_json())
    previous = authority(state, actor)
    if _harpy(state, actor):
        if identities:
            raise ValueError("Do not copy/reset an actual Harpy's existing resource authority")
        values = pool(state, actor)
        if not set(ordinary_ids) <= {x.id for x in values if not x.protected and not x.paired}:
            raise ValueError(
                "Identify actual eligible Harpy slots; protected extras/Pair stay intact"
            )
        if len(ordinary_ids) + sum(x.paired for x in values) > 4:
            raise ValueError("Identify at most four actual ordinary/Paired slots")
        if (
            previous is not None
            and previous.role == "harpy_review"
            and (
                set(previous.reviewed_ids) == {x.id for x in values}
                and previous.ordinary != ordinary_ids
            )
        ):
            raise ValueError("Do not reclassify the same actual identities to evade a known result")
        record = IdentityAuthority(
            actor=actor,
            role="harpy_review",
            ordinary=ordinary_ids,
            reviewed_ids=tuple(x.id for x in values),
            event=event,
            owner=owner,
            judge=judge,
            revision=previous.revision + 1 if previous else 1,
        )
    else:
        body = (
            next((x for x in state.world.pilots if x.id == actor.entity), None)
            if state.world
            else None
        )
        if body is None or body.kind not in ("foundation", "rebel") or previous is not None:
            raise ValueError(
                "Import only first factual Foundation/Rebel identities; never reset a pool"
            )
        if not set(ordinary_ids) <= {x.id for x in identities if not x.protected and not x.paired}:
            raise ValueError("The actual ordinary pointers must preserve protected extras and Pair")
        if len(ordinary_ids) + sum(x.paired for x in identities) > 4:
            raise ValueError("The actual existing ordinary/Paired slots have a four-slot cap")
        if any(x.obsession_sources for x in identities):
            raise ValueError("A factual import cannot fabricate preexisting source-lock provenance")
        if body.girl.upper() == "NEWGIRL":
            if mentor is None or mentor == actor:
                raise ValueError("Record this actual Newgirl's existing original Mentor")
            if mentor.kind == "pilot":
                mentor_sheet = state.sheets.get(mentor.entity)
                if mentor_sheet is None or mentor_sheet.character_id != mentor.incarnation:
                    raise ValueError("Use the actual original Mentor character")
            elif mentor.kind == "external_pilot":
                assert state.world is not None
                if not any(x.id == mentor.entity for x in state.world.pilots):
                    raise ValueError("Use the actual known external Girl Mentor")
            else:
                raise ValueError("A Newgirl's Mentor is another actual Girl")
        record = IdentityAuthority(
            actor=actor,
            role="external_factual",
            identities=identities,
            ordinary=ordinary_ids,
            reviewed_ids=tuple(x.id for x in identities),
            event=event,
            owner=owner,
            judge=judge,
            mentor=mentor,
        )
    state.leviathan_identity_authorities = [
        x for x in state.leviathan_identity_authorities if x.actor != actor
    ] + [record]
    state.facts.append(
        dict(
            kind="leviathan_identity_authority",
            actor=actor.model_dump_json(),
            event=event,
            body=record.model_dump_json(),
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def _harpy(state: GameState, actor: ActorRef) -> bool:
    return actor.kind == "external_pilot" and (
        any(x.id == actor.entity for x in state.harpy_states)
        or any(x.id == actor.entity for x in state.native_harpies)
        or any(x.id == actor.entity for x in state.janus_cores)
    )


def pool(state: GameState, actor: ActorRef) -> tuple[GrantedIdentity, ...]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Use the actual original Girl's current Identity authority")
        return tuple(GrantedIdentity.model_validate(x.model_dump()) for x in sheet.identities)
    if _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import harpy

        return tuple(
            GrantedIdentity.model_validate(x.model_dump()) for x in harpy(state, actor).identities
        )
    if actor.kind == "handler":
        ref = subject_ref(state, actor)
        context = next(
            (x for x in state.director_contexts if x.active and x.body_actor == ref), None
        )
        if context:
            return tuple(GrantedIdentity.model_validate(x.model_dump()) for x in context.identities)
    imported = authority(state, actor)
    if imported is not None:
        if imported.delegated_context:
            context = next(x for x in state.director_contexts if x.id == imported.delegated_context)
            return tuple(GrantedIdentity.model_validate(x.model_dump()) for x in context.identities)
        return imported.identities
    if actor.kind == "external_pilot":
        raise ValueError(
            "FACTUAL_IDENTITIES_REQUIRED: review this actual external Girl's existing pool"
        )
    return ()


def ordinary(state: GameState, actor: ActorRef) -> tuple[str, ...]:
    values = pool(state, actor)
    if _harpy(state, actor):
        imported = authority(state, actor)
        if imported is None or imported.role != "harpy_review":
            raise ValueError(
                "FACTUAL_IDENTITIES_REQUIRED: identify the actual Harpy ordinary slots"
            )
        if not set(imported.ordinary) <= {x.id for x in values if not x.protected and not x.paired}:
            raise ValueError("STALE_ORDINARY_IDENTITIES: review changed actual Harpy resources")
        return imported.ordinary
    imported = authority(state, actor)
    if imported is not None and actor.kind != "pilot":
        if actor.kind != "handler" or not any(
            x.active and x.body_actor == subject_ref(state, actor) for x in state.director_contexts
        ):
            return tuple(x for x in imported.ordinary if x in {y.id for y in values})
    return tuple(x.id for x in values if not x.protected and not x.paired)


def _put(
    state: GameState,
    actor: ActorRef,
    values: tuple[GrantedIdentity, ...],
    ordinary_ids: tuple[str, ...],
    source: str | None,
    event: str,
    judge: int | None = None,
) -> None:
    ref = subject_ref(state, actor)
    if actor.kind == "pilot":
        sheet = state.sheets[actor.entity]
        sheet.identities = [IdentityState.model_validate(x.model_dump()) for x in values]
        if source is not None:
            sheet.obsession_sources = tuple(dict.fromkeys((*sheet.obsession_sources, source)))
        sheet.revision += 1
    elif _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import update
        from girlframe.engine.m3_void_state import HarpyIdentity

        changed = update(
            state,
            actor,
            identities=tuple(HarpyIdentity.model_validate(x.model_dump()) for x in values),
        )
        state.harpy_states, state.native_harpies, state.janus_cores = (
            changed.harpy_states,
            changed.native_harpies,
            changed.janus_cores,
        )
    else:
        from girlframe.engine.m3_actors import resolve

        controller = (
            int(actor.entity) if actor.kind == "handler" else resolve(state, actor, ()).controller
        )
        source_judge = judge if judge is not None else state.handler
        if source_judge is None:
            raise ValueError("The actual source judgment needs its real human principal")
        context = next(
            (x for x in state.director_contexts if x.active and x.body_actor == ref), None
        )
        existing = authority(state, actor)
        if context is not None:
            context.identities = [IdentityState.model_validate(x.model_dump()) for x in values]
            if source is not None:
                context.obsession_sources = tuple(
                    dict.fromkeys((*context.obsession_sources, source))
                )
            context.revision += 1
            record = IdentityAuthority(
                actor=ref,
                role="granted",
                ordinary=ordinary_ids,
                delegated_context=context.id,
                event=event,
                owner=controller,
                judge=source_judge,
                revision=existing.revision + 1 if existing else 1,
                reviewed_ids=tuple(x.id for x in values),
            )
        else:
            record = IdentityAuthority(
                actor=ref,
                role=existing.role if existing else "granted",
                identities=values,
                ordinary=ordinary_ids,
                event=event,
                owner=existing.owner if existing else controller,
                judge=existing.judge if existing else source_judge,
                revision=existing.revision + 1 if existing else 1,
                reviewed_ids=tuple(x.id for x in values),
                mentor=existing.mentor if existing else None,
            )
        state.leviathan_identity_authorities = [
            x for x in state.leviathan_identity_authorities if x.actor != ref
        ] + [record]
    if _harpy(state, actor):
        existing = authority(state, actor)
        assert existing is not None
        state.leviathan_identity_authorities = [
            x.model_copy(update={"ordinary": ordinary_ids, "revision": x.revision + 1})
            if x.actor == ref
            else x
            for x in state.leviathan_identity_authorities
        ]


def influence(
    original: GameState,
    source: ActorRef,
    actor: ActorRef,
    level: str,
    event: str,
    *,
    replace: str | None = None,
    reuse: str | None = None,
    reuse_many: tuple[str, ...] = (),
    judge: int | None = None,
) -> GameState:
    if level not in ("mid", "high") or source.kind != "gorgon" or source == actor:
        raise ValueError("Apply the actual distinct Leviathan's source result")
    body = (
        next(
            (
                x
                for x in original.world.gorgons
                if x.id == source.entity and x.alive and "leviathan" in x.types
            ),
            None,
        )
        if original.world
        else None
    )
    if body is None or not event.strip():
        raise ValueError("The actual living original Leviathan and effect source are required")
    state = GameState.model_validate_json(original.model_dump_json())
    values = pool(state, actor)
    eligible = ordinary(state, actor)
    ordinary_ids = list(eligible)
    selected: list[str] = []
    changed = list(values)
    existing_authority = authority(state, actor)
    base_pool = (
        actor.kind == "pilot"
        or _harpy(state, actor)
        or (
            actor.kind == "handler"
            and any(
                x.active and x.body_actor == subject_ref(state, actor)
                for x in state.director_contexts
            )
        )
        or (existing_authority is not None and existing_authority.role == "external_factual")
    )

    def make(index: int, slot: int | None) -> GrantedIdentity:
        return GrantedIdentity(
            id=str(uuid5(NAMESPACE_URL, event + ":obsessed:" + str(index))),
            name="obsessed",
            slot=slot,
            obsession_sources=(source.entity,),
        )

    def bind(identity: GrantedIdentity) -> GrantedIdentity:
        return identity.model_copy(
            update={
                "obsession_sources": tuple(
                    dict.fromkeys((*identity.obsession_sources, source.entity))
                )
            }
        )

    if level == "mid":
        if reuse_many:
            raise ValueError("A mid result gains one actual obsessed Identity")
        if reuse is not None:
            existing = next(
                (
                    x
                    for x in values
                    if x.id == reuse
                    and x.id in eligible
                    and (x.obsession_sources or x.name.casefold() == "obsessed")
                ),
                None,
            )
            if existing is None or replace is not None:
                raise ValueError(
                    "Reuse only an actual ordinary obsessed Identity without resetting it"
                )
            changed = [bind(x) if x.id == reuse else x for x in values]
            selected.append(reuse)
        else:
            capacity = len(eligible) + sum(x.paired for x in values)
            if base_pool and capacity >= 4:
                old = next((x for x in values if x.id == replace and x.id in eligible), None)
                if old is None:
                    raise ValueError("The actual owner selects one eligible ordinary replacement")
                require_identity_change(state, actor, (old.id,))
                require_unlocked(values, (old.id,))
                fresh = make(0, old.slot)
                changed = [fresh if x.id == old.id else x for x in values]
                ordinary_ids = [fresh.id if x == old.id else x for x in ordinary_ids]
            else:
                if replace is not None:
                    raise ValueError(
                        "Do not remove an actual Identity when no replacement is required"
                    )
                occupied = {x.slot for x in values if x.slot is not None}
                slot = next((x for x in range(4) if x not in occupied), None)
                fresh = make(0, slot if actor.kind in ("pilot", "handler") else None)
                changed.append(fresh)
                ordinary_ids.append(fresh.id)
            selected.append(fresh.id)
    else:
        if replace is not None or reuse is not None:
            raise ValueError(
                "High affects actual eligible ordinary slots, not an arbitrary replacement"
            )
        if not base_pool:
            if (
                len(reuse_many) > 4
                or len(set(reuse_many)) != len(reuse_many)
                or not set(reuse_many)
                <= {
                    x.id
                    for x in values
                    if x.id in eligible and (x.obsession_sources or x.name.casefold() == "obsessed")
                }
            ):
                raise ValueError("Choose up to four actual acquired obsessed Identities to retain")
            changed = [bind(x) if x.id in reuse_many else x for x in values]
            selected = list(reuse_many)
            new_grants = [make(i, None) for i in range(4 - len(reuse_many))]
            changed.extend(new_grants)
            ordinary_ids.extend(x.id for x in new_grants)
            selected.extend(x.id for x in new_grants)
        else:
            if reuse_many:
                raise ValueError("The actual base ordinary slots determine this high result")
            for i, old in enumerate(values):
                if old.id not in eligible:
                    continue
                if old.obsession_sources or old.name.casefold() == "obsessed":
                    fresh = bind(old)
                else:
                    require_identity_change(state, actor, (old.id,))
                    require_unlocked(values, (old.id,))
                    fresh = make(i, old.slot)
                changed[i] = fresh
                ordinary_ids = [fresh.id if x == old.id else x for x in ordinary_ids]
                selected.append(fresh.id)
    _put(state, actor, tuple(changed), tuple(ordinary_ids), source.entity, event, judge)
    state.leviathan_obsessions.append(
        Obsession(
            id=str(uuid5(NAMESPACE_URL, event + ":obsession:" + source.entity)),
            source=source,
            subject=subject_ref(state, actor),
            identity_ids=tuple(selected),
            level="mid" if level == "mid" else "high",
            event=event,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def subject_ref(state: GameState, actor: ActorRef) -> ActorRef:
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import body_original

        return body_original(state, actor).actor
    return actor


def active(state: GameState, actor: ActorRef) -> tuple[Obsession, ...]:
    if not state.leviathan_obsessions:
        return ()
    actor = subject_ref(state, actor)
    dead = {x.id for x in state.world.gorgons if not x.alive} if state.world else set()
    return tuple(
        x
        for x in state.leviathan_obsessions
        if x.subject == actor and x.released_event is None and x.source.entity not in dead
    )


def require_identity_change(state: GameState, actor: ActorRef, identities: Iterable[str]) -> None:
    selected = set(identities)
    from girlframe.engine.m3_am import require_identity_change as require_am_identity_change

    require_am_identity_change(state, actor, tuple(selected))
    if any(selected & set(x.identity_ids) for x in active(state, actor)):
        raise ValueError(
            "This original obsessed Identity cannot be removed until its Leviathan dies"
        )


def require_unlocked(identities: Iterable[Any], selected: Iterable[str]) -> None:
    chosen = set(selected)
    if any(x.id in chosen and x.obsession_sources for x in identities):
        raise ValueError("The source Leviathan must die before removing this obsessed Identity")


def require_identity_gain(state: GameState, actor: ActorRef, identity: str) -> None:
    sources: dict[str, set[str]] = {}
    for condition in active(state, actor):
        sources.setdefault(condition.source.entity, set()).update(condition.identity_ids)
    if any(identity not in ids for ids in sources.values()):
        raise ValueError("Only the actual source-qualifying obsessed Identity can generate Heat")


def allowed_gain(
    state: GameState,
    actor: ActorRef,
    requested: int,
    reason: str,
    event: str = "",
    *,
    identity: str | None = None,
) -> int:
    if requested <= 0:
        return requested
    conditions = active(state, actor)
    allowed = True
    if conditions:
        try:
            if identity is None:
                allowed = False
            else:
                require_identity_gain(state, actor, identity)
        except ValueError:
            allowed = False
    if not allowed:
        state.facts.append(
            dict(
                kind="blocked_by_obsession",
                actor=subject_ref(state, actor).model_dump_json(),
                requested=str(requested),
                actual="0",
                reason=reason,
                event=event,
                sources="|".join(sorted({x.source.entity for x in conditions})),
            )
        )
    return requested if allowed else 0


def rebind(state: GameState, old: ActorRef, new: ActorRef, event: str) -> GameState:
    """Trusted same-person conversion only; never controller-UID/current-character aliasing."""
    affected = [x for x in state.leviathan_obsessions if x.subject == old]
    if affected:
        state.leviathan_obsessions = [
            x.model_copy(update={"subject": new}) if x.subject == old else x
            for x in state.leviathan_obsessions
        ]
        state.facts.append(
            dict(
                kind="leviathan_obsession_rebound",
                original=old.model_dump_json(),
                resulting=new.model_dump_json(),
                event=event,
            )
        )
    state.leviathan_identity_authorities = [
        x.model_copy(update={"actor": new}) if x.actor == old else x
        for x in state.leviathan_identity_authorities
    ]
    return state


def release_dead_sources(state: GameState, event: str) -> GameState:
    dead = {x.id for x in state.world.gorgons if not x.alive} if state.world else set()
    affected = [
        x
        for x in state.leviathan_obsessions
        if x.released_event is None and x.source.entity in dead
    ]
    sources = dead & {x.source.entity for x in state.leviathan_obsessions}
    if not sources:
        return state

    def identities(values: Iterable[Any]) -> list[Any]:
        return [
            x.model_copy(
                update={
                    "obsession_sources": tuple(y for y in x.obsession_sources if y not in sources)
                }
            )
            for x in values
        ]

    for sheet in state.sheets.values():
        sheet.identities = identities(sheet.identities)
        sheet.obsession_sources = tuple(x for x in sheet.obsession_sources if x not in sources)
    for context in state.director_contexts:
        context.identities = identities(context.identities)
        context.obsession_sources = tuple(x for x in context.obsession_sources if x not in sources)
    for collection in ("harpy_states", "native_harpies", "janus_cores"):
        setattr(
            state,
            collection,
            [
                x.model_copy(update={"identities": tuple(identities(x.identities))})
                for x in getattr(state, collection)
            ],
        )
    state.leviathan_identity_authorities = [
        x.model_copy(update={"identities": tuple(identities(x.identities))})
        for x in state.leviathan_identity_authorities
    ]
    state.leviathan_obsessions = [
        x.model_copy(update={"released_event": event}) if x in affected else x
        for x in state.leviathan_obsessions
    ]
    for source in {x.source.entity for x in affected}:
        state.facts.append(
            dict(kind="leviathan_obsession_source_ended", source=source, event=event)
        )
    return state
