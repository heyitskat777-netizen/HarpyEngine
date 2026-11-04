"""Private original-recipient decisions, proved against the actual random source."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_contraband as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ContrabandService(RequisitionService):
    def source(self, c: Connection, find: ContrabandFind) -> None:
        works = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(works)
                .where(works.c.campaign_id == self.store.campaign_id, works.c.id == find.id)
                .order_by(works.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == find.source_event,
                )
            )
            .mappings()
            .first()
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == find.source_event,
            )
        )
        original = GameState.model_validate_json(history) if history else None
        first = (
            next((x for x in original.contraband_finds if x.id == find.id), None)
            if original
            else None
        )
        strain = (
            next((x for x in original.strain.events if x.id + ":effect" == find.id), None)
            if original and original.strain
            else None
        )
        if (
            row is None
            or row["state"] != "resolved"
            or row["kind"] != "strain_event"
            or row["off_duty_id"] != find.period
            or row["event_id"] != find.source_event
            or event is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != row["owner_id"]
            or strain is None
            or strain.rule_id != "strain.rebellion.low.2.2"
            or strain.period_id != find.period
            or json.loads(row["body_json"]).get("rule_id") != strain.rule_id
            or json.loads(row["body_json"]).get("choice", {}).get("target") != find.base
            or json.loads(event["payload_json"]).get("rule_id") != strain.rule_id
            or json.loads(event["payload_json"]).get("work_id") != find.id
            or first is None
            or first.taken is not None
        ):
            raise WorkflowError(
                "SOURCE_CONTRABAND_MISSING: recover the actual private random-find source."
            )
        original_fields = (
            "id",
            "period",
            "source_event",
            "base",
            "population",
            "index",
            "rng_source",
            "label",
        )
        if any(getattr(first, key) != getattr(find, key) for key in original_fields):
            raise WorkflowError(
                "SOURCE_CONTRABAND_CHANGED: recover the original recipient and draw."
            )

    def _find(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, ContrabandFind]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        find = next(
            (
                x
                for x in state.contraband_finds
                if x.id == identity and x.actor.entity == str(viewer.user_id)
            ),
            None,
        )
        if find is None:
            raise WorkflowError(
                "This private find belongs to its original recipient or is unavailable."
            )
        self.source(c, find)
        return state, find

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            found = []
            for find in state.contraband_finds:
                if find.actor.entity != str(viewer.user_id):
                    continue
                self.source(c, find)
                found.append(
                    dict(
                        id=find.id,
                        label=find.label,
                        state="pending"
                        if find.taken is None
                        else "accepted"
                        if find.taken
                        else "declined",
                    )
                )
            return found

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, find = self._find(c, viewer, identity)
            current = None
            try:
                current = resolve(
                    state,
                    find.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
            except ValueError:
                pass  # Original owned history stays readable; a new character cannot claim it.
            sheet = state.sheets.get(find.actor.entity) if current is not None else None
            asset = (
                next((x for x in sheet.assets if x.id == find.asset_id), None) if sheet else None
            )
            return dict(
                id=find.id,
                label=find.label,
                taken=find.taken,
                choice=find.choice.model_dump(mode="json") if find.choice else None,
                account=find.account,
                find_sha256=fingerprint(find),
                actor_sha256=current.source_sha256 if current else None,
                eligible=bool(current and current.rules == "girl_frame"),
                assets=[x.model_dump(mode="json") for x in current.assets if x.family == "girl"]
                if current
                else [],
                concealed=asset.concealed if asset else None,
                can_share=bool(
                    asset and asset.concealed and sheet and "assets" in sheet.public_fields
                ),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected_find: str,
        expected_actor: str,
        taken: bool,
        choice: GirlAsset | None,
        account: str,
    ) -> dict[str, Any]:
        if choice is not None:
            choice = GirlAsset.model_validate_json(choice.model_dump_json())

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            Access(self.store).authorize(c, viewer, "plays")
            self._find(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            if taken:
                self.game.unpaused(c)
            state, find = self._find(c, viewer, identity)
            if fingerprint(find) != expected_find:
                raise WorkflowError("STALE_CONTRABAND: reopen your actual saved find.")
            if taken:
                self._safe(c, state, viewer.user_id)
            source = str(uuid4())
            updated = rules.claim(
                state,
                profiles(c, self.store.campaign_id),
                find,
                expected_actor,
                taken,
                choice,
                account,
                source,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.contraband_decided",
                updated,
                event_id=source,
                find_id=identity,
                taken=taken,
            )
            return dict(id=identity, taken=taken)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.contraband_decided",
                dict(
                    id=identity,
                    expected_find=expected_find,
                    expected_actor=expected_actor,
                    taken=taken,
                    choice=choice.model_dump(mode="json") if choice else None,
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except (ValidationError, ValueError) as error:
            raise WorkflowError(str(error)) from None

    def share(self, viewer: GuildViewer, key: str, identity: str, expected: str) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            self._find(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, find = self._find(c, viewer, identity)
            self._safe(c, state, viewer.user_id)
            state = rules.share(state, profiles(c, self.store.campaign_id), find, expected)
            self.game.event(c, viewer.user_id, key, "m3.contraband_shared", state, find_id=identity)
            return dict(id=identity, shared=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.contraband_shared",
                dict(id=identity, expected=expected),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except (ValidationError, ValueError) as error:
            raise WorkflowError(str(error)) from None
