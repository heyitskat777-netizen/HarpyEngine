"""Native Only She Matters activation through current physical and role authority."""

from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import ONLY_SHE_MATTERS
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_harpy_only_she import Killing, kill
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _visible, synchronize_casts
from girlframe.services.m3_harpy_advancements import advancement_source
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class OnlySheMattersService:
    def __init__(self, game: GameService):
        self.game, self.store, self.access = game, game.store, Access(game.store)

    def source(
        self, c: Connection, state: GameState, viewer: GuildViewer, cast: SceneCast, actor: ActorRef
    ) -> tuple[ActorView, str]:
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if (
            actor.kind != "external_pilot"
            or actual.girl != "harpy"
            or actual.controller != viewer.user_id
            or actual.cell is None
            or actual.offstage_source is not None
            or not any(
                role.actor == actor and role.controller == viewer.user_id for role in cast.roles
            )
            or is_helpless(state, actor)
        ):
            raise WorkflowError("Use your actual living Harpy in the original scene")
        receipt = advancement_source(self.game, c, state, actor, viewer.user_id, ONLY_SHE_MATTERS)
        if receipt is None or harpy(state, actor).body_incapacitated:
            raise WorkflowError("Use an active Harpy with its own Only She Matters advancement")
        return actual, receipt

    def _targets(
        self, c: Connection, state: GameState, cast: SceneCast, actual: ActorView
    ) -> dict[ActorRef, str]:
        if state.world is None:
            return {}
        physical = {
            x.id
            for x in state.world.npcs
            if x.alive and x.source_kind is None and "director" not in x.jobs
        }
        bound = profiles(c, self.store.campaign_id)
        return {
            npc.ref: npc.label
            for role in cast.roles
            if role.actor.kind == "npc"
            and role.actor.entity in physical
            and _visible(state, role.actor, actual.controller)
            and (npc := resolve(state, role.actor, bound, require_current_profile=False)).cell
            == actual.cell
            and npc.offstage_source is None
        }

    def get(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.access.authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            actual, _receipt = self.source(c, state, viewer, cast, actor)
            return dict(revision=state.revision, targets=self._targets(c, state, cast, actual))

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        actor: ActorRef,
        target: ActorRef,
        heat: Literal[1, 2],
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not account or len(account) > 1200 or type(heat) is not int or heat not in (1, 2):
            raise WorkflowError("Describe the actual outcome and choose one or two Heat")

        def authorize(c: Connection) -> None:
            self.access.authorize(c, viewer, "plays", director_response=True)
            self.access.require_specialist_rule(ONLY_SHE_MATTERS)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.engine.m3_doctor import require_harm_allowed
            from girlframe.services.m3_wyvern_combat import require_damage_allowed, require_free
            from girlframe.services.p1_facilitator import require_scene_clear

            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_HARPY: reopen the actual source scene")
            cast = _cast(self.game, c, state, channel)
            actual, receipt = self.source(c, state, viewer, cast, actor)
            if target not in self._targets(c, state, cast, actual):
                raise WorkflowError("Choose the original known ordinary NPC in this actual square")
            lock = self.game.lock(c, channel)
            if lock is not None and lock["state"] != "released":
                raise WorkflowError("Finish the actual open Play before the Harpy acts")
            require_scene_clear(self.game, c, channel)
            require_free(self.game, c, state, actor)
            require_damage_allowed(self.game, c, state, target)
            require_harm_allowed(state, target, actor)
            event = str(uuid4())
            result = Killing(
                harpy=actor,
                target=target,
                controller=viewer.user_id,
                advancement=receipt,
                scene=cast.id,
                event=event,
                heat=heat,
            )
            changed = kill(state, result, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_only_she_matters",
                changed,
                event_id=event,
                scene=cast.id,
                result=result.model_dump(mode="json"),
                account=account,
            )
            synchronize_casts(self.game, c, event)
            return dict(event=event, heat=heat)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_only_she_matters",
                dict(
                    channel=channel,
                    revision=revision,
                    actor=actor.model_dump(mode="json"),
                    target=target.model_dump(mode="json"),
                    heat=heat,
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
