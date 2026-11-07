"""Exactly-once, Frame-bound Off-Duty bonuses with actual human decision owners."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_frame_rewards as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_intracadre_marriage import is_dog
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_world_state import AdversaryPilot
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("frame_off_duty_reward", "frame_reward_court", "doctor_credit")
INTEREST = "frame_reward_interest"


def latest(c: Connection, store: OnboardingStore, period: Period) -> dict[str, dict[str, Any]]:
    table = t.m3["m3_required_work"]
    return {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == store.campaign_id,
                table.c.off_duty_id == period.id,
                table.c.kind.in_(KINDS),
            )
            .order_by(table.c.revision)
        ).mappings()
    }


def eligibility(
    c: Connection,
    store: OnboardingStore,
    state: GameState,
    period: Period,
    uid: int,
) -> tuple[GameState, str | None]:
    progress = period.progress.get(str(uid))
    if progress is None or progress.roll is None:
        return state, None
    if progress.action_id is None:
        raise WorkflowError("LEGACY_REWARD_CONTEXT: recover the actual saved roll receipt first.")
    source = progress.reward_source_event
    if source is None:
        history = t.m3["m3_off_duty_history"]
        for body, event in c.execute(
            sa.select(history.c.body_json, history.c.event_id)
            .where(
                history.c.campaign_id == store.campaign_id,
                history.c.id == period.id,
            )
            .order_by(history.c.revision)
        ):
            saved = Period.model_validate_json(body).progress.get(str(uid))
            if (
                saved is not None
                and saved.action_id == progress.action_id
                and saved.roll is not None
            ):
                source = event
                break
    history = t.m2["m2_state_history"]
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == store.campaign_id, history.c.event_id == source
        )
    )
    event = (
        c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == store.campaign_id, t.events.c.id == source
            )
        )
        .mappings()
        .first()
    )
    receipts = t.m2["m2_receipts"]
    receipt = c.scalar(
        sa.select(receipts.c.body_json).where(
            receipts.c.campaign_id == store.campaign_id, receipts.c.action_id == progress.action_id
        )
    )
    actions = t.m2["m2_actions"]
    action = (
        c.execute(
            sa.select(actions.c.actor_id, actions.c.body_json).where(
                actions.c.campaign_id == store.campaign_id, actions.c.id == progress.action_id
            )
        )
        .mappings()
        .first()
    )
    recorded = json.loads(receipt) if receipt else {}
    manual = progress.roll.adjudication
    valid_method = event is not None and (
        manual is not None
        and event["kind"] == "m3.manual_adjudicated"
        and recorded.get("faces") is None
        and recorded.get("rng_source") == "manual_adjudication"
        and recorded.get("adjudication") == manual.model_dump(mode="json")
        and manual.source_event == source
        and manual.action == progress.action_id
        and manual.required.actor.entity == str(uid)
        and manual.required.actor.incarnation == period.character_ids.get(str(uid))
        or manual is None
        and event["kind"] == "m3.rolled"
        and progress.roll.faces is not None
        and recorded.get("faces") == list(progress.roll.faces)
    )
    if (
        body is None
        or event is None
        or not valid_method
        or json.loads(event["payload_json"]).get("action_id") != progress.action_id
        or receipt is None
        or action is None
        or action["actor_id"] != str(uid)
        or json.loads(action["body_json"]).get("m3", {}).get("period_id") != period.id
    ):
        raise WorkflowError(
            "LEGACY_REWARD_CONTEXT: the actual roll-state provenance is unavailable."
        )
    return GameState.model_validate_json(body), source


def specifications(
    c: Connection, store: OnboardingStore, state: GameState, period: Period
) -> list[dict[str, Any]]:
    result = []
    for uid in period.pilots:
        if str(uid) in period.ended_characters or str(uid) not in state.sheets:
            continue
        facts, source = eligibility(c, store, state, period, uid)
        sheet = facts.sheets.get(str(uid))
        from girlframe.services.m2_game import GameService

        character = GameService(store).character_binding(
            c, state, uid, require_current_profile=False
        )
        if sheet is None or sheet.frame_scrapped or character != period.character_ids.get(str(uid)):
            continue
        frame = rules.official(sheet.frame)
        if frame not in rules.PAGES:
            raise WorkflowError("Resolve the unsupported current Frame before Off-Duty rewards.")
        doctor_recorded = frame == "DOCTORDOCTOR MK. II" and uid in period.credit_recorded
        identity = str(
            uuid5(
                NAMESPACE_URL,
                period.id + ":frame-reward:" + str(uid) + ":" + rules.incarnation(sheet),
            )
        )
        owner, kind, mode = uid, "frame_off_duty_reward", "conditional"
        if frame == "DOCTORDOCTOR MK. II":
            identity, kind, mode = (
                period.id + ":doctor_credit:" + str(uid),
                "doctor_credit",
                "doctor_credit",
            )
        elif frame == "THE RED QUEEN":
            try:
                owner = rules.queen(sheet)
                mode = "queen"
            except ValueError:
                owner, kind, mode = period.handler, "frame_reward_court", "unresolved_court"
        body = {
            "origin_frame": frame,
            "origin_frame_id": rules.incarnation(sheet),
            "origin_character_id": character,
            "source_pdf": rules.PAGES[frame],
            "due_stage": "preparing" if mode in ("doctor_credit", "unresolved_court") else "active",
            "mode": mode,
            "reward_source_event": source,
        }
        if not doctor_recorded:
            result.append(
                {
                    "id": identity,
                    "owner_id": str(owner),
                    "subject_id": str(uid),
                    "kind": kind,
                    "body": body,
                }
            )
        if frame != "THE ENFORCER":
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.engine.m3_enforcer_requisitions import PERMISSION
            from girlframe.services.m3_enforcer_requisitions import owned

            grant = owned(
                c,
                GameService(store),
                facts,
                ActorRef(kind="pilot", entity=str(uid), incarnation=character),
                PERMISSION,
            )
            if grant is not None:
                result.append(
                    dict(
                        id=str(uuid5(NAMESPACE_URL, identity + ":retained-enforcer-trigger")),
                        owner_id=str(uid),
                        subject_id=str(uid),
                        kind="frame_off_duty_reward",
                        body=body
                        | dict(
                            origin_frame="THE ENFORCER",
                            source_pdf=78,
                            due_stage="active",
                            mode="conditional",
                            source_rule=PERMISSION,
                            source_rule_grant=grant.id,
                        ),
                    )
                )
    return result


def matches(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    body = json.loads(row["body_json"])
    header = all(
        body.get(k) == spec["body"].get(k)
        for k in (
            "origin_frame",
            "origin_frame_id",
            "origin_character_id",
            "source_rule",
            "source_rule_grant",
        )
    )
    return header and (
        row["state"] == "resolved"
        and not body.get("superseded_by_frame_event")
        or (
            row["state"] in ("pending", "awaiting_interest")
            and row["owner_id"] == spec["owner_id"]
            and row["kind"] == spec["kind"]
            and body.get("reward_source_event") == spec["body"].get("reward_source_event")
        )
    )


def needs_refresh(c: Connection, store: OnboardingStore, state: GameState, period: Period) -> bool:
    saved = latest(c, store, period)
    return any(
        x["id"] not in saved or not matches(saved[x["id"]], x)
        for x in specifications(c, store, state, period)
    )


def synchronize(
    c: Connection, store: OnboardingStore, state: GameState, period: Period, event: str
) -> None:
    specs = specifications(c, store, state, period)
    wanted = {x["id"] for x in specs}
    saved = latest(c, store, period)
    table = t.m3["m3_required_work"]

    def append(row: dict[str, Any], **values: Any) -> None:
        c.execute(
            table.insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "event_id")},
                revision=row["revision"] + 1,
                event_id=event,
            )
            .values(**values)
        )

    for old_row in saved.values():
        # Completed real grants remain historical even when a Frame is replaced.
        if old_row["state"] != "resolved" and old_row["id"] not in wanted:
            body = json.loads(old_row["body_json"]) | {
                "superseded_by_frame_event": event,
                "reward_granted": False,
            }
            append(old_row, state="resolved", body_json=json.dumps(body, sort_keys=True))
    parent = {"campaign_id": store.campaign_id, "mission_id": None, "off_duty_id": period.id}
    for spec in specs:
        row = saved.get(spec["id"])
        if row is not None and matches(row, spec):
            continue
        if row is None:
            related(
                c,
                store,
                parent,
                spec["id"],
                int(spec["owner_id"]),
                int(spec["subject_id"]),
                spec["kind"],
                spec["body"],
                event,
            )
        else:
            append(
                row,
                state="pending",
                kind=spec["kind"],
                owner_id=spec["owner_id"],
                body_json=json.dumps(spec["body"], sort_keys=True),
            )


class RewardService:
    def __init__(self, periods: OffDutyService):
        self.periods, self.missions = periods, periods.missions
        self.store, self.game = periods.store, periods.game

    def _permission_proof(self, c: Connection, row: dict[str, Any]) -> None:
        body = json.loads(row["body_json"])
        if row["state"] != "resolved" or not body.get("reward_granted"):
            return
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_intracadre_marriage import acquisitions
        from girlframe.services.m3_asset_loss import snapshots
        from girlframe.services.m3_intracadre_marriage import prove_flow

        before, after = snapshots(self.game, c, body["applied_event"])
        if not acquisitions(before):
            return
        beneficiary = (
            int(body["review"]["recipient"]) if body["mode"] == "queen" else int(row["subject_id"])
        )
        source = body.get("root_id", row["id"])
        prove_flow(
            self.game,
            c,
            before,
            after,
            current_ref(before, beneficiary),
            body["applied_event"],
            "frame-reward:" + source,
            1,
        )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] not in (*KINDS[:2], INTEREST):
            raise WorkflowError("Resume an actual current Frame reward task.")
        return dict(row)

    def _view(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.game.authorize(c, viewer, game=False)
        if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
            raise WorkflowError("This Frame reward belongs to other participants.")

    def _context(
        self,
        c: Connection,
        row: dict[str, Any],
        expected: int,
        game_revision: int,
        *,
        states: tuple[str, ...] = ("pending",),
    ) -> tuple[GameState, Period, dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        period = self.periods._get(c, row["off_duty_id"])
        from girlframe.services.m3_off_duty import current_original_characters

        characters = current_original_characters(c, self.game, state, period)
        if row["subject_id"] not in characters or any(
            not HandlerService(self.store)._member(c, int(uid)) for uid in characters
        ):
            raise WorkflowError(
                "Recover the changed character roster before this old period's rewards."
            )
        specs = specifications(c, self.store, state, period)
        spec = next((x for x in specs if x["id"] == row["id"]), None)
        if (
            spec is None
            or not matches(row, spec)
            or row["state"] not in states
            or row["revision"] != expected
            or state.revision != game_revision
        ):
            raise WorkflowError("STALE_REWARD: refresh the actual Frame, holder and current task.")
        if (
            self.missions._current_handler(c) != state.handler
            or state.handler != period.handler
            or period.phase != "active"
            or self.game.pending_actions(c)
        ):
            raise WorkflowError("Finish preparation/pending Plays and review the current Handler.")
        locks = t.m2["m2_locks"]
        if c.scalar(
            sa.select(locks.c.channel_id)
            .where(locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released")
            .limit(1)
        ):
            raise WorkflowError("Restore scene chat before the Off-Duty bonus review.")
        progress = period.progress.get(row["subject_id"])
        if progress is None or progress.roll is None or progress.roll.stage != "choices":
            raise WorkflowError(
                "Make this Frame's actual Off-Duty Play and finish its Tag choices first."
            )
        return state, period, spec

    def _check(
        self,
        c: Connection,
        viewer: GuildViewer,
        row: dict[str, Any],
        expected: int,
        game_revision: int,
    ) -> tuple[GameState, Period, dict[str, Any]]:
        self._view(c, viewer, row)
        state, period, spec = self._context(c, row, expected, game_revision)
        if spec["owner_id"] != str(viewer.user_id) or row["kind"] != "frame_off_duty_reward":
            raise WorkflowError("Only the actual source decision owner may resolve this bonus.")
        return state, period, spec

    def refresh(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, game_revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            period = self.periods._get(c, identity)
            self.periods._view(c, viewer, period)
            state = load_state(c, self.store.campaign_id)
            if (
                period.phase == "complete"
                or period.revision != expected
                or state.revision != game_revision
            ):
                raise WorkflowError("Refresh the current unfinished period.")
            event = self.game.event(
                c, viewer.user_id, key, "m3.frame_rewards_refreshed", period_id=identity
            )
            synchronize(c, self.store, state, period, event)
            return {"id": identity, "state": "refreshed"}

        return self.missions._write(
            viewer,
            key,
            "m3.frame_rewards_refreshed",
            {"id": identity, "expected": expected, "game_revision": game_revision},
            operation,
            lambda c: self.missions.access.authorize(c, viewer, "playbooks"),
        )

    def _known_pilot(self, c: Connection, pilot: AdversaryPilot, owner: int) -> bool:
        return bool(
            pilot.revealed
            or pilot.custodian == owner
            or pilot.controller == owner
            or (
                pilot.custody_event
                and c.scalar(
                    sa.select(t.events.c.actor_id).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == pilot.custody_event,
                    )
                )
                == str(owner)
            )
        )

    def _claim_targets(
        self, c: Connection, facts: GameState, owner: int, frame: str, claim: rules.Claim
    ) -> None:
        if not claim.fulfilled:
            return
        if frame == "JANUS" and claim.official != "handler:" + str(facts.handler):
            if facts.world is None or not any(
                "npc:" + x.id == claim.official and (x.revealed or x.controller == owner)
                for x in facts.world.npcs
            ):
                raise WorkflowError("Choose a known official for this recorded Play.")
        if frame in ("CONSUME", "THE ENFORCER") and claim.prisoner:
            if facts.world is None or facts.handler is None:
                raise WorkflowError("The actual delivery/custody record is unavailable.")
            kind, _, target = claim.prisoner.partition(":")
            known = (
                kind == "npc"
                and any(
                    x.id == target and (x.revealed or x.controller == owner)
                    for x in facts.world.npcs
                )
            ) or (
                kind == "pilot"
                and any(
                    x.id == target and self._known_pilot(c, x, owner) for x in facts.world.pilots
                )
            )
            if not known:
                raise WorkflowError("Choose a known actual delivered prisoner.")
            proof = rules.prisoner(
                facts.world,
                claim.prisoner,
                owner,
                facts.handler,
                rebel=frame == "THE ENFORCER",
                cadre=frozenset(facts.order),
            )
            if not c.scalar(
                sa.select(t.events.c.id).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == proof
                )
            ):
                raise WorkflowError(
                    "The actual custody source event is unavailable; no reward was granted."
                )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._row(c, identity)
            self._view(c, viewer, row)
            self._permission_proof(c, row)
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            result = {
                k: row[k] for k in ("id", "owner_id", "subject_id", "revision", "state", "kind")
            }
            period = self.periods._get(c, row["off_duty_id"])
            progress = period.progress.get(row["subject_id"])
            result.update(
                frame=body["origin_frame"],
                mode=body["mode"],
                game_revision=state.revision,
                ready=bool(
                    period.phase == "active"
                    and progress
                    and progress.roll
                    and progress.roll.stage == "choices"
                ),
            )
            if row["kind"] == INTEREST:
                if row["owner_id"] == str(viewer.user_id) and row["state"] != "resolved":
                    result["offering"] = body["claim"]["offering"]
                    result["account"] = body["claim"]["account"]
                return result
            if row["owner_id"] != str(viewer.user_id) or row["state"] == "resolved":
                return result
            if body["mode"] == "unresolved_court":
                result["issue"] = "Resolve the actual Court allocation before a Queen choice."
                return result
            period = self.periods._get(c, row["off_duty_id"])
            facts, _ = eligibility(c, self.store, state, period, int(row["subject_id"]))
            result["frame_label"] = facts.sheets[row["subject_id"]].frame
            result["pilots"] = tuple(
                (str(uid), state.sheets[str(uid)].callsign)
                for uid in state.order
                if not (body["mode"] == "queen" and uid == viewer.user_id and is_dog(state, uid))
            )
            if body["mode"] == "queen":
                return result
            result["officials"] = (
                ("handler:" + str(facts.handler), "Handler at this Off-Duty Play"),
            )
            result["prisoners"] = ()
            if facts.world is not None:
                known = [
                    x for x in facts.world.npcs if x.revealed or x.controller == viewer.user_id
                ]
                result["officials"] += tuple(
                    ("npc:" + x.id, x.name)
                    for x in known
                    if x.employment == "foundation"
                    or set(x.jobs)
                    & {"handler", "director", "guard", "scientist", "doctor", "base_personnel"}
                )
                candidates = [("npc:" + x.id, x.name) for x in known if "prisoner" in x.jobs]
                # Only a current custodian/role player gets undisclosed external identities.
                candidates += [
                    ("pilot:" + x.id, x.name)
                    for x in facts.world.pilots
                    if self._known_pilot(c, x, viewer.user_id)
                ]
                prisoners = []
                for target, name in candidates:
                    try:
                        rules.prisoner(
                            facts.world,
                            target,
                            int(row["subject_id"]),
                            int(facts.handler or 0),
                            rebel=body["origin_frame"] == "THE ENFORCER",
                            cadre=frozenset(facts.order),
                        )
                    except ValueError:
                        continue
                    prisoners.append((target, name))
                result["prisoners"] = tuple(prisoners)
            sheet = facts.sheets[row["subject_id"]]
            fanbase = (
                sheet.frame_runtime.fanbase
                if sheet.frame_runtime
                else sheet.review.creation.fanbase
            )
            result["fanbase"] = (
                fanbase.model_dump(mode="json")
                if fanbase and body["origin_frame"] == "THE PRINCE"
                else None
            )
            return result

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        claim: rules.Claim | None = None,
        recipient: int | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        if claim is not None:
            claim = rules.Claim.model_validate_json(claim.model_dump_json())

        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "playbooks")
            row = self._row(c, identity)
            self._view(c, viewer, row)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("Only the actual source decision owner chooses this reward.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            state, period, spec = self._check(c, viewer, row, expected, game_revision)
            facts, _ = eligibility(c, self.store, state, period, int(row["subject_id"]))
            event_id = str(uuid4())
            if spec["body"]["mode"] == "queen":
                if (
                    claim is not None
                    or recipient is None
                    or not account.strip()
                    or len(account) > 1200
                ):
                    raise WorkflowError(
                        "The Queen holder selects one actual Girl and records its own reason."
                    )
                updated = rules.queen_award(
                    state,
                    int(row["subject_id"]),
                    viewer.user_id,
                    recipient,
                    identity,
                    eligibility=facts,
                    event=event_id,
                )
                details = {"recipient": recipient, "account": account.strip()}
                granted = True
            else:
                if claim is None or recipient is not None or account:
                    raise WorkflowError(
                        "Record only this Frame's actual conditional trigger or no-trigger review."
                    )
                if spec["body"]["origin_frame"] == "WYVERN 0.4" and claim.fulfilled:
                    if (
                        not claim.offering.strip()
                        or not claim.account.strip()
                        or any(
                            (claim.prisoner, claim.official, claim.influenced_pilot, claim.evidence)
                        )
                    ):
                        raise WorkflowError(
                            "Describe only the actual Wyvern offering and its factual account."
                        )
                    assert facts.handler is not None
                    child = str(uuid5(NAMESPACE_URL, identity + ":handler-interest"))
                    event = self.game.event(
                        c,
                        viewer.user_id,
                        key,
                        "m3.frame_interest_requested",
                        work_id=identity,
                        interest_id=child,
                    )
                    table = t.m3["m3_required_work"]
                    c.execute(
                        table.insert().values(
                            **{
                                k: v
                                for k, v in row.items()
                                if k not in ("revision", "state", "body_json", "event_id")
                            },
                            revision=row["revision"] + 1,
                            state="awaiting_interest",
                            event_id=event,
                            body_json=json.dumps(
                                json.loads(row["body_json"])
                                | {"claim": claim.model_dump(mode="json"), "interest_id": child},
                                sort_keys=True,
                            ),
                        )
                    )
                    related(
                        c,
                        self.store,
                        row,
                        child,
                        facts.handler,
                        int(row["subject_id"]),
                        INTEREST,
                        spec["body"]
                        | {
                            "mode": "interest",
                            "root_id": identity,
                            "root_revision": row["revision"] + 1,
                            "claim": claim.model_dump(mode="json"),
                        },
                        event,
                    )
                    return {"id": identity, "state": "awaiting_interest", "reward_granted": False}
                self._claim_targets(c, facts, viewer.user_id, spec["body"]["origin_frame"], claim)
                updated = rules.review(
                    state,
                    viewer.user_id,
                    claim,
                    identity,
                    eligibility=facts,
                    character_id=period.character_ids[row["subject_id"]],
                    source_rule=spec["body"].get("source_rule"),
                    event=event_id,
                )
                details = claim.model_dump(mode="json")
                granted = claim.fulfilled
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_reward_reviewed",
                updated,
                event_id=event_id,
                work_id=identity,
                reward_granted=granted,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                    body_json=json.dumps(
                        json.loads(row["body_json"])
                        | {"review": details, "reward_granted": granted, "applied_event": event},
                        sort_keys=True,
                    ),
                )
            )
            return {"id": identity, "state": "resolved", "reward_granted": granted}

        return self.missions._write(
            viewer,
            key,
            "m3.frame_reward_reviewed",
            {
                "id": identity,
                "expected": expected,
                "game_revision": game_revision,
                "claim": claim.model_dump(mode="json") if claim else None,
                "recipient": recipient,
                "account": account,
            },
            operation,
            authorize,
        )

    def answer_interest(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        interested: bool,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "playbooks")
            row = self._row(c, identity)
            self._view(c, viewer, row)
            if row["owner_id"] != str(viewer.user_id) or row["kind"] != INTEREST:
                raise WorkflowError("Only the recorded Handler answers its own interest question.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            if (
                type(interested) is not bool
                or row["state"] != "pending"
                or row["revision"] != expected
            ):
                raise WorkflowError("STALE_INTEREST: reopen your own current interest question.")
            body = json.loads(row["body_json"])
            parent = self._row(c, body["root_id"])
            state, period, spec = self._context(
                c, parent, body["root_revision"], game_revision, states=("awaiting_interest",)
            )
            facts, _ = eligibility(c, self.store, state, period, int(parent["subject_id"]))
            if (
                facts.handler != viewer.user_id
                or spec["body"]["origin_frame"] != "WYVERN 0.4"
                or row["subject_id"] != parent["subject_id"]
            ):
                raise WorkflowError("The offering's actual Handler/Frame binding changed.")
            claim = rules.Claim.model_validate_json(json.dumps(body["claim"]))
            event_id = str(uuid4())
            updated = rules.review(
                state,
                int(parent["subject_id"]),
                claim,
                parent["id"],
                eligibility=facts,
                handler_interested=interested,
                character_id=period.character_ids[parent["subject_id"]],
                event=event_id,
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_reward_reviewed",
                updated,
                event_id=event_id,
                work_id=parent["id"],
                interest_id=identity,
                reward_granted=interested,
            )
            for saved in (parent, row):
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
                        **{
                            k: v
                            for k, v in saved.items()
                            if k not in ("revision", "state", "body_json", "event_id")
                        },
                        revision=saved["revision"] + 1,
                        state="resolved",
                        event_id=event,
                        body_json=json.dumps(
                            json.loads(saved["body_json"])
                            | {
                                "handler_interested": interested,
                                "review": claim.model_dump(mode="json"),
                                "reward_granted": interested,
                                "applied_event": event,
                            },
                            sort_keys=True,
                        ),
                    )
                )
            return {"id": identity, "state": "resolved", "reward_granted": interested}

        return self.missions._write(
            viewer,
            key,
            "m3.frame_interest_answered",
            {
                "id": identity,
                "expected": expected,
                "game_revision": game_revision,
                "interested": interested,
            },
            operation,
            authorize,
        )
