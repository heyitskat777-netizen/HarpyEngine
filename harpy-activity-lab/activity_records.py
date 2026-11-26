"""Local campaign directory, invitations, and personnel-file descriptions."""

import json
import re
import secrets
import sqlite3
from contextlib import closing
from hashlib import sha256
from time import time

from girlframe.services.onboarding import WorkflowError

LEGACY_LOCATIONS = {
    "hangar": {"id": "hangar", "name": "Hangar Deck", "area": "Foundation"},
    "outpost": {"id": "outpost", "name": "Outpost K-12", "area": "Mountain Sector"},
}
LOCATION_ALIASES = {
    label.casefold(): identity
    for identity, location in LEGACY_LOCATIONS.items()
    for label in (identity, location["name"])
}
RELAY = {
    "id": "relay",
    "name": "Relay operations",
    "location": "hangar",
    "location_name": LEGACY_LOCATIONS["hangar"]["name"],
    "kind": "engine",
}
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVITE_LIFETIME = 86400


def location_fields(stored):
    if not stored:
        return {"location": None, "location_name": None}
    if stored in LEGACY_LOCATIONS:
        return {"location": stored, "location_name": LEGACY_LOCATIONS[stored]["name"]}
    identity = sha256(stored.casefold().encode("utf-8")).hexdigest()[:24]
    return {"location": f"location-{identity}", "location_name": stored}


def scene_locations(rooms):
    locations = {}
    for room in rooms:
        if room.get("archived_at") is not None or (identity := room["location"]) is None:
            continue
        locations[identity] = LEGACY_LOCATIONS.get(
            identity, {"id": identity, "name": room["location_name"], "area": ""}
        )
    return sorted(locations.values(), key=lambda location: location["name"].casefold())


def profile_assets(assets, descriptions):
    files = {"girl": [], "frame": []}
    for asset in assets:
        if asset["family"] not in files:
            continue
        description, revision = descriptions.get(asset["id"], (asset["description"], 0))
        files[asset["family"]].append(
            {
                "id": asset["id"],
                "name": asset["name"],
                "damaged": asset["damaged"],
                "void": asset["void"],
                "description": description,
                "description_revision": revision,
            }
        )
    return {"girl_assets": files["girl"], "assets": files["frame"]}


