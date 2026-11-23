"""Roster Battlefield commands on the Activity campaign's HarpyEngine store."""

import json
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import get_args
from uuid import UUID, uuid4, uuid5

import sqlalchemy as sa
from girlframe.database import tables
from girlframe.engine import m3_battle as battle_rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Context
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_world_state import (
    Asset,
    Board,
    CorePlan,
    Gorgon,
    GorgonType,
    Location,
    Npc,
)
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_movement import proposal_context
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError

from battlefield import (
    ASSAULT,
    BENEATH,
    CORE,
    DECLARED_PLAYS,
    FLIRT,
    PLAY_LABELS,
    Battlefield,
    BattlefieldChanged,
)
from battlefield_frame_work import BattlefieldFrameWork

PRIVATE_BATTLEFIELD_CHANNEL = 901
TURN_FACT = "activity_battlefield_turn"
FACILITY_FACT = "activity_battlefield_facility"
FACILITY_PLANS = json.loads(Path(__file__).with_name("facility-plans.json").read_text(encoding="utf-8"))
LOCATION_CELLS = ((0, 0), (4, 0), (8, 0), (0, 5), (8, 5), (2, 3), (5, 5), (7, 8))
LOCATION_KINDS = (
    "base",
    "base",
    "base",
    "city",
    "city",
    "important",
    "important",
    "important",
)
GORGON_TYPES = get_args(GorgonType)


def facility_board(plan):
    x, y = plan["minimum"]
    return Board(minimum=(x, y), maximum=(x + len(plan["floor"][0]) - 1, y + len(plan["floor"]) - 1))


def walkable(plan, cell):
    if not isinstance(cell, (list, tuple)) or len(cell) != 2 or any(type(value) is not int for value in cell):
        raise ValueError("Choose an actual grid square.")
    x, y = cell
    left, top = plan["minimum"]
    return (
        0 <= y - top < len(plan["floor"])
        and 0 <= x - left < len(plan["floor"][y - top])
        and plan["floor"][y - top][x - left] != "w"
    )


