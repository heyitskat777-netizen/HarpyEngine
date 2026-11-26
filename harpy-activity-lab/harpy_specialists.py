"""Original Harpy advancement actions and owner-assigned responses."""

from girlframe.discord_adapter.m3_harpy_visions import ADJUSTMENTS
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_advancements import (
    ADVANCEMENTS,
    EAGLE,
    KISS,
    MANIC_PIXIE,
    MASK,
    NOTHING,
    ONLY_SHE_MATTERS,
    SONG_OF_LOVE_LOST,
    VISIONS,
    advances,
)
from girlframe.engine.m3_harpy_visions import Adjustment
from girlframe.services.m2_state import load_state
from girlframe.services.m3_harpy_eagle import EagleService
from girlframe.services.m3_harpy_gaze import CHOICES, GazeService
from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService
from girlframe.services.m3_harpy_intimacy import records as encounters
from girlframe.services.m3_harpy_kiss import KissService
from girlframe.services.m3_harpy_kiss import records as surprises
from girlframe.services.m3_harpy_mask import MaskService
from girlframe.services.m3_harpy_only_she import OnlySheMattersService
from girlframe.services.m3_harpy_rewrite import RewriteService
from girlframe.services.m3_harpy_song import HarpySongService
from girlframe.services.m3_harpy_visions import VisionsService
from girlframe.services.native_form_fields import Field
from girlframe.services.onboarding import WorkflowError

LABELS = dict(ADVANCEMENTS)
YES_NO = (("yes", "Confirm"), ("no", "Decline"))
ACCOUNT = Field("account", "Describe what happened", paragraph=True)
HEAT_GAIN = Field("heat", "Heat to gain", (("1", "1 Heat"), ("2", "2 Heat")))
TITLES = {
    "song": LABELS[SONG_OF_LOVE_LOST],
    "gaze": LABELS[MANIC_PIXIE],
    "rewrite": LABELS[NOTHING],
    "visions": LABELS[VISIONS],
    "reinstall": "Reinstall recovered cockpit",
    "reconditioning": "Foundation reconditioning",
    "mask": LABELS[MASK],
    "kiss": LABELS[KISS],
    "private": "Private encounter",
}


def selected(values, key):
    return values.get(key, (None,))[0]


