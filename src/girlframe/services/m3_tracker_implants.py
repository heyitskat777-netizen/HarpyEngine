"""Actual secret implants, location knowledge and source-bound Handler observations."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_tracker_implants as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import physical_cell, resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_handler_play_state import Effect, HandlerPlay
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services import m3_advancement_acquisition as acquisition_source
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return acquisition_source.prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the immutable original Tracker Implants acquisition",
        failure="Recover the actual original held advancement and exact tracker spend",
    )


def current(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = paid(game, c, state, identity)
    if (
        not same_handler_body(state, value.handler)
        or HandlerCreationService(game.store)._appointment_source(c, int(value.handler.entity))
        != value.appointment
    ):
        raise WorkflowError("This knowledge and hardware source belong to their original Handler")
    return value


def prove_installation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> tuple[rules.Acquisition, rules.Implant]:
    value, item = rules.implant(state, identity)
    paid(game, c, state, value.id)
    born = _history(c, game, value.event)
    body = next((x for x in born.placements if x.actor == item.actor), None)
    if body is None or body.vessel_id != item.vessel or item.actor.entity not in born.sheets:
        raise WorkflowError("Recover the exact original body's installed hardware/site")
    return value, item


def location(
    game: GameService, c: Connection, state: GameState, item: rules.Implant
) -> tuple[int, int] | None:
    pose = next(
        (x for x in state.placements if x.actor == item.actor and x.vessel_id == item.vessel), None
    )
    if pose is None:
        raise WorkflowError(
            "SOURCE_TRACKER_BODY_REQUIRED: recover the actual implanted "
            "vessel; do not follow a replacement mind"
        )
    return physical_cell(
        state, item.actor, profiles(c, game.store.campaign_id), require_alive=False
    )


def prepare(
    game: GameService, c: Connection, before: GameState, after: GameState, event: str
) -> None:
    """Nonrecursive canonical observer: only real same-body, mapped Girl Void changes."""
    for source in rules.acquisitions(before):
        paid(game, c, before, source.id)
        if source not in rules.acquisitions(after):
            raise WorkflowError("Preserve the actual original tracker installation history")
        for item in source.implants:
            if not rules.attached(before, item.id) or not rules.attached(after, item.id):
                continue
            if item.asset is not None and item.asset in rules.body_void_changes(
                before, after, item.actor, item.vessel
            ):
                rules.add_alert(
                    after,
                    source,
                    item,
                    reason="site_void",
                    event=event,
                    source_event=event,
                    asset=item.asset,
                )


def _born(
    game: GameService, c: Connection, value: rules.Moment | rules.SiteVoid | rules.Removal
) -> GameState:
    original = _history(c, game, value.event)
    if value not in rules.records(original, type(value)):
        raise WorkflowError("Recover the immutable original body/source fact")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    expected = {
        rules.Moment: "m3.tracker_moment",
        rules.SiteVoid: "m3.tracker_site_void",
        rules.Removal: "m3.tracker_removed",
    }[type(value)]
    if audit != (expected, str(value.controller)):
        raise WorkflowError("Recover the actual original human's body/source fact")
    return original


def prove_moment(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Moment:
    value = next((x for x in rules.records(state, rules.Moment) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Use an actual human-authored private fictional moment")
    original = _born(game, c, value)
    actual_cast = next((x for x in original.scene_casts if x.id == value.cast.id), None)
    if (
        value.actor.kind != "pilot"
        or int(value.actor.entity) != value.controller
        or actual_cast != value.cast
        or not value.cast.open
        or not any(
            x.actor == value.actor and x.controller == value.controller for x in value.cast.roles
        )
        or not any(
            x.actor == value.actor and x.vessel_id == value.vessel for x in original.placements
        )
    ):
        raise WorkflowError("Recover the actual original moment's body, human and scene cast")
    return value


def prove_initial_presence(
    game: GameService, c: Connection, state: GameState, handler: ActorRef
) -> None:
    positions = [
        x
        for x in state.facts
        if x.get("kind") == "tracker_initial_handler_position"
        and x.get("actor") == handler.model_dump_json()
    ]
    for fact in positions:
        born = _history(c, game, fact["event"])
        source, item = prove_installation(game, c, born, fact["tracker"])
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == fact["event"]
            )
        ).first()
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.revision == born.revision - 1,
            )
        )
        if (
            fact not in born.facts
            or source.id != fact["acquisition"]
            or source.handler != handler
            or audit != ("m3.tracker_initial_position", handler.entity)
            or raw is None
            or physical_cell(
                GameState.model_validate_json(raw), handler, profiles(c, game.store.campaign_id)
            )
            is not None
            or json.loads(fact["cell"]) != list(location(game, c, born, item) or ())
        ):
            raise WorkflowError("Recover the original Handler's truthful initial physical presence")


def prove_tracker_play(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay
) -> rules.PlaySource:
    value = next((x for x in rules.records(state, rules.PlaySource) if x.id == grant.id), None)
    if value is None:
        raise WorkflowError("Recover this actual source-owned tracker Play")
    source, item = prove_installation(game, c, state, value.tracker)
    born = _history(c, game, value.event)
    first = next((x for x in born.handler_plays if x.id == grant.id), None)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        value not in rules.records(born, rules.PlaySource)
        or first is None
        or value.event != grant.source_event
        or source.id != value.acquisition
        or grant.source != "ordinary"
        or grant.clause != "tracker:" + item.id
        or grant.chooser_actor != source.handler
        or grant.chooser_controller != int(source.handler.entity)
        or grant.appointment != source.appointment
        or grant.targets != (item.actor,)
        or grant.target_controllers != {item.actor.token: int(item.actor.entity)}
        or any(
            getattr(first, key) != getattr(grant, key)
            for key in (
                "id",
                "source",
                "source_event",
                "source_action",
                "source_choice",
                "clause",
                "chooser_actor",
                "chooser_controller",
                "appointment",
                "adjudicator_ref",
                "adjudicator_source",
                "targets",
                "target_controllers",
                "scope",
                "final_original",
                "nonbody_only",
            )
        )
        or value.cast not in born.scene_casts
        or audit != ("m3.handler_play_started", source.handler.entity)
        or not any(
            x.actor == item.actor and x.controller == int(item.actor.entity)
            for x in value.cast.roles
        )
        or location(game, c, born, item) != value.cell
        or physical_cell(born, source.handler, profiles(c, game.store.campaign_id)) != value.cell
    ):
        raise WorkflowError(
            "Recover the exact tracker source, original Handler and original target"
        )
    if value.moment is not None:
        moment = prove_moment(game, c, state, value.moment)
        if moment.actor != item.actor or moment.vessel != item.vessel or moment.cell != value.cell:
            raise WorkflowError("The observed actual moment belongs to another body or place")
    prove_initial_presence(game, c, state, source.handler)
    if grant.state == "pending":
        current(game, c, state, source.id)
        if not rules.attached(state, item.id):
            raise WorkflowError("The actual tracker was removed; it grants no new Play")
    return value


def apply_play(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay, effect: Effect
) -> GameState:
    value = prove_tracker_play(game, c, state, grant)
    _, item = rules.implant(state, value.tracker)
    cast = _cast(game, c, state, value.cast.channel)
    if (
        effect.kind != value.play
        or effect.target != item.actor
        or cast != value.cast
        or location(game, c, state, item) != value.cell
        or physical_cell(
            state,
            rules.implant(state, value.tracker)[0].handler,
            profiles(c, game.store.campaign_id),
        )
        != value.cell
    ):
        raise WorkflowError(
            "SOURCE_TRACKER_CONTACT_REQUIRED: actual unchanged scene "
            "contact/co-presence or completed travel is required"
        )
    if value.play == "tracker_voyeur":
        if value.moment is None:
            raise WorkflowError("Use the actual source-authored private fictional moment")
        moment = prove_moment(game, c, state, value.moment)
        if effect.detail != moment.account:
            raise WorkflowError(
                "Observe the actual supplied fictional moment, not private notes "
                "or invented information"
            )
    return state


def prove_recovered(game: GameService, c: Connection, state: GameState, item: HeldItem) -> None:
    source, tracker = prove_installation(game, c, state, item.id)
    removal = next((x for x in rules.records(state, rules.Removal) if x.tracker == item.id), None)
    if removal is None:
        raise WorkflowError("The same actual tracker has not been physically removed")
    born = _born(game, c, removal)
    original = next((x for x in born.held_items if x.id == item.id), None)
    if (
        original is None
        or item.source_event != removal.event
        or item.origin_event != source.event
        or item.source_owner != source.handler
        or original.holder != removal.remover
        or original.name != "Recovered tracker"
        or original.asset_id is not None
        or not any(
            x.actor == tracker.actor and x.vessel_id == tracker.vessel for x in born.placements
        )
    ):
        raise WorkflowError("Recover the genuine original implanted object and physical removal")


def _transition(
    game: GameService, c: Connection, event: str, actor: ActorRef, asset: str
) -> tuple[GameState, GameState, str]:
    after = _history(c, game, event)
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.revision == after.revision - 1,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual immediately preceding Void source snapshot")
    before = GameState.model_validate_json(raw)
    pose = next((x for x in before.placements if x.actor == actor), None)
    if pose is None or asset not in rules.body_void_changes(before, after, actor, pose.vessel_id):
        raise WorkflowError(
            "SOURCE_TRACKER_VOID_REQUIRED: choose an actual same-vessel Girl-body Void transition"
        )
    # Finite unmapped-site source: a genuine original player's committed Dive effect.
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if audit is None or audit.kind != "m3.choice_resolved":
        raise WorkflowError("SOURCE_TRACKER_VOID_REQUIRED: recover the performed body-Void source")
    payload = json.loads(audit.payload_json)
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    response = c.execute(
        sa.select(choices.c.kind, choices.c.action_id, responses.c.answer_json)
        .join(
            responses,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == payload.get("choice_id"),
            responses.c.event_id == event,
            responses.c.actor_id == actor.entity,
        )
    ).first()
    if (
        response is None
        or response.kind != "dive_effect"
        or response.action_id != payload.get("action_id")
    ):
        raise WorkflowError(
            "SOURCE_TRACKER_VOID_REQUIRED: this anatomical source adapter requires genuine Dive"
        )
    action = game.action(c, response.action_id)
    fact = next(
        (
            x
            for x in after.facts
            if x.get("kind") == "dive_effect"
            and x.get("action") == action["id"]
            and x.get("source_event") == event
            and x.get("option") == "void_and_unmark_all"
        ),
        None,
    )
    if (
        action["data"].get("dive", {}).get("actor") != actor.model_dump(mode="json")
        or audit.actor_id != actor.entity
        or fact is None
        or json.loads(response.answer_json).get("fields", {}).get("asset") != asset
    ):
        raise WorkflowError(
            "SOURCE_TRACKER_VOID_REQUIRED: prove the same original human, "
            "real action, selected Asset and Void event"
        )
    return before, after, pose.vessel_id


def prove_alert(game: GameService, c: Connection, state: GameState, alert: rules.Alert) -> None:
    source, item = prove_installation(game, c, state, alert.tracker)
    born = _history(c, game, alert.event)
    if source.id != alert.acquisition or alert not in rules.records(born, rules.Alert):
        raise WorkflowError("Recover the actual original tracker alert")
    if alert.reason == "removed":
        value = next(
            (
                x
                for x in rules.records(state, rules.Removal)
                if x.event == alert.source_event and x.tracker == item.id
            ),
            None,
        )
        if value is None:
            raise WorkflowError("Recover the actual physical tracker removal")
        _born(game, c, value)
    elif alert.attribution is not None:
        value_void = next(
            (x for x in rules.records(state, rules.SiteVoid) if x.id == alert.attribution), None
        )
        if value_void is None:
            raise WorkflowError(
                "Recover the original affected human's anatomical source attribution"
            )
        _born(game, c, value_void)
        _, _, vessel = _transition(
            game, c, value_void.source_event, value_void.actor, value_void.asset
        )
        if (
            value_void.actor != item.actor
            or vessel != item.vessel
            or value_void.site.casefold() != item.site.casefold()
            or value_void.controller != int(item.actor.entity)
            or alert.source_event != value_void.source_event
            or alert.asset != value_void.asset
        ):
            raise WorkflowError("Recover the exact same original body, site and real Void event")
    else:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.revision == born.revision - 1,
            )
        )
        if (
            raw is None
            or alert.event != alert.source_event
            or alert.asset != item.asset
            or item.asset
            not in rules.body_void_changes(
                GameState.model_validate_json(raw), born, item.actor, item.vessel
            )
        ):
            raise WorkflowError("Recover the actual mapped body-part Void transition")


class TrackerService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "playbooks")
        assert self.store.policy.m3_approval is not None
        gate = Access(self.store)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)
        self.game.authorize(c, viewer, game=False)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        revision: int,
        sites: tuple[rules.Site, ...],
        account: str,
        *,
        actual: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, handler, appointment, award = acquisition_source.held(
                self.game,
                c,
                viewer,
                award_id,
                revision,
                account,
                failure="Spend one held advancement to actually implant each current original Girl",
            )
            roster = tuple(current_ref(state, x) for x in state.order)
            if (
                not actual
                or len(account) > 1200
                or len(sites) != len(roster)
                or {x.actor for x in sites} != set(roster)
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Spend one held advancement to actually implant each current original Girl"
                )
            event, identity = str(uuid4()), "tracker-acquisition:" + award_id
            installed = []
            for site in sites:
                actor = resolve(
                    state,
                    site.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                body = next((x for x in state.placements if x.actor == site.actor), None)
                if body is None or actor.cell is None:
                    raise WorkflowError(
                        "SOURCE_TRACKER_BODY_REQUIRED: establish the actual original body "
                        "and location"
                    )
                if site.asset is not None and not any(
                    x.id == site.asset and x.family == "girl" and x.battery_asset is None
                    for x in state.sheets[site.actor.entity].assets
                ):
                    raise WorkflowError(
                        "Map this anatomical site only to an actual physical Girl Asset"
                    )
                installed.append(
                    rules.Implant(
                        **site.model_dump(),
                        id="tracker-implant:" + event + ":" + site.actor.token,
                        vessel=body.vessel_id,
                    )
                )
            source = rules.Acquisition(
                id=identity,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
                implants=tuple(installed),
            )
            rules.put(state, source)
            acquisition_source.record_spend(state, award, source, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=identity, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_acquired",
            dict(
                award=award_id,
                revision=revision,
                sites=[x.model_dump(mode="json") for x in sites],
                account=account,
                actual=actual,
            ),
            operation,
        )

    def record_initial_presence(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        tracker: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = current(self.game, c, state, acquisition)
            _, item = prove_installation(self.game, c, state, tracker)
            body = resolve(
                state,
                source.handler,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            cell = location(self.game, c, state, item)
            if (
                state.revision != revision
                or viewer.user_id != int(source.handler.entity)
                or item not in source.implants
                or body.cell is not None
                or body.custody not in (None, "free")
                or cell is None
                or not account.strip()
                or len(account) > 1200
                or not rules.attached(state, item.id)
            ):
                raise WorkflowError(
                    "Record only your original body's previously unknown actual initial presence"
                )
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="tracker_initial_handler_position",
                    actor=source.handler.model_dump_json(),
                    cell=json.dumps(cell),
                    event=event,
                    acquisition=source.id,
                    tracker=item.id,
                    account=account.strip(),
                )
            )
            self.game.event(
                c, viewer.user_id, key, "m3.tracker_initial_position", state, event_id=event
            )
            return dict(id=source.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_initial_position",
            dict(acquisition=acquisition, revision=revision, tracker=tracker, account=account),
            operation,
        )

    def record_moment(
        self, viewer: GuildViewer, key: str, revision: int, channel: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            pose = next((x for x in state.placements if x.actor == actor), None)
            if (
                state.revision != revision
                or pose is None
                or actual.cell is None
                or not account.strip()
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
            ):
                raise WorkflowError(
                    "Supply your actual original body's fictional moment in its real scene"
                )
            event = str(uuid4())
            value = rules.Moment(
                id="tracker-moment:" + event,
                actor=actor,
                vessel=pose.vessel_id,
                event=event,
                controller=viewer.user_id,
                cast=cast,
                account=account.strip(),
                cell=actual.cell,
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.tracker_moment", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_moment",
            dict(revision=revision, channel=channel, account=account),
            operation,
        )

    def start_play(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        tracker: str,
        play: Literal["tracker_intercept", "tracker_voyeur"],
        channel: int,
        *,
        moment: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_handler_plays import _ordinary_scene_idle

            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            source, item = prove_installation(self.game, c, state, tracker)
            current(self.game, c, state, source.id)
            cast = _cast(self.game, c, state, channel)
            cell = location(self.game, c, state, item)
            if (
                state.revision != revision
                or viewer.user_id != int(source.handler.entity)
                or not rules.attached(state, tracker)
                or cell is None
                or not any(
                    x.actor == item.actor and x.controller == int(item.actor.entity)
                    for x in cast.roles
                )
                or physical_cell(state, source.handler, profiles(c, self.store.campaign_id)) != cell
            ):
                raise WorkflowError(
                    "SOURCE_TRACKER_CONTACT_REQUIRED: establish actual Handler "
                    "co-presence and original target scene"
                )
            if play == "tracker_voyeur":
                observed = prove_moment(self.game, c, state, moment or "")
                if (
                    observed.actor != item.actor
                    or observed.vessel != item.vessel
                    or observed.cast != cast
                    or observed.cell != cell
                ):
                    raise WorkflowError(
                        "Use the same original body's actual current private fictional moment"
                    )
            elif play != "tracker_intercept" or moment is not None:
                raise WorkflowError("Choose one actually granted tracker Play")
            event, identity = str(uuid4()), str(uuid4())
            state.handler_plays.append(
                HandlerPlay(
                    id=identity,
                    source="ordinary",
                    source_event=event,
                    clause="tracker:" + tracker,
                    chooser_actor=source.handler,
                    chooser_controller=viewer.user_id,
                    appointment=source.appointment,
                    targets=(item.actor,),
                    target_controllers={item.actor.token: int(item.actor.entity)},
                    scope=WorkScope(campaign_context=True),
                )
            )
            rules.put(
                state,
                rules.PlaySource(
                    id=identity,
                    tracker=tracker,
                    acquisition=source.id,
                    event=event,
                    play=play,
                    cast=cast,
                    cell=cell,
                    moment=moment,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_play_started",
                state,
                event_id=event,
                grant_id=identity,
            )
            return dict(id=identity, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_play_started",
            dict(revision=revision, tracker=tracker, play=play, channel=channel, moment=moment),
            operation,
        )

    def remove(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        tracker: str,
        remover: ActorRef,
        account: str,
        *,
        actual: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source, item = prove_installation(self.game, c, state, tracker)
            actual_remover = resolve(
                state, remover, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            cell = location(self.game, c, state, item)
            if (
                state.revision != revision
                or not actual
                or not account.strip()
                or len(account) > 1200
                or actual_remover.controller != viewer.user_id
                or not rules.attached(state, tracker)
                or cell is None
                or actual_remover.cell != cell
                or (remover != item.actor and remover != source.handler)
            ):
                raise WorkflowError(
                    "Record actual physical removal by this original person in real reach"
                )
            event = str(uuid4())
            removed = rules.Removal(
                id="tracker-removal:" + tracker,
                tracker=tracker,
                event=event,
                remover=remover,
                controller=viewer.user_id,
                account=account.strip(),
            )
            rules.put(state, removed)
            state.held_items.append(
                HeldItem(
                    id=item.id,
                    holder=remover,
                    name="Recovered tracker",
                    description=account.strip(),
                    source_event=event,
                    source_owner=source.handler,
                    origin_event=source.event,
                    state_event=event,
                    confirmed_by=remover,
                    confirmed_controller=viewer.user_id,
                    confirmed_event=event,
                )
            )
            rules.add_alert(state, source, item, reason="removed", event=event, source_event=event)
            self.game.event(c, viewer.user_id, key, "m3.tracker_removed", state, event_id=event)
            return dict(id=removed.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_removed",
            dict(
                revision=revision,
                tracker=tracker,
                remover=remover.model_dump(mode="json"),
                account=account,
                actual=actual,
            ),
            operation,
        )

    def record_site_void(
        self, viewer: GuildViewer, key: str, revision: int, source_event: str, asset: str, site: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            _, birth, vessel = _transition(self.game, c, source_event, actor, asset)
            if state.revision != revision or not site.strip() or len(site) > 120:
                raise WorkflowError(
                    "Attribute the actual source transition to its actual anatomical site"
                )
            if any(
                x.actor == actor
                and x.source_event == source_event
                and x.asset == asset
                and x.site == site.strip()
                for x in rules.records(state, rules.SiteVoid)
            ):
                raise WorkflowError("This actual source/body/site was already recorded")
            event = str(uuid4())
            value = rules.SiteVoid(
                id="tracker-site-void:" + event,
                actor=actor,
                vessel=vessel,
                source_event=source_event,
                asset=asset,
                site=site.strip(),
                controller=viewer.user_id,
                event=event,
            )
            rules.put(state, value)
            for source in rules.acquisitions(birth):
                paid(self.game, c, state, source.id)
                for item in source.implants:
                    if (
                        item.actor == actor
                        and item.vessel == vessel
                        and item.site.casefold() == site.strip().casefold()
                        and rules.attached(birth, item.id)
                    ):
                        rules.add_alert(
                            state,
                            source,
                            item,
                            reason="site_void",
                            event=event,
                            source_event=source_event,
                            asset=asset,
                            attribution=value.id,
                        )
            self.game.event(c, viewer.user_id, key, "m3.tracker_site_void", state, event_id=event)
            return dict(id=value.id, game_revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.tracker_site_void",
            dict(revision=revision, source_event=source_event, asset=asset, site=site),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            own = [x for x in rules.acquisitions(state) if int(x.handler.entity) == viewer.user_id]
            if own:
                source = current(self.game, c, state, own[0].id)
                if (
                    identity is not None
                    and identity != source.id
                    and not any(
                        x.id == identity and x.acquisition == source.id
                        for x in rules.records(state, rules.Alert)
                    )
                ):
                    raise WorkflowError("Use your original private tracker controls")
                rows = []
                for item in source.implants:
                    prove_installation(self.game, c, state, item.id)
                    cell = None
                    gap = None
                    if rules.attached(state, item.id):
                        try:
                            cell = location(self.game, c, state, item)
                        except ValueError as error:
                            gap = str(error)
                    rows.append(
                        dict(
                            id=item.id,
                            actor=item.actor.model_dump(mode="json"),
                            site=item.site,
                            asset=item.asset,
                            vessel=item.vessel,
                            attached=rules.attached(state, item.id),
                            cell=cell,
                            gap=gap,
                        )
                    )
                moments = []
                for moment in rules.records(state, rules.Moment):
                    if any(
                        x.actor == moment.actor
                        and x.vessel == moment.vessel
                        and rules.attached(state, x.id)
                        for x in source.implants
                    ):
                        prove_moment(self.game, c, state, moment.id)
                        moments.append(
                            dict(
                                id=moment.id,
                                label=state.sheets[moment.actor.entity].callsign,
                                actor=moment.actor.model_dump(mode="json"),
                                scene=moment.cast.channel,
                            )
                        )
                alerts = []
                for alert in rules.records(state, rules.Alert):
                    if alert.acquisition == source.id:
                        prove_alert(self.game, c, state, alert)
                        alerts.append(alert.model_dump(mode="json"))
                return dict(
                    id=source.id,
                    game_revision=state.revision,
                    owner=True,
                    implants=rows,
                    alerts=alerts,
                    moments=moments,
                    can_record_initial=physical_cell(
                        state, source.handler, profiles(c, self.store.campaign_id)
                    )
                    is None,
                    handler=source.handler.model_dump(mode="json"),
                    scenes=[
                        dict(id=str(x.channel), label=str(x.channel))
                        for x in state.scene_casts
                        if x.open
                    ],
                )
            if viewer.user_id == state.handler:
                from girlframe.services.m3_medical import MedicalService

                handler, appointment = MedicalService(self.store)._handler(c)
                held = [
                    x
                    for x in awards.awards(state)
                    if x.handler.entity == str(handler)
                    and x.appointment == appointment
                    and x.phase == "held"
                ]
                if identity is not None and identity not in {x.id for x in held}:
                    raise WorkflowError("Use an actual held original Handler advancement")
                return dict(
                    id=identity,
                    game_revision=state.revision,
                    owner=True,
                    awards=[dict(id=x.id, label="Actual held advancement") for x in held],
                    roster=[
                        dict(
                            actor=current_ref(state, x).model_dump(mode="json"),
                            label=state.sheets[str(x)].callsign,
                            assets=[
                                dict(id=a.id, name=a.name)
                                for a in state.sheets[str(x)].assets
                                if a.family == "girl" and a.battery_asset is None
                            ],
                        )
                        for x in state.order
                    ],
                )
            actor = current_ref(state, viewer.user_id)
            if identity is not None and identity != "tracker-body-facts:" + actor.token:
                raise WorkflowError("This tracker knowledge belongs to its original Handler")
            return dict(
                id="tracker-body-facts:" + actor.token,
                game_revision=state.revision,
                owner=False,
                actor=actor.model_dump(mode="json"),
                scenes=[
                    dict(id=str(x.channel), label=str(x.channel))
                    for x in state.scene_casts
                    if x.open and any(r.actor == actor for r in x.roles)
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        rows = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Private tracker locations / controls",
                phase="active",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if int(x.handler.entity) == viewer.user_id
        ]
        for source in rules.acquisitions(state):
            if int(source.handler.entity) == viewer.user_id:
                rows.extend(
                    dict(
                        id=x.id,
                        revision=state.revision,
                        label="Tracker alert: " + x.reason,
                        phase="recorded",
                        pending=False,
                    )
                    for x in rules.records(state, rules.Alert)
                    if x.acquisition == source.id
                )
        if str(viewer.user_id) in state.sheets and state.sheets[str(viewer.user_id)].character_id:
            actor = current_ref(state, viewer.user_id)
            rows.append(
                dict(
                    id="tracker-body-facts:" + actor.token,
                    revision=state.revision,
                    label="Record actual body / fictional scene facts",
                    phase="available",
                    pending=False,
                )
            )
        return rows
