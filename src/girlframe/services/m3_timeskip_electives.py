"""Optional Timeskip invitations and the original Handler's follow-on scene."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_timeskip import Timeskip, TimeskipService, put_case
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "optional.ancillary.timeskip-introduction"


def _candidate(service: TimeskipService, c: Connection, viewer: GuildViewer) -> None:
    service._gate(c, viewer)
    access = Access(service.store)
    access.require_specialist_rule(RULE)
    AncillaryService(MissionService(service.store))._access(c, viewer)


def _finish_choice(case: Timeskip, owner: int, event: str) -> Timeskip:
    choices = case.electives | {str(owner): event}
    if len(choices) == len(case.voters):
        return case.model_copy(
            update=dict(electives=choices, step="opening", opening_eligible=event)
        )
    return case.model_copy(update=dict(electives=choices))


def bind_invite(
    game: GameService, c: Connection, state: GameState, offer: ancillary.Offer, viewer: GuildViewer
) -> None:
    assert offer.timeskip is not None
    service = TimeskipService(game)
    _candidate(service, c, viewer)
    case = service._case(c, state, viewer, offer.timeskip)
    owner = str(offer.controller)
    if (
        viewer.user_id != case.gm
        or case.step != "electives"
        or owner not in case.ancillary_requests
        or owner in case.electives
        or owner in case.ancillary_offers
        or offer.site != case.new_base
        or offer.faction is not None
    ):
        raise WorkflowError("Use the original request and this Timeskip’s actual Foundation base")
    case = case.model_copy(update=dict(ancillary_offers=case.ancillary_offers | {owner: offer.id}))
    put_case(state, case)


def settle_invite(
    game: GameService,
    c: Connection,
    state: GameState,
    offer: ancillary.Offer,
    viewer: GuildViewer,
    actor: ActorRef | None,
    event: str,
) -> None:
    assert offer.timeskip is not None
    service = TimeskipService(game)
    _candidate(service, c, viewer)
    case = service._case(c, state, viewer, offer.timeskip)
    owner = str(viewer.user_id)
    if (
        offer.controller != viewer.user_id
        or case.step != "electives"
        or case.ancillary_offers.get(owner) != offer.id
        or owner not in case.ancillary_requests
        or owner in case.electives
    ):
        raise WorkflowError("Recover the original owner’s actual pending Timeskip invitation")
    if actor is None:
        case = case.model_copy(
            update=dict(
                ancillary_requests={k: v for k, v in case.ancillary_requests.items() if k != owner},
                ancillary_offers={k: v for k, v in case.ancillary_offers.items() if k != owner},
            )
        )
    else:
        person = next((x for x in ancillary.records(state) if x.actor == actor), None)
        if person is None or person.event != event or person.controller != viewer.user_id:
            raise WorkflowError("The actual Ancillary Girl must already be created")
        case = _finish_choice(case, viewer.user_id, event)
        state.facts.append(
            dict(
                kind="timeskip_ancillary_introduced",
                id=case.id,
                event=event,
                actor=actor.model_dump_json(),
                reason=case.ancillary_requests[owner],
                owner=owner,
                offer=offer.id,
            )
        )
    put_case(state, case)


class TimeskipElectives:
    def __init__(self, timeskip: TimeskipService):
        self.timeskip, self.game, self.store = timeskip, timeskip.game, timeskip.store

    def menu(
        self, c: Connection, state: GameState, case: Timeskip, viewer: GuildViewer, step: str
    ) -> dict[str, Any]:
        if step == "introduce_self":
            assert case.opening_channel is not None
            scene = self.game.scene(c, case.opening_channel)
            ready = scene["id"] == case.opening_scene and viewer.user_id in scene["participants"]
            return dict(ready=ready, opening=case.opening_text if ready else None)
        if step == "choose_elective":
            try:
                _candidate(self.timeskip, c, viewer)
            except (ValueError, WorkflowError):
                return dict(ancillary=False)
            return dict(ancillary=True)
        return dict(
            nominees={
                user: reason
                for user, reason in case.ancillary_requests.items()
                if user not in case.ancillary_offers and user not in case.electives
            },
            site=case.new_base,
            contacts=(
                {x.id: x.name for x in state.world.npcs if x.alive and "patron" in x.jobs}
                if state.world is not None
                else {}
            ),
        )

    def choose(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, reason: str | None
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self.timeskip._case(c, state, viewer, identity)
            owner = str(viewer.user_id)
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            if (
                case.step != "electives"
                or state.revision != revision
                or owner in case.electives
                or owner in case.ancillary_requests
            ):
                raise WorkflowError("Reopen your actual original Timeskip elective choice")
            event = str(uuid4())
            if reason is not None:
                _candidate(self.timeskip, c, viewer)
                if not 0 < len(reason.strip()) <= 1200:
                    raise WorkflowError("Describe why this actual Ancillary Girl will matter")
                case = case.model_copy(
                    update=dict(
                        ancillary_requests=case.ancillary_requests | {owner: reason.strip()}
                    )
                )
                return self.timeskip._save(
                    c, state, viewer, key, case, "ancillary_requested", event
                )
            case = _finish_choice(case, viewer.user_id, event)
            return self.timeskip._save(c, state, viewer, key, case, "elective_passed", event)

        return self.timeskip._write(
            viewer, key, dict(id=identity, revision=revision, reason=reason), operation
        )

    def open_scene(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, channel: int, text: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self.timeskip._case(c, state, viewer, identity)
            handler = active_handler(state)
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            if (
                case.step != "opening"
                or state.revision != revision
                or viewer.user_id != case.gm
                or handler is None
                or handler.entity != str(viewer.user_id)
                or not 0 < len(text.strip()) <= 1200
            ):
                raise WorkflowError("Only the original Handler can set the actual follow-on scene")
            scene = self.game.scene(c, channel)
            if viewer.user_id not in scene["participants"]:
                raise WorkflowError("Join the actual new scene as the original Handler first")
            require_scene_clear(self.game, c, channel)
            events = t.events
            earliest = c.scalar(
                sa.select(events.c.seq).where(
                    events.c.campaign_id == self.store.campaign_id,
                    events.c.id == case.opening_eligible,
                )
            )
            contexts = t.m3["m3_scene_contexts"]
            actual_bind = c.scalar(
                sa.select(events.c.seq)
                .join(contexts, contexts.c.binding_event == events.c.id)
                .where(
                    contexts.c.campaign_id == self.store.campaign_id,
                    contexts.c.id == scene["id"],
                    contexts.c.channel_id == str(channel),
                    events.c.campaign_id == self.store.campaign_id,
                    events.c.kind == "m2.scene_bound",
                )
            )
            if earliest is None or actual_bind is None or actual_bind <= earliest:
                raise WorkflowError("Use a newly bound scene after the original elective choices")
            event = str(uuid4())
            case = case.model_copy(
                update=dict(
                    step="introductions",
                    opening_channel=channel,
                    opening_scene=scene["id"],
                    opening_text=text.strip(),
                )
            )
            return self.timeskip._save(c, state, viewer, key, case, "scene_opened", event)

        return self.timeskip._write(
            viewer,
            key,
            dict(id=identity, revision=revision, opening_channel=channel, text=text),
            operation,
        )

    def introduce(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, text: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            case = self.timeskip._case(c, state, viewer, identity)
            owner = str(viewer.user_id)
            self.game.unpaused(c)
            if (
                case.step != "introductions"
                or state.revision != revision
                or owner in case.introductions
                or case.opening_channel is None
                or not 0 < len(text.strip()) <= 1200
            ):
                raise WorkflowError("Open your original Timeskip reintroduction")
            require_scene_clear(self.game, c, case.opening_channel)
            scene = self.game.scene(c, case.opening_channel)
            if scene["id"] != case.opening_scene or viewer.user_id not in scene["participants"]:
                raise WorkflowError("Join the same actual Timeskip scene first")
            actor = (
                current_ref(state, viewer.user_id)
                if owner in state.sheets
                else active_handler(state)
                if viewer.user_id == case.gm
                else None
            )
            if actor is None:
                raise WorkflowError("Recover your original actual reintroduced character")
            event = str(uuid4())
            people = case.introductions | {owner: event}
            state.facts.append(
                dict(
                    kind="timeskip_reintroduction",
                    id=identity,
                    actor=actor.model_dump_json(),
                    event=event,
                    scene=scene["id"],
                    description=text.strip(),
                )
            )
            step = "complete" if len(people) == len(case.voters) else "introductions"
            case = case.model_copy(update=dict(step=step, introductions=people))
            return self.timeskip._save(c, state, viewer, key, case, "reintroduced", event)

        return self.timeskip._write(
            viewer, key, dict(id=identity, revision=revision, introduction=text), operation
        )
