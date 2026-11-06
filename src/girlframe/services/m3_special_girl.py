"""Source-owned Handler token, Status bonus and genuine compulsory discipline."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_special_girl as rules
from girlframe.engine.m2 import AssetState, ChoiceAnswer, GameState, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def entitlement(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> FrameRuleReceipt | None:
    receipt = rules.held(state, actor)
    if receipt is None:
        return None
    gate = Access(game.store)
    if gate.registry is None:
        return None
    try:
        gate.registry.require_available(rules.RULE)
    except ValueError:
        return None
    SpecialGirlService(game)._source(c, state, receipt.id)
    return receipt


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    if prepared.play != "put_someone_beneath_you":
        return None
    actor = current_ref(state, viewer.user_id)
    receipt = entitlement(game, c, state, actor)
    if receipt is None:
        return None
    if prepared.target is None:
        raise WorkflowError("Use the actual original Beneath target")
    handler = active_handler(state)
    if handler is None or state.handler != HandlerService(game.store).current(c)[1].handler_id:
        raise WorkflowError("Recover this actual living Handler appointment before the Play")
    target = current_ref(state, prepared.target)
    return dict(
        purchase=receipt.id,
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        frame=receipt.frame_instance,
        handler=handler.model_dump(mode="json"),
        bonus=int(higher(state, viewer.user_id, prepared.target)),
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    actual = prepare(game, c, viewer, state, PlayInput.model_validate(action["data"]["prepared"]))
    if actual != (action["data"].get("beneath") or {}).get("special_girl"):
        raise WorkflowError(
            "Recover the original unrolled Special Girl source, Handler and actual Status"
        )


def modifiers(action: dict[str, Any]) -> list[dict[str, Any]]:
    value = (action["data"].get("beneath") or {}).get("special_girl")
    return [dict(source="Handler's Special Girl", amount=1)] if value and value["bonus"] else []


def receipt(
    action: dict[str, Any], value: dict[str, Any], pre_modifiers: list[dict[str, Any]]
) -> None:
    source = (action["data"].get("beneath") or {}).get("special_girl")
    if source:
        value.update(special_girl_purchase=source["purchase"], pre_modifiers=pre_modifiers)
        value.setdefault("base_modifier", value["heat"])
        value.setdefault("modifier_source", "Heat")


def counter(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    selected: ChoiceAnswer,
    source_choice: str,
    asset: str | None,
) -> None:
    meta = action["data"]["beneath"].get("special_girl")
    if not meta or action["data"]["result"]["tier"] != "low" or selected.options != ("damage",):
        return
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    handler = ActorRef.model_validate(meta["handler"])
    paid = entitlement(game, c, state, actor)
    damaged = next(
        (x for x in state.sheets[actor.entity].assets if x.id == asset and x.damaged), None
    )
    if (
        paid is None
        or paid.id != meta["purchase"]
        or damaged is None
        or not same_handler_body(state, handler)
        or action["data"]["handler"] != int(handler.entity)
        or action["data"]["receipt"].get("special_girl_purchase") != paid.id
    ):
        raise WorkflowError("Recover the actual Special Girl damage and original Handler source")
    identity = str(
        uuid5(
            NAMESPACE_URL, "girlframe:special-girl-punishment:" + action["id"] + ":" + source_choice
        )
    )
    game.request(
        c,
        action,
        int(handler.entity),
        "beneath_punishment",
        dict(
            owner=handler.model_dump(mode="json"),
            target=target.model_dump(mode="json"),
            work_id=identity,
        ),
    )
    pending = next(x for x in game.pending(c, action["id"]) if x["kind"] == "beneath_punishment")
    action["data"]["beneath_work"] = dict(
        id=identity,
        request=pending["id"],
        source_choice=source_choice,
        owner=handler.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        special_girl=dict(purchase=paid.id, asset=asset, counter_choice=request["id"]),
    )


def verify_discipline_owner(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> None:
    body = json.loads(row["body_json"])
    meta = action["data"].get("beneath_work") or {}
    declared = (action["data"].get("beneath") or {}).get("special_girl")
    owner = ActorRef.model_validate(body["discipline_owner_actor"])
    if (
        not declared
        or not meta.get("special_girl")
        or owner.kind != "handler"
        or owner.model_dump(mode="json") != meta.get("owner")
        or row["subject_id"] != declared["target"]["entity"]
        or not same_handler_body(state, owner)
        or HandlerService(game.store).current(c)[1].handler_id != int(owner.entity)
        or action["data"]["result"]["tier"] != "low"
    ):
        raise WorkflowError("Recover the actual original Handler-owned Special Girl Punishment")
    table = t.m3["m3_required_work"]
    versions = list(
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == row["id"],
                table.c.revision <= row["revision"],
            )
            .order_by(table.c.revision)
        ).mappings()
    )
    executor = owner
    if not versions or versions[0]["owner_id"] != owner.entity:
        raise WorkflowError("Recover the actual original Handler discipline source")
    frozen = (
        "special_girl",
        "source_action",
        "source_choice",
        "continuation",
        "discipline_owner_actor",
    )
    for version in versions:
        saved = json.loads(version["body_json"])
        if any(saved.get(key) != body.get(key) for key in frozen):
            raise WorkflowError("Recover the unchanged original Handler discipline source")
        if version["owner_id"] != executor.entity:
            event = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == version["event_id"],
                    )
                )
                .mappings()
                .first()
            )
            command = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == game.store.campaign_id,
                        t.commands.c.interaction_key == event["command_key"],
                    )
                )
                .mappings()
                .first()
                if event
                else None
            )
            outcome = json.loads(command["outcome_json"]) if command else {}
            if (
                event is None
                or event["kind"] != "m3.punishment_delegated"
                or event["actor_id"] != executor.entity
                or json.loads(event["payload_json"]).get("work_id") != row["id"]
                or outcome.get("id") != row["id"]
                or outcome.get("state") != "delegated"
                or not saved.get("discipline_owner_character")
            ):
                raise WorkflowError("Recover the actual original executor's delegated Punishment")
            executor = ActorRef(
                kind="pilot",
                entity=version["owner_id"],
                incarnation=saved["discipline_owner_character"],
            )
        elif (
            executor.kind == "pilot"
            and saved.get("discipline_owner_character") != executor.incarnation
        ):
            raise WorkflowError("A delegated Punishment cannot pass to another character")
    if executor.entity != row["owner_id"] or (
        executor.kind == "pilot"
        and game.character_binding(c, state, int(executor.entity), require_current_profile=False)
        != executor.incarnation
    ):
        raise WorkflowError("Recover the actual current delegated Pilot and original character")


class SpecialGirlService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id, table.c.kind == rules.KIND
                    )
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def _source(
        self, c: Connection, state: GameState, identity: str
    ) -> tuple[dict[str, Any], rules.Token, FrameRuleReceipt]:
        row = next((x for x in self._rows(c) if x["id"] == identity), None)
        value = rules.token(state, identity)
        paid = next(
            (
                x
                for x in state.requisitions
                if isinstance(x, FrameRuleReceipt) and x.id == identity and x.rule_id == rules.RULE
            ),
            None,
        )
        if row is None or value is None or paid is None:
            raise WorkflowError("Recover the original actual Handler token request")
        purchase_proof(c, self.store, paid)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        if (
            original is None
            or rules.token(original, identity) != value
            or json.loads(row["body_json"]).get("token") != value.model_dump(mode="json")
            or value.actor != paid.actor
            or value.frame != paid.frame_instance
            or value.source_event != paid.source_event
            or row["owner_id"] != value.handler.entity
            or row["subject_id"] != value.actor.entity
            or row["event_id"] != value.event
        ):
            raise WorkflowError("Recover the actual immutable Handler-authored token source")

        def snapshot(event: str) -> GameState | None:
            body = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == event,
                )
            )
            return GameState.model_validate_json(body) if body else None

        first_state = snapshot(value.source_event)
        first = rules.token(first_state, identity) if first_state else None
        keys = ("id", "actor", "handler", "frame", "purchase", "source_event")
        if first is None or any(getattr(first, key) != getattr(value, key) for key in keys):
            raise WorkflowError("Recover the original paid token's actual Handler and owner")
        if value.phase != "handler":
            authored_state = snapshot(value.authored_event) if value.authored_event else None
            authored = rules.token(authored_state, identity) if authored_state else None
            author = c.execute(
                sa.select(t.events.c.actor_id, t.events.c.kind).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.authored_event,
                )
            ).first()
            if (
                author is None
                or author.actor_id != value.handler.entity
                or author.kind != "m3.special_girl_token"
                or authored is None
                or authored.phase != "owner"
                or authored.asset != value.asset
            ):
                raise WorkflowError("Recover the actual original Handler's authored token")
        if value.phase == "complete":
            installer = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.installed_event,
                )
            )
            if (
                value.installed_event != value.event
                or installer != value.actor.entity
                or value.asset is None
                or not any(x == value.asset for x in original.sheets[value.actor.entity].assets)
            ):
                raise WorkflowError("Recover the original owner's exact installed token and slot")
        return row, value, paid

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        assert gate.registry is not None
        entry = gate.registry.require_available(rules.RULE)
        if (entry.scope, entry.frame_class, entry.frame_rule) != (
            "frame",
            "autocrat",
            "class_requisition",
        ):
            raise WorkflowError("Recover the printed Autocrat Special Girl source")

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            try:
                actor = current_ref(state, viewer.user_id)
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                gate = Access(self.store)
                if gate.registry is None:
                    return dict(available=False)
                gate.registry.require_available(rules.RULE)
                if active_handler(state) is None:
                    return dict(available=False)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            paid = next(
                (
                    x
                    for x in state.requisitions
                    if isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and x.rule_id == rules.RULE
                    and grafts.eligible(state, x)
                ),
                None,
            )
            if paid:
                self._source(c, state, paid.id)
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                owned=paid is not None,
                suspended=bool(paid and suspended(state, paid.id)),
                request=paid.id if paid else None,
                permissions=sheet.permissions,
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        frame: str,
        account: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if (
                state.revision != revision
                or actor != current_ref(state, viewer.user_id)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual original Special Girl acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            handler = active_handler(state)
            if current != frame or sheet.permissions < price or handler is None:
                raise WorkflowError(
                    "Recover the actual Frame, living Handler and available Permissions"
                )
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == frame
                and x.rule_id == rules.RULE
                for x in state.requisitions
            ):
                raise WorkflowError(
                    "Restore the original entitlement and token instead of buying twice"
                )
            identity, event = str(uuid4()), str(uuid4())
            value = rules.Token(
                id=identity,
                actor=actor,
                handler=handler,
                frame=frame,
                purchase=identity,
                source_event=event,
                event=event,
            )
            sheet.permissions -= price
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind=kind,
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=donor,
                    rule_id=rules.RULE,
                    grant="special-girl:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=price,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                int(handler.entity),
                viewer.user_id,
                rules.KIND,
                dict(token=value.model_dump(mode="json"), immediate=True),
                event,
            )
            return dict(id=identity, cost=price)

        return self.store._write(
            viewer,
            key,
            "m3.special_girl_purchased",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                account=account,
                donor_frame=donor_frame,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            row, value, paid = self._source(c, state, identity)
            if str(viewer.user_id) not in (value.actor.entity, value.handler.entity):
                raise WorkflowError("This original token belongs to its real Handler and owner")
            current = (
                grafts.held(state, value.actor, rules.RULE) == paid
                and same_handler_body(state, value.handler)
                and HandlerService(self.store).current(c)[1].handler_id == int(value.handler.entity)
            )
            sheet = state.sheets.get(value.actor.entity)
            effective = stored_ids(state, value.actor)
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                token=value.model_dump(mode="json"),
                can_act=current
                and (
                    (value.phase == "handler" and viewer.user_id == int(value.handler.entity))
                    or (value.phase == "owner" and viewer.user_id == int(value.actor.entity))
                ),
                needs_replace=bool(
                    sheet
                    and sum(
                        x.family == "girl" and counts_toward_limit(sheet, x) for x in sheet.assets
                    )
                    >= 4
                ),
                replacements=[
                    dict(id=x.id, label=x.name)
                    for x in sheet.assets
                    if x.family == "girl"
                    and x.id not in effective
                    and can_replace_at_limit(sheet, x)
                ]
                if sheet
                else [],
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        *,
        name: str = "",
        description: str = "",
        replace: str | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            row, value, paid = self._source(c, state, identity)
            view = self.get(viewer, identity)
            if not view["can_act"] or row["revision"] != revision or state.revision != expected:
                raise WorkflowError("Refresh the original owned token response")
            self.game.character_binding(c, state, int(value.actor.entity))
            from girlframe.services.m3_physical import PhysicalService

            PhysicalService(self.store)._idle(c)
            if self.game.immediate_work(
                c, int(value.actor.entity), excluding=frozenset({identity})
            ):
                raise WorkflowError("Resolve the other actual immediate source first")
            event = str(uuid4())
            if value.phase == "handler":
                HandlerService(self.store).authorize(c, viewer)
                if not name.strip() or not description.strip() or replace is not None:
                    raise WorkflowError("The actual Handler must name and describe the token")
                asset = AssetState(
                    id="special-token:" + paid.id,
                    family="girl",
                    name=name.strip(),
                    description=description.strip(),
                )
                value = value.model_copy(
                    update=dict(asset=asset, phase="owner", event=event, authored_event=event)
                )
                rules.put(state, value)
            elif value.phase == "owner":
                if name or description:
                    raise WorkflowError("Receive only the exact Handler-authored token")
                rules.give(state, value, replace, event)
                given = rules.token(state, identity)
                assert given is not None
                value = given
            else:
                raise WorkflowError("This actual token is already installed")
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.special_girl_token",
                state,
                event_id=event,
                token_id=identity,
                phase=value.phase,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=revision + 1,
                    state="resolved" if value.phase == "complete" else "pending",
                    event_id=event,
                    body_json=json.dumps(
                        dict(
                            token=value.model_dump(mode="json"), immediate=value.phase != "complete"
                        ),
                        sort_keys=True,
                    ),
                )
            )
            return dict(id=identity, phase=value.phase)

        return self.store._write(
            viewer,
            key,
            "m3.special_girl_token",
            dict(
                identity=identity,
                revision=revision,
                expected=expected,
                name=name,
                description=description,
                replace=replace,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for row in self._rows(c):
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                continue
            _, value, _ = self._source(c, state, row["id"])
            if value.phase != "complete":
                result.append(
                    dict(
                        id=value.id,
                        state=value.phase,
                        actionable=viewer.user_id
                        == int(
                            value.handler.entity if value.phase == "handler" else value.actor.entity
                        ),
                    )
                )
        return result
