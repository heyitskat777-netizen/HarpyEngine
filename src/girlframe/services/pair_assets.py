"""Pair-only names; the counterpart's private creation body is never read."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.pair_assets import PairChoice, PairNames
from girlframe.services.bonds import BondService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class PairService:
    def __init__(self, store: OnboardingStore):
        self.store, self.bonds = store, BondService(store)

    def _choice(self, connection: Connection, bond: dict[str, Any]) -> PairChoice:
        row = (
            connection.execute(
                sa.select(t.pair_asset_revisions)
                .where(
                    t.pair_asset_revisions.c.campaign_id == self.store.campaign_id,
                    t.pair_asset_revisions.c.bond_id == bond["id"],
                )
                .order_by(t.pair_asset_revisions.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return PairChoice(
            bond["id"],
            bond["revision"],
            row["revision"] if row else 0,
            PairNames(names=tuple(json.loads(row["names_json"]))).names if row else (),
        )

    def _pair(self, connection: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        bond = self.bonds._party(connection, viewer, identity)
        if (
            bond["girl_playbook"] != "BONDED"
            or bond["state"] != "accepted"
            or bond["target_id"] != str(viewer.user_id)
            or self.bonds._stale(connection, bond)
        ):
            raise WorkflowError(
                "Only the current accepted Pair can select these starting Girl Assets."
            )
        return bond

    def prepare(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            bond = self._pair(connection, viewer, identity)
            choice = self._choice(connection, bond)
            return {
                "bond_id": bond["id"],
                "bond_revision": bond["revision"],
                "owner_id": int(bond["source_id"]),
                "revision": choice.revision,
                "names": choice.names,
            }

    def resolve(self, viewer: GuildViewer, owner: int) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.bonds._authorize(connection, viewer)
            for bond in self.bonds._latest(connection, str(viewer.user_id)):
                if (
                    bond["source_id"] == str(owner)
                    and bond["girl_playbook"] == "BONDED"
                    and bond["state"] == "accepted"
                ):
                    self._pair(connection, viewer, bond["id"])
                    identity = bond["id"]
                    break
            else:
                raise WorkflowError("No current accepted Pair agreement with that Bonded player.")
        return self.prepare(viewer, identity)

    def for_owner(self, connection: Connection, viewer: GuildViewer) -> PairChoice | None:
        self.bonds._authorize(connection, viewer)
        for bond in self.bonds._latest(connection, str(viewer.user_id)):
            if (
                bond["source_id"] == str(viewer.user_id)
                and bond["girl_playbook"] == "BONDED"
                and bond["state"] == "accepted"
                and not self.bonds._stale(connection, bond)
            ):
                return self._choice(connection, bond)
        return None

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        bond_revision: int,
        expected: int,
        names: PairNames,
    ) -> dict[str, Any]:
        names = PairNames.model_validate_json(names.model_dump_json())

        def authorize(connection: Connection) -> None:
            self._pair(connection, viewer, identity)

        def operation(connection: Connection) -> dict[str, Any]:
            bond = self._pair(connection, viewer, identity)
            previous = self._choice(connection, bond)
            if bond["revision"] != bond_revision or previous.revision != expected:
                raise WorkflowError("STALE_REVISION: reopen Pair Assets; saved choices preserved.")
            result = {"bond_id": bond["id"], "revision": expected + 1}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.pair_assets_chosen", result
            )
            connection.execute(
                t.pair_asset_revisions.insert().values(
                    campaign_id=self.store.campaign_id,
                    **result,
                    bond_revision=bond_revision,
                    names_json=json.dumps(names.names),
                    event_id=event,
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.pair_assets_chosen",
            {
                "bond_id": identity,
                "bond_revision": bond_revision,
                "expected": expected,
                "names": names.model_dump(mode="json"),
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )
