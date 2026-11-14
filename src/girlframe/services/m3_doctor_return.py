"""Mandatory Wings return: actual custody, an exact engineer package and donor decision."""

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_doctor as doctor
from girlframe.engine import m3_doctor_return as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_off_duty import Period
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_doctor_procedures import wings_thresholds
from girlframe.services.m3_doctor_wings_void import prove_loss_source as prove_loan
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_scene_requisitions import _activation
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KIND = "doctor_wings_return"


def _identity(loan: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:doctor-wings-return:" + loan))


def synchronize_pending(
    c: Connection,
    game: "GameService",
    state: GameState,
    initial: GameState,
    period: Period,
    source: str,
) -> None:
    work = t.m3["m3_required_work"]
    for value in doctor.values(state, "doctor_loan", doctor.Loan):
        if value.phase != "borrowed" or not any(
            x.id == value.id for x in doctor.values(initial, "doctor_loan", doctor.Loan)
        ):
            continue
        identity = _identity(value.id)
        if c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == identity
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, off_duty_id=period.id),
            identity,
            int(value.donor.entity),
            int(value.donor.entity),
            KIND,
            dict(
                source_pdf=72,
                loan=value.id,
                loan_event=value.source_event,
                period_event=source,
                immediate=True,
            ),
            source,
        )


def _digest(package: rules.Package) -> str:
    return hashlib.sha256(package.model_dump_json().encode()).hexdigest()


