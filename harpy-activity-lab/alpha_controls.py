"""Brutalize results and real source-bound counters for the original actor."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import m3_npc_guard
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_guard import GuardService
from girlframe.services.onboarding import WorkflowError

BRUTALIZE = "brutalize"
COUNTER = "alpha_counter_play"
RESULTS = frozenset({"alpha_damage", "alpha_low", "alpha_npc_damage", "alpha_npc_mercy"})
COUNTERS = {
    "keep_your_head": "Keep Your Head",
    "flirt": "Flirt",
    "put_someone_beneath_you": "Put Someone Beneath You",
    "old_dog_new_pups": "Old Dog, New Pups",
    BRUTALIZE: "Brutalize",
    "dose_up": "Dose Up",
    "easy_target": "Easy Target",
    "unassuming_doll": "Unassuming Doll",
}


def result_fields(decision):
    detail = decision["alpha"]
    kind = decision["kind"]
    if kind == "alpha_damage":
        return [Field("choice", "Damage one actual Girl Asset", tuple(
            (row["id"], row["label"]) for row in detail["assets"]
        ))]
    if kind == "alpha_npc_damage":
        if decision["result"]["tier"] == "high":
            return [Field("effect", "Printed high result", (("kill", "Apply the original result"),))]
        return [Field("injury", "Describe the actual injury", paragraph=True)]
    if kind == "alpha_npc_mercy":
        return [Field("choice", "After the Guard's original chance to respond", (
            ("spare", "Spare the NPC"), ("kill", "Kill the unarmed NPC"),
        ))]
    choices = [("pass", "Pass this opportunity")]
    if detail["can_counter"]:
        choices.extend((
            ("counter_broken", "Counter and leave the Alpha Broken"),
            ("counter_only", "Counter without Broken"),
        ))
    return [Field("choice", "Your actual counter opportunity", tuple(choices))]


def result_answer(kind, values):
    if kind == "alpha_npc_damage":
        if values == {"effect": "kill"}:
            return ChoiceAnswer(options=("kill",))
        if values.keys() == {"injury"}:
            return ChoiceAnswer(options=("injure",), text=values["injury"])
    if kind in RESULTS and kind != "alpha_npc_damage" and values.keys() == {"choice"}:
        return ChoiceAnswer(options=(values["choice"],))
    raise WorkflowError("File the decision from the original confrontation.")


def counter_fields(game, viewer, decision):
    detail = decision["alpha"]
    if detail.get("npc"):
        data = GuardService(game).counter(viewer, decision["parent"], decision["id"])
        moves = tuple(row for row in m3_npc_guard.MOVES if row[0] != "draw_weapon" or data["weapons"])
        fields = [Field("move", "Your Guard move", moves)]
        if data["weapons"]:
            fields.append(Field("weapon", "Actual weapon if drawing", tuple(
                (row["id"], row["label"]) for row in data["weapons"]
            ), required=False))
        fields.append(Field("context", "What did the Guard do?", paragraph=True))
        return data["revision"], fields
    sheet = game.sheet(viewer)
    possible = tuple((key, COUNTERS[key]) for key in detail["counter_plays"] if key in COUNTERS)
    if not possible:
        raise WorkflowError("The actual assigned counter needs a supported Activity form.")
    identities = tuple(
        (row["id"], row["name"]) for row in sheet["identities"] + sheet.get("additional_identities", [])
        if not row["marked"]
    )
    fields = [
        Field("play", "Your counter Play", possible),
        Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet["heat"] + (6 if identities else 1)))),
        Field("context", "Describe your actual counter", paragraph=True),
    ]
    if "put_someone_beneath_you" in dict(possible):
        fields.append(Field("piloting", "Beneath only · Are you actually piloting?", (
            ("no", "No"), ("yes", "Yes"),
        ), required=False))
    if "dose_up" in dict(possible) and sheet["girl"] == "STIM-BLISSED":
        fields.append(Field("disposable_heat", "Dose Up only · Remove the marked Identity?", (
            ("0", "Keep it"), ("3", "Remove it for 3 Heat"), ("4", "Remove it for 4 Heat"),
        ), required=False))
    if identities:
        fields.extend((
            Field("identity", "Optional Identity to mark", identities, required=False),
            Field("gain", "Heat gained from marking", tuple((str(n), str(n)) for n in range(6)), required=False),
        ))
    return sheet["revision"], fields


def perform_counter(game, viewer, key, action, identity, revision, values):
    original = action["data"]["alpha"]
    if original["target"]["kind"] == "npc":
        required = {"move", "context"}
        if not required <= values.keys() or values.keys() - required - {"weapon"}:
            raise ValueError("Use the original Guard fields.")
        return GuardService(game).perform_counter(
            viewer, key, action["id"], identity, revision, values["move"], values["context"],
            values.get("weapon") or None,
        )
    required = {"play", "heat", "context"}
    if not required <= values.keys() <= required | {"identity", "gain", "piloting", "disposable_heat"} or values["play"] not in COUNTERS:
        raise ValueError("Use the current native counter fields.")
    play = values["play"]
    piloting = values.get("piloting") == "yes"
    disposable = int(values.get("disposable_heat") or "0")
    if (piloting and play != "put_someone_beneath_you") or (disposable and play != "dose_up"):
        raise ValueError("Use the occupancy and Identity choices only for the matching counter.")
    target = ActorRef.model_validate(original["actor"])
    return game.begin(viewer, key, int(action["channel_id"]), revision, PlayInput(
        play=play, parent=action["id"],
        target=int(target.entity) if play in ("flirt", "put_someone_beneath_you", "old_dog_new_pups") else None,
        target_actor=target if play in (BRUTALIZE, "unassuming_doll") else None,
        trigger_confirmed=True, heat=int(values["heat"]), context=values["context"],
        identity=values.get("identity") or None, gain=int(values.get("gain") or "0"),
        piloting=piloting, disposable_heat=disposable,
    ))
