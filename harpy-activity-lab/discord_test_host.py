"""Offline Discord-protocol stand-in for the end-to-end Activity verifier."""

import argparse
import json
import re
from dataclasses import replace
from hashlib import sha256
from http import HTTPStatus
from uuid import uuid4

import sqlalchemy as sa

import mission_lab
from campaign_registry import CampaignRegistry
from discord_session import DiscordConfig, DiscordSessions, SignInError
from mission_lab import HANDLER, OFFERED, open_campaign, serve

CONFIG = DiscordConfig(
    client_id="111111111111111111",
    client_secret="offline-only",
    guild_id="222222222222222222",
    invited_user_id="333333333333333333",
    other_user_id="444444444444444444",
    handler_user_id="555555555555555555",
)
IDENTITIES = {
    "invited": CONFIG.invited_user_id,
    "other": CONFIG.other_user_id,
    "handler": CONFIG.handler_user_id,
    "role-pilot": "666666666666666666",
    "unapproved": "777777777777777777",
}
TESTER_ROLE = "888888888888888888"
MANAGED_ROLES = ("999999999999999991", "999999999999999992")
MANAGED_CHANNELS = ("888888888888888891", "888888888888888892")
TACTICAL_DICE = {"low": (1, 1), "mid": (4, 5), "high": (6, 6)}
DEFEAT_DICE = {"mid": (3, 3), "high": (6, 6), "low": (1, 1), "death": (1, 1)}


def prepare_off_duty_fixture(missions, observation):
    from girlframe.engine.m3_off_duty import Period
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_frame_rewards import RewardService
    from girlframe.services.m3_observation import ObservationService
    from girlframe.services.m3_off_duty import OffDutyService

    approval = missions.store.policy.m3_approval
    missions.store.policy = missions.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays", "playbooks"}}
            )
        }
    )
    periods = OffDutyService(missions)
    if periods.current(HANDLER):
        return
    # Keep the independent relay offer fixture and seed only a completed preparation.
    with missions.store.transaction() as connection:
        state = load_state(connection, missions.store.campaign_id)
        pilots = tuple(uid for uid in state.order if str(uid) in state.sheets)
        state.order = pilots
        sheet = state.sheets[str(OFFERED.user_id)]
        next(asset for asset in sheet.assets if asset.family == "frame").damaged = True
        sheet.identities[0].marked = True
        sheet.revision += 1
        period = Period(
            id=str(uuid4()),
            handler=HANDLER.user_id,
            pilots=pilots,
            character_ids={
                str(uid): state.sheets[str(uid)].character_id for uid in pilots
            },
            phase="active",
        )
        event = missions.game.event(
            connection,
            HANDLER.user_id,
            "offline-off-duty-active",
            "synthetic.active",
            state,
        )
        periods._save(connection, period, event)
        game_revision = load_state(connection, missions.store.campaign_id).revision
    RewardService(periods).refresh(
        HANDLER,
        "offline-off-duty-rewards",
        period.id,
        period.revision,
        game_revision,
    )
    if observation:
        ObservationService(periods).order(
            HANDLER,
            "offline-observation-order",
            period.id,
            period.revision,
            game_revision,
            OFFERED.user_id,
            False,
            "Review the pilot's Void exposure.",
        )


class FixedTacticalDice:
    def __init__(self, faces, next_faces=None):
        self.faces = faces
        self.next_faces = next_faces

    def roll(self):
        faces = self.faces
        if self.next_faces:
            self.faces = self.next_faces
            self.next_faces = None
        return faces


