"""Loopback-only Activity development harness for the pinned HarpyEngine source."""

# ruff: noqa: E402
# The pinned engine path must be selected before importing any engine-consuming modules.

import argparse
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from hashlib import sha256
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, RLock, Thread
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from discord_session import DiscordConfig, DiscordSessions, SignInError

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parent / ".sites-runtime" / "harpyengine-mission-lab"
ENGINE = RUNTIME / (
    "HarpyEngine-p2-candidate"
    if any(arg == "--p2-trial" or arg.startswith("--p2-trial=") for arg in sys.argv)
    else "HarpyEngine-release-723955c"
)
sys.path[:0] = [
    str(ENGINE / "src"),
    str(ENGINE / "tests"),
    str(ENGINE / "tests" / "rules"),
]

import sqlalchemy as sa
from activity_ai_trial import ActivityAITrial
from activity_artwork import ARTWORK, CATALOG, artwork_bytes
from alembic import command
from alembic.config import Config
from battlefield import Battlefield, BattlefieldChanged, seed_battlefield
from campaign_registry import (
    DEFAULT_CAMPAIGN,
    SNOWFLAKE,
    CampaignBinding,
    CampaignBindingError,
    CampaignRegistry,
)
from handler_playbook import HANDLER_PLAY_STEPS
from mission_desk import MissionDesk
from p2_scene import (
    SESSION_ZERO_READS,
    SESSION_ZERO_WRITES,
    P2Scene,
    activity_facilitator,
    local_fixture_director,
    manual_campaign_setup,
)
from player_setup import SCENE, EnrollmentInputError, PlayerSetup, seed_players, seed_roster
from private_battlefield import PRIVATE_BATTLEFIELD_CHANNEL, PrivateBattlefield

from girlframe.config import Settings
from girlframe.database import tables
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine.rules_registry import Registry
from girlframe.services.ledger import CampaignLedger
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.p1_facilitator import UNLISTED_ACTION, FacilitatorService
from girlframe.services.read_only_bot import GuildViewer

GUILD = 200
HANDLER = GuildViewer(1, GUILD, True, True)
OFFERED = GuildViewer(2, GUILD, True, False)
OTHER = GuildViewer(4, GUILD, True, False)
DRILL_OPPONENT = GuildViewer(3, GUILD, True, False)
COOKIE = "harpy_lab_session"
PRESENCE_SECONDS = 90
MISSION_ROUTE = re.compile(r"/api/mission-offers/([0-9a-f-]{36})/response")
DM_RECEIPT_ROUTE = re.compile(r"/api/dm-receipts/([0-9a-f]{32})")
DIRECTOR_ROUTE = re.compile(
    r"/api/director/([0-9a-f-]{36})/([a-z-]{1,35})(?:/([A-Za-z0-9:-]{1,100}))?"
)
SETUP_ROUTE = re.compile(r"/api/campaign-opening/([a-z-]{1,35})(?:/([A-Za-z0-9:-]{1,100}))?")
SETUP_READ = {
    "opening",
    "opening-brief",
    "persona-setup",
    "persona-agreement",
    "fictional-time",
    "portrayal-sheets",
} | SESSION_ZERO_READS
SETUP_WRITE = {
    "opening-save",
    "opening-launch",
    "persona-save",
    "persona-notes",
    "persona-activate",
    "persona-propose",
    "persona-answer",
    "portrayal-draft",
    "portrayal-confirm",
} | SESSION_ZERO_WRITES.keys()
TRANSCRIPT_ROUTE = re.compile(r"/api/rooms/(relay|[0-9a-f]{16})/transcript")
COMMUNICATION_ROUTE = re.compile(r"/api/communications/((?:pilot|handler)-[0-9a-z-]{1,80})")
BATTLEFIELD_ROUTE = re.compile(
    r"/api/battlefield/(open|join|place|review-placement|create-enemy|add-enemy|start-turns|end-turn|close-turns|move|engage|check_sensors|keep_your_head|flirt|put_someone_beneath_you|living_battery|disobey_orders|issue-order|choice|fulfill|core-expose|frame-work|(?:assault|core)-(?:declare|review|roll))"
)
KEY = re.compile(r"[A-Za-z0-9._-]{8,100}")
SESSION_ZERO_PATH = "/api/campaign-opening/session-zero"
FACILITATOR_ROUTE = re.compile(r"/api/facilitator-reviews(?:/([0-9a-f-]{36}))?")
START_FRESH_PATH = "/api/activity/start-fresh"
FRESH_JOB_ROUTE = re.compile(r"/api/activity/start-fresh/([0-9a-f]{32})")
UI_FILES = (
    "foundation.css",
    "foundation-ova.css",
    "shift-handover.css",
    "shift-handover.js",
    "popup-ui.js",
    "rulebook-text.json",
    "foundation-ui.js",
    "facility-plans.json",
    "mail-spool.js",
    "artwork-ui.js",
    "artwork.css",
    "player-setup.js",
    "mission-desk.js",
    "battlefield-ui.js",
    "communications-ui.js",
    "director-trial.js",
    "p2-desk.js",
    "character-sheet-ui.js",
    "character-draft-ui.js",
    "character-sheets/harpyengine-sheets.mjs",
    "character-sheets/validators.mjs",
    "character-sheets/creation-catalog-v1.json",
)


def activity_assets(sdk):
    """Serve the HTML and all its imports from one release."""
    files = {name: (HERE / name).read_bytes() for name in ("index.html", *UI_FILES)}
    if sdk is not None:
        files["discord-sdk.js"] = sdk
    digest = sha256()
    for name, payload in files.items():
        digest.update(name.encode())
        digest.update(sha256(payload).digest())
    version = digest.hexdigest()[:16]
    for name in ("index.html", *UI_FILES):
        payload = files[name]
        for dependency in (*UI_FILES, "discord-sdk.js"):
            payload = payload.replace(
                f'"/{dependency}"'.encode(), f'"/{dependency}?v={version}"'.encode()
            )
        files[name] = payload
    return version, files


def roster_viewers(config: DiscordConfig):
    if not config.other_user_id or not config.handler_user_id:
        raise ValueError("Configure two pilots and a Handler for the private roster.")
    guild = int(config.guild_id)
    return {
        "invited": GuildViewer(int(config.invited_user_id), guild, True, False),
        "other": GuildViewer(int(config.other_user_id), guild, True, False),
        "handler": GuildViewer(int(config.handler_user_id), guild, True, False),
    }


def open_campaign(
    name: str, *, tactical: bool = False, roster: DiscordConfig | None = None
) -> MissionService:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise ValueError("Use a lowercase alphanumeric test campaign name.")
    os.environ["GIRLFRAME_RULES_REGISTRY"] = str(ENGINE / "rules" / "registry.json")
    registry = load_registry()
    campaigns = RUNTIME / "playtest-campaigns"
    sandbox = (campaigns / name).resolve()
    if sandbox.parent != campaigns.resolve():
        raise ValueError("Campaign storage must stay inside the local lab.")
    sandbox.mkdir(parents=True, exist_ok=True)
    database = sandbox / "missions.sqlite3"
    policy_file = sandbox / "synthetic-policy.json"
    roster_file = sandbox / "discord-roster.json"
    viewers = roster_viewers(roster) if roster else None
    membership = (
        {role: str(viewer.user_id) for role, viewer in viewers.items()} if viewers else None
    )
    guild_id = int(roster.guild_id) if roster else GUILD
    application_id = int(roster.client_id) if roster else 100
    if database.exists() != policy_file.exists():
        raise RuntimeError("Incomplete lab data. Choose a new test campaign name.")
    if database.exists() and (
        (roster_file.exists() != bool(roster))
        or (roster and json.loads(roster_file.read_bytes()) != membership)
    ):
        raise RuntimeError("This private campaign is bound to a different Discord roster.")
    url = f"sqlite:///{database.as_posix()}"
    engine = create_database_engine(Settings(database_url=url))
    if policy_file.exists():
        policy = BotPolicy.model_validate_json(policy_file.read_bytes())
        if (
            policy.sandbox != sandbox
            or policy.guild_id != guild_id
            or policy.application_id != application_id
        ):
            raise RuntimeError("Only the lab's synthetic policy can be opened here.")
        return MissionService(OnboardingStore(engine, policy), registry)

    # Alembic reads only this fixed lab DB URL. No bot configuration is loaded.
    os.environ["GIRLFRAME_DATABASE_URL"] = url
    os.environ.pop("GIRLFRAME_ENGINE_SANDBOX", None)
    command.upgrade(Config(str(ENGINE / "alembic.ini")), "head")
    policy = BotPolicy(
        application_id=application_id,
        guild_id=guild_id,
        campaign_id=uuid4(),
        sandbox=sandbox,
        allow_guild_administrators=True,
        status_audience_approved=True,
    )
    store = OnboardingStore(engine, policy)
    # Reuse upstream's synthetic character/approval setup. The offer and its
    # responses run through the actual engine service and database.
    from m3_policy_scenario import configure_m3_fixture

    if viewers:
        seed_roster(store, viewers["handler"], viewers["invited"], viewers["other"])
        service = MissionService(store, configure_m3_fixture(store))
        roster_file.write_text(json.dumps(membership), encoding="utf-8")
    elif tactical:
        from test_m2_game import setup_game

        setup_game(store)
        service = MissionService(store, configure_m3_fixture(store))
        seed_battlefield(service, HANDLER, OFFERED, DRILL_OPPONENT)
    else:
        seed_players(store, HANDLER, OFFERED, OTHER)
        service = MissionService(store, configure_m3_fixture(store))
        service.offer(
            HANDLER,
            "lab-offer-001",
            "Check the relay beacon and report its signal pattern.",
            (OFFERED.user_id,),
        )
    policy_file.write_text(store.policy.model_dump_json(indent=2), encoding="utf-8")
    return service


