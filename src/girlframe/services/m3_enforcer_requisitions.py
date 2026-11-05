"""Owned Enforcer acquisitions and their real, bounded passive choice consumers."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_enforcer_requisitions as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def proof(c: Connection, game: GameService, grant: rules.Grant) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == grant.source_event,
        )
    )
    initial = GameState.model_validate_json(raw) if raw else None
    original = (
        next((x for x in rules.grants(initial) if x.id == grant.id), None) if initial else None
    )
    receipt = (
        next((x for x in initial.requisitions if x.id == grant.purchase), None) if initial else None
    )
    if original != grant:
        raise WorkflowError("SOURCE_ENFORCER_GRANT_MISSING: recover the original paid rule.")
    if grant.source_kind == "replacement":
        _replacement_proof(c, game, grant)
        return
    if grant.source_kind == "frame_swap":
        from girlframe.engine.m3_frame_swap_state import SwapReceipt

        if (
            not isinstance(receipt, SwapReceipt)
            or receipt.actor != grant.actor
            or receipt.new_frame != grant.frame
            or receipt.selection.retained_rule != grant.rule
            or receipt.source_event != grant.source_event
        ):
            raise WorkflowError("Recover the actual paid Frame rule retention receipt.")
        purchase_proof(c, game.store, receipt)
        return
    if not isinstance(receipt, FrameRuleReceipt):
        raise WorkflowError("SOURCE_ENFORCER_GRANT_MISSING: recover the original paid rule.")
    purchase_proof(c, game.store, receipt)


def _replacement_proof(c: Connection, game: GameService, grant: rules.Grant) -> None:
    table = t.m3["m3_required_work"]
    rows = [
        dict(x)
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == grant.source_work)
            .order_by(table.c.revision)
        ).mappings()
    ]
    root = next(
        (x for x in rows if x["event_id"] == grant.source_event and x["state"] == "resolved"), None
    )
    body = json.loads(root["body_json"]) if root else {}
    quote = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == body.get("package_id"),
                table.c.state == "quoted",
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    supplied = json.loads(quote["body_json"]) if quote else {}
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == grant.source_event,
            )
        )
        .mappings()
        .first()
    )
    proposal = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == quote["event_id"]
            )
        )
        .mappings()
        .first()
        if quote
        else None
    )
    if (
        root is None
        or root["subject_id"] != grant.actor.entity
        or body.get("applied_event") != grant.source_event
        or body.get("frame_id") != grant.frame
        or grant.rule not in supplied.get("package", {}).get("additional_rules", [])
        or event is None
        or event["kind"] != "m3.compulsory_frame_replaced"
        or event["actor_id"] != grant.actor.entity
        or proposal is None
        or proposal["kind"] != "m3.frame_package_quoted"
        or proposal["actor_id"] != str(supplied.get("handler"))
    ):
        raise WorkflowError(
            "SOURCE_REPLACEMENT_GRANT_MISSING: recover the quoted package and owner response."
        )


def owned(
    c: Connection, game: GameService, state: GameState, actor: ActorRef, rule: str
) -> rules.Grant | None:
    grant = rules.held(state, actor, rule)
    if grant is not None:
        access = Access(game.store)
        assert access.registry is not None
        access.registry.require_available(rule)
        proof(c, game, grant)
        for receipt_id in rules.binding(state, grant)[2]:
            receipt = next(x for x in state.requisitions if x.id == receipt_id)
            purchase_proof(c, game.store, receipt)
        if actor.kind == "external_pilot":
            from girlframe.services.m3_tag_permissions import prove_birth

            prove_birth(c, game, state, actor)
    return grant


class EnforcerRequisitionService(RequisitionService):
    def __init__(self, game: GameService, registry: Registry | None = None):
        super().__init__(game)
        self.registry = registry

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        data = super().view(viewer)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(data["actor"])
            room = rules.room(state, actor)
            data["masters_room"] = room.model_dump(mode="json") if room else None
            data["enforcer_rules"] = [
                dict(
                    id=grant.id,
                    rule=grant.rule,
                    label=rules.TITLES[grant.rule],
                    active=rules.held(state, actor, grant.rule) is not None,
                )
                for grant in rules.grants(state)
                if grant.actor == actor and grant.frame == rules.frame(state, actor)
            ]
            return data

    def acquisition_view(self, viewer: GuildViewer, kind: rules.Kind) -> dict[str, Any]:
        data = self.view(viewer)
        with self.store.engine.connect() as c:
            Access(self.store, self.registry).authorize(c, viewer, "economy")
            registry = self.registry or Access(self.store).registry
            assert registry is not None
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(data["actor"])
            own = state.sheets[actor.entity].frame == "THE ENFORCER"
            if (
                kind not in ("ability_unlock", "frame_grafting")
                or (kind == "ability_unlock") != own
            ):
                raise WorkflowError(
                    "Unlock uses your actual Enforcer; Grafting uses another Frame."
                )
            choices = []
            for rule in (*rules.RULES, *(rules.BASE if kind == "frame_grafting" else ())):
                try:
                    registry.require_available(rule)
                except ValueError:
                    continue
                if not any(
                    x.actor == actor and x.rule == rule and x.frame == rules.frame(state, actor)
                    for x in rules.grants(state)
                ):
                    choices.append(dict(id=rule, label=rules.TITLES[rule]))
            return data | dict(kind=kind, price=2 if kind == "ability_unlock" else 3, rules=choices)

    def buy_rule(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        kind: rules.Kind,
        rule: str,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store, self.registry).authorize(c, viewer, "economy")
            if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the actual original Girl acquires her Frame rule.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            if self._actor(c, state, viewer).ref != actor:
                raise WorkflowError("Recover the original character's current acquisition view.")
            identity, grant, event = str(uuid4()), str(uuid4()), str(uuid4())
            registry = self.registry or Access(self.store).registry
            assert registry is not None
            changed = rules.purchase(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                registry,
                kind,
                rule,
                account,
                identity,
                grant,
                event,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                changed,
                event_id=event,
                requisition_id=identity,
                rule_id=rule,
                cost=2 if kind == "ability_unlock" else 3,
            )
            return dict(
                id=identity, grant=grant, rule=rule, cost=2 if kind == "ability_unlock" else 3
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3." + kind + "_purchased",
                dict(
                    actor=actor.model_dump(mode="json"),
                    expected=expected,
                    kind=kind,
                    rule=rule,
                    account=account,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def prepare_keep(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, prepared: PlayInput
) -> dict[str, Any]:
    if prepared.play != "keep_your_head":
        return {}
    grant = owned(c, game, state, actor, rules.PAVLOV)
    obeying = bool(getattr(prepared, "obeying_orders", False))
    account = str(getattr(prepared, "order_account", ""))
    if obeying and not account.strip():
        raise WorkflowError("Record your own actual current obedience before rolling Keep.")
    return dict(
        actor=actor.model_dump(mode="json"),
        grant=grant.id if grant else None,
        obeying=obeying,
        account=account,
        available=bool(grant and obeying),
    )


def pavlov_available(game: GameService, viewer: GuildViewer) -> bool:
    """A native Pilot form only offers the optional condition for its actual owned rule."""
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        actor = ActorRef(
            kind="pilot",
            entity=str(viewer.user_id),
            incarnation=game.character_binding(c, state, viewer.user_id),
        )
        return owned(c, game, state, actor, rules.PAVLOV) is not None


def keep_extras(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], answer: ChoiceAnswer
) -> set[str]:
    keys = {"pavlov_good_soldier": "good_soldier", "pavlov_bliss": "feels_as_good_as_sex"}
    supplied = {k: v for k, v in answer.fields.items() if k.startswith("pavlov_")}
    if not supplied:
        return set()
    meta = action["data"].get("enforcer_keep") or {}
    if (
        set(supplied) - set(keys)
        or any(x != "yes" for x in supplied.values())
        or not meta.get("available")
    ):
        raise WorkflowError(
            "Choose only optional owned Pavlov positives while actually obeying orders."
        )
    actor = ActorRef.model_validate(meta["actor"])
    grant = owned(c, game, state, actor, rules.PAVLOV)
    if grant is None or grant.id != meta["grant"] or not meta["account"].strip():
        raise WorkflowError("Recover the actual original Pavlov source and pre-roll obedience.")
    return {keys[x] for x in supplied}


def _raw(game: GameService, c: Connection, action: dict[str, Any]) -> GameState:
    receipt = action["data"]["receipt"]
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == receipt["id"],
        )
    )
    if raw is None:
        raise WorkflowError("SOURCE_MASTER_DOG_ROLL_MISSING: recover the actual raw receipt.")
    return GameState.model_validate_json(raw)


def _master(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    require_current: bool = True,
) -> rules.Grant | None:
    if not any(
        x.rule == rules.MASTER and x.actor.entity == str(action["actor_id"])
        for x in rules.grants(state)
    ):
        return None
    actor = ActorRef(
        kind="pilot",
        entity=str(action["actor_id"]),
        incarnation=action["data"]["character_ids"][str(action["actor_id"])],
    )
    if not any(x.actor == actor and x.rule == rules.MASTER for x in rules.grants(state)):
        return None
    before = _raw(game, c, action)
    original = rules.held(before, actor, rules.MASTER)
    if original is None or original.counterpart is None or rules.room(before, actor) is None:
        return None
    proof(c, game, original)
    if not require_current:
        return original
    grant = owned(c, game, state, actor, rules.MASTER)
    if grant != original or rules.room(state, actor) is None:
        raise WorkflowError("SOURCE_MASTER_DOG_CHANGED: recover the original Intense Handler Bond.")
    return grant


def intercept_results(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if action["data"]["play"] != "go_off_duty" or not action["data"].get("m3"):
        return False
    meta = action["data"].get("master_dog")
    if meta:
        return bool(meta["state"] == "pending")
    grant = _master(game, c, state, action, require_current=False)
    if grant is None:
        action["data"]["master_dog"] = dict(state="unavailable")
        return False
    actor = ActorRef.model_validate(grant.actor.model_dump(mode="json"))
    if owned(c, game, state, actor, rules.MASTER) != grant or rules.room(state, actor) is None:
        action["data"]["master_dog"] = dict(state="unavailable_current_source", grant=grant.id)
        return False
    action["data"]["master_dog"] = dict(
        state="pending", grant=grant.id, receipt=action["data"]["receipt"]["id"]
    )
    game.request(c, action, int(action["actor_id"]), "enforcer_master_dog", dict(grant=grant.id))
    return True


def apply_master(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    meta = action["data"].get("master_dog") or {}
    grant = _master(game, c, state, action, require_current=answer.number != 0)
    if (
        meta.get("state") != "pending"
        or grant is None
        or grant.id != meta.get("grant")
        or request["actor_id"] != str(action["actor_id"])
        or answer.number not in (-2, 0, 2)
        or answer.options
        or answer.denied
        or answer.fields
        or answer.text
        or answer.flag is not None
    ):
        raise WorkflowError("The original owner chooses exactly +2, -2 or decline once.")
    if any(x["source"] == rules.MASTER for x in action["data"]["modifiers"]):
        raise WorkflowError("This real roll already used Master's Dog.")
    action["data"]["modifiers"].append(
        dict(source=rules.MASTER, amount=answer.number, actor=int(action["actor_id"]))
    )
    meta.update(state="done", amount=answer.number)
    ChoiceEngine(game).results(c, state, action)
