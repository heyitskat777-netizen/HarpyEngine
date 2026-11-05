"""Owned archived careers and explicit fresh-character drafts over stable SQL profiles."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_careers as rules
from girlframe.engine.creation import CreationDraft
from girlframe.engine.drafts import DraftInput
from girlframe.engine.frame_setup import frame_setup
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_career_state import CareerArchive, CareerReturn, Ending
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def end_in_transaction(
    c: Connection,
    game: GameService,
    state: GameState,
    actor: ActorRef,
    *,
    reason: Ending,
    source_event: str,
    account: str,
    archive_id: str,
) -> GameState:
    """Trusted source resolver supplies the already-owned actual ending and event ID."""
    profile = c.execute(
        sa.select(t.characters.c.id, t.characters.c.revision).where(
            t.characters.c.campaign_id == game.store.campaign_id,
            t.characters.c.user_id == actor.entity,
        )
    ).first()
    if (
        profile is None
        or game.character_binding(c, state, int(actor.entity), require_current_profile=False)
        != actor.incarnation
    ):
        raise WorkflowError("STALE_CAREER: end only the original actual character.")
    return rules.end(
        state,
        actor,
        reason=reason,
        source_event=source_event,
        account=account,
        archive_id=archive_id,
        profile_id=profile.id,
        profile_revision=profile.revision,
    )


def synchronize_end(
    c: Connection,
    game: GameService,
    archive: CareerArchive,
    *,
    exclude_work: tuple[str, ...] = (),
) -> None:
    """Close original unavailable-subject work; never resolve someone else's required effect."""
    saved = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == archive.source_event,
        )
    )
    proof = GameState.model_validate_json(saved) if saved else None
    if proof is None or archive not in proof.career_archives:
        raise WorkflowError(
            "SOURCE_CAREER_MISSING: commit the actual ending before synchronization."
        )
    scenes = t.m2["m2_scenes"]
    for row in c.execute(
        sa.select(scenes).where(
            scenes.c.campaign_id == game.store.campaign_id,
            scenes.c.open.is_(True),
        )
    ).mappings():
        people = json.loads(row["participants_json"])
        owner = int(archive.actor.entity)
        cast = next((x for x in proof.scene_casts if x.id == row["id"] and x.open), None)
        actual = (
            sorted(
                {x.controller for x in cast.roles}
                | ({cast.facilitator} if cast.facilitator else set())
            )
            if cast
            else [x for x in people if x != owner]
        )
        if sorted(people) != actual:
            c.execute(
                scenes.update()
                .where(
                    scenes.c.campaign_id == game.store.campaign_id,
                    scenes.c.channel_id == row["channel_id"],
                )
                .values(
                    revision=row["revision"] + 1,
                    participants_json=json.dumps(actual),
                )
            )
    work = t.m3["m3_required_work"]
    latest = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.subject_id == archive.actor.entity,
            )
            .order_by(work.c.revision)
        ).mappings()
    }
    for task in latest.values():
        if task["id"] in exclude_work or task["state"] == "resolved":
            continue
        declared_owner = json.loads(task["body_json"]).get("owner")
        if isinstance(declared_owner, dict) and declared_owner.get("kind"):
            subject = ActorRef.model_validate(declared_owner)
            if (
                subject.kind != "pilot"
                or subject.entity != archive.actor.entity
                or subject.incarnation is not None
                and subject != archive.actor
            ):
                continue
        if work_subject_character(c, game, task) != archive.actor.incarnation:
            continue
        body = json.loads(task["body_json"]) | dict(
            resolution="original_character_career_ended",
            career_archive=archive.id,
            original_character=archive.actor.incarnation,
        )
        c.execute(
            work.insert().values(
                **{
                    k: v
                    for k, v in task.items()
                    if k not in ("body_json", "revision", "state", "event_id")
                },
                revision=task["revision"] + 1,
                state="resolved",
                body_json=json.dumps(body, sort_keys=True),
                event_id=archive.source_event,
            )
        )
    from girlframe.services.m3_off_duty import end_off_duty_original
    from girlframe.services.m3_scene_requisitions import end_career_rooms

    end_career_rooms(c, game.store, archive)
    end_off_duty_original(c, game, archive)