def seed_test_state(battlefield, *, core_heat=False, last_asset=False):
    """Prepare the original synthetic sheet once, including across lab restarts."""
    from girlframe.database import tables
    from girlframe.services.m2_state import load_state

    game = battlefield.game
    actor = battlefield.owner.user_id
    with game.store.transaction() as connection:
        key = "offline-test-last-asset" if last_asset else "offline-test-core-heat"
        events = tables.events
        if connection.scalar(
            sa.select(events.c.id).where(
                events.c.campaign_id == game.store.campaign_id,
                events.c.command_key == key,
            )
        ):
            return
        state = load_state(connection, game.store.campaign_id)
        sheet = state.sheets[str(actor)]
        if core_heat:
            sheet.heat = 4
        if last_asset:
            frames = [asset for asset in sheet.assets if asset.family == "frame"]
            assert frames
            for asset in frames[1:]:
                asset.damaged = True
            sheet.permissions = 2
        game.event(connection, actor, key, "synthetic.state", state)


def offline_discord_request(path, *, token=None, form=None):
    if path == "/oauth2/token" and form and form["client_id"] == CONFIG.client_id:
        role = form["code"]
        if role in IDENTITIES or role == "pending-member":
            return {
                "access_token": role,
                "expires_in": 600,
                "scope": "identify guilds.members.read",
                "refresh_token": "must-stay-server-side",
            }
    if token == "pending-member":
        if path == "/users/@me":
            return {"id": CONFIG.invited_user_id}
        if path == f"/users/@me/guilds/{CONFIG.guild_id}/member":
            return {"user": {"id": CONFIG.invited_user_id}, "pending": True}
    if token in IDENTITIES:
        if path == "/users/@me":
            return {"id": IDENTITIES[token]}
        if path == f"/users/@me/guilds/{CONFIG.guild_id}/member":
            return {
                "user": {"id": IDENTITIES[token]},
                "pending": False,
                "roles": [TESTER_ROLE] if token == "role-pilot" else [],
            }
    raise SignInError(
        HTTPStatus.FORBIDDEN, "Discord authorization or membership was denied."
    )


def managed_campaign_fixture(campaign):
    catalog = CampaignRegistry(
        mission_lab.RUNTIME
        / "playtest-campaigns"
        / campaign
        / "managed-fixture.sqlite3"
    )
    source = 100_000_000_000_000_000 + 2 * int.from_bytes(
        sha256(campaign.encode()).digest()[:7], "big"
    )
    for index, (name, role, channel) in enumerate(
        zip(
            ("Northern Reach", "Southern Signal"),
            MANAGED_ROLES,
            MANAGED_CHANNELS,
            strict=True,
        )
    ):
        catalog.register(
            application_id=CONFIG.client_id,
            guild_id=CONFIG.guild_id,
            owner_id=CONFIG.handler_user_id,
            actor_id=CONFIG.handler_user_id,
            role_id=role,
            role_guild_id=CONFIG.guild_id,
            handler_id=CONFIG.handler_user_id,
            interaction_id=str(source + index),
            name=name,
            channel_id=channel,
            channel_guild_id=CONFIG.guild_id,
            provision=mission_lab.provision_managed_campaign,
        )
    return catalog


def managed_discord_request(path, *, token=None, form=None):
    result = offline_discord_request(path, token=token, form=form)
    if path.endswith("/member"):
        if token in ("invited", "other", "handler"):
            result["roles"] = list(MANAGED_ROLES)
        elif token == "role-pilot":
            result["roles"] = [MANAGED_ROLES[0]]
    return result


