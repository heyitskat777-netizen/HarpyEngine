"""Bounded bot-authored enrollment work through native Handler APIs.

No player answers, private-note edits, review saves, activation or gameplay actions.
"""

import hashlib
import json
from threading import RLock

import sqlalchemy as sa

from girlframe.database import tables
from girlframe.engine.creation_details import DESIRES, STANDARDS, DesireChoice, StandardChoice
from girlframe.engine.handler_setup import PilotRef
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.handler_setup import HandlerService, assigned_late_wing, late_wing_eligible
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.session_zero import SessionZeroService

POLICY_VERSION = "foundation-enrollment-v1"


class BotEnrollment:
    def __init__(self, store, handler):
        self.store, self.bot = store, handler
        self.handler = HandlerService(store)
        self.coordination = CoordinationService(store)
        self.lock = RLock()

    def enabled(self):
        if self.bot.user_id != self.store.policy.application_id:
            return False
        with self.store.engine.connect() as c:
            return self.handler.current(c)[
                1
            ].handler_id == self.bot.user_id and self.handler._member(c, self.bot.user_id)

    def snapshot(self):
        with self.store.engine.connect() as c:
            self.handler.authorize(c, self.bot)
            revision, setup = self.handler.current(c)
            return revision, setup, self.handler._roster(c), load_state(c, self.store.campaign_id)

    def key(self, action, payload):
        digest = hashlib.sha256(
            json.dumps(
                [str(self.store.campaign_id), POLICY_VERSION, action, payload], sort_keys=True
            ).encode()
        ).hexdigest()
        return "bot-enrollment:" + digest

    def view(self, viewer):
        self.store.guild_member(viewer)
        with self.store.engine.connect() as c:
            self.store._membership(c, viewer)
        if not self.enabled() or viewer.user_id == self.bot.user_id:
            return None
        profile = self.store.draft(viewer)
        setup_revision, setup, roster, state = self.snapshot()
        with self.store.engine.connect() as c:
            choices = [
                row
                for row in self.coordination._latest(c, viewer.user_id)
                if row["owner_id"] == str(viewer.user_id)
                and row["author_id"] == str(self.bot.user_id)
                and row["role"] in ("princess_handler", "vatgrown_handler")
                and not self.coordination._stale(c, row)
            ]
            rulings = self.handler.effective_rulings(c)
            plan = (
                SessionZeroService(self.store).enrollment_order(c, roster)
                if not state.order
                else None
            )
        notes = []
        if not state.order and len(roster) < 2:
            notes.append("Starting Status requires at least two filed pilot profiles.")
        if plan is not None:
            notes.append(
                "Starting Status is on file in the approved Session Zero plan."
                if plan
                else "Starting Status is awaiting the approved Session Zero plan."
            )
        if (
            state.order
            and profile
            and viewer.user_id not in state.order
            and not any(x.actor.entity == str(viewer.user_id) for x in state.career_archives)
        ):
            if profile["girl_playbook"] == "PRINCESS":
                notes.append(
                    "Princess requires starting as Ace. The current Ace position is occupied."
                )
            elif assigned_late_wing(state, setup, viewer.user_id, profile):
                notes.append("Wing placement filed. Complete your own review to activate.")
            else:
                notes.append("Wing placement is awaiting the Handler.")
        if (
            sum(row["girl_playbook"] == "PRINCESS" for row in roster.values()) > 1
            and not state.order
        ):
            notes.append(
                "Multiple Princesses require an explicit campaign resolution before a "
                "single starting Ace can be assigned."
            )
        if self.store.policy.owner_initial_conditions is None or rulings is None:
            notes.append(
                "Campaign-owner initial conditions and creation rulings are required. The "
                "bot cannot approve them for the owner."
            )
        return {
            "policy": POLICY_VERSION,
            "can_request": bool(profile and not profile.get("canonical")),
            "character_revision": profile["revision"] if profile else 0,
            "status": "BOT HANDLER ON DUTY",
            "description": (
                "Personnel intake assigns starting Status and eligible Mentors, and files "
                "Handler-owned standards and investor proposals. Each pilot must countersign "
                "its own choices and authorize its own activation."
            ),
            "status_order": [str(ref.user_id) for ref in setup.status_order],
            "order_frozen": bool(state.order),
            "notes": notes,
            "pending_choices": sum(row["state"] == "pending" for row in choices),
            "declined_choices": 0
            if any(row["state"] in ("pending", "accepted") for row in choices)
            else sum(row["state"] in ("declined", "withdrawn") for row in choices),
            "context": hashlib.sha256(
                json.dumps(
                    [
                        str(self.store.campaign_id),
                        viewer.user_id,
                        POLICY_VERSION,
                        profile["revision"] if profile else 0,
                        setup_revision,
                        sorted((row["id"], row["revision"], row["state"]) for row in choices),
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        }

    def request(self, viewer, key, data):
        if (
            not isinstance(data, dict)
            or set(data)
            not in (
                {"character_revision", "context"},
                {"character_revision", "context", "retry_declined"},
            )
            or type(data.get("character_revision")) is not int
            or ("retry_declined" in data and type(data["retry_declined"]) is not bool)
            or not isinstance(data.get("context"), str)
        ):
            raise ValueError("Use the current owner enrollment request.")
        self.store.guild_member(viewer)
        with self.store.engine.connect() as c:
            self.store._membership(c, viewer)
        if not self.enabled() or viewer.user_id == self.bot.user_id:
            raise WorkflowError(
                "This campaign does not have its application bot appointed as Handler."
            )
        with self.lock:
            profile = self.store.draft(viewer)
            if (
                not profile
                or profile.get("canonical")
                or profile["revision"] != data["character_revision"]
            ):
                raise WorkflowError("STALE_PROFILE: reopen your own unfinished enrollment.")
            with self.store.engine.connect() as c:
                exists = (
                    c.scalar(
                        sa.select(tables.commands.c.interaction_key).where(
                            tables.commands.c.campaign_id == self.store.campaign_id,
                            tables.commands.c.interaction_key == key,
                        )
                    )
                    is not None
                )
            if not exists and self.view(viewer)["context"] != data["context"]:
                raise WorkflowError(
                    "STALE_CONTEXT: reopen enrollment before requesting Handler setup."
                )
            # Record the human request before bot work. A retried key cannot
            # create another offer after the pilot has declined the first one.
            receipt = self.store._write(
                viewer,
                key,
                "character.bot_enrollment_requested",
                data,
                lambda c: {"state": "requested", "policy": POLICY_VERSION},
                authorize=lambda c: self.store._membership(c, viewer),
            )
            if not exists:
                self.reconcile(
                    owner=viewer.user_id,
                    retry_owner=viewer.user_id if data.get("retry_declined") else None,
                )
            return receipt

    def reconcile(self, *, owner=None, retry_owner=None):
        if not self.enabled():
            return {"enabled": False, "actions": [], "blocked": []}
        with self.lock:
            actions, blocked = [], []
            revision, setup, roster, state = self.snapshot()
            with self.store.engine.connect() as c:
                plan = (
                    SessionZeroService(self.store).enrollment_order(c, roster)
                    if not state.order
                    else None
                )
            if not state.order and plan is None:
                if len(roster) < 2:
                    blocked.append("Starting Status requires at least two filed pilot profiles.")
                elif any(row["callsign"] == "RECRUIT" for row in roster.values()):
                    blocked.append(
                        "Each pilot must save its own callsign before Status is assigned."
                    )
                else:
                    princesses = [
                        uid for uid, row in roster.items() if row["girl_playbook"] == "PRINCESS"
                    ]
                    if len(princesses) > 1:
                        blocked.append(
                            "Starting Ace assignment requires a ruling on the competing "
                            "Princess files."
                        )
                    else:
                        order = [ref.user_id for ref in setup.status_order if ref.user_id in roster]
                        order.extend(uid for uid in sorted(roster) if uid not in order)
                        if princesses:
                            order.remove(princesses[0])
                            order.insert(0, princesses[0])
                        refs = tuple(
                            PilotRef(user_id=uid, character_revision=roster[uid]["revision"])
                            for uid in order
                        )
                        if refs != setup.status_order:
                            payload = [revision, [ref.model_dump(mode="json") for ref in refs]]
                            try:
                                self.handler.rank(
                                    self.bot, self.key("status", payload), revision, refs
                                )
                                actions.append("STARTING STATUS FILED")
                            except WorkflowError as error:
                                blocked.append(str(error))
            elif state.order and owner is not None:
                profile = roster.get(owner)
                if (
                    profile
                    and late_wing_eligible(state, setup, owner, profile)
                    and not (assigned_late_wing(state, setup, owner, profile))
                ):
                    ref = PilotRef(user_id=owner, character_revision=profile["revision"])
                    payload = [revision, ref.model_dump(mode="json")]
                    try:
                        self.handler.assign_late_wing(
                            self.bot, self.key("late-wing", payload), revision, ref
                        )
                        actions.append("WING PLACEMENT FILED")
                    except WorkflowError as error:
                        blocked.append(str(error))
            # Handler nominates; the Mentor still chooses the callsign and the Newgirl answers.
            _, setup, roster, state = self.snapshot()
            for uid, row in sorted(roster.items()):
                if (
                    row["girl_playbook"] != "NEWGIRL"
                    or str(uid) in state.sheets
                    or (owner is not None and uid != owner)
                ):
                    continue
                with self.store.engine.connect() as c:
                    current = self.handler.mentor_for(c, uid)
                if current:
                    continue
                previous = next(
                    (item for item in setup.mentors if item.newgirl.user_id == uid), None
                )
                peers = [peer for peer in roster if peer != uid]
                peers.sort(key=lambda peer: (roster[peer]["girl_playbook"] == "NEWGIRL", peer))
                if previous and previous.mentor.user_id in peers:
                    peers.remove(previous.mentor.user_id)
                    peers.insert(0, previous.mentor.user_id)
                if not peers:
                    blocked.append("An eligible peer pilot is required for a Newgirl Mentor.")
                    continue
                revision, _, _, _ = self.snapshot()
                newgirl = PilotRef(user_id=uid, character_revision=row["revision"])
                mentor = PilotRef(user_id=peers[0], character_revision=roster[peers[0]]["revision"])
                try:
                    self.handler.mentor(
                        self.bot,
                        self.key(
                            "mentor",
                            [
                                revision,
                                newgirl.model_dump(mode="json"),
                                mentor.model_dump(mode="json"),
                            ],
                        ),
                        revision,
                        newgirl,
                        mentor,
                    )
                    actions.append(
                        "Mentor assigned; its callsign choice remains with the Mentor and Newgirl."
                    )
                except WorkflowError as error:
                    blocked.append(str(error))
            with self.store.engine.connect() as c:
                tasks = self.coordination.tasks(c, self.bot)
                _, _, _, state = self.snapshot()
                candidates = []
                for task in tasks:
                    uid = task["owner"]
                    if (
                        task["role"] not in ("princess_handler", "vatgrown_handler")
                        or str(uid) in state.sheets
                        or (owner is not None and uid != owner)
                    ):
                        continue
                    prior = [
                        row
                        for row in self.coordination._latest(c, uid)
                        if row["author_id"] == str(self.bot.user_id)
                        and row["role"] == task["role"]
                        and json.loads(row["context_json"]) == task["context"]
                    ]
                    declined = sum(row["state"] in ("declined", "withdrawn") for row in prior)
                    if declined and retry_owner != uid:
                        blocked.append(
                            "A pilot declined its Handler proposal; a new offer requires "
                            "its own request."
                        )
                        continue
                    candidates.append((task, declined))
            for task, declined in candidates:
                if task["role"] == "princess_handler":
                    labels = (
                        "Report Cadre conduct",
                        "Use official pronouns",
                        "Impeccable grooming",
                    )
                    choice = StandardChoice(slot=STANDARDS.index(labels[declined % len(labels)]))
                else:
                    labels = ("A weapon", "An opportunity", "A triumph")
                    choice = DesireChoice(slots=(DESIRES.index(labels[declined % len(labels)]),))
                key = self.key(
                    "choice",
                    [
                        task["owner"],
                        task["role"],
                        task["context"],
                        declined,
                        choice.model_dump(mode="json"),
                    ],
                )
                try:
                    self.coordination.propose(
                        self.bot, key, task["owner"], task["role"], task["context"], choice
                    )
                    actions.append("Handler proposal filed; the pilot must accept or decline.")
                except WorkflowError as error:
                    blocked.append(str(error))
            with self.store.engine.connect() as c:
                if (
                    self.store.policy.owner_initial_conditions is None
                    or self.handler.effective_rulings(c) is None
                ):
                    blocked.append(
                        "Explicit campaign-owner initial conditions and creation rulings "
                        "are required; the bot cannot invent them."
                    )
            return {
                "enabled": True,
                "actions": actions,
                "blocked": list(dict.fromkeys(blocked)),
                "policy": POLICY_VERSION,
            }
