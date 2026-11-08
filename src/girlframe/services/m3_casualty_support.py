"""The actual physical and career consequences of source-proved Casualty parts."""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def require_god(game: GameService) -> None:
    from girlframe.services.m3_access import Access, digest

    approval = game.store.policy.m3_approval
    registry = Access(game.store).registry
    if (
        approval is None
        or registry is None
        or "plays" not in approval.subsystems
        or approval.registry_sha256 != digest(registry)
        or game.store.policy.owner_m3_rulings is None
        or approval.scope == "core_complete"
        and registry.coverage != "RULES_COMPLETE"
    ):
        raise WorkflowError("M3_REVIEW_PENDING: approve the actual Casualty part source")
    registry.require_available("girl.casualty.wounded-god")


def resistance_answer(answer: ChoiceAnswer) -> tuple[ChoiceAnswer, str | None, str]:

    if not isinstance(answer, ChoiceAnswer):
        raise WorkflowError("Use the actual pending source response")
    part = answer.fields.get("casualty_part")
    account = answer.fields.get("casualty_site_account", "")
    if not part:
        if account:
            raise WorkflowError("Choose the actual infected body part for this source")
        return answer, None, ""
    return (
        answer.model_copy(
            update={
                "fields": {
                    k: v
                    for k, v in answer.fields.items()
                    if k not in {"casualty_part", "casualty_site_account"}
                }
            }
        ),
        part.removeprefix("part:"),
        account,
    )


def part_choices(
    game: GameService, c: Connection, state: object, actor: ActorRef
) -> list[dict[str, str]]:
    from girlframe.engine.m2 import GameState
    from girlframe.engine.m3_casualty import GOD, LABELS, PARTS, body
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.services.m3_casualty import prove_parts

    if not isinstance(state, GameState) or actor.kind != "pilot":
        return []
    sheet = state.sheets.get(actor.entity)
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or not has_rule(sheet, GOD, "CASUALTY")
    ):
        return []
    try:
        require_god(game)
    except (WorkflowError, ValueError):
        return []
    intact: tuple[str, ...]
    value = body(state, actor)
    if value is not None:
        prove_parts(game, c, state, actor)
        intact = tuple(x.id for x in value.parts if x.condition == "intact")
    elif sheet.girl == "CASUALTY":
        setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
        damaged = (
            {x.name.casefold().replace(" ", "_") for x in setup.body_parts if x.damaged}
            if setup
            else set()
        )
        intact = tuple(x for x in PARTS if x not in damaged)
    else:
        return []
    return [dict(id="part:" + x, name="Body part: " + LABELS[x]) for x in intact]


def post_response(
    game: GameService,
    c: Connection,
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    from girlframe.engine.m3_casualty import PartChange, records

    state = load_state(c, game.store.campaign_id)
    actors = tuple(dict.fromkeys(x.actor for x in records(state, PartChange) if x.event == event))
    for actor in actors:
        post_part_change(game, c, actor, event, viewer, key)


def post_part_change(
    game: GameService,
    c: Connection,
    actor: ActorRef,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.engine.m3_casualty import can_pilot, part_state
    from girlframe.engine.m3_physical import stop_piloting
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end
    from girlframe.services.m3_casualty import prove_parts

    state = load_state(c, game.store.campaign_id)
    stamp = actor.token + ":" + event
    if any(
        x.get("kind") == "casualty_part_consequence" and x.get("id") == stamp for x in state.facts
    ):
        return
    if (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        is None
    ):
        raise WorkflowError("Publish the genuine part-change source before its consequences")
    prove_parts(game, c, state, actor)
    fatal = part_state(state, actor, "brain") in ("destroyed", "removed")
    placement = next((x for x in state.placements if x.actor == actor), None)
    stop = not can_pilot(state, actor) and placement is not None and placement.mode == "piloting"
    if not fatal and not stop:
        return
    actual = str(uuid4())
    if fatal:
        changed = end_in_transaction(
            c,
            game,
            state,
            actor,
            reason="death",
            source_event=actual,
            account="Actual source-proved Casualty Brain destruction",
            archive_id=str(uuid4()),
        )
    else:
        changed = stop_piloting(
            state,
            profiles(c, game.store.campaign_id),
            actor,
            actual,
            "Actual broken Casualty Link stops piloting without moving this body",
        )
    changed.facts.append(
        dict(
            kind="casualty_part_consequence",
            id=stamp,
            source=event,
            actor=actor.model_dump_json(),
            event=actual,
        )
    )
    game.event(
        c,
        viewer.user_id if viewer else int(actor.entity),
        key + ":parts:" + event,
        "m3.casualty_brain_destroyed" if fatal else "m3.casualty_piloting_stopped",
        changed,
        event_id=actual,
        source=event,
        subject=actor.model_dump(mode="json"),
    )
    if fatal:
        archive = next(x for x in changed.career_archives if x.actor == actor)
        synchronize_end(c, game, archive)