def copy_rehearsal_for_browser(name, config):
    """Use the migrated ledger in a separate fixture with fake Discord identities."""
    from director_trial import discord_trial_binding
    from girlframe.database.maintenance import copy_database

    if not re.fullmatch(r"browser-[0-9a-f-]{36}", name):
        raise ValueError("A rehearsal copy requires a generated browser fixture name.")
    root = (mission_lab.RUNTIME / "p2-discord-trials").resolve()
    source = root / "rehearsal"
    destination = root / name
    if destination.exists():
        return  # Resume the original test copy after the server restarts.
    saved = json.loads((source / "synthetic-trial.json").read_bytes())
    if not saved.get("synthetic") or saved["policy"]["sandbox"] != str(source):
        raise ValueError("Only the isolated synthetic rehearsal may be copied.")
    destination.mkdir()
    copy_database(source / "ledger.db", destination / "ledger.db")
    saved["policy"]["sandbox"] = str(destination)
    (destination / "synthetic-trial.json").write_text(json.dumps(saved), encoding="utf-8")
    (destination / "activity-discord-binding.json").write_text(
        json.dumps(discord_trial_binding(config)), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--p2-trial")
    parser.add_argument("--copy-p2-rehearsal", action="store_true")
    parser.add_argument("--dm", action="store_true")
    parser.add_argument("--allow-dm", action="store_true")
    parser.add_argument("--bound-roster", action="store_true")
    parser.add_argument("--tester-roles", action="store_true")
    parser.add_argument("--managed-campaigns", action="store_true")
    parser.add_argument("--tactical-tier", choices=TACTICAL_DICE)
    parser.add_argument("--scene-tier", choices=TACTICAL_DICE)
    parser.add_argument("--core-test-heat", action="store_true")
    parser.add_argument("--defeat-test", choices=DEFEAT_DICE)
    parser.add_argument("--off-duty-test", choices=("ordinary", "observation"))
    args = parser.parse_args()
    if not args.campaign.startswith("discord-offline-"):
        parser.error("Use a separate campaign name beginning with discord-offline-.")
    if args.bound_roster and args.dm:
        parser.error("--bound-roster requires the three-account fixture.")
    if args.tester_roles and not args.bound_roster:
        parser.error("--tester-roles requires --bound-roster.")
    if args.managed_campaigns and not args.bound_roster:
        parser.error("--managed-campaigns requires --bound-roster.")
    if args.copy_p2_rehearsal and not args.p2_trial:
        parser.error("--copy-p2-rehearsal requires --p2-trial.")
    if args.p2_trial:
        import sys

        from girlframe.services.m3_missions import MissionService

        sys.path.insert(0, str(mission_lab.ENGINE / "tools"))
        from director_trial import open_trial

        config = replace(CONFIG, allow_dm=args.allow_dm)
        if args.copy_p2_rehearsal:
            copy_rehearsal_for_browser(args.p2_trial, config)
        director = open_trial(
            mission_lab.ENGINE,
            mission_lab.RUNTIME / "p2-activity-trials",
            args.p2_trial,
            discord_config=config,
        )
        serve(
            MissionService(director.session.store),
            0,
            True,
            DiscordSessions(config, offline_discord_request),
            scene_dice=FixedTacticalDice(TACTICAL_DICE["mid"]),
            director=director,
        )
        raise SystemExit
    missions = open_campaign(
        args.campaign, roster=CONFIG if args.bound_roster else None
    )
    if args.off_duty_test:
        prepare_off_duty_fixture(missions, args.off_duty_test == "observation")
    config = replace(
        CONFIG,
        other_user_id=None if args.dm else CONFIG.other_user_id,
        allow_dm=args.dm or args.allow_dm,
        tester_role_ids=frozenset({TESTER_ROLE}) if args.tester_roles else frozenset(),
    )
    serve(
        missions,
        0,
        True,
        DiscordSessions(
            config,
            managed_discord_request
            if args.managed_campaigns
            else offline_discord_request,
        ),
        bound_roster=args.bound_roster,
        campaign_registry=managed_campaign_fixture(args.campaign)
        if args.managed_campaigns
        else None,
        tactical_dice=FixedTacticalDice(
            TACTICAL_DICE["low"], DEFEAT_DICE[args.defeat_test]
        )
        if args.defeat_test
        else FixedTacticalDice(TACTICAL_DICE[args.tactical_tier])
        if args.tactical_tier
        else None,
        scene_dice=FixedTacticalDice(TACTICAL_DICE[args.scene_tier])
        if args.scene_tier
        else None,
        prepare_test_battlefield=(
            lambda battlefield: seed_test_state(
                battlefield,
                core_heat=args.core_test_heat,
                last_asset=bool(args.defeat_test),
            )
        )
        if args.core_test_heat or args.defeat_test
        else None,
    )
