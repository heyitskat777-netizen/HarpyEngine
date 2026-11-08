"""Actual advancement acquisition, owned Mission deliveries and mechanical expiry."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_supply_drop as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
from girlframe.engine.m3_core import install
from girlframe.engine.m3_doctor import repair
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_modular import Replacement, replace_repaired
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import create_loss_work, identity, snapshots
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_modular import entitlement as modular_entitlement
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, receipt_id: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == receipt_id), None)
    if value is None:
        raise WorkflowError("Recover the actual acquired Supply Drop rule source")
    original = _history(c, game, value.event)
    born = next((x for x in rules.acquisitions(original) if x.id == receipt_id), None)
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.phase != "spent"
        or award.acquired_rule != rules.RULE
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (value.handler, value.appointment) != (handler, appointment)
    ):
        raise WorkflowError("Recover this actual original advancement purchase receipt")
    return value


def use_source(game: GameService, c: Connection, state: GameState, identity_: str) -> rules.Use:
    value = next((x for x in rules.uses(state) if x.id == identity_), None)
    if value is None:
        raise WorkflowError("Recover the actual original Supply Drop use")
    paid(game, c, state, value.acquisition)
    original = _history(c, game, value.event)
    born = next((x for x in rules.uses(original) if x.id == identity_), None)
    stable = (
        "id",
        "acquisition",
        "handler",
        "mission",
        "target",
        "frame",
        "kind",
        "asset",
        "name",
        "description",
        "position",
        "cell",
        "event",
        "account",
    )
    if born is None or any(getattr(born, k) != getattr(value, k) for k in stable):
        raise WorkflowError("Recover the actual immutable repair/delivery proposal")
    if value.effect_event:
        effect = _history(c, game, value.effect_event)
        delivered = next((x for x in rules.uses(effect) if x.id == value.id), None)
        if delivered is None or delivered.phase not in ("delivered", "repaired"):
            raise WorkflowError("Recover this actual delivered equipment or repair effect")
    return value


def _frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        raise WorkflowError("Recover the actual original Girl")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def _idle(game: GameService, c: Connection) -> None:
    if game.pending_actions(c):
        raise WorkflowError("Finish the actual pending Play before this Supply Drop effect")


class SupplyDropService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "missions", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _current(self, c: Connection, state: GameState, value: rules.Acquisition) -> None:
        HandlerAdvancementService(self.store)._current(c, state, value.handler, value.appointment)

    def _mission(self, c: Connection, state: GameState, mission_id: str) -> Mission:
        missions = MissionService(self.store)
        mission = missions._mission(c, mission_id)
        if mission.phase != "active" or mission.handler != state.handler:
            raise WorkflowError("Use an actual active Mission under its current Handler")
        missions._source_characters(c, mission)
        return mission

    def menu(self, viewer: GuildViewer, mission_id: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            held = []
            for x in rules.acquisitions(state):
                if same_handler_body(state, x.handler):
                    value = paid(self.game, c, state, x.id)
                    self._current(c, state, value)
                    held.append(dict(id=value.id, award=value.award))
            awards = HandlerAdvancementService(self.store)._tasks(c, viewer)
            missions = [
                dict(id=x["id"], label=json.loads(x["body_json"])["objective"])
                for x in c.execute(
                    sa.select(t.m3["m3_missions"]).where(
                        t.m3["m3_missions"].c.campaign_id == self.store.campaign_id
                    )
                ).mappings()
                if json.loads(x["body_json"])["phase"] == "active"
                and json.loads(x["body_json"])["handler"] == viewer.user_id
            ]
            targets = []
            used = False
            if held and mission_id:
                self._mission(c, state, mission_id)
                used = rules.spent(state, held[0]["id"], mission_id)
                for sheet in state.sheets.values():
                    actor = current_ref(state, sheet.owner)
                    actual = resolve(
                        state,
                        actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    targets.append(
                        dict(
                            actor=actor.model_dump(mode="json"),
                            token=actor.token,
                            label=sheet.callsign,
                            damaged=[
                                dict(id=x.id, label=x.name)
                                for x in sheet.assets
                                if x.damaged and (x.family == "girl" or not sheet.frame_scrapped)
                            ],
                            deliverable=actual.frame_cell is not None
                            and not sheet.frame_scrapped
                            and not actual.offstage_source,
                        )
                    )
            return dict(
                revision=state.revision,
                owned=bool(held),
                receipt=held[0]["id"] if held else None,
                awards=awards,
                missions=missions,
                mission=mission_id,
                targets=targets,
                used=used,
            )

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
                or len(account) > 1200
                or any(same_handler_body(state, x.handler) for x in rules.acquisitions(state))
            ):
                raise WorkflowError("Use one actual held advancement for an unowned Supply Drop")
            event = str(uuid4())
            receipt_id = "supply-drop:" + award_id
            value = rules.Acquisition(
                id=receipt_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            consumed = advancement.Award.model_validate_json(
                award.model_copy(
                    update=dict(
                        phase="spent",
                        acquired_rule=rules.RULE,
                        acquisition=receipt_id,
                        spend_event=event,
                        spend_account=account.strip(),
                    )
                ).model_dump_json()
            )
            advancement.put(state, consumed)
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
            return dict(id=receipt_id, phase="acquired")

        return self.store._write(
            viewer,
            key,
            "m3.supply_drop_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        mission_id: str,
        revision: int,
        kind: str,
        target: ActorRef,
        account: str,
        *,
        asset: str | None = None,
        name: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _idle(self.game, c)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            self._mission(c, state, mission_id)
            values = [x for x in rules.acquisitions(state) if same_handler_body(state, x.handler)]
            if len(values) != 1:
                raise WorkflowError("Use your actual original acquired Supply Drop")
            value = paid(self.game, c, state, values[0].id)
            self._current(c, state, value)
            if (
                state.revision != revision
                or kind not in ("repair", "drop")
                or not account.strip()
                or len(account) > 1200
                or rules.spent(state, value.id, mission_id)
                or any(
                    x.acquisition == value.id and x.mission == mission_id and x.phase == "proposed"
                    for x in rules.uses(state)
                )
            ):
                raise WorkflowError("Reopen this Mission's actual unused Supply Drop")
            actual = resolve(
                state, target, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if target.kind != "pilot" or current_ref(state, int(target.entity)) != target:
                raise WorkflowError("Use an actual current original Girl")
            sheet = state.sheets[target.entity]
            frame = _frame(state, target)
            identity_ = str(uuid4())
            event = str(uuid4())
            if kind == "repair":
                item = next(
                    (
                        x
                        for x in sheet.assets
                        if x.id == asset
                        and x.damaged
                        and (x.family == "girl" or not sheet.frame_scrapped)
                    ),
                    None,
                )
                if item is None:
                    raise WorkflowError("Select one actual damaged owned Asset")
                name_, description_ = item.name, item.description or "Actual owned damaged Asset"
                request = bool(
                    item.family == "frame" and modular_entitlement(self.game, c, state, target)
                )
                asset_id = item.id
            else:
                if (
                    sheet.frame_scrapped
                    or actual.frame_cell is None
                    or actual.offstage_source
                    or not name.strip()
                    or not description.strip()
                    or len(name) > 120
                    or len(description) > 1200
                ):
                    raise WorkflowError(
                        "Author actual equipment for this known current Frame position"
                    )
                name_, description_ = name.strip(), description.strip()
                request = True
                asset_id = "supply-drop:" + identity_
            use = rules.Use(
                id=identity_,
                acquisition=value.id,
                handler=value.handler,
                mission=mission_id,
                target=target,
                frame=frame,
                kind="repair" if kind == "repair" else "drop",
                phase="proposed" if request else "repaired",
                asset=asset_id,
                name=name_,
                description=description_,
                position=actual.source_sha256,
                cell=actual.frame_cell,
                event=event,
                account=account.strip(),
                effect_event=None if request else event,
                effect_account=None if request else account.strip(),
            )
            if not request:
                repair(state, target, (asset_id,), 1)
            rules.put(state, use)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.supply_drop_" + ("proposed" if request else "repaired"),
                state,
                event_id=event,
                use_id=identity_,
                mission_id=mission_id,
            )
            return dict(id=identity_, phase=use.phase)

        return self.store._write(
            viewer,
            key,
            "m3.supply_drop_used",
            dict(
                mission=mission_id,
                revision=revision,
                kind="repair" if kind == "repair" else "drop",
                target=target.model_dump(mode="json"),
                account=account,
                asset=asset,
                name=name,
                description=description,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Supply Drop — actual owned delivery",
                phase=x.phase,
                subject=int(x.target.entity),
            )
            for x in rules.uses(state)
            if x.phase == "proposed"
            and viewer.user_id in (int(x.target.entity), int(x.handler.entity))
            or x.phase == "expired"
            and x.in_battle is None
            and self._context_pending(c, x)
            and viewer.user_id == state.handler
        ]

    def _context_pending(self, c: Connection, use: rules.Use) -> bool:
        work = t.m3["m3_required_work"]
        raw = c.scalar(
            sa.select(work.c.state)
            .where(
                work.c.campaign_id == self.store.campaign_id,
                work.c.id == identity("supply_drop_expiry", use.id, use.target, "context"),
            )
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        return raw == "pending"

    def view_delivery(self, viewer: GuildViewer, identity_: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            use = use_source(self.game, c, state, identity_)
            if viewer.user_id not in (
                int(use.target.entity),
                int(use.handler.entity),
            ):
                raise WorkflowError("This actual delivery belongs to its original participants")
            sheet = state.sheets.get(use.target.entity)
            valid = sheet is not None and sheet.character_id == use.target.incarnation
            at_cap = bool(
                sheet is not None
                and valid
                and sum(x.family == "frame" and counts_toward_limit(sheet, x) for x in sheet.assets)
                >= frame_capacity(sheet, state)
            )
            return dict(
                id=use.id,
                revision=state.revision,
                phase=use.phase,
                kind=use.kind,
                receiver=viewer.user_id == int(use.target.entity),
                name=use.name,
                description=use.description,
                asset=use.asset,
                account=use.account,
                effect_account=use.effect_account,
                mission=use.mission,
                context_pending=self._context_pending(c, use),
                modular=bool(
                    valid
                    and use.kind == "repair"
                    and modular_entitlement(self.game, c, state, use.target)
                ),
                needs_replace=at_cap and use.kind == "drop",
                replacements=[
                    dict(id=x.id, label=x.name)
                    for x in sheet.assets
                    if x.family == "frame"
                    and can_replace_at_limit(sheet, x)
                    and x.id not in stored_ids(state, use.target)
                ]
                if sheet is not None and valid and at_cap
                else [],
            )

    def receive(
        self,
        viewer: GuildViewer,
        key: str,
        identity_: str,
        revision: int,
        accept: bool,
        account: str,
        *,
        replace: str | None = None,
        modular: Replacement | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _idle(self.game, c)
            state = load_state(c, self.store.campaign_id)
            use = use_source(self.game, c, state, identity_)
            value = paid(self.game, c, state, use.acquisition)
            self._current(c, state, value)
            self._mission(c, state, use.mission)
            if (
                state.revision != revision
                or use.phase != "proposed"
                or type(accept) is not bool
                or not account.strip()
                or len(account) > 1200
                or viewer.user_id not in (int(use.target.entity), int(use.handler.entity))
                or accept
                and viewer.user_id != int(use.target.entity)
            ):
                raise WorkflowError(
                    "Only the actual original recipient receives and installs this source"
                )
            event = str(uuid4())
            if accept:
                actual = resolve(
                    state,
                    use.target,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if actual.source_sha256 != use.position or _frame(state, use.target) != use.frame:
                    raise WorkflowError(
                        "Reopen the actual unchanged Girl, Frame, resources and delivery position"
                    )
                if rules.spent(state, use.acquisition, use.mission):
                    raise WorkflowError("This Mission's Supply Drop was already used")
                if use.kind == "drop":
                    if modular is not None or actual.frame_cell != use.cell:
                        raise WorkflowError(
                            "Deliver the actual Frame equipment at its frozen position"
                        )
                    state.sheets[use.target.entity] = install(
                        state.sheets[use.target.entity],
                        AssetState(
                            id=use.asset, family="frame", name=use.name, description=use.description
                        ),
                        replace=replace,
                        effective_void=stored_ids(state, use.target),
                        state=state,
                    ).sheet
                else:
                    if replace is not None or modular is not None and modular.asset != use.asset:
                        raise WorkflowError(
                            "Choose only this actual repaired Asset's Modular option"
                        )
                    before = state.sheets[use.target.entity].model_copy(deep=True)
                    repair(state, use.target, (use.asset,), 1)
                    if modular is not None:
                        if modular_entitlement(self.game, c, state, use.target) is None:
                            raise WorkflowError("Restore the actual original Modular source")
                        replace_repaired(state, use.target, before, (modular,), None, source=use.id)
                phase = "delivered" if use.kind == "drop" else "repaired"
            else:
                phase = "declined" if viewer.user_id == int(use.target.entity) else "cancelled"
            use = use.model_copy(
                update=dict(
                    phase=phase,
                    effect_event=event if accept else None,
                    effect_account=account.strip(),
                    replacement=replace,
                )
            )
            rules.put(state, use)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.supply_drop_" + phase,
                state,
                event_id=event,
                use_id=use.id,
            )
            return dict(id=use.id, phase=phase)

        return self.store._write(
            viewer,
            key,
            "m3.supply_drop_received",
            dict(
                id=identity_,
                revision=revision,
                accept=accept,
                account=account,
                replace=replace,
                modular=modular.model_dump(mode="json") if modular else None,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def review_expiry(
        self,
        viewer: GuildViewer,
        key: str,
        identity_: str,
        revision: int,
        in_battle: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _idle(self.game, c)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            use = use_source(self.game, c, state, identity_)
            if (
                state.revision != revision
                or use.phase != "expired"
                or use.context_event is not None
                or not self._context_pending(c, use)
                or type(in_battle) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual Handler-owned loss context review")
            work = t.m3["m3_required_work"]
            row = dict(
                c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.id == identity("supply_drop_expiry", use.id, use.target, "context"),
                    )
                    .order_by(work.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .one()
            )
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("This factual loss review belongs to its actual Handler")
            event = str(uuid4())
            use = use.model_copy(
                update=dict(
                    context_event=event,
                    in_battle=in_battle,
                    reviewer=active_handler(state),
                    context_account=account.strip(),
                )
            )
            rules.put(state, use)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.supply_drop_context_reviewed",
                state,
                event_id=event,
                use_id=use.id,
            )
            c.execute(
                work.insert().values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            if in_battle:
                body = json.loads(row["body_json"]) | dict(
                    source_pdf=29,
                    in_battle=True,
                    context_event=event,
                    trigger="last_frame_asset_removed",
                )
                related(
                    c,
                    self.store,
                    row,
                    identity("supply_drop_expiry", use.id, use.target, "defeat"),
                    int(use.target.entity),
                    int(use.target.entity),
                    "defeat",
                    body,
                    event,
                )
            return dict(id=use.id, defeat_required=in_battle)

        return self.store._write(
            viewer,
            key,
            "m3.supply_drop_context_reviewed",
            dict(id=identity_, revision=revision, in_battle=in_battle, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )


def expire_mission(
    game: GameService, c: Connection, mission: Mission, viewer: GuildViewer, key: str
) -> list[str]:
    """Expire source equipment before rewards; real followups keep the Mission ending."""
    state = load_state(c, game.store.campaign_id)
    result = []
    for value in tuple(rules.uses(state)):
        if value.mission != mission.id or value.phase not in ("proposed", "delivered"):
            continue
        use_source(game, c, state, value.id)
        event = str(uuid4())
        prior_index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
            )
        )
        event_index = max(0, int(prior_index or 0)) + 1
        if value.phase == "proposed":
            rules.put(state, value.model_copy(update=dict(phase="cancelled")))
            game.event(
                c,
                viewer.user_id,
                key,
                "m3.supply_drop_cancelled",
                state,
                event_id=event,
                event_index=event_index,
                use_id=value.id,
                mission_id=mission.id,
            )
            continue
        if _frame(state, value.target) != value.frame:
            raise WorkflowError("Recover the original temporary equipment's actual Frame container")
        before = GameState.model_validate_json(state.model_dump_json())
        sheet = state.sheets[value.target.entity]
        asset_id = rules.current_asset(state, value)
        previous = len(sheet.assets)
        sheet.assets = [x for x in sheet.assets if x.id != asset_id]
        if len(sheet.assets) != previous:
            sheet.revision += 1
        rules.put(state, value.model_copy(update=dict(phase="expired", expiry_event=event)))
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.supply_drop_expired",
            state,
            event_id=event,
            event_index=event_index,
            use_id=value.id,
            mission_id=mission.id,
        )
        result += create_loss_work(
            game,
            c,
            before,
            state,
            scope=dict(campaign_id=game.store.campaign_id, mission_id=mission.id),
            actor=value.target,
            event=event,
            reason="supply_drop_expiry",
            source_id=value.id,
        )
    return result


def require_expired(state: GameState, mission_id: str) -> None:
    if any(
        x.mission == mission_id and x.phase in ("proposed", "delivered") for x in rules.uses(state)
    ):
        raise WorkflowError("Expire the actual Mission Supply Drop before rewards or completion")


def prove_loss_source(
    game: GameService, c: Connection, proof: GameState, event: str, source_id: str, actor: ActorRef
) -> dict[str, bool | None]:
    before, after = snapshots(game, c, event)
    old = next((x for x in rules.uses(before) if x.id == source_id), None)
    new = next((x for x in rules.uses(after) if x.id == source_id), None)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if old is None or new is None or proof != after:
        raise WorkflowError("Recover the actual immutable Supply Drop expiry")
    use_source(game, c, after, source_id)
    mission = MissionService(game.store)._mission(c, new.mission)
    asset_id = rules.current_asset(before, old)
    a = before.sheets.get(actor.entity)
    b = after.sheets.get(actor.entity)
    if (
        old.phase != "delivered"
        or new.phase != "expired"
        or new.expiry_event != event
        or old.target != actor
        or new.target != actor
        or old.frame != new.frame
        or audit is None
        or audit["kind"] != "m3.supply_drop_expired"
        or audit["actor_id"] != str(mission.handler)
        or json.loads(audit["payload_json"]).get("use_id") != source_id
        or a is None
        or b is None
        or a.character_id != actor.incarnation
        or b.character_id != actor.incarnation
        or not any(x.id == asset_id for x in a.assets)
        or [x for x in a.assets if x.id != asset_id] != b.assets
    ):
        raise WorkflowError("Prove the exact temporary Asset removed from its actual Frame")
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    current = next(
        x for x in rules.uses(load_state(c, game.store.campaign_id)) if x.id == source_id
    )
    battle = None
    if current.context_event:
        review = _history(c, game, current.context_event)
        recorded = next((x for x in rules.uses(review) if x.id == source_id), None)
        review_event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == current.context_event,
                )
            )
            .mappings()
            .first()
        )
        context_id = identity("supply_drop_expiry", source_id, actor, "context")
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(
                    t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                    t.m3["m3_required_work"].c.id == context_id,
                )
                .order_by(t.m3["m3_required_work"].c.revision)
            )
            .mappings()
            .first()
        )
        if (
            recorded is None
            or recorded.context_event != current.context_event
            or recorded.in_battle != current.in_battle
            or current.reviewer is None
            or review_event is None
            or review_event["kind"] != "m3.supply_drop_context_reviewed"
            or review_event["actor_id"] != current.reviewer.entity
            or work is None
            or work["owner_id"] != current.reviewer.entity
            or work["event_id"] != event
        ):
            raise WorkflowError("Recover the actual Handler's original loss-context judgment")
        battle = current.in_battle
    return dict(piloting=actual.piloting, in_battle=battle)
