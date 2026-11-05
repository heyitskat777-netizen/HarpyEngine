"""Resumable original-CID Girl baseline setup after an actual Defeat book change."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_girl_transition as rules
from girlframe.engine.creation_details import DesireChoice
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_transition_state import Plan
from girlframe.engine.m3_recovery_state import fingerprint
from girlframe.engine.m3_standards import ready as standards_ready
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "girl_playbook_transition"


def synchronize(c: Connection, store: OnboardingStore, action: dict[str, Any], event: str) -> None:
    state = load_state(c, store.campaign_id)
    ref = action.get("data", {}).get("defeat", {}).get("actor")
    if ref is None:
        return
    owner = ActorRef.model_validate_json(json.dumps(ref))
    sheet = state.sheets.get(owner.entity)
    if sheet is None or sheet.character_id != owner.incarnation:
        return
    fact = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "girl_playbook_changed"
            and x.get("source_event") == event
            and x.get("original_character") == owner.incarnation
        ),
        None,
    )
    if fact is None:
        return
    identity = str(uuid5(NAMESPACE_URL, "girlframe:girl-transition:" + action["id"] + ":" + event))
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id)
        .where(table.c.campaign_id == store.campaign_id, table.c.id == identity)
        .limit(1)
    ):
        return
    related(
        c,
        store,
        dict(campaign_id=store.campaign_id, campaign_context=True),
        identity,
        int(owner.entity),
        int(owner.entity),
        KIND,
        dict(
            owner=owner.model_dump(mode="json"),
            epoch=event,
            old_book=fact["old_book"],
            new_book=fact["new_book"],
            source_action=action["id"],
            source_event=event,
            entries={},
            immediate=True,
        ),
        event,
    )


class GirlTransitionService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _row(self, c: Connection, identity: str, *, first: bool = False) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.kind == KIND,
                    table.c.id == identity,
                )
                .order_by(table.c.revision if first else table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This original Girl baseline transition is unavailable.")
        return dict(row)

    def _source(
        self, c: Connection, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any], ActorRef]:
        row, first = self._row(c, identity), self._row(c, identity, first=True)
        try:
            body, start = json.loads(row["body_json"]), json.loads(first["body_json"])
            owner = ActorRef.model_validate_json(json.dumps(start["owner"]))
            if (
                owner.kind != "pilot"
                or first["revision"] != 1
                or first["owner_id"] != owner.entity
                or first["subject_id"] != owner.entity
                or any(row[k] != first[k] for k in ("owner_id", "subject_id", "campaign_context"))
                or not first["campaign_context"]
                or first["event_id"] != start["epoch"]
                or any(
                    body.get(k) != start.get(k)
                    for k in (
                        "owner",
                        "epoch",
                        "old_book",
                        "new_book",
                        "source_action",
                        "source_event",
                    )
                )
                or identity
                != str(
                    uuid5(
                        NAMESPACE_URL,
                        "girlframe:girl-transition:"
                        + start["source_action"]
                        + ":"
                        + start["epoch"],
                    )
                )
            ):
                raise ValueError()
            source = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == start["epoch"],
                    )
                )
                .mappings()
                .first()
            )
            meta = json.loads(source["payload_json"]) if source else {}
            action = self.game.action(c, start["source_action"])
            if (
                source is None
                or source["kind"] != "m3.choice_resolved"
                or source["actor_id"] != owner.entity
                or meta.get("action_id") != action["id"]
                or action["data"].get("play") != "defeat"
                or action["data"].get("defeat", {}).get("actor") != start["owner"]
            ):
                raise ValueError()
            history = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == start["epoch"],
                )
            )
            original = GameState.model_validate_json(history) if history else None
            fact = (
                next(
                    (
                        x
                        for x in original.facts
                        if x.get("kind") == "girl_playbook_changed"
                        and x.get("source_event") == start["epoch"]
                        and x.get("original_character") == owner.incarnation
                    ),
                    None,
                )
                if original
                else None
            )
            if (
                fact is None
                or fact["new_book"] != start["new_book"]
                or fact["old_book"] != start["old_book"]
            ):
                raise ValueError()
            expected = {"plan": owner.entity, "completed": owner.entity}
            entries = body["entries"]
            if "assignment" in entries:
                expected["assignment"] = entries["assignment"]["data"]["handler"]["entity"]
                expected["mentor"] = entries["assignment"]["data"]["mentor"]["entity"]
            if "plan" in entries:
                plan = Plan.model_validate_json(json.dumps(entries["plan"]["data"]))
                if plan.pair:
                    expected["pair"] = plan.pair.entity
            if "investor" in entries:
                expected["investor"] = entries["investor"]["data"]["handler"]["entity"]
            for kind, entry in entries.items():
                proof = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == entry["event"],
                        )
                    )
                    .mappings()
                    .first()
                )
                data = json.loads(proof["payload_json"]) if proof else {}
                if (
                    proof is None
                    or proof["kind"] != "m3.girl_transition_" + kind
                    or proof["actor_id"] != expected.get(kind)
                    or data.get("work_id") != identity
                    or data.get("choice_sha256") != fingerprint(entry["data"])
                ):
                    raise ValueError()
                if kind in ("assignment", "mentor", "pair", "investor", "completed") and (
                    entry["data"].get("plan_source") != entries["plan"]["event"]
                ):
                    raise ValueError()
                if (
                    kind == "mentor"
                    and entry["data"].get("assignment_source") != entries["assignment"]["event"]
                ):
                    raise ValueError()
            if body.get("complete") and (row["state"] != "resolved" or "completed" not in entries):
                raise ValueError()
            return row, body, owner
        except (ValueError, KeyError, TypeError):
            raise WorkflowError(
                "SOURCE_GIRL_TRANSITION_MISSING: recover the original baseline and human choices."
            ) from None

    def _actual(self, c: Connection, body: dict[str, Any], owner: ActorRef) -> GameState:
        state = load_state(c, self.store.campaign_id)
        runtime = state.sheets[owner.entity].girl_runtime if owner.entity in state.sheets else None
        if (
            resolve(
                state, owner, profiles(c, self.store.campaign_id), require_current_profile=False
            ).rules
            != "girl_frame"
            or runtime is None
            or runtime.baseline_event != body["epoch"]
            or state.sheets[owner.entity].girl != body["new_book"]
        ):
            raise WorkflowError("Recover the original Girl and actual current new baseline.")
        return state

    def _handler(self, c: Connection) -> tuple[ActorRef, str]:
        uid, appointment = MedicalService(self.store)._handler(c)
        state = load_state(c, self.store.campaign_id)
        return ActorRef(
            kind="handler",
            entity=str(uid),
            incarnation=state.handler_persona.id if state.handler_persona else None,
        ), appointment

    def _assignment(self, c: Connection, body: dict[str, Any]) -> tuple[ActorRef, str, ActorRef]:
        data = body["entries"]["assignment"]["data"]
        handler = ActorRef.model_validate_json(json.dumps(data["handler"]))
        mentor = ActorRef.model_validate_json(json.dumps(data["mentor"]))
        if self._handler(c) != (handler, data["appointment"]):
            raise WorkflowError("Recover the actual Mentor assignment's Handler appointment.")
        resolve(
            load_state(c, self.store.campaign_id),
            mentor,
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        )
        return handler, data["appointment"], mentor

    def _view(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row, body, owner = self._source(c, identity)
        entries, book = body["entries"], body["new_book"]
        try:
            handler, _appointment = self._handler(c)
        except WorkflowError:
            handler = None
        role = "owner" if owner.entity == str(viewer.user_id) else None
        if handler and handler.entity == str(viewer.user_id) and book in ("NEWGIRL", "VATGROWN"):
            role = "handler"
        plan = (
            Plan.model_validate_json(json.dumps(entries["plan"]["data"]))
            if "plan" in entries
            else None
        )
        if plan and plan.pair and plan.pair.entity == str(viewer.user_id):
            role = "pair"
        if "assignment" in entries and entries["assignment"]["data"]["mentor"]["entity"] == str(
            viewer.user_id
        ):
            role = "mentor"
        if role is None:
            raise WorkflowError("This setup belongs to its actual original participants.")
        stale = False
        try:
            state = self._actual(c, body, owner)
            if plan:
                rules.validate(
                    state, owner, body["epoch"], plan, profiles(c, self.store.campaign_id)
                )
            if "assignment" in entries:
                self._assignment(c, body)
        except (ValueError, WorkflowError):
            stale = True
            state = load_state(c, self.store.campaign_id)
        required = {"plan"}
        if book == "NEWGIRL":
            required |= {"assignment", "mentor"}
        if book == "BONDED":
            required.add("pair")
        if book == "VATGROWN":
            required.add("investor")
        enough = required <= set(entries)
        if book == "BONDED" and "pair" in entries:
            enough &= entries["pair"]["data"]["accepted"] is True
        if book == "PRINCESS":
            enough &= standards_ready(state.sheets.get(owner.entity))
        result = dict(
            id=identity,
            revision=row["revision"],
            game_revision=state.revision,
            owner=role == "owner",
            role=role,
            book=book,
            old_book=body["old_book"],
            stale=stale,
            state=row["state"],
            complete=body.get("complete", False),
            epoch=body["epoch"],
            can_configure=role == "owner" and row["state"] == "pending",
            can_assign=role == "handler"
            and book == "NEWGIRL"
            and "plan" in entries
            and row["state"] == "pending",
            can_respond=not stale
            and role in ("mentor", "pair", "handler")
            and "plan" in entries
            and row["state"] == "pending"
            and (
                (role == "mentor" and "mentor" not in entries)
                or (role == "pair" and "pair" not in entries)
                or (role == "handler" and book == "VATGROWN" and "investor" not in entries)
            ),
            can_finalize=not stale and role == "owner" and row["state"] == "pending" and enough,
            needs_standards=book == "PRINCESS"
            and not standards_ready(state.sheets.get(owner.entity)),
        )
        if role == "owner":
            result["plan"] = plan.model_dump(mode="json") if plan else None
            result["responses"] = {k: x["data"] for k, x in entries.items() if k != "plan"}
            result["identities"] = (
                [
                    dict(id=x.id, name=x.name)
                    for x in state.sheets[owner.entity].identities
                    if not x.protected or x.paired
                ]
                if owner.entity in state.sheets
                else []
            )
            result["investors"] = (
                [
                    dict(id=x.id, name=x.name)
                    for x in state.world.npcs
                    if x.id in rules.starting_investors(state, owner) and x.alive
                ]
                if state.world
                else []
            )
        if role == "pair" and plan:
            result["paired_identity"] = plan.paired_identity
        result["people"] = self._people(c, state, owner) if role in ("owner", "handler") else []
        if "assignment" in entries and role in ("owner", "mentor", "handler"):
            result["mentor"] = entries["assignment"]["data"]["mentor"]
        return result

    def _people(self, c: Connection, state: GameState, owner: ActorRef) -> list[dict[str, Any]]:
        result = []
        for uid, sheet in state.sheets.items():
            if uid == owner.entity or not HandlerService(self.store)._member(c, int(uid)):
                continue
            try:
                ref = ActorRef(
                    kind="pilot",
                    entity=uid,
                    incarnation=self.game.character_binding(
                        c, state, int(uid), require_current_profile=False
                    ),
                )
                resolve(
                    state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
                )
            except (ValueError, WorkflowError):
                continue
            result.append(dict(ref=ref.model_dump(mode="json"), label=sheet.callsign))
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer, identity)

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        body: dict[str, Any],
        event: str,
        *,
        complete: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "event_id", "body_json")
                },
                revision=row["revision"] + 1,
                state="resolved" if complete else "pending",
                event_id=event,
                body_json=json.dumps(body, sort_keys=True),
            )
        )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        kind: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self._view(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, body, owner = self._source(c, identity)
            state = self._actual(c, body, owner)
            view = self._view(c, viewer, identity)
            if row["state"] != "pending" or row["revision"] != revision:
                raise WorkflowError("STALE_GIRL_SETUP: reopen the current owned choices.")
            entries = body["entries"].copy()
            if kind == "plan":
                if not view["can_configure"]:
                    raise WorkflowError("Only the original Girl chooses her actual setup.")
                plan = Plan.model_validate_json(json.dumps(data))
                rules.validate(
                    state, owner, body["epoch"], plan, profiles(c, self.store.campaign_id)
                )
                entries = {}
            elif kind == "assignment":
                if not view["can_assign"]:
                    raise WorkflowError("Only the current Handler assigns the actual Mentor.")
                handler, appointment = self._handler(c)
                mentor = ActorRef.model_validate_json(json.dumps(data["mentor"]))
                if (
                    mentor == owner
                    or resolve(
                        state,
                        mentor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).rules
                    != "girl_frame"
                ):
                    raise WorkflowError("Assign another actual current Girl as Mentor.")
                data.update(handler=handler.model_dump(mode="json"), appointment=appointment)
                data["plan_source"] = entries["plan"]["event"]
                entries.pop("mentor", None)
            elif kind in ("mentor", "pair", "investor"):
                if not view["can_respond"]:
                    raise WorkflowError("This original response belongs to its actual chooser.")
                if kind == "mentor":
                    if (
                        view["role"] != "mentor"
                        or not data["callsign"].strip()
                        or len(data["callsign"]) > 80
                    ):
                        raise WorkflowError(
                            "The actual assigned Mentor chooses a callsign of1–80 characters."
                        )
                    data["assignment_source"] = entries["assignment"]["event"]
                elif kind == "pair":
                    if view["role"] != "pair" or type(data["accepted"]) is not bool:
                        raise WorkflowError("Only the actual nominated Pair accepts or declines.")
                else:
                    if view["role"] != "handler" or body["new_book"] != "VATGROWN":
                        raise WorkflowError("Only the current Handler chooses their own desires.")
                    DesireChoice.model_validate_json(json.dumps(data["desires"]))
                    handler, appointment = self._handler(c)
                    data.update(handler=handler.model_dump(mode="json"), appointment=appointment)
                data["plan_source"] = entries["plan"]["event"]
            else:
                raise WorkflowError("Choose a known original setup response.")
            source = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.girl_transition_" + kind,
                work_id=identity,
                choice_sha256=fingerprint(data),
            )
            entries[kind] = dict(data=data, event=source)
            self._save(c, row, body | dict(entries=entries), source)
            return dict(id=identity, revision=revision + 1)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.girl_transition_" + kind,
                dict(id=identity, revision=revision, data=data.copy()),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def configure(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, plan: Plan
    ) -> dict[str, Any]:
        return self._write(viewer, key, identity, revision, "plan", plan.model_dump(mode="json"))

    def assign(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, mentor: ActorRef
    ) -> dict[str, Any]:
        return self._write(
            viewer,
            key,
            identity,
            revision,
            "assignment",
            dict(mentor=mentor.model_dump(mode="json")),
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        callsign: str | None = None,
        accepted: bool | None = None,
        desires: DesireChoice | None = None,
    ) -> dict[str, Any]:
        if sum(x is not None for x in (callsign, accepted, desires)) != 1:
            raise WorkflowError("Provide only your own actual response.")
        kind, data = (
            ("mentor", dict(callsign=callsign))
            if callsign is not None
            else (
                ("pair", dict(accepted=accepted))
                if accepted is not None
                else (
                    "investor",
                    dict(desires=desires.model_dump(mode="json") if desires else None),
                )
            )
        )
        return self._write(viewer, key, identity, revision, kind, data)

    def finalize(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, game_revision: int
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            if not self._view(c, viewer, identity)["owner"]:
                raise WorkflowError("Only the original Girl confirms the complete actual setup.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, body, owner = self._source(c, identity)
            state = self._actual(c, body, owner)
            if (
                row["revision"] != revision
                or state.revision != game_revision
                or not self._view(c, viewer, identity)["can_finalize"]
            ):
                raise WorkflowError("STALE_GIRL_SETUP: review the actual complete current choices.")
            MedicalService(self.store)._idle(c)
            entries = body["entries"]
            plan = Plan.model_validate_json(json.dumps(entries["plan"]["data"]))
            mentor, callsign, handler, appointment, desires = None, None, None, None, None
            if body["new_book"] == "NEWGIRL":
                handler, appointment, mentor = self._assignment(c, body)
                callsign = entries["mentor"]["data"]["callsign"]
            if body["new_book"] == "VATGROWN":
                grant = entries["investor"]["data"]
                handler = ActorRef.model_validate_json(json.dumps(grant["handler"]))
                appointment = grant["appointment"]
                if self._handler(c) != (handler, appointment):
                    raise WorkflowError(
                        "Recover the original investor chooser's actual Handler appointment."
                    )
                desires = DesireChoice.model_validate_json(json.dumps(grant["desires"]))
            event = str(uuid4())
            updated = rules.apply(
                state,
                owner,
                body["epoch"],
                plan,
                profiles(c, self.store.campaign_id),
                event,
                mentor=mentor,
                callsign=callsign,
                handler=handler,
                appointment=appointment,
                handler_desires=desires,
            )
            sheet = updated.sheets[owner.entity]
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == owner.entity,
                    )
                )
                .mappings()
                .one()
            )
            if profile["revision"] != sheet.source_profile_revision:
                raise WorkflowError("STALE_PROFILE: resolve the actual profile before finalizing.")
            public = json.loads(profile["public_json"]) | dict(
                girl_playbook=sheet.girl, callsign=sheet.callsign
            )
            draft = DraftInput.model_validate_json(json.dumps(public))
            sheet.source_profile_revision = profile["revision"] + 1
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == owner.entity,
                )
                .values(revision=sheet.source_profile_revision, public_json=json.dumps(public))
            )
            self.store._enqueue_sync(c, int(owner.entity), sheet.source_profile_revision, draft)
            data = dict(epoch=body["epoch"], plan_source=entries["plan"]["event"])
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.girl_transition_completed",
                updated,
                event_id=event,
                work_id=identity,
                choice_sha256=fingerprint(data),
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=owner.entity,
                    revision=sheet.source_profile_revision,
                    character_id=profile["id"],
                    event_id=event,
                    public_json=json.dumps(public),
                    private_json=profile["private_json"],
                )
            )
            entries["completed"] = dict(data=data, event=event)
            self._save(
                c,
                row,
                body | dict(entries=entries, complete=True, immediate=False),
                event,
                complete=True,
            )
            return dict(id=identity, complete=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.girl_transition_completed",
                dict(id=identity, revision=revision, game_revision=game_revision),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        rows = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                .order_by(table.c.revision)
            ).mappings()
        }
        result = []
        for row in rows.values():
            if not history and row["state"] == "resolved":
                continue
            try:
                data = self._view(c, viewer, row["id"])
            except WorkflowError as error:
                if "actual original participants" in str(error):
                    continue
                raise
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    state=row["state"],
                    stale=data["stale"],
                    label="Girl playbook change: " + data["book"],
                    actionable=any(
                        data[k]
                        for k in ("can_configure", "can_assign", "can_respond", "can_finalize")
                    ),
                )
            )
        return result

    def tasks(self, viewer: GuildViewer, *, history: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer, history=history)