class ReturnService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _handler(self, c: Connection) -> int | None:
        return HandlerService(self.store).current(c)[1].handler_id

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                    table.c.kind == KIND,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Open the actual mandatory Wings return")
        return dict(row)

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        event: str,
        body: dict[str, Any],
        *,
        resolved: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "event_id", "body_json", "state")
                },
                revision=row["revision"] + 1,
                event_id=event,
                body_json=json.dumps(body, sort_keys=True),
                state="resolved" if resolved else "pending",
            )
        )

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, doctor.Loan, dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        row = self._row(c, identity)
        body = dict(json.loads(row["body_json"]))
        state = load_state(c, self.store.campaign_id)
        value = next(
            (
                x
                for x in doctor.values(state, "doctor_loan", doctor.Loan)
                if x.id == body.get("loan")
            ),
            None,
        )
        if value is None or viewer.user_id not in (
            int(value.doctor.entity),
            int(value.donor.entity),
            self._handler(c),
        ):
            raise WorkflowError(
                "This return is private to its original participants and current Handler"
            )
        if (
            identity != _identity(value.id)
            or value.source_event != body.get("loan_event")
            or row["owner_id"] != value.donor.entity
            or row["subject_id"] != value.donor.entity
        ):
            raise WorkflowError("Recover the original owned Wings return source")
        raw = c.scalar(
            sa.select(t.m3["m3_off_duty"].c.body_json).where(
                t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                t.m3["m3_off_duty"].c.id == row["off_duty_id"],
            )
        )
        activation = _activation(c, self.store, Period.model_validate_json(raw)) if raw else None
        if (
            activation is None
            or activation[1] != body.get("period_event")
            or not any(
                x.id == value.id for x in doctor.values(activation[0], "doctor_loan", doctor.Loan)
            )
        ):
            raise WorkflowError("Recover the actual next Off-Duty return boundary")
        prove_loan(self.game, c, state, value.source_event, value.id, value.donor)
        return row, state, value, body

    def _package(
        self,
        c: Connection,
        state: GameState,
        value: doctor.Loan,
        account: str,
        event: str,
        handler: int,
        replace: str | None,
    ) -> rules.Package:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Describe the actual engineer access/recovery and exact destination package"
            )
        try:
            source = rules.locate(state, value)
            destination = rules.frame(state, value.donor)
            if source.item:
                prove_item(c, self.game, state, source.item)
            from girlframe.engine.m3_janus_storage import active
            from girlframe.engine.m3_supply_drop import current_asset, live

            if any(x.asset == source.asset.id for x in active(state, source.actor)) or any(
                current_asset(state, x) == source.asset.id for x in live(state, source.actor)
            ):
                raise WorkflowError(
                    "SOURCE_PORT_REQUIRED: unplug/resolve the exact stored-Void "
                    "or temporary component source first"
                )
            if replace:
                from girlframe.engine.m3_budget_removal import blocked

                if replace in blocked(state, value.donor):
                    raise WorkflowError(
                        "SOURCE_PORT_REQUIRED: preserve the selected cap component's own source"
                    )
                wings_thresholds(state, value.donor, replace)
            if source.kind == "gorgon":
                assert state.world is not None
                gorgon = next(x for x in state.world.gorgons if x.id == source.actor.entity)
                threshold = next(
                    x
                    for x in state.void_thresholds
                    if x.actor == value.doctor and x.gorgon == source.actor
                )
                _, converted = snapshots(self.game, c, threshold.response_event or "")
                born = (
                    next((x for x in converted.world.gorgons if x.id == gorgon.id), None)
                    if converted.world
                    else None
                )
                if (
                    threshold.source_event is None
                    or born is None
                    or not any(x.id == value.asset for x in born.assets)
                ):
                    raise WorkflowError(
                        "SOURCE_PORT_REQUIRED: recover the actual original "
                        "converted graft and source"
                    )
                destination_view = resolve(
                    state,
                    value.donor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if (
                    (gorgon.alive and gorgon.gorgon_class != "benevolent")
                    or gorgon.cell is None
                    or destination_view.frame_cell != gorgon.cell
                ):
                    raise WorkflowError(
                        "SOURCE_PORT_REQUIRED: recover actual engineers access to this "
                        "hostile/custodial body, or the known receiving Frame location; "
                        "defeated or benevolent co-located bodies have an actual recovery port"
                    )
            package = rules.Package(
                loan=value.id,
                source=source,
                destination=value.donor,
                frame=destination,
                replace=replace,
                account=account.strip(),
                quote_event=event,
                handler=handler,
                game_revision=state.revision,
            )
            rules.transfer(state, package, "package-preview", int(value.donor.entity))
            return package
        except ValueError as error:
            raise WorkflowError(str(error)) from error

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, value, body = self._source(c, viewer, identity)
            source = None
            blocked = None
            if value.phase == "borrowed":
                try:
                    source = rules.locate(state, value).model_dump(mode="json")
                    self._package(
                        c,
                        state,
                        value,
                        "Preview actual engineer access and receiving package",
                        "preview",
                        self._handler(c) or 0,
                        None,
                    )
                except (ValueError, WorkflowError) as error:
                    blocked = str(error)
            from girlframe.engine.m3_assets import can_replace_at_limit
            from girlframe.engine.m3_budget_removal import blocked as blocked_assets

            replacements = []
            donor_sheet = state.sheets.get(value.donor.entity)
            if donor_sheet and donor_sheet.character_id == value.donor.incarnation:
                forbidden = blocked_assets(state, value.donor)
                forbidden.update(
                    {
                        x.asset: "borrowed"
                        for x in doctor.values(state, "doctor_loan", doctor.Loan)
                        if x.doctor == value.donor and x.phase == "borrowed"
                    }
                )
                replacements = [
                    dict(id=x.id, name=x.name)
                    for x in donor_sheet.assets
                    if x.family == "frame"
                    and x.id not in forbidden
                    and can_replace_at_limit(donor_sheet, x)
                ]
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                loan=value.model_dump(mode="json"),
                custody=source,
                blocked=blocked,
                package=body.get("package"),
                replacements=replacements,
                destination_frame=donor_sheet.frame if donor_sheet else None,
                can_quote=row["state"] == "pending" and viewer.user_id == self._handler(c),
                can_confirm=row["state"] == "pending"
                and viewer.user_id == int(value.donor.entity)
                and bool(body.get("package")),
                can_read=True,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        latest = {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                .order_by(table.c.revision)
            ).mappings()
        }
        state = load_state(c, self.store.campaign_id)
        loans = {x.id: x for x in doctor.values(state, "doctor_loan", doctor.Loan)}
        result = []
        for row in latest.values():
            value = loans.get(json.loads(row["body_json"]).get("loan"))
            if (
                row["state"] == "pending"
                and value
                and viewer.user_id
                in (int(value.doctor.entity), int(value.donor.entity), self._handler(c))
            ):
                result.append(
                    dict(
                        id=row["id"],
                        kind=KIND,
                        label="Borrowed Wings — actual component return",
                        revision=row["revision"],
                        actionable=viewer.user_id == self._handler(c)
                        or (
                            viewer.user_id == int(value.donor.entity)
                            and bool(json.loads(row["body_json"]).get("package"))
                        ),
                    )
                )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def quote(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        account: str,
        *,
        replace: str | None = None,
    ) -> dict[str, Any]:
        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, value, body = self._source(c, viewer, identity)
            if viewer.user_id != self._handler(c):
                raise WorkflowError("The actual current Handler records the engineer package")
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != game_revision
            ):
                raise WorkflowError("STALE_RETURN: reopen the actual return and current custody")
            event = str(uuid4())
            package = self._package(c, state, value, account, event, viewer.user_id, replace)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.doctor_return_quoted",
                event_id=event,
                work_id=identity,
                package_sha256=_digest(package),
            )
            self._save(c, row, event, body | dict(package=package.model_dump(mode="json")))
            return dict(id=identity, state="quoted")

        return self.store._write(
            viewer,
            key,
            "m3.doctor_return_quoted",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                account=account,
                replace=replace,
            ),
            apply,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "playbooks"),
        )

    def confirm(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, game_revision: int
    ) -> dict[str, Any]:
        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, value, body = self._source(c, viewer, identity)
            if viewer.user_id != int(value.donor.entity):
                raise WorkflowError(
                    "Only the original donor confirms the actual receiving Frame package"
                )
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != game_revision
                or not body.get("package")
            ):
                raise WorkflowError("STALE_RETURN: reopen the exact current return package")
            package = rules.Package.model_validate(body["package"])
            quote = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == package.quote_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                quote is None
                or quote["kind"] != "m3.doctor_return_quoted"
                or quote["actor_id"] != str(package.handler)
                or json.loads(quote["payload_json"]).get("package_sha256") != _digest(package)
                or package.handler != self._handler(c)
            ):
                raise WorkflowError("Recover the actual current Handler's immutable exact quote")
            current = self._package(
                c,
                state,
                value,
                package.account,
                package.quote_event,
                package.handler,
                package.replace,
            )
            if current != package:
                raise WorkflowError("STALE_RETURN: the exact original package changed")
            event = str(uuid4())
            updated = rules.transfer(state, package, event, viewer.user_id)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.doctor_wings_returned",
                updated,
                event_id=event,
                work_id=identity,
                loan=value.id,
                quote_event=package.quote_event,
            )
            self._save(c, row, event, body | dict(return_event=event), resolved=True)
            from girlframe.services.m3_asset_loss import create_loss_work

            subjects = {value.donor}
            if package.source.actor.kind == "pilot":
                subjects.add(package.source.actor)
            for actor in subjects:
                create_loss_work(
                    self.game,
                    c,
                    state,
                    updated,
                    scope=row,
                    actor=actor,
                    event=event,
                    reason="doctor_wings_return",
                    source_id=value.id,
                )
            return dict(id=identity, state="resolved", return_event=event)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_wings_returned",
            dict(id=identity, revision=revision, game_revision=game_revision),
            apply,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(c, viewer, "playbooks"),
        )