class ActivityRecords:
    def __init__(self, path, owner, *, campaign_codes=True):
        self.path = path
        self.owner = owner
        self.campaign_codes = campaign_codes
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL,
                    owner INTEGER NOT NULL, request_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS participants (
                    room TEXT NOT NULL, actor INTEGER NOT NULL, PRIMARY KEY (room, actor)
                );
                CREATE TABLE IF NOT EXISTS scene_archives (
                    room TEXT PRIMARY KEY, closed_at INTEGER NOT NULL,
                    dialogue_json TEXT NOT NULL, views_json TEXT NOT NULL,
                    pilots_json TEXT
                );
                CREATE TABLE IF NOT EXISTS room_channels (
                    room TEXT PRIMARY KEY, channel INTEGER NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    code TEXT PRIMARY KEY, recipient INTEGER, room TEXT NOT NULL,
                    expires INTEGER NOT NULL, request_key TEXT NOT NULL UNIQUE, issuer
                      INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scene_invites (
                    id TEXT PRIMARY KEY, room TEXT NOT NULL, issuer INTEGER NOT NULL,
                    recipient TEXT NOT NULL, expires INTEGER NOT NULL,
                    request_key TEXT NOT NULL UNIQUE, decision TEXT
                );
                CREATE INDEX IF NOT EXISTS scene_invites_recipient ON scene_invites (recipient);
                CREATE TABLE IF NOT EXISTS descriptions (
                    actor INTEGER NOT NULL, character TEXT NOT NULL, asset TEXT NOT NULL,
                    text TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY (actor,
                      character, asset)
                );
                CREATE TABLE IF NOT EXISTS artwork (
                    kind TEXT NOT NULL, subject TEXT NOT NULL, art_id TEXT NOT NULL,
                    PRIMARY KEY (kind, subject)
                );
                CREATE TABLE IF NOT EXISTS dialogue (
                    room TEXT NOT NULL, actor INTEGER NOT NULL, callsign TEXT NOT NULL,
                    body TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, created INTEGER NOT NULL,
                    author_character TEXT
                );
                CREATE TABLE IF NOT EXISTS private_messages (
                    id INTEGER PRIMARY KEY, sender TEXT NOT NULL, recipient TEXT NOT NULL,
                    callsign TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL,
                    request_key TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS private_messages_pair
                    ON private_messages (sender, recipient, id);
                CREATE INDEX IF NOT EXISTS private_messages_recipient
                    ON private_messages (recipient, sender, id);
                CREATE TABLE IF NOT EXISTS scene_intel (
                    id INTEGER PRIMARY KEY, room TEXT NOT NULL, sender TEXT NOT NULL,
                    callsign TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL,
                    request_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS scene_intel_recipients (
                    recipient TEXT NOT NULL, report INTEGER NOT NULL, PRIMARY KEY
                      (recipient, report)
                );
                """
            )
            db.execute("BEGIN IMMEDIATE")
            if not any(
                row[1] == "author_character" for row in db.execute("PRAGMA table_info(dialogue)")
            ):
                db.execute("ALTER TABLE dialogue ADD COLUMN author_character TEXT")
            if not any(
                row[1] == "pilots_json" for row in db.execute("PRAGMA table_info(scene_archives)")
            ):
                db.execute("ALTER TABLE scene_archives ADD COLUMN pilots_json TEXT")

    def directory(self, viewer, pilot_callsigns):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            rooms = db.execute(
                """SELECT r.id, r.name, r.location, r.owner, rc.channel, a.closed_at AS archived_at,
                          a.pilots_json, p.actor IS NOT NULL AS joined
                   FROM rooms r
                   LEFT JOIN room_channels rc ON rc.room = r.id
                   LEFT JOIN scene_archives a ON a.room = r.id
                   LEFT JOIN participants p ON p.room = r.id AND p.actor = ?
                   WHERE a.room IS NULL OR p.actor IS NOT NULL
                   ORDER BY r.rowid""",
                (viewer.user_id,),
            ).fetchall()
            occupants = {}
            for room, actor in db.execute("SELECT room, actor FROM participants ORDER BY actor"):
                occupants.setdefault(room, []).append(str(actor))
            legacy_callsigns = {}
            for room, actor, callsign in db.execute(
                """SELECT p.room, p.actor,
                          (SELECT d.callsign FROM dialogue d WHERE d.room = p.room AND
                            d.actor = p.actor
                           ORDER BY d.rowid DESC LIMIT 1)
                   FROM participants p
                   JOIN scene_archives a ON a.room = p.room AND a.pilots_json IS NULL
                   JOIN participants viewer ON viewer.room = p.room AND viewer.actor = ?""",
                (viewer.user_id,),
            ):
                if name := callsign or pilot_callsigns.get(str(actor)):
                    legacy_callsigns.setdefault(room, []).append(name)
        return [
            {
                "id": row["id"],
                "name": row["name"],
                **location_fields(row["location"]),
                "kind": "lobby",
                "joined": bool(row["joined"]),
                "can_invite": row["owner"] == viewer.user_id and row["archived_at"] is None,
                "can_end": row["owner"] == viewer.user_id and row["archived_at"] is None,
                "archived_at": row["archived_at"],
                **(
                    {
                        "archived_pilots": json.loads(row["pilots_json"])
                        if row["pilots_json"] is not None
                        else legacy_callsigns.get(row["id"], [])
                    }
                    if row["archived_at"] is not None
                    else {}
                ),
                "pilot_ids": occupants.get(row["id"], []),
                "_channel": row["channel"] if row["joined"] else None,
            }
            for row in rooms
        ]

    def play_room(self, viewer, target, *, allocate=False):
        with closing(sqlite3.connect(self.path)) as db, db:
            if allocate:
                db.execute("BEGIN IMMEDIATE")
            self.require_member(db, viewer, target)
            self.require_open(db, target)
            room = db.execute(
                (
                    "SELECT name, (SELECT channel FROM room_channels WHERE room = rooms.id) "
                    "FROM rooms WHERE id = ?"
                ),
                (target,),
            ).fetchone()
            if not room:
                raise WorkflowError("Room unavailable.")
            name, channel = room
            if allocate and channel is None:
                while channel is None:
                    candidate = (1 << 62) | secrets.randbits(62)
                    inserted = db.execute(
                        "INSERT OR IGNORE INTO room_channels (room, channel) VALUES (?, ?)",
                        (target, candidate),
                    )
                    if inserted.rowcount:
                        channel = candidate
        return name, channel

    def has_channel(self, channel):
        with closing(sqlite3.connect(self.path)) as db:
            return (
                db.execute(
                    """SELECT 1 FROM room_channels rc WHERE channel = ? AND NOT EXISTS
                       (SELECT 1 FROM scene_archives a WHERE a.room = rc.room)""",
                    (channel,),
                ).fetchone()
                is not None
            )

    def bound_rooms(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {
                channel: (room, name)
                for channel, room, name in db.execute(
                    """SELECT rc.channel, r.id, r.name FROM room_channels rc JOIN rooms r
                      ON r.id = rc.room
                       WHERE NOT EXISTS (SELECT 1 FROM scene_archives a WHERE a.room = r.id)"""
                )
            }

    def create_room(self, viewer, key, data, *, recipients=()):
        if data.keys() not in ({"name"}, {"name", "location"}):
            raise ValueError
        name, location = data["name"], data.get("location")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise WorkflowError("Enter a room name of 1 to 80 characters.")
        if location is not None and not isinstance(location, str):
            raise ValueError
        location = " ".join((location or "").split())
        if len(location) > 80:
            raise WorkflowError("Enter a location of at most 80 characters.")
        normalized = location.casefold()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if normalized in LOCATION_ALIASES:
                location = LOCATION_ALIASES[normalized]
            elif location:
                for (saved,) in db.execute("SELECT location FROM rooms ORDER BY rowid"):
                    if saved.casefold() == normalized:
                        location = saved
                        break
            prefix = f"room-create:{key}:"
            row = db.execute(
                "SELECT id, name, location, owner FROM rooms WHERE request_key = ?",
                (key,),
            ).fetchone()
            if row:
                if row[1:] != (name.strip(), location, viewer.user_id):
                    raise WorkflowError("This room request already has a different result.")
                invites = [
                    {"id": identity, "recipient": recipient}
                    for identity, recipient in db.execute(
                        """SELECT id, recipient FROM scene_invites
                           WHERE room = ? AND substr(request_key, 1, ?) = ?
                           ORDER BY recipient""",
                        (row[0], len(prefix), prefix),
                    )
                ]
                if [item["recipient"] for item in invites] != sorted(recipients):
                    raise WorkflowError("This room request already has different invitees.")
                return {"room": row[0]} | ({"invitations": invites} if invites else {})
            room = secrets.token_hex(8)
            db.execute(
                "INSERT INTO rooms VALUES (?, ?, ?, ?, ?)",
                (room, name.strip(), location, viewer.user_id, key),
            )
            db.execute("INSERT INTO participants VALUES (?, ?)", (room, viewer.user_id))
            invites = [
                self.new_scene_invite(db, viewer, room, recipient, prefix + recipient)
                for recipient in sorted(recipients)
            ]
            return {"room": room} | ({"invitations": invites} if invites else {})

    def room(self, db, target):
        if target in ("campaign", RELAY["id"]):
            return self.owner
        row = db.execute("SELECT owner FROM rooms WHERE id = ?", (target,)).fetchone()
        if row is None:
            raise WorkflowError("Room unavailable.")
        return row[0]

    def require_member(self, db, viewer, target):
        if (
            target != RELAY["id"]
            and not db.execute(
                "SELECT 1 FROM participants WHERE room = ? AND actor = ?",
                (target, viewer.user_id),
            ).fetchone()
        ):
            raise WorkflowError("Enter this room to read its transcript.")

    @staticmethod
    def require_open(db, target):
        if db.execute("SELECT 1 FROM scene_archives WHERE room = ?", (target,)).fetchone():
            raise WorkflowError("This scene is archived and read-only.")

    @staticmethod
    def dialogue(db, target, *, limit=75):
        rows = db.execute(
            """SELECT dialogue.rowid AS id, callsign, body, created, artwork.art_id AS portrait,
                      CASE WHEN author_character IS NULL THEN actor END AS legacy_author
               FROM dialogue
               LEFT JOIN artwork ON artwork.kind = 'pilot' AND artwork.subject = author_character
               WHERE room = ? ORDER BY dialogue.rowid DESC LIMIT ?""",
            (target, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def transcript(self, viewer, target):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            self.require_member(db, viewer, target)
            archived = db.execute(
                "SELECT closed_at, dialogue_json, views_json FROM scene_archives WHERE room = ?",
                (target,),
            ).fetchone()
            if archived:
                return {
                    "archived_at": archived["closed_at"],
                    "entries": json.loads(archived["dialogue_json"]),
                    **json.loads(archived["views_json"]).get(str(viewer.user_id), {}),
                }
            return {"entries": self.dialogue(db, target)}

    def handover_dialogue(self, viewer, room_ids, *, relay_joined=False):
        """Return only the latest active dialogue metadata for the viewer's scenes."""
        if not room_ids:
            return {}
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """WITH recent AS (
                       SELECT d.room, d.rowid AS id, d.callsign, d.created, art.art_id,
                              ROW_NUMBER() OVER (PARTITION BY d.room ORDER BY d.rowid
                                DESC) AS position
                       FROM json_each(?) requested
                       JOIN dialogue d ON d.room = requested.value
                       LEFT JOIN rooms r ON r.id = d.room
                       LEFT JOIN participants p ON p.room = r.id AND p.actor = ?
                       LEFT JOIN scene_archives a ON a.room = d.room
                       LEFT JOIN artwork art ON art.kind = 'pilot' AND art.subject =
                         d.author_character
                       WHERE a.room IS NULL AND (p.actor IS NOT NULL OR (d.room = ? AND ?))
                   )
                   SELECT room, id, callsign, created, art_id FROM recent
                   WHERE position <= 75 ORDER BY room, id""",
                (
                    json.dumps(list(dict.fromkeys(room_ids))),
                    viewer.user_id,
                    RELAY["id"],
                    relay_joined,
                ),
            ).fetchall()
        scenes = {}
        for room, identity, callsign, created, portrait in rows:
            scenes.setdefault(room, []).append(
                {"id": identity, "callsign": callsign, "created": created, "portrait": portrait}
            )
        return scenes

    def archived_receipts(self, viewer, archived_rooms):
        """Read filed mail from the same private snapshot as the archived transcript."""
        if not archived_rooms:
            return []
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """SELECT a.room, a.closed_at, json_extract(a.views_json, ?)
                   FROM scene_archives a
                   JOIN participants p ON p.room = a.room AND p.actor = ?
                   ORDER BY a.closed_at DESC, a.rowid DESC""",
                (f'$."{viewer.user_id}"', viewer.user_id),
            ).fetchall()
        return [
            receipt | {"room": room, "archived_at": closed_at, "pending": []}
            for room, closed_at, projection in rows
            if room in archived_rooms and projection is not None
            for receipt in json.loads(projection).get("receipts", [])
            if receipt["state"] == "complete"
        ]

    def archive(self, viewer, target, freeze):
        if target in ("campaign", RELAY["id"]):
            raise WorkflowError("Only scenes created with Start Scene can be archived.")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            if self.room(db, target) != viewer.user_id:
                raise WorkflowError("Only the scene host can end this scene.")
            saved = db.execute(
                "SELECT closed_at FROM scene_archives WHERE room = ?", (target,)
            ).fetchone()
            if saved:
                return {"room": target, "archived_at": saved[0]}
            bound = db.execute(
                "SELECT channel FROM room_channels WHERE room = ?", (target,)
            ).fetchone()
            members = [
                row[0]
                for row in db.execute("SELECT actor FROM participants WHERE room = ?", (target,))
            ]
            entries = self.dialogue(db, target, limit=-1)
            for entry in entries:
                entry.pop("legacy_author")
            views, pilots = freeze(bound[0] if bound else None, members)
            for actor, callsign in db.execute(
                """SELECT d.actor, d.callsign FROM dialogue d
                   JOIN participants p ON p.room = d.room AND p.actor = d.actor
                   WHERE d.room = ? ORDER BY d.rowid DESC""",
                (target,),
            ):
                pilots.setdefault(str(actor), callsign)
            closed_at = int(time())
            db.execute(
                """INSERT INTO scene_archives (room, closed_at, dialogue_json, views_json,
                  pilots_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    target,
                    closed_at,
                    json.dumps(entries),
                    json.dumps(views),
                    json.dumps(sorted(set(pilots.values()))),
                ),
            )
            return {"room": target, "archived_at": closed_at}

    def post_dialogue(self, viewer, key, callsign, target, text, *, character):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200:
            raise WorkflowError("Enter dialogue or narration of 1 to 1200 characters.")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.require_member(db, viewer, target)
            previous = db.execute(
                "SELECT rowid, room, actor, body FROM dialogue WHERE request_key = ?",
                (key,),
            ).fetchone()
            if previous:
                if previous[1:] != (target, viewer.user_id, text.strip()):
                    raise WorkflowError("This dialogue request already has a different result.")
                return {"entry": previous[0]}
            self.require_open(db, target)
            result = db.execute(
                """INSERT INTO dialogue (room, actor, callsign, body, request_key,
                  created, author_character)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    target,
                    viewer.user_id,
                    callsign,
                    text.strip(),
                    key,
                    int(time()),
                    character,
                ),
            )
            return {"entry": result.lastrowid}

    def private_updates(self, participant, aliases=()):
        recipients = tuple(dict.fromkeys((participant, *aliases)))
        placeholders = ",".join("?" for _ in recipients)
        with closing(sqlite3.connect(self.path)) as db:
            return dict(
                db.execute(
                    f"SELECT sender, max(id) FROM private_messages "
                    f"WHERE recipient IN ({placeholders}) GROUP BY sender",
                    recipients,
                )
            )

    def private_thread(self, participant, contact, participant_aliases=(), contact_aliases=()):
        actors = tuple(dict.fromkeys((participant, *participant_aliases)))
        peers = tuple(dict.fromkeys((contact, *contact_aliases)))
        a, b = ",".join("?" for _ in actors), ",".join("?" for _ in peers)
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                f"""SELECT id, sender, callsign, body, created FROM private_messages
                   WHERE (sender IN ({a}) AND recipient IN ({b})) OR (sender IN ({b}) AND
                     recipient IN ({a}))
                   ORDER BY id DESC LIMIT 75""",
                (*actors, *peers, *peers, *actors),
            ).fetchall()
        return {"entries": [dict(row) for row in reversed(rows)]}

    def send_private(self, key, sender, contact, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200:
            raise WorkflowError("Enter a message of 1 to 1200 characters.")
        message = (sender["id"], contact, text.strip())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT id, sender, recipient, body FROM private_messages WHERE request_key = ?",
                (key,),
            ).fetchone()
            if previous:
                if previous[1:] != message:
                    raise WorkflowError("This message request already has a different result.")
                return {"entry": previous[0]}
            result = db.execute(
                """INSERT INTO private_messages (sender, recipient, body, callsign,
                  created, request_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (*message, sender["label"], int(time()), key),
            )
            return {"entry": result.lastrowid}

    def intel_mail(self, character):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in db.execute(
                    """SELECT i.id, i.callsign, i.body, i.created
                       FROM scene_intel_recipients r JOIN scene_intel i ON i.id = r.report
                       WHERE r.recipient = ? ORDER BY i.id DESC""",
                    (character,),
                )
            ]

    def share_intel(self, viewer, key, room, sender, recipients, text):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.require_member(db, viewer, room)
            previous = db.execute(
                "SELECT id, room, sender, body FROM scene_intel WHERE request_key = ?",
                (key,),
            ).fetchone()
            if previous:
                previous_id, *request = previous
                if request != [room, sender.character_id, text] or recipients != {
                    row[0]
                    for row in db.execute(
                        "SELECT recipient FROM scene_intel_recipients WHERE report = ?",
                        (previous_id,),
                    )
                }:
                    raise WorkflowError("This intel request already has a different result.")
                return {"report": previous_id}
            self.require_open(db, room)
            report = db.execute(
                """INSERT INTO scene_intel (room, sender, callsign, body, created, request_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (room, sender.character_id, sender.callsign, text, int(time()), key),
            ).lastrowid
            db.executemany(
                "INSERT INTO scene_intel_recipients (recipient, report) VALUES (?, ?)",
                ((recipient, report) for recipient in recipients),
            )
            return {"report": report}

    def issue_scene_invite(self, viewer, key, room, recipient):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if (
                room == "campaign"
                or recipient == str(viewer.user_id)
                or self.room(db, room) != viewer.user_id
            ):
                raise WorkflowError("Only the scene host may invite another pilot.")
            self.require_open(db, room)
            previous = db.execute(
                "SELECT id, room, issuer, recipient FROM scene_invites WHERE request_key = ?",
                (key,),
            ).fetchone()
            if previous:
                if previous[1:] != (room, viewer.user_id, recipient):
                    raise WorkflowError("This invitation request already has a different result.")
                return {"id": previous[0], "recipient": recipient}
            if db.execute(
                "SELECT 1 FROM participants WHERE room = ? AND actor = ?", (room, int(recipient))
            ).fetchone():
                raise WorkflowError("This pilot has already joined the scene.")
            open_invite = db.execute(
                """SELECT id FROM scene_invites
                   WHERE room = ? AND recipient = ? AND expires > ? AND decision IS NULL""",
                (room, recipient, int(time())),
            ).fetchone()
            if open_invite:
                return {"id": open_invite[0], "recipient": recipient}
            return self.new_scene_invite(db, viewer, room, recipient, key)

    @staticmethod
    def new_scene_invite(db, viewer, room, recipient, key):
        identity = secrets.token_hex(16)
        db.execute(
            "INSERT INTO scene_invites VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (identity, room, viewer.user_id, recipient, int(time()) + INVITE_LIFETIME, key),
        )
        return {"id": identity, "recipient": recipient}

    def scene_invites(self, viewer):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """SELECT i.id, i.room, COALESCE(r.name, ?) AS name
                   FROM scene_invites i LEFT JOIN rooms r ON r.id = i.room
                   LEFT JOIN scene_archives a ON a.room = i.room
                   LEFT JOIN participants p ON p.room = i.room AND p.actor = ?
                   WHERE i.recipient = ? AND i.decision IS NULL AND i.expires > ?
                   AND a.room IS NULL AND p.actor IS NULL
                   AND (i.room = ? OR r.id IS NOT NULL)""",
                (RELAY["name"], viewer.user_id, str(viewer.user_id), int(time()), RELAY["id"]),
            )
            return [dict(row) for row in rows]

    def decide_scene_invite(self, viewer, identity, decision):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            record = db.execute(
                "SELECT room, expires, decision FROM scene_invites WHERE id = ? AND recipient = ?",
                (identity, str(viewer.user_id)),
            ).fetchone()
            if record is None:
                raise WorkflowError("Scene invitation unavailable.")
            room, expires, saved = record
            if saved == decision:
                return {"room": room, "decision": saved}
            if saved is not None or expires <= time():
                raise WorkflowError("This scene invitation is closed.")
            self.require_open(db, room)
            if decision == "accept" and room != RELAY["id"]:
                db.execute(
                    "INSERT OR IGNORE INTO participants VALUES (?, ?)", (room, viewer.user_id)
                )
            db.execute("UPDATE scene_invites SET decision = ? WHERE id = ?", (decision, identity))
            return {"room": room, "decision": decision}

    def issue(self, viewer, key, data):
        if data.keys() != {"target"} or not isinstance(data["target"], str):
            raise ValueError
        target = data["target"]
        if target == "campaign" and not self.campaign_codes:
            raise WorkflowError("Campaign access comes from Discord sign-in and the server role.")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if self.room(db, target) != viewer.user_id:
                raise WorkflowError("Only the room host can issue an invitation.")
            self.require_open(db, target)
            row = db.execute(
                "SELECT code, room, expires, issuer FROM invitations WHERE request_key = ?",
                (key,),
            ).fetchone()
            if row:
                if (row[1], row[3]) != (target, viewer.user_id):
                    raise WorkflowError("This invitation request already has a different result.")
                return {"code": row[0], "expires": row[2]}
            code = "".join(secrets.choice(ALPHABET) for _ in range(12))
            expires = int(time()) + INVITE_LIFETIME
            db.execute(
                "INSERT INTO invitations VALUES (?, NULL, ?, ?, ?, ?)",
                (code, target, expires, key, viewer.user_id),
            )
            return {"code": code, "expires": expires}

    def redeem(self, viewer, data):
        if data.keys() != {"code"} or not isinstance(data["code"], str):
            raise ValueError
        code = data["code"].strip().replace("-", "").upper()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = (
                db.execute(
                    "SELECT room, expires, issuer, recipient FROM invitations WHERE code = ?",
                    (code,),
                ).fetchone()
                if re.fullmatch(r"[A-Z2-9]{12}", code)
                else None
            )
            if row is None or row[1] <= time() or row[3] not in (None, viewer.user_id):
                raise WorkflowError("This binding code is unavailable or expired.")
            room, _, issuer, recipient = row
            self.require_open(db, room)
            if room == "campaign" and not self.campaign_codes:
                raise WorkflowError(
                    "Campaign access comes from Discord sign-in and the server role."
                )
            if viewer.user_id == issuer:
                raise WorkflowError("Send this binding code to another test account.")
            if recipient is None:
                db.execute(
                    "UPDATE invitations SET recipient = ? WHERE code = ?",
                    (viewer.user_id, code),
                )
            if room not in ("campaign", RELAY["id"]):
                db.execute(
                    "INSERT OR IGNORE INTO participants VALUES (?, ?)",
                    (room, viewer.user_id),
                )
            return {"target": room}

    def asset_descriptions(self, viewer, character):
        with closing(sqlite3.connect(self.path)) as db:
            return {
                asset: (text, revision)
                for asset, text, revision in db.execute(
                    (
                        "SELECT asset, text, revision FROM descriptions WHERE actor = ? AND "
                        "character = ?"
                    ),
                    (viewer.user_id, character),
                )
            }

    def artwork(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {
                (kind, subject): art_id
                for kind, subject, art_id in db.execute("SELECT kind, subject, art_id FROM artwork")
            }

    def select_artwork(self, viewer, kind, subject, artwork, previous):
        identity = (kind, subject)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if kind == "scene" and (
                subject == "campaign" or self.room(db, subject) != viewer.user_id
            ):
                raise WorkflowError("Only the scene host can select scene artwork.")
            if kind == "scene":
                self.require_open(db, subject)
            row = db.execute(
                "SELECT art_id FROM artwork WHERE kind = ? AND subject = ?", identity
            ).fetchone()
            current = row[0] if row else None
            if current == artwork:
                return {"artwork": current}
            if current != previous:
                raise WorkflowError("Refresh before saving. The artwork has changed.")
            if artwork is None:
                db.execute("DELETE FROM artwork WHERE kind = ? AND subject = ?", identity)
            else:
                db.execute(
                    "INSERT OR REPLACE INTO artwork VALUES (?, ?, ?)",
                    (*identity, artwork),
                )
        return {"artwork": artwork}

    def describe_asset(self, viewer, character, asset, data):
        if data.keys() != {"asset", "description", "revision"} or data["asset"] != asset:
            raise ValueError
        text = data["description"]
        if not isinstance(text, str) or len(text) > 700 or type(data["revision"]) is not int:
            raise ValueError
        if not character:
            raise WorkflowError("This assignment has no saved character.")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            identity = (viewer.user_id, character, asset)
            row = db.execute(
                (
                    "SELECT text, revision FROM descriptions WHERE actor = ? AND character = ? "
                    "AND asset = ?"
                ),
                identity,
            ).fetchone()
            revision = row[1] if row else 0
            if row and row[0] == text:
                return {"revision": revision}
            if revision != data["revision"]:
                raise WorkflowError("Refresh the asset before saving. Its description has changed.")
            db.execute(
                "INSERT OR REPLACE INTO descriptions VALUES (?, ?, ?, ?, ?)",
                (*identity, text, revision + 1),
            )
            return {"revision": revision + 1}
