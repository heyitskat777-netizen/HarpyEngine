"""HarpyEngine scene Plays for the isolated Activity campaigns."""

import asyncio
import json
import logging
import sqlite3
from contextlib import closing, nullcontext
from copy import copy
from dataclasses import asdict
from threading import Event, Thread
from uuid import uuid4

import sqlalchemy as sa
from defeat_play import DEFEAT, DEFEAT_CHOICES, defeat_choice
from dive_play import DIVE, DIVE_CHOICES, dive_choice
from mockingbird_play import (
    PERSON,
    PERSON_CHOICES,
    person_choice,
    person_start,
    start_person,
)
from native_scene_forms import (
    RISK_CHOICE,
    TAG_DECISIONS,
    risk_choice_card,
    tag_choice_card,
)
from oldgen_play import OLDGEN_ADVICE, OLDGEN_CHOICES, advice_choice, advice_targets
from rulebook_text import FLIRT_QUESTION_TEXT, printed_fields, sensor_question_text
from snoop_play import SNOOP, snoop_targets

from girlframe.database import tables
from girlframe.delivery.m2_worker import GameWorker
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m2_ui import choice_fields
from girlframe.engine import m3_cast
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, mark_identity
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_disposable_psyche import PsychePermit
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.activity_timing import _snowflake
from girlframe.services.handler_setup import HandlerService
from girlframe.services.ledger import CampaignLedger
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_defeat import start_work as start_defeat_work
from girlframe.services.m3_defeat import work as defeat_work
from girlframe.services.m3_disposable_psyche import (
    prepare_off_duty as admit_native_psyche,
)
from girlframe.services.m3_dive import prepare as prepare_dive
from girlframe.services.m3_learned_plays import (
    PSYCHE,
    prepare_call_lessons,
    prepare_daily_lessons,
    prepare_keep_riders,
)
from girlframe.services.m3_play_support import periods
from girlframe.services.m3_play_support import prepare as prepare_off_duty
from girlframe.services.m3_princess_sex import decision_author
from girlframe.services.m3_scene_requisitions import guard
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_source_pause import require_clear as require_source_clear

PLAY = "keep_your_head"
FOLLOW_THROUGH = "flirt_followthrough"
REJECT_TAG = "reject_tag"
OFF_DUTY_PLAYS = ("go_off_duty", "void_observation")
LESSON_MARK_FIELDS = {"learned_psyche", "identity", "gain", "disposable_heat"}
LESSON_FIELDS = {
    PLAY: {"learned_keep_rider"} | LESSON_MARK_FIELDS,
    "flirt": {"learned_keep_rider"} | LESSON_MARK_FIELDS,
    "check_sensors": LESSON_MARK_FIELDS,
    "engage": LESSON_MARK_FIELDS,
    "put_someone_beneath_you": LESSON_MARK_FIELDS,
    DIVE: {"learned_call"} | LESSON_MARK_FIELDS,
    "go_off_duty": {"learned_show_dog"} | LESSON_MARK_FIELDS,
    "void_observation": LESSON_MARK_FIELDS,
}
BENEATH = "put_someone_beneath_you"
RECEIVE = "receive_orders"
DISOBEY = "disobey_orders"
SCENE_PLAYS = (
    "check_sensors",
    "engage",
    "flirt",
    RECEIVE,
    BENEATH,
    DIVE,
    DEFEAT,
    PERSON,
    OLDGEN_ADVICE,
    SNOOP,
    FOLLOW_THROUGH,
    REJECT_TAG,
    *OFF_DUTY_PLAYS,
)
SCENE_CHOICES = frozenset(
    {
        *TAG_DECISIONS,
        RISK_CHOICE,
        "actor_sensors",
        "handler_sensors",
        "harpy_sensor_answers",
        "actor_engage",
        "actor_flirt",
        "target_flirt",
        "actor_flirt_answer",
        "flirt_escape",
        "escape_play",
        "flirt_owe_tag",
        "order_response",
        "order_disobey",
        "actor_disobey",
        "handler_disobey",
        "follow_disobey",
        "handler_brief",
        "actor_keep",
        "handler_keep",
        "followthrough_confirm",
        "beneath_select",
        "beneath_details",
        "beneath_pin_response",
        "beneath_response_play",
        "beneath_defeat",
        *DEFEAT_CHOICES,
        *DIVE_CHOICES,
        *PERSON_CHOICES,
        *OLDGEN_CHOICES,
    }
)
BENEATH_CHILDREN = (PLAY, DEFEAT)


def activity_choice_answer(payload):
    """Decode Discord member IDs without passing through JavaScript numbers."""
    if isinstance(payload, dict):
        member = payload.get("member")
        if isinstance(member, str):
            payload = payload | {"member": _snowflake(member)}
        elif type(member) is int and member >= 2**53:
            raise ValueError("Send Discord member IDs as text to preserve every digit.")
    return ChoiceAnswer.model_validate_json(json.dumps(payload))


def completed_flirt(game, connection, identity):
    try:
        source = game.action(connection, identity)
    except WorkflowError:
        return False
    return source["data"]["play"] == "flirt" and source["state"] == "complete"


def scene_child_allowed(root, action):
    return (
        not action["parent_id"]
        or (root["data"]["play"] == "flirt" and action["data"]["play"] == PLAY)
        or (root["data"]["play"] == RECEIVE and action["data"]["play"] == DISOBEY)
        or (root["data"]["play"] == BENEATH and action["data"]["play"] in BENEATH_CHILDREN)
    )


logger = logging.getLogger(__name__)


