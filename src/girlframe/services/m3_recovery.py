"""Owned shared-Play recovery from actual transactional root/descendant evidence."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import PLAY_IDS
from girlframe.engine.m3_plays import HEAT_IDS
from girlframe.engine.m3_recovery_state import Interruption, SavedChoice, fingerprint
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def pending(game: "GameService", c: Connection, *, include_unrolled: bool = False) -> bool:
    table = t.m2["m2_actions"]
    return (
        c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.state == "aborted",
                sa.or_(
                    sa.and_(
                        sa.func.json_extract(table.c.body_json, "$.shared_recovery").is_not(None),
                        sa.or_(
                            sa.literal(include_unrolled),
                            sa.func.json_extract(table.c.body_json, "$.shared_recovery.known_roll")
                            == 1,
                        ),
                    ),
                    sa.and_(
                        sa.func.json_extract(table.c.body_json, "$.receipt").is_not(None),
                        sa.or_(
                            sa.func.json_extract(table.c.body_json, "$.m3_recovery").is_not(None),
                            sa.func.json_extract(table.c.body_json, "$.actor_recovery").is_not(
                                None
                            ),
                        ),
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def enable(game: "GameService", c: Connection, viewer: GuildViewer, data: dict[str, Any]) -> None:
    if pending(game, c, include_unrolled=True):
        raise WorkflowError(
            "REQUIRED_RECOVERY: resume or cancel the actual interrupted Play first."
        )
    approval = game.store.policy.m3_approval
    if approval is not None and "plays" in approval.subsystems and not data.get("m3"):
        from girlframe.services.m3_access import Access

        Access(game.store).authorize(c, viewer, "plays")
        data["m3_shared"] = {"registry": approval.registry_sha256}


def authorize(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    action: dict[str, Any],
    *,
    director_response: bool = False,
) -> None:
    meta = action["data"].get("m3_shared") or action["data"].get("shared_recovery")
    if meta is None:
        return
    from girlframe.services.m3_access import Access

    Access(game.store).authorize(c, viewer, "plays", director_response=director_response)
    approval = game.store.policy.m3_approval
    if approval is None or approval.registry_sha256 != meta.get("registry"):
        raise WorkflowError("M3_POLICY_CHANGED: recover the original shared Play approval first.")


def capture(
    game: "GameService", c: Connection, root: dict[str, Any], rows: list[dict[str, Any]], event: str
) -> dict[str, Interruption]:
    if root["data"].get("m3") or root["data"].get("actor_basic"):
        return {}
    actual = {row["id"]: game.action(c, row["id"]) for row in rows}
    protocol = root["data"].get("m3_shared") or next(
        (x["data"]["m3_shared"] for x in actual.values() if x["data"].get("m3_shared")), None
    )
    if protocol is None:
        return {}
    if root["id"] not in actual or any(x["data"].get("shared_recovery") for x in actual.values()):
        raise WorkflowError("Recover the existing actual interruption before aborting it again.")
    for child in actual.values():
        node, seen = child, set()
        while node["id"] != root["id"]:
            if node["id"] in seen or node["parent_id"] not in actual:
                raise WorkflowError("The actual pending response chain is inconsistent.")
            seen.add(node["id"])
            node = actual[node["parent_id"]]
        if child["scene_id"] != root["scene_id"] or child["channel_id"] != root["channel_id"]:
            raise WorkflowError("The response chain changed its actual scene.")
        receipt = child["data"].get("receipt")
        if receipt is not None:
            saved = c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == child["id"],
                )
            )
            if saved is None or json.loads(saved) != receipt:
                raise WorkflowError("Recover the original immutable roll receipt first.")
    known = any(x["data"].get("receipt") is not None for x in actual.values())
    feedback_committed = False
    for action in actual.values():
        if action["data"].get("ankou_feedback"):
            from girlframe.services.m3_ankou_feedback import prove as prove_feedback

            source = prove_feedback(
                game, c, load_state(c, game.store.campaign_id), action["data"]["ankou_feedback"]
            )
            if source.action != action["id"]:
                raise WorkflowError("Preserve the actual interrupted Feedback source.")
            feedback_committed = True
    cancellable = (
        not known
        and not feedback_committed
        and len(actual) == 1
        and (
            root["data"]["play"] in (*PLAY_IDS, *HEAT_IDS)
            or root["data"].get("gorgon_play", {}).get("started") is False
            or root["data"].get("leviathan_obsession", {}).get("started") is False
        )
        and not root["data"]["choices"]
    )
    choices = t.m2["m2_choices"]
    return {
        identity: Interruption(
            root=root["id"],
            event=event,
            registry=protocol["registry"],
            nodes=tuple(actual),
            known_roll=known,
            cancellable=cancellable,
            state=child["state"],
            body_sha256=fingerprint(child["data"]),
            choices=tuple(
                SavedChoice(
                    id=x["id"],
                    owner=x["actor_id"],
                    revision=x["revision"],
                    state=x["state"],
                    body_sha256=fingerprint(json.loads(x["body_json"])),
                )
                for x in c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.action_id == identity,
                        choices.c.state.in_(("pending", "submitted")),
                    )
                ).mappings()
            ),
        )
        for identity, child in actual.items()
    }


class RecoveryService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def saved(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            table = t.m2["m2_actions"]
            results = []
            for row in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.actor_id == str(viewer.user_id),
                    table.c.state == "aborted",
                    table.c.parent_id.is_(None),
                )
            ).mappings():
                meta = json.loads(row["body_json"]).get("shared_recovery")
                if meta is not None:
                    saved = Interruption.model_validate_json(json.dumps(meta))
                    results.append(
                        dict(
                            id=row["id"],
                            revision=row["revision"],
                            rolled=saved.known_roll,
                            cancellable=saved.cancellable,
                            play=json.loads(row["body_json"])["play"],
                            descendants=len(saved.nodes) - 1,
                        )
                    )
            return results

    def recover(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, *, cancel: bool = False
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.game.authorize(c, viewer, game=False)
            from girlframe.services.m3_access import Access

            action = self.game.action(c, identity)
            if action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import GorgonPlayService

                GorgonPlayService(self.game).authorize(c, viewer, action)
            elif action["data"].get("leviathan_obsession"):
                from girlframe.services.m3_leviathan_obsession import ObsessionService

                ObsessionService(self.game).authorize(c, viewer, action)
            else:
                Access(self.store).authorize(c, viewer, "plays")
            if action["actor_id"] != str(viewer.user_id) or action["parent_id"] is not None:
                raise WorkflowError("Only the actual root actor may recover this response chain.")
            authorize(
                self.game,
                c,
                viewer,
                action,
                director_response=bool(
                    action["data"].get("gorgon_play") or action["data"].get("leviathan_obsession")
                ),
            )

        def operation(c: Connection) -> dict[str, Any]:
            if not cancel:
                self.game.unpaused(c)
            root = self.game.action(c, identity)
            meta = root["data"].get("shared_recovery")
            if (
                type(expected) is not int
                or type(cancel) is not bool
                or meta is None
                or root["revision"] != expected
                or root["state"] != "aborted"
            ):
                raise WorkflowError("STALE_RECOVERY: reopen your actual interrupted root Play.")
            snapshot = Interruption.model_validate_json(json.dumps(meta))
            lock = self.game.lock(c, root["channel_id"])
            scene = self.game.scene(c, int(root["channel_id"]))
            if (
                lock is None
                or lock["state"] != "released"
                or lock["action_id"] != identity
                or snapshot.root != identity
                or scene["id"] != root["scene_id"]
            ):
                raise WorkflowError("Restore chat and retain the original scene before recovery.")
            event = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == snapshot.event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                event is None
                or event["kind"] != "m2.action_aborted"
                or json.loads(event["payload_json"]).get("action_id") != identity
            ):
                raise WorkflowError("Recover the actual original interruption source first.")
            if cancel and not snapshot.cancellable:
                if root["data"].get("ankou_feedback"):
                    raise WorkflowError(
                        "Committed Feedback costs and required choices cannot be discarded."
                    )
                raise WorkflowError(
                    "Known dice or prior responses cannot be discarded or refunded."
                )
            state = load_state(c, self.store.campaign_id)
            if not cancel and HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("Recover the actual original Handler appointment first.")
            choices = t.m2["m2_choices"]
            released_learning = False
            recovery_event = str(uuid4())
            for node in snapshot.nodes:
                action = self.game.action(c, node)
                data = dict(action["data"])
                child_meta = data.pop("shared_recovery", None)
                if child_meta is None:
                    raise WorkflowError("The original pending response chain changed.")
                saved = Interruption.model_validate_json(json.dumps(child_meta))
                if (
                    action["state"] != "aborted"
                    or saved.root != identity
                    or saved.event != snapshot.event
                    or saved.nodes != snapshot.nodes
                    or saved.registry != snapshot.registry
                    or saved.known_roll != snapshot.known_roll
                    or saved.cancellable != snapshot.cancellable
                    or fingerprint(data) != saved.body_sha256
                    or action["scene_id"] != root["scene_id"]
                    or action["channel_id"] != root["channel_id"]
                    or (
                        "prepared" in data and data["prepared"].get("parent") != action["parent_id"]
                    )
                ):
                    raise WorkflowError(
                        "The saved interruption evidence changed; recover it explicitly."
                    )
                if not cancel:
                    gorgon_chain = bool(root["data"].get("gorgon_play"))
                    leviathan_chain = bool(root["data"].get("leviathan_obsession"))
                    if leviathan_chain:
                        from girlframe.services.m3_leviathan_obsession import ObsessionService

                        ObsessionService(self.game).current(c, root)
                    elif gorgon_chain:
                        from girlframe.services.m3_gorgon_play import (
                            allowed_archived,
                            recovery_cast,
                        )

                        recovery_cast(self.game, c, state, root)
                        ancestor, seen = action, set()
                        while ancestor["id"] != root["id"]:
                            if (
                                ancestor["id"] in seen
                                or ancestor["parent_id"] not in snapshot.nodes
                            ):
                                raise WorkflowError("Recover the actual saved response ancestry")
                            seen.add(ancestor["id"])
                            ancestor = self.game.action(c, ancestor["parent_id"])
                        if action["data"].get("actor_basic"):
                            from girlframe.services.m3_actor_plays import ActorPlayService

                            actual = ActorPlayService(self.game).validate(c, state, action)
                            counter = action["data"].get("gorgon_counter_source")
                            if actual.controller != int(action["actor_id"]) or (
                                counter is not None
                                and actual.ref.model_dump(mode="json") != counter.get("actor")
                            ):
                                raise WorkflowError("Recover the original response body's role")
                        else:
                            self.game.action_characters(
                                c,
                                action,
                                state,
                                allowed_archived=allowed_archived(self.game, c, state, action),
                            )
                    else:
                        self.game.action_characters(c, action, state)
                    if (action["data"].get("battle") or {}).get(
                        "procedural_gm", action["data"]["handler"]
                    ) != state.handler:
                        raise WorkflowError("The original response Handler changed.")
                    if (
                        not gorgon_chain
                        and not leviathan_chain
                        and set(scene["participants"]) != set(action["data"]["participants"])
                    ):
                        raise WorkflowError("Recover the original scene participants first.")
                    if any(
                        not HandlerService(self.store)._member(c, uid)
                        for uid in action["data"]["participants"]
                    ):
                        raise WorkflowError(
                            "Recover the original participants' active memberships first."
                        )
                for item in saved.choices:
                    row = (
                        c.execute(
                            sa.select(choices).where(
                                choices.c.campaign_id == self.store.campaign_id,
                                choices.c.id == item.id,
                                choices.c.action_id == node,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if (
                        row is None
                        or row["state"] != "aborted"
                        or row["revision"] != item.revision
                        or row["actor_id"] != item.owner
                        or fingerprint(json.loads(row["body_json"])) != item.body_sha256
                    ):
                        raise WorkflowError("The original saved decision changed.")
                    if not cancel:
                        c.execute(
                            choices.update()
                            .where(
                                choices.c.campaign_id == self.store.campaign_id,
                                choices.c.id == item.id,
                            )
                            .values(state=item.state, revision=item.revision + 1)
                        )
                if cancel and (
                    action["data"].get("wyvern_pin_response")
                    or action["data"].get("wyvern_replacement")
                ):
                    from girlframe.services.m3_wyvern_combat import (
                        release_unrolled as release_counter,
                    )

                    released_learning = (
                        release_counter(self.game, c, state, action, key) or released_learning
                    )
                if cancel and (
                    action["data"].get("changeling") or action["data"].get("changeling_flirt")
                ):
                    from girlframe.services.m3_changeling import (
                        release_unrolled as release_changeling,
                    )

                    release_changeling(self.game, c, state, action)
                    released_learning = True
                if cancel and action["data"].get("changeling_child"):
                    from girlframe.services.m3_changeling_effects import (
                        release_child as release_changeling_child,
                    )

                    release_changeling_child(self.game, c, state, action)
                    released_learning = True
                if cancel and action["data"].get("bonded_rejection_child"):
                    from girlframe.services.m3_bonded_rejection import (
                        release_unrolled as release_rejection,
                    )

                    released_learning = (
                        release_rejection(self.game, c, state, action, recovery_event)
                        or released_learning
                    )
                if cancel and action["data"].get("npc_flirt"):
                    from girlframe.services.m3_npc_flirt import (
                        release_unrolled as release_npc_flirt,
                    )

                    released_learning = (
                        release_npc_flirt(self.game, c, state, action, recovery_event)
                        or released_learning
                    )
                if cancel and action["data"].get("void_frame_entry"):
                    from girlframe.services.m3_void_frame_entry import (
                        release_unrolled as release_entry_dive,
                    )

                    release_entry_dive(self.game, c, state, action, recovery_event)
                    released_learning = True
                if cancel and action["data"].get("ankou_effect_child"):
                    from girlframe.services.m3_required_plays import (
                        release_unrolled as release_required_play,
                    )

                    release_required_play(self.game, c, state, action, recovery_event)
                    from girlframe.services.m3_ankou_feedback_sequences import (
                        release_child as release_ankou_effect_child,
                    )

                    release_ankou_effect_child(self.game, c, state, action)
                    released_learning = True
                if cancel and action["data"].get("red_queen_child"):
                    from girlframe.services.m3_red_queen_support import (
                        release_child as release_royal_child,
                    )

                    released_learning = (
                        release_royal_child(self.game, c, state, action, key) or released_learning
                    )
                if cancel and (action["data"].get("wyvern") or action["data"].get("wyvern_child")):
                    from girlframe.services.m3_wyvern import release_unrolled as release_wyvern

                    release_wyvern(self.game, c, state, action, key)
                    released_learning = True
                if cancel and action["data"].get("consume_child"):
                    from girlframe.services.m3_consume import release_child

                    release_child(self.game, c, state, action, key)
                    released_learning = True
                if cancel and action["data"].get("learned_play"):
                    from girlframe.services.m3_learned_plays import release_unrolled

                    released_learning = (
                        release_unrolled(self.game, c, state, action) or released_learning
                    )
                if cancel and action["data"].get("learned_no_one_better"):
                    from girlframe.services.m3_learned_plays import release_triggered_unrolled

                    released_learning = (
                        release_triggered_unrolled(self.game, c, state, action) or released_learning
                    )
                if cancel and action["data"].get("learned_keep_rider"):
                    from girlframe.services.m3_learned_plays import release_keep_rider_unrolled

                    released_learning = (
                        release_keep_rider_unrolled(self.game, c, state, action)
                        or released_learning
                    )
                if cancel and action["data"].get("learned_call"):
                    from girlframe.services.m3_learned_plays import release_call_unrolled

                    released_learning = (
                        release_call_unrolled(self.game, c, state, action) or released_learning
                    )
                if cancel and (
                    action["data"].get("learned_show_dog") or action["data"].get("learned_psyche")
                ):
                    from girlframe.services.m3_learned_plays import release_daily_unrolled

                    released_learning = (
                        release_daily_unrolled(self.game, c, state, action) or released_learning
                    )
                if cancel and (
                    (action["data"].get("stim_sex") or {}).get("learned_source")
                    or (action["data"].get("princess_sex") or {}).get("learned_source")
                ):
                    from girlframe.services.m3_learned_sex import release_unrolled as release_sex

                    released_learning = (
                        release_sex(self.game, c, state, action, recovery_event)
                        or released_learning
                    )
                del action["data"]["shared_recovery"]
                self.game.save_action(c, action, state="aborted" if cancel else saved.state)
            if not cancel:
                locks = t.m2["m2_locks"]
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == root["channel_id"],
                        locks.c.action_id == identity,
                    )
                    .values(state="acquiring", body_json="{}", lease_until=0, claim_token=None)
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.shared_play_recovered",
                state if released_learning else None,
                event_id=recovery_event,
                action_id=identity,
                cancelled_unrolled=cancel,
                nodes=len(snapshot.nodes),
            )
            return dict(
                action_id=identity, cancelled_unrolled=cancel, receipt_preserved=snapshot.known_roll
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.shared_play_recovered",
                dict(action_id=identity, expected=expected, cancel=cancel),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except (ValueError, ValidationError):
            raise WorkflowError(
                "Invalid saved recovery evidence; recover the original records."
            ) from None
