"""Put Someone Beneath You uses the existing dice, durable choices and scene lock."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_beneath as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, higher
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def roles(action: dict[str, Any], level: str) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["beneath"]
    actor, target = (
        ActorRef.model_validate_json(json.dumps(meta[key])) for key in ("actor", "target")
    )
    return (target, actor) if level == "low" else (actor, target)


def no_conflict(
    game: "GameService", c: Connection, viewer: GuildViewer, prepared: PlayInput
) -> None:
    """Serialize actual affected characters, while permitting their real response chain."""
    ancestors: set[str] = set()
    parent = prepared.parent
    while parent:
        if parent in ancestors:
            raise WorkflowError("Recover the inconsistent actual response chain.")
        ancestors.add(parent)
        ancestor = game.action(c, parent)
        if ancestor["data"].get("beneath"):
            authorize(game, c, viewer, ancestor)
        parent = ancestor["parent_id"]
    requested = {str(viewer.user_id)}
    if prepared.target is not None:
        requested.add(str(prepared.target))
    actions = t.m2["m2_actions"]
    for row in c.execute(
        sa.select(actions).where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.state.not_in(("complete", "aborted")),
        )
    ).mappings():
        if row["id"] in ancestors:
            continue
        data = json.loads(row["body_json"])
        if prepared.play not in (rules.PLAY, "defeat", "dive_deep") and not (
            data.get("beneath") or data.get("defeat") or data.get("dive") or data.get("void_keep")
        ):
            continue
        involved = {row["actor_id"]}
        target = (data.get("prepared") or {}).get("target")
        if target is not None:
            involved.add(str(target))
        if requested & involved:
            raise WorkflowError(
                "ACTOR_BUSY: resolve the actual affected character's pending Play first."
            )


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays")
    ruling = game.store.policy.owner_m3_rulings
    if ruling is None or ruling.beneath_private_choices != "affected_owner":
        raise WorkflowError(
            "UNRESOLVED_RULING: record the delegated private-detail choice ownership."
        )
    if action:
        approval = game.store.policy.m3_approval
        if (
            approval is None
            or (action["data"].get("m3_shared") or {}).get("registry") != approval.registry_sha256
        ):
            raise WorkflowError(
                "M3_POLICY_CHANGED: recover the original social Play approval first."
            )
        for key in ("actor", "target"):
            ref = ActorRef.model_validate_json(json.dumps(action["data"]["beneath"][key]))
            if not HandlerService(game.store)._member(c, int(ref.entity)):
                raise WorkflowError("Recover this Play's changed participant membership first.")
            if (
                game.character_binding(
                    c,
                    load_state(c, game.store.campaign_id),
                    int(ref.entity),
                    require_current_profile=False,
                )
                != ref.incarnation
            ):
                raise WorkflowError(
                    "STALE_ACTOR: recover the original characters before responding."
                )


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, prepared: PlayInput, state: GameState
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.target is None
        or prepared.target == viewer.user_id
        or prepared.off_duty_id is not None
    ):
        raise WorkflowError("Choose another actual Girl in the scene for this Heat-based Play.")
    refs = tuple(
        ActorRef(
            kind="pilot",
            entity=str(uid),
            incarnation=game.character_binding(
                c, state, uid, require_current_profile=uid == viewer.user_id
            ),
        )
        for uid in (viewer.user_id, prepared.target)
    )
    actors = tuple(
        resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
        for ref in refs
    )
    if actors[0].piloting is not None and actors[0].piloting != prepared.piloting:
        raise WorkflowError("STALE_POSITION: confirm your actual recorded Frame occupancy.")
    if not HandlerService(game.store)._member(c, prepared.target):
        raise WorkflowError("The actual target must still be a campaign member.")
    return dict(
        actor=refs[0].model_dump(mode="json"),
        target=refs[1].model_dump(mode="json"),
        target_sha256=actors[1].source_sha256,
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    authorize(game, c, viewer, action)
    target = ActorRef.model_validate_json(json.dumps(action["data"]["beneath"]["target"]))
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.source_sha256 != action["data"]["beneath"]["target_sha256"]:
        raise WorkflowError(
            "STALE_TARGET: recover the unrolled Play and confirm its actual target."
        )


def bonds(
    game: "GameService", c: Connection, state: GameState, victim: ActorRef
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_actor_bonds import current_ref, depth

    result = []
    for uid in (*state.order, state.handler):
        if uid is None or str(uid) == victim.entity:
            continue
        peer = current_ref(state, uid)
        if depth(state, victim, peer) < 1:
            continue
        actual = resolve(
            state, peer, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        result.append(dict(token=peer.token, ref=peer.model_dump(mode="json"), label=actual.label))
    if state.world:
        for npc in state.world.npcs:
            peer = ActorRef(kind="npc", entity=npc.id)
            if depth(state, victim, peer) > 0:
                result.append(
                    dict(token=peer.token, ref=peer.model_dump(mode="json"), label=npc.name)
                )
    for archive in state.career_archives:
        peer = archive.actor
        if peer != victim and depth(state, victim, peer) > 0:
            result.append(
                dict(
                    token=peer.token,
                    ref=peer.model_dump(mode="json"),
                    label=json.loads(archive.sheet_json)["callsign"] + " (original character)",
                )
            )
    return result


def orders(
    game: "GameService", c: Connection, setter: ActorRef, channel: str
) -> list[dict[str, Any]]:
    table = t.m2["m2_orders"]
    candidates = [
        dict(x)
        for x in c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.target_id == setter.entity,
                table.c.channel_id == channel,
                table.c.state == "followed",
            )
        ).mappings()
    ]
    actions = t.m2["m2_actions"]
    state = load_state(c, game.store.campaign_id)
    proven = []
    for row in candidates:
        source = (
            c.execute(
                sa.select(actions).where(
                    actions.c.campaign_id == game.store.campaign_id,
                    actions.c.actor_id == setter.entity,
                    actions.c.state == "complete",
                    sa.func.json_extract(actions.c.body_json, "$.order_id") == row["id"],
                    sa.func.json_extract(actions.c.body_json, "$.play") == "receive_orders",
                )
            )
            .mappings()
            .first()
        )
        if source is None:
            continue
        data = json.loads(source["body_json"])
        responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
        reply = c.scalar(
            sa.select(responses.c.answer_json)
            .join(
                choices,
                sa.and_(
                    choices.c.campaign_id == responses.c.campaign_id,
                    choices.c.id == responses.c.choice_id,
                ),
            )
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == source["id"],
                choices.c.kind == "order_response",
                responses.c.actor_id == setter.entity,
            )
        )
        if reply is None or json.loads(reply).get("options", [])[:1] not in (
            ["obedient"],
            ["immediate"],
            ["hesitant"],
            ["mouthing_off"],
            ["gritted_teeth"],
        ):
            continue
        if data.get("character_ids", {}).get(setter.entity) != setter.incarnation:
            continue
        issuer = int(row["issuer_id"])
        if issuer == state.handler:
            if data.get("handler") != issuer:
                continue
        elif data.get("character_ids", {}).get(str(issuer)) != game.character_binding(
            c, state, issuer, require_current_profile=False
        ):
            continue
        if data.get("result", {}).get("response") not in (
            "obedient",
            "immediate",
            "hesitant",
            "mouthing_off",
            "gritted_teeth",
        ):
            continue
        proven.append(row)
    return proven


def lineage(game: "GameService", c: Connection, identity: str) -> list[str]:
    result = []
    node = game.action(c, identity)
    scene, channel = node["scene_id"], node["channel_id"]
    while True:
        if node["id"] in result or node["scene_id"] != scene or node["channel_id"] != channel:
            raise WorkflowError("Recover the actual original response lineage.")
        result.append(node["id"])
        if node["parent_id"] is None:
            return result
        node = game.action(c, node["parent_id"])


def projection(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    level = action["data"]["result"]["tier"]
    setter, victim = roles(action, level)
    body = json.loads(request["body_json"])
    result: dict[str, Any] = dict(level=level, affected_label=state.sheets[victim.entity].callsign)
    if request["kind"] == "beneath_select":
        sheet = state.sheets[victim.entity]
        result.update(
            tags=[
                dict(id=x.id, label=x.label) for x in sheet.tags if viewer.user_id in x.observers
            ],
            orders=[
                dict(id=x["id"], label=json.loads(x["body_json"])["text"][:90])
                for x in orders(game, c, setter, action["channel_id"])
            ],
        )
    elif request["kind"] == "beneath_details":
        result.update(options=body["options"], bonds=bonds(game, c, state, victim))
    return result


def results(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    setter, _ = roles(action, action["data"]["result"]["tier"])
    game.request(c, action, int(setter.entity), "beneath_select")


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    kind = request["kind"]
    if kind == "beneath_pin_response":
        if answer.options == ("play",):
            if (
                answer.denied
                or answer.fields
                or answer.flag is not None
                or answer.member is not None
                or answer.number is not None
            ):
                raise WorkflowError("Continue to your own real response Play.")
            action["data"]["result"]["pinned_response_kind"] = "play"
            game.request(c, action, int(request["actor_id"]), "beneath_response_play")
            return
        if (
            not answer.text.strip()
            or answer.options not in ((), ("narrative",))
            or answer.denied
            or answer.fields
            or answer.flag is not None
            or answer.member is not None
            or answer.number is not None
        ):
            raise WorkflowError("The pinned character's human describes their own next response.")
        action["data"]["result"]["pinned_response"] = answer.text
        state.facts.append(
            dict(
                kind="pin_response",
                action=action["id"],
                owner=request["actor_id"],
                text=answer.text,
            )
        )
        if not game.pending(c, action["id"]):
            ChoiceEngine(game).finish(c, state, action)
        return
    if kind not in ("beneath_select", "beneath_details"):
        raise WorkflowError(
            "REQUIRED_FOLLOWUP: this actual consequence needs its source-backed resolver."
        )
    level = action["data"]["result"]["tier"]
    setter, victim = roles(action, level)
    selected = answer
    body = json.loads(request["body_json"])
    source_choice = request["id"]
    peer = None
    asset = None
    if kind == "beneath_select":
        if (
            str(request["actor_id"]) != setter.entity
            or answer.denied
            or answer.member is not None
            or answer.flag is not None
            or answer.number is not None
        ):
            raise WorkflowError("Only the actual tier's choice owner selects these effects.")
        rules.choices(level, answer.options)
        if (
            not answer.text.strip()
            or set(answer.fields) - {"tag", "locked_tag", "order"}
            or bool(answer.fields.get("tag", "").strip()) != ("tag" in answer.options)
            or bool(answer.fields.get("locked_tag")) != ("lock_tag" in answer.options)
        ):
            raise WorkflowError("Supply the selected effects' actual Tag and Conversation details.")
        if "bond" in answer.options or "damage" in answer.options:
            if selected.fields.get("order"):
                raise WorkflowError("Order authority applies only to Punishment.")
            if "bond" in answer.options and not bonds(game, c, state, victim):
                raise WorkflowError(
                    "There is no existing actual Bond to weaken; choose legal effects."
                )
            game.request(
                c,
                action,
                int(victim.entity),
                "beneath_details",
                dict(options=list(answer.options), source_choice=request["id"]),
            )
            return
    else:
        if (
            str(request["actor_id"]) != victim.entity
            or answer.options
            or answer.flag is not None
            or answer.member is not None
            or answer.number is not None
            or answer.text
        ):
            raise WorkflowError(
                "The affected human selects only their actual private resource details."
            )
        selected = ChoiceAnswer.model_validate_json(
            json.dumps(action["data"]["choices"]["beneath_select:" + setter.entity])
        )
        source_choice = body["source_choice"]
        if "bond" in selected.options:
            if set(answer.fields) != {"bond"} or answer.denied:
                raise WorkflowError("Choose one of your actual existing Bonds.")
            known = {x["token"]: x for x in bonds(game, c, state, victim)}
            option = known.get(answer.fields["bond"])
            if option is None:
                raise WorkflowError("This actual Bond changed; reopen your private choices.")
            peer = ActorRef.model_validate_json(json.dumps(option["ref"]))
        else:
            if len(answer.denied) != 1 or answer.fields:
                raise WorkflowError(
                    "Choose one actual undamaged owned Asset for the counterattack."
                )
            asset = answer.denied[0]
    authority = None
    if selected.fields.get("order"):
        if "punish" not in selected.options:
            raise WorkflowError("Order authority applies only to Punishment.")
        actual = next(
            (
                x
                for x in orders(game, c, setter, action["channel_id"])
                if x["id"] == selected.fields["order"]
            ),
            None,
        )
        if actual is None or not higher(state, int(actual["issuer_id"]), int(setter.entity)):
            raise WorkflowError("Use an actual followed order from the current superior.")
        authority = rules.Authority(
            order_id=actual["id"], issuer=int(actual["issuer_id"]), recipient=setter
        )
    meta = action["data"]["beneath"]
    outcome = rules.apply(
        state,
        profiles(c, game.store.campaign_id),
        ActorRef.model_validate_json(json.dumps(meta["actor"])),
        ActorRef.model_validate_json(json.dumps(meta["target"])),
        level,
        rules.Decision(
            options=selected.options,
            text=selected.text,
            tag=selected.fields.get("tag", ""),
            locked_tag=selected.fields.get("locked_tag"),
            bond=peer,
            asset=asset,
        ),
        action["id"],
        source_choice,
        tuple(action["data"]["participants"]),
        authority=authority,
        actor_piloting=action["data"]["prepared"]["piloting"],
        source_event=action["data"]["response_event"],
    )
    for name in GameState.model_fields:
        setattr(state, name, getattr(outcome.state, name))
    for gate in state.obligations:
        if gate.id == action["id"] + ":consent:" + source_choice:
            gate.details["effect_choice"] = request["id"]
    action["data"]["result"]["beneath_effects"] = list(selected.options)
    for followup in outcome.followups:
        work_id = str(
            uuid5(
                NAMESPACE_URL,
                "girlframe:beneath:" + action["id"] + ":" + source_choice + ":" + followup.kind,
            )
        )
        game.request(
            c,
            action,
            int(followup.owner.entity),
            "beneath_" + followup.kind,
            dict(
                owner=followup.owner.model_dump(mode="json"),
                target=followup.target.model_dump(mode="json"),
                work_id=work_id,
            ),
        )
        if followup.kind == "punishment":
            pending = next(
                x for x in game.pending(c, action["id"]) if x["kind"] == "beneath_punishment"
            )
            action["data"]["beneath_work"] = dict(
                id=work_id,
                request=pending["id"],
                source_choice=source_choice,
                owner=followup.owner.model_dump(mode="json"),
                target=followup.target.model_dump(mode="json"),
            )
    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_work import related

    meta = action["data"].get("beneath_work")
    if not meta:
        return
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id)
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == meta["id"])
        .limit(1)
    ):
        return
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
        meta["id"],
        int(meta["owner"]["entity"]),
        int(meta["target"]["entity"]),
        "punishment",
        dict(
            reason=rules.PLAY,
            source_action=action["id"],
            source_choice=meta["source_choice"],
            continuation=meta["request"],
            source_pdf=22,
            immediate=True,
            discipline_owner_character=meta["owner"]["incarnation"],
        ),
        event,
    )


def work_root(game: "GameService", c: Connection, row: dict[str, Any]) -> dict[str, Any] | None:
    table = t.m3["m3_required_work"]
    seen: set[str] = set()
    while row["id"] not in seen:
        seen.add(row["id"])
        body = json.loads(row["body_json"])
        if body.get("reason") == rules.PLAY:
            return row
        parent = body.get("source_work")
        versions = body.get("work_versions", {})
        if parent is None and len(versions) == 1:
            parent = next(iter(versions))
        if parent is None:
            return None
        saved = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == game.store.campaign_id, table.c.id == parent)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if saved is None:
            raise WorkflowError("Recover the actual original discipline source chain.")
        row = dict(saved)
    raise WorkflowError("Recover the inconsistent discipline source chain.")


def discipline_action(
    game: "GameService", c: Connection, row: dict[str, Any], *, allow_archived: bool = False
) -> str | None:
    root = work_root(game, c, row)
    if root is None:
        return None
    body = json.loads(root["body_json"])
    action = game.action(c, body["source_action"])
    meta = action["data"].get("beneath_work")
    lock = game.lock(c, action["channel_id"])
    expected_root = lineage(game, c, action["id"])[-1]
    pending = next(
        (
            x
            for x in game.pending(c, action["id"])
            if x["id"] == body["continuation"] and x["kind"] == "beneath_punishment"
        ),
        None,
    )
    state = load_state(c, game.store.campaign_id)
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or "plays" not in approval.subsystems
        or (action["data"].get("m3_shared") or {}).get("registry") != approval.registry_sha256
    ):
        raise WorkflowError("M3_POLICY_CHANGED: recover the original social Play approval first.")
    if (
        meta is None
        or meta["id"] != root["id"]
        or root["scene_id"] != action["scene_id"]
        or action["state"] != "awaiting_choices"
        or pending is None
        or lock is None
        or lock["action_id"] != expected_root
        or lock["state"] != "held"
    ):
        raise WorkflowError(
            "REQUIRED_RECOVERY: resume the original held social Play before discipline."
        )
    game.action_characters(c, action, state, allow_archived=allow_archived)
    if allow_archived:
        from girlframe.engine.m3_careers import archive_for

        if archive_for(
            state,
            ActorRef(
                kind="pilot",
                entity=root["owner_id"],
                incarnation=body["discipline_owner_character"],
            ),
        ):
            return str(action["id"])
    if (
        game.character_binding(c, state, int(root["owner_id"]), require_current_profile=False)
        != body["discipline_owner_character"]
    ):
        raise WorkflowError("STALE_ACTOR: the original discipline owner changed characters.")
    return str(action["id"])


def discipline_finished(
    game: "GameService", c: Connection, viewer: GuildViewer, key: str, row: dict[str, Any]
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    root = work_root(game, c, row)
    if root is None:
        return
    action_id = discipline_action(game, c, row, allow_archived=True)
    assert action_id is not None
    table = t.m3["m3_required_work"]
    latest = {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id, table.c.scene_id == root["scene_id"]
            )
            .order_by(table.c.revision)
        ).mappings()
    }
    for work in latest.values():
        if work["state"] != "resolved":
            origin = work_root(game, c, work)
            if origin is not None and origin["id"] == root["id"]:
                return
    action = game.action(c, action_id)
    continuation = json.loads(root["body_json"])["continuation"]
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == continuation,
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    action["data"]["result"]["punishment_work"] = root["id"]
    state = load_state(c, game.store.campaign_id)
    if not game.pending(c, action_id):
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.beneath_discipline_completed",
        action_id=action_id,
        work_id=root["id"],
        event_index=10,
    )