def prove_loss_source(
    game: "GameService", c: Connection, state: GameState, event: str, identity: str, actor: ActorRef
) -> dict[str, Any]:
    before, born = snapshots(game, c, event)
    receipt = next(
        (
            rules.Receipt.model_validate_json(x["body"])
            for x in born.facts
            if x.get("kind") == "doctor_wings_return_receipt" and x.get("id") == identity
        ),
        None,
    )
    if (
        receipt is None
        or receipt.event != event
        or actor not in (receipt.package.destination, receipt.package.source.actor)
    ):
        raise WorkflowError("Recover the actual source-owned component return receipt")
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        audit is None
        or audit["kind"] != "m3.doctor_wings_returned"
        or audit["actor_id"] != str(receipt.confirmed_by)
    ):
        raise WorkflowError("Recover the actual original donor return confirmation")
    try:
        expected = rules.transfer(before, receipt.package, event, receipt.confirmed_by)
    except ValueError as error:
        raise WorkflowError("Recover the actual before/after component custody") from error
    if (
        expected.sheets != born.sheets
        or expected.world != born.world
        or expected.held_items != born.held_items
        or expected.item_transfers != born.item_transfers
        or doctor.values(expected, "doctor_loan", doctor.Loan)
        != doctor.values(born, "doctor_loan", doctor.Loan)
        or next(
            (
                x
                for x in expected.facts
                if x.get("kind") == "doctor_wings_return_receipt" and x.get("id") == identity
            ),
            None,
        )
        != next(
            (
                x
                for x in born.facts
                if x.get("kind") == "doctor_wings_return_receipt" and x.get("id") == identity
            ),
            None,
        )
    ):
        raise WorkflowError("Preserve the one real source removal and exact receiving component")
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(piloting=actual.piloting, in_battle=None, source_action=None)
