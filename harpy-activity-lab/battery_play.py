"""Web fields for Living Battery's engine-projected choices."""

from dataclasses import asdict

from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m2_ui import menu, text
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_janus_play import preview

BATTERY = "living_battery"
BATTERY_CHOICES = ("janus_erase", "janus_select", "janus_answer")


def ready_batteries(game, viewer, channel):
    targets = []
    for item in preview(game, viewer, channel).get("targets", ()):
        ref = ActorRef.model_validate(item["ref"])
        detail = preview(game, viewer, channel, ref)
        if detail.get("connection") and not detail["rolled"]:
            targets.append({"id": item["token"], "label": item["label"], "ref": item["ref"]})
    return targets


def battery_choice(game, viewer, identity, kind):
    detail = game.decision(viewer, identity)["janus"]
    if kind == "janus_answer":
        return {
            "schema": [asdict(text("text", "Your private brain response"))],
            "prompt": detail["question"],
        }
    if kind == "janus_erase":
        tags = tuple((row["id"], row["label"]) for row in detail["tags"])
        return {
            "schema": [asdict(Field("options", "Erase one actual battery Tag", tags))]
            if tags
            else []
        }
    fields = [
        Field(
            "options",
            "Choose printed benefits",
            tuple((row["id"], row["label"]) for row in detail["options"]),
            detail["count"],
            detail["count"],
        ),
        menu("number", "Heat only if selected", range(5)),
        text("text", "Private brain question, only if selected", False),
    ]
    if detail["universal"]:
        fields.append(text("fields.tag", "Optional Universal Plug Tag", False))
    identities = tuple((row["id"], row["label"]) for row in detail["identities"])
    if identities:
        fields.append(
            Field(
                "fields.identities",
                "Unmark up to two",
                identities,
                0,
                min(2, len(identities)),
                required=False,
            )
        )
    return {"schema": [asdict(field) for field in fields]}
