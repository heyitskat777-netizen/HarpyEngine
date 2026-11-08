"""Original-player maintenance losses and genuine persistent source consequences."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_removal as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def history(game: GameService, c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual immutable Budget removal source")
    return GameState.model_validate_json(raw)


def roster(original: GameState) -> tuple[ActorRef, ...]:
    from girlframe.engine.creation_catalog import CATALOG

    result = tuple(current_ref(original, uid) for uid in original.order)
    if not result or any(
        x.kind != "pilot" or CATALOG.get(original.sheets[x.entity].girl, {}).get("family") != "girl"
        for x in result
    ):
        raise WorkflowError("SOURCE_PORT_REQUIRED: recover this original native Girl roster")
    return result


def original_frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        raise WorkflowError("Recover this actual original Girl, not her successor")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def first_event(game: GameService, c: Connection, work: str) -> str:
    table = t.m3["m3_required_work"]
    return str(
        c.scalar(
            sa.select(table.c.event_id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == work)
            .order_by(table.c.revision)
            .limit(1)
        )
    )


def prove_context(game: GameService, c: Connection, value: rules.Context) -> None:
    row, original = _selection(c, game, value.work, rule=rules.RULE)
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    saved = history(game, c, value.event)
    if (
        value not in rules.contexts(saved)
        or value.actor not in roster(original)
        or value.handler != active_handler(original)
        or value.source_event != first_event(game, c, row["id"])
        or value.frame != original_frame(original, value.actor)
        or event is None
        or event.kind != "m3.budget_removal_context"
        or event.actor_id != value.handler.entity
    ):
        raise WorkflowError("Recover the original Handler's actual physical and opponent facts")


def prove_loss_source(
    game: GameService, c: Connection, proof: GameState, event: str, source_id: str, actor: ActorRef
) -> dict[str, bool | None]:
    from girlframe.services.m3_asset_loss import snapshots

    value = next(
        (
            x
            for x in rules.losses(proof)
            if x.id == source_id and x.actor == actor and x.event == event
        ),
        None,
    )
    if value is None:
        raise WorkflowError("Recover the actual original player's Asset removal")
    _, original = _selection(c, game, value.work, rule=rules.RULE)
    context = next((x for x in rules.contexts(proof) if x.id == value.context), None)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if (
        context is None
        or actor not in roster(original)
        or audit is None
        or audit.kind != "m3.budget_assets_removed"
        or audit.actor_id != actor.entity
        or context.actor != actor
        or value.frame != original_frame(original, actor)
    ):
        raise WorkflowError("Recover the exact real removal and source subject")
    prove_context(game, c, context)
    before, after = snapshots(game, c, event)
    if (
        after != proof
        or next((x for x in before.placements if x.actor == actor), None) != context.placement
    ):
        raise WorkflowError("Recover the unchanged actual pre-loss body context")
    expected, actual = rules.remove(
        before, context, value.id, value.girl_asset.id, value.frame_asset.id, event, value.account
    )
    expected.revision = after.revision
    if expected != after or actual != value:
        raise WorkflowError("Recover the exact original Asset pair and mechanical loss")
    return dict(piloting=context.piloting, in_battle=context.in_battle)


def prove_bound(game: GameService, c: Connection, state: GameState, value: rules.Loss) -> None:
    original = history(game, c, value.event)
    initial = next((x for x in rules.losses(original) if x.id == value.id), None)
    if initial != value.model_copy(update=dict(children=(), bound_event=None)):
        raise WorkflowError("Recover this immutable original removal receipt")
    prove_loss_source(game, c, original, value.event, value.id, value.actor)
    if value.bound_event is None:
        raise WorkflowError("Bind the actual source consequences before finishing removal")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.bound_event
        )
    ).first()
    if (
        value not in rules.losses(history(game, c, value.bound_event))
        or audit is None
        or audit.kind != "m3.budget_removal_bound"
        or audit.actor_id != value.actor.entity
    ):
        raise WorkflowError("Recover the actual bound mandatory Asset-loss work")


class RemovalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _base(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, GameState]:
        Access(self.store).authorize(c, viewer, "strain")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        people = roster(original)
        handler = active_handler(original)
        state = load_state(c, self.store.campaign_id)
        if (
            handler is None
            or row["owner_id"] != handler.entity
            or viewer.user_id not in {int(x.entity) for x in (*people, handler)}
            or not same_handler_body(state, handler)
        ):
            raise WorkflowError("Use this original Endgame's actual Handler or affected Girl")
        return row, original, state

    def _current(
        self, c: Connection, original: GameState, state: GameState, actor: ActorRef, identity: str
    ) -> None:
        completed = {
            x.actor
            for x in rules.losses(state)
            if x.work == identity and x.actor in roster(original)
        }
        if set(state.order) - set(original.order):
            raise WorkflowError("SOURCE_PORT_REQUIRED: recover this changed actual Girl roster")
        for person in roster(original):
            if person not in completed and (
                str(person.entity) not in state.sheets
                or current_ref(state, int(person.entity)) != person
            ):
                raise WorkflowError("SOURCE_PORT_REQUIRED: recover the unchosen original Girl body")
        if current_ref(state, int(actor.entity)) != actor or original_frame(
            state, actor
        ) != original_frame(original, actor):
            raise WorkflowError("SOURCE_PORT_REQUIRED: recover this original body and Frame")
        self.game.character_binding(c, state, int(actor.entity), require_current_profile=False)
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        body = next((x for x in state.placements if x.actor == actor), None)
        if (
            body is None
            or actual.inside_frame is None
            or actual.piloting is None
            or actual.cell is None
            or actual.frame_cell is None
            or actual.offstage_source
            or body.custody
            or body.occupied_frame_owner
            or body.subsumed
            or not body.vitals_active
            or body.incapacitated
            or any(x.state == "boarded" and x.carrier == actor for x in state.passengers)
        ):
            raise WorkflowError(
                "SOURCE_PORT_REQUIRED: establish this free original body's actual physical facts"
            )

    def _children(self, c: Connection, value: rules.Loss) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        result = []
        for identity in value.children:
            row = (
                c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("Recover the actual mandatory removal consequence")
            body = json.loads(row["body_json"])
            if (
                body.get("reason") != "budget_removal"
                or body.get("source_id") != value.id
                or body.get("loss_event") != value.event
                or body.get("owner") != value.actor.model_dump(mode="json")
            ):
                raise WorkflowError("Recover this original removal's exact source child")
            result.append(dict(id=identity, kind=row["kind"], state=row["state"]))
        return result

    def view(
        self, viewer: GuildViewer, identity: str, actor: ActorRef | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer, identity, actor)

    def _view(
        self, c: Connection, viewer: GuildViewer, identity: str, actor: ActorRef | None = None
    ) -> dict[str, Any]:
        row, original, state = self._base(c, viewer, identity)
        handler = active_handler(original)
        assert handler is not None
        gm = viewer.user_id == int(handler.entity)
        people = roster(original)
        if not gm:
            own = next(x for x in people if int(x.entity) == viewer.user_id)
            if actor is not None and actor != own:
                raise WorkflowError("Only your own original Asset lists are private to you")
            actor = own
        elif actor is not None and actor not in people:
            raise WorkflowError("Choose one actual source-roster original Girl")
        losses = [x for x in rules.losses(state) if x.work == identity]
        for loss in losses:
            prove_bound(self.game, c, state, loss)
        rows = [
            dict(
                actor=x.model_dump(mode="json"),
                label=original.sheets[x.entity].callsign,
                removed=any(y.actor == x for y in losses),
            )
            for x in people
        ]
        result = dict(
            id=identity,
            revision=row["revision"],
            game_revision=state.revision,
            gm=gm,
            phase="complete" if row["state"] == "resolved" else "roster",
            people=rows,
            actor=actor.model_dump(mode="json") if actor else None,
            assets=[],
            children=[],
            context=None,
            can_finish=len(losses) == len(people)
            and all(
                all(x["state"] == "resolved" for x in self._children(c, loss)) for loss in losses
            ),
        )
        if actor is not None:
            removed = next((x for x in losses if x.actor == actor), None)
            if removed:
                children = self._children(c, removed)
                result.update(
                    phase="resolved" if row["state"] == "resolved" else "removed",
                    children=children,
                    loss=removed.id,
                    pending=any(x["state"] != "resolved" for x in children),
                )
                if viewer.user_id == int(actor.entity):
                    result["record"] = removed.model_dump(mode="json")
                return result
            self._current(c, original, state, actor, identity)
            context = next(
                (
                    x
                    for x in reversed(rules.contexts(state))
                    if x.work == identity and x.actor == actor
                ),
                None,
            )
            if context:
                prove_context(self.game, c, context)
            body = next(x for x in state.placements if x.actor == actor)
            if context is not None and context.placement != body:
                context = None
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            result.update(
                phase="choose" if context else "context",
                context=context.model_dump(mode="json") if context else None,
                physical=dict(
                    inside_frame=actual.inside_frame,
                    piloting=actual.piloting,
                    cell=actual.cell,
                    frame_cell=actual.frame_cell,
                ),
            )
            if viewer.user_id == int(actor.entity):
                blocked = rules.blocked(state, actor)
                result["assets"] = [
                    x.model_dump(mode="json") | dict(blocked=blocked.get(x.id))
                    for x in state.sheets[actor.entity].assets
                ]
            if gm:
                candidates = [*people, handler]
                if state.world:
                    candidates.extend(
                        ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive
                    )
                    candidates.extend(
                        ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons if x.alive
                    )
                opponents = []
                for ref in candidates:
                    if ref == actor:
                        continue
                    try:
                        view = resolve(
                            state,
                            ref,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        )
                    except ValueError:
                        continue
                    opponents.append(
                        dict(ref=ref.model_dump(mode="json"), token=ref.token, label=view.label)
                    )
                result["opponents"] = opponents
        return result

    def review_context(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        actor: ActorRef,
        expected: int,
        *,
        inside_frame: bool,
        piloting: bool,
        in_battle: bool,
        opponent: ActorRef | None,
        opponent_known: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, original, state = self._base(c, viewer, identity)
            handler = active_handler(original)
            if (
                handler is None
                or viewer.user_id != int(handler.entity)
                or row["state"] != "pending"
                or state.revision != expected
                or actor not in roster(original)
                or any(x.work == identity and x.actor == actor for x in rules.losses(state))
                or not account.strip()
                or len(account) > 1200
                or opponent_known is not True
            ):
                raise WorkflowError("Record this original Handler's actual pending factual context")
            _ordinary_scene_idle(c, self.game)
            self._current(c, original, state, actor, identity)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                type(in_battle) is not bool
                or inside_frame is not actual.inside_frame
                or piloting is not actual.piloting
            ):
                raise WorkflowError("Use the actual canonical inside-Frame and piloting facts")
            if opponent:
                if opponent == actor:
                    raise WorkflowError("An actual opponent is another original person")
                resolve(
                    state,
                    opponent,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
            event = str(uuid4())
            value = rules.Context(
                id=event,
                work=identity,
                source_event=first_event(self.game, c, identity),
                handler=handler,
                actor=actor,
                frame=original_frame(original, actor),
                event=event,
                placement=next(x for x in state.placements if x.actor == actor),
                inside_frame=inside_frame,
                piloting=piloting,
                in_battle=in_battle,
                opponent=opponent,
                opponent_known=True,
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_removal_context",
                state,
                event_id=event,
                work_id=identity,
                affected_actor=actor.model_dump(mode="json"),
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.budget_removal_context",
            dict(
                work=identity,
                actor=actor.model_dump(mode="json"),
                expected=expected,
                inside_frame=inside_frame,
                piloting=piloting,
                in_battle=in_battle,
                opponent=opponent.model_dump(mode="json") if opponent else None,
                opponent_known=opponent_known,
                account=account,
            ),
            operation,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "strain"),
            auto_audit=False,
        )

    def remove(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        girl_asset: str,
        frame_asset: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, original, state = self._base(c, viewer, identity)
            actor = next((x for x in roster(original) if x.entity == str(viewer.user_id)), None)
            if actor is None or row["state"] != "pending" or state.revision != expected:
                raise WorkflowError("Only the actual original Girl chooses her pending Asset pair")
            _ordinary_scene_idle(c, self.game)
            self._current(c, original, state, actor, identity)
            context = next(
                (
                    x
                    for x in reversed(rules.contexts(state))
                    if x.work == identity and x.actor == actor
                ),
                None,
            )
            if context is None:
                raise WorkflowError("The original Handler must record actual context first")
            prove_context(self.game, c, context)
            if next((x for x in state.placements if x.actor == actor), None) != context.placement:
                raise WorkflowError("Refresh this original body's actual changed physical context")
            event = str(uuid4())
            loss_id = str(uuid5(NAMESPACE_URL, "budget-removal:" + identity + ":" + actor.token))
            changed, value = rules.remove(
                state, context, loss_id, girl_asset, frame_asset, event, account
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_assets_removed",
                changed,
                event_id=event,
                work_id=identity,
                loss_id=loss_id,
            )
            from girlframe.services.m3_asset_loss import create_loss_work

            children = create_loss_work(
                self.game,
                c,
                state,
                changed,
                scope=dict(campaign_id=self.store.campaign_id, off_duty_id=row["off_duty_id"]),
                actor=actor,
                event=event,
                reason="budget_removal",
                source_id=loss_id,
                in_battle=context.in_battle,
            )
            bound = str(uuid4())
            rules.put(
                changed, value.model_copy(update=dict(children=tuple(children), bound_event=bound))
            )
            self.game.event(
                c,
                viewer.user_id,
                str(uuid4()),
                "m3.budget_removal_bound",
                changed,
                event_id=bound,
                work_id=identity,
                loss_id=loss_id,
                child_count=len(children),
            )
            return dict(id=loss_id, children=children)

        return self.store._write(
            viewer,
            key,
            "m3.budget_assets_removed",
            dict(
                work=identity,
                expected=expected,
                girl_asset=girl_asset,
                frame_asset=frame_asset,
                account=account,
            ),
            operation,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "strain"),
            auto_audit=False,
        )

    def finish(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, original, state = self._base(c, viewer, identity)
            handler = active_handler(original)
            losses = [x for x in rules.losses(state) if x.work == identity]
            if (
                handler is None
                or viewer.user_id != int(handler.entity)
                or row["state"] != "pending"
                or state.revision != expected
                or {x.actor for x in losses} != set(roster(original))
            ):
                raise WorkflowError(
                    "Every original Girl must actually remove her own Asset pair first"
                )
            _ordinary_scene_idle(c, self.game)
            for value in losses:
                prove_bound(self.game, c, state, value)
                if any(x["state"] != "resolved" for x in self._children(c, value)):
                    raise WorkflowError(
                        "Finish every genuine mandatory Asset-loss consequence first"
                    )
            event = self.game.event(
                c, viewer.user_id, key, "m3.budget_removal_completed", work_id=identity
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, state="resolved")

        return self.store._write(
            viewer,
            key,
            "m3.budget_removal_completed",
            dict(work=identity, expected=expected),
            operation,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "strain"),
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.kind == "strain_endgame_effect",
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        result = []
        for row in rows.values():
            if json.loads(row["body_json"]).get("rule_id") != rules.RULE:
                continue
            try:
                data = self._view(c, viewer, row["id"])
            except (ValueError, WorkflowError):
                try:
                    _, original, _ = self._base(c, viewer, row["id"])
                except (ValueError, WorkflowError):
                    continue
                own = next((x for x in roster(original) if x.entity == str(viewer.user_id)), None)
                data = dict(
                    phase="source_recovery",
                    actor=own.model_dump(mode="json") if own else None,
                    pending=row["state"] == "pending",
                )
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    phase=data["phase"],
                    label="Original Budget Asset removal",
                    actor=data["actor"],
                    pending=data.get("pending", row["state"] == "pending"),
                )
            )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)
