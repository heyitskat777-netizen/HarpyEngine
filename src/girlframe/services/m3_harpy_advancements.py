"""Own the printed Harpy advancement in the private campaign controls."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_advancements as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_janus_state import JanusCore
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def capacity(c: Connection, campaign: str, state: GameState, birth: str) -> tuple[int, str]:
    """Past natural Void High and actual Endgames keep their slots after severity changes."""
    if rules.strain_capacity(state.strain) == 1 and state.strain is None:
        return 1, birth
    history = t.m2["m2_state_history"]
    query = (
        sa.select(history.c.event_id, history.c.body_json)
        .where(
            history.c.campaign_id == campaign,
            sa.func.json_type(history.c.body_json, "$.strain") == "object",
            sa.or_(
                sa.func.json_extract(history.c.body_json, "$.strain.levels.void") == "high",
                sa.func.json_array_length(history.c.body_json, "$.strain.endgames") > 0,
                sa.func.json_array_length(history.c.body_json, "$.strain.requests") > 0,
                sa.func.json_array_length(history.c.body_json, "$.strain.events") > 0,
            ),
        )
        .order_by(history.c.revision)
    )
    best = (1, birth)
    for event, raw in c.execute(query):
        actual = rules.strain_capacity(GameState.model_validate_json(raw).strain)
        if actual > best[0]:
            best = actual, event
        if actual == 3:
            break
    return best


def advancement_source(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, owner: int, rule: str
) -> str | None:
    record = next((x for x in rules.advances(state, actor) if x.rule == rule), None)
    if record is None or record.controller != owner:
        return None
    try:
        Access(game.store).require_specialist_rule(rule)
    except (ValueError, WorkflowError):
        return None
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == record.event,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.harpy_advancement_selected",
            t.events.c.actor_id == str(owner),
        )
    )
    if raw is None or record not in rules.advances(GameState.model_validate_json(raw), actor):
        raise WorkflowError("Recover the actual original Harpy advancement receipt")
    return record.event


def scene_harpy(
    game: GameService,
    c: Connection,
    state: GameState,
    controller: int,
    cast: SceneCast,
    actor: ActorRef,
    advancement: str,
) -> tuple[ActorView, str]:
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        actor.kind != "external_pilot"
        or actual.girl != "harpy"
        or not actual.alive
        or actual.controller != controller
        or actual.cell is None
        or actual.offstage_source is not None
        or not any(role.actor == actor and role.controller == controller for role in cast.roles)
        or is_helpless(state, actor)
    ):
        raise WorkflowError("Use your actual living Harpy in the original scene")
    receipt = advancement_source(game, c, state, actor, controller, advancement)
    if receipt is None or harpy(state, actor).body_incapacitated:
        raise WorkflowError("Use an active Harpy with its own required advancement")
    return actual, receipt


def choose_sparrows(action: dict[str, Any], value: str | None) -> None:
    if value is None:
        return
    source = action["data"].get("harpy_sparrows")
    if source is None or value not in dict(rules.SPARROWS_CHOICES):
        raise WorkflowError("Use the actual Harpy's original Sparrows advancement")
    action["data"]["result"]["sparrows"] = dict(choice=value, source=source)


class HarpyAdvancementService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game, self.access = store, GameService(store), Access(store)

    def _actors(self, state: GameState, viewer: GuildViewer) -> tuple[ActorRef, ...]:
        bodies = (
            *(x.id for x in state.harpy_states if x.alive and x.controller == viewer.user_id),
            *(x.id for x in state.native_harpies if x.controller == viewer.user_id),
        )
        actors = []
        for identity in bodies:
            actor = ActorRef(kind="external_pilot", entity=identity)
            try:
                self._owned(state, viewer, actor)
            except (ValueError, WorkflowError):
                continue
            actors.append(actor)
        return tuple(dict.fromkeys(actors))

    def _owned(self, state: GameState, viewer: GuildViewer, actor: ActorRef) -> str:
        original = harpy(state, actor)
        if isinstance(original, JanusCore) or original.controller != viewer.user_id:
            raise WorkflowError("Only the actual Harpy controller selects its own advancement")
        native = (
            next((x for x in state.world.pilots if x.id == actor.entity), None)
            if state.world
            else None
        )
        if not getattr(original, "alive", True) or native is not None and not native.alive:
            raise WorkflowError("Use the actual living original Harpy")
        return original.source_event

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[ActorRef, bool], ...]:
        actors = self._actors(state, viewer)
        if not actors:
            return ()
        try:
            self.access.authorize(c, viewer, "plays")
        except (WorkflowError, ValueError):
            return ()
        choices = {rule for rule, _label in self.options()}
        if not choices:
            return ()
        result = []
        for actor in actors:
            learned = {x.rule for x in rules.advances(state, actor)}
            available = False
            if choices - learned:
                slots, _source = capacity(
                    c, self.store.campaign_id, state, self._owned(state, viewer, actor)
                )
                available = len(learned) < slots
            result.append((actor, available))
        return tuple(result)

    def options(self) -> tuple[tuple[str, str], ...]:
        available = []
        for rule, label in rules.ADVANCEMENTS:
            try:
                self.access.require_specialist_rule(rule)
            except (ValueError, WorkflowError):
                continue
            available.append((rule, label))
        return tuple(available)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        actor = ActorRef(kind="external_pilot", entity=identity)
        with self.store.engine.connect() as c:
            self.access.authorize(c, viewer, "plays")
            available = self.options()
            if not available:
                raise WorkflowError("Harpy advancement implementation and review are incomplete")
            state = load_state(c, self.store.campaign_id)
            birth = self._owned(state, viewer, actor)
            slots, _source = capacity(c, self.store.campaign_id, state, birth)
            learned = tuple(x.rule for x in rules.advances(state, actor))
            choices = tuple(x for x in available if x[0] not in learned and len(learned) < slots)
            return dict(
                revision=state.revision,
                slots=slots,
                learned=learned,
                available=bool(choices),
                choices=choices,
            )

    def select(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, rule: str
    ) -> dict[str, Any]:
        actor = ActorRef(kind="external_pilot", entity=identity)

        def authorize(c: Connection) -> None:
            self.access.authorize(c, viewer, "plays")
            if rule not in dict(rules.ADVANCEMENTS):
                raise WorkflowError("Choose a supported original Harpy advancement")
            self.access.require_specialist_rule(rule)
            self.game.unpaused(c)
            self._owned(load_state(c, self.store.campaign_id), viewer, actor)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if revision != state.revision:
                raise WorkflowError(
                    "Reopen the actual advancement and choose a supported original rule"
                )
            birth = self._owned(state, viewer, actor)
            slots, basis = capacity(c, self.store.campaign_id, state, birth)
            receipt = rules.Advancement(
                actor=actor,
                controller=viewer.user_id,
                rule=rule,
                event=str(uuid4()),
                capacity_source=basis,
            )
            rules.add(state, receipt, slots)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_advancement_selected",
                state,
                event_id=receipt.event,
                actor_ref=actor.model_dump(mode="json"),
                advancement=rule,
                capacity_source=basis,
            )
            return dict(rule=rule, receipt=receipt.event, slots=slots)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_advancement_selected",
                dict(identity=identity, revision=revision, rule=rule),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
