"""Retryable delivery. Acknowledgement loss may duplicate a Discord post."""

import asyncio
from typing import Protocol

from girlframe.engine.rolls import RollReceipt
from girlframe.services.ledger import CampaignLedger


class RollDeliveryGateway(Protocol):
    async def reconcile(self, channel_id: int, receipt_id: str) -> int | None: ...
    async def send(self, channel_id: int, receipt: RollReceipt, nonce: str) -> int: ...


class OutboxWorker:
    def __init__(self, ledger: CampaignLedger):
        self.ledger = ledger

    async def deliver_one(self, gateway: RollDeliveryGateway) -> bool:
        job = await asyncio.to_thread(self.ledger.claim_delivery)
        if job is None:
            return False
        try:
            receipt = RollReceipt.model_validate_json(job["receipt_json"])
            identity = (
                await gateway.reconcile(int(job["channel_id"]), receipt.id)
                if job["attempts"] > 1
                else None
            )
            if identity is None:
                identity = await gateway.send(int(job["channel_id"]), receipt, job["nonce"])
        except Exception:
            await asyncio.to_thread(self.ledger.mark_delivery, job, None)
            return False
        # A crash here leaves a lease; recovery reconciles the stable receipt first.
        await asyncio.to_thread(self.ledger.mark_delivery, job, identity)
        return True
