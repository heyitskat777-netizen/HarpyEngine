"""Native JANUS and Wyvern controls scoped to the Battlefield scene."""

import json

import sqlalchemy as sa
from consume_regrowth import KIND as PARTAKE
from consume_regrowth import regrowth_answer, regrowth_operations
from play_continuations import ACCOUNT, YES_NO, field, operation

from girlframe.database import tables
from girlframe.engine import m3_wyvern as wyvern
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, spend_heat
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_state import load_state
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.m3_janus_play import preview as battery_preview
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.m3_wyvern import WyvernService
from girlframe.services.m3_wyvern_combat import WyvernCombatService
from girlframe.services.onboarding import WorkflowError

ROUSE = "wyvern_rouse"
ROUSE_COST = "wyvern_rouse_cost"
INTERCEPT = "battle_sprite_intercept"
COUNTER_PLAYS = {
    "keep_your_head": "Keep Your Head",
    "check_sensors": "Check Sensors",
}


def available_heat(sheet):
    amounts = []
    for value in range(sheet.heat + 1):
        try:
            spend_heat(sheet.model_copy(), value)
        except ValueError:
            continue
        amounts.append(value)
    return amounts


def heat_field(sheet):
    return field("heat", "Heat to spend", [(str(n), str(n)) for n in available_heat(sheet)])


def card(identity, revision, action, title, forms, description=None):
    return {
        "id": identity,
        "revision": revision,
        "action": action,
        "instruction": title,
        "operations": forms,
        "scene": description,
    }


def choice_fields(data):
    fields = []
    for slot in range(data["count"]):
        fields.append(
            field(
                f"identity_{slot}",
                f"Identity to erase · {slot + 1}",
                data["identities"],
            )
        )
        if tags := data.get("requirements", {}).get("mentor_tags", []):
            fields.append(
                field(
                    f"mentor_{slot}",
                    f"Mentor Tag for erasure {slot + 1}",
                    [(x["id"], x["label"]) for x in tags],
                    required=False,
                )
            )
    if data["heat"]:
        fields.append(field("heat", "Heat to gain", [(str(x), str(x)) for x in range(1, 11)]))
    return [*fields, ACCOUNT]


