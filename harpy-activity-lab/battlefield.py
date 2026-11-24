"""Single-account tactical drill backed by HarpyEngine's native services."""

import json
from dataclasses import asdict

import sqlalchemy as sa
from girlframe.database import tables
from girlframe.discord_adapter.m2_ui import choice_fields
from girlframe.engine import m3_battle as battle_rules
from girlframe.engine.frame_classes import FRAME_CLASSES
from girlframe.engine.m2 import (
    ChoiceAnswer,
    GameState,
    PlayInput,
)
from girlframe.engine.m2_registry import REGISTRY
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_am import require_freedom
from girlframe.engine.m3_appearance_matrix import damages
from girlframe.engine.m3_battle_state import Context, Declaration
from girlframe.engine.m3_collateral import Selection as CollateralSelection
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import KINDS
from girlframe.engine.m3_punishments import Details as PunishmentDetails
from girlframe.engine.m3_world import distance
from girlframe.engine.m3_world_state import Board
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state, public_sheet
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_beneath import prepare as prepare_beneath
from girlframe.services.m3_collateral import CollateralService
from girlframe.services.m3_defeat import start_work as begin_defeat_work
from girlframe.services.m3_engage import prepare as prepare_engage
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_movement import MovementService, proposal_context
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from pydantic import ValidationError

from battery_play import BATTERY, BATTERY_CHOICES, battery_choice, ready_batteries
from battlefield_frame_work import (
    INTERCEPT,
    ROUSE,
    ROUSE_COST,
    BattlefieldFrameWork,
    available_heat,
)
from consume_regrowth import KIND as PARTAKE
from defeat_play import DEFEAT, DEFEAT_CHOICES, defeat_choice
from native_scene_forms import (
    RISK_CHOICE,
    TAG_DECISIONS,
    risk_choice_card,
    tag_choice_card,
)
from play_catalog import (
    DISOBEY_ORDERS,
    RECEIVE_ORDERS,
    character_plays,
    frame_upgrades,
    play_category,
)
from rulebook_text import FLIRT_QUESTION_TEXT, printed_fields, sensor_question_text
from scene_plays import TestSceneGateway, completed_flirt, start_game_worker

CHANNEL = 900
ENGAGE = next(item for item in REGISTRY["plays"] if item["play_id"] == "engage")
ASSAULT = "all_out_assault"
CORE = "go_for_the_core"
KEEP = "keep_your_head"
SENSORS = "check_sensors"
FLIRT = "flirt"
BENEATH = "put_someone_beneath_you"
BENEATH_CHOICES = ("beneath_select", "beneath_details", "beneath_pin_response")
BENEATH_PUNISHMENTS = ("quality_time", "demotion", "stimulant_injection")
FOLLOW_THROUGH = "flirt_followthrough"
REJECT_TAG = "reject_tag"
FOLLOWUPS = frozenset({FOLLOW_THROUGH, REJECT_TAG})
HANDLER_FORMS = frozenset({"brief", "escalate", "expectation"})
FLIRT_CHOICES = (
    "actor_flirt",
    "target_flirt",
    "actor_flirt_answer",
    "flirt_owe_tag",
    "flirt_escape",
)
DECLARED_PLAYS = {"assault": ASSAULT, "core": CORE}
PLAYS = {item["play_id"]: item for item in REGISTRY["plays"]}
PLAY_LABELS = {
    ENGAGE["play_id"]: "Engage",
    ASSAULT: "All-Out Assault",
    CORE: "Go for the Core",
    KEEP: "Keep Your Head",
    SENSORS: "Check Sensors",
    FLIRT: "Flirt",
    BENEATH: "Put Someone Beneath You",
    DEFEAT: "Defeat",
    BATTERY: "Living Battery",
    ROUSE: "Rouse the Frame",
    FOLLOW_THROUGH: "Flirt Follow-through",
    REJECT_TAG: "Reject Tag",
    RECEIVE_ORDERS: "Receive Orders",
    DISOBEY_ORDERS: "Disobey Orders",
}
ORDER_CHOICES = {"order_response": RECEIVE_ORDERS, "order_disobey": DISOBEY_ORDERS}


class BattlefieldChanged(WorkflowError):
    """A concurrent engine write interrupted this projection."""


