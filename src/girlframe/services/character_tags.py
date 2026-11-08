"""Durable, cosmetic character tags. Discord effects are not database transactions."""

import asyncio
import json
from typing import Literal, Protocol

from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class TagSyncIssue(WorkflowError):
    """Safe operational message, never a raw provider response."""


class RoleCreationRefused(TagSyncIssue):
    """Known no-effect Discord refusal; role creation may be retried."""


class CharacterTagGateway(Protocol):
    async def member_ready(self, owner: int) -> None: ...
    async def safe_role_exists(self, identity: int, label: str | None = None) -> bool: ...
    async def create_tag_role(self, label: str) -> int: ...
    async def apply_roles(self, owner: int, desired: set[int], managed: dict[int, str]) -> None: ...
    async def nickname(
        self, owner: int, callsign: str
    ) -> Literal["updated", "unchanged", "owner", "hierarchy"]: ...


class CharacterTagSynchronizer:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.lock = asyncio.Lock()

    async def _role(self, viewer: GuildViewer, key: str, gateway: CharacterTagGateway) -> int:
        for _ in range(2):
            state, identity = await asyncio.to_thread(self.store.claim_role, viewer, key)
            if state == "uncertain":
                raise TagSyncIssue(
                    "Role creation outcome needs administrator review; no duplicate was created."
                )
            if state == "ready":
                assert identity is not None
                if await gateway.safe_role_exists(identity, key.split(":", 1)[1]):
                    return identity
                await asyncio.to_thread(self.store.invalidate_role, viewer, key, identity)
                continue
            try:
                identity = await gateway.create_tag_role(key.split(":", 1)[1])
            except RoleCreationRefused:
                await asyncio.to_thread(self.store.record_role, viewer, key, None)
                raise
            except Exception:
                raise TagSyncIssue(
                    "Role creation outcome is unknown; ask the administrator to inspect it."
                ) from None
            await asyncio.to_thread(self.store.record_role, viewer, key, identity)
            if await gateway.safe_role_exists(identity, key.split(":", 1)[1]):
                return identity
            raise TagSyncIssue("The created role disappeared. Retry /character sync.")
        raise TagSyncIssue("A managed role changed during synchronization. Retry /character sync.")

    async def sync(self, viewer: GuildViewer, gateway: CharacterTagGateway) -> str:
        async with self.lock:
            job = await asyncio.to_thread(self.store.sync_job, viewer)
            if job is None:
                return "No Discord-tag job is pending. Save a draft or use /character sync."
            if job["state"] == "complete":
                return str(job["warning"]) or "Character Discord tags are already synchronized."
            try:
                draft = await asyncio.to_thread(
                    self.store.cosmetic_draft, viewer, json.loads(job["desired_json"])
                )
                await gateway.member_ready(viewer.user_id)
            except Exception:
                message = (
                    "Discord tags pending: check server membership "
                    "and reopen the character dropdowns."
                )
                await asyncio.to_thread(
                    self.store.finish_sync, viewer, job["revision"], False, message
                )
                return message
            warnings = []
            roles_done = False
            try:
                girl = await self._role(viewer, "girl:" + draft.girl_playbook, gateway)
                frame = await self._role(viewer, "frame:" + draft.frame_playbook, gateway)
                managed = await asyncio.to_thread(self.store.managed_role_labels, viewer)
                await gateway.apply_roles(viewer.user_id, {girl, frame}, managed)
                roles_done = True
            except TagSyncIssue as error:
                warnings.append(str(error))
            except Exception:
                warnings.append("Roles pending: check Manage Roles and the bot's role position.")
            nickname_done = False
            nickname_message = ""
            try:
                result = await gateway.nickname(viewer.user_id, draft.callsign)
                if result == "owner":
                    warnings.append(
                        "Discord prevents bots renaming the server owner; "
                        "set that nickname manually."
                    )
                    nickname_done = True  # Terminal platform restriction, not a claimed rename.
                elif result == "hierarchy":
                    warnings.append(
                        "Nickname pending: move the bot's role above the member's highest role."
                    )
                else:
                    nickname_done = True
                    nickname_message = (
                        "Server nickname matches the callsign. "
                        if draft.callsign
                        else "Server nickname cleared for the recorded name removal. "
                    )
            except TagSyncIssue as error:
                warnings.append(str(error))
            except Exception:
                warnings.append("Nickname pending: check Manage Nicknames and role hierarchy.")
            message = (
                "Character roles synchronized. " if roles_done else "Character roles pending. "
            )
            message += nickname_message + " ".join(warnings)
            current = await asyncio.to_thread(
                self.store.finish_sync,
                viewer,
                job["revision"],
                roles_done and nickname_done,
                message,
            )
            if not current:
                return "A newer draft was saved during sync; its Discord tags remain queued."
            return message
