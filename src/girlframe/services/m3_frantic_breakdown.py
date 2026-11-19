"""Saved Frantic rolls and their original private choice and effect owners."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_frantic_breakdown as rules
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str, kind: str) -> GameState | None:
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == event,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == kind,
        )
    )
    return GameState.model_validate_json(raw) if raw else None


def _case(state: GameState, identity: str) -> rules.Breakdown | None:
    return next((x for x in rules.records(state) if x.id == identity), None)


def _source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Breakdown:
    value = _case(state, identity)
    birth = _history(game, c, value.source_event, "m3.frantic_breakdown_rolled") if value else None
    original = _case(birth, identity) if birth else None
    if (
        value is None
        or original is None
        or original.choices
        or original.model_dump(exclude={"choices"}) != value.model_dump(exclude={"choices"})
    ):
        raise WorkflowError("Recover the actual original Frantic breakdown and saved roll")
    return value


def discipline_source(
    game: GameService, c: Connection, state: GameState, debt: Obligation, handler: int
) -> str:
    value = _source(game, c, state, debt.action)
    match = next((x for x in value.choices if debt.id in x.debts), None)
    if (
        match is None
        or value.handler != active_handler(state)
        or debt.target != handler
        or current_ref(state, debt.owner).incarnation != debt.details.get("character_id")
    ):
        raise WorkflowError("Recover this actual Frantic breakdown's original discipline owners")
    saved = _history(game, c, match.event, "m3.frantic_breakdown_selected")
    actual = _case(saved, value.id) if saved else None
    if actual is None or match not in actual.choices:
        raise WorkflowError("Recover the original Frantic decision that assigned this Punishment")
    if match.option == "minor_all" and current_ref(state, debt.owner) in value.cadre:
        return "minor"
    if match.option == "moderate_one" and current_ref(state, debt.owner) == match.target:
        return "moderate"
    raise WorkflowError("Keep the original affected Girl and the printed Punishment severity")


class FranticBreakdownService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, authorize=access, auto_audit=False
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _state(self, c: Connection, expected: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        if state.revision != expected:
            raise WorkflowError("STALE_STATE: reopen this Frantic breakdown")
        return state

    def plan_roll(
        self, c: Connection, state: GameState, viewer: GuildViewer, channel: int, account: str
    ) -> rules.Breakdown:
        owned = active_book(self.game, c, state, book="Frantic", rule=rules.RULE)
        if (
            owned is None
            or owned[0].entity != str(viewer.user_id)
            or state.world is None
            or not account.strip()
        ):
            raise WorkflowError(
                "Only the original Frantic may declare a breakdown in the actual world"
            )
        if any(
            x.handler == owned[0] and rules.phase(state, x) != "complete"
            for x in rules.records(state)
        ):
            raise WorkflowError("Continue the actual existing Frantic breakdown first")
        scene = self.game.scene(c, channel)
        if viewer.user_id not in scene["participants"]:
            raise WorkflowError("Join the actual breakdown scene")
        lock = self.game.lock(c, channel)
        if lock is not None and lock["state"] != "released":
            raise WorkflowError("Finish the actual pending Play in this scene first")
        self.game.pilot_cast(c, state, scene, owners=(viewer.user_id,))
        groups = status_groups(state)
        if len(groups) < 2 or len(groups[0]) != 1 or len(groups[-1]) != 1:
            raise WorkflowError("Recover the single original Ace and Dog before this roll")
        if not {groups[0][0], groups[-1][0]} <= set(scene["participants"]):
            raise WorkflowError("The original Ace and Dog must join the breakdown scene")
        cadre = tuple(current_ref(state, x) for x in state.order)
        event, identity = str(uuid4()), str(uuid4())
        return rules.Breakdown(
            id=identity,
            source_event=event,
            handler=owned[0],
            scene=scene["id"],
            channel=channel,
            faces=self.game.dice.roll(),
            bases=tuple(
                x.id
                for x in state.world.locations
                if x.kind == "base"
                and x.foundation_operational
                and in_responsibility(state, x.cell)
            ),
            cadre=cadre,
            in_scene=tuple(x for x in cadre if int(x.entity) in scene["participants"]),
            ace=current_ref(state, groups[0][0]),
            dog=current_ref(state, groups[-1][0]),
            account=account.strip(),
        )

    def start(
        self, viewer: GuildViewer, key: str, expected: int, channel: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            value = self.plan_roll(c, state, viewer, channel, account)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_breakdown_rolled",
                state,
                event_id=value.source_event,
                breakdown=value.id,
            )
            return dict(id=value.id, game_revision=state.revision, total=value.total)

        return self._write(
            viewer,
            key,
            "m3.frantic_breakdown_rolled",
            dict(
                expected=expected,
                channel=channel,
                account=account,
            ),
            operation,
        )

    def _choice_scene(
        self, c: Connection, state: GameState, value: rules.Breakdown, *originals: ActorRef
    ) -> None:
        owned = active_book(self.game, c, state, book="Frantic", rule=rules.RULE)
        if owned is None or owned[0] != value.handler:
            raise WorkflowError("The original active Frantic has changed")
        scene = self.game.scene(c, value.channel)
        owners = tuple(dict.fromkeys(int(x.entity) for x in (value.handler, *originals)))
        if (
            scene["id"] != value.scene
            or not set(owners) <= set(scene["participants"])
            or any(
                (
                    active_handler(state)
                    if x.kind == "handler"
                    else current_ref(state, int(x.entity))
                )
                != x
                for x in originals
            )
        ):
            raise WorkflowError("Recover the actual original breakdown scene and its participants")
        self.game.pilot_cast(c, state, scene, owners=owners)

    def select(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        options: tuple[rules.Option, ...],
        *,
        office: ActorRef | None = None,
        moderate: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            value = _source(self.game, c, state, identity)
            chosen = value.next_choice()
            if chosen is None or chosen[0].entity != str(viewer.user_id):
                raise WorkflowError(
                    "Only the saved original owner chooses this breakdown's effects"
                )
            if (
                len(set(options)) != chosen[1]
                or len(options) != chosen[1]
                or not set(options) <= set(rules.OPTIONS) - {x.option for x in value.choices}
                or (office is not None) != ("office" in options)
                or (moderate is not None) != ("moderate_one" in options)
                or (office is not None and office not in value.in_scene)
                or (moderate is not None and moderate not in value.in_scene)
            ):
                raise WorkflowError("Choose the exact printed count and original scene targets")
            self._choice_scene(c, state, value, chosen[0], *(x for x in (office, moderate) if x))
            event = str(uuid4())
            new = []
            for option in options:
                targets = (
                    value.cadre
                    if option == "minor_all"
                    else (moderate,)
                    if moderate and option == "moderate_one"
                    else ()
                )
                debts = []
                for target in targets:
                    owner = int(target.entity)
                    if target.incarnation is None or target != current_ref(state, owner):
                        raise WorkflowError("No replacement may inherit the breakdown's discipline")
                    debts.append(
                        self.game.obligation(
                            state,
                            {"id": identity},
                            "punishment",
                            owner,
                            int(value.handler.entity),
                            cause=rules.RULE,
                            source_pdf="132",
                            character_id=target.incarnation,
                        )
                    )
                new.append(
                    rules.Selection(
                        option=option,
                        chooser=chosen[0],
                        event=event,
                        debts=tuple(debts),
                        target=office
                        if option == "office"
                        else moderate
                        if option == "moderate_one"
                        else None,
                    )
                )
            updated = value.model_copy(update=dict(choices=(*value.choices, *new)))
            rules.put(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_breakdown_selected",
                state,
                event_id=event,
                breakdown=identity,
            )
            return dict(
                id=identity, state=rules.phase(state, updated), game_revision=state.revision
            )

        return self._write(
            viewer,
            key,
            "m3.frantic_breakdown_selected",
            dict(
                id=identity,
                expected=expected,
                options=options,
                office=office.model_dump(mode="json") if office else None,
                moderate=moderate.model_dump(mode="json") if moderate else None,
            ),
            operation,
        )

    def discover(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            value = _source(self.game, c, state, identity)
            selected = next((x for x in value.choices if x.option == "office"), None)
            if (
                selected is None
                or selected.target is None
                or selected.discovered_event is not None
                or selected.target.entity != str(viewer.user_id)
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError(
                    "Only the original Girl may confirm her actual office discovery"
                )
            self._choice_scene(c, state, value, selected.target)
            event = str(uuid4())
            result = selected.model_copy(update=dict(discovered_event=event))
            updated = value.model_copy(
                update=dict(
                    choices=tuple(result if x == selected else x for x in value.choices),
                )
            )
            rules.put(state, updated)
            state.facts.append(
                dict(
                    kind="frantic_office_discovery",
                    id=identity,
                    event=event,
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_office_discovered",
                state,
                event_id=event,
                breakdown=identity,
            )
            return dict(
                id=identity, state=rules.phase(state, updated), game_revision=state.revision
            )

        return self._write(
            viewer,
            key,
            "m3.frantic_office_discovered",
            dict(
                id=identity,
                expected=expected,
                account=account,
            ),
            operation,
        )

    def _roles(
        self, c: Connection, state: GameState, value: rules.Breakdown, viewer: GuildViewer
    ) -> set[str]:
        if viewer.user_id not in state.order and viewer.user_id != state.handler:
            return set()
        ref = (
            active_handler(state)
            if viewer.user_id == state.handler and viewer.user_id not in state.order
            else current_ref(state, viewer.user_id)
        )
        if ref is None:
            return set()
        result = (
            {"handler"}
            if value.handler == active_handler(state)
            and viewer.user_id == int(value.handler.entity)
            else set()
        )
        if not result:
            if ref not in value.in_scene:
                return result
            try:
                self._choice_scene(c, state, value, ref)
            except (ValueError, WorkflowError):
                return result
        choice = value.next_choice()
        if choice and choice[0] == ref:
            result.add("choose")
        if any(
            x.target == ref and x.option == "office" and not x.discovered_event
            for x in value.choices
        ):
            result.add("discover")
        return result

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=rules.phase(state, x), can_act=bool(roles - {"handler"}))
            for x in rules.records(state)
            if rules.phase(state, x) != "complete" and (roles := self._roles(c, state, x, viewer))
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _source(self.game, c, state, identity)
            roles = self._roles(c, state, value, viewer)
            if not roles:
                raise WorkflowError("This choice belongs to an actual original participant")
            next_choice = value.next_choice()
            return dict(
                id=identity,
                revision=state.revision,
                phase=rules.phase(state, value),
                faces=value.faces,
                bases=len(value.bases),
                total=value.total,
                account=value.account,
                choose=next_choice[1] if next_choice and "choose" in roles else 0,
                discover="discover" in roles,
                options=tuple(
                    (k, v)
                    for k, v in rules.OPTIONS.items()
                    if k not in {x.option for x in value.choices}
                ),
                targets=tuple(
                    dict(
                        ref=x.model_dump(mode="json"),
                        token=x.token,
                        name=state.sheets[x.entity].callsign,
                    )
                    for x in value.in_scene
                    if x.entity in state.sheets and current_ref(state, int(x.entity)) == x
                )
                if "choose" in roles
                else (),
            )
