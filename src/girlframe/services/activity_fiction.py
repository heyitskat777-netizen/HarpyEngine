"""Scoped continuity and repeat checks over delivered Activity contributions."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.activity_batch import FictionBeat, PriorContribution, ReceivedOffer
from girlframe.ai.handler_initiative import initiative_for
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_character import PlaybookProfile
from girlframe.services.director_context import DirectorContextService
from girlframe.services.onboarding import WorkflowError


class ActivityFiction:
    def __init__(self, context: DirectorContextService):
        self.context = context

    def _delivered(
        self, c: Connection, scene: str, actor: ActorRef, *, received: bool = False
    ) -> list[dict[str, Any]]:
        active = {
            ref.id
            for ref in self.context._current(c, scene)
            if (ref.reported_by == actor) is not received
            and ref.source_id.startswith(("handler-delivery:", "npc-delivery:"))
            and actor.token in ref.known_by
        }
        if not active:
            return []
        table = t.director_context["shadow"]
        return [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json)
                .where(
                    table.c.campaign_id == self.context.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type").in_(
                        ("handler_delivery", "npc_delivery")
                    ),
                    sa.func.json_extract(table.c.body_json, "$.reference").in_(active),
                )
                .order_by(sa.func.json_extract(table.c.body_json, "$.ordinal"))
            )
        ]

    def recent(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        listener: ActorRef,
        *,
        include_carried: bool = False,
    ) -> tuple[PriorContribution, ...]:
        rows = self._delivered(c, scene, actor)
        closed = {row.get("fiction", {}).get("follows_offer") for row in rows}
        visible = [row for row in rows if listener.model_dump(mode="json") in row["recipients"]]
        carried = (
            tuple(
                PriorContribution(
                    reference=ref.id,
                    text=ref.text.removeprefix("Reported claim: "),
                    own_action=None,
                    open_offer=False,
                    carried=True,
                )
                for ref in self.context._current(c, scene)
                if ref.origin_scene
                and ref.source_id.startswith("npc-delivery:")
                and ref.reported_by == actor
                and {actor.token, listener.token} <= set(ref.known_by)
            )[-3:]
            if include_carried
            else ()
        )
        return (
            *carried,
            *(
                PriorContribution(
                    reference=row["reference"],
                    text=row.get("dialogue", row["text"]),
                    own_action=row.get("action") or row.get("fiction", {}).get("own_action"),
                    open_offer=bool(
                        row.get("fiction", {}).get("offers_help") and row["reference"] not in closed
                    ),
                )
                for row in visible[-6:]
            ),
        )[-6:]

    def received_offers(
        self, c: Connection, scene: str, actor: ActorRef
    ) -> tuple[ReceivedOffer, ...]:
        answered = {
            row.get("fiction", {}).get("answers_offer") for row in self._delivered(c, scene, actor)
        }
        incoming = self._delivered(c, scene, actor, received=True)
        answered.update(row.get("fiction", {}).get("follows_offer") for row in incoming)
        return tuple(
            ReceivedOffer(
                reference=row["reference"],
                speaker=ActorRef.model_validate(row["actor"]),
                text=row.get("dialogue", row["text"]),
            )
            for row in incoming
            if row.get("fiction", {}).get("offers_help") and row["reference"] not in answered
        )[-3:]

    def delivered_initiatives(
        self, c: Connection, scene: str, actor: ActorRef
    ) -> dict[ActorRef, set[str]]:
        """Remember the issue only for listeners who actually heard a contribution."""
        delivered: dict[ActorRef, set[str]] = {}
        for row in self._delivered(c, scene, actor):
            if issue := self._initiative_issue(c, scene, row):
                for raw in row["recipients"]:
                    listener = ActorRef.model_validate(raw)
                    delivered.setdefault(listener, set()).add(issue)
        return delivered

    def _initiative_issue(self, c: Connection, scene: str, row: dict[str, Any]) -> str | None:
        if isinstance(issue := row.get("initiative_issue"), str) and issue:
            return issue
        if not row.get("character_cue"):
            return None
        # The first cue implementation saved the verified report in the draft.
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.context.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == row["id"].removeprefix("handler-delivery:"),
            )
        )
        if raw is None:
            return None
        draft = json.loads(raw)
        initial = draft.get("initiative")
        profile = draft.get("request", {}).get("playbook_profile")
        if initial is None or profile is None:
            return None
        report = next(
            (
                item
                for item in draft.get("batch_reports", ())
                if item["source_id"] == initial["report_id"]
            ),
            None,
        )
        if report is None:
            return None
        candidate = initiative_for(
            PlaybookProfile.model_validate_json(json.dumps(profile)),
            report["source_id"],
            report["text"],
        )
        return candidate.issue if candidate and candidate.cue == initial["cue"] else None

    def check(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        source: ActorRef,
        beat: FictionBeat,
        *,
        recipients: tuple[ActorRef, ...] = (),
        text: str = "",
        citations: tuple[str, ...] = (),
    ) -> None:
        chosen = {role.token for role in recipients}
        if beat.answers_offer:
            origin_offer = next(
                (
                    offer
                    for offer in self.received_offers(c, scene, actor)
                    if offer.reference == beat.answers_offer
                ),
                None,
            )
            if origin_offer is None or (recipients and recipients != (origin_offer.speaker,)):
                raise WorkflowError(
                    "FICTION_OFFER_UNAVAILABLE: answer one heard offer to its original speaker."
                )
            return
        rows = self._delivered(c, scene, actor)
        if beat.follows_offer:
            origin = next((row for row in rows if row["reference"] == beat.follows_offer), None)
            if (
                origin is None
                or not origin.get("fiction", {}).get("offers_help")
                or source.model_dump(mode="json") not in origin["recipients"]
                or not chosen <= origin["controllers"].keys()
                or any(
                    row.get("fiction", {}).get("follows_offer") == beat.follows_offer
                    for row in rows
                )
            ):
                raise WorkflowError(
                    "FICTION_OFFER_UNAVAILABLE: follow up only with the original listeners."
                )
        if not chosen or beat.follows_offer:
            return
        normalized = " ".join(text.casefold().split())
        for prior in rows[-3:]:
            if (
                chosen <= prior["controllers"].keys()
                and " ".join(prior.get("dialogue", prior["text"]).casefold().split()) == normalized
                and (prior.get("action") or prior.get("fiction", {}).get("own_action"))
                == beat.own_action
                and sorted(prior.get("citations", prior.get("dependencies", ())))
                == sorted(citations)
            ):
                raise WorkflowError(
                    "FICTION_ALREADY_SAID: these listeners already heard the same contribution."
                )
