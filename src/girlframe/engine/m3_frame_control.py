"""One source-bound neural contact and actual Frame controller; no body movement."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_frame_control_state import FrameCommand, NeuralConnection
from girlframe.engine.m3_janus_link_state import BatteryLink


def connection(state: GameState, identity: str) -> NeuralConnection:
    value = next((x for x in state.neural_connections if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original spinal contact")
    return value


def frame_address(state: GameState, owner: ActorRef, instance: str) -> tuple[ActorRef, str]:
    """An actual rebirth may keep a physical Frame, never its human's replacement."""
    if owner.kind != "external_pilot":
        return owner, instance
    body = next(
        (x for x in state.harpy_states if x.id == owner.entity and x.frame_instance == instance),
        None,
    )
    if body is None:
        return owner, instance
    archive = next(
        (
            x
            for x in state.career_archives
            if x.id == body.original_archive
            and x.actor == body.origin
            and x.source_event == body.source_event
            and x.ending == "harpy"
        ),
        None,
    )
    birth = next(
        (
            x
            for x in state.void_thresholds
            if x.actor == body.origin
            and x.stage == "converted"
            and x.resulting_actor == owner
            and x.response_event == body.source_event
        ),
        None,
    )
    if archive is None or birth is None:
        return owner, instance
    original = PilotSheet.model_validate_json(archive.sheet_json)
    original_frame = (
        original.frame_runtime.id
        if original.frame_runtime
        else "initial:" + str(original.character_id or archive.actor.incarnation)
    )
    return (body.origin, instance) if original_frame == instance else (owner, instance)


def _alive(state: GameState, ref: ActorRef) -> bool:
    if ref.kind == "pilot":
        sheet = state.sheets.get(ref.entity)
        return sheet is not None and sheet.character_id == ref.incarnation
    if ref.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime

        try:
            body = harpy(state, ref)
            if isinstance(body, NativeHarpyRuntime):
                return bool(
                    state.world and any(x.id == ref.entity and x.alive for x in state.world.pilots)
                )
            return body.alive
        except ValueError:
            return bool(
                state.world
                and any(
                    x.id == ref.entity and x.kind in ("rebel", "foundation") and x.alive
                    for x in state.world.pilots
                )
            )
    if ref.kind == "npc":
        return bool(state.world and any(x.id == ref.entity and x.alive for x in state.world.npcs))
    if ref.kind == "gorgon":
        return bool(
            state.world and any(x.id == ref.entity and x.alive for x in state.world.gorgons)
        )
    if ref.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, ref)
    return False


def _has_tags(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        try:
            return bool(harpy(state, actor).tags)
        except ValueError:
            original = (
                next(
                    (
                        x
                        for x in state.world.pilots
                        if x.id == actor.entity and x.kind in ("rebel", "foundation")
                    ),
                    None,
                )
                if state.world
                else None
            )
            if original is None:
                raise ValueError(
                    "Recover this actual external battery's sole Tag authority"
                ) from None
            return bool(original.tags)
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("The original battery's Tags cannot come from a successor")
        return bool(sheet.tags)
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, actor):
            raise ValueError("Use this actual original Handler body's Tags")
        return bool(state.handler_tags)
    values = (
        state.world.npcs
        if state.world and actor.kind == "npc"
        else state.world.gorgons
        if state.world and actor.kind == "gorgon"
        else ()
    )
    actual = next((x for x in values if x.id == actor.entity), None)
    if actual is None:
        raise ValueError("Recover the actual source battery's resources")
    return bool(actual.tags)


