"""Actual NPC-issued Orders and genuine Pilot refusal use the existing shared protocol."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_orders as rules
from girlframe.engine.m2 import GameState, PlayInput, higher
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_alpha import RULE
from girlframe.engine.m3_alpha_state import Broken
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_harpy_advancements import ECHOES
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

NPC_HANDLER = "npc.npc.handler"


def npc_handler_authority(
    game: GameService,
    c: Connection,
    state: GameState,
    cast: SceneCast,
    issuer: ActorRef,
    recipient: ActorRef,
    owner: int,
) -> str:
    bound = profiles(c, game.store.campaign_id)
    npc = resolve(state, issuer, bound, require_current_profile=False)
    girl = resolve(state, recipient, bound, require_current_profile=False)
    role = next((x for x in cast.roles if x.actor == issuer and x.controller == owner), None)
    if (
        role is None
        or issuer.kind != "npc"
        or npc.controller != owner
        or npc.controller == girl.controller
        or not npc.alive
        or npc.offstage_source
        or npc.custody
        or "handler" not in npc.jobs
        or "director" in npc.jobs
        or npc.cell is None
        or not girl.alive
        or girl.rules != "girl_frame"
        or girl.offstage_source
        or girl.cell != npc.cell
        or not any(x.actor == recipient and x.controller == girl.controller for x in cast.roles)
    ):
        raise WorkflowError("Use a living original NPC Handler and a local cast Girl")
    from girlframe.services.m3_expanded_status import ExpandedStatusService

    status = ExpandedStatusService(game)
    issuer_level = status.view(c, state, npc)["level"]
    recipient_level = status.view(c, state, girl)["level"]
    if issuer_level is None or recipient_level is None or issuer_level >= recipient_level:
        raise WorkflowError("This original NPC Handler does not outrank the Girl")
    return role.source_event


def _history(game: GameService, c: Connection, event: str) -> GameState:
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if body is None:
        raise WorkflowError("Recover the actual original NPC order source history")
    return GameState.model_validate_json(body)


def _condition(
    game: GameService, c: Connection, state: GameState, issuer: ActorRef, target: ActorRef
) -> Broken:
    try:
        found = rules.authority(state, issuer, target)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    original = next(
        (x for x in _history(game, c, found.source_event).alpha_broken if x.id == found.id), None
    )
    if original != found:
        raise WorkflowError("Recover the actual original source of this NPC's Broken condition")
    return found


def ranked_issuer(state: GameState, cast: SceneCast, controller: int) -> tuple[ActorRef, str]:
    handler = active_handler(state)
    if controller == cast.facilitator == state.handler and handler and cast.facilitator_source:
        return handler, cast.facilitator_source
    sheet = state.sheets.get(str(controller))
    for role in cast.roles:
        if (
            sheet is not None
            and role.actor.kind == "pilot"
            and role.controller == controller
            and role.actor.entity == str(controller)
            and role.actor.incarnation == sheet.character_id
        ):
            return role.actor, role.source_event
    raise WorkflowError("Issue as your original ranked pilot or the appointed scene Handler.")


def _access(
    game: GameService, c: Connection, viewer: GuildViewer, origin_kind: rules.Origin = "broken"
) -> None:
    if origin_kind == "ranked":
        game.authorize(c, viewer)
        return
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=True)
    assert access.registry is not None
    rule = {
        "broken": RULE,
        "am_secret": "girl.am.scrutinized",
        "secretary": "handler-advancement.handler-advancement.secretary",
        "npc_flirt": "play.basic.flirt",
        "stim_sex": "girl.stim-blissed.sex-play",
        "rebel_voice": "strain.rebellion.high.5.1",
        "harpy_echoes": ECHOES,
        "npc_handler": NPC_HANDLER,
    }[origin_kind]
    if origin_kind == "rebel_voice":
        access.authorize(c, viewer, "strain", director_response=True)
    if origin_kind == "npc_handler":
        access.authorize(c, viewer, "world", director_response=True)
    if origin_kind in ("harpy_echoes", "npc_handler"):
        try:
            access.require_specialist_rule(rule)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
    else:
        access.registry.require_available(rule)


def source(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Order,
    *,
    removal_action: str | None = None,
) -> None:
    approval = game.store.policy.m3_approval
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.event,
        )
    ).first()
    original = _history(game, c, value.event)
    if value.origin_kind == "ranked":
        if (
            audit is None
            or audit.kind != "m3.ranked_order_issued"
            or audit.actor_id != str(value.controller)
            or not any(
                row.get("kind") == "ranked_order"
                and row.get("id") == value.id
                and rules.Order.model_validate_json(row["body"]) == value
                for row in original.facts
            )
            or ranked_issuer(original, value.cast, value.controller)
            != (value.issuer, value.condition)
            or ranked_issuer(state, value.cast, value.controller) != (value.issuer, value.condition)
            or not higher(original, value.controller, int(value.target.entity))
            or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
            or resolve(state, value.target, profiles(c, game.store.campaign_id)).controller
            != int(value.target.entity)
        ):
            raise WorkflowError("Recover the original ranked issuer, recipient and scene.")
        return
    recorded = next(
        (
            x
            for x in original.facts
            if x.get("kind") == rules.FACT_KINDS[value.origin_kind] and x.get("id") == value.id
        ),
        None,
    )
    actual = resolve(state, value.issuer, profiles(c, game.store.campaign_id))
    recipient = resolve(state, value.target, profiles(c, game.store.campaign_id))
    if value.origin_kind == "npc_handler":
        current_cast = _cast(game, c, state, value.cast.channel)
        condition_invalid = any(
            npc_handler_authority(
                game, c, canon, cast, value.issuer, value.target, value.controller
            )
            != value.condition
            for canon, cast in ((original, value.cast), (state, current_cast))
        )
    elif value.origin_kind == "rebel_voice":
        from girlframe.services.m3_rebel_voice import authority as voice_authority

        rights = voice_authority(
            game, c, state, value.condition, value.controller, value.issuer, value.target
        )
        born = voice_authority(
            game, c, original, value.condition, value.controller, value.issuer, value.target
        )
        condition_invalid = (
            rights != born
            or value.principal != rights.handler
            or value.controller not in game.scene(c, value.cast.channel)["participants"]
        )
    elif value.origin_kind == "stim_sex":
        from girlframe.services.m3_stim_npc import order_authority as stim_authority

        condition_invalid = (
            stim_authority(game, c, original, value.issuer, value.target, effect_id=value.condition)
            is None
        )
    elif value.origin_kind == "npc_flirt":
        from girlframe.services.m3_npc_flirt import cannot_refuse

        condition_invalid = (
            cannot_refuse(game, c, original, value.target, value.issuer) != value.condition
        )
    elif value.origin_kind == "secretary":
        from girlframe.services.m3_secretary import prove_order

        prove_order(game, c, state, value)
        condition_invalid = False
    elif value.origin_kind == "am_secret":
        from girlframe.services.m3_am_scrutinized import prove_order_grant

        prove_order_grant(game, c, state, value)
        condition_invalid = False
    elif value.origin_kind == "harpy_echoes":
        from girlframe.services.m3_harpy_echoes import authority as echoes_authority
        from girlframe.services.m3_harpy_echoes import voices as known_voices

        echoes_authority(
            game,
            c,
            original,
            value.issuer,
            value.target,
            value.controller,
            condition=value.condition,
        )
        condition_invalid = (
            value.voice is not None
            and known_voices(game, c, original, value.cast, value.controller).get(value.voice)
            != value.voice_label
        )
    else:
        condition = next((x for x in state.alpha_broken if x.id == value.condition), None)
        birth = _condition(game, c, original, value.issuer, value.target)
        condition_invalid = (
            birth.id != value.condition
            or condition is None
            or condition.subject != value.target
            or condition.inflictor != value.issuer
            or condition.source_event != birth.source_event
            or condition.removed_event is not None
            and (removal_action is None or condition.removed_action != removal_action)
        )
    if (
        approval is None
        or value.registry != approval.registry_sha256
        or audit is None
        or audit.kind != "m3.npc_order_issued"
        or audit.actor_id != str(value.controller)
        or recorded is None
        or rules.Order.model_validate_json(recorded["body"]) != value
        or value.origin_kind != "secretary"
        and actual.controller != value.controller
        or recipient.controller != int(value.target.entity)
        or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
        or condition_invalid
    ):
        raise WorkflowError("Recover the original NPC, recipient, cast and order authority")


def order(game: GameService, c: Connection, action: dict[str, Any]) -> rules.Order:
    identity = action["data"].get("order_id") or action["data"].get("prepared", {}).get("order_id")
    raw = c.scalar(
        sa.select(t.m2["m2_orders"].c.body_json).where(
            t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_orders"].c.id == identity,
        )
    )
    body = json.loads(raw) if raw else {}
    scope = body.get("ranked_order") or body.get("npc_order")
    if not scope:
        raise WorkflowError("Recover the actual source order.")
    value = rules.Order.model_validate_json(json.dumps(scope))
    if (
        action["data"].get(value.scope) != value.model_dump(mode="json")
        or body.get("text") != value.instruction
        or action["actor_id"] != value.target.entity
        or int(action["channel_id"]) != value.cast.channel
        or action["scene_id"] != value.cast.id
        or value.origin_kind == "npc_handler"
        and any(
            action["data"].get(k) != value.audience() for k in ("private_audience", "participants")
        )
        or action["data"]["play"] == "receive_orders"
        and (action["id"] != value.action or action["data"].get("order_text") != value.instruction)
        or action["data"]["play"] != "receive_orders"
        and (action["data"]["play"] != "disobey_orders" or action["parent_id"] != value.action)
    ):
        raise WorkflowError("The actual original NPC Order binding changed")
    return value


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    value = order(game, c, action)
    _access(game, c, viewer, value.origin_kind)
    if viewer.user_id not in action["data"]["participants"]:
        raise WorkflowError("Only the original source table owns this NPC Order response")
    source(game, c, load_state(c, game.store.campaign_id), value, removal_action=action["id"])


def prepare(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    channel: int,
    prepared: PlayInput,
) -> dict[str, Any] | None:
    if prepared.play != "disobey_orders" or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    if not (parent["data"].get("npc_order") or parent["data"].get("ranked_order")):
        return None
    authorize(game, c, viewer, parent)
    value = order(game, c, parent)
    if value.target.entity != str(viewer.user_id) or prepared.order_id != value.id:
        raise WorkflowError("Only this original Pilot may refuse this exact NPC order")
    if channel != value.cast.channel:
        raise WorkflowError("Use the actual original NPC Order scene")
    _allow_refusal(game, c, state, value)
    return value.model_dump(mode="json")


def _allow_refusal(game: GameService, c: Connection, state: GameState, value: rules.Order) -> None:
    if value.origin_kind == "rebel_voice" and value.principal is not None:
        from girlframe.engine.m3_harpy_flirt import assert_can_refuse

        assert_can_refuse(state, value.target, value.principal)
        if any(
            x.kind == "cannot_refuse_until_tag_resolved"
            and x.state == "pending"
            and str(x.owner) == value.target.entity
            and str(x.target) == value.principal.entity
            for x in state.obligations
        ):
            raise WorkflowError("COMPULSION: resolve the owed Tag before refusing this Order.")
    if value.origin_kind == "npc_flirt":
        from girlframe.services.m3_npc_flirt import cannot_refuse

        if cannot_refuse(game, c, state, value.target, value.issuer) is not None:
            raise WorkflowError("Resolve the actual NPC-given Tag before refusing this NPC")


def valid_order(
    game: GameService,
    c: Connection,
    state: GameState,
    owner: int,
    channel: int,
    row: dict[str, Any],
) -> bool:
    body = json.loads(row["body_json"])
    scope = body.get("ranked_order") or body.get("npc_order")
    if not scope:
        return False
    value = rules.Order.model_validate_json(json.dumps(scope))
    source(game, c, state, value)
    if (
        row["issuer_id"] != value.issuer.entity
        or row["target_id"] != str(owner)
        or value.target.entity != str(owner)
        or row["id"] != value.id
        or row["state"] != "disobey"
        or channel != value.cast.channel
    ):
        raise WorkflowError("Use only this original recipient's actual refused NPC Order")
    _allow_refusal(game, c, state, value)
    parent = game.action(c, value.action)
    if parent["data"].get(value.scope) != value.model_dump(mode="json"):
        raise WorkflowError("Recover the original NPC Order action")
    return True


def removable(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorRef, ActorRef]:
    value = order(game, c, action)
    source(game, c, state, value)
    if action["data"]["play"] != "disobey_orders" or action["parent_id"] != value.action:
        raise WorkflowError("Only the genuine original Disobey may remove this NPC-source Broken")
    return value.target, value.issuer


class NpcOrderService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def ranked_preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, "ranked")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            issuer, _ = ranked_issuer(state, cast, viewer.user_id)
            targets = []
            if not self.game.pending_actions(c):
                for role in cast.roles:
                    sheet = state.sheets.get(role.actor.entity)
                    if (
                        role.actor.kind == "pilot"
                        and role.actor.entity == str(role.controller)
                        and sheet is not None
                        and sheet.character_id == role.actor.incarnation
                        and higher(state, viewer.user_id, role.controller)
                    ):
                        targets.append((role.actor.entity, sheet.callsign))
            return {
                "revision": state.revision,
                "issuer": issuer.model_dump(mode="json"),
                "targets": targets,
            }

    def handler_recipients(
        self, viewer: GuildViewer, channel: int, issuer: ActorRef
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, "npc_handler")
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            targets = {}
            bound = profiles(c, self.store.campaign_id)
            for role in cast.roles:
                if role.actor.kind != "pilot":
                    continue
                try:
                    npc_handler_authority(
                        self.game, c, state, cast, issuer, role.actor, viewer.user_id
                    )
                    targets[role.actor.entity] = resolve(
                        state, role.actor, bound, require_current_profile=False
                    ).label
                except (ValueError, WorkflowError):
                    continue
            return dict(revision=state.revision, targets=targets)

    def preview(
        self,
        viewer: GuildViewer,
        channel: int,
        target: int,
        *,
        origin_kind: rules.Origin = "broken",
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, origin_kind)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            if str(target) not in state.sheets:
                return dict(revision=state.revision, issuers=[])
            recipient = ActorRef(
                kind="pilot", entity=str(target), incarnation=state.sheets[str(target)].character_id
            )
            issuers = []
            for role in cast.roles:
                issuer_kind = "external_pilot" if origin_kind == "harpy_echoes" else "npc"
                if role.actor.kind != issuer_kind or role.controller != viewer.user_id:
                    continue
                try:
                    if origin_kind == "harpy_echoes":
                        from girlframe.services.m3_harpy_echoes import authority as echoes_authority

                        condition_id = echoes_authority(
                            self.game,
                            c,
                            state,
                            role.actor,
                            recipient,
                            viewer.user_id,
                        )
                    elif origin_kind == "stim_sex":
                        from girlframe.services.m3_stim_npc import order_authority as stim_authority

                        effect = stim_authority(self.game, c, state, role.actor, recipient)
                        if effect is None:
                            continue
                        condition_id = effect.id
                    elif origin_kind == "npc_flirt":
                        from girlframe.services.m3_npc_flirt import cannot_refuse

                        flirt_condition = cannot_refuse(self.game, c, state, recipient, role.actor)
                        if flirt_condition is None:
                            continue
                        condition_id = flirt_condition
                    elif origin_kind == "npc_handler":
                        condition_id = npc_handler_authority(
                            self.game, c, state, cast, role.actor, recipient, viewer.user_id
                        )
                    else:
                        condition_id = _condition(self.game, c, state, role.actor, recipient).id
                except (ValueError, WorkflowError):
                    continue
                if not any(x.actor == recipient for x in cast.roles):
                    continue
                issuers.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        label=resolve(state, role.actor, ()).label,
                        condition=condition_id,
                    )
                )
            result = dict(revision=state.revision, issuers=issuers)
            if origin_kind == "harpy_echoes" and issuers:
                from girlframe.services.m3_harpy_echoes import voices as known_voices

                result["voices"] = [
                    dict(ref=ref.model_dump(mode="json"), label=label)
                    for ref, label in known_voices(
                        self.game, c, state, cast, viewer.user_id
                    ).items()
                ]
            return result

    def issue(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        issuer: ActorRef,
        target: int,
        expected: int,
        text: str,
        *,
        origin_kind: rules.Origin = "broken",
        source_effect: str | None = None,
        voice: ActorRef | None = None,
    ) -> dict[str, Any]:
        if source_effect is not None and origin_kind not in ("stim_sex", "rebel_voice"):
            raise WorkflowError("This Order does not accept an exact source effect")
        if voice is not None and origin_kind != "harpy_echoes":
            raise WorkflowError("Only Echoes can choose an imitated voice with this Order")
        if origin_kind not in (
            "broken",
            "am_secret",
            "secretary",
            "npc_flirt",
            "stim_sex",
            "rebel_voice",
            "harpy_echoes",
            "npc_handler",
            "ranked",
        ):
            raise WorkflowError("Use only an implemented actual order source")
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("State the actual direct order in 1–1200 characters")

        ranked = origin_kind == "ranked"
        event_kind = "m3.ranked_order_issued" if ranked else "m3.npc_order_issued"

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_sentinel import require_communication

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            cast = _cast(self.game, c, state, channel)
            if str(target) not in state.sheets:
                raise WorkflowError("Choose the actual active original Pilot receiving this order")
            recipient = ActorRef(
                kind="pilot", entity=str(target), incarnation=state.sheets[str(target)].character_id
            )
            principal = None
            voice_label = None
            if ranked:
                actual, condition_id = ranked_issuer(state, cast, viewer.user_id)
                if issuer != actual or not higher(state, viewer.user_id, target):
                    raise WorkflowError("Only the original ranked superior can issue this order.")
            elif origin_kind == "harpy_echoes":
                from girlframe.services.m3_harpy_echoes import authority as echoes_authority
                from girlframe.services.m3_harpy_echoes import voices as known_voices

                condition_id = echoes_authority(
                    self.game,
                    c,
                    state,
                    issuer,
                    recipient,
                    viewer.user_id,
                )
                if voice is not None:
                    voice_label = known_voices(self.game, c, state, cast, viewer.user_id).get(voice)
                    if voice_label is None:
                        raise WorkflowError("Choose an actual known voice from the original cast")
            elif origin_kind == "rebel_voice":
                from girlframe.services.m3_rebel_voice import authority as voice_authority

                if viewer.user_id not in scene["participants"]:
                    raise WorkflowError("Use the voice only in a scene you are authorized to view")
                rights = voice_authority(
                    self.game, c, state, source_effect or "", viewer.user_id, issuer, recipient
                )
                condition_id, principal = rights.id, rights.handler
            elif origin_kind == "stim_sex":
                from girlframe.services.m3_stim_npc import order_authority as stim_authority

                effect = stim_authority(
                    self.game, c, state, issuer, recipient, effect_id=source_effect
                )
                if effect is None:
                    raise WorkflowError("Use the original NPC's actual unexpired drug authority")
                condition_id = effect.id
            elif origin_kind == "npc_flirt":
                from girlframe.services.m3_npc_flirt import cannot_refuse

                flirt_condition = cannot_refuse(self.game, c, state, recipient, issuer)
                if flirt_condition is None:
                    raise WorkflowError("Use the actual NPC-given unresolved Tag source")
                condition_id = flirt_condition
            elif origin_kind == "secretary":
                from girlframe.services.m3_secretary import order_authority

                authority = order_authority(self.game, c, state, issuer, recipient, viewer.user_id)
                condition_id = authority.id
                principal = authority.handler
            elif origin_kind == "am_secret":
                from girlframe.services.m3_am_scrutinized import secret_authority

                condition_id = secret_authority(self.game, c, state, issuer, recipient).id
            elif origin_kind == "npc_handler":
                condition_id = npc_handler_authority(
                    self.game, c, state, cast, issuer, recipient, viewer.user_id
                )
            else:
                condition_id = _condition(self.game, c, state, issuer, recipient).id
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or not ranked and origin_kind != "rebel_voice"
                and not any(
                    x.actor == issuer
                    and (origin_kind == "secretary" or x.controller == viewer.user_id)
                    for x in cast.roles
                )
                or not any(x.actor == recipient and x.controller == target for x in cast.roles)
            ):
                raise WorkflowError("STALE_NPC_ORDER: reopen the original NPC and recipient")
            require_communication(c, self.store.campaign_id, state, issuer, (recipient,))
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: finish the actual pending Play")
            event, action, identity = str(uuid4()), str(uuid4()), str(uuid4())
            approval = self.store.policy.m3_approval
            value = rules.Order(
                id=identity,
                action=action,
                issuer=issuer,
                target=recipient,
                controller=viewer.user_id,
                condition=condition_id,
                origin_kind=origin_kind,
                event=event,
                cast=cast,
                registry=approval.registry_sha256 if approval and not ranked else None,
                instruction=text,
                principal=principal,
                voice=voice,
                voice_label=voice_label,
            )
            c.execute(
                t.m2["m2_orders"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    issuer_id=issuer.entity,
                    target_id=str(target),
                    channel_id=str(channel),
                    state="awaiting_response",
                    body_json=json.dumps(
                        {"text": text, value.scope: value.model_dump(mode="json")}
                    ),
                )
            )
            table = value.audience()
            handler = active_handler(state)
            data = dict(
                play="receive_orders",
                order_id=identity,
                order_text=text,
                participants=table,
                character_ids={
                    str(x.controller): x.actor.incarnation
                    for x in cast.roles
                    if x.actor.kind == "pilot"
                },
                handler=state.handler,
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                tag_context=dict(
                    actor=recipient.model_dump(mode="json"),
                    handler=handler.model_dump(mode="json") if handler else None,
                    gm_controller=state.handler,
                    table=table,
                    cast=cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(cast),
                ),
            )
            if origin_kind == "npc_handler":
                data["private_audience"] = table
            data[value.scope] = value.model_dump(mode="json")
            from girlframe.services.m3_recovery import enable

            enable(self.game, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=action,
                    actor_id=str(target),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            values = dict(
                action_id=action, state="acquiring", body_json="{}", lease_until=0, claim_token=None
            )
            locks = t.m2["m2_locks"]
            if lock:
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            state.facts.append(
                dict(
                    kind=rules.FACT_KINDS[origin_kind],
                    id=identity,
                    body=value.model_dump_json(),
                )
            )
            if origin_kind == "secretary":
                from girlframe.services.m3_secretary import record_authority

                record_authority(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                event_kind,
                state,
                event_id=event,
                action_id=action,
                order_id=identity,
            )
            return dict(action_id=action, order_id=identity)

        return self.store._write(
            viewer,
            key,
            event_kind,
            dict(
                channel=channel,
                issuer=issuer.model_dump(mode="json"),
                target=target,
                expected=expected,
                text=text,
            )
            | (dict(origin_kind=origin_kind) if origin_kind != "broken" else {})
            | (dict(source_effect=source_effect) if source_effect is not None else {})
            | (dict(voice=voice.model_dump(mode="json")) if voice is not None else {}),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer, origin_kind),
        )