def restore_windows_fixture_approval(policy, registry, registry_bytes):
    approval = policy.m3_approval
    canonical = digest(registry)
    if (
        approval is None
        or approval.reviewer != "synthetic fixture only"
        or approval.reference != "Not independent certification"
        or approval.registry_sha256 == canonical
    ):
        return policy
    try:
        legacy = Registry.model_validate_json(registry_bytes.decode("cp1252"))
    except ValueError:
        return policy
    if approval.registry_sha256 != digest(legacy):
        return policy
    # Older Windows fixtures fingerprinted the same bundled bytes as CP1252.
    # Recheck that exact source, then keep the filed subsystem scope.
    return policy.model_copy(
        update={
            "m3_approval": approval.model_copy(update={"registry_sha256": canonical}),
        }
    )


def open_managed_campaign(binding: CampaignBinding, *, initialize=True) -> MissionService:
    sandbox = (RUNTIME / "playtest-campaigns" / ("activity-" + UUID(binding.id).hex)).resolve()
    if initialize:
        sandbox.mkdir(parents=True, exist_ok=True)
    database = sandbox / "missions.sqlite3"
    policy_file = sandbox / "synthetic-policy.json"
    url = f"sqlite:///{database.as_posix()}"
    registry_path = ENGINE / "rules" / "registry.json"
    os.environ["GIRLFRAME_RULES_REGISTRY"] = str(registry_path)
    registry_bytes = registry_path.read_bytes()
    registry = Registry.model_validate_json(registry_bytes)
    if policy_file.is_file():
        policy = BotPolicy.model_validate_json(policy_file.read_bytes())
        if (
            policy.sandbox != sandbox
            or policy.campaign_id != UUID(binding.id)
            or policy.guild_id != int(binding.guild_id)
            or policy.application_id != int(binding.application_id)
            or not database.is_file()
        ):
            raise RuntimeError("The registered campaign’s storage binding is invalid.")
        policy = restore_windows_fixture_approval(policy, registry, registry_bytes)
        return MissionService(
            OnboardingStore(create_database_engine(Settings(database_url=url)), policy),
            registry,
        )
    if not initialize:
        raise RuntimeError("The bot must finish setting up this campaign store.")

    # Keep the migration's database settings out of the running server environment.
    env = os.environ | {
        "GIRLFRAME_DATABASE_URL": url,
        "PYTHONPATH": str(ENGINE / "src"),
    }
    env.pop("GIRLFRAME_ENGINE_SANDBOX", None)
    env.pop("GIRLFRAME_ACTIVITY_SETUP_BOT_TOKEN", None)
    env.pop("GIRLFRAME_ACTIVITY_DISCORD_CLIENT_SECRET", None)
    env.pop("OPENAI_API_KEY", None)
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "alembic",
            "-c",
            str(ENGINE / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=ENGINE,
        env=env,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=90,
    )
    policy = BotPolicy(
        application_id=int(binding.application_id),
        guild_id=int(binding.guild_id),
        campaign_id=UUID(binding.id),
        sandbox=sandbox,
        allow_guild_administrators=True,
        status_audience_approved=True,
    )
    store = OnboardingStore(create_database_engine(Settings(database_url=url)), policy)
    # Match the existing private Activity's isolated campaign rule approvals.
    from m3_policy_scenario import configure_m3_fixture

    handler = GuildViewer(int(binding.handler_id), policy.guild_id, True, False)
    seed_roster(store, handler)
    service = MissionService(store, configure_m3_fixture(store))
    # New managed campaigns use the established owner ruling for original Handler creation.
    rulings = store.policy.owner_m3_rulings
    store.policy = store.policy.model_copy(
        update={
            "owner_m3_rulings": rulings.model_copy(
                update={"handler_creation": "owned_shared_choices_preserve_existing"}
            )
        }
    )
    ledger = CampaignLedger(store)
    organizer = GuildViewer(int(binding.handler_id), policy.guild_id, True, True)
    status = ledger.status(organizer)
    if not status["initialized"]:
        ledger.create_campaign(
            organizer, "activity-campaign-created", status["revision"], binding.name
        )
    pending = policy_file.with_suffix(".pending")
    pending.write_text(store.policy.model_dump_json(indent=2), encoding="utf-8")
    pending.replace(policy_file)
    return service


def provision_managed_campaign(binding):
    open_managed_campaign(binding).store.engine.dispose()


def load_owner_setup_preview(path):
    try:
        record = json.loads(path.read_bytes())
        identity, owner = record["campaign_id"], record["owner_id"]
        if not SNOWFLAKE.fullmatch(owner):
            raise ValueError
        return UUID(identity).hex, owner
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("Owner setup preview is disabled. Check its local grant.", file=sys.stderr)
        return None


@dataclass
class ActivityCampaign:
    service: MissionService
    setup: PlayerSetup
    battlefield: Battlefield | None
    training: object | None = None
    enrollment_lock: Lock = field(default_factory=Lock)
    presence_lock: Lock = field(default_factory=Lock)
    presence: dict[str, float] = field(default_factory=dict)
    reviewed_director: P2Scene | None = None
    managed: bool = False
    work_lock: RLock = field(default_factory=RLock)
    worker: tuple | None = None
    retired: bool = False
    resetting: bool = False


class ActivityHTTPServer(ThreadingHTTPServer):
    request_queue_size = 32


# Reviewed for the private Activity against official printed pp. 79–81 and 86–89.
# This scope cannot certify the canonical registry or enable either entire Frame.
ACTIVITY_SPECIALIST_RULES = frozenset(
    {
        "frame.changeling.blank-slate",
        "frame.changeling.psych-strings",
        "frame.changeling.body-of-clay",
        "frame.red-queen.queens-court",
        "frame.red-queen.memory-extraction",
        "frame.red-queen.am-transfer",
    }
)


def enable_private_subsystems(service):
    from girlframe.engine.m3_policy import Rulings

    policy = service.store.policy
    approval = policy.m3_approval
    if approval and approval.reviewer == "synthetic fixture only":
        # Expand synthetic drills only. Explicit campaign releases retain their filed scope.
        rulings = policy.owner_m3_rulings or Rulings()
        service.store.policy = policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={
                        "subsystems": approval.subsystems
                        | {"world", "plays", "strain", "playbooks"},
                        "activity_specialist_rules": ACTIVITY_SPECIALIST_RULES,
                    }
                ),
                "owner_m3_rulings": rulings.model_copy(
                    update={"beneath_private_choices": "affected_owner"}
                ),
            }
        )


def audit(service: MissionService) -> dict:
    offers = service.list(OFFERED)
    table = tables.events
    with service.store.engine.connect() as connection:
        response_events = connection.execute(
            sa.select(table.c.actor_id, table.c.command_key).where(
                table.c.campaign_id == service.store.campaign_id,
                table.c.kind == "m3.mission_response",
            )
        ).all()
        receipts = dict(
            connection.execute(
                sa.select(tables.commands.c.interaction_key, tables.commands.c.outcome_json).where(
                    tables.commands.c.campaign_id == service.store.campaign_id,
                    tables.commands.c.interaction_key.in_([key for _, key in response_events]),
                )
            ).all()
        )
    return {
        "offers": offers,
        "responses": service.get(OFFERED, offers[0]["id"])["mission"]["responses"],
        "response_events": [{"actor": actor, "key": key} for actor, key in response_events],
        "stored_receipts": {key: json.loads(value) for key, value in receipts.items()},
    }


