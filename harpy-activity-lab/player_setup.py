"""Activity projection for the isolated lab's character and scene workflow."""

import json
from dataclasses import replace

import sqlalchemy as sa
from activity_artwork import KINDS, frame_subject, validate_selection
from activity_records import RELAY, ActivityRecords, profile_assets, scene_activity, scene_locations
from am_scene_controls import am_work_channels
from bot_enrollment import BotEnrollment
from defeat_play import DEFEAT
from dive_play import DIVE
from doll_controls import RETURN as DOLL_RETURN
from enrollment_choices import EnrollmentChoices
from frame_purchases import FramePurchases
from handler_playbook import HandlerPlaybook
from handler_punishments import HandlerPunishments
from mockingbird_play import PERSON, person_start
from off_duty_followups import OffDutyFollowups
from oldgen_play import OLDGEN_ADVICE, advice_targets
from owned_followups import OwnedFollowups
from play_catalog import ORDER_PLAYS, character_plays, frame_upgrades, play_category
from play_continuations import ACTIONS as CONTINUATION_ACTIONS
from player_reset import awaiting_replacement, purge_sheet
from pydantic import ValidationError
from rulebook_text import BOND_PROMPTS as PROMPTS
from rulebook_text import NPC_BOND_ROLES as NPC_ROLES
from scene_beneath_work import SceneBeneathWork
from scene_orders import SceneOrders
from scene_plays import BENEATH, OFF_DUTY_PLAYS, REJECT_TAG, ScenePlays
from snoop_play import SNOOP, snoop_targets
from specialist_scene import SpecialistScene

from girlframe.database import tables
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import CreationDraft, official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import InitialConditions
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.drafts import DraftInput
from girlframe.engine.frame_classes import FRAME_CLASSES
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PLAY_IDS, ReleaseApproval
from girlframe.engine.m2_registry import REGISTRY, registry_digest
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES, canonical_frame
from girlframe.services.activity_timing import _snowflake
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state, public_sheet
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_careers import CareerService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

SCENE = 900
GIRL = "MOCKINGBIRD"
FRAME = "JANUS"
OWNER_CREATION_FIELDS = frozenset(
    {
        "girl_assets",
        "frame_assets",
        "void_asset",
        "npc_bonds",
        "frame_name",
        "girl_appearance",
        "frame_appearance",
        "pair_asset_descriptions",
        "dna_basis",
        "fanbase",
        "girl_details",
        "prior_missions",
        "cadre_discussed",
    }
)
ROOM_PLAYS = [
    {
        "id": play["play_id"],
        "trigger": play["trigger"],
        "category": play_category(play["play_id"]),
    }
    for play in REGISTRY["plays"]
    if play["play_id"] in PLAY_IDS and play["play_id"] not in ORDER_PLAYS
]
OFF_DUTY_ROOM_PLAYS = [
    {
        "id": play,
        "trigger": "Describe your time at base",
        "category": play_category(play),
    }
    for play in OFF_DUTY_PLAYS
]
SUPPORTED_ROOM_PLAYS = [
    *ROOM_PLAYS,
    *OFF_DUTY_ROOM_PLAYS,
    {"id": DIVE, "trigger": "Describe the actual Void link", "category": "scan"},
    {"id": DEFEAT, "trigger": "Describe the actual Defeat", "category": "fight"},
    {"id": BENEATH, "trigger": "Describe the actual confrontation", "category": "talk"},
    {
        "id": REJECT_TAG,
        "trigger": "Describe how the Tag was rejected in the fiction",
        "category": "recover",
    },
]
BATTLEFIELD_PLAYS = frozenset(
    {"all_out_assault", "go_for_the_core", "living_battery", *ORDER_PLAYS}
)


class EnrollmentInputError(ValueError):
    def __init__(self, fields, *, conflict=False):
        super().__init__("Check the enrollment fields below.")
        self.fields = fields
        self.conflict = conflict


def _enrollment_validation(error, draft):
    fields = []
    for issue in error.errors(include_input=False, include_url=False)[:8]:
        path = list(issue["loc"])
        context = issue.get("ctx") or {}
        reason = str(context.get("error", ""))
        if reason == "Choose distinct Assets from the selected playbook":
            for key in ("girl_assets", "frame_assets"):
                seen = set()
                for index, asset in enumerate(draft.get(key, [])):
                    name = asset["name"]
                    if name in seen:
                        fields.append(
                            {
                                "path": [key, index, "name"],
                                "message": "Choose a different Asset for this slot.",
                            }
                        )
                    seen.add(name)
            if fields:
                continue
        if reason == "Choose distinct NPC roles":
            path, message = ["npc_bonds", 1, "slot"], "Choose a different NPC Bond role."
        elif reason == "Only a selected Mockingbird Girl Asset can start Void-altered":
            path, message = ["void_asset"], "Choose one of your selected Pilot Assets."
        elif reason == "Declare each Cadre counterpart only once":
            path, message = ["prior_missions"], "Use one answer per Cadre member."
        elif reason == "Only a custom standard takes nonempty custom text":
            message = "Enter text for a custom standard, or choose a listed standard."
        elif issue["type"] == "string_too_long":
            message = f"Use at most {context['max_length']} characters."
        elif issue["type"] in ("missing", "string_too_short"):
            message = "Enter a value for this field."
        else:
            message = (
                "Choose a listed value or correct this entry."
                if path
                else ("Check the Asset, Bond, and playbook selections in this dossier.")
            )
        fields.append({"path": path, "message": message})
    return EnrollmentInputError(fields)


def seed_players(store, handler, owner, recruit):
    from test_creation_review import ready
    from test_ledger import seed

    review, _, _ = ready(store)
    seed(store, recruit, callsign="RECRUIT", notes="")
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    setup = PlayerSetup(store, handler, owner, recruit)
    setup.refresh_test_rank("lab-initial-rank")
    current = review.get(owner)
    review.save(owner, "lab-owner-review", current.saved_revision, current.fingerprint)
    setup.game.activate(owner, "lab-owner-activate", current.fingerprint)
    setup.game.bind_scene(handler, "lab-open-scene", SCENE)
    setup.game.join_scene(handler, "lab-handler-join-scene", SCENE)
    setup.game.join_scene(owner, "lab-owner-join-scene", SCENE)


def seed_roster(store, handler, first=None, second=None):
    store.policy = store.policy.model_copy(
        update={
            "owner_initial_conditions": InitialConditions(),
            "owner_creation_rulings": CreationRulings(provenance="owner_approved_campaign_ruling"),
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="private playtest preset",
                reference="isolated Activity campaign only",
            ),
        }
    )
    for role, viewer in (("handler", handler), ("first", first), ("second", second)):
        if viewer:
            store.join(viewer, f"roster-join-{role}")
    bootstrap = replace(handler, is_administrator=True)
    HandlerService(store).appoint(bootstrap, "roster-appoint-handler", 0, handler.user_id)
    GameService(store).bind_scene(bootstrap, "lab-open-scene", SCENE)


