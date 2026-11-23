"""Source-bound Experimental Abysstech contact and owned consequences."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, AssetView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import assets, damage
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "ancillary.abyssal-acolyte.experimental-abysstech"
KIND = "experimental_abysstech"


class Contact(Model):
    id: str
    scene: str
    channel: int
    acolyte: ActorRef
    owner: int
    girl: ActorRef
    respondent: int
    tool: str
    account: str
    asset: str | None = None
    contact_event: str | None = None
    pressure: str | None = None
    outcome: Literal["declined", "heat", "damage", "helpless"] | None = None
    resolved: str | None = None


def records(state: GameState) -> tuple[Contact, ...]:
    return tuple(
        Contact.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class AbysstechService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        gate = Access(self.store)
        gate.require_specialist_rule(RULE)
        assert gate.registry is not None
        gate.registry.require_available(ancillary.STARTERS["ABYSSAL ACOLYTE"].rule)

    def _acolyte(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
    ) -> tuple[SceneCast, ActorView, dict[str, AssetView]]:
        cast = _cast(self.game, c, state, channel)
        bound = profiles(c, self.store.campaign_id)
        actual = resolve(state, actor, bound, require_current_profile=False)
        role = ancillary.find(state, actor)
        if (
            role is None
            or role.draft.book != "ABYSSAL ACOLYTE"
            or not actual.alive
            or actual.offstage_source
            or actual.cell is None
            or actual.custody not in (None, "free")
            or not any(x.actor == actor and x.controller == actual.controller for x in cast.roles)
        ):
            raise WorkflowError("Recover the actual local original Abyssal Acolyte")
        tools = {
            x.id: x for x in assets(state, actor, bound) if x.family == "girl" and not x.damaged
        }
        return cast, actual, tools

    def _girls(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        acolyte: ActorView,
    ) -> dict[ActorRef, ActorView]:
        bound = profiles(c, self.store.campaign_id)
        people = {}
        for role in cast.roles:
            if role.actor.kind != "pilot" or role.controller == acolyte.controller:
                continue
            try:
                girl = resolve(state, role.actor, bound, require_current_profile=False)
            except ValueError:
                continue
            if (
                girl.controller == role.controller
                and girl.rules == "girl_frame"
                and not girl.offstage_source
                and girl.cell == acolyte.cell
                and girl.inside_frame is False
            ):
                people[girl.ref] = girl
        return people

    def _source(
        self,
        c: Connection,
        state: GameState,
        case: Contact,
    ) -> tuple[ActorView, dict[str, AssetView]]:
        cast, actor, tools = self._acolyte(c, state, case.channel, case.acolyte)
        girl = self._girls(c, state, cast, actor).get(case.girl)
        if (
            girl is None
            or actor.controller != case.owner
            or girl.controller != case.respondent
            or cast.id != case.scene
            or case.tool not in tools
        ):
            raise WorkflowError("Recover the same original people, scene, and equipment")
        available = {
            x.id: x
            for x in assets(state, girl.ref, profiles(c, self.store.campaign_id))
            if x.void and not x.damaged and x.family == "girl"
        }
        if case.asset is not None and case.asset not in available:
            raise WorkflowError("The original contacted Asset is no longer accessible")
        return girl, available

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.experimental_abysstech",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        case: Contact,
        kind: str,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
        state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))
        self.game.event(c, viewer.user_id, key, "m3.abysstech_" + kind, state, event_id=event)
        return dict(id=case.id, outcome=case.outcome)

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast, actual, tools = self._acolyte(c, state, channel, actor)
            if actual.controller != viewer.user_id:
                raise WorkflowError("Only the original Acolyte reaches with their own equipment")
            return dict(
                revision=state.revision,
                tools={x.id: x.name for x in tools.values()},
                people={x.ref.token: x.label for x in self._girls(c, state, cast, actual).values()},
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        tool: str,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, actual, tools = self._acolyte(c, state, channel, actor)
            girl = next(
                (x for x in self._girls(c, state, cast, actual).values() if x.ref.token == target),
                None,
            )
            if (
                state.revision != revision
                or actual.controller != viewer.user_id
                or tool not in tools
                or girl is None
                or not 0 < len(account.strip()) <= 1200
                or any(
                    x.scene == cast.id
                    and x.acolyte == actor
                    and x.girl == girl.ref
                    and not x.resolved
                    for x in records(state)
                )
            ):
                raise WorkflowError("Select your own tool and an actual other Girl in this scene")
            event = str(uuid4())
            case = Contact(
                id=event,
                scene=cast.id,
                channel=channel,
                acolyte=actor,
                owner=actual.controller,
                girl=girl.ref,
                respondent=girl.controller,
                tool=tool,
                account=account.strip(),
            )
            return self._save(c, state, viewer, key, case, "proposed", event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                tool=tool,
                target=target,
                account=account,
            ),
            operation,
        )

    def _step(self, case: Contact, user: int) -> str | None:
        if case.resolved:
            return None
        if user == case.respondent:
            return "contact" if case.asset is None else "pressure" if case.pressure else None
        if user == case.owner and case.asset and case.pressure is None:
            return "choose"
        return None

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        rows = [
            (case.id, step)
            for case in records(state)
            if (step := self._step(case, viewer.user_id)) is not None
        ]
        if not rows:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        return tuple(rows)

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> tuple[Contact, str]:
        case = next((x for x in records(state) if x.id == identity), None)
        step = self._step(case, viewer.user_id) if case else None
        if case is None or step is None:
            raise WorkflowError("This original Abysstech choice is unavailable")
        return case, step

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._case(state, viewer, identity)
            _, options = self._source(c, state, case)
            return dict(
                revision=state.revision,
                step=step,
                account=case.account,
                assets={x.id: x.name for x in options.values()} if step == "contact" else {},
                asset=options[case.asset].name if case.asset else None,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        choice: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case, stage = self._case(state, viewer, identity)
            require_scene_clear(self.game, c, case.channel)
            if state.revision != revision or stage != step:
                raise WorkflowError("STALE_ABYSSTECH: reopen the original private choice")
            girl, options = self._source(c, state, case)
            event = str(uuid4())
            if stage == "contact":
                if choice == "decline":
                    case = case.model_copy(update=dict(outcome="declined", resolved=event))
                elif choice in options:
                    case = case.model_copy(update=dict(asset=choice, contact_event=event))
                else:
                    raise WorkflowError(
                        "Confirm the actual contacted and accessible owned Void Asset"
                    )
            elif stage == "choose" and choice == "heat":
                acolyte = ancillary.find(state, case.acolyte)
                assert acolyte is not None
                ancillary.put(state, acolyte.model_copy(update=dict(heat=acolyte.heat + 2)))
                case = case.model_copy(update=dict(outcome="heat", resolved=event))
            elif stage == "choose" and choice == "pressure":
                case = case.model_copy(update=dict(pressure=event))
            elif stage == "pressure" and choice == "helpless":
                state = make_helpless(state, girl.ref, case.acolyte, event)
                case = case.model_copy(update=dict(outcome="helpless", resolved=event))
            elif stage == "pressure" and choice == "damage":
                assert case.asset is not None
                state, required = damage(
                    state,
                    girl.ref,
                    case.asset,
                    profiles(c, self.store.campaign_id),
                    event,
                    opponent=case.acolyte,
                )
                if required:
                    raise WorkflowError(
                        "Resolve the actual required damage consequence with the GM"
                    )
                case = case.model_copy(update=dict(outcome="damage", resolved=event))
            else:
                raise WorkflowError("Choose one currently supported printed Abysstech effect")
            return self._save(c, state, viewer, key, case, stage, event)

        return self._write(
            viewer, key, dict(id=identity, revision=revision, step=step, choice=choice), operation
        )