def serve(
    service: MissionService,
    port: int,
    stop_on_input_close: bool,
    discord: DiscordSessions | None = None,
    *,
    tactical_dice=None,
    scene_dice=None,
    prepare_test_battlefield=None,
    bound_roster=False,
    campaign_registry=None,
    campaign_bot_token=None,
    director=None,
    rehearsal_origin=None,
    inbox_dms=True,
    campaign_roles_only=False,
    p2_fixture=False,
    p2_shadow_readiness=False,
) -> None:
    if director is not None:
        from director_trial import discord_trial_binding

        binding = discord_trial_binding(discord.config) if discord else None
        if (
            director.discord_binding != binding
            or bound_roster
            or campaign_registry
            or campaign_bot_token
            or campaign_roles_only
        ):
            raise ValueError(
                "The assisted trial requires its original isolated campaign and roster."
            )
    if rehearsal_origin is not None:
        target = urlsplit(rehearsal_origin)
        if (
            director is None
            or discord is None
            or target.scheme != "https"
            or not target.hostname
            or target.username is not None
            or rehearsal_origin != f"https://{target.netloc}"
        ):
            raise ValueError(
                "A direct Activity origin requires an isolated Discord rehearsal "
                "and an HTTPS origin."
            )
    if p2_shadow_readiness and not p2_fixture:
        raise ValueError("Shadow readiness requires the disposable P2 fixture.")
    if p2_fixture and (discord or bound_roster or campaign_registry):
        raise ValueError("P2 fixture routes require a disposable offline Activity lab.")
    if bound_roster and not discord:
        raise ValueError("The private roster requires Discord sign-in.")
    if discord and discord.config.tester_role_ids and not bound_roster:
        raise ValueError("Girl and Frame roles require the private roster campaign.")
    if campaign_roles_only:
        from girlframe.services.handler_setup import HandlerService

        with service.store.engine.connect() as connection:
            appointed = HandlerService(service.store).current(connection)[1].handler_id
        if appointed is None:
            raise ValueError("The campaign requires its appointed Handler.")
        actual_handler = GuildViewer(int(appointed), service.store.policy.guild_id, True, False)
        viewers = dict.fromkeys(("invited", "other", "handler"), actual_handler)
    else:
        viewers = (
            director.viewers
            if director
            else (
                roster_viewers(discord.config)
                if bound_roster
                else {
                    "invited": OFFERED,
                    "other": OTHER,
                    "handler": HANDLER,
                }
            )
        )
    first, second, handler = (viewers[role] for role in ("invited", "other", "handler"))
    if bound_roster:
        enable_private_subsystems(service)
    elif director and (approval := service.store.policy.m3_approval):
        service.store.policy = service.store.policy.model_copy(
            update={
                "m3_approval": approval.model_copy(
                    update={"subsystems": approval.subsystems | {"world"}}
                )
            }
        )
    setup = PlayerSetup(service.store, handler, first, second, bound_roster=bound_roster)
    setup.enable_activity_records()
    battlefield = None
    discord_log = logging.getLogger("harpy_activity.discord")
    diagnostics = None
    if discord:
        diagnostics = logging.FileHandler(
            service.store.policy.sandbox / "activity-gateway.log", encoding="utf-8"
        )
        diagnostics.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        discord_log.addHandler(diagnostics)
    setup.enable_scene_plays(
        scene_dice,
        extra_channels=(PRIVATE_BATTLEFIELD_CHANNEL,) if bound_roster or director else (),
    )
    if director:
        setup.scene_plays.handler_proxy = False
    if bound_roster or director:
        battlefield = PrivateBattlefield(
            service, setup, dice=tactical_dice or scene_dice, facilities=director is not None
        )
    elif (
        not director
        and discord
        and not bound_roster
        and (discord.config.allow_dm or discord.config.other_user_id)
    ):
        identity = sha256(str(service.store.campaign_id).encode()).hexdigest()[:24]
        shared = bool(discord.config.other_user_id)
        tactical = open_campaign(
            ("tactical-shared-" if shared else "tactical-") + identity, tactical=True
        )
        if shared:
            # Only the isolated synthetic drill uses this local adjudication preset.
            rulings = tactical.store.policy.owner_m3_rulings
            if rulings is not None:
                tactical.store.policy = tactical.store.policy.model_copy(
                    update={
                        "owner_m3_rulings": rulings.model_copy(
                            update={"beneath_private_choices": "affected_owner"}
                        )
                    }
                )
        battlefield = Battlefield(
            tactical,
            HANDLER,
            OFFERED,
            DRILL_OPPONENT,
            dice=tactical_dice,
            shared=shared,
        )
        if prepare_test_battlefield is not None:
            prepare_test_battlefield(battlefield)
    fixture_director = (
        local_fixture_director(setup.game, activity_shadow=p2_shadow_readiness)
        if p2_fixture
        else None
    )
    director_scene = None
    if fixture_director:
        with service.store.engine.connect() as connection:
            director_scene = setup.game.scene(connection, 900)["id"]

    def director_room(room):
        if not fixture_director or room != "relay":
            return False
        with service.store.engine.connect() as connection:
            observer = fixture_director.session.observer
            state = observer._state(connection, director_scene)
            return state.policy.mode == "shadow" and (
                not p2_shadow_readiness
                or observer._consented(
                    connection,
                    observer._scene(connection, director_scene, allow_closed=True),
                    state,
                )
            )

    def campaign_opening(campaign, route):
        setup = campaign.setup
        opening = manual_campaign_setup(
            setup.game,
            setup.handler.user_id,
            opening_channel=SCENE,
            setup_organizer=bot_setup_organizer(campaign),
        )
        if not route.startswith("opening"):
            return opening, ""
        with setup.game.store.engine.connect() as connection:
            return opening, setup.game.scene(connection, SCENE)["id"]

    def paired_ai_ready(campaign):
        store = campaign.setup.game.store
        if (
            ai_trial is None
            or campaign.reviewed_director is None
            or ai_trial.campaign != store.campaign_id
        ):
            return False
        with store.engine.connect() as connection:
            models = ai_trial.model_selection(connection)["models"]
        return bool(models["handler"] and models["director"])

    participants = {
        secrets.token_urlsafe(32): (label, viewers[role])
        for role, label in (("invited", "Invited pilot"), ("other", "Other pilot"))
    }
    if director:
        participants[secrets.token_urlsafe(32)] = ("GM and Handler", handler)
    sessions: dict[str, tuple[str, GuildViewer]] = {}
    sdk = (RUNTIME / "discord-sdk" / "embedded-app.js").read_bytes() if discord else None
    asset_version, assets = activity_assets(sdk)
    default = ActivityCampaign(service, setup, battlefield)
    if bound_roster:
        setup.bot_enrollment.reconcile()
    if campaign_roles_only:
        from director_trial import campaign_training

        default.training = campaign_training(service, handler)
    catalog = campaign_registry or (
        CampaignRegistry(RUNTIME / "activity-campaigns.sqlite3") if bound_roster else None
    )
    owner_setup_grant = (
        load_owner_setup_preview(RUNTIME / "activity-owner-setup-preview.json") if catalog else None
    )
    inbox_notices = None
    if inbox_dms and bound_roster and catalog and campaign_bot_token:
        from campaign_inbox import InboxNotices

        namespace = f"{discord.config.client_id}-{discord.config.guild_id}"
        inbox_notices = InboxNotices(RUNTIME / f"activity-inbox-notices-{namespace}.sqlite3")
    ai_trial = None
    if discord and catalog:
        try:
            ai_trial = ActivityAITrial.from_environment()
        except ValueError:
            print(
                "Reviewed AI is disabled. Check the Activity AI environment settings.",
                file=sys.stderr,
            )
    runtime_lock = Lock()
    runtimes = {}
    if campaign_roles_only and catalog:
        for binding in catalog.bindings(discord.config.client_id, discord.config.guild_id):
            if str(UUID(binding.id)) == str(service.store.campaign_id):
                default.managed = True
                if ai_trial and ai_trial.campaign == service.store.campaign_id:
                    default.reviewed_director = ai_trial.adapter(
                        setup.game,
                        opening_channel=SCENE,
                        setup=setup,
                        battlefield=default.battlefield,
                    )
                runtimes[binding.id] = default
    workers = []
    shutting_down = False
    reset_jobs = {}
    reset_jobs_lock = Lock()

    def bindings():
        return (
            catalog.bindings(discord.config.client_id, discord.config.guild_id) if catalog else []
        )

    def bot_setup_organizer(campaign):
        if not campaign.managed or owner_setup_grant is None:
            return None
        origin, owner = owner_setup_grant
        campaign_id = catalog.latest(origin)
        if (
            UUID(campaign.service.store.campaign_id).hex == campaign_id
            and str(campaign.setup.handler.user_id) == discord.config.client_id
            and catalog.owns_bot_managed_campaign(
                campaign_id, discord.config.client_id, discord.config.guild_id, owner
            )
        ):
            return int(owner)
        return None

    scanned = {}

    def scan_interactions():
        from campaign_inbox import pending_interactions

        with runtime_lock:
            active = tuple(campaign for campaign in runtimes.values() if not campaign.retired)
        for campaign in active:
            store = campaign.service.store
            with store.engine.connect() as connection:
                version = connection.scalar(
                    sa.select(sa.func.max(tables.events.c.seq)).where(
                        tables.events.c.campaign_id == store.campaign_id
                    )
                )
            if store.campaign_id in scanned and scanned[store.campaign_id] == version:
                continue
            items = []
            members = campaign.setup.campaign_members(campaign.setup.handler)
            for member in members:
                if member["bot"]:
                    continue
                owner = GuildViewer(int(member["id"]), store.policy.guild_id, True, False)
                items.extend(
                    (kind, identity, member["id"])
                    for kind, identity in pending_interactions(
                        campaign.setup, campaign.service, campaign.battlefield, owner
                    )
                )
            inbox_notices.sync(store.campaign_id, items)
            scanned[store.campaign_id] = version

    def notice_pending(binding, item):
        from campaign_inbox import pending_interactions

        _, kind, identity, recipient = item
        with runtime_lock:
            active = runtimes.get(binding.id)
        owner = GuildViewer(int(recipient), int(binding.guild_id), True, False)
        source = active.service if active else open_managed_campaign(binding, initialize=False)
        try:
            if active:
                players, arena = active.setup, active.battlefield
            else:
                enable_private_subsystems(source)
                handler = GuildViewer(int(binding.handler_id), int(binding.guild_id), True, False)
                players = PlayerSetup(source.store, handler, handler, handler, bound_roster=True)
                players.enable_activity_records()
                arena = PrivateBattlefield(source, players)
            if kind == "scene_invite":
                with source.store.engine.connect() as connection:
                    players.game.authorize(connection, owner, game=False)
                return any(card["id"] == identity for card in players.records.scene_invites(owner))
            return (kind, identity) in pending_interactions(players, source, arena, owner)
        except WorkflowError:
            return False
        finally:
            if not active:
                source.store.engine.dispose()

    if catalog:
        discord.managed_roles = lambda: frozenset(item.role_id for item in bindings())
        discord.campaign_roles_only = campaign_roles_only or campaign_registry is not None

    def managed_runtime(binding):
        with runtime_lock:
            if shutting_down:
                raise SignInError(HTTPStatus.SERVICE_UNAVAILABLE, "The Activity is restarting.")
            if binding.id in runtimes:
                return runtimes[binding.id]
            try:
                managed = open_managed_campaign(binding, initialize=False)
                enable_private_subsystems(managed)
                gm = GuildViewer(int(binding.handler_id), int(binding.guild_id), True, False)
                # In role-bound mode admission is dynamic. Only the configured Handler is pre-bound.
                players = PlayerSetup(managed.store, gm, gm, gm, bound_roster=True)
                players.enable_activity_records()
                players.enable_scene_plays(extra_channels=(PRIVATE_BATTLEFIELD_CHANNEL,))
                players.bot_enrollment.reconcile()
                arena = PrivateBattlefield(managed, players)
                runtime = ActivityCampaign(managed, players, arena, managed=True)
                if discord.campaign_roles_only:
                    from director_trial import campaign_training

                    runtime.training = campaign_training(managed, gm)
                if ai_trial and ai_trial.campaign == managed.store.campaign_id:
                    runtime.reviewed_director = ai_trial.adapter(
                        players.game, opening_channel=SCENE, setup=players, battlefield=arena
                    )
                runtime.worker = players.scene_plays.start_worker(work_lock=runtime.work_lock)
                workers.append(runtime.worker)
                runtimes[binding.id] = runtime
                return runtime
            except (
                OSError,
                RuntimeError,
                ValueError,
                subprocess.SubprocessError,
                WorkflowError,
            ):
                raise SignInError(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "This campaign could not be opened. Contact the server owner.",
                ) from None

    def replace_campaign(campaign, binding, owner, data, key):
        def checkpoint():
            from activity_campaign_archive import export_campaign, import_campaign

            directory = RUNTIME / "campaign-checkpoints" / binding.id
            directory.mkdir(parents=True, exist_ok=True)
            archive = directory / (uuid4().hex + ".zip")
            export_campaign(RUNTIME, binding.id, archive, registry=catalog.path)
            with TemporaryDirectory(prefix="restore-check-", dir=directory) as temporary:
                import_campaign(archive, Path(temporary) / "verified-restore")

        replacement = catalog.replace_campaign(
            binding.id,
            application_id=binding.application_id,
            guild_id=binding.guild_id,
            owner_id=owner,
            confirmation=data["confirmation"],
            name=data["name"],
            key=key,
            checkpoint=checkpoint,
            provision=provision_managed_campaign,
        )
        campaign.retired = True
        if campaign.worker:
            campaign.worker[0].set()
        return replacement.id

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # Launch capabilities and cookies are deliberately omitted from logs.
            return

        def send_payload(self, status, body, media="application/json", **headers):
            if discord and status >= 500:
                # Record the fixed route family only. Discard request data, IDs and tokens.
                route = urlsplit(self.path).path
                family = (
                    "mission"
                    if route.startswith("/api/mission-offers")
                    else ("scene" if route.startswith("/api/player-setup") else "sign-in")
                )
                discord_log.warning("Activity %s %s returned HTTP %s", self.command, family, status)
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, value):
            self.send_payload(status, json.dumps(value).encode("utf-8"))

        def queue_notice(self, kind, source, actor, receipt):
            if inbox_notices is None:
                return receipt
            try:
                getattr(inbox_notices, kind)(source, actor, receipt)
                token = inbox_notices.sender_receipt(
                    source.store.campaign_id, actor.user_id, kind, receipt["id"]
                )
                if token:
                    return receipt | {"dm_receipt": token}
            except (WorkflowError, sa.exc.SQLAlchemyError, sqlite3.Error, OSError):
                discord_log.warning("Could not file an Inbox DM for a saved decision.")
            return receipt

        def read_dm_receipt(self, campaign, viewer, identity):
            if inbox_notices is None:
                return None
            rows = inbox_notices.read_receipt(
                campaign.service.store.campaign_id, viewer.user_id, identity
            )
            if not rows:
                return None
            names = {
                member["id"]: member["name"] for member in campaign.setup.campaign_members(viewer)
            }
            now = monotonic()
            with campaign.presence_lock:
                return {
                    "recipients": [
                        {
                            "name": names.get(recipient, "Pilot"),
                            "status": outcome,
                            "online": now - campaign.presence.get(recipient, now - PRESENCE_SECONDS)
                            < PRESENCE_SECONDS,
                        }
                        for recipient, outcome in rows
                    ]
                }

        def session(self):
            if getattr(self, "selected_session", None):
                return self.selected_session
            if discord:
                identity = discord.resolve(self.headers.get("Authorization", ""))
                role = identity.role
                if (
                    director
                    and director.discord_binding["accounts"].get(role) != identity.discord_id
                ):
                    raise SignInError(
                        HTTPStatus.FORBIDDEN, "This account has no seat in the P2 trial."
                    )
                if discord.campaign_roles_only:
                    raise SignInError(
                        HTTPStatus.CONFLICT, "Select a campaign before opening its records."
                    )
                if role == "role_tester":
                    if not discord.can_use_default(identity):
                        raise SignInError(
                            HTTPStatus.FORBIDDEN,
                            "Your role does not grant access to this campaign.",
                        )
                    return "Pilot", GuildViewer(
                        int(identity.discord_id),
                        int(discord.config.guild_id),
                        True,
                        False,
                    )
                viewer = viewers[role]
                if bound_roster and str(viewer.user_id) != identity.discord_id:
                    raise SignInError(HTTPStatus.FORBIDDEN, "Activity roster access was denied.")
                return {
                    "invited": "Pilot" if bound_roster else "Invited pilot",
                    "other": "Pilot" if bound_roster else "Other pilot",
                    "handler": "Handler",
                }[role], viewer
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
            except CookieError:
                cookie = SimpleCookie()
            token = cookie.get(COOKIE)
            identity = sessions.get(token.value) if token else None
            if not identity:
                raise SignInError(HTTPStatus.UNAUTHORIZED, "Open a test pilot launch link.")
            return identity

        def campaign_context(self, query):
            keys = parse_qs(query, keep_blank_values=True).get("campaign", [DEFAULT_CAMPAIGN])
            if len(keys) != 1:
                raise SignInError(HTTPStatus.BAD_REQUEST, "Specify one campaign.")
            selected = keys[0]
            if not discord:
                if selected != DEFAULT_CAMPAIGN:
                    raise SignInError(HTTPStatus.FORBIDDEN, "Campaign unavailable.")
                return default
            identity = discord.resolve(self.headers.get("Authorization", ""))
            if selected == DEFAULT_CAMPAIGN and discord.campaign_roles_only:
                permitted = [item for item in bindings() if item.role_id in identity.role_ids]
                if len(permitted) != 1:
                    raise SignInError(
                        HTTPStatus.CONFLICT,
                        "Select a campaign before opening its records.",
                    )
                selected = permitted[0].id
            path = urlsplit(self.path).path
            scene_route = DIRECTOR_ROUTE.fullmatch(path)
            private_review = {
                "timeline",
                "activity-review",
                "handler-draft",
                "handler-need",
                "gm-work",
                "handler-native-work",
                "handler-hunt",
                "scene-initiative-review",
                "npc-owner-review",
                "scene-alternate-actors",
                "scene-alternate-handovers",
                "scene-alternate-choices",
                "scene-alternate-battles",
            }
            trial_access = (
                ai_trial
                and selected == UUID(ai_trial.campaign).hex
                and (
                    path in ("/api/activity/review-scenes", "/api/activity/ai-provider")
                    or (
                        scene_route and (self.command == "POST" or scene_route[2] in private_review)
                    )
                )
            )
            session_zero = (
                path.startswith(SESSION_ZERO_PATH)
                and owner_setup_grant is not None
                and selected == catalog.latest(owner_setup_grant[0])
            )
            if (
                trial_access
                or path
                in (
                    "/api/activity/ai-setup",
                    "/api/activity/ai-settings",
                    "/api/activity/ai-models",
                )
                or session_zero
                or FACILITATOR_ROUTE.fullmatch(path)
            ):
                identity = discord.resolve(self.headers.get("Authorization", ""), fresh=True)
            if selected == DEFAULT_CAMPAIGN:
                self.selected_session = self.session()
                if identity.role == "role_tester":
                    self.admit(default, self.selected_session[1], legacy=True)
                return default
            binding = next((item for item in bindings() if item.id == selected), None)
            if binding is None or binding.role_id not in identity.role_ids:
                raise SignInError(
                    HTTPStatus.FORBIDDEN,
                    "Your Discord role does not grant access to this campaign.",
                )
            runtime = managed_runtime(binding)
            viewer = GuildViewer(int(identity.discord_id), int(binding.guild_id), True, False)
            if runtime.resetting:
                raise SignInError(HTTPStatus.CONFLICT, "This campaign is being archived.")
            with runtime.work_lock:
                if runtime.retired:
                    raise SignInError(
                        HTTPStatus.GONE, "This campaign was archived. Reopen the Activity."
                    )
                if runtime.resetting:
                    raise SignInError(HTTPStatus.CONFLICT, "This campaign is being archived.")
                self.admit(runtime, viewer)
            self.selected_session = (
                "Handler" if viewer == runtime.setup.handler else "Pilot",
                viewer,
            )
            return runtime

        def may_preview_setup(self, campaign, viewer):
            return bot_setup_organizer(campaign) == viewer.user_id

        def start_fresh(self, campaign, viewer):
            if not self.may_preview_setup(campaign, viewer):
                raise SignInError(HTTPStatus.FORBIDDEN, "Only the campaign owner can start fresh.")
            key = self.headers.get("Idempotency-Key", "")
            data = self.read_object(1024, {"name", "confirmation"})
            if not KEY.fullmatch(key) or any(not isinstance(value, str) for value in data.values()):
                raise ValueError("Use the current campaign name and a new name.")
            campaign_id = UUID(campaign.service.store.campaign_id).hex
            binding = next((item for item in bindings() if item.id == campaign_id), None)
            if binding is None or data["confirmation"] != binding.name:
                raise ValueError("Type the exact current campaign name.")
            identity = discord.resolve(self.headers.get("Authorization", ""), force=True)
            if (
                identity.discord_id != str(viewer.user_id)
                or binding.role_id not in identity.role_ids
            ):
                raise SignInError(HTTPStatus.FORBIDDEN, "The campaign role is required.")
            job_id = uuid4().hex
            job = {
                "owner": identity.discord_id,
                "role": binding.role_id,
                "state": "pending",
                "expires": monotonic() + 600,
            }
            with reset_jobs_lock:
                for previous, report in tuple(reset_jobs.items()):
                    if report["state"] != "pending" and report["expires"] <= monotonic():
                        del reset_jobs[previous]
                reset_jobs[job_id] = job
            campaign.resetting = True

            def run():
                with campaign.work_lock:
                    try:
                        next_id = replace_campaign(
                            campaign, binding, identity.discord_id, data, key
                        )
                        outcome = {"state": "complete", "campaign_id": next_id}
                    except CampaignBindingError as error:
                        outcome = {"state": "failed", "error": str(error)}
                    except Exception:
                        discord_log.exception("Private campaign reset failed.")
                        outcome = {
                            "state": "failed",
                            "error": (
                                "Campaign reset could not complete. "
                                "Reopen the Activity to check the current campaign."
                            ),
                        }
                    finally:
                        campaign.resetting = False
                    with reset_jobs_lock:
                        job.update(outcome)

            try:
                Thread(target=run, daemon=True).start()
            except RuntimeError:
                campaign.resetting = False
                with reset_jobs_lock:
                    del reset_jobs[job_id]
                raise
            return {"job": job_id, "state": "pending"}

        def fresh_job(self, job_id):
            if not discord:
                raise SignInError(HTTPStatus.NOT_FOUND, "Campaign reset progress is unavailable.")
            identity = discord.resolve(self.headers.get("Authorization", ""))
            with reset_jobs_lock:
                job = reset_jobs.get(job_id)
                if (
                    job is None
                    or job["owner"] != identity.discord_id
                    or job["role"] not in identity.role_ids
                    or job["expires"] <= monotonic()
                ):
                    raise SignInError(
                        HTTPStatus.NOT_FOUND, "Campaign reset progress is unavailable."
                    )
                return {key: job[key] for key in ("state", "campaign_id", "error") if key in job}

        def session_zero_preview(self, campaign, viewer, adapter):
            game = campaign.setup.game
            with game.store.engine.connect() as connection:
                game.authorize(connection, viewer, game=False)
                zero = adapter.session_zero.service._latest(connection)
                return {
                    "owner_preview": True,
                    "group_configured": bool(zero.members),
                    "plan_status": (
                        "approved"
                        if zero.plan_approved
                        else "pending"
                        if zero.plan_proposal
                        else "not_filed"
                    ),
                    "facilitator_appointed": activity_facilitator(connection, game.store)
                    is not None,
                }

        def ai_setup(self, campaign, viewer):
            if not campaign.managed:
                raise SignInError(HTTPStatus.NOT_FOUND, "AI setup requires a managed campaign.")
            game = campaign.setup.game
            campaign_id = game.store.campaign_id
            configured = ai_trial is not None and campaign.reviewed_director is not None
            with game.store.engine.connect() as connection:
                game.authorize(connection, viewer, game=False)
                facilitator = activity_facilitator(
                    connection, game.store, ai_trial.facilitator if configured else None
                )
                model_selection = ai_trial.model_selection(connection) if configured else None
                if viewer.user_id != (facilitator or campaign.setup.handler.user_id):
                    if bot_setup_organizer(campaign) is not None:
                        desk, _ = campaign_opening(campaign, "session-zero")
                        zero = desk.session_zero.service._latest(connection)
                        if desk.session_zero.service._organizes_bot_setup(connection, viewer, zero):
                            preview = {
                                "campaign_id": campaign_id,
                                "setup_preview": True,
                                "configured": configured,
                            }
                            if model_selection is not None:
                                preview["handler_model"] = model_selection["models"]["handler"]
                                observer = campaign.reviewed_director.session.observer
                                preview["ai_on"] = (
                                    facilitator is not None
                                    and observer._activity_policy(connection)["enabled"]
                                )
                            return preview
                    raise WorkflowError("AI setup is private to the campaign facilitator.")
            policy = (
                campaign.reviewed_director.read(viewer, "", "activity-policy")
                if configured and facilitator is not None
                else None
            )
            return {
                "campaign_id": campaign_id,
                "configured": configured,
                "policy": policy,
                "provider": ai_trial.status() if policy is not None else None,
                "model_selection": model_selection if policy is not None else None,
            }

        def ai_provider(self, campaign, viewer):
            if ai_trial is None or campaign.reviewed_director is None:
                raise SignInError(HTTPStatus.NOT_FOUND, "AI provider controls are unavailable.")
            try:
                campaign.reviewed_director.authorize_provider(viewer)
            except WorkflowError:
                raise SignInError(
                    HTTPStatus.FORBIDDEN, "AI provider controls are private to the facilitator."
                ) from None
            return ai_trial

        def admit(self, runtime, viewer, *, legacy=False):
            store = runtime.service.store
            with runtime.enrollment_lock:
                with store.engine.connect() as connection:
                    member = connection.scalar(
                        sa.select(tables.members.c.active).where(
                            tables.members.c.campaign_id == store.campaign_id,
                            tables.members.c.user_id == str(viewer.user_id),
                        )
                    )
                if member is False:
                    raise SignInError(HTTPStatus.FORBIDDEN, "Campaign membership is inactive.")
                if member:
                    return
                if legacy:
                    runtime.setup.join_tester(viewer)
                else:
                    store.join(viewer, f"activity-role-admission:{viewer.user_id}")

        def list_campaigns(self, query):
            identity = discord.resolve(self.headers.get("Authorization", ""))
            channel = parse_qs(query).get("channel", [None])[0]
            permitted = [item for item in bindings() if item.role_id in identity.role_ids]
            preferred = next(
                (item.id for item in permitted if channel and item.channel_id == channel),
                None,
            )
            available = [{"id": item.id, "name": item.name} for item in permitted]
            if discord.can_use_default(identity):
                available.insert(0, {"id": DEFAULT_CAMPAIGN, "name": "The Long Winter"})
            self.send_json(
                HTTPStatus.OK,
                {
                    "campaigns": available,
                    "discord_user_id": identity.discord_id,
                    "preferred": preferred,
                },
            )

        def read_object(self, limit: int, keys: set[str] | None = None) -> dict:
            size = int(self.headers.get("Content-Length", "0"))
            if self.headers.get_content_type() != "application/json" or not 0 < size <= limit:
                raise ValueError
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict) or (keys is not None and value.keys() != keys):
                raise ValueError
            return value

        def sign_in(self, path: str) -> None:
            if discord is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            try:
                if path == "/api/discord/challenge":
                    self.send_json(HTTPStatus.OK, {"nonce": discord.challenge()})
                    return
                request = self.read_object(2048, {"code", "nonce", "guild_id"})
                guild_id = request["guild_id"]
                if any(
                    not isinstance(request[key], str) or not request[key]
                    for key in ("code", "nonce")
                ) or (
                    guild_id is not None
                    and (
                        not isinstance(guild_id, str) or not re.fullmatch(r"[0-9]{17,20}", guild_id)
                    )
                ):
                    raise ValueError
                self.send_json(HTTPStatus.OK, discord.exchange(**request))
            except ValueError:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Invalid Discord sign-in request."},
                )
            except SignInError as error:
                self.send_access_error(error)
            except WorkflowError as error:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})

        def send_access_error(self, error):
            reauthenticate = discord is not None and error.status in (
                HTTPStatus.UNAUTHORIZED,
                HTTPStatus.FORBIDDEN,
            )
            payload = {"error": str(error)}
            if reauthenticate:
                payload["reauthenticate"] = True
            if error.retry_after is None:
                self.send_json(error.status, payload)
            else:
                self.send_payload(
                    error.status,
                    json.dumps(payload).encode("utf-8"),
                    Retry_After=str(error.retry_after),
                )

        def do_GET(self):
            self.selected_session = None
            if not discord and self.headers.get("Host") != self.server.origin_host:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid local host."})
                return
            request = urlsplit(self.path)
            path = request.path
            campaign = default
            try:
                if match := FRESH_JOB_ROUTE.fullmatch(path):
                    self.send_json(HTTPStatus.OK, self.fresh_job(match[1]))
                    return
                if path == "/api/campaigns" and catalog:
                    self.list_campaigns(request.query)
                    return
                if path.startswith("/api/") and path != "/api/activity/config":
                    campaign = self.campaign_context(request.query)
            except SignInError as error:
                self.send_access_error(error)
                return
            except WorkflowError as error:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                return
            protected = (
                campaign.managed and path.startswith("/api/") and path != "/api/activity/config"
            )
            with campaign.work_lock if protected else nullcontext():
                if protected and campaign.retired:
                    self.send_json(
                        HTTPStatus.GONE,
                        {"error": "This campaign was archived. Reopen the Activity."},
                    )
                    return
                self.get_activity(request, campaign)

        def get_activity(self, request, campaign):
            path = request.path
            service, setup, battlefield = (
                campaign.service,
                campaign.setup,
                campaign.battlefield,
            )
            handler = setup.handler
            if not discord and path.startswith("/launch/"):
                identity = participants.get(path.removeprefix("/launch/"))
                if identity:
                    token = secrets.token_urlsafe(32)
                    sessions[token] = identity
                    self.send_payload(
                        HTTPStatus.SEE_OTHER,
                        b"",
                        Location="/activity",
                        Set_Cookie=f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict",
                    )
                    return
            if path in ("/", "/activity"):
                self.send_payload(
                    HTTPStatus.OK,
                    assets["index.html"],
                    "text/html; charset=utf-8",
                )
            elif path == "/api/activity/config":
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "client_id": discord.config.client_id if discord else None,
                        "allow_dm": discord.config.allow_dm if discord else False,
                        "battlefield": battlefield is not None,
                        "bound_roster": bound_roster,
                        "director_scene": director_scene,
                        "activity_shadow": p2_shadow_readiness,
                        "reviewed_ai_trial": ai_trial is not None,
                        "campaign_setup": catalog is not None,
                        "campaign_switcher": catalog is not None,
                        "director_trial": director is not None
                        or bool(discord and discord.campaign_roles_only),
                        "tester_role_gate": bool(
                            discord
                            and not discord.campaign_roles_only
                            and discord.config.tester_role_ids
                        ),
                        "campaign_role_gate": bool(discord and discord.campaign_roles_only),
                    },
                )
            elif path == "/api/director-trial" and (director or campaign.training):
                try:
                    _, viewer = self.session()
                    self.send_json(HTTPStatus.OK, (director or campaign.training).view(viewer))
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
            elif path == "/api/dm-receipts" or (match := DM_RECEIPT_ROUTE.fullmatch(path)):
                try:
                    _, viewer = self.session()
                    if path == "/api/dm-receipts":
                        receipts = (
                            inbox_notices.recent_receipts(service.store.campaign_id, viewer.user_id)
                            if inbox_notices
                            else []
                        )
                        self.send_json(HTTPStatus.OK, {"receipts": receipts})
                        return
                    receipt = self.read_dm_receipt(campaign, viewer, match[1])
                except SignInError as error:
                    self.send_access_error(error)
                    return
                except (WorkflowError, sa.exc.SQLAlchemyError, sqlite3.Error, OSError):
                    self.send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "DM status is temporarily unavailable."},
                    )
                    return
                if receipt is None:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "DM receipt unavailable."})
                else:
                    self.send_json(HTTPStatus.OK, receipt)
            elif campaign.managed and (match := FACILITATOR_ROUTE.fullmatch(path)):
                try:
                    _, viewer = self.session()
                    reviews = FacilitatorService(setup.game)
                    if match[1] is not None:
                        result = reviews.view(viewer, str(UUID(match[1])))
                    elif room := parse_qs(request.query).get("room", [None])[0]:
                        room_plays = setup.room_plays(viewer, room)
                        result = reviews.candidates(viewer, room_plays.channel)
                        result["unlisted_rule"] = UNLISTED_ACTION
                    else:
                        result = {"reviews": reviews.tasks(viewer, include_closed=True)}
                    self.send_json(HTTPStatus.OK, result)
                except (TypeError, ValueError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid review or scene."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            elif (
                campaign.managed
                and (match := SETUP_ROUTE.fullmatch(path))
                and match[1] in SETUP_READ
            ):
                try:
                    _, viewer = self.session()
                    adapter, scene = campaign_opening(campaign, match[1])
                    try:
                        record = adapter.read(viewer, scene, match[1], match[2])
                    except WorkflowError:
                        if path != SESSION_ZERO_PATH or not self.may_preview_setup(
                            campaign, viewer
                        ):
                            raise
                        record = self.session_zero_preview(campaign, viewer, adapter)
                    if match[1] == "session-zero" and record.get("bot_managed"):
                        visible = set(record["members"]) | set(record.get("group_options", ()))
                        record["member_names"] = {
                            person["id"]: person["name"]
                            for person in setup.campaign_members(viewer)
                            if person["id"] in visible
                        }
                        if first := record.get("first_briefing"):
                            first["paired_ai_ready"] = paired_ai_ready(campaign)
                            first["ai_on"] = bool(
                                campaign.reviewed_director
                                and campaign.reviewed_director.ai_enabled()
                            )
                    self.send_json(HTTPStatus.OK, record)
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                except ValueError:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown setup view."})
            elif path == START_FRESH_PATH:
                _, viewer = self.session()
                if not self.may_preview_setup(campaign, viewer):
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": "Campaign reset is owner-only."})
                else:
                    identity = UUID(campaign.service.store.campaign_id).hex
                    name = next(item.name for item in bindings() if item.id == identity)
                    self.send_json(HTTPStatus.OK, {"current_name": name})
            elif path == "/api/activity/ai-setup":
                try:
                    _, viewer = self.session()
                    self.send_json(HTTPStatus.OK, self.ai_setup(campaign, viewer))
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": "AI setup is unavailable."})
            elif path == "/api/activity/ai-provider":
                try:
                    _, viewer = self.session()
                    self.send_json(HTTPStatus.OK, self.ai_provider(campaign, viewer).status())
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError:
                    self.send_json(
                        HTTPStatus.FORBIDDEN, {"error": "AI provider controls are unavailable."}
                    )
            elif path == "/api/activity/review-scenes":
                try:
                    _, viewer = self.session()
                    adapter = campaign.reviewed_director
                    self.send_json(
                        HTTPStatus.OK, adapter.trial_scenes(viewer) if adapter else {"scenes": []}
                    )
                except (SignInError, WorkflowError):
                    self.send_json(
                        HTTPStatus.FORBIDDEN, {"error": "Scene discovery is unavailable."}
                    )
            elif (
                adapter := campaign.reviewed_director
                or (fixture_director if campaign is default else None)
            ) and (match := DIRECTOR_ROUTE.fullmatch(path)):
                try:
                    _, viewer = self.session()
                    value = adapter.read(viewer, match[1], match[2], match[3])
                    self.send_json(HTTPStatus.OK, value)
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                except ValueError:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown scene view."})
            elif path == "/api/presence":
                try:
                    _, viewer = self.session()
                    from girlframe.services.m2_state import load_state

                    with setup.store.engine.connect() as connection:
                        setup.game.authorize(connection, viewer, game=False)
                        state = load_state(connection, setup.store.campaign_id)
                    people = setup.campaign_members(viewer) if bound_roster else []
                    contacts = (
                        setup.communication_view(viewer, state, members=people)
                        if bound_roster or viewer == handler or str(viewer.user_id) in state.sheets
                        else None
                    )
                    now = monotonic()
                    with campaign.presence_lock:
                        for identity, seen in list(campaign.presence.items()):
                            if now - seen >= PRESENCE_SECONDS:
                                del campaign.presence[identity]
                        campaign.presence[str(viewer.user_id)] = now
                        online = set(campaign.presence)
                    self.send_json(
                        HTTPStatus.OK,
                        {
                            "mailbox": f"{service.store.campaign_id}:{viewer.user_id}",
                            "communications": contacts,
                            "members": [
                                person | {"online": person["id"] in online} for person in people
                            ],
                        },
                    )
                except SignInError as error:
                    self.send_access_error(error)
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            elif path.removeprefix("/") in assets and path != "/index.html":
                version = parse_qs(request.query).get("v")
                if version and version != [asset_version]:
                    self.send_json(
                        HTTPStatus.GONE,
                        {"error": "Reload the Activity to use the current files."},
                    )
                else:
                    self.send_payload(
                        HTTPStatus.OK,
                        assets[path.removeprefix("/")],
                        {
                            ".css": "text/css; charset=utf-8",
                            ".json": "application/json; charset=utf-8",
                        }.get(Path(path).suffix, "text/javascript; charset=utf-8"),
                    )
            elif path.startswith("/api/artwork/"):
                try:
                    _, viewer = self.session()
                    if viewer == handler and not bound_roster:
                        raise SignInError(
                            HTTPStatus.FORBIDDEN,
                            "This account uses Communications only.",
                        )
                    art_id = path.removeprefix("/api/artwork/")
                    if art_id == "catalog":
                        self.send_json(HTTPStatus.OK, CATALOG)
                    elif art_id in ARTWORK:
                        self.send_payload(HTTPStatus.OK, artwork_bytes(art_id), "image/webp")
                    else:
                        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Artwork unavailable."})
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
            elif path == "/api/player-setup":
                try:
                    _, viewer = self.session()
                    query = parse_qs(request.query, keep_blank_values=True)
                    pilot_mode = (
                        bound_roster and viewer == handler and query.get("perspective") == ["pilot"]
                    )
                    scene = query.get("scene")
                    if scene is not None and (
                        len(scene) != 1 or not re.fullmatch(r"relay|[0-9a-f]{16}", scene[0])
                    ):
                        raise SignInError(HTTPStatus.BAD_REQUEST, "Select one scene.")
                    record = setup.view(
                        viewer, pilot_mode=pilot_mode, scene_id=scene[0] if scene else None
                    )
                    if record["stage"] == "active" and setup.records:
                        joined = [
                            room["id"]
                            for room in record["directory"]["rooms"]
                            if room["joined"] and room.get("archived_at") is None
                        ]
                        record["handover_dialogue"] = setup.records.handover_dialogue(
                            viewer, joined, relay_joined="relay" in joined
                        )
                    if bound_roster:
                        record["bot_enrollment"] = setup.bot_enrollment.view(viewer)
                    if bound_roster and "communications" not in record:
                        with setup.store.engine.connect() as connection:
                            from girlframe.services.m2_state import load_state

                            state = load_state(connection, setup.store.campaign_id)
                        record["communications"] = setup.communication_view(viewer, state)
                    self.send_json(
                        HTTPStatus.OK,
                        record
                        | {
                            "mailbox": f"{setup.store.campaign_id}:{viewer.user_id}",
                            "handler_account": bound_roster and viewer == handler,
                            "perspective": "pilot"
                            if pilot_mode
                            else "handler"
                            if viewer == handler
                            else "pilot",
                            "handler_pilot_notice": (
                                "The current engine excludes the Handler account from Pilot "
                                "activation and Status ranks. You can prepare your own draft here; "
                                "playing it requires native dual-role support."
                            )
                            if pilot_mode and record["stage"] != "active"
                            else None,
                        },
                    )
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
            elif path == "/api/battlefield" and battlefield:
                try:
                    _, viewer = self.session()
                    native = isinstance(battlefield, PrivateBattlefield)
                    if not native and viewer == handler:
                        raise SignInError(
                            HTTPStatus.FORBIDDEN,
                            "This account uses Communications only.",
                        )
                    self.send_json(
                        HTTPStatus.OK,
                        battlefield.view(
                            DRILL_OPPONENT if not native and viewer == OTHER else viewer
                        ),
                    )
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except BattlefieldChanged as error:
                    self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
            elif match := TRANSCRIPT_ROUTE.fullmatch(path):
                try:
                    _, viewer = self.session()
                    if director_room(match[1]):
                        timeline = fixture_director.timeline(viewer, director_scene)
                        transcript = (
                            setup.transcript(viewer, match[1])
                            if timeline["open"]
                            else {"receipts": setup.scene_plays.receipts(viewer, {"900": match[1]})}
                        )
                        with service.store.engine.connect() as connection:
                            from girlframe.services.m2_state import load_state

                            state = load_state(connection, service.store.campaign_id)
                        transcript["entries"] = []
                        for entry in timeline["entries"]:
                            actor = entry["actor"]
                            sheet = state.sheets.get(actor["entity"])
                            names = (
                                {npc.id: npc.name for npc in state.world.npcs}
                                if state.world
                                else {}
                            )
                            label = (
                                "GM"
                                if actor["kind"] == "gm"
                                else "Handler"
                                if actor["kind"] == "handler"
                                else names.get(actor["entity"], "NPC")
                                if actor["kind"] == "npc"
                                else (
                                    sheet.callsign
                                    if sheet and sheet.character_id == actor["incarnation"]
                                    else "Pilot"
                                )
                            )
                            transcript["entries"].append(
                                {
                                    "id": entry["sequence"] * 1000 + entry["ordinal"],
                                    "callsign": label,
                                    "body": entry["text"],
                                    "created": entry["created"],
                                    "action": entry.get("action"),
                                }
                            )
                        transcript["director"] = {
                            "scene": director_scene,
                            "revision": timeline["revision"],
                            "open": timeline["open"],
                        }
                    else:
                        transcript = setup.transcript(viewer, match[1])
                    self.send_json(HTTPStatus.OK, transcript)
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            elif match := COMMUNICATION_ROUTE.fullmatch(path):
                try:
                    _, viewer = self.session()
                    self.send_json(HTTPStatus.OK, setup.communication(viewer, match[1]))
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            elif path == "/api/mission-offers":
                try:
                    label, viewer = self.session()
                    self.send_json(
                        HTTPStatus.OK,
                        MissionDesk(service).view(viewer, label, lifecycle=bound_roster),
                    )
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

        def do_POST(self):
            self.selected_session = None
            expected_origin = discord.config.origin if discord else self.server.origin
            origin = self.headers.get("Origin")
            approved = origin == expected_origin or (
                rehearsal_origin is not None and origin == rehearsal_origin
            )
            if (
                not discord and self.headers.get("Host") != self.server.origin_host
            ) or not approved:
                self.send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "Only the configured Activity origin may submit changes."},
                )
                return
            request_path = urlsplit(self.path)
            path = request_path.path
            if path in ("/api/discord/challenge", "/api/discord/session"):
                self.sign_in(path)
                return
            try:
                campaign = self.campaign_context(request_path.query)
                session = self.session()
            except SignInError as error:
                self.send_access_error(error)
                return
            except WorkflowError as error:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                return
            with campaign.work_lock if campaign.managed else nullcontext():
                if campaign.retired:
                    self.send_json(
                        HTTPStatus.GONE,
                        {"error": "This campaign was archived. Reopen the Activity."},
                    )
                    return
                self.post_activity(request_path, campaign, session)

        def post_activity(self, request_path, campaign, session):
            path = request_path.path
            service, setup, battlefield = (
                campaign.service,
                campaign.setup,
                campaign.battlefield,
            )
            handler = setup.handler
            if path == START_FRESH_PATH:
                try:
                    self.send_json(HTTPStatus.ACCEPTED, self.start_fresh(campaign, session[1]))
                except SignInError as error:
                    self.send_access_error(error)
                except CampaignBindingError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                except (TypeError, ValueError) as error:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                except (
                    OSError,
                    RuntimeError,
                    WorkflowError,
                    sqlite3.Error,
                    sa.exc.SQLAlchemyError,
                ):
                    self.send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {
                            "error": (
                                "Campaign reset could not complete. "
                                "Reopen the Activity to check the current campaign."
                            )
                        },
                    )
                return
            if path == "/api/director-trial" and (director or campaign.training):
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    data = self.read_object(32768)
                    self.send_json(
                        HTTPStatus.OK,
                        (director or campaign.training).perform(session[1], key, data),
                    )
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Review the trial form and its required fields."},
                    )
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if campaign.managed and (match := FACILITATOR_ROUTE.fullmatch(path)):
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    viewer = session[1]
                    reviews = FacilitatorService(setup.game)
                    if match[1] is None:
                        data = self.read_object(
                            8192, {"room", "source", "rule", "revision", "reason"}
                        )
                        if (
                            type(data["revision"]) is not int
                            or any(
                                not isinstance(data[field], str)
                                for field in ("room", "source", "rule", "reason")
                            )
                            or not 1 <= len(data["reason"].strip()) <= 1200
                        ):
                            raise ValueError
                        room_plays = setup.room_plays(viewer, data["room"])
                        kind, _, source = data["source"].partition(":")
                        result = reviews.request(
                            viewer,
                            key,
                            room_plays.channel,
                            kind,
                            source,
                            data["rule"],
                            data["revision"],
                            data["reason"].strip(),
                            shared=True,
                        )
                    else:
                        data = self.read_object(
                            8192, {"revision", "game_revision", "operation", "text", "adapter"}
                        )
                        if (
                            any(
                                type(data[field]) is not int
                                for field in ("revision", "game_revision")
                            )
                            or any(
                                not isinstance(data[field], str)
                                for field in ("operation", "text", "adapter")
                            )
                            or len(data["text"]) > 1200
                        ):
                            raise ValueError
                        result = reviews.change(
                            viewer,
                            key,
                            str(UUID(match[1])),
                            data["revision"],
                            data["game_revision"],
                            data["operation"],
                            data["text"],
                            adapter=data["adapter"],
                        )
                    self.send_json(HTTPStatus.OK, result)
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Use the current facilitator review form."},
                    )
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if (
                campaign.managed
                and (match := SETUP_ROUTE.fullmatch(path))
                and (match[1] in SETUP_WRITE or match[1].startswith("time-"))
                and match[2] is None
            ):
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    data = self.read_object(96_000 if match[1] == "opening-save" else 16384)
                    if (
                        match[1] == "session-zero-briefing-offer"
                        and data.get("enable_ai") is True
                        and not paired_ai_ready(campaign)
                    ):
                        raise WorkflowError(
                            "Configure both the Handler and Director models before enabling them."
                        )
                    adapter, scene = campaign_opening(campaign, match[1])
                    self.send_json(
                        HTTPStatus.OK, adapter.write(session[1], key, scene, match[1], data)
                    )
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid setup command."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if path in ("/api/activity/ai-settings", "/api/activity/ai-models"):
                try:
                    provider = self.ai_provider(campaign, session[1])
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    if path == "/api/activity/ai-models":
                        data = self.read_object(1024, {"models", "revision"})
                        provider.save_models(campaign.reviewed_director, session[1], key, data)
                        campaign.reviewed_director = provider.adapter(
                            setup.game,
                            opening_channel=SCENE,
                            setup=setup,
                            battlefield=campaign.battlefield,
                        )
                    else:
                        data = self.read_object(1024, {"enabled", "revision"})
                        if (
                            type(data["enabled"]) is not bool
                            or type(data["revision"]) is not int
                            or data["revision"] < 0
                        ):
                            raise ValueError
                        campaign.reviewed_director.write(
                            session[1], key, "", "activity-policy-save", data
                        )
                    self.send_json(HTTPStatus.OK, self.ai_setup(campaign, session[1]))
                except SignInError as error:
                    self.send_access_error(error)
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Use the saved revision and valid model IDs."},
                    )
                return
            if path == "/api/activity/ai-provider":
                try:
                    provider = self.ai_provider(campaign, session[1])
                    key = self.headers.get("Idempotency-Key", "")
                    data = self.read_object(1024, {"role"})
                    if not KEY.fullmatch(key) or not isinstance(data["role"], str):
                        raise ValueError
                    if not campaign.reviewed_director.ai_enabled():
                        self.send_json(
                            HTTPStatus.CONFLICT,
                            {"error": "Enable AI assistance before checking the connection."},
                        )
                        return
                    outcome = provider.check(data["role"], key)
                    self.send_json(HTTPStatus.OK, {"result": outcome, **provider.status()})
                except SignInError as error:
                    self.send_json(error.status, {"error": str(error)})
                except WorkflowError:
                    self.send_json(
                        HTTPStatus.FORBIDDEN, {"error": "AI provider controls are unavailable."}
                    )
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Select an enabled role and a new check key."},
                    )
                return
            adapter = campaign.reviewed_director or (
                fixture_director if campaign is default else None
            )
            if (match := DIRECTOR_ROUTE.fullmatch(path)) and match[3] is None:
                if adapter is None:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Scene work is unavailable."})
                    return
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    data = self.read_object(96_000 if match[2] == "opening-save" else 16384)
                    value = adapter.write(session[1], key, match[1], match[2], data)
                    self.send_json(HTTPStatus.OK, value)
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid scene command."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if match := COMMUNICATION_ROUTE.fullmatch(path):
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    request = self.read_object(8192, {"text"})
                    receipt = setup.communication(
                        session[1], match[1], message=(key, request["text"])
                    )
                    self.send_json(HTTPStatus.OK, receipt)
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid message."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if path == "/api/mission-desk" and bound_roster:
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    data = self.read_object(16384)
                    receipt = MissionDesk(service).perform(session[1], key, data)
                    if data.get("action") == "offer":
                        receipt = self.queue_notice("mission", service, session[1], receipt)
                    self.send_json(HTTPStatus.OK, receipt)
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid mission fields."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            handler_steps = {"/api/player-setup/off-duty-followup"}
            handler_steps.add("/api/player-setup/scene-cancel")
            if director:
                handler_steps.update(
                    ("/api/player-setup/keep-choice", "/api/player-setup/scene-choice")
                )
            if bound_roster:
                handler_steps.update(
                    (
                        "/api/player-setup/scene-beneath-work",
                        "/api/player-setup/scene-specialist",
                        "/api/player-setup/scene-orders",
                        "/api/player-setup/career-status",
                        "/api/player-setup/creation-choice",
                    )
                )
            if bound_roster:
                handler_steps.update(
                    ("/api/player-setup/keep-choice", "/api/player-setup/scene-choice")
                )
                handler_plays = {"/api/player-setup/" + step for step in HANDLER_PLAY_STEPS}
                if path in handler_plays and session[1] != handler:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "This operation is reserved for the Handler."},
                    )
                    return
                handler_steps.update(handler_plays | {"/api/player-setup/handler-punishment"})
            battle = BATTLEFIELD_ROUTE.fullmatch(path) if battlefield else None
            native = isinstance(battlefield, PrivateBattlefield)
            if (
                session[1] == handler
                and not (
                    bound_roster and parse_qs(request_path.query).get("perspective") == ["pilot"]
                )
                and path not in handler_steps
                and not (native and battle)
            ):
                self.send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "This operation is reserved for pilots."},
                )
                return
            if battle:
                try:
                    command_key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(command_key):
                        raise ValueError
                    value = battlefield.perform(
                        DRILL_OPPONENT if not native and session[1] == OTHER else session[1],
                        command_key,
                        battle[1],
                        self.read_object(8192),
                    )
                    self.send_json(HTTPStatus.OK, value)
                except (TypeError, ValueError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid battlefield fields."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            if path.startswith("/api/player-setup/"):
                try:
                    key = self.headers.get("Idempotency-Key", "")
                    if not KEY.fullmatch(key):
                        raise ValueError
                    step = path.rsplit("/", 1)[1]
                    data = self.read_object(
                        32768
                        if step
                        in (
                            "build",
                            "off-duty-followup",
                            "handler-punishment",
                            "scene-beneath-work",
                            "scene-specialist",
                        )
                        else 8192
                    )
                    lock = (
                        campaign.enrollment_lock
                        if bound_roster
                        and step
                        in (
                            "profile",
                            "build",
                            "review",
                            "select-bond",
                            "bond-decision",
                            "bot-enrollment",
                            "activate",
                            "creation-choice",
                            "purge-sheet",
                            "career-status",
                            "share-intel",
                        )
                        else battlefield.commands
                        if native and step == "enter-scene"
                        else nullcontext()
                    )
                    with lock:
                        if bound_roster and step in ("review", "activate"):
                            setup.bot_enrollment.reconcile(owner=session[1].user_id)
                        if step == "room-post" and director_room(data.get("target")):
                            if data.keys() != {
                                "target",
                                "text",
                                "fictional_channel",
                                "scene_revision",
                            }:
                                raise ValueError
                            receipt = fixture_director.write(
                                session[1],
                                key,
                                director_scene,
                                "input",
                                {
                                    "expected_scene_revision": data["scene_revision"],
                                    "speaker": "pilot",
                                    "text": data["text"],
                                    "fictional_channel": data["fictional_channel"],
                                },
                            )
                        else:
                            receipt = setup.perform(session[1], key, step, data)
                        if bound_roster and step in (
                            "profile",
                            "build",
                            "creation-choice",
                            "select-bond",
                            "bond-decision",
                        ):
                            setup.bot_enrollment.reconcile(owner=session[1].user_id)
                    if step in ("bond", "scene-invite"):
                        receipt = self.queue_notice(
                            step.replace("-", "_"), setup, session[1], receipt
                        )
                    if step == "room-create" and receipt.get("invitations"):
                        receipt["invitations"] = [
                            self.queue_notice("scene_invite", setup, session[1], invite)
                            for invite in receipt["invitations"]
                        ]
                    self.send_json(HTTPStatus.OK, receipt)
                except EnrollmentInputError as error:
                    self.send_json(
                        HTTPStatus.CONFLICT if error.conflict else HTTPStatus.BAD_REQUEST,
                        {"error": str(error), "fields": error.fields},
                    )
                except (TypeError, ValueError, UnicodeError):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid setup fields."})
                except WorkflowError as error:
                    self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
                return
            match = MISSION_ROUTE.fullmatch(path)
            if not match:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            try:
                identity = str(UUID(match[1]))
                key = self.headers.get("Idempotency-Key", "")
                if not KEY.fullmatch(key):
                    raise ValueError
                request = self.read_object(512, {"expected_revision", "response"})
                revision, response = request["expected_revision"], request["response"]
                if (
                    type(revision) is not int
                    or revision < 1
                    or response not in ("accept", "decline")
                ):
                    raise ValueError
            except (ValueError, UnicodeError):
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid mission response."})
                return

            try:
                receipt = service.respond(session[1], key, identity, revision, response)
            except WorkflowError as error:
                reason = str(error)
                if "visible only" in reason or reason == "Unknown mission.":
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Mission offer unavailable."})
                else:
                    self.send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "Response rejected. Refresh the offer."},
                    )
                return
            self.send_json(HTTPStatus.OK, {**receipt, "response": response})

    with ActivityHTTPServer(("127.0.0.1", port), Handler) as server:
        server.origin_host = f"127.0.0.1:{server.server_port}"
        server.origin = f"http://{server.origin_host}"
        lab_metadata = {"director_scene": director_scene} if fixture_director else {}
        print(
            json.dumps(
                {
                    **lab_metadata,
                    "origin": server.origin,
                    "pilots": {}
                    if discord
                    else {
                        label: f"{server.origin}/launch/{key}"
                        for key, (label, _) in participants.items()
                    },
                    "discord_activity_origin": discord.config.origin if discord else None,
                }
            ),
            flush=True,
        )
        if stop_on_input_close:

            def stop_after_eof():
                sys.stdin.buffer.read()
                server.shutdown()

            Thread(target=stop_after_eof, daemon=True).start()
        if setup.scene_plays:
            default.worker = setup.scene_plays.start_worker(
                work_lock=default.work_lock if default.managed else None
            )
            workers.append(default.worker)
        if battlefield and not isinstance(battlefield, PrivateBattlefield):
            workers.append(battlefield.start_worker())
        commands = nullcontext()
        if campaign_bot_token:
            from campaign_bot import serve_commands

            commands = serve_commands(
                discord.config,
                catalog,
                campaign_bot_token,
                provision_managed_campaign,
                inbox_notices=inbox_notices,
                notice_pending=notice_pending,
                scan_interactions=scan_interactions,
            )
        try:
            with commands:
                server.serve_forever()
        finally:
            with runtime_lock:
                shutting_down = True
            for stopped, _ in workers:
                stopped.set()
            for _, thread in workers:
                thread.join(timeout=5)
            if diagnostics:
                discord_log.removeHandler(diagnostics)
                diagnostics.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign")
    parser.add_argument("--discord", action="store_true")
    parser.add_argument("--allow-dm", action="store_true")
    parser.add_argument("--bound-roster", action="store_true")
    parser.add_argument("--inbox-dms", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--p2-trial", metavar="NAME")
    parser.add_argument("--rehearsal-origin", metavar="HTTPS_ORIGIN")
    parser.add_argument("--fork-discord-rehearsal", action="store_true")
    parser.add_argument("--stop-on-input-close", action="store_true")
    parser.add_argument("--p2-fixture", action="store_true")
    parser.add_argument("--p2-shadow-readiness", action="store_true")
    args = parser.parse_args()
    if args.fork_discord_rehearsal and (args.p2_trial != "rehearsal" or not args.discord):
        parser.error("--fork-discord-rehearsal requires --p2-trial rehearsal and --discord.")
    if args.rehearsal_origin is not None and (args.p2_trial is None or not args.discord):
        parser.error("--rehearsal-origin requires --p2-trial and --discord.")
    if args.p2_trial is not None:
        if args.bound_roster or args.audit or args.campaign or (args.allow_dm and not args.discord):
            parser.error("--p2-trial cannot use an ordinary campaign or managed bindings.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", args.p2_trial):
            parser.error("Use a lowercase trial name with letters, numbers and hyphens.")
        sys.path.insert(0, str(ENGINE / "tools"))
        from director_trial import fork_discord_rehearsal, open_trial

        try:
            config = (
                DiscordConfig.load(os.environ, allow_dm=args.allow_dm) if args.discord else None
            )
            trial_name = args.p2_trial
            if args.fork_discord_rehearsal:
                trial_name = fork_discord_rehearsal(RUNTIME / "p2-discord-trials", config)
            director = open_trial(
                ENGINE, RUNTIME / "p2-activity-trials", trial_name, discord_config=config
            )
        except (ValueError, WorkflowError, OSError) as error:
            parser.error(str(error))
        serve(
            MissionService(director.session.store),
            args.port,
            args.stop_on_input_close,
            DiscordSessions(config) if config else None,
            director=director,
            rehearsal_origin=args.rehearsal_origin,
        )
        raise SystemExit
    if args.p2_fixture and (args.discord or args.audit):
        parser.error("--p2-fixture only serves a local synthetic lab.")
    if args.allow_dm and not args.discord:
        parser.error("--allow-dm requires --discord.")
    if args.bound_roster and (not args.discord or args.audit):
        parser.error("--bound-roster requires a Discord serving command.")
    campaign = args.campaign or ("discord-private" if args.discord else "mission-offer")
    discord = None
    if args.discord:
        if not campaign.startswith("discord-"):
            parser.error("Discord tests require a separate campaign name beginning with discord-.")
        if not args.audit:
            try:
                discord = DiscordSessions(
                    DiscordConfig.load(
                        os.environ,
                        allow_dm=args.allow_dm,
                        campaign_roles_only=args.bound_roster,
                    )
                )
            except ValueError as error:
                parser.error(str(error))
    campaign_registry = None
    registered = []
    if args.bound_roster:
        campaign_registry = CampaignRegistry(RUNTIME / "activity-campaigns.sqlite3")
        registered = campaign_registry.bindings(discord.config.client_id, discord.config.guild_id)
        if not registered:
            parser.error(
                "Use the bot's /activity-campaign create command "
                "to bind this campaign to a Discord role."
            )
    service = (
        open_managed_campaign(registered[0], initialize=False)
        if registered
        else open_campaign(campaign, roster=discord.config if args.bound_roster else None)
    )
    if args.audit:
        print(json.dumps(audit(service)))
    else:
        serve(
            service,
            args.port,
            args.stop_on_input_close,
            discord,
            bound_roster=args.bound_roster,
            campaign_roles_only=args.bound_roster,
            campaign_registry=campaign_registry,
            inbox_dms=args.inbox_dms,
            p2_fixture=args.p2_fixture,
            p2_shadow_readiness=args.p2_shadow_readiness,
            campaign_bot_token=os.environ.pop("GIRLFRAME_ACTIVITY_SETUP_BOT_TOKEN", None)
            if args.bound_roster
            else None,
        )
