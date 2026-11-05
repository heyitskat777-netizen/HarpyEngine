"""Private inflictor selections and actual original-patient surgery responses."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_lobotomy as rules
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_lobotomy_state import PROMPTS, Plan, Surgery
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def start_in_transaction(
    c: Connection,
    service: Any,
    viewer: GuildViewer,
    key: str,
    row: dict[str, Any],
    bundle: list[dict[str, Any]],
) -> dict[str, Any]:
    state = load_state(c, service.store.campaign_id)
    if state.handler != viewer.user_id:
        raise WorkflowError("Only the actual Handler may inflict Severe surgery.")
    existing = service._body(row).get("lobotomy_id")
    if existing:
        return {"id": row["id"], "state": "surgery_pending", "surgery": existing}
    identity, source = str(uuid4()), str(uuid4())
    state.lobotomies.append(
        Surgery(
            id=identity,
            subject=current_ref(state, int(row["subject_id"])),
            inflictor=current_ref(state, viewer.user_id),
            work_ids=tuple(x["id"] for x in bundle),
            source_event=source,
        )
    )
    event = service.game.event(
        c,
        viewer.user_id,
        key,
        "m3.lobotomy_started",
        state,
        event_id=source,
        surgery=identity,
        work_id=row["id"],
    )
    for item in bundle:
        service._save(c, item, event, body=service._body(item) | {"lobotomy_id": identity})
    return {"id": row["id"], "state": "surgery_pending", "surgery": identity}


class LobotomyService:
    def __init__(self, store: OnboardingStore):
        from girlframe.services.m3_punishments import PunishmentService

        self.store, self.discipline = store, PunishmentService(store)
        self.game, self.access = self.discipline.game, Access(store)

    def _get(self, c: Connection, viewer: GuildViewer, identity: str) -> tuple[GameState, Surgery]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        surgery = next((x for x in state.lobotomies if x.id == identity), None)
        if surgery is None or viewer.user_id not in (
            int(surgery.subject.entity),
            int(surgery.inflictor.entity),
        ):
            raise WorkflowError("This surgery belongs to its actual inflictor and patient.")
        source = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == surgery.source_event,
            )
        )
        proof = GameState.model_validate_json(source) if source else None
        original = next((x for x in proof.lobotomies if x.id == identity), None) if proof else None
        if original is None or (original.subject, original.inflictor, original.work_ids) != (
            surgery.subject,
            surgery.inflictor,
            surgery.work_ids,
        ):
            raise WorkflowError("Recover the actual source surgery and original participants.")
        try:
            rules._actual(state, surgery)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        return state, surgery

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for surgery in state.lobotomies:
            owner = surgery.subject if surgery.phase == "responses" else surgery.inflictor
            if surgery.phase == "applied" or owner.entity != str(viewer.user_id):
                continue
            try:
                _, saved = self._get(c, viewer, surgery.id)
            except WorkflowError:
                continue
            result.append(
                dict(
                    id=saved.id,
                    kind="lobotomy",
                    phase=saved.phase,
                    subject=int(saved.subject.entity),
                )
            )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, surgery = self._get(c, viewer, identity)
            sheet = state.sheets[surgery.subject.entity]
            owner = surgery.subject if surgery.phase == "responses" else surgery.inflictor
            actors = [
                (current_ref(state, uid), state.sheets[str(uid)].callsign)
                for uid in state.order
                if str(uid) != surgery.subject.entity
            ]
            if state.world:
                actors.extend(
                    (ActorRef(kind="npc", entity=x.id), x.name) for x in state.world.npcs if x.alive
                )
                actors.extend(
                    (ActorRef(kind="external_pilot", entity=x.id), x.name)
                    for x in state.world.pilots
                    if x.alive
                )
                actors.extend(
                    (ActorRef(kind="gorgon", entity=x.id), x.name)
                    for x in state.world.gorgons
                    if x.alive
                )
            actors.extend(
                (ActorRef(kind="external_pilot", entity=x.id), x.name)
                for x in state.harpy_states
                if x.alive
            )
            if viewer.user_id != int(surgery.inflictor.entity):
                actors = []
            return dict(
                id=surgery.id,
                phase=surgery.phase,
                owner=int(owner.entity),
                patient=sheet.callsign,
                game_revision=state.revision,
                plan=surgery.plan.model_dump(mode="json") if surgery.plan else None,
                prompts={key: PROMPTS[key] for key in surgery.plan.options} if surgery.plan else {},
                can_act=owner.entity == str(viewer.user_id) and surgery.phase != "applied",
                identities=[
                    dict(id=x.id, name=x.name, slot=x.slot, protected=x.protected, paired=x.paired)
                    for x in sheet.identities
                ],
                protected_slots=[
                    x.slot for x in sheet.identities if x.protected and x.slot is not None
                ],
                starting=list(CATALOG[sheet.girl]["identities"]),
                actors=[
                    dict(ref=x.model_dump(mode="json"), label=name, token=x.token)
                    for x, name in actors
                ],
                plays=list(rules.ROLLABLE),
            )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        plan: Plan | None,
        descriptions: dict[str, str] | None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.access.authorize(c, viewer, "discipline")
            _, surgery = self._get(c, viewer, identity)
            owner = surgery.inflictor if plan is not None else surgery.subject
            if owner.entity != str(viewer.user_id):
                raise WorkflowError("Only the actual owner may provide these surgery choices.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, surgery = self._get(c, viewer, identity)
            if state.revision != revision:
                raise WorkflowError("STALE_SURGERY: reopen the current original patient.")
            for work in surgery.work_ids:
                row = self.discipline._row(c, work)
                self.discipline._check(c, row, row["revision"], revision)
                if (
                    row["state"] == "resolved"
                    or self.discipline._body(row).get("lobotomy_id") != identity
                ):
                    raise WorkflowError("The source Punishment has changed.")
            source = str(uuid4())
            ruling = self.store.policy.owner_m3_rulings
            changed = (
                rules.prepare(
                    state,
                    identity,
                    plan,
                    source,
                    allow_duplicate_labels=bool(
                        ruling and ruling.identity_duplicate_labels == "distinct_ids"
                    ),
                )
                if plan is not None
                else rules.respond(state, identity, descriptions or {}, source)
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.lobotomy_choices_saved",
                changed,
                event_id=source,
                surgery=identity,
            )
            return dict(
                id=identity,
                phase=next(x.phase for x in changed.lobotomies if x.id == identity),
                event=event,
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.lobotomy_choices_saved",
                dict(
                    identity=identity,
                    revision=revision,
                    plan=plan.model_dump(mode="json") if plan else None,
                    descriptions=descriptions,
                ),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def prepare(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, plan: Plan
    ) -> dict[str, Any]:
        return self._write(viewer, key, identity, revision, plan, None)

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        descriptions: dict[str, str],
    ) -> dict[str, Any]:
        return self._write(viewer, key, identity, revision, None, descriptions)

    def finish(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        from girlframe.engine.m3_punishments import Details

        with self.store.engine.connect() as c:
            _, surgery = self._get(c, viewer, identity)
            work = self.discipline.get(viewer, surgery.work_ids[0])
            execution_account = None
            row = self.discipline._row(c, surgery.work_ids[0])
            if self.discipline._body(row).get("role_case"):
                from girlframe.services.m3_role_punishments import pc_execution

                case = pc_execution(
                    c, self.game, row, viewer, Details(kind="lobotomization", surgery=identity)
                )
                if (
                    case is None
                    or case.source_kind != "handler_play"
                    or case.chooser != case.executor
                    or case.executor != surgery.inflictor
                    or case.subject != surgery.subject
                    or case.chooser_controller != case.executor_controller
                    or not case.scene_account.strip()
                ):
                    raise WorkflowError(
                        "Use the actual same Handler's saved surgery scene and owned execution."
                    )
                execution_account = case.scene_account
        return self.discipline.apply(
            viewer,
            key,
            surgery.work_ids[0],
            work["revision"],
            work["game_revision"],
            Details(kind="lobotomization", surgery=identity),
            execution_account=execution_account,
        )


def rename_profile(
    c: Connection, store: OnboardingStore, state: GameState, surgery_id: str
) -> dict[str, Any] | None:
    surgery = next(x for x in state.lobotomies if x.id == surgery_id)
    if surgery.plan is None or "name" not in surgery.plan.options:
        return None
    profile = dict(
        c.execute(
            sa.select(t.characters).where(
                t.characters.c.campaign_id == store.campaign_id,
                t.characters.c.user_id == surgery.subject.entity,
            )
        )
        .mappings()
        .one()
    )
    public = json.loads(profile["public_json"])
    public["callsign"] = state.sheets[surgery.subject.entity].callsign
    profile["revision"] += 1
    profile["public_json"] = json.dumps(public)
    c.execute(
        t.characters.update()
        .where(
            t.characters.c.campaign_id == store.campaign_id,
            t.characters.c.user_id == surgery.subject.entity,
        )
        .values(revision=profile["revision"], public_json=profile["public_json"])
    )
    state.sheets[surgery.subject.entity].source_profile_revision = profile["revision"]
    return profile


def save_name_snapshot(
    c: Connection, store: OnboardingStore, profile: dict[str, Any], event: str
) -> None:
    c.execute(
        t.snapshots.insert().values(
            campaign_id=store.campaign_id,
            user_id=profile["user_id"],
            revision=profile["revision"],
            character_id=profile["id"],
            event_id=event,
            public_json=profile["public_json"],
            private_json=profile["private_json"],
        )
    )
    public = json.loads(profile["public_json"])
    draft = store._cosmetic_draft(c, int(profile["user_id"]), public)
    store._enqueue_sync(c, int(profile["user_id"]), profile["revision"], draft)
