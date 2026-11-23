"""Read the same native, owner-scoped Play controls used by the Activity."""

from girlframe.engine import m3_disposable_psyche, m3_show_dog, m3_tracker_implants
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.director_play_catalog import PlayCatalog
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

from am_scene_controls import PLAYS as AM_PLAYS
from handler_playbook import RULES as BASIC_HANDLER_RULES
from native_scene_forms import HANDLER_SCENE_PLAYS, NATIVE_TITLES
from play_catalog import character_plays
from psyche_controls import PsycheControls
from scene_plays import FOLLOW_THROUGH, REJECT_TAG
from show_dog_controls import ShowDogControls
from specialist_scene import (
    BLANK,
    CLAY,
    CONSULT,
    MEMORY,
    PANOPTICON,
    TRANSFER,
    SpecialistScene,
)

FRAME_STARTS = {
    "janus_start": "living_battery",
    "wyvern_start": "wyvern_rouse",
}
SCENE_STARTERS = frozenset((*NATIVE_TITLES, BLANK, CLAY, CONSULT, MEMORY, PANOPTICON, TRANSFER))
OWNED_SCENE_PLAYS = {
    FOLLOW_THROUGH: (
        "Flirt follow-through",
        "flirt",
        "Follow through on the actual answered Flirt.",
    ),
    REJECT_TAG: (
        "Reject Tag",
        REJECT_TAG,
        "Reject the Tag in the assigned open obligation.",
    ),
}


