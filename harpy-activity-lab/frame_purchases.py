"""Use HarpyEngine's owned Asset Installment and original receipts."""

import json

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import Installation
from girlframe.services.m3_enforcer_requisitions import EnforcerRequisitionService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError


class FramePurchases:
    def __init__(self, game):
        self.service = RequisitionService(game)
        self.enforcer = EnforcerRequisitionService(game)

    def view(self, viewer):
        try:
            view = self.service.activity_offer(viewer)
            acquisition = self.enforcer.acquisition_view(viewer)
        except WorkflowError as error:
            return {"reason": str(error)}
        return {
            **{
                key: view[key]
                for key in (
                    "actor",
                    "source_sha256",
                    "permissions",
                    "asset_installment_price",
                    "asset_count",
                    "frame_capacity",
                    "replacement_options",
                    "catalog",
                )
            },
            "receipts": self.service.installation_history(viewer),
            "abilities": {
                key: acquisition[key]
                for key in ("actor", "source_sha256", "kind", "price", "rules", "enforcer_rules")
            },
        }

    def perform(self, viewer, key, data):
        if data.keys() != {"actor", "expected", "choice"} or not isinstance(
            data["expected"], str
        ):
            raise ValueError("Reopen your current Frame requisition form.")
        return self.service.buy(
            viewer,
            key,
            ActorRef.model_validate(data["actor"]),
            data["expected"],
            Installation.model_validate_json(json.dumps(data["choice"])),
        )

    def acquire(self, viewer, key, data):
        if (
            data.keys() != {"actor", "expected", "kind", "rule", "account", "confirmed"}
            or any(not isinstance(data[field], str) for field in ("expected", "kind", "rule", "account"))
            or data["kind"] not in ("ability_unlock", "frame_grafting")
            or not 1 <= len(data["account"].strip()) <= 1200
            or data["confirmed"] is not True
        ):
            raise ValueError("Review and confirm the price on your current Frame acquisition form.")
        return self.enforcer.buy_rule(
            viewer,
            key,
            ActorRef.model_validate(data["actor"]),
            data["expected"],
            data["kind"],
            data["rule"],
            data["account"],
        )
