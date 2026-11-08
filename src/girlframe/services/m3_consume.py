"""Original CONSUME choices consume actual body, custody and acquisition sources."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_consume as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
from girlframe.engine.m3_budget_removal import blocked
from girlframe.engine.m3_frame_state import SuppliedAsset
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_sprite import Blow
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "consume_eat",
    "consume_feral",
    "consume_child",
    "consume_erase",
    "consume_partake",
    "consume_time_eat",
    "consume_order_child",
)
HEAT_IDS = ("consume_eat",)


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def acting(state: GameState, action: dict[str, Any]) -> ActorRef | None:
    actual = action["data"].get("tag_context", {}).get("actor")
    if actual is not None:
        return ActorRef.model_validate(actual)
    owner = str(action["actor_id"])
    return current_ref(state, int(owner)) if owner in state.sheets else None


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=action is not None)
    if action is not None:
        meta = action["data"].get("consume")
        if meta is None:
            state = load_state(c, game.store.campaign_id)
            if not any(
                x.action == action["id"] and x.actor.entity == str(viewer.user_id)
                for x in rules.records(state, rules.Opportunity)
            ) and not any(
                x.parent == action["id"] and x.actor.entity == str(viewer.user_id)
                for x in rules.records(state, rules.OrderPursuit)
            ):
                raise WorkflowError(
                    "Only the actual original optional source owner answers this choice"
                )
            return
        approval = game.store.policy.m3_approval
        if (
            approval is None
            or approval.registry_sha256 != meta["registry"]
            or viewer.user_id not in meta["table"]
        ):
            raise WorkflowError(
                "Only an actual original source-table human may answer this CONSUME source"
            )


def _native(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    rules.frame(state, actor)
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if not actual.alive or actual.offstage_source or actual.inside_frame is None:
        raise WorkflowError(
            "Establish the actual original living body and physical CONSUME context"
        )
    return actual


def prove_acquisition(
    game: GameService, c: Connection, state: GameState, receipt: FrameRuleReceipt
) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.id == receipt.source_event,
                t.events.c.campaign_id == game.store.campaign_id,
            )
        )
        .mappings()
        .first()
    )
    saved = _history(c, game, receipt.source_event)
    if (
        row is None
        or row["kind"] != "m3.ability_unlock_purchased"
        or row["actor_id"] != receipt.actor.entity
        or receipt not in saved.requisitions
        or receipt.donor_frame != "CONSUME"
        or receipt.rule_id not in rules.REQUISITIONS
        or receipt.price != 2
        or receipt.kind != "ability_unlock"
        or receipt.grant != "consume:" + receipt.id
        or json.loads(row["payload_json"]).get("requisition_id") != receipt.id
    ):
        raise WorkflowError("Recover the actual original paid CONSUME acquisition receipt")


def require_rule(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> None:
    _native(game, c, state, actor)
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("Review the actual CONSUME source registry")
    registry.require_available(rule)
    if rule in rules.REQUISITIONS:
        receipt = rules.held(state, actor, rule)
        if receipt is None:
            raise WorkflowError("Acquire this actual original Frame Requisition first")
        prove_acquisition(game, c, state, receipt)


def require_heat(state: GameState, actor: ActorRef, heat: int) -> None:
    if rules.hunger(state, actor) == "Ravenous" and heat:
        raise WorkflowError("RAVENOUS: the actual CONSUME Pilot cannot spend Heat")


def roll_basis(
    state: GameState, actor: ActorRef, play: str, heat: int, *, seek_food: bool = False
) -> int:
    require_heat(state, actor, heat)
    level = rules.hunger(state, actor)
    if play == "consume_feral":
        if heat:
            raise WorkflowError("Feral uses its actual hunger basis rather than spending Heat")
        return {"Quiet": -1, "Gnawing": 1, "Ravenous": 3}[level]
    return 4 if level == "Ravenous" and seek_food else heat


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    from girlframe.services import m3_consume_support as support

    authorize(game, c, viewer)
    actor = current_ref(state, viewer.user_id)
    require_rule(game, c, state, actor, rules.PLAYS[prepared.play])
    cast = _cast(game, c, state, channel)
    handler = active_handler(state)
    if handler is None or not any(
        x.actor == actor and x.controller == viewer.user_id for x in cast.roles
    ):
        raise WorkflowError("Use the actual original CONSUME Pilot, Handler and scene")
    if (
        prepared.source_work
        or prepared.target is not None
        or prepared.order_id
        or prepared.off_duty_id
    ):
        raise WorkflowError("Use the actual CONSUME source and target in this scene")
    if not prepared.context.strip() or not prepared.trigger_confirmed:
        raise WorkflowError("Declare your actual lunge or succumb to an actual impulse")
    context: dict[str, Any] = {}
    if prepared.play == "consume_eat":
        if prepared.target_actor is None or prepared.target_actor == actor:
            raise WorkflowError("Lunge at another actual original person")
        context = support.context(game, c, state, actor, prepared.target_actor, cast)
    elif prepared.target_actor is not None:
        raise WorkflowError("Feral's actual impulse does not invent a target")
    basis = roll_basis(
        state, actor, prepared.play, prepared.heat, seek_food=prepared.play == "consume_eat"
    )
    if cast not in state.scene_casts:
        state.scene_casts.append(cast)
    assert game.store.policy.m3_approval is not None
    return dict(
        play=prepared.play,
        actor=actor.model_dump(mode="json"),
        target=prepared.target_actor.model_dump(mode="json") if prepared.target_actor else None,
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        table=sorted(
            {x.controller for x in cast.roles}
            | {state.handler}
            | ({cast.facilitator} if cast.facilitator is not None else set())
        ),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        registry=game.store.policy.m3_approval.registry_sha256,
        frame=rules.frame(state, actor),
        hunger=rules.hunger(state, actor),
        sourcefacts=context,
        basis=basis,
        phase="unrolled",
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    action["data"]["consume"]["begin_event"] = event


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["consume"]
    expected = prepare(
        game,
        c,
        viewer,
        state,
        PlayInput.model_validate(action["data"]["prepared"]),
        int(action["channel_id"]),
    )
    if any(meta.get(k) != v for k, v in expected.items() if k != "phase"):
        raise WorkflowError(
            "Reopen actual unchanged CONSUME bodies, hunger and source before rolling"
        )


def _source(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.Session:
    source = rules.session(state, action["id"])
    meta = action["data"]["consume"]
    if (
        source.actor.model_dump(mode="json") != meta["actor"]
        or source.frame != meta["frame"]
        or not action["data"].get("receipt")
    ):
        raise WorkflowError("Preserve the actual original CONSUME source and committed receipt")
    return source


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["consume"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume this actual CONSUME receipt without rerolling")
    _, roll_event = _raw_receipt(game, c, action)
    context = meta["sourcefacts"]
    source = rules.Session(
        id=action["id"],
        play=meta["play"],
        actor=ActorRef.model_validate(meta["actor"]),
        target=ActorRef.model_validate(meta["target"]) if meta["target"] else None,
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        frame=meta["frame"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        hunger=meta["hunger"],
        vulnerable=context.get("vulnerable", False),
        killable=context.get("killable", False),
        total=action["data"]["result"]["total"],
        roll_event=roll_event,
        event=action["data"].get("response_event") or roll_event,
    )
    rules.put(state, source)
    meta["phase"] = "choosing"
    chooser = (
        source.handler_controller
        if source.play == "consume_feral" and (source.total < 8 or source.total > 10)
        else int(source.actor.entity)
    )
    game.request(c, action, chooser, source.play)


def _eat_options(
    game: GameService, c: Connection, state: GameState, source: rules.Session
) -> list[tuple[str, str]]:
    if source.total < 8:
        return [("repelled", "They fight you off")]
    options = [
        ("kill", "Consume them entirely")
        if source.vulnerable and source.total >= 11 and source.killable
        else ("bite", "Bite down")
    ]
    if source.vulnerable and source.killable and source.total < 11:
        options.append(("kill", "Consume them entirely"))
    if source.total < 11:
        options.append(("swallow", "Swallow them alive"))
    if source.hunger != "Ravenous" and rules.held(state, source.actor, rules.NIBBLE):
        require_rule(game, c, state, source.actor, rules.NIBBLE)
        options.append(("nibble", "Hold your teeth gently and deepen your Bond"))
    return options


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    kind = row["kind"]
    if kind in ("consume_time_eat", "consume_partake"):
        offer = next(
            x
            for x in rules.records(state, rules.Opportunity)
            if x.action == action["id"]
            and x.kind == ("partake" if kind == "consume_partake" else "time_eat")
        )
        sheet = state.sheets[offer.actor.entity]
        regrowth: tuple[dict[str, str], ...] = ()
        if kind == "consume_partake":
            from girlframe.services.m3_consume_regrowth import regrowth_options

            regrowth = regrowth_options(game, c, state, offer.actor, action)
        return dict(
            options=[("pass", "Decline"), ("give", "Mark an Identity and give Just Meat")]
            if kind == "consume_time_eat"
            else [
                ("pass", "Decline"),
                ("regrow", "Damage a Girl Asset; regrow up to two Frame Assets"),
                ("excrete", "Lose a Girl Asset; excrete a new Void Frame Asset"),
                ("appearance", "Change appearance and touch a Girl Asset with Void"),
            ],
            identities=[(x.id, x.name) for x in sheet.identities if not x.marked],
            girl_assets=[(x.id, x.name) for x in sheet.assets if x.family == "girl"],
            frame_assets=[(row["id"], row["label"]) for row in regrowth],
            regrow_missing=[row["id"] for row in regrowth if row["kind"] == "missing"],
            regrow_free=max(
                0,
                frame_capacity(sheet, state)
                - sum(
                    counts_toward_limit(sheet, asset)
                    for asset in sheet.assets
                    if asset.family == "frame"
                ),
            ),
            regrow_replacements=[
                (asset.id, asset.name)
                for asset in sheet.assets
                if asset.family == "frame"
                and can_replace_at_limit(sheet, asset)
                and asset.id not in blocked(state, offer.actor)
            ],
            frame_replacements=[
                (x.id, x.name)
                for x in sheet.assets
                if x.family == "frame" and can_replace_at_limit(sheet, x)
            ],
        )
    if kind == "consume_order_child":
        pursuit = next(
            x for x in rules.records(state, rules.OrderPursuit) if x.parent == action["id"]
        )
        return dict(child=pursuit.id, tag=pursuit.tag, options=[])
    source = _source(game, c, state, action)
    if kind == "consume_child":
        child = next(x for x in rules.records(state, rules.Reaffirmation) if x.session == source.id)
        return dict(child=child.id, tag=child.tag, options=[])
    if kind == "consume_erase":
        return dict(
            options=[
                ("forget", "Destroy all canonical memory of the actual killed person"),
                ("remember", "Do not erase their existence"),
            ]
        )
    context = action["data"]["consume"]["sourcefacts"]
    return dict(
        options=_eat_options(game, c, state, source)
        if kind == "consume_eat"
        else [(k, v) for k, v in rules.TAGS.items()]
        if source.total >= 8
        else [],
        own_assets=[(x["id"], x["name"]) for x in context.get("own_assets", [])],
        target_assets=[(x["id"], x["name"]) for x in context.get("target_assets", [])],
        tier="low" if source.total < 8 else "high" if source.total >= 11 else "mid",
        own_cost=source.total < 8 or not source.vulnerable,
    )


detail = projection


def _tag(
    game: GameService,
    c: Connection,
    state: GameState,
    source: rules.Session,
    label: str,
    event: str,
    *,
    giver: ActorRef | None = None,
) -> str:
    changed = give_tag(
        state,
        profiles(c, game.store.campaign_id),
        source.actor,
        giver or source.handler,
        label,
        event,
        event,
        tuple(sorted({x.controller for x in source.cast.roles})),
    )
    _copy(state, changed)
    return event


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services import m3_consume_support as support

    event = action["data"]["response_event"]
    kind = row["kind"]
    if kind in ("consume_time_eat", "consume_partake"):
        _apply_opportunity(game, c, state, action, row, answer)
        if not game.pending(c, action["id"]):
            from girlframe.services.m2_choices import ChoiceEngine

            ChoiceEngine(game).finish(c, state, action)
        return
    source = _source(game, c, state, action)
    if (
        answer.denied
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
        or not answer.text.strip()
        or len(answer.options) != (0 if kind == "consume_feral" and source.total < 8 else 1)
    ):
        raise WorkflowError("Choose only your actual printed CONSUME result and source account")
    expected = (
        source.handler_controller
        if kind == "consume_feral" and (source.total < 8 or source.total >= 11)
        else int(source.actor.entity)
    )
    if int(row["actor_id"]) != expected or source.completed_event:
        raise WorkflowError("Preserve the actual original chooser and pending CONSUME source")
    if kind == "consume_child":
        raise WorkflowError(
            "Perform the actual required Play; an acknowledgement cannot reaffirm the Tag"
        )
    if kind == "consume_erase":
        if answer.fields or answer.options not in (("forget",), ("remember",)):
            raise WorkflowError("Choose whether to erase the actual committed killed person")
        consumed = next(
            x for x in rules.records(state, rules.Consumption) if x.session == source.id
        )
        if consumed.option != "kill" or source.target is None:
            raise WorkflowError("Ontological Consumption requires the actual completed killing")
        if answer.options == ("forget",):
            _copy(
                state, support.forget(game, c, state, source.actor, source.target, event, source.id)
            )
            rules.put(
                state,
                rules.Erasure(
                    id=event,
                    session=source.id,
                    actor=source.actor,
                    target=source.target,
                    event=event,
                ),
            )
        action["data"]["consume"]["phase"] = "effects"
        return
    if kind == "consume_feral":
        if answer.fields:
            raise WorkflowError("The original printed chooser authors only this actual Tag")
        tier: Literal["low", "mid", "high"] = (
            "low" if source.total < 8 else "high" if source.total >= 11 else "mid"
        )
        label = answer.text.strip() if tier == "low" else rules.TAGS.get(answer.options[0])
        if label is None or len(label) > 120:
            raise WorkflowError("Select the actual printed Feral Tag")
        tag = _tag(
            game,
            c,
            state,
            source,
            label,
            event,
            giver=source.actor if tier == "mid" else source.handler,
        )
        rules.put(
            state,
            rules.FeralEffect(
                id=event,
                session=source.id,
                actor=source.actor,
                handler=source.handler,
                tag=tag,
                label=label,
                tier=tier,
                event=event,
            ),
        )
        if tier == "high":
            child = rules.Reaffirmation(
                id=rules.identity("child", source.id),
                session=source.id,
                actor=source.actor,
                tag=tag,
                event=event,
            )
            rules.put(state, child)
            game.request(
                c, action, int(source.actor.entity), "consume_child", dict(source_work=child.id)
            )
            action["data"]["consume"]["phase"] = "child"
        else:
            action["data"]["consume"]["phase"] = "effects"
        return
    if (
        kind != "consume_eat"
        or source.target is None
        or answer.options[0] not in dict(_eat_options(game, c, state, source))
        or set(answer.fields) - {"own_asset", "target_asset"}
    ):
        raise WorkflowError("Choose one actual available Eat outcome")
    option = answer.options[0]
    own_asset, target_asset = answer.fields.get("own_asset"), answer.fields.get("target_asset")
    work: tuple[str, ...] = ()
    own_cost = source.total < 8 or not source.vulnerable
    if own_cost:
        if own_asset not in {
            x["id"] for x in action["data"]["consume"]["sourcefacts"]["own_assets"]
        }:
            raise WorkflowError("Damage one of your actual available Assets")
        assert own_asset is not None
        changed, work = support.damage(game, c, state, source.actor, own_asset, event, source.id)
        _copy(state, changed)
    elif own_asset is not None:
        raise WorkflowError("This actual choice has no own Asset cost")
    custody = None
    if option == "bite":
        if target_asset not in {
            x["id"] for x in action["data"]["consume"]["sourcefacts"]["target_assets"]
        }:
            raise WorkflowError("Damage one actual target Asset")
        assert target_asset is not None
        changed, owed = support.damage(
            game, c, state, source.target, target_asset, event, source.id
        )
        _copy(state, changed)
        work += owed
        if not _sprite_work(game, c, state, work):
            feeding_before = GameState.model_validate_json(state.model_dump_json())
            rules.fed(state, source.actor, event, entire=False)
            work += support.stage_starvation_expiry(
                game, c, feeding_before, state, source.actor, event, source.id
            )
    elif option == "kill":
        rules.put(
            state,
            rules.Consumption(
                id=event,
                session=source.id,
                actor=source.actor,
                target=source.target,
                option="kill",
                own_asset=own_asset,
                event=event,
                choice=row["id"],
            ),
        )
        from girlframe.services.m3_sprite import defer

        changed, owed = defer(
            game,
            c,
            state,
            target=source.target,
            asset=None,
            source_action=source.id,
            source_work=None,
            event=event,
            opponent=source.actor,
            chooser=int(source.actor.entity),
            occurrence="consume_kill",
            effect="fatal",
        )
        if owed:
            _copy(state, changed)
            work += owed
        else:
            changed, owed = support.kill(
                game, c, state, source.actor, source.target, event, source.id
            )
            _copy(state, changed)
            work += owed
            feeding_before = GameState.model_validate_json(state.model_dump_json())
            rules.fed(state, source.actor, event, entire=True)
            work += support.stage_starvation_expiry(
                game, c, feeding_before, state, source.actor, event, source.id
            )
    elif option == "swallow":
        changed, custody, owed = support.swallow(
            game, c, state, source.actor, source.target, event, source.id
        )
        _copy(state, changed)
        work += owed
    elif option == "nibble":
        _copy(state, change(state, source.actor, source.target, 1, event))
        changed, owed = support.mouth(
            game, c, state, source.actor, source.target, event, source.id, held=True
        )
        _copy(state, changed)
        work += owed
        rules.put(
            state,
            rules.MouthHold(
                id=event,
                session=source.id,
                actor=source.actor,
                target=source.target,
                frame=source.frame,
                helpless=source.total >= 11,
                event=event,
            ),
        )
    else:
        changed, owed = support.escape(
            game, c, state, source.actor, source.target, event, source.id
        )
        _copy(state, changed)
        work += owed
    if option != "bite" and target_asset is not None:
        raise WorkflowError("Only the actual bite chooses a target Asset")
    rules.put(
        state,
        rules.Consumption(
            id=event,
            session=source.id,
            actor=source.actor,
            target=source.target,
            option=cast(Literal["bite", "kill", "swallow", "nibble", "repelled"], option),
            own_asset=own_asset,
            target_asset=target_asset,
            custody=custody,
            event=event,
            choice=row["id"],
        ),
    )
    rules.put(state, source.model_copy(update={"work": tuple(dict.fromkeys(work))}))
    action["data"]["consume"]["phase"] = "effects"
    if (
        option == "kill"
        and not _sprite_work(game, c, state, work)
        and rules.held(state, source.actor, rules.DRIVE)
    ):
        require_rule(game, c, state, source.actor, rules.DRIVE)
        game.request(c, action, int(source.actor.entity), "consume_erase")
        action["data"]["consume"]["phase"] = "erasure"


def _work_complete(game: GameService, c: Connection, work: tuple[str, ...]) -> bool:
    table = t.m3["m3_required_work"]
    for identity in work:
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Recover the actual immediate CONSUME effect work")
        if row["state"] == "pending":
            return False
    return True


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_consume_support import synchronize as synchronize_effects

    synchronize_effects(game, c, event)
    if (
        not action["data"].get("consume")
        or action["state"] in ("complete", "aborted")
        or game.pending(c, action["id"])
    ):
        return
    state = load_state(c, game.store.campaign_id)
    source = _source(game, c, state, action)
    if not _work_complete(game, c, source.work):
        return
    feeding = _feed_sprite_resolutions(game, c, state, action, event)
    if feeding != event:
        event = feeding
        _copy(state, load_state(c, game.store.campaign_id))
        current = game.action(c, action["id"])
        action.clear()
        action.update(current)
        if action["state"] in ("complete", "aborted"):
            return
    source = rules.session(state, action["id"])
    if not _work_complete(game, c, source.work) or game.pending(c, action["id"]):
        return
    from girlframe.services.m2_choices import ChoiceEngine

    if source.completed_event is None:
        completed = str(uuid4())
        rules.put(state, source.model_copy(update={"completed_event": completed}))
        actual_human = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if actual_human is None:
            raise WorkflowError(
                "Preserve the actual human source event completing this consequence"
            )
        game.event(
            c,
            int(actual_human),
            str(uuid4()),
            "m3.consume_completed",
            state,
            event_id=completed,
            action_id=source.id,
            source_event=event,
        )
    action["data"]["consume"]["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    table = t.m3["m3_required_work"]
    work = tuple(
        x
        for source in rules.records(state, rules.Partaking)
        if source.action == action["id"]
        for x in source.work
    )
    if action["data"].get("consume"):
        source = next(
            (x for x in rules.records(state, rules.Session) if x.id == action["id"]), None
        )
        work += source.work if source else ()
    for identity in work:
        row = c.execute(
            sa.select(table.c.state)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        ).first()
        if row is None or row.state == "pending":
            return True
    return any(
        x.action == action["id"] and (not x.completed_event or x.primary_waiting)
        for x in rules.records(state, rules.Opportunity)
    )


def _opportunity(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    kind: Literal["partake", "time_eat"],
    target: ActorRef | None,
    event: str,
) -> None:
    actor = acting(state, action)
    if actor is None or actor.kind != "pilot":
        return
    rule = rules.PARTAKE if kind == "partake" else rules.TIME
    if state.sheets[actor.entity].frame != "CONSUME" or rules.held(state, actor, rule) is None:
        return
    require_rule(game, c, state, actor, rule)
    if not action["data"].get("receipt"):
        raise WorkflowError("Use the actual committed Dive or targeted Play receipt")
    if kind == "partake" and action["data"]["play"] != "dive_deep":
        raise WorkflowError("Let Us Partake requires the actual Dive Deep source")
    if kind == "time_eat" and (target is None or action["data"]["result"].get("total", 0) < 8):
        return
    identity = rules.identity(kind, action["id"])
    if any(x.id == identity for x in rules.records(state, rules.Opportunity)):
        return
    rules.put(
        state,
        rules.Opportunity(
            id=identity, action=action["id"], actor=actor, target=target, kind=kind, event=event
        ),
    )
    game.request(c, action, int(actor.entity), "consume_" + kind)


def after_targeted_result(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    event: str,
) -> None:
    _opportunity(game, c, state, action, "time_eat", target, event)


def intercept_targeted_results(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("receipt") or action["data"].get("result", {}).get("total", 0) < 8:
        return False
    identity = rules.identity("time_eat", action["id"])
    existing = next((x for x in rules.records(state, rules.Opportunity) if x.id == identity), None)
    if existing is not None:
        if not existing.completed_event:
            return True
        if existing.primary_waiting:
            event = action["data"].get("response_event") or existing.completed_event
            rules.put(
                state,
                existing.model_copy(
                    update={"primary_waiting": False, "primary_resumed_event": event}
                ),
            )
            action["data"]["consume_time_primary_released"] = identity
        return False
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    actor = acting(state, action)
    if actor is None or actor.kind != "pilot":
        return False
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.frame != "CONSUME" or rules.held(state, actor, rules.TIME) is None:
        return False
    target = prepared.target_actor
    if target is None and prepared.target is not None:
        target = current_ref(state, prepared.target)
    if target is None:
        return False
    _, event = _raw_receipt(game, c, action)
    _opportunity(game, c, state, action, "time_eat", target, event)
    source = next(x for x in rules.records(state, rules.Opportunity) if x.id == identity)
    rules.put(state, source.model_copy(update={"primary_waiting": True}))
    return True


def offer_partake(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    _opportunity(game, c, state, action, "partake", None, event)


def _apply_opportunity(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services import m3_consume_support as support

    kind = "partake" if row["kind"] == "consume_partake" else "time_eat"
    source = next(
        x
        for x in rules.records(state, rules.Opportunity)
        if x.action == action["id"] and x.kind == kind
    )
    if (
        source.completed_event
        or int(row["actor_id"]) != int(source.actor.entity)
        or len(answer.options) != 1
        or answer.denied
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
        or not answer.text.strip()
    ):
        raise WorkflowError(
            "Only the original owner chooses the actual optional source consequence"
        )
    event, option = action["data"]["response_event"], answer.options[0]
    if option == "pass":
        if answer.fields:
            raise WorkflowError("A declined optional effect cannot supply mechanical changes")
    elif kind == "time_eat":
        if option != "give" or set(answer.fields) != {"identity"} or source.target is None:
            raise WorkflowError("Choose one actual unmarked Identity for the actual Just Meat Tag")
        require_rule(game, c, state, source.actor, rules.TIME)
        changed, _ = support.mark_identity(
            game, c, state, source.actor, answer.fields["identity"], event, source.action
        )
        _copy(state, changed)
        _copy(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                source.target,
                source.actor,
                "Just Meat",
                event,
                event,
                tuple(sorted(action["data"].get("table", ()) or {int(source.actor.entity)})),
            ),
        )
    else:
        require_rule(game, c, state, source.actor, rules.PARTAKE)
        if option not in ("regrow", "excrete", "appearance") or set(answer.fields) - {
            "girl_asset",
            "frame_assets",
            "new_asset",
            "appearance",
            "replace_frame",
            "regrow_replacements",
        }:
            raise WorkflowError("Choose one actual printed Let Us Partake effect")
        supplied = (
            SuppliedAsset.model_validate_json(answer.fields["new_asset"])
            if answer.fields.get("new_asset")
            else None
        )
        frames = tuple(json.loads(answer.fields.get("frame_assets", "[]")))
        if any(not isinstance(x, str) for x in frames) or len(set(frames)) != len(frames):
            raise WorkflowError("Select distinct actual Frame Assets")
        replacements = json.loads(answer.fields.get("regrow_replacements", "{}"))
        if not isinstance(replacements, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in replacements.items()
        ):
            raise WorkflowError("Choose actual source-matched Frame cap replacements")
        changed, work = support.partake(
            game,
            c,
            state,
            source.actor,
            event,
            source.action,
            option=option,
            girl_asset=answer.fields.get("girl_asset", ""),
            frame_assets=frames,
            new_asset=supplied,
            appearance=answer.fields.get("appearance", ""),
            replace_frame=answer.fields.get("replace_frame"),
            regrow_replacements=replacements,
        )
        _copy(state, changed)
        rules.put(
            state,
            rules.Partaking(
                id=event,
                action=source.action,
                actor=source.actor,
                option=cast(Literal["regrow", "excrete", "appearance"], option),
                girl_asset=answer.fields.get("girl_asset", ""),
                frame_assets=frames,
                appearance=answer.fields.get("appearance", ""),
                event=event,
                work=work,
                replaced_frame=answer.fields.get("replace_frame"),
                regrow_replacements=replacements,
            ),
        )
    rules.put(state, source.model_copy(update={"completed_event": event}))
    if source.kind == "time_eat" and source.primary_waiting:
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).results(c, state, action)


def _child(state: GameState, identity: str) -> rules.Reaffirmation | rules.OrderPursuit:
    reaffirmation = next(
        (x for x in rules.records(state, rules.Reaffirmation) if x.id == identity), None
    )
    if reaffirmation is not None:
        return reaffirmation
    pursuit = next((x for x in rules.records(state, rules.OrderPursuit) if x.id == identity), None)
    if pursuit is None:
        raise WorkflowError("Recover the actual original required CONSUME performance")
    return pursuit


def prepare_child(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    known = {x.id for x in rules.records(state, rules.Reaffirmation)} | {
        x.id for x in rules.records(state, rules.OrderPursuit)
    }
    if not prepared.source_work or prepared.source_work not in known:
        return None
    child = _child(state, prepared.source_work)
    pursuit = isinstance(child, rules.OrderPursuit)
    parent_id = child.parent if isinstance(child, rules.OrderPursuit) else child.session
    parent = game.action(c, parent_id)
    scene = (
        child.scene
        if isinstance(child, rules.OrderPursuit)
        else _source(game, c, state, parent).cast
    )
    current = _cast(game, c, state, channel)
    if (
        child.completed_event
        or child.action
        or viewer.user_id != int(child.actor.entity)
        or channel != int(parent["channel_id"])
        or prepared.parent not in (None, parent_id)
        or not rules.tag(state, child.actor, child.tag)
        or not prepared.context.strip()
        or not prepared.trigger_confirmed
        or fingerprint(scene) != fingerprint(current)
    ):
        raise WorkflowError("Perform the original genuine Tag/hunger source in its real scene")
    kind = "consume_order_child" if pursuit else "consume_child"
    row = next(
        (
            x
            for x in game.pending(c, parent_id)
            if x["kind"] == kind and x["actor_id"] == child.actor.entity
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Recover the original exact pending source-performance row")
    return dict(
        id=child.id,
        kind="order" if pursuit else "reaffirm",
        parent=parent_id,
        choice=row["id"],
        actor=child.actor.model_dump(mode="json"),
        tag=child.tag,
        hunger=isinstance(child, rules.OrderPursuit) and child.mode == "hunger",
        cast=current.model_dump(mode="json"),
        cast_sha256=fingerprint(current),
        table=sorted(
            {x.controller for x in current.roles}
            | ({current.facilitator} if current.facilitator is not None else set())
        ),
    )


def bind_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    child = _child(state, action["data"]["consume_child"]["id"])
    if child.action or child.completed_event:
        raise WorkflowError("Resume the actual already-bound source performance")
    rules.put(state, child.model_copy(update={"action": action["id"]}))


def release_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("consume_child")
    if meta is None:
        return
    child = _child(state, meta["id"])
    if (
        child.action != action["id"]
        or child.completed_event
        or action["data"].get("receipt")
        or c.scalar(
            sa.select(t.m2["m2_receipts"].c.action_id).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
    ):
        raise WorkflowError(
            "Release only the original genuinely unrolled cancelled child reservation"
        )
    rules.put(state, child.model_copy(update={"action": None}))


def complete_child(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("consume_child")
    if meta is None:
        return
    child = _child(state, meta["id"])
    if child.completed_event:
        return
    actual_event = c.execute(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if (
        child.action != action["id"]
        or action["state"] != "complete"
        or not action["data"].get("receipt")
        or not action["data"].get("result")
        or actual_event is None
    ):
        raise WorkflowError("Commit the actual completed child Play and all its real effects first")
    completed = str(uuid4())
    rules.put(state, child.model_copy(update={"completed_event": completed}))
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.id == meta["choice"], choices.c.campaign_id == game.store.campaign_id
            )
        )
        .mappings()
        .one()
    )
    expected = "consume_order_child" if isinstance(child, rules.OrderPursuit) else "consume_child"
    if row["actor_id"] != child.actor.entity or row["kind"] != expected:
        raise WorkflowError("Preserve the original actual source row and its author")
    c.execute(
        choices.update()
        .where(choices.c.id == row["id"], choices.c.campaign_id == game.store.campaign_id)
        .values(state="completed_by_work", revision=row["revision"] + 1)
    )
    parent_id = child.parent if isinstance(child, rules.OrderPursuit) else child.session
    parent = game.action(c, parent_id)
    if isinstance(child, rules.OrderPursuit):
        orders = t.m2["m2_orders"]
        c.execute(
            orders.update()
            .where(
                orders.c.id == child.order,
                orders.c.campaign_id == game.store.campaign_id,
                orders.c.target_id == child.actor.entity,
            )
            .values(state="consume_followed")
        )
        parent["data"].setdefault("result", {}).update(
            response="consume_follow", not_disobedience=True, pursuit_action=action["id"]
        )
    else:
        parent["data"]["consume"]["phase"] = "effects"
    game.event(
        c,
        int(actual_event.actor_id),
        str(uuid4()),
        "m3.consume_child_completed",
        state,
        event_id=completed,
        action_id=parent_id,
        child_action=action["id"],
        source_event=event,
    )
    game.save_action(c, parent)
    if isinstance(child, rules.OrderPursuit):
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).finish(c, state, parent)
        game.save_action(c, parent)
    else:
        synchronize(game, c, parent, completed)


def stage_link(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    original_frame: str,
    event: str,
) -> None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.frame != "CONSUME":
        return
    require_rule(game, c, state, actor, rules.STARVATION)
    actual = _native(game, c, state, actor)
    if rules.frame(state, actor) != original_frame or not actual.inside_frame:
        raise WorkflowError("Prove the actual completed link to this original physical Frame")
    rules.increase(state, actor, actor, "link", event)


def stage_helpless(
    game: GameService,
    c: Connection,
    before: GameState,
    state: GameState,
    subject: ActorRef,
    event: str,
    *,
    channel: int | None = None,
) -> None:
    if is_helpless(before, subject) or not is_helpless(state, subject):
        return
    bound = profiles(c, game.store.campaign_id)
    target = resolve(state, subject, bound, require_alive=False, require_current_profile=False)
    if not target.alive:
        return
    for uid in state.order:
        sheet = state.sheets[str(uid)]
        if sheet.frame != "CONSUME":
            continue
        actor = current_ref(state, uid)
        own = _native(game, c, state, actor)
        if subject != actor:
            if own.cell is None or target.cell is None or own.cell != target.cell:
                continue
            if channel is None:
                raise WorkflowError(
                    "CONSUME_PROXIMITY_SOURCE_REQUIRED: prove the actual nearby source scene"
                )
            cast = _cast(game, c, state, channel)
            if not all(any(x.actor == ref for x in cast.roles) for ref in (actor, subject)):
                raise WorkflowError(
                    "CONSUME_PROXIMITY_SOURCE_REQUIRED: actual nearby source roles are missing"
                )
        require_rule(game, c, state, actor, rules.STARVATION)
        rules.increase(state, actor, subject, "helpless", event)


def sensor_question(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> str | None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.frame != "CONSUME" or rules.held(state, actor, rules.HOUND) is None:
        return None
    require_rule(game, c, state, actor, rules.HOUND)
    return "What can I smell?"


def starvation_source(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    marker: ActorRef,
    scene: SceneCast,
) -> dict[str, Any] | None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.frame != "CONSUME":
        return None
    require_rule(game, c, state, actor, rules.STARVATION)
    if not all(any(x.actor == ref for x in scene.roles) for ref in (actor, marker)):
        return None
    level = rules.hunger(state, actor)
    identity = rules.identity("starvation-mark", rules.frame(state, actor), scene.id)
    if (level == "Quiet" and marker != actor) or any(
        x.id == identity for x in rules.records(state, rules.StarvationMark)
    ):
        return None
    return dict(
        id=identity,
        label=level,
        amount=-1,
        actor=actor.model_dump(mode="json"),
        marker=marker.model_dump(mode="json"),
        scene=scene.id,
    )


def mark_starvation(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    marker: ActorRef,
    scene: SceneCast,
    event: str,
) -> int:
    source = starvation_source(game, c, state, actor, marker, scene)
    if source is None:
        raise WorkflowError("Use only the actual current starvation source once in this scene")
    rules.put(
        state,
        rules.StarvationMark(
            id=source["id"],
            actor=actor,
            marker=marker,
            frame=rules.frame(state, actor),
            scene=scene.id,
            level=rules.hunger(state, actor),
            event=event,
        ),
    )
    return -1


def follows_feral(state: GameState, actor: ActorRef, tag: str) -> bool:
    return any(
        x.tag == tag and x.tier in ("mid", "high") for x in rules.feral_effects(state, actor)
    )


def _prove_feral(
    game: GameService, c: Connection, state: GameState, effect: rules.FeralEffect
) -> None:
    from girlframe.services.m3_consume_support import prove_session

    saved = _history(c, game, effect.event)
    if (
        effect not in rules.records(saved, rules.FeralEffect)
        or rules.tag(saved, effect.actor, effect.tag) is None
        or prove_session(game, c, saved, effect.session).play != "consume_feral"
    ):
        raise WorkflowError("Recover the original actual Feral Tag and committed source")


def _raw_receipt(
    game: GameService, c: Connection, action: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    table = t.m2["m2_receipts"]
    row = c.execute(
        sa.select(table.c.body_json, table.c.id).where(
            table.c.campaign_id == game.store.campaign_id, table.c.action_id == action["id"]
        )
    ).one()
    raw = json.loads(row.body_json)
    if raw != action["data"].get("receipt"):
        raise WorkflowError("Preserve the actual unaltered source receipt")
    event = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == str(action["actor_id"]),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == row.id,
        )
    )
    if event is None:
        raise WorkflowError("Recover the actual original canonical roll event")
    return raw, event


def apply_disobey_limit(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if action["data"].get("play") != "disobey_orders":
        return False
    if action["data"].get("consume_disobey_limit"):
        return prove_disobey_limit(game, c, state, action) is not None
    actor = acting(state, action)
    if actor is None or actor.kind != "pilot":
        return False
    effect = next((x for x in rules.feral_effects(state, actor) if x.tier == "low"), None)
    if effect is None:
        return False
    _prove_feral(game, c, state, effect)
    raw, event = _raw_receipt(game, c, action)
    total = raw["pre_total"] + sum(x["amount"] for x in action["data"].get("modifiers", ()))
    if action["data"]["result"]["total"] != total:
        raise WorkflowError("Apply the Feral limit only after the actual final Tag total")
    cap = min(total, 7)
    action["data"]["consume_disobey_limit"] = dict(
        feral=effect.id,
        source_event=effect.event,
        actor=actor.model_dump(mode="json"),
        tag=effect.tag,
        event=event,
        receipt=json.dumps(raw, sort_keys=True),
        uncapped=total,
        cap=cap,
    )
    action["data"]["result"].update(total=cap, tier="low")
    return True


def prove_disobey_limit(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    value = action["data"].get("consume_disobey_limit")
    if value is None:
        return None
    raw, event = _raw_receipt(game, c, action)
    actor = ActorRef.model_validate(value["actor"])
    effect = next(
        (x for x in rules.records(state, rules.FeralEffect) if x.id == value["feral"]), None
    )
    uncapped = raw["pre_total"] + sum(x["amount"] for x in action["data"].get("modifiers", ()))
    if (
        action["data"]["play"] != "disobey_orders"
        or effect is None
        or effect.actor != actor
        or actor.entity != action["actor_id"]
        or effect.tier != "low"
        or effect.tag != value["tag"]
        or effect.event != value["source_event"]
        or event != value["event"]
        or json.dumps(raw, sort_keys=True) != value["receipt"]
        or uncapped != value["uncapped"]
        or value["cap"] != min(uncapped, 7)
    ):
        raise WorkflowError(
            "Preserve the exact original low Feral source, actor, receipt and effective cap"
        )
    _prove_feral(game, c, state, effect)
    return int(value["cap"])


def begin_order_pursuit(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> None:
    if (
        answer.options != ("consume_follow",)
        or set(answer.fields) != {"consume_tag", "consume_follow"}
        or answer.fields["consume_follow"] not in ("tag", "hunger")
        or not answer.text.strip()
        or answer.denied
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError(
            "Declare the actual source-bound Tag or hunger pursuit, then really perform it"
        )
    order = (
        c.execute(
            sa.select(t.m2["m2_orders"]).where(
                t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_orders"].c.id == action["data"].get("order_id"),
            )
        )
        .mappings()
        .first()
    )
    if order is None:
        raise WorkflowError("Recover the actual original Order source")
    actor = current_ref(state, int(order["target_id"]))
    effect = next(
        (
            x
            for x in rules.feral_effects(state, actor)
            if x.tag == answer.fields["consume_tag"] and x.tier in ("mid", "high")
        ),
        None,
    )
    if (
        effect is None
        or order["channel_id"] != str(action["channel_id"])
        or action["state"] in ("complete", "aborted")
    ):
        raise WorkflowError("Use the actual original outstanding Order and active Feral Tag")
    _prove_feral(game, c, state, effect)
    scene = _cast(game, c, state, int(action["channel_id"]))
    identity = rules.identity("order-pursuit", action["id"])
    game.request(c, action, int(actor.entity), "consume_order_child", dict(source_work=identity))
    pending = next(x for x in game.pending(c, action["id"]) if x["kind"] == "consume_order_child")
    rules.put(
        state,
        rules.OrderPursuit(
            id=identity,
            actor=actor,
            feral=effect.id,
            tag=effect.tag,
            order=order["id"],
            parent=action["id"],
            scene=scene,
            mode=cast(Literal["tag", "hunger"], answer.fields["consume_follow"]),
            event=event,
            choice=pending["id"],
        ),
    )
    action["data"].update(consume_order_pursuit=identity, consume_order_account=answer.text.strip())
    action["data"].setdefault("result", {})["response"] = "consume_follow_pending"


def resume_pending(game: GameService, c: Connection, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    actions = {x.id for x in rules.records(state, rules.Session) if not x.completed_event} | {
        x.action for x in rules.records(state, rules.Partaking)
    }
    for identity in actions:
        action = game.action(c, identity)
        if (
            action["state"] in ("complete", "aborted")
            or game.pending(c, identity)
            or intercept_finish(game, c, state, action)
        ):
            continue
        if action["data"].get("consume"):
            synchronize(game, c, action, event)
        else:
            from girlframe.services.m2_choices import ChoiceEngine

            ChoiceEngine(game).finish(c, state, action)
            game.save_action(c, action)


class ConsumeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            own = _native(self.game, c, state, actor)
            cast = _cast(self.game, c, state, channel)
            from girlframe.services import m3_consume_support as support

            targets = []
            for role in cast.roles:
                if role.actor == actor:
                    continue
                try:
                    support.context(self.game, c, state, actor, role.actor, cast)
                    targets.append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            token=role.actor.token,
                            label=resolve(
                                state, role.actor, profiles(c, self.store.campaign_id)
                            ).label,
                        )
                    )
                except (ValueError, WorkflowError):
                    continue
            return dict(
                revision=state.revision,
                sheet_revision=state.sheets[actor.entity].revision,
                actor=actor.model_dump(mode="json"),
                source_sha256=own.source_sha256,
                hunger=rules.hunger(state, actor),
                heat=state.sheets[actor.entity].heat,
                identities=[
                    (x.id, x.name) for x in state.sheets[actor.entity].identities if not x.marked
                ],
                targets=targets,
                legal_targets=[
                    dict(
                        ref=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        label=resolve(state, x.actor, profiles(c, self.store.campaign_id)).label,
                    )
                    for x in cast.roles
                    if x.actor != active_handler(state) and not same_handler_body(state, x.actor)
                ],
                requisitions=[
                    dict(id=rule, held=rules.held(state, actor, rule) is not None)
                    for rule in rules.REQUISITIONS
                ],
                plays=[("consume_eat", "Eat")]
                + ([("consume_feral", "Feral")] if rules.held(state, actor, rules.FERAL) else []),
            )

    def purchase(
        self,
        viewer: GuildViewer,
        key: str,
        expected: str,
        rule: str,
        account: str,
        *,
        hierarchy: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            scope = Access(self.store)
            scope.authorize(c, viewer, "economy")
            assert scope.registry is not None
            scope.registry.require_available(rule)
            if rule not in rules.REQUISITIONS:
                raise WorkflowError("Choose an actual printed CONSUME Requisition")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            own = _native(self.game, c, state, actor)
            if own.source_sha256 != expected or not account.strip():
                raise WorkflowError("Reopen the actual original Frame and voluntary acquisition")
            if rule != rules.FORMS and (hierarchy is not None or rules.held(state, actor, rule)):
                raise WorkflowError(
                    "Restore the actual existing Requisition rather than acquiring it twice"
                )
            request = None
            if rule == rules.FORMS:
                request = next(
                    (x for x in rules.records(state, rules.PermitRequest) if x.id == hierarchy),
                    None,
                )
                if (
                    request is None
                    or request.actor != actor
                    or request.frame != rules.frame(state, actor)
                    or request.handler != active_handler(state)
                    or request.superior is not False
                    or not request.review_event
                    or request.receipt
                ):
                    raise WorkflowError(
                        "CANNIBAL_HIERARCHY_SOURCE_REQUIRED: use the actual original "
                        "Handler-authored target fact"
                    )
                reviewed = _history(c, self.game, request.review_event)
                saved = next(
                    (x for x in rules.records(reviewed, rules.PermitRequest) if x.id == request.id),
                    None,
                )
                source = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.id == request.review_event,
                        )
                    )
                    .mappings()
                    .one()
                )
                if (
                    saved != request
                    or source["kind"] != "m3.consume_hierarchy_reviewed"
                    or int(source["actor_id"]) != request.handler_controller
                ):
                    raise WorkflowError(
                        "Recover the actual original Handler's factual hierarchy review"
                    )
            if available(state, actor) < 2:
                raise WorkflowError("This actual native Frame Requisition costs two Permissions")
            identity, event = str(uuid4()), str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, 2, "CONSUME")
            debit(state, actor, 2, event=event, source=identity, payment=payment)
            state.sheets[actor.entity].revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock",
                    actor=actor,
                    frame_instance=rules.frame(state, actor),
                    frame="CONSUME",
                    donor_frame="CONSUME",
                    rule_id=rule,
                    grant="consume:" + identity,
                    price=2,
                    account=account.strip(),
                    source_event=event,
                )
            )
            if request is not None:
                rules.put(
                    state,
                    rules.CannibalPermit(
                        id=identity,
                        receipt=identity,
                        actor=actor,
                        frame=request.frame,
                        target=request.target,
                        handler=request.handler,
                        event=event,
                    ),
                )
                rules.put(
                    state,
                    request.model_copy(update={"receipt": identity, "completed_event": event}),
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ability_unlock_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rule,
                cost=2,
            )
            return dict(id=identity, rule=rule, cost=2)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.consume_rule_purchased",
                dict(expected=expected, rule=rule, account=account, hierarchy=hierarchy),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose_permit(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        target: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            authorize(self.game, c, viewer)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            _native(self.game, c, state, actor)
            cast = _cast(self.game, c, state, channel)
            handler = active_handler(state)
            if (
                revision != state.revision
                or handler is None
                or target == handler
                or same_handler_body(state, target)
                or not account.strip()
                or not any(x.actor == target for x in cast.roles)
            ):
                raise WorkflowError(
                    "Select an actual source target other than the original Handler"
                )
            resolve(state, target, profiles(c, self.store.campaign_id))
            identity, event = str(uuid4()), str(uuid4())
            assert state.handler is not None
            rules.put(
                state,
                rules.PermitRequest(
                    id=identity,
                    actor=actor,
                    frame=rules.frame(state, actor),
                    target=target,
                    handler=handler,
                    handler_controller=state.handler,
                    event=event,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.consume_hierarchy_requested",
                state,
                event_id=event,
                request_id=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.consume_hierarchy_requested",
            dict(
                channel=channel,
                revision=revision,
                target=target.model_dump(mode="json"),
                account=account,
            ),
            operation,
            auto_audit=False,
        )

    def review_permit(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        superior: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            authorize(self.game, c, viewer)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = next(x for x in rules.records(state, rules.PermitRequest) if x.id == identity)
            if (
                state.revision != revision
                or viewer.user_id != source.handler_controller
                or active_handler(state) != source.handler
                or source.review_event
                or type(superior) is not bool
                or not account.strip()
            ):
                raise WorkflowError(
                    "The actual original Handler factually adjudicates this target's hierarchy"
                )
            event = str(uuid4())
            rules.put(
                state, source.model_copy(update={"superior": superior, "review_event": event})
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.consume_hierarchy_reviewed",
                state,
                event_id=event,
                request_id=identity,
            )
            return dict(id=identity, superior=superior)

        return self.store._write(
            viewer,
            key,
            "m3.consume_hierarchy_reviewed",
            dict(id=identity, revision=revision, superior=superior, account=account),
            operation,
            auto_audit=False,
        )

    def release_mouth(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        from girlframe.services import m3_consume_support as support

        def operation(c: Connection) -> dict[str, Any]:
            self.game.authorize(c, viewer, game=False)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = next(x for x in rules.records(state, rules.MouthHold) if x.id == identity)
            if state.revision != revision or source.ended_event or not account.strip():
                raise WorkflowError("Reopen the actual current held body part")
            bound = profiles(c, self.store.campaign_id)
            if viewer.user_id not in {
                resolve(
                    state, ref, bound, require_alive=False, require_current_profile=False
                ).controller
                for ref in (source.actor, source.target)
            }:
                raise WorkflowError(
                    "Only an actual original participant records the real physical ending"
                )
            event = str(uuid4())
            changed, work = support.mouth(
                self.game, c, state, source.actor, source.target, event, source.session, held=False
            )
            if work:
                raise WorkflowError(
                    "Resolve the actual held body-part ending through its immediate source work"
                )
            rules.put(changed, source.model_copy(update={"ended_event": event}))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.consume_mouth_ended",
                changed,
                event_id=event,
                hold_id=identity,
            )
            return dict(id=identity, ended=True)

        return self.store._write(
            viewer,
            key,
            "m3.consume_mouth_ended",
            dict(id=identity, revision=revision, account=account),
            operation,
            auto_audit=False,
        )

    def rip_out(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        from girlframe.services import m3_consume_support as support

        def operation(c: Connection) -> dict[str, Any]:
            self.game.authorize(c, viewer, game=False)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = next(x for x in rules.records(state, rules.Consumption) if x.id == identity)
            session = rules.session(state, source.session)
            actual = resolve(
                state,
                source.target,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                state.revision != revision
                or actual.controller != viewer.user_id
                or source.option != "swallow"
                or session.vulnerable
                or source.custody is None
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only the actual nonvulnerable swallowed person may rip their way out"
                )
            event = str(uuid4())
            changed, work = support.escape(
                self.game,
                c,
                state,
                source.actor,
                source.target,
                event,
                source.session,
                custody=source.custody,
            )
            rules.put(changed, source.model_copy(update={"escaped_event": event}))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.consume_ripped_out",
                changed,
                event_id=event,
                consumption_id=identity,
            )
            return dict(id=identity, escaped=True, work=list(work))

        return self.store._write(
            viewer,
            key,
            "m3.consume_ripped_out",
            dict(id=identity, revision=revision, account=account),
            operation,
            auto_audit=False,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            regrowth = next(
                (
                    value
                    for value in rules.records(state, rules.RegrownFrame)
                    if value.id == identity
                ),
                None,
            )
            if regrowth is not None:
                if viewer.user_id != int(regrowth.actor.entity):
                    raise WorkflowError(
                        "Only the original source owner reads this regrowth history"
                    )
                from girlframe.services.m3_consume_regrowth import prove_regrowth

                proved = prove_regrowth(self.game, c, state, identity)
                return dict(
                    id=identity,
                    type="regrowth",
                    revision=state.revision,
                    source=proved.model_dump(mode="json"),
                )
            permit = next(
                (x for x in rules.records(state, rules.PermitRequest) if x.id == identity), None
            )
            if permit is not None:
                if viewer.user_id not in (int(permit.actor.entity), permit.handler_controller):
                    raise WorkflowError("This actual legal-target source is addressed privately")
                return dict(
                    id=identity,
                    type="permit",
                    revision=state.revision,
                    source=permit.model_dump(mode="json"),
                    own=viewer.user_id == int(permit.actor.entity),
                )
            hold = next(
                (x for x in rules.records(state, rules.MouthHold) if x.id == identity), None
            )
            if hold:
                bound = profiles(c, self.store.campaign_id)
                if viewer.user_id not in {
                    resolve(
                        state, ref, bound, require_alive=False, require_current_profile=False
                    ).controller
                    for ref in (hold.actor, hold.target)
                }:
                    raise WorkflowError(
                        "This actual physical hold belongs to its original participants"
                    )
                return dict(
                    id=identity,
                    type="mouth",
                    revision=state.revision,
                    source=hold.model_dump(mode="json"),
                )
            consumed = next(
                (x for x in rules.records(state, rules.Consumption) if x.id == identity), None
            )
            if consumed:
                bound = profiles(c, self.store.campaign_id)
                if viewer.user_id not in {
                    resolve(
                        state, ref, bound, require_alive=False, require_current_profile=False
                    ).controller
                    for ref in (consumed.actor, consumed.target)
                }:
                    raise WorkflowError(
                        "This actual consumption belongs to its original participants"
                    )
                return dict(
                    id=identity,
                    type="consumption",
                    revision=state.revision,
                    source=consumed.model_dump(mode="json"),
                    pending_sprite=_pending_sprite(
                        game=self.game, c=c, state=state, session=consumed.session
                    ),
                    resolution=next(
                        (
                            prove_resolution(self.game, c, state, x.id).model_dump(mode="json")
                            for x in rules.records(state, rules.ConsumptionResolution)
                            if x.consumption == consumed.id
                        ),
                        None,
                    ),
                    vulnerable=rules.session(state, consumed.session).vulnerable,
                )
            raise WorkflowError("Recover the actual saved source-owned CONSUME history")

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return _tasks(self.game, c, load_state(c, self.store.campaign_id), viewer)


def _tasks(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for source in rules.records(state, rules.PermitRequest):
        if viewer.user_id not in (int(source.actor.entity), source.handler_controller):
            continue
        pending = not source.completed_event and source.superior is not True
        actionable = pending and (
            (source.review_event is None and viewer.user_id == source.handler_controller)
            or (source.superior is False and viewer.user_id == int(source.actor.entity))
        )
        tasks.append(
            dict(
                id=source.id,
                revision=state.revision,
                label="Actual Cannibal target and hierarchy",
                phase="pending" if pending else "resolved",
                pending=actionable,
            )
        )
    bound = profiles(c, game.store.campaign_id)
    for hold in rules.records(state, rules.MouthHold):
        owners = {
            resolve(
                state, ref, bound, require_alive=False, require_current_profile=False
            ).controller
            for ref in (hold.actor, hold.target)
        }
        if viewer.user_id in owners:
            tasks.append(
                dict(
                    id=hold.id,
                    revision=state.revision,
                    label="Actual body part held in CONSUME's mouth",
                    phase="resolved" if hold.ended_event else "pending",
                    pending=not hold.ended_event,
                )
            )
    for consumed in rules.records(state, rules.Consumption):
        if consumed.option != "swallow":
            continue
        owner = resolve(
            state, consumed.target, bound, require_alive=False, require_current_profile=False
        ).controller
        if viewer.user_id in (owner, int(consumed.actor.entity)):
            tasks.append(
                dict(
                    id=consumed.id,
                    revision=state.revision,
                    label="Actual swallowed prisoner",
                    phase="pending" if not consumed.escaped_event else "resolved",
                    pending=not consumed.escaped_event
                    and viewer.user_id == owner
                    and not rules.session(state, consumed.session).vulnerable,
                )
            )
    tasks.extend(
        dict(
            id=value.id,
            revision=state.revision,
            label="Actual regrown Frame component",
            phase="resolved",
            pending=False,
        )
        for value in rules.records(state, rules.RegrownFrame)
        if viewer.user_id == int(value.actor.entity)
    )
    return tasks


def _sprite_work(game: GameService, c: Connection, state: GameState, work: tuple[str, ...]) -> bool:
    from girlframe.engine.m3_battle_state import Required

    return any(
        x.get("kind") == "battle_damage_stage"
        and x.get("id") in work
        and Required.model_validate_json(x["requirement"]).kind == "sprite_intercept"
        for x in state.facts
        if "requirement" in x
    )


def consume_sprite_source(
    game: GameService, c: Connection, state: GameState, action_id: str, work_id: str
) -> tuple[rules.Session, rules.Consumption, Blow]:
    from girlframe.engine.m3_sprite import consume_effect
    from girlframe.services.m3_consume_support import prove_session
    from girlframe.services.m3_sprite import SpriteService

    source = prove_session(game, c, state, action_id)
    actual = game.action(c, action_id)
    _raw_receipt(game, c, actual)
    consumed = next(
        (
            x
            for x in rules.records(state, rules.Consumption)
            if x.session == action_id and x.option in ("bite", "kill")
        ),
        None,
    )
    _, blow = SpriteService(game.store)._proof(c, work_id)
    if (
        consumed is None
        or source.play != "consume_eat"
        or source.total < 8
        or work_id not in source.work
        or blow.source_action != action_id
        or blow.source_event != consumed.event
        or blow.target != source.target
        or consumed.target != source.target
        or consumed.actor != source.actor
        or blow.opponent != source.actor
        or blow.chooser != int(source.actor.entity)
        or consume_effect(blow) != consumed.option
        or blow.asset
        != (
            consumed.target_asset
            if consumed.option == "bite" and consumed.target_asset != "source-body-consequence"
            else None
        )
        or consumed not in rules.records(_history(c, game, consumed.event), rules.Consumption)
    ):
        raise WorkflowError("Prove the exact original Eat choice, target and real Sprite work")
    choice = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == consumed.choice,
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == consumed.choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        choice is None
        or response is None
        or choice["kind"] != "consume_eat"
        or choice["action_id"] != action_id
        or choice["actor_id"] != source.actor.entity
        or response["actor_id"] != source.actor.entity
        or response["event_id"] != consumed.event
        or ChoiceAnswer.model_validate_json(response["answer_json"]).options != (consumed.option,)
    ):
        raise WorkflowError(
            "Preserve the actual original human's canonical killing/biting response"
        )
    return source, consumed, blow


def _sprite_recipient(
    game: GameService, c: Connection, state: GameState, work_id: str, blow: Blow
) -> tuple[ActorRef, str | None]:
    from girlframe.services.m3_sprite import SpriteService

    row, _ = SpriteService(game.store)._proof(c, work_id)
    decisions = json.loads(row["body_json"])["decisions"]
    selected: list[tuple[ActorRef, str]] = []
    for owner, decision in decisions.items():
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == decision["event"],
                )
            )
            .mappings()
            .first()
        )
        saved = _history(c, game, decision["event"])
        fact = next(
            (
                x
                for x in saved.facts
                if x.get("kind") == "sprite_opportunity_answered"
                and x.get("id") == work_id
                and x.get("controller") == owner
                and x.get("event") == decision["event"]
            ),
            None,
        )
        if (
            audit is None
            or audit["kind"] != "m3.sprite_opportunity_answered"
            or audit["actor_id"] != owner
            or fact is None
            or json.loads(audit["payload_json"]).get("source_work") != work_id
        ):
            raise WorkflowError("Prove each actual Sprite controller's original optional response")
        if decision["choice"] == "intercept":
            ref = ActorRef.model_validate_json(fact["sprite"])
            if not any(
                x.actor == ref and x.controller == int(owner) and fact["asset"] in x.assets
                for x in blow.candidates
            ):
                raise WorkflowError("Only the genuine originally offered Sprite pays its own Asset")
            selected.append((ref, fact["asset"]))
        elif decision["choice"] != "pass" or fact["sprite"] or fact["asset"]:
            raise WorkflowError("Preserve the actual optional leap or pass")
    if len(selected) == 1:
        return selected[0]
    if selected or set(decisions) != {str(x.controller) for x in blow.candidates}:
        raise WorkflowError(
            "Wait for the original actual controllers to decline or pay one interception"
        )
    return blow.target, blow.asset


def resolve_sprite(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    action_id: str,
    work_id: str,
    recipient: ActorRef | None,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    source, consumed, blow = consume_sprite_source(game, c, state, action_id, work_id)
    expected, _ = _sprite_recipient(game, c, state, work_id, blow)
    if recipient != expected or any(
        x.work == work_id for x in rules.records(state, rules.ConsumptionResolution)
    ):
        raise WorkflowError(
            "Resolve this actual recipient and feeding source once, without retargeting"
        )
    entire = consumed.option == "kill" and recipient == consumed.target
    resolution = rules.ConsumptionResolution(
        id=rules.identity("sprite-resolution", work_id),
        session=source.id,
        consumption=consumed.id,
        original_target=consumed.target,
        recipient=expected,
        option="kill" if entire else "bite",
        work=work_id,
        event=event,
    )
    rules.put(state, resolution)
    followups: tuple[str, ...] = ()
    if entire:
        from girlframe.services.m3_consume_support import kill

        state, followups = kill(game, c, state, source.actor, consumed.target, event, action_id)
    return state, followups


def prove_resolution(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.ConsumptionResolution:
    from girlframe.engine.m3_battle import original_ended
    from girlframe.engine.m3_battle_state import Required

    value = next(
        (x for x in rules.records(state, rules.ConsumptionResolution) if x.id == identity), None
    )
    if value is None:
        raise WorkflowError("Recover the real original Sprite/CONSUME resolution")
    source, consumed, blow = consume_sprite_source(game, c, state, value.session, value.work)
    born = _history(c, game, value.event)
    original = next(
        (x for x in rules.records(born, rules.ConsumptionResolution) if x.id == identity), None
    )
    actual, asset = _sprite_recipient(game, c, born, value.work, blow)
    result = next(
        (
            x
            for x in born.facts
            if x.get("kind") == "sprite_blow_resolved"
            and x.get("id") == value.work
            and x.get("event") == value.event
        ),
        None,
    )
    entire = consumed.option == "kill" and actual == consumed.target
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.event,
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    cause = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == payload.get("source_event"),
            )
        )
        .mappings()
        .first()
    )
    from girlframe.services.m3_sprite import SpriteService

    row, _ = SpriteService(game.store)._proof(c, value.work)
    decisions = json.loads(row["body_json"])["decisions"]
    if (
        audit is None
        or audit["kind"] != "m3.sprite_blow_resolved"
        or payload.get("source_work") != value.work
        or cause is None
        or cause["kind"] != "m3.sprite_opportunity_answered"
        or audit["actor_id"] != cause["actor_id"]
        or payload.get("source_event") not in {x["event"] for x in decisions.values()}
    ):
        raise WorkflowError("Prove the actual Sprite application and real deciding human")
    if (
        original is None
        or original.model_dump(exclude={"feeding_event"})
        != value.model_dump(exclude={"feeding_event"})
        or value.original_target != consumed.target
        or value.recipient != actual
        or value.consumption != consumed.id
        or value.option != ("kill" if entire else "bite")
        or result is None
        or result["original"] != consumed.target.model_dump_json()
        or result["intercepted"] != (actual.model_dump_json() if actual != consumed.target else "")
    ):
        raise WorkflowError("Preserve intended target, actual paid recipient and genuine outcome")
    if entire:
        if not original_ended(born, actual):
            raise WorkflowError(
                "Entire consumption must use the actual original body's genuine ending"
            )
    elif asset is not None:
        actual_body = resolve(
            born,
            actual,
            profiles(c, game.store.campaign_id),
            require_alive=False,
            require_current_profile=False,
        )
        if not any(x.id == asset and x.damaged for x in actual_body.assets):
            raise WorkflowError("The actual intercepted or original Bite must pay its real Asset")
    elif not any(
        x.get("kind") == "battle_damage_stage"
        and x.get("source_work") == value.work
        and Required.model_validate_json(x["requirement"]).kind in ("npc_damage", "handler_damage")
        and Required.model_validate_json(x["requirement"]).target == actual
        for x in born.facts
        if "requirement" in x
    ):
        raise WorkflowError("Prove the genuine original NPC/Handler body-damage consequence")
    if value.feeding_event:
        fed = _history(c, game, value.feeding_event)
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == value.feeding_event,
                )
            )
            .mappings()
            .first()
        )
        saved = next(
            (x for x in rules.records(fed, rules.ConsumptionResolution) if x.id == identity), None
        )
        if (
            event is None
            or event["kind"] != "m3.consume_sprite_fed"
            or saved != value
            or json.loads(event["payload_json"]).get("resolution") != identity
        ):
            raise WorkflowError(
                "Prove the actual one-time feeding event, not the earlier intention"
            )
    return value


def _feed_sprite_resolutions(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> str:
    from girlframe.services.m3_collateral import latest
    from girlframe.services.m3_consume_support import (
        stage_starvation_expiry,
    )
    from girlframe.services.m3_consume_support import (
        synchronize as sync_effects,
    )

    for value in rules.records(state, rules.ConsumptionResolution):
        if value.session != action["id"] or value.feeding_event:
            continue
        value = prove_resolution(game, c, state, value.id)
        work = latest(game, c, value.work)
        if work["state"] != "resolved":
            continue
        source = rules.session(state, action["id"])
        if rules.frame(state, source.actor) != source.frame:
            raise WorkflowError("Keep actual feeding bound to the original physical CONSUME Frame")
        cause = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == work["event_id"],
                )
            )
            .mappings()
            .one()
        )
        before = GameState.model_validate_json(state.model_dump_json())
        fresh = str(uuid4())
        rules.fed(state, source.actor, fresh, entire=value.option == "kill")
        owed = stage_starvation_expiry(game, c, before, state, source.actor, fresh, source.id)
        rules.put(
            state, source.model_copy(update=dict(work=tuple(dict.fromkeys((*source.work, *owed)))))
        )
        rules.put(state, value.model_copy(update=dict(feeding_event=fresh)))
        if value.option == "kill" and rules.held(state, source.actor, rules.DRIVE):
            require_rule(game, c, state, source.actor, rules.DRIVE)
            game.request(c, action, int(source.actor.entity), "consume_erase")
            action["data"]["consume"]["phase"] = "erasure"
            game.save_action(c, action)
        game.event(
            c,
            int(cause["actor_id"]),
            str(uuid4()),
            "m3.consume_sprite_fed",
            state,
            event_id=fresh,
            action_id=source.id,
            resolution=value.id,
            source_event=work["event_id"],
        )
        sync_effects(game, c, fresh)
        event = fresh
    return event


def _pending_sprite(game: GameService, c: Connection, state: GameState, session: str) -> bool:
    table = t.m3["m3_required_work"]
    for identity in rules.session(state, session).work:
        row = c.execute(
            sa.select(table.c.kind, table.c.state)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        ).first()
        if row is not None and row.kind == "sprite_intercept" and row.state != "resolved":
            return True
    return False
