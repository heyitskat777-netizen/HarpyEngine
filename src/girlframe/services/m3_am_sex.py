"""AM's printed no-extra-roll path reads genuine counterpart sources privately."""

import json
from typing import Any

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_dose_up import _roll_source
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "girl.am.sex-play"
# These are existing actual source adapters, not substitute Plays or copied effects.
PARTNER_PLAYS = (
    "alpha_sex",
    "princess_sex",
    "mockingbird_sex",
    "stim_sex",
    "oldgen_sex",
    "casualty_sex",
    "vatgrown_sex",
    "newgirl_sex",
)


class SexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(
        self, viewer: GuildViewer, channel: int, *, bonded_source: str | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            access = Access(self.store)
            access.authorize(c, viewer, "plays", director_response=True)
            assert access.registry is not None
            access.registry.require_available(RULE)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None:
                raise WorkflowError("Use the actual original living Girl")
            borrowed_target: ActorRef | None = None
            if bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_bonded import admit_delegation

                route = bonded.get(state, bonded_source)
                if route.target is None:
                    raise WorkflowError("Use the actual original counterpart")
                channel = route.cast.channel
                borrowed_target = route.target
                admit_delegation(
                    self.game,
                    c,
                    state,
                    current_ref(state, viewer.user_id),
                    route.target,
                    RULE,
                    bonded_source,
                )
            elif not has_rule(sheet, RULE, "AM"):
                raise WorkflowError("This no-extra-roll source belongs to the actual original AM")
            actor = current_ref(state, viewer.user_id)
            scene = self.game.scene(c, channel)
            if viewer.user_id not in scene["participants"]:
                raise WorkflowError("Join the actual source scene first")
            table = t.m2["m2_actions"]
            sources = []
            owned_choices = self.game.choices(viewer)
            for saved in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                    table.c.scene_id == scene["id"],
                )
            ).mappings():
                data = json.loads(saved["body_json"])
                play = data.get("play")
                if play not in PARTNER_PLAYS:
                    continue
                meta = data.get(play)
                if play == "mockingbird_sex":
                    meta = data.get("mockingbird")
                    targets = [x["actor"] for x in (meta or {}).get("parties", ())[:1]]
                elif play == "newgirl_sex":
                    targets = (meta or {}).get("partners", ())
                else:
                    targets = [(meta or {}).get("target")]
                if not isinstance(meta, dict) or not any(
                    x is not None and ActorRef.model_validate(x) == actor for x in targets
                ):
                    continue
                if bonded_source is not None and (
                    borrowed_target is None
                    or meta.get("actor") != borrowed_target.model_dump(mode="json")
                ):
                    continue
                if meta.get("actor") == actor.model_dump(mode="json"):
                    continue
                # Existing rule service rechecks genuine consent, incarnation and audience.
                actual = self.game.action(c, saved["id"])
                self.game.inspect(viewer, actual["id"])
                receipt = None
                if data.get("receipt"):
                    _roll_source(self.game, c, actual)
                    receipt = data["receipt"]["id"]
                sources.append(
                    dict(
                        id=actual["id"],
                        play=play,
                        state=actual["state"],
                        receipt=receipt,
                        choices=[x["id"] for x in owned_choices if x["action_id"] == actual["id"]],
                    )
                )
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                sources=sources,
                channel=channel,
                no_additional_roll=True,
                bonded_source=bonded_source,
            )

    def bind_source(
        self, viewer: GuildViewer, key: str, source_id: str, action_id: str
    ) -> dict[str, Any]:
        """Bind the genuine counterpart Action, without another performance or roll."""

        def operation(c: sa.Connection) -> dict[str, Any]:
            from uuid import uuid4

            from girlframe.engine import m3_bonded as bonded
            from girlframe.services.m3_bonded import admit_delegation, prove

            self.game.unpaused(c)
            access = Access(self.store)
            access.authorize(c, viewer, "plays", director_response=True)
            assert access.registry is not None
            access.registry.require_available(RULE)

            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, source_id)
            if value.target is None or value.actor != current_ref(state, viewer.user_id):
                raise WorkflowError(
                    "Only the actual original Bonded owns this no-extra-roll source"
                )
            admit_delegation(self.game, c, state, value.actor, value.target, RULE, source_id)
            action = self.game.action(c, action_id)
            if (
                action["scene_id"] != value.cast.id
                or action["data"]["play"] not in PARTNER_PLAYS
                or str(action["actor_id"]) != value.target.entity
                or action["data"].get("character_ids", {}).get(value.target.entity)
                != value.target.incarnation
            ):
                raise WorkflowError("Use the actual original counterpart's real Sex source")
            # Reuse the ordinary source's own private inspection/proof and real roles.
            self.game.inspect(viewer, action_id)
            meta = action["data"].get(action["data"]["play"])
            if action["data"]["play"] == "mockingbird_sex":
                meta = action["data"].get("mockingbird")
                targets = [x["actor"] for x in (meta or {}).get("parties", ())[:1]]
            elif action["data"]["play"] == "newgirl_sex":
                targets = (meta or {}).get("partners", ())
            else:
                targets = [(meta or {}).get("target")]
            if not any(
                x is not None and ActorRef.model_validate(x) == value.actor for x in targets
            ):
                raise WorkflowError(
                    "The real source must involve this original Bonded, not their account"
                )
            existing = next(
                (x for x in bonded.records(state, bonded.Delegation) if x.source == source_id), None
            )
            if existing:
                if existing.session != action_id:
                    raise WorkflowError("Preserve the original no-extra-roll counterpart source")
                return dict(id=source_id, action=action_id)
            event = str(uuid4())
            bonded.put(
                state,
                bonded.Delegation(
                    id=source_id + ":delegation",
                    source=source_id,
                    session=action_id,
                    rule=RULE,
                    actor=value.actor,
                    target=value.target,
                    event=event,
                ),
            )
            bonded.put(state, value.model_copy(update=dict(phase="bound")))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_am_source",
                state,
                event_id=event,
                source=source_id,
                action_id=action_id,
            )
            if action["state"] == "complete":
                from girlframe.services.m3_bonded import synchronize_delegation

                synchronize_delegation(self.game, c, action, event)
            return dict(id=source_id, action=action_id)

        return self.store._write(
            viewer,
            key,
            "m3.bonded_am_source",
            dict(source=source_id, action=action_id),
            operation,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
        )
