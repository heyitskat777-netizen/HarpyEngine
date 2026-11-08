"""Owned paid discharge, actual immutable archive and original receipt history."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_retirement as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import RetirementReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class RetirementService(RequisitionService):
    def retire(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        account: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy")
            if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the actual Girl's human owner may confirm Retirement.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            if confirmed is not True:
                raise WorkflowError("Explicitly confirm twenty Permissions and this career ending.")
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            if any(x.active and actor in (x.traveler, x.supervisor) for x in state.escort_journeys):
                raise WorkflowError("Complete the actual supervised journey before Retirement.")
            if any(x.held and actor in (x.actor, x.target) for x in state.enforcer_grasps):
                raise WorkflowError("End the actual grasp before voluntary Retirement.")
            placement = next((x for x in state.placements if x.actor == actor), None)
            if placement is not None and (
                placement.custody is not None
                or placement.subsumed
                or not placement.vitals_active
                or placement.incapacitated
            ):
                raise WorkflowError(
                    "Resolve actual custody, extraction or medical care before Retirement."
                )
            identity, archive, source = str(uuid4()), str(uuid4()), str(uuid4())
            from girlframe.engine.m3_offered_requisition_state import require_request

            require_request(state, actor)
            prepare_payment(self.game, c, state, viewer, actor, "retirement", 20)
            paid = rules.pay(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                account,
                identity,
                archive,
                source,
            )
            ended = end_in_transaction(
                c,
                self.game,
                paid,
                actor,
                reason="retirement",
                source_event=source,
                account=account,
                archive_id=archive,
            )
            ended.facts.append(
                dict(
                    kind="retirement_discharge",
                    actor=actor.model_dump_json(),
                    source_event=source,
                    archive=archive,
                    destination="home_offstage",
                    surgeries="reversed",
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.retirement_purchased",
                ended,
                event_id=source,
                requisition_id=identity,
                cost=20,
                archive_id=archive,
            )
            synchronize_end(c, self.game, ended.career_archives[-1])
            return dict(id=identity, archive_id=archive, cost=20, ending="retirement")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.retirement_purchase",
                dict(
                    actor=actor.model_dump(mode="json"),
                    expected=expected,
                    account=account,
                    confirmed=confirmed,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def receipt(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            receipt = next(
                (
                    x
                    for x in state.requisitions
                    if isinstance(x, RetirementReceipt)
                    and x.id == identity
                    and x.actor.entity == str(viewer.user_id)
                ),
                None,
            )
            if receipt is None:
                raise WorkflowError("This original Retirement receipt belongs to another human.")
            purchase_proof(c, self.store, receipt)
            archive = next(
                (
                    x
                    for x in state.career_archives
                    if x.id == receipt.archive_id
                    and x.actor == receipt.actor
                    and x.ending == "retirement"
                    and x.source_event == receipt.source_event
                ),
                None,
            )
            if archive is None:
                raise WorkflowError("SOURCE_RETIREMENT_MISSING: recover the original paid ending.")
            return dict(
                receipt=receipt.model_dump(mode="json"),
                archive_id=archive.id,
                ending=archive.ending,
            )

    def retirement_history(self, viewer: GuildViewer) -> list[dict[str, str]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return [
                dict(id=x.id, archive_id=x.archive_id)
                for x in load_state(c, self.store.campaign_id).requisitions
                if isinstance(x, RetirementReceipt) and x.actor.entity == str(viewer.user_id)
            ]