class PlayerSetup:
    def __init__(self, store, handler, owner, recruit, *, bound_roster=False):
        self.store = store
        self.handler = handler
        self.owner = owner
        self.recruit = recruit
        self.bound_roster = bound_roster
        self.game = GameService(store)
        self.off_duty = OffDutyFollowups(self.game)
        self.off_duty.strain.rooms = self.handler_rooms
        self.handler_setup = HandlerService(store)
        self.bot_enrollment = BotEnrollment(store, handler)
        self.creation = CreationService(store)
        self.bonds = BondService(store, enrollment=bound_roster)
        self.enrollment_choices = EnrollmentChoices(self.game)
        self.review = CreationReviewService(store)
        self.play_registry = load_registry()
        self.handler_playbook = HandlerPlaybook(store, self.play_registry, self.off_duty.periods)
        self.handler_punishments = HandlerPunishments(self.game)
        self.owned_followups = OwnedFollowups(self.game, self.handler_rooms)
        self.beneath_work = SceneBeneathWork(self.game, self.handler_rooms, self.owned_followups)
        self.scene_plays = None
        self.records = None

    def enable_activity_records(self):
        self.records = ActivityRecords(
            self.store.policy.sandbox / "activity-records.sqlite3",
            self.owner.user_id,
            campaign_codes=not self.bound_roster,
        )

    def check_room(self, viewer, target, *, posting=False):
        if not isinstance(target, str):
            raise TypeError
        profile = self.store.draft(viewer)
        canonical = profile.get("canonical") if profile else None
        if not canonical:
            raise WorkflowError("Activate a pilot to read the scene transcript.")
        if not posting and target == RELAY["id"] and not self.relay_member(viewer):
            raise WorkflowError("Join the relay scene to read its transcript.")
        return canonical

    def relay_member(self, viewer):
        with self.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            events = tables.events
            return (
                viewer.user_id in self.game.scene(connection, SCENE)["participants"]
                or connection.scalar(
                    sa.select(events.c.id)
                    .where(
                        events.c.campaign_id == self.store.campaign_id,
                        events.c.actor_id == str(viewer.user_id),
                        events.c.kind == "m2.scene_joined",
                        sa.func.json_extract(events.c.payload_json, "$.channel") == SCENE,
                    )
                    .limit(1)
                )
                is not None
            )

    def transcript(self, viewer, target):
        self.check_room(viewer, target)
        transcript = self.records.transcript(viewer, target)
        if transcript.get("archived_at") is not None:
            return transcript
        legacy_entries = [
            (entry, author)
            for entry in transcript["entries"]
            if (author := entry.pop("legacy_author")) is not None
        ]
        if legacy_entries:
            artwork = self.records.artwork()
            with self.store.engine.connect() as connection:
                state = load_state(connection, self.store.campaign_id)
            for entry, author in legacy_entries:
                sheet = state.sheets.get(str(author))
                if sheet and sheet.callsign == entry["callsign"]:
                    entry["portrait"] = artwork.get(("pilot", sheet.character_id))
        channel = SCENE if target == RELAY["id"] else self.records.play_room(viewer, target)[1]
        return transcript | {
            "cast": self.transcript_cast(viewer, channel) if channel is not None else [],
            "receipts": self.scene_plays.receipts(viewer, {str(channel): target})
            if channel is not None
            else [],
        }

    def transcript_cast(self, viewer, channel):
        roles = CastService(ActorService(MissionService(self.store))).view(viewer, channel)["roles"]
        return [
            {"id": row["token"], "name": row["label"], "kind": row["ref"]["kind"]}
            for row in roles
            if not row["stale"] and row["ref"]["kind"] in ("npc", "gorgon", "external_pilot")
        ]

    def end_room(self, viewer, target):
        self.check_room(viewer, target)

        def freeze(channel, members):
            table = tables.m2["m2_scenes"]
            with self.store.engine.connect() as connection:
                state = load_state(connection, self.store.campaign_id)
                pilots = {
                    str(member): sheet.callsign
                    for member in members
                    if (sheet := state.sheets.get(str(member)))
                }
                if channel is None:
                    return {}, pilots
                is_open = connection.scalar(
                    sa.select(table.c.open).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                )
                active = connection.scalars(
                    sa.select(tables.members.c.user_id).where(
                        tables.members.c.campaign_id == self.store.campaign_id,
                        tables.members.c.active.is_(True),
                        tables.members.c.user_id.in_(str(member) for member in members),
                    )
                ).all()
            # Capture only each member's own visible cast and receipt projection.
            principals = {
                member: replace(viewer, user_id=int(member), is_administrator=False)
                for member in active
            }
            casts = (
                {
                    member: self.transcript_cast(principal, channel)
                    for member, principal in principals.items()
                }
                if is_open
                else {}
            )
            if is_open:
                authority = replace(self.handler, is_administrator=True)
                self.game.close_scene(authority, f"activity-end-scene:{target}", channel)
            views = {
                str(member): {
                    "cast": casts.get(member, []),
                    "receipts": self.scene_plays.receipts(
                        principal, {str(channel): target}, limit=None
                    ),
                }
                for member, principal in principals.items()
            }
            return views, pilots

        return self.records.archive(viewer, target, freeze)

    def communication_contacts(self, viewer, state, *, members=None):
        if self.bound_roster:
            people = {}
            portraits = self.records.artwork() if self.records else {}
            for member in members if members is not None else self.campaign_members(viewer):
                uid = int(member["id"])
                profile = self.store.draft(viewer, uid)
                aliases = [f"pilot-account-{uid}", f"handler-{uid}"]
                if profile:
                    aliases.append(f"pilot-{profile['id']}")
                contact_id = (
                    f"handler-{uid}"
                    if member["handler"]
                    else (f"pilot-{profile['id']}" if profile else f"pilot-account-{uid}")
                )
                people[uid] = {
                    "id": contact_id,
                    "aliases": [item for item in aliases if item != contact_id],
                    "label": member["name"],
                    "portrait": portraits.get(("pilot", profile["id"])) if profile else None,
                    "bot": member.get("bot", False),
                    "role": "Handler"
                    if member["handler"]
                    else "Pilot"
                    if member["pilot"]
                    else "Enrollment pending",
                }
            if viewer.user_id not in people:
                raise WorkflowError("Join this campaign before using Communications.")
            actor = people.pop(viewer.user_id)
            return actor, list(people.values())
        if self.bound_roster and viewer == self.handler and state.handler is None:
            return {
                "id": f"handler-{viewer.user_id}",
                "label": (self.store.draft(viewer) or {}).get("callsign") or "Handler",
                "role": "Handler",
            }, []
        handler = {
            "id": f"handler-{state.handler}",
            "label": (self.store.draft(viewer, state.handler) or {}).get("callsign") or "Handler",
            "role": "Handler",
        }
        pilots = {
            sheet.owner: {
                "id": f"pilot-{sheet.character_id}",
                "label": sheet.callsign,
                "role": public_sheet(sheet, state).get("rank") or "Pilot",
            }
            for sheet in state.sheets.values()
        }
        if viewer == self.handler and viewer.user_id == state.handler:
            return handler, list(pilots.values())
        if viewer.user_id not in pilots:
            raise WorkflowError("Activate a pilot before using Communications.")
        return pilots.pop(viewer.user_id), [*pilots.values(), handler]

    def communication_view(self, viewer, state, *, members=None):
        if not self.records:
            return []
        actor, contacts = self.communication_contacts(viewer, state, members=members)
        latest = self.records.private_updates(actor["id"], actor.get("aliases", ()))
        return [
            contact
            | {
                "latest_message": max(
                    (
                        latest.get(identity, 0)
                        for identity in (contact["id"], *contact.get("aliases", ()))
                    ),
                    default=0,
                )
                or None
            }
            for contact in sorted(contacts, key=lambda item: item["label"].casefold())
        ]

    def communication(self, viewer, target, *, message=None):
        with self.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            state = load_state(connection, self.store.campaign_id)
            actor, contacts = self.communication_contacts(viewer, state)
        if not self.records or not any(contact["id"] == target for contact in contacts):
            raise WorkflowError("This communication is unavailable.")
        if message is None:
            contact = next(contact for contact in contacts if contact["id"] == target)
            thread = self.records.private_thread(
                actor["id"], target, actor.get("aliases", ()), contact.get("aliases", ())
            )
            parties = {
                identity: party
                for party in (actor, contact)
                for identity in (party["id"], *party.get("aliases", ()))
            }
            for entry in thread["entries"]:
                party = parties[entry["sender"]]
                entry["portrait"] = party.get("portrait")
                entry["author_id"] = party["id"]
            return thread | {
                "sender": {k: v for k, v in actor.items() if k != "aliases"},
                "recipient": {k: v for k, v in contact.items() if k != "aliases"},
            }
        key, text = message
        return self.records.send_private(key, actor, target, text)

    def intel_pilots(self, connection, state):
        members = tables.members
        active = connection.scalars(
            sa.select(members.c.user_id).where(
                members.c.campaign_id == self.store.campaign_id,
                members.c.active.is_(True),
                members.c.user_id != str(self.handler.user_id),
            )
        )
        return {
            identity: sheet
            for identity in active
            if (sheet := state.sheets.get(identity)) and sheet.character_id
        }

    def share_intel(self, viewer, key, data):
        if data.keys() != {"room", "recipients", "text"} or not isinstance(data["room"], str):
            raise ValueError
        room, recipients, text = data["room"], data["recipients"], data["text"]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200:
            raise WorkflowError("Enter a discovery of 1 to 1200 characters.")
        if not isinstance(recipients, list) or not all(
            isinstance(item, str) for item in recipients
        ):
            raise ValueError
        if not recipients:
            raise WorkflowError("Choose at least one recipient.")
        self.check_room(viewer, room)
        with self.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            state = load_state(connection, self.store.campaign_id)
            pilots = self.intel_pilots(connection, state)
        sender = pilots.pop(str(viewer.user_id), None)
        selected = set(recipients)
        if not sender or not selected <= {sheet.character_id for sheet in pilots.values()}:
            raise WorkflowError("Choose other active pilots from this campaign.")
        return self.records.share_intel(viewer, key, room, sender, selected, text.strip())

    def enable_scene_plays(self, dice=None, *, extra_channels=()):
        if dice is not None:
            self.game.dice = dice
        self.scene_plays = ScenePlays(
            self.game,
            SCENE,
            self.handler,
            self.owner,
            self.recruit,
            lambda channel: channel in extra_channels or self.records.has_channel(channel),
            handler_proxy=not self.bound_roster,
            actor_lookup=self.activity_scene_actor if self.bound_roster else None,
            activity_cast_channels=extra_channels,
        )

    def activity_scene_actor(self, user_id):
        viewer = replace(self.owner, user_id=user_id)
        self.game.sheet(viewer)
        return viewer

    def join_tester(self, viewer):
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            if state.order and viewer.user_id not in state.order:
                raise WorkflowError(
                    "Enrollment for this cadre has closed. Contact the Handler for "
                    "campaign placement."
                )
        return self.store.join(viewer, f"discord-role-join-{viewer.user_id}")

    def handler_rooms(self):
        return self.records.bound_rooms() | {SCENE: (RELAY["id"], RELAY["name"])}

    def specialist_assignments(self, viewer, state):
        rooms = self.handler_rooms()
        return [
            {key: card[key] for key in ("id", "room", "room_name", "instruction", "decision")}
            for channel in sorted(am_work_channels(state, viewer) & rooms.keys())
            for card in SpecialistScene(self.game, channel).view(viewer, rooms[channel])
            if card.get("decision")
        ]

    def room_plays(self, viewer, target, *, enter=False):
        if not isinstance(target, str):
            raise TypeError
        if target == RELAY["id"]:
            if (
                enter
                and self.bound_roster
                and not self.game.scene_info(self.handler, SCENE)["joined"]
            ):
                self.game.join_scene(self.handler, "lab-handler-join-scene", SCENE)
            return self.scene_plays
        if viewer == self.handler and not self.scene_plays.handler_proxy and not enter:
            for channel, (room, _) in self.handler_rooms().items():
                if room == target:
                    return self.scene_plays.for_channel(channel)
            raise WorkflowError("Scene unavailable.")
        _, channel = self.records.play_room(viewer, target, allocate=enter)
        if channel is None:
            raise WorkflowError("Enter this scene first.")
        if enter:
            bootstrap = (
                replace(self.handler, is_administrator=True) if self.bound_roster else self.handler
            )
            self.game.bind_scene(bootstrap, f"activity-room-bind:{target}", channel)
            self.game.join_scene(self.handler, f"activity-room-handler:{target}", channel)
        return self.scene_plays.for_channel(channel)

    def room_play_directory(
        self, viewer, rooms, channels, state, safety, off_duty, *, scene_id=None
    ):
        active = None
        table = tables.m2["m2_scenes"]
        character = state.sheets[str(viewer.user_id)]
        specialist = {
            play["id"]
            for play in character_plays(self.play_registry, character, owns_sheet=True, state=state)
            if play["id"] in (PERSON, OLDGEN_ADVICE, SNOOP)
        }
        with self.store.engine.connect() as connection:
            native = {
                int(row["channel_id"]): (row, json.loads(row["participants_json"]))
                for row in connection.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.open.is_(True),
                    )
                ).mappings()
            }
            current_locks = {
                channel: lock
                for channel in native
                if (lock := self.game.lock(connection, channel)) and lock["state"] != "released"
            }
            casts = {cast.id for cast in state.scene_casts if cast.open}
            locked_memberships = [
                self.scene_plays.allows_parallel_membership(channel, row["id"], casts)
                for channel, (row, participants) in native.items()
                if channel in current_locks and viewer.user_id in participants
            ]
            for room in rooms:
                if room.get("archived_at") is not None:
                    continue
                if not room["joined"] and room["id"] != RELAY["id"]:
                    continue
                channel = channels.get(room["id"])
                row, participants = native.get(channel, (None, []))
                is_active = viewer.user_id in participants
                room["play_active"] = is_active
                if is_active and (scene_id is None or room["id"] == scene_id):
                    active = room
                reasons = self.scene_plays.start_reasons(viewer, state, participants)
                blockers = []
                current_play = None
                defeat_in_progress = None
                if safety["paused"]:
                    blockers.append({"code": "paused", "message": "A safety pause is active."})
                if lock := current_locks.get(channel):
                    blockers.append(
                        {
                            "code": "scene_busy",
                            "message": "Resolve the pending Play in this scene first.",
                        }
                    )
                    if is_active:
                        held = self.game.action(connection, lock["action_id"])
                        if held["parent_id"]:
                            held = self.game.action(connection, held["parent_id"])
                        current_play = held["data"]["play"]
                        if current_play == DEFEAT and held["actor_id"] == str(viewer.user_id):
                            defeat_in_progress = held["data"].get("defeat", {}).get("source_work")
                elif (
                    not is_active
                    and locked_memberships
                    and (
                        not all(locked_memberships)
                        or not self.scene_plays.allows_parallel_membership(
                            channel,
                            row["id"] if row else None,
                            casts,
                            unbound_room=room["joined"],
                        )
                    )
                ):
                    blockers.append(
                        {
                            "code": "switch_busy",
                            "message": "Resolve the pending Play before leaving its active scene.",
                        }
                    )
                if (
                    row
                    and not is_active
                    and not self.scene_plays.allows_cast(channel)
                    and row["id"] in casts
                ):
                    blockers.append(
                        {
                            "code": "cast_controls",
                            "message": "Use this scene’s original cast controls.",
                        }
                    )

                availability = {}
                adapter = self.scene_plays.for_channel(channel) if row else None
                play_ids = [play["id"] for play in SUPPORTED_ROOM_PLAYS]
                play_ids.extend(sorted(specialist))
                for identity in play_ids:
                    issues = [*blockers]
                    if reason := reasons.get(identity):
                        issues.append(reason)
                    if reason := off_duty.get(identity, {}).get("reason"):
                        issues.append({"code": "off_duty", "message": reason})
                    defeat_sources = []
                    if identity == DEFEAT:
                        if row:
                            defeat_sources = adapter.defeat_sources(
                                connection, viewer, state, row["id"]
                            )
                        if not defeat_sources and not defeat_in_progress:
                            issues.append(
                                {
                                    "code": "required_defeat",
                                    "message": (
                                        "HarpyEngine has assigned no Defeat to this pilot here."
                                    ),
                                }
                            )
                    if (
                        identity == DIVE
                        and is_active
                        and not issues
                        and (reason := adapter.dive_reason(connection, viewer, state))
                    ):
                        issues.append({"code": "dive", "message": reason})
                    if identity == REJECT_TAG and not any(
                        item.kind == REJECT_TAG
                        and item.owner == viewer.user_id
                        and item.state == "pending"
                        for item in state.obligations
                    ):
                        issues.append(
                            {
                                "code": "required_tag_rejection",
                                "message": (
                                    "HarpyEngine has assigned no Tag rejection to this pilot."
                                ),
                            }
                        )
                    if (
                        identity == PERSON
                        and is_active
                        and not issues
                        and (
                            reason := person_start(self.game, viewer, state, channel).get("reason")
                        )
                    ):
                        issues.append({"code": "conversation", "message": reason})
                    if identity == OLDGEN_ADVICE and is_active and not issues:
                        targets, reason = advice_targets(self.game, viewer, channel)
                        if not targets:
                            issues.append(
                                {
                                    "code": "advice",
                                    "message": reason or "Another eligible Girl must be present.",
                                }
                            )
                    if (
                        identity == SNOOP
                        and is_active
                        and not issues
                        and not snoop_targets(self.game, viewer, channel)
                    ):
                        issues.append(
                            {
                                "code": "snoop",
                                "message": "Snoop needs a paid Requisition and eligible property.",
                            }
                        )
                    state_label = (
                        "resume"
                        if identity == current_play
                        else "unavailable"
                        if issues
                        else "ready"
                    )
                    availability[identity] = {"state": state_label, "reasons": issues}
                    if identity == DEFEAT:
                        availability[identity]["sources"] = (
                            [defeat_in_progress]
                            if state_label == "resume" and defeat_in_progress
                            else [source["id"] for source in defeat_sources]
                        )
                room["play_availability"] = availability
                room["available_play_ids"] = [
                    identity
                    for identity, option in availability.items()
                    if option["state"] != "unavailable"
                ]
        return active

    def scene_projection(self, viewer, room, channel, canonical, sheet, state, safety, off_duty):
        native = self.game.scene_info(viewer, channel)
        joined = native["joined"]
        locked = bool(joined and native["lock"] and native["lock"]["state"] != "released")
        adapter = self.scene_plays.for_channel(channel)
        blocked = "keep_your_head" in adapter.start_reasons(viewer, state, native.get("pilots", []))
        options = (
            adapter.play_options(viewer, native, sheet, state, locked, safety["paused"], off_duty)
            if joined
            else {}
        )
        plays = {}
        if joined:
            pilot = state.sheets[str(viewer.user_id)]
            plays = {
                play["id"]: play
                for play in character_plays(
                    self.play_registry,
                    pilot,
                    owns_sheet=True,
                    state=state,
                    include_unimplemented=True,
                )
            }
            for play in SUPPORTED_ROOM_PLAYS:
                identity = play["id"]
                plays[identity] = plays.get(identity, {}) | play
            for identity, label in (
                (PERSON, "Bad at Being a Person"),
                (OLDGEN_ADVICE, "Old Dog, New Pups"),
            ):
                if identity not in plays and options.get(identity, {}).get("choices"):
                    plays[identity] = {
                        "id": identity,
                        "label": label,
                        "category": "talk",
                        "group": "girl",
                    }
            if self.bound_roster and options["receive_orders"]["current"]:
                plays["receive_orders"] = {
                    "id": "receive_orders",
                    "label": "Receive Orders",
                    "category": "talk",
                    "group": "basic",
                }
            if SNOOP not in plays and options[SNOOP]["choices"]:
                plays[SNOOP] = {
                    "id": SNOOP,
                    "label": "Snoop",
                    "category": "scan",
                    "group": "frame",
                }
            for identity in (PERSON, OLDGEN_ADVICE, SNOOP):
                if identity not in plays:
                    options.pop(identity, None)
                elif "rule_id" not in plays[identity]:
                    # Another character's specialist Play can require your response.
                    # Keep that original decision accessible without offering a fresh start.
                    options[identity]["can_start"] = False
            for identity, play in plays.items():
                if identity not in options and identity != "keep_your_head":
                    if play.get("blocked"):
                        play["reference_reason"] = "This Play is blocked on your sheet."
                    elif identity in BATTLEFIELD_PLAYS:
                        play["destination"] = "battlefield"
        return {
            "id": room["id"],
            "name": room["name"],
            "joined": joined,
            "locked": locked,
            "cancellation": adapter.cancellation(viewer) if joined else None,
            "safety": safety if joined else None,
            "keep": adapter.view(
                viewer,
                canonical,
                locked,
                safety["paused"],
                scene=native,
                blocked=blocked,
            )
            if joined
            else None,
            "options": options,
            "pilots": [native["labels"][str(uid)] for uid in native.get("pilots", [])],
            "pilot_ids": [str(uid) for uid in native.get("pilots", [])],
            "supported_play_ids": [play["id"] for play in SUPPORTED_ROOM_PLAYS],
            "plays": list(plays.values()),
            "specialist_work": self.scene_specialist_work(viewer, room, channel, joined),
        }

    def scene_specialist_work(self, viewer, room, channel, joined):
        if not self.bound_roster:
            return []
        label = room["id"], room["name"]
        cards = SpecialistScene(self.game, channel).view(viewer, label)
        if joined:
            return cards + SceneOrders(self.game, channel).view(viewer, label)
        return [card for card in cards if card["id"].startswith(DOLL_RETURN + ":")]

    def refresh_test_rank(self, key):
        # The lab assigns a starter order once both callsigns are on file.
        roster = self.handler_setup.roster(self.handler)
        if len(roster["pilots"]) < 2:
            return
        order = tuple(
            PilotRef(user_id=uid, character_revision=profile["revision"])
            for uid, profile in sorted(roster["pilots"].items())
        )
        with self.store.engine.connect() as connection:
            if self.bound_roster and load_state(connection, self.store.campaign_id).order:
                return
            current = self.handler_setup.current(connection)[1].status_order
        if order != tuple(current):
            if self.bound_roster:
                key = f"roster-rank-{roster['revision']}"
            self.handler_setup.rank(self.handler, key, roster["revision"], order)

    def bond_peer(self, viewer):
        return self.recruit if viewer == self.owner else self.owner

    def scene_invite_targets(self, viewer):
        return [
            {"id": row["id"], "name": row["name"], "pilot": row["pilot"]}
            for row in self.campaign_members(viewer)
            if not row["bot"]
            and (not row["handler"] or row["pilot"])
            and row["id"] != str(viewer.user_id)
        ]

    def validate_scene_invitees(self, viewer, recipients):
        if not isinstance(recipients, list) or not all(isinstance(id, str) for id in recipients):
            raise ValueError
        selected = set(recipients)
        if len(selected) != len(recipients) or (
            selected and not selected <= {row["id"] for row in self.scene_invite_targets(viewer)}
        ):
            raise WorkflowError("Choose distinct members of this campaign.")
        return selected

    def campaign_members(self, viewer):
        with self.store.engine.connect() as connection:
            self.game.authorize(connection, viewer, game=False)
            state = load_state(connection, self.store.campaign_id)
            ids = connection.scalars(
                sa.select(tables.members.c.user_id).where(
                    tables.members.c.campaign_id == self.store.campaign_id,
                    tables.members.c.active.is_(True),
                )
            ).all()
        people = []
        for identity in ids:
            sheet = state.sheets.get(identity)
            handler = identity == str(self.handler.user_id)
            people.append(
                {
                    "id": identity,
                    "name": "HarpyEngine"
                    if handler and identity == str(self.store.policy.application_id)
                    else sheet.callsign
                    if sheet
                    else (
                        (self.store.draft(viewer, int(identity)) or {}).get("callsign")
                        or ("Handler" if handler else "Recruit · " + identity[-4:])
                    ),
                    "handler": handler,
                    "bot": handler and identity == str(self.store.policy.application_id),
                    "enrolled": handler or sheet is not None,
                    "pilot": sheet is not None,
                }
            )
        return sorted(
            people,
            key=lambda person: (not person["enrolled"], person["name"].casefold()),
        )

    def view(self, viewer, *, pilot_mode=False, scene_id=None):
        if viewer == self.handler and not (self.bound_roster and pilot_mode):
            with self.store.engine.connect() as connection:
                self.game.authorize(connection, viewer, game=False)
                state = load_state(connection, self.store.campaign_id)
            record = {
                "stage": "handler",
                "off_duty": self.off_duty.view(viewer),
                "show_dog_mail": self.off_duty.show_dog.correspondence(viewer)
                if self.bound_roster
                else [],
                "specialist_assignments": self.specialist_assignments(viewer, state)
                if self.bound_roster
                else [],
                "callsign": (self.store.draft(viewer) or {}).get("callsign") or "Handler",
                "communications": self.communication_view(viewer, state),
                "bonds": [],
            }
            if self.records:
                pilot_callsigns = {identity: sheet.callsign for identity, sheet in state.sheets.items()}
                try:
                    relay_pilots = [str(uid) for uid in self.game.scene_info(viewer, SCENE).get("pilots", ())]
                except WorkflowError:
                    relay_pilots = []
                record["scene_activity"] = scene_activity(
                    self.records.directory(viewer, pilot_callsigns), pilot_callsigns, relay_pilots
                )
            if self.bound_roster:
                followups = self.owned_followups.view(viewer)
                punishments = self.handler_punishments.view(viewer)
                record["creation_choices"] = self.enrollment_choices.view(viewer, ())
                record["handler_playbook"] = self.handler_playbook.view(viewer)
                record["handler_punishments"] = (
                    punishments + followups + self.handler_playbook.dress_work(viewer)
                )
                record["handler_notices"] = self.handler_playbook.notices(viewer)
                record["career_status"] = [
                    item | {"owner": str(item["owner"])}
                    for item in CareerService(self.store).status_requests(viewer)
                    if item["position"] is None
                ] + self.handler_setup.late_wing_requests(viewer)
                record["scene_beneath_work"] = self.beneath_work.view(
                    viewer, followups, punishments
                )
                rooms = self.handler_rooms()
                record["specialist_work"] = [
                    card
                    for channel, room in rooms.items()
                    for card in (
                        SpecialistScene(self.game, channel).view(viewer, room)
                        + SceneOrders(self.game, channel).view(viewer, room)
                    )
                ]
                record["handler_choices"] = [
                    {
                        **card,
                        "room": rooms[card["channel"]][0],
                        "room_name": rooms[card["channel"]][1],
                    }
                    for card in self.scene_plays.handler_choices(viewer)
                    if card["channel"] in rooms
                ]
            elif self.scene_plays and not self.scene_plays.handler_proxy:
                rooms = self.handler_rooms()
                record["handler_choices"] = [
                    {
                        **card,
                        "room": rooms[card["channel"]][0],
                        "room_name": rooms[card["channel"]][1],
                    }
                    for card in self.scene_plays.handler_choices(viewer)
                    if card["channel"] in rooms
                ]
            if self.scene_plays:
                cancellation_rooms = (
                    self.handler_rooms() if self.records else {SCENE: (RELAY["id"], RELAY["name"])}
                )
                record["scene_cancellations"] = [
                    cancellation | {"room": room, "room_name": name}
                    for channel, (room, name) in cancellation_rooms.items()
                    if (cancellation := self.scene_plays.for_channel(channel).cancellation(viewer))
                    and cancellation["can_cancel"]
                ]
            return record
        profile = self.store.draft(viewer)
        bonds = []
        bond_history = []
        for item in self.bonds.list(viewer):
            if item["stale"] or item["state"] not in ("pending", "accepted", "declined", "withdrawn"):
                continue
            if not self.bound_roster and str(self.recruit.user_id) not in (
                item["source_id"],
                item["target_id"],
            ):
                continue
            incoming = item["target_id"] == str(viewer.user_id)
            bond = {
                "id": item["id"],
                "revision": item["revision"],
                "state": item["state"],
                "incoming": incoming,
                "prompt": PROMPTS[item["girl_playbook"]][item["prompt"]],
                "context": item["context"],
            }
            if self.bound_roster:
                counterpart = int(item["source_id"] if incoming else item["target_id"])
                peer = self.store.draft(viewer, counterpart)
                bond["counterpart"] = peer["callsign"] if peer else None
            records = bonds if item["state"] in ("pending", "accepted") else bond_history
            records.append(bond)
        creation_choices = (
            self.enrollment_choices.view(viewer, bonds) if self.bound_roster else None
        )
        bond_setup = (
            self.bonds.enrollment_options(viewer) if self.bound_roster and profile else None
        )
        if bond_setup:
            bond_setup["prompts"] = list(PROMPTS[profile["girl_playbook"]])
        canonical = profile.get("canonical") if profile else None
        if canonical:
            with self.store.engine.connect() as connection:
                game_state = load_state(connection, self.store.campaign_id)
                intel_pilots = self.intel_pilots(connection, game_state)
            pilot_callsigns = {actor: sheet.callsign for actor, sheet in game_state.sheets.items()}
        else:
            pilot_callsigns = {}
        rooms = self.records.directory(viewer, pilot_callsigns) if self.records else []
        channels = {room["id"]: room.pop("_channel") for room in rooms}
        channels[RELAY["id"]] = SCENE
        if canonical:
            own_sheet = self.game.sheet(viewer)
            self.game.gate()
            safety = self.scene_plays.safety_status(viewer)
            rooms.insert(
                0,
                RELAY
                | {
                    "joined": self.relay_member(viewer),
                    "can_invite": viewer == self.owner,
                },
            )
        directory = {
            "locations": scene_locations(rooms),
            "rooms": rooms,
            "can_create": bool(canonical),
            "can_invite_campaign": viewer == self.owner and not self.bound_roster,
        }
        scene_invites = self.records.scene_invites(viewer) if self.records else []
        if canonical:
            artwork = self.records.artwork() if self.records else {}
            for room in rooms:
                room["artwork"] = artwork.get(("scene", room["id"])) if room["joined"] else None
            descriptions = (
                self.records.asset_descriptions(viewer, canonical["character_id"])
                if self.records
                else {}
            )
            cadre = []
            for sheet in game_state.sheets.values():
                public = public_sheet(sheet, game_state)
                cadre.append(
                    {
                        "id": str(sheet.owner),
                        "callsign": public["callsign"],
                        "status": public.get("rank"),
                        "frame": public["frame_playbook"],
                        "frame_class": FRAME_CLASSES.get(sheet.frame),
                        "frame_name": public.get("frame_name"),
                        "artwork": artwork.get(("pilot", sheet.character_id)),
                        "frame_artwork": artwork.get(
                            (
                                "frame",
                                frame_subject(
                                    sheet.character_id,
                                    sheet.frame,
                                    sheet.frame_runtime.id if sheet.frame_runtime else None,
                                ),
                            )
                        ),
                        "girl": public["girl_playbook"],
                        "plays": character_plays(
                            self.play_registry,
                            sheet,
                            owns_sheet=sheet.owner == viewer.user_id,
                            state=game_state,
                        ),
                        "own": sheet.owner == viewer.user_id,
                    }
                )
            off_duty = self.scene_plays.off_duty_status(viewer)
            active_room = self.room_play_directory(
                viewer, rooms, channels, game_state, safety, off_duty, scene_id=scene_id
            )
            relay = self.scene_projection(
                viewer,
                rooms[0],
                SCENE,
                canonical,
                own_sheet,
                game_state,
                safety,
                off_duty,
            )
            active_scene = (
                self.scene_projection(
                    viewer,
                    active_room,
                    channels[active_room["id"]],
                    canonical,
                    own_sheet,
                    game_state,
                    safety,
                    off_duty,
                )
                if active_room and active_room["id"] != RELAY["id"]
                else relay
                if active_room
                else None
            )
            followups = self.owned_followups.view(viewer) if self.bound_roster else []
            punishments = self.handler_punishments.view(viewer) if self.bound_roster else []
            archived_rooms = {room["id"] for room in rooms if room.get("archived_at") is not None}
            intel_pilot = intel_pilots.pop(str(viewer.user_id), None)
            return {
                "stage": "active",
                "frame_purchase": FramePurchases(self.game).view(viewer)
                if self.bound_roster
                else None,
                "scene_beneath_work": self.beneath_work.view(viewer, followups, punishments)
                if self.bound_roster
                else [],
                "handler_punishments": (
                    punishments + followups + self.handler_playbook.dress_work(viewer)
                )
                if self.bound_roster
                else [],
                "handler_notices": self.handler_playbook.notices(viewer)
                if self.bound_roster
                else [],
                "off_duty": self.off_duty.view(viewer),
                "show_dog_mail": self.off_duty.show_dog.correspondence(viewer)
                if self.bound_roster
                else [],
                "specialist_assignments": self.specialist_assignments(viewer, game_state)
                if self.bound_roster
                else [],
                "callsign": canonical["callsign"],
                "sheet_reset": {
                    "callsign": canonical["callsign"],
                    "character": own_sheet["character_id"],
                    "revision": own_sheet["revision"],
                }
                if self.bound_roster
                else None,
                "directory": directory,
                "cadre": cadre,
                "scene_activity": scene_activity(rooms, pilot_callsigns, relay["pilot_ids"]),
                "communications": self.communication_view(viewer, game_state),
                "intel_targets": [
                    {"id": sheet.character_id, "callsign": sheet.callsign}
                    for sheet in sorted(
                        intel_pilots.values(), key=lambda sheet: sheet.callsign.casefold()
                    )
                ]
                if intel_pilot and self.records
                else [],
                "intel_mail": self.records.intel_mail(intel_pilot.character_id)
                if intel_pilot and self.records
                else [],
                "bonds": bonds,
                "bond_history": bond_history,
                "creation_choices": creation_choices,
                "bond_setup": bond_setup,
                "scene": relay,
                "scene_invites": scene_invites,
                "scene_invite_targets": self.scene_invite_targets(viewer) if self.records else [],
                "active_scene": active_scene,
                "scene_mail": self.scene_plays.receipts(
                    viewer,
                    {
                        str(channels[room["id"]]): room["id"]
                        for room in rooms
                        if room["joined"]
                        and room["id"] not in archived_rooms
                        and channels.get(room["id"]) is not None
                    },
                    limit=25,
                )
                + (self.records.archived_receipts(viewer, archived_rooms) if self.records else []),
                "profile": {
                    "status": next(pilot["status"] for pilot in cadre if pilot["own"]),
                    "heat": own_sheet["heat"],
                    "frame": own_sheet["frame"],
                    "upgrades": frame_upgrades(self.play_registry, own_sheet.get("frame_runtime")),
                    "frame_name": (
                        own_sheet.get("frame_runtime") or own_sheet["review"]["creation"]
                    )["frame_name"],
                    "tags": [tag["label"] for tag in own_sheet["tags"]],
                    "identities": [
                        {"name": identity["name"], "marked": identity["marked"]}
                        for identity in own_sheet["identities"]
                        + own_sheet.get("additional_identities", [])
                    ],
                    **profile_assets(own_sheet["assets"], descriptions),
                },
            }
        if not self.bound_roster and viewer != self.recruit:
            raise WorkflowError("This lab did not seed an active Pilot for this account.")

        options = {
            "girl": profile["girl_playbook"] if profile else GIRL,
            "frame": profile["frame_playbook"] if profile else canonical_frame(FRAME),
            **({"girls": GIRL_TYPES, "frames": FRAME_TYPES} if self.bound_roster else {}),
        }
        enrollment = None
        reset_pending = False
        if self.bound_roster:
            if profile:
                with self.store.engine.connect() as c:
                    reset_pending = bool(
                        awaiting_replacement(load_state(c, self.store.campaign_id), viewer.user_id)
                    )
            portrait = (
                self.records.artwork().get(("pilot", profile["id"]))
                if profile and self.records and not reset_pending
                else None
            )
            enrollment = {"owner_id": str(viewer.user_id), "portrait": portrait}
        if not profile or profile["callsign"] == "RECRUIT" or reset_pending:
            return {
                "stage": "profile",
                "revision": profile["revision"] if profile else 0,
                "options": options,
                "bonds": bonds,
                "bond_history": bond_history,
                "creation_choices": creation_choices,
                "directory": directory,
                "scene_invites": scene_invites,
                "enrollment": enrollment,
            }
        try:
            progress = self.creation.get(viewer)
        except ValueError as error:
            # An unmigrated cosmetic draft can be repaired by its actual owner
            # using the native revision-checked profile save. Never rewrite history.
            if profile.get("frame_playbook") != "JANUS-B":
                raise WorkflowError(
                    "The saved enrollment needs engine validation. Its records have been preserved."
                ) from error
            with self.store.engine.connect() as connection:
                saved_choices = connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(tables.creation_drafts)
                    .where(
                        tables.creation_drafts.c.campaign_id == self.store.campaign_id,
                        tables.creation_drafts.c.user_id == str(viewer.user_id),
                    )
                )
            if saved_choices:
                raise WorkflowError(
                    "This saved enrollment requires a JANUS history migration. Its choices "
                    "have been preserved."
                ) from error
            return {
                "stage": "profile",
                "callsign": profile["callsign"],
                "revision": profile["revision"],
                "options": options | {"frame": "JANUS"},
                "bonds": bonds,
                "bond_history": bond_history,
                "creation_choices": creation_choices,
                "directory": directory,
                "enrollment": enrollment,
                "scene_invites": scene_invites,
                "recovery_notice": (
                    "A previous Frame label is no longer supported. Confirm JANUS and save "
                    "your callsign to resume enrollment. Your notes and profile picture are "
                    "retained."
                ),
            }
        review = self.review.get(viewer)
        peer = self.bond_peer(viewer).user_id
        bond_target = None
        if not self.bound_roster:
            bond_target = self.bonds.prepare(viewer, peer)
        draft = progress.draft.model_dump(mode="json")
        for entry in draft["prior_missions"]:
            entry["user_id"] = str(entry["user_id"])
        return {
            "stage": "draft",
            "directory": directory,
            "scene_invites": scene_invites,
            "callsign": profile["callsign"],
            "revision": progress.revision,
            "character_revision": progress.character_revision,
            "draft": draft,
            "options": {
                **options,
                "girl_assets": CATALOG[options["girl"]]["assets"],
                "frame_assets": CATALOG[official_frame(options["frame"])]["assets"],
                "npc_roles": NPC_ROLES[options["girl"]],
                "bond_prompts": PROMPTS[options["girl"]],
            },
            "bond_target": bond_target,
            "bond_setup": bond_setup,
            "select_starting_bond": self.bound_roster,
            "enrollment": enrollment
            | {
                "pair_names": list(progress.pair_choice.names) if progress.pair_choice else [],
                "cadre": [
                    {
                        "id": str(uid),
                        "revision": row["revision"],
                        "callsign": row["label"],
                    }
                    for uid, row in self.creation.cadre(viewer).items()
                ]
                if options["girl"] == "NEWGIRL"
                else [],
            }
            if enrollment
            else None,
            "bonds": bonds,
            "bond_history": bond_history,
            "creation_choices": creation_choices,
            "review": {
                "ready": review.sheet.ready_for_rules_review,
                "saved": review.saved_current,
                "revision": review.saved_revision,
                "fingerprint": review.fingerprint,
                "status": review.sheet.status,
                "identities": review.sheet.creation.identities,
                "issues": [
                    item.message
                    for item in review.sheet.issues
                    if item.code != "independent_review"
                ],
            },
        }

    def perform(self, viewer, key, step, data):
        if step == "bot-enrollment" and self.bound_roster:
            return self.bot_enrollment.request(viewer, key, data)
        if step == "share-intel" and self.records:
            return self.share_intel(viewer, key, data)
        if step == "room-end" and self.records:
            if data.keys() != {"room"} or not isinstance(data["room"], str):
                raise ValueError("Choose a scene you host.")
            return self.end_room(viewer, data["room"])
        if step == "frame-purchase" and self.bound_roster and viewer != self.handler:
            return FramePurchases(self.game).perform(viewer, key, data)
        if step == "frame-acquire-rule" and self.bound_roster and viewer != self.handler:
            return FramePurchases(self.game).acquire(viewer, key, data)
        if step == "purge-sheet" and self.bound_roster and viewer != self.handler:
            return purge_sheet(self.game, viewer, key, data)
        if step == "career-status" and self.bound_roster and viewer == self.handler:
            if data.keys() == {"owner", "character_revision", "setup_revision", "late_wing"}:
                owner = data["owner"]
                if (
                    data["late_wing"] is not True
                    or type(data["character_revision"]) is not int
                    or type(data["setup_revision"]) is not int
                    or not isinstance(owner, str)
                    or not owner.isascii()
                    or not owner.isdecimal()
                    or not 0 < len(owner) <= 20
                ):
                    raise ValueError("Use the current Wing placement record.")
                return self.handler_setup.assign_late_wing(
                    viewer,
                    key,
                    data["setup_revision"],
                    PilotRef(user_id=int(owner), character_revision=data["character_revision"]),
                )
            if (
                data.keys() != {"owner", "character", "revision", "position"}
                or type(data["revision"]) is not int
                or type(data["position"]) is not int
                or not isinstance(data["owner"], str)
                or not data["owner"].isascii()
                or not data["owner"].isdecimal()
                or len(data["owner"]) > 20
                or not isinstance(data["character"], str)
            ):
                raise ValueError("Use the current replacement Status request.")
            return CareerService(self.store).assign_status(
                viewer,
                key,
                int(data["owner"]),
                data["character"],
                data["revision"],
                data["position"],
            )
        if step in ("scene-specialist", "scene-orders") and self.bound_roster:
            try:
                adapter = self.room_plays(viewer, data["room"])
                returning = (
                    step == "scene-specialist"
                    and data["answer"]["operation"].partition(":")[0] == DOLL_RETURN
                )
                if (
                    viewer != self.handler
                    and not returning
                    and not self.game.scene_info(viewer, adapter.channel)["joined"]
                ):
                    raise WorkflowError("Enter the original scene first.")
                service = SceneOrders if step == "scene-orders" else SpecialistScene
                return service(self.game, adapter.channel).perform(viewer, key, data)
            except (KeyError, TypeError, AttributeError) as error:
                raise ValueError("Use the fields from the current specialist form.") from error
        if step == "creation-choice" and self.bound_roster:
            try:
                return self.enrollment_choices.perform(viewer, key, data)
            except (KeyError, TypeError) as error:
                raise ValueError("Choose an available enrollment decision.") from error
        if step == "scene-beneath-work" and self.bound_roster:
            return self.beneath_work.perform(viewer, key, data)
        if step == "handler-punishment" and self.bound_roster:
            if data.get("action") == "dress_performance":
                return self.handler_playbook.perform_dress(viewer, key, data)
            if isinstance(data.get("action"), str) and (
                data["action"].startswith(("feedback_", "followup_"))
                or data["action"] == "resolve_void"
                or data["action"] in CONTINUATION_ACTIONS
            ):
                try:
                    return self.owned_followups.perform(viewer, key, data)
                except (KeyError, IndexError, AttributeError) as error:
                    raise ValueError("Choose the current follow-up fields.") from error
            return self.handler_punishments.perform(viewer, key, data)
        if step.startswith("handler-play-") and self.bound_roster:
            if viewer != self.handler:
                raise WorkflowError("Only this campaign's Handler can make Handler Plays.")
            room = data.get("room") if step == "handler-play-start" else None
            channel = self.room_plays(viewer, room).channel if room is not None else None
            return self.handler_playbook.perform(viewer, key, step, data, scene_channel=channel)
        if step == "off-duty-followup":
            return self.off_duty.perform(viewer, key, data)
        if self.records and step == "artwork":
            if data.keys() != {"kind", "target", "artwork", "previous"}:
                raise ValueError
            kind, target = data["kind"], data["target"]
            if not isinstance(kind, str) or kind not in KINDS or not isinstance(target, str):
                raise ValueError
            validate_selection(kind, data["artwork"])
            validate_selection(kind, data["previous"])
            if kind == "scene":
                self.game.sheet(viewer)
                subject = target
            else:
                if target != str(viewer.user_id):
                    raise WorkflowError("Select artwork for your own pilot or assigned Frame.")
                if kind == "pilot" and self.bound_roster:
                    profile = self.store.draft(viewer)
                    subject = profile["id"] if profile else None
                else:
                    own_sheet = self.game.sheet(viewer)
                    subject = own_sheet.get("character_id")
                if not subject:
                    raise WorkflowError(
                        "This pilot needs a saved character before selecting artwork."
                    )
                if kind == "frame":
                    runtime = own_sheet.get("frame_runtime") or {}
                    subject = frame_subject(subject, own_sheet["frame"], runtime.get("id"))
            return self.records.select_artwork(
                viewer, kind, subject, data["artwork"], data["previous"]
            )
        if self.records and step == "room-post" and data.keys() == {"target", "text"}:
            if not isinstance(data["text"], str) or not 1 <= len(data["text"].strip()) <= 1200:
                raise WorkflowError("Enter dialogue or narration of 1 to 1200 characters.")
            pilot = self.check_room(viewer, data["target"], posting=True)
            adapter = self.room_plays(viewer, data["target"], enter=True)
            adapter.enter(viewer, "dialogue-join:" + key)
            return self.records.post_dialogue(
                viewer,
                key,
                pilot["callsign"],
                data["target"],
                data["text"],
                character=pilot.get("character_id"),
            )
        if self.records and step in ("scene-invite", "scene-invite-decision"):
            if step == "scene-invite":
                self.game.sheet(viewer)
                if data.keys() != {"room", "recipient"} or not all(
                    isinstance(value, str) for value in data.values()
                ):
                    raise ValueError
                recipient = data["recipient"]
                self.validate_scene_invitees(viewer, [recipient])
                return self.records.issue_scene_invite(viewer, key, data["room"], recipient)
            if (
                data.keys() != {"id", "decision"}
                or not isinstance(data["id"], str)
                or data["decision"] not in ("accept", "decline")
            ):
                raise ValueError
            with self.store.engine.connect() as connection:
                self.game.authorize(connection, viewer, game=False)
            return self.records.decide_scene_invite(viewer, data["id"], data["decision"])
        if self.records and step in (
            "room-create",
            "invite-issue",
            "invite-redeem",
            "asset-description",
        ):
            profile = self.store.draft(viewer)
            if step == "invite-redeem":
                return self.records.redeem(viewer, data)
            canonical = profile.get("canonical") if profile else None
            if not canonical:
                raise WorkflowError("Activate your own pilot to use these records.")
            if step == "room-create":
                form = dict(data)
                recipients = self.validate_scene_invitees(viewer, form.pop("recipients", []))
                return self.records.create_room(viewer, key, form, recipients=recipients)
            if step == "invite-issue":
                return self.records.issue(viewer, key, data)
            asset = next(
                (
                    item
                    for item in canonical["assets"]
                    if item["family"] in ("girl", "frame") and item["id"] == data.get("asset")
                ),
                None,
            )
            if asset is None:
                raise WorkflowError("You can edit descriptions for your own Girl and Frame assets.")
            return self.records.describe_asset(viewer, canonical["character_id"], asset["id"], data)
        if self.scene_plays and step == "enter-scene":
            if data.keys() not in ({"room"}, {"room", "play"}) or data.get("play") not in (
                None,
                PERSON,
                OLDGEN_ADVICE,
                SNOOP,
                *(play["id"] for play in SUPPORTED_ROOM_PLAYS),
            ):
                raise ValueError
            self.game.sheet(viewer)
            adapter = self.room_plays(viewer, data["room"], enter=True)
            return adapter.enter(viewer, key, data.get("play"))
        if self.scene_plays and step == "scene-cancel":
            target = data.pop("room", RELAY["id"])
            return self.room_plays(viewer, target).cancel(viewer, key, data)
        if self.scene_plays and step in (
            "keep-start",
            "keep-choice",
            "scene-start",
            "scene-choice",
            "scene-safety",
        ):
            target = data.pop("room", RELAY["id"])
            adapter = self.room_plays(viewer, target)
            if not self.game.scene_info(viewer, adapter.channel)["joined"]:
                raise WorkflowError("Enter the selected scene to use its Plays.")
            if step.startswith("keep-"):
                return adapter.perform(viewer, key, step, data)
            if step == "scene-safety":
                return adapter.safety(viewer, key, data)
            return adapter.perform_scene(viewer, key, step, data)
        if step == "bond-decision" and data.keys() == {"id", "revision", "decision"}:
            decisions = (
                ("accept", "decline", "withdraw") if self.bound_roster else ("accept", "decline")
            )
            if (
                not isinstance(data["id"], str)
                or type(data["revision"]) is not int
                or data["decision"] not in decisions
            ):
                raise ValueError
            return self.bonds.decide(viewer, key, data["id"], data["revision"], data["decision"])
        if self.bound_roster and step == "bond":
            if data.keys() != {
                "target",
                "source_revision",
                "target_revision",
                "prompt",
                "context",
            }:
                raise ValueError
            target = data["target"]
            if (
                not isinstance(target, str)
                or not target.isascii()
                or not target.isdecimal()
                or not 17 <= len(target) <= 20
                or any(
                    type(data[field]) is not int
                    for field in ("source_revision", "target_revision", "prompt")
                )
            ):
                raise ValueError
            proposal = BondProposal(
                target_id=int(target), prompt=data["prompt"], context=data["context"]
            )
            return self.bonds.propose(
                viewer, key, data["source_revision"], data["target_revision"], proposal
            )
        if step == "join-scene" and not data:
            self.game.sheet(viewer)
            return self.room_plays(viewer, RELAY["id"], enter=True).enter(viewer, key)
        if not self.bound_roster and (viewer == self.handler or viewer != self.recruit):
            raise WorkflowError("Character creation belongs to the pilot.")
        if step == "profile" and data.keys() in (
            {"revision", "callsign"},
            {"revision", "callsign", "girl_playbook", "frame_playbook"},
        ):
            if type(data["revision"]) is not int:
                raise ValueError
            current = self.store.draft(viewer)
            archive = None
            if self.bound_roster:
                with self.store.engine.connect() as connection:
                    state = load_state(connection, self.store.campaign_id)
                    archive = awaiting_replacement(state, viewer.user_id)
            try:
                draft = DraftInput(
                    callsign=data["callsign"],
                    girl_playbook=data.get("girl_playbook", GIRL) if self.bound_roster else GIRL,
                    frame_playbook=data.get("frame_playbook", FRAME)
                    if self.bound_roster
                    else FRAME,
                    notes=current.get("notes", "") if current and not archive else "",
                )
            except ValidationError as error:
                raise _enrollment_validation(error, data) from None
            if draft.callsign.casefold() == "recruit":
                raise EnrollmentInputError(
                    [
                        {"path": ["callsign"], "message": "Choose a callsign for your Pilot."},
                    ],
                    conflict=True,
                )
            if archive:
                if data["revision"] != current["revision"]:
                    raise WorkflowError("Reopen the replacement enrollment before saving.")
                return CareerService(self.store).begin_replacement(
                    viewer, key, archive.id, state.revision, draft
                )
            result = self.store.save_draft(viewer, key, data["revision"], draft)
            if not self.bot_enrollment.enabled():
                self.refresh_test_rank("lab-rank-" + str(result["revision"]))
            return result
        if step == "build" and data.keys() - {"pair_token", "shared_tokens"} == {
            "revision",
            "character_revision",
            "draft",
        }:
            if (
                type(data["revision"]) is not int
                or type(data["character_revision"]) is not int
                or not isinstance(data["draft"], dict)
            ):
                raise ValueError
            fields = data["draft"]
            if not fields.keys() <= OWNER_CREATION_FIELDS:
                raise ValueError("Only owner-controlled starting choices can be saved.")
            if isinstance(history := fields.get("prior_missions"), list):
                # Discord IDs travel as text in the Activity. The engine still
                # checks exact integer identities against the current Cadre.
                adapted = []
                for index, entry in enumerate(history):
                    identity = entry.get("user_id") if isinstance(entry, dict) else None
                    if isinstance(identity, str):
                        try:
                            entry = entry | {"user_id": _snowflake(identity)}
                        except ValueError:
                            raise EnrollmentInputError(
                                [
                                    {
                                        "path": ["prior_missions", index, "user_id"],
                                        "message": "Choose a current Cadre member.",
                                    }
                                ]
                            ) from None
                    adapted.append(entry)
                fields = fields | {"prior_missions": adapted}
            current = self.creation.get(viewer).draft
            try:
                draft = CreationDraft.model_validate_json(
                    json.dumps(
                        current.model_dump(mode="json")
                        | fields
                        | {"shared_tokens": data.get("shared_tokens", current.shared_tokens)}
                    )
                )
            except ValidationError as error:
                raise _enrollment_validation(error, fields) from None
            try:
                return self.creation.save(
                    viewer,
                    key,
                    data["revision"],
                    data["character_revision"],
                    draft,
                    expected_pair_token=data.get("pair_token"),
                )
            except WorkflowError as error:
                if str(error) == "Discuss and declare history for every current Cadre counterpart.":
                    raise EnrollmentInputError(
                        [
                            {
                                "path": ["prior_missions"],
                                "message": (
                                    "Answer for every current Cadre member "
                                    "before confirming the discussion."
                                ),
                            }
                        ],
                        conflict=True,
                    ) from None
                raise
        if (
            self.bound_roster
            and step == "select-bond"
            and data.keys() == {"id", "revision", "character_revision"}
        ):
            if (
                not isinstance(data["id"], str)
                or type(data["revision"]) is not int
                or type(data["character_revision"]) is not int
            ):
                raise ValueError
            current = self.creation.get(viewer)
            return self.review.select_bond(
                viewer,
                key,
                data["revision"],
                data["character_revision"],
                current.draft,
                data["id"],
            )
        if step == "bond" and data.keys() == {
            "source_revision",
            "target_revision",
            "prompt",
            "context",
        }:
            if any(
                type(data[field]) is not int for field in ("source_revision", "target_revision")
            ):
                raise ValueError
            bond = BondProposal(
                target_id=self.bond_peer(viewer).user_id,
                prompt=data["prompt"],
                context=data["context"],
            )
            return self.bonds.propose(
                viewer, key, data["source_revision"], data["target_revision"], bond
            )
        if step == "review" and data.keys() == {"revision", "fingerprint"}:
            if type(data["revision"]) is not int or not isinstance(data["fingerprint"], str):
                raise ValueError
            return self.review.save(viewer, key, data["revision"], data["fingerprint"])
        if step == "activate" and data.keys() == {"fingerprint"}:
            if not isinstance(data["fingerprint"], str):
                raise ValueError
            return self.game.activate(viewer, key, data["fingerprint"])
        raise ValueError