class TestSceneGateway:
    """Durable local acknowledgements for the engine worker. No Discord writes."""

    def __init__(
        self,
        path,
        channel,
        handler,
        owner,
        application,
        extra_viewers=(),
        has_channel=None,
        actor_lookup=None,
    ):
        self.path = path
        self.channel = channel
        self.handler = handler
        self.owner = owner
        self.application = application
        self.viewers = (owner, handler, *extra_viewers)
        self.has_channel = has_channel
        self.actor_lookup = actor_lookup
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS overwrites (target TEXT PRIMARY KEY, body TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS deliveries (nonce TEXT UNIQUE)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS room_overwrites "
                "(channel INTEGER NOT NULL, target TEXT NOT NULL, body TEXT NOT NULL, "
                "PRIMARY KEY (channel, target))"
            )

    def check(self, channel):
        if channel != self.channel and not (self.has_channel and self.has_channel(channel)):
            raise WorkflowError("This local scene is unavailable.")

    def overwrites(self, channel):
        # The original relay and drill databases already have a single-channel table.
        return (
            ("overwrites", {})
            if channel == self.channel
            else ("room_overwrites", {"channel": channel})
        )

    async def snapshot(self, channel, participants):
        self.check(channel)
        table, columns = self.overwrites(channel)
        where = " WHERE channel = ?" if columns else ""
        with closing(sqlite3.connect(self.path)) as db:
            return {
                "everyone_id": self.owner.guild_id,
                "bot_id": self.application,
                "overwrites": [
                    dict(zip(("kind", "id"), json.loads(target), strict=True)) | json.loads(body)
                    for target, body in db.execute(
                        f"SELECT target, body FROM {table}{where}",
                        tuple(columns.values()),
                    )
                ],
            }

    async def overwrite(self, channel, target):
        self.check(channel)
        table, columns = self.overwrites(channel)
        key = json.dumps((target["kind"], str(target["id"])))
        conditions = columns | {"target": key}
        where = " AND ".join(f"{column} = ?" for column in conditions)
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                f"SELECT body FROM {table} WHERE {where}", tuple(conditions.values())
            ).fetchone()
        return json.loads(row[0]) if row else None

    async def set_overwrite(self, channel, target, value):
        self.check(channel)
        table, columns = self.overwrites(channel)
        key = json.dumps((target["kind"], str(target["id"])))
        conditions = columns | {"target": key}
        with closing(sqlite3.connect(self.path)) as db, db:
            if value is None:
                where = " AND ".join(f"{column} = ?" for column in conditions)
                db.execute(f"DELETE FROM {table} WHERE {where}", tuple(conditions.values()))
            else:
                record = conditions | {"body": json.dumps(value)}
                db.execute(
                    f"INSERT OR REPLACE INTO {table} ({', '.join(record)}) "
                    f"VALUES ({', '.join('?' for _ in record)})",
                    tuple(record.values()),
                )

    def find_delivery(self, nonce):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT rowid FROM deliveries WHERE nonce = ?", (nonce,)).fetchone()
        return row[0] if row else None

    def acknowledge(self, nonce):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR IGNORE INTO deliveries VALUES (?)", (nonce,))
        return self.find_delivery(nonce)

    async def publish(self, channel, _payload, nonce):
        self.check(channel)
        return self.acknowledge(nonce)

    async def find(self, channel, nonce):
        self.check(channel)
        return self.find_delivery(nonce)

    async def publish_private(self, recipient, _payload, nonce):
        await self.actor(recipient)
        return self.acknowledge(nonce)

    async def find_private(self, recipient, nonce):
        await self.actor(recipient)
        return self.find_delivery(nonce)

    async def actor(self, identity):
        for viewer in self.viewers:
            if viewer.user_id == identity:
                return viewer
        if self.actor_lookup:
            return self.actor_lookup(identity)
        raise WorkflowError("Only the configured test participants may take part.")


def start_game_worker(game, gateway, *, work_lock=None):
    worker = GameWorker(game)
    source_pauses = SourcePauseWorker(game)
    stopped = Event()

    async def run():
        while not stopped.is_set():
            try:
                with work_lock if work_lock is not None else nullcontext():
                    if stopped.is_set():
                        return
                    await worker.tick(gateway)
                    await source_pauses.tick(gateway)
            except Exception:
                logger.exception("Local Activity scene worker failed")
            await asyncio.sleep(0.35)

    thread = Thread(target=lambda: asyncio.run(run()), daemon=True)
    thread.start()
    return stopped, thread


