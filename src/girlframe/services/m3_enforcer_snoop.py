"""Snoop keeps actual private answers, object facts and physical effects source-bound."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_enforcer_snoop as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_enforcer_requisitions import SNOOP
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_role_punishments import bond_ref, view
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast, _judge, _known_target
from girlframe.services.m3_enforcer_requisitions import owned
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "snoop_select",
    "snoop_answer",
    "snoop_object_fact",
    "snoop_relevance",
    "snoop_capacity",
    "snoop_damage_consequence",
    "snoop_item_void_threshold",
    "snoop_body_context",
)


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def _refs(meta: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    meta = action["data"]["snoop"] if action else None
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=bool(meta))
    assert access.registry is not None
    access.registry.require_available(SNOOP)
    if meta is None or action is None:
        return
    if (
        game.store.policy.m3_approval is None
        or meta["registry"] != game.store.policy.m3_approval.registry_sha256
    ):
        raise WorkflowError("Recover this Snoop's original rules approval.")
    state = load_state(c, game.store.campaign_id)
    if MedicalService(game.store)._handler(c) != (meta["procedural_gm"], meta["appointment"]):
        raise WorkflowError("Recover the original OOC facilitator appointment.")
    if fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]:
        raise WorkflowError("Recover this Snoop's original actual scene cast.")
    actor, target = _refs(meta)
    if (
        view(state, actor, profiles(c, game.store.campaign_id)).controller
        != meta["actor_controller"]
    ):
        raise WorkflowError("Recover the original snooping person's actual controller.")
    if (
        view(state, target, profiles(c, game.store.campaign_id)).controller
        != meta["target_controller"]
    ):
        raise WorkflowError("Recover the original target's actual answer owner.")


def _targets(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_handler_consequences import active_handler

    refs = [current_ref(state, int(x)) for x in state.sheets]
    handler = active_handler(state)
    if handler is not None:
        refs.append(handler)
    refs.extend(ActorRef(kind="external_pilot", entity=x.id) for x in state.harpy_states)
    if state.world is not None:
        refs.extend(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs)
        refs.extend(ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons)
        refs.extend(ActorRef(kind="external_pilot", entity=x.id) for x in state.world.pilots)
    result = []
    for ref in refs:
        if ref == actor:
            continue
        actual = view(state, ref, profiles(c, game.store.campaign_id))
        if not actual.alive or not _known_target(state, actor, ref, actual.controller):
            continue
        # Mid-result Intense deepening must have both actual printed Heat resources.
        if depth(state, bond_ref(state, actor), bond_ref(state, ref)) == 2 and any(
            x.kind != "npc" and view(state, x, profiles(c, game.store.campaign_id)).heat is None
            for x in (actor, ref)
        ):
            continue
        result.append(dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actual.label))
    return result


def preview(game: GameService, viewer: GuildViewer, channel: int) -> dict[str, Any]:
    try:
        with game.store.engine.connect() as c:
            authorize(game, c, viewer)
            state = load_state(c, game.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if owned(c, game, state, actor, SNOOP) is None:
                return dict(available=False, targets=[])
            cast = _cast(game, c, state, channel)
            if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
                return dict(available=False, targets=[])
            choices = _targets(game, c, state, actor)
            return dict(available=bool(choices), targets=choices)
    except (ValueError, WorkflowError):
        return dict(available=False, targets=[])


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
    actor_ref: ActorRef | None = None,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    actor = actor_ref or current_ref(state, viewer.user_id)
    target = prepared.target_actor
    grant = owned(c, game, state, actor, SNOOP)
    if (
        prepared.target is not None
        or prepared.off_duty_id
        or prepared.order_id
        or prepared.source_work
    ):
        raise WorkflowError(
            "Use an actual Snoop target and its accessible stuff in this source scene."
        )
    if (
        target is None
        or grant is None
        or target.model_dump(mode="json") not in [x["ref"] for x in _targets(game, c, state, actor)]
    ):
        raise WorkflowError(
            "Choose an actual known original person with supported Snoop resources."
        )
    cast = _cast(game, c, state, channel)
    bound = profiles(c, game.store.campaign_id)
    own, other = view(state, actor, bound), view(state, target, bound)
    if own.controller != viewer.user_id or not any(
        x.actor == actor and x.controller == viewer.user_id for x in cast.roles
    ):
        raise WorkflowError("Join as the actual snooping person; the target may remain absent.")
    if not prepared.context.strip() or not prepared.trigger_confirmed:
        raise WorkflowError(
            "Describe actual access to that person's stuff without moving their body."
        )
    judge, controller, source = _judge(game, c, state, cast)
    human, appointment = MedicalService(game.store)._handler(c)
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_controller=own.controller,
        target_controller=other.controller,
        target_frame=other.frame_instance,
        label=own.label,
        grant=grant.id,
        scene=cast.id,
        access=prepared.context,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
        ),
        judge=judge.model_dump(mode="json"),
        judge_controller=controller,
        judge_source=source,
        procedural_gm=human,
        appointment=appointment,
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
        discoveries=[],
        followups=[],
        effects=[],
        relevance=[],
        objects=[],
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    meta = action["data"]["snoop"]
    actor, target = _refs(meta)
    grant = owned(c, game, state, actor, SNOOP)
    if (
        grant is None
        or grant.id != meta["grant"]
        or target.model_dump(mode="json") not in [x["ref"] for x in _targets(game, c, state, actor)]
    ):
        raise WorkflowError(
            "Recover the actual original paid Snoop ability and target before rolling."
        )
    if (
        view(state, target, profiles(c, game.store.campaign_id)).frame_instance
        != meta["target_frame"]
    ):
        raise WorkflowError("Recover the original target's actual Frame before rolling Snoop.")


def _request(
    game: GameService, c: Connection, action: dict[str, Any], owner: int, kind: str, **body: Any
) -> None:
    game.request(c, action, owner, "snoop_" + kind, body)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["snoop"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("The actual known Snoop result already started.")
    meta["phase"] = "selecting"
    _request(game, c, action, meta["actor_controller"], "select")


def _next(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["snoop"]
    if game.pending(c, action["id"]):
        return
    answered = {x["question"] for x in meta["discoveries"]}
    for question in meta["selected"]:
        if question not in answered:
            meta["phase"] = "answering"
            _request(game, c, action, meta["target_controller"], "answer", question=question)
            return
    if action["data"]["result"]["tier"] == "high" and not meta.get("relevance_event"):
        meta["phase"] = "relevance"
        _request(game, c, action, meta["judge_controller"], "relevance")
        return
    if any(x["question"] == "valuable" for x in meta["discoveries"]) and not meta.get(
        "capacity_event"
    ):
        meta["phase"] = "capacity"
        _request(game, c, action, meta["actor_controller"], "capacity")
        return
    _, target = _refs(meta)
    actual = view(state, target, profiles(c, game.store.campaign_id))
    if (
        actual.rules in ("girl_frame", "handler_girl", "external_pilot")
        and actual.inside_frame is None
        and not meta.get("body_context_event")
        and (
            meta["relevance"]
            or any(x["question"] in ("valuable", "personal") for x in meta["discoveries"])
        )
    ):
        meta["phase"] = "body_context"
        _request(game, c, action, meta["target_controller"], "body_context")
        return
    meta["phase"] = "ready_effects"


def _response(c: Connection, game: GameService, event: str, kind: str, owner: int) -> ChoiceAnswer:
    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    row = c.execute(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                responses.c.campaign_id == choices.c.campaign_id,
                responses.c.choice_id == choices.c.id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == event,
            responses.c.actor_id == str(owner),
            choices.c.kind == kind,
        )
    ).scalar_one_or_none()
    if row is None:
        raise WorkflowError("Recover the genuine original owner's saved source response.")
    return ChoiceAnswer.model_validate_json(row)


def _asset_choices(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, Any]]:
    _, target = _refs(action["data"]["snoop"])
    actual = view(state, target, profiles(c, game.store.campaign_id))
    from girlframe.engine.m3_items import mechanical_assets
    from girlframe.services.m3_items import prove_item

    result = [dict(id=x.id, label=x.name, family=x.family) for x in actual.assets if not x.damaged]
    for asset in mechanical_assets(state, target):
        item = next(
            x for x in state.held_items if x.asset_id == asset.id and x.asset_json is not None
        )
        prove_item(c, game, state, item.id)
        if not asset.damaged and not any(x["id"] == asset.id for x in result):
            result.append(dict(id=asset.id, label=asset.name, family=asset.family))
    return result


def projection(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    from girlframe.services.m3_items import available_items

    meta = action["data"]["snoop"]
    _, target = _refs(meta)
    return dict(
        kind=request["kind"],
        question=json.loads(request["body_json"]).get("question"),
        questions=[dict(id=x, label=rules.LABELS[x]) for x in rules.QUESTIONS],
        maximum=1 if action["data"]["result"]["tier"] == "low" else 2,
        items=available_items(c, game, state, target, scene=meta["scene"])
        if request["kind"] == "snoop_answer"
        else [],
        assets=_asset_choices(game, c, state, action),
        replacements=[
            dict(id=x.id, label=x.name)
            for x in state.sheets[meta["actor"]["entity"]].assets
            if x.family == "girl" and x.intrinsic is None
        ]
        if meta["actor"]["kind"] == "pilot"
        else [],
        proposal=meta.get("proposal"),
        discoveries=meta["discoveries"]
        if viewer.user_id
        in (
            meta["actor_controller"],
            meta["target_controller"],
            meta["procedural_gm"],
        )
        else [],
    )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    meta = action["data"]["snoop"]
    actor, target = _refs(meta)
    kind = request["kind"]
    event = action["data"]["response_event"]
    if kind == "snoop_select":
        if (
            int(request["actor_id"]) != meta["actor_controller"]
            or answer.fields
            or answer.denied
            or answer.number is not None
            or answer.flag is not None
        ):
            raise WorkflowError("The original snooper chooses only the printed questions.")
        meta["selected"] = list(rules.select(action["data"]["result"]["tier"], answer.options))
        if action["data"]["result"]["tier"] == "mid":
            _copy(state, change(state, bond_ref(state, actor), bond_ref(state, target), 1, event))
            meta["bond_event"] = event
    elif kind == "snoop_answer":
        question = json.loads(request["body_json"])["question"]
        if (
            int(request["actor_id"]) != meta["target_controller"]
            or not answer.text.strip()
            or answer.options
            or answer.denied
            or answer.number is not None
            or answer.flag is not None
        ):
            raise WorkflowError("The actual original target supplies the printed private finding.")
        fields = answer.fields
        discovery = rules.Discovery(
            question=question,
            author=meta["target_controller"],
            source_event=event,
            text=answer.text,
            item=fields.get("item"),
            asset=fields.get("asset"),
            object_name=fields.get("name"),
            object_description=fields.get("description"),
        )
        if question in ("valuable", "personal"):
            if (
                set(fields) - {"item", "asset", "name", "description"}
                or sum(bool(x) for x in (discovery.item, discovery.asset, discovery.object_name))
                != 1
            ):
                raise WorkflowError(
                    "Identify one actual object or relevant Asset; a description grants no Asset."
                )
            if question == "valuable" and discovery.asset:
                raise WorkflowError(
                    "Pocket an actual takeable object, not an installed Frame or body part."
                )
            if discovery.item:
                from girlframe.services.m3_items import available_items

                if set(fields) != {"item"} or discovery.item not in {
                    x["id"] for x in available_items(c, game, state, target, scene=meta["scene"])
                }:
                    raise WorkflowError("Select this original person's actual accessible property.")
            if discovery.asset and (
                set(fields) != {"asset"}
                or discovery.asset not in {x["id"] for x in _asset_choices(game, c, state, action)}
            ):
                raise WorkflowError("Select an actual current relevant Asset owned by this target.")
            if discovery.object_name:
                if not discovery.object_description or set(fields) != {"name", "description"}:
                    raise WorkflowError("Describe the actual preexisting ordinary object.")
                meta["proposal"] = discovery.model_dump(mode="json")
                _request(game, c, action, meta["procedural_gm"], "object_fact")
                return
        elif fields:
            raise WorkflowError(
                "This printed question records an answer, not a new object or Asset."
            )
        meta["discoveries"].append(discovery.model_dump(mode="json"))
    elif kind == "snoop_object_fact":
        if (
            int(request["actor_id"]) != meta["procedural_gm"]
            or answer.flag is None
            or not answer.text.strip()
            or answer.fields
            or answer.options
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError(
                "The original OOC facilitator records actual object existence and room access."
            )
        proposal = meta.pop("proposal")
        if not answer.flag:
            meta.setdefault("rejected_objects", []).append(
                proposal | dict(review=answer.text, event=event)
            )
            _next(game, c, state, action)
            return
        identity = str(uuid4())
        item = HeldItem(
            id=identity,
            holder=target,
            name=proposal["object_name"],
            description=proposal["object_description"],
            source_owner=target,
            source_event=event,
            proposed_event=proposal["source_event"],
            origin_event=proposal["source_event"],
            confirmed_event=event,
            confirmed_controller=meta["procedural_gm"],
            factual_source_action=action["id"],
            location_mode="scene",
            scene_id=meta["scene"],
            location_event=event,
        )
        state.held_items.append(item)
        meta["objects"].append(
            dict(item=identity, proposal=proposal, review=answer.text, event=event)
        )
        meta["discoveries"].append(proposal | dict(item=identity))
    elif kind == "snoop_relevance":
        if (
            int(request["actor_id"]) != meta["judge_controller"]
            or not answer.text.strip()
            or answer.fields
            or answer.denied
            or answer.flag is not None
            or answer.number is not None
            or not set(answer.options) <= {x["id"] for x in _asset_choices(game, c, state, action)}
        ):
            raise WorkflowError(
                "The original source judge selects the relevant actual Assets and describes why."
            )
        meta["relevance"] = list(answer.options)
        meta["relevance_event"] = event
        meta["relevance_account"] = answer.text
    elif kind == "snoop_body_context":
        if (
            int(request["actor_id"]) != meta["target_controller"]
            or answer.flag is None
            or not answer.text.strip()
            or answer.fields
            or answer.options
            or answer.denied
            or answer.number is not None
        ):
            raise WorkflowError(
                "The actual original target records its body's factual cockpit context."
            )
        meta["occupancy"] = {target.token: answer.flag}
        meta["body_context_event"] = event
        meta["body_context_account"] = answer.text
    elif kind == "snoop_capacity":
        if (
            int(request["actor_id"]) != meta["actor_controller"]
            or set(answer.fields) - {"replace"}
            or answer.options
            or answer.denied
            or answer.number is not None
            or answer.flag is not None
        ):
            raise WorkflowError(
                "The actual snooper chooses any necessary real inventory replacement."
            )
        meta["replace"] = answer.fields.get("replace")
        meta["capacity_event"] = event
    else:
        raise WorkflowError("Open the actual saved Snoop response.")
    _next(game, c, state, action)


def validate_frame_damage_source(
    c: Connection,
    game: GameService,
    state: GameState,
    action_id: str,
    target: ActorRef,
    frame_instance: str,
    asset_id: str,
) -> None:
    action = game.action(c, action_id)
    meta = action["data"].get("snoop")
    if (
        meta is None
        or meta["phase"] != "ready_effects"
        or target.model_dump(mode="json") != meta["target"]
    ):
        raise WorkflowError("Use the exact actual Snoop target and ready physical source.")
    actor, _ = _refs(meta)
    grant = owned(c, game, state, actor, SNOOP)
    if grant is None or grant.id != meta["grant"]:
        raise WorkflowError("Recover the original paid Snoop ability.")
    own, other = (view(state, x, profiles(c, game.store.campaign_id)) for x in (actor, target))
    if (
        other.frame_instance != frame_instance
        or frame_instance != meta.get("target_frame")
        or not any(x.id == asset_id and x.family == "frame" and not x.damaged for x in other.assets)
    ):
        raise WorkflowError(
            "Damage the actual current relevant Frame Asset, not another or parked Frame."
        )
    personal = next(
        (
            x
            for x in meta["discoveries"]
            if x["question"] == "personal" and x.get("asset") == asset_id
        ),
        None,
    )
    if personal:
        response = _response(
            c, game, personal["source_event"], "snoop_answer", meta["target_controller"]
        )
        if response.fields.get("asset") != asset_id:
            raise WorkflowError("Recover the target's actual personal-property finding.")
    elif action["data"]["result"]["tier"] == "high" and asset_id in meta["relevance"]:
        response = _response(
            c, game, meta["relevance_event"], "snoop_relevance", meta["judge_controller"]
        )
        if asset_id not in response.options:
            raise WorkflowError("Recover the actual judge's source-relevance response.")
    else:
        raise WorkflowError(
            "This Frame Asset has no actual personal or high-result relevance source."
        )
    if own.cell is not None and other.frame_cell is not None and own.cell != other.frame_cell:
        raise WorkflowError("Actual known body/Frame locations contradict this source-room damage.")


def prove_object(c: Connection, game: GameService, state: GameState, item: HeldItem) -> None:
    action = game.action(c, str(item.factual_source_action))
    meta = action["data"].get("snoop") or {}
    record = next((x for x in meta.get("objects", []) if x["item"] == item.id), None)
    if (
        record is None
        or record["event"] != item.confirmed_event
        or item.source_owner.model_dump(mode="json") != meta["target"]
    ):
        raise WorkflowError("Recover the actual Snoop ordinary-object source.")
    proposed = _response(
        c, game, item.proposed_event or "", "snoop_answer", meta["target_controller"]
    )
    confirmed = _response(
        c, game, item.confirmed_event or "", "snoop_object_fact", meta["procedural_gm"]
    )
    if (
        not confirmed.flag
        or proposed.fields.get("name") != item.name
        or proposed.fields.get("description") != item.description
        or item.origin_asset_json is not None
    ):
        raise WorkflowError(
            "Recover the original private finding and actual object review; no invented Asset."
        )


def validate_transfer_source(
    c: Connection,
    game: GameService,
    state: GameState,
    action_id: str,
    source: ActorRef,
    recipient: ActorRef,
    selection: str,
) -> str:
    from girlframe.engine.m3_items import same_holder

    action = game.action(c, action_id)
    meta = action["data"].get("snoop") or {}
    if meta.get("phase") != "ready_effects":
        raise WorkflowError("Take only the actual source-proved Snoop valuable object.")
    actor, target = _refs(meta)
    discovery = next((x for x in meta["discoveries"] if x["question"] == "valuable"), None)
    if (
        recipient != actor
        or not same_holder(state, source, target)
        or discovery is None
        or discovery.get("item") != selection
    ):
        raise WorkflowError("Keep the exact original snooper, actual owner and pocketed discovery.")
    response = _response(
        c, game, discovery["source_event"], "snoop_answer", meta["target_controller"]
    )
    if response.fields.get("item") != selection and not any(
        x["item"] == selection for x in meta["objects"]
    ):
        raise WorkflowError("Recover the actual target's printed valuable-object response.")
    grant = owned(c, game, state, actor, SNOOP)
    if grant is None or grant.id != meta["grant"]:
        raise WorkflowError("Recover the actual paid Snoop source before taking property.")
    own, other = (view(state, x, profiles(c, game.store.campaign_id)) for x in (actor, target))
    item = next((x for x in state.held_items if x.id == selection), None)
    if (
        (item is None or item.location_mode == "carried")
        and own.cell is not None
        and other.cell is not None
        and own.cell != other.cell
    ):
        raise WorkflowError("Actual carried object and body locations contradict pocketing here.")
    return str(meta["scene"])


def _finish(game: GameService, c: Connection, action: dict[str, Any], state: GameState) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    if action["state"] == "complete" or game.pending(c, action["id"]):
        return
    meta = action["data"]["snoop"]
    meta["phase"] = "complete"
    action["data"]["result"]["snoop_findings"] = meta["discoveries"]
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    else:
        ChoiceEngine(game).finish(c, state, action)


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    """Runs after actual authenticated response insertion, inside that same transaction."""
    from girlframe.engine.m3_items import actual_asset
    from girlframe.services.m3_battle import damage_actor, synchronize_damage
    from girlframe.services.m3_items import create_snoop_item_void, take_in_transaction

    meta = action["data"]["snoop"]
    if meta["phase"] != "ready_effects":
        return
    actor, target = _refs(meta)
    state = load_state(c, game.store.campaign_id)
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.id == event, t.events.c.campaign_id == game.store.campaign_id
            )
        )
        .mappings()
        .one()
    )
    effect = str(uuid4())
    transfers = []
    damage: set[str] = set(meta["relevance"])
    for discovery in meta["discoveries"]:
        _response(c, game, discovery["source_event"], "snoop_answer", meta["target_controller"])
        if discovery["question"] == "valuable":
            before = state
            state = take_in_transaction(
                c,
                game,
                state,
                source=target,
                recipient=actor,
                selection=discovery["item"],
                action=action["id"],
                event=effect,
                account=discovery["text"],
                replace=meta.get("replace"),
                inside_frame=meta.get("occupancy", {}).get(target.token),
                snoop=True,
            )
            transfers.append(state.item_transfers[-1].id)
            if before is state:
                raise WorkflowError("Preserve the immutable actual before-possession source.")
        if discovery["question"] == "personal":
            if discovery.get("asset"):
                damage.add(discovery["asset"])
            elif discovery.get("item"):
                item = next((x for x in state.held_items if x.id == discovery["item"]), None)
                if item is None:
                    raise WorkflowError("Recover the actual personal-property object.")
                asset = actual_asset(state, item)
                if asset is not None:
                    damage.add(asset.id)
                else:
                    state.held_items = [
                        x.model_copy(update=dict(condition="ruined", state_event=effect))
                        if x.id == item.id
                        else x
                        for x in state.held_items
                    ]
    if action["data"]["result"]["tier"] == "high":
        from girlframe.engine.m3_items import same_holder

        state.held_items = [
            x.model_copy(update=dict(condition="ruined", state_event=effect))
            if same_holder(state, x.holder, target)
            and x.location_mode == "scene"
            and x.scene_id == meta["scene"]
            and x.asset_json is None
            else x
            for x in state.held_items
        ]
    for asset_id in sorted(damage):
        actual = view(state, target, profiles(c, game.store.campaign_id))
        damage_asset = next(
            (x for x in _asset_choices(game, c, state, action) if x["id"] == asset_id), None
        )
        if damage_asset is None:
            continue
        if damage_asset["family"] == "frame":
            from girlframe.services.m3_battle import damage_frame_at_scene

            if actual.frame_instance is None:
                raise WorkflowError("Recover the actual source Frame identity before damage.")
            state, work = damage_frame_at_scene(
                game,
                c,
                state,
                target=target,
                frame_instance=actual.frame_instance,
                asset_id=asset_id,
                source_action=action["id"],
                event=effect,
                actor=actor,
                chooser_controller=meta["actor_controller"],
                occurrence="snoop:" + asset_id,
            )
        else:
            state, work = damage_actor(
                game,
                c,
                state,
                target=target,
                asset_id=asset_id,
                source_action=action["id"],
                source_work=None,
                event=effect,
                actor=actor,
                chooser_controller=meta["actor_controller"],
                occurrence="snoop:" + asset_id,
            )
        meta["followups"].extend(work)
        meta["effects"].append(dict(asset=asset_id, event=effect))
    meta["phase"] = "waiting_consequences"
    meta["physical_event"] = effect
    meta["transfers"] = transfers
    game.save_action(c, action)
    game.event(
        c,
        source["actor_id"],
        source["command_key"],
        "m3.snoop_physical_effects",
        state,
        event_id=effect,
        event_index=source["event_index"] + 1,
        action_id=action["id"],
        source_event=event,
    )
    synchronize_damage(game, c, effect)
    for transfer in transfers:
        create_snoop_item_void(game, c, transfer, effect)
    action.update(game.action(c, action["id"]))
    state = load_state(c, game.store.campaign_id)
    _finish(game, c, action, state)
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("battle_counter_source"):
        from girlframe.services.m3_battle import complete_counter_play

        complete_counter_play(game, c, action, effect, None, source["command_key"])


def complete_damage(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    meta = action["data"]["snoop"]
    body = json.loads(row["body_json"])
    if (
        row["state"] != "resolved"
        or row["id"] not in meta["followups"]
        or body.get("source_action") != action["id"]
    ):
        raise WorkflowError("Finish this exact actual Snoop damage consequence first.")
    state = load_state(c, game.store.campaign_id)
    _finish(game, c, action, state)
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("battle_counter_source"):
        from girlframe.services.m3_battle import complete_counter_play

        complete_counter_play(game, c, action, event, viewer, key)


def complete_item_void(
    game: GameService,
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.engine.m3_void import FINAL
    from girlframe.services.m3_items import prove_transfer

    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .one()
    )
    body = json.loads(row["body_json"])
    state = load_state(c, game.store.campaign_id)
    _, _, transfer = prove_transfer(c, game, body["transfer"])
    if (
        row["state"] != "resolved"
        or body.get("item_source") != "enforcer_snoop"
        or transfer.source_kind != "enforcer_snoop"
        or not any(identity in x.source_works and x.stage in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Finish the exact actual Snoop transfer corruption threshold first.")
    action = game.action(c, transfer.action)
    choices = t.m2["m2_choices"]
    for request in game.pending(c, action["id"]):
        if (
            request["kind"] == "snoop_item_void_threshold"
            and json.loads(request["body_json"]).get("work_id") == identity
        ):
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == game.store.campaign_id, choices.c.id == request["id"]
                )
                .values(state="completed_by_work", revision=request["revision"] + 1)
            )
    _finish(game, c, action, state)
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("battle_counter_source"):
        from girlframe.services.m3_battle import complete_counter_play

        complete_counter_play(game, c, action, event, viewer, key)


def visible_result(
    action: dict[str, Any], viewer: GuildViewer, result: dict[str, Any]
) -> dict[str, Any]:
    meta = action["data"]["snoop"]
    if viewer.user_id in (
        meta["actor_controller"],
        meta["target_controller"],
        meta["procedural_gm"],
    ):
        return result
    return {k: v for k, v in result.items() if k not in ("discoveries", "snoop_findings")} | dict(
        snoop_findings=[x for x in meta["discoveries"] if x["question"] == "embarrassing"]
    )
