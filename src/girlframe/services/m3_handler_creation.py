"""Private appointment-bound creation, exact owned agreements and atomic initial effects."""

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_creation as rules
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_state import Agreement, Draft, NpcAgreement, SavedDraft
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "handler_creation"
AGREEMENT = "handler_creation_agreement"
NPC_AGREEMENT = "handler_creation_npc_agreement"
Offer = Agreement | NpcAgreement


def _recipient(offer: Offer) -> int:
    return (
        offer.relationship.controller
        if isinstance(offer, NpcAgreement)
        else int(offer.bond.pilot.entity)
    )


def _source_hash(value: SavedDraft | Offer, raw: dict[str, Any]) -> str:
    # New defaults cannot rewrite the digest of an actual older signed source.
    excluded: dict[str, Any] = {}
    if "generation" not in raw:
        excluded["generation"] = True
    if isinstance(value, SavedDraft) and "npc_starting" not in raw.get("draft", {}):
        excluded["draft"] = {"npc_starting"}
    return hashlib.sha256(value.model_dump_json(exclude=excluded).encode()).hexdigest()


class HandlerCreationService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _policy(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "playbooks", director_response=True)
        rulings = self.store.policy.owner_m3_rulings
        if rulings is None or rulings.handler_creation != "owned_shared_choices_preserve_existing":
            raise WorkflowError("UNRESOLVED_RULING: record the Handler creation interpretation.")

    def _appointment(self, c: Connection, viewer: GuildViewer) -> str:
        HandlerService(self.store).authorize(c, viewer)
        return self._appointment_source(c, viewer.user_id)

    def _appointment_source(self, c: Connection, owner: int) -> str:
        handler = HandlerService(self.store)
        if (
            load_state(c, self.store.campaign_id).handler != owner
            or handler.current(c)[1].handler_id != owner
            or not handler._member(c, owner)
        ):
            raise WorkflowError("Recover the actual canonical Handler appointment first.")
        setup = t.setup_revisions
        row = (
            c.execute(
                sa.select(setup.c.event_id, setup.c.body_json)
                .join(
                    t.events,
                    t.events.c.id == setup.c.event_id,
                )
                .where(
                    setup.c.campaign_id == self.store.campaign_id,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "campaign.handler_appointed",
                )
                .order_by(setup.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or json.loads(row["body_json"]).get("handler_id") != owner:
            raise WorkflowError("Recover the same-campaign original appointment source.")
        return str(row["event_id"])

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
        if row is None or row["kind"] not in (KIND, AGREEMENT, NPC_AGREEMENT):
            raise WorkflowError("This Handler creation request is unavailable.")
        return dict(row)

    def _draft_row(
        self, c: Connection, owner: int, appointment: str | None
    ) -> dict[str, Any] | None:
        table = t.m3["m3_required_work"]
        query = (
            sa.select(table)
            .join(t.events, t.events.c.id == table.c.event_id)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.owner_id == str(owner),
                table.c.kind == KIND,
            )
        )
        if appointment is not None:
            query = query.where(
                sa.func.json_extract(table.c.body_json, "$.appointment") == appointment,
                sa.func.coalesce(sa.func.json_extract(table.c.body_json, "$.generation"), "initial")
                == rules.generation(load_state(c, self.store.campaign_id)),
            )
        row = c.execute(query.order_by(t.events.c.seq.desc()).limit(1)).mappings().first()
        return dict(row) if row else None

    def _draft(self, c: Connection, row: dict[str, Any]) -> SavedDraft:
        try:
            body = SavedDraft.model_validate_json(row["body_json"])
            source = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.id == row["event_id"],
                        t.events.c.campaign_id == self.store.campaign_id,
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(source["payload_json"]) if source else {}
            if (
                source is None
                or source["kind"] not in ("m3.handler_draft_saved", "m3.handler_activated")
                or source["actor_id"] != row["owner_id"]
                or row["owner_id"] != row["subject_id"]
                or metadata.get("work_id") != row["id"]
                or metadata.get("body_sha256") != _source_hash(body, json.loads(row["body_json"]))
                or not row["campaign_context"]
            ):
                raise ValueError()
            return body
        except (ValueError, KeyError):
            raise WorkflowError(
                "SOURCE_HANDLER_DRAFT_MISSING: recover the original saved draft."
            ) from None

    def _save_work(
        self, c: Connection, row: dict[str, Any], event: str, body: Any, state: str = "pending"
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "body_json", "event_id", "state")
                },
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
                state=state,
            )
        )

    def _actual(self, c: Connection, saved: SavedDraft, *, complete: bool = True) -> None:
        state = load_state(c, self.store.campaign_id)
        if saved.generation != rules.generation(state) or any(
            x.actor.incarnation == saved.persona_id for x in state.handler_archives
        ):
            raise WorkflowError("STALE_HANDLER_GENERATION: start a fresh original persona.")
        for choice in saved.draft.starting:
            uid = int(choice.pilot.entity)
            if not HandlerService(self.store)._member(c, uid):
                raise WorkflowError("Recover the selected Girl's campaign membership.")
            resolve(
                state,
                choice.pilot,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )

        selected_npcs = set(saved.draft.surveilled)
        if state.handler is None:
            raise WorkflowError("Recover the actual Handler appointment before starting labels.")
        if saved.draft.sympathizer is not None:
            selected_npcs.add(saved.draft.sympathizer)
        npcs = {x.id: x for x in state.world.npcs} if state.world else {}
        packages = {x.npc.entity: x for x in saved.draft.npc_starting}
        for identity in selected_npcs:
            npc = npcs.get(identity)
            if npc is None or not npc.alive:
                raise WorkflowError("Choose actual living NPCs for the starting relationships.")
            package = packages.get(identity)
            if package is not None:
                if (
                    npc.controller != package.controller
                    or not HandlerService(self.store)._member(c, package.controller)
                    or not (npc.revealed or npc.controller == state.handler)
                ):
                    raise WorkflowError(
                        "Recover the actual known NPC and its participating controller."
                    )
            elif complete and (
                state.handler_archives
                or depth(
                    state,
                    ActorRef(kind="handler", entity=str(state.handler)),
                    ActorRef(kind="npc", entity=identity),
                )
                < 1
            ):
                raise WorkflowError(
                    "Describe and request the new persona's Personal NPC relationship."
                )

    def _view(self, c: Connection, viewer: GuildViewer) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        try:
            appointment = self._appointment(c, viewer)
        except WorkflowError:
            appointment = None
        row = self._draft_row(c, viewer.user_id, appointment)
        saved = self._draft(c, row) if row else None
        if appointment is None and saved is None:
            raise WorkflowError("Only the current appointed Handler can begin creation.")
        state = load_state(c, self.store.campaign_id)
        draft = saved.draft if saved else Draft()
        pilots = []
        if appointment is not None:
            for uid in state.order:
                if HandlerService(self.store)._member(c, uid):
                    ref = ActorRef(
                        kind="pilot",
                        entity=str(uid),
                        incarnation=self.game.character_binding(
                            c, state, uid, require_current_profile=False
                        ),
                    )
                    pilots.append(
                        dict(
                            ref=ref.model_dump(mode="json"),
                            token=ref.token,
                            label=state.sheets[str(uid)].callsign,
                        )
                    )
        npcs: list[dict[str, Any]] = (
            [
                dict(
                    id=x.id,
                    name=x.name,
                    controller=x.controller,
                    legacy=not state.handler_archives
                    and depth(
                        state,
                        ActorRef(kind="handler", entity=str(viewer.user_id)),
                        ActorRef(kind="npc", entity=x.id),
                    )
                    > 0,
                )
                for x in state.world.npcs
                if x.alive
                and (
                    x.revealed
                    or x.controller == viewer.user_id
                    or (
                        not state.handler_archives
                        and depth(
                            state,
                            ActorRef(kind="handler", entity=str(viewer.user_id)),
                            ActorRef(kind="npc", entity=x.id),
                        )
                        > 0
                    )
                )
            ]
            if state.world and appointment is not None
            else []
        )
        return dict(
            id=row["id"] if row else None,
            revision=row["revision"] if row else 0,
            appointment=appointment,
            persona_id=saved.persona_id if saved else None,
            generation=rules.generation(state),
            editable=appointment is not None
            and (saved is None or saved.appointment == appointment)
            and state.handler_persona is None,
            draft=draft.model_dump(mode="json"),
            missing=list(draft.missing)
            + [
                "NPC relationship history: " + x["name"]
                for x in npcs
                if x["id"]
                in set(draft.surveilled) | ({draft.sympathizer} if draft.sympathizer else set())
                and not x["legacy"]
                and x["id"] not in {n.npc.entity for n in draft.npc_starting}
            ],
            pilots=pilots,
            npcs=npcs if appointment is not None else [],
            game_revision=state.revision,
            activated=bool(
                state.handler_persona and saved and state.handler_persona.id == saved.persona_id
            ),
        )

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._view(c, viewer)

    def save(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        appointment: str,
        draft: Draft,
        *,
        generation: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._policy(c, viewer)
            current_generation = rules.generation(load_state(c, self.store.campaign_id))
            if generation != current_generation and not (
                generation is None and current_generation == "initial"
            ):
                raise WorkflowError("STALE_HANDLER_GENERATION: reopen the new persona's creation.")
            if self._appointment(c, viewer) != appointment:
                raise WorkflowError("STALE_HANDLER: reopen the original appointment.")

        def operation(c: Connection) -> dict[str, Any]:
            if load_state(c, self.store.campaign_id).handler_persona is not None:
                raise WorkflowError("The Handler is activated; creation cannot reset it.")
            row = self._draft_row(c, viewer.user_id, appointment)
            if type(expected) is not int or expected != (row["revision"] if row else 0):
                raise WorkflowError("STALE_HANDLER_DRAFT: reopen the current saved draft.")
            previous = self._draft(c, row) if row else None
            saved = SavedDraft(
                persona_id=previous.persona_id if previous else str(uuid4()),
                appointment=appointment,
                draft=draft,
                generation=rules.generation(load_state(c, self.store.campaign_id)),
            )
            self._actual(c, saved, complete=False)
            identity, source = row["id"] if row else str(uuid4()), str(uuid4())
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_draft_saved",
                event_id=source,
                work_id=identity,
                body_sha256=fingerprint(saved),
            )
            if row:
                self._save_work(c, row, source, saved.model_dump(mode="json"))
            else:
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, campaign_context=True),
                    identity,
                    viewer.user_id,
                    viewer.user_id,
                    KIND,
                    saved.model_dump(mode="json"),
                    source,
                )
            return dict(id=identity, revision=expected + 1, activated=False)

        try:
            draft = Draft.model_validate_json(draft.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.handler_draft_saved",
                dict(
                    expected=expected,
                    appointment=appointment,
                    generation=generation,
                    draft=draft.model_dump(mode="json"),
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid Handler details or source state; reopen creation."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _requests(self, c: Connection, persona: str) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.kind.in_((AGREEMENT, NPC_AGREEMENT)),
                        sa.func.json_extract(table.c.body_json, "$.agreement.persona_id")
                        == persona,
                    )
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def propose(
        self, viewer: GuildViewer, key: str, expected: int, *, generation: str | None = None
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._policy(c, viewer)
            self._appointment(c, viewer)
            current_generation = rules.generation(load_state(c, self.store.campaign_id))
            if generation != current_generation and not (
                generation is None and current_generation == "initial"
            ):
                raise WorkflowError(
                    "STALE_HANDLER_GENERATION: review the new persona before sending requests."
                )

        def operation(c: Connection) -> dict[str, Any]:
            row = self._draft_row(c, viewer.user_id, self._appointment(c, viewer))
            if row is None or row["revision"] != expected or row["state"] != "pending":
                raise WorkflowError("STALE_HANDLER_DRAFT: reopen the saved draft.")
            saved = self._draft(c, row)
            if saved.draft.missing:
                raise WorkflowError(
                    "Complete Handler creation before proposing its starting relationships."
                )
            self._actual(c, saved)
            offers: list[tuple[str, Offer]] = []
            for choice in saved.draft.starting:
                pc_offer = rules.agreement(saved, viewer.user_id, choice)
                identity = str(uuid5(NAMESPACE_URL, saved.persona_id + ":" + fingerprint(pc_offer)))
                offers.append((identity, pc_offer))
            for npc_choice in saved.draft.npc_starting:
                npc_offer = rules.npc_agreement(saved, viewer.user_id, npc_choice)
                identity = str(
                    uuid5(NAMESPACE_URL, saved.persona_id + ":" + fingerprint(npc_offer))
                )
                offers.append((identity, npc_offer))
            existing = {x["id"]: x for x in self._requests(c, saved.persona_id)}
            source = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_starting_proposed",
                proposals={i: fingerprint(a) for i, a in offers},
            )
            for identity, offer in offers:
                if identity not in existing:
                    related(
                        c,
                        self.store,
                        dict(campaign_id=self.store.campaign_id, campaign_context=True),
                        identity,
                        _recipient(offer),
                        viewer.user_id,
                        NPC_AGREEMENT if isinstance(offer, NpcAgreement) else AGREEMENT,
                        dict(
                            agreement=offer.model_dump(mode="json"),
                            proposed_event=source,
                            decision="pending",
                        ),
                        source,
                    )
            current_ids = {identity for identity, _ in offers}
            for identity, old in existing.items():
                if identity not in current_ids and old["state"] == "pending":
                    self._save_work(
                        c,
                        old,
                        source,
                        json.loads(old["body_json"])
                        | {
                            "decision": "superseded",
                        },
                        state="resolved",
                    )
            return dict(ids=[i for i, _ in offers])

        return self.store._write(
            viewer,
            key,
            "m3.handler_starting_proposed",
            dict(expected=expected, generation=generation),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def _agreement(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], Offer]:
        self.game.authorize(c, viewer, game=False)
        row = self._row(c, identity)
        body = json.loads(row["body_json"])
        try:
            offer: Offer = (
                NpcAgreement if row["kind"] == NPC_AGREEMENT else Agreement
            ).model_validate_json(json.dumps(body["agreement"]))
            if row["kind"] not in (AGREEMENT, NPC_AGREEMENT) or viewer.user_id not in (
                offer.handler,
                _recipient(offer),
            ):
                raise ValueError()
            event = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == body["proposed_event"],
                    )
                )
                .mappings()
                .first()
            )
            metadata = json.loads(event["payload_json"]) if event else {}
            if (
                event is None
                or event["kind"] != "m3.handler_starting_proposed"
                or event["actor_id"] != str(offer.handler)
                or metadata.get("proposals", {}).get(identity)
                != _source_hash(offer, body["agreement"])
                or row["owner_id"] != str(_recipient(offer))
                or row["subject_id"] != str(offer.handler)
                or not row["campaign_context"]
            ):
                raise ValueError()
            if body["decision"] in ("accepted", "declined"):
                response = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == row["event_id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                response_data = json.loads(response["payload_json"]) if response else {}
                if (
                    response is None
                    or response["kind"] != "m3.handler_starting_answered"
                    or response["actor_id"] != str(_recipient(offer))
                    or response_data.get("work_id") != identity
                    or response_data.get("proposal_sha256")
                    != _source_hash(offer, body["agreement"])
                    or response_data.get("accept") is not (body["decision"] == "accepted")
                    or row["state"] != "resolved"
                ):
                    raise ValueError()
        except (ValueError, KeyError):
            raise WorkflowError(
                "This shared Handler request belongs to its original participants."
            ) from None
        return row, offer

    def _current_offer(self, c: Connection, offer: Offer) -> bool:
        try:
            if self._appointment_source(c, offer.handler) != offer.appointment:
                return False
            row = self._draft_row(c, offer.handler, offer.appointment)
            if row is None or row["state"] != "pending":
                return False
            saved = self._draft(c, row)
            self._actual(c, saved)
            if isinstance(offer, NpcAgreement):
                return offer in tuple(
                    rules.npc_agreement(saved, offer.handler, x) for x in saved.draft.npc_starting
                )
            return offer in tuple(
                rules.agreement(saved, offer.handler, x) for x in saved.draft.starting
            )
        except (ValueError, WorkflowError):
            return False

    def get_agreement(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, offer = self._agreement(c, viewer, identity)
            current = self._current_offer(c, offer)
            return dict(
                id=identity,
                revision=row["revision"],
                proposal=offer.model_dump(mode="json"),
                decision=json.loads(row["body_json"])["decision"],
                stale=not current,
                can_answer=current
                and row["state"] == "pending"
                and viewer.user_id == _recipient(offer),
            )

    def answer(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, accept: bool
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.game.authorize(c, viewer, game=False)
            _, offer = self._agreement(c, viewer, identity)
            if viewer.user_id != _recipient(offer):
                raise WorkflowError(
                    "Only the actual original relationship participant owns this response."
                )

        def operation(c: Connection) -> dict[str, Any]:
            row, offer = self._agreement(c, viewer, identity)
            if (
                type(accept) is not bool
                or row["revision"] != revision
                or row["state"] != "pending"
                or not self._current_offer(c, offer)
            ):
                raise WorkflowError("STALE_HANDLER_AGREEMENT: reopen the exact original proposal.")
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_starting_answered",
                work_id=identity,
                accept=accept,
                proposal_sha256=_source_hash(offer, json.loads(row["body_json"])["agreement"]),
            )
            self._save_work(
                c,
                row,
                event,
                json.loads(row["body_json"]) | dict(decision="accepted" if accept else "declined"),
                state="resolved",
            )
            return dict(id=identity, accepted=accept)

        return self.store._write(
            viewer,
            key,
            "m3.handler_starting_answered",
            dict(id=identity, revision=revision, accept=accept),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def activate(
        self, viewer: GuildViewer, key: str, revision: int, game_revision: int, confirmed: bool
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._policy(c, viewer)
            self._appointment(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            appointment = self._appointment(c, viewer)
            row = self._draft_row(c, viewer.user_id, appointment)
            state = load_state(c, self.store.campaign_id)
            if (
                confirmed is not True
                or row is None
                or row["revision"] != revision
                or row["state"] != "pending"
                or state.revision != game_revision
            ):
                raise WorkflowError("STALE_HANDLER_CREATION: review the actual current activation.")
            if self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays before applying initial Handler effects.")
            locks = t.m2["m2_locks"]
            if c.scalar(
                sa.select(locks.c.channel_id)
                .where(locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released")
                .limit(1)
            ):
                raise WorkflowError("Restore chat permissions before Handler activation.")
            for name in ("m3_missions", "m3_off_duty"):
                table = t.m3[name]
                if c.scalar(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.phase.not_in(("complete", "cancelled")),
                    )
                    .limit(1)
                ):
                    raise WorkflowError(
                        "Finish the active mission or Off-Duty period before initial activation."
                    )
            saved = self._draft(c, row)
            self._actual(c, saved)
            accepted: list[Agreement] = []
            npc_accepted: list[NpcAgreement] = []
            for request in self._requests(c, saved.persona_id):
                body = json.loads(request["body_json"])
                if body["decision"] != "accepted":
                    continue
                try:
                    _, offer = self._agreement(c, viewer, request["id"])
                except WorkflowError:
                    raise WorkflowError(
                        "SOURCE_HANDLER_AGREEMENT_MISSING: recover the owned response."
                    ) from None
                if self._current_offer(c, offer):
                    if isinstance(offer, NpcAgreement):
                        npc_accepted.append(offer)
                    else:
                        accepted.append(offer)
            source = str(uuid4())
            updated = rules.activate(
                state,
                viewer.user_id,
                saved,
                profiles(c, self.store.campaign_id),
                tuple(accepted),
                source,
                npc_accepted=tuple(npc_accepted),
            )
            if not state.handler_archives:
                from girlframe.services.m3_battle_director import bind_legacy_context_bodies

                updated = bind_legacy_context_bodies(self.game, c, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_activated",
                updated,
                event_id=source,
                work_id=row["id"],
                body_sha256=fingerprint(saved),
            )
            self._save_work(c, row, source, saved.model_dump(mode="json"), state="resolved")
            for request in self._requests(c, saved.persona_id):
                if request["state"] == "pending":
                    self._save_work(
                        c,
                        request,
                        source,
                        json.loads(request["body_json"])
                        | {
                            "decision": "superseded",
                        },
                        state="resolved",
                    )
            return dict(id=saved.persona_id, activated=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_activated",
                dict(revision=revision, game_revision=game_revision, confirmed=confirmed),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValidationError:
            raise WorkflowError("Handler creation source needs review before activation.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        result = []
        try:
            appointment = self._appointment(c, viewer)
        except WorkflowError:
            appointment = None
        row = self._draft_row(c, viewer.user_id, appointment)
        if row is not None and (history or row["state"] != "resolved"):
            saved = self._draft(c, row)
            current = (
                appointment == saved.appointment
                and load_state(c, self.store.campaign_id).handler_persona is None
            )
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    kind=KIND,
                    state=row["state"],
                    actionable=current,
                    stale=not current,
                    label="Your Handler creation",
                )
            )
        table = t.m3["m3_required_work"]
        requests = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.kind.in_((AGREEMENT, NPC_AGREEMENT)),
                    sa.or_(
                        table.c.owner_id == str(viewer.user_id),
                        table.c.subject_id == str(viewer.user_id),
                    ),
                )
                .order_by(table.c.revision)
            ).mappings()
        }
        for request in requests.values():
            if not history and request["state"] == "resolved":
                continue
            _, offer = self._agreement(c, viewer, request["id"])
            current = self._current_offer(c, offer)
            result.append(
                dict(
                    id=request["id"],
                    revision=request["revision"],
                    kind=request["kind"],
                    state=json.loads(request["body_json"])["decision"],
                    actionable=current
                    and request["state"] == "pending"
                    and _recipient(offer) == viewer.user_id,
                    stale=not current,
                    label="NPC starting relationship"
                    if isinstance(offer, NpcAgreement)
                    else "Shared starting Bond and rank",
                )
            )
        return result

    def tasks(self, viewer: GuildViewer, *, history: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer, history=history)
