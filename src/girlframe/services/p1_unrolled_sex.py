"""Genuine source-owned mandatory Animal gifts, without a synthetic Action or receipt."""

from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Connection

from girlframe.engine import p1_unrolled_sex as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_bonded import Source
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_gender_designation import _current, designation
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def offer(game: "GameService", c: Connection, state: GameState, source: Source, event: str) -> None:
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
    game: "GameService", c: Connection, state: GameState, source: Source, viewer: GuildViewer
) -> list[dict[str, Any]]:
    if viewer.user_id not in source.controllers.values():
        raise WorkflowError("These actual source gifts belong to their original participants")
    return [
        dict(
            id=x.id,
            pending=x.tag is None and source.controllers[x.animal.token] == viewer.user_id,
            waiting=x.tag is None,
            animal=x.animal.model_dump(mode="json"),
            tag=x.tag,
        )
        for x in rules.gifts(state)
        if x.source == source.id
    ]


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> rules.AnimalGift:
    from girlframe.engine.m3_bonded import get
    from girlframe.services.m3_bonded import prove as prove_source

    gift = next((x for x in rules.gifts(state) if x.id == identity), None)
    if gift is None:
        raise WorkflowError("Recover the genuine original non-rolling Sex gift")
    birth = _history(c, game, gift.event)
    original = next((x for x in rules.gifts(birth) if x.id == identity), None)
    source = prove_source(game, c, birth, gift.source)
    law = designation(game, c, birth, gift.designation)
    other = _current(game, c, birth, gift.target)
    if (
        original is None
        or any(
            getattr(original, k) != getattr(gift, k)
            for k in ("id", "source", "animal", "target", "designation", "event")
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
        tag = next((x for x in tagged.sheets[gift.target.entity].tags if x.id == gift.tag), None)
        from girlframe.services.m3_dose_up import _audit

        _audit(
            game,
            c,
            gift.tag_event or "",
            ("m3.unrolled_animal_tag",),
            source.controllers[gift.animal.token],
        )
        if saved != gift or tag is None or tag.giver_actor != gift.animal:
            raise WorkflowError("Recover the actual original owned Tag effect")
    get(state, gift.source)
    return gift


def give(
    game: "GameService", viewer: GuildViewer, key: str, identity: str, revision: int, label: str
) -> dict[str, Any]:
    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.engine.m3_bonded import SEX
        from girlframe.engine.m3_mockingbird import give_tag
        from girlframe.services.m3_bonded import _access
        from girlframe.services.m3_bonded import prove as prove_source
        from girlframe.services.p1_source_pause import require_ready

        _access(game, c, viewer, SEX)
        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        if state.revision != revision:
            raise WorkflowError("Reopen the actual current source gift")
        gift = prove(game, c, state, identity)
        source = prove_source(game, c, state, gift.source)
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
        return dict(source=source.id, tag=tag)

    return game.store._write(
        viewer,
        key,
        "m3.unrolled_animal_tag",
        dict(gift=identity, revision=revision, label=label),
        operation,
        auto_audit=False,
    )
