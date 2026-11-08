"""Finite required context; each real recipe retains its own costs and consent."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_required_plays as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

DIRECT_NOMINATIONS = {
    "brutalize": ("girl.alpha.brutalize", "ALPHA"),
    "old_dog_new_pups": ("girl.oldgen.old-dog-new-pups", "OLDGEN"),
    "easy_target": ("girl.newgirl.easy-target", "NEWGIRL"),
}


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    Access(game.store).authorize(c, viewer, "plays")


def nomination_options(
    game: GameService, c: Connection, state: GameState, nominee: ActorRef
) -> tuple[str, ...]:
    """One additional actual own source, no copied entitlement or phantom person."""
    sheet = state.sheets.get(nominee.entity) if nominee.kind == "pilot" else None
    registry = Access(game.store).registry
    if sheet is None or sheet.character_id != nominee.incarnation or registry is None:
        return ()
    result = []
    for rule, play, girl in (
        (alpha.RULE, alpha.PLAY, "ALPHA"),
        (dose.RULE, dose.PLAY, "STIM-BLISSED"),
    ):
        if not has_rule(sheet, rule, girl) or (play == dose.PLAY and sheet.girl != girl):
            continue
        try:
            registry.require_available(rule)
        except ValueError:
            continue
        result.append(play)
    for play, (rule, girl) in DIRECT_NOMINATIONS.items():
        if not has_rule(sheet, rule, girl):
            continue
        try:
            registry.require_available(rule)
        except ValueError:
            continue
        result.append(play)
    return tuple(result)


def _task(game: GameService, c: Connection, state: GameState, source: str) -> ankou.Task:
    from girlframe.services.m3_ankou import prove_relay, prove_task

    value = prove_task(game, c, state, source)
    if value.kind != "perform" or value.actor.kind != "pilot":
        raise WorkflowError("Use an actual standalone Ankou nominated performance")
    relay = prove_relay(game, c, state, value.source)
    if relay.consequence != "nominees" or value.actor != relay.actor or value.cast != relay.cast:
        raise WorkflowError("Preserve the actual Handler consequence and original nominated actor")
    born = _history(c, game, value.event)
    peers = [
        x
        for x in ankou.records(born, ankou.Task)
        if x.source == value.source and x.kind == "nominate"
    ]
    choices = []
    for peer in peers:
        proved = prove_task(game, c, born, peer.id)
        if not proved.completed_event or proved.selected_event != proved.completed_event:
            raise WorkflowError("Preserve every actual original nominator's own completed choice")
        origin = _history(c, game, proved.event)
        if depth(origin, value.actor, proved.actor) != 2:
            raise WorkflowError(
                "Nomination requires the original actual Intense Bond, not a virtual cost"
            )
        if proved.choice and proved.choice != "pass":
            choices.append(proved.choice)
    if (
        not peers
        or value.options != tuple(dict.fromkeys(choices))
        or not {alpha.PLAY, dose.PLAY, *DIRECT_NOMINATIONS}.intersection(value.options)
    ):
        raise WorkflowError("Use only the actual printed nominees' supported offered Play")
    return value


def direct_nomination(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
) -> bool:
    """Positive actual Task source for three Plays with no separate recipe ID."""
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in ankou.records(state, ankou.Task)
    ):
        return False
    task = _task(game, c, state, prepared.source_work)
    if (
        prepared.play not in DIRECT_NOMINATIONS
        or prepared.play not in task.options
        or task.actor != actor
        or task.controller != int(actor.entity)
        or current_ref(state, task.controller) != actor
        or task.completed_event
        or prepared.parent
        or task.cast.channel != channel
    ):
        raise WorkflowError("Use the original actor's genuine selected standalone nomination")
    from girlframe.services.m3_ankou_support import cast_actor

    cast_actor(game, c, state, task.cast, actor)
    if task.child:
        action = game.action(c, task.child)
        if (
            action["actor_id"] != actor.entity
            or action["data"].get("ankou_effect_child", {}).get("id") != task.id
            or PlayInput.model_validate_json(json.dumps(action["data"]["prepared"])) != prepared
            or action["parent_id"] is not None
        ):
            raise WorkflowError("Keep this exact original already-bound nominated Play")
    return True


def _birth(game: GameService, c: Connection, state: GameState, identity: str) -> rules.RequiredLink:
    value = rules.get(state, identity)
    born = rules.get(_history(c, game, value.event), identity)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        born.action is not None
        or born.bound_event is not None
        or born.completed_event is not None
        or bool(born.releases)
        or born.retired_event is not None
        or value.id != rules.identity(value.source, value.recipe, value.event)
        or value.model_dump(
            exclude={"action", "bound_event", "completed_event", "releases", "retired_event"}
        )
        != born.model_dump(
            exclude={"action", "bound_event", "completed_event", "releases", "retired_event"}
        )
        or audit is None
        or audit.kind != "m3.required_play_linked"
        or audit.actor_id != value.actor.entity
    ):
        raise WorkflowError("Preserve the canonical original source/recipe/actor link")
    payload = json.loads(audit.payload_json)
    if payload.get("source") != value.source or payload.get("recipe") != value.recipe:
        raise WorkflowError("Recover the exact original human-selected required recipe")
    for release in value.releases:
        source = rules.get(_history(c, game, release.bound_event), identity)
        released = rules.get(_history(c, game, release.event), identity)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == release.event
            )
        ).first()
        payload = json.loads(audit.payload_json) if audit else {}
        if (
            source.action != release.action
            or source.bound_event != release.bound_event
            or release not in released.releases
            or released.action is not None
            or released.bound_event is not None
            or released.retired_event != release.event
            or audit is None
            or audit.kind != "m3.shared_play_recovered"
            or audit.actor_id != value.actor.entity
            or payload.get("action_id") != release.action
            or payload.get("cancelled_unrolled") is not True
        ):
            raise WorkflowError(
                "Preserve the actual unrolled cancellation and original linked reservation"
            )
        if value.rule == alpha.RULE:
            released_recipe = alpha.get(_history(c, game, release.event), value.recipe)
            original_recipe = alpha.get(_history(c, game, value.event), value.recipe)
            if (
                released_recipe.phase != "accepted"
                or released_recipe.action is not None
                or released_recipe.consent_event != original_recipe.consent_event
            ):
                raise WorkflowError(
                    "Cancellation preserves the original accepted source without performed effects"
                )
        else:
            original_dose = rules.self_dose_recipe(_history(c, game, value.event), value.recipe)
            if (
                rules.self_dose_recipe(_history(c, game, release.event), value.recipe)
                != original_dose
            ):
                raise WorkflowError("Preserve the original self-Dose recipe after cancellation")
            cancelled = game.action(c, release.action)
            if cancelled["data"].get("receipt") or any(
                x.id == release.action
                for x in dose.records(_history(c, game, release.event), dose.Dose)
            ):
                raise WorkflowError("An actually rolled or applied Dose cannot be cancelled")
    if value.retired_event and (
        not value.releases
        or value.releases[-1].event != value.retired_event
        or value.action is not None
        or value.bound_event is not None
        or value.completed_event is not None
    ):
        raise WorkflowError("Retire only an actually cancelled unrolled linked source")
    if value.releases and not value.retired_event:
        raise WorkflowError("Preserve the actual canonical cancellation of this link generation")
    return value


def _active(game: GameService, c: Connection, state: GameState) -> tuple[rules.RequiredLink, ...]:
    # A forged retirement flag must never remove required-source authority.
    values = rules.records(state)
    for value in values:
        if value.retired_event:
            _birth(game, c, state, value.id)
    return tuple(x for x in values if x.retired_event is None)


def _prove_self_dose(
    game: GameService, c: Connection, state: GameState, value: rules.RequiredLink
) -> rules.SelfDoseRecipe:
    recipe = rules.self_dose_recipe(state, value.recipe)
    born = _history(c, game, value.event)
    original = rules.self_dose_recipe(born, value.recipe)
    sheet = born.sheets.get(value.actor.entity)
    if (
        recipe != original
        or recipe.event != value.event
        or recipe.source != value.source
        or recipe.actor != value.actor
        or recipe.target != value.target
        or recipe.target != recipe.actor
        or recipe.cast != value.cast
        or sheet is None
        or sheet.character_id != value.actor.incarnation
        or sheet.girl != "STIM-BLISSED"
        or not has_rule(sheet, dose.RULE, "STIM-BLISSED")
    ):
        raise WorkflowError("Recover the actual immutable native owned self-Dose source")
    return recipe


def self_dose_for_play(
    game: GameService, c: Connection, state: GameState, prepared: PlayInput
) -> rules.SelfDoseRecipe | None:
    value = link_for_play(game, c, state, prepared)
    if value is None:
        return None
    if (
        value.rule != dose.RULE
        or prepared.order_id
        or prepared.target_actor not in (None, value.actor)
    ):
        raise WorkflowError("Use the actual self-Dose recipe without a foreign Contact or Order")
    return _prove_self_dose(game, c, state, value)


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.RequiredLink:
    from girlframe.services.m3_alpha_sex import prove as prove_alpha

    value = _birth(game, c, state, identity)
    task = _task(game, c, state, value.source)
    if value.actor != task.actor or value.cast != task.cast:
        raise WorkflowError("Preserve the original nominated actor and source cast")
    if value.rule == dose.RULE:
        own_dose = _prove_self_dose(game, c, state, value)
        if dose.PLAY not in task.options or own_dose.target != value.actor:
            raise WorkflowError("Use only the actual nominated owned self-Dose")
    else:
        recipe = prove_alpha(game, c, state, value.recipe)
        if (
            alpha.PLAY not in task.options
            or recipe.actor != value.actor
            or recipe.target != value.target
            or fingerprint(recipe.cast) != fingerprint(value.cast)
            or recipe.bonded_source is not None
            or recipe.changeling_source is not None
        ):
            raise WorkflowError(
                "Use this actual actor's own Alpha source; no borrowed or psychic authority"
            )
    if value.bound_event:
        bound = rules.get(_history(c, game, value.bound_event), identity)
        if (
            bound.action != value.action
            or bound.bound_event != value.bound_event
            or (value.rule == alpha.RULE and alpha.get(state, value.recipe).action != value.action)
            or task.child != value.action
        ):
            raise WorkflowError("Preserve the exact single real bound recipe Action")
        actual = game.action(c, value.action or "")
        _action(value, actual)
    elif value.action is not None:
        raise WorkflowError("A bound required recipe needs its canonical actual source event")
    if value.completed_event:
        completed = rules.get(_history(c, game, value.completed_event), identity)
        if completed != value or not task.completed_event:
            raise WorkflowError("The required source closes only after genuine child completion")
    return value


def link_for_play(
    game: GameService, c: Connection, state: GameState, prepared: PlayInput
) -> rules.RequiredLink | None:
    candidates = [x for x in _active(game, c, state) if x.recipe == prepared.source_work]
    if not candidates:
        return None
    if len(candidates) != 1 or prepared.play != (
        dose.PLAY if candidates[0].rule == dose.RULE else alpha.PLAY
    ):
        raise WorkflowError("Use the exact linked own recipe and required context")
    return prove(game, c, state, candidates[0].id)


def source_for_play(
    game: GameService, c: Connection, state: GameState, prepared: PlayInput
) -> str | None:
    """Positive lookup for source-pause admission; no for_play/require_ready recursion."""
    value = link_for_play(game, c, state, prepared)
    return value.source if value else None


def for_play(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    source = source_for_play(game, c, state, prepared)
    if source is None:
        return None
    _access(game, c, viewer)
    value = link_for_play(game, c, state, prepared)
    assert value is not None
    task = _task(game, c, state, source)
    if (
        value.action
        or value.completed_event
        or task.completed_event
        or viewer.user_id != int(value.actor.entity)
        or current_ref(state, viewer.user_id) != value.actor
    ):
        raise WorkflowError("Only the original actual actor performs this unbound required source")
    if value.rule == dose.RULE:
        from girlframe.services.m3_dose_up import prepare as prepare_dose

        prepare_dose(game, c, viewer, state, prepared, channel)
    else:
        from girlframe.services.m3_alpha_sex import prepare as prepare_alpha

        prepare_alpha(game, c, viewer, state, prepared, channel)
    from girlframe.services.m3_ankou_feedback_sequences import prepare_child

    meta = prepare_child(game, c, viewer, state, prepared, channel)
    if meta is None or meta["id"] != source or meta["parent"] is not None:
        raise WorkflowError("Preserve the actual standalone required context")
    return meta | dict(
        required_link=value.id,
        recipe=value.recipe,
        target=value.target.model_dump(mode="json"),
        source_work=value.recipe,
        required_source=source,
    )


def _action(value: rules.RequiredLink, action: dict[str, Any]) -> None:
    from girlframe.services.m3_ankou_support import actual_action_actor

    meta = action["data"].get("ankou_effect_child", {})
    if (
        action["id"] != value.action
        or action.get("parent_id") is not None
        or action["data"]["play"] != (dose.PLAY if value.rule == dose.RULE else alpha.PLAY)
        or actual_action_actor(action) != value.actor
        or action["data"].get("prepared", {}).get("source_work") != value.recipe
        or (
            action["data"].get("dose_up", {}).get("required_recipe") != value.recipe
            if value.rule == dose.RULE
            else action["data"].get("alpha_sex", {}).get("session") != value.recipe
        )
        or meta.get("id") != value.source
        or meta.get("required_link") != value.id
        or meta.get("recipe") != value.recipe
    ):
        raise WorkflowError("Preserve both exact original required context and actual Alpha recipe")


def bind_action(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("ankou_effect_child", {})
    key = meta.get("required_link")
    candidates = [
        x
        for x in _active(game, c, state)
        if x.recipe == action["data"].get("prepared", {}).get("source_work")
    ]
    if not candidates:
        if key:
            raise WorkflowError("Recover the actual required recipe link")
        return
    if len(candidates) != 1 or key != candidates[0].id:
        raise WorkflowError("Do not omit this recipe's genuine required context")
    value = _birth(game, c, state, key)
    task = _task(game, c, state, value.source)
    if value.action or task.child not in (None, action["id"]):
        raise WorkflowError("Bind only one actual child to the original required slot")
    changed = value.model_copy(update={"action": action["id"], "bound_event": event})
    _action(changed, action)
    rules.put(state, changed)


def pre_roll(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    candidates = [x for x in rules.records(state) if x.action == action["id"]]
    if not candidates:
        if action["data"].get("ankou_effect_child", {}).get("required_link"):
            raise WorkflowError("Recover the actual canonical bound required link")
        return
    value = prove(game, c, state, candidates[0].id)
    _action(value, action)
    task = _task(game, c, state, value.source)
    if task.completed_event or value.completed_event:
        raise WorkflowError("This required source already completed its real performance")
    from girlframe.services.p1_source_pause import require_ready

    require_ready(game, c, state, task.id)


def completion_ready(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    candidates = [x for x in rules.records(state) if x.action == action["id"]]
    if not candidates:
        if action["data"].get("ankou_effect_child", {}).get("required_link"):
            raise WorkflowError("Recover the actual bound required source")
        return True
    value = prove(game, c, state, candidates[0].id)
    if value.rule == dose.RULE:
        if action["data"].get("dose_up", {}).get("phase") != "complete":
            return False
        from girlframe.services.m3_dose_up import prove as prove_dose

        actual_dose = prove_dose(game, c, state, action["id"])
        ready = actual_dose.actor == value.actor and actual_dose.target == value.target
    else:
        ready = alpha.get(state, value.recipe).phase == "complete"
    return bool(
        ready
        and action["state"] == "complete"
        and action["data"].get("receipt")
        and not game.pending(c, action["id"])
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    ancestors = set()
    current = action
    while current["id"] not in ancestors:
        ancestors.add(current["id"])
        if not current.get("parent_id"):
            break
        current = game.action(c, current["parent_id"])
    for link in rules.records(state):
        if link.retired_event or link.completed_event or link.action not in ancestors:
            continue
        child = game.action(c, link.action or "")
        if not completion_ready(game, c, state, child):
            continue
        from girlframe.services.m3_ankou_feedback_sequences import complete_child

        complete_child(game, c, state, child, event)
        state = load_state(c, game.store.campaign_id)
        task = _task(game, c, state, link.source)
        if not task.completed_event:
            raise WorkflowError("The actual required Task still awaits its true completion")
        final = str(uuid4())
        rules.put(state, rules.get(state, link.id).model_copy(update={"completed_event": final}))
        author = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if not isinstance(author, str) or not author.isdecimal():
            raise WorkflowError(
                "Recover the actual triggering human source author before closing this requirement"
            )
        game.event(
            c,
            int(author),
            final,
            "m3.required_play_completed",
            state,
            event_id=final,
            source=link.source,
            recipe=link.recipe,
            action_id=child["id"],
            source_completion=task.completed_event,
            subject_actor=link.actor.model_dump(mode="json"),
        )


class RequiredPlayService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _owner(
        self, c: Connection, viewer: GuildViewer, state: GameState, source: str
    ) -> ankou.Task:
        _access(self.game, c, viewer)
        task = _task(self.game, c, state, source)
        if task.controller != viewer.user_id or current_ref(state, viewer.user_id) != task.actor:
            raise WorkflowError("Only the actual original nominated actor controls this source")
        return task

    def link(
        self, viewer: GuildViewer, key: str, source: str, recipe: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            task = self._owner(c, viewer, state, source)
            if state.revision != revision:
                raise WorkflowError("STALE_REQUIRED_PLAY: reopen the actual source and recipe")
            if (
                task.completed_event
                or task.child
                or any(
                    x.source == source or x.recipe == recipe for x in _active(self.game, c, state)
                )
            ):
                raise WorkflowError(
                    "Preserve the exact one pending required slot and actual selected recipe"
                )
            from girlframe.services.m3_alpha_sex import _contact
            from girlframe.services.m3_alpha_sex import prove as prove_alpha

            if alpha.PLAY not in task.options:
                raise WorkflowError("Alpha was not offered by these actual nominators")
            own = prove_alpha(self.game, c, state, recipe)
            if (
                own.phase != "accepted"
                or own.action
                or own.actor != task.actor
                or own.bonded_source is not None
                or own.changeling_source is not None
                or fingerprint(own.cast) != fingerprint(task.cast)
            ):
                raise WorkflowError(
                    "Select an accepted unperformed actual OWN Alpha source in this original scene"
                )
            _contact(self.game, c, state, own.actor, own.target, own.cast.channel)
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, task.id)
            event = str(uuid4())
            value = rules.RequiredLink(
                id=rules.identity(source, recipe, event),
                source=source,
                recipe=recipe,
                actor=own.actor,
                target=own.target,
                cast=own.cast,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.required_play_linked",
                state,
                event_id=event,
                source=source,
                recipe=recipe,
                link=value.id,
            )
            return dict(id=value.id, source=source, recipe=recipe, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.required_play_linked",
            dict(source=source, recipe=recipe, revision=revision),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def link_self_dose(
        self, viewer: GuildViewer, key: str, source: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            task = self._owner(c, viewer, state, source)
            if state.revision != revision:
                raise WorkflowError("STALE_REQUIRED_PLAY: reopen the actual source")
            if (
                task.completed_event
                or task.child
                or dose.PLAY not in task.options
                or dose.PLAY not in nomination_options(self.game, c, state, task.actor)
                or any(x.source == source for x in _active(self.game, c, state))
            ):
                raise WorkflowError("Select only an actual pending owned nominated self-Dose")
            from girlframe.services.m3_dose_up import self_recipe_context
            from girlframe.services.p1_source_pause import require_ready

            position, vessel = self_recipe_context(self.game, c, state, task.actor, task.cast)
            require_ready(self.game, c, state, task.id)
            event, recipe_id = str(uuid4()), str(uuid4())
            recipe = rules.SelfDoseRecipe(
                id=recipe_id,
                source=source,
                actor=task.actor,
                target=task.actor,
                cast=task.cast,
                event=event,
                actor_position=position,
                actor_vessel=vessel,
            )
            rules.put_self_dose_recipe(state, recipe)
            value = rules.RequiredLink(
                id=rules.identity(source, recipe_id, event),
                source=source,
                recipe=recipe_id,
                rule="girl.stim-blissed.dose-up",
                actor=task.actor,
                target=task.actor,
                cast=task.cast,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.required_play_linked",
                state,
                event_id=event,
                source=source,
                recipe=recipe_id,
                link=value.id,
            )
            return dict(id=value.id, source=source, recipe=recipe_id, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.required_play_linked",
            dict(source=source, revision=revision, self_dose=True),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def menu(self, viewer: GuildViewer, source: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            task = self._owner(c, viewer, state, source)
            links = [x for x in _active(self.game, c, state) if x.source == source]
            if len(links) > 1:
                raise WorkflowError("Recover the one actual selected recipe")
            link = prove(self.game, c, state, links[0].id) if links else None
            from girlframe.services.m3_alpha_sex import prove as prove_alpha

            accepted = []
            invitations = []
            for recipe in alpha.sessions(state) if alpha.PLAY in task.options else ():
                if (
                    recipe.actor != task.actor
                    or recipe.cast.id != task.cast.id
                    or recipe.bonded_source
                    or recipe.changeling_source
                ):
                    continue
                if recipe.phase == "accepted" and recipe.action is None:
                    prove_alpha(self.game, c, state, recipe.id)
                    accepted.append(
                        dict(
                            id=recipe.id,
                            label="Alpha with "
                            + resolve(
                                state, recipe.target, profiles(c, self.store.campaign_id)
                            ).label,
                            target=recipe.target.model_dump(mode="json"),
                        )
                    )
                elif recipe.phase == "invited":
                    invitations.append(
                        dict(id=recipe.id, label="Await actual counterpart confirmation")
                    )
            from girlframe.services.p1_source_pause import projection as pause

            return dict(
                source=source,
                self_dose=(
                    dose.PLAY in task.options
                    and dose.PLAY in nomination_options(self.game, c, state, task.actor)
                ),
                alpha_offered=alpha.PLAY in task.options,
                revision=state.revision,
                actor=task.actor.model_dump(mode="json"),
                channel=task.cast.channel,
                completed=bool(task.completed_event),
                accepted=accepted,
                invitations=invitations,
                cancelled=[
                    x.id for x in rules.records(state) if x.source == source and x.retired_event
                ],
                link=link.model_dump(mode="json") if link else None,
                pause=pause(self.game, c, source),
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            link = prove(self.game, c, state, identity)
        return self.menu(viewer, link.source)


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    candidates = [x for x in rules.records(state) if x.action == action["id"]]
    if not candidates:
        if action["data"].get("ankou_effect_child", {}).get("required_link"):
            raise WorkflowError(
                "Recover the actual original linked reservation before cancellation"
            )
        return False
    value = prove(game, c, state, candidates[0].id)
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.action_id).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        not event
        or value.completed_event
        or action["data"].get("receipt")
        or receipt is not None
        or not value.bound_event
    ):
        raise WorkflowError("Cancel only a genuine unrolled source, preserving known receipts")
    if value.rule == alpha.RULE:
        recipe = alpha.get(state, value.recipe)
        if recipe.phase != "active" or recipe.action != action["id"] or recipe.effect_event:
            raise WorkflowError("Preserve every actual Alpha effect")
        alpha.put(state, recipe.model_copy(update={"action": None, "phase": "accepted"}))
    elif action["data"].get("dose_up", {}).get("phase") != "unrolled" or any(
        x.id == action["id"] for x in dose.records(state, dose.Dose)
    ):
        raise WorkflowError("Preserve every actual Dose effect")
    release = rules.Release(action=action["id"], bound_event=value.bound_event, event=event)
    rules.put(
        state,
        value.model_copy(
            update={
                "action": None,
                "bound_event": None,
                "releases": (*value.releases, release),
                "retired_event": event,
            }
        ),
    )
    return True
