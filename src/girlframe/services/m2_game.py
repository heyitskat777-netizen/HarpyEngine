"""Transactional M2 canonical state, activation, scenes and durable Play actions."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import (
    PLAY_IDS,
    RULESET,
    AssetState,
    ChoiceAnswer,
    GameState,
    IdentityState,
    Obligation,
    PilotSheet,
    PlayInput,
    higher,
    mark_identity,
    pair_key,
    spend_heat,
)
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.rolls import DiceSource, OsDice
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state, public_sheet
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

PUBLIC_FIELDS = {
    "frame_name",
    "appearance",
    "frame_appearance",
    "identities",
    "assets",
    "asset_descriptions",
}


class GameService:
    def __init__(self, store: OnboardingStore, *, dice: DiceSource | None = None):
        self.store = store
        self.dice = dice if dice is not None else OsDice()
        self.rng_source = "os" if dice is None else "test_injected"

    def gate(self) -> None:
        approval = self.store.policy.m2_approval
        if (
            approval is None
            or approval.registry_sha256 != registry_digest()
            or self.store.policy.owner_intense_tag_bonus is None
        ):
            raise WorkflowError("M2_REVIEW_PENDING: gameplay awaits the end-of-M2 release review.")

    def authorize(self, c: Connection, viewer: GuildViewer, *, game: bool = True) -> None:
        self.store.guild_member(viewer)
        self.store._membership(c, viewer)
        if game:
            self.gate()
            state = load_state(c, self.store.campaign_id)
            if (
                state.sheets
                and HandlerService(self.store).current(c)[1].handler_id != state.handler
            ):
                raise WorkflowError("STALE_HANDLER: canonical Handler replacement needs review.")

    def unpaused(self, c: Connection) -> None:
        if c.execute(
            sa.select(t.pauses).where(t.pauses.c.campaign_id == self.store.campaign_id)
        ).first():
            raise WorkflowError(
                "SAFETY_PAUSED: gameplay is paused; recovery and saved views remain available."
            )

    def event(
        self,
        c: Connection,
        actor: int | str,
        key: str,
        kind: str,
        state: GameState | None = None,
        **metadata: Any,
    ) -> str:
        if state is not None:
            state.revision += 1
            metadata["game_revision"] = state.revision
        event = self.store._audit(c, actor, key, kind, metadata)
        if state is not None:
            body = GameState.model_validate_json(state.model_dump_json()).model_dump_json()
            c.execute(
                t.m2["m2_state_history"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    revision=state.revision,
                    body_json=body,
                    event_id=event,
                )
            )
            table = t.m2["m2_state"]
            where = table.c.campaign_id == self.store.campaign_id
            if c.execute(sa.select(table.c.revision).where(where)).first():
                c.execute(
                    table.update().where(where).values(revision=state.revision, body_json=body)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, revision=state.revision, body_json=body
                    )
                )
        return event

    def sheet(self, viewer: GuildViewer, owner: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(owner if owner is not None else viewer.user_id))
            if sheet is None:
                raise WorkflowError("This Pilot has no activated M2 sheet.")
            return (
                sheet.model_dump(mode="json")
                if sheet.owner == viewer.user_id
                else public_sheet(sheet, state)
            )

    def activate(
        self, viewer: GuildViewer, key: str, fingerprint: str, public_fields: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        if not set(public_fields) <= PUBLIC_FIELDS or len(set(public_fields)) != len(public_fields):
            raise WorkflowError("Choose supported public fields explicitly.")

        def authorize(c: Connection) -> None:
            self.authorize(c, viewer)
            self.unpaused(c)
            current = CreationReviewService(self.store)._current(c, viewer)
            if (
                current.fingerprint != fingerprint
                or not current.saved_current
                or not current.sheet.ready_for_rules_review
            ):
                raise WorkflowError(
                    "STALE_OR_INCOMPLETE: save a current complete review before activation."
                )

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) in state.sheets:
                raise WorkflowError(
                    "Already activated; activation cannot reset gameplay resources."
                )
            review = CreationReviewService(self.store)._current(c, viewer).sheet
            setup = HandlerService(self.store).current(c)[1]
            if not state.order:
                state.order = tuple(x.user_id for x in setup.status_order)
                state.handler = setup.handler_id
                state.intense_tag_bonus = self.store.policy.owner_intense_tag_bonus
            elif state.handler != setup.handler_id or set(state.order) != {
                x.user_id for x in setup.status_order
            }:
                raise WorkflowError(
                    "UNSUPPORTED_RULE: canonical roster/Handler changes need explicit migration."
                )
            identities = [
                IdentityState(
                    id="identity:" + str(i),
                    name=name,
                    paired=review.creation.girl_playbook == "BONDED" and name == "Hers",
                    protected=review.creation.girl_playbook == "BONDED" and name == "Hers",
                )
                for i, name in enumerate(review.creation.identities)
            ]
            if review.creation.fanbase:
                identities.extend(
                    IdentityState(id="fan:" + str(i), name=name, protected=True)
                    for i, name in enumerate(review.creation.fanbase.additional_identities)
                )
            assets: list[AssetState] = []
            for family, values in (
                (
                    "girl",
                    review.creation.pair_asset_descriptions
                    if review.creation.girl_playbook == "BONDED"
                    else review.creation.girl_assets,
                ),
                ("frame", review.creation.frame_assets),
            ):
                assets.extend(
                    AssetState(
                        id=family + ":" + str(i),
                        family=cast(Literal["girl", "frame"], family),
                        name=x.name,
                        description=x.description,
                        void=x.name == review.creation.void_asset and family == "girl",
                    )
                    for i, x in enumerate(values)
                )
            assets.extend(
                AssetState(id="frame:intrinsic:" + str(i), family="frame", name=name)
                for i, name in enumerate(review.creation.intrinsic_frame_assets)
            )
            outgoing = next((x for x in review.bonds if x.outgoing), None)
            sheet = PilotSheet(
                owner=viewer.user_id,
                callsign=review.activation_callsign,
                girl=review.creation.girl_playbook,
                frame=review.creation.frame_playbook,
                source_fingerprint=fingerprint,
                source_profile_revision=review.character_revision,
                review=review,
                identities=identities,
                assets=assets,
                heat=review.rulings.starting_heat if review.rulings else 0,
                mentor=outgoing.counterpart
                if outgoing and review.creation.girl_playbook == "NEWGIRL"
                else None,
                pair=outgoing.counterpart
                if outgoing and review.creation.girl_playbook == "BONDED"
                else None,
                public_fields=public_fields,
            )
            state.sheets[str(viewer.user_id)] = sheet
            for bond in review.bonds:
                pair = pair_key(viewer.user_id, bond.counterpart)
                if pair not in state.bonds:
                    state.bonds[pair] = 2 if bond.depth == "Intense" else 1
            self.event(
                c, viewer.user_id, key, "m2.character_activated", state, owner=viewer.user_id
            )
            self.store._enqueue_sync(
                c,
                viewer.user_id,
                review.character_revision,
                DraftInput(
                    callsign=sheet.callsign, girl_playbook=sheet.girl, frame_playbook=sheet.frame
                ),
            )
            return {
                "owner": viewer.user_id,
                "revision": sheet.revision,
                "state": "active_m2_subset",
            }

        return self.store._write(
            viewer,
            key,
            "m2.character_activated",
            {"fingerprint": fingerprint, "public_fields": list(public_fields)},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def scene(self, c: Connection, channel: int | str) -> dict[str, Any]:
        table = t.m2["m2_scenes"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                    table.c.open.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Bind an open M2 scene channel first.")
        return dict(row) | {"participants": json.loads(row["participants_json"])}

    def bind_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer)
            self.store.administrator(viewer)

        def operation(c: Connection) -> dict[str, Any]:
            table = t.m2["m2_scenes"]
            where = sa.and_(
                table.c.campaign_id == self.store.campaign_id, table.c.channel_id == str(channel)
            )
            old = c.execute(sa.select(table).where(where)).mappings().first()
            if old and old["open"]:
                raise WorkflowError("This scene is already open.")
            values = {
                "id": str(uuid4()),
                "revision": old["revision"] + 1 if old else 1,
                "participants_json": "[]",
                "open": True,
            }
            if old:
                c.execute(table.update().where(where).values(**values))
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.event(c, viewer.user_id, key, "m2.scene_bound", channel=channel)
            return {"channel": channel, "scene": values["id"]}

        return self.store._write(
            viewer,
            key,
            "m2.scene_bound",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def join_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) not in state.sheets and viewer.user_id != state.handler:
                raise WorkflowError("Activate a Pilot or use the appointed Handler account.")
            scene = self.scene(c, channel)
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError(
                    "Wait for this scene's pending Play before changing participants."
                )
            table = t.m2["m2_scenes"]
            if viewer.user_id != state.handler:
                rows = c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id, table.c.open.is_(True)
                    )
                ).mappings()
                if any(
                    x["channel_id"] != str(channel)
                    and viewer.user_id in json.loads(x["participants_json"])
                    for x in rows
                ):
                    raise WorkflowError("A Pilot may join one active M2 scene at a time.")
            people = sorted(set(scene["participants"]) | {viewer.user_id})
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=scene["revision"] + 1)
            )
            self.event(c, viewer.user_id, key, "m2.scene_joined", channel=channel)
            return {"channel": channel, "participants": people}

        return self.store._write(
            viewer,
            key,
            "m2.scene_joined",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def lock(self, c: Connection, channel: int | str) -> dict[str, Any] | None:
        table = t.m2["m2_locks"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def action(self, c: Connection, identity: str) -> dict[str, Any]:
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("Unknown action.") from None
        table = t.m2["m2_actions"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == identity
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Unknown action.")
        return dict(row) | {"data": json.loads(row["body_json"])}

    def save_action(self, c: Connection, action: dict[str, Any], **changes: Any) -> None:
        action.update(changes)
        action["revision"] += 1
        table = t.m2["m2_actions"]
        c.execute(
            table.update()
            .where(table.c.campaign_id == self.store.campaign_id, table.c.id == action["id"])
            .values(
                revision=action["revision"],
                state=action["state"],
                body_json=json.dumps(action["data"], sort_keys=True),
            )
        )

    def request(
        self,
        c: Connection,
        action: dict[str, Any],
        actor: int | None,
        kind: str,
        body: dict[str, Any] | None = None,
    ) -> str:
        if actor is None:
            raise WorkflowError("The required decision owner is unavailable.")
        identity = str(uuid4())
        c.execute(
            t.m2["m2_choices"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=identity,
                action_id=action["id"],
                actor_id=str(actor),
                kind=kind,
                revision=1,
                state="pending",
                body_json=json.dumps(body or {}, sort_keys=True),
            )
        )
        return identity

    def queue(
        self, c: Connection, action: dict[str, Any], kind: str, body: dict[str, Any] | None = None
    ) -> None:
        identity = str(uuid4())
        c.execute(
            t.m2["m2_outbox"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=identity,
                action_id=action["id"],
                channel_id=action["channel_id"],
                nonce=str(int(UUID(identity)) % (2**63 - 1)),
                body_json=json.dumps({"kind": kind, **(body or {})}),
                state="pending",
            )
        )

    def obligation(
        self,
        state: GameState,
        action: dict[str, Any],
        kind: str,
        owner: int,
        target: int | None = None,
        **details: str,
    ) -> str:
        identity = str(uuid4())
        state.obligations.append(
            Obligation(
                id=identity,
                kind=kind,
                owner=owner,
                target=target,
                action=action["id"],
                details=details,
            )
        )
        return identity

    def begin(
        self, viewer: GuildViewer, key: str, channel: int, sheet_revision: int, prepared: PlayInput
    ) -> dict[str, Any]:
        prepared = PlayInput.model_validate_json(prepared.model_dump_json())
        if prepared.play not in PLAY_IDS:
            raise WorkflowError("UNSUPPORTED_RULE: this Play is not implemented in M2.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or sheet.revision != sheet_revision:
                raise WorkflowError("STALE_SHEET: refresh the Play wizard.")
            if sheet.frame_scrapped:
                raise WorkflowError(
                    "REQUIRED_FOLLOWUP: replace the scrapped Frame before new Plays."
                )
            work = t.m3["m3_required_work"]
            latest_work = {
                row["id"]: row
                for row in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.subject_id == str(viewer.user_id),
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }
            if any(
                row["state"] != "resolved" and json.loads(row["body_json"]).get("immediate")
                for row in latest_work.values()
            ):
                raise WorkflowError(
                    "REQUIRED_FOLLOWUP: resolve the immediate mechanical follow-up first."
                )
            if sheet.helpless_against:
                raise WorkflowError(
                    "UNSUPPORTED_RULE: recover from Helplessness before a new defensive Play."
                )
            profile_revision = c.scalar(
                sa.select(t.characters.c.revision).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            )
            if profile_revision != sheet.source_profile_revision:
                raise WorkflowError(
                    "STALE_PROFILE: active profile changed; canonical resources were preserved."
                )
            if HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("STALE_HANDLER: canonical Handler replacement needs review.")
            scene = self.scene(c, channel)
            if (
                viewer.user_id not in scene["participants"]
                or state.handler not in scene["participants"]
            ):
                raise WorkflowError("The acting Pilot and Handler must explicitly join this scene.")
            root_lock = self.lock(c, channel)
            parent = None
            if prepared.parent:
                parent = self.action(c, prepared.parent)
                if (
                    parent["channel_id"] != str(channel)
                    or not root_lock
                    or root_lock["state"] != "held"
                ):
                    raise WorkflowError("An escape Play must use its held parent scene.")
                choices = self.pending(c, parent["id"])
                required = next(
                    (
                        x
                        for x in choices
                        if x["kind"] in ("escape_play", "order_disobey")
                        and x["actor_id"] == str(viewer.user_id)
                    ),
                    None,
                )
                if required is None:
                    raise WorkflowError("Only the required player can make this response Play.")
                if required["kind"] == "order_disobey" and (
                    prepared.play != "disobey_orders"
                    or prepared.order_id != parent["data"]["order_id"]
                ):
                    raise WorkflowError(
                        "Receive Orders requires the actual Disobey Orders response."
                    )
                actions = t.m2["m2_actions"]
                if c.execute(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.parent_id == prepared.parent,
                        actions.c.state.not_in(("complete", "aborted")),
                    )
                ).first():
                    raise WorkflowError(
                        "A response Play already exists; resume it instead of creating another."
                    )
                if parent["data"].get("depth", 0) >= 8:
                    raise WorkflowError(
                        "UNSUPPORTED_RULE: nested response depth requires staff recovery."
                    )
            elif root_lock and root_lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the pending Play first.")
            if prepared.play == "flirt":
                if (
                    prepared.target == viewer.user_id
                    or str(prepared.target) not in state.sheets
                    or prepared.target not in scene["participants"]
                ):
                    raise WorkflowError("Choose another active human Pilot in this scene.")
            elif prepared.target is not None:
                raise WorkflowError("This implemented Play does not take a Pilot target.")
            if prepared.play == "engage" and not any(not x.damaged for x in sheet.assets):
                raise WorkflowError("No legal undamaged Asset is available for Engage.")
            if prepared.play == "disobey_orders":
                self.valid_order(c, state, viewer.user_id, channel, prepared.order_id)
            preview = PilotSheet.model_validate_json(sheet.model_dump_json())
            if prepared.identity:
                share = mark_identity(
                    preview, prepared.identity, prepared.gain, prepared.pair_share
                )
                if share and str(sheet.pair) not in state.sheets:
                    raise WorkflowError("The Pair must have an active sheet to receive Heat.")
            elif prepared.gain or prepared.pair_share:
                raise WorkflowError("Heat gain requires an eligible Identity.")
            spend_heat(preview, prepared.heat)
            identity = str(uuid4())
            data = {
                "prepared": prepared.model_dump(mode="json"),
                "sheet_revision": sheet_revision,
                "play": prepared.play,
                "participants": scene["participants"],
                "depth": parent["data"].get("depth", 0) + 1 if parent else 0,
                "handler": state.handler,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=prepared.parent,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            action = self.action(c, identity)
            if parent:
                self.save_action(c, action, state="ready_to_roll")
            else:
                table = t.m2["m2_locks"]
                values = {
                    "action_id": identity,
                    "state": "acquiring",
                    "body_json": "{}",
                    "lease_until": 0,
                    "claim_token": None,
                }
                if root_lock:
                    c.execute(
                        table.update()
                        .where(
                            table.c.campaign_id == self.store.campaign_id,
                            table.c.channel_id == str(channel),
                        )
                        .values(**values)
                    )
                else:
                    c.execute(
                        table.insert().values(
                            campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                        )
                    )
            self.event(
                c, viewer.user_id, key, "m2.play_confirmed", action_id=identity, play=prepared.play
            )
            return {"action_id": identity, "state": action["state"]}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.play_confirmed",
                {
                    "channel": channel,
                    "sheet_revision": sheet_revision,
                    "prepared": prepared.model_dump(mode="json"),
                },
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def pending(self, c: Connection, action_id: str) -> list[dict[str, Any]]:
        table = t.m2["m2_choices"]
        return [
            dict(x)
            for x in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.action_id == action_id,
                    table.c.state.in_(("pending", "submitted")),
                )
            ).mappings()
        ]

    def valid_order(
        self, c: Connection, state: GameState, owner: int, channel: int, identity: str | None
    ) -> dict[str, Any]:
        table = t.m2["m2_orders"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.target_id == str(owner),
                    table.c.channel_id == str(channel),
                    table.c.state == "disobey",
                )
            )
            .mappings()
            .first()
        )
        if row is None or not higher(state, int(row["issuer_id"]), owner):
            raise WorkflowError("A recorded direct order from a current superior is required.")
        if any(
            x.kind == "cannot_refuse_until_tag_resolved"
            and x.state == "pending"
            and x.owner == owner
            and x.target == int(row["issuer_id"])
            for x in state.obligations
        ):
            raise WorkflowError("COMPULSION: resolve the owed Tag before refusing this character.")
        return dict(row)

    def roll(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            if action["actor_id"] != str(viewer.user_id):
                raise WorkflowError("Only the acting Pilot can confirm this roll.")
            if action["data"]["receipt"]:
                return {"action_id": identity, "receipt": action["data"]["receipt"]}
            self.unpaused(c)
            lock = self.lock(c, action["channel_id"])
            if (
                not lock
                or lock["state"] != "held"
                or action["state"] not in ("acquiring", "ready_to_roll")
            ):
                raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no dice or Heat were consumed.")
            if action["data"]["play"] not in PLAY_IDS:
                raise WorkflowError("This action is diceless.")
            state = load_state(c, self.store.campaign_id)
            if HandlerService(self.store).current(c)[1].handler_id != state.handler:
                raise WorkflowError("STALE_HANDLER: staff recovery is required.")
            sheet = state.sheets[str(viewer.user_id)]
            if sheet.revision != action["data"]["sheet_revision"]:
                raise WorkflowError("STALE_SHEET: recover the unrolled action; no dice consumed.")
            prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
            if prepared.identity:
                share = mark_identity(sheet, prepared.identity, prepared.gain, prepared.pair_share)
                if share:
                    state.sheets[str(sheet.pair)].heat += share
                    state.sheets[str(sheet.pair)].revision += 1
            spend_heat(sheet, prepared.heat)
            faces = self.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise ValueError("Dice source returned invalid faces")
            receipt = {
                "id": str(uuid4()),
                "action_id": identity,
                "faces": list(faces),
                "heat": prepared.heat,
                "pre_total": sum(faces) + prepared.heat,
                "rng_source": self.rng_source,
                "rolled_utc": datetime.now(UTC).isoformat(),
                "ruleset": RULESET,
            }
            c.execute(
                t.m2["m2_receipts"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    action_id=identity,
                    id=receipt["id"],
                    body_json=json.dumps(receipt, sort_keys=True),
                )
            )
            action["data"]["receipt"] = receipt
            sheet.revision += 1
            self.save_action(c, action, state="tag_window")
            for person in action["data"]["participants"]:
                self.request(c, action, person, "tag_window")
            self.queue(
                c,
                action,
                "receipt",
                {"receipt": receipt, "callsign": sheet.callsign, "play": prepared.play},
            )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.rolled",
                state,
                action_id=identity,
                receipt_id=receipt["id"],
            )
            return {"action_id": identity, "receipt": receipt}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.rolled",
                {"action_id": identity},
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def choices(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            table = t.m2["m2_choices"]
            return [
                dict(x)
                for x in c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.actor_id == str(viewer.user_id),
                        table.c.state == "pending",
                    )
                ).mappings()
            ]

    def respond(
        self, viewer: GuildViewer, key: str, choice_id: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        from girlframe.services.m2_choices import ChoiceEngine

        answer = ChoiceAnswer.model_validate_json(answer.model_dump_json())

        def owned(c: Connection) -> dict[str, Any]:
            self.authorize(c, viewer)
            table = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == choice_id,
                        table.c.actor_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision belongs to another player or is unavailable.")
            action = self.action(c, row["action_id"])
            if (
                str(viewer.user_id) == str(action["data"]["handler"])
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError("The Handler appointment changed; staff recovery is required.")
            return dict(row)

        def authorize(c: Connection) -> None:
            owned(c)

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            row = owned(c)
            if row["state"] != "pending" or row["revision"] != revision:
                raise WorkflowError("STALE_CHOICE: reopen your current decisions.")
            action = self.action(c, row["action_id"])
            if action["state"] in ("complete", "aborted"):
                raise WorkflowError("This action no longer accepts decisions.")
            lock = self.lock(c, action["channel_id"])
            if not lock or lock["state"] != "held":
                raise WorkflowError("SCENE_LOCK_RECOVERY: decisions await a confirmed scene lock.")
            state = load_state(c, self.store.campaign_id)
            table = t.m2["m2_choices"]
            c.execute(
                table.update()
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == choice_id)
                .values(state="answered", revision=revision + 1)
            )
            action["data"]["choices"][row["kind"] + ":" + row["actor_id"]] = answer.model_dump(
                mode="json"
            )
            ChoiceEngine(self).apply(c, state, action, row, answer)
            self.save_action(c, action)
            event = self.event(
                c,
                viewer.user_id,
                key,
                "m2.choice_resolved",
                state,
                action_id=action["id"],
                choice_id=choice_id,
            )
            c.execute(
                t.m2["m2_responses"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    choice_id=choice_id,
                    actor_id=str(viewer.user_id),
                    answer_json=answer.model_dump_json(),
                    event_id=event,
                )
            )
            return {"action_id": action["id"], "state": action["state"], "choice_id": choice_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.choice_resolved",
                {
                    "choice_id": choice_id,
                    "revision": revision,
                    "answer": answer.model_dump(mode="json"),
                },
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def issue_order(
        self, viewer: GuildViewer, key: str, channel: int, target: int, text: str
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("Provide a direct order in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.scene(c, channel)
            if (
                viewer.user_id not in scene["participants"]
                or target not in scene["participants"]
                or str(target) not in state.sheets
                or not higher(state, viewer.user_id, target)
            ):
                raise WorkflowError(
                    "Only a current superior in this scene can issue a direct order."
                )
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the current action first.")
            identity, order_id = str(uuid4()), str(uuid4())
            c.execute(
                t.m2["m2_orders"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=order_id,
                    issuer_id=str(viewer.user_id),
                    target_id=str(target),
                    channel_id=str(channel),
                    body_json=json.dumps({"text": text}),
                    state="awaiting_response",
                )
            )
            data = {
                "play": "receive_orders",
                "order_id": order_id,
                "order_text": text,
                "participants": scene["participants"],
                "handler": state.handler,
                "depth": 0,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(target),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            table = t.m2["m2_locks"]
            values = {
                "action_id": identity,
                "state": "acquiring",
                "body_json": "{}",
                "lease_until": 0,
                "claim_token": None,
            }
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.event(c, viewer.user_id, key, "m2.order_issued", action_id=identity)
            return {"action_id": identity, "order_id": order_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m2.order_issued",
                {"channel": channel, "target": target, "text": text},
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Canonical state validation failed; contact staff without sharing private details."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def abort(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            if (
                not (viewer.is_administrator and self.store.policy.allow_guild_administrators)
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError(
                    "Only configured staff or the appointed Handler can recover an action."
                )

        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            if action["parent_id"]:
                raise WorkflowError("Recover the root action so its scene lock is restored safely.")
            lock = self.lock(c, action["channel_id"])
            if not lock or lock["action_id"] != identity or lock["state"] == "released":
                raise WorkflowError("STALE_ACTION: this action no longer owns the channel lock.")
            if action["state"] == "complete":
                raise WorkflowError(
                    "Completed effects remain canonical; use emergency restoration."
                )
            table = t.m2["m2_actions"]
            # Root abort also stops descendant decisions; existing receipts/spends remain immutable.
            rows = [
                dict(x)
                for x in c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == action["channel_id"],
                        table.c.state.not_in(("complete", "aborted")),
                    )
                ).mappings()
            ]
            for row in rows:
                child = self.action(c, row["id"])
                self.save_action(c, child, state="aborted")
                choices = t.m2["m2_choices"]
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.action_id == child["id"],
                        choices.c.state.in_(("pending", "submitted")),
                    )
                    .values(state="aborted")
                )
            if action["state"] == "complete":
                raise WorkflowError(
                    "Completed effects remain canonical; use emergency restoration."
                )
            self.queue(c, action, "aborted")
            locks = t.m2["m2_locks"]
            c.execute(
                locks.update()
                .where(locks.c.campaign_id == self.store.campaign_id, locks.c.action_id == identity)
                .values(state="releasing", lease_until=0, claim_token=None)
            )
            self.event(c, viewer.user_id, key, "m2.action_aborted", action_id=identity)
            return {
                "action_id": identity,
                "state": "aborted",
                "receipt_preserved": bool(action["data"]["receipt"]),
            }

        return self.store._write(
            viewer,
            key,
            "m2.action_aborted",
            {"action_id": identity},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            action = self.action(c, identity)
            if viewer.user_id not in action["data"]["participants"]:
                raise WorkflowError("This action is not visible to you.")
            result = action["data"]["result"] if action["state"] == "complete" else None
            parties = {int(action["actor_id"]), action["data"].get("prepared", {}).get("target")}
            if result and viewer.user_id not in parties:
                result = {k: v for k, v in result.items() if k in ("total", "tier")}
            return {
                "id": identity,
                "state": action["state"],
                "revision": action["revision"],
                "play": action["data"]["play"],
                "receipt": action["data"]["receipt"],
                "modifiers": [
                    {k: v for k, v in x.items() if k in ("source", "amount")}
                    for x in action["data"]["modifiers"]
                ],
                "result": result,
            }

    def rebuild(self) -> int:
        with self.store.transaction() as c:
            table = t.m2["m2_state_history"]
            row = (
                c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id)
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return 0
            state = GameState.model_validate_json(row["body_json"])
            view = t.m2["m2_state"]
            c.execute(view.delete().where(view.c.campaign_id == self.store.campaign_id))
            c.execute(
                view.insert().values(
                    campaign_id=self.store.campaign_id,
                    revision=state.revision,
                    body_json=state.model_dump_json(),
                )
            )
            self.store._audit(
                c,
                "system:local_operator",
                str(uuid4()),
                "m2.projection_rebuilt",
                {"game_revision": state.revision},
            )
            return state.revision

    def fulfill(
        self, viewer: GuildViewer, key: str, channel: int, obligation_id: str, text: str
    ) -> dict[str, Any]:
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("Describe the source-backed follow-through action.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.scene(c, channel)
            obligation = next(
                (
                    x
                    for x in state.obligations
                    if x.id == obligation_id and x.owner == viewer.user_id and x.state == "pending"
                ),
                None,
            )
            if obligation is None or obligation.kind not in ("flirt_followthrough", "reject_tag"):
                raise WorkflowError(
                    "This obligation has no implemented owner follow-through action."
                )
            if (
                viewer.user_id not in scene["participants"]
                or state.handler not in scene["participants"]
                or (
                    obligation.kind == "flirt_followthrough"
                    and obligation.target not in scene["participants"]
                )
            ):
                raise WorkflowError("The required actors must join this scene.")
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the current action first.")
            identity = str(uuid4())
            data = {
                "play": obligation.kind,
                "obligation_id": obligation_id,
                "context": text,
                "participants": scene["participants"],
                "handler": state.handler,
                "depth": 0,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            table = t.m2["m2_locks"]
            values = {
                "action_id": identity,
                "state": "acquiring",
                "body_json": "{}",
                "lease_until": 0,
                "claim_token": None,
            }
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.event(c, viewer.user_id, key, "m2.followthrough_confirmed", action_id=identity)
            return {"action_id": identity}

        return self.store._write(
            viewer,
            key,
            "m2.followthrough_confirmed",
            {"channel": channel, "obligation": obligation_id, "text": text},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def own_obligations(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return [
                x.model_dump(mode="json")
                for x in state.obligations
                if x.owner == viewer.user_id and x.state == "pending"
            ]

    def retry_recovery(
        self, viewer: GuildViewer, key: str, identity: str, *, restore_only: bool = False
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer, game=False)
            if (
                not (viewer.is_administrator and self.store.policy.allow_guild_administrators)
                and HandlerService(self.store).current(c)[1].handler_id != viewer.user_id
            ):
                raise WorkflowError("Only configured staff can reconcile deliveries or unlock.")

        def operation(c: Connection) -> dict[str, Any]:
            action = self.action(c, identity)
            if action["parent_id"]:
                raise WorkflowError("Recover the root scene action.")
            locks = t.m2["m2_locks"]
            current = self.lock(c, action["channel_id"])
            if not current or current["action_id"] != identity or current["state"] == "released":
                raise WorkflowError("STALE_ACTION: this action no longer owns the channel lock.")
            if restore_only:
                if action["state"] not in ("complete", "aborted"):
                    raise WorkflowError(
                        "Abort the pending root action before emergency restoration."
                    )
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id, locks.c.action_id == identity
                    )
                    .values(state="releasing", lease_until=0, claim_token=None)
                )
            else:
                jobs = t.m2["m2_outbox"]
                c.execute(
                    jobs.update()
                    .where(
                        jobs.c.campaign_id == self.store.campaign_id,
                        jobs.c.action_id == identity,
                        jobs.c.state == "review",
                    )
                    .values(state="pending", lease_until=0, claim_token=None)
                )
                row = self.lock(c, action["channel_id"])
                if row and row["state"] == "review":
                    c.execute(
                        locks.update()
                        .where(
                            locks.c.campaign_id == self.store.campaign_id,
                            locks.c.action_id == identity,
                        )
                        .values(
                            state="releasing"
                            if action["state"] in ("complete", "aborted")
                            else "acquiring",
                            lease_until=0,
                            claim_token=None,
                        )
                    )
            self.event(
                c,
                viewer.user_id,
                key,
                "m2.staff_reconciliation",
                action_id=identity,
                restore_only=restore_only,
            )
            return {"action_id": identity, "restore_only": restore_only}

        return self.store._write(
            viewer,
            key,
            "m2.staff_reconciliation",
            {"action_id": identity, "restore_only": restore_only},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def close_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.authorize(c, viewer)
            self.store.administrator(viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.scene(c, channel)
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError(
                    "Resolve or recover the pending action before closing this scene."
                )
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(open=False)
            )
            self.event(c, viewer.user_id, key, "m2.scene_closed", channel=channel)
            return {"channel": channel, "closed": True}

        return self.store._write(
            viewer,
            key,
            "m2.scene_closed",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def scene_info(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            scene = self.scene(c, channel)
            lock = self.lock(c, channel)
            if viewer.user_id not in scene["participants"]:
                return {"participants": [], "lock": None, "joined": False}
            state = load_state(c, self.store.campaign_id)
            return {
                "pilots": [uid for uid in scene["participants"] if str(uid) in state.sheets],
                "labels": {
                    str(uid): state.sheets[str(uid)].callsign
                    if str(uid) in state.sheets
                    else "Handler"
                    for uid in scene["participants"]
                },
                "participants": scene["participants"],
                "lock": {k: lock[k] for k in ("action_id", "state")} if lock else None,
                "joined": True,
            }

    def decision(self, viewer: GuildViewer, choice_id: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer, game=False)
            table = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == choice_id,
                        table.c.actor_id == str(viewer.user_id),
                        table.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("This decision is no longer available to you.")
            action = self.action(c, row["action_id"])
            state = load_state(c, self.store.campaign_id)
            actor = state.sheets[str(action["actor_id"])]
            own = state.sheets.get(str(viewer.user_id))
            # Return only selectable entities needed by this decision, never another private sheet.
            body = json.loads(row["body_json"])
            tags = [
                x.model_dump(mode="json")
                for x in actor.tags
                if viewer.user_id in x.observers or viewer.user_id == actor.owner
            ]
            return dict(row) | {
                "body": body,
                "play": action["data"]["play"],
                "result": action["data"]["result"],
                "actor": actor.owner,
                "tags": tags,
                "own": own.model_dump(mode="json") if own else None,
                "participants": action["data"]["participants"],
                "pilots": [
                    uid for uid in action["data"]["participants"] if str(uid) in state.sheets
                ],
                "labels": {
                    str(uid): state.sheets[str(uid)].callsign
                    for uid in action["data"]["participants"]
                    if str(uid) in state.sheets
                },
                "parent": action["id"],
                "channel": int(action["channel_id"]),
                "order_text": action["data"].get("order_text"),
                "context": action["data"].get("context"),
                "prepared": {
                    k: v
                    for k, v in action["data"].get("prepared", {}).items()
                    if k in ("order_id", "target")
                },
            }

    def recover_helpless(
        self, viewer: GuildViewer, key: str, revision: int, context: str, asset: str | None
    ) -> dict[str, Any]:
        if not context.strip() or len(context) > 1200:
            raise WorkflowError("Describe the moment alone in which you compose yourself.")

        def operation(c: Connection) -> dict[str, Any]:
            self.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or sheet.revision != revision or not sheet.helpless_against:
                raise WorkflowError("STALE_SHEET: no matching Helpless recovery is available.")
            scenes = t.m2["m2_scenes"]
            for row in c.execute(
                sa.select(scenes).where(
                    scenes.c.campaign_id == self.store.campaign_id, scenes.c.open.is_(True)
                )
            ).mappings():
                if viewer.user_id in json.loads(row["participants_json"]):
                    lock = self.lock(c, row["channel_id"])
                    if lock and lock["state"] != "released":
                        raise WorkflowError(
                            "Resolve the immediate scene action before taking a moment alone."
                        )
            girls = [x for x in sheet.assets if x.family == "girl"]
            if girls and all(x.damaged for x in girls):
                chosen = next((x for x in girls if x.id == asset), None)
                if chosen is None:
                    raise WorkflowError("Choose one damaged Girl Asset to recover.")
                chosen.damaged = False
            elif asset is not None:
                raise WorkflowError("Recover an Asset only if all Girl Assets are damaged.")
            sheet.helpless_against = ()
            sheet.revision += 1
            self.event(c, viewer.user_id, key, "m2.helpless_recovered", state, owner=viewer.user_id)
            return {"owner": viewer.user_id, "revision": sheet.revision}

        return self.store._write(
            viewer,
            key,
            "m2.helpless_recovered",
            {"revision": revision, "context": context, "asset": asset},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )

    def leave_scene(self, viewer: GuildViewer, key: str, channel: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            scene = self.scene(c, channel)
            lock = self.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Resolve the pending Play before leaving this scene.")
            people = [x for x in scene["participants"] if x != viewer.user_id]
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=scene["revision"] + 1)
            )
            self.event(c, viewer.user_id, key, "m2.scene_left", channel=channel)
            return {"channel": channel, "participants": people}

        return self.store._write(
            viewer,
            key,
            "m2.scene_left",
            {"channel": channel},
            operation,
            auto_audit=False,
            authorize=lambda c: self.authorize(c, viewer),
        )
