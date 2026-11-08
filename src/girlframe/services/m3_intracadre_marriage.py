"""Original Marriage declaration, source-priced approvals and allocated discipline."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_intracadre_marriage as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services import m3_advancement_acquisition as acquisition
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the original immutable Marriage source")
    return value


def _born(game: GameService, c: Connection, value: Model, kind: str, actor: int) -> GameState:
    event = value.model_dump()["event"]
    born = _history(c, game, event)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if value not in rules.records(born, type(value)) or audit != (kind, str(actor)):
        raise WorkflowError("Recover the real original human's Marriage source event")
    return born


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = acquisition.prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the original Intracadre Marriage acquisition",
        failure="Recover the exact original Marriage Award and declaration",
    )
    born = _born(game, c, value, "m3.handler_advancement_spent", int(value.handler.entity))
    before, _ = snapshots(game, c, value.event)
    pair = (value.first, value.second)
    if (
        value.first == value.second
        or {value.financial, value.punished} != set(pair)
        or value.status_from not in pair
        or any(x.kind != "pilot" or current_ref(before, int(x.entity)) != x for x in pair)
        or any(rules.marriage_for(before, x) is not None for x in pair)
        or tuple(before.sheets[x.entity].permissions for x in pair) != value.initial_permissions
        or born.sheets[value.financial.entity].permissions != sum(value.initial_permissions)
        or born.sheets[value.punished.entity].permissions != 0
        or depth(born, *pair) != min(2, depth(before, *pair) + 1)
    ):
        raise WorkflowError("Recover the original Girls, Bond, shared Status and conserved custody")
    expected_heat = 2 if depth(before, *pair) == 2 else 0
    if any(
        born.sheets[x.entity].heat != before.sheets[x.entity].heat + expected_heat for x in pair
    ):
        raise WorkflowError("Recover the actual printed Bond-deepening Heat consequence")
    return value


def _price(state: GameState, actor: ActorRef, product: str, detail: str) -> int:
    fixed = {
        "asset_installment": 1,
        "creature_comforts": 1,
        "privacy": 1,
        "visiting_home": 2,
        "frame_swap": 4,
        "retirement": 20,
    }
    if product in fixed:
        return fixed[product]
    if product == "girl.casualty.wounded-god":
        from girlframe.engine.m3_casualty import part_state

        if part_state(state, actor, detail) != "broken":
            raise WorkflowError("Quote one actual broken Casualty part at its printed repair price")
        return 1
    if product == "vatgrown_investor":
        from girlframe.engine.m3_vatgrown_plays import Investor, records

        value = next((x for x in records(state, Investor) if x.id == detail), None)
        if (
            value is None
            or value.actor != actor
            or value.source != "added"
            or not value.quote_event
            or value.added_event
            or type(value.quote) is not int
            or value.quote <= 0
        ):
            raise WorkflowError("Use the original pending Handler quote for this actual Investor.")
        return value.quote
    if product == "extra_asset_repair":
        quote = next((x for x in state.repair_quotes if x.id == detail), None)
        if quote is None or quote.owner != actor or quote.state != "pending":
            raise WorkflowError("Use this original body's real pending Handler repair quote")
        return quote.cost
    if product == "frame.enforcer.personal-firearm":
        return 2 if state.sheets[actor.entity].frame == "THE ENFORCER" else 3
    from girlframe.engine import m3_doctor as doctor
    from girlframe.engine import m3_janus as janus

    if product in doctor.REQUISITIONS:
        if state.sheets[actor.entity].frame != doctor.BOOK:
            raise WorkflowError("Use the actual DoctorDoctor Frame source")
        return 2
    if product in janus.RULES:
        return 2 if state.sheets[actor.entity].frame in ("JANUS", "JANUS-B") else 3
    if product in grafts.CLASSES:
        return grafts.acquisition(state, actor, product, detail or None)[3]
    from girlframe.engine import m3_enforcer_requisitions as enforcer

    if product in (*enforcer.RULES, *enforcer.BASE):
        return 2 if state.sheets[actor.entity].frame == "THE ENFORCER" else 3
    raise WorkflowError("Choose an actual supported source-priced product")


def _quote_proof(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.PaymentQuote:
    value = _record(state, rules.PaymentQuote, identity)
    source = prove(game, c, state, value.marriage)
    born = _born(game, c, value, "m3.marriage_payment_requested", int(value.beneficiary.entity))
    if (
        value.beneficiary not in (source.first, source.second)
        or value.wallet != source.financial
        or value.beneficiary == value.wallet
        or value.frame != rules.frame(born, value.beneficiary)
        or value.price != _price(born, value.beneficiary, value.product, value.detail)
    ):
        raise WorkflowError("Recover the exact original source-priced Marriage payment request")
    return value


def _approval_proof(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Approval:
    value = _record(state, rules.Approval, identity)
    quote = _quote_proof(game, c, state, value.quote)
    _born(game, c, value, "m3.marriage_payment_approved", int(quote.wallet.entity))
    if value.financial != quote.wallet:
        raise WorkflowError("Recover the actual financial partner's payment decision")
    return value


def prepare_payment(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    beneficiary: ActorRef,
    product: str,
    amount: int,
    detail: str = "",
) -> rules.Payment:
    if current_ref(state, viewer.user_id) != beneficiary:
        raise WorkflowError("Only the original body human completes this actual purchase")
    source = rules.marriage_for(state, beneficiary)
    if source is not None:
        prove(game, c, state, source.id)
    payment = rules.payment_for(state, beneficiary, product, amount, detail)
    if payment.quote is not None:
        quote = _quote_proof(game, c, state, payment.quote)
        assert payment.approval is not None
        _approval_proof(game, c, state, payment.approval)
        if quote.price != amount:
            raise WorkflowError("Use the actual source-derived product price")
    return payment


def prove_flow(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    beneficiary: ActorRef,
    event: str,
    source: str,
    amount: int,
) -> rules.PermissionFlow | None:
    prior, born = snapshots(game, c, event)
    marriage = rules.marriage_for(prior, beneficiary)
    if marriage is None:
        return None
    prove(game, c, after, marriage.id)
    flows = [x for x in rules.records(born, rules.PermissionFlow) if x.event == event]
    value = next((x for x in flows if x.source == source and x.beneficiary == beneficiary), None)
    if (
        value is None
        or value.amount != amount
        or value not in rules.records(after, rules.PermissionFlow)
    ):
        raise WorkflowError("MARRIAGE_FLOW_REQUIRED: recover the actual original financial source")
    balances: dict[str, int] = {}
    for flow in flows:
        owner = flow.wallet.entity
        opening = balances.get(owner, prior.sheets[owner].permissions)
        expected_wallet = rules.wallet(prior, flow.beneficiary)
        flow_marriage = rules.marriage_for(prior, flow.beneficiary)
        if (
            flow_marriage is None
            or flow.marriage != flow_marriage.id
            or flow.wallet != expected_wallet
            or flow.before != opening
            or flow.after != opening + (flow.amount if flow.kind == "grant" else -flow.amount)
        ):
            raise WorkflowError("Recover conserved source-ordered shared Permission flows")
        if flow.kind == "purchase":
            if flow.beneficiary != flow.wallet:
                if flow.quote is None or flow.approval is None:
                    raise WorkflowError("Recover the actual financial partner's approval")
                quote = _quote_proof(game, c, prior, flow.quote)
                approved = _approval_proof(game, c, prior, flow.approval)
                if (
                    (quote.beneficiary, quote.wallet, quote.product, quote.detail, quote.price)
                    != (flow.beneficiary, flow.wallet, flow.product, flow.detail, flow.amount)
                    or approved.quote != quote.id
                    or quote.frame != rules.frame(prior, flow.beneficiary)
                    or any(x.quote == quote.id for x in rules.records(prior, rules.PermissionFlow))
                ):
                    raise WorkflowError("Recover the exact once-consumed approved product")
            audit = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            if audit != flow.beneficiary.entity:
                raise WorkflowError("Recover the original body human's actual purchase")
        balances[owner] = flow.after
    if any(born.sheets[owner].permissions != total for owner, total in balances.items()):
        raise WorkflowError("Recover the actual final shared financial balance")
    return value


def allocate_punishment(
    game: GameService,
    c: Connection,
    state: GameState,
    original: ActorRef,
    *,
    source_event: str,
    source_id: str,
    work_id: str,
) -> rules.Allocation | None:
    source = rules.marriage_for(state, original)
    if source is None:
        return None
    prove(game, c, state, source.id)
    return rules.allocate(
        state, original, source_event=source_event, source_id=source_id, work_id=work_id
    )


def prepare_punishments(
    game: GameService, c: Connection, before: GameState, state: GameState, event: str
) -> None:
    if not rules.acquisitions(before):
        return
    old = {x.id for x in before.obligations}
    for debt in state.obligations:
        if debt.id in old or debt.kind != "punishment" or debt.state != "pending":
            continue
        raw = debt.details.get("actor")
        if raw is not None:
            original = ActorRef.model_validate_json(raw)
        elif str(debt.owner) in before.sheets and debt.details.get("character_id"):
            original = current_ref(before, debt.owner)
            if original.incarnation != debt.details["character_id"]:
                raise WorkflowError("Retain the actual original offender's native character")
        elif debt.action:
            action = game.action(c, debt.action)
            actual = (action["data"].get("actor_basic") or {}).get("ref")
            if actual is None:
                actual = (action["data"].get("tag_context") or {}).get("actor")
            if actual is not None:
                original = ActorRef.model_validate(actual)
            elif str(debt.owner) in before.sheets:
                original = current_ref(before, debt.owner)
            else:
                continue
        elif str(debt.owner) in before.sheets:
            original = current_ref(before, debt.owner)
        else:
            continue
        marriage = rules.marriage_for(before, original)
        if marriage is None:
            continue
        prove(game, c, before, marriage.id)
        rules.allocate(state, original, source_event=event, source_id=debt.id, work_id=debt.id)


def original_offender(
    game: GameService,
    c: Connection,
    state: GameState,
    source_id: str,
    source_event: str,
    actual_subject: ActorRef,
) -> ActorRef:
    before, born = snapshots(game, c, source_event)
    value = next(
        (x for x in rules.records(born, rules.Allocation) if x.source_id == source_id), None
    )
    if value is None:
        if rules.marriage_for(before, actual_subject) is not None:
            raise WorkflowError("MARRIAGE_ALLOCATION_REQUIRED: retain the original offender")
        return actual_subject
    source = prove(game, c, state, value.marriage)
    if (
        value not in rules.records(state, rules.Allocation)
        or value.source_event != source_event
        or value.subject != actual_subject
        or value.original not in (source.first, source.second)
        or value.subject != source.punished
        or rules.marriage_for(before, value.original) != source
    ):
        raise WorkflowError("Recover the exact original offender and allocated Punishment subject")
    return value.original


def prove_allocation(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> rules.Allocation | None:
    work = t.m3["m3_required_work"]
    first = (
        c.execute(
            sa.select(work).where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == row["id"],
                work.c.revision == 1,
            )
        )
        .mappings()
        .first()
    )
    if first is None:
        raise WorkflowError("Recover the actual original discipline work")
    body = json.loads(first["body_json"])
    if first["kind"] != "punishment":
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == first["event_id"],
            )
        ).first()
        if audit is None:
            raise WorkflowError("Recover the actual derived discipline source event")
        metadata = json.loads(audit.payload_json)
        if first["kind"] == "punishment_consult":
            parents = body.get("work_versions", {})
            if (
                audit.kind != "m3.punishment_consult_requested"
                or metadata.get("work_id") not in parents
            ):
                raise WorkflowError("Recover the actual original consultation request")
        elif first["kind"] in (
            "punishment_paired_identity_heat",
            "punishment_helpless",
            "punishment_frame_loss",
        ):
            parent = body.get("source_work")
            if audit.kind != "m3.punishment_applied" or metadata.get("work_id") != parent:
                raise WorkflowError("Recover the actual applied Punishment's immediate followup")
            parents = {parent: None}
        else:
            raise WorkflowError("Use the actual supported derived discipline source")
        if not parents:
            raise WorkflowError("Recover this child's real original Punishment work")
        for parent_id, revision in parents.items():
            query = sa.select(work).where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == parent_id,
                work.c.kind == "punishment",
                work.c.event_id == first["event_id"],
            )
            if revision is not None:
                query = query.where(work.c.revision == revision)
            parent_row = c.execute(query.order_by(work.c.revision.desc())).mappings().first()
            if parent_row is None or any(
                parent_row[k] != first[k]
                for k in ("mission_id", "off_duty_id", "scene_id", "campaign_context")
            ):
                raise WorkflowError("Recover the real matching-context parent Punishment")
            parent_body = json.loads(parent_row["body_json"])
            if first["kind"] == "punishment_consult":
                if (
                    parent_body.get("consult_id") != first["id"]
                    or parent_row["subject_id"] != first["subject_id"]
                ):
                    raise WorkflowError("Recover the exact original consultation participants")
            elif parent_body.get("applied_event") != first["event_id"]:
                raise WorkflowError("Recover the actual applied parent effect")
            prove_allocation(game, c, state, dict(parent_row))
        return None
    original = body.get("marriage_offender")
    identity = body.get("marriage_allocation")
    if identity is None:
        before, _ = snapshots(game, c, first["event_id"])
        if not rules.acquisitions(before) or first["subject_id"] not in before.sheets:
            return None
        ref = current_ref(before, int(first["subject_id"]))
        marriage = rules.marriage_for(before, ref)
        if marriage is not None:
            old, _ = snapshots(game, c, marriage.event)
            if not any(
                x.id == body.get("obligation_id") and x.owner == int(ref.entity)
                for x in old.obligations
            ):
                raise WorkflowError("MARRIAGE_ALLOCATION_REQUIRED: retain the original subject")
        return None
    value = _record(state, rules.Allocation, identity)
    actual = original_offender(game, c, state, value.source_id, value.source_event, value.subject)
    if (
        original != actual.model_dump(mode="json")
        or row["subject_id"] != value.subject.entity
        or body.get("character") != value.subject.incarnation
    ):
        raise WorkflowError("Recover the exact allocated original-person discipline work")
    if value.work_id != row["id"]:
        if body.get("obligation_id") == value.work_id:
            before, _ = snapshots(game, c, first["event_id"])
            debt = next((x for x in before.obligations if x.id == value.work_id), None)
            if (
                debt is None
                or debt.owner != int(value.original.entity)
                or debt.action != body.get("source_action")
            ):
                raise WorkflowError("Recover the actual original discipline obligation bridge")
        elif body.get("return_source_work") == value.work_id:
            from girlframe.services.m3_debts import check_returned

            check_returned(c, game.store, row)
        else:
            raise WorkflowError("Recover the exact source-owned discipline work lineage")
    if body.get("reason") == "marriage_caught":
        prove_caught(game, c, state, value.source_id)
    return value


def _flirt_source(
    game: GameService, c: Connection, identity: str
) -> tuple[dict[str, Any], GameState, str, ActorRef, ActorRef]:
    action = game.action(c, identity)
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == identity,
            )
        )
        .mappings()
        .first()
    )
    if (
        action["state"] != "complete"
        or action["data"].get("prepared", {}).get("play") != "flirt"
        or action["data"].get("actor_basic") is not None
        or receipt is None
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
    ):
        raise WorkflowError("Use the actual completed original Girl's native Flirt receipt")
    rolled = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == str(action["actor_id"]),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == identity,
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == receipt["id"],
        )
    )
    if rolled is None:
        raise WorkflowError("Recover the genuine canonical Flirt roll source")
    born = _history(c, game, rolled)
    actor = current_ref(born, int(action["actor_id"]))
    target = current_ref(born, int(action["data"]["prepared"]["target"]))
    tagged_actor = (action["data"].get("tag_context") or {}).get("actor")
    if tagged_actor is not None and ActorRef.model_validate(tagged_actor) != actor:
        raise WorkflowError("A controlled other person cannot inherit this Girl's Marriage")
    return action, born, str(rolled), actor, target


def _witness(
    game: GameService,
    c: Connection,
    state: GameState,
    channel: int,
    observer: ActorRef,
    human: int,
    actor: ActorRef,
    target: ActorRef,
) -> SceneCast:
    cast = next((x for x in state.scene_casts if x.channel == channel and x.open), None)
    if (
        cast is None
        or observer == actor
        or not any(x.actor == observer and x.controller == human for x in cast.roles)
    ):
        raise WorkflowError("Use the actual other observer's original scene role")
    people = [
        resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
        for ref in (actor, target, observer)
    ]
    if (
        any(x.cell is None or x.offstage_source is not None for x in people)
        or len({x.cell for x in people}) != 1
    ):
        raise WorkflowError(
            "Actual source-time physical co-presence is required for this witness port"
        )
    if not {actor, target} <= {x.actor for x in cast.roles}:
        raise WorkflowError("Retain the actual performed Flirt's original scene participants")
    return cast


def prove_caught(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Caught:
    value = _record(state, rules.Caught, identity)
    source = prove(game, c, state, value.marriage)
    _, observed, event, actor, target = _flirt_source(game, c, value.action)
    human = next(x.controller for x in value.cast.roles if x.actor == value.observer)
    _born(game, c, value, "m3.marriage_flirt_caught", human)
    witness = _witness(game, c, observed, value.cast.channel, value.observer, human, actor, target)
    relation = rules.marriage_for(observed, actor)
    if (
        relation != source
        or value.observed_event != event
        or value.cast != witness
        or (value.actor, value.target) != (actor, target)
        or target in (source.first, source.second)
    ):
        raise WorkflowError(
            "Recover the actual outsider Flirt and explicit original witness discovery"
        )
    return value


class MarriageService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store = store
        self.game = game or GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def products(self, viewer: GuildViewer, marriage: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, marriage)
            actor = current_ref(state, viewer.user_id)
            if actor not in (source.first, source.second) or actor == source.financial:
                raise WorkflowError("Use existing purchases when you own the actual wallet")
            options: list[dict[str, Any]] = []
            for product in (
                "asset_installment",
                "creature_comforts",
                "privacy",
                "visiting_home",
                "retirement",
            ):
                options.append(
                    dict(
                        category="Basic purchases",
                        product=product,
                        detail="",
                        price=_price(state, actor, product, ""),
                        label=product.replace("_", " ").title(),
                    )
                )
            from girlframe.engine import m3_doctor as doctor
            from girlframe.engine import m3_enforcer_requisitions as enforcer
            from girlframe.engine import m3_janus_requisitions as janus
            from girlframe.engine.m3_personal_firearm import RULE as firearm

            catalogs: list[tuple[str, str, tuple[str, ...]]] = [
                ("Class abilities", rule, grafts.donors(rule)) for rule in grafts.CLASSES
            ]
            catalogs += [
                ("Doctor requisitions", rule, (doctor.BOOK,)) for rule in doctor.REQUISITIONS
            ]
            catalogs += [("JANUS requisitions", rule, ("JANUS",)) for rule in janus.TITLES]
            catalogs += [
                ("Enforcer requisitions", rule, ("",))
                for rule in (*enforcer.RULES, *enforcer.BASE, firearm)
            ]
            registry = Access(self.store).registry
            assert registry is not None
            for category, product, details in catalogs:
                for detail in details:
                    try:
                        registry.require_available(product)
                        price = _price(state, actor, product, detail)
                    except (ValueError, WorkflowError):
                        continue
                    options.append(
                        dict(
                            category=category,
                            product=product,
                            detail=detail,
                            price=price,
                            label=product.rsplit(".", 1)[-1].replace("-", " ").title()
                            + (" — " + detail if detail else ""),
                        )
                    )
            for quote in state.repair_quotes:
                if quote.owner == actor and quote.state == "pending":
                    options.append(
                        dict(
                            category="Basic purchases",
                            product="extra_asset_repair",
                            detail=quote.id,
                            price=quote.cost,
                            label="Existing Handler repair quote",
                        )
                    )
            from girlframe.services.m3_frame_swap import FrameSwapService

            swaps = FrameSwapService(self.game)
            for row in swaps._rows(c):
                if row["owner_id"] == str(viewer.user_id) and row["state"] == "pending":
                    plan = swaps._row(c, viewer, row["id"])
                    body = json.loads(plan["body_json"])
                    if ActorRef.model_validate(body["actor"]) == actor:
                        options.append(
                            dict(
                                category="Basic purchases",
                                product="frame_swap",
                                detail=row["id"],
                                price=4,
                                label="Prepared Frame Swap — "
                                + str(body["selection"].get("frame", "replacement Frame")),
                            )
                        )
            return options

    def witnessed_flirts(self, viewer: GuildViewer, marriage: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, marriage)
            rows = c.execute(
                sa.select(t.m2["m2_actions"]).where(
                    t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_actions"].c.state == "complete",
                )
            ).mappings()
            result = []
            for row in rows:
                try:
                    action, observed, _, actor, target = _flirt_source(self.game, c, row["id"])
                    if rules.marriage_for(observed, actor) != source or target in (
                        source.first,
                        source.second,
                    ):
                        continue
                    for cast in observed.scene_casts:
                        for role in cast.roles:
                            if role.controller != viewer.user_id:
                                continue
                            _witness(
                                self.game,
                                c,
                                observed,
                                int(action["channel_id"]),
                                role.actor,
                                viewer.user_id,
                                actor,
                                target,
                            )
                            result.append(
                                dict(
                                    id=row["id"],
                                    observer=role.actor.model_dump(mode="json"),
                                    label=observed.sheets[actor.entity].callsign
                                    + " → "
                                    + observed.sheets[target.entity].callsign,
                                )
                            )
                except (ValueError, WorkflowError):
                    continue
            return result

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result: list[dict[str, Any]] = []
        for source in rules.acquisitions(state):
            if str(viewer.user_id) not in (
                source.handler.entity,
                source.first.entity,
                source.second.entity,
            ):
                continue
            result.append(
                dict(
                    id=source.id,
                    revision=state.revision,
                    phase="established",
                    pending=False,
                    label="Marriage: roles and shared budget",
                )
            )
            for caught in rules.records(state, rules.Caught):
                if caught.marriage == source.id:
                    result.append(
                        dict(
                            id=caught.id,
                            revision=state.revision,
                            phase="established",
                            pending=False,
                            label="Witnessed outsider Flirt — saved discipline source",
                        )
                    )
            for quote in rules.records(state, rules.PaymentQuote):
                if quote.marriage != source.id or str(viewer.user_id) not in (
                    quote.beneficiary.entity,
                    quote.wallet.entity,
                ):
                    continue
                approved = any(x.quote == quote.id for x in rules.records(state, rules.Approval))
                spent = any(x.quote == quote.id for x in rules.records(state, rules.PermissionFlow))
                chooser = quote.beneficiary.entity if approved else quote.wallet.entity
                result.append(
                    dict(
                        id=quote.id,
                        revision=state.revision,
                        phase="complete" if spent else "pending",
                        pending=not spent and str(viewer.user_id) == chooser,
                        label=("Paid: " if spent else "Approved: " if approved else "Approve: ")
                        + quote.product.replace("_", " ")
                        + " ("
                        + str(quote.price)
                        + "P)",
                    )
                )
        return result

    def view(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            quote = next(
                (x for x in rules.records(state, rules.PaymentQuote) if x.id == identity), None
            )
            caught = next((x for x in rules.records(state, rules.Caught) if x.id == identity), None)
            source = next(
                (
                    x
                    for x in rules.acquisitions(state)
                    if x.id
                    == (quote.marriage if quote else caught.marriage if caught else identity)
                ),
                None,
            )
            if source is None:
                return dict(
                    revision=state.revision,
                    marriages=self._tasks(c, viewer),
                    girls=[
                        dict(
                            ref=current_ref(state, owner).model_dump(mode="json"),
                            label=state.sheets[str(owner)].callsign,
                        )
                        for owner in state.order
                        if rules.marriage_for(state, current_ref(state, owner)) is None
                    ],
                    awards=[
                        dict(id=x.id, label="Actual held Marriage advancement")
                        for x in awards.awards(state)
                        if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                    ],
                    can_declare=viewer.user_id == state.handler,
                )
            if str(viewer.user_id) not in (
                source.handler.entity,
                source.first.entity,
                source.second.entity,
            ):
                raise WorkflowError("This Marriage record belongs to its actual participants")
            prove(self.game, c, state, source.id)
            own_pair = str(viewer.user_id) in (source.first.entity, source.second.entity)
            current_pair = all(
                x.entity in state.sheets and state.sheets[x.entity].character_id == x.incarnation
                for x in (source.first, source.second)
            )
            born = _history(c, self.game, source.event)
            data: dict[str, Any] = dict(
                id=source.id,
                revision=state.revision,
                source=source.model_dump(
                    mode="json", exclude=set() if own_pair else {"initial_permissions"}
                ),
                names={
                    x.entity: born.sheets[x.entity].callsign for x in (source.first, source.second)
                },
                permissions=rules.available(state, source.financial)
                if own_pair and current_pair
                else None,
                recovery=None
                if current_pair
                else (
                    "Original ending/replacement requires explicit source recovery; "
                    "no annulment or transfer."
                ),
                label="Your Handler declared you partners"
                if str(viewer.user_id) != source.handler.entity
                else "Original Marriage declaration",
                legal_partner_sex=(
                    "In-fiction legal permission; actual humans author "
                    "voluntary responses and may pause."
                ),
                tasks=[
                    x
                    for x in self._tasks(c, viewer)
                    if x["id"] == source.id
                    or any(
                        q.id == x["id"] and q.marriage == source.id
                        for q in rules.records(state, rules.PaymentQuote)
                    )
                ],
            )
            if quote is not None:
                if str(viewer.user_id) not in (quote.beneficiary.entity, quote.wallet.entity):
                    raise WorkflowError("Only actual payment participants read this request")
                _quote_proof(self.game, c, state, quote.id)
                data["quote"] = quote.model_dump(mode="json")
            data["caught"] = [
                x.model_dump(mode="json")
                for x in rules.records(state, rules.Caught)
                if x.marriage == source.id
            ]
            return data

    def report_caught(
        self,
        viewer: GuildViewer,
        key: str,
        marriage: str,
        action: str,
        observer: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_work import related

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, marriage)
            if str(viewer.user_id) not in (
                source.handler.entity,
                source.first.entity,
                source.second.entity,
            ):
                raise WorkflowError("Use an original Marriage party's supported witness report")
            performed, observed, rolled, actor, target = _flirt_source(self.game, c, action)
            relation = rules.marriage_for(observed, actor)
            if (
                relation != source
                or target in (source.first, source.second)
                or any(
                    x.action == action and x.marriage == marriage
                    for x in rules.records(state, rules.Caught)
                )
            ):
                raise WorkflowError("Use one genuine outsider Flirt performed under this Marriage")
            cast = _witness(
                self.game,
                c,
                observed,
                int(performed["channel_id"]),
                observer,
                viewer.user_id,
                actor,
                target,
            )
            identity, event = str(uuid4()), str(uuid4())
            work = str(uuid5(NAMESPACE_URL, "marriage-caught:" + marriage + ":" + action))
            value = rules.Caught(
                id=identity,
                marriage=marriage,
                action=action,
                observer=observer,
                actor=actor,
                target=target,
                observed_event=rolled,
                cast=cast,
                event=event,
                account=account,
                work=work,
            )
            rules.put(state, value)
            allocation = allocate_punishment(
                self.game, c, state, actor, source_event=event, source_id=identity, work_id=work
            )
            assert allocation is not None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.marriage_flirt_caught",
                state,
                event_id=event,
                caught_id=identity,
                source_action=action,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, scene_id=performed["scene_id"]),
                work,
                int(source.handler.entity),
                int(allocation.subject.entity),
                "punishment",
                dict(
                    reason="marriage_caught",
                    source_pdf=155,
                    caught=identity,
                    source_action=action,
                    character=allocation.subject.incarnation,
                    **rules.allocation_fields(state, identity),
                ),
                event,
            )
            return dict(id=identity, work=work, phase="required_punishment")

        result: dict[str, Any] = self.store._write(
            viewer,
            key,
            "m3.marriage_flirt_caught",
            dict(
                marriage=marriage,
                action=action,
                observer=observer.model_dump(mode="json"),
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
        return result

    def declare(
        self,
        viewer: GuildViewer,
        key: str,
        award: str,
        revision: int,
        first: ActorRef,
        second: ActorRef,
        financial: ActorRef,
        status_from: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            held = acquisition.held(
                self.game,
                c,
                viewer,
                award,
                revision,
                account,
                failure="Reopen the actual held Marriage Award",
            )
            state, handler, appointment, paid = held
            pair = (first, second)
            if (
                first == second
                or financial not in pair
                or status_from not in pair
                or any(x.kind != "pilot" or current_ref(state, int(x.entity)) != x for x in pair)
                or any(rules.marriage_for(state, x) is not None for x in pair)
            ):
                raise WorkflowError("Declare two distinct original unmarried Girls")
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Acquisition(
                id=identity,
                award=award,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account,
                first=first,
                second=second,
                financial=financial,
                punished=second if financial == first else first,
                status_from=status_from,
                initial_permissions=(
                    state.sheets[first.entity].permissions,
                    state.sheets[second.entity].permissions,
                ),
            )
            state = change(state, first, second, 1, event)
            state.sheets[value.financial.entity].permissions = sum(value.initial_permissions)
            state.sheets[value.punished.entity].permissions = 0
            for actor in pair:
                state.sheets[actor.entity].revision += 1
            rules.put(state, value)
            acquisition.record_spend(state, paid, value, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award,
                acquisition_id=identity,
                rule_id=rules.RULE,
            )
            return dict(id=identity, phase="established")

        result: dict[str, Any] = self.store._write(
            viewer,
            key,
            "m3.marriage_declared",
            dict(
                award=award,
                revision=revision,
                first=first.model_dump(mode="json"),
                second=second.model_dump(mode="json"),
                financial=financial.model_dump(mode="json"),
                status_from=status_from.model_dump(mode="json"),
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
        return result

    def request_payment(
        self,
        viewer: GuildViewer,
        key: str,
        marriage: str,
        revision: int,
        product: str,
        detail: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, marriage)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or actor not in (source.first, source.second)
                or actor == source.financial
            ):
                raise WorkflowError("Reopen your actual cross-partner payment request")
            price = _price(state, actor, product, detail)
            identity, event = str(uuid4()), str(uuid4())
            value = rules.PaymentQuote(
                id=identity,
                marriage=marriage,
                beneficiary=actor,
                wallet=source.financial,
                product=product,
                detail=detail,
                frame=rules.frame(state, actor),
                price=price,
                event=event,
                account=account,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.marriage_payment_requested",
                state,
                event_id=event,
                quote_id=identity,
            )
            return dict(id=identity, phase="awaiting_financial_partner", price=price)

        result: dict[str, Any] = self.store._write(
            viewer,
            key,
            "m3.marriage_payment_requested",
            dict(
                marriage=marriage,
                revision=revision,
                product=product,
                detail=detail,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
        return result

    def approve_payment(
        self, viewer: GuildViewer, key: str, quote: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _quote_proof(self.game, c, state, quote)
            if (
                state.revision != revision
                or current_ref(state, viewer.user_id) != value.wallet
                or value.frame != rules.frame(state, value.beneficiary)
                or any(x.quote == quote for x in rules.records(state, rules.Approval))
            ):
                raise WorkflowError(
                    "Only the original financial partner approves this exact current request"
                )
            event = str(uuid4())
            approval = rules.Approval(
                id=str(uuid4()), quote=quote, financial=value.wallet, event=event, account=account
            )
            rules.put(state, approval)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.marriage_payment_approved",
                state,
                event_id=event,
                quote_id=quote,
            )
            return dict(id=quote, phase="approved", price=value.price)

        result: dict[str, Any] = self.store._write(
            viewer,
            key,
            "m3.marriage_payment_approved",
            dict(quote=quote, revision=revision, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
        return result