class PrivateBattlefield(Battlefield):
    def __init__(self, missions, setup, *, dice=None, facilities=False):
        super().__init__(
            missions,
            setup.handler,
            setup.owner,
            setup.recruit,
            dice=dice,
            shared=True,
            channel=PRIVATE_BATTLEFIELD_CHANNEL,
            private=True,
        )
        self.scene = setup.scene_plays.for_channel(self.channel)
        self.physical = PhysicalService(self.store)
        self.casts = CastService(ActorService(missions))
        self.commands = RLock()
        self.facilities = facilities

    def facility(self, state):
        if self.facilities:
            for fact in state.facts:
                if fact.get("kind") == FACILITY_FACT:
                    return FACILITY_PLANS[fact["body"]]
        return None

    def open_facility(self, viewer, key, data):
        if (
            data.keys() != {"revision", "facility"}
            or type(data["revision"]) is not int
            or not isinstance(data["facility"], str)
            or data["facility"] not in FACILITY_PLANS
        ):
            raise ValueError("Select a facility to open.")
        identity = data["facility"]
        plan = FACILITY_PLANS[identity]
        bounds = facility_board(plan)

        def operation(connection):
            state = load_state(connection, self.store.campaign_id)
            self.handler_only(connection, viewer, state)
            self.game.unpaused(connection)
            if data["revision"] != state.revision:
                raise WorkflowError("Refresh the current campaign map.")
            if self.facility(state) is not None:
                raise WorkflowError("The Battlefield facility has already been filed.")
            if not state.world or not all(
                state.world.board.contains(cell) for cell in (bounds.minimum, bounds.maximum)
            ):
                raise WorkflowError("This facility does not fit the existing HarpyEngine board.")
            state.facts.append({"kind": FACILITY_FACT, "body": identity})
            self.game.event(
                connection, viewer.user_id, key, "activity.battlefield.facility",
                state, channel=self.channel,
            )
            return {"facility": identity}

        result = self.store._write(
            viewer, key, "activity.battlefield.facility", data, operation, auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer),
        )
        self.bind_battlefield(viewer)
        return result | {"opened": True}

    def scene_row(self, connection):
        scenes = tables.m2["m2_scenes"]
        row = (
            connection.execute(
                sa.select(scenes).where(
                    scenes.c.campaign_id == self.store.campaign_id,
                    scenes.c.channel_id == str(self.channel),
                    scenes.c.open.is_(True),
                )
            )
            .mappings()
            .first()
        )
        return (
            dict(row) | {"participants": json.loads(row["participants_json"])}
            if row
            else None
        )

    def joined(self, viewer, scene):
        return bool(scene and viewer.user_id in scene["participants"])

    def placed(self, connection, state, scene):
        if not state.world or not scene:
            return {}
        bindings = profiles(connection, self.store.campaign_id)
        order = list(state.order) + sorted(
            set(scene["participants"]) - set(state.order)
        )
        eligible = {}
        for uid in order:
            sheet = state.sheets.get(str(uid))
            if uid not in scene["participants"] or not sheet or not sheet.character_id:
                continue
            ref = ActorRef(
                kind="pilot", entity=str(uid), incarnation=sheet.character_id
            )
            try:
                actor = resolve(state, ref, bindings, require_current_profile=False)
            except ValueError:
                continue
            if actor.alive and actor.controller == uid and actor.cell is not None:
                eligible[ref.token] = actor
        cast = next(
            (
                item
                for item in state.scene_casts
                if item.id == scene["id"] and item.open
            ),
            None,
        )
        visible = {
            ActorRef(kind=kind, entity=x.id).token
            for kind, actors in (("npc", state.world.npcs), ("gorgon", state.world.gorgons))
            for x in actors if x.revealed and x.alive
        }
        harpies = {x.id for x in state.harpy_states if x.alive and x.revealed}
        harpies.update(x.id for x in state.world.pilots if x.kind == "harpy" and x.alive and x.revealed)
        for role in cast.roles if cast else ():
            harpy = role.actor.kind == "external_pilot" and role.actor.entity in harpies
            if not harpy and role.actor.token not in visible:
                continue
            if role.controller not in scene["participants"]:
                continue
            try:
                actor = resolve(
                    state, role.actor, bindings, require_current_profile=False
                )
            except ValueError:
                continue
            if (
                actor.alive
                and actor.controller == role.controller
                and actor.cell is not None
                and not actor.offstage_source
            ):
                eligible[role.actor.token] = actor
        return eligible

    def enemy_roster(self, state):
        if not state.world:
            return {}
        return {
            ref.token: (ref, actor.name)
            for kind, actors in (
                ("npc", state.world.npcs),
                ("gorgon", state.world.gorgons),
            )
            for actor in actors
            if actor.revealed
            and actor.alive
            and actor.cell is not None
            and getattr(actor, "controller", state.handler) == state.handler
            for ref in (ActorRef(kind=kind, entity=actor.id),)
        }

    def turn_record(self, state, scene):
        if not scene:
            return None
        for fact in state.facts:
            if fact.get("kind") == TURN_FACT and fact.get("scene") == scene["id"]:
                return json.loads(fact["body"])
        return None

    def current_turn(self, record, eligible):
        if not record:
            return None
        count = len(record["order"])
        for offset in range(count):
            current = record["offset"] + offset
            token = record["order"][current % count]
            if token in eligible:
                return current, token, current // count + 1
        return None

    def lock_active(self, connection):
        lock = self.game.lock(connection, self.channel)
        return bool(lock and lock["state"] != "released")

    def setup_status(self, viewer, state, scene, eligible, active, locked, paused):
        handler = viewer.user_id == state.handler
        joined = self.joined(viewer, scene)
        record = self.turn_record(state, scene)
        is_active = bool(active and eligible[active[1]].controller == viewer.user_id)
        own_placement = bool(
            any(actor.controller == viewer.user_id for actor in eligible.values())
        )
        placement = self.physical.tasks(viewer) if state.world and joined else []
        reviews = []
        if handler:
            for task in placement:
                if not task["incoming"]:
                    continue
                reviewed = self.physical.get(viewer, task["id"])
                proof = reviewed["review"]["proposal"]
                reviews.append(
                    task
                    | {
                        "cell": proof["girl_cell"],
                        "mode": proof["mode"],
                        "account": proof["account"],
                    }
                )
        return {
            "handler": handler,
            "has_world": state.world is not None,
            "gorgon_types": GORGON_TYPES if handler and not state.world else (),
            "can_open": handler and not paused and (not scene or not joined),
            "joined": joined,
            "can_join": bool(
                scene
                and not joined
                and not handler
                and not record
                and not paused
                and str(viewer.user_id) in state.sheets
            ),
            "can_place": bool(
                joined
                and not handler
                and not own_placement
                and not record
                and not paused
                and not placement
            ),
            "placement_pending": bool(placement and not handler),
            "reviews": reviews if not paused else [],
            "ready": [actor.label for actor in eligible.values()],
            "running": record is not None,
            "round": active[2] if active else None,
            "active": eligible[active[1]].label if active else None,
            "enemy_turn": bool(active and eligible[active[1]].ref.kind != "pilot"),
            "turn": f"{record['epoch']}:{active[0]}" if active else None,
            "yours": is_active,
            "can_end_turn": is_active and not locked and not paused,
            "can_start": bool(
                handler
                and any(actor.ref.kind == "pilot" for actor in eligible.values())
                and not record
                and not locked
                and not paused
            ),
            "can_close": bool(handler and record and not locked and not paused),
        }

    def view(self, viewer):
        with self.commands:
            for attempt in range(3):
                try:
                    return self._view(viewer)
                except BattlefieldChanged:
                    if attempt == 2:
                        raise

    def _view(self, viewer):
        world = self.world.get(viewer)
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            if world["game_revision"] != state.revision:
                raise BattlefieldChanged(
                    "Battlefield changed while loading. Please retry."
                )
            scene = self.scene_row(connection)
            plan = self.facility(state)
            map_view = {
                "board": facility_board(plan).model_dump(mode="json"),
                "facility": {key: plan[key] for key in ("name", "floor", "rooms")},
                "locations": [],
            } if plan else {}
            eligible = self.placed(connection, state, scene)
            active = self.current_turn(self.turn_record(state, scene), eligible)
            acting = eligible[active[1]] if active else None
            bindings = profiles(connection, self.store.campaign_id)
            exposed = []
            for actor in eligible.values():
                if actor.ref.kind != "pilot" or not actor.inside_frame:
                    continue
                try:
                    battle_rules.core_available(state, actor.ref, actor.ref, bindings)
                except ValueError:
                    continue
                exposed.append(actor.ref.token)
            try:
                self.game.unpaused(connection)
                paused = False
            except WorkflowError:
                paused = True
            setup = self.setup_status(
                viewer,
                state,
                scene,
                eligible,
                active,
                self.lock_active(connection),
                paused,
            )
            if self.facilities and setup["can_join"]:
                scenes = tables.m2["m2_scenes"]
                participants = sa.func.json_each(scenes.c.participants_json).table_valued("value")
                joined_channels = connection.scalars(
                    sa.select(scenes.c.channel_id).where(
                        scenes.c.campaign_id == self.store.campaign_id,
                        scenes.c.open.is_(True),
                        sa.select(1).select_from(participants).where(
                            participants.c.value == viewer.user_id
                        ).exists(),
                    )
                )
                if any(
                    (lock := self.game.lock(connection, int(channel))) and lock["state"] != "released"
                    for channel in joined_channels
                ):
                    setup["can_join"] = False
                    setup["entry_blocker"] = "Resolve the pending Play in your active scene before entering Battlefield."
            if self.facilities:
                setup["facility_options"] = [
                    {"id": identity, "name": item["name"]} for identity, item in FACILITY_PLANS.items()
                ] if setup["can_open"] and not plan else []
            enemy_move = None
            if setup["enemy_turn"] and setup["yours"]:
                try:
                    proposal_context(
                        self.game,
                        connection,
                        viewer,
                        state,
                        self.channel,
                        acting.ref,
                        acting.cell,
                        False,
                        "Check movement from the current position.",
                    )
                except (ValueError, WorkflowError):
                    pass
                else:
                    enemy_move = {
                        "id": "move",
                        "label": "Move enemy",
                        "actor": acting.ref.model_dump(mode="json"),
                        "frame": False,
                        "range": {
                            "kind": "board",
                            "label": "Select an enemy destination on the mapped board.",
                        },
                    }
            if (
                setup["handler"]
                and setup["joined"]
                and not setup["running"]
                and not paused
            ):
                setup["can_add_enemies"] = not self.lock_active(connection)
                setup["enemies"] = [
                    {"id": token, "label": label}
                    for token, (ref, label) in self.enemy_roster(state).items()
                    if token not in eligible and (
                        not plan or walkable(plan, resolve(state, ref, bindings, require_current_profile=False).cell)
                    )
                ]
            setup["expose_core"] = (
                acting.ref.token
                if acting
                and setup["yours"]
                and not setup["enemy_turn"]
                and setup["can_end_turn"]
                and acting.inside_frame
                and acting.ref.token not in exposed
                and any(
                    pose.actor == acting.ref and pose.occupied_frame_owner is None
                    for pose in state.placements
                )
                else None
            )
        if setup["joined"] and world["world"]:
            view = super().view(viewer)
            if view["revision"] != state.revision:
                raise BattlefieldChanged(
                    "Battlefield changed while loading. Please retry."
                )
            if not setup["yours"] or paused:
                view["actions"] = [
                    item for item in view["actions"] if item["range"]["kind"] == "order"
                ]
            if enemy_move and not view["busy"]:
                view["actions"].append(enemy_move)
            for actor in view["actors"]:
                actor["enemy"] = (
                    actor["id"] in eligible
                    and eligible[actor["id"]].ref.kind != "pilot"
                )
                actor["core_exposed"] = actor["id"] in exposed
            if setup["handler"] and not paused and not view["busy"]:
                setup["attack_reviews"] = self.attack_reviews(viewer, scene, view)
            for play in view["actions"]:
                for target in play.get("targets", ()):
                    if "owner" in target:
                        target["owner"] = str(target["owner"])
            view["frame_work"] = BattlefieldFrameWork(self.game, self.channel).view(
                viewer,
                proactive=not setup["running"]
                or setup["yours"]
                and not setup["enemy_turn"],
                busy=view["busy"],
            )
            return view | map_view | {"title": plan["name"] if plan else "Campaign Battlefield", "encounter": setup}
        return {
            "title": plan["name"] if plan else "Campaign Battlefield",
            "revision": world["game_revision"],
            "board": world["world"]["board"] if world["world"] and not self.facilities else None,
            "locations": [],
            "actors": [],
            "roster": [],
            "actions": [],
            "choices": [],
            "history": [],
            "declarations": {},
            "shared": True,
            "busy": False,
            "encounter": setup,
        } | map_view

    def attack_reviews(self, viewer, scene, view):
        actors = {actor["id"]: actor["label"] for actor in view["actors"]}
        reviews = []
        for item in self.combat.tasks(viewer):
            if (
                not item["incoming"]
                or item["scene"] != scene["id"]
                or item["source_action"]
            ):
                continue
            saved = Context.model_validate(
                self.combat.context(viewer, item["id"])["context"]
            )
            play = saved.declaration.play
            if play not in DECLARED_PLAYS.values():
                continue
            reviews.append(
                {
                    "id": item["id"],
                    "play": play,
                    "label": PLAY_LABELS[play],
                    "actor": actors.get(saved.declaration.actor.token, "Pilot"),
                    "target": actors.get(saved.declaration.target.token, "Target"),
                    "account": saved.declaration.account,
                }
            )
        return reviews

    def actions(self, connection, viewer, state, scene, pilot, movement, battle):
        actions = super().actions(
            connection, viewer, state, scene, pilot, movement, battle
        )
        try:
            self.game.pilot_cast(connection, state, scene, owners=(viewer.user_id,))
        except WorkflowError:
            # Mixed casts use only the actor-aware adapters wired into this board.
            return [
                action
                for action in actions
                if action["id"] in ("move", "engage", ASSAULT, CORE)
            ]
        return actions

    def handler_only(self, connection, viewer, state):
        self.world.missions._handler(connection, viewer)
        if state.handler != viewer.user_id:
            raise WorkflowError(
                "Activate a pilot to finalize the campaign Handler appointment."
            )

    def set_enemy(self, viewer, key, command, body, scene_id):
        if command == "create-enemy":
            if (
                body.keys() != {"revision", "name", "cell", "account"}
                or type(body["revision"]) is not int
            ):
                raise ValueError
            identity = str(uuid5(UUID(self.store.campaign_id), key + ":enemy"))
            npc = Npc.model_validate_json(
                json.dumps(
                    {
                        "id": identity,
                        "name": body["name"],
                        "cell": body["cell"],
                        "detail": body["account"],
                        "controller": viewer.user_id,
                        "jobs": ["guard"],
                        "revealed": True,
                    }
                )
            )
            self.world.npc(viewer, key, body["revision"], npc)
            target = ActorRef(kind="npc", entity=identity).token
            cast_key = key + ":cast"
        else:
            if (
                body.keys() != {"revision", "target"}
                or type(body["revision"]) is not int
            ):
                raise ValueError
            target = body["target"]
            cast_key = key
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            cast, _ = self.casts._current(connection, state, self.channel)
            items = self.enemy_roster(state)
            if (
                cast.id != scene_id
                or not isinstance(target, str)
                or target not in items
            ):
                raise WorkflowError(
                    "Choose a visible, mapped enemy controlled by the Handler."
                )
            ref, _ = items[target]
            if command == "create-enemy" and any(
                role.actor == ref for role in cast.roles
            ):
                return {"actor": target}
            revision = state.revision if command == "create-enemy" else body["revision"]
            cast_revision = cast.revision
        self.casts.change(
            viewer, cast_key, self.channel, revision, cast_revision, "join", ref
        )
        return {"actor": target}

    def open_world(self, viewer, key, data):
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            self.handler_only(connection, viewer, state)
        if data.keys() == {"revision"} and state.world:
            if type(data["revision"]) is not int or data["revision"] != state.revision:
                raise WorkflowError("Refresh the current campaign map.")
        else:
            if data.keys() != {
                "revision",
                "locations",
                "name",
                "type",
                "base",
                "assets",
                "weakness",
            }:
                raise ValueError
            if (
                type(data["revision"]) is not int
                or type(data["base"]) is not int
                or not 0 <= data["base"] < 3
            ):
                raise ValueError
            if (
                data["type"] not in GORGON_TYPES
                or not isinstance(data["locations"], list)
                or not isinstance(data["assets"], list)
            ):
                raise ValueError
            if len(data["locations"]) != 8 or len(data["assets"]) != 2:
                raise WorkflowError("Use eight location names and two Class 0 Assets.")

            def identity(label):
                return str(uuid5(UUID(self.store.campaign_id), key + ":" + label))

            locations = tuple(
                Location(id=identity(str(i)), name=name, cell=cell, kind=kind)
                for i, (name, cell, kind) in enumerate(
                    zip(data["locations"], LOCATION_CELLS, LOCATION_KINDS, strict=True)
                )
            )
            assets = tuple(
                Asset(
                    id=identity("asset:" + str(i)),
                    name=name,
                    description=name,
                    family="gorgon",
                )
                for i, name in enumerate(data["assets"])
            )
            secret = Gorgon(
                id=identity("class-zero"),
                name=data["name"],
                gorgon_class="benevolent",
                types=(data["type"],),
                cell=locations[data["base"]].cell,
                assets=assets,
                core_plan=CorePlan(
                    assets=tuple(asset.id for asset in assets),
                    weakness=data["weakness"],
                ),
            )
            self.world.initialize(
                viewer,
                key,
                data["revision"],
                Board(minimum=(0, 0), maximum=(9, 9)),
                locations,
                secret,
            )
        self.bind_battlefield(viewer)
        return {"opened": True}

    def bind_battlefield(self, viewer):
        with self.store.engine.connect() as connection:
            scene = self.scene_row(connection)
        if not scene:
            self.game.bind_scene(
                replace(viewer, is_administrator=True),
                "activity-battlefield-bind",
                self.channel,
            )
        if not self.game.scene_info(viewer, self.channel)["joined"]:
            self.game.join_scene(
                viewer, "activity-battlefield-handler-entry", self.channel
            )
    def change_turn(self, viewer, key, command, body):
        if body.keys() != {"revision"} or type(body["revision"]) is not int:
            raise ValueError

        def operation(connection):
            state = load_state(connection, self.store.campaign_id)
            scene = self.scene_row(connection)
            if not self.joined(viewer, scene) or not state.world:
                raise WorkflowError("Enter the mapped Battlefield first.")
            if body["revision"] != state.revision or self.lock_active(connection):
                raise WorkflowError(
                    "Refresh the Battlefield and resolve any pending Play."
                )
            eligible = self.placed(connection, state, scene)
            record = self.turn_record(state, scene)
            if command == "end-turn":
                active = self.current_turn(record, eligible)
                if not active or eligible[active[1]].controller != viewer.user_id:
                    raise WorkflowError("Only the active pilot can end this turn.")
                record["offset"] = active[0] + 1
            else:
                self.handler_only(connection, viewer, state)
                if command == "start-turns":
                    if record or not any(
                        actor.ref.kind == "pilot" for actor in eligible.values()
                    ):
                        raise WorkflowError("Place a pilot and open turns once.")
                    record = {
                        "order": list(eligible),
                        "offset": 0,
                        "epoch": str(uuid4()),
                    }
                else:
                    if not record:
                        raise WorkflowError("There are no open turns.")
                    record = None
            state.facts = [
                fact
                for fact in state.facts
                if not (
                    fact.get("kind") == TURN_FACT and fact.get("scene") == scene["id"]
                )
            ]
            if record:
                state.facts.append(
                    {
                        "kind": TURN_FACT,
                        "scene": scene["id"],
                        "body": json.dumps(record),
                    }
                )
            self.game.event(
                connection,
                viewer.user_id,
                key,
                "activity.battlefield." + command,
                state,
                channel=self.channel,
            )
            return {"revision": state.revision}

        def authorize(connection):
            self.game.authorize(connection, viewer)
            self.game.unpaused(connection)

        return self.store._write(
            viewer,
            key,
            "activity.battlefield." + command,
            body,
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def perform(self, viewer, key, command, body):
        self.authorize(viewer)
        with self.commands:
            if command == "open":
                if self.facilities and "facility" in body:
                    return self.open_facility(viewer, key, body)
                if self.facilities:
                    with self.store.engine.connect() as connection:
                        if self.facility(load_state(connection, self.store.campaign_id)) is None:
                            raise WorkflowError("Select a facility before opening Battlefield admission.")
                return self.open_world(viewer, key, body)
            if command in ("start-turns", "end-turn", "close-turns"):
                return self.change_turn(viewer, key, command, body)
            with self.store.engine.connect() as connection:
                state = load_state(connection, self.store.campaign_id)
                scene = self.scene_row(connection)
                plan = self.facility(state)
                record = self.turn_record(state, scene)
                if command == "join":
                    if body:
                        raise ValueError
                    if not scene or record and not self.joined(viewer, scene):
                        raise WorkflowError(
                            "The Handler must open Battlefield admission before you enter."
                        )
                    if plan and (sheet := state.sheets.get(str(viewer.user_id))):
                        current = resolve(
                            state,
                            ActorRef(kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id),
                            profiles(connection, self.store.campaign_id),
                            require_current_profile=False,
                        )
                        if current.cell is not None and not walkable(plan, current.cell):
                            raise WorkflowError("Your saved placement is outside the facility's accessible floor.")
                    return self.scene.enter(viewer, key)
                if not self.joined(viewer, scene):
                    raise WorkflowError("Enter the Battlefield first.")
                if command == "frame-work":
                    answer = body.get("answer")
                    fields = answer.get("values") if isinstance(answer, dict) else None
                    if not isinstance(fields, dict):
                        raise ValueError("Choose the current Frame decision.")
                    action = body.get("action")
                    effect = None
                    if action == "wyvern_use":
                        effect = json.loads(fields.get("use", "null"))
                        if not isinstance(effect, dict):
                            raise ValueError("Choose an available Roused effect.")
                    proactive = action in ("janus_start", "wyvern_start") or (
                        effect is not None and effect.get("kind") != "too_big"
                    )
                    if proactive and record:
                        eligible = self.placed(connection, state, scene)
                        active = self.current_turn(record, eligible)
                        if (
                            not active
                            or eligible[active[1]].ref.kind != "pilot"
                            or eligible[active[1]].controller != viewer.user_id
                        ):
                            raise WorkflowError(
                                "Wait for your pilot's turn before starting this Frame action."
                            )
                    return super().perform(viewer, key, command, body)
                if command in ("create-enemy", "add-enemy"):
                    self.handler_only(connection, viewer, state)
                    if record or self.lock_active(connection):
                        raise WorkflowError(
                            "Close turns and resolve pending Plays before changing enemies."
                        )
                    if plan:
                        if command == "create-enemy":
                            cell = body.get("cell")
                        else:
                            found = self.enemy_roster(state).get(body.get("target"))
                            if not found:
                                raise WorkflowError("Choose a visible enemy on this facility map.")
                            cell = resolve(
                                state, found[0], profiles(connection, self.store.campaign_id),
                                require_current_profile=False,
                            ).cell
                        if not walkable(plan, cell):
                            raise WorkflowError("Deploy the enemy on an accessible facility square.")
                    return self.set_enemy(viewer, key, command, body, scene["id"])
                if command == "place":
                    if body.keys() != {"revision", "cell", "mode", "account"}:
                        raise ValueError
                    if record or body["mode"] not in ("piloting", "outside_frame"):
                        raise WorkflowError("Set initial positions before turns start.")
                    if plan and not walkable(plan, body["cell"]):
                        raise WorkflowError("Place your pilot on an accessible facility square.")
                    if any(
                        actor.controller == viewer.user_id
                        for actor in self.placed(connection, state, scene).values()
                    ):
                        raise WorkflowError(
                            "This pilot already has an initial placement."
                        )
                    original = self.physical.preview(viewer)
                    proof = InitialPlacement.model_validate_json(
                        json.dumps(
                            {
                                "actor": original["actor"],
                                "frame_instance": original["frame_instance"],
                                "girl_cell": body["cell"],
                                "frame_cell": body["cell"],
                                "mode": body["mode"],
                                "account": body["account"],
                                "facts_confirmed": True,
                            }
                        )
                    )
                    return self.physical.propose(viewer, key, body["revision"], proof)
                if command == "review-placement":
                    if body.keys() != {"id", "revision", "decision", "account"}:
                        raise ValueError
                    if record:
                        raise WorkflowError(
                            "Finish the current encounter before changing initial placements."
                        )
                    return self.physical.decide(
                        viewer,
                        key,
                        body["id"],
                        body["revision"],
                        body["decision"],
                        body["account"],
                    )
                if command in (
                    "choice",
                    "assault-review",
                    "core-review",
                    "disobey_orders",
                ):
                    return super().perform(viewer, key, command, body)
                if command == "issue-order":
                    raise WorkflowError(
                        "This Play needs its own Handler workflow in the private Battlefield."
                    )
                eligible = self.placed(connection, state, scene)
                active = self.current_turn(record, eligible)
                if not active or eligible[active[1]].controller != viewer.user_id:
                    raise WorkflowError("Wait for the turn of an actor you control.")
                if body.pop("turn", None) != f"{record['epoch']}:{active[0]}":
                    raise WorkflowError(
                        "Refresh the current turn before submitting this action."
                    )
                if (
                    command == "move"
                    and ActorRef.model_validate(body.get("actor")).token != active[1]
                ):
                    raise WorkflowError("Move only your active pilot.")
                if plan and command == "move" and not walkable(plan, body.get("destination")):
                    raise WorkflowError("Move to an accessible facility square.")
                self.game.unpaused(connection)
                if command == "core-expose":
                    if (
                        body.keys() != {"revision", "target", "account", "confirmed"}
                        or type(body["revision"]) is not int
                    ):
                        raise ValueError
                    actor = eligible[active[1]]
                    if (
                        body["confirmed"] is not True
                        or actor.ref.kind != "pilot"
                        or body["target"] != active[1]
                        or self.lock_active(connection)
                    ):
                        raise WorkflowError(
                            "Voluntarily expose only your own occupied Frame Core on your turn."
                        )
                    account = body["account"]
                    if (
                        not isinstance(account, str)
                        or not account.strip()
                        or len(account) > 1200
                    ):
                        raise ValueError
                    return self.combat.expose(
                        viewer, key, body["revision"], actor.ref, account, willing=True
                    )
                if eligible[active[1]].ref.kind != "pilot" and command != "move":
                    raise WorkflowError(
                        "The Handler can move the active enemy or end its turn."
                    )
                if command in (FLIRT, BENEATH):
                    target = body.get("target")
                    if (
                        not isinstance(target, str)
                        or not 1 <= len(target) <= 20
                        or not target.isascii()
                        or not target.isdecimal()
                    ):
                        raise ValueError
                    body["target"] = int(target)
            return super().perform(viewer, key, command, body)