def controller(
    state: GameState,
    frame_owner: ActorRef,
    frame_instance: str,
    bindings: tuple[ProfileBinding, ...] = (),
) -> ActorRef | None:
    """A Frame voice or Core's mere presence never establishes piloting control."""
    from girlframe.engine.m3_janus import bound

    requested_owner = frame_owner
    frame_owner, frame_instance = frame_address(state, frame_owner, frame_instance)
    core = bound(state, frame_owner, frame_instance)
    if core is not None and core.takeover_event and core.alive and core.attached and core.linked:
        return ActorRef(kind="external_pilot", entity=core.id)
    commands = [
        x
        for x in state.frame_commands
        if x.active and x.frame_owner == frame_owner and x.frame_instance == frame_instance
    ]
    if len(commands) > 1:
        raise ValueError("Recover this physical Frame's single actual control authority")
    if commands:
        command = commands[0]
        actual = connection(state, command.connection)
        if (
            actual.phase == "connected"
            and actual.battery == command.actor
            and actual.frame_owner == frame_owner
            and actual.frame_instance == frame_instance
            and _alive(state, command.actor)
        ):
            return command.actor
        return None
    history = [
        x
        for x in state.frame_commands
        if x.frame_owner == frame_owner and x.frame_instance == frame_instance
    ]
    if history and history[-1].recovered_event is None:
        return None
    frame_owner = requested_owner
    if not _alive(state, frame_owner):
        return None
    if frame_owner.kind == "pilot":
        sheet = state.sheets[frame_owner.entity]
        current_frame = (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id)
        )
        pose = next((x for x in state.placements if x.actor == frame_owner), None)
        if (
            current_frame == frame_instance
            and pose is not None
            and pose.frame_instance == frame_instance
            and pose.mode == "piloting"
            and pose.occupied_frame_owner is None
            and pose.custody is None
        ):
            return frame_owner
    elif frame_owner.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        try:
            actual_harpy = harpy(state, frame_owner)
        except ValueError:
            external_pose = next(
                (
                    x
                    for x in state.external_poses
                    if x.actor == frame_owner and x.frame == frame_instance and x.mode == "piloting"
                ),
                None,
            )
            pilot = (
                next(
                    (
                        x
                        for x in state.world.pilots
                        if x.id == frame_owner.entity
                        and x.kind in ("rebel", "foundation")
                        and x.alive
                    ),
                    None,
                )
                if state.world
                else None
            )
            if (
                external_pose is not None
                and pilot is not None
                and external_pose.owner == pilot.controller
                and pilot.custody == "free"
            ):
                return frame_owner
        else:
            if actual_harpy.frame_instance == frame_instance and actual_harpy.linked:
                return frame_owner
    return None


def active_takeover(state: GameState, owner: ActorRef, frame: str) -> ActorRef | None:
    from girlframe.engine.m3_janus import bound

    owner, frame = frame_address(state, owner, frame)
    core = bound(state, owner, frame)
    if core is not None and core.takeover_event and core.alive and core.attached and core.linked:
        return ActorRef(kind="external_pilot", entity=core.id)
    active = [
        x
        for x in state.frame_commands
        if x.active and x.frame_owner == owner and x.frame_instance == frame
    ]
    if len(active) > 1:
        raise ValueError("Recover this actual Frame's sole source controller")
    return active[0].actor if active else None


def recover_control(state: GameState, owner: ActorRef, frame: str, event: str) -> GameState:
    if active_takeover(state, owner, frame) is not None:
        raise ValueError("An actual takeover cannot be overwritten by ordinary piloting")
    state = GameState.model_validate_json(state.model_dump_json())
    owner, frame = frame_address(state, owner, frame)
    state.frame_commands = [
        x.model_copy(update=dict(recovered_event=event))
        if not x.active
        and x.frame_owner == owner
        and x.frame_instance == frame
        and x.recovered_event is None
        else x
        for x in state.frame_commands
    ]
    return state


def unplug(
    original: GameState,
    identity: str,
    actor: ActorRef,
    event: str,
    account: str,
    *,
    ended: bool = False,
) -> GameState:
    from girlframe.engine.m3_janus_link import expire_link_assets

    value = connection(original, identity)
    if (
        value.phase != "connected"
        or actor not in (value.caster, value.battery)
        or not account.strip()
    ):
        raise ValueError("Record an actual original participant's connected neural unplug")
    state = GameState.model_validate_json(original.model_dump_json())
    for link in list(state.battery_links):
        if link.connection != identity or link.phase in ("unplugged", "ended"):
            continue
        state = expire_link_assets(state, link, event)
        updated = link.model_copy(
            update=dict(
                phase="ended" if ended else "unplugged", end_event=event, end_reason=account.strip()
            )
        )
        state.battery_links = [updated if x.id == link.id else x for x in state.battery_links]
    state.neural_connections = [
        x.model_copy(
            update=dict(
                phase="ended" if ended else "unplugged",
                ended_event=event,
                ended_by=actor,
                end_account=account.strip(),
            )
        )
        if x.id == identity
        else x
        for x in state.neural_connections
    ]
    state.frame_commands = [
        x.model_copy(update=dict(active=False, ended_event=event))
        if x.active and x.connection == identity
        else x
        for x in state.frame_commands
    ]
    return state


