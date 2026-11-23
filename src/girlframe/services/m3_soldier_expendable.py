"""An original Soldier may consent to take the actual hit from another Pilot's Defeat."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import update
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "ancillary.soldier.expendable"
OPTION = "soldier_take_hit"
REQUEST = "defeat_soldier_consent"


def candidates(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[tuple[ActorView, CastRole], ...]:
    data = action["data"]
    result = data.get("result", {})
    if (
        data.get("play") != "defeat"
        or result.get("tier") != "low"
        or data.get("receipt") is None
        or not ancillary.records(state)
    ):
        return ()
    approval, registry = game.store.policy.m3_approval, Access(game.store).registry
    if (
        approval is None
        or registry is None
        or "plays" not in approval.subsystems
        or digest(registry) != approval.registry_sha256
    ):
        return ()
    try:
        for rule in (ancillary.RULE, ancillary.STARTERS["SOLDIER"].rule, RULE):
            registry.require_available(rule)
    except ValueError:
        return ()
    cast = next((x for x in state.scene_casts if x.id == action["scene_id"] and x.open), None)
    if cast is None:
        return ()
    defeated = ActorRef.model_validate(data["defeat"]["actor"])
    bound = profiles(c, game.store.campaign_id)
    victim = resolve(state, defeated, bound, require_current_profile=False)
    if (
        victim.cell is None
        or victim.offstage_source
        or not any(x.actor == defeated and x.controller == victim.controller for x in cast.roles)
    ):
        return ()
    declined = set(data.get("soldiers_declined", ()))
    options = []
    for role in cast.roles:
        record = ancillary.find(state, role.actor)
        if (
            record is None
            or record.draft.book != "SOLDIER"
            or role.controller not in data["participants"]
            or role.actor.token in declined
            or not HandlerService(game.store)._member(c, role.controller)
        ):
            continue
        try:
            actual = resolve(state, role.actor, bound, require_current_profile=False)
        except ValueError:
            continue
        if (
            actual.controller == role.controller
            and actual.alive
            and actual.cell == victim.cell
            and not actual.offstage_source
            and actual.custody in (None, "free")
        ):
            options.append((actual, role))
    return tuple(options)


def ask(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    token = answer.fields.get("soldier")
    if (
        answer.options != (OPTION,)
        or set(answer.fields) != {"soldier"}
        or answer.flag is not None
        or answer.denied
        or answer.number is not None
        or answer.member is not None
        or not answer.text.strip()
    ):
        raise WorkflowError("Choose one actual Soldier instead of another Defeat consequence.")
    selected = next(
        (x for x in candidates(game, c, state, action) if x[0].ref.token == token), None
    )
    if selected is None:
        raise WorkflowError("The original Soldier is no longer available for this rolled Defeat.")
    soldier, role = selected
    action["data"]["soldier_expendable"] = dict(
        soldier=soldier.ref.model_dump(mode="json"),
        controller=soldier.controller,
        role_source=role.source_event,
        label=soldier.label,
        token=soldier.ref.token,
        context=answer.text.strip(),
        asked=action["data"]["response_event"],
    )
    game.request(c, action, soldier.controller, REQUEST)


def answer_request(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    data = action["data"]
    source = data.get("soldier_expendable")
    if (
        source is None
        or str(source["controller"]) != str(request["actor_id"])
        or answer.flag is None
        or answer.options
        or answer.denied
        or answer.number is not None
        or answer.member is not None
        or answer.fields
    ):
        raise WorkflowError(
            "Only the original Soldier's controller may confirm or decline the hit."
        )
    if not answer.flag:
        data.setdefault("soldiers_declined", []).append(source["token"])
        data.pop("soldier_expendable")
        game.request(c, action, int(action["actor_id"]), "defeat_select")
        return
    exact = next(
        (
            x
            for x in candidates(game, c, state, action)
            if x[0].ref.model_dump(mode="json") == source["soldier"]
            and x[1].source_event == source["role_source"]
            and x[0].controller == source["controller"]
        ),
        None,
    )
    if exact is None or state.world is None or not answer.text.strip():
        raise WorkflowError(
            "Confirm the original living Soldier and its actual fatal intervention."
        )
    soldier, _ = exact
    state.world = update(
        state.world,
        pilots=tuple(
            x.model_copy(update={"alive": False}) if x.id == soldier.ref.entity else x
            for x in state.world.pilots
        ),
    )
    event = data["response_event"]
    protected = ActorRef.model_validate(data["defeat"]["actor"]).model_dump_json()
    state.facts.append(
        dict(
            kind="soldier_expendable",
            action=action["id"],
            event=event,
            actor=soldier.ref.model_dump_json(),
            protected=protected,
            source=source["asked"],
            account=answer.text.strip(),
        )
    )
    state.facts.append(
        dict(
            kind="defeat_resolved",
            action=action["id"],
            actor=protected,
            source_event=event,
            account=source["context"],
        )
    )
    data["result"].update(
        expendable=True,
        true_consequence="soldier_takes_fatal_hit",
    )
    ChoiceEngine(game).finish(c, state, action)
