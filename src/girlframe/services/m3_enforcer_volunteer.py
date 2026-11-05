"""Volunteering preserves the actual chooser's debt, instruction and on-screen executor."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcer import EnforcerService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_role_punishments import open_case, synchronize
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "enforcer_volunteer"


class VolunteerService(EnforcerService):
    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id)
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def _candidates(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        actor = self._actor(c, viewer)
        state = load_state(c, self.store.campaign_id)
        result = []
        for row in self._rows(c):
            body = json.loads(row["body_json"])
            if row["kind"] != "punishment" or row["state"] == "resolved" or body.get("role_case"):
                continue
            if row["subject_id"] == actor.entity:
                continue
            try:
                subject = current_ref(state, int(row["subject_id"]))
                chooser = current_ref(state, int(row["owner_id"]))
                if subject.kind != "pilot" or chooser.kind not in ("pilot", "handler"):
                    continue
                PunishmentService(self.store)._row(c, row["id"])
                if body.get("character") and body["character"] != subject.incarnation:
                    continue
            except (ValueError, WorkflowError):
                continue
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    event=row["event_id"],
                    subject=subject.model_dump(mode="json"),
                    chooser=chooser.model_dump(mode="json"),
                    label=state.sheets[subject.entity].callsign,
                )
            )
        return result

    def preview_volunteer(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            return dict(candidates=self._candidates(c, viewer))

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        return [
            dict(
                id=x["id"],
                kind=KIND,
                revision=x["revision"],
                state=x["state"],
                actionable=str(viewer.user_id) in (x["owner_id"], x["subject_id"])
                and x["state"] != "resolved",
            )
            for x in self._rows(c)
            if x["kind"] == KIND and str(viewer.user_id) in (x["owner_id"], x["subject_id"])
        ]

    def _offer(self, c: Connection, identity: str) -> dict[str, Any]:
        row = next((x for x in self._rows(c) if x["id"] == identity and x["kind"] == KIND), None)
        if row is None:
            raise WorkflowError("Recover the actual original volunteer offer.")
        return row

    def get_offer(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._offer(c, identity)
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                raise WorkflowError("This proposal belongs to the actual chooser and volunteer.")
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                body=json.loads(row["body_json"]),
                can_decide=str(viewer.user_id) == row["owner_id"],
                can_withdraw=str(viewer.user_id) == row["subject_id"]
                and row["state"] != "resolved",
            )

    def volunteer(self, viewer: GuildViewer, key: str, work: str, account: str) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual offer to carry out this Punishment.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            actor = self._actor(c, viewer)
            candidate = next((x for x in self._candidates(c, viewer) if x["id"] == work), None)
            if candidate is None:
                raise WorkflowError(
                    "Choose an actual unchanged pending Punishment you can volunteer for."
                )
            if any(
                x["kind"] == KIND
                and x["state"] != "resolved"
                and json.loads(x["body_json"]).get("source_work") == work
                and x["subject_id"] == str(viewer.user_id)
                for x in self._rows(c)
            ):
                raise WorkflowError("Your actual original offer is already pending.")
            identity = str(uuid4())
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_volunteered",
                work_id=identity,
                source_work=work,
            )
            source = next(x for x in self._rows(c) if x["id"] == work)
            related(
                c,
                self.store,
                source,
                identity,
                int(source["owner_id"]),
                viewer.user_id,
                KIND,
                dict(
                    source_work=work,
                    source_revision=candidate["revision"],
                    source_event=candidate["event"],
                    actor=actor.model_dump(mode="json"),
                    target=candidate["subject"],
                    chooser=candidate["chooser"],
                    offered_event=event,
                    account=account.strip(),
                    immediate=False,
                ),
                event,
            )
            return dict(id=identity, state="pending")

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_volunteer",
            dict(work=work, account=account),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record your actual decision about the proposed executor.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row = self._offer(c, identity)
            if (
                row["owner_id"] != str(viewer.user_id)
                or row["revision"] != revision
                or row["state"] == "resolved"
            ):
                raise WorkflowError(
                    "The original actual chooser decides this current volunteer offer."
                )
            body = json.loads(row["body_json"])
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(body["actor"])
            target = ActorRef.model_validate(body["target"])
            chooser = ActorRef.model_validate(body["chooser"])
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == body["offered_event"],
                    )
                )
                .mappings()
                .first()
            )
            if (
                audit is None
                or audit["kind"] != "m3.enforcer_volunteered"
                or audit["actor_id"] != row["subject_id"]
                or actor.entity != row["subject_id"]
                or chooser.entity != row["owner_id"]
                or json.loads(audit["payload_json"]).get("source_work") != body["source_work"]
            ):
                raise WorkflowError(
                    "Recover the actual original volunteer and chooser source event."
                )
            source = None
            if accept:
                source = PunishmentService(self.store)._row(c, body["source_work"])
                if (
                    source["state"] == "resolved"
                    or source["owner_id"] != row["owner_id"]
                    or json.loads(source["body_json"]).get("role_case")
                ):
                    raise WorkflowError(
                        "This original Punishment changed; do not transfer/reopen its debt."
                    )
                from girlframe.engine.m3_enforcer import conditioning

                if (
                    not conditioning(state, actor)
                    or current_ref(state, viewer.user_id) != chooser
                    or current_ref(state, int(source["subject_id"])) != target
                ):
                    raise WorkflowError(
                        "Recover the original non-Dog Enforcer, chooser and affected Girl."
                    )
            first = next(
                (
                    x
                    for x in c.execute(
                        sa.select(t.m3["m3_required_work"]).where(
                            t.m3["m3_required_work"].c.campaign_id == self.store.campaign_id,
                            t.m3["m3_required_work"].c.id == identity,
                            t.m3["m3_required_work"].c.revision == 1,
                        )
                    ).mappings()
                ),
                None,
            )
            if first is None or json.loads(first["body_json"]) != body:
                raise WorkflowError(
                    "Recover the immutable original offer and actual source participants."
                )
            event, case_id = str(uuid4()), None
            if accept:
                assert source is not None
                case_id = str(uuid4())
                state, _ = open_case(
                    state,
                    profiles(c, self.store.campaign_id),
                    actor=actor,
                    target=target,
                    chooser=chooser,
                    source_kind="obedience_volunteer",
                    action=None,
                    source_event=event,
                    identity=case_id,
                    source_work=source["id"],
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_volunteer_decided",
                state,
                event_id=event,
                offer_id=identity,
                accepted=accept,
                case_id=case_id,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "event_id", "body_json", "state")
                    },
                    revision=revision + 1,
                    event_id=event,
                    state="resolved",
                    body_json=json.dumps(
                        body | dict(accepted=accept, decision=account.strip(), case_id=case_id)
                    ),
                )
            )
            if accept:
                synchronize(self.game, c, None, event)
            return dict(id=identity, state="accepted" if accept else "declined", case_id=case_id)

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_volunteer_decide",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            authorize=lambda c: self.game.authorize(c, viewer),
            auto_audit=False,
        )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual withdrawal of this pending offer.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._offer(c, identity)
            if (
                row["subject_id"] != str(viewer.user_id)
                or row["revision"] != revision
                or row["state"] == "resolved"
            ):
                raise WorkflowError(
                    "Only the original proposer withdraws their current unaccepted offer."
                )
            event = self.game.event(
                c, viewer.user_id, key, "m3.enforcer_volunteer_withdrawn", offer_id=identity
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "event_id", "state", "body_json")
                    },
                    revision=revision + 1,
                    event_id=event,
                    state="resolved",
                    body_json=json.dumps(
                        json.loads(row["body_json"])
                        | dict(resolution="offer_withdrawn", account=account.strip())
                    ),
                )
            )
            return dict(id=identity, state="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_volunteer_withdraw",
            dict(id=identity, revision=revision, account=account),
            operation,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
            auto_audit=False,
        )
