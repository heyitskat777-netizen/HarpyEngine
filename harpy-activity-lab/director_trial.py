"""Local assisted P2 trial transport over the pinned HarpyEngine services."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

import sqlalchemy as sa
from girlframe.database import tables
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


class DirectorTrial:
    def __init__(self, trial):
        from girlframe.services.director_session import DirectorSessionService

        self.scene = trial.scene
        self.viewers = {
            "invited": trial.viewers()["lark"],
            "other": trial.viewers()["kite"],
            "handler": trial.viewers()["handler"],
        }
        trial.store.clock = time
        trial.observer.game = GameService(trial.store)
        self.session = DirectorSessionService(trial.context)
        self.observer = self.session.observer
        self.outcomes = self.session.outcomes

    def view(self, viewer):
        status = self.observer.status(viewer, self.scene)
        with self.session.store.engine.connect() as connection:
            scene = self.observer._scene(connection, self.scene, viewer)
            state = self.observer._state(connection, self.scene)
            consent = state.consents.get(str(viewer.user_id))
            active_members = set(
                connection.scalars(
                    sa.select(tables.members.c.user_id).where(
                        tables.members.c.campaign_id == self.session.store.campaign_id,
                        tables.members.c.active.is_(True),
                        tables.members.c.user_id.in_(
                            str(user_id) for user_id in scene["participants"]
                        ),
                    )
                )
            )
            roles = {
                member.user_id: role for role, member in self.viewers.items()
            }
            labels = {
                "invited": "First pilot",
                "other": "Second pilot",
                "handler": "Handler",
            }
            readiness = [
                {
                    "role": roles.get(user_id, "participant"),
                    "label": labels.get(roles.get(user_id), "Participant"),
                    "own": user_id == viewer.user_id,
                    "active": str(user_id) in active_members,
                    "consented": state.consents.get(str(user_id))
                    == status.policy_revision
                    and status.policy_revision > 0,
                }
                for user_id in scene["participants"]
            ]
            own_pause = (
                connection.scalar(
                    sa.select(tables.pauses.c.user_id).where(
                        tables.pauses.c.campaign_id == self.session.store.campaign_id,
                        tables.pauses.c.user_id == str(viewer.user_id),
                    )
                )
                is not None
            )
        result = {
            "status": status.model_dump(mode="json"),
            "own_consent": bool(consent and consent == status.policy_revision),
            "own_pause": own_pause,
            "participants": readiness,
            "safety_revision": self.session.store.status(viewer)["revision"],
            "facilitator": viewer == self.viewers["handler"],
            "speaker": "handler" if viewer == self.viewers["handler"] else "pilot",
        }
        if status.phase not in ("off", "awaiting_consent", "paused"):
            result["work"] = self.session.work(viewer, self.scene)
            result["contributions"] = self.session.contributions(viewer, self.scene)
        return result

    def perform(self, viewer, key, data):
        from girlframe.ai.gm_outcomes import OutcomeProposal
        from girlframe.ai.gm_protocol import TaskFrame
        from girlframe.ai.observation import AppendSceneInput, ObservationPolicy

        scene = self.scene
        fields = set(data) - {"operation"}
        match data.get("operation"):
            case "configure" if fields == {"revision", "mode"}:
                return self.observer.configure_scene(
                    viewer,
                    key,
                    scene,
                    data["revision"],
                    ObservationPolicy(mode=data["mode"]),
                )
            case "consent" if fields == {"revision", "consent"}:
                return self.observer.set_consent(
                    viewer, key, scene, data["revision"], consent=data["consent"]
                )
            case "safety" if fields == {"revision", "pause"}:
                if type(data["revision"]) is not int or type(data["pause"]) is not bool:
                    raise ValueError
                with self.session.store.engine.connect() as connection:
                    self.observer._scene(connection, scene, viewer)
                return self.session.store.safety(
                    viewer, key, data["revision"], pause=data["pause"]
                )
            case "submit" if fields == {"revision", "text", "classification"}:
                command = AppendSceneInput(
                    command_key=key,
                    expected_scene_revision=data["revision"],
                    speaker="handler" if viewer == self.viewers["handler"] else "pilot",
                    text=data["text"],
                    classification=data["classification"],
                )
                result = self.session.submit(viewer, scene, command)
                conversation = result["conversation"]
                replies = []
                if conversation:
                    gm = conversation["gm"]
                    decision = gm["reply"].get("gm_decision")
                    if decision and decision["action"] == "RESPOND":
                        replies.append({"role": "GM", "reply": gm["reply"]["text"]})
                    if handler := conversation["handler"]:
                        replies.append(
                            {"role": "Handler", "reply": handler["reply"]["text"]}
                        )
                return {"input": result["input"], "replies": replies}
            case "gm-work" if not fields:
                return self.session.work(viewer, scene, gm=True)
            case "bind" if fields == {"review", "action"}:
                return self.session.bind_action(
                    viewer, key, scene, data["review"], data["action"]
                )
            case "open" if fields == {"kind", "source", "frame"}:
                frame = (
                    TaskFrame.model_validate_json(json.dumps(data["frame"]))
                    if data["frame"] is not None
                    else None
                )
                request = self.outcomes.open(
                    viewer, key, scene, data["kind"], data["source"], frame
                )
                packet = self.outcomes.packet(viewer, scene, request["id"])
                return {
                    "request": request["id"],
                    "packet": packet.model_dump(mode="json"),
                }
            case "propose" if fields == {"request", "proposal"}:
                return self.outcomes.propose(
                    viewer,
                    key,
                    scene,
                    data["request"],
                    OutcomeProposal.model_validate_json(json.dumps(data["proposal"])),
                )
            case "review" if fields == {"proposal"}:
                return self.outcomes.owner_review(viewer, scene, data["proposal"])
            case "confirm" if (
                fields == {"proposal", "approved"} and data["approved"] is True
            ):
                return self.outcomes.confirm(viewer, key, scene, data["proposal"])
            case "memory" if not fields:
                with self.session.store.engine.connect() as connection:
                    self.outcomes._scope(connection, viewer, scene, gm=True)
                    context = self.session.context._build(connection, viewer, scene)
                    return context.model_dump(mode="json") | {
                        "next_order": len(
                            self.session.context._references(connection, scene)
                        )
                    }
            case "remember" if fields == {"source", "order", "roles", "topic"}:
                if not isinstance(data["roles"], list) or any(
                    role not in self.viewers for role in data["roles"]
                ):
                    raise ValueError
                with self.session.store.engine.connect() as connection:
                    self.outcomes._scope(connection, viewer, scene, gm=True)
                    actors = tuple(
                        self.observer._authorize_input(
                            connection,
                            self.viewers[role],
                            scene,
                            "handler" if role == "handler" else "pilot",
                        )[2]
                        for role in data["roles"]
                    )
                return self.session.context.record(
                    viewer,
                    key,
                    scene,
                    data["source"],
                    data["order"],
                    known_by=actors,
                    topic=data["topic"],
                )
            case "archive" if fields == {"revision", "references", "reason"}:
                if not isinstance(data["references"], list):
                    raise TypeError
                return self.session.context.archive(
                    viewer,
                    key,
                    scene,
                    data["revision"],
                    tuple(data["references"]),
                    data["reason"],
                )
            case _:
                raise ValueError


def discord_trial_binding(config):
    accounts = {
        "invited": config.invited_user_id,
        "other": config.other_user_id,
        "handler": config.handler_user_id,
    }
    if (
        None in accounts.values()
        or len(set(accounts.values())) != 3
        or config.tester_role_ids
    ):
        raise ValueError(
            "P2 requires two named pilot accounts and one named Handler account."
        )
    return {
        "application": config.client_id,
        "guild": config.guild_id,
        "accounts": accounts,
    }


def fork_discord_rehearsal(root, config):
    """Copy the synthetic rehearsal without rebinding any existing trial."""
    root = root.resolve()
    binding = discord_trial_binding(config)
    name = f"rehearsal-{config.client_id}"
    source, destination = root / "rehearsal", root / name
    original = json.loads((source / "activity-discord-binding.json").read_bytes())
    saved = json.loads((source / "synthetic-trial.json").read_bytes())
    if (
        source.resolve() != source
        or original["application"] == binding["application"]
        or original["guild"] != binding["guild"]
        or original["accounts"] != binding["accounts"]
        or saved.get("synthetic") is not True
        or saved.get("version") != 1
        or Path(saved["policy"]["sandbox"]).resolve() != source
    ):
        raise WorkflowError("A separate app must use the original synthetic rehearsal roster.")
    if destination.exists():
        if (
            destination.resolve() != destination
            or json.loads((destination / "activity-discord-binding.json").read_bytes()) != binding
        ):
            raise WorkflowError("The existing app-specific rehearsal has a different binding.")
        return name
    with TemporaryDirectory(prefix=".rehearsal-copy-", dir=root) as staging:
        copy = Path(staging) / "ledger"
        copy.mkdir()
        database = source / "ledger.db"
        if database.resolve().parent != source:
            raise WorkflowError("The rehearsal database must be local to the trial.")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(copy / database.name)) as copied_db:
                source_db.backup(copied_db)
                if copied_db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise WorkflowError("The rehearsal backup failed its integrity check.")
        saved["policy"]["sandbox"] = str(destination)
        (copy / "synthetic-trial.json").write_text(json.dumps(saved), encoding="utf-8")
        (copy / "activity-discord-binding.json").write_text(json.dumps(binding), encoding="utf-8")
        copy.rename(destination)
    return name


def open_trial(engine: Path, root: Path, name: str, *, discord_config=None):
    from girlframe.ai.observation import ObservationPolicy
    from p2_trial_runtime import Trial

    binding = (
        discord_trial_binding(discord_config) if discord_config is not None else None
    )
    if binding is not None:
        root = root.with_name("p2-discord-trials")
    root.mkdir(exist_ok=True)
    directory = (root / name).resolve()
    if directory.parent != root.resolve():
        raise WorkflowError("Use an isolated trial directory.")
    os.environ["GIRLFRAME_RULES_REGISTRY"] = str(engine / "rules" / "registry.json")
    create = not directory.exists()
    binding_file = directory / "activity-discord-binding.json"
    if (
        not create
        and binding is not None
        and (not binding_file.is_file() or json.loads(binding_file.read_bytes()) != binding)
    ):
        raise WorkflowError(
            "This P2 trial belongs to its original Discord roster. Use a new trial name."
        )
    trial = DirectorTrial(Trial(directory, create=create))
    trial.discord_binding = binding
    if create:
        trial.observer.configure_scene(
            trial.viewers["handler"],
            "activity-consent-notice",
            trial.scene,
            1,
            ObservationPolicy(mode="shadow"),
        )
        if binding is not None:
            with binding_file.open("x", encoding="utf-8") as file:
                json.dump(binding, file)
    return trial


class CampaignTraining:
    """Expose actual campaign readiness until native rehearsal support is installed."""

    def __init__(self, service, handler):
        self.store = service.store
        self.handler = handler

    def view(self, viewer):
        self.store.guild_member(viewer)
        with self.store.engine.connect() as connection:
            self.store._membership(connection, viewer)
        return {
            "training_available": False,
            "availability_code": "NATIVE_REHEARSAL_REQUIRED",
            "availability_message": (
                "A training channel has not been commissioned for this campaign. "
                "Use the Operations desk to continue with scene Plays."
            ),
            "status": {"phase": "unavailable", "mode": "off"},
            "facilitator": viewer.user_id == self.handler.user_id,
            "speaker": (
                "handler" if viewer.user_id == self.handler.user_id else "pilot"
            ),
        }

    def perform(self, viewer, key, data):
        self.view(viewer)
        raise WorkflowError(
            "NATIVE_REHEARSAL_REQUIRED: this campaign's engine has no commissioned "
            "training channel."
        )


def campaign_training(service, handler):
    return CampaignTraining(service, handler)
