"""Owned printed intimacy mechanics; no generated acts, responses or discoveries."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_mockingbird_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird_state import CAPABILITIES
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def context(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["mockingbird"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(
        meta["parties"][0]["actor"]
    )


def _copy(state: GameState, changed: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))


def _actual(game: "GameService", c: Connection, state: GameState, ref: ActorRef) -> ActorView:
    return resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)


def _strict(
    answer: ChoiceAnswer,
    fields: set[str],
    *,
    options: int = 0,
    text: bool = False,
    flag: bool = False,
) -> None:
    if (
        len(answer.options) != options
        or answer.denied
        or set(answer.fields) != fields
        or answer.number is not None
        or answer.member is not None
        or (answer.flag is not True if flag else answer.flag is not None)
        or (not answer.text.strip() if text else bool(answer.text))
    ):
        raise WorkflowError("Use only this exact owned printed effect response")


def _finish(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if not game.pending(c, action["id"]):
        from girlframe.services.m3_mockingbird_plays import _finish as finish

        finish(game, c, state, action)


def _bond_risk(state: GameState, action: dict[str, Any], *, risk: bool) -> None:
    actor, target = context(action)
    meta = action["data"]["mockingbird"]
    if meta.get("sex_bond_applied"):
        raise WorkflowError("This original intimacy source already deepened its actual Bond")
    event = action["data"]["response_event"]
    _copy(state, rules.deepen(state, actor, target, event))
    meta["sex_bond_applied"] = event
    if risk:
        _copy(state, rules.exposure(state, actor, target, "both_risk", action["id"], event))
    from girlframe.services.m3_mockingbird_discovery import bind_exposures

    bind_exposures(state, action)


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    actor, target = context(action)
    level = action["data"]["result"]["tier"]
    meta = action["data"]["mockingbird"]
    if meta.get("sex_started"):
        raise WorkflowError("Resume this actual source's existing intimacy decisions")
    meta["sex_started"] = True
    if level == "low":
        _copy(
            state,
            rules.helpless(state, actor, target, action["id"], action["data"]["response_event"]),
        )
        from girlframe.services.m3_mockingbird_discovery import bind_exposures

        bind_exposures(state, action)
        _finish(game, c, state, action)
    elif level == "mid":
        game.request(c, action, int(action["actor_id"]), "mockingbird_sex_select")
    else:
        actual = _actual(game, c, state, target)
        if actual.rules in ("handler", "director", "handler_girl"):
            game.request(c, action, int(action["actor_id"]), "mockingbird_sex_high_commit")
        elif actual.rules == "npc":
            game.request(c, action, meta["judge_controller"], "mockingbird_sex_npc_void")
        elif any(not x.void for x in rules.assets(state, target)):
            game.request(c, action, int(action["actor_id"]), "mockingbird_sex_infect")
        else:
            from girlframe.services.m3_sup import offer

            if offer(game, c, state, target):
                meta["sex_infection"] = dict(
                    target=target.model_dump(mode="json"),
                    asset=None,
                    snapshot=None,
                    caster_choice=None,
                )
                game.request(c, action, actual.controller, "mockingbird_sex_rewrite")
                return
            # Mandatory existing all-Void is a factual no-change outcome, not a fake answer.
            values = rules.assets(state, target)
            if not values or not all(x.void for x in values):
                raise WorkflowError("Establish this actual counterpart's real corruption resources")
            state.facts.append(
                dict(
                    kind="mockingbird_already_void",
                    action=action["id"],
                    target=target.model_dump_json(),
                    event=action["data"]["response_event"],
                )
            )
            _bond_risk(state, action, risk=True)
            _finish(game, c, state, action)


def _destination(action: dict[str, Any], token: str) -> ActorRef:
    meta = action["data"]["mockingbird"]
    candidates = [
        ActorRef.model_validate(meta["actor"]),
        *(ActorRef.model_validate(x["actor"]) for x in meta["parties"]),
    ]
    chosen = next((x for x in candidates if x.token == token), None)
    if chosen is None:
        raise WorkflowError("Redirect only to an actual participant in this source interaction")
    return chosen


def _transfer_source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[GameState, ActorRef]:
    _, target = context(action)
    selection = action["data"]["mockingbird"]["sex_transfer"]
    current = next(
        (x for x in rules.assets(state, target) if x.id == selection["source_asset"]), None
    )
    if current is None or current.model_dump_json() != selection["source_snapshot"]:
        raise WorkflowError("The actual source Void Asset changed; recover the owned transfer")
    changed = rules.remove_void(
        state, target, current.id, selection["restore"], action["data"]["response_event"]
    )
    return changed, target


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_mockingbird_effects import record_effect

    actor, target = context(action)
    meta = action["data"]["mockingbird"]
    event = action["data"]["response_event"]
    kind = row["kind"]
    affected: tuple[ActorRef, ...]
    if kind in (
        "mockingbird_handler_void",
        "mockingbird_handler_girl_void",
        "mockingbird_redirect_handler_void",
        "mockingbird_redirect_handler_girl_void",
        "mockingbird_sex_void_threshold",
    ):
        raise WorkflowError(
            "Finish the real owned Void continuation; an acknowledgment cannot replace it"
        )
    if kind == "mockingbird_sex_select":
        _strict(answer, set(answer.fields), options=1)
        if (
            int(row["actor_id"]) != int(action["actor_id"])
            or action["data"]["result"]["tier"] != "mid"
        ):
            raise WorkflowError("Only the original caster owns this actual mid-tier selection")
        if answer.options == ("starry",):
            if (
                set(answer.fields) != {"capability"}
                or answer.fields["capability"] not in CAPABILITIES
            ):
                raise WorkflowError(
                    "Choose the one actual always-available conversation capability"
                )
            other = _actual(game, c, state, target)
            _copy(
                state,
                rules.starry(
                    state,
                    profiles(c, game.store.campaign_id),
                    actor,
                    target,
                    answer.fields["capability"],
                    action["id"],
                    event,
                    tuple(sorted({int(action["actor_id"]), other.controller})),
                ),
            )
            meta["sex_bond_applied"] = event
            _finish(game, c, state, action)
        elif answer.options == ("collect",) and not answer.fields:
            if not any(x.void for x in rules.assets(state, target)) or not _destinations(
                game, c, state, action
            ):
                raise WorkflowError("The source counterpart has no actual Void Asset to take from")
            game.request(c, action, int(action["actor_id"]), "mockingbird_sex_redirect")
        elif answer.options == ("hide",) and not answer.fields:
            if not rules.corruption_options(state, target):
                raise WorkflowError("The actual counterpart has no existing corruption to hide")
            game.request(
                c, action, _actual(game, c, state, target).controller, "mockingbird_sex_hide"
            )
        else:
            raise WorkflowError("Choose one printed effect with its exact real prerequisites")
    elif kind == "mockingbird_sex_hide":
        _strict(answer, set(), options=len(answer.options), text=True)
        if not answer.options or int(row["actor_id"]) != _actual(game, c, state, target).controller:
            raise WorkflowError("Only the actual counterpart describes their own suppression")
        before = GameState.model_validate_json(state.model_dump_json())
        _copy(
            state, rules.suppress(state, target, answer.options, answer.text, action["id"], event)
        )
        _bond_risk(state, action, risk=False)
        _copy(state, rules.exposure(state, actor, target, "teaching", action["id"], event))
        from girlframe.services.m3_mockingbird_discovery import bind_exposures

        bind_exposures(state, action)
        record_effect(
            game,
            c,
            state,
            before,
            action,
            row,
            (target,),
            "hide",
            dict(selected=list(answer.options)),
        )
        _finish(game, c, state, action)
    elif kind == "mockingbird_sex_infect":
        _strict(answer, {"asset"})
        selected = next(
            (
                x
                for x in rules.assets(state, target)
                if x.id == answer.fields["asset"] and not x.void
            ),
            None,
        )
        if selected is None or int(row["actor_id"]) != int(action["actor_id"]):
            raise WorkflowError(
                "The original caster chooses an actual uncorrupted counterpart Asset"
            )
        meta["sex_infection"] = dict(
            target=target.model_dump(mode="json"),
            asset=selected.id,
            snapshot=selected.model_dump_json(),
            caster_choice=row["id"],
        )
        game.request(
            c, action, _actual(game, c, state, target).controller, "mockingbird_sex_rewrite"
        )
    elif kind == "mockingbird_sex_redirect":
        _strict(answer, {"source_asset", "destination", "destination_asset"})
        if int(row["actor_id"]) != int(action["actor_id"]):
            raise WorkflowError("The original caster chooses the actual Void's destination")
        source_asset = next(
            (
                x
                for x in rules.assets(state, target)
                if x.id == answer.fields["source_asset"] and x.void
            ),
            None,
        )
        destination = _destination(action, answer.fields["destination"])
        if source_asset is None:
            raise WorkflowError("Choose the actual source_asset counterpart's existing Void Asset")
        destination_view = _actual(game, c, state, destination)
        chosen = None
        if destination != actor and destination_view.rules not in (
            "handler",
            "director",
            "handler_girl",
            "npc",
        ):
            chosen = next(
                (
                    x
                    for x in rules.assets(state, destination)
                    if x.id == answer.fields["destination_asset"] and not x.void
                ),
                None,
            )
            if chosen is None:
                raise WorkflowError("Choose a different actual uncorrupted destination Asset")
        elif answer.fields["destination_asset"]:
            raise WorkflowError(
                "Self/physiological choices do not invent an existing destination Asset"
            )
        meta["sex_transfer"] = dict(
            source_asset=source_asset.id,
            source_snapshot=source_asset.model_dump_json(),
            destination=destination.model_dump(mode="json"),
            destination_asset=chosen.id if chosen else None,
            destination_snapshot=chosen.model_dump_json() if chosen else None,
            caster_choice=row["id"],
        )
        game.request(
            c, action, _actual(game, c, state, target).controller, "mockingbird_sex_restore"
        )
    elif kind == "mockingbird_sex_restore":
        _strict(answer, set(), text=True)
        if int(row["actor_id"]) != _actual(game, c, state, target).controller:
            raise WorkflowError("The original source owner describes the actual uncorrupted Asset")
        selection = meta["sex_transfer"]
        selection.update(restore=answer.text, restore_choice=row["id"], restore_event=event)
        destination = ActorRef.model_validate(selection["destination"])
        actual = _actual(game, c, state, destination)
        if destination == actor:
            game.request(c, action, int(action["actor_id"]), "mockingbird_sex_self")
        elif actual.rules in ("handler", "director", "handler_girl"):
            # Source removal and real physiological destination are committed atomically.
            changed, _ = _transfer_source(game, c, state, action)
            _copy(state, changed)
            from girlframe.services.m3_mockingbird_void import stage_redirect_handler_void

            stage_redirect_handler_void(
                game,
                c,
                state,
                action,
                destination,
                row["id"],
                event,
                girl_rules=actual.rules == "handler_girl",
            )
            _bond_risk(state, action, risk=False)
        elif actual.rules == "npc":
            game.request(c, action, meta["judge_controller"], "mockingbird_sex_redirect_npc")
        else:
            meta["sex_infection"] = dict(
                target=selection["destination"],
                asset=selection["destination_asset"],
                snapshot=selection["destination_snapshot"],
                caster_choice=selection["caster_choice"],
            )
            game.request(c, action, actual.controller, "mockingbird_sex_rewrite")
    elif kind == "mockingbird_sex_self":
        _strict(
            answer,
            {"name", "replace", "storage"} if "storage" in answer.fields else {"name", "replace"},
            text=True,
        )
        if answer.fields.get("storage", "yes") != "yes":
            raise WorkflowError("Choose only the actual offered Void Storage destination")
        if int(row["actor_id"]) != int(action["actor_id"]):
            raise WorkflowError("The actual caster writes their own new Void Asset")
        before = GameState.model_validate_json(state.model_dump_json())
        changed, source = _transfer_source(game, c, state, action)
        from girlframe.services.m3_janus_storage import gain_source

        changed = rules.write_self_asset(
            changed,
            actor,
            answer.fields["name"],
            answer.text,
            action["id"],
            event,
            replace=answer.fields["replace"] or None,
            storage=gain_source(
                game, c, changed, actor, row["id"], "mockingbird_sex", "storage" in answer.fields
            ),
        )
        _copy(state, changed)
        _bond_risk(state, action, risk=False)
        record_effect(
            game,
            c,
            state,
            before,
            action,
            row,
            (source, actor),
            "collect_self",
            dict(meta["sex_transfer"]),
        )
        _finish(game, c, state, action)
    elif kind == "mockingbird_sex_rewrite":
        infection = meta["sex_infection"]
        recipient = ActorRef.model_validate(infection["target"])
        from girlframe.services.m3_sup import parse

        growth = parse(game, c, state, recipient, answer.fields)
        _strict(
            answer,
            set(answer.fields) if growth else {"storage"} if "storage" in answer.fields else set(),
            text=True,
        )
        if answer.fields.get("storage", "yes") != "yes":
            raise WorkflowError("Choose only the actual offered Storage destination")
        actual = _actual(game, c, state, recipient)
        chosen = next(
            (x for x in rules.assets(state, recipient) if x.id == infection["asset"]), None
        )
        if (
            int(row["actor_id"]) != actual.controller
            or (chosen is None and not (growth and infection["asset"] is None))
            or (chosen is not None and chosen.model_dump_json() != infection["snapshot"])
        ):
            raise WorkflowError(
                "Only the real unchanged destination Asset's owner supplies its rewrite"
            )
        before = GameState.model_validate_json(state.model_dump_json())
        changed = state
        affected = (recipient,)
        if meta.get("sex_transfer"):
            changed, source = _transfer_source(game, c, state, action)
            affected = (source, recipient)
        from girlframe.services.m3_janus_storage import gain_source

        changed, _ = rules.infect(
            changed,
            profiles(c, game.store.campaign_id),
            actor,
            recipient,
            chosen.id if chosen is not None and growth is None else "",
            answer.text,
            action["id"],
            event,
            storage=gain_source(
                game,
                c,
                changed,
                recipient,
                row["id"],
                "mockingbird_sex",
                "storage" in answer.fields,
            ),
            growth=growth,
        )
        _copy(state, changed)
        _bond_risk(state, action, risk=action["data"]["result"]["tier"] == "high")
        record_effect(
            game,
            c,
            state,
            before,
            action,
            row,
            affected,
            "collect_redirect" if meta.get("sex_transfer") else "high_infect",
            dict(infection=infection, transfer=meta.get("sex_transfer")),
        )
        _finish(game, c, state, action)
    elif kind in ("mockingbird_sex_npc_void", "mockingbird_sex_redirect_npc"):
        _strict(answer, {"manifestation"})
        if int(row["actor_id"]) != meta["judge_controller"]:
            raise WorkflowError("The actual source Handler/Director chooses NPC Void manifestation")
        before = GameState.model_validate_json(state.model_dump_json())
        changed = state
        destination = target
        affected = (target,)
        if kind == "mockingbird_sex_redirect_npc":
            changed, source = _transfer_source(game, c, state, action)
            destination = ActorRef.model_validate(meta["sex_transfer"]["destination"])
            affected = (source, destination)
        judge = ActorRef.model_validate(meta["judge"]) if meta["judge"] else None
        _copy(
            state,
            rules.npc_void(
                changed,
                destination,
                answer.fields["manifestation"],
                judge,
                meta["judge_controller"],
                action["id"],
                event,
            ),
        )
        _bond_risk(state, action, risk=kind == "mockingbird_sex_npc_void")
        record_effect(
            game,
            c,
            state,
            before,
            action,
            row,
            affected,
            "npc_void",
            dict(manifestation=answer.fields["manifestation"]),
        )
        _finish(game, c, state, action)
    elif kind == "mockingbird_sex_high_commit":
        _strict(answer, set(), flag=True)
        if action["data"]["result"]["tier"] != "high" or int(row["actor_id"]) != int(
            action["actor_id"]
        ):
            raise WorkflowError("Only this original high source infects its actual counterpart")
        actual = _actual(game, c, state, target)
        from girlframe.services.m3_mockingbird_void import (
            stage_handler_girl_void,
            stage_handler_void,
        )

        if actual.rules == "handler_girl":
            stage_handler_girl_void(game, c, state, action, target, row["id"], event)
        else:
            stage_handler_void(game, c, state, action, target, row["id"], event)
        _bond_risk(state, action, risk=True)
    else:
        raise WorkflowError("Use the exact original owned intimacy effect")


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    actor, target = context(action)
    kind = row["kind"]
    if kind in (
        "mockingbird_handler_void",
        "mockingbird_handler_girl_void",
        "mockingbird_redirect_handler_void",
        "mockingbird_redirect_handler_girl_void",
        "mockingbird_sex_void_threshold",
    ):
        return dict(work_id=json.loads(row["body_json"])["work_id"])
    actual = _actual(game, c, state, target)
    from girlframe.services.m3_janus_storage import available as storage_available

    values = rules.assets(state, target)
    choices = ["starry"]
    if any(x.void for x in values):
        choices.insert(0, "collect")
    if rules.corruption_options(state, target):
        choices.insert(0, "hide")
    result: dict[str, Any] = dict(
        storage_available=storage_available(
            game,
            c,
            state,
            ActorRef.model_validate(
                action["data"]["mockingbird"].get("sex_infection", {}).get("target")
            )
            if kind == "mockingbird_sex_rewrite"
            else actor
            if kind == "mockingbird_sex_self"
            else target,
        ),
        target=actual.label,
        options=choices,
        capabilities=list(CAPABILITIES),
        assets=[dict(id=x.id, label=x.name) for x in values if not x.void],
        void_assets=[dict(id=x.id, label=x.name) for x in values if x.void],
        corruption=[
            dict(id=i, label=label) for i, label in rules.corruption_options(state, target)
        ],
        destinations=[],
    )
    from girlframe.services.m3_sup import offer

    recipient = (
        ActorRef.model_validate(action["data"]["mockingbird"]["sex_infection"]["target"])
        if kind == "mockingbird_sex_rewrite"
        else target
    )
    result["sup"] = offer(game, c, state, recipient) if kind == "mockingbird_sex_rewrite" else None
    result["sup_only"] = (
        kind == "mockingbird_sex_rewrite"
        and action["data"]["mockingbird"]["sex_infection"]["asset"] is None
    )
    result["destinations"] = _destinations(game, c, state, action)
    if not result["destinations"] and "collect" in choices:
        choices.remove("collect")
    if kind == "mockingbird_sex_self":
        girls = [x for x in rules.assets(state, actor) if x.family == "girl"]
        result["replace"] = (
            [dict(id=x.id, label=x.name) for x in girls if not x.void] if len(girls) >= 4 else []
        )
        result["replacement_required"] = len(girls) >= 4
    return result


def _destinations(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, Any]]:
    actor, _ = context(action)
    meta = action["data"]["mockingbird"]
    result = []
    for ref in [actor, *(ActorRef.model_validate(x["actor"]) for x in meta["parties"])]:
        view = _actual(game, c, state, ref)
        values = rules.assets(state, ref)
        eligible = [dict(id=x.id, label=x.name) for x in values if not x.void]
        if ref == actor:
            girls = [x for x in values if x.family == "girl"]
            if len(girls) >= 4 and not any(not x.void for x in girls):
                continue
        elif view.rules not in ("handler", "director", "handler_girl", "npc") and not eligible:
            continue
        result.append(
            dict(
                token=ref.token,
                ref=ref.model_dump(mode="json"),
                label=view.label,
                self=ref == actor,
                assets=eligible if ref != actor else [],
            )
        )
    return result
