"""Mandatory Defeat uses the shared actual dice, owned choices and held-scene pipeline."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_defeat as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_defeat_state import Alternative, Decision, NewVoidAsset
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RESPONSE_KINDS = ("beneath_defeat", "required_defeat")


def work(game: "GameService", c: Connection, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "defeat" or row["state"] == "resolved":
        raise WorkflowError("Resume the actual original pending Defeat consequence.")
    return dict(row)


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays")
    if action:
        meta = action["data"]["defeat"]
        approval = game.store.policy.m3_approval
        if approval is None or meta["registry"] != approval.registry_sha256:
            raise WorkflowError("M3_POLICY_CHANGED: recover the original Defeat release approval.")
        game.action_characters(c, action, load_state(c, game.store.campaign_id))


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, prepared: PlayInput, state: GameState
) -> dict[str, Any]:
    authorize(game, c, viewer)
    if (
        prepared.heat
        or prepared.identity is not None
        or prepared.gain
        or prepared.pair_share
        or prepared.target is not None
        or prepared.order_id is not None
        or prepared.witnessed
        or prepared.off_duty_id is not None
    ):
        raise WorkflowError(
            "Defeat rolls with undamaged Girl Assets, without Heat or Identity gain."
        )
    actor = ActorRef(
        kind="pilot",
        entity=str(viewer.user_id),
        incarnation=game.character_binding(
            c,
            state,
            viewer.user_id,
            require_current_profile=False,
        ),
    )
    source_work = None
    source_request = None
    if prepared.source_work:
        source_work = work(game, c, prepared.source_work)
        body = json.loads(source_work["body_json"])
        if source_work["owner_id"] != actor.entity or body.get("character") != actor.incarnation:
            raise WorkflowError("This Defeat belongs to a different original character.")
        battle_damage = isinstance(body.get("requirement"), dict)
        if battle_damage:
            from girlframe.services.m3_battle import source_parent_for_defeat

            if source_parent_for_defeat(game, c, source_work, actor) != prepared.parent:
                raise WorkflowError("Use the actual original damage source for this Defeat.")
        if prepared.parent:
            from girlframe.services.m3_beneath import discipline_action

            if not battle_damage and discipline_action(game, c, source_work) != prepared.parent:
                raise WorkflowError("Use the actual held source Play for this Defeat.")
            parent = game.action(c, prepared.parent)
            source_request = next(
                (
                    x
                    for x in game.pending(c, parent["id"])
                    if x["kind"] in ("required_defeat", "battle_defeat")
                    and x["actor_id"] == actor.entity
                    and json.loads(x["body_json"]).get("work_id") == source_work["id"]
                ),
                None,
            )
            if source_request is None:
                game.request(
                    c,
                    parent,
                    viewer.user_id,
                    "required_defeat",
                    dict(work_id=source_work["id"], actor=actor.model_dump(mode="json")),
                )
                game.save_action(c, parent)
                source_request = next(
                    x
                    for x in game.pending(c, parent["id"])
                    if x["kind"] == "required_defeat" and x["actor_id"] == actor.entity
                )
    elif prepared.parent:
        parent = game.action(c, prepared.parent)
        source_request = next(
            (
                x
                for x in game.pending(c, parent["id"])
                if x["kind"] in RESPONSE_KINDS and x["actor_id"] == actor.entity
            ),
            None,
        )
        if source_request is None:
            raise WorkflowError("Defeat needs its actual pending source consequence.")
        body = json.loads(source_request["body_json"])
        recorded = body.get("actor", body.get("owner"))
        if recorded and ActorRef.model_validate_json(json.dumps(recorded)) != actor:
            raise WorkflowError("The required Defeat belongs to another character incarnation.")
    else:
        raise WorkflowError("Defeat requires an actual source Play or required-work receipt.")
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        modifier=rules.modifier(state, actor, profiles(c, game.store.campaign_id)),
        source_request=source_request["id"] if source_request else None,
        source_work=source_work["id"] if source_work else None,
        registry=game.store.policy.m3_approval.registry_sha256,
    )


def results(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    game.request(c, action, int(action["actor_id"]), "defeat_select")


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    sheet = state.sheets[action["actor_id"]]
    data: dict[str, Any] = dict(offer=action["data"].get("defeat_offer"))
    if request["kind"] == "defeat_alternative":
        data.update(
            assets=[
                dict(id=x.id, name=x.name) for x in sheet.assets if not x.void and not x.intrinsic
            ],
            identities=[dict(id=x.id, name=x.name) for x in sheet.identities if not x.protected],
            permissions=sheet.permissions,
            foes=foes(game, c, state, action),
        )
    if data["offer"] is not None:
        offer = data["offer"]
        data["offer"] = offer | dict(
            asset_names=[x.name for x in sheet.assets if x.id in offer["assets_removed"]],
            identity_names=[
                x.name for x in sheet.identities if x.id in offer["identities_removed"]
            ],
            foe_label=next(
                (
                    x["label"]
                    for x in foes(game, c, state, action)
                    if x["ref"] == offer.get("helpless_foe")
                ),
                "Original opposing actor",
            ),
        )
    return data


def foes(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actors import resolve

    cast = next((x for x in state.scene_casts if x.id == action["scene_id"] and x.open), None)
    refs = (
        [x.actor for x in cast.roles]
        if cast
        else [
            current_ref(state, uid)
            for uid in action["data"]["participants"]
            if str(uid) in state.sheets
        ]
    )
    result = []
    for ref in refs:
        if ref.kind == "pilot" and ref.entity == action["actor_id"]:
            continue
        try:
            actual = resolve(
                state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
            )
        except ValueError:
            continue
        result.append(dict(token=ref.token, label=actual.label, ref=ref.model_dump(mode="json")))
    return result


def start_work(
    game: "GameService", viewer: GuildViewer, key: str, identity: str, channel: int, account: str
) -> dict[str, Any]:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        row = work(game, c, identity)
        if row["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only the actual affected original Girl may begin Defeat.")
        scene = game.scene(c, channel)
        if row["scene_id"] is not None and row["scene_id"] != scene["id"]:
            raise WorkflowError("Use the actual source scene channel for this Defeat.")
        from girlframe.services.m3_beneath import discipline_action

        parent = discipline_action(game, c, row)
        if parent is None:
            candidate = json.loads(row["body_json"]).get("source_action")
            if candidate:
                original = game.action(c, candidate)
                if original["state"] not in ("complete", "aborted"):
                    parent = candidate
        sheet = load_state(c, game.store.campaign_id).sheets[str(viewer.user_id)]
    return game.begin(
        viewer,
        key,
        channel,
        sheet.revision,
        PlayInput(
            play="defeat",
            heat=0,
            context=account,
            trigger_confirmed=True,
            parent=parent,
            source_work=identity,
        ),
    )


def _ref(
    game: "GameService", c: Connection, state: GameState, value: str | None
) -> ActorRef | None:
    if not value:
        return None
    if not value.isdecimal():
        raise WorkflowError("Choose an actual Girl from the current scene selector.")
    return ActorRef(
        kind="pilot",
        entity=value,
        incarnation=game.character_binding(
            c,
            state,
            int(value),
            require_current_profile=False,
        ),
    )


def decision(
    game: "GameService", c: Connection, state: GameState, answer: ChoiceAnswer
) -> Decision:
    known = {
        "girl_name",
        "girl_description",
        "girl_replace",
        "frame_name",
        "frame_description",
        "frame_replace",
        "rescuer",
        "tag_giver",
        "girl_playbook",
        "amnesiac_slot",
    }
    if (
        answer.denied
        or answer.number is not None
        or answer.member is not None
        or answer.flag is not None
        or set(answer.fields) - known
    ):
        raise WorkflowError("Supply exactly your selected Defeat effects and their actual details.")
    assets = {}
    for family in ("girl", "frame"):
        if any(
            answer.fields.get(family + suffix) for suffix in ("_name", "_description", "_replace")
        ):
            assets[family + "_asset"] = NewVoidAsset(
                name=answer.fields.get(family + "_name", ""),
                description=answer.fields.get(family + "_description", ""),
                replace=answer.fields.get(family + "_replace") or None,
            )
    return Decision(
        options=answer.options,
        account=answer.text,
        rescuer=_ref(game, c, state, answer.fields.get("rescuer")),
        tag_giver=_ref(game, c, state, answer.fields.get("tag_giver")),
        girl_playbook=answer.fields.get("girl_playbook") or None,
        amnesiac_slot=int(answer.fields["amnesiac_slot"])
        if answer.fields.get("amnesiac_slot")
        else None,
        **assets,
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    actor = ActorRef.model_validate_json(json.dumps(action["data"]["defeat"]["actor"]))
    kind = request["kind"]
    if kind == "defeat_tag_gift":
        if (
            answer.options not in (("give",), ("decline",))
            or answer.denied
            or answer.fields
            or answer.member is not None
            or answer.number is not None
            or answer.flag is not None
        ):
            raise WorkflowError("The invited original Girl may give the Tag or explicitly decline.")
        if answer.options == ("give",):
            if not answer.text.strip() or len(answer.text) > 120:
                raise WorkflowError("Write the actual Tag in 1–120 characters.")
            giver = int(request["actor_id"])
            state.sheets[actor.entity].tags.append(
                TagState(
                    id=request["id"] + ":tag",
                    label=answer.text.strip(),
                    giver=giver,
                    observers=tuple(action["data"]["participants"]),
                    giver_character=game.character_binding(
                        c, state, giver, require_current_profile=False
                    ),
                )
            )
            state.sheets[actor.entity].revision += 1
        if not game.pending(c, action["id"]):
            ChoiceEngine(game).finish(c, state, action)
        return
    if kind == "defeat_alternative":
        if int(request["actor_id"]) != state.handler or answer.flag is not True:
            raise WorkflowError(
                "The current Handler must explicitly confirm an equally ruinous offer."
            )
        if (
            answer.options
            or answer.denied
            or answer.member is not None
            or set(answer.fields) - {"assets", "identities", "tag", "helpless_foe", "frame_context"}
        ):
            raise WorkflowError("Choose the actual supported resource consequences of this offer.")
        foe = answer.fields.get("helpless_foe")
        chosen_foe = next((x for x in foes(game, c, state, action) if x["token"] == foe), None)
        if foe and chosen_foe is None:
            raise WorkflowError("Choose the actual opposing actor from this original scene.")
        context = answer.fields.get("frame_context", "unspecified")
        if context not in ("unspecified", "inside", "outside"):
            raise WorkflowError("Confirm actual Frame context from the native selector.")
        if action["data"]["prepared"]["piloting"] and context == "outside":
            raise WorkflowError("This original Defeat records the Girl piloting her Frame.")
        proposed_offer = Alternative(
            account=answer.text,
            equally_ruinous_confirmed=True,
            permissions_lost=answer.number or 0,
            assets_removed=tuple(filter(None, answer.fields.get("assets", "").split(","))),
            identities_removed=tuple(filter(None, answer.fields.get("identities", "").split(","))),
            tag=answer.fields.get("tag", ""),
            helpless_foe=ActorRef.model_validate_json(json.dumps(chosen_foe["ref"]))
            if chosen_foe
            else None,
            outside_frame=(context == "outside") if context != "unspecified" else None,
        )
        test = GameState.model_validate_json(state.model_dump_json())
        rules.alternative(test, actor, proposed_offer, action["id"])
        action["data"]["defeat_offer"] = proposed_offer.model_dump(mode="json")
        game.request(c, action, int(actor.entity), "defeat_accept_alternative")
        return
    offer: Alternative | None = None
    if kind == "defeat_accept_alternative":
        if (
            answer.flag is None
            or answer.options
            or answer.denied
            or answer.fields
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError("Accept or decline only your actual Handler offer.")
        if not answer.flag:
            action["data"].pop("defeat_offer", None)
            game.request(c, action, int(actor.entity), "defeat_select")
            return
        chosen = Decision.model_validate_json(json.dumps(action["data"]["defeat_selected"]))
        offer = Alternative.model_validate_json(json.dumps(action["data"]["defeat_offer"]))
    elif kind == "defeat_select":
        chosen = decision(game, c, state, answer)
        for ref in (chosen.rescuer, chosen.tag_giver):
            if ref is not None and int(ref.entity) not in action["data"]["participants"]:
                raise WorkflowError("Choose another actual Girl in this original scene.")
        action["data"]["defeat_selected"] = chosen.model_dump(mode="json")
    else:
        raise WorkflowError("Choose the source-specific owned Defeat resolver.")
    source = action["data"]["response_event"]
    outcome = rules.apply(
        state,
        actor,
        profiles(c, game.store.campaign_id),
        action["data"]["result"]["total"],
        chosen,
        action["id"],
        source,
        offer=offer,
        prior_event=action["data"]["defeat"]["roll_event"],
    )
    for field in GameState.model_fields:
        setattr(state, field, getattr(outcome.state, field))
    for followup in outcome.followups:
        if followup.kind == "alternative":
            game.request(c, action, int(followup.owner.entity), "defeat_alternative")
        elif followup.kind == "tag_gift":
            game.request(c, action, int(followup.owner.entity), "defeat_tag_gift")
        elif followup.kind == "death":
            from girlframe.engine.m3_careers import end

            profile = c.execute(
                sa.select(t.characters.c.id, t.characters.c.revision).where(
                    t.characters.c.campaign_id == game.store.campaign_id,
                    t.characters.c.user_id == actor.entity,
                )
            ).one()
            ended = end(
                state,
                actor,
                reason="death",
                source_event=source,
                account=chosen.account,
                archive_id=str(uuid5(NAMESPACE_URL, "girlframe:defeat-death:" + action["id"])),
                profile_id=profile.id,
                profile_revision=profile.revision,
            )
            for field in GameState.model_fields:
                setattr(state, field, getattr(ended, field))
        else:
            index = len(action["data"].get("defeat_followups", []))
            action["data"].setdefault("defeat_followups", []).append(
                followup.model_dump(mode="json")
            )
            if followup.kind == "void_threshold":
                identity = str(
                    uuid5(NAMESPACE_URL, "girlframe:defeat:" + action["id"] + ":" + str(index))
                )
                game.request(
                    c,
                    action,
                    int(actor.entity),
                    "defeat_void_threshold",
                    dict(work_id=identity, actor=actor.model_dump(mode="json")),
                )
    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)


def synchronize(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    from girlframe.services.m3_work import related

    state = load_state(c, game.store.campaign_id)
    from girlframe.services.m3_careers import synchronize_end
    from girlframe.services.m3_girl_transition import synchronize as synchronize_girl_transition

    synchronize_girl_transition(c, game.store, action, event)

    current_work = action["data"]["defeat"].get("source_work")
    for archive in state.career_archives:
        if archive.source_event == event:
            synchronize_end(c, game, archive, exclude_work=(current_work,) if current_work else ())
    for index, followup in enumerate(action["data"].get("defeat_followups", [])):
        identity = str(uuid5(NAMESPACE_URL, "girlframe:defeat:" + action["id"] + ":" + str(index)))
        table = t.m3["m3_required_work"]
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .limit(1)
        ):
            continue
        future = followup["kind"] in ("medical_wake", "frame_replacement")
        context = (
            dict(campaign_id=game.store.campaign_id, campaign_context=True)
            if future
            else dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"])
        )
        related(
            c,
            game.store,
            context,
            identity,
            int(followup["owner"]["entity"]),
            int(action["actor_id"]),
            "defeat_" + followup["kind"],
            followup
            | dict(
                source_action=action["id"],
                character=action["data"]["defeat"]["actor"]["incarnation"],
                immediate=not future,
            ),
            event,
        )
    source_work = action["data"]["defeat"].get("source_work")
    if action["state"] == "complete" and source_work:
        row = work(game, c, source_work)
        body = json.loads(row["body_json"]) | dict(resolved_action=action["id"])
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "event_id", "body_json")
                },
                revision=row["revision"] + 1,
                state="resolved",
                event_id=event,
                body_json=json.dumps(body, sort_keys=True),
            )
        )
        if isinstance(body.get("requirement"), dict):
            from girlframe.services.m3_battle import complete_damage_work, source_parent_for_defeat

            source_parent_for_defeat(
                game,
                c,
                row,
                ActorRef.model_validate_json(json.dumps(action["data"]["defeat"]["actor"])),
            )
            complete_damage_work(game, c, row, event, viewer, key)
        else:
            from girlframe.services.m3_beneath import discipline_finished

            discipline_finished(game, c, viewer, key, row)


def complete_void_continuation(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    """Release only a source-proved continuation after its actual Void work resolves."""
    from girlframe.services.m2_choices import ChoiceEngine

    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "defeat_void_threshold" or row["state"] != "resolved":
        raise WorkflowError("Complete the actual original Void threshold before resuming Defeat.")
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    if action["state"] == "complete":
        return
    if action["data"].get("defeat", {}).get("actor", {}).get("incarnation") != body["character"]:
        raise WorkflowError("The Void continuation belongs to a different original character.")
    pending = [
        r
        for r in game.pending(c, action["id"])
        if r["kind"] == "defeat_void_threshold"
        and json.loads(r["body_json"]).get("work_id") == identity
        and r["actor_id"] == row["subject_id"]
    ]
    if len(pending) != 1 or row["event_id"] != event:
        raise WorkflowError("Recover the actual resolved Void event and held Defeat linkage.")
    state = load_state(c, game.store.campaign_id)
    game.action_characters(c, action, state, allow_archived=True)
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == pending[0]["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    action["data"]["result"].setdefault("void_work", []).append(identity)
    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)
    synchronize(game, c, action, event, viewer, key)
    event_index = (
        int(
            c.scalar(
                sa.select(sa.func.max(t.events.c.event_index)).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.command_key == key,
                )
            )
            or 0
        )
        + 1
    )
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.defeat_void_completed",
        action_id=action["id"],
        work_id=identity,
        event_index=event_index,
    )
