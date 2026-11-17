"""Development-only persistent synthetic fixture; never a live campaign bootstrap."""

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "tests", ROOT / "tests" / "rules"):
    sys.path.insert(0, str(directory))


class Trial:
    def __init__(self, directory, *, create=False, brief=None):
        from test_director_observation import Clock
        from test_m2_game import Dice, Gateway

        from girlframe.config import Settings
        from girlframe.database.connection import create_database_engine
        from girlframe.delivery.m2_worker import GameWorker
        from girlframe.discord_adapter.config import BotPolicy
        from girlframe.services.director_context import DirectorContextService
        from girlframe.services.director_observation import DirectorObservationService
        from girlframe.services.director_session import DirectorSessionService
        from girlframe.services.ledger import CampaignLedger
        from girlframe.services.m2_game import GameService
        from girlframe.services.onboarding import OnboardingStore

        self.directory = Path(directory).resolve()
        self.clock, self.dice, self.gateway = Clock(), Dice(), Gateway()
        self.role, self.last_message = "lark", None
        self.console_state = {}
        self.fixture = self.patch = None
        if create:
            import pytest
            from test_battle_service import prepared
            from test_ledger import ledger

            if self.directory.exists():
                raise ValueError("Choose a new trial directory; existing files are never replaced.")
            self.directory.mkdir(parents=True, mode=0o700)
            self.patch = pytest.MonkeyPatch()
            self.fixture = ledger.__wrapped__(self.directory, self.patch)
            self.store = next(self.fixture)
            self.game, self.worker, self.gateway, _, _, _ = prepared(self.store)
            self.store.policy = self.store.policy.model_copy(
                update={"owner_table_outcomes": "gm_discretion"}
            )
            self.dice = self.game.dice
        else:
            saved = json.loads((self.directory / "synthetic-trial.json").read_text())
            if saved.get("synthetic") is not True or saved.get("version") != 1:
                raise ValueError("This is not an explicitly created synthetic trial.")
            policy = BotPolicy.model_validate_json(json.dumps(saved["policy"]))
            if (
                policy.sandbox.resolve() != self.directory
                or not (self.directory / "ledger.db").is_file()
            ):
                raise ValueError("Trial directory does not match its original synthetic store.")
            engine = create_database_engine(
                Settings(database_url=f"sqlite:///{self.directory / 'ledger.db'}")
            )
            self.store = CampaignLedger(OnboardingStore(engine, policy, self.clock), dice=self.dice)
            self.game = GameService(self.store, dice=self.dice)
            self.worker = GameWorker(self.game)
            self.clock.now = saved["clock"]
            self.dice.faces = tuple(saved["faces"])
            self.dice.calls = saved["dice_calls"]
            self.role, self.last_message = saved["role"], saved["last_message"]
            self.console_state = saved.get("console_state", {})
            self.gateway.values = {tuple(key): value for key, value in saved["gateway_values"]}
            self.gateway.messages = saved["gateway_messages"]
        self.store.clock = self.clock
        self.observer = DirectorObservationService(self.store, synthetic=True)
        self.observer.game = self.game
        with self.store.engine.connect() as c:
            self.scene = self.game.scene(c, 900)["id"]
        self.context = DirectorContextService(self.observer)
        self.session = DirectorSessionService(self.context)
        if create:
            self._seed(brief)
        self.save()

    @staticmethod
    def viewers():
        from test_ledger import ADMIN, OTHER, PLAYER

        return {"gm": ADMIN, "handler": ADMIN, "lark": PLAYER, "kite": OTHER}

    @property
    def viewer(self):
        return self.viewers()[self.role]

    def _seed(self, brief):
        from test_ledger import ADMIN, OTHER, PLAYER
        from test_m2_game import state

        from girlframe.ai.observation import ObservationPolicy

        self.role = "gm"
        self.observer.configure_scene(
            ADMIN, "trial-policy", self.scene, 0, ObservationPolicy(mode="shadow")
        )
        for viewer in (ADMIN, PLAYER, OTHER):
            self.observer.set_consent(
                viewer, f"trial-consent:{viewer.user_id}", self.scene, 1, consent=True
            )
        with self.store.transaction() as c:
            canon = state(self.game)
            canon.facts.append({"kind": "gm_only", "body": "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY"})
            self.game.event(c, 1, "trial-background", "synthetic.trial_background", canon)
        brief = brief or {
            "objective": "Discuss readiness and investigate the stated simulation observations.",
            "scope": "Training only; forced entry is not authorised. Disclosures are voluntary.",
            "status": "No actual mission has been accepted; this is a synthetic exercise.",
        }
        for topic, text in brief.items():
            self.message(text, role="handler", route=False)
            self.remember(self.last_message["source_id"], ("lark", "kite", "handler"), topic)
        self.role, self.last_message = "lark", None

    def message(self, text, *, role=None, route=True, command_key=None):
        from girlframe.ai.observation import AppendSceneInput

        role = role or self.role
        if role == "gm":
            raise ValueError("Use GM review commands; choose Handler for in-fiction speech.")
        viewer = self.viewers()[role]
        command = AppendSceneInput(
            command_key=command_key or str(uuid4()),
            expected_scene_revision=self.observer.status(viewer, self.scene).scene_revision,
            speaker="handler" if role in ("handler", "gm") else "pilot",
            text=text,
        )
        self.last_message = {
            "role": role,
            "command": command.model_dump(mode="json"),
            "source_id": None,
        }
        self.save()
        if route:
            result = self.session.submit(viewer, self.scene, command)
            self.last_message["source_id"] = result["input"]["source_id"]
        else:
            result = self.observer.append_scene_input(viewer, self.scene, command).model_dump(
                mode="json"
            )
            self.last_message["source_id"] = result["source_id"]
        self.save()
        return result

    def retry(self):
        from girlframe.ai.observation import AppendSceneInput

        if not self.last_message or self.last_message["role"] != self.role:
            raise ValueError("Switch to the original synthetic sender before retrying.")
        return self.session.submit(
            self.viewer,
            self.scene,
            AppendSceneInput.model_validate_json(json.dumps(self.last_message["command"])),
        )

    def remember(self, source, roles, topic="general"):
        from test_ledger import ADMIN

        if self.role != "gm":
            # The service always verifies GM identity; the console does not infer it from text.
            raise ValueError("Select the synthetic GM persona for reference assignments.")
        with self.store.engine.connect() as c:
            actors = tuple(
                self.observer._authorize_input(
                    c,
                    self.viewers()[role],
                    self.scene,
                    "handler" if role in ("handler", "gm") else "pilot",
                )[2]
                for role in roles
            )
            order = len(self.context._references(c, self.scene))
        return self.context.record(
            ADMIN, str(uuid4()), self.scene, source, order, known_by=actors, topic=topic
        )

    def tick(self, count=5):
        from test_m2_game import tick

        tick(self.worker, self.gateway, count)
        self.save()

    def restart_services(self):
        from girlframe.services.director_context import DirectorContextService
        from girlframe.services.director_session import DirectorSessionService

        self.store.engine.dispose()
        self.context = DirectorContextService(self.observer)
        self.session = DirectorSessionService(self.context)

    def save(self):
        if not hasattr(self, "store"):
            return
        value = {
            "version": 1,
            "synthetic": True,
            "policy": self.store.policy.model_dump(mode="json"),
            "clock": self.clock.now,
            "faces": list(self.dice.faces),
            "dice_calls": self.dice.calls,
            "role": self.role,
            "last_message": self.last_message,
            "console_state": self.console_state,
            "gateway_values": [[list(k), v] for k, v in self.gateway.values.items()],
            "gateway_messages": self.gateway.messages,
        }
        temporary = self.directory / "synthetic-trial.tmp"
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.directory / "synthetic-trial.json")

    def close(self):
        self.save()
        self.store.engine.dispose()
        if self.fixture:
            self.fixture.close()
        if self.patch:
            self.patch.undo()