class HarpySpecialists:
    def __init__(self, game, rooms):
        self.game, self.rooms = game, rooms
        self.song = HarpySongService(game)
        self.gaze = GazeService(game)
        self.mask = MaskService(game)
        self.rewrite = RewriteService(game)
        self.visions = VisionsService(game)
        self.eagle = EagleService(game)
        self.kiss = KissService(game)
        self.private = HarpyIntimacyService(game)
        self.only_she = OnlySheMattersService(game)
        self.starts = {
            SONG_OF_LOVE_LOST: self.song.options,
            MANIC_PIXIE: self.gaze.targets,
            NOTHING: self.rewrite.targets,
            VISIONS: self.visions.targets,
            EAGLE: self.eagle.get,
            ONLY_SHE_MATTERS: self.only_she.get,
            MASK: self.mask_source,
            KISS: self.kiss.menu,
        }

    def tasks(self, connection, state, viewer):
        for identity in self.kiss.tasks(connection, state, viewer):
            yield "advancement_kiss", identity, TITLES["kiss"]
        for identity, _ in self.private.tasks(connection, state, viewer):
            yield "advancement_private", identity, TITLES["private"]
        for name, cases in (
            ("song", self.song.tasks(connection, state, viewer)),
            ("gaze", (case for case, _ in self.gaze.tasks(connection, state, viewer))),
            ("rewrite", (case for case, _ in self.rewrite.tasks(connection, state, viewer))),
            ("visions", (case for case, _ in self.visions.tasks(connection, state, viewer))),
            ("reinstall", self.eagle.restoration_tasks(connection, state, viewer)),
            (
                "reconditioning",
                (case for case, _ in self.visions.recovery_tasks(connection, state, viewer)),
            ),
            ("mask", (case for case, _ in self.mask.tasks(connection, state, viewer))),
        ):
            for case in cases:
                identity = case.event if name in ("gaze", "reinstall", "mask") else case.id
                yield "advancement_" + name, identity, TITLES[name]
        for cast in state.scene_casts:
            if cast.channel not in self.rooms:
                continue
            for role in cast.roles:
                actor = role.actor
                if role.controller != viewer.user_id or actor.kind != "external_pilot":
                    continue
                for item in advances(state, actor):
                    if item.rule not in self.starts:
                        continue
                    identity = f"{cast.channel}/{item.rule}/{actor.entity}"
                    try:
                        _, fields = self.start_form(viewer, identity)
                    except (ValueError, WorkflowError):
                        continue
                    if fields:
                        title = LABELS[item.rule] + " · " + self.rooms[cast.channel][1]
                        yield "advancement_start", identity, title

    def mask_source(self, viewer, channel, actor):
        return self.mask.get(viewer, channel=channel)

    def start_form(self, viewer, identity):
        raw_channel, rule, entity = identity.split("/", 2)
        channel = int(raw_channel)
        if channel not in self.rooms or rule not in self.starts:
            raise WorkflowError("Choose the original Activity scene and Harpy advancement.")
        actor = ActorRef(kind="external_pilot", entity=entity)
        data = self.starts[rule](viewer, channel, actor)
        if rule == MASK:
            return data | {"actor": actor, "channel": channel, "rule": rule}, [
                Field("appearance", "Human appearance"),
                ACCOUNT,
            ]
        if rule == KISS:
            with self.game.store.engine.connect() as connection:
                choices = tuple(
                    (action, label)
                    for action, label in data["actions"].items()
                    if self.game.action(connection, action)["data"]["play"] == "flirt"
                )
            fields = (
                [
                    Field("source", "Original Flirt", choices),
                    Field("choice", "Your response", (("kiss", "Kiss"), ("linger", "Linger"))),
                    ACCOUNT,
                ]
                if choices
                else []
            )
            return data | {"actor": actor, "channel": channel, "rule": rule}, fields
        targets = data["targets"]
        if rule == ONLY_SHE_MATTERS:
            targets = {ref.token: label for ref, label in targets.items()}
        elif rule == EAGLE and data["holding"]:
            targets = {"release": "Release the original Girl and cockpit"}
        elif rule == SONG_OF_LOVE_LOST:
            targets = dict(targets)
            if data["handler"]:
                targets["handler"] = "Make the Handler flinch"
            if data["crowd"]:
                targets["crowd"] = "Draw local NPCs toward you"
        fields = []
        if targets:
            fields = [Field("target", "Original target", tuple(targets.items())), ACCOUNT]
            if rule == ONLY_SHE_MATTERS:
                fields.append(HEAT_GAIN)
        return data | {"actor": actor, "channel": channel, "rule": rule}, fields

    def detail(self, viewer, kind, identity):
        name = kind.removeprefix("advancement_")
        if name == "start":
            data, fields = self.start_form(viewer, identity)
            return data, LABELS[data["rule"]], "File this action in its original scene.", fields
        if name == "song":
            data = self.song.get(viewer, identity)
            choice = {
                "handler": "Flinch",
                "girl": "Step toward the Harpy",
                "crowd": "Verify the crowd’s approach",
            }[data["option"]]
            return (
                data,
                TITLES[name],
                data["account"],
                [Field("choice", "Your response", (("yes", choice), YES_NO[1])), ACCOUNT],
            )
        if name == "mask":
            data = self.mask.get(viewer, identity=identity)
            if data["step"] == "review":
                text = data["appearance"] + "\n" + data["account"]
                choices = (("yes", "Approve this appearance"), YES_NO[1])
            else:
                text = data["appearance"]
                choices = (("yes", "End this appearance"),)
            return data, TITLES[name], text, [Field("choice", "Your decision", choices), ACCOUNT]
        if name == "kiss":
            data = self.kiss.get(viewer, identity)
            text = "Review the original encounter with " + data["girl"] + ".\n" + data["account"]
            can_approve = data["choice"] == "linger" or self.is_flirt_surprise(identity)
            choices = YES_NO if can_approve else (YES_NO[1],)
            if not can_approve:
                text += "\nApproval requires the original Flirt receipt."
            return data, TITLES[name], text, [Field("choice", "Your ruling", choices)]
        if name == "private":
            data = self.private.get(viewer, identity)
            text, fields = self.private_form(viewer, identity, data)
            return data, TITLES[name], text, fields
        if name == "gaze":
            data = self.gaze.get(viewer, identity)
            text, fields = self.gaze_form(viewer, data)
        elif name == "rewrite":
            data = self.rewrite.get(viewer, identity)
            text, fields = self.rewrite_form(data)
        elif name == "visions":
            data = self.visions.get(viewer, identity)
            text, fields = self.visions_form(data)
        elif name == "reinstall":
            with self.game.store.engine.connect() as connection:
                state = load_state(connection, self.game.store.campaign_id)
                if not any(
                    case.event == identity
                    for case in self.eagle.restoration_tasks(connection, state, viewer)
                ):
                    raise WorkflowError("Choose your own recovered cockpit.")
            return {"revision": state.revision}, TITLES[name], "", [ACCOUNT]
        elif name == "reconditioning":
            data = self.visions.recovery(viewer, identity)
            if data["step"] == "request":
                fields = (
                    [Field("site", "Foundation care site", tuple(data["sites"].items())), ACCOUNT]
                    if data["sites"]
                    else []
                )
                text = "Request reconditioning for " + data["play"]
            else:
                fields = [Field("choice", "Original care outcome", YES_NO), ACCOUNT]
                text = data["account"]
        else:
            raise WorkflowError("Choose the original Harpy assignment.")
        return data, TITLES[name], text, fields

    def gaze_form(self, viewer, data):
        step = data["step"]
        if step == "keep":
            sheet = self.game.sheet(viewer)
            return data["account"], [
                Field(
                    "heat",
                    "Heat to commit",
                    tuple((str(x), str(x)) for x in range(sheet["heat"] + 1)),
                ),
                Field("account", "What are you trying to endure?", paragraph=True),
            ]
        if step == "void":
            return "Keep Your Head failed. File the original Void change.", [
                Field("choices", "Eligible Asset", tuple(data["assets"].items())),
                ACCOUNT,
            ] if data["assets"] else []
        if step == "choose":
            return data["account"], [
                Field("choices", "Two responses", tuple(CHOICES.items()), 2, 2),
                ACCOUNT,
                Field("promise", "Promise, if selected", paragraph=True, required=False),
            ]
        if step == "break":
            return data["promise"], [Field("confirm", "Your decision", (("break", "Withdraw"),))]
        return data["promise"], [Field("account", "The Tag you give", paragraph=True)]

    def is_flirt_surprise(self, identity, *, encounter=False):
        with self.game.store.engine.connect() as connection:
            state = load_state(connection, self.game.store.campaign_id)
            if encounter:
                case = next((x for x in encounters(state) if x.id == identity), None)
                identity = case.kiss if case else None
            case = next((x for x in surprises(state) if x.id == identity), None)
            if not case:
                return False
            return self.game.action(connection, case.action)["data"]["play"] == "flirt"

    def private_form(self, viewer, identity, data):
        step = data["step"]
        choices = ()
        fields = []
        if step == "consent":
            choices = (("decline", "Decline"),)
            if self.is_flirt_surprise(identity, encounter=True):
                choices = (("accept", "Accept"), *choices)
            text = "Choose whether to participate."
        elif step == "escape":
            choices = (("keep", "Keep Your Head"), ("stay", "Stay"), ("withdraw", "Withdraw"))
            heat = self.game.sheet(viewer)["heat"]
            fields = [
                Field(
                    "heat",
                    "Heat to commit if attempting to leave",
                    tuple((str(x), str(x)) for x in range(heat + 1)),
                    required=False,
                ),
                Field("account", "What are you trying to endure?", paragraph=True, required=False),
            ]
            text = "Your response is private."
        elif step == "rebirth":
            choices = (("begin", "Open the original transformation"),)
            text = "The original Apometanoia is ready."
        else:
            choices = tuple(data["assets"].items())
            text = "File the original Void change."
            fields = [Field("account", "Describe the Asset’s change", paragraph=True)]
        return text, [Field("choice", "Your decision", choices), *fields] if choices else []

    @staticmethod
    def rewrite_form(data):
        step, slots = data["step"], data["slots"]
        if step == "verify":
            return data["account"], [
                Field("allow", "Alone and no help is coming?", YES_NO),
                Field("account", "Factual review", required=False),
            ]
        if step == "authorize":
            fields = [Field("allow", "Authorize the selected Identities?", YES_NO)]
            if slots:
                fields.append(
                    Field(
                        "slots",
                        "Authorized Identities",
                        tuple(slots.items()),
                        minimum=0,
                        maximum=len(slots),
                        required=False,
                    )
                )
            return "The original Girl can review the proposed edits.", fields
        if step == "draft":
            return f"{data['remaining']} seconds remain.", [
                Field(key, "New name for " + name, required=False) for key, name in slots.items()
            ]
        if step == "apply":
            return "\n".join(f"{slots[key]} → {new}" for key, new in data["changes"].items()), [
                Field("allow", "Apply these edits?", YES_NO)
            ]
        return "The one-minute window expired.", [
            Field("close", "Close expired edit", (("yes", "Close edit"),))
        ]

    @staticmethod
    def visions_form(data):
        step = data["step"]
        if step == "consent":
            return data["account"], [Field("choice", "Allow the contact?", YES_NO)]
        if step == "roll":
            return "The original Girl allowed the contact.", [
                Field(
                    "heat",
                    "Heat to commit",
                    tuple((str(x), str(x)) for x in range(data["heat"] + 1)),
                )
            ]
        if step == "replace" and data["can_replace"]:
            return "\n".join(data["identities"]), [
                Field("choice", "Original effect", (("yes", "Apply change"),))
            ]
        if step == "plan":
            count = 8 if data["tier"] == "high" else 4
            return "Choose the effects in order. A choice can repeat.", [
                *(
                    Field(
                        f"effect_{index}", f"Effect {index + 1}", ADJUSTMENTS, required=count == 8
                    )
                    for index in range(count)
                ),
                Field("names", "New Identity names, one per line", paragraph=True, required=False),
            ]
        if step == "confirm":
            descriptions = data["descriptions"]
            return (
                "\n".join(descriptions) or "The Harpy chose zero effects."
                if descriptions is not None
                else "These choices cannot be applied to the current sheet."
            ), [
                Field(
                    "choice", "Your decision", YES_NO if descriptions is not None else (YES_NO[1],)
                )
            ]
        return "Awaiting the original consequence.", []

    def write(self, viewer, key, kind, identity, data, values):
        name = kind.removeprefix("advancement_")
        args = viewer, key, identity, data["revision"]
        account = values.get("account", "")
        if name == "start":
            actor, channel, rule = data["actor"], data["channel"], data["rule"]
            call = viewer, key, channel, actor, data["revision"]
            target = selected(values, "target")
            if rule == MASK:
                return self.mask.offer(*call, values["appearance"], account)
            if rule == KISS:
                source, choice = selected(values, "source"), selected(values, "choice")
                return self.kiss.propose(*call, source, choice, account)
            if rule == ONLY_SHE_MATTERS:
                recipient = next(ref for ref in data["targets"] if ref.token == target)
                return self.only_she.act(
                    viewer,
                    key,
                    channel,
                    data["revision"],
                    actor,
                    recipient,
                    int(selected(values, "heat")),
                    account,
                )
            handlers = {
                EAGLE: self.eagle.act,
                SONG_OF_LOVE_LOST: self.song.act,
                MANIC_PIXIE: self.gaze.start,
                NOTHING: self.rewrite.start,
                VISIONS: self.visions.start,
            }
            return handlers[rule](*call, target, account)
        if name == "reinstall":
            return self.eagle.restore(*args, account)
        if name == "song":
            return self.song.respond(
                *args, accept=selected(values, "choice") == "yes", account=account
            )
        if name == "kiss":
            return self.kiss.confirm(*args, selected(values, "choice") == "yes")
        step = data["step"]
        if name == "mask":
            return self.mask.respond(*args, step, selected(values, "choice") == "yes", account)
        if name == "gaze":
            if step == "keep":
                return self.game.begin(
                    viewer,
                    key,
                    data["channel"],
                    self.game.sheet(viewer)["revision"],
                    PlayInput(
                        play="keep_your_head",
                        source_work=identity,
                        context=account,
                        trigger_confirmed=True,
                        heat=int(selected(values, "heat")),
                    ),
                )
            return self.gaze.respond(
                *args,
                step,
                choices=values.get("choices", ()),
                account=account,
                promise=values.get("promise", ""),
            )
        if name == "private":
            choice = selected(values, "choice")
            if step == "escape" and choice == "keep":
                if not account or selected(values, "heat") is None:
                    raise ValueError("File the Heat and account for Keep Your Head.")
                return self.game.begin(
                    viewer,
                    key,
                    data["channel"],
                    self.game.sheet(viewer)["revision"],
                    PlayInput(
                        play="keep_your_head",
                        source_work=identity,
                        context=account,
                        trigger_confirmed=True,
                        heat=int(selected(values, "heat")),
                    ),
                )
            return self.private.respond(*args, step, choice, account)
        if name == "rewrite":
            allow = selected(values, "allow")
            return self.rewrite.respond(
                *args,
                step,
                allow=allow == "yes" if allow is not None else None,
                selected=values.get("slots", ()),
                changes={k: values[k] for k in data["slots"] if k in values}
                if step == "draft"
                else None,
                account=account,
            )
        decision = selected(values, "choice")
        confirmed = decision == "yes" if decision is not None else None
        if name == "reconditioning":
            return self.visions.recondition(
                *args, step, site=selected(values, "site"), verified=confirmed, account=account
            )
        heat = selected(values, "heat")
        return self.visions.respond(
            *args,
            step,
            heat=int(heat) if heat is not None else None,
            choice=confirmed,
            choices=self.effects(values) if step == "plan" else None,
        )

    @staticmethod
    def effects(values):
        effects = [value[0] for key, value in sorted(values.items()) if key.startswith("effect_")]
        names = [x.strip() for x in values.get("names", "").splitlines() if x.strip()]
        if len(names) != effects.count("identity"):
            raise ValueError("Provide one name per new Identity.")
        names = iter(names)
        result = []
        for selection in effects:
            effect, _, arg = selection.partition(":")
            result.append(
                Adjustment(
                    effect=effect,
                    slot=int(arg) if effect == "tag" else None,
                    name=next(names) if effect == "identity" else arg if effect == "play" else "",
                )
            )
        return tuple(result)