class ActivityNativePlays:
    def __init__(self, setup, battlefield):
        self.setup, self.battlefield = setup, battlefield
        self.game = setup.game
        self.catalog = PlayCatalog(setup.play_registry)

    def __call__(self, connection, scene, actor):
        if actor.kind not in ("pilot", "handler"):
            return ()
        state = load_state(connection, self.game.store.campaign_id)
        controller = int(actor.entity)
        if controller not in scene["participants"]:
            return ()
        try:
            self.game.unpaused(connection)
            self.game.scene_unpaused(connection, scene["id"])
        except WorkflowError:
            return ()
        # Internal read projection for the already validated actor. It never submits a command.
        viewer = (
            self.setup.handler
            if actor.kind == "handler"
            else GuildViewer(controller, self.game.store.policy.guild_id, True, False)
        )
        if actor.kind == "handler":
            if not same_handler_body(state, actor):
                return ()
            return self.handler_plays(connection, scene, state, viewer)
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            return ()
        channel = int(scene["channel_id"])
        try:
            if self.battlefield is not None and channel == self.battlefield.channel:
                view = self.battlefield._view(viewer)
                if view["revision"] != state.revision:
                    return ()
                return self.battlefield_plays(view, sheet, state)
            return self.scene_plays(viewer, scene, sheet, state, channel)
        except (ValueError, WorkflowError):
            # A missing board, cast, edition, or native prerequisite yields no selection.
            return ()

    def option(
        self, identity, label, destination, *, trigger="", control=None, room=""
    ):
        return {
            "id": identity,
            "label": label,
            "destination": destination,
            "trigger": trigger,
            "control": control or identity,
            "room": room,
        }

    def battlefield_plays(self, view, sheet, state):
        playable = {
            row["id"]: self.option(row["id"], row["label"], "battlefield")
            for row in view["actions"]
            if row["id"] != "move"
        }
        inventory = {
            row["id"]: row
            for row in character_plays(
                self.setup.play_registry, sheet, owns_sheet=True, state=state
            )
            if not row["blocked"]
        }
        for card in view.get("frame_work", ()):
            identity = FRAME_STARTS.get(card["action"])
            if (
                identity in inventory
                and identity not in playable
                and card["operations"]
            ):
                item = inventory[identity]
                playable[identity] = self.option(
                    identity,
                    item["label"],
                    "battlefield_frame",
                    trigger=item["trigger"],
                    control=card["id"],
                )
        return tuple(playable.values())

    def scene_plays(self, viewer, scene, sheet, state, channel):
        adapter = self.setup.scene_plays.for_channel(channel)
        native = self.game.scene_info(viewer, channel)
        if not native["joined"]:
            return ()
        locked = bool(native["lock"] and native["lock"]["state"] != "released")
        character = {"revision": sheet.revision}
        room = self.setup.handler_rooms().get(channel)
        if room is None:
            return ()
        options = adapter.play_options(
            viewer,
            native,
            character,
            state,
            locked,
            False,
            adapter.off_duty_status(viewer),
        )
        cards = SpecialistScene(self.game, channel).view(viewer, room)
        forms = {
            operation["id"]: card["id"]
            for card in cards
            for operation in card["operations"]
        }
        blocked = {entry.play for entry in sheet.blocked_plays}
        if locked:
            orders = {
                "order_response": "receive_orders",
                "order_disobey": "disobey_orders",
            }
            owned_orders = (
                self.option(
                    identity,
                    self.catalog.get(identity).title,
                    "scene",
                    control="receive_orders",
                    room=room[0],
                )
                for identity in dict.fromkeys(
                    orders[choice["kind"]]
                    for choice in options["receive_orders"]["choices"]
                    if choice["role"] == "pilot" and choice["kind"] in orders
                )
                if not any(entry.play == identity for entry in sheet.blocked_plays)
            )
            preparation = {key: value for key, value in forms.items() if key in AM_PLAYS}
            return (*owned_orders, *self.specialist_options(preparation, blocked, (), room[0]))
        keep = adapter.view(
            viewer,
            character,
            False,
            blocked="keep_your_head"
            in adapter.start_reasons(viewer, state, native["pilots"]),
        )
        # This is the same sheet filter as the Play rail, including learned and grafted rules.
        result = []
        for play in character_plays(
            self.setup.play_registry, sheet, owns_sheet=True, state=state
        ):
            identity = play["id"]
            if play["blocked"]:
                continue
            if (
                identity == "keep_your_head"
                and keep["can_start"]
                or options.get(identity, {}).get("can_start")
            ):
                result.append(
                    self.option(
                        identity,
                        play["label"],
                        "scene",
                        trigger=play["trigger"],
                        room=room[0],
                    )
                )
        existing = {row["id"] for row in result}
        result.extend(self.specialist_options(forms, blocked, existing, room[0]))
        for identity, (label, control, trigger) in OWNED_SCENE_PLAYS.items():
            if (
                identity not in existing
                and identity not in blocked
                and options.get(identity, {}).get("can_start")
            ):
                result.append(
                    self.option(
                        identity,
                        label,
                        "scene",
                        trigger=trigger,
                        control=control,
                        room=room[0],
                    )
                )
        result.extend(self.off_duty_options(viewer, scene, state, room[0]))
        return tuple(result)

    def specialist_options(self, forms, blocked, existing, room):
        for identity, control in forms.items():
            if identity not in SCENE_STARTERS or identity in existing:
                continue
            referral = self.catalog.get(identity)
            if blocked.intersection({identity, referral.rule_id}):
                continue
            rule = self.setup.play_registry.entry(referral.rule_id)
            yield self.option(
                identity, referral.title, "scene_specialist",
                trigger=rule.contract.trigger if rule.contract else "",
                control=control, room=room,
            )

    def off_duty_options(self, viewer, scene, state, room):
        shows = ShowDogControls(self.game)
        try:
            current = shows.periods.current(viewer)
        except WorkflowError:
            return
        if not current or current["phase"] != "active":
            return
        psyche = PsycheControls(self.game)
        cards = (
            (m3_show_dog.RULE, shows.cards(viewer, state, current["id"])),
            (m3_disposable_psyche.RULE, (
                card for card in psyche.cards(viewer, state, current["id"])
                if card["phase"] == "pending" and card["tags"]
            )),
        )
        with self.game.store.engine.connect() as c:
            for rule, source_cards in cards:
                for card in source_cards:
                    if self.game.action(c, card["source_action"])["scene_id"] == scene["id"]:
                        yield self.option(
                            rule, card["label"], "off_duty_work", control=card["id"], room=room,
                        )

    def handler_plays(self, connection, scene, state, viewer):
        if viewer.user_id != state.handler:
            return ()
        try:
            Access(self.game.store).authorize(connection, viewer, "plays")
            playbook = self.setup.handler_playbook
            book = playbook.view(viewer)
        except WorkflowError:
            return ()
        if book["revision"] != state.revision:
            return ()
        try:
            _ordinary_scene_idle(connection, self.game)
        except WorkflowError:
            ordinary_idle = False
        else:
            ordinary_idle = True
        options = {}
        tracked_scenes = {
            source.id: str(source.cast.channel)
            for source in m3_tracker_implants.records(state, m3_tracker_implants.PlaySource)
        }
        for task in book["tasks"]:
            if (
                task["stale"]
                or task["state"] != "pending"
                or (task["ordinary"] and not ordinary_idle)
            ):
                continue
            detail = playbook.service.get(viewer, task["id"])["grant"]
            if detail["scope"]["scene_id"] != scene["id"] and (
                tracked_scenes.get(task["id"]) != scene["channel_id"]
            ):
                continue
            for row in task["plays"]:
                if row["reason"] is None:
                    identity = row["id"]
                    # Include the source in the option ID so two earned grants cannot
                    # silently replace each other in a model proposal.
                    options[f"{identity}:{task['id']}"] = self.option(
                        f"handler_{identity}:{task['id']}",
                        row["label"],
                        "handler_effect",
                        control=task["id"],
                    )
        if not ordinary_idle:
            return tuple(options.values())
        room = self.setup.handler_rooms().get(int(scene["channel_id"]))
        if room is not None:
            for work in self.off_duty_options(viewer, scene, state, room[0]):
                options[work["id"]] = work
            for card in SpecialistScene(self.game, int(scene["channel_id"])).view(viewer, room):
                identity = card["id"]
                if identity in HANDLER_SCENE_PLAYS:
                    options[identity] = self.option(
                        identity, self.catalog.get(identity).title, "handler_scene_specialist", room=room[0]
                    )
        if not any(
            int(target["ref"]["entity"]) in scene["participants"]
            for target in book["targets"]
        ):
            return tuple(options.values())
        for row in book["plays"]:
            identity = row["id"]
            if not row["playable"] or identity not in BASIC_HANDLER_RULES:
                continue
            if identity == "support" and not (state.world and state.world.locations):
                continue
            if identity == "off_duty" and not book["off_duty_phase"]:
                continue
            options[identity] = self.option(
                "handler_" + identity, row["label"], "handler", control=identity, room=room[0] if room else "",
            )
        if room is not None:
            for row in book["plays"]:
                identity = row["id"]
                if book["scene_effects"].get(identity):
                    options[identity] = self.option(
                        "handler_" + identity,
                        row["label"],
                        "handler",
                        control=identity,
                        room=room[0],
                    )
        return tuple(options.values())
