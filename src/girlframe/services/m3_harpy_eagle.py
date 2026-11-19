"""Mark an actual Tag, remove its exposed cockpit, and preserve the two bodies."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_eagle as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_doctor import require_harm_allowed
from girlframe.engine.m3_harpy_advancements import EAGLE
from girlframe.engine.m3_janus_pandora import require_can_harm
from girlframe.engine.m3_physical import extract
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import scene_harpy
from girlframe.services.m3_wyvern_combat import require_damage_allowed, require_free
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer


class EagleService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(EAGLE)

    def _exposure(
        self,
        c: Connection,
        state: GameState,
        source: ActorRef,
        girl: ActorView,
    ) -> str | None:
        entries = [
            x
            for x in state.facts
            if x.get("kind") == "battle_frame_exposure"
            and x.get("target") == girl.ref.model_dump_json()
            and x.get("frame") == girl.frame_instance
        ]
        if not entries or entries[-1].get("opponent") != source.model_dump_json():
            return None
        record = entries[-1]
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == record["event"],
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "m3.battle_frame_exposed",
            )
        )
        if raw is None or record not in GameState.model_validate_json(raw).facts:
            return None
        return record["event"]

    def _targets(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        source: ActorView,
    ) -> dict[str, tuple[ActorView, TagState, str]]:
        bound = profiles(c, self.store.campaign_id)
        results: dict[str, tuple[ActorView, TagState, str]] = {}
        for role in cast.roles:
            if role.actor.kind != "pilot":
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                not girl.alive
                or girl.controller != role.controller
                or girl.cell != source.cell
                or girl.offstage_source
                or girl.custody not in (None, "free")
                or girl.inside_frame is not True
                or girl.frame_instance is None
                or girl.occupied_frame_instance != girl.frame_instance
                or rules.missing(state, girl.ref, girl.frame_instance)
                or self.game.immediate_work(c, girl.controller)
            ):
                continue
            event = self._exposure(c, state, source.ref, girl)
            if event is None:
                continue
            for tag in state.sheets[girl.ref.entity].tags:
                if tag.giver_actor == source.ref and not tag.marked and not tag.rejection_pending:
                    results[f"{girl.ref.token}/{tag.id}"] = (girl, tag, event)
        return results

    def get(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            source, _ = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, EAGLE)
            holding = rules.holding(state, source.ref)
            return dict(
                revision=state.revision,
                holding=bool(holding),
                targets={
                    key: f"{girl.label} · {tag.label}"
                    for key, (girl, tag, _) in self._targets(c, state, cast, source).items()
                }
                if holding is None
                else {},
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Finish the actual held Play before this Harpy action")
            state = load_state(c, self.store.campaign_id)
            if revision != state.revision or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError("Refresh the original Harpy and describe the actual effect")
            cast = _cast(self.game, c, state, channel)
            source, advancement = scene_harpy(
                self.game, c, state, viewer.user_id, cast, actor, EAGLE
            )
            require_free(self.game, c, state, actor)
            event = str(uuid4())
            holding = rules.holding(state, actor)
            released = target == "release"
            if released:
                if (
                    holding is None
                    or holding.controller != source.controller
                    or holding.advancement != advancement
                ):
                    raise WorkflowError("Recover the actual original cockpit held by this Harpy")
                self._release(state, source, holding, event, account.strip())
                current = holding.model_copy(update=dict(released=event))
            else:
                if holding is not None:
                    raise WorkflowError("The original Harpy can hold only one Girl this way")
                chosen = self._targets(c, state, cast, source).get(target)
                if chosen is None:
                    raise WorkflowError(
                        "Choose an actual exposed original Frame and known unmarked Tag"
                    )
                girl, tag, exposure = chosen
                require_can_harm(state, source.ref, girl.ref)
                require_damage_allowed(self.game, c, state, girl.ref)
                require_harm_allowed(state, girl.ref, source.ref)
                ChoiceEngine(self.game).prove_tag_setter(c, state, girl.controller, tag)
                assert girl.frame_instance is not None
                state = extract(
                    state, profiles(c, self.store.campaign_id), girl.ref, event, account.strip()
                )
                sheet = state.sheets[girl.ref.entity]
                next(x for x in sheet.tags if x.id == tag.id).marked = True
                sheet.revision += 1
                placement = next(x for x in state.placements if x.actor == girl.ref)
                captured = placement.model_copy(update=dict(custody=source.ref, girl_cell=None))
                state.placements = [
                    captured if x.actor == girl.ref else x for x in state.placements
                ]
                current = rules.Cockpit(
                    event=event,
                    scene=cast.id,
                    harpy=source.ref,
                    controller=source.controller,
                    girl=girl.ref,
                    frame=girl.frame_instance,
                    exposure=exposure,
                    tag=tag.id,
                    advancement=advancement,
                )
            rules.put(state, current)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_eagle_released" if released else "m3.harpy_eagle_held",
                state,
                event_id=event,
                scene=cast.id,
                capture=current.event,
            )
            return dict(event=event, held=not released)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_eagle",
                dict(
                    actor=actor.model_dump(mode="json"),
                    channel=channel,
                    revision=revision,
                    target=target,
                    account=account,
                ),
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    @staticmethod
    def _release(
        state: GameState, source: ActorView, case: rules.Cockpit, event: str, account: str
    ) -> None:
        placement = next((x for x in state.placements if x.actor == case.girl), None)
        if (
            placement is None
            or placement.custody != case.harpy
            or placement.frame_instance != case.frame
            or source.cell is None
        ):
            raise WorkflowError("Recover the original held Girl and actual release location")
        replacement = placement.model_copy(
            update=dict(
                custody=None,
                girl_cell=source.cell,
                source_event=event,
                account=account,
            )
        )
        state.placements = [replacement if x.actor == case.girl else x for x in state.placements]