def seed_battlefield(missions, handler, pilot, opponent):
    from test_world import initial

    store = missions.store
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            ),
        }
    )
    world = WorldService(missions)
    initial_world = initial()
    revision = world.get(pilot)["game_revision"]
    world.initialize(
        handler,
        "drill-board",
        revision,
        Board(minimum=(0, 0), maximum=(8, 5)),
        initial_world.locations,
        initial_world.gorgons[0],
    )
    physical = PhysicalService(store)
    for person, cell in ((pilot, (1, 1)), (opponent, (4, 1))):
        actual = physical.preview(person)
        request = physical.propose(
            person,
            f"drill-place-{person.user_id}",
            actual["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(actual["actor"]),
                frame_instance=actual["frame_instance"],
                girl_cell=cell,
                frame_cell=cell,
                mode="piloting",
                account="Isolated tactical drill starting position.",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            handler,
            f"drill-placement-review-{person.user_id}",
            request["id"],
            request["revision"],
            "accept",
            "Confirmed drill placement.",
        )


class Battlefield:
    def __init__(
        self,
        missions,
        handler,
        pilot,
        opponent,
        *,
        dice=None,
        shared=False,
        channel=CHANNEL,
        private=False,
    ):
        self.store = missions.store
        self.game = GameService(self.store, dice=dice)
        self.movement = MovementService(self.game)
        self.combat = BattleService(self.store)
        self.world = WorldService(missions)
        self.registry = missions.access.registry
        self.owner = pilot
        self.shared = shared
        self.private = private
        self.channel = channel
        self.roles = {"pilot": pilot, "handler": handler, "opponent": opponent}
        self.gateway = (
            None
            if private
            else TestSceneGateway(
                self.store.policy.sandbox / "activity-delivery.sqlite3",
                channel,
                handler,
                pilot,
                self.store.policy.application_id,
                extra_viewers=(opponent,),
            )
        )

    def start_worker(self):
        return start_game_worker(self.game, self.gateway)

    def authorize(self, viewer):
        if self.private:
            with self.store.engine.connect() as connection:
                self.game.authorize(connection, viewer, game=False)
            return
        if viewer != self.owner and not (
            self.shared and viewer == self.roles["opponent"]
        ):
            raise WorkflowError(
                "This tactical drill belongs to its configured test pilot."
            )

    def recent_actions(self, connection, viewer, state):
        table = tables.m2["m2_actions"]
        play = sa.func.json_extract(table.c.body_json, "$.play")
        visible = table.c.actor_id == str(viewer.user_id)
        if self.shared:
            visible = sa.or_(
                visible,
                sa.and_(
                    play.in_((FLIRT, BENEATH)),
                    sa.func.json_extract(table.c.body_json, "$.prepared.target")
                    == viewer.user_id,
                ),
                sa.and_(
                    play == FOLLOW_THROUGH,
                    sa.func.json_extract(table.c.body_json, "$.obligation_id").in_(
                        [
                            item.id
                            for item in state.obligations
                            if item.kind == FOLLOW_THROUGH
                            and item.target == viewer.user_id
                        ]
                    ),
                ),
                sa.and_(
                    play == BATTERY,
                    sa.func.json_extract(table.c.body_json, "$.janus.target_controller")
                    == viewer.user_id,
                ),
            )
        return connection.scalars(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                visible,
                table.c.channel_id == str(self.channel),
                table.c.parent_id.is_(None),
                play.in_(PLAY_LABELS),
            )
            .order_by(sa.literal_column("rowid").desc())
            .limit(11)
        ).all()

    def view(self, viewer):
        self.authorize(viewer)
        world = self.world.get(viewer)
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet:
                moves = self.movement.menu(viewer, self.channel)
                combat = self.combat.preview(viewer, self.channel)
            elif self.private and viewer.user_id == state.handler:
                moves = {"revision": state.revision}
                combat = self.combat.preview(viewer, self.channel)
            else:
                moves = {"revision": state.revision}
                combat = {"revision": state.revision, "actors": []}
            if {world["game_revision"], moves["revision"], combat["revision"]} != {
                state.revision
            }:
                raise BattlefieldChanged(
                    "The drill changed while loading. Please retry."
                )
            scene = self.game.scene(connection, self.channel)
            lock = self.game.lock(connection, self.channel)
            busy = bool(lock and lock["state"] != "released")
            bound = profiles(connection, self.store.campaign_id)
            actors = [
                {
                    "id": row["token"],
                    "label": row["name"],
                    "controlled": row["owned"],
                    "cell": resolve(
                        state, ActorRef.model_validate(row["ref"]), bound
                    ).cell,
                    "asset_count": len(row["assets"]),
                }
                for row in combat["actors"]
            ]
            actions = []
            if sheet and not busy:
                pilot_ref = ActorRef(
                    kind="pilot",
                    entity=str(viewer.user_id),
                    incarnation=sheet.character_id,
                )
                actions = self.actions(
                    connection, viewer, state, scene, pilot_ref, moves, combat
                )
            declarations = (
                self.declarations(viewer, state, bound, combat) if sheet and not busy else {}
            )
            recent = self.recent_actions(connection, viewer, state)
            exposure = (
                self.exposure_options(state, bound, combat)
                if sheet and not busy and not self.shared
                else []
            )
            if busy and self.shared:
                held = self.game.action(connection, lock["action_id"])
                if (
                    viewer.user_id in held["data"]["participants"]
                    and held["id"] not in recent
                ):
                    recent.insert(0, held["id"])
            latest = self.game.action(connection, recent[0]) if recent else None
            latest_play = latest["data"]["play"] if latest else None
            child_id = (
                self.last_child(connection, latest["id"])
                if latest_play in (ASSAULT, CORE, RECEIVE_ORDERS, FLIRT, BENEATH)
                or latest
                and latest["data"].get("wyvern_deflected")
                else None
            )
            target_ended = bool(
                latest
                and latest["data"]["play"] == CORE
                and latest["data"].get("battle", {}).get("fatal_event")
            )
            roster = []
            for row in combat["actors"]:
                ref = ActorRef.model_validate(row["ref"])
                roster_sheet = (
                    state.sheets.get(ref.entity) if ref.kind == "pilot" else None
                )
                if roster_sheet and roster_sheet.character_id == ref.incarnation:
                    public = public_sheet(roster_sheet, state)
                    profile = None
                    if row["owned"]:
                        runtime = roster_sheet.frame_runtime
                        profile = {
                            "frame": roster_sheet.frame,
                            "frame_name": runtime.frame_name
                            if runtime
                            else roster_sheet.review.creation.frame_name,
                            "heat": roster_sheet.heat,
                            "tags": [tag.label for tag in roster_sheet.tags],
                            "upgrades": frame_upgrades(
                                self.registry, runtime.model_dump() if runtime else None
                            ),
                            "assets": [
                                {
                                    "id": asset.id,
                                    "name": asset.name,
                                    "damaged": asset.damaged,
                                    "void": asset.void,
                                    "description": asset.description,
                                }
                                for asset in roster_sheet.assets
                                if asset.family == "frame"
                            ],
                        }
                    roster.append(
                        {
                            "id": row["token"],
                            "label": row["name"],
                            "controlled": row["owned"],
                            "status": public.get("rank"),
                            "frame_name": public.get("frame_name"),
                            "profile": profile,
                            "girl": roster_sheet.girl,
                            "frame": roster_sheet.frame,
                            "frame_class": FRAME_CLASSES.get(roster_sheet.frame),
                            "plays": character_plays(
                                self.registry,
                                roster_sheet,
                                owns_sheet=row["owned"],
                                state=state,
                            ),
                        }
                    )
        identity = recent[0] if recent else None
        play = self.game.inspect(viewer, identity) if identity else None
        if (
            latest_play == FOLLOW_THROUGH
            and latest["state"] == "complete"
            and self.shared
        ):
            item = next(
                (
                    row
                    for row in state.obligations
                    if row.id == latest["data"]["obligation_id"]
                    and viewer.user_id in (row.owner, row.target)
                ),
                None,
            )
            if item:
                play["result"] = {
                    key: latest["data"]["result"][key]
                    for key in ("confirmed", "response")
                }
        child = self.game.inspect(viewer, child_id) if child_id else None
        history = []
        for action_id in recent[1:]:
            previous = self.game.inspect(viewer, action_id)
            if previous["state"] != "complete":
                continue
            if previous["play"] == BENEATH:
                with self.store.engine.connect() as connection:
                    past_child = self.last_child(connection, action_id)
                if past_child:
                    previous["beneath_response"] = self.game.inspect(viewer, past_child)
            if previous["play"] == RECEIVE_ORDERS and previous["result"].get(
                "response_play"
            ):
                previous["refusal"] = self.game.inspect(
                    viewer, previous["result"]["response_play"]
                )
            history.append(previous)
        choices = (
            self.choices(
                child["id"]
                if child and child["state"] not in ("complete", "aborted")
                else identity,
                viewer,
                latest["actor_id"],
            )
            if play and play["state"] not in ("complete", "aborted")
            else []
        )
        if latest_play == RECEIVE_ORDERS and lock and lock["action_id"] == identity:
            actions.extend(self.order_actions(viewer, latest, choices))
        visible_actors = {actor["token"]: actor for actor in combat["actors"]}
        impacts = []
        for hit in damages(state):
            actor = visible_actors.get(hit.target.token)
            if hit.action != identity or not actor:
                continue
            asset = next(
                (entry for entry in actor["core_assets"] if entry["id"] == hit.asset),
                None,
            )
            if asset is not None:
                impacts.append({"actor": actor["name"], "asset": asset["name"]})
        return {
            "title": "Relay perimeter drill",
            "revision": state.revision,
            "sheet_revision": sheet.revision if sheet else None,
            "heat_options": self.heat_options(sheet) if sheet else [],
            "board": world["world"]["board"],
            "locations": [
                {
                    "name": location["name"],
                    "kind": location["kind"],
                    "cell": location["cell"],
                }
                for location in world["world"]["locations"]
            ],
            "actors": actors,
            "roster": roster,
            "actions": [
                {**action, "category": play_category(action["id"])}
                if action["id"] != "move"
                else action
                for action in actions
            ],
            "declaration": declarations.get(ASSAULT),
            "declarations": declarations,
            "core_exposure_targets": exposure,
            "play": play,
            "wyvern_response": child
            if latest and latest["data"].get("wyvern_deflected")
            else None,
            "history": history,
            "impacts": impacts,
            "choices": choices,
            "frame_work": []
            if self.private
            else BattlefieldFrameWork(self.game, self.channel).view(viewer, busy=busy),
            "shared": self.shared,
            "counter": child if latest_play == CORE else None,
            "refusal": child if latest_play == RECEIVE_ORDERS else None,
            "order_text": latest["data"].get("order_text")
            if latest_play == RECEIVE_ORDERS
            and latest["actor_id"] == str(viewer.user_id)
            else None,
            "can_issue_order": bool(sheet and not busy and not self.shared),
            "flirt_escape": child if latest_play == FLIRT else None,
            "beneath_response": child if latest_play == BENEATH else None,
            "target_ended": target_ended,
            "busy": busy,
        }

    def actions(self, connection, viewer, state, scene, pilot, movement, battle):
        available = []
        controlled = next(
            (actor for actor in movement["actors"] if actor["id"] == pilot.token), None
        )
        if controlled:
            cell = tuple(controlled["cell"])
            try:
                proposal_context(
                    self.game,
                    connection,
                    viewer,
                    state,
                    self.channel,
                    pilot,
                    cell,
                    controlled["piloting"] is True,
                    "Check movement from the current position.",
                )
            except WorkflowError:
                pass
            else:
                available.append(
                    {
                        "id": "move",
                        "label": "Move",
                        "actor": controlled["ref"],
                        "frame": controlled["piloting"] is True,
                        "range": {
                            "kind": "board",
                            "label": "Destination must be on the mapped board.",
                        },
                    }
                )
        targets = []
        bound = profiles(connection, self.store.campaign_id)
        origin = resolve(state, pilot, bound).cell
        for actor in battle["actors"]:
            if actor["owned"]:
                continue
            ref = ActorRef.model_validate(actor["ref"])
            try:
                self.game.unpaused(connection)
                prepare_engage(
                    self.game,
                    connection,
                    viewer,
                    state,
                    scene,
                    PlayInput(
                        play=ENGAGE["play_id"],
                        context=ENGAGE["trigger"],
                        trigger_confirmed=True,
                        heat=0,
                        target_actor=ref,
                    ),
                )
            except (WorkflowError, ValueError):
                continue
            target = resolve(state, ref, bound)
            targets.append(
                {
                    "id": actor["token"],
                    "label": actor["name"],
                    "ref": actor["ref"],
                    "separation": distance(origin, target.cell)
                    if origin is not None and target.cell is not None
                    else None,
                }
            )
        if targets:
            available.append(
                {
                    "id": ENGAGE["play_id"],
                    "label": "Engage",
                    "trigger": ENGAGE["trigger"],
                    "range": {
                        "kind": "scene",
                        "label": "Actual opposing actor in the same scene.",
                    },
                    "targets": targets,
                }
            )
        if battle["actors"]:
            self.add_declared_plays(connection, viewer, state, bound, battle, available)
        available.append(
            {
                "id": KEEP,
                "label": PLAY_LABELS[KEEP],
                "trigger": PLAYS[KEEP]["trigger"],
                "range": {
                    "kind": "self",
                    "label": "Resolve what this pilot is trying to endure.",
                },
            }
        )
        if any(actor["owned"] and actor["piloting"] for actor in battle["actors"]):
            available.append(
                {
                    "id": SENSORS,
                    "label": PLAY_LABELS[SENSORS],
                    "trigger": PLAYS[SENSORS]["trigger"],
                    "range": {"kind": "scene", "label": "Ask about the current scene."},
                }
            )
        prohibited = {
            item.play for item in state.sheets[str(viewer.user_id)].blocked_plays
        }
        if self.shared:
            targets = self.pilot_targets(connection, viewer, state, scene)
            if targets:
                available.append(
                    {
                        "id": FLIRT,
                        "label": PLAY_LABELS[FLIRT],
                        "trigger": PLAYS[FLIRT]["trigger"],
                        "range": {
                            "kind": "scene",
                            "label": "Ask another active pilot in the scene. Its player answers from its own Activity.",
                        },
                        "targets": targets,
                    }
                )
            piloting = bool(resolve(state, pilot, bound).piloting)
            eligible = []
            for target in targets:
                try:
                    prepare_beneath(
                        self.game,
                        connection,
                        viewer,
                        PlayInput(
                            play=BENEATH,
                            target=target["owner"],
                            piloting=piloting,
                            context="Check eligible scene targets.",
                            heat=0,
                            trigger_confirmed=True,
                        ),
                        state,
                    )
                except (ValueError, WorkflowError):
                    continue
                eligible.append(target)
            if eligible:
                available.append(
                    {
                        "id": BENEATH,
                        "label": PLAY_LABELS[BENEATH],
                        "trigger": "Describe the confrontation",
                        "range": {
                            "kind": "social",
                            "label": "Challenge another pilot. The roll determines who chooses effects.",
                        },
                        "targets": eligible,
                    }
                )
        for item in state.obligations:
            if (
                item.owner != viewer.user_id
                or item.state != "pending"
                or item.kind not in FOLLOWUPS
            ):
                continue
            if item.kind == FOLLOW_THROUGH and (
                not self.shared or item.target not in scene["participants"]
            ):
                continue
            source = self.game.action(connection, item.action)
            if source["scene_id"] != scene["id"]:
                continue
            if item.kind == FOLLOW_THROUGH and (
                source["data"]["play"] != FLIRT or source["state"] != "complete"
            ):
                continue
            detail = (
                item.details.get("wanted")
                if item.kind == FOLLOW_THROUGH
                else next(
                    (
                        tag.label
                        for tag in state.sheets[str(viewer.user_id)].tags
                        if tag.id == item.details.get("tag")
                    ),
                    None,
                )
            )
            if not detail:
                continue
            available.append(
                {
                    "id": item.id,
                    "label": PLAY_LABELS[item.kind],
                    "range": {"kind": "followup", "label": detail},
                    "obligation": item.id,
                }
            )
        if state.sheets[str(viewer.user_id)].frame == "JANUS":
            targets = ready_batteries(self.game, viewer, self.channel)
            if targets:
                available.append(
                    {
                        "id": BATTERY,
                        "label": PLAY_LABELS[BATTERY],
                        "trigger": "Describe your use of the reviewed neural link",
                        "range": {
                            "kind": "connection",
                            "label": "Use an actual connected battery. HarpyEngine counts its Tags.",
                        },
                        "targets": targets,
                    }
                )
        return [action for action in available if action["id"] not in prohibited]

    def pilot_targets(self, connection, viewer, state, scene):
        joined = self.game.scene_info(viewer, self.channel)
        humans = (self.owner.user_id, self.roles["opponent"].user_id)
        targets = []
        for owner in joined.get("pilots", ()):
            if owner == viewer.user_id or not self.private and owner not in humans:
                continue
            try:
                self.game.pilot_cast(
                    connection, state, scene, owners=(viewer.user_id, owner)
                )
            except WorkflowError:
                continue
            sheet = state.sheets[str(owner)]
            ref = ActorRef(
                kind="pilot", entity=str(owner), incarnation=sheet.character_id
            )
            targets.append(
                {"id": ref.token, "label": joined["labels"][str(owner)], "owner": owner}
            )
        return targets

    @staticmethod
    def heat_options(sheet):
        return available_heat(sheet)

    def add_declared_plays(self, connection, viewer, state, bound, battle, available):
        from girlframe.services.m3_battle import authorize

        try:
            authorize(self.game, connection, viewer)
        except WorkflowError:
            return
        for play in DECLARED_PLAYS.values():
            option = self.declared_options(state, bound, battle, play)
            if option is not None:
                available.append(option)

    @staticmethod
    def declared_options(state, bound, battle, play, *, actor_token=None):
        acting = next((item for item in battle["actors"] if item["owned"] and (
            actor_token is None or item["token"] == actor_token
        )), None)
        if acting is None:
            return None
        origin_ref = ActorRef.model_validate(acting["ref"])
        origin = resolve(state, origin_ref, bound)
        weapons = []
        for asset in acting["core_assets"] if play == CORE else acting["assets"]:
            try:
                battle_rules.owned_asset(
                    state,
                    origin_ref,
                    asset["id"],
                    bound,
                    attacking=True,
                    allow_damaged=play == CORE,
                )
            except ValueError:
                continue
            weapons.append(asset)
        if not weapons or origin.offstage_source is not None:
            return None
        targets = []
        for item in battle["actors"]:
            if (item["owned"] if actor_token is None else item["token"] == actor_token) or (
                play == ASSAULT and not item["assets"]
            ):
                continue
            ref = ActorRef.model_validate(item["ref"])
            actual = resolve(state, ref, bound)
            if (
                actual.offstage_source is not None
                or ref.kind == "pilot"
                and actual.inside_frame is None
            ):
                continue
            if play == CORE:
                try:
                    battle_rules.core_available(state, ref, origin_ref, bound)
                except ValueError:
                    continue
            targets.append(
                {
                    "id": item["token"],
                    "label": item["name"],
                    "assets": item["assets"],
                    "separation": distance(origin.cell, actual.cell)
                    if origin.cell is not None and actual.cell is not None
                    else None,
                }
            )
        if targets:
            return {
                "id": play,
                "label": PLAY_LABELS[play],
                "trigger": "Describe the opening to the exposed Core"
                if play == CORE
                else "Describe the opening for the assault",
                "range": {
                    "kind": "adjudicated",
                    "label": "Strike an exposed Core. The Handler confirms opening and reach."
                    if play == CORE
                    else "The appointed Handler must confirm the opening and reach before the roll.",
                },
                "attacking_assets": weapons,
                "targets": targets,
            }
        return None

    def declarations(self, viewer, state, bound, battle):
        used = {
            fact.get("context")
            for fact in state.facts
            if fact.get("kind") == "battle_context_used"
        }
        resources = {actor["token"]: actor for actor in battle["actors"]}
        available = {}
        for raw in reversed(battle["contexts"]):
            value = Context.model_validate(raw)
            draft = value.declaration
            if (
                draft.play not in DECLARED_PLAYS.values()
                or value.id in used
                or draft.play in available
            ):
                continue
            if value.state == "confirmed" and not (value.reach and value.opening):
                continue
            if value.state not in ("proposed", "confirmed"):
                continue
            actor = resources.get(draft.actor.token)
            target = resources.get(draft.target.token)
            if not actor or not target or not actor["owned"]:
                continue
            if (
                actor["sha256"] != draft.actor_sha256
                or target["sha256"] != draft.target_sha256
                or resolve(state, draft.actor, bound).position_sha256
                != value.actor_position
                or resolve(state, draft.target, bound).position_sha256
                != value.target_position
            ):
                continue
            available[draft.play] = {
                "id": value.id,
                "state": value.state,
                "target": target["name"],
                "account": draft.account,
                "evidence": value.evidence,
                "damaged_weapon": any(
                    asset["id"] == draft.attacking_asset and asset["damaged"]
                    for asset in actor["core_assets"]
                ),
            }
            if draft.play == ASSAULT and value.state == "confirmed":
                source = self.combat.context(viewer, value.id)
                if source["revision"] != state.revision:
                    raise BattlefieldChanged("The drill changed while loading. Please retry.")
                if rider := source.get("learned_rider"):
                    available[draft.play]["learned_rider"] = rider["text"]
        return available

    def exposure_options(self, state, bound, battle):
        origin = next((row for row in battle["actors"] if row["owned"]), None)
        if not origin:
            return []
        acting = ActorRef.model_validate(origin["ref"])
        eligible = []
        for row in battle["actors"]:
            target = ActorRef.model_validate(row["ref"])
            actual = resolve(state, target, bound)
            if (
                target.kind != "pilot"
                or actual.controller != self.roles["opponent"].user_id
                or not actual.piloting
            ):
                continue
            try:
                battle_rules.core_available(state, target, acting, bound)
            except ValueError:
                eligible.append({"id": row["token"], "label": row["name"]})
        return eligible

    def last_child(self, connection, root):
        table = tables.m2["m2_actions"]
        return connection.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.parent_id == root,
            )
            .order_by(sa.literal_column("rowid").desc())
            .limit(1)
        )

    def order_actions(self, viewer, action, choices):
        ready = []
        for choice in choices:
            play = ORDER_CHOICES.get(choice["kind"])
            if not play or choice["role"] != "pilot":
                continue
            if play == DISOBEY_ORDERS:
                try:
                    self.game.decision(viewer, choice["id"])
                    with self.store.engine.connect() as connection:
                        state = load_state(connection, self.store.campaign_id)
                        sheet = state.sheets[str(viewer.user_id)]
                        if any(item.play == play for item in sheet.blocked_plays):
                            continue
                        self.game.valid_order(
                            connection,
                            state,
                            viewer.user_id,
                            self.channel,
                            action["data"]["order_id"],
                        )
                        actor = ActorRef(
                            kind="pilot",
                            entity=str(viewer.user_id),
                            incarnation=sheet.character_id,
                        )
                        require_freedom(state, actor, "refuse")
                except (WorkflowError, ValueError):
                    continue
            ready.append(
                {
                    "id": play,
                    "label": PLAY_LABELS[play],
                    "range": {
                        "kind": "order",
                        "label": "Respond to the direct order."
                        if play == RECEIVE_ORDERS
                        else "Resolve your refusal of this direct order.",
                    },
                    "order": {"text": action["data"]["order_text"], "choice": choice},
                }
            )
        return ready

    def choice_roles(self, viewer, actor_id):
        if self.private:
            role = (
                "handler"
                if viewer.user_id == self.roles["handler"].user_id
                else "pilot"
            )
            return {role: viewer}
        if not self.shared:
            return self.roles
        roles = {"pilot": viewer}
        if str(viewer.user_id) == actor_id:
            roles["handler"] = self.roles["handler"]
        return roles

    def handler_fields(self, viewer, grant):
        detail = HandlerPlayService(self.store).get(viewer, grant)
        return {
            "game_revision": detail["game_revision"],
            "plays": [
                {"id": name, "label": label}
                for name, label, *_ in detail["plays"]
                if name in HANDLER_FORMS
            ],
        }

    def choices(self, identity, audience, actor_id):
        result = []
        for role, viewer in self.choice_roles(audience, actor_id).items():
            for choice in self.game.choices(viewer):
                if choice["action_id"] != identity:
                    continue
                kind = choice["kind"]
                if kind in (PARTAKE, ROUSE_COST, INTERCEPT, "wyvern_replacement"):
                    continue
                option = {
                    "id": choice["id"],
                    "revision": choice["revision"],
                    "kind": kind,
                    "role": role,
                }
                if kind in TAG_DECISIONS:
                    option.update(tag_choice_card(self.game.decision(viewer, choice["id"])))
                elif kind == RISK_CHOICE:
                    option.update(risk_choice_card(self.game.decision(viewer, choice["id"])))
                elif kind in ("engage_maneuvers", "engage_assault_extra"):
                    decision = self.game.decision(viewer, choice["id"])["engage"]
                    option["fields"] = {
                        key: decision[key]
                        for key in (
                            "maneuvers",
                            "minimum",
                            "maximum",
                            "assets",
                            "damage",
                        )
                    }
                    option["fields"]["wyvern_vehicles"] = decision.get(
                        "wyvern_vehicles", []
                    )
                    if decision.get("learned_rider"):
                        option["prompt"] = decision["learned_rider"]
                elif kind in (
                    "actor_sensors",
                    "handler_sensors",
                    "actor_keep",
                    "handler_keep",
                    "order_response",
                    "actor_disobey",
                    "handler_disobey",
                    "follow_disobey",
                    "followthrough_confirm",
                    *FLIRT_CHOICES,
                    *BENEATH_CHOICES,
                ):
                    try:
                        decision = self.game.decision(viewer, choice["id"])
                    except WorkflowError:
                        if kind == "order_response":
                            continue
                        raise
                    if kind == "order_response" and any(
                        item["play"] == DISOBEY_ORDERS
                        for item in (decision["own"] or {}).get("blocked_plays", ())
                    ):
                        decision["am_can_refuse"] = False
                    option["schema"] = printed_fields([
                        asdict(field) for field in choice_fields(decision)
                    ],kind)
                    if kind == "actor_disobey":
                        for field in option["schema"]:
                            if field["key"] == "member":
                                field["options"] = [
                                    (value, decision["labels"].get(value, label))
                                    for value, label in field["options"]
                                ]
                    if kind == "handler_sensors":
                        option["questions"] = [
                            sensor_question_text(question)
                            for question in decision["result"]["questions"]
                        ]
                    if kind == "followthrough_confirm":
                        option["prompt"] = decision["context"]
                    if kind in ("target_flirt", "actor_flirt_answer"):
                        answer_key = (
                            "question" if kind == "target_flirt" else "return_question"
                        )
                        question = decision["result"].get(answer_key)
                        option["prompt"] = (
                            (
                                decision["result"].get("question_text")
                                if kind == "target_flirt"
                                else None
                            )
                            or FLIRT_QUESTION_TEXT.get(question, question)
                            or FLIRT_QUESTION_TEXT["rejection"]
                        )
                        if question in FLIRT_QUESTION_TEXT:
                            option["prompt"] = FLIRT_QUESTION_TEXT[question]
                        if kind == "target_flirt" and decision["result"].get("tier") == "low":
                            option["prompt"] = FLIRT_QUESTION_TEXT["rejection"]
                elif kind in BATTERY_CHOICES:
                    option.update(battery_choice(self.game, viewer, choice["id"], kind))
                elif kind in DEFEAT_CHOICES:
                    option.update(
                        defeat_choice(self.game.decision(viewer, choice["id"]))
                    )
                elif kind in ("escape_play", "beneath_response_play", "beneath_defeat"):
                    option["fields"] = {
                        "sheet_revision": self.game.sheet(viewer)["revision"]
                    }
                elif kind == "beneath_punishment":
                    decision = self.game.decision(viewer, choice["id"])
                    work = PunishmentService(self.store).get(
                        viewer, decision["body"]["work_id"]
                    )
                    if (
                        work["owner_id"] == str(viewer.user_id)
                        and work["kind"] == "punishment"
                        and not work.get("role_case")
                    ):
                        option["fields"] = {
                            "subject": work["callsign"],
                            "revision": work["revision"],
                            "game_revision": work["game_revision"],
                            "options": [
                                (key, KINDS[key][0])
                                for key in BENEATH_PUNISHMENTS
                                if work.get("required_severity")
                                in (None, KINDS[key][1])
                            ],
                        }
                elif kind == "handler_brief":
                    decision = self.game.decision(viewer, choice["id"])
                    grant = decision["body"].get("handler_grant")
                    if grant:
                        option["fields"] = self.handler_fields(viewer, grant)
                    else:
                        option["schema"] = [
                            asdict(field) for field in choice_fields(decision)
                        ]
                elif kind.startswith("battle_"):
                    decision = self.game.decision(viewer, choice["id"])["battle"]
                    option["fields"] = {
                        key: decision[key]
                        for key in ("assets", "options", "maximum")
                        if key in decision
                    }
                    if kind == "battle_handler_play":
                        option["fields"] = self.handler_fields(
                            viewer, decision["grant_id"]
                        )
                    elif kind == "battle_collateral":
                        detail = CollateralService(self.store).get(
                            viewer, decision["work_id"]
                        )
                        option["fields"] = {
                            "revision": detail["revision"],
                            "game_revision": detail["game_revision"],
                        }
                    elif kind == "battle_counter_play":
                        option["fields"]["plays"] = [
                            {"id": KEEP, "label": PLAY_LABELS[KEEP]}
                        ]
                        option["fields"]["sheet_revision"] = self.game.sheet(viewer)[
                            "revision"
                        ]
                result.append(option)
        return result

    def perform(self, viewer, key, command, body):
        self.authorize(viewer)
        if command == "frame-work":
            try:
                return BattlefieldFrameWork(self.game, self.channel).perform(
                    viewer, key, body
                )
            except (KeyError, TypeError, AttributeError) as error:
                raise ValueError(
                    "Use the fields from the current Frame decision."
                ) from error
        if command == "fulfill":
            if (
                body.keys() != {"id", "account"}
                or not isinstance(body["id"], str)
                or not isinstance(body["account"], str)
            ):
                raise ValueError
            with self.store.engine.connect() as connection:
                state = load_state(connection, self.store.campaign_id)
                obligation = next((
                    item for item in state.obligations
                    if item.id == body["id"] and item.kind == FOLLOW_THROUGH
                    and item.owner == viewer.user_id
                ), None)
                if obligation is None or not completed_flirt(self.game, connection, obligation.action):
                    raise WorkflowError("A completed original Flirt is required.")
            return self.game.fulfill(
                viewer, key, self.channel, body["id"], body["account"]
            )
        if command == FLIRT:
            return self.start_flirt(viewer, key, body)
        if command == BENEATH:
            return self.start_beneath(viewer, key, body)
        if command == BATTERY:
            if (
                body.keys() != {"target", "account", "sheet_revision", "confirmed"}
                or body["confirmed"] is not True
                or type(body["sheet_revision"]) is not int
            ):
                raise ValueError
            return self.game.begin(
                viewer,
                key,
                self.channel,
                body["sheet_revision"],
                PlayInput(
                    play=BATTERY,
                    context=body["account"],
                    trigger_confirmed=True,
                    target_actor=ActorRef.model_validate(body["target"]),
                    heat=0,
                ),
            )
        if command == "issue-order":
            if self.shared:
                raise WorkflowError(
                    "Synthetic orders are only available in the one-pilot drill."
                )
            if body.keys() != {"text"} or not isinstance(body["text"], str):
                raise ValueError
            return self.game.issue_order(
                self.roles["handler"], key, self.channel, viewer.user_id, body["text"]
            )
        if command == DISOBEY_ORDERS:
            return self.start_refusal(viewer, key, body)
        if command == "move" and body.keys() == {
            "actor",
            "revision",
            "frame",
            "destination",
            "account",
        }:
            if type(body["frame"]) is not bool or not isinstance(body["account"], str):
                raise ValueError
            destination = body["destination"]
            if (
                not isinstance(destination, list)
                or len(destination) != 2
                or any(type(v) is not int for v in destination)
            ):
                raise ValueError
            return self.movement.move(
                viewer,
                key,
                body["revision"],
                self.channel,
                ActorRef.model_validate(body["actor"]),
                tuple(destination),
                frame=body["frame"],
                account=body["account"],
            )
        if command == ENGAGE["play_id"] and body.keys() == {
            "target",
            "account",
            "sheet_revision",
            "confirmed",
        }:
            if body["confirmed"] is not True or type(body["sheet_revision"]) is not int:
                raise ValueError
            target = ActorRef.model_validate(body["target"])
            preview = self.combat.preview(viewer, self.channel)
            if not any(
                not actor["owned"] and ActorRef.model_validate(actor["ref"]) == target
                for actor in preview["actors"]
            ):
                raise WorkflowError(
                    "Select an opposing actor shown on the battlefield."
                )
            prepared = PlayInput(
                play=ENGAGE["play_id"],
                target_actor=target,
                context=body["account"],
                trigger_confirmed=True,
                heat=0,
            )
            return self.game.begin(
                viewer, key, self.channel, body["sheet_revision"], prepared
            )
        if command == "choice" and body.keys() == {"role", "id", "revision", "answer"}:
            return self.respond(viewer, key, body)
        if command in (SENSORS, KEEP) and body.keys() == {
            "account",
            "sheet_revision",
            "confirmed",
        }:
            if body["confirmed"] is not True or type(body["sheet_revision"]) is not int:
                raise ValueError
            return self.game.begin(
                viewer,
                key,
                self.channel,
                body["sheet_revision"],
                PlayInput(
                    play=command,
                    context=body["account"],
                    trigger_confirmed=True,
                    heat=0,
                    piloting=command == SENSORS,
                ),
            )
        if command == "core-expose":
            if self.shared:
                raise WorkflowError("A signed-in player controls their own pilot.")
            if body.keys() != {"revision", "target"}:
                raise ValueError
            opponent = self.roles["opponent"]
            placement = PhysicalService(self.store).preview(opponent)
            ref = ActorRef.model_validate(placement["actor"])
            if ref.token != body["target"]:
                raise WorkflowError(
                    "Only the drill opponent can expose its own Core here."
                )
            return self.combat.expose(
                opponent,
                key,
                body["revision"],
                ref,
                "The drill opponent willingly exposes its own Frame Core.",
                willing=True,
            )
        prefix, _, stage = command.partition("-")
        if prefix in DECLARED_PLAYS:
            play = DECLARED_PLAYS[prefix]
            if stage == "declare":
                return self.declare_attack(viewer, key, play, body)
            if stage in ("review", "roll"):
                return self.advance_attack(viewer, key, play, stage, body)
        raise ValueError

    def start_flirt(self, viewer, key, body):
        if not self.shared:
            raise WorkflowError(
                "Flirt requires a second signed-in pilot in the shared drill."
            )
        if body.keys() != {"target", "account", "sheet_revision", "confirmed"} or (
            type(body["target"]) is not int
            or type(body["sheet_revision"]) is not int
            or body["confirmed"] is not True
        ):
            raise ValueError
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            scene = self.game.scene(connection, self.channel)
            targets = self.pilot_targets(connection, viewer, state, scene)
        if not any(row["owner"] == body["target"] for row in targets):
            raise WorkflowError("Choose another eligible pilot from the same scene.")
        return self.game.begin(
            viewer,
            key,
            self.channel,
            body["sheet_revision"],
            PlayInput(
                play=FLIRT,
                context=body["account"],
                trigger_confirmed=True,
                target=body["target"],
                heat=0,
            ),
        )

    def start_beneath(self, viewer, key, body):
        if not self.shared:
            raise WorkflowError("This Play requires a second signed-in pilot.")
        if body.keys() != {
            "target",
            "account",
            "sheet_revision",
            "confirmed",
            "heat",
        } or (
            type(body["target"]) is not int
            or type(body["sheet_revision"]) is not int
            or type(body["heat"]) is not int
            or body["confirmed"] is not True
        ):
            raise ValueError
        with self.store.engine.connect() as connection:
            state = load_state(connection, self.store.campaign_id)
            scene = self.game.scene(connection, self.channel)
            if not any(
                target["owner"] == body["target"]
                for target in self.pilot_targets(connection, viewer, state, scene)
            ):
                raise WorkflowError("Choose another eligible pilot from this scene.")
            sheet = state.sheets[str(viewer.user_id)]
            ref = ActorRef(
                kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id
            )
            piloting = bool(
                resolve(
                    state, ref, profiles(connection, self.store.campaign_id)
                ).piloting
            )
        return self.game.begin(
            viewer,
            key,
            self.channel,
            body["sheet_revision"],
            PlayInput(
                play=BENEATH,
                target=body["target"],
                piloting=piloting,
                heat=body["heat"],
                context=body["account"],
                trigger_confirmed=True,
            ),
        )

    def start_refusal(self, viewer, key, body):
        if body.keys() != {
            "choice",
            "revision",
            "sheet_revision",
            "account",
            "heat",
            "witnessed",
            "confirmed",
        } or (
            not isinstance(body["choice"], str)
            or body["confirmed"] is not True
            or type(body["revision"]) is not int
            or type(body["sheet_revision"]) is not int
            or type(body["heat"]) is not int
            or type(body["witnessed"]) is not bool
        ):
            raise ValueError
        table = tables.m2["m2_choices"]
        with self.store.engine.connect() as connection:
            choice = (
                connection.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == body["choice"],
                        table.c.actor_id == str(viewer.user_id),
                        table.c.kind == "order_disobey",
                    )
                )
                .mappings()
                .first()
            )
            if choice is None or not (
                choice["revision"] == body["revision"]
                or choice["state"] == "completed_by_child"
                and choice["revision"] == body["revision"] + 1
            ):
                raise WorkflowError("Reopen your applicable order before refusing it.")
            source = self.game.action(connection, choice["action_id"])
            if (
                source["actor_id"] != str(viewer.user_id)
                or source["channel_id"] != str(self.channel)
                or source["data"]["play"] != RECEIVE_ORDERS
            ):
                raise WorkflowError(
                    "Use your own direct order in this Battlefield scene."
                )
        return self.game.begin(
            viewer,
            key,
            self.channel,
            body["sheet_revision"],
            PlayInput(
                play=DISOBEY_ORDERS,
                context=body["account"],
                trigger_confirmed=True,
                heat=body["heat"],
                witnessed=body["witnessed"],
                parent=source["id"],
                order_id=source["data"]["order_id"],
            ),
        )

    def declare_attack(self, viewer, key, play, body):
        expected = {
            "revision",
            "target",
            "attacking_asset",
            "account",
        }
        if play == ASSAULT:
            expected.add("target_asset")
        if body.keys() != expected or type(body["revision"]) is not int:
            raise ValueError
        preview = self.combat.preview(viewer, self.channel)
        actor = next((row for row in preview["actors"] if row["owned"]), None)
        target = next(
            (
                row
                for row in preview["actors"]
                if row["token"] == body["target"] and not row["owned"]
            ),
            None,
        )
        if not actor or not target:
            raise WorkflowError(
                "Select an eligible opposing actor from the Battlefield."
            )
        # Keep the resource proof from the original request available to exact retries.
        with self.store.engine.connect() as connection:
            history = tables.m2["m2_state_history"]
            raw = connection.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.revision == body["revision"],
                )
            )
            if raw is None:
                raise WorkflowError("Fetch the actual battlefield declaration again.")
            state = GameState.model_validate_json(raw)
            bound = profiles(connection, self.store.campaign_id)
            origin = ActorRef.model_validate(actor["ref"])
            victim = ActorRef.model_validate(target["ref"])
            proof = Declaration(
                play=play,
                actor=origin,
                target=victim,
                attacking_asset=body["attacking_asset"],
                target_asset=body.get("target_asset"),
                actor_sha256=battle_rules.resource_sha(state, origin, bound),
                target_sha256=battle_rules.resource_sha(state, victim, bound),
                account=body["account"],
            )
        return self.combat.propose(viewer, key, body["revision"], self.channel, proof)

    def advance_attack(self, viewer, key, play, stage, body):
        expected = (
            {"id", "revision", "opening", "reach", "evidence"}
            if stage == "review"
            else {"id", "sheet_revision"}
        )
        if play == CORE:
            expected.add("capability" if stage == "review" else "heat")
        optional = {"heat"} if play == ASSAULT and stage == "roll" else set()
        if (
            not expected <= body.keys() <= expected | optional
            or not isinstance(body["id"], str)
            or "heat" in body and (type(body["heat"]) is not int or body["heat"] < 0)
        ):
            raise ValueError
        saved = self.combat.context(viewer, body["id"])
        context = Context.model_validate(saved["context"])
        declaration = context.declaration
        authority = (
            context.adjudicator if self.private and stage == "review" else context.owner
        )
        if (
            saved["channel"] != self.channel
            or authority != viewer.user_id
            or declaration.play != play
        ):
            raise WorkflowError("Use your own Battlefield declaration.")
        if stage == "review":
            if (
                type(body["opening"]) is not bool
                or type(body["reach"]) is not bool
                or not isinstance(body["evidence"], str)
                or not body["evidence"].strip()
                or play == CORE
                and type(body["capability"]) is not bool
            ):
                raise ValueError
            return self.combat.confirm(
                viewer if self.private else self.roles["handler"],
                key,
                body["revision"],
                context.id,
                opening=body["opening"],
                reach=body["reach"],
                evidence=body["evidence"],
                outside_permission=False,
                indirect=False,
                core_capability_confirmed=body.get("capability", False),
            )
        return self.game.begin(
            viewer,
            key,
            self.channel,
            body["sheet_revision"],
            PlayInput(
                play=play,
                target_actor=declaration.target,
                attacking_asset=declaration.attacking_asset,
                target_asset=declaration.target_asset,
                battle_context=context.id,
                context=declaration.account,
                trigger_confirmed=True,
                heat=body.get("heat", 0),
                piloting=True,
            ),
        )

    def respond(self, viewer, key, body):
        role, identity, revision = body["role"], body["id"], body["revision"]
        if (
            role not in self.roles
            or not isinstance(identity, str)
            or type(revision) is not int
        ):
            raise ValueError
        table = tables.m2["m2_choices"]
        with self.store.engine.connect() as connection:
            row = connection.execute(
                sa.select(
                    table.c.action_id, table.c.kind, table.c.actor_id, table.c.body_json
                ).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                )
            ).first()
            if row is None:
                raise WorkflowError("This choice belongs to another participant.")
            action = self.game.action(connection, row.action_id)
            source = (
                self.game.action(connection, action["parent_id"])
                if action["parent_id"]
                else action
            )
            principal = self.choice_roles(viewer, source["actor_id"]).get(role)
            if principal is None or row.actor_id != str(principal.user_id):
                raise WorkflowError("This choice belongs to another participant.")
            if (
                (
                    viewer.user_id not in source["data"]["participants"]
                    if self.shared
                    else source["actor_id"] != str(viewer.user_id)
                )
                or str(action["channel_id"]) != str(self.channel)
                or action["data"]["play"] not in PLAY_LABELS
                or action["parent_id"]
                and not action["data"].get("wyvern_replacement")
                and (source["data"]["play"], action["data"]["play"], action["actor_id"])
                not in (
                    (
                        CORE,
                        KEEP,
                        row.actor_id
                        if self.private
                        else str(self.roles["opponent"].user_id),
                    ),
                    (RECEIVE_ORDERS, DISOBEY_ORDERS, str(viewer.user_id)),
                    (
                        FLIRT,
                        KEEP,
                        str(source["data"].get("prepared", {}).get("target")),
                    ),
                    (BENEATH, KEEP, source["actor_id"]),
                    (BENEATH, DEFEAT, source["actor_id"]),
                    (ASSAULT, DEFEAT, row.actor_id),
                    (CORE, DEFEAT, row.actor_id),
                    (
                        BENEATH,
                        KEEP,
                        str(source["data"].get("prepared", {}).get("target")),
                    ),
                )
            ):
                raise WorkflowError("This choice belongs to another Play.")
        if row.kind == "battle_defeat":
            answer = body["answer"]
            if (
                not self.shared or principal != viewer
                or not isinstance(answer, dict) or answer.keys() != {"account"}
                or not isinstance(answer["account"], str) or not answer["account"].strip()
            ):
                raise WorkflowError("Begin Defeat from your actual assigned Battlefield consequence.")
            return begin_defeat_work(
                self.game, viewer, key, json.loads(row.body_json)["work_id"],
                self.channel, answer["account"],
            )
        if row.kind == "beneath_defeat":
            answer = body["answer"]
            if (
                not self.shared
                or principal != viewer
                or action["data"]["play"] != BENEATH
                or not isinstance(answer, dict)
                or answer.keys() != {"account", "sheet_revision"}
                or not isinstance(answer["account"], str)
                or type(answer["sheet_revision"]) is not int
            ):
                raise WorkflowError(
                    "Begin Defeat from its assigned last-Asset consequence."
                )
            return self.game.begin(
                principal,
                key,
                self.channel,
                answer["sheet_revision"],
                PlayInput(
                    play=DEFEAT,
                    context=answer["account"],
                    trigger_confirmed=True,
                    piloting=action["data"]["prepared"]["piloting"] is True,
                    heat=0,
                    parent=row.action_id,
                ),
            )
        if row.kind in ("battle_counter_play", "escape_play", "beneath_response_play"):
            answer = body["answer"]
            if (
                not isinstance(answer, dict)
                or answer.keys() != {"play", "account", "sheet_revision"}
                or answer["play"] != KEEP
                or (
                    principal != viewer
                    if self.shared
                    else principal != self.roles["opponent"]
                )
                or (
                    row.kind == "escape_play"
                    and (not self.shared or source["data"]["play"] != FLIRT)
                )
                or (
                    row.kind == "beneath_response_play"
                    and (not self.shared or source["data"]["play"] != BENEATH)
                )
            ):
                raise WorkflowError(
                    "Choose a Play from the drill opponent's actual counter."
                )
            return self.game.begin(
                principal,
                key,
                self.channel,
                answer["sheet_revision"],
                PlayInput(
                    play=KEEP,
                    context=answer["account"],
                    trigger_confirmed=True,
                    heat=0,
                    parent=row.action_id,
                ),
            )
        if row.kind == "beneath_punishment":
            answer = body["answer"]
            if (
                not isinstance(answer, dict)
                or answer.keys() != {"kind", "tag", "revision", "game_revision"}
                or answer["kind"] not in BENEATH_PUNISHMENTS
            ):
                raise WorkflowError(
                    "Choose a supported Punishment for this assigned work."
                )
            return PunishmentService(self.store).apply(
                principal,
                key,
                json.loads(row.body_json)["work_id"],
                answer["revision"],
                answer["game_revision"],
                PunishmentDetails(kind=answer["kind"], tag=answer["tag"]),
            )
        grant = (
            json.loads(row.body_json).get("handler_grant")
            if row.kind == "handler_brief"
            else None
        )
        if row.kind == "battle_handler_play" or grant:
            answer = body["answer"]
            if (
                not isinstance(answer, dict)
                or not {"play", "account", "game_revision"} <= answer.keys()
                or answer.keys()
                - {"play", "account", "game_revision", "detail", "stakes"}
                or not isinstance(answer["play"], str)
                or answer["play"] not in HANDLER_FORMS
            ):
                raise WorkflowError(
                    "Choose an available effect from the current Handler Play."
                )
            with self.store.engine.connect() as connection:
                request = connection.execute(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == identity,
                    )
                ).scalar_one()
            return HandlerPlayService(self.store).submit(
                principal,
                key,
                grant or json.loads(request)["grant_id"],
                answer["game_revision"],
                answer["play"],
                Effect(
                    kind=answer["play"],
                    account=answer["account"],
                    detail=answer.get("detail", ""),
                    stakes=answer.get("stakes", ""),
                ),
            )
        if row.kind == "battle_collateral":
            answer = body["answer"]
            if not isinstance(answer, dict) or answer.keys() != {
                "revision",
                "game_revision",
                "ordinary",
                "account",
                "reach",
            }:
                raise ValueError
            return CollateralService(self.store).submit(
                principal,
                key,
                json.loads(row.body_json)["work_id"],
                answer["revision"],
                answer["game_revision"],
                CollateralSelection(
                    ordinary=(answer["ordinary"],),
                    account=answer["account"],
                    reach=answer["reach"],
                ),
            )
        try:
            answer = ChoiceAnswer.model_validate_json(json.dumps(body["answer"]))
        except ValidationError as error:
            raise WorkflowError("Use the fields from the current choice.") from error
        allowed = (
            row.kind in TAG_DECISIONS | {RISK_CHOICE}
            or principal == viewer
            and row.kind in ("engage_maneuvers", "engage_assault_extra")
            or row.kind
            in ("battle_assault_table", "battle_low_damage", "battle_actor_damage")
            or row.kind
            in (
                "battle_handler",
                "battle_counter",
                "battle_target_damage",
                "actor_sensors",
                "handler_sensors",
                "actor_keep",
                "handler_keep",
                "order_response",
                "actor_disobey",
                "handler_disobey",
                "follow_disobey",
                "followthrough_confirm",
                "handler_brief",
                *FLIRT_CHOICES,
                *BATTERY_CHOICES,
                *BENEATH_CHOICES,
                *DEFEAT_CHOICES,
            )
        )
        if not allowed:
            raise WorkflowError("This response is unavailable in the drill.")
        return self.game.respond(principal, key, identity, revision, answer)