class ScenePlays:
    def __init__(
        self,
        game,
        channel,
        handler,
        owner,
        recruit,
        has_channel=None,
        *,
        handler_proxy=True,
        actor_lookup=None,
        activity_cast_channels=(),
    ):
        self.game = game
        self.channel = channel
        self.handler = handler
        self.owner = owner
        self.recruit = recruit
        self.handler_proxy = handler_proxy
        self.activity_cast_channels = activity_cast_channels
        self.has_channel = has_channel
        self.ledger = CampaignLedger(game.store)
        policy = game.store.policy
        self.gateway = TestSceneGateway(
            policy.sandbox / "activity-delivery.sqlite3",
            channel,
            handler,
            owner,
            policy.application_id,
            extra_viewers=(recruit,),
            has_channel=has_channel,
            actor_lookup=actor_lookup,
        )

    def for_channel(self, channel):
        scoped = copy(self)
        scoped.channel = channel
        return scoped

    def allows_cast(self, channel):
        return channel in self.activity_cast_channels or (
            not self.handler_proxy
            and (channel == self.gateway.channel or self.has_channel and self.has_channel(channel))
        )

    def allows_parallel_membership(self, channel, scene_id, active_casts, *, unbound_room=False):
        """Only ordinary Activity rooms can keep their memberships in parallel."""
        if scene_id in active_casts or channel in self.activity_cast_channels:
            return False
        if channel is None:
            return unbound_room
        return channel == self.gateway.channel or (
            self.has_channel is not None and self.has_channel(channel)
        )

    def start_worker(self, *, work_lock=None):
        return start_game_worker(self.game, self.gateway, work_lock=work_lock)

    def safety_status(self, viewer):
        return self.ledger.safety_status(viewer)

    def safety(self, viewer, key, data):
        if (
            data.keys() != {"pause", "revision"}
            or type(data["pause"]) is not bool
            or type(data["revision"]) is not int
        ):
            raise ValueError
        return self.ledger.safety(viewer, key, data["revision"], pause=data["pause"])

    def cancellation(self, viewer):
        """Project the locked source and the native recovery authority."""
        with self.game.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            lock = self.game.lock(connection, self.channel)
            if not lock or lock["state"] == "released":
                return None
            source = self.game.action(connection, lock["action_id"])
            while source["parent_id"]:
                source = self.game.action(connection, source["parent_id"])
            if source["state"] in ("complete", "aborted"):
                return None
            if viewer.user_id not in source["data"].get("participants", ()):
                return None
            can_cancel = bool(
                viewer.is_administrator
                and self.game.store.policy.allow_guild_administrators
                or (
                    HandlerService(self.game.store).current(connection)[1].handler_id
                    == viewer.user_id
                )
            )
            return {
                "id": source["id"],
                "root": source["id"],
                "play": source["data"]["play"],
                "owner_id": str(source["actor_id"]),
                "can_cancel": can_cancel,
                "can_request": not can_cancel and source["actor_id"] == str(viewer.user_id),
                "reason": None if can_cancel else "The Handler must cancel this pending Play.",
                "receipt_preserved": bool(source["data"].get("receipt")),
                "state": source["state"],
            }

    def cancel(self, viewer, key, data):
        if (
            data.keys() != {"id", "confirmed"}
            or not isinstance(data["id"], str)
            or data["confirmed"] is not True
        ):
            raise ValueError("Confirm cancellation of the pending Play.")
        with self.game.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            source = self.game.action(connection, data["id"])
            if str(source["channel_id"]) != str(self.channel) or source["parent_id"]:
                raise WorkflowError("Cancel this scene's original root Play.")
        return self.game.abort(viewer, key, source["id"])

    @staticmethod
    def start_reasons(viewer, state, pilots):
        sheet = state.sheets[str(viewer.user_id)]
        reasons = {
            entry.play: {
                "code": "sheet_blocked",
                "message": "This Play is blocked on your sheet.",
            }
            for entry in sheet.blocked_plays
        }
        if not any(uid != viewer.user_id and str(uid) in state.sheets for uid in pilots):
            reasons.setdefault(
                "flirt",
                {
                    "code": "needs_pilot",
                    "message": "Another pilot must enter this scene for Plays.",
                },
            )
        if all(asset.damaged for asset in sheet.assets):
            reasons.setdefault(
                "engage",
                {"code": "needs_asset", "message": "An undamaged Asset is required."},
            )
        return reasons

    def piloting(self, connection, viewer, state):
        actor = resolve(
            state,
            current_ref(state, viewer.user_id),
            profiles(connection, self.game.store.campaign_id),
        )
        return actor.piloting is True

    def dive_reason(self, connection, viewer, state):
        try:
            prepare_dive(
                self.game,
                connection,
                viewer,
                PlayInput(
                    play=DIVE,
                    context="Check availability",
                    trigger_confirmed=True,
                    heat=0,
                    piloting=self.piloting(connection, viewer, state),
                ),
                state,
                channel=self.channel,
            )
        except WorkflowError as error:
            return str(error)
        return None

    def defeat_sources(self, connection, viewer, state, scene_id):
        work = tables.m3["m3_required_work"]
        identities = connection.scalars(
            sa.select(work.c.id)
            .where(
                work.c.campaign_id == self.game.store.campaign_id,
                work.c.owner_id == str(viewer.user_id),
                work.c.kind == "defeat",
                sa.or_(work.c.scene_id == scene_id, work.c.scene_id.is_(None)),
            )
            .distinct()
        )
        character = state.sheets[str(viewer.user_id)].character_id
        result = []
        for identity in identities:
            try:
                row = defeat_work(self.game, connection, identity)
            except WorkflowError:
                continue
            if row["state"] != "pending":
                continue
            detail = json.loads(row["body_json"])
            if detail.get("character") == character:
                result.append(
                    {
                        "id": identity,
                        "label": detail.get("reason", "Required Defeat")
                        .replace("_", " ")
                        .capitalize(),
                    }
                )
        return result

    def enter(self, viewer, key, play=None):
        game = self.game
        table = tables.m2["m2_scenes"]

        def operation(connection):
            game.unpaused(connection)
            state = load_state(connection, game.store.campaign_id)
            destination = game.scene(connection, self.channel)
            sheet = state.sheets.get(str(viewer.user_id))
            if not sheet or state.handler not in destination["participants"]:
                raise WorkflowError("An active pilot and the scene Handler are required.")
            if viewer.user_id in destination["participants"]:
                return {"channel": self.channel}
            if play and (
                reason := self.start_reasons(viewer, state, destination["participants"]).get(play)
            ):
                raise WorkflowError(reason["message"])
            ref = ActorRef(kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id)
            guard(connection, game.store, destination["id"], ref)
            current = [
                row
                for row in connection.execute(
                    sa.select(table).where(
                        table.c.campaign_id == game.store.campaign_id,
                        table.c.open.is_(True),
                    )
                ).mappings()
                if viewer.user_id in json.loads(row["participants_json"])
            ]
            casts = {cast.id: cast for cast in state.scene_casts if cast.open}
            if self.allows_parallel_membership(self.channel, destination["id"], casts):
                current = [
                    row
                    for row in current
                    if not self.allows_parallel_membership(int(row["channel_id"]), row["id"], casts)
                ]
            for scene in [*current, destination]:
                channel = int(scene["channel_id"])
                if scene["id"] in casts and not self.allows_cast(channel):
                    raise WorkflowError("This scene requires its original cast controls.")
                lock = game.lock(connection, channel)
                if lock and lock["state"] != "released":
                    message = (
                        "Resolve the pending Play in this scene before entering."
                        if channel == self.channel
                        else "Resolve the pending Play before leaving its active scene."
                    )
                    raise WorkflowError(message)

            def save_members(scene, people):
                connection.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == game.store.campaign_id,
                        table.c.channel_id == scene["channel_id"],
                    )
                    .values(
                        participants_json=json.dumps(people),
                        revision=scene["revision"] + 1,
                    )
                )

            def save_cast(updated):
                state.scene_casts = [
                    updated if cast.id == updated.id else cast for cast in state.scene_casts
                ]

            for old in current:
                source = int(old["channel_id"])
                require_source_clear(game, connection, source)
                original_cast = casts.get(old["id"])
                if original_cast:
                    try:
                        save_cast(m3_cast.withdraw(original_cast, ref, viewer.user_id))
                    except ValueError as error:
                        raise WorkflowError(str(error)) from None
                save_members(
                    old,
                    [uid for uid in json.loads(old["participants_json"]) if uid != viewer.user_id],
                )
                game.event(
                    connection,
                    viewer.user_id,
                    f"{key}:leave:{source}",
                    "m2.scene_left",
                    state if original_cast else None,
                    channel=source,
                )
            event = str(uuid4())
            destination_cast = casts.get(destination["id"])
            if destination_cast:
                try:
                    actor = resolve(state, ref, profiles(connection, game.store.campaign_id))
                    save_cast(
                        m3_cast.join(
                            state.scene_casts,
                            destination["id"],
                            actor,
                            viewer.user_id,
                            event,
                        )
                    )
                except ValueError as error:
                    raise WorkflowError(str(error)) from None
            save_members(destination, sorted({*destination["participants"], viewer.user_id}))
            game.event(
                connection,
                viewer.user_id,
                key,
                "m2.scene_joined",
                state if destination_cast else None,
                event_id=event,
                channel=self.channel,
            )
            return {"channel": self.channel}

        return game.store._write(
            viewer,
            key,
            "activity.scene_entered",
            {"channel": self.channel, "play": play},
            operation,
            auto_audit=False,
            authorize=lambda connection: game.authorize(connection, viewer),
        )

    def recent(self, viewer):
        table = tables.m2["m2_actions"]
        with self.game.store.engine.connect() as connection:
            return connection.scalars(
                sa.select(table.c.id)
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.actor_id == str(viewer.user_id),
                    table.c.channel_id == str(self.channel),
                    table.c.parent_id.is_(None),
                    sa.func.json_extract(table.c.body_json, "$.play") == PLAY,
                )
                .order_by(sa.literal_column("rowid").desc())
                .limit(11)
            ).all()

    def receipts(self, viewer, rooms, limit=75):
        """Read filed outcomes and expose only decisions this account can answer."""
        if not rooms:
            return []
        table = tables.m2["m2_actions"]
        events = tables.events
        participants = sa.func.json_each(table.c.body_json, "$.participants").table_valued(
            "value", joins_implicitly=True
        )
        filed = (
            sa.select(events.c.created_utc)
            .where(
                events.c.campaign_id == table.c.campaign_id,
                sa.func.json_extract(events.c.payload_json, "$.action_id") == table.c.id,
            )
            .order_by(events.c.seq)
            .limit(1)
            .scalar_subquery()
        )
        updated = (
            sa.select(events.c.created_utc)
            .where(
                events.c.campaign_id == table.c.campaign_id,
                sa.func.json_extract(events.c.payload_json, "$.action_id") == table.c.id,
            )
            .order_by(events.c.seq.desc())
            .limit(1)
            .scalar_subquery()
        )
        with self.game.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            state = load_state(connection, self.game.store.campaign_id)
            own = self.game.pending_choices(connection, viewer)
            proxy = (
                self.game.pending_choices(connection, self.handler) if self.handler_proxy else []
            )
            rows = (
                connection.execute(
                    sa.select(table, filed.label("filed"), updated.label("updated"))
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.channel_id.in_(rooms),
                        sa.func.json_extract(table.c.body_json, "$.play").in_(
                            (PLAY, DISOBEY, *SCENE_PLAYS)
                        ),
                        sa.select(1)
                        .select_from(participants)
                        .where(participants.c.value == viewer.user_id)
                        .exists(),
                    )
                    .order_by(sa.literal_column("rowid").desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
            unresolved = {
                row["id"]: dict(row) | {"data": json.loads(row["body_json"])}
                for row in rows
                if row["state"] not in ("complete", "aborted")
            }
            waiting = {}
            if unresolved:
                choices = tables.m2["m2_choices"]
                for item in connection.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == self.game.store.campaign_id,
                        choices.c.state == "pending",
                        choices.c.action_id.in_(unresolved),
                        choices.c.kind.in_(SCENE_CHOICES),
                    )
                ).mappings():
                    source = unresolved[item["action_id"]]
                    try:
                        owner = decision_author(self.game, connection, state, source, dict(item))
                    except WorkflowError:
                        continue
                    owner = owner if owner is not None else int(item["actor_id"])
                    pilot = state.sheets.get(str(owner))
                    label = (
                        "Handler"
                        if owner == state.handler
                        else (
                            pilot.callsign
                            if pilot and owner in source["data"]["participants"]
                            else "Assigned participant"
                        )
                    )
                    waiting.setdefault(item["action_id"], set()).add(label)
            receipts = []
            for row in rows:
                view = self.game.inspect(viewer, row["id"])
                audience = [(item, "viewer") for item in own]
                if row["actor_id"] == str(viewer.user_id):
                    audience.extend((item, "handler") for item in proxy)
                pending = (
                    [
                        {key: item[key] for key in ("id", "revision", "kind")} | {"owner": owner}
                        for item, owner in audience
                        if item["action_id"] == row["id"] and item["kind"] in SCENE_CHOICES
                    ]
                    if view["state"] not in ("complete", "aborted")
                    else []
                )
                roll = view.get("receipt")
                result = view.get("result")
                if not roll and not result and not pending:
                    continue
                pilot = state.sheets.get(row["actor_id"])
                receipts.append(
                    {
                        "id": row["id"],
                        "root": row["parent_id"] or row["id"],
                        "room": rooms[row["channel_id"]],
                        "pilot": pilot.callsign if pilot else "Scene operations",
                        "play": view["play"],
                        "state": view["state"],
                        "revision": row["revision"],
                        "created": roll.get("rolled_utc") if roll else row["filed"],
                        "updated": row["updated"],
                        "roll": {key: roll[key] for key in ("faces", "pre_total")}
                        if roll
                        else None,
                        "result": {
                            key: result[key]
                            for key in (
                                "total",
                                "tier",
                                "ruling",
                                "enough",
                                "response",
                                "answers",
                            )
                            if key in result
                        }
                        if result
                        else None,
                        "pending": pending,
                        "waiting_on": sorted(waiting.get(row["id"], ()))
                        if view["state"] not in ("complete", "aborted")
                        else [],
                    }
                )
            return receipts

    def view(self, viewer, character, locked, paused=False, *, scene=None, blocked=False):
        recent = self.recent(viewer)
        identity = recent[0] if recent else None
        current = self.game.inspect(viewer, identity) if identity else None
        history = [
            previous
            for action_id in recent[1:]
            if (previous := self.game.inspect(viewer, action_id))["state"] == "complete"
        ]
        principals = {"pilot": viewer}
        if self.handler_proxy:
            principals["handler"] = self.handler
        if scene and locked and scene["lock"]["action_id"] != identity:
            with self.game.store.engine.connect() as connection:
                held = self.game.action(connection, scene["lock"]["action_id"])
            if (
                held["data"]["play"] == PLAY
                and not held["parent_id"]
                and viewer.user_id in held["data"]["participants"]
            ):
                identity = held["id"]
                current = self.game.inspect(viewer, identity)
                principals = self.roles(viewer, held)
        choices = []
        if current and current["state"] not in ("complete", "aborted"):
            for role, principal in principals.items():
                for item in self.game.choices(principal):
                    if item["action_id"] != identity:
                        continue
                    kind = item["kind"]
                    if kind not in TAG_DECISIONS | {"actor_keep", "handler_keep", RISK_CHOICE}:
                        continue
                    choices.append(self.choice_card(principal, role, item))
        can_start = not locked and not paused and not blocked
        lessons = {}
        if can_start:
            with self.game.store.engine.connect() as c:
                state = load_state(c, self.game.store.campaign_id)
            lessons = self.scene_lessons(viewer, state, PLAY)
        return {
            "can_start": can_start,
            "character_revision": character["revision"],
            "current": current,
            "history": history,
            "choices": choices,
            "waiting": locked and not choices,
            **lessons,
        }

    def scene_lessons(self, viewer, state, play):
        sheet = state.sheets.get(str(viewer.user_id))
        if play not in LESSON_FIELDS or not sheet:
            return {}
        native = has_rule(sheet, PSYCHE, "STIM-BLISSED")
        learned = bool(
            sheet.girl_runtime
            and any(lesson.rolled_event is None for lesson in sheet.girl_runtime.learned_plays)
        )
        if not (native or learned):
            return {}
        if native:
            try:
                admit_native_psyche(self.game, state, sheet.owner)
            except (ValueError, WorkflowError):
                native = False
        try:
            actor = current_ref(state, viewer.user_id)
            with self.game.store.engine.connect() as c:
                daily = prepare_daily_lessons(self.game, c, state, actor, play)
                options = {
                    "learned_keep_rider": prepare_keep_riders(self.game, c, state, actor, play),
                    "learned_call": prepare_call_lessons(self.game, c, state, actor, play),
                    "learned_show_dog": daily["show_dog"],
                    "learned_psyche": daily["psyche"],
                }
        except (ValueError, WorkflowError):
            return {}
        permit = None
        if daily["psyche"]:
            lesson = next(
                row
                for row in sheet.girl_runtime.learned_plays
                if row.id == daily["psyche"][0]["id"]
            )
            mode = "mark_off_duty" if play in OFF_DUTY_PLAYS else "mark"
            permit = PsychePermit(lesson=lesson, mode=mode)
        marks = self.lesson_marks(state, sheet, permit) if native or permit else []
        if not marks and play not in OFF_DUTY_PLAYS:
            options["learned_psyche"] = ()
        allowed = LESSON_FIELDS[play]
        choices = {
            name: [(row["id"], row["label"]) for row in rows]
            for name, rows in options.items()
            if name in allowed and rows
        }
        if not (choices or marks):
            return {}
        return {
            "lessons": choices,
            "lesson_marks": marks,
            "native_psyche": native,
            "lesson_heat": list(self.beneath_heat(sheet)) if play not in OFF_DUTY_PLAYS else [],
            "lesson_disposal_required": play not in OFF_DUTY_PLAYS,
        }

    def lesson_marks(self, state, sheet, permit):
        marks = []
        for identity in sheet.identities:
            if identity.marked:
                continue
            amounts = {}
            for gain in (1, 2, 3, 5):
                for disposal in (3, 4):
                    draft = sheet.model_copy(deep=True)
                    try:
                        mark_identity(
                            draft,
                            identity.id,
                            gain,
                            state=state,
                            disposable_heat=disposal,
                            learned_psyche=permit,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    amounts.setdefault(str(gain), {})[str(disposal)] = list(
                        self.beneath_heat(draft)
                    )
            if amounts:
                marks.append({"id": identity.id, "name": identity.name, "amounts": amounts})
        return marks

    def off_duty_status(self, viewer):
        try:
            period = periods(self.game).current(viewer)
        except WorkflowError:
            period = None
        if not period or period["phase"] != "active":
            reason = "An active Off-Duty period is required."
            return {play: {"reason": reason} for play in OFF_DUTY_PLAYS}
        options = {}
        with self.game.store.engine.connect() as connection:
            for play in OFF_DUTY_PLAYS:
                try:
                    prepare_off_duty(
                        self.game,
                        connection,
                        viewer,
                        PlayInput(
                            play=play,
                            off_duty_id=period["id"],
                            context="Spend time at base.",
                            trigger_confirmed=True,
                            heat=0,
                        ),
                    )
                except (ValueError, WorkflowError) as error:
                    options[play] = {"reason": str(error)}
                else:
                    options[play] = {"period": period["id"]}
        return options

    def play_options(self, viewer, scene, sheet, state, locked, paused, off_duty):
        table = tables.m2["m2_actions"]
        with self.game.store.engine.connect() as connection:
            actions = [
                self.game.action(connection, identity)
                for identity in connection.scalars(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.channel_id == str(self.channel),
                        table.c.parent_id.is_(None),
                        sa.func.json_extract(table.c.body_json, "$.play").in_(SCENE_PLAYS),
                    )
                    .order_by(sa.literal_column("rowid").desc())
                )
            ]
            visible = {}
            defeat = self.defeat_sources(
                connection,
                viewer,
                state,
                self.game.scene(connection, self.channel)["id"],
            )
            dive_unavailable = (
                None if locked or paused else self.dive_reason(connection, viewer, state)
            )
            held = scene["lock"] if locked else None
            for action in actions:
                if viewer.user_id not in action["data"]["participants"]:
                    continue
                prepared = action["data"].get("prepared", {})
                play = action["data"]["play"]
                counterparty = play == FOLLOW_THROUGH and any(
                    item.id == action["data"]["obligation_id"] and item.target == viewer.user_id
                    for item in state.obligations
                )
                if play == PERSON:
                    counterparty = any(
                        party["controller"] == viewer.user_id
                        for party in action["data"]["mockingbird"]["parties"]
                    )
                if (
                    action["actor_id"] != str(viewer.user_id)
                    and prepared.get("target") != viewer.user_id
                    and not counterparty
                    and not (held and held["action_id"] == action["id"])
                ):
                    continue
                group = visible.setdefault(play, [])
                if len(group) < 11:
                    group.append(action)
            children = {}
            for play, allowed in (
                ("flirt", (PLAY,)),
                (RECEIVE, (DISOBEY,)),
                (BENEATH, BENEATH_CHILDREN),
            ):
                if play not in visible:
                    continue
                root = visible[play][0]
                children[play] = [
                    identity
                    for identity in connection.scalars(
                        sa.select(table.c.id)
                        .where(
                            table.c.campaign_id == self.game.store.campaign_id,
                            table.c.parent_id == root["id"],
                            sa.func.json_extract(table.c.body_json, "$.play").in_(allowed),
                        )
                        .order_by(sa.literal_column("rowid").desc())
                    )
                    if viewer.user_id
                    in self.game.action(connection, identity)["data"]["participants"]
                ]
        targets = [
            {"id": str(uid), "label": scene["labels"][str(uid)]}
            for uid in scene["pilots"]
            if uid != viewer.user_id and str(uid) in state.sheets
        ]
        with self.game.store.engine.connect() as connection:
            obligations = [
                {"id": item.id, "label": state.sheets[str(item.target)].callsign}
                for item in state.obligations
                if item.kind == FOLLOW_THROUGH
                and item.owner == viewer.user_id
                and item.state == "pending"
                and item.target in scene["pilots"]
                and str(item.target) in state.sheets
                and completed_flirt(self.game, connection, item.action)
            ]
        tags = {tag.id: tag.label for tag in state.sheets[str(viewer.user_id)].tags}
        rejections = [
            {"id": item.id, "label": tags[item.details["tag"]]}
            for item in state.obligations
            if item.kind == REJECT_TAG
            and item.owner == viewer.user_id
            and item.state == "pending"
            and item.details.get("tag") in tags
        ]
        result = {}
        reasons = self.start_reasons(viewer, state, scene["pilots"])
        person = {} if locked or paused else person_start(self.game, viewer, state, self.channel)
        pupils, advice_reason = (
            ([], None) if locked or paused else advice_targets(self.game, viewer, self.channel)
        )
        property_targets = (
            [] if locked or paused else snoop_targets(self.game, viewer, self.channel)
        )
        for play in SCENE_PLAYS:
            past = visible.get(play, [])
            current = self.game.inspect(viewer, past[0]["id"]) if past else None
            nested = [self.game.inspect(viewer, identity) for identity in children.get(play, ())]
            choices = []
            waiting = False
            if current and current["state"] not in ("complete", "aborted"):
                active = {
                    item["id"]
                    for item in [current, *nested]
                    if item["state"] not in ("complete", "aborted")
                }
                for role, principal in self.roles(viewer, past[0]).items():
                    for item in self.game.choices(principal):
                        if item["action_id"] in active and item["kind"] in SCENE_CHOICES:
                            choices.append(self.choice_card(principal, role, item))
                waiting = not choices
            reason = reasons.get(play, {}).get("message")
            if play == RECEIVE and not current:
                reason = "A superior or an NPC with authority must file the original order."
            period = off_duty.get(play, {})
            reason = reason or period.get("reason")
            if play == FOLLOW_THROUGH and not obligations:
                reason = "There is no follow-through to start."
            if play == REJECT_TAG and not rejections:
                reason = "HarpyEngine has assigned no Tag rejection to this pilot."
            if play == BENEATH and not targets:
                reason = "Another pilot must be present in this scene."
            if play == DIVE:
                reason = reason or dive_unavailable
            if play == DEFEAT and not defeat:
                reason = "HarpyEngine has assigned no Defeat to this pilot here."
            if play == PERSON:
                reason = reason or person.get("reason")
            if play == OLDGEN_ADVICE:
                reason = (
                    reason
                    or advice_reason
                    or (None if pupils else "Another eligible Girl must be present.")
                )
            if play == SNOOP and not property_targets:
                reason = (
                    "Snoop needs an available paid Requisition and eligible property in this scene."
                )
            result[play] = {
                "current": current,
                "child": nested[0] if nested else None,
                **({"children": nested} if play == BENEATH else {}),
                "choices": choices,
                "waiting": waiting,
                "can_start": play != RECEIVE and not locked and not paused and not reason,
                "reason": reason
                or (
                    "Resolve the current Play first."
                    if locked
                    else "A safety pause is active."
                    if paused
                    else None
                ),
                **({"period": period["period"]} if "period" in period else {}),
                "character_revision": sheet["revision"],
                **(
                    self.scene_lessons(viewer, state, play)
                    if not locked and not paused and not reason
                    else {}
                ),
                **(
                    {key: person[key] for key in ("sources", "counterparts") if key in person}
                    if play == PERSON
                    else {}
                ),
                "targets": targets
                if play in ("flirt", BENEATH)
                else obligations
                if play == FOLLOW_THROUGH
                else rejections
                if play == REJECT_TAG
                else defeat
                if play == DEFEAT
                else pupils
                if play == OLDGEN_ADVICE
                else [{"id": item["token"], "label": item["label"]} for item in property_targets]
                if play == SNOOP
                else [],
                **(
                    {"heat_options": self.beneath_heat(state.sheets[str(viewer.user_id)])}
                    if play in (BENEATH, DIVE, OLDGEN_ADVICE, SNOOP)
                    or (play == PERSON and person.get("sources"))
                    else {}
                ),
                "history": [
                    self.game.inspect(viewer, action["id"])
                    for action in past[1:]
                    if action["state"] == "complete"
                ],
            }
        confrontation = result[BENEATH]
        if any(choice["kind"] == "beneath_defeat" for choice in confrontation["choices"]) or any(
            child["play"] == DEFEAT and child["state"] not in ("complete", "aborted")
            for child in confrontation["children"]
        ):
            result[DEFEAT]["resume_source"] = BENEATH
            result[DEFEAT]["reason"] = None
        return result

    @staticmethod
    def beneath_heat(sheet):
        from battlefield import Battlefield

        return Battlefield.heat_options(sheet)

    def roles(self, viewer, root):
        if not self.handler_proxy and viewer == self.handler:
            return {"handler": viewer}
        roles = {"pilot": viewer}
        if self.handler_proxy and root["actor_id"] == str(viewer.user_id):
            roles["handler"] = self.handler
        return roles

    def handler_choices(self, viewer):
        if self.handler_proxy or viewer != self.handler:
            return []
        cards = []
        with self.game.store.engine.connect() as connection:
            for choice in self.game.choices(viewer):
                if choice["actor_id"] != str(viewer.user_id):
                    continue
                action = self.game.action(connection, choice["action_id"])
                root = (
                    self.game.action(connection, action["parent_id"])
                    if action["parent_id"]
                    else action
                )
                if viewer.user_id not in root["data"].get("participants", ()):
                    continue
                play = root["data"].get("play")
                if play == PLAY and not action["parent_id"]:
                    kinds = ("tag_window", "handler_keep")
                    if action["data"].get("actor_basic"):
                        kinds += ("actor_keep",)
                    if choice["kind"] not in kinds:
                        continue
                    step = "keep-choice"
                elif (
                    play in SCENE_PLAYS
                    and choice["kind"] in SCENE_CHOICES
                    and scene_child_allowed(root, action)
                ):
                    step = "scene-choice"
                else:
                    continue
                cards.append(
                    {
                        "channel": int(action["channel_id"]),
                        "play": play,
                        "root": root["id"],
                        "step": step,
                        "choice": self.choice_card(viewer, "handler", choice),
                    }
                )
        return cards

    def choice_card(self, principal, role, choice):
        card = {key: choice[key] for key in ("id", "revision", "kind")} | {"role": role}
        kind = choice["kind"]
        if kind == "escape_play":
            return card
        decision = self.game.decision(principal, choice["id"])
        if kind in TAG_DECISIONS:
            return card | tag_choice_card(decision)
        if kind == RISK_CHOICE:
            return card | risk_choice_card(decision)
        if kind in ("order_response", "order_disobey"):
            issuer = decision.get("npc_order_issuer") or decision.get("ranked_order_issuer")
            order = decision.get("order_text")
            card["prompt"] = f"{issuer}: {order}" if issuer else order
        if kind == "order_disobey":
            with self.game.store.engine.connect() as c:
                sheet = load_state(c, self.game.store.campaign_id).sheets[str(principal.user_id)]
            return card | {
                "character_revision": sheet.revision,
                "heat_options": self.beneath_heat(sheet),
            }
        if kind in ("beneath_response_play", "beneath_defeat"):
            return card | {"character_revision": self.game.sheet(principal)["revision"]}
        if kind in DEFEAT_CHOICES:
            form = defeat_choice(decision)
            return card | {"fields": form["schema"], "offer": form["offer"]}
        if kind in DIVE_CHOICES:
            return card | dive_choice(decision)
        if kind in PERSON_CHOICES:
            return card | person_choice(decision)
        if kind in OLDGEN_CHOICES:
            return card | advice_choice(decision)
        card["fields"] = printed_fields(
            [asdict(field) for field in choice_fields(decision)], choice["kind"]
        )
        if choice["kind"] == "harpy_sensor_answers":
            card["prompt"] = decision["context"]
        if choice["kind"] == "handler_sensors":
            for field in card["fields"]:
                if field["key"].startswith("fields.a"):
                    index = int(field["key"][8:]) - 1
                    field["label"] = sensor_question_text(decision["result"]["questions"][index])
        if choice["kind"] in ("target_flirt", "actor_flirt_answer"):
            result_key = "question" if choice["kind"] == "target_flirt" else "return_question"
            question = decision["result"].get(result_key)
            card["prompt"] = FLIRT_QUESTION_TEXT.get(question, question)
            if choice["kind"] == "target_flirt" and decision["result"].get("tier") == "low":
                card["prompt"] = FLIRT_QUESTION_TEXT["rejection"]
        return card

    def perform_scene(self, viewer, key, step, data):
        if step == "scene-start":
            if not self.handler_proxy and viewer == self.handler:
                raise WorkflowError("Only pilots can start these Plays.")
            return self.start_scene_play(viewer, key, data)
        if step != "scene-choice" or data.keys() != {
            "id",
            "revision",
            "role",
            "answer",
        }:
            raise ValueError
        if (
            not isinstance(data["id"], str)
            or type(data["revision"]) is not int
            or data["role"] not in ("pilot", "handler")
        ):
            raise ValueError
        table = tables.m2["m2_choices"]
        with self.game.store.engine.connect() as connection:
            choice = connection.execute(
                sa.select(
                    table.c.action_id,
                    table.c.actor_id,
                    table.c.kind,
                    table.c.body_json,
                    table.c.revision,
                    table.c.state,
                ).where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == data["id"],
                )
            ).first()
            if not choice or choice.kind not in SCENE_CHOICES:
                raise WorkflowError("This choice is unavailable.")
            action = self.game.action(connection, choice.action_id)
            root = (
                self.game.action(connection, action["parent_id"]) if action["parent_id"] else action
            )
            principal = self.roles(viewer, root).get(data["role"])
            if (
                principal is None
                or choice.actor_id != str(principal.user_id)
                or str(action["channel_id"]) != str(self.channel)
                or viewer.user_id not in root["data"]["participants"]
                or root["data"]["play"] not in SCENE_PLAYS
                or not scene_child_allowed(root, action)
            ):
                raise WorkflowError("This choice is unavailable.")
        if choice.kind == "order_disobey":
            answer = data["answer"]
            if (
                not isinstance(answer, dict)
                or answer.keys() != {"context", "character_revision", "heat", "witnessed"}
                or not isinstance(answer["context"], str)
                or type(answer["character_revision"]) is not int
                or type(answer["heat"]) is not int
                or type(answer["witnessed"]) is not bool
                or principal != viewer
                or action["id"] != root["id"]
                or root["data"]["play"] != RECEIVE
                or not (
                    choice.revision == data["revision"]
                    or choice.state == "completed_by_child"
                    and choice.revision == data["revision"] + 1
                )
            ):
                raise WorkflowError("Reopen your original assigned order before refusing.")
            return self.game.begin(
                viewer,
                key,
                self.channel,
                answer["character_revision"],
                PlayInput(
                    play=DISOBEY,
                    context=answer["context"],
                    trigger_confirmed=True,
                    heat=answer["heat"],
                    witnessed=answer["witnessed"],
                    parent=root["id"],
                    order_id=root["data"]["order_id"],
                ),
            )
        if choice.kind in ("escape_play", "beneath_response_play", "beneath_defeat"):
            answer = data["answer"]
            if (
                principal != viewer
                or not isinstance(answer, dict)
                or answer.keys() != {"context", "character_revision"}
                or not isinstance(answer["context"], str)
                or type(answer["character_revision"]) is not int
            ):
                raise ValueError
            return self.game.begin(
                viewer,
                key,
                self.channel,
                answer["character_revision"],
                PlayInput(
                    play=DEFEAT if choice.kind == "beneath_defeat" else PLAY,
                    context=answer["context"],
                    trigger_confirmed=True,
                    heat=0,
                    parent=action["id"],
                    piloting=choice.kind == "beneath_defeat"
                    and action["data"]["prepared"]["piloting"],
                ),
            )
        answer = activity_choice_answer(data["answer"])
        return self.game.respond(principal, key, data["id"], data["revision"], answer)

    def start_scene_play(self, viewer, key, data):
        play = data.get("play")
        if not isinstance(play, str) or play not in SCENE_PLAYS or play == RECEIVE:
            raise ValueError("Choose an available Scene Play.")
        off_duty = play in OFF_DUTY_PLAYS
        required = (
            {
                "play",
                "context",
                "confirmed",
                "character_revision",
                "target",
            }
            | ({"period"} if off_duty else set())
            | (
                {"heat"}
                if play in (BENEATH, DIVE, OLDGEN_ADVICE, SNOOP)
                or (play == PERSON and isinstance(data.get("target"), str))
                else set()
            )
        )
        optional = LESSON_FIELDS.get(play, set())
        if play in LESSON_FIELDS and not off_duty:
            optional = optional | {"heat"}
        if not required <= data.keys() <= required | optional:
            raise ValueError
        if data["confirmed"] is not True:
            raise ValueError
        if type(data["character_revision"]) is not int or not isinstance(data["context"], str):
            raise ValueError
        context = data["context"].strip()
        target = data["target"]
        if off_duty and (not isinstance(data["period"], str) or not data["period"]):
            raise ValueError
        if not context:
            raise WorkflowError("Describe the scene before starting this Play.")
        if play == PERSON:
            return start_person(self.game, viewer, key, self.channel, data)
        if play == SNOOP:
            actor = next(
                (
                    item["ref"]
                    for item in snoop_targets(self.game, viewer, self.channel)
                    if item["token"] == target
                ),
                None,
            )
            if actor is None:
                raise WorkflowError("Choose an eligible property owner from the original scene.")
            return self.game.begin(
                viewer,
                key,
                self.channel,
                data["character_revision"],
                PlayInput(
                    play=SNOOP,
                    target_actor=ActorRef.model_validate(actor),
                    context=context,
                    trigger_confirmed=True,
                    heat=data["heat"],
                ),
            )
        if play == DEFEAT:
            if not isinstance(target, str):
                raise ValueError("Choose an assigned Defeat.")
            return start_defeat_work(self.game, viewer, key, target, self.channel, context)
        if play in (FOLLOW_THROUGH, REJECT_TAG):
            if not isinstance(target, str):
                raise ValueError
            with self.game.store.engine.connect() as connection:
                state = load_state(connection, self.game.store.campaign_id)
                obligation = next(
                    (
                        item
                        for item in state.obligations
                        if item.id == target and item.kind == play and item.owner == viewer.user_id
                    ),
                    None,
                )
                if obligation is None or (
                    play == FOLLOW_THROUGH
                    and not completed_flirt(self.game, connection, obligation.action)
                ):
                    raise WorkflowError("This assigned follow-through is unavailable.")
            return self.game.fulfill(viewer, key, self.channel, target, context)
        targeted = play in ("flirt", BENEATH, OLDGEN_ADVICE)
        if (
            targeted and not (isinstance(target, str) and target.isascii() and target.isdecimal())
        ) or (not targeted and target is not None):
            raise ValueError
        heat = data.get("heat", 0)
        if type(heat) is not int or heat < 0:
            raise ValueError
        piloting = False
        if play in (BENEATH, DIVE):
            with self.game.store.engine.connect() as c:
                state = load_state(c, self.game.store.campaign_id)
                piloting = self.piloting(c, viewer, state)
        return self.game.begin(
            viewer,
            key,
            self.channel,
            data["character_revision"],
            PlayInput(
                play=play,
                context=context,
                trigger_confirmed=True,
                heat=heat,
                piloting=piloting,
                target=int(target) if target else None,
                off_duty_id=data.get("period"),
                **{name: data[name] for name in LESSON_FIELDS.get(play, ()) if name in data},
            ),
        )

    def perform(self, viewer, key, step, data):
        signed_in_handler = not self.handler_proxy and viewer == self.handler
        allowed = (
            viewer in (self.owner, self.recruit)
            if self.handler_proxy
            else viewer != self.handler or (signed_in_handler and step == "keep-choice")
        )
        if not allowed:
            raise WorkflowError("Keep Your Head belongs to the active pilot.")
        required = {
            "context",
            "confirmed",
            "character_revision",
        }
        if step == "keep-start" and required <= data.keys() <= required | LESSON_FIELDS[PLAY] | {
            "heat"
        }:
            if not isinstance(data["context"], str) or not data["context"].strip():
                raise WorkflowError("Describe what the pilot is trying to endure.")
            if data["confirmed"] is not True or type(data["character_revision"]) is not int:
                raise WorkflowError("Confirm the Play's trigger.")
            prepared = PlayInput(
                play=PLAY,
                context=data["context"].strip(),
                trigger_confirmed=True,
                heat=data.get("heat", 0),
                **{name: data[name] for name in LESSON_FIELDS[PLAY] if name in data},
            )
            return self.game.begin(viewer, key, self.channel, data["character_revision"], prepared)
        if step == "keep-choice" and data.keys() == {
            "id",
            "revision",
            "role",
            "answer",
        }:
            if not isinstance(data["id"], str) or type(data["revision"]) is not int:
                raise ValueError
            if data["role"] not in ("pilot", "handler"):
                raise ValueError
            if self.handler_proxy:
                principal = self.handler if data["role"] == "handler" else viewer
            elif data["role"] == ("handler" if signed_in_handler else "pilot"):
                principal = viewer
            else:
                raise WorkflowError("This choice is unavailable.")
            table = tables.m2["m2_choices"]
            with self.game.store.engine.connect() as connection:
                choice = connection.execute(
                    sa.select(table.c.action_id, table.c.actor_id, table.c.kind).where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.id == data["id"],
                    )
                ).first()
                permitted = (
                    TAG_DECISIONS | {"handler_keep"}
                    if principal == self.handler
                    else TAG_DECISIONS | {"actor_keep", RISK_CHOICE}
                )
                if not choice or choice.actor_id != str(principal.user_id):
                    raise WorkflowError("This choice is unavailable.")
                action = self.game.action(connection, choice.action_id)
                actual_role = action["data"].get("actor_basic")
                if actual_role:
                    permitting = TAG_DECISIONS | {"actor_keep", "handler_keep", RISK_CHOICE}
                else:
                    permitting = permitted
                if (
                    choice.kind not in permitting
                    or action["data"]["play"] != PLAY
                    or str(action["channel_id"]) != str(self.channel)
                    or action["parent_id"]
                    or (
                        action["actor_id"] != str(viewer.user_id)
                        and (
                            principal != viewer
                            or (
                                choice.kind not in TAG_DECISIONS
                                and not signed_in_handler
                                and not actual_role
                            )
                            or viewer.user_id not in action["data"]["participants"]
                        )
                    )
                ):
                    raise WorkflowError("This choice is unavailable.")
            answer = activity_choice_answer(data["answer"])
            return self.game.respond(principal, key, data["id"], data["revision"], answer)
        raise ValueError
