"""Actual scene-owned Frame Core facts; potential Tag marking spends nothing."""

from typing import Any

from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService, _cast, _scene_judge
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class FrameCoreService:
    def __init__(self, battle: BattleService):
        self.battle = battle

    def preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        battle, game = self.battle, self.battle.game
        data = battle.preview(viewer, channel)
        with battle.store.engine.connect() as c:
            state = load_state(c, battle.store.campaign_id)
            if data["revision"] != state.revision:
                raise WorkflowError("STALE_CORE: reopen this scene's actual Frame facts")
            cast = _cast(game, c, state, channel)
            _, judge, _ = _scene_judge(game, c, state, cast)
            bound = profiles(c, battle.store.campaign_id)
            result = []
            for row in data["actors"]:
                target = ActorRef.model_validate(row["ref"])
                actual = resolve(state, target, bound, require_current_profile=False)
                if target.kind != "pilot" or not actual.inside_frame:
                    continue
                if not row["owned"] and judge != viewer.user_id:
                    continue
                placement = next((x for x in state.placements if x.actor == target), None)
                if placement is None or placement.occupied_frame_owner is not None:
                    continue
                sheet = state.sheets[target.entity]
                girl = [x for x in sheet.assets if x.family == "girl"]
                opponents = []
                if viewer.user_id == judge:
                    for enemy_row in data["actors"]:
                        enemy = ActorRef.model_validate(enemy_row["ref"])
                        other = resolve(state, enemy, bound, require_current_profile=False)
                        if other.controller == actual.controller:
                            continue
                        opponents.append(
                            dict(
                                token=enemy.token,
                                ref=enemy.model_dump(mode="json"),
                                name=other.label,
                                intense=depth(state, target, enemy) == 2,
                                tags=[
                                    dict(id=x.id, name=x.label)
                                    for x in sheet.tags
                                    if other.controller in x.observers
                                    and x.scene_used != cast.id
                                    and not x.rejection_pending
                                ],
                            )
                        )
                result.append(
                    dict(
                        token=target.token,
                        ref=target.model_dump(mode="json"),
                        name=actual.label,
                        willing=row["owned"],
                        opponents=opponents,
                        girl_assets=bool(girl) and all(x.damaged for x in girl),
                        identities=bool(sheet.identities)
                        and all(x.marked for x in sheet.identities),
                    )
                )
            return dict(revision=state.revision, scene=cast.id, targets=result)
