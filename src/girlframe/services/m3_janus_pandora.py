"""Actual Off-Duty insemination, shared birth roll and owned Handler newborn authoring."""

from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus_pandora as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, spend_heat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_janus_requisitions import PANDORA
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_janus_requisitions import owned
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_scene_requisitions import _activation
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    if period.phase != "active":
        return
    state = load_state(c, store.campaign_id)
    if not any(getattr(x, "rule_id", None) == PANDORA for x in state.requisitions):
        return
    activation = _activation(c, store, period)
    if activation is None:
        return
    source, activation_event = activation
    game = GameService(store)
    changed = False
    for uid in period.pilots:
        if (
            str(uid) in period.ended_characters
            or str(uid) not in source.sheets
            or str(uid) not in state.sheets
        ):
            continue
        actor = current_ref(source, uid)
        if state.sheets[str(uid)].character_id != actor.incarnation:
            continue
        receipt = owned(c, game, source, actor, PANDORA)
        if receipt is None or owned(c, game, state, actor, PANDORA) is None:
            continue
        if any(
            x.actor == actor
            and x.frame == receipt.frame_instance
            and (x.period == period.id or x.phase != "born")
            for x in rules.pregnancies(state)
        ):
            continue
        judge, appointment = MedicalService(store)._handler(c)
        value = rules.Pregnancy(
            id=str(uuid5(NAMESPACE_URL, "girlframe:pandora:" + period.id + ":" + actor.token)),
            actor=actor,
            frame=receipt.frame_instance,
            purchase=receipt.id,
            period=period.id,
            source_event=activation_event,
            judge=judge,
            appointment=appointment,
        )
        rules.put(state, value)
        changed = True
    if changed:
        game.event(
            c,
            period.handler,
            str(uuid4()),
            "m3.janus_inseminated",
            state,
            period_id=period.id,
            source_event=activation_event,
        )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Pregnancy:
    value = rules.get(state, identity)
    history = t.m3["m3_off_duty_history"]
    body = c.scalar(
        sa.select(history.c.body_json)
        .where(history.c.campaign_id == game.store.campaign_id, history.c.id == value.period)
        .order_by(history.c.revision)
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover the actual original Off-Duty source of Inseminated")
    period = Period.model_validate_json(body)
    activation = _activation(c, game.store, period)
    if activation is None or activation[1] != value.source_event:
        raise WorkflowError("This pregnancy needs its actual period activation")
    receipt = owned(c, game, activation[0], value.actor, PANDORA)
    if receipt is None or receipt.id != value.purchase or receipt.frame_instance != value.frame:
        raise WorkflowError("No retroactive or other-Frame PANDORA grants")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
) -> dict[str, Any]:
    access = Access(game.store)
    access.authorize(c, viewer, "plays")
    assert access.registry is not None
    access.registry.require_available(PANDORA)
    actor = current_ref(state, viewer.user_id)
    receipt = owned(c, game, state, actor, PANDORA)
    if receipt is None:
        raise WorkflowError("Acquire the actual PANDORA implanted womb first")
    values = [
        x
        for x in rules.pregnancies(state)
        if x.actor == actor and x.frame == receipt.frame_instance and x.phase == "inseminated"
    ]
    if len(values) != 1 or state.world is None:
        raise WorkflowError("Go Off-Duty with PANDORA and establish the actual world before birth")
    value = prove(game, c, state, values[0].id)
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if actual.frame_cell is None:
        raise WorkflowError(
            "Establish the original Frame's actual birthplace "
            "through approved placement before birth"
        )
    if (
        prepared.target_actor is not None
        or prepared.target is not None
        or prepared.identity
        or prepared.gain
        or prepared.pair_share
        or prepared.parent
        or prepared.source_work
        or prepared.off_duty_id
        or prepared.order_id
        or not prepared.context.strip()
        or not prepared.trigger_confirmed
    ):
        raise WorkflowError("Birth from the actual Inseminated Frame using its real available Heat")
    spend_heat(state.sheets[actor.entity].model_copy(deep=True), prepared.heat)
    cast = _cast(game, c, state, channel)
    if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
        raise WorkflowError("Join as the actual original mother in this source scene")
    judge, appointment = MedicalService(game.store)._handler(c)
    assert game.store.policy.m3_approval is not None
    return dict(
        mode="pandora",
        actor=actor.model_dump(mode="json"),
        actor_controller=viewer.user_id,
        target_controller=judge,
        judge=judge,
        appointment=appointment,
        pregnancy=value.id,
        frame=value.frame,
        purchase=receipt.id,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({x.controller for x in cast.roles} | {cast.facilitator}),
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["janus"]
    value = prove(game, c, state, meta["pregnancy"])
    receipt = owned(c, game, state, value.actor, PANDORA)
    if value.phase != "inseminated" or receipt is None or receipt.id != meta["purchase"]:
        raise WorkflowError(
            "Recover this actual original Inseminated Frame before the one birth roll"
        )
    view = resolve(state, value.actor, profiles(c, game.store.campaign_id))
    if view.frame_instance != value.frame or view.frame_scrapped:
        raise WorkflowError("Birth only from this actual original available implanted Frame")
    if view.frame_cell is None:
        raise WorkflowError(
            "Establish the original Frame's actual birthplace "
            "through approved placement before birth"
        )
    event = str(uuid4())
    rules.put(
        state,
        value.model_copy(
            update=dict(
                phase="birth_rolled",
                birth_action=action["id"],
                roll_event=event,
                birth_cell=view.frame_cell,
                judge=meta["judge"],
                appointment=meta["appointment"],
            )
        ),
    )
    meta["roll_event"] = event


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["janus"]
    value = prove(game, c, state, meta["pregnancy"])
    if value.phase != "birth_rolled" or value.tier is not None:
        raise WorkflowError("Resume the actual known birth result instead of writing it twice")
    rules.put(state, value.model_copy(update={"tier": action["data"]["result"]["tier"]}))
    game.request(c, action, value.judge, "janus_pandora_child")


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any]:
    from girlframe.engine.m3_gorgon_catalog import ASSETS

    value = prove(game, c, state, action["data"]["janus"]["pregnancy"])
    tier = str(value.tier)
    return dict(
        count={"low": 1, "mid": 2, "high": 3}[tier],
        classes={"low": ["dormant"], "mid": ["benevolent"], "high": ["aggressive", "erratic"]}[
            tier
        ],
        types=list(ASSETS),
        assets=ASSETS,
        behavior={
            "low": "Stays at its actual birthplace",
            "mid": "Obedient and vicious",
            "high": "Willful; will not harm original mother",
        }[tier],
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    value = prove(game, c, state, action["data"]["janus"]["pregnancy"])
    if request["kind"] != "janus_pandora_child" or int(request["actor_id"]) != value.judge:
        raise WorkflowError("Only the actual original Handler writes this real child")
    if MedicalService(game.store)._handler(c) != (value.judge, value.appointment):
        raise WorkflowError("Recover the source birth's original Handler appointment")
    if (
        answer.options
        or answer.number is not None
        or answer.flag is not None
        or answer.denied
        or answer.member is not None
        or set(answer.fields) != {"child"}
    ):
        raise WorkflowError("Submit the actual Handler-authored child proposal only")
    proposal = rules.ChildProposal.model_validate_json(answer.fields["child"])
    changed = rules.write_child(state, value.id, proposal, action["data"]["response_event"])
    for field in GameState.model_fields:
        setattr(state, field, getattr(changed, field))
    child = rules.get(state, value.id).child
    assert child is not None
    action["data"]["result"]["child"] = child.model_dump(mode="json")
    ChoiceEngine(game).finish(c, state, action)


def menu(game: GameService, viewer: GuildViewer) -> dict[str, Any]:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        actor = current_ref(state, viewer.user_id)
        actual = resolve(state, actor, profiles(c, game.store.campaign_id))
        values = [
            x
            for x in rules.pregnancies(state)
            if x.actor == actor and x.frame == actual.frame_instance
        ]
        return dict(
            pregnancies=[x.model_dump(mode="json") for x in values],
            heat=state.sheets[actor.entity].heat,
            sheet_revision=state.sheets[actor.entity].revision,
            can_birth=owned(c, game, state, actor, PANDORA) is not None
            and any(x.phase == "inseminated" for x in values),
        )
