"""A concealed mission threat is consumed by the actual original Rebel's Assault."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_ambush as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_resources import rebel_inventory
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_missions import Mission
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Ambush, ...]:
    return tuple(
        x
        for x in rules.ambushes(state)
        if x.mission is not None
        and (
            x.controller == viewer.user_id
            or x.handler.entity == str(viewer.user_id)
            and same_handler_body(state, x.handler)
        )
    )


def _mission(c: Connection, game: GameService, case: rules.Ambush) -> Mission:
    if case.mission is None or case.dispatch is None:
        raise WorkflowError("Wait for the actual next mission to dispatch")
    proof = c.execute(
        sa.select(t.events.c.kind, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == case.dispatch,
        )
    ).first()
    if (
        proof is None
        or proof.kind != "m3.mission_started"
        or json.loads(proof.payload_json).get("mission_id") != case.mission
    ):
        raise WorkflowError("Recover the actual original mission dispatch")
    return MissionService(game.store)._mission(c, case.mission)


def _resources(c: Connection, game: GameService, state: GameState, case: rules.Ambush) -> None:
    if rules.attacker(state, case.attacker) != case.controller:
        raise WorkflowError("The actual Rebel controller changed")
    inventory = rebel_inventory(state, case.attacker)
    assert inventory is not None
    proof = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == inventory.initial_event,
        )
    ).first()
    if (
        proof is None
        or proof.kind != "m3.rebel_inventory_confirmed"
        or proof.actor_id != str(case.controller)
        or json.loads(proof.payload_json).get("actor_ref") != case.attacker.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the actual original Rebel inventory source")


def _targets(
    state: GameState, mission: Mission, case: rules.Ambush, cast: SceneCast
) -> tuple[ActorRef, ...]:
    if not any(
        role.actor == case.attacker and role.controller == case.controller for role in cast.roles
    ):
        return ()
    hunt = (
        next((x for x in rules.hunts(state) if x.id == case.pursuit), None)
        if case.pursuit
        else None
    )
    if case.pursuit and (
        hunt is None
        or hunt.ended is not None
        or hunt.source != case.source
        or hunt.attacker != case.attacker
        or hunt.controller != case.controller
    ):
        return ()
    return tuple(
        x.actor
        for x in cast.roles
        if x.actor.kind == "pilot"
        and x.controller == int(x.actor.entity)
        and x.controller != case.controller
        and (hunt is None or x.actor == hunt.victim)
        and mission.character_ids.get(x.actor.entity) == x.actor.incarnation
        and x.actor.entity not in mission.ended_participants
        and (sheet := state.sheets.get(x.actor.entity)) is not None
        and sheet.character_id == x.actor.incarnation
    )


def _case(state: GameState, viewer: GuildViewer, identity: str) -> rules.Ambush:
    value = next((x for x in visible(state, viewer) if x.id == identity), None)
    if value is None:
        raise WorkflowError("This attack belongs to its original Rebel and Handler")
    return value


def _cast(game: GameService, c: Connection, state: GameState, channel: int) -> SceneCast | None:
    from girlframe.services.m3_battle import _cast as battle_cast

    try:
        return battle_cast(game, c, state, channel)
    except WorkflowError:
        return None


def scoped(state: GameState, actor: ActorRef, channel: int) -> bool:
    return any(
        x.attacker == actor and x.channel == channel and x.completed is None
        for x in rules.ambushes(state)
    )


def context(
    c: Connection,
    game: GameService,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    cast: SceneCast,
) -> rules.Ambush:
    result = next(
        (
            x
            for x in rules.ambushes(state)
            if x.attacker == actor
            and x.target == target
            and x.channel == cast.channel
            and x.scene == cast.id
            and x.action is None
        ),
        None,
    )
    if result is None or result.opening is None:
        raise WorkflowError("Open the original mission ambush before rolling this Rebel Assault")
    proof = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == result.opening,
        )
    ).first()
    if (
        proof is None
        or proof.kind != "m3.rebel_ambush_opened"
        or proof.actor_id != str(result.controller)
        or json.loads(proof.payload_json).get("work_id") != result.id
    ):
        raise WorkflowError("Recover the actual original Rebel's opening receipt")
    mission = _mission(c, game, result)
    _resources(c, game, state, result)
    if mission.phase != "active" or target not in _targets(state, mission, result, cast):
        raise WorkflowError("The original attacker and mission target must still be present")
    acting = resolve(state, actor, ())
    defender = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not acting.piloting or acting.cell is None or defender.cell != acting.cell:
        raise WorkflowError("Recover the actual co-located mission opening and piloted Rebel Frame")
    return result


def claim(c: Connection, game: GameService, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["battle"]
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    cast = _cast(game, c, state, int(action["channel_id"]))
    if cast is None:
        raise WorkflowError("Recover the actual original mission ambush scene")
    value = context(c, game, state, actor, target, cast)
    if value.id != meta["rebel_ambush"] or value.controller != int(action["actor_id"]):
        raise WorkflowError("Use the actual original prepared Rebel attack")
    rules.save(state, value.model_copy(update=dict(action=action["id"])))


def require_completed(
    c: Connection, game: GameService, state: GameState, mission: Mission, event: str | None = None
) -> None:
    for case in rules.ambushes(state):
        if case.mission != mission.id or case.completed:
            continue
        if case.action is None:
            raise WorkflowError(
                "Complete the actual Rebel ambush against this mission before ending it"
            )
        action = game.action(c, case.action)
        meta = action["data"].get("battle", {})
        if (
            action["state"] != "complete"
            or action["data"].get("play") != "all_out_assault"
            or action["scene_id"] != case.scene
            or action["actor_id"] != str(case.controller)
            or meta.get("rebel_ambush") != case.id
            or meta.get("roll_event") is None
            or meta.get("actor") != case.attacker.model_dump(mode="json")
            or case.target is None
            or meta.get("target") != case.target.model_dump(mode="json")
        ):
            raise WorkflowError(
                "Complete the actual original ambush and its native combat consequences"
            )
        if event is not None:
            rules.save(state, case.model_copy(update=dict(completed=event)))


class AmbushService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def get(self, viewer: GuildViewer, identity: str, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = _case(state, viewer, identity)
            cast = (
                _cast(self.game, c, state, channel) if viewer.user_id == case.controller else None
            )
            mission = _mission(c, self.game, case)
            targets: tuple[tuple[str, str], ...] = ()
            if case.opening is None and cast is not None and mission.phase == "active":
                targets = tuple(
                    (x.entity, state.sheets[x.entity].callsign)
                    for x in _targets(state, mission, case, cast)
                )
            return dict(
                revision=state.revision,
                targets=targets,
                opened=bool(case.opening),
                used=bool(case.action),
                complete=bool(case.completed),
            )

    def open(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        recipient: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError("Describe the actual attempt to capture the original Girl")
        missions = MissionService(self.store)

        def authorize(c: Connection) -> None:
            missions.access.authorize(c, viewer, "plays")
            missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            if (
                _case(load_state(c, self.store.campaign_id), viewer, identity).controller
                != viewer.user_id
            ):
                raise WorkflowError("Only the original Rebel opens the actual attack")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = _case(state, viewer, identity)
            _resources(c, self.game, state, case)
            cast = _cast(self.game, c, state, channel)
            mission = _mission(c, self.game, case)
            attacker = resolve(state, case.attacker, ())
            eligible = _targets(state, mission, case, cast) if cast is not None else ()
            target = next((x for x in eligible if x.entity == recipient), None)
            if (
                state.revision != revision
                or case.opening is not None
                or cast is None
                or target is None
                or mission.phase != "active"
                or self.game.pending_actions(c)
                or not attacker.piloting
                or attacker.cell is None
                or resolve(
                    state,
                    target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).cell
                != attacker.cell
                or any(
                    x.id != case.id
                    and x.attacker == case.attacker
                    and x.channel == channel
                    and x.target == target
                    and x.action is None
                    for x in rules.ambushes(state)
                )
            ):
                raise WorkflowError(
                    "Reopen the actual mission cast with the original target and an operating Frame"
                )
            event = str(uuid4())
            rules.save(
                state,
                case.model_copy(
                    update=dict(
                        channel=channel,
                        scene=cast.id,
                        target=target,
                        opening=event,
                        opening_account=account,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_ambush_opened",
                state,
                event_id=event,
                work_id=identity,
            )
            return dict(id=identity, opened=True)

        return missions._write(
            viewer,
            key,
            "m3.rebel_ambush_opened",
            dict(
                id=identity, revision=revision, channel=channel, target=recipient, account=account
            ),
            operation,
            authorize,
        )


def visible_hunts(state: GameState, viewer: GuildViewer) -> tuple[rules.Hunt, ...]:
    return tuple(
        x
        for x in rules.hunts(state)
        if x.controller == viewer.user_id
        or x.handler.entity == str(viewer.user_id)
        and same_handler_body(state, x.handler)
    )


def hunt_options(
    state: GameState, value: rules.Hunt, viewer: GuildViewer
) -> tuple[tuple[str, str], ...]:
    attempts = tuple(x for x in rules.ambushes(state) if x.pursuit == value.id)
    if value.ended or not attempts or any(not x.completed for x in attempts):
        return ()
    if viewer.user_id == value.controller and value.proposal is None:
        return (("propose", "Permanently abandon the pursuit"),)
    if value.handler.entity == str(viewer.user_id) and value.proposal is not None:
        return (("approve", "Confirm the pursuit has ended"), ("decline", "Keep it active"))
    return ()


class HuntService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _hunt(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Hunt:
        value = next((x for x in visible_hunts(state, viewer) if x.id == identity), None)
        if value is None:
            raise WorkflowError("The pursuit belongs to its original Rebel and Handler")
        return value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = self._hunt(state, viewer, identity)
            return dict(
                revision=state.revision,
                ended=bool(value.ended),
                proposal=value.withdrawal,
                choices=hunt_options(state, value, viewer),
                attempts=sum(
                    x.pursuit == identity and bool(x.completed) for x in rules.ambushes(state)
                ),
            )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, action: str, account: str
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError(
                "Record your own reason for permanently ending or keeping the pursuit"
            )
        missions = MissionService(self.store)

        def authorize(c: Connection) -> None:
            missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._hunt(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = self._hunt(state, viewer, identity)
            members = HandlerService(self.store)
            if (
                state.revision != revision
                or self.game.pending_actions(c)
                or action not in {x[0] for x in hunt_options(state, value, viewer)}
                or not same_handler_body(state, value.handler)
                or not members._member(c, value.controller)
                or rules.attacker(state, value.attacker) != value.controller
                or any(
                    _mission(c, self.game, attempt).phase != "complete"
                    for attempt in rules.ambushes(state)
                    if attempt.pursuit == value.id
                )
            ):
                raise WorkflowError(
                    "Reopen the original pursuit with its actual parties between missions"
                )
            event = str(uuid4())
            if action == "propose":
                updated = value.model_copy(update=dict(proposal=event, withdrawal=account))
            else:
                proof = c.execute(
                    sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == value.proposal,
                    )
                ).first()
                if (
                    proof is None
                    or proof.kind != "m3.rebel_hunt_reviewed"
                    or proof.actor_id != str(value.controller)
                    or json.loads(proof.payload_json).get("work_id") != identity
                ):
                    raise WorkflowError("Recover the original Rebel's actual withdrawal")
                updated = (
                    value.model_copy(update=dict(ended=event, reason=account))
                    if action == "approve"
                    else value.model_copy(update=dict(proposal=None, withdrawal=""))
                )
            rules.save_hunt(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_hunt_reviewed",
                state,
                event_id=event,
                work_id=identity,
                decision=action,
            )
            return dict(id=identity, ended=bool(updated.ended))

        return missions._write(
            viewer,
            key,
            "m3.rebel_hunt_reviewed",
            dict(id=identity, revision=revision, action=action, account=account),
            operation,
            authorize,
        )
