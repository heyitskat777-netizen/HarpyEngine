"""Project the actual cast Harpy's independent Plays off the native engine controls."""

from battlefield import ASSAULT, CORE, Battlefield

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_plays import HEAT_IDS
from girlframe.services import m3_dive, m3_engage, m3_harpy_flirt, m3_harpy_rest
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_battle import authorize as authorize_battle
from girlframe.services.native_form_fields import Field, form_fields
from girlframe.services.onboarding import WorkflowError


def harpy_plays(game, c, viewer, scene, state, cast, role):
    service = ActorPlayService(game)
    channel = int(scene["channel_id"])
    actor = role.ref
    view = service.preview(viewer, channel, actor)
    if view["game_revision"] != state.revision or role.heat is None:
        return ()
    heat = [role.heat] if role.heat >= 5 else list(range(role.heat + 1))
    base = {"adjudicator": view["adjudicator"]["ref"], "piloting": bool(role.piloting)}
    playable = []
    specs = (
        ("put_someone_beneath_you", "Put Someone Beneath You", view["beneath_targets"]),
        ("keep_your_head", "Keep Your Head", (None,)),
        ("check_sensors", "Check Sensors", (None,)),
        ("dive_deep", "Dive Deep", (None,)),
        ("go_off_duty", "Go Off-Duty", (None,)),
        ("flirt", "Flirt", view["opponents"]),
        ("engage", "Engage the Enemy", view["opponents"]),
        ("snoop", "Snoop", view["snoop_targets"]),
        ("enforcement_initiative", "Enforcement Initiative", view["enforcement_targets"]),
    )
    for play, label, targets in specs:
        try:
            service._eligible_play(state, actor, rejection=False, play=play)
        except (ValueError, WorkflowError):
            continue
        for target in targets:
            ref = ActorRef.model_validate(target["ref"]) if target else None
            sample = PlayInput(
                play=play,
                context="Preview the actual Play trigger.",
                trigger_confirmed=True,
                heat=0,
                target_actor=ref,
                piloting=bool(role.piloting) if play == "engage" else False,
            )
            try:
                if play == "go_off_duty":
                    m3_harpy_rest.prepare(game, c, viewer, state, cast, sample, actor)
                elif play == "dive_deep":
                    m3_dive.prepare_actor(game, c, viewer, state, cast, sample, actor)
                elif play == "flirt":
                    m3_harpy_flirt.prepare(game, c, state, cast, actor, sample)
                elif play == "engage":
                    m3_engage.prepare(game, c, viewer, state, scene, sample, actor_ref=actor)
            except (ValueError, WorkflowError):
                continue
            choices = {} if play in ("check_sensors", "go_off_duty") else {"heat": heat}
            playable.append(
                dict(
                    key="harpy_beneath" if play == "put_someone_beneath_you" else "harpy_" + play,
                    label=label,
                    target_token=target["token"] if target else "self",
                    target_name=(target.get("name") or target.get("label")) if target else "",
                    binding=base
                    | dict(
                        harpy_basic=play,
                        target=target["ref"] if target else None,
                        choices=choices,
                        costs=choices,
                        reach="same_cell"
                        if play
                        in (
                            "flirt",
                            "put_someone_beneath_you",
                        )
                        else "native_review",
                    ),
                )
            )
    for item in state.obligations:
        if item.kind != "harpy_flirt_followthrough" or item.owner != viewer.user_id:
            continue
        try:
            service._eligible_play(state, actor, rejection=False, play="harpy_followthrough")
            owed = m3_harpy_flirt.prepare_followthrough(
                game,
                c,
                state,
                cast,
                actor,
                PlayInput(
                    play="harpy_followthrough",
                    context="Preview the actual owed follow-through.",
                    trigger_confirmed=True,
                    heat=0,
                    source_work=item.id,
                ),
            )
            target = ActorRef.model_validate(owed["target"])
            recipient = resolve(state, target, profiles(c, game.store.campaign_id))
        except (ValueError, WorkflowError):
            continue
        playable.append(
            dict(
                key="harpy_followthrough_" + item.id,
                label="Follow through on Flirt",
                target_token=target.token,
                target_name=recipient.label,
                binding=base
                | dict(
                    harpy_basic="harpy_followthrough",
                    target=None,
                    source_work=item.id,
                    choices={},
                    costs={},
                    reach="native_review",
                ),
            )
        )
    try:
        authorize_battle(game, c, viewer)
        battle = BattleService(game.store).preview(viewer, channel)
    except (ValueError, WorkflowError):
        return tuple(playable)
    if battle["revision"] != state.revision:
        return tuple(playable)
    bound = profiles(c, game.store.campaign_id)
    actors = {row["token"]: row for row in battle["actors"]}
    for play in (ASSAULT, CORE):
        try:
            service._eligible_play(state, role.ref, rejection=False, play=play)
        except (ValueError, WorkflowError):
            continue
        if play not in HEAT_IDS:
            continue
        option = Battlefield.declared_options(state, bound, battle, play, actor_token=actor.token)
        if option is None:
            continue
        for target in option["targets"]:
            victim = actors[target["id"]]
            fields = [
                Field(
                    "weapon",
                    "Your actual attacking Asset",
                    tuple((x["id"], x["name"]) for x in option["attacking_assets"]),
                )
            ]
            if play == ASSAULT:
                fields.append(
                    Field(
                        "opposing_asset",
                        "Original opposing Asset",
                        tuple((x["id"], x["name"]) for x in target["assets"]),
                    )
                )
            playable.append(
                dict(
                    key="harpy_battle_" + play,
                    label=option["label"],
                    target_token=victim["token"],
                    target_name=victim["name"],
                    binding=base
                    | dict(
                        harpy_battle=play,
                        target=victim["ref"],
                        target_sha256=victim["sha256"],
                        combat_sha256=actors[actor.token]["sha256"],
                        fields=form_fields(fields),
                        choices={},
                        costs={},
                        reach="requires_judge",
                    ),
                )
            )
    return tuple(playable)