def work_subject_character(c: Connection, game: GameService, task: dict[str, Any]) -> str:
    """A UID-only old task still belongs to its actual original source subject."""
    body = json.loads(task["body_json"])
    declared = body.get("character") or body.get("subject_character")
    if declared:
        return str(declared)
    event_sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == task["event_id"],
        )
    )
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == history.c.campaign_id,
                t.events.c.id == history.c.event_id,
            ),
        )
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.seq <= event_sequence if event_sequence is not None else sa.false(),
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    source = GameState.model_validate_json(raw) if raw else None
    sheet = source.sheets.get(task["subject_id"]) if source else None
    if sheet is None:
        raise WorkflowError(
            "Recover the actual original subject of required work before ending it."
        )
    assert source is not None
    return sheet.character_id or game.character_binding(
        c, source, int(task["subject_id"]), require_current_profile=False
    )


class CareerService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _archive(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, CareerArchive]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        archive = next(
            (
                x
                for x in state.career_archives
                if x.id == identity and x.actor.entity == str(viewer.user_id)
            ),
            None,
        )
        if archive is None:
            raise WorkflowError("This career archive belongs to its original human owner.")
        history = t.m2["m2_state_history"]
        original = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == archive.source_event,
            )
        )
        proof = GameState.model_validate_json(original) if original else None
        if proof is None or archive not in proof.career_archives:
            raise WorkflowError("SOURCE_CAREER_MISSING: recover the original recorded ending.")
        return state, archive

    def _idle(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError(
                "Finish actual Plays and restore chat before starting a replacement."
            )

    def archives(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return [
                dict(
                    id=x.id, ending=x.ending, callsign=rules.original_sheet(state, x.actor).callsign
                )
                for x in state.career_archives
                if x.actor.entity == str(viewer.user_id)
            ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, archive = self._archive(c, viewer, identity)
            current = rules.binding(state, viewer.user_id)
            return dict(
                archive=archive.model_dump(mode="json"),
                game_revision=state.revision,
                sheet=rules.original_sheet(state, archive.actor).model_dump(mode="json"),
                can_replace=current is not None
                and not current.active
                and current.character == archive.actor.incarnation
                and str(viewer.user_id) not in state.sheets,
                pending_character=current.character
                if current and current.active and str(viewer.user_id) not in state.sheets
                else None,
            )

    def begin_replacement(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        draft: DraftInput,
    ) -> dict[str, Any]:
        draft = DraftInput.model_validate_json(draft.model_dump_json())

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")
            self._archive(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state, archive = self._archive(c, viewer, identity)
            if state.revision != revision:
                raise WorkflowError("STALE_CAREER: reopen the original replacement request.")
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .one()
            )
            source, character = str(uuid4()), str(uuid4())
            new_revision = profile["revision"] + 1
            changed = rules.replacement(
                state,
                identity,
                owner=viewer.user_id,
                new_character=character,
                profile_id=profile["id"],
                profile_revision=new_revision,
                source_event=source,
            )
            public = json.dumps(draft.model_dump(exclude={"notes"}))
            private = json.dumps(dict(notes=draft.notes))
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
                .values(revision=new_revision, public_json=public, private_json=private)
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.replacement_character_started",
                changed,
                event_id=source,
                archive_id=archive.id,
                character_id=character,
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=new_revision,
                    character_id=profile["id"],
                    event_id=event,
                    public_json=public,
                    private_json=private,
                )
            )
            creation_revision = (
                c.scalar(
                    sa.select(sa.func.max(t.creation_drafts.c.revision)).where(
                        t.creation_drafts.c.campaign_id == self.store.campaign_id,
                        t.creation_drafts.c.user_id == str(viewer.user_id),
                    )
                )
                or 0
            )
            empty = CreationDraft(
                girl_playbook=draft.girl_playbook,
                frame_playbook=draft.frame_playbook,
                frame_setup=frame_setup(draft.frame_playbook),
            )
            c.execute(
                t.creation_drafts.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=creation_revision + 1,
                    character_revision=new_revision,
                    event_id=event,
                    body_json=empty.model_dump_json(),
                )
            )
            self.store._enqueue_sync(c, viewer.user_id, new_revision, draft)
            return dict(
                character=character, profile_revision=new_revision, state="new_creation_draft"
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.replacement_character_started",
                dict(
                    archive=identity,
                    revision=revision,
                    draft=draft.model_dump(mode="json"),
                ),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def status_requests(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._status_requests(c, viewer)

    def _status_requests(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        HandlerService(self.store).authorize(c, viewer)
        state = load_state(c, self.store.campaign_id)
        result = []
        for owner in {x.owner for x in state.incarnation_bindings}:
            current = rules.binding(state, owner)
            if (
                current is None
                or not current.active
                or current.previous_archive is None
                or str(owner) in state.sheets
            ):
                continue
            profile = c.scalar(
                sa.select(t.characters.c.public_json).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(owner),
                )
            )
            if profile is None:
                raise WorkflowError("Recover the new character's actual profile first.")
            result.append(
                dict(
                    owner=owner,
                    character=current.character,
                    callsign=json.loads(profile)["callsign"],
                    position=current.status_position,
                    game_revision=state.revision,
                    maximum=len(state.order),
                )
            )
        return result

    def assign_status(
        self,
        viewer: GuildViewer,
        key: str,
        owner: int,
        character: str,
        revision: int,
        position: int,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")
            HandlerService(self.store).authorize(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or state.handler != viewer.user_id:
                raise WorkflowError("STALE_CAREER: review the actual replacement Status request.")
            source = str(uuid4())
            changed = rules.replacement_status(state, owner, character, position, source)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.replacement_status_assigned",
                changed,
                event_id=source,
                owner=owner,
                character=character,
            )
            return dict(character=character, position=position)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.replacement_status_assigned",
                dict(
                    owner=owner,
                    character=character,
                    revision=revision,
                    position=position,
                ),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _return_candidates(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        HandlerService(self.store).authorize(c, viewer)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                owner=int(x.actor.entity),
                ending=x.ending,
                callsign=PilotSheet.model_validate_json(x.sheet_json).callsign,
                maximum=len([uid for uid in state.order if str(uid) != x.actor.entity]),
                game_revision=state.revision,
            )
            for x in state.career_archives
            if x.ending in ("imprisonment", "reserve")
            and rules.archive_for(state, x.actor) == x
            and (
                x.actor.entity not in state.sheets
                or state.sheets[x.actor.entity].character_id != x.actor.incarnation
            )
        ]

    def return_candidates(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._return_candidates(c, viewer)

    def _return_offer(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, CareerReturn, CareerArchive]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        ticket = next(
            (
                x
                for x in state.career_returns
                if x.id == identity and viewer.user_id in (x.owner, state.handler)
            ),
            None,
        )
        if ticket is None:
            raise WorkflowError("This original return offer belongs to its actual participants.")
        archive = next(x for x in state.career_archives if x.id == ticket.archive)
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == ticket.source_event,
            )
        )
        source = GameState.model_validate_json(body) if body else None
        first = (
            next((x for x in source.career_returns if x.id == identity), None) if source else None
        )
        if first is None or first != ticket.model_copy(
            update={"state": "offered", "response_event": None}
        ):
            raise WorkflowError("SOURCE_RETURN_MISSING: recover the actual Handler offer.")
        return state, ticket, archive

    def _return_requests(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, archive=x.archive, owner=x.owner, state=x.state)
            for x in state.career_returns
            if x.owner == viewer.user_id and x.state == "offered"
        ]

    def return_requests(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._return_requests(c, viewer)

    def get_return(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, ticket, archive = self._return_offer(c, viewer, identity)
            original = PilotSheet.model_validate_json(archive.sheet_json)
            current = state.sheets.get(str(ticket.owner))
            return dict(
                id=ticket.id,
                state=ticket.state,
                owner=ticket.owner,
                callsign=original.callsign,
                account=ticket.account,
                position=ticket.position,
                current_callsign=current.callsign if current else None,
                game_revision=state.revision,
                can_respond=viewer.user_id == ticket.owner and ticket.state == "offered",
            )

    def offer_return(
        self,
        viewer: GuildViewer,
        key: str,
        archive_id: str,
        revision: int,
        position: int,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "discipline")
            HandlerService(self.store).authorize(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_RETURN: review the current original return proposal.")
            archive = next((x for x in state.career_archives if x.id == archive_id), None)
            if archive is None:
                raise WorkflowError("Choose an actual original archived character.")
            history = t.m2["m2_state_history"]
            body = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == archive.source_event,
                )
            )
            proof = GameState.model_validate_json(body) if body else None
            if proof is None or archive not in proof.career_archives:
                raise WorkflowError(
                    "SOURCE_CAREER_MISSING: recover the actual imprisoned character."
                )
            owner = int(archive.actor.entity)
            others = tuple(
                ActorRef(
                    kind="pilot",
                    entity=str(uid),
                    incarnation=self.game.character_binding(
                        c, state, uid, require_current_profile=False
                    ),
                )
                for uid in state.order
                if uid != owner
            )
            identity, source = str(uuid4()), str(uuid4())
            changed = rules.offer_return(
                state,
                archive_id,
                handler=viewer.user_id,
                identity=identity,
                source_event=source,
                position=position,
                account=account,
                other_characters=others,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.career_return_offered",
                changed,
                event_id=source,
                offer_id=identity,
                archive_id=archive_id,
            )
            return dict(id=identity, state="offered")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.career_return_offered",
                dict(archive=archive_id, revision=revision, position=position, account=account),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def answer_return(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")
            _, ticket, _ = self._return_offer(c, viewer, identity)
            if viewer.user_id != ticket.owner:
                raise WorkflowError("Only the original human owner chooses its active character.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state, ticket, archive = self._return_offer(c, viewer, identity)
            if (
                state.revision != revision
                or ticket.state != "offered"
                or type(accept) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("STALE_RETURN: reopen the original owned return offer.")
            source = str(uuid4())
            if not accept:
                state.career_returns = [
                    x.model_copy(update={"state": "declined", "response_event": source})
                    if x.id == identity
                    else x
                    for x in state.career_returns
                ]
                self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.career_return_declined",
                    state,
                    event_id=source,
                    offer_id=identity,
                )
                return dict(id=identity, state="declined")
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .one()
            )
            current = state.sheets.get(str(viewer.user_id))
            parked = None
            if current is not None:
                from girlframe.engine.m3_actor_bonds import is_helpless

                current_ref = ActorRef(
                    kind="pilot", entity=str(viewer.user_id), incarnation=current.character_id
                )
                tasks = t.m3["m3_required_work"]
                latest = {
                    row["id"]: row
                    for row in c.execute(
                        sa.select(tasks)
                        .where(
                            tasks.c.campaign_id == self.store.campaign_id,
                            tasks.c.subject_id == str(viewer.user_id),
                        )
                        .order_by(tasks.c.revision)
                    ).mappings()
                }
                if (
                    any(row["state"] != "resolved" for row in latest.values())
                    or is_helpless(state, current_ref)
                    or current.medical_state != "fit"
                    or any(
                        x.held and current_ref in (x.actor, x.target) for x in state.enforcer_grasps
                    )
                    or any(
                        x.actor == current_ref and x.custody is not None for x in state.placements
                    )
                    or any(
                        x.owner == viewer.user_id
                        and x.state == "pending"
                        and x.kind != "tag_rejection_permission"
                        for x in state.obligations
                    )
                    or any(
                        x.active and current_ref in (x.traveler, x.supervisor)
                        for x in state.escort_journeys
                    )
                ):
                    raise WorkflowError(
                        "Resolve the current Girl's obligations before changing active characters."
                    )
                missions = t.m3["m3_missions"]
                for body in c.scalars(
                    sa.select(missions.c.body_json).where(
                        missions.c.campaign_id == self.store.campaign_id,
                        missions.c.phase.in_(("active", "ending", "awaiting_consequences")),
                    )
                ):
                    from girlframe.engine.m3_missions import Mission
                    from girlframe.services.m3_missions import MissionService

                    mission = Mission.model_validate_json(body)
                    actual = MissionService(self.store)._source_characters(c, mission)
                    if actual.get(str(viewer.user_id)) == current_ref.incarnation:
                        raise WorkflowError(
                            "Finish the current Girl's mission before changing active characters."
                        )
                periods = t.m3["m3_off_duty"]
                for body in c.scalars(
                    sa.select(periods.c.body_json).where(
                        periods.c.campaign_id == self.store.campaign_id,
                        periods.c.phase != "complete",
                    )
                ):
                    from girlframe.engine.m3_off_duty import Period

                    period = Period.model_validate_json(body)
                    if period.character_ids.get(str(viewer.user_id)) == current_ref.incarnation:
                        raise WorkflowError(
                            "Finish the current Girl's Off-Duty period before changing characters."
                        )
                from girlframe.engine.m3_scene_requisitions import active
                from girlframe.services.m3_scene_requisitions import benefit, rows

                if any(
                    active(saved) and current_ref in (saved.actor, saved.companion)
                    for row in rows(c, self.store)
                    for saved in (benefit(row),)
                ):
                    raise WorkflowError(
                        "Close the actual protected scene before changing active characters."
                    )
                state = end_in_transaction(
                    c,
                    self.game,
                    state,
                    ActorRef(
                        kind="pilot", entity=str(viewer.user_id), incarnation=current.character_id
                    ),
                    reason="reserve",
                    source_event=source,
                    account="Original owner chose the Handler-authorized return",
                    archive_id=str(uuid4()),
                )
                parked = state.career_archives[-1]
            new_revision = profile["revision"] + 1
            state = rules.return_original(
                state,
                identity,
                response_event=source,
                profile_id=profile["id"],
                profile_revision=new_revision,
                account=account,
            )
            from girlframe.services.m3_harpy_defeat import restore_death_tags

            state = restore_death_tags(self.game, c, state, archive.actor, source)
            restored = state.sheets[str(viewer.user_id)]
            original_private = c.scalar(
                sa.select(t.snapshots.c.private_json).where(
                    t.snapshots.c.campaign_id == self.store.campaign_id,
                    t.snapshots.c.user_id == str(viewer.user_id),
                    t.snapshots.c.revision == archive.profile_revision,
                )
            )
            if original_private is None:
                raise WorkflowError("Recover the original profile snapshot before its return.")
            public = json.dumps(
                dict(
                    callsign=restored.callsign,
                    girl_playbook=restored.girl,
                    frame_playbook=restored.frame,
                )
            )
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
                .values(revision=new_revision, public_json=public, private_json=original_private)
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.original_character_returned",
                state,
                event_id=source,
                offer_id=identity,
                archive_id=archive.id,
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=new_revision,
                    character_id=profile["id"],
                    event_id=event,
                    public_json=public,
                    private_json=original_private,
                )
            )
            if restored.callsign.strip():
                self.store._enqueue_sync(
                    c,
                    viewer.user_id,
                    new_revision,
                    DraftInput(
                        callsign=restored.callsign,
                        girl_playbook=restored.girl,
                        frame_playbook=restored.frame,
                    ),
                )
            if parked is not None:
                synchronize_end(c, self.game, parked)
            return dict(id=identity, state="returned", character=archive.actor.incarnation)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.career_return_answered",
                dict(id=identity, revision=revision, accept=accept, account=account),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
