"""Finite required context; each real recipe retains its own costs and consent."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_alpha_sex as alpha
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_casualty as casualty
from girlframe.engine import m3_dose_up as dose
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_oldgen_sex as oldgen
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine import m3_required_plays as rules
from girlframe.engine import m3_stim_sex as stim
from girlframe.engine import m3_vatgrown_plays as vatgrown
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

MOCK_RULE = "girl.mockingbird.bad-at-being-a-person"
MOCK_PLAY = "mockingbird_person"
MOCK_SEX_RULE = "girl.mockingbird.sex-play"
MOCK_SEX_PLAY = "mockingbird_sex"
MOCK_SOURCES = {MOCK_RULE: MOCK_PLAY, MOCK_SEX_RULE: MOCK_SEX_PLAY}

DIRECT_NOMINATIONS = {
    "brutalize": ("girl.alpha.brutalize", "ALPHA"),
    "old_dog_new_pups": ("girl.oldgen.old-dog-new-pups", "OLDGEN"),
    "easy_target": ("girl.newgirl.easy-target", "NEWGIRL"),
}


# Basic Frame Plays retain their own real trigger, resources and result authority.
CORE_NOMINATIONS = {"dive_deep": "play.basic.dive_deep"}


# These real invitation recipes share only their required-source lifecycle.
# Self-Dose keeps its distinct immutable own-recipe proof and effects.
OWN_SEX = {
    alpha.RULE: (alpha.PLAY, "ALPHA"),
    oldgen.RULE: (oldgen.PLAY, "OLDGEN"),
    newgirl.RULE: (newgirl.PLAY, "NEWGIRL"),
    vatgrown.SEX: (vatgrown.PLAY, "VATGROWN"),
    stim.RULE: (stim.PLAY, "STIM-BLISSED"),
    princess.RULE: (princess.PLAY, "PRINCESS"),
    casualty.SEX: (casualty.PLAY, "CASUALTY"),
}
SexRecipe = (
    alpha.Session
    | oldgen.Session
    | newgirl.Session
    | vatgrown.Session
    | stim.Session
    | princess.Session
    | casualty.SexSession
)


def _recipe_target(recipe: SexRecipe) -> ActorRef:
    # The required link keeps an anchor, not a replacement for the actual group.
    # Newgirl proof and prepare retain every original partner and their consent.
    if isinstance(recipe, newgirl.Session):
        if not recipe.partners:
            raise WorkflowError("Recover the actual Newgirl source partners")
        return recipe.partners[0]
    return recipe.target


def _consent_basis(state: GameState, recipe: SexRecipe) -> object:
    if isinstance(recipe, newgirl.Session):
        return tuple(x for x in newgirl.records(state, newgirl.Consent) if x.session == recipe.id)
    return recipe.consent_event


def _sex_session(state: GameState, rule: str, identity: str) -> SexRecipe:
    if rule == casualty.SEX:
        from girlframe.services.m3_casualty import _session

        return _session(state, identity)
    if rule == princess.RULE:
        return princess.get(state, identity)
    if rule == stim.RULE:
        return stim.get(state, identity)
    if rule == vatgrown.SEX:
        return vatgrown.get(state, identity)
    if rule == alpha.RULE:
        return alpha.get(state, identity)
    if rule == newgirl.RULE:
        return newgirl.get(state, identity)
    if rule == oldgen.RULE:
        return oldgen.get(state, identity)
    raise WorkflowError("Recover this actual supported owned intimacy recipe")


def _prove_sex(
    game: GameService, c: Connection, state: GameState, rule: str, identity: str
) -> SexRecipe:
    if rule == casualty.SEX:
        from girlframe.services.m3_casualty import prove_sex

        casualty_value = prove_sex(game, c, state, identity)
        if casualty_value.learned_source is not None:
            raise WorkflowError(
                "This nomination uses the actor's own Casualty recipe, not a lesson"
            )
        return casualty_value
    if rule == princess.RULE:
        from girlframe.services.m3_princess_sex import prove as prove_princess

        princess_value = prove_princess(game, c, state, identity)
        if princess_value.learned_source is not None:
            raise WorkflowError(
                "This nomination uses the actor's own Princess recipe, not a lesson"
            )
        return princess_value
    if rule == stim.RULE:
        from girlframe.services.m3_stim_sex import prove as prove_stim

        stim_value = prove_stim(game, c, state, identity)
        if stim_value.learned_source is not None:
            raise WorkflowError("This nomination uses the actor's own Stim recipe, not a lesson")
        return stim_value
    if rule == vatgrown.SEX:
        from girlframe.services.m3_vatgrown_plays import prove as prove_vatgrown

        vatgrown_value = prove_vatgrown(game, c, state, identity)
        if vatgrown_value.learned_source is not None:
            raise WorkflowError(
                "This nomination uses the actor's own Vatgrown recipe, not a lesson"
            )
        return vatgrown_value
    if rule == alpha.RULE:
        from girlframe.services.m3_alpha_sex import prove as prove_alpha

        return prove_alpha(game, c, state, identity)
    if rule == oldgen.RULE:
        from girlframe.services.m3_oldgen_sex import prove as prove_oldgen

        value = prove_oldgen(game, c, state, identity)
        if value.learned_source is not None:
            raise WorkflowError("This nomination uses the actor's own Oldgen recipe, not a lesson")
        return value
    if rule == newgirl.RULE:
        from girlframe.services.m3_newgirl_sex import prove as prove_newgirl

        newgirl_value = prove_newgirl(game, c, state, identity)
        if newgirl_value.learned_source is not None:
            raise WorkflowError("This nomination uses the actor's own Newgirl recipe, not a lesson")
        return newgirl_value
    raise WorkflowError("Recover the actual supported owned intimacy source")


def _recipe_play(rule: str) -> str:
    return (
        ankou.PLAY
        if rule == ankou.PROCESSOR
        else MOCK_SOURCES[rule]
        if rule in MOCK_SOURCES
        else dose.PLAY
        if rule == dose.RULE
        else OWN_SEX[rule][0]
    )


def _sex_choices(state: GameState) -> tuple[tuple[str, SexRecipe], ...]:
    return (
        tuple((alpha.RULE, x) for x in alpha.sessions(state))
        + tuple((oldgen.RULE, x) for x in oldgen.records(state, oldgen.Session))
        + tuple((newgirl.RULE, x) for x in newgirl.records(state, newgirl.Session))
        + tuple((vatgrown.SEX, x) for x in vatgrown.records(state, vatgrown.Session))
        + tuple((stim.RULE, x) for x in stim.records(state, stim.Session))
        + tuple((princess.RULE, x) for x in princess.sessions(state))
        + tuple((casualty.SEX, x) for x in casualty.records(state, casualty.SexSession))
    )


def _restore_sex(state: GameState, rule: str, recipe: SexRecipe) -> None:
    if rule == alpha.RULE and isinstance(recipe, alpha.Session):
        alpha.put(state, recipe.model_copy(update={"action": None, "phase": "accepted"}))
    elif rule == oldgen.RULE and isinstance(recipe, oldgen.Session):
        oldgen.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    elif rule == newgirl.RULE and isinstance(recipe, newgirl.Session):
        newgirl.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    elif rule == princess.RULE and isinstance(recipe, princess.Session):
        princess.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    elif rule == stim.RULE and isinstance(recipe, stim.Session):
        stim.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    elif rule == casualty.SEX and isinstance(recipe, casualty.SexSession):
        casualty.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    elif rule == vatgrown.SEX and isinstance(recipe, vatgrown.Session):
        vatgrown.put(
            state,
            recipe.model_copy(update={"action": None, "bound_event": None, "phase": "accepted"}),
        )
    else:
        raise WorkflowError("Restore only the original unrolled typed recipe")


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
        *((rule, play, girl) for rule, (play, girl) in OWN_SEX.items()),
        (dose.RULE, dose.PLAY, "STIM-BLISSED"),
        *((rule, play, "MOCKINGBIRD") for rule, play in MOCK_SOURCES.items()),
    ):
        if not has_rule(sheet, rule, girl) or (
            play
            in (
                dose.PLAY,
                oldgen.PLAY,
                newgirl.PLAY,
                vatgrown.PLAY,
                stim.PLAY,
                princess.PLAY,
                casualty.PLAY,
                *MOCK_SOURCES.values(),
            )
            and sheet.girl != girl
        ):
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
    for play, rule in CORE_NOMINATIONS.items():
        try:
            registry.require_available(rule)
        except ValueError:
            continue
        result.append(play)
    from girlframe.services.m3_required_processor import available

    if available(game, c, state, nominee):
        result.append(ankou.PLAY)
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
        or not {
            *(x[0] for x in OWN_SEX.values()),
            dose.PLAY,
            *MOCK_SOURCES.values(),
            *DIRECT_NOMINATIONS,
            *CORE_NOMINATIONS,
            ankou.PLAY,
        }.intersection(value.options)
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
    """Positive actual Task source for finite Plays with no separate recipe ID."""
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in ankou.records(state, ankou.Task)
    ):
        return False
    task = _task(game, c, state, prepared.source_work)
    if (
        prepared.play not in (*DIRECT_NOMINATIONS, *CORE_NOMINATIONS)
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
        or born.withdrawn_event is not None
        or value.id != rules.identity(value.source, value.recipe, value.event)
        or value.model_dump(
            exclude={
                "action",
                "bound_event",
                "completed_event",
                "releases",
                "retired_event",
                "withdrawn_event",
            }
        )
        != born.model_dump(
            exclude={
                "action",
                "bound_event",
                "completed_event",
                "releases",
                "retired_event",
                "withdrawn_event",
            }
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
        if value.rule in OWN_SEX:
            released_recipe = _sex_session(
                _history(c, game, release.event), value.rule, value.recipe
            )
            original_recipe = _sex_session(_history(c, game, value.event), value.rule, value.recipe)
            if (
                released_recipe.phase != "accepted"
                or released_recipe.action is not None
                or _consent_basis(_history(c, game, release.event), released_recipe)
                != _consent_basis(_history(c, game, value.event), original_recipe)
            ):
                raise WorkflowError(
                    "Cancellation preserves the original accepted source without performed effects"
                )
        elif value.rule == ankou.PROCESSOR:
            from girlframe.services.m3_required_processor import prove_recipe

            original_processor = prove_recipe(game, c, _history(c, game, value.event), value)
            released_processor = prove_recipe(game, c, _history(c, game, release.event), value)
            if (
                released_processor != original_processor
                or released_processor.action
                or released_processor.bound_event
            ):
                raise WorkflowError("Preserve the actual unrolled processor proposal")
        elif value.rule in MOCK_SOURCES:
            from girlframe.services.m3_required_mockingbird import prove_trigger

            original_trigger = prove_trigger(game, c, _history(c, game, value.event), value)
            released_trigger = prove_trigger(game, c, _history(c, game, release.event), value)
            if (
                original_trigger != released_trigger
                or released_trigger.state != "ready"
                or released_trigger.action
            ):
                raise WorkflowError("Preserve the original unrolled attested conversation")
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
    if value.withdrawn_event is not None:
        if value.rule == princess.RULE:
            _prove_princess_withdrawal(game, c, value)
        elif value.rule == stim.RULE:
            _prove_stim_withdrawal(game, c, value)
        elif value.rule == ankou.PROCESSOR:
            from girlframe.services.m3_required_processor import (
                prove_withdrawal as prove_processor_withdrawal,
            )

            prove_processor_withdrawal(game, c, state, value)
        else:
            from girlframe.services.m3_required_mockingbird import prove_withdrawal

            prove_withdrawal(game, c, state, value)
    elif value.retired_event and (
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
    value = _birth(game, c, state, identity)
    task = _task(game, c, state, value.source)
    if value.actor != task.actor or value.cast != task.cast:
        raise WorkflowError("Preserve the original nominated actor and source cast")
    if value.rule == ankou.PROCESSOR:
        from girlframe.services.m3_required_processor import prove_recipe

        prove_recipe(game, c, state, value)
        if ankou.PLAY not in task.options:
            raise WorkflowError("Use only the actually nominated Processor Core")
    elif value.rule in MOCK_SOURCES:
        from girlframe.services.m3_required_mockingbird import prove_trigger

        prove_trigger(
            game, c, _history(c, game, value.event) if value.withdrawn_event else state, value
        )
        if MOCK_SOURCES[value.rule] not in task.options:
            raise WorkflowError("Use the actual nominated conversation Play")
    elif value.rule == dose.RULE:
        own_dose = _prove_self_dose(game, c, state, value)
        if dose.PLAY not in task.options or own_dose.target != value.actor:
            raise WorkflowError("Use only the actual nominated owned self-Dose")
    else:
        recipe = _prove_sex(
            game,
            c,
            _history(c, game, value.withdrawn_event) if value.withdrawn_event else state,
            value.rule,
            value.recipe,
        )
        if (
            _recipe_play(value.rule) not in task.options
            or recipe.actor != value.actor
            or _recipe_target(recipe) != value.target
            or fingerprint(recipe.cast) != fingerprint(value.cast)
            or recipe.bonded_source is not None
            or recipe.changeling_source is not None
        ):
            raise WorkflowError(
                "Use this actual actor's own intimacy source; no borrowed or psychic authority"
            )
    if value.bound_event:
        bound = rules.get(_history(c, game, value.bound_event), identity)
        if (
            bound.action != value.action
            or bound.bound_event != value.bound_event
            or (
                value.rule in OWN_SEX
                and _sex_session(state, value.rule, value.recipe).action != value.action
            )
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
    if len(candidates) != 1 or prepared.play != _recipe_play(candidates[0].rule):
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
    if value.rule == ankou.PROCESSOR:
        from girlframe.services.m3_ankou import prepare as prepare_processor

        prepare_processor(game, c, viewer, state, prepared, channel)
    elif value.rule in MOCK_SOURCES:
        from girlframe.services.m3_mockingbird_plays import prepare as prepare_mock

        prepare_mock(game, c, viewer, prepared, state, channel=channel)
    elif value.rule == dose.RULE:
        from girlframe.services.m3_dose_up import prepare as prepare_dose

        prepare_dose(game, c, viewer, state, prepared, channel)
    elif value.rule == casualty.SEX:
        from girlframe.services.m3_casualty import prepare as prepare_casualty

        prepare_casualty(game, c, viewer, state, prepared, channel)
    elif value.rule == princess.RULE:
        from girlframe.services.m3_princess_sex import prepare as prepare_princess

        prepare_princess(game, c, viewer, state, prepared, channel)
    elif value.rule == stim.RULE:
        from girlframe.services.m3_stim_sex import prepare as prepare_stim

        prepare_stim(game, c, viewer, state, prepared, channel)
    elif value.rule == vatgrown.SEX:
        from girlframe.services.m3_vatgrown_plays import prepare as prepare_vatgrown

        prepare_vatgrown(game, c, viewer, state, prepared, channel)
    elif value.rule == newgirl.RULE:
        from girlframe.services.m3_newgirl_sex import prepare as prepare_newgirl

        prepare_newgirl(game, c, viewer, state, prepared, channel)
    elif value.rule == oldgen.RULE:
        from girlframe.services.m3_oldgen_sex import prepare as prepare_oldgen

        prepare_oldgen(game, c, viewer, state, prepared, channel)
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
        or action["data"]["play"] != _recipe_play(value.rule)
        or actual_action_actor(action) != value.actor
        or action["data"].get("prepared", {}).get("source_work") != value.recipe
        or (
            action["data"].get("ankou", {}).get("proposal") != value.recipe
            if value.rule == ankou.PROCESSOR
            else action["data"].get("dose_up", {}).get("required_recipe") != value.recipe
            if value.rule == dose.RULE
            else action["data"].get("mockingbird", {}).get("trigger") != value.recipe
            if value.rule in MOCK_SOURCES
            else action["data"].get(_recipe_play(value.rule), {}).get("session") != value.recipe
        )
        or meta.get("id") != value.source
        or meta.get("required_link") != value.id
        or meta.get("recipe") != value.recipe
    ):
        raise WorkflowError("Preserve both exact original required context and actual owned recipe")


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
    if value.rule == ankou.PROCESSOR:
        if action["data"].get("ankou", {}).get("phase") != "complete":
            return False
        from girlframe.services.m3_ankou import prove_source

        processor = prove_source(game, c, state, action["id"])
        ready = processor.actor == value.actor and bool(processor.completed_event)
    elif value.rule in MOCK_SOURCES:
        from girlframe.services.m3_required_mockingbird import prove_trigger

        trigger = prove_trigger(game, c, state, value)
        ready = trigger.state == "complete" and trigger.action == action["id"]
    elif value.rule == dose.RULE:
        if action["data"].get("dose_up", {}).get("phase") != "complete":
            return False
        from girlframe.services.m3_dose_up import prove as prove_dose

        actual_dose = prove_dose(game, c, state, action["id"])
        ready = actual_dose.actor == value.actor and actual_dose.target == value.target
    else:
        ready = _sex_session(state, value.rule, value.recipe).phase == "complete"
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
            if any(x.id == recipe for x in ankou.records(state, ankou.Proposal)):
                from girlframe.services.m3_required_processor import link_recipe

                return link_recipe(self.game, c, state, viewer, key, task, recipe)
            if any(
                x.id == recipe and x.play in MOCK_SOURCES.values()
                for x in state.mockingbird.triggers
            ):
                from girlframe.services.m3_required_mockingbird import link_trigger

                return link_trigger(self.game, c, state, viewer, key, task, recipe)
            matches = [
                (rule, candidate)
                for rule, candidate in _sex_choices(state)
                if candidate.id == recipe
            ]
            if len(matches) != 1:
                raise WorkflowError("Choose one actual supported owned source recipe")
            rule, _ = matches[0]
            if OWN_SEX[rule][0] not in task.options:
                raise WorkflowError("This own Play was not offered by these actual nominators")
            own = _prove_sex(self.game, c, state, rule, recipe)
            if (
                own.phase != "accepted"
                or own.action
                or own.actor != task.actor
                or own.bonded_source is not None
                or own.changeling_source is not None
                or fingerprint(own.cast) != fingerprint(task.cast)
            ):
                raise WorkflowError(
                    "Select an accepted unperformed OWN source in this original scene"
                )
            if rule == alpha.RULE:
                from girlframe.services.m3_alpha_sex import _contact

                assert isinstance(own, alpha.Session)
                _contact(self.game, c, state, own.actor, own.target, own.cast.channel)
            elif rule == casualty.SEX:
                from girlframe.services.m3_casualty import _contact as casualty_contact

                assert isinstance(own, casualty.SexSession)
                casualty_contact(self.game, c, state, own)
            elif rule == princess.RULE:
                from girlframe.services.m3_princess_sex import _contact as princess_contact

                assert isinstance(own, princess.Session)
                princess_contact(self.game, c, state, own.actor, own.target, own.cast.channel)
            elif rule == stim.RULE:
                from girlframe.services.m3_stim_sex import _contact as stim_contact

                assert isinstance(own, stim.Session)
                stim_contact(self.game, c, state, own)
            elif rule == vatgrown.SEX:
                from girlframe.services.m3_vatgrown_plays import _contact as vatgrown_contact

                assert isinstance(own, vatgrown.Session)
                vatgrown_contact(self.game, c, state, own)
            elif rule == newgirl.RULE:
                from girlframe.services.m3_newgirl_sex import _contact as newgirl_contact

                assert isinstance(own, newgirl.Session)
                newgirl_contact(self.game, c, state, own)
            else:
                from girlframe.services.m3_oldgen_sex import _contact as oldgen_contact

                assert isinstance(own, oldgen.Session)
                oldgen_contact(self.game, c, state, own)
            from girlframe.services.p1_source_pause import require_ready

            require_ready(self.game, c, state, task.id)
            event = str(uuid4())
            value = rules.RequiredLink(
                id=rules.identity(source, recipe, event),
                source=source,
                recipe=recipe,
                rule=(
                    "girl.casualty.sex-play"
                    if rule == casualty.SEX
                    else "girl.princess.sex-play"
                    if rule == princess.RULE
                    else "girl.stim-blissed.sex-play"
                    if rule == stim.RULE
                    else "girl.vatgrown.sex-play"
                    if rule == vatgrown.SEX
                    else "girl.newgirl.sex-play"
                    if rule == newgirl.RULE
                    else "girl.oldgen.sex-play"
                    if rule == oldgen.RULE
                    else "girl.alpha.sex-play"
                ),
                actor=own.actor,
                target=_recipe_target(own),
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

    def withdraw_princess(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            task = self._owner(c, viewer, state, value.source)
            if state.revision != revision:
                raise WorkflowError("STALE_REQUIRED_PLAY: reopen the actual source")
            if (
                value.rule != princess.RULE
                or value.action
                or value.bound_event
                or value.retired_event
                or value.completed_event
                or value.releases
                or task.child
                or task.completed_event
            ):
                raise WorkflowError("Withdraw only this unprepared selection; the Play stays owed")
            recipe = _prove_sex(self.game, c, state, value.rule, value.recipe)
            assert isinstance(recipe, princess.Session)
            if (
                recipe.phase != "accepted"
                or recipe.action
                or recipe.bound_event
                or recipe.effect_event
            ):
                raise WorkflowError("Preserve the actual unperformed accepted Princess source")
            event = str(uuid4())
            rules.put(
                state, value.model_copy(update={"retired_event": event, "withdrawn_event": event})
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.required_princess_withdrawn",
                state,
                event_id=event,
                link=value.id,
                source=value.source,
                recipe=value.recipe,
            )
            return dict(id=value.id, source=value.source, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.required_princess_withdrawn",
            dict(link=identity, revision=revision),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def withdraw_stim(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            task = self._owner(c, viewer, state, value.source)
            if state.revision != revision:
                raise WorkflowError("STALE_REQUIRED_PLAY: reopen the actual source")
            if (
                value.rule != stim.RULE
                or value.action
                or value.bound_event
                or value.retired_event
                or value.completed_event
                or value.releases
                or task.child
                or task.completed_event
            ):
                raise WorkflowError("Withdraw only this unprepared selection; the Play stays owed")
            recipe = _prove_sex(self.game, c, state, value.rule, value.recipe)
            assert isinstance(recipe, stim.Session)
            if (
                recipe.phase != "accepted"
                or recipe.action
                or recipe.bound_event
                or recipe.effect_event
            ):
                raise WorkflowError("Preserve the actual unperformed accepted Stim source")
            event = str(uuid4())
            rules.put(
                state, value.model_copy(update={"retired_event": event, "withdrawn_event": event})
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.required_stim_withdrawn",
                state,
                event_id=event,
                link=value.id,
                source=value.source,
                recipe=value.recipe,
            )
            return dict(id=value.id, source=value.source, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.required_stim_withdrawn",
            dict(link=identity, revision=revision),
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
            accepted = []
            invitations = []
            for rule, recipe in _sex_choices(state):
                if (
                    OWN_SEX[rule][0] not in task.options
                    or recipe.actor != task.actor
                    or recipe.cast.id != task.cast.id
                    or recipe.bonded_source
                    or recipe.changeling_source
                    or (
                        isinstance(
                            recipe,
                            (
                                oldgen.Session,
                                newgirl.Session,
                                vatgrown.Session,
                                stim.Session,
                                princess.Session,
                                casualty.SexSession,
                            ),
                        )
                        and recipe.learned_source
                    )
                ):
                    continue
                if recipe.phase == "accepted" and recipe.action is None:
                    _prove_sex(self.game, c, state, rule, recipe.id)
                    if rule == princess.RULE:
                        from girlframe.services.m3_princess_sex import _contact as princess_contact

                        assert isinstance(recipe, princess.Session)
                        try:
                            princess_contact(
                                self.game,
                                c,
                                state,
                                recipe.actor,
                                recipe.target,
                                recipe.cast.channel,
                            )
                        except (WorkflowError, ValueError):
                            continue
                    if rule == stim.RULE:
                        from girlframe.services.m3_stim_sex import _contact as stim_contact

                        assert isinstance(recipe, stim.Session)
                        try:
                            stim_contact(self.game, c, state, recipe)
                        except (WorkflowError, ValueError):
                            continue
                    if rule == casualty.SEX:
                        from girlframe.services.m3_casualty import _contact as casualty_contact

                        assert isinstance(recipe, casualty.SexSession)
                        try:
                            casualty_contact(self.game, c, state, recipe)
                        except (WorkflowError, ValueError):
                            continue
                    accepted.append(
                        dict(
                            id=recipe.id,
                            rule=rule,
                            play=OWN_SEX[rule][0],
                            label=OWN_SEX[rule][1].title()
                            + " with "
                            + resolve(
                                state, _recipe_target(recipe), profiles(c, self.store.campaign_id)
                            ).label
                            + (
                                f" and {len(recipe.partners) - 1} other confirmed partner(s)"
                                if isinstance(recipe, newgirl.Session) and len(recipe.partners) > 1
                                else ""
                            ),
                            target=_recipe_target(recipe).model_dump(mode="json"),
                        )
                    )
                elif recipe.phase == "invited":
                    invitations.append(
                        dict(id=recipe.id, label="Await actual counterpart confirmation")
                    )
            from girlframe.services.m3_required_mockingbird import menu_triggers

            mock_accepted, mock_invitations = menu_triggers(self.game, c, state, task)
            from girlframe.services.m3_required_processor import menu_recipes

            accepted.extend(menu_recipes(self.game, c, state, task))
            accepted.extend(mock_accepted)
            invitations.extend(mock_invitations)
            from girlframe.services.p1_source_pause import projection as pause

            return dict(
                source=source,
                self_dose=(
                    dose.PLAY in task.options
                    and dose.PLAY in nomination_options(self.game, c, state, task.actor)
                ),
                processor_offered=(
                    ankou.PLAY in task.options
                    and ankou.PLAY in nomination_options(self.game, c, state, task.actor)
                ),
                mockingbird_offered=bool(set(MOCK_SOURCES.values()).intersection(task.options)),
                alpha_offered=alpha.PLAY in task.options,
                oldgen_offered=oldgen.PLAY in task.options,
                newgirl_offered=newgirl.PLAY in task.options,
                vatgrown_offered=vatgrown.PLAY in task.options,
                stim_offered=stim.PLAY in task.options,
                princess_offered=princess.PLAY in task.options,
                casualty_offered=casualty.PLAY in task.options,
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
    if value.rule == ankou.PROCESSOR:
        from girlframe.services.m3_required_processor import prove_recipe

        proposal = prove_recipe(game, c, state, value)
        if proposal.action != action["id"] or any(
            x.id == action["id"] for x in ankou.records(state, ankou.Processor)
        ):
            raise WorkflowError("Preserve every actual processor effect")
        ankou.put(state, proposal.model_copy(update={"action": None, "bound_event": None}))
    elif value.rule in OWN_SEX:
        recipe = _sex_session(state, value.rule, value.recipe)
        if (
            recipe.phase != ("bound" if value.rule in (newgirl.RULE, casualty.SEX) else "active")
            or recipe.action != action["id"]
            or recipe.effect_event
        ):
            raise WorkflowError("Preserve every actual owned source effect")
        _restore_sex(state, value.rule, recipe)
    elif value.rule in MOCK_SOURCES:
        from girlframe.services.m3_required_mockingbird import prove_trigger

        trigger = prove_trigger(game, c, state, value)
        if trigger.state != "ready" or trigger.action is not None:
            raise WorkflowError("Preserve the actual performed conversation and its receipt")
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


def _prove_stim_withdrawal(game: GameService, c: Connection, value: rules.RequiredLink) -> None:
    if (
        value.rule != stim.RULE
        or not value.withdrawn_event
        or value.retired_event != value.withdrawn_event
        or value.action
        or value.bound_event
        or value.completed_event
        or value.releases
    ):
        raise WorkflowError("Preserve the actual unprepared Stim selection withdrawal")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.withdrawn_event,
        )
    ).first()
    payload = json.loads(audit.payload_json) if audit else {}
    withdrawn = _history(c, game, value.withdrawn_event)
    recipe = _prove_sex(game, c, withdrawn, value.rule, value.recipe)
    assert isinstance(recipe, stim.Session)
    task = _task(game, c, withdrawn, value.source)
    if (
        audit is None
        or audit.kind != "m3.required_stim_withdrawn"
        or audit.actor_id != value.actor.entity
        or payload.get("link") != value.id
        or payload.get("source") != value.source
        or payload.get("recipe") != value.recipe
        or rules.get(withdrawn, value.id) != value
        or recipe.phase != "accepted"
        or recipe.action
        or recipe.bound_event
        or recipe.effect_event
        or task.child
        or task.completed_event
    ):
        raise WorkflowError("Recover the owner-authored withdrawal without resolving the owed Task")


def _prove_princess_withdrawal(game: GameService, c: Connection, value: rules.RequiredLink) -> None:
    if (
        value.rule != princess.RULE
        or not value.withdrawn_event
        or value.retired_event != value.withdrawn_event
        or value.action
        or value.bound_event
        or value.completed_event
        or value.releases
    ):
        raise WorkflowError("Preserve the actual unprepared Princess selection withdrawal")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.withdrawn_event,
        )
    ).first()
    payload = json.loads(audit.payload_json) if audit else {}
    withdrawn = _history(c, game, value.withdrawn_event)
    recipe = _prove_sex(game, c, withdrawn, value.rule, value.recipe)
    assert isinstance(recipe, princess.Session)
    task = _task(game, c, withdrawn, value.source)
    if (
        audit is None
        or audit.kind != "m3.required_princess_withdrawn"
        or audit.actor_id != value.actor.entity
        or payload.get("link") != value.id
        or payload.get("source") != value.source
        or payload.get("recipe") != value.recipe
        or rules.get(withdrawn, value.id) != value
        or recipe.phase != "accepted"
        or recipe.action
        or recipe.bound_event
        or recipe.effect_event
        or task.child
        or task.completed_event
    ):
        raise WorkflowError("Recover the owner-authored withdrawal without resolving the owed Task")
