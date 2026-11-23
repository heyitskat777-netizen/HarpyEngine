"""Activity forms for the current HarpyEngine Off-Duty period."""

import json

from girlframe.discord_adapter.m3_observation import LABELS
from girlframe.engine.m2 import tier
from girlframe.engine.m3_choices import OFF_DUTY
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.engine.m3_observation import all_chosen, complete, scene_roles
from girlframe.engine.m3_observation_state import Details
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.services.m2_state import load_state
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.m3_observation import ObservationService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_play_support import periods
from girlframe.services.onboarding import WorkflowError

from off_duty_review import OffDutyReview
from psyche_controls import PsycheControls
from show_dog_controls import ShowDogControls
from strain_preparation import StrainPreparation


def scene_label(kind):
    if kind in ("prime_mid", "prime_high"):
        return "Prime Investment"
    if kind.startswith("observation:"):
        return LABELS[kind.removeprefix("observation:")]
    return kind.replace("_", " ").capitalize()


class OffDutyFollowups:
    def __init__(self, game):
        self.periods = periods(game)
        self.cycle = CycleService(self.periods)
        self.final_review = OffDutyReview(self.cycle)
        self.strain = StrainPreparation(self.periods)
        self.observation = ObservationService(self.periods)
        self.rewards = RewardService(self.periods)
        self.show_dog = ShowDogControls(game)
        self.psyche = PsycheControls(game)

    def view(self, viewer):
        try:
            current = self.periods.current(viewer)
        except WorkflowError:
            return None
        if not current:
            return None

        with self.periods.store.engine.connect() as connection:
            state = load_state(connection, self.periods.store.campaign_id)
            if any(str(uid) not in state.sheets for uid in state.order):
                return None

        review = self.cycle.review(viewer, current["id"])
        closing = self.final_review.view(viewer, review)
        if current["phase"] != "active":
            if closing and closing["handler"] and current["phase"] == "preparing":
                closing["strain"] = self.strain.view(viewer, review)
            return (
                {
                    "period": review["id"],
                    "revision": review["revision"],
                    "game_revision": review["game_revision"],
                    "closing": closing,
                    "work": [],
                    "invitations": [],
                }
                if closing
                else None
            )
        uid = str(viewer.user_id)
        callsigns = dict(review["participants"])
        own = review["own"]
        ready = bool(
            review["sheet"]
            and own
            and own["roll"]
            and own["roll"]["stage"] == "choices"
        )
        invitations = [
            {
                "owner": str(scene["owner"]),
                "label": scene_label(scene["kind"]),
                "pilot": callsigns.get(str(scene["owner"])),
                "summary": scene["summary"],
                "confirmed": viewer.user_id in scene["acknowledgements"],
                "remaining": len(
                    set(scene["participants"]) - set(scene["acknowledgements"])
                ),
            }
            for scene in review["invitations"]
        ]
        work = list(self.show_dog.cards(viewer, state, current["id"]))
        work.extend(self.psyche.cards(viewer, state, current["id"]))
        for item in review["work"]:
            if item["kind"] in ("observation_choice", "observation_effect"):
                data = self.observation.get(viewer, item["id"])
                if data["owner_id"] == uid and data["state"] == "pending":
                    work.append(
                        observation_card(data)
                        | {"pilot": callsigns.get(data["subject_id"])}
                    )
            elif item["kind"] == "frame_off_duty_reward":
                data = self.rewards.get(viewer, item["id"])
                if (
                    data["owner_id"] == uid
                    and data["state"] == "pending"
                    and data["ready"]
                    and data["frame"] == "JANUS"
                    and data["mode"] == "conditional"
                    and not data.get("issue")
                ):
                    work.append(
                        {
                            "id": data["id"],
                            "revision": data["revision"],
                            "kind": "janus_reward",
                            "label": "JANUS Permission review",
                            "officials": data["officials"],
                        }
                    )
        if not (ready or invitations or work or closing):
            return None

        picker = recovery = reason = None
        with self.periods.store.engine.connect() as connection:
            period = self.periods._get(connection, current["id"])
            state = load_state(connection, self.periods.store.campaign_id)
            if (period.revision, state.revision) != (
                review["revision"],
                review["game_revision"],
            ):
                return None  # The next refresh will project the committed choices together.
            if review["rewards_need_refresh"]:
                reason = "Refresh the Frame reward reviews before continuing."
            if ready and not own["recovered"] and not reason:
                progress = period.progress[uid]
                if not progress.scene and not progress.scene_declined:
                    picker = scene_picker(viewer.user_id, period, state, review)
                    if picker is None:
                        reason = (
                            "Waiting for the assigned Observation consequence choices."
                        )
                elif progress.scene and set(progress.scene.participants) != set(
                    progress.scene.acknowledgements
                ):
                    reason = "Waiting for participants to confirm their own attendance."
                elif progress.observation and not complete(period, viewer.user_id):
                    reason = (
                        "Resolve the saved Observation consequences before recovery."
                    )
                elif any(
                    item["subject_id"] == uid
                    and item["kind"]
                    not in ("off_duty_handler_scene", "off_duty_status_review")
                    for item in self.periods._pending(connection, period.id)
                ):
                    reason = "Finish the remaining required work before recovery."
                elif any(
                    item.owner == viewer.user_id
                    and item.state == "pending"
                    and item.kind
                    in ("punishment", "void_observation", "defeat", "helpless")
                    and item.details.get("after_period") != period.id
                    for item in state.obligations
                ):
                    reason = (
                        "Resolve the compulsory sheet consequences before recovery."
                    )
                else:
                    recovery = recovery_fields(review)
            if self.periods.game.pending_actions(connection):
                reason = "Finish the pending Play before continuing Off-Duty."
        return {
            "period": review["id"],
            "revision": review["revision"],
            "game_revision": review["game_revision"],
            "scene": picker,
            "invitations": invitations,
            "work": work,
            "recovery": recovery,
            "recovered": bool(own and own["recovered"]),
            "declined": bool(own and own["scene_declined"]),
            "reason": reason,
            "refresh_rewards": review["rewards_need_refresh"],
            "closing": closing,
        }

    def perform(self, viewer, key, data):
        if data.keys() != {"period", "revision", "game_revision", "action", "answer"}:
            raise ValueError
        period, revision, game_revision = (
            data[k] for k in ("period", "revision", "game_revision")
        )
        action, answer = data["action"], data["answer"]
        if (
            not isinstance(period, str)
            or type(revision) is not int
            or type(game_revision) is not int
            or not isinstance(answer, dict)
        ):
            raise ValueError
        cycle_args = (viewer, key, period, revision, game_revision)
        if action == "show_dog":
            return self.show_dog.perform(viewer, key, period, game_revision, answer)
        if action == "disposable_psyche":
            return self.psyche.perform(viewer, key, period, game_revision, answer)
        if isinstance(action, str) and action.startswith("strain_"):
            return self.strain.perform(cycle_args, action, answer)
        if action in (
            "activate_period",
            "acknowledge_handler_scene",
            "review_status",
            "set_handler_scene",
            "finish_period",
        ):
            return self.final_review.perform(cycle_args, action, answer)
        if action == "choose_scene" and answer.keys() == {
            "kind",
            "participants",
            "summary",
            "investor",
        }:
            from girlframe.engine.m3_actor_state import ActorRef

            kind, people, summary = (
                answer[k] for k in ("kind", "participants", "summary")
            )
            if (
                (kind is not None and not isinstance(kind, str))
                or not isinstance(people, list)
                or any(
                    not isinstance(uid, str) or not uid.isdecimal() for uid in people
                )
                or not isinstance(summary, str)
                or len(summary) > 1200
            ):
                raise ValueError
            investor = (
                ActorRef.model_validate(answer["investor"])
                if answer["investor"] is not None
                else None
            )
            return self.cycle.scene(
                *cycle_args,
                kind,
                (viewer.user_id, *map(int, people)) if kind else (),
                summary,
                investor=investor,
            )
        if action == "confirm_scene" and answer.keys() == {"owner"}:
            if not isinstance(answer["owner"], str) or not answer["owner"].isdecimal():
                raise ValueError
            return self.cycle.acknowledge(*cycle_args, int(answer["owner"]))
        if action == "recover":
            return self.cycle.recover(
                *cycle_args, RecoveryChoice.model_validate_json(json.dumps(answer))
            )
        if action == "refresh_rewards" and not answer:
            return self.rewards.refresh(*cycle_args)
        if action == "choose_observation" and answer.keys() == {"subject", "choices"}:
            if (
                not isinstance(answer["subject"], str)
                or not answer["subject"].isdecimal()
                or not isinstance(answer["choices"], list)
                or any(not isinstance(value, str) for value in answer["choices"])
            ):
                raise ValueError
            return self.observation.select(
                *cycle_args, int(answer["subject"]), tuple(answer["choices"])
            )
        if (
            not isinstance(answer.get("id"), str)
            or type(answer.get("work_revision")) is not int
        ):
            raise ValueError
        work_args = (viewer, key, answer["id"], answer["work_revision"])
        if action == "apply_observation" and answer.keys() == {
            "id",
            "work_revision",
            "details",
        }:
            return self.observation.apply(
                *work_args,
                revision,
                game_revision,
                Details.model_validate(answer["details"]),
            )
        if (
            action == "answer_observation"
            and answer.keys() == {"id", "work_revision", "accepted"}
            and type(answer["accepted"]) is bool
        ):
            return self.observation.answer_npc(
                *work_args, revision, game_revision, answer["accepted"]
            )
        if action == "review_janus" and answer.keys() == {
            "id",
            "work_revision",
            "claim",
        }:
            return self.rewards.apply(
                *work_args, game_revision, Claim.model_validate(answer["claim"])
            )
        raise ValueError