def end_actor(original: GameState, actor: ActorRef, event: str) -> GameState:
    """End only source gameplay authority; do not claim physical unplug or relocation."""
    state = original
    for value in list(state.neural_connections):
        if actor not in (value.caster, value.battery) or value.phase in (
            "refused",
            "unplugged",
            "ended",
        ):
            continue
        if value.phase == "connected":
            state = unplug(
                state,
                value.id,
                actor,
                event,
                "Original career/body ended; this gameplay connection is interrupted",
                ended=True,
            )
        else:
            state = GameState.model_validate_json(state.model_dump_json())
            state.neural_connections = [
                x.model_copy(
                    update=dict(
                        phase="ended",
                        ended_event=event,
                        ended_by=actor,
                        end_account="Original career/body ended before actual contact",
                    )
                )
                if x.id == value.id
                else x
                for x in state.neural_connections
            ]
    return state


def prepare_endings(previous: GameState, state: GameState, event: str) -> GameState:
    ended = [
        x.actor
        for x in state.career_archives
        if x.source_event == event and not any(y.id == x.id for y in previous.career_archives)
    ]
    ended += [
        x.actor
        for x in state.handler_archives
        if x.source_event == event and not any(y.id == x.id for y in previous.handler_archives)
    ]
    ended += [
        ActorRef(kind="external_pilot", entity=x.id)
        for x in state.harpy_states
        if not x.alive and x.condition_event == event
    ]
    if state.world and previous.world:
        ended += [
            ActorRef(kind="external_pilot", entity=x.id)
            for x in state.world.pilots
            if not x.alive and any(y.id == x.id and y.alive for y in previous.world.pilots)
        ]
        ended += [
            ActorRef(kind="npc", entity=x.id)
            for x in state.world.npcs
            if not x.alive and any(y.id == x.id and y.alive for y in previous.world.npcs)
        ]
        ended += [
            ActorRef(kind="gorgon", entity=x.id)
            for x in state.world.gorgons
            if not x.alive and any(y.id == x.id and y.alive for y in previous.world.gorgons)
        ]
    for actor in dict.fromkeys(ended):
        state = end_actor(state, actor, event)
    return state


def takeover(original: GameState, link: BatteryLink, event: str) -> GameState:
    """Trusted source service proves actual final-Tag erasure before this exact effect."""
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_janus import find as find_core

    actual = connection(original, link.connection or "")
    if (
        actual.phase != "connected"
        or actual.caster != link.caster
        or actual.battery != link.battery
        or actual.frame_owner != link.caster_frame_owner
        or actual.frame_instance != link.caster_frame
        or not link.erased_tag
        or not link.erasure_event
        or link.erasure_event != event
        or link.erased_tag not in (link.erasure_before_tags or link.source_tags)
        or _has_tags(original, link.battery)
    ):
        raise ValueError(
            "Only actual final source Tag erasure releases this original Frame control"
        )
    state = GameState.model_validate_json(original.model_dump_json())
    state.placements = [
        x.model_copy(
            update=dict(
                mode="inside_frame",
                source_event=event,
                account="Actual original piloting control lost to source-bound neural takeover",
            )
        )
        if x.actor == actual.frame_owner
        and x.frame_instance == actual.frame_instance
        and x.mode == "piloting"
        and x.occupied_frame_owner is None
        else x
        for x in state.placements
    ]
    core = find_core(state, link.battery)
    if (
        core is not None
        and core.attached
        and core.linked
        and core.frame_owner == actual.frame_owner
        and core.frame_instance == actual.frame_instance
    ):
        state.janus_cores = [
            x.model_copy(update=dict(takeover_event=event, state_event=event))
            if x.id == core.id
            else x
            for x in state.janus_cores
        ]
    else:
        identity = str(uuid5(NAMESPACE_URL, "girlframe:frame-control:" + link.id))
        if any(
            x.active
            and x.frame_owner == actual.frame_owner
            and x.frame_instance == actual.frame_instance
            for x in state.frame_commands
        ):
            raise ValueError("This Frame already has another actual takeover source")
        state.frame_commands.append(
            FrameCommand(
                id=identity,
                actor=link.battery,
                frame_owner=actual.frame_owner,
                frame_instance=actual.frame_instance,
                connection=actual.id,
                battery_link=link.id,
                source_event=event,
            )
        )
    # Source resource mutation is owned by JANUS's sole-frame resource effect port.
    # This operation changes no cell, cockpit occupancy, assigned Frame or body.
    if link.battery.kind == "external_pilot":
        harpy(state, link.battery)  # Prove the actual source body; no controller-PC substitution.
    return state