class BattlefieldFrameWork:
    def __init__(self, game, channel):
        self.game = game
        self.channel = channel
        self.neural = FrameControlService(game)
        self.wyvern = WyvernService(game)
        self.combat = WyvernCombatService(game)
        self.sprites = SpriteService(game.store)

    def view(self, viewer, *, proactive=True, busy=False):
        with self.game.store.engine.connect() as c:
            state = load_state(c, self.game.store.campaign_id)
            try:
                self.game.unpaused(c)
            except WorkflowError:
                return []
            sheet = state.sheets.get(str(viewer.user_id))
            connections = self.neural._tasks(c, viewer) if state.neural_connections else []
            connected = {
                value.id for value in state.neural_connections if value.cast.channel == self.channel
            }
        cards = []
        for task in connections:
            if task["id"] not in connected:
                continue
            saved = self.neural.get(viewer, task["id"])
            phase = saved["connection"]["phase"]
            forms = []
            if saved["can_act"]:
                title = "Confirm contact" if phase == "target" else "Review the spinal connection"
                forms = [
                    operation(
                        "decide",
                        title,
                        [
                            field("allowed", "Confirm or refuse", YES_NO),
                            ACCOUNT,
                        ],
                    )
                ]
            elif saved["can_unplug"]:
                forms = [operation("unplug", "Unplug", [ACCOUNT])]
            cards.append(
                card(
                    saved["id"],
                    saved["revision"],
                    "janus_connection",
                    "JANUS · Neural contact · " + phase,
                    forms,
                    saved["connection"]["account"]
                    if saved["can_act"]
                    else "Waiting for the assigned participant."
                    if phase != "connected"
                    else None,
                )
            )
        if proactive and not busy and sheet and sheet.frame == "JANUS":
            preview = battery_preview(self.game, viewer, self.channel)
            actor = preview.get("actor")
            has_port = any(
                value.phase in ("target", "review", "connected")
                and actor
                in (
                    value.caster.model_dump(mode="json"),
                    value.battery.model_dump(mode="json"),
                )
                for value in state.neural_connections
            )
            if preview.get("available") and not has_port:
                cards.append(
                    card(
                        "janus",
                        state.revision,
                        "janus_start",
                        "JANUS · Neural contact",
                        [
                            operation(
                                "connect",
                                "Request neural contact",
                                [
                                    field(
                                        "target",
                                        "Battery",
                                        [(x["token"], x["label"]) for x in preview["targets"]],
                                    ),
                                    field(
                                        "account",
                                        "Describe the jack, exposure, reach, and performed contact",
                                    ),
                                ],
                            ),
                        ],
                    )
                )
        if sheet and sheet.frame == wyvern.FRAME:
            self.wyvern_starts(viewer, cards, proactive, busy, sheet)
            with self.game.store.engine.connect() as c:
                scene = self.game.scene(c, self.channel)
                lock = self.game.lock(c, self.channel)
                reserved = self.game.action(c, lock["action_id"]) if scene and lock else None
            if (
                reserved
                and reserved["data"]["play"] == ROUSE
                and reserved["actor_id"] == str(viewer.user_id)
            ) and (roll := self.roll_form(viewer, reserved["id"])):
                cards.append(
                    card(
                        reserved["id"],
                        state.revision,
                        "wyvern_roll",
                        "Wyvern · Rouse the Frame",
                        [roll],
                    )
                )
        try:
            tasks = self.combat.menu(viewer)["tasks"]
        except (WorkflowError, ValueError):
            tasks = []
        for task in tasks:
            if task["phase"] == "complete":
                continue
            data = self.combat.view(viewer, task["id"])
            if data["counter"]["channel"] != self.channel:
                continue
            forms = self.combat_operations(viewer, sheet, data)
            cards.append(
                card(
                    data["id"],
                    data["revision"],
                    "wyvern_source",
                    "Wyvern · " + data["label"],
                    forms,
                    data["summary"],
                )
            )
            if sheet:
                cards[-1]["game_revision"] = sheet.revision
        for choice in self.game.choices(viewer):
            if choice["kind"] not in (PARTAKE, ROUSE_COST, INTERCEPT):
                continue
            decision = self.game.decision(viewer, choice["id"])
            if decision["channel"] != self.channel:
                continue
            if choice["kind"] == INTERCEPT:
                work = self.sprites.get(viewer, decision["work_id"])
                if not work["answered"] and work["phase"] == "choose":
                    sprite = card(
                        choice["id"],
                        work["revision"],
                        INTERCEPT,
                        "Sprite · Interception",
                        [
                            operation(
                                "intercept",
                                "File the Sprite response",
                                [
                                    field(
                                        "target",
                                        "Your interception",
                                        [
                                            ("pass", "Decline interception"),
                                            *[
                                                (
                                                    json.dumps(
                                                        {
                                                            "actor": x["actor"],
                                                            "asset": x["asset"],
                                                        }
                                                    ),
                                                    x["label"],
                                                )
                                                for x in work["options"]
                                            ],
                                        ],
                                    ),
                                    ACCOUNT,
                                ],
                            )
                        ],
                    )
                    cards.append(sprite | {"game_revision": work["game_revision"]})
                continue
            data = decision["detail"]
            forms = (
                regrowth_operations(data, field, operation, ACCOUNT)
                if choice["kind"] == PARTAKE
                else [operation("cost", "File the Rouse cost", choice_fields(data))]
            )
            cards.append(
                card(
                    choice["id"],
                    choice["revision"],
                    choice["kind"],
                    "CONSUME · Let Us Partake"
                    if choice["kind"] == PARTAKE
                    else "Wyvern · Rouse cost",
                    forms,
                    f"Available Frame capacity: {data['regrow_free']}."
                    if choice["kind"] == PARTAKE
                    else None,
                )
            )
        return cards

    def wyvern_starts(self, viewer, cards, proactive, busy, sheet):
        try:
            candidates = self.wyvern.roused_options(viewer, self.channel)
        except (ValueError, WorkflowError):
            candidates = None
        if candidates:
            options = [
                (json.dumps(row), row["label"])
                for row in candidates["options"]
                if row["kind"] == "too_big" or proactive
            ]
            if options:
                cards.append(
                    card(
                        "roused",
                        candidates["revision"],
                        "wyvern_use",
                        "Wyvern · Roused Frame",
                        [
                            operation(
                                "use",
                                "Commit Roused effect",
                                [field("use", "Effect", options)],
                            ),
                        ],
                    )
                )
            return
        if not proactive or busy:
            return
        try:
            menu = self.wyvern.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return
        if ROUSE in dict(menu["plays"]):
            cards.append(
                card(
                    "rouse",
                    sheet.revision,
                    "wyvern_start",
                    "Wyvern · Rouse the Frame",
                    [
                        operation(
                            "start",
                            "Start Rouse",
                            [
                                heat_field(sheet),
                                ACCOUNT,
                            ],
                        ),
                    ],
                )
            )

    def combat_operations(self, viewer, sheet, data):
        operations = []
        if data["can_release"]:
            operations.append(operation("release", "Release the pinned actor", [ACCOUNT]))
        if data["can_counter"] and sheet:
            blocked = {record.play for record in sheet.blocked_plays}
            if parent := data["counter"]["parent"]:
                with self.game.store.engine.connect() as c:
                    blocked.add(self.game.action(c, parent)["data"]["play"])
            operations.append(
                operation(
                    "counter",
                    "Start the source response",
                    [
                        field(
                            "play",
                            "Triggered Play",
                            [
                                (play, label)
                                for play, label in COUNTER_PLAYS.items()
                                if play not in blocked
                            ],
                        ),
                        heat_field(sheet),
                        ACCOUNT,
                    ],
                )
            )
        if data["can_resume"]:
            roll = self.roll_form(viewer, data["child"])
            if roll:
                operations.append(roll)
        return operations

    def roll_form(self, viewer, identity):
        saved = self.game.inspect(viewer, identity)
        if saved["state"] == "ready_to_roll":
            return operation("roll:" + identity, "Roll the reserved Play", [])
        return None

    def perform(self, viewer, key, data):
        action, identity, revision = (data[k] for k in ("action", "id", "revision"))
        op, values = (data["answer"][k] for k in ("operation", "values"))
        if action in (PARTAKE, ROUSE_COST, INTERCEPT):
            table = tables.m2["m2_choices"]
            with self.game.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                choice = c.execute(
                    sa.select(table.c.action_id, table.c.kind).where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.id == identity,
                        table.c.actor_id == str(viewer.user_id),
                    )
                ).first()
                if (
                    choice is None
                    or choice.kind != action
                    or self.game.action(c, choice.action_id)["channel_id"] != str(self.channel)
                ):
                    raise WorkflowError("Open your assigned Battlefield decision.")
            if action == INTERCEPT and op == "intercept":
                target = values["target"]
                selected = json.loads(target) if target != "pass" else None
                return self.sprites.respond(
                    viewer,
                    key,
                    self.sprites.choice_source(viewer, identity),
                    revision,
                    data["game_revision"],
                    ActorRef.model_validate(selected["actor"]) if selected else None,
                    selected["asset"] if selected else None,
                    values["account"],
                )
            if action == PARTAKE:
                response = regrowth_answer(op, values)
            elif op == "cost":
                picked = tuple(
                    values[f"identity_{i}"] for i in range(2) if f"identity_{i}" in values
                )
                mentors = {
                    name: values[f"mentor_{i}"]
                    for i, name in enumerate(picked)
                    if f"mentor_{i}" in values
                }
                response = ChoiceAnswer(
                    denied=picked,
                    number=int(values["heat"]) if "heat" in values else None,
                    fields={"mentor_tags": json.dumps(mentors)} if mentors else {},
                    text=values["account"],
                )
            else:
                raise WorkflowError("Open the original Rouse cost.")
            return self.game.respond(viewer, key, identity, revision, response)
        if action == "janus_start" and op == "connect":
            preview = battery_preview(self.game, viewer, self.channel)
            target = next(
                (x["ref"] for x in preview.get("targets", ()) if x["token"] == values["target"]),
                None,
            )
            if target is None:
                raise WorkflowError("Choose a battery HarpyEngine offers in this scene.")
            return self.neural.propose(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate(preview["actor"]),
                ActorRef.model_validate(target),
                values["account"],
            )
        if action == "janus_connection":
            saved = self.neural.get(viewer, identity)
            if saved["connection"]["cast"]["channel"] != self.channel:
                raise WorkflowError("Open the original neural contact scene.")
            if op == "decide" and values["allowed"] in ("yes", "no"):
                return self.neural.decide(
                    viewer,
                    key,
                    identity,
                    revision,
                    values["allowed"] == "yes",
                    values["account"],
                )
            if op == "unplug":
                return self.neural.unplug(viewer, key, identity, revision, values["account"])
        if action == "wyvern_use" and op == "use":
            use = json.loads(values["use"])
            return self.wyvern.use_roused(
                viewer,
                key,
                self.channel,
                revision,
                ActorRef.model_validate(use["target"]),
                use["kind"],
                **{k: use[k] for k in ("asset", "target_frame", "incoming") if k in use},
            )
        if action == "wyvern_start" and op == "start":
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=ROUSE,
                    context=values["account"],
                    heat=int(values["heat"]),
                    trigger_confirmed=True,
                ),
            )
        if action in ("wyvern_roll", "wyvern_source") and op.startswith("roll:"):
            child = op.removeprefix("roll:")
            with self.game.store.engine.connect() as c:
                self.game.authorize(c, viewer, game=False)
                saved = self.game.action(c, child)
                native_source = saved["data"].get("wyvern_pin_response") or saved["data"].get(
                    "wyvern_replacement"
                )
                valid = (
                    saved["data"]["play"] == ROUSE and action == "wyvern_roll" and identity == child
                ) or (
                    native_source and action == "wyvern_source" and native_source["id"] == identity
                )
                if not valid or str(saved["channel_id"]) != str(self.channel):
                    raise WorkflowError("Roll from the actual original Battlefield Play.")
            return self.game.roll(viewer, key, child)
        if action == "wyvern_source":
            saved = self.combat.view(viewer, identity)
            counter = saved["counter"]
            if counter and counter["channel"] != self.channel:
                raise WorkflowError("Open the original Wyvern scene.")
            if op == "release":
                return self.combat.release_pin(viewer, key, identity, revision, values["account"])
            if op == "counter" and counter and (saved["can_counter"] or saved["can_resume"]):
                if values["play"] not in COUNTER_PLAYS:
                    raise WorkflowError("Choose a supported response to the original source.")
                target = None
                if saved["kind"] == "pin":
                    with self.game.store.engine.connect() as c:
                        state = load_state(c, self.game.store.campaign_id)
                        target = next(
                            x.actor for x in wyvern.records(state, wyvern.Pin) if x.id == identity
                        )
                return self.game.begin(
                    viewer,
                    key,
                    self.channel,
                    data["game_revision"],
                    PlayInput(
                        play=values["play"],
                        context=values["account"],
                        heat=int(values["heat"]),
                        target_actor=target,
                        parent=counter["parent"],
                        source_work=identity,
                        trigger_confirmed=True,
                    ),
                )
        raise WorkflowError("Open the current assigned Battlefield decision.")
