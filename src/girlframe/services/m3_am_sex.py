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

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            access = Access(self.store)
            access.authorize(c, viewer, "plays", director_response=True)
            assert access.registry is not None
            access.registry.require_available(RULE)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or not has_rule(sheet, RULE, "AM"):
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
            )
