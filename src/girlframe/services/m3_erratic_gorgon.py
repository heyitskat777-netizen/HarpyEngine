"""An original Erratic Gorgon can put a real Tag on a living NPC."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Gorgon, Npc, WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "gorgon.gorgon.class-iii-erratic"
TAG_EVENT = "m3.erratic_npc_tag_inflicted"


class ErraticService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        GorgonPlayService(self.game).authorize(c, viewer)
        registry = Access(self.store).registry
        assert registry is not None
        try:
            registry.require_available(RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _options(
        self, c: Connection, viewer: GuildViewer, channel: int
    ) -> tuple[GameState, SceneCast, dict[str, Gorgon], dict[str, Npc]]:
        state = load_state(c, self.store.campaign_id)
        cast = _cast(self.game, c, state, channel)
        if state.world is None:
            raise WorkflowError("Initialize the actual world before the Gorgon acts")
        bound = profiles(c, self.store.campaign_id)
        by_id = {x.id: x for x in state.world.gorgons if x.alive and x.gorgon_class == "erratic"}
        gorgons = {}
        for role in cast.roles:
            if (
                role.actor.kind != "gorgon"
                or role.controller != viewer.user_id
                or role.actor.entity not in by_id
            ):
                continue
            actual = resolve(state, role.actor, bound)
            if (
                actual.controller == viewer.user_id
                and actual.cell is not None
                and actual.offstage_source is None
            ):
                gorgons[role.actor.entity] = by_id[role.actor.entity]
        targets = (
            {
                x.id: x
                for x in state.world.npcs
                if x.alive and _visible(state, ActorRef(kind="npc", entity=x.id), viewer.user_id)
            }
            if gorgons
            else {}
        )
        return state, cast, gorgons, targets

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state, _, gorgons, targets = self._options(c, viewer, channel)
            return dict(
                revision=state.revision,
                gorgons=tuple((key, x.name) for key, x in gorgons.items()),
                npcs=tuple((key, x.name) for key, x in targets.items()),
            )

    def tag(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        gorgon: str,
        npc: str,
        label: str,
        account: str,
    ) -> dict[str, Any]:
        if not 0 < len(label.strip()) <= 120 or not 0 < len(account.strip()) <= 1200:
            raise WorkflowError("Provide the actual Tag and how the Erratic Gorgon caused it")

        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, cast, gorgons, targets = self._options(c, viewer, channel)
            lock = self.game.lock(c, channel)
            if state.revision != expected or (lock is not None and lock["state"] != "released"):
                raise WorkflowError(
                    "STALE_ERRATIC: finish the actual current scene Play and reopen the choice"
                )
            target = targets.get(npc)
            if gorgon not in gorgons or target is None:
                raise WorkflowError(
                    "Choose an actual controlled Erratic Gorgon and eligible original NPC"
                )
            assert state.world is not None
            event = str(uuid4())
            actor = ActorRef(kind="gorgon", entity=gorgon)
            tag = WorldTag(id=event, label=label.strip(), giver_entity=actor.model_dump_json())
            altered = target.model_copy(update={"tags": (*target.tags, tag)})
            state.world = update(
                state.world, npcs=tuple(altered if x.id == npc else x for x in state.world.npcs)
            )
            state.facts.append(
                dict(
                    kind="erratic_npc_tag",
                    id=event,
                    gorgon=gorgon,
                    npc=npc,
                    scene=cast.id,
                    account=account.strip(),
                )
            )
            self.game.event(
                c, viewer.user_id, key, TAG_EVENT, state, event_id=event, scene_id=cast.id
            )
            return dict(event=event, state="resolved")

        return self.store._write(
            viewer,
            key,
            TAG_EVENT,
            dict(
                channel=channel,
                expected=expected,
                gorgon=gorgon,
                npc=npc,
                label=label,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
