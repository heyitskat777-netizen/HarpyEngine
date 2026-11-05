"""One actual Virus superior order, real ReceiveOrders and source-only HandlerGirl Disobey."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actor_plays as actor_rules
from girlframe.engine import m3_compliance_virus as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_compliance_virus_state import Purge
from girlframe.engine.m3_items import body_ref
from girlframe.engine.m3_role_punishments import view as person_view
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_compliance_virus import (
    VirusService,
    _authority,
    _history,
    _resolve_work,
    source,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RESPONSES = ("obedient", "immediate", "hesitant", "mouthing_off", "gritted_teeth", "disobey")


def create_order(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: Purge,
    viewer: GuildViewer,
    key: str,
    text: str,
) -> dict[str, Any]:
    if value.target is None:
        raise WorkflowError("Actual direct order needs original recipient.")
    target = person_view(state, value.target, profiles(c, game.store.campaign_id))
    if (
        value.kind != "girl"
        or value.phase != "order"
        or value.order_id
        or not value.contact_confirmed
        or not value.review_event
    ):
        raise WorkflowError("One actual touch purge creates exactly one owned source order.")
    from girlframe.services.m3_compliance_virus import _audit

    _audit(
        c, game, value.review_event, value.judge_controller, "m3.compliance_virus_contact_reviewed"
    )
    reviewed = rules.record(_history(c, game, value.review_event), Purge, value.id)
    if (
        not reviewed.contact_confirmed
        or reviewed.phase != "order"
        or reviewed.target != value.target
    ):
        raise WorkflowError("Actual original judge must confirm real source touching.")
    event = str(uuid4())
    if target.girl == "harpy":
        # Printed exemption is retained even if the actual source owner issues the words.
        updated = value.model_copy(
            update=dict(
                phase="complete",
                immune=True,
                order_text=text,
                effect_event=event,
                completion_event=event,
                revision=value.revision + 1,
            )
        )
        rules.put(state, updated)
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.compliance_virus_order_issued",
            state,
            event_id=event,
            purge=value.id,
            immune=True,
            order=text,
        )
        _resolve_work(c, game, updated, event)
        return dict(id=value.id, immune=True, phase="complete")
    if (
        target.rules not in ("girl_frame", "handler_girl")
        or target.controller != value.target_controller
    ):
        raise WorkflowError("This actual original has no printed ReceiveOrders port.")
    from girlframe.services.m3_virus_operations import _clear, held

    action = held(game, c, value)
    identity = value.operational_action
    order = str(uuid4())
    action = _clear(game, c, value, event)
    action["data"].update(
        play="receive_orders",
        virus_order=value.id,
        order_actor=value.target_controller,
        order_id=order,
        order_text=text,
        depth=0,
        label=target.label,
        character_ids={uid: sheet.character_id for uid, sheet in state.sheets.items()},
    )
    c.execute(
        t.m2["m2_orders"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            id=order,
            issuer_id=str(value.creator_controller),
            target_id=str(value.target_controller),
            channel_id=str(value.channel),
            body_json=json.dumps(
                dict(
                    text=text,
                    virus_purge=value.id,
                    issuer_actor=value.creator.model_dump(mode="json"),
                    target_actor=value.target.model_dump(mode="json"),
                )
            ),
            state="awaiting_response",
        )
    )
    game.request(c, action, value.target_controller, "order_response")
    game.save_action(c, action, state="awaiting_choices")
    updated = value.model_copy(
        update=dict(
            phase="awaiting_order",
            order_text=text,
            order_action=identity,
            order_id=order,
            order_event=event,
            effect_event=event,
            revision=value.revision + 1,
        )
    )
    rules.put(state, updated)
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.compliance_virus_order_issued",
        state,
        event_id=event,
        purge=value.id,
        order_id=order,
        action_id=identity,
    )
    return dict(id=value.id, action_id=identity, order_id=order, immune=False)


def prove_order(
    game: "GameService", c: Connection, action: dict[str, Any]
) -> tuple[GameState, Purge]:
    state, value = source(c, game, action["data"].get("virus_order", ""))
    if (
        action["id"] != value.order_action
        or action["data"].get("order_id") != value.order_id
        or int(action["actor_id"]) != value.creator_controller
        or action["data"].get("order_actor") != value.target_controller
        or int(action["channel_id"]) != value.channel
        or action["scene_id"] != value.scope.scene_id
        or action["data"].get("play") != "receive_orders"
    ):
        raise WorkflowError("Recover the actual original Virus order and response source.")
    proof = rules.record(_history(c, game, value.order_event), Purge, value.id)
    if (
        proof.order_action != action["id"]
        or proof.order_text != value.order_text
        or proof.target != value.target
        or proof.phase != "awaiting_order"
    ):
        raise WorkflowError("A label cannot create superior-order authority.")
    return state, value


def valid_order(
    game: "GameService",
    c: Connection,
    state: GameState,
    owner: int,
    channel: int,
    order: dict[str, Any],
) -> bool:
    body = json.loads(order["body_json"])
    if not body.get("virus_purge"):
        return False
    actual, value = source(c, game, body["virus_purge"])
    _authority(c, game, actual, value)
    if value.order_action is None or value.target is None:
        raise WorkflowError("Recover actual source order and original recipient.")
    original = game.action(c, value.order_action)
    prove_order(game, c, original)
    sheet = state.sheets.get(str(owner))
    if (
        value.phase != "awaiting_order"
        or value.target.kind != "pilot"
        or value.target_controller != owner
        or sheet is None
        or value.target.incarnation != sheet.character_id
        or value.channel != channel
        or value.order_id != order["id"]
        or order["state"] != "disobey"
    ):
        raise WorkflowError(
            "Only the actual original recipient may Disobey this one-shot superior order."
        )
    return True


def finish_order(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    _, value = prove_order(game, c, action)
    if game.pending(c, action["id"]):
        raise WorkflowError("Resolve actual original recipient's order response first.")
    event = action["data"].get("response_event")
    if not event:
        raise WorkflowError("An actual human source response must finish the order.")
    changed = rules.complete(state, value.id, event)
    state.facts = changed.facts
    action["state"] = "complete"
    game.queue(
        c,
        action,
        "outcome",
        dict(
            play="receive_orders",
            callsign=action["data"]["label"],
            receipt=None,
            total=None,
            tier=None,
        ),
    )


def synchronize_order(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    if not action["data"].get("virus_order") or action["state"] != "complete":
        return
    state, value = source(c, game, action["data"]["virus_order"])
    if value.phase == "complete":
        _resolve_work(c, game, value, event)


class VirusOrderService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        state, value = prove_order(self.game, c, action)
        if value.target is None:
            raise WorkflowError("Actual order has no fictional recipient.")
        if int(row["actor_id"]) != viewer.user_id or viewer.user_id != value.target_controller:
            raise WorkflowError("This original direct order belongs to its actual recipient.")
        return dict(row) | dict(
            virus_order=True,
            body=json.loads(row["body_json"]),
            play="receive_orders",
            result=action["data"]["result"],
            order_text=value.order_text,
            actor=value.target_controller,
            target_actor=person_view(
                state, value.target, profiles(c, self.store.campaign_id)
            ).ref.model_dump(mode="json"),
            source_purge=value.id,
            child=action["data"].get("disobey_child"),
        )

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            action = self.game.action(c, identity)
            _, value = prove_order(self.game, c, action)
            if viewer.user_id not in (
                value.creator_controller,
                value.target_controller,
                value.judge_controller,
            ):
                raise WorkflowError("Only original source roles read this actual direct order.")
            return dict(
                id=identity,
                state=action["state"],
                revision=action["revision"],
                play="receive_orders",
                receipt=None,
                modifiers=[],
                result=action["data"]["result"] if action["state"] == "complete" else None,
            )

    def respond(
        self, viewer: GuildViewer, key: str, choice: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            table = t.m2["m2_choices"]
            raw_row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == choice,
                        table.c.actor_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if raw_row is None:
                raise WorkflowError("This actual direct order response belongs to another human.")
            row = dict(raw_row)
            action = self.game.action(c, row["action_id"])
            state, value = prove_order(self.game, c, action)
            _authority(c, self.game, state, value)
            if value.target is None:
                raise WorkflowError("Actual original recipient is required.")
            if (
                viewer.user_id != value.target_controller
                or row["state"] != "pending"
                or row["revision"] != revision
                or row["kind"] != "order_response"
                or len(answer.options) != 1
                or answer.options[0] not in RESPONSES
                or answer.denied
                or answer.fields
                or answer.member
                or answer.number is not None
                or answer.flag is not None
                or answer.text
            ):
                raise WorkflowError("Choose your actual original response to this direct order.")
            target = person_view(state, value.target, profiles(c, self.store.campaign_id))
            if target.controller != viewer.user_id or target.rules not in (
                "girl_frame",
                "handler_girl",
            ):
                raise WorkflowError("A new body cannot answer this original order.")
            event = str(uuid4())
            selected = answer.options[0]
            c.execute(
                table.update()
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == choice)
                .values(state="answered", revision=revision + 1)
            )
            c.execute(
                t.m2["m2_orders"]
                .update()
                .where(
                    t.m2["m2_orders"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_orders"].c.id == value.order_id,
                )
                .values(state="disobey" if selected == "disobey" else "followed")
            )
            action["data"]["choices"]["order_response:" + str(viewer.user_id)] = answer.model_dump(
                mode="json"
            )
            action["data"]["response_event"] = event
            action["data"]["result"]["response"] = selected
            if selected == "disobey":
                self.game.request(
                    c,
                    action,
                    viewer.user_id,
                    "order_disobey",
                    dict(
                        order_id=value.order_id,
                        virus_purge=value.id,
                        target_actor=value.target.model_dump(mode="json"),
                    ),
                )
            else:
                finish_order(self.game, c, state, action)
            self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.virus_order_response",
                state,
                event_id=event,
                action_id=action["id"],
                choice_id=choice,
            )
            c.execute(
                t.m2["m2_responses"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    choice_id=choice,
                    actor_id=str(viewer.user_id),
                    answer_json=answer.model_dump_json(),
                    event_id=event,
                )
            )
            synchronize_order(self.game, c, action, event)
            return dict(action_id=action["id"], state=action["state"])

        return VirusService(self.game)._write(
            viewer,
            key,
            "m3.virus_order_response",
            dict(choice=choice, revision=revision, answer=answer.model_dump(mode="json")),
            operation,
        )


def required_disobey(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> str | None:
    if prepared.play != "disobey_orders" or not prepared.parent:
        return None
    parent = game.action(c, prepared.parent)
    if not parent["data"].get("virus_order"):
        return None
    _, value = prove_order(game, c, parent)
    _authority(c, game, state, value)
    if (
        value.target is None
        or value.target.kind != "pilot"
        or value.target.entity != str(viewer.user_id)
        or value.target.incarnation != state.sheets[str(viewer.user_id)].character_id
        or value.channel != channel
        or value.order_id != prepared.order_id
        or value.phase != "awaiting_order"
        or len(
            [
                x
                for x in game.pending(c, parent["id"])
                if x["kind"] == "order_disobey" and int(x["actor_id"]) == viewer.user_id
            ]
        )
        != 1
    ):
        raise WorkflowError(
            "Only actual original recipient's required Disobey may continue this source."
        )
    return value.id


def prepare_disobey(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    if prepared.play != "disobey_orders" or not prepared.parent or not prepared.order_id:
        raise WorkflowError("This actual HandlerGirl may Disobey only its real Virus source order.")
    parent = game.action(c, prepared.parent)
    _, value = prove_order(game, c, parent)
    _authority(c, game, state, value)
    if game.immediate_work(
        c, viewer.user_id, scene_id=parent["scene_id"], excluding=frozenset({value.id})
    ):
        raise WorkflowError("Resolve unrelated actual immediate source work first.")
    requests = [
        x
        for x in game.pending(c, parent["id"])
        if x["kind"] == "order_disobey" and int(x["actor_id"]) == viewer.user_id
    ]
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if value.target is None:
        raise WorkflowError("Original actual recipient required.")
    if (
        body_ref(state, actor) != body_ref(state, value.target)
        or actual.rules != "handler_girl"
        or viewer.user_id != value.target_controller
        or prepared.order_id != value.order_id
        or len(requests) != 1
        or parent["data"].get("disobey_child")
    ):
        raise WorkflowError(
            "Use the original source-owned actual HandlerGirl response; no proxy PC."
        )
    return dict(
        purge=value.id,
        parent=parent["id"],
        choice=requests[0]["id"],
        actor=actor.model_dump(mode="json"),
        judge=value.judge_controller,
        witnessed=prepared.witnessed,
    )


def actor_results(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["virus_disobey"]
    level = action["data"]["result"]["tier"]
    # Actual HandlerGirl has no Status. Witness fact is retained without inventing a rank.
    action["data"]["result"].update(
        witnessed=meta["witnessed"], status_change=None, can_disobey=level != "low"
    )
    if level == "low":
        game.request(c, action, meta["judge"], "virus_disobey_discovery")
    else:
        game.request(c, action, int(action["actor_id"]), "virus_disobey_outcome")


def apply_actor(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["virus_disobey"]
    _, value = source(c, game, meta["purge"])
    actor = ActorRef.model_validate(meta["actor"])
    kind = row["kind"]
    level = action["data"]["result"]["tier"]
    if kind == "virus_disobey_outcome":
        if int(row["actor_id"]) != value.target_controller:
            raise WorkflowError("The actual original Girl owns the Disobey outcome.")
        if level == "high":
            if answer.flag is not True or answer.options or answer.denied:
                raise WorkflowError("Confirm actual immediate action without thinking.")
            from girlframe.engine.m3_leviathan_obsession import allowed_gain

            state.handler_heat += allowed_gain(
                state, actor, 2, "Immediate Disobey", action["data"]["response_event"]
            )
        elif level == "mid":
            if len(answer.options) != 1 or answer.options[0] not in (
                "tag_heat",
                "reject_tag",
                "follow",
            ):
                raise WorkflowError("Choose one printed Disobey result.")
            option = answer.options[0]
            if option == "tag_heat":
                if answer.number not in (1, 2) or not answer.text.strip():
                    raise WorkflowError("Give your actual Girl a Tag and one or two Heat.")
                actor_rules.add_tag(
                    state, actor, answer.text, tuple(action["data"]["participants"])
                )
                from girlframe.engine.m3_leviathan_obsession import allowed_gain

                state.handler_heat += allowed_gain(
                    state, actor, answer.number, "Disobey Tag", action["data"]["response_event"]
                )
            elif option == "reject_tag":
                if len(answer.denied) != 1:
                    raise WorkflowError("Choose one actual Tag to reject.")
                from girlframe.engine.m3_tag_permissions import can_reject

                if not can_reject(state, actor, answer.denied[0]):
                    raise WorkflowError("Actual original locker permission is required.")
                selected = next((x for x in state.handler_tags if x.id == answer.denied[0]), None)
                if selected is None:
                    raise WorkflowError("Reject only the actual original Girl's existing Tag.")
                # This printed immediate option does not require a prior reject-action marker.
                state.handler_tags = [x for x in state.handler_tags if x.id != selected.id]
                actor_rules.context(state, actor).revision += 1
            else:
                cast = SceneCast.model_validate_json(value.cast_json)
                follower = next(
                    (
                        x
                        for x in cast.roles
                        if x.actor.token == answer.fields.get("follower_actor") and x.actor != actor
                    ),
                    None,
                )
                if follower is None:
                    raise WorkflowError("Choose one actual other original scene role to follow.")
                actual = resolve(
                    state,
                    follower.actor,
                    profiles(c, game.store.campaign_id),
                    require_current_profile=False,
                )
                if actual.controller != follower.controller:
                    raise WorkflowError(
                        "The actual selected follower's original controller changed."
                    )
                game.request(
                    c,
                    action,
                    follower.controller,
                    "virus_disobey_follow",
                    dict(invited=follower.controller, actor=follower.actor.model_dump(mode="json")),
                )
        else:
            raise WorkflowError("Low cannot disobey; no successful outcome is invented.")
        game.request(c, action, value.judge_controller, "virus_disobey_discovery")
    elif kind == "virus_disobey_follow":
        if answer.flag is None:
            raise WorkflowError(
                "The actual other human chooses immediate unthinking follow or refusal."
            )
        action["data"]["result"]["followed"] = answer.flag
        action["data"]["result"]["follower"] = int(row["actor_id"])
    elif kind == "virus_disobey_discovery":
        if int(row["actor_id"]) != value.judge_controller or answer.flag is None:
            raise WorkflowError("The actual source rules Handler records whether it finds out.")
        action["data"]["result"]["handler_knows"] = answer.flag
        if answer.flag:
            from girlframe.services.m3_role_punishments import open_case

            if value.judge is None:
                raise WorkflowError(
                    "Actual Punishment needs the real original inflictor body, not an OOC "
                    "principal."
                )
            actual = resolve(
                state,
                value.judge,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            )
            event = action["data"]["response_event"]
            case = str(uuid4())
            changed, _ = open_case(
                state,
                profiles(c, game.store.campaign_id),
                actor=value.judge,
                target=actor,
                chooser=value.judge,
                source_kind="compliance_virus",
                action=None,
                source_work=value.id,
                source_event=event,
                identity=case,
                chooser_controller=value.judge_controller,
                executor_controller=value.judge_controller,
            )
            updated = value.model_copy(
                update=dict(
                    phase="punishment",
                    role_case=case,
                    effect_event=event,
                    punishment_executor=value.judge,
                    punishment_executor_frame=actual.frame_instance,
                    discovery_action=action["id"],
                    discovery_choice=row["id"],
                    revision=value.revision + 1,
                )
            )
            rules.put(changed, updated)
            state.role_punishments, state.facts = changed.role_punishments, changed.facts
            game.request(
                c, action, value.judge_controller, "virus_disobey_punishment", dict(case_id=case)
            )
    else:
        raise WorkflowError("Use the actual source-specific Disobey decision.")
    if not game.pending(c, action["id"]):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)


def prove_discovery(game: "GameService", c: Connection, value: Purge) -> None:
    if value.discovery_action is None or value.discovery_choice is None:
        raise WorkflowError("Actual Disobey Punishment requires genuine original discovery.")
    action = game.action(c, value.discovery_action)
    row = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == value.discovery_choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["event_id"] != value.effect_event
        or int(row["actor_id"]) != value.judge_controller
        or ChoiceAnswer.model_validate_json(row["answer_json"]).flag is not True
        or action["data"].get("virus_disobey", {}).get("purge") != value.id
        or action["data"]["receipt"] is None
        or action["data"]["result"].get("handler_knows") is not True
    ):
        raise WorkflowError("A source label cannot fabricate real discovered Disobey or dice.")


def synchronize_disobey(
    game: "GameService", c: Connection, action: dict[str, Any], event: str
) -> None:
    if not action["data"].get("virus_disobey"):
        return
    from girlframe.services.m3_role_punishments import synchronize

    synchronize(game, c, None, event)
    if action["state"] != "complete":
        return
    state, value = source(c, game, action["data"]["virus_disobey"]["purge"])
    if value.order_action is None:
        raise WorkflowError("Actual original parent order required.")
    parent = game.action(c, value.order_action)
    requests = [x for x in game.pending(c, parent["id"]) if x["kind"] == "order_disobey"]
    if len(requests) != 1:
        raise WorkflowError("Recover the exact original source order continuation.")
    row = requests[0]
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == row["id"])
        .values(
            state="answered",
            revision=row["revision"] + 1,
            body_json=json.dumps(
                json.loads(row["body_json"])
                | dict(completed_by_action=action["id"], completion_event=event)
            ),
        )
    )
    parent["data"]["response_event"] = event
    parent["data"]["result"]["response_play"] = action["id"]
    if value.phase != "complete":
        finish_order(game, c, state, parent)
    else:
        parent["state"] = "complete"
        game.queue(
            c,
            parent,
            "outcome",
            dict(
                play="receive_orders",
                callsign=parent["data"]["label"],
                receipt=None,
                total=None,
                tier=None,
            ),
        )
    game.save_action(c, parent)
    event_row = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.command_key).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if event_row is None:
        raise WorkflowError("Actual source completion event required.")
    last = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == event_row.command_key,
        )
    )
    completed = game.event(
        c,
        str(event_row.actor_id),
        str(event_row.command_key),
        "m3.virus_order_completed",
        state,
        event_index=int(last or 0) + 1,
        purge=value.id,
        action_id=parent["id"],
    )
    synchronize_order(game, c, parent, completed)


def complete_disobey_punishment(
    game: "GameService", c: Connection, value: Purge, event: str
) -> None:
    """Real RoleCase completion closes only its actual waiting Disobey choice, no human reply."""
    if value.kind != "girl" or not value.discovery_action or not value.role_case:
        return
    action = game.action(c, value.discovery_action)
    requests = [
        x
        for x in game.pending(c, action["id"])
        if x["kind"] == "virus_disobey_punishment"
        and json.loads(x["body_json"]).get("case_id") == value.role_case
    ]
    if len(requests) != 1:
        raise WorkflowError("Recover actual original Disobey Punishment continuation.")
    row = requests[0]
    table = t.m2["m2_choices"]
    c.execute(
        table.update()
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == row["id"])
        .values(
            state="answered",
            revision=row["revision"] + 1,
            body_json=json.dumps(
                json.loads(row["body_json"])
                | dict(completed_by_case=value.role_case, completion_event=event)
            ),
        )
    )
    if not game.pending(c, action["id"]):
        from girlframe.services.m3_actor_plays import ActorPlayService

        state = load_state(c, game.store.campaign_id)
        ActorPlayService(game).finish(c, state, action)
        game.save_action(c, action)
        synchronize_disobey(game, c, action, event)


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    _, value = source(c, game, action["data"]["virus_disobey"]["purge"])
    cast = SceneCast.model_validate_json(value.cast_json)
    followers = []
    for role in cast.roles:
        if role.actor == value.target:
            continue
        try:
            actual = resolve(
                state,
                role.actor,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            )
        except ValueError:
            continue
        followers.append(dict(token=role.actor.token, label=actual.label))
    return dict(virus_disobey=True, disobey_followers=followers)


def post_response(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    # Called AFTER actual m2_responses insertion, so discovery proof is genuine.
    if action["data"].get("virus_disobey"):
        synchronize_disobey(game, c, action, event)
    if action["data"].get("virus_order"):
        synchronize_order(game, c, action, event)
    elif action.get("parent_id"):
        parent = game.action(c, action["parent_id"])
        if parent["data"].get("virus_order"):
            synchronize_order(game, c, parent, event)
