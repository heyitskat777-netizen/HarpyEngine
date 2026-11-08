"""Genuine source-owned mandatory Animal gifts, without a synthetic Action or receipt."""

from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Connection

from girlframe.engine import p1_unrolled_sex as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_bonded import Source
from girlframe.engine.m3_changeling_sex import UnrolledAMSex
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_gender_designation import _current, designation
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def offer(
    game: "GameService", c: Connection, state: GameState, source: Source | UnrolledAMSex, event: str
) -> None:
    if source.kind != "sex" or source.action is not None or source.target is None:
        return
    for animal, target in ((source.actor, source.target), (source.target, source.actor)):
        law, other = _current(game, c, state, animal), _current(game, c, state, target)
        if law is None or law.gender != "animal" or other and other.gender == "animal":
            continue
        identity = str(uuid5(NAMESPACE_URL, "unrolled-animal:" + source.id + ":" + animal.token))
        if any(x.id == identity for x in rules.gifts(state)):
            continue
        rules.put(
            state,
            rules.AnimalGift(
                id=identity,
                source_kind="changeling_am" if isinstance(source, UnrolledAMSex) else None,
                source=source.id,
                animal=animal,
                target=target,
                designation=law.id,
                event=event,
            ),
        )


def require_complete(game: "GameService", c: Connection, state: GameState, source: str) -> None:
    if any(x.source == source and x.tag is None for x in rules.gifts(state)):
        raise WorkflowError(
            "The actual Animal must give its original non-Animal partner a Tag first"
        )


def tasks(
    game: "GameService",
    c: Connection,
    state: GameState,
    source: Source | UnrolledAMSex,
    viewer: GuildViewer,
) -> list[dict[str, Any]]:
    if viewer.user_id not in source.controllers.values():
        raise WorkflowError("These actual source gifts belong to their original participants")
    result = []
    for gift in rules.gifts(state):
        if gift.source != source.id:
            continue
        prove(game, c, state, gift.id)
        label = None
        if gift.tag is not None:
            from girlframe.engine.m3_mockingbird import actor_tags

            tagged = _history(c, game, gift.tag_event or "")
            label = next(
                value.label for value in actor_tags(tagged, gift.target) if value.id == gift.tag
            )
        result.append(
            dict(
                id=gift.id,
                pending=gift.tag is None
                and source.controllers[gift.animal.token] == viewer.user_id,
                waiting=gift.tag is None,
                animal=gift.animal.model_dump(mode="json"),
                target=gift.target.model_dump(mode="json"),
                tag=gift.tag,
                tag_label=label,
                state="owed" if gift.tag is None else "given",
            )
        )
    return result


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> rules.AnimalGift:
    gift = next((x for x in rules.gifts(state) if x.id == identity), None)
    if gift is None:
        raise WorkflowError("Recover the genuine original non-rolling Sex gift")
    birth = _history(c, game, gift.event)
    original = next((x for x in rules.gifts(birth) if x.id == identity), None)
    source = _source(game, c, birth, gift)
    law = designation(game, c, birth, gift.designation)
    other = _current(game, c, birth, gift.target)
    if (
        original is None
        or any(
            getattr(original, k) != getattr(gift, k)
            for k in ("id", "source_kind", "source", "animal", "target", "designation", "event")
        )
        or source.kind != "sex"
        or source.action is not None
        or source.target is None
        or source.effect_event != gift.event
        or {source.actor, source.target} != {gift.animal, gift.target}
        or law.actor != gift.animal
        or law.gender != "animal"
        or _current(game, c, birth, gift.animal) != law
        or other
        and other.gender == "animal"
    ):
        raise WorkflowError("Preserve actual performed Sex, designation and original Tag author")
    if gift.tag is not None:
        tagged = _history(c, game, gift.tag_event or "")
        saved = next((x for x in rules.gifts(tagged) if x.id == gift.id), None)
        from girlframe.engine.m3_mockingbird import actor_tags

        tag = next((x for x in actor_tags(tagged, gift.target) if x.id == gift.tag), None)
        from girlframe.services.m3_dose_up import _audit

        _audit(
            game,
            c,
            gift.tag_event or "",
            ("m3.unrolled_animal_tag",),
            source.controllers[gift.animal.token],
        )
        giver = getattr(tag, "giver_actor", None)
        entity = getattr(tag, "giver_entity", None)
        if giver is None and isinstance(entity, str):
            from girlframe.engine.m3_actor_state import ActorRef

            giver = ActorRef.model_validate_json(entity)
        if saved != gift or tag is None or giver != gift.animal:
            raise WorkflowError("Recover the actual original owned Tag effect")
    _source(game, c, state, gift)
    return gift


def give(
    game: "GameService", viewer: GuildViewer, key: str, identity: str, revision: int, label: str
) -> dict[str, Any]:
    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.engine.m3_bonded import SEX
        from girlframe.engine.m3_mockingbird import give_tag
        from girlframe.services.m3_bonded import _access
        from girlframe.services.p1_source_pause import require_ready

        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        if state.revision != revision:
            raise WorkflowError("Reopen the actual current source gift")
        gift = prove(game, c, state, identity)
        source = _source(game, c, state, gift)
        if gift.source_kind == "changeling_am":
            from girlframe.engine.m3_changeling_sex import RULES
            from girlframe.services.m3_access import Access

            gate = Access(game.store)
            gate.authorize(c, viewer, "plays", director_response=True)
            assert gate.registry is not None
            gate.registry.require_available(RULES["AM"])
        else:
            _access(game, c, viewer, SEX)
            require_ready(game, c, state, source.id)
        if (
            gift.tag is not None
            or source.controllers[gift.animal.token] != viewer.user_id
            or not label.strip()
            or len(label.strip()) > 120
        ):
            raise WorkflowError("Only the actual original Animal authors its ordinary Tag once")
        event, tag = str(uuid4()), str(uuid4())
        changed = give_tag(
            state,
            profiles(c, game.store.campaign_id),
            gift.target,
            gift.animal,
            label.strip(),
            tag,
            event,
            tuple(sorted(source.controllers.values())),
        )
        rules.put(changed, gift.model_copy(update=dict(tag=tag, tag_event=event)))
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.unrolled_animal_tag",
            changed,
            event_id=event,
            source_id=source.id,
            gift_id=gift.id,
        )
        if gift.source_kind == "changeling_am":
            from girlframe.services.m3_changeling_sex import synchronize_am

            synchronize_am(game, c, changed, source.id, event)
        return dict(source=source.id, tag=tag)

    return game.store._write(
        viewer,
        key,
        "m3.unrolled_animal_tag",
        dict(gift=identity, revision=revision, label=label),
        operation,
        auto_audit=False,
    )


def _source(
    game: "GameService", c: Connection, state: GameState, gift: rules.AnimalGift
) -> Source | UnrolledAMSex:
    if gift.source_kind == "changeling_am":
        from girlframe.services.m3_changeling_sex import prove_am_source

        return prove_am_source(game, c, state, gift.source)
    from girlframe.services.m3_bonded import prove as prove_bonded

    return prove_bonded(game, c, state, gift.source)
