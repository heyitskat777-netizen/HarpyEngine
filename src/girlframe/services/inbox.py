"""Complete private aggregation with derived role-specific coordination tasks."""

import json
from datetime import datetime

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.engine.bonds import starting_kind
from girlframe.engine.inbox import CATEGORIES, SCOPES, InboxItem, InboxPage
from girlframe.services.bonds import BondService, Decision
from girlframe.services.creation import CreationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService


class InboxService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.bonds, self.shared = BondService(store), SharedSetupService(store)

    def items(self, viewer: GuildViewer) -> tuple[InboxItem, ...]:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")  # One read snapshot across sources and tasks.
            self.bonds._authorize(connection, viewer)
            user = str(viewer.user_id)
            bonds = self.bonds._latest(connection, user)
            shared = self.shared._latest(connection, viewer.user_id)
            events = [x["event_id"] for x in bonds + shared]
            times = {
                str(identity): str(stamp)
                for identity, stamp in connection.execute(
                    sa.select(t.events.c.id, t.events.c.created_utc).where(
                        t.events.c.campaign_id == self.store.campaign_id, t.events.c.id.in_(events)
                    )
                ).all()
            }
            # Project public aliases only, never another character's private body.
            profiles = {
                int(uid): json.loads(body)
                for uid, body in connection.execute(
                    sa.select(t.characters.c.user_id, t.characters.c.public_json).where(
                        t.characters.c.campaign_id == self.store.campaign_id
                    )
                )
            }

            def label(uid: str | int) -> str:
                return (
                    str(profiles.get(int(uid), {}).get("callsign", "Player"))
                    + " ("
                    + str(uid)
                    + ")"
                )

            items: list[InboxItem] = []
            for row in bonds:
                incoming = row["target_id"] == user
                stale = self.bonds._stale(connection, row)
                girl = row["girl_playbook"]
                category = (
                    "mentors" if girl == "NEWGIRL" else "pair" if girl == "BONDED" else "bonds"
                )
                title = (
                    "Mentor agreement"
                    if girl == "NEWGIRL"
                    else "Pair agreement"
                    if girl == "BONDED"
                    else "Starting Bond"
                )
                pending = row["state"] == "pending"
                primary = "Accept agreement" if pending and incoming else None
                secondary = (
                    "decline"
                    if pending and incoming
                    else "withdraw"
                    if pending or row["state"] == "accepted"
                    else None
                )
                effect = f"Save a mutual {starting_kind(girl)} starting agreement. No Play runs."
                details = row["context"] or "No shared context provided."
                if girl == "NEWGIRL":
                    details += (
                        "\nHandler-nominated Mentor: chooses callsign and counts as higher Status."
                    )
                if girl == "BONDED":
                    details += "\nPair chooses Girl Asset names; owner writes descriptions."
                if girl == "AM":
                    details += "\nAM counterpart: this Girl is Jailbroken."
                items.append(
                    InboxItem(
                        "bond:" + row["id"],
                        "bond",
                        row["id"],
                        row["revision"],
                        category,
                        title,
                        label(row["source_id"] if incoming else row["target_id"]),
                        row["state"],
                        incoming,
                        stale,
                        effect,
                        details,
                        primary,
                        secondary,
                        sort_time=times.get(row["event_id"], ""),
                    )
                )
            for row in shared:
                incoming = row["target_id"] == user
                court = row["kind"] == "court"
                pending = row["state"] == "pending"
                value = str(next(iter(json.loads(row["choice_json"]).values())))
                effect = (
                    "Assign this AM to the recipient and keep four on the pilot. Setup only."
                    if court
                    else "Save the Mentor callsign for activation; current nickname is unchanged."
                )
                items.append(
                    InboxItem(
                        "shared:" + row["id"],
                        "shared",
                        row["id"],
                        row["revision"],
                        "court" if court else "mentors",
                        "Red Queen's Court" if court else "Mentor callsign",
                        label(row["source_id"] if incoming else row["target_id"]),
                        row["state"],
                        incoming,
                        self.shared._stale(connection, row),
                        effect,
                        value,
                        "Accept setup" if pending and incoming else None,
                        "decline"
                        if pending and incoming
                        else "withdraw"
                        if pending or row["state"] == "accepted"
                        else None,
                        sort_time=times.get(row["event_id"], ""),
                    )
                )

            def has_shared(kind: str, target: int | None = None) -> bool:
                return any(
                    x["source_id"] == user
                    and x["kind"] == kind
                    and (target is None or int(x["target_id"]) == target)
                    and x["state"] in ("pending", "accepted")
                    and not self.shared._stale(connection, x)
                    for x in shared
                )

            def task(
                key: str,
                category: str,
                title: str,
                other: int | None,
                effect: str,
                action: str,
                route: str,
                revision: int = 0,
            ) -> None:
                items.append(
                    InboxItem(
                        "task:" + key,
                        "task",
                        key,
                        revision,
                        category,
                        title,
                        label(other) if other else "Your character",
                        "pending",
                        True,
                        False,
                        effect,
                        "Continue the authorized wizard. Opening a task saves nothing.",
                        action,
                        task=route,
                        target=other,
                    )
                )

            handler = HandlerService(self.store)
            nomination = handler.mentor_for(connection, viewer.user_id)
            if nomination:
                present = any(
                    x["source_id"] == user
                    and int(x["target_id"]) == nomination.mentor.user_id
                    and x["girl_playbook"] == "NEWGIRL"
                    and x["state"] in ("pending", "accepted")
                    and not self.bonds._stale(connection, x)
                    for x in bonds
                )
                if not present:
                    task(
                        "mentor:" + nomination.assignment_id,
                        "mentors",
                        "Start Mentor agreement",
                        nomination.mentor.user_id,
                        "Review a Bond with the nominated Mentor; the Mentor then accepts.",
                        "Start agreement",
                        "mentor_start",
                    )
            for row in bonds:
                if row["state"] != "accepted" or self.bonds._stale(connection, row):
                    continue
                if (
                    row["girl_playbook"] == "NEWGIRL"
                    and row["target_id"] == user
                    and not has_shared("callsign", int(row["source_id"]))
                ):
                    task(
                        "name:" + row["id"],
                        "mentors",
                        "Choose Newgirl callsign",
                        int(row["source_id"]),
                        "As accepted Mentor, propose a callsign for Newgirl to review.",
                        "Enter callsign",
                        "callsign",
                        row["revision"],
                    )
                if row["girl_playbook"] == "BONDED":
                    choice = PairService(self.store)._choice(connection, row)
                    if row["target_id"] == user and not choice.names:
                        task(
                            "assets:" + row["id"],
                            "pair",
                            "Choose Pair Assets",
                            int(row["source_id"]),
                            "Choose two Girl Asset names. The owner supplies private descriptions.",
                            "Choose Assets",
                            "pair",
                            row["revision"],
                        )
                    elif row["source_id"] == user and choice.names:
                        progress = CreationService(self.store)._current(connection, viewer)
                        described = {
                            x.name
                            for x in progress.draft.pair_asset_descriptions
                            if x.description.strip()
                        }
                        if described != set(choice.names):
                            task(
                                "describe:" + choice.token,
                                "pair",
                                "Describe Pair-selected Assets",
                                int(row["target_id"]),
                                "Describe the Pair-selected names and save your draft.",
                                "Open builder",
                                "describe",
                                choice.revision,
                            )
            own = profiles.get(viewer.user_id)
            if (
                own
                and own["frame_playbook"] == "THE RED QUEEN"
                and handler.current(connection)[1].handler_id != viewer.user_id
                and not has_shared("court")
            ):
                task(
                    "court:" + str(viewer.user_id),
                    "court",
                    "Choose starting Court assignment",
                    None,
                    "Choose the other Girl and external AM. Four stay on you; recipient reviews.",
                    "Choose recipient",
                    "court",
                )
        return tuple(
            sorted(
                items,
                key=lambda x: (
                    x.state != "pending",
                    not (x.incoming or x.stale),
                    -datetime.fromisoformat(x.sort_time).timestamp() if x.sort_time else 0,
                    x.key,
                ),
            )
        )

    def page(
        self,
        viewer: GuildViewer,
        scope: str = "pending",
        category: str = "all",
        index: int = 0,
        *,
        selected_key: str | None = None,
        expected_revision: int | None = None,
    ) -> InboxPage:
        if scope not in SCOPES or category not in CATEGORIES:
            raise WorkflowError("Unknown inbox filter.")
        items = [x for x in self.items(viewer) if category == "all" or x.category == category]

        def matches(x: InboxItem, value: str) -> bool:
            return (
                x.state != "pending"
                if value == "history"
                else x.state == "pending"
                and (value == "pending" or (x.incoming or x.stale) == (value == "you"))
            )

        counts = {key: sum(matches(x, key) for x in items) for key in SCOPES}
        filtered = [x for x in items if matches(x, scope)]
        position = min(max(index, 0), max(len(filtered) - 1, 0))
        if selected_key is not None:
            found = next((i for i, x in enumerate(filtered) if x.key == selected_key), None)
            if found is None or (
                expected_revision is not None and filtered[found].revision != expected_revision
            ):
                raise WorkflowError("This request changed. Refresh and select its current version.")
            position = found
        start = (position // 5) * 5
        return InboxPage(
            filtered[position] if filtered else None,
            position,
            len(filtered),
            counts,
            tuple(filtered[start : start + 5]),
        )

    def current(self, viewer: GuildViewer, key: str, revision: int) -> InboxItem:
        item = next((x for x in self.items(viewer) if x.key == key), None)
        if item is None or item.revision != revision:
            raise WorkflowError("This request changed. Refresh the inbox; saved data is preserved.")
        return item

    def decide(
        self, viewer: GuildViewer, interaction: str, item: InboxItem, decision: Decision
    ) -> None:
        # Existing services own idempotency, revision and authority checks. Delegating
        # the original snapshot lets an exact interaction retry return its receipt.
        if item.key != item.source + ":" + item.identity:
            raise WorkflowError("This request identifier is invalid.")
        if item.source == "bond":
            self.bonds.decide(viewer, interaction, item.identity, item.revision, decision)
        elif item.source == "shared":
            self.shared.decide(viewer, interaction, item.identity, item.revision, decision)
        else:
            raise WorkflowError("Open the task's authorized wizard instead.")
