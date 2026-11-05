"""Source-bound current Handler decisions use the normal owned Tag/outcome pipeline."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_adjudication as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_adjudication_state import Decision, Required
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_lobotomy import blocked_play
from girlframe.engine.m3_policy import RULESET
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prepare_required(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    source: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    sheet = state.sheets.get(str(viewer.user_id))
    prohibition = blocked_play(sheet, prepared.play) if sheet else None
    if prohibition is None:
        return None
    if prepared.play not in ("defeat", "go_off_duty", "void_observation"):
        raise WorkflowError("This original Girl cannot roll that Play after actual surgery.")
    if prepared.heat or prepared.identity or prepared.gain or prepared.pair_share:
        raise WorkflowError(
            "A mandatory no-roll adjudication cannot spend Heat or mark an Identity."
        )
    if prepared.play == "defeat":
        from girlframe.services.m3_defeat import prepare

        source = source or prepare(game, c, viewer, prepared, state)
        if source.get("source_work"):
            from girlframe.services.m3_defeat import work

            work_row = work(game, c, source["source_work"])
            kind, identity, revision = "defeat_work", work_row["id"], work_row["revision"]
        else:
            choices = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == game.store.campaign_id,
                        choices.c.id == source.get("source_request"),
                        choices.c.state.in_(("pending", "submitted")),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("Recover the actual pending mandatory Defeat source.")
            kind, identity, revision = "defeat_response", row["id"], 1
    else:
        from girlframe.services.m3_play_support import periods
        from girlframe.services.m3_play_support import prepare as prepare_period

        source = source or prepare_period(game, c, viewer, prepared)
        period = periods(game)._get(c, source["period_id"])
        kind, identity, revision = "off_duty", period.id, period.revision
    approval = game.store.policy.m3_approval
    if approval is None or state.handler is None:
        raise WorkflowError("Mandatory adjudication requires the actual approved M3 subsystem.")
    from girlframe.services.m3_medical import MedicalService

    required = Required.model_validate(
        dict(
            play=prepared.play,
            actor=current_ref(state, viewer.user_id),
            handler=active_handler(state),
            gm_controller=state.handler,
            appointment=MedicalService(game.store)._handler(c)[1],
            prohibition=prohibition,
            source_kind=kind,
            source_id=identity,
            source_revision=revision,
            registry=approval.registry_sha256,
        )
    )
    verify(game, c, state, required)
    return required.model_dump(mode="json")


def verify(game: "GameService", c: Connection, state: GameState, required: Required) -> None:
    rules.validate(state, required)
    from girlframe.services.m3_medical import MedicalService

    gm, appointment = MedicalService(game.store)._handler(c)
    if (required.adjudicator is None and gm != required.controller) or (
        required.appointment is not None and appointment != required.appointment
    ):
        raise WorkflowError("Recover the actual appointed human GM for this manual decision.")
    approval = game.store.policy.m3_approval
    if approval is None or approval.registry_sha256 != required.registry:
        raise WorkflowError("M3_POLICY_CHANGED: recover the original required adjudication.")
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == required.prohibition.source_event,
        )
    )
    proof = GameState.model_validate_json(raw) if raw else None
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == required.prohibition.source_event,
        )
    ).first()
    if proof is None or event is None or event.kind != "m3.punishment_applied":
        raise WorkflowError("Recover the actual original surgery source before adjudicating.")
    surgery = next((x for x in proof.lobotomies if x.id == required.prohibition.surgery), None)
    if (
        surgery is None
        or surgery.phase != "applied"
        or surgery.subject
        != (
            next(x.origin for x in state.harpy_states if x.id == required.actor.entity)
            if required.play == "harpy_defeat"
            else required.actor
        )
        or (event.actor_id != surgery.inflictor.entity)
    ):
        raise WorkflowError("The actual source surgery and original patient have changed.")
    if required.source_kind == "harpy_defeat_work":
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        service = HarpyDefeatService(game.store, game=game)
        harpy_row, _, actor = service._source(c, required.source_id)
        declarations = [
            x
            for x in state.harpy_defeat_declarations
            if x.work == required.source_id and x.actor == actor
        ]
        if (
            harpy_row["revision"] != required.source_revision
            or actor != required.actor
            or len(declarations) != 1
            or declarations[0].gm_controller != required.controller
            or declarations[0].adjudicator != required.adjudicator
            or declarations[0].appointment != required.appointment
        ):
            raise WorkflowError("Recover the actual original Harpy's mandatory source and judge.")
        service._current(c, game.action(c, declarations[0].id), unrolled=True)
    elif required.source_kind == "defeat_work":
        from girlframe.services.m3_defeat import work

        work_row = work(game, c, required.source_id)
        if (
            work_row["revision"] != required.source_revision
            or work_row["owner_id"] != required.actor.entity
            or json.loads(work_row["body_json"]).get("character") != required.actor.incarnation
        ):
            raise WorkflowError("Recover the original mandatory Defeat work revision.")
    elif required.source_kind == "defeat_response":
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == required.source_id,
                    choices.c.state.in_(("pending", "submitted")),
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["actor_id"] != required.actor.entity
            or row["kind"] not in ("beneath_defeat", "required_defeat")
        ):
            raise WorkflowError("Recover the actual original mandatory Defeat response.")
    else:
        from girlframe.services.m3_play_support import periods

        period = periods(game)._get(c, required.source_id)
        progress = period.progress.get(required.actor.entity)
        if (
            period.phase != "active"
            or period.character_ids.get(required.actor.entity) != (required.actor.incarnation)
            or required.actor.entity in period.ended_characters
            or (progress and progress.roll)
        ):
            raise WorkflowError("Recover the actual original mandatory Off-Duty Play.")


def reserve_request(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any], *, key: str
) -> dict[str, Any]:
    required = Required.model_validate_json(json.dumps(action["data"]["adjudication"]))
    state = load_state(c, game.store.campaign_id)
    verify(game, c, state, required)
    if (
        action["actor_id"] != str(viewer.user_id)
        or str(required.patient_controller) != action["actor_id"]
    ):
        raise WorkflowError("Only the actual original Girl resumes this mandatory Play.")
    existing = next(
        (x for x in game.pending(c, action["id"]) if x["kind"] == "manual_adjudication"), None
    )
    identity = (
        existing["id"]
        if existing
        else game.request(
            c,
            action,
            required.controller,
            "manual_adjudication",
            required.model_dump(mode="json"),
        )
    )
    game.save_action(c, action, state="awaiting_adjudication")
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.manual_adjudication_requested",
        action_id=action["id"],
        request_id=identity,
    )
    return dict(action_id=action["id"], state="awaiting_adjudication", request_id=identity)


def written_receipt(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    action: dict[str, Any],
    total: int,
    reason: str,
    *,
    request_id: str,
    key: str,
) -> dict[str, Any]:
    """Actual Handler-owned choice, no RNG/resource spend, then ordinary Tag decisions."""
    if action["data"].get("harpy_defeat") is not None:
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        return HarpyDefeatService(game.store, game=game).manual_receipt(
            c, viewer, key, action, total, reason, request_id
        )
    HandlerService(game.store).authorize(c, viewer)
    game.unpaused(c)
    required = Required.model_validate_json(json.dumps(action["data"]["adjudication"]))
    state = load_state(c, game.store.campaign_id)
    verify(game, c, state, required)
    if viewer.user_id != required.controller:
        raise WorkflowError("Only the actual source-appointed Handler may adjudicate.")
    if action["state"] != "awaiting_adjudication" or action["data"].get("receipt"):
        raise WorkflowError("STALE_ADJUDICATION: resume the actual pending manual decision.")
    lock = game.lock(c, action["channel_id"])
    if not lock or lock["state"] != "held":
        raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no adjudication was applied.")
    game.action_characters(c, action, state)
    sheet = state.sheets[required.actor.entity]
    if sheet.revision != action["data"]["sheet_revision"]:
        raise WorkflowError("STALE_SHEET: recover the original unadjudicated Play.")
    request = next(
        (
            x
            for x in game.pending(c, action["id"])
            if x["id"] == request_id
            and x["kind"] == "manual_adjudication"
            and x["actor_id"] == str(required.controller)
        ),
        None,
    )
    if request is None:
        raise WorkflowError("Resume the actual current Handler's manual decision.")
    if required.source_kind == "off_duty":
        from girlframe.services.m3_play_support import periods

        period = periods(game)._get(c, required.source_id)
        if period.progress[required.actor.entity].action_id != action["id"]:
            raise WorkflowError("Recover this exact original period's actual reserved Play.")
    if action["data"]["play"] == "void_observation":
        from girlframe.engine.m3_observation import lower_before_roll
        from girlframe.services.m3_play_support import periods

        period = periods(game)._get(c, required.source_id)
        if period.progress[required.actor.entity].action_id != action["id"]:
            raise WorkflowError("Recover the actual reserved original Observation.")
        state = lower_before_roll(period, int(required.actor.entity), state)
        sheet = state.sheets[required.actor.entity]
    source = str(uuid4())
    decision = Decision(
        id=str(uuid4()),
        action=action["id"],
        request=request_id,
        required=required,
        total=total,
        reason=reason.strip(),
        source_event=source,
    )
    receipt = rules.receipt(decision, str(uuid4()), datetime.now(UTC).isoformat())
    receipt["ruleset"] = RULESET
    c.execute(
        t.m2["m2_receipts"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            action_id=action["id"],
            id=receipt["id"],
            body_json=json.dumps(receipt, sort_keys=True),
        )
    )
    action["data"]["receipt"] = receipt
    if action["data"].get("defeat") is not None:
        action["data"]["defeat"]["roll_event"] = source
    sheet.revision += 1
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == request_id,
            choices.c.state == "pending",
        )
        .values(
            state="resolved",
            revision=request["revision"] + 1,
            body_json=json.dumps(
                json.loads(request["body_json"]) | {"decision": decision.model_dump(mode="json")},
                sort_keys=True,
            ),
        )
    )
    game.save_action(c, action, state="tag_window")
    for person in action["data"]["participants"]:
        game.request(c, action, person, "tag_window")
    game.queue(
        c,
        action,
        "receipt",
        {"receipt": receipt, "callsign": sheet.callsign, "play": action["data"]["play"]},
    )
    event = game.event(
        c,
        viewer.user_id,
        key,
        "m3.manual_adjudicated",
        state,
        event_id=source,
        action_id=action["id"],
        receipt_id=receipt["id"],
        adjudication_id=decision.id,
    )
    c.execute(
        t.m2["m2_responses"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            choice_id=request_id,
            actor_id=str(viewer.user_id),
            event_id=event,
            answer_json=json.dumps(
                {"manual_adjudication": decision.model_dump(mode="json")}, sort_keys=True
            ),
        )
    )
    if action["data"].get("m3") is not None:
        from girlframe.services.m3_play_support import save_raw_roll

        save_raw_roll(game, c, action, state, event)
    return {"action_id": action["id"], "receipt": receipt}


class AdjudicationService:
    def __init__(self, store: OnboardingStore):
        from girlframe.services.m2_game import GameService

        self.store, self.game, self.access = store, GameService(store), Access(store)

    def _get(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any], Required]:
        self.game.authorize(c, viewer, game=False)
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == self.store.campaign_id,
                    choices.c.id == identity,
                    choices.c.kind == "manual_adjudication",
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This actual manual adjudication request is unavailable.")
        action = self.game.action(c, row["action_id"])
        required = Required.model_validate_json(json.dumps(action["data"]["adjudication"]))
        if viewer.user_id not in (required.controller, required.patient_controller):
            raise WorkflowError("This manual decision belongs to its actual Handler and Girl.")
        if row["state"] == "pending":
            verify(self.game, c, load_state(c, self.store.campaign_id), required)
        else:
            canonical = c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == action["id"],
                )
            )
            if canonical is None or json.loads(canonical) != action["data"].get("receipt"):
                raise WorkflowError("Recover the actual saved manual receipt before reading it.")
            decision = Decision.model_validate_json(
                json.dumps(json.loads(canonical)["adjudication"])
            )
            if decision.required != required or decision.request != identity:
                raise WorkflowError("The source manual decision belongs to a different request.")
        return action, dict(row), required

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            action, row, required = self._get(c, viewer, identity)
            from girlframe.engine.m3_careers import original_sheet

            state = load_state(c, self.store.campaign_id)
            if required.play == "harpy_defeat":
                from girlframe.engine.m3_actors import resolve
                from girlframe.services.m3_actors import profiles

                patient = resolve(
                    state,
                    required.actor,
                    profiles(c, self.store.campaign_id),
                    require_alive=False,
                    require_current_profile=False,
                ).label
            else:
                patient = original_sheet(state, required.actor).callsign
            return dict(
                id=identity,
                action_id=action["id"],
                revision=action["revision"],
                play=required.play,
                patient=patient,
                can_act=row["state"] == "pending" and viewer.user_id == required.controller,
                receipt=action["data"].get("receipt"),
            )

    def submit(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, total: int, reason: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.access.authorize(c, viewer, "plays")
            _, _, required = self._get(c, viewer, identity)
            if required.play != "harpy_defeat":
                HandlerService(self.store).authorize(c, viewer)
            elif viewer.user_id != required.controller:
                raise WorkflowError("Only this source's actual human adjudicator can decide.")

        def operation(c: Connection) -> dict[str, Any]:
            action, row, _ = self._get(c, viewer, identity)
            if action["revision"] != revision or row["state"] != "pending":
                raise WorkflowError("STALE_ADJUDICATION: reopen the actual pending decision.")
            return written_receipt(
                self.game, c, viewer, action, total, reason, request_id=identity, key=key
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.manual_adjudicated",
                dict(identity=identity, revision=revision, total=total, reason=reason),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
