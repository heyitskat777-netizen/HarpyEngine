"""Actual Casualty body costs, repair, original sources and independently owned Sex effects."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_intracadre_marriage import debit
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment, prove_flow
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

SEX_KINDS = (
    "casualty_present",
    "casualty_focus",
    "casualty_unmark",
    "casualty_mutual_tag",
    "casualty_high_heat",
    "casualty_high_asset",
    "casualty_high_part",
    "casualty_unsatisfied",
    "casualty_agree",
    "casualty_low_tag",
    "casualty_low_both",
)


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _source_event(game: GameService, c: Connection, event: str) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the genuine original Casualty source event")
    return dict(row)


def _before(game: GameService, c: Connection, event: str) -> GameState:
    actual = _source_event(game, c, event)
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.seq < actual["seq"])
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover the actual original state before this body effect")
    return GameState.model_validate_json(body)


def _ensure(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, event: str
) -> rules.Body:
    actual = _native(game, c, state, actor)
    value = rules.body(state, actor)
    if value is not None:
        if value.vessel != actual.vessel_id:
            raise WorkflowError(
                "SOURCE_BODY_ADAPTER_REQUIRED: preserve the actual original ideal parts"
            )
        return value
    sheet = state.sheets[actor.entity]
    if sheet.girl != "CASUALTY" or actual.vessel_id is None:
        raise WorkflowError("Establish this actual native Casualty's original physical body first")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    source: str | None
    if setup and setup.book == "CASUALTY":
        source = setup.source_event
        initial = tuple(
            rules.Part.model_validate(
                dict(
                    id=part,
                    condition="broken"
                    if any(x.name == rules.LABELS[part] and x.damaged for x in setup.body_parts)
                    else "intact",
                )
            )
            for part in rules.PARTS
        )
    else:
        source = c.scalar(
            sa.select(t.events.c.id)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.character_activated",
                t.events.c.actor_id == actor.entity,
            )
            .order_by(t.events.c.seq)
            .limit(1)
        )
        if source is None:
            raise WorkflowError("Recover the genuine original Casualty activation")
        original = _history(c, game, source).sheets.get(actor.entity)
        if (
            original is None
            or original.character_id != actor.incarnation
            or original.girl != "CASUALTY"
        ):
            raise WorkflowError(
                "Use the source-owned original Casualty, never a replacement profile"
            )
        initial = tuple(rules.Part.model_validate(dict(id=x)) for x in rules.PARTS)
    value = rules.Body(
        actor=actor,
        vessel=actual.vessel_id,
        parts=initial,
        initial_parts=initial,
        setup_source=source,
        event=event,
    )
    rules.put(state, value)
    return value


def _resistance_work(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    work: str,
    source_kind: str,
    before_event: dict[str, Any] | None,
) -> None:
    """Prove the real producer and its pending revision before the actual onset."""
    table = t.m3["m3_required_work"]
    query = sa.select(table).where(
        table.c.campaign_id == game.store.campaign_id, table.c.id == work
    )
    if before_event is not None:
        query = query.join(t.events, t.events.c.id == table.c.event_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < before_event["seq"],
        )
    row = c.execute(query.order_by(table.c.revision.desc()).limit(1)).mappings().first()
    if row is None or row["state"] != "pending":
        raise WorkflowError("Use the actual original still-pending required Void source")
    if source_kind == "dormant":
        from girlframe.services.m3_battle_dormant import DormantService, actual_actor

        _, _, original = DormantService(game.store, game)._source(c, work)
        body = json.loads(row["body_json"])
        if (
            row["kind"] != "dormant_void"
            or original != actor
            or actual_actor(game, c, state, original) != actor
            or row["subject_id"] != actor.entity
            or body.get("phase", "void") != "void"
            or body.get("corruption_event") is not None
            or any(
                x.get("kind") == "dormant_void_paid" and x.get("work") == work for x in state.facts
            )
        ):
            raise WorkflowError("Use the actual affected original Dormant victim's pending onset")
    elif source_kind == "budget_cleanup":
        from girlframe.services.m3_budget_cleanup import current, source

        value = source(game, c, state, work)
        current(game, c, state, value)
        if (
            row["kind"] != "budget_cleanup"
            or value.mode != "exposure"
            or value.phase != "rewrite"
            or value.selected is None
            or value.people[value.selected] != actor
            or value.gain_event is not None
        ):
            raise WorkflowError("Use the actual selected original cleanup Girl's pending onset")
    else:
        raise WorkflowError("Use a supported real required-work Void producer")


def _prove_work_resistance(
    game: GameService,
    c: Connection,
    state: GameState,
    original: GameState,
    item: rules.PartChange,
    event: dict[str, Any],
) -> None:
    value = next(
        (x for x in rules.records(original, rules.Resistance) if x.change == item.id), None
    )
    if value is None or value not in rules.records(state, rules.Resistance):
        raise WorkflowError("Recover the actual immutable required-work resistance receipt")
    prior = _before(game, c, item.event)
    payload = json.loads(event["payload_json"])
    expected = (
        event["kind"] == "m3.dormant_void_taken" and payload.get("work_id") == value.work
        if value.source_kind == "dormant"
        else event["kind"] == "m3.budget_cleanup_changed"
        and payload.get("cleanup") == value.work
        and payload.get("action") == "rewrite"
    )
    sheet = prior.sheets.get(item.actor.entity)
    asset = next((x for x in sheet.assets if x.id == value.asset), None) if sheet else None
    actual = resolve(
        prior, item.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        not expected
        or value.work is None
        or value.action is not None
        or value.choice is not None
        or not value.consumed
        or value.actor != item.actor
        or value.vessel != item.vessel
        or value.event != item.event
        or value.part != item.part
        or value.step != item.step
        or value.account != item.account
        or item.source_work != value.work
        or item.source_action is not None
        or item.source_choice is not None
        or item.inflictor != item.actor
        or item.before != "intact"
        or item.after != "broken"
        or event["actor_id"] != item.actor.entity
        or actual.vessel_id != value.vessel
        or sheet is None
        or sheet.character_id != item.actor.incarnation
        or not has_rule(sheet, rules.GOD, "CASUALTY")
        or asset is None
        or asset.family != "girl"
        or asset.void
        or asset.name != value.asset_name
    ):
        raise WorkflowError("Recover the real owned work onset, original body and infected site")
    _resistance_work(game, c, prior, item.actor, value.work, value.source_kind, event)


def prove_parts(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> rules.Body:
    value = rules.body(state, actor)
    if value is None:
        raise WorkflowError("Establish the actual original Casualty body source")
    born = rules.body(_history(c, game, value.event), actor)
    if born is None or any(
        getattr(value, k) != getattr(born, k)
        for k in ("actor", "vessel", "initial_parts", "setup_source", "event")
    ):
        raise WorkflowError("Preserve original ideal parts and immutable body provenance")
    source = _history(c, game, value.setup_source).sheets.get(actor.entity)
    if (
        source is None
        or source.character_id != actor.incarnation
        or not has_rule(source, rules.GOD, "CASUALTY")
    ):
        raise WorkflowError("Recover the original printed Casualty body source")
    expected = {x.id: x.condition for x in value.initial_parts}
    if set(expected) != set(rules.PARTS) or len(expected) != 9:
        raise WorkflowError("Preserve exactly the nine original printed parts")
    changes = [x for x in rules.records(state, rules.PartChange) if x.actor == actor]
    for item in changes:
        original = _history(c, game, item.event)
        if (
            item not in rules.records(original, rules.PartChange)
            or item.vessel != value.vessel
            or item.part not in expected
            or item.before != expected[item.part]
        ):
            raise WorkflowError("Recover each actual source-bound part transition in order")
        actual_event = _source_event(game, c, item.event)
        if item.reason == "resist_void" and item.source_work is not None:
            _prove_work_resistance(game, c, state, original, item, actual_event)
        elif item.reason in ("push_roll", "resist_void", "sex"):
            if not item.source_action or not item.source_choice:
                raise WorkflowError("Use the actual rolled source choice for this part cost")
            choice = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == item.source_choice,
                    )
                )
                .mappings()
                .first()
            )
            if choice is None or choice["action_id"] != item.source_action:
                raise WorkflowError("Recover the exact source Play and original body-part chooser")
            answer = _response(
                game,
                c,
                item.source_action,
                item.source_choice,
                item.event,
                int(item.inflictor.entity),
                choice["kind"],
            )
            if item.reason == "push_roll" and (
                choice["kind"] != "casualty_roll_push" or answer.options != (item.part,)
            ):
                raise WorkflowError("Recover the actual owned roll-push cost")
            if item.reason == "resist_void" and (
                answer.fields.get("casualty_part") != item.part
                or answer.fields.get("casualty_site_account", "").strip() != item.account
            ):
                raise WorkflowError("Recover the actual native onset's infected-part attribution")
            if item.reason == "sex" and (
                choice["kind"] != "casualty_high_part" or answer.options != (item.part,)
            ):
                raise WorkflowError("Recover the actual counterpart's body-part damage choice")
        elif item.reason == "repair":
            repair = next(
                (x for x in rules.records(original, rules.Repair) if x.change == item.id), None
            )
            if repair is None or actual_event["kind"] != "m3.casualty_part_repaired":
                raise WorkflowError("Recover the actual source-priced part repair receipt")
            prove_flow(
                game, c, _before(game, c, item.event), original, actor, item.event, repair.id, 1
            )
        elif item.reason == "helpless":
            _audit(game, c, item.event, ("m3.casualty_push_helpless",), int(actor.entity))
            if not any(x.change == item.id for x in rules.records(original, rules.Helpless)):
                raise WorkflowError("Recover the genuine unqualified Helpless source cost")
        elif item.reason in ("punishment", "source_destroy"):
            if item.inflictor.kind != "handler":
                raise WorkflowError("Use the actual source Handler's performed body damage")
            direct = next(
                (x for x in rules.records(original, rules.Damage) if x.change == item.id), None
            )
            if direct is not None:
                from girlframe.engine.m3_handler_consequences import active_handler

                prior = _before(game, c, item.event)
                if (
                    direct.actor != actor
                    or direct.inflictor != item.inflictor
                    or direct.inflictor != active_handler(prior)
                    or direct.part != item.part
                    or direct.condition != item.after
                    or direct.vessel != item.vessel
                    or direct.account != item.account
                    or item.source_work is not None
                    or actual_event["kind"] != "m3.casualty_part_damaged"
                    or actual_event["actor_id"] != item.inflictor.entity
                ):
                    raise WorkflowError(
                        "Recover the original Handler's actual performed body damage"
                    )
                expected[item.part] = item.after
                continue
            if item.source_work is None:
                raise WorkflowError("Queued discipline needs its actual original source work")
            table = t.m3["m3_required_work"]
            work = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == game.store.campaign_id,
                        table.c.id == item.source_work,
                        table.c.event_id == item.event,
                    )
                )
                .mappings()
                .first()
            )
            if work is None or work["kind"] != "punishment" or work["subject_id"] != actor.entity:
                raise WorkflowError("Recover the actual original source discipline effect")
        expected[item.part] = item.after
    if {x.id: x.condition for x in value.parts} != expected:
        raise WorkflowError("Do not reset or relabel actual broken/destroyed original hardware")
    return value


def repair_price(
    game: GameService, c: Connection, state: GameState, beneficiary: ActorRef, part: str
) -> int:
    body = prove_parts(game, c, state, beneficiary)
    _native(game, c, state, beneficiary)
    if not has_rule(state.sheets[beneficiary.entity], rules.GOD, "CASUALTY"):
        raise WorkflowError("Only the actual current Wounded God source grants this repair price")
    if not any(x.id == part and x.condition == "broken" for x in body.parts):
        raise WorkflowError("Only a genuine broken original part costs1 Permission to repair")
    return 1


def stage_part_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    part: str,
    *,
    event: str,
    inflictor: ActorRef,
    source_work: str,
    account: str,
    condition: rules.Condition = "broken",
) -> rules.PartChange:
    if inflictor.kind != "handler" or condition not in ("broken", "destroyed", "removed"):
        raise WorkflowError("Use the actual Handler's source-bound performed part discipline")
    _ensure(game, c, state, actor, event)
    return rules.change_part(
        state,
        actor,
        part,
        condition,
        event=event,
        reason="punishment" if condition == "broken" else "source_destroy",
        inflictor=inflictor,
        work=source_work,
        account=account,
    )


def stage_resistance(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    *,
    actor: ActorRef,
    asset: str,
    step: int,
    part: str,
    account: str,
    source_kind: str,
) -> None:
    _ensure(game, c, state, actor, action["data"]["response_event"])
    actual = _native(game, c, state, actor)
    entry = next(
        (x for x in actual.assets if x.id == asset and x.family == "girl" and not x.void), None
    )
    if (
        entry is None
        or row["action_id"] != action["id"]
        or row["actor_id"] != str(actual.controller)
        or not has_rule(state.sheets[actor.entity], rules.GOD, "CASUALTY")
        or not account.strip()
        or len(account) > 1200
    ):
        raise WorkflowError(
            "Use your genuine pending native body-Void onset and truthful infected site"
        )
    event = action["data"]["response_event"]
    changed = rules.change_part(
        state,
        actor,
        part,
        "broken",
        event=event,
        reason="resist_void",
        inflictor=actor,
        account=account,
        action=action["id"],
        choice=row["id"],
        step=step,
    )
    value = rules.Resistance.model_validate(
        dict(
            id=changed.id,
            actor=actor,
            vessel=changed.vessel,
            asset=asset,
            asset_name=entry.name,
            action=action["id"],
            choice=row["id"],
            step=step,
            source_kind=source_kind,
            part=part,
            account=account.strip(),
            change=changed.id,
            event=event,
        )
    )
    rules.put(state, value)


def stage_work_resistance(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    actor: ActorRef,
    asset: str,
    work: str,
    event: str,
    part: str,
    account: str,
    source_kind: Literal["dormant", "budget_cleanup"],
    step: int = 0,
) -> None:
    """Stage an owned real work onset, without inventing a Play or response row."""
    if not event or c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ):
        raise WorkflowError("Resist only the actual pending onset before its canonical event")
    prior = load_state(c, game.store.campaign_id)
    _resistance_work(game, c, prior, actor, work, source_kind, None)
    actual = _native(game, c, state, actor)
    entry = next(
        (x for x in actual.assets if x.id == asset and x.family == "girl" and not x.void), None
    )
    prior_sheet = prior.sheets.get(actor.entity)
    prior_asset = (
        next((x for x in prior_sheet.assets if x.id == asset), None) if prior_sheet else None
    )
    if (
        entry is None
        or prior_sheet is None
        or prior_sheet.character_id != actor.incarnation
        or not has_rule(prior_sheet, rules.GOD, "CASUALTY")
        or prior_asset is None
        or prior_asset.family != "girl"
        or prior_asset.void
        or actual.controller != int(actor.entity)
        or step != 0
        or not account.strip()
        or len(account) > 1200
    ):
        raise WorkflowError("Use your actual pending body-Asset onset and truthful infected site")
    _ensure(game, c, state, actor, event)
    changed = rules.change_part(
        state,
        actor,
        part,
        "broken",
        event=event,
        reason="resist_void",
        inflictor=actor,
        account=account,
        work=work,
        step=step,
    )
    rules.put(
        state,
        rules.Resistance(
            id=changed.id,
            actor=actor,
            vessel=changed.vessel,
            asset=asset,
            asset_name=entry.name,
            work=work,
            step=step,
            source_kind=source_kind,
            part=part,
            account=account.strip(),
            change=changed.id,
            event=event,
        ),
    )


def intercept_results(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if action["data"].get("casualty_push_offered"):
        return bool(action["data"].get("casualty_push_pending"))
    actor_id = int(action["actor_id"])
    sheet = state.sheets.get(str(actor_id))
    if sheet is None or not has_rule(sheet, rules.GOD, "CASUALTY"):
        return False
    actor = current_ref(state, actor_id)
    if action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation:
        raise WorkflowError("Use this actual original Casualty's owned unresolved roll")
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return False
    try:
        registry = Access(game.store).registry
        if (
            registry is None
            or approval.registry_sha256 != digest(registry)
            or (approval.scope == "core_complete" and registry.coverage != "RULES_COMPLETE")
        ):
            return False
        registry.require_available(rules.GOD)
    except (ValueError, WorkflowError):
        return False
    event = action["data"]["response_event"]
    value = _ensure(game, c, state, actor, event)
    action["data"]["casualty_push_offered"] = True
    if not any(x.condition == "intact" for x in value.parts):
        return False
    action["data"]["casualty_push_pending"] = True
    game.request(c, action, actor_id, "casualty_roll_push")
    return True


def _post(
    game: GameService, c: Connection, actor: ActorRef, event: str, viewer: GuildViewer, key: str
) -> None:
    from girlframe.services.m3_casualty_support import post_part_change

    post_part_change(game, c, actor, event, viewer, key)


class CasualtyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        data: dict[str, Any],
        operation: Any,
        rule: str = rules.GOD,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer, rule)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, data, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def body(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            event = str(uuid4())
            value = _ensure(self.game, c, state, actor, event)
            if value.event == event:
                self.game.event(
                    c, viewer.user_id, key, "m3.casualty_body_established", state, event_id=event
                )
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                parts=[x.model_dump() | dict(label=rules.LABELS[x.id]) for x in value.parts],
            )

        return self._write(viewer, key, "m3.casualty_body_established", {}, operation)

    def barely(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, asset: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            actual = resolve(state, actor, profiles(c, self.store.campaign_id))
            sheet = state.sheets[actor.entity]
            chosen = next((x for x in sheet.assets if x.id == asset and x.damaged), None)
            if state.revision != revision or chosen is None or not account.strip():
                raise WorkflowError("Erase a real owned Identity to undamage an actual owned Asset")
            if not actual.alive or actual.rules != "girl_frame":
                raise WorkflowError("Use your actual current living original native Girl")
            event, identity_receipt = str(uuid4()), str(uuid4())
            erased = rules.erase_identity(sheet, identity)
            chosen.damaged = False
            rules.put(
                state,
                rules.Barely(
                    id=identity_receipt,
                    actor=actor,
                    vessel=actual.vessel_id,
                    identity=erased,
                    asset=asset,
                    asset_name=chosen.name,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_barely_repaired",
                state,
                event_id=event,
                repair=identity_receipt,
            )
            return dict(id=identity_receipt, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_barely_repaired",
            dict(revision=revision, identity=identity, asset=asset, account=account),
            operation,
            rules.BARELY,
        )

    def repair_part(
        self, viewer: GuildViewer, key: str, revision: int, part: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if state.revision != revision:
                raise WorkflowError("STALE_CASUALTY: refresh the actual original body")
            price = repair_price(self.game, c, state, actor, part)
            payment = prepare_payment(self.game, c, state, viewer, actor, rules.GOD, price, part)
            event, receipt = str(uuid4()), str(uuid4())
            debit(state, actor, price, event=event, source=receipt, payment=payment)
            changed = rules.change_part(
                state,
                actor,
                part,
                "intact",
                event=event,
                reason="repair",
                inflictor=actor,
                account="Actual paid original part repair",
            )
            body = rules.body(state, actor)
            assert body is not None
            rules.put(
                state,
                rules.Repair(
                    id=receipt,
                    actor=actor,
                    vessel=body.vessel,
                    part=part,
                    change=changed.id,
                    event=event,
                    payment=payment.approval,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_part_repaired",
                state,
                event_id=event,
                repair=receipt,
            )
            _post(self.game, c, actor, event, viewer, key)
            return dict(id=receipt, revision=load_state(c, self.store.campaign_id).revision)

        return self._write(
            viewer, key, "m3.casualty_part_repaired", dict(revision=revision, part=part), operation
        )

    def request_part_payment(
        self, viewer: GuildViewer, key: str, revision: int, part: str, account: str
    ) -> dict[str, Any]:
        from girlframe.engine.m3_intracadre_marriage import marriage_for
        from girlframe.services.m3_intracadre_marriage import MarriageService

        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, rules.GOD)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            repair_price(self.game, c, state, actor, part)
            source = marriage_for(state, actor)
            if source is None or source.financial == actor:
                raise WorkflowError("Your actual purchase already decides your own wallet")
        return MarriageService(self.store, self.game).request_payment(
            viewer, key, source.id, revision, rules.GOD, part, account
        )

    def push_helpless(
        self, viewer: GuildViewer, key: str, revision: int, part: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if state.revision != revision or not account.strip() or len(account) > 1200:
                raise WorkflowError("Describe your actual push and original part cost")
            if not has_rule(state.sheets[actor.entity], rules.GOD, "CASUALTY"):
                raise WorkflowError("Only the actual current Wounded God source grants this push")
            event, identity = str(uuid4()), str(uuid4())
            body = _ensure(self.game, c, state, actor, event)
            changed = rules.change_part(
                state,
                actor,
                part,
                "broken",
                event=event,
                reason="helpless",
                inflictor=actor,
                account=account,
            )
            rules.put(
                state,
                rules.Helpless(
                    id=identity,
                    actor=actor,
                    vessel=body.vessel,
                    change=changed.id,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_push_helpless",
                state,
                event_id=event,
                helpless=identity,
            )
            _post(self.game, c, actor, event, viewer, key)
            return dict(id=identity, revision=load_state(c, self.store.campaign_id).revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_push_helpless",
            dict(revision=revision, part=part, account=account),
            operation,
        )

    def record_found(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        finder: ActorRef,
        channel: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = next(
                (
                    x
                    for x in rules.records(state, rules.Helpless)
                    if x.model_dump()["id"] == identity
                ),
                None,
            )
            if (
                source is None
                or source.recovered_event
                or state.revision != revision
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Find the actual original helpless body with a truthful encounter"
                )
            prove_parts(self.game, c, state, source.actor)
            victim, other = (
                resolve(state, x, profiles(c, self.store.campaign_id))
                for x in (source.actor, finder)
            )
            cast = _cast(self.game, c, state, channel)
            if (
                finder == source.actor
                or other.controller != viewer.user_id
                or victim.cell is None
                or victim.cell != other.cell
                or victim.vessel_id != source.vessel
                or not any(x.actor == finder and x.controller == viewer.user_id for x in cast.roles)
                or any(x.helpless == identity for x in rules.records(state, rules.Finder))
            ):
                raise WorkflowError(
                    "Only the actual original finder's human records their real encounter"
                )
            event, found = str(uuid4()), str(uuid4())
            state = change(state, source.actor, finder, 1, event)
            rules.put(
                state,
                rules.Finder(
                    id=found,
                    helpless=identity,
                    actor=source.actor,
                    finder=finder,
                    controller=viewer.user_id,
                    cast=cast,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.casualty_found", state, event_id=event, found=found
            )
            return dict(id=found, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_found",
            dict(
                id=identity,
                revision=revision,
                finder=finder.model_dump(mode="json"),
                channel=channel,
                account=account,
            ),
            operation,
        )

    def damage_part(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        part: str,
        condition: rules.Condition,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.engine.m3_handler_consequences import active_handler
            from girlframe.services.handler_setup import HandlerService

            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            inflictor = active_handler(state)
            if (
                state.revision != revision
                or inflictor != current_ref(state, viewer.user_id)
                or condition not in ("broken", "destroyed", "removed")
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original Handler records their performed body damage"
                )
            event, identity = str(uuid4()), str(uuid4())
            body = _ensure(self.game, c, state, actor, event)
            changed = rules.change_part(
                state,
                actor,
                part,
                condition,
                event=event,
                reason="punishment" if condition == "broken" else "source_destroy",
                inflictor=inflictor,
                account=account,
            )
            rules.put(
                state,
                rules.Damage(
                    id=identity,
                    actor=actor,
                    inflictor=inflictor,
                    vessel=body.vessel,
                    part=part,
                    condition=condition,
                    change=changed.id,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_part_damaged",
                state,
                event_id=event,
                damage=identity,
            )
            _post(self.game, c, actor, event, viewer, key)
            return dict(id=identity, revision=load_state(c, self.store.campaign_id).revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_part_damaged",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                part=part,
                condition=condition,
                account=account,
            ),
            operation,
        )

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        target: ActorRef,
        revision: int,
        account: str,
        *,
        bonded_source: str | None = None,
        changeling_source: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Use the real idle source and actual voluntary proposal")
            event, identity = str(uuid4()), str(uuid4())
            body = _ensure(self.game, c, state, actor, event)
            other = _native(self.game, c, state, target)
            cast = _cast(self.game, c, state, channel)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            assert self.store.policy.m3_approval is not None
            value = rules.SexSession(
                id=identity,
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                target=target,
                caster=viewer.user_id,
                counterpart=other.controller,
                cast=cast,
                actor_vessel=body.vessel,
                target_vessel=other.vessel_id or "",
                registry=self.store.policy.m3_approval.registry_sha256,
                proposed_event=event,
                proposal=account.strip(),
            )
            _contact(self.game, c, state, value)
            if not any(x.condition == "intact" for x in body.parts) or not any(
                not x.damaged for x in other.assets
            ):
                raise WorkflowError(
                    "SOURCE_SEX_CONSEQUENCE_REQUIRED: provide real high-result damage targets"
                )
            rules.put(state, value)
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(
                    self.game,
                    c,
                    state,
                    changeling_source,
                    value.id,
                    rules.SEX,
                    value.proposed_event,
                )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import bind_delegation

                bind_delegation(self.game, c, state, bonded_source, value.id, rules.SEX, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_sex_proposed",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, revision=state.revision, phase="invited")

        return self._write(
            viewer,
            key,
            "m3.casualty_sex_proposed",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                revision=revision,
                account=account,
            )
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
            operation,
            rules.SEX,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove_sex(self.game, c, state, identity)
            if (
                state.revision != revision
                or value.phase != "invited"
                or current_ref(state, viewer.user_id) != value.target
                or viewer.user_id != value.counterpart
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "The actual original counterpart gives only their own voluntary response"
                )
            _contact(self.game, c, state, value)
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        phase="accepted" if accept else "declined",
                        consent_event=event,
                        consent_account=account.strip(),
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_sex_confirmed",
                state,
                event_id=event,
                session=identity,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(
                id=identity, revision=state.revision, phase="accepted" if accept else "declined"
            )

        return self._write(
            viewer,
            key,
            "m3.casualty_sex_confirmed",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            rules.SEX,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, rules.SexSession):
            if viewer.user_id in (value.caster, value.counterpart):
                result.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        phase=value.phase,
                        label="Your actual original Casualty intimacy source",
                        pending=(
                            value.phase == "invited"
                            and viewer.user_id == value.counterpart
                            or value.phase == "accepted"
                            and viewer.user_id == value.caster
                        ),
                    )
                )
        for model in (
            rules.Barely,
            rules.Repair,
            rules.Damage,
            rules.Helpless,
            rules.Finder,
            rules.RollPush,
            rules.Resistance,
        ):
            for record in rules.records(state, model):
                actor = ActorRef.model_validate(record.model_dump()["actor"])
                allowed = {int(actor.entity)}
                if isinstance(record, rules.Damage):
                    allowed.add(int(record.inflictor.entity))
                if isinstance(record, rules.Finder):
                    allowed.add(record.controller)
                if viewer.user_id in allowed:
                    result.append(
                        dict(
                            id=record.model_dump()["id"],
                            revision=state.revision,
                            phase="recorded",
                            label="Your actual Casualty body/source history",
                            pending=False,
                        )
                    )
        return result

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            owned = state.sheets.get(str(viewer.user_id))
            try:
                actor = current_ref(state, viewer.user_id)
            except ValueError:
                return dict(
                    revision=state.revision,
                    actor=None,
                    available=False,
                    payment_needed=False,
                    parts=[],
                    identities=[],
                    assets=[],
                    sex_targets=[],
                    damage_targets=[],
                    find_targets=[],
                    history=self._tasks(c, viewer),
                )
            body = rules.body(state, actor)
            targets = []
            available = owned is not None and any(
                has_rule(owned, rule, "CASUALTY") for rule in (rules.GOD, rules.BARELY, rules.SEX)
            )
            if available:
                try:
                    cast = _cast(self.game, c, state, channel)
                    own = _native(self.game, c, state, actor)
                    for role in cast.roles:
                        if role.actor.kind != "pilot" or role.actor == actor:
                            continue
                        other = _native(self.game, c, state, role.actor)
                        if (
                            own.cell is not None
                            and own.cell == other.cell
                            and other.inside_frame is False
                        ):
                            targets.append(
                                dict(ref=role.actor.model_dump(mode="json"), label=other.label)
                            )
                except (WorkflowError, ValueError):
                    pass
            handlers = []
            from girlframe.engine.m3_handler_consequences import active_handler

            if actor == active_handler(state):
                handlers = [
                    dict(ref=current_ref(state, x.owner).model_dump(mode="json"), label=x.callsign)
                    for x in state.sheets.values()
                    if x.girl == "CASUALTY"
                ]
            from girlframe.engine.m3_intracadre_marriage import marriage_for

            marriage = marriage_for(state, actor) if actor.kind == "pilot" else None
            return dict(
                payment_needed=bool(marriage and marriage.financial != actor),
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                available=available,
                parts=[x.model_dump() | dict(label=rules.LABELS[x.id]) for x in body.parts]
                if body
                else [],
                identities=[
                    dict(id=x.id, label=x.name)
                    for x in owned.identities
                    if not x.protected
                    and not x.paired
                    and not x.am_limiter
                    and x.id not in owned.sedation_locked
                    and not x.obsession_sources
                ]
                if owned
                else [],
                assets=[dict(id=x.id, label=x.name) for x in owned.assets if x.damaged]
                if owned
                else [],
                sex_targets=targets,
                damage_targets=handlers,
                find_targets=self._find_options(c, state, viewer, channel),
                history=self._tasks(c, viewer),
            )

    def _find_options(
        self, c: Connection, state: GameState, viewer: GuildViewer, channel: int
    ) -> list[dict[str, Any]]:
        try:
            cast = _cast(self.game, c, state, channel)
        except WorkflowError:
            return []
        found = {x.helpless for x in rules.records(state, rules.Finder)}
        result = []
        for source in rules.records(state, rules.Helpless):
            if (
                source.id in found
                or source.recovered_event
                or not any(x.actor == source.actor for x in cast.roles)
            ):
                continue
            victim = resolve(state, source.actor, profiles(c, self.store.campaign_id))
            for role in cast.roles:
                if role.controller != viewer.user_id or role.actor == source.actor:
                    continue
                actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                if actual.cell is not None and actual.cell == victim.cell:
                    result.append(
                        dict(
                            id=source.id + ":" + role.actor.token,
                            source=source.id,
                            finder=role.actor.model_dump(mode="json"),
                            label=actual.label + " finds " + victim.label,
                        )
                    )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if any(x.id == identity for x in rules.records(state, rules.SexSession)):
                value = prove_sex(self.game, c, state, identity)
                if viewer.user_id not in (value.caster, value.counterpart):
                    raise WorkflowError(
                        "Only the original actual intimacy participants read this source"
                    )
                return dict(
                    id=identity,
                    kind="sex",
                    revision=state.revision,
                    phase=value.phase,
                    proposal=value.proposal,
                    actor=value.actor.model_dump(mode="json"),
                    target=value.target.model_dump(mode="json"),
                    caster=value.caster,
                    counterpart=value.counterpart,
                    channel=value.cast.channel,
                    can_confirm=value.phase == "invited" and viewer.user_id == value.counterpart,
                    can_roll=value.phase == "accepted" and viewer.user_id == value.caster,
                    outcomes=[
                        x.model_dump(mode="json")
                        for x in rules.records(state, rules.SexSelection)
                        if x.session == identity
                    ],
                )
            for model in (
                rules.Barely,
                rules.Repair,
                rules.Damage,
                rules.Helpless,
                rules.Finder,
                rules.RollPush,
                rules.Resistance,
            ):
                record: Any = next(
                    (x for x in rules.records(state, model) if x.model_dump()["id"] == identity),
                    None,
                )
                if record is None:
                    continue
                allowed = {int(record.actor.entity)}
                if isinstance(record, rules.Damage):
                    allowed.add(int(record.inflictor.entity))
                if isinstance(record, rules.Finder):
                    allowed.add(record.controller)
                if viewer.user_id not in allowed:
                    raise WorkflowError(
                        "Only the original source people read this private body history"
                    )
                source = _history(c, self.game, record.event)
                stored = next(
                    (x for x in rules.records(source, model) if x.model_dump()["id"] == identity),
                    None,
                )
                if stored != record:
                    raise WorkflowError("Preserve the original actual private Casualty record")
                if not isinstance(record, rules.Barely):
                    prove_parts(self.game, c, state, record.actor)
                return dict(
                    id=identity,
                    kind="body",
                    revision=state.revision,
                    source=model.__name__,
                    record=record.model_dump(mode="json"),
                )
            raise WorkflowError("This original Casualty source is unavailable")


def prove_override(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    raw = action["data"].get("casualty_override")
    if raw is None:
        return None
    value = rules.RollPush.model_validate_json(json.dumps(raw))
    stored = next((x for x in rules.records(state, rules.RollPush) if x.id == value.id), None)
    born = next(
        (
            x
            for x in rules.records(_history(c, game, value.event), rules.RollPush)
            if x.id == value.id
        ),
        None,
    )
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    from girlframe.engine.m3_gender_designation import man_floor

    total = action["data"]["receipt"]["pre_total"] + sum(
        x["amount"] for x in action["data"]["modifiers"]
    )
    total = max(total, man_floor(action) or total)
    if (
        stored != value
        or born != value
        or receipt is None
        or json.loads(receipt) != action["data"]["receipt"]
        or value.action != action["id"]
        or value.receipt != action["data"]["receipt"]["id"]
        or action["data"].get("character_ids", {}).get(value.actor.entity)
        != value.actor.incarnation
        or value.before != total
        or value.total != max(total, 11)
    ):
        raise WorkflowError(
            "Recover the exact actual part-paid effective11 source and original receipt"
        )
    prove_parts(game, c, state, value.actor)
    cost = next((x for x in rules.records(state, rules.PartChange) if x.id == value.change), None)
    if (
        cost is None
        or cost.reason != "push_roll"
        or cost.source_choice != value.choice
        or cost.event != value.event
    ):
        raise WorkflowError("Recover the actual original roll-push body cost")
    return value.total


def _session(state: GameState, identity: str) -> rules.SexSession:
    value = next(
        (x for x in rules.records(state, rules.SexSession) if x.model_dump()["id"] == identity),
        None,
    )
    if value is None:
        raise WorkflowError("Recover the actual original Casualty intimacy source")
    return value


def _contact(game: GameService, c: Connection, state: GameState, value: rules.SexSession) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact

    if value.changeling_source is not None and value.bonded_source is not None:
        raise WorkflowError("Keep actual psychic contact separate from Bonded delegation")
    remote = admit_contact(
        game, c, state, value.actor, value.target, rules.SEX, value.changeling_source
    )

    own, other = (_native(game, c, state, x) for x in (value.actor, value.target))
    if (
        value.actor == value.target
        or not (
            has_rule(state.sheets[value.actor.entity], rules.SEX, "CASUALTY")
            if value.bonded_source is None
            else admit_delegation(
                game, c, state, value.actor, value.target, rules.SEX, value.bonded_source
            )
        )
        or any(
            x.vessel_id is None or (not remote and (x.cell is None or x.inside_frame is not False))
            for x in (own, other)
        )
        or (not remote and own.cell != other.cell)
        or (own.vessel_id, other.vessel_id) != (value.actor_vessel, value.target_vessel)
        or (own.controller, other.controller) != (value.caster, value.counterpart)
        or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
        or not all(
            any(r.actor == ref and r.controller == person for r in value.cast.roles)
            for ref, person in ((value.actor, value.caster), (value.target, value.counterpart))
        )
    ):
        raise WorkflowError(
            "Use the actual original willing Casualty and native counterpart together"
        )


def prove_sex(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.SexSession:
    value = _session(state, identity)
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game, c, state, value.changeling_source, value.id, value.actor, value.target, rules.SEX
        )

    from girlframe.services.m3_bonded import prove_delegation

    if value.bonded_source is not None:
        prove_delegation(
            game, c, state, value.bonded_source, value.id, value.actor, value.target, rules.SEX
        )
    born = _session(_history(c, game, value.proposed_event), identity)
    if any(
        getattr(value, k) != getattr(born, k)
        for k in (
            "id",
            "actor",
            "target",
            "caster",
            "counterpart",
            "cast",
            "actor_vessel",
            "target_vessel",
            "registry",
            "proposed_event",
            "proposal",
            "bonded_source",
            "changeling_source",
        )
    ):
        raise WorkflowError("Preserve the immutable original voluntary Casualty source")
    _audit(game, c, value.proposed_event, ("m3.casualty_sex_proposed",), value.caster)
    if value.consent_event:
        confirmed = _session(_history(c, game, value.consent_event), identity)
        _audit(game, c, value.consent_event, ("m3.casualty_sex_confirmed",), value.counterpart)
        if confirmed.consent_account != value.consent_account or not value.consent_account.strip():
            raise WorkflowError("Preserve the original counterpart's actual voluntary confirmation")
    if value.action:
        actual = game.action(c, value.action)
        bound = _session(_history(c, game, value.bound_event or ""), identity)
        if (
            not value.consent_event
            or bound.action != value.action
            or bound.bound_event != value.bound_event
            or actual["data"]["play"] != rules.PLAY
            or actual["data"].get("casualty_sex", {}).get("session") != value.id
        ):
            raise WorkflowError("Recover the real source-confirmed original Sex Play")
        if value.effect_event:
            _, total = _roll_source(game, c, actual)
            from girlframe.engine.m2 import tier

            if (
                value.tier != tier(total)
                or _session(_history(c, game, value.effect_event), identity).effect_event
                != value.effect_event
            ):
                raise WorkflowError("Recover the genuine rolled Casualty Sex result")
            event = _source_event(game, c, value.effect_event)
            payload = json.loads(event["payload_json"])
            row = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == payload.get("choice_id"),
                    )
                )
                .mappings()
                .first()
            )
            if row is None or row["kind"] not in (
                "tag_window",
                "tag_resolution",
                "tag_marker_agreement",
                "gender_animal_tag",
                "casualty_roll_push",
            ):
                raise WorkflowError("Recover the actual Tag, Gender or paid-push result completion")
            _response(
                game,
                c,
                value.action,
                row["id"],
                value.effect_event,
                int(row["actor_id"]),
                row["kind"],
            )
    for selected in rules.records(state, rules.SexSelection):
        if selected.session != identity:
            continue
        if selected not in rules.records(_history(c, game, selected.event), rules.SexSelection):
            raise WorkflowError("Preserve each actual original participant's printed response")
        answer = _response(
            game,
            c,
            selected.action,
            selected.id,
            selected.event,
            selected.controller,
            selected.kind,
        )
        if (
            answer.options != selected.options
            or answer.denied != selected.identities
            or answer.text != selected.text
            or answer.number != selected.number
            or answer.fields != selected.fields
            or selected.actor not in (value.actor, value.target)
            or selected.controller
            != (value.caster if selected.actor == value.actor else value.counterpart)
        ):
            raise WorkflowError("Preserve the exact actual source person's own choice")
    if value.completed_event:
        if _session(_history(c, game, value.completed_event), identity) != value:
            raise WorkflowError("Recover the real completed intimacy source and mandatory effects")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer, rules.SEX)
    value = prove_sex(game, c, state, prepared.source_work or "")
    if (
        value.phase != "accepted"
        or value.caster != viewer.user_id
        or prepared.target is not None
        or prepared.target_actor != value.target
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or channel != value.cast.channel
    ):
        raise WorkflowError("Use this actual original voluntarily confirmed Sex source")
    _contact(game, c, state, value)
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover this actual scene's original Handler")
    if value.cast.facilitator is None:
        raise WorkflowError("Recover the genuine source facilitator before preparing this Play")
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            target=value.target.model_dump(mode="json"),
            caster=value.caster,
            counterpart=value.counterpart,
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            handler=handler.model_dump(mode="json"),
            handler_controller=value.cast.facilitator,
            table=sorted({x.controller for x in value.cast.roles} | {value.cast.facilitator}),
        )
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = _session(state, action["data"]["casualty_sex"]["session"])
    if not event or value.action:
        raise WorkflowError("Bind only the genuine original actual Sex source once")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="bound"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer, rules.SEX)
    if viewer.user_id not in action["data"]["casualty_sex"]["table"]:
        raise WorkflowError("Only original actual source participants own responses")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove_sex(game, c, state, action["data"]["casualty_sex"]["session"])
    if value.phase != "bound" or value.actor != current_ref(state, viewer.user_id):
        raise WorkflowError("Resume the real source without duplicate Heat or dice")
    _contact(game, c, state, value)


def sex_parties(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    value = _session(state, action["data"]["casualty_sex"]["session"])
    return value.actor, value.target


def _request(
    game: GameService, c: Connection, action: dict[str, Any], owner: int, kind: str, **body: Any
) -> None:
    game.request(c, action, owner, kind, body)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = _session(state, action["data"]["casualty_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume genuine saved Casualty outcomes, never reroll")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    level = action["data"]["result"]["tier"]
    value = value.model_copy(
        update=dict(tier=level, effect_event=action["data"]["response_event"], phase="results")
    )
    rules.put(state, value)
    if level == "mid":
        _request(game, c, action, value.caster, "casualty_present")
    elif level == "high":
        for human in (value.caster, value.counterpart):
            _request(game, c, action, human, "casualty_high_heat")
        _request(game, c, action, value.caster, "casualty_high_asset")
        _request(game, c, action, value.counterpart, "casualty_high_part")
    else:
        _request(game, c, action, value.caster, "casualty_unsatisfied")


def _pending_damage(
    game: GameService, c: Connection, state: GameState, value: rules.SexSession
) -> bool:

    # Existing actual work keys/scope remain canonical; only this source's real work is queried.
    table = t.m3["m3_required_work"]
    rows = {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id)
            .order_by(table.c.revision)
        ).mappings()
    }
    roots = {
        w for x in rules.records(state, rules.SexSelection) if x.session == value.id for w in x.work
    }
    if any(w not in rows or rows[w]["state"] != "resolved" for w in roots):
        return True
    return any(
        x["state"] != "resolved"
        and json.loads(x["body_json"]).get("immediate")
        and json.loads(x["body_json"]).get("source_action") == value.action
        for x in rows.values()
    )


def _finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if game.pending(c, action["id"]):
        return
    value = _session(state, action["data"]["casualty_sex"]["session"])
    if value.phase == "complete":
        return
    if _pending_damage(game, c, state, value):
        rules.put(state, value.model_copy(update=dict(phase="damage")))
        return
    if value.tier == "high":
        _copy(state, change(state, value.actor, value.target, 1, event))
    rules.put(state, value.model_copy(update=dict(phase="complete", completed_event=event)))
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] == "casualty_roll_push":
        actor = current_ref(state, int(action["actor_id"]))
        if (
            row["actor_id"] != actor.entity
            or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
            or not action["data"].get("casualty_push_pending")
            or answer.denied
            or answer.fields
            or answer.number is not None
            or answer.flag is not None
            or answer.member is not None
            or len(answer.options) != 1
        ):
            raise WorkflowError("Only the actual original roll owner selects this source part cost")
        action["data"]["casualty_push_pending"] = False
        if answer.options == ("skip",):
            if answer.text:
                raise WorkflowError("Declining does not invent a performed push")
        else:
            event = action["data"]["response_event"]
            _ensure(game, c, state, actor, event)
            push_change = rules.change_part(
                state,
                actor,
                answer.options[0],
                "broken",
                event=event,
                reason="push_roll",
                inflictor=actor,
                account=answer.text,
                action=action["id"],
                choice=row["id"],
            )
            before = action["data"]["result"]["total"]
            receipt = action["data"]["receipt"]["id"]
            push_value = rules.RollPush(
                id=push_change.id,
                actor=actor,
                action=action["id"],
                choice=row["id"],
                receipt=receipt,
                before=before,
                total=max(before, 11),
                change=push_change.id,
                event=event,
            )
            rules.put(state, push_value)
            action["data"]["casualty_override"] = push_value.model_dump(mode="json")
        ChoiceEngine(game).results(c, state, action)
        return True
    if row["kind"] not in SEX_KINDS:
        return False
    value = prove_sex(game, c, state, action["data"]["casualty_sex"]["session"])
    kind, event, owner = row["kind"], action["data"]["response_event"], int(row["actor_id"])
    person = value.actor if owner == value.caster else value.target
    if (
        owner not in (value.caster, value.counterpart)
        or answer.flag is not None
        or answer.member is not None
    ):
        raise WorkflowError("Use only this actual original person's owned Casualty response")
    body = rules.body(state, value.actor)
    assert body is not None
    tag, change_id = None, None
    work: tuple[str, ...] = ()
    if kind == "casualty_present":
        available = {x.id for x in body.parts if x.condition != "removed"}
        if (
            owner != value.caster
            or len(answer.options) > 3
            or not set(answer.options) <= available
            or answer.denied
            or answer.fields
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError("Actually present zero to three distinct real original parts")
        value = value.model_copy(update=dict(presented=answer.options))
        rules.put(state, value)
        if answer.options:
            _request(game, c, action, value.counterpart, "casualty_focus")
    elif kind == "casualty_focus":
        if (
            owner != value.counterpart
            or set(answer.fields) != set(value.presented)
            or not set(answer.fields.values()) <= {"focus", "hesitate"}
            or answer.options
            or answer.denied
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError("Actually focus or hesitate on each original presented part")
        for part, response in answer.fields.items():
            if response == "focus":
                for human in (value.caster, value.counterpart):
                    _request(game, c, action, human, "casualty_unmark", part=part)
        if "hesitate" in answer.fields.values():
            for human in (value.caster, value.counterpart):
                _request(game, c, action, human, "casualty_mutual_tag")
    elif kind == "casualty_unmark":
        if (
            answer.options not in (("unmark",), ("skip",))
            or answer.fields
            or answer.number is not None
            or answer.text
        ):
            raise WorkflowError("Each actual human may unmark one actual Identity per focused part")
        if answer.options == ("skip",):
            if answer.denied:
                raise WorkflowError("Skipping grants no unmark")
        else:
            if len(answer.denied) != 1:
                raise WorkflowError("Select one actually marked owned Identity")
            ChoiceEngine(game).unmark(c, state, state.sheets[person.entity], answer.denied, 1)
    elif kind == "casualty_high_heat":
        if (
            answer.number not in (3, 4)
            or answer.options
            or answer.fields
            or answer.denied
            or answer.text
        ):
            raise WorkflowError("Each original beneficiary chooses their own3–4 Heat")
        from girlframe.engine.m3_leviathan_obsession import allowed_gain

        state.sheets[person.entity].heat += allowed_gain(
            state, person, answer.number, "Casualty Sex", event
        )
        state.sheets[person.entity].revision += 1
    elif kind == "casualty_high_asset":
        if (
            owner != value.caster
            or len(answer.denied) != 1
            or answer.options
            or answer.fields
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError("Choose the counterpart's real Asset you actually damage")
        from girlframe.services.m3_battle import damage_actor

        changed, work = damage_actor(
            game,
            c,
            state,
            target=value.target,
            asset_id=answer.denied[0],
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=value.actor,
            opponent=value.actor,
            chooser_controller=owner,
            occurrence="casualty_sex",
            physical_blow=True,
        )
        _copy(state, changed)
    elif kind == "casualty_high_part":
        if (
            owner != value.counterpart
            or len(answer.options) != 1
            or answer.denied
            or answer.fields
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError("The actual counterpart chooses the real Casualty part they break")
        change_id = rules.change_part(
            state,
            value.actor,
            answer.options[0],
            "broken",
            event=event,
            reason="sex",
            inflictor=value.target,
            account=answer.text,
            action=action["id"],
            choice=row["id"],
        ).id
    elif kind == "casualty_unsatisfied":
        if (
            owner != value.caster
            or answer.options
            or answer.denied
            or answer.fields
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError("Actually tell the counterpart they are unsatisfied")
        _request(game, c, action, value.counterpart, "casualty_agree")
    elif kind == "casualty_agree":
        if (
            owner != value.counterpart
            or answer.options not in (("agree",), ("disagree",))
            or answer.denied
            or answer.fields
            or answer.number is not None
            or not answer.text.strip()
        ):
            raise WorkflowError(
                "The actual counterpart authors their own agreement or disagreement"
            )
        _request(
            game,
            c,
            action,
            value.counterpart if answer.options == ("agree",) else value.caster,
            "casualty_low_tag" if answer.options == ("agree",) else "casualty_low_both",
        )
    else:
        options: tuple[str, ...]
        if kind == "casualty_mutual_tag":
            if answer.options:
                raise WorkflowError("The real reciprocal Tag is mandatory; no invented option")
            options = ()
        else:
            if answer.options not in (("give",), ("decline",)):
                raise WorkflowError("The original printed giver owns their optional Tag")
            options = answer.options
        if (
            answer.denied
            or answer.number is not None
            or kind != "casualty_low_both"
            and answer.fields
        ):
            raise WorkflowError("Author only the actual printed Tag labels")
        if kind == "casualty_low_tag" and owner != value.counterpart:
            raise WorkflowError("Only the actual counterpart authors this optional Tag")
        if options == ("decline",):
            if answer.text or answer.fields:
                raise WorkflowError("Declining fabricates no Tag or speech")
        elif kind == "casualty_low_both":
            if (
                owner != value.caster
                or set(answer.fields) != {"self", "other"}
                or any(not x.strip() or len(x.strip()) > 120 for x in answer.fields.values())
                or answer.text
            ):
                raise WorkflowError("The Casualty authors one actual Tag for each original person")
            for recipient, label in (
                (value.actor, answer.fields["self"]),
                (value.target, answer.fields["other"]),
            ):
                identity = str(uuid4())
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, game.store.campaign_id),
                        recipient,
                        value.actor,
                        label.strip(),
                        identity,
                        event,
                        tuple(action["data"]["participants"]),
                    ),
                )
        else:
            if not answer.text.strip() or len(answer.text.strip()) > 120:
                raise WorkflowError("Author your actual ordinary Tag")
            giver = person
            target = value.target if person == value.actor else value.actor
            tag = str(uuid4())
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    target,
                    giver,
                    answer.text.strip(),
                    tag,
                    event,
                    tuple(action["data"]["participants"]),
                ),
            )
    rules.put(
        state,
        rules.SexSelection(
            id=row["id"],
            session=value.id,
            action=action["id"],
            actor=person,
            controller=owner,
            kind=kind,
            options=answer.options,
            identities=answer.denied,
            number=answer.number,
            text=answer.text,
            fields=answer.fields,
            event=event,
            tag=tag,
            change=change_id,
            work=work,
        ),
    )
    _finish(game, c, state, action, event)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    if row["kind"] == "casualty_roll_push":
        actor = current_ref(state, int(action["actor_id"]))
        body_value = rules.body(state, actor)
        return dict(
            options=(("skip", "Keep the genuine current result"),)
            + tuple(
                (x.id, "Break " + rules.LABELS[x.id] + "; result becomes11+")
                for x in body_value.parts
                if x.condition == "intact"
            )
            if body_value
            else (),
            minimum=1,
            maximum=1,
            identities=[],
            assets=[],
            parts=[],
            label="Actual performed push (blank if skip)",
        )
    value = _session(state, action["data"]["casualty_sex"]["session"])
    kind = row["kind"]
    parts = rules.body(state, value.actor)
    person = value.actor if int(row["actor_id"]) == value.caster else value.target
    options = (
        (("focus", "Focus"), ("hesitate", "Hesitate"))
        if kind == "casualty_focus"
        else (
            (("unmark", "Unmark one real Identity"), ("skip", "Decline optional unmark"))
            if kind == "casualty_unmark"
            else (("agree", "I agree"), ("disagree", "I disagree"))
            if kind == "casualty_agree"
            else (("give", "Give actual Tag(s)"), ("decline", "Decline optional Tag(s)"))
            if kind in ("casualty_low_tag", "casualty_low_both")
            else ()
        )
    )
    return dict(
        options=options,
        minimum=0 if kind == "casualty_present" else 1,
        maximum=3 if kind == "casualty_present" else 1,
        parts=[
            dict(id=x.id, label=rules.LABELS[x.id])
            for x in parts.parts
            if x.condition != "removed"
            and (kind != "casualty_high_part" or x.condition == "intact")
        ]
        if parts and kind in ("casualty_present", "casualty_high_part")
        else [],
        presented=[dict(id=p, label=rules.LABELS[p]) for p in value.presented],
        identities=[
            dict(id=x.id, label=x.name) for x in state.sheets[person.entity].identities if x.marked
        ],
        assets=[
            dict(id=x.id, label=x.name)
            for x in state.sheets[value.target.entity].assets
            if not x.damaged
        ]
        if kind == "casualty_high_asset"
        else [],
        label="Your actual source account or authored Tag",
        heat=kind == "casualty_high_heat",
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    if not action["data"].get("casualty_sex"):
        return
    value = prove_sex(game, c, state, action["data"]["casualty_sex"]["session"])
    if value.phase != "damage" or _pending_damage(game, c, state, value):
        return
    finished = str(uuid4())
    _finish(game, c, state, action, finished)
    game.event(
        c,
        value.caster,
        "casualty-damage:" + event,
        "m3.casualty_sex_completed",
        state,
        event_id=finished,
        session=value.id,
    )

    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import synchronize_session

        synchronize_session(game, c, state, value.id, finished)