def observation_card(data):
    keys = (
        "id",
        "revision",
        "kind",
        "subject_id",
        "count",
        "assets",
        "npcs",
        "npc_name",
        "proposal_account",
        "response_required",
    )
    card = {key: data[key] for key in keys if key in data}
    if data["kind"] == "observation_choice":
        return card | {
            "label": "Your Observation consequences",
            "options": [(x, LABELS[x]) for x in data["options"]],
        }
    kind = data["consequence"]
    if kind == "reprogram":
        card["identities"] = [
            (x["id"], x["name"]) for x in data["identities"] if not x["protected"]
        ]
        if "Malfunctioning" not in data["starting_identities"]:
            paired = {x["slot"] for x in data["identities"] if x["paired"]}
            card["slots"] = [
                (x, x)
                for i, x in enumerate(data["starting_identities"])
                if i not in paired
            ]
    return card | {"consequence": kind, "label": LABELS[kind]}


def scene_picker(actor, period, state, review):
    progress = period.progress[str(actor)]
    level = tier(progress.roll.total)
    participants = [
        (uid, label) for uid, label in review["participants"] if uid != str(actor)
    ]
    options = list(OFF_DUTY[level])
    required = {}
    prime = []
    if progress.observation:
        if not all_chosen(period, actor):
            return None
        options = list(OFF_DUTY["low"])
        for outcome in progress.observation.outcomes:
            kind = "observation:" + outcome.kind
            try:
                roles = scene_roles(period, state, actor, kind)
            except ValueError:
                continue  # This appearance still needs its actual NPC assignment.
            options.append(kind)
            required[kind] = sorted(str(uid) for uid in roles if uid != actor)
        participants.extend(review["observation_participants"])
    elif level != "low":
        for item in review["prime_investors"]:
            prime.append(
                {
                    "id": item["id"],
                    "actor": item["actor"],
                    "controller": str(item["controller"]),
                }
            )
    if level != "mid" or progress.observation:
        participants.append((str(period.handler), "Handler"))
    return {
        "options": [(kind, scene_label(kind)) for kind in options],
        "participants": list(dict(participants).items()),
        "required": required,
        "can_decline": level == "mid" and not progress.observation,
        "prime": prime,
        "prime_kind": "prime_high" if level == "high" else "prime_mid",
    }


def recovery_fields(review):
    sheet = review["sheet"]
    identities = (
        sheet["identities"] + sheet["additional_identities"] + sheet["marked_maxims"]
    )
    return {
        "tags": [(x["id"], x["label"]) for x in sheet["tags"]],
        "replace": [
            (x["id"], x["name"]) for x in sheet["identities"] if not x["protected"]
        ],
        "unmark": [
            (x["id"], x["name"])
            for x in identities
            if x["marked"] and x["id"] not in sheet["sedation_locked"]
        ],
        "repair_limit": review["repair_limit"],
        "damaged": {
            family: [
                (x["id"], x["name"])
                for x in sheet["assets"]
                if x["family"] == family and x["damaged"]
            ]
            for family in ("girl", "frame")
        },
        "modular": [
            (x["id"], x["name"])
            for x in sheet["assets"]
            if x["id"] in review["modular"]
        ],
    }
