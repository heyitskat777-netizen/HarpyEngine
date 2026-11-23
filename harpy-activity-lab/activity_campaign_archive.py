"""Export one managed Activity campaign and restore it to a new, offline runtime."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from campaign_registry import RUNTIME, CampaignRegistry

if __name__ == "__main__":
    sys.path.insert(0, str(RUNTIME / "HarpyEngine-playtest" / "src"))

from girlframe.database.maintenance import copy_database  # noqa: E402
from girlframe.discord_adapter.config import BotPolicy, load_bot_policy  # noqa: E402

FORMAT = "harpyengine-activity-campaign-v1"
REGISTRY = "activity-campaigns.sqlite3"
DATABASE = "missions.sqlite3"
POLICY = "synthetic-policy.json"
OPTIONAL_DATABASES = ("activity-records.sqlite3", "activity-delivery.sqlite3")
MANIFEST = "manifest.json"
MAX_METADATA = 64 * 1024
BINDING_FIELDS = (
    "id",
    "application_id",
    "guild_id",
    "role_id",
    "handler_id",
    "name",
    "channel_id",
    "owner_id",
    "interaction_id",
)


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)


def _bindings(registry: Path) -> list[dict[str, Any]]:
    with closing(_read_only(registry)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(bindings)")}
        projection = ", ".join(
            ("NULL AS channel_id" if field == "channel_id" and field not in columns else field)
            for field in BINDING_FIELDS
        )
        conn.row_factory = sqlite3.Row
        # These column names are fixed above. No input is used to construct the query.
        return [
            dict(row) for row in conn.execute(f"SELECT {projection} FROM bindings ORDER BY name")
        ]


def _sandbox(runtime: Path, binding: dict[str, Any]) -> Path:
    return runtime / "playtest-campaigns" / f"activity-{UUID(binding['id']).hex}"


def _verify_binding(binding: dict[str, Any], policy: BotPolicy, database: Path) -> None:
    if (
        UUID(binding["id"]) != policy.campaign_id
        or binding["guild_id"] != str(policy.guild_id)
        or binding["application_id"] != str(policy.application_id)
    ):
        raise ValueError("The campaign policy does not match its Activity binding.")
    with closing(_read_only(database)) as conn:
        if conn.execute("SELECT id, guild_id FROM campaigns").fetchall() != [
            (str(policy.campaign_id), str(policy.guild_id))
        ]:
            raise ValueError("The engine store does not match the selected Activity campaign.")


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _write_policy(path: Path, data: str) -> None:
    with path.open("x", encoding="utf-8") as target:
        path.chmod(0o600)
        target.write(data)


def export_campaign(
    runtime: Path, selector: str, destination: Path, *, registry: Path | None = None
) -> None:
    runtime = runtime.resolve(strict=True)
    bindings = _bindings(registry if registry is not None else runtime / REGISTRY)
    try:
        target_id = UUID(selector).hex
    except ValueError:
        target_id = None
    matches = [
        binding
        for binding in bindings
        if binding["id"] == target_id or binding["name"].casefold() == selector.strip().casefold()
    ]
    if len(matches) != 1:
        raise ValueError("Choose one registered campaign by UUID or exact name.")
    binding = matches[0]
    sandbox = _sandbox(runtime, binding)
    if sandbox.resolve(strict=True) != sandbox or any(
        (sandbox / name).is_symlink() for name in (POLICY, DATABASE, *OPTIONAL_DATABASES)
    ):
        raise ValueError("The campaign sandbox does not match its registered path.")
    policy = load_bot_policy(sandbox / POLICY)
    if policy.sandbox != sandbox:
        raise ValueError("The campaign sandbox does not match its registered path.")
    destination = destination.parent.resolve(strict=True) / destination.name
    if destination.exists() or destination.is_symlink() or destination.is_relative_to(sandbox):
        raise ValueError("Choose a new archive path outside the campaign sandbox.")
    with TemporaryDirectory(prefix=".harpy-archive-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        _write_policy(staging / POLICY, policy.model_dump_json(exclude={"sandbox"}))
        names = [POLICY, DATABASE]
        copy_database(sandbox / DATABASE, staging / DATABASE)
        _verify_binding(binding, policy, staging / DATABASE)
        for name in OPTIONAL_DATABASES:
            if (sandbox / name).exists():
                copy_database(sandbox / name, staging / name, require_migration_marker=False)
                names.append(name)
        package = staging / "campaign.zip"
        package.touch(mode=0o600)
        with ZipFile(package, "w", ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(staging / name, name)
            archive.writestr(
                MANIFEST,
                json.dumps(
                    {
                        "format": FORMAT,
                        "binding": binding,
                        "files": {name: _sha256(staging / name) for name in names},
                    },
                    sort_keys=True,
                ),
            )
        with package.open("r+b") as completed:
            os.fsync(completed.fileno())
        os.link(package, destination)


def _restore_registration(registry: Path, binding: dict[str, Any]) -> None:
    saved = CampaignRegistry(registry).register(
        application_id=binding["application_id"],
        guild_id=binding["guild_id"],
        owner_id=binding["owner_id"],
        actor_id=binding["owner_id"],
        role_id=binding["role_id"],
        role_guild_id=binding["guild_id"],
        handler_id=binding["handler_id"],
        interaction_id=binding["interaction_id"],
        name=binding["name"],
        channel_id=binding["channel_id"],
        channel_guild_id=binding["guild_id"],
    )
    if saved.id != UUID(binding["id"]).hex:
        raise ValueError("The restored Discord binding has a different campaign UUID.")


def import_campaign(package: Path, runtime: Path) -> None:
    runtime = runtime.absolute()
    if runtime.exists() or runtime.is_symlink():
        raise FileExistsError("Import requires a new, offline Activity runtime directory.")
    runtime = runtime.parent.resolve(strict=True) / runtime.name
    with (
        ZipFile(package) as archive,
        TemporaryDirectory(prefix=".harpy-import-", dir=runtime.parent) as temporary,
    ):
        names = archive.namelist()
        if (
            not {MANIFEST, POLICY, DATABASE} <= set(names)
            or len(names) != len(set(names))
            or not set(names) <= {MANIFEST, POLICY, DATABASE, *OPTIONAL_DATABASES}
            or archive.getinfo(MANIFEST).file_size > MAX_METADATA
            or archive.getinfo(POLICY).file_size > MAX_METADATA
        ):
            raise ValueError("The archive contains invalid campaign files.")
        manifest = json.loads(archive.read(MANIFEST))
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ValueError("Unsupported Activity campaign archive format.")
        hashes, binding = manifest.get("files"), manifest.get("binding")
        if (
            not isinstance(hashes, dict)
            or hashes.keys() != set(names) - {MANIFEST}
            or not isinstance(binding, dict)
            or binding.keys() != set(BINDING_FIELDS)
            or not all(
                isinstance(value, str) or (field == "channel_id" and value is None)
                for field, value in binding.items()
            )
        ):
            raise ValueError("The archive manifest is incomplete.")
        staging = Path(temporary) / "runtime"
        staging.mkdir(mode=0o700)
        sandbox = _sandbox(staging, binding)
        sandbox.mkdir(parents=True, mode=0o700)
        for name, expected in hashes.items():
            unpacked = Path(temporary) / name
            with archive.open(name) as source, unpacked.open("xb") as target:
                shutil.copyfileobj(source, target)
            if _sha256(unpacked) != expected:
                raise ValueError("An archived campaign file failed checksum verification.")
            if name != POLICY:
                copy_database(unpacked, sandbox / name, require_migration_marker=name == DATABASE)
        policy_data = json.loads((Path(temporary) / POLICY).read_bytes())
        if not isinstance(policy_data, dict) or "sandbox" in policy_data:
            raise ValueError("The archive must contain a portable campaign policy.")
        policy_data["sandbox"] = str(_sandbox(runtime, binding))
        policy = BotPolicy.model_validate_json(json.dumps(policy_data))
        _verify_binding(binding, policy, sandbox / DATABASE)
        _write_policy(sandbox / POLICY, policy.model_dump_json())
        _restore_registration(staging / REGISTRY, binding)
        if runtime.exists() or runtime.is_symlink():
            raise FileExistsError("Use a new, offline Activity runtime directory.")
        staging.rename(runtime)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    show = commands.add_parser("list", help="List registered campaigns and their UUIDs.")
    show.add_argument("--runtime", type=Path, default=RUNTIME)
    export = commands.add_parser("export", help="Save one private campaign archive.")
    export.add_argument("--runtime", type=Path, default=RUNTIME)
    export.add_argument("--campaign", required=True)
    export.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("import", help="Restore into a separate, new runtime.")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "list":
            for binding in _bindings(args.runtime / REGISTRY):
                print(f"{UUID(binding['id'])}  {binding['name']}")
        elif args.operation == "export":
            export_campaign(args.runtime, args.campaign, args.output)
            print("Verified private campaign archive saved.")
        else:
            import_campaign(args.archive, args.runtime)
            print("Verified campaign restored to a new offline runtime.")
    except (ValueError, OSError, BadZipFile, sqlite3.Error) as error:
        print(f"Activity campaign archive failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
