"""Owned Mockingbird conversation preparation and roll decisions."""

from dataclasses import asdict

from girlframe.discord_adapter.m2_ui import menu, text
from girlframe.discord_adapter.m3_mockingbird_plays import LABELS
from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird_state import PERSON
from girlframe.services.m2_state import load_state
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.onboarding import WorkflowError
from girlframe.engine.m3_mockingbird import require_departure

PERSON_CHOICES = (
    "mockingbird_person_capabilities",
    "mockingbird_person_tag",
    "mockingbird_person_agreement",
    "mockingbird_person_commit",
)


def person_choice(decision):
    detail = decision["mockingbird_play"]
    kind = decision["kind"]
    if kind == "mockingbird_person_capabilities":
        fields = [
            Field(
                "options",
                "Choose the capabilities you can use",
                tuple((key, LABELS[key]) for key in detail["capabilities"]),
                detail["minimum"],
                detail["maximum"],
                required=bool(detail["minimum"]),
            )
        ]
    elif kind == "mockingbird_person_tag":
        fields = [
            text(
                "text",
                "Tag based on unavailable: "
                + ", ".join(LABELS[key] for key in detail["unavailable"]),
            )
        ]
    elif kind == "mockingbird_person_agreement":
        fields = [menu("flag", "Accept this proposed Tag?", ("yes", "no"))]
    else:
        return {
            "fields": [],
            "fixed_answer": {"flag": True},
            "prompt": detail["proposed_tag"],
        }
    return {
        "fields": [asdict(field) for field in fields],
        "prompt": detail.get("proposed_tag"),
    }


def person_start(game, viewer, state, channel):
    service = MockingbirdService(game)
    actor = current_ref(state, viewer.user_id)
    try:
        view = service.preview(viewer, channel, actor)
    except WorkflowError as error:
        return {"reason": str(error)}
    if PERSON not in view["plays"]:
        return {
            "reason": "HarpyEngine has no available Bad at Being a Person rule for this pilot."
        }
    ready = [
        trigger
        for trigger in state.mockingbird.triggers
        if trigger.actor == actor
        and trigger.play == PERSON
        and trigger.channel == channel
        and trigger.state == "ready"
    ]
    if ready:
        return {
            "sources": [{"id": record.id, "label": record.account} for record in ready]
        }
    return {
        "counterparts": [
            {"id": row["token"], "label": row["label"]} for row in view["targets"]
        ],
        "reason": None
        if view["targets"]
        else "Another eligible conversation participant is required.",
    }


def start_person(game, viewer, key, channel, data):
    service = MockingbirdService(game)
    with game.store.engine.connect() as c:
        state = load_state(c, game.store.campaign_id)
        actor = current_ref(state, viewer.user_id)
    target = data["target"]
    if (
        isinstance(target, list)
        and target
        and all(isinstance(item, str) for item in target)
    ):
        projection = service.preview(viewer, channel, actor)
        targets = {
            row["token"]: ActorRef.model_validate(row["ref"])
            for row in projection["targets"]
        }
        if not set(target) <= targets.keys():
            raise WorkflowError("Choose actual counterparts in this scene.")
        if projection["sheet_revision"] != data["character_revision"]:
            raise WorkflowError("Reopen this Play with the current character sheet.")
        return service.propose(
            viewer,
            key,
            channel,
            actor,
            PERSON,
            tuple(targets[item] for item in target),
            data["context"],
        )
    if not isinstance(target, str):
        raise WorkflowError("Choose an actual Mockingbird trigger.")
    record = service.get(viewer, target)
    body = record["body"]
    if not record["owner"] or body["channel"] != channel or body["play"] != PERSON:
        raise WorkflowError("Reopen the actual owned trigger in its original scene.")
    return game.begin(
        viewer,
        key,
        channel,
        data["character_revision"],
        PlayInput(
            play=PERSON,
            context=body["account"],
            trigger_confirmed=True,
            heat=data["heat"],
            source_work=target,
        ),
    )


def conversation_work(game, viewer, state, conversation):
    if conversation.ended_event:
        return []
    service = MockingbirdService(game)
    try:
        data = service.get(viewer, conversation.id)
    except WorkflowError:
        return []
    cards = []
    for party in conversation.counterparts:
        if not conversation.low or party.controller != viewer.user_id:
            continue
        token = party.actor.token
        cards.append(
            {
                "id": conversation.id + ":" + token,
                "revision": state.revision,
                "instruction": "Conversation departure · "
                + data["party_labels"][token],
                "action": "mockingbird_release",
                "fields": [
                    {
                        "key": "allow",
                        "label": "Allow the speaker to leave?",
                        "required": True,
                        "options": [("yes", "Allow"), ("no", "Refuse")],
                    }
                ],
            }
        )
    if data["owner"]:
        waiting = None
        try:
            require_departure(
                state, ActorRef.model_validate(data["current_actor"]), conversation.id
            )
        except ValueError as error:
            waiting = str(error)
        cards.append(
            {
                "id": conversation.id,
                "revision": state.revision,
                "instruction": "End conversation",
                "scene": waiting,
                "read_only": bool(waiting),
                "action": None if waiting else "mockingbird_end",
            }
        )
    return cards


def complete_conversation(game, viewer, key, root, state, identity, action, answer):
    service = MockingbirdService(game)
    entry = next(
        (item for item in state.mockingbird.conversations if item.action == root), None
    )
    if entry is None:
        raise WorkflowError("Open the original conversation.")
    data = service.get(viewer, entry.id)
    if action == "mockingbird_end" and entry.id == identity and answer == {}:
        return service.end(
            viewer, key, entry.id, ActorRef.model_validate(data["current_actor"])
        )
    if (
        action == "mockingbird_release"
        and isinstance(answer, dict)
        and answer.get("allow") in ("yes", "no")
    ):
        party = next(
            (
                item.actor
                for item in entry.counterparts
                if identity == entry.id + ":" + item.actor.token
            ),
            None,
        )
        if party:
            return service.release(
                viewer, key, entry.id, party, answer["allow"] == "yes"
            )
    raise ValueError("Choose your role's conversation response.")
