"""Append-only factual past link proof; no historical rewriting or current control grant."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_compliance_virus as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_compliance_virus_state import InfectedPerson, PastLinkExposure, Strain
from girlframe.engine.m3_items import body_ref
from girlframe.engine.m3_role_punishments import view
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_compliance_virus import (
    VirusService,
    _audit,
    _cast,
    _history,
    prove_strain,
)
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _chronology(c: Connection, game: Any, value: PastLinkExposure) -> None:
    prior = _history(c, game, value.prior_event)
    # The earlier immutable record itself must already contain the active strain.
    strain = rules.record(prior, Strain, value.strain)
    actor = view(prior, value.context_actor, profiles(c, game.store.campaign_id))
    owner = view(prior, value.frame.owner, profiles(c, game.store.campaign_id))
    if (
        strain.purged_event
        or strain.target != value.frame
        or actor.rules != "handler_girl"
        or actor.controller != value.controller
        or body_ref(prior, value.context_actor) != value.actor
        or owner.controller != value.frame_controller
        or owner.frame_instance != value.frame.instance
    ):
        raise WorkflowError("Missing or contradictory original body/Frame/infection chronology.")
    cast = SceneCast.model_validate_json(value.cast_json)
    if not any(
        x.actor == value.context_actor and x.controller == value.controller for x in cast.roles
    ) or not any(
        x.actor == value.frame.owner and x.controller == value.frame_controller for x in cast.roles
    ):
        raise WorkflowError(
            "Both original people must belong to this actual earlier source episode."
        )
    earlier = next((x for x in prior.scene_casts if x.id == cast.id), None)
    if earlier != cast:
        raise WorkflowError("The exposure must name the real unchanged earlier source cast.")
    history = t.m2["m2_state_history"]
    source_revision = c.scalar(
        sa.select(history.c.revision).where(
            history.c.campaign_id == game.store.campaign_id, history.c.event_id == value.prior_event
        )
    )
    proposed_revision = c.scalar(
        sa.select(history.c.revision).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == value.proposed_event,
        )
    )
    if proposed_revision is not None and (
        source_revision is None or source_revision >= proposed_revision
    ):
        raise WorkflowError(
            "Past exposure cannot precede the actual infection or follow its new proposal."
        )


def prove_exposure(c: Connection, game: Any, value: PastLinkExposure) -> None:
    first = rules.record(_history(c, game, value.proposed_event), PastLinkExposure, value.id)
    stable = (
        "id",
        "actor",
        "context_actor",
        "controller",
        "strain",
        "frame",
        "frame_controller",
        "judge",
        "judge_controller",
        "appointment",
        "prior_event",
        "proposed_event",
        "channel",
        "cast_json",
        "episode",
    )
    if any(getattr(first, k) != getattr(value, k) for k in stable):
        raise WorkflowError("Recover exact original factual exposure, without a new-body alias.")
    _audit(c, game, value.proposed_event, value.controller, "m3.virus_past_link_proposed")
    _chronology(c, game, value)
    if value.frame_confirmed_event:
        _audit(
            c,
            game,
            value.frame_confirmed_event,
            value.frame_controller,
            "m3.virus_past_link_confirmed",
        )
        confirmed = rules.record(
            _history(c, game, value.frame_confirmed_event), PastLinkExposure, value.id
        )
        if (
            confirmed.frame_confirmed_event != value.frame_confirmed_event
            or confirmed.phase != "judge_review"
        ):
            raise WorkflowError("Actual Frame owner must confirm the original past exposure.")
    if value.reviewed_event:
        _audit(c, game, value.reviewed_event, value.judge_controller, "m3.virus_past_link_reviewed")
        reviewed = rules.record(_history(c, game, value.reviewed_event), PastLinkExposure, value.id)
        if reviewed != value:
            raise WorkflowError("Recover actual original frozen judge's factual decision.")


class ExposureService:
    def __init__(self, game: Any):
        self.game, self.store = game, game.store

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        strain: str,
        prior_event: str,
        episode: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _scene_judge

            self.game.unpaused(c)
            if self.game.pending_actions(c):
                raise WorkflowError("SCENE_BUSY: factual exposure cannot jump an owned Play.")
            state = load_state(c, self.store.campaign_id)
            actual = view(state, actor, profiles(c, self.store.campaign_id))
            original = prove_strain(c, self.game, state, strain)
            cast = _cast(self.game, c, state, channel)
            if (
                actor.kind != "handler"
                or actual.rules != "handler_girl"
                or actual.controller != viewer.user_id
                or not episode.strip()
            ):
                raise WorkflowError("Actual original HandlerGirl proposes only her real past link.")
            owner = view(state, original.target.owner, profiles(c, self.store.campaign_id))
            judge, human, _ = _scene_judge(self.game, c, state, cast)
            _, appointment = MedicalService(self.store)._handler(c)
            event = str(uuid4())
            value = PastLinkExposure(
                id=str(uuid4()),
                actor=body_ref(state, actor),
                context_actor=actor,
                controller=viewer.user_id,
                strain=strain,
                frame=original.target,
                frame_controller=owner.controller,
                judge=judge,
                judge_controller=human,
                appointment=appointment,
                prior_event=prior_event,
                proposed_event=event,
                channel=channel,
                cast_json=cast.model_dump_json(),
                episode=episode,
            )
            _chronology(c, self.game, value)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.virus_past_link_proposed",
                state,
                event_id=event,
                exposure=value.id,
            )
            return dict(id=value.id)

        return VirusService(self.game)._write(
            viewer,
            key,
            "m3.virus_past_link_proposed",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                strain=strain,
                prior_event=prior_event,
                episode=episode,
            ),
            operation,
        )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        confirmed: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = rules.record(state, PastLinkExposure, identity)
            prove_exposure(c, self.game, value)
            if (
                value.revision != revision
                or type(confirmed) is not bool
                or not account.strip()
                or value.phase not in ("frame_confirmation", "judge_review")
            ):
                raise WorkflowError("Use the exact current owned factual source review.")
            owner = (
                value.frame_controller
                if value.phase == "frame_confirmation"
                else value.judge_controller
            )
            if (
                viewer.user_id != owner
                or MedicalService(self.store)._handler(c)[1] != value.appointment
            ):
                raise WorkflowError(
                    "Only the frozen actual Frame owner or original judge owns this review."
                )
            current_actor = view(state, value.actor, profiles(c, self.store.campaign_id))
            current_owner = view(state, value.frame.owner, profiles(c, self.store.campaign_id))
            if (
                current_actor.controller != value.controller
                or current_owner.controller != value.frame_controller
            ):
                raise WorkflowError("No successor may adopt this original factual source.")
            event = str(uuid4())
            fields: dict[str, Any] = dict(revision=value.revision + 1)
            if value.phase == "frame_confirmation":
                fields.update(
                    frame_confirmed_event=event if confirmed else None,
                    phase="judge_review" if confirmed else "rejected",
                )
                kind = "m3.virus_past_link_confirmed"
            else:
                fields.update(reviewed_event=event, phase="approved" if confirmed else "rejected")
                kind = "m3.virus_past_link_reviewed"
            updated = value.model_copy(update=fields)
            rules.put(state, updated)
            if updated.phase == "approved":
                if not any(
                    x.strain == value.strain and x.actor == value.actor and x.purged_event is None
                    for x in rules.records(state, InfectedPerson)
                ):
                    rules.put(
                        state,
                        InfectedPerson(
                            id=rules.identity("past-person", value.id),
                            strain=value.strain,
                            actor=value.actor,
                            controller=value.controller,
                            source_event=event,
                            link_source=event,
                        ),
                    )
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                exposure=identity,
                confirmed=confirmed,
                account=account,
            )
            return dict(id=identity, phase=updated.phase)

        return VirusService(self.game)._write(
            viewer,
            key,
            "m3.virus_past_link_review",
            dict(id=identity, revision=revision, confirmed=confirmed, account=account),
            operation,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = rules.record(state, PastLinkExposure, identity)
            prove_exposure(c, self.game, value)
            if viewer.user_id not in (
                value.controller,
                value.frame_controller,
                value.judge_controller,
            ):
                raise WorkflowError(
                    "This actual original exposure is private to its source people."
                )
            return dict(
                id=value.id,
                revision=value.revision,
                phase=value.phase,
                episode=value.episode,
                can_act=(
                    value.phase in ("frame_confirmation", "judge_review")
                    and viewer.user_id
                    == (
                        value.frame_controller
                        if value.phase == "frame_confirmation"
                        else value.judge_controller
                    )
                    and VirusService(self.game)._can_act(c, viewer)
                ),
            )

    def preview(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            VirusService(self.game)._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actual = view(state, actor, profiles(c, self.store.campaign_id))
            cast = _cast(self.game, c, state, channel)
            if (
                actor.kind != "handler"
                or actual.rules != "handler_girl"
                or actual.controller != viewer.user_id
            ):
                raise WorkflowError(
                    "Only the actual HandlerGirl records her original past exposure."
                )
            frames = [
                x
                for x in rules.records(state, Strain)
                if any(role.actor == x.target.owner for role in cast.roles)
            ]
            history = t.m2["m2_state_history"]
            rows = c.execute(
                sa.select(history.c.event_id, history.c.body_json)
                .where(history.c.campaign_id == self.store.campaign_id)
                .order_by(history.c.revision.desc())
                .limit(50)
            ).all()
            events = []
            for row in rows:
                prior = GameState.model_validate_json(row.body_json)
                try:
                    eligible = (
                        view(prior, actor, profiles(c, self.store.campaign_id)).rules
                        == "handler_girl"
                    )
                except ValueError:
                    continue
                if (
                    eligible
                    and next((x for x in prior.scene_casts if x.id == cast.id), None) == cast
                ):
                    events.append(
                        dict(
                            id=row.event_id,
                            label="Actual original episode source " + row.event_id[:8],
                        )
                    )
            return dict(
                frames=[dict(id=x.id, label="Actual Frame " + x.target.instance) for x in frames],
                episodes=events,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state, PastLinkExposure):
            owner = (
                value.frame_controller
                if value.phase == "frame_confirmation"
                else value.judge_controller
            )
            if value.phase not in ("frame_confirmation", "judge_review") or viewer.user_id not in (
                value.controller,
                value.frame_controller,
                value.judge_controller,
            ):
                continue
            prove_exposure(c, self.game, value)
            result.append(
                dict(
                    id=value.id,
                    kind="compliance_virus_exposure",
                    state=value.phase,
                    can_act=viewer.user_id == owner and VirusService(self.game)._can_act(c, viewer),
                    label="Confirm original past link fact"
                    if value.phase == "frame_confirmation"
                    else "Review actual past infection chronology",
                )
            )
        return result
