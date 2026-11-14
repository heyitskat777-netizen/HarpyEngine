"""Source-proved, owner-chosen Sin of Temptation Void and its real continuations."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_bond_void as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_bond_operations import records as changes
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def require_rule(game: GameService, actor: ActorRef) -> None:
    registry = Access(game.store).registry
    approval = game.store.policy.m3_approval
    if (
        registry is None
        or approval is None
        or approval.registry_sha256 != digest(registry)
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        raise WorkflowError("M3_REVIEW_PENDING: review the real Sin of Temptation consequence")
    parent = next(x for x in registry.entries if x.id == rules.RULE)
    if actor.kind == "pilot" and not parent.verified:
        registry.require_available(rules.NATIVE_RULE)
    else:
        registry.require_available(rules.RULE)


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Temptation:
    value = rules.get(state, identity)
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original Harpy Bond change history")
    original = GameState.model_validate_json(raw)
    initial = rules.get(original, identity)
    change = next((x for x in changes(original) if x.id == value.change), None)
    if (
        change is None
        or change.event != value.source_event
        or change.delta != 1
        or change.before_depth not in (1, 2)
        or change.after_depth != 2
        or value.id != rules.effect_id(change, value.actor)
        or {change.first, change.second} != {value.harpy, value.actor}
        or not rules.is_harpy(original, value.harpy)
        or rules.actual_girl(original, value.actor).rules
        not in {"girl_frame", "handler_girl", "clone_am"}
        or any(
            getattr(initial, k) != getattr(value, k)
            for k in (
                "id",
                "change",
                "source_event",
                "harpy",
                "actor",
                "controller",
                "source_action",
            )
        )
        or initial.controller != rules.actual_girl(original, value.actor).controller
        or initial.phase != "rewrite"
        or initial.gain_event is not None
    ):
        raise WorkflowError("Recover the actual single Intense Harpy Bond's original Void onset")
    return value


def current(game: GameService, c: Connection, state: GameState, value: rules.Temptation) -> None:
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.controller != value.controller or actual.rules not in {
        "girl_frame",
        "handler_girl",
        "clone_am",
    }:
        raise WorkflowError("Recover this consequence's actual original Girl and controller")


def stage(
    game: GameService, c: Connection, state: GameState, event: str, metadata: dict[str, Any]
) -> None:
    """Before canonical save: approval cannot silently discard the printed onset."""
    for value in rules.cases(state):
        if value.source_event != event:
            continue
        require_rule(game, value.actor)
        identity = metadata.get("action_id")
        if value.source_action is None and metadata.get("case_id"):
            case = next((x for x in state.role_punishments if x.id == metadata["case_id"]), None)
            if (
                case is not None
                and case.action is not None
                and case.effect_event == event
                and case.instruction is not None
                and case.instruction.kind == "quality_time"
                and {case.executor, case.subject} == {value.harpy, value.actor}
            ):
                original = game.action(c, case.action)
                if original["state"] in ("complete", "aborted"):
                    raise WorkflowError("Recover the actual held source of this required Void gain")
                value = value.model_copy(update=dict(source_action=case.action))
                rules.put(state, value)
        if value.source_action is None and isinstance(identity, str):
            action = game.action(c, identity)
            if action["data"].get("response_event") == event:
                rules.put(state, value.model_copy(update=dict(source_action=identity)))


def hold_action(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> bool:
    """The genuine receipt waits; no extra roll or replacement source is invented."""
    held = False
    for value in rules.cases(state):
        if not (
            value.source_action == action["id"]
            or value.source_action is None
            and value.source_event == action["data"].get("response_event")
        ):
            continue
        if value.phase == "complete":
            continue
        require_rule(game, value.actor)
        held = True
        if value.source_action is None:
            value = value.model_copy(update=dict(source_action=action["id"]))
            rules.put(state, value)
        rows = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.action_id == action["id"],
                    t.m2["m2_choices"].c.kind == "harpy_bond_void",
                )
            )
            .mappings()
            .all()
        )
        if value.phase == "rewrite" and not any(
            json.loads(x["body_json"]).get("work_id") == value.id for x in rows
        ):
            game.request(c, action, value.controller, "harpy_bond_void", dict(work_id=value.id))
    if held:
        game.save_action(c, action, state="awaiting_choices")
    return held


def work(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "harpy_bond_void":
        raise WorkflowError("Recover this actual Harpy Bond's required Void work")
    return dict(row)


def finish_work(game: GameService, c: Connection, identity: str, event: str) -> None:
    row = work(game, c, identity)
    if row["state"] == "pending":
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **(
                    row
                    | dict(
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=event,
                    )
                )
            )
        )


def synchronize(
    game: GameService, c: Connection, state: GameState, event: str, metadata: dict[str, Any]
) -> None:
    """After the real event exists, expose the source and any actual threshold work."""
    table = t.m3["m3_required_work"]
    for value in rules.cases(state):
        if value.source_event == event:
            source(game, c, state, value.id)
            if not c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == value.id,
                )
            ):
                context = dict(campaign_id=game.store.campaign_id, campaign_context=True)
                if value.source_action is not None:
                    action = game.action(c, value.source_action)
                    context = dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"])
                related(
                    c,
                    game.store,
                    context,
                    value.id,
                    value.controller,
                    value.controller,
                    "harpy_bond_void",
                    dict(
                        owner=value.actor.model_dump(mode="json"),
                        source_action=value.source_action,
                        source_pdf=180,
                        reason="harpy_bond_void",
                        change=value.change,
                    ),
                    event,
                )
        if value.gain_event == event:
            parent = work(game, c, value.id)
            for identity in value.thresholds:
                if c.scalar(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == game.store.campaign_id,
                        table.c.id == identity,
                    )
                ):
                    continue
                kind = identity.rsplit(":", 1)[-1]
                related(
                    c,
                    game.store,
                    parent,
                    identity,
                    value.controller,
                    value.controller,
                    "void_threshold",
                    dict(
                        owner=value.actor.model_dump(mode="json"),
                        character=value.actor.incarnation,
                        source_action=value.source_action,
                        source_pdf=19,
                        reason="harpy_bond_void",
                        temptation=value.id,
                        details=dict(family="girl" if kind == "girl_void_threshold" else "frame"),
                    ),
                    event,
                )
            if value.phase == "complete":
                finish_work(game, c, value.id, event)


def _alter(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Temptation,
    event: str,
    account: str,
    asset: str | None,
    storage: bool,
    growth_fields: dict[str, str],
    casualty_part: str | None,
    casualty_account: str,
) -> None:
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_janus_storage import alter
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_janus_storage import gain_source
    from girlframe.services.m3_sup import parse

    require_rule(game, value.actor)
    current(game, c, state, value)
    if value.phase != "rewrite" or not account.strip() or len(account) > 1200:
        raise WorkflowError("Resume the original owned Void onset with its actual alteration")
    if value.actor.kind != "pilot":
        raise WorkflowError(
            "PENDING_ACTUAL_RESOURCES: this actual Girl-rule role requires its own Void "
            "resource port; no controller sheet is substituted"
        )
    growth = parse(game, c, state, value.actor, growth_fields)
    if asset is None and growth is None or growth and (asset is not None or storage):
        raise WorkflowError("Choose one actual uncorrupted Asset, or this owner's paid Sup growth")
    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.piloting is None:
        raise WorkflowError("Review the actual Girl/Frame mode in /mission position first")
    gain = gain_source(game, c, state, value.actor, value.id, "harpy_bond_void", storage)
    if casualty_part is not None:
        if growth or storage or asset is None:
            raise WorkflowError("Resist the actual body onset instead of Storage or growth")
        from girlframe.services.m3_casualty import stage_work_resistance
        from girlframe.services.m3_casualty_support import require_god

        require_god(game)
        stage_work_resistance(
            game,
            c,
            state,
            actor=value.actor,
            asset=asset,
            work=value.id,
            event=event,
            part=casualty_part.removeprefix("part:"),
            account=casualty_account,
            source_kind="harpy_bond_void",
        )
    elif casualty_account:
        raise WorkflowError("Select the real infected body part for this resistance account")
    changed, followups = alter(
        state,
        value.actor,
        asset or "",
        account.strip(),
        value.id,
        event,
        piloting=actual.piloting,
        source=gain,
        growth=growth,
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    if growth:
        from girlframe.engine.m3_sup import growths

        asset = next(x.asset for x in growths(state) if x.actor == value.actor and x.event == event)
    thresholds = tuple(value.id + ":void:" + x.kind for x in followups)
    rules.put(
        state,
        value.model_copy(
            update=dict(
                phase="threshold" if thresholds else "complete",
                asset=asset,
                description=account.strip(),
                storage=storage,
                gain_event=event,
                thresholds=thresholds,
                ended_event=None if thresholds else event,
            )
        ),
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = source(game, c, state, json.loads(request["body_json"])["work_id"])
    if (
        request["kind"] != "harpy_bond_void"
        or request["actor_id"] != str(value.controller)
        or value.source_action != action["id"]
    ):
        raise WorkflowError("Only the actual affected Girl owns this original source choice")
    if (
        answer.denied
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only this original onset's owned Asset and alteration fields")
    allowed = {
        "description",
        "casualty_part",
        "casualty_site_account",
        "sup_name",
        "sup_family",
        "sup_replace",
    }
    if set(answer.fields) - allowed:
        raise WorkflowError("Use only the actual original Void alteration fields")
    selected = tuple(x for x in answer.options if x != "storage")
    if len(selected) > 1:
        raise WorkflowError("Choose exactly one owned uncorrupted Asset")
    _alter(
        game,
        c,
        state,
        value,
        action["data"]["response_event"],
        answer.fields.get("description", answer.text),
        selected[0] if selected else None,
        "storage" in answer.options,
        {k: v for k, v in answer.fields.items() if k.startswith("sup_")},
        answer.fields.get("casualty_part") or None,
        answer.fields.get("casualty_site_account", ""),
    )


class HarpyBondVoidService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if viewer.user_id != value.controller:
                raise WorkflowError(
                    "Only this actual affected Girl may read its private Void choice"
                )
            if value.phase == "rewrite":
                current(self.game, c, state, value)
            assets, storage, sup, casualty_parts = [], False, None, []
            representable = value.actor.kind == "pilot"
            if value.phase == "rewrite" and representable:
                from girlframe.engine.m3_janus_storage import effective_assets
                from girlframe.services.m3_casualty_support import part_choices
                from girlframe.services.m3_janus_storage import available
                from girlframe.services.m3_sup import offer

                assets = [
                    dict(id=x.id, label=x.name, family=x.family)
                    for x in effective_assets(state, value.actor)
                    if not x.void
                ]
                storage = available(self.game, c, state, value.actor)
                sup = offer(self.game, c, state, value.actor)
                casualty_parts = part_choices(self.game, c, state, value.actor)
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                actor=value.actor.model_dump(mode="json"),
                source_action=value.source_action,
                source_pdf=180,
                assets=assets,
                storage=storage,
                sup=sup,
                casualty_parts=casualty_parts,
                thresholds=value.thresholds,
                blocked=(
                    "PENDING_ACTUAL_RESOURCES"
                    if not representable
                    else "PENDING_UNCORRUPTED_ASSET"
                    if value.phase == "rewrite" and not assets and sup is None
                    else None
                ),
                asset=value.asset,
                description=value.description,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        account: str,
        asset: str | None = None,
        storage: bool = False,
        growth_fields: dict[str, str] | None = None,
        *,
        casualty_part: str | None = None,
        casualty_site_account: str = "",
    ) -> dict[str, Any]:
        """Non-Play Bond producers retain the same durable owned consequence."""

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            value = source(self.game, c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id != value.controller:
                raise WorkflowError("Only the actual affected Girl chooses the Void alteration")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if value.source_action is not None:
                raise WorkflowError("Use the original Play's saved owned Void choice")
            if state.revision != expected:
                raise WorkflowError("STALE_HARPY_BOND_VOID: reopen the original owned onset")
            event = str(uuid4())
            _alter(
                self.game,
                c,
                state,
                value,
                event,
                account,
                asset,
                storage,
                growth_fields or {},
                casualty_part,
                casualty_site_account,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_bond_void_changed",
                state,
                event_id=event,
                temptation=identity,
            )
            return dict(id=identity, phase=rules.get(state, identity).phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_bond_void_changed",
                dict(
                    id=identity,
                    expected=expected,
                    account=account,
                    asset=asset,
                    storage=storage,
                    growth_fields=growth_fields,
                    casualty_part=casualty_part,
                    casualty_site_account=casualty_site_account,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def prove_gain(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Temptation:
    value = source(game, c, state, identity)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.gain_event,
            )
        )
        .mappings()
        .first()
    )
    if (
        value.gain_event is None
        or value.asset is None
        or not value.description
        or event is None
        or event["actor_id"] != str(value.controller)
    ):
        raise WorkflowError("Recover this actual Girl's single source-owned Void gain")
    payload = json.loads(event["payload_json"])
    if value.source_action is None:
        valid = (
            event["kind"] == "m3.harpy_bond_void_changed" and payload.get("temptation") == identity
        )
    else:
        choices = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.action_id == value.source_action,
                    t.m2["m2_choices"].c.actor_id == str(value.controller),
                    t.m2["m2_choices"].c.kind == "harpy_bond_void",
                    t.m2["m2_choices"].c.state == "answered",
                )
            )
            .mappings()
            .all()
        )
        valid = (
            event["kind"] in {"m2.choice_resolved", "m3.choice_resolved", "m3.harpy_defeat_choice"}
            and payload.get("action_id") == value.source_action
            and any(
                x["id"] == payload.get("choice_id")
                and json.loads(x["body_json"]).get("work_id") == identity
                for x in choices
            )
        )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.gain_event,
        )
    )
    saved = rules.get(GameState.model_validate_json(raw), identity) if raw else None
    if (
        not valid
        or saved is None
        or any(
            getattr(saved, k) != getattr(value, k)
            for k in ("gain_event", "asset", "description", "storage", "thresholds")
        )
    ):
        raise WorkflowError(
            "Recover the real owned response and its unchanged original Bond source"
        )
    return value


def prove_void_source(
    game: GameService, c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    if raw is None:
        raise WorkflowError("Recover the original Harpy Bond Void gain history")
    value = prove_gain(game, c, GameState.model_validate_json(raw), body.get("temptation", ""))
    if (
        actor != value.actor
        or first["id"] not in value.thresholds
        or first["event_id"] != value.gain_event
        or body.get("source_action") != value.source_action
    ):
        raise WorkflowError("Recover this exact original Harpy Bond's Void threshold")


def complete_void(
    game: GameService, c: Connection, work_id: str, event: str, viewer: GuildViewer | None, key: str
) -> None:
    table = t.m3["m3_required_work"]
    body = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == work_id,
            table.c.revision == 1,
        )
    )
    if body is None:
        raise WorkflowError("Recover the original Harpy Bond Void continuation")
    identity = json.loads(body).get("temptation", "")
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, identity)
    if value.phase == "complete":
        return
    if value.phase != "threshold" or work_id not in value.thresholds:
        raise WorkflowError("Resume this exact original source-owned Void threshold")
    for required in value.thresholds:
        status = c.scalar(
            sa.select(table.c.state)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == required,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        if status != "resolved":
            return
    rules.put(state, value.model_copy(update=dict(phase="complete", ended_event=event)))
    prior_index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    from girlframe.services.m3_janus_storage import continuation_actor

    completed = game.event(
        c,
        continuation_actor(game, c, event, viewer),
        key,
        "m3.harpy_bond_void_completed",
        state,
        temptation=identity,
        event_index=1 if prior_index is None else prior_index + 1,
    )
    finish_work(game, c, identity, completed)
    if value.source_action is not None:
        action = game.action(c, value.source_action)
        if not game.pending(c, action["id"]):
            if action["data"].get("harpy_defeat"):
                from girlframe.services.m3_harpy_defeat import resume_void_source

                resume_void_source(game, c, action["id"], completed, viewer, key)
                return
            if action["data"].get("actor_basic"):
                from girlframe.services.m3_actor_plays import ActorPlayService

                ActorPlayService(game).finish(c, state, action)
            else:
                from girlframe.services.m2_choices import ChoiceEngine

                ChoiceEngine(game).finish(c, state, action)
            game.save_action(c, action)
