"""Read the same native, owner-scoped Play controls used by the Activity."""

import hashlib

from am_scene_controls import PLAYS as AM_PLAYS
from handler_playbook import RULES as BASIC_HANDLER_RULES
from harpy_play_options import harpy_plays
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

from girlframe.engine import m3_disposable_psyche, m3_show_dog, m3_tracker_implants
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.director_play_catalog import PlayCatalog
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_erratic_gorgon import ErraticService
from girlframe.services.m3_gorgon_forms import declarations as gorgon_declarations
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.m3_npc_handover import LABELS, NpcHandoverService
from girlframe.services.m3_npc_intelligence import IntelligenceService
from girlframe.services.native_form_fields import Field, form_fields
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

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

    def option(self, identity, label, destination, *, trigger="", control=None, room=""):
        return {
            "id": identity,
            "label": label,
            "destination": destination,
            "trigger": trigger,
            "control": control or identity,
            "room": room,
        }

    def alternate(self, connection, scene, actor):
        """Read actual scene roles and native options without looking up a Pilot sheet."""
        state = load_state(connection, self.game.store.campaign_id)
        channel = int(scene["channel_id"])
        cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        if cast is None:
            return ()
        try:
            self.game.unpaused(connection)
            self.game.scene_unpaused(connection, scene["id"])
            role = resolve(state, actor, profiles(connection, self.game.store.campaign_id))
            if role.controller not in scene["participants"] or not any(
                x.actor == actor and x.controller == role.controller for x in cast.roles
            ):
                return ()
            lock = self.game.lock(connection, channel)
            if self.game.pending_actions(connection) or lock and lock["state"] != "released":
                return ()
            turn = None
            if any(
                x.get("kind") == "activity_battlefield_turn" and x.get("scene") == cast.id
                for x in state.facts
            ):
                arena = self.battlefield
                if arena is None or arena.channel != channel:
                    return ()
                record = arena.turn_record(state, scene)
                active = arena.current_turn(record, arena.placed(connection, state, scene))
                if active is None or active[1] != actor.token:
                    return ()
                turn = f"{record['epoch']}:{active[0]}"
            viewer = GuildViewer(role.controller, self.game.store.policy.guild_id, True, False)
            binding = dict(
                channel=channel,
                revision=state.revision,
                turn=turn,
                actor_sha256=role.source_sha256,
                cast_revision=cast.revision,
            )
            if actor.kind == "npc":
                native = NpcHandoverService(self.game)
                handovers = []
                for job in LABELS:
                    if job not in role.jobs:
                        continue
                    try:
                        menu = native.menu(viewer, channel, actor, job)
                    except (ValueError, WorkflowError):
                        continue
                    if job != "fan" and not menu["items"]:
                        continue
                    choices = {"item": menu["items"]} if job != "fan" else {}
                    handovers.extend(
                        self._alternate_option(
                            job,
                            f"{job.title()} handover",
                            token,
                            name,
                            binding,
                            costs={},
                            choices=choices,
                            reach="same_cell",
                        )
                        for token, name in menu["targets"].items()
                    )
                if "intelligence_agent" in role.jobs:
                    try:
                        inquiry = IntelligenceService(self.game).menu(viewer, channel, actor)
                    except (ValueError, WorkflowError):
                        inquiry = None
                    if inquiry and inquiry["revision"] == state.revision:
                        handovers.extend(
                            self._alternate_option(
                                "npc_inquiry",
                                "Make an intelligence inquiry",
                                token,
                                name,
                                binding,
                                costs={},
                                choices={},
                                reach="same_cell",
                            )
                            for token, name in inquiry["targets"].items()
                        )
                return tuple(handovers)
            if actor.kind == "external_pilot" and role.girl == "harpy":
                return tuple(
                    self._alternate_option(
                        row["key"],
                        row["label"],
                        row["target_token"],
                        row["target_name"],
                        binding,
                        **row["binding"],
                    )
                    for row in harpy_plays(self.game, connection, viewer, scene, state, cast, role)
                )
            if actor.kind == "gorgon":
                view = GorgonPlayService(self.game).preview(viewer, channel)
                if view["revision"] != state.revision:
                    return ()
                targets = view["attack_targets"].get(actor.token, {})
                assets = {x.id: x.name for x in role.assets}
                attacks = tuple(
                    self._alternate_option(
                        "gorgon_attack",
                        "Attack",
                        target["token"],
                        target["label"],
                        binding,
                        target=target["ref"],
                        target_sha256=target["source_sha256"],
                        costs={},
                        choices={"asset": assets},
                        reach=targets[target["token"]],
                    )
                    for target in view["actors"]
                    if target["token"] in targets
                )
                return (
                    attacks
                    + tuple(
                        self._alternate_option(
                            "gorgon_declaration_" + entry["kind"],
                            "Collateral Damage"
                            if entry["kind"] == "collateral"
                            else entry["kind"].replace("_", " ").title(),
                            entry["target_token"],
                            entry["target_name"],
                            binding,
                            kind=entry["kind"],
                            target=entry["target"],
                            target_sha256=entry["target_sha256"],
                            day=entry["day"],
                            fields=entry["fields"],
                            costs={},
                            choices={},
                            reach="native_review",
                        )
                        for entry in gorgon_declarations(view, actor.token)
                    )
                    + (
                        self.erratic_plays(viewer, actor, binding)
                        if state.world
                        and any(
                            x.id == actor.entity and x.gorgon_class == "erratic"
                            for x in state.world.gorgons
                        )
                        else ()
                    )
                )
        except (ValueError, WorkflowError):
            return ()
        return ()

    def erratic_plays(self, viewer, actor, binding):
        service = ErraticService(self.game)
        channel = binding["channel"]
        try:
            originals = service.view(viewer, channel)
            if originals["revision"] != binding["revision"] or actor.entity not in dict(
                originals["gorgons"]
            ):
                return ()
            flight = service.flight_view(viewer, channel)
        except (ValueError, WorkflowError):
            return ()
        tags = tuple(
            self._alternate_option(
                "gorgon_erratic_tag",
                "Give an Erratic Tag",
                "npc:" + identity,
                label,
                binding,
                target_npc=identity,
                fields=form_fields((Field("tag", "Original NPC Tag"),)),
                choices={},
                costs={},
                reach="native_review",
            )
            for identity, label in originals["npcs"]
        )
        if flight["revision"] != binding["revision"]:
            return ()
        return tags + tuple(
            self._alternate_option(
                "gorgon_erratic_flee",
                "Slip away from the exchange",
                item["action"],
                "",
                binding,
                source_work="erratic:" + item["action"],
                battle=item["action"],
                fields=form_fields((Field("x", "Destination X"), Field("y", "Destination Y"))),
                choices={},
                costs={},
                reach="mapped_destination",
            )
            for item in flight["battles"]
            if item["gorgon"] == actor.entity
        )

    def _alternate_option(self, play, label, token, name, binding, **details):
        identity = f"{play}:{token}"
        if len(identity) > 120:
            identity = play[:50] + ":" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        option = self.option(identity, f"{label} · {name}" if name else label, "alternate_native")
        return option | {"alternate": binding | {"play": play, "target_token": token} | details}

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
            if identity in inventory and identity not in playable and card["operations"]:
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
        forms = {operation["id"]: card["id"] for card in cards for operation in card["operations"]}
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
            blocked="keep_your_head" in adapter.start_reasons(viewer, state, native["pilots"]),
        )
        # This is the same sheet filter as the Play rail, including learned and grafted rules.
        result = []
        for play in character_plays(self.setup.play_registry, sheet, owns_sheet=True, state=state):
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
                identity,
                referral.title,
                "scene_specialist",
                trigger=rule.contract.trigger if rule.contract else "",
                control=control,
                room=room,
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
            (
                m3_disposable_psyche.RULE,
                (
                    card
                    for card in psyche.cards(viewer, state, current["id"])
                    if card["phase"] == "pending" and card["tags"]
                ),
            ),
        )
        with self.game.store.engine.connect() as c:
            for rule, source_cards in cards:
                for card in source_cards:
                    if self.game.action(c, card["source_action"])["scene_id"] == scene["id"]:
                        yield self.option(
                            rule,
                            card["label"],
                            "off_duty_work",
                            control=card["id"],
                            room=room,
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
                        identity,
                        self.catalog.get(identity).title,
                        "handler_scene_specialist",
                        room=room[0],
                    )
        if not any(
            int(target["ref"]["entity"]) in scene["participants"] for target in book["targets"]
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
                "handler_" + identity,
                row["label"],
                "handler",
                control=identity,
                room=room[0] if room else "",
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
