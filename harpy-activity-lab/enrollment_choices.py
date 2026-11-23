"""Private HarpyEngine setup work shared between a recruit and its actual authors."""

import json

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import (
    DesireChoice,
    StandardChoice,
)
from rulebook_text import DESIRES, STANDARDS
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.pair_assets import PairNames
from girlframe.engine.shared_setup import AM_ROLES, CallsignChoice, CourtChoice
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.shared_setup import SharedSetupService


class EnrollmentChoices:
    def __init__(self, game):
        self.game = game
        self.store = game.store
        self.shared = SharedSetupService(self.store)
        self.coordination = CoordinationService(self.store)
        self.pair = PairService(self.store)
        self.handler = HandlerService(self.store)

    def view(self, viewer, bonds):
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            active = load_state(c, self.store.campaign_id).sheets
            roster = {
                str(uid): row
                for uid, row in self.handler._roster(c).items()
                if row["callsign"] != "RECRUIT"
            }
            current = roster.get(str(viewer.user_id))
            handler_revision, appointment = self.handler.current(c)
            is_handler = appointment.handler_id == viewer.user_id
            shared = self.shared.list(viewer)
            coordinated = [
                row | {"stale": self.coordination._stale(c, row)}
                for row in self.coordination._latest(c, viewer.user_id)
            ]
            choices = self.coordination.tasks(c, viewer)
        work = []
        for row in shared:
            owner = row["source_id"] if row["kind"] == "court" else row["target_id"]
            if (
                owner not in active
                and not row["stale"]
                and row["state"] in ("accepted", "pending")
            ):
                work.append(
                    self.request(row, "shared", row["kind"], "target_id", viewer)
                )
        for row in coordinated:
            if (
                row["owner_id"] not in active
                and not row["stale"]
                and row["state"] in ("accepted", "pending")
            ):
                work.append(
                    self.request(row, "coordination", row["role"], "owner_id", viewer)
                )

        current_requests = [
            item
            for item in shared
            if item["state"] in ("accepted", "pending") and not item["stale"]
        ]
        has_court = any(
            item["kind"] == "court" and item["source_id"] == str(viewer.user_id)
            for item in current_requests
        )
        mentor_names = {
            item["target_id"] for item in current_requests if item["kind"] == "callsign"
        }
        proposals = []
        for target, row in roster.items():
            if target == str(viewer.user_id):
                continue
            possible = []
            if (
                current
                and current["frame_playbook"] == "THE RED QUEEN"
                and str(viewer.user_id) not in active
                and not has_court
            ):
                possible.append("court")
            if (
                row["girl_playbook"] == "NEWGIRL"
                and target not in active
                and target not in mentor_names
            ):
                possible.append("callsign")
            for kind in possible:
                try:
                    context = self.shared.prepare(viewer, int(target), kind)
                except WorkflowError:
                    continue
                proposals.append(
                    {
                        "kind": kind,
                        "target": target,
                        "callsign": row["callsign"],
                        "context": context,
                    }
                )
        for choice in choices:
            target = str(choice["owner"])
            if target not in active and target in roster:
                proposals.append(
                    {
                        "kind": choice["role"],
                        "target": target,
                        "callsign": roster[target]["callsign"],
                        "context": choice["context"],
                    }
                )
        pairs = []
        for bond in bonds:
            if not bond["incoming"] or bond["state"] != "accepted":
                continue
            try:
                data = self.pair.prepare(viewer, bond["id"])
            except WorkflowError:
                continue
            if str(data["owner_id"]) not in active:
                pairs.append(
                    {
                        k: data[k]
                        for k in ("bond_id", "bond_revision", "names", "revision")
                    }
                    | {"callsign": bond["counterpart"]}
                )

        mentors = (
            [
                {
                    "id": target,
                    "revision": row["revision"],
                    "callsign": row["callsign"],
                    "newgirl": row["girl_playbook"] == "NEWGIRL"
                    and target not in active,
                }
                for target, row in roster.items()
            ]
            if is_handler
            else []
        )
        if not any(item["newgirl"] for item in mentors) or len(mentors) < 2:
            mentors = []
        return {
            "requests": work,
            "proposals": proposals,
            "pairs": pairs,
            "mentors": mentors,
            "handler_revision": handler_revision,
            "roles": AM_ROLES,
            "standards": STANDARDS,
            "desires": DESIRES,
            "pair_assets": CATALOG["BONDED"]["assets"],
        }

    @staticmethod
    def request(row, family, kind, recipient, viewer):
        incoming = row[recipient] == str(viewer.user_id)
        state = row["state"]
        return {
            "id": row["id"],
            "revision": row["revision"],
            "family": family,
            "kind": kind,
            "incoming": incoming,
            "state": state,
            "choice": json.loads(row["choice_json"]),
            "decisions": ["accept", "decline"]
            if incoming and state == "pending"
            else ["withdraw"],
        }

    def perform(self, viewer, key, data):
        op = data.get("operation")
        if op == "decide":
            service = {"shared": self.shared, "coordination": self.coordination}[
                data["family"]
            ]
            return service.decide(
                viewer, key, data["id"], data["revision"], data["decision"]
            )
        if op == "mentor":
            return self.handler.mentor(
                viewer,
                key,
                data["revision"],
                PilotRef.model_validate_json(json.dumps(data["newgirl"])),
                PilotRef.model_validate_json(json.dumps(data["mentor"])),
            )
        if op == "pair":
            return self.pair.choose(
                viewer,
                key,
                data["id"],
                data["bond_revision"],
                data["revision"],
                PairNames.model_validate_json(json.dumps(data["choice"])),
            )
        if op == "propose":
            kind, target = data["kind"], int(data["target"])
            choice = json.dumps(data["choice"])
            if kind in ("court", "callsign"):
                model = CourtChoice if kind == "court" else CallsignChoice
                return self.shared.propose(
                    viewer,
                    key,
                    target,
                    kind,
                    data["context"],
                    model.model_validate_json(choice),
                )
            if kind in ("princess_peer", "princess_handler", "vatgrown_handler"):
                model = DesireChoice if kind == "vatgrown_handler" else StandardChoice
                return self.coordination.propose(
                    viewer,
                    key,
                    target,
                    kind,
                    data["context"],
                    model.model_validate_json(choice),
                )
        raise ValueError("Choose an available enrollment decision.")
