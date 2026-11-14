"""Private source-proved Void resolution, shared by real Defeat and Dive Deep sources."""

import hashlib
import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_physical as physical
from girlframe.engine import m3_void as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, owned_refs, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_void_state import HarpyAsset, RebirthChoice, VoidThreshold
from girlframe.engine.m3_world_state import Gorgon
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("defeat_void_threshold", "void_threshold")


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source(
    game: GameService, c: Connection, identity: str
) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
    table = t.m3["m3_required_work"]
    rows = list(
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
                table.c.kind.in_(KINDS),
            )
            .order_by(table.c.revision)
        ).mappings()
    )
    if not rows:
        raise WorkflowError("This actual Void consequence is unavailable.")
    first, current = dict(rows[0]), dict(rows[-1])
    body, latest = json.loads(first["body_json"]), json.loads(current["body_json"])
    try:
        actor = ActorRef.model_validate_json(json.dumps(body["owner"]))
        family = body["details"]["family"]
        if (
            actor.kind != "pilot"
            or body["character"] != actor.incarnation
            or family not in ("girl", "frame")
            or first["revision"] != 1
            or first["owner_id"] != actor.entity
            or body["source_pdf"] != 19
        ):
            raise ValueError()
        if any(
            latest.get(k) != body.get(k)
            for k in ("owner", "character", "details", "source_action", "source_pdf")
        ):
            raise ValueError()
        if current["revision"] > 1 and current["state"] == "pending":
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == current["event_id"],
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(audit["payload_json"]) if audit else {}
            if (
                audit is None
                or audit["kind"] != "m3.void_response"
                or metadata.get("work_id") != identity
                or metadata.get("pending_sha256") != _digest(latest)
            ):
                raise ValueError()
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == first["event_id"],
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        sheet = proof.sheets.get(actor.entity) if proof else None
        from girlframe.engine.m3_janus_storage import effective_assets, for_family

        assets = [x for x in effective_assets(proof, actor) if x.family == family] if proof else []
        if (
            sheet is None
            or sheet.character_id != actor.incarnation
            or not assets
            or not all(x.void for x in assets)
        ):
            raise ValueError()
        from girlframe.services.m3_sup import prove_growth

        if proof is not None:
            prove_growth(game, c, proof, actor, first["event_id"])
        if proof and for_family(proof, actor, family):
            from girlframe.services.m3_janus_storage import prove as prove_stored_point

            for point in for_family(proof, actor, family):
                prove_stored_point(game, c, proof, point)
        if body.get("reason") in (
            "supply_drop_expiry",
            "budget_removal",
            "ankou_feedback",
            "ankou_feedback_sequence",
            "ankou_processor_unlink",
            "consume_partake",
            "consume_starvation_expiry",
            "doctor_wings",
        ):
            from girlframe.services.m3_asset_loss import prove_loss_work

            prove_loss_work(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "am_body_adjustment":
            from girlframe.services.m3_am_body_consequences import (
                prove_void_source as prove_am_body_void_source,
            )

            prove_am_body_void_source(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "wyvern_renovation":
            from girlframe.services.m3_wyvern_support import prove_renovation_void

            prove_renovation_void(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "budget_cleanup":
            from girlframe.services.m3_budget_cleanup import prove_void_source as prove_cleanup

            prove_cleanup(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "janus_storage_replug":
            from girlframe.services.m3_janus_storage import prove_replug

            prove_replug(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "janus_core_freed":
            from girlframe.services.m3_janus_requisitions import prove_freed_core_void

            prove_freed_core_void(c, game, first, body, actor)
            return current, body, actor
        if body.get("reason") == "janus_battery":
            from girlframe.services.m3_janus_play import prove_void_source as prove_battery_void

            prove_battery_void(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "item_transfer":
            from girlframe.services.m3_items import new_void_families, prove_transfer

            before, after, transfer = prove_transfer(c, game, body["transfer"])
            action = (
                game.action(c, transfer.action) if transfer.source_kind != "npc_damage" else None
            )
            if transfer.source_kind == "npc_damage":
                from girlframe.services.m3_battle_npc import NpcDamageService

                parent = NpcDamageService(game.store)._row(c, transfer.source_work or "")
                actual_source, actual_receiver = NpcDamageService(game.store)._proof(c, parent)
                fact = next(
                    (
                        x
                        for x in after.facts
                        if x.get("kind") == "npc_asset_replacement"
                        and x.get("work") == transfer.source_work
                        and x.get("effect") == "take_item"
                        and x.get("event") == transfer.event
                    ),
                    None,
                )
                if (
                    body.get("item_source") != "npc_damage"
                    or body.get("source_work") != transfer.source_work
                    or json.loads(parent["body_json"]).get("source_action")
                    != body.get("source_action")
                    or transfer.action != (body.get("source_action") or transfer.source_work)
                    or actual_source != transfer.source
                    or actual_receiver != transfer.recipient
                    or fact is None
                ):
                    raise ValueError()
            elif transfer.source_kind == "enforcer_snoop":
                meta = action["data"].get("snoop") if action else None
                if (
                    meta is None
                    or transfer.id not in meta.get("transfers", [])
                    or meta.get("physical_event") != transfer.event
                    or body.get("item_source") != "enforcer_snoop"
                    or body.get("source_action") != transfer.action
                    or transfer.source.model_dump(mode="json") != meta.get("target")
                    or transfer.recipient.model_dump(mode="json") != meta.get("actor")
                ):
                    raise ValueError()
            else:
                if action is None:
                    raise ValueError()
                meta = action["data"].get("enforcement")
                record = (
                    next((x for x in meta.get("item_void", []) if x["id"] == identity), None)
                    if meta
                    else None
                )
                if (
                    record is None
                    or record["owner"] != actor.model_dump(mode="json")
                    or record["transfer"] != transfer.id
                    or transfer.source_kind != "enforcement_initiative"
                    or body.get("source_action") != transfer.action
                ):
                    raise ValueError()
            if (
                transfer.event != first["event_id"]
                or actor not in (transfer.source, transfer.recipient)
                or actor not in new_void_families(before, after)
                or family != "girl"
            ):
                raise ValueError()
            return current, body, actor
        if body.get("reason") == "call_guest":
            from girlframe.services.m3_mockingbird_communion import prove_call_guest_void

            prove_call_guest_void(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "mockingbird_sex":
            from girlframe.services.m3_mockingbird_effects import prove_void_source as prove_sex

            prove_sex(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "mockingbird_risk":
            from girlframe.services.m3_mockingbird import prove_void_source as prove_risk

            prove_risk(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "dormant_void":
            from girlframe.services.m3_battle_dormant import prove_void_source

            prove_void_source(game, c, first, body, actor)
            return current, body, actor
        if body.get("reason") == "physical_entry":
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == first["event_id"],
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(audit["payload_json"]) if audit else {}
            placed = (
                next((x for x in proof.placements if x.actor == actor), None) if proof else None
            )
            if (
                audit is None
                or audit["kind"] != "m3.cockpit_operated"
                or audit["actor_id"] != actor.entity
                or metadata.get("operation") not in ("sit", "pilot")
                or placed is None
                or placed.mode == "outside_frame"
                or placed.occupied_frame_owner is not None
                or placed.frame_instance != body["frame"]
                or placed.source_event != first["event_id"]
            ):
                raise ValueError()
            return current, body, actor
        action = game.action(c, body["source_action"])
        if action["data"]["play"] not in ("defeat", "dive_deep"):
            raise ValueError()
        if first["kind"] == "defeat_void_threshold":
            index = next(
                (
                    i
                    for i, x in enumerate(action["data"].get("defeat_followups", []))
                    if x["kind"] == "void_threshold"
                    and x["owner"] == body["owner"]
                    and x["details"]["family"] == family
                ),
                None,
            )
            if (
                action["actor_id"] != actor.entity
                or action["data"].get("defeat", {}).get("actor") != actor.model_dump(mode="json")
                or index is None
                or identity
                != str(uuid5(NAMESPACE_URL, "girlframe:defeat:" + action["id"] + ":" + str(index)))
            ):
                raise ValueError()
        else:
            from girlframe.services.m3_dive import prove_void_source

            prove_void_source(game, c, first, body, actor)
    except (ValueError, KeyError, TypeError, ImportError):
        raise WorkflowError(
            "SOURCE_VOID_MISSING: recover the actual original corruption consequence."
        ) from None
    return current, body, actor


def prepare_threshold(
    c: Connection, game: GameService, identity: str, state: GameState | None = None
) -> tuple[GameState, VoidThreshold]:
    row, body, actor = source(game, c, identity)
    state = load_state(c, game.store.campaign_id) if state is None else state
    existing = next((x for x in state.void_thresholds if identity in x.source_works), None)
    table = t.m3["m3_required_work"]
    event = c.scalar(
        sa.select(table.c.event_id).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == identity,
            table.c.revision == 1,
        )
    )
    if event is None:
        raise WorkflowError("Recover the original corruption event.")
    if existing is None:
        state, existing = rules.start_threshold(
            state,
            profiles(c, game.store.campaign_id),
            actor,
            body["details"]["family"],
            event,
            row["id"],
            source_action=body["source_action"],
        )
    latest = {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.kind.in_(KINDS),
                table.c.owner_id == actor.entity,
            )
            .order_by(table.c.revision)
        ).mappings()
    }
    if existing.stage not in rules.FINAL:
        for sibling in latest.values():
            if sibling["state"] != "pending" or sibling["id"] in existing.source_works:
                continue
            _, sibling_body, sibling_actor = source(game, c, sibling["id"])
            if sibling_actor != actor:
                continue
            first_event = c.scalar(
                sa.select(table.c.event_id).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == sibling["id"],
                    table.c.revision == 1,
                )
            )
            if first_event is None:
                raise WorkflowError("Recover the actual related corruption source.")
            state, existing = rules.start_threshold(
                state,
                profiles(c, game.store.campaign_id),
                actor,
                sibling_body["details"]["family"],
                first_event,
                sibling["id"],
                source_action=sibling_body["source_action"],
            )
    return state, existing


def complete(
    c: Connection,
    game: GameService,
    value: VoidThreshold,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    if value.stage not in rules.FINAL:
        return
    if value.stage == "escaped" and value.gorgon is not None:
        table = t.m3["m3_required_work"]
        replacement = str(uuid5(NAMESPACE_URL, "girlframe:void-frame-replacement:" + value.id))
        if not c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == replacement)
            .limit(1)
        ):
            from girlframe.services.m3_work import related

            related(
                c,
                game.store,
                dict(campaign_id=game.store.campaign_id, campaign_context=True),
                replacement,
                int(value.actor.entity),
                int(value.actor.entity),
                "void_frame_replacement",
                dict(
                    owner=value.actor.model_dump(mode="json"),
                    character=value.actor.incarnation,
                    frame=value.frame_instance,
                    source_threshold=value.id,
                    source_gorgon=value.gorgon.model_dump(mode="json"),
                    source_pdf=19,
                    reason="involuntary_void_frame_loss",
                    next_off_duty="true",
                    immediate=False,
                ),
                event,
            )
    completed = []
    for identity in value.source_works:
        row, body, _ = source(game, c, identity)
        if row["state"] == "resolved":
            continue
        _append(
            c,
            row,
            event,
            json.loads(row["body_json"])
            | dict(
                threshold=value.id,
                resolution=value.stage,
                actual_actor=value.resulting_actor.model_dump(mode="json")
                if value.resulting_actor
                else None,
            ),
            resolved=True,
        )
        completed.append((identity, row, body))
    from girlframe.services.m3_void_keep import complete_keep_continuations

    complete_keep_continuations(game, c, value, event, viewer, key)
    for identity, row, body in completed:
        if row["kind"] == "defeat_void_threshold":
            from girlframe.services.m3_defeat import complete_void_continuation as defeat_complete

            defeat_complete(game, c, identity, event, viewer, key)
        elif body.get("reason") == "item_transfer":
            if body.get("item_source") == "npc_damage":
                from girlframe.services.m3_battle_npc import complete_void_continuation

                complete_void_continuation(game, c, identity, event, viewer, key)
            elif body.get("item_source") == "enforcer_snoop":
                from girlframe.services.m3_enforcer_snoop import (
                    complete_item_void as snoop_complete,
                )

                snoop_complete(game, c, identity, event, viewer, key)
            else:
                from girlframe.services.m3_enforcement_initiative import complete_item_void

                complete_item_void(game, c, identity, event)
        elif body.get("reason") == "janus_battery":
            from girlframe.services.m3_janus_play import (
                complete_void_continuation as complete_battery,
            )

            complete_battery(game, c, identity, event, viewer, key)
        elif body.get("reason") == "janus_storage_replug":
            from girlframe.services.m3_janus_storage import complete_replug

            complete_replug(game, c, identity, event, viewer, key)
        elif body.get("reason") == "call_guest":
            from girlframe.services.m3_mockingbird_communion import complete_call_guest_void

            complete_call_guest_void(game, c, identity, event, viewer, key)
        elif body.get("reason") == "mockingbird_sex":
            from girlframe.services.m3_mockingbird_effects import (
                complete_void_continuation as complete_sex,
            )

            complete_sex(game, c, identity, event, viewer, key)
        elif body.get("reason") == "mockingbird_risk":
            from girlframe.services.m3_mockingbird import (
                complete_void_continuation as complete_risk,
            )

            complete_risk(game, c, identity, event, viewer, key)
        elif body.get("reason") == "dormant_void":
            from girlframe.services.m3_battle_dormant import complete_void

            complete_void(game, c, identity, event, viewer, key)
        elif body.get("reason") in ("supply_drop_expiry", "budget_removal", "doctor_wings"):
            # These actual loss sources have no synthetic parent Play; source-scoped
            # required work was resolved above by the real owned Void outcome.
            continue
        elif body.get("reason") in ("ankou_feedback_sequence", "ankou_processor_unlink"):
            from girlframe.services.m3_ankou import synchronize_events as sync_ankou_effects

            sync_ankou_effects(game, c, event)
        elif body.get("reason") == "wyvern_renovation":
            from girlframe.services.m3_wyvern_support import synchronize as sync_renovation

            sync_renovation(game, c, event)
        elif body.get("reason") in ("consume_partake", "consume_starvation_expiry"):
            from girlframe.services.m3_consume import resume_pending

            resume_pending(game, c, event)
        elif body.get("reason") == "budget_cleanup":
            from girlframe.services.m3_budget_cleanup import complete_void as complete_cleanup

            complete_cleanup(game, c, identity, event, viewer, key)
        elif body.get("reason") == "am_body_adjustment":
            from girlframe.services.m3_am_body_consequences import complete_void_continuation

            complete_void_continuation(game, c, identity, event, viewer, key)
        elif body.get("reason") != "physical_entry":
            from girlframe.services.m3_dive import complete_void_continuation as dive_complete

            dive_complete(game, c, identity, event, viewer, key)


def _append(
    c: Connection, row: dict[str, Any], event: str, body: dict[str, Any], *, resolved: bool = False
) -> None:
    c.execute(
        t.m3["m3_required_work"]
        .insert()
        .values(
            **{
                k: v
                for k, v in row.items()
                if k not in ("revision", "event_id", "body_json", "state")
            },
            revision=row["revision"] + 1,
            event_id=event,
            body_json=json.dumps(body, sort_keys=True),
            state="resolved" if resolved else "pending",
        )
    )


class VoidService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _handler(self, c: Connection, viewer: GuildViewer) -> None:
        HandlerService(self.store).authorize(c, viewer)
        if load_state(c, self.store.campaign_id).handler != viewer.user_id:
            raise WorkflowError("Only the actual current Handler owns this factual consequence.")

    def _owned_plays(self, state: GameState, actor: ActorRef) -> list[dict[str, str]]:
        from girlframe.engine.m3_medical import rule_book

        sheet = state.sheets[actor.entity]
        result = []
        for entry in load_registry().entries:
            book = rule_book(entry.id)
            if (
                book is not None
                and entry.kind in ("play", "mechanic")
                and has_rule(sheet, entry.id, book)
            ):
                result.append(dict(id=entry.id, name=entry.title))
        if sheet.frame_runtime:
            result.extend(dict(id=x, name=x) for x in sheet.frame_runtime.acquired_rules)
        frame = sheet.frame.casefold().replace("-", "").replace(" ", "")
        for entry in load_registry().entries:
            parts = entry.id.split(".")
            if (
                len(parts) > 2
                and entry.scope == "frame"
                and parts[1].replace("-", "") == frame
                and entry.kind in ("play", "mechanic")
            ):
                result.append(dict(id=entry.id, name=entry.title))
        from girlframe.engine.m3_enforcer_requisitions import owned_plays as enforcer_plays

        result.extend(enforcer_plays(state, actor, load_registry()))
        return list({x["id"]: x for x in result}.values())

    def _view(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.engine.m3_janus_storage import effective_assets

        self.game.authorize(c, viewer, game=False)
        row, body, actor = source(self.game, c, identity)
        state, value = prepare_threshold(c, self.game, identity)
        pending = json.loads(row["body_json"])
        owner = actor.entity == str(viewer.user_id)
        handler = False
        try:
            self._handler(c, viewer)
            handler = True
        except WorkflowError:
            pass
        guardian = value.guardian or (
            ActorRef.model_validate_json(json.dumps(pending["guardian"]))
            if pending.get("guardian")
            else None
        )
        guardian_owned = (
            guardian in owned_refs(state, viewer.user_id, profiles(c, self.store.campaign_id))
            if guardian
            else False
        )
        if not owner and not handler and not guardian_owned:
            raise WorkflowError("This private Void consequence belongs to its actual participants.")
        from girlframe.services.m3_learned_plays import prove_risk_ward

        learned_ward = prove_risk_ward(self.game, c, state, value)
        result: dict[str, Any] = dict(
            id=identity,
            revision=row["revision"],
            game_revision=state.revision,
            expected=fingerprint(value),
            stage=value.stage,
            actor=actor.model_dump(mode="json"),
            owner=owner,
            handler=handler,
            guardian_owned=guardian_owned,
            guardian=guardian.model_dump(mode="json") if guardian else None,
            pending_escape=pending.get("damage_asset"),
            occupancy=pending.get("occupancy"),
            approach=pending.get("approach"),
            question=rules.QUESTIONS[len(value.answers)]
            if value.stage == "questions" and value.free_identity
            else None,
            needs_free=value.stage in ("allured", "enclosed", "questions")
            and value.free_identity is None,
            source_action=body["source_action"],
            threshold=value.model_dump(mode="json", exclude={"sheet_json"}),
            source_work=row["kind"],
            storage_unplug=next(
                (
                    x.id
                    for x in state.neural_connections
                    if owner
                    and value.storage_points
                    and x.caster == actor
                    and x.phase == "connected"
                ),
                None,
            ),
            protection_active=value.guardian is not None
            and value.protection_release_event is None
            and any(x.actor == actor and x.custody == value.guardian for x in state.placements),
        )
        if learned_ward is not None:
            result["learned_risk_ward"] = True
        if owner:
            from girlframe.engine.m3_learned_play_state import DefensiveRiskUse
            from girlframe.services.m3_learned_plays import defensive_risk_lessons

            result["defensive_risk_lessons"] = defensive_risk_lessons(self.game, c, state, value)
            if isinstance(learned_ward, DefensiveRiskUse):
                result["defensive_risk_use"] = learned_ward.model_dump(mode="json")
        if value.stage not in rules.FINAL:
            sheet = state.sheets.get(actor.entity)
            if sheet is None:
                raise WorkflowError(
                    "Recover the actual original Girl before resolving this threshold."
                )
            result["callsign"] = sheet.callsign
            if owner:
                try:
                    owned_plays = self._owned_plays(state, actor)
                except WorkflowError:
                    owned_plays = []
                result.update(
                    identities=[x.model_dump(mode="json") for x in sheet.identities],
                    tags=[x.model_dump(mode="json") for x in sheet.tags],
                    assets=[x.model_dump(mode="json") for x in effective_assets(state, actor)],
                    plays=owned_plays,
                    bonds=[
                        dict(
                            ref=(edge.second if edge.first == actor else edge.first).model_dump(
                                mode="json"
                            ),
                            depth=edge.depth,
                        )
                        for edge in state.actor_bonds
                        if actor in (edge.first, edge.second)
                    ],
                )
                candidates: list[dict[str, Any]] = []
                ownview = resolve(
                    state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                casts = list(state.scene_casts)
                if row["scene_id"] is not None:
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_cast import CastService
                    from girlframe.services.m3_missions import MissionService

                    channel = c.scalar(
                        sa.select(t.m2["m2_scenes"].c.channel_id).where(
                            t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                            t.m2["m2_scenes"].c.id == row["scene_id"],
                        )
                    )
                    if channel is not None:
                        try:
                            source_cast, _ = CastService(
                                ActorService(MissionService(self.store))
                            )._current(c, state, int(channel))
                            casts = [source_cast]
                        except WorkflowError:
                            casts = []
                for other in casts:
                    if not other.open:
                        continue
                    if not any(x.actor == actor for x in other.roles):
                        continue
                    for cast in other.roles:
                        if cast.actor == actor or any(
                            x["ref"] == cast.actor.model_dump(mode="json") for x in candidates
                        ):
                            continue
                        try:
                            view = resolve(
                                state,
                                cast.actor,
                                profiles(c, self.store.campaign_id),
                                require_current_profile=False,
                            )
                            if not (
                                ownview.cell is not None
                                and view.cell is not None
                                and view.cell != ownview.cell
                            ) and view.custody in (None, "free"):
                                candidates.append(
                                    dict(ref=cast.actor.model_dump(mode="json"), label=view.label)
                                )
                        except ValueError:
                            continue
                result["guardians"] = candidates
                if value.stage == "rebirth":
                    result["rebirth_choice"] = pending.get("rebirth_choice") or RebirthChoice(
                        assets=tuple(
                            HarpyAsset(**(x.model_dump() | {"void": True})) for x in sheet.assets
                        ),
                        account="My actual chosen irreversible rebirth",
                    ).model_dump(mode="json")
            if handler:
                result["frame_assets"] = [
                    x.model_dump(mode="json") for x in sheet.assets if x.family == "frame"
                ]
                result["frame_cell"] = next(
                    (x.frame_cell for x in state.placements if x.actor == actor), None
                )
                goals = []
                if result["frame_cell"] is not None:
                    goals.append(
                        dict(
                            id="frame-cell",
                            name="Original affected Frame's actual cell",
                            kind="cell",
                            cell=result["frame_cell"],
                        )
                    )
                if state.world:
                    goals.extend(
                        dict(id="location:" + x.id, name=x.name, kind="location", entity_id=x.id)
                        for x in state.world.locations
                    )
                    goals.extend(
                        dict(id="npc:" + x.id, name=x.name, kind="npc", entity_id=x.id)
                        for x in state.world.npcs
                    )
                result["gorgon_goals"] = goals
                result["gorgon_leaders"] = (
                    [dict(id=x.id, name=x.name) for x in state.world.gorgons if x.alive]
                    if state.world
                    else []
                )
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer, identity)

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        ids = c.scalars(
            sa.select(table.c.id)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.kind.in_(KINDS))
            .distinct()
        )
        result = []
        for identity in ids:
            try:
                view = self._view(c, viewer, identity)
                if view["stage"] not in rules.FINAL or view["protection_active"]:
                    result.append(
                        dict(
                            id=identity,
                            kind="m3_void_threshold",
                            title="Void transformation",
                            state=view["stage"],
                            revision=view["revision"],
                        )
                    )
            except (ValueError, WorkflowError):
                continue
        return result

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        expected: str,
        operation: Literal[
            "begin",
            "answer",
            "choose_escape",
            "escape",
            "protect",
            "accept_protection",
            "overgrown",
            "rebirth",
            "save_rebirth",
            "propose_occupancy",
            "confirm_occupancy",
            "abandoned",
            "propose_approach",
            "confirm_approach",
            "release_protection",
            "use_risk_lesson",
        ],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)
            view = self._view(c, viewer, identity)
            if operation in (
                "escape",
                "overgrown",
                "confirm_occupancy",
                "abandoned",
                "confirm_approach",
            ):
                self._handler(c, viewer)
            elif operation in ("accept_protection", "release_protection"):
                if not view["guardian_owned"]:
                    raise WorkflowError(
                        "Only the actual chosen guardian accepts this physical hold."
                    )
            elif not view["owner"]:
                raise WorkflowError("Only the original Girl owns these transformation choices.")

        def apply(c: Connection) -> dict[str, Any]:
            row, body, actor = source(self.game, c, identity)
            state, value = prepare_threshold(c, self.game, identity)
            if (
                (row["state"] != "pending" and operation != "release_protection")
                or row["revision"] != revision
                or state.revision != game_revision
                or fingerprint(value) != expected
            ):
                raise WorkflowError("STALE_VOID: reopen the actual original transformation.")
            current = json.loads(row["body_json"])
            event = str(uuid4())
            bindings = profiles(c, self.store.campaign_id)
            account = str(data.get("account", "")).strip()
            if not account or len(account) > 1200:
                raise WorkflowError("Describe this actual owned choice or factual consequence.")
            if operation == "use_risk_lesson":
                from girlframe.services.m3_learned_plays import activate_defensive_risk

                use = activate_defensive_risk(
                    self.game, c, state, value, data["lesson"], event, account
                )
                state = rules.apply_defensive_risk(state, bindings, value.id, use, event)
                current["defensive_risk_use"] = use.id
            elif operation == "release_protection":
                if value.guardian is None:
                    raise WorkflowError("This source has no actual protective guardian.")
                state = physical.release_protective_hold(
                    state, value.id, value.guardian, event, account
                )
            elif operation == "begin":
                state = rules.begin_questions(
                    state, bindings, value.id, data["identity"], event, account
                )
            elif operation == "propose_approach":
                if value.stage != "allured" or not any(
                    x.id == data["identity"] for x in state.sheets[actor.entity].identities
                ):
                    raise WorkflowError(
                        "The original Girl selects her actual stage-one arrival and Identity."
                    )
                current["approach"] = dict(
                    identity=data["identity"],
                    account=account,
                    expected=fingerprint(state),
                    identity_name=next(
                        x.name
                        for x in state.sheets[actor.entity].identities
                        if x.id == data["identity"]
                    ),
                )
            elif operation == "confirm_approach":
                proposed = current.get("approach")
                if not proposed:
                    raise WorkflowError(
                        "The original owner must first propose her actual completed arrival."
                    )
                # The proposal event changes revision only; actual facts stay exact.
                before = state.model_copy(update={"revision": state.revision - 1})
                if fingerprint(before) != proposed["expected"]:
                    raise WorkflowError(
                        "STALE_APPROACH: actual physical facts changed; ask the owner to repropose."
                    )
                state = rules.confirm_approach(
                    state, bindings, value.id, proposed["identity"], event, account
                )
            elif operation == "propose_occupancy":
                if value.stage != "physical_review" or data.get("mode") not in (
                    "outside_frame",
                    "inside_frame",
                    "piloting",
                ):
                    raise WorkflowError(
                        "Propose only this original body's genuinely unknown occupancy."
                    )
                current["occupancy"] = dict(
                    mode=data["mode"], account=account, owner=viewer.user_id
                )
            elif operation == "confirm_occupancy":
                proposed = current.get("occupancy")
                if not proposed or proposed["owner"] != int(actor.entity):
                    raise WorkflowError(
                        "The original owner must first describe her actual occupancy."
                    )
                state = rules.confirm_occupancy(
                    state,
                    bindings,
                    value.id,
                    proposed["mode"],
                    event,
                    account,
                    proposed_event=row["event_id"],
                )
            elif operation == "answer":
                if type(data.get("answer")) is not bool or data.get("honest") is not True:
                    raise WorkflowError(
                        "The original owner must honestly answer this actual question."
                    )
                state = rules.answer_question(
                    state, value.id, viewer.user_id, data["answer"], event, honest=True
                )
            elif operation == "choose_escape":
                if (
                    value.stage != "enclosed"
                    or value.family != "frame"
                    or not any(
                        x.id == data["asset"] and x.family == "girl" and not x.damaged
                        for x in state.sheets[actor.entity].assets
                    )
                ):
                    raise WorkflowError(
                        "Choose an actual undamaged Girl Asset for the printed escape."
                    )
                current["damage_asset"] = data["asset"]
            elif operation == "protect":
                guardian = ActorRef.model_validate_json(json.dumps(data["guardian"]))
                view = self._view(c, viewer, identity)
                if value.stage != "allured" or guardian.model_dump(mode="json") not in [
                    x["ref"] for x in view["guardians"]
                ]:
                    raise WorkflowError("Choose an actual present guardian before own-Frame entry.")
                current["guardian"] = guardian.model_dump(mode="json")
            elif operation == "accept_protection":
                guardian = ActorRef.model_validate_json(json.dumps(current["guardian"]))
                state = rules.prevent_entry(state, bindings, value.id, guardian, event, account)
            elif operation in ("escape", "overgrown", "abandoned"):
                gorgon = Gorgon.model_validate_json(json.dumps(data["gorgon"])).model_copy(
                    update={"position_event": event}
                )
                if operation == "abandoned":
                    state = rules.abandoned_frame(state, bindings, value.id, gorgon, event)
                elif operation == "escape":
                    state = rules.escape_frame(
                        state, bindings, value.id, current["damage_asset"], gorgon, event, account
                    )
                else:
                    profile = next(x for x in bindings if x.owner == int(actor.entity))
                    state = rules.overgrown_fate(
                        state,
                        value.id,
                        gorgon,
                        event,
                        account,
                        alive=data["alive"],
                        archive_id=str(uuid4()),
                        profile_id=profile.source_character_id or profile.character_id,
                        profile_revision=profile.profile_revision,
                    )
            elif operation == "save_rebirth":
                if value.stage != "rebirth":
                    raise WorkflowError("Only five honest no answers open rebirth choices.")
                choice = RebirthChoice.model_validate_json(json.dumps(data["choice"]))
                current["rebirth_choice"] = choice.model_dump(mode="json")
            elif operation == "rebirth":
                choice = RebirthChoice.model_validate_json(json.dumps(data["choice"]))
                profile = next(x for x in bindings if x.owner == int(actor.entity))
                plays = tuple(x["id"] for x in self._owned_plays(state, actor))
                state = rules.rebirth(
                    state,
                    bindings,
                    value.id,
                    event,
                    harpy_id=str(uuid4()),
                    new_vessel=str(uuid4()),
                    archive_id=str(uuid4()),
                    profile_id=profile.source_character_id or profile.character_id,
                    profile_revision=profile.profile_revision,
                    owned_plays=plays,
                    **choice.model_dump(exclude={"assets", "discarded_bonds"}),
                    assets=choice.assets,
                    discarded_bonds=choice.discarded_bonds,
                )
            else:
                raise WorkflowError("Unsupported actual transformation response.")
            value = rules.threshold(state, value.id)
            current["threshold"] = value.id
            defensive_metadata: dict[str, Any] = {}
            if operation == "use_risk_lesson":
                defensive_metadata.update(defensive_risk_use=use.id, lesson=use.lesson)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_response",
                state,
                event_id=event,
                work_id=identity,
                threshold=value.id,
                operation=operation,
                pending_sha256=_digest(current),
                **defensive_metadata,
            )
            if operation == "release_protection":
                _append(
                    c, row, event, current | dict(protection_release_event=event), resolved=True
                )
            elif value.stage in rules.FINAL:
                archive = next((x for x in state.career_archives if x.source_event == event), None)
                if archive:
                    from girlframe.services.m3_careers import synchronize_end

                    exclusions = list(value.source_works)
                    for work_id in value.source_works:
                        _, original_body, _ = source(self.game, c, work_id)
                        if original_body.get("source_action") is None:
                            continue
                        action = self.game.action(c, original_body["source_action"])
                        held = action["data"].get("defeat", {}).get("source_work")
                        if held:
                            exclusions.append(held)
                    synchronize_end(c, self.game, archive, exclude_work=tuple(exclusions))
                complete(c, self.game, value, event, viewer, key)
            else:
                _append(c, row, event, current | dict(threshold=value.id))
            return dict(id=identity, stage=value.stage, revision=revision + 1)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.void_response",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    expected=expected,
                    operation=operation,
                    data=data,
                ),
                apply,
                authorize=access,
                auto_audit=False,
            )
        except (ValueError, KeyError, StopIteration) as exc:
            raise WorkflowError(str(exc)) from None
