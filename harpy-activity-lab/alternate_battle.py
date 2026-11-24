"""The original approved alternate combatant's declaration, judge review and roll."""

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Context
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_mother_hazard import PLAY as HAZARD
from girlframe.services import m3_engage
from girlframe.services.director_observation import _digest
from girlframe.services.director_play_options import initiative_play_options
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_erratic_gorgon import ErraticService
from girlframe.services.onboarding import WorkflowError


class AlternateBattle:
    def __init__(self, session):
        self.session = session
        self.store, self.game = session.store, session.game
        self.battle = BattleService(session.store)
        self.erratic = ErraticService(self.game)

    def source(self, c, viewer, scene, identity):
        row = self.session.observer._scene(c, scene, viewer)
        proposal = self.session.reactions.alternate_battle_ids(c, scene).get(identity)
        if proposal is None:
            raise WorkflowError("Use this actor's saved battle declaration in its original scene.")
        return row, proposal

    def view(self, viewer, scene):
        with self.store.engine.connect() as c:
            scoped_scene = self.session.observer._scene(c, scene, viewer)
            original = load_state(c, self.store.campaign_id)
            battles = self.session.reactions.alternate_battle_ids(c, scene)
            actions = self.session.reactions.alternate_action_ids(c, scene)
            advances = []
            for action_id in actions:
                action = self.game.action(c, action_id)
                if action["actor_id"] != str(viewer.user_id) or action["state"] not in (
                    "acquiring",
                    "ready_to_roll",
                ):
                    continue
                lock = self.game.lock(c, int(action["channel_id"]))
                advances.append(
                    dict(
                        id=action_id,
                        play=action["data"]["play"],
                        ready=bool(lock and lock["state"] == "held"),
                        diceless=bool(action["data"].get("gorgon_play"))
                        or action["data"]["play"] in ("check_sensors", "harpy_followthrough"),
                    )
                )
        tasks = []
        for task in self.battle.tasks(viewer) if battles else ():
            if task["id"] not in battles:
                continue
            saved = self.battle.context(viewer, task["id"])
            value = Context.model_validate(saved["context"])
            target = value.declaration.target
            dormant = (
                target.kind == "gorgon"
                and original.world is not None
                and any(
                    x.id == target.entity and x.gorgon_class == "dormant"
                    for x in original.world.gorgons
                )
            )
            commit = (
                value.state == "confirmed"
                and value.opening
                and value.reach
                and value.owner == viewer.user_id
            )
            heat = harpy(original, value.declaration.actor).heat if commit else 0
            tasks.append(
                dict(
                    id=value.id,
                    revision=saved["revision"],
                    state=value.state,
                    play=value.declaration.play,
                    account=value.declaration.account,
                    review=value.state == "proposed" and value.adjudicator == viewer.user_id,
                    commit=commit,
                    heat=[heat] if heat >= 5 else list(range(heat + 1)),
                    dormant=dormant,
                )
            )
        try:
            flight = self.erratic.flight_view(viewer, int(scoped_scene["channel_id"]))
            pursuits = [item | {"revision": flight["revision"]} for item in flight["pursuits"]]
        except (ValueError, WorkflowError):
            pursuits = []
        return dict(battles=tasks, advances=advances, pursuits=pursuits)

    def catch_erratic(self, viewer, key, scene, data):
        with self.store.engine.connect() as c:
            row = self.session.observer._scene(c, scene, viewer)
        channel = int(row["channel_id"])

        def scoped(c):
            current = self.session.observer._scene(c, scene, viewer)
            if int(current["channel_id"]) != channel:
                raise WorkflowError("Use the original pursuit scene.")

        with self.store.source_guard(scoped):
            return self.erratic.catch(
                viewer, key, channel, data["revision"], data["event"], data["action"]
            )

    def review(self, viewer, key, scene, data):
        def scoped(c):
            self.source(c, viewer, scene, data["id"])

        with self.store.source_guard(scoped):
            return self.battle.confirm(
                viewer,
                key,
                data["revision"],
                data["id"],
                opening=data["opening"],
                reach=data["reach"],
                outside_permission=data["outside_permission"],
                indirect=data["indirect"],
                evidence=data["evidence"],
                core_capability_confirmed=data.get("core_capability_confirmed", False),
                dormant_awakened=data.get("dormant_awakened", False),
                dormant_close=data.get("dormant_close", False),
            )

    def commit(self, viewer, scene, identity, heat):
        reactions = self.session.reactions
        with self.store.engine.connect() as c:
            _, proposal = self.source(c, viewer, scene, identity)
            record, packet = reactions._owned(c, viewer, scene, proposal, fresh=False)
            binding = reactions._native_play_preview(c, scene, proposal, record, packet)[
                "native_play"
            ]["alternate"]
        saved = self.battle.context(viewer, identity)
        value = Context.model_validate(saved["context"])
        move = value.declaration
        if (
            value.owner != viewer.user_id
            or value.state != "confirmed"
            or not (value.opening and value.reach)
        ):
            raise WorkflowError("The actual opening and reach need the original judge's approval.")
        key = "director-alternate-battle:" + _digest((scene, identity))

        def scoped(c):
            row, native_proposal = self.source(c, viewer, scene, identity)
            if native_proposal != proposal:
                raise WorkflowError("Recover this original battle declaration.")
            reactions._owned(c, viewer, scene, proposal, fresh=False)
            observation = self.session.observer._state(c, scene)
            if observation.policy.mode != "shadow" or not self.session.observer._consented(
                c, row, observation
            ):
                raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")
            role = reactions.initiative._alternate_roles(c, row).get(move.actor)
            if (
                role is None
                or reactions.initiative._delegated(c, row, role) != packet["activity_alternate"]
            ):
                raise WorkflowError(
                    "INITIATIVE_CONTROL_OWNER: recover the original delegated role."
                )
            if binding["turn"] is not None and not reactions.alternate_battle_receipt(
                c, scene, identity
            ):
                if not any(
                    play["alternate"]["turn"] == binding["turn"]
                    for play in initiative_play_options(
                        self.session.context, c, scene, move.actor, alternate=True
                    )
                ):
                    raise WorkflowError("The original actor's turn has ended.")

        with self.store.source_guard(scoped):
            return ActorPlayService(self.game).begin(
                viewer,
                key,
                binding["channel"],
                move.actor,
                binding["actor_sha256"],
                ActorRef.model_validate(binding["adjudicator"]) if binding["adjudicator"] else None,
                binding["cast_revision"],
                PlayInput(
                    play=move.play,
                    context=move.account,
                    trigger_confirmed=True,
                    heat=heat,
                    piloting=binding["piloting"],
                    target_actor=move.target,
                    attacking_asset=move.attacking_asset,
                    target_asset=move.target_asset,
                    battle_context=identity,
                ),
            )

    def advance(self, viewer, key, scene, action):
        def scoped(c):
            self.session.observer._scene(c, scene, viewer)
            if action not in self.session.reactions.alternate_action_ids(c, scene) or (
                self.game.action(c, action)["actor_id"] != str(viewer.user_id)
            ):
                raise WorkflowError("Only the owner advances their actual alternate Play.")

        with self.store.source_guard(scoped):
            return self.game.roll(viewer, key, action)

    def response_view(self, viewer, decision):
        body = decision["body"]
        ref = ActorRef.model_validate(body["actor"])
        attacker = ActorRef.model_validate(body["attacker"])
        with self.store.engine.connect() as c:
            parent = self.game.action(c, decision["parent"])
            source = parent["data"]["gorgon_play"]
            state = load_state(c, self.store.campaign_id)
            actor = resolve(state, ref, profiles(c, self.store.campaign_id))
            if (
                actor.heat is None
                or actor.controller != viewer.user_id
                or ref.kind
                not in (
                    "pilot",
                    "external_pilot",
                )
            ):
                return None
            plays = []
            for play, label in (
                ("keep_your_head", "Keep Your Head"),
                ("engage", "Engage the Enemy"),
            ):
                if (
                    source.get("frame_intervention")
                    and play != "engage"
                    or source["kind"] == HAZARD
                    and play != "keep_your_head"
                ):
                    continue
                try:
                    ActorPlayService(self.game)._eligible_play(
                        state, ref, rejection=False, play=play
                    )
                    if play == "engage":
                        scene = self.game.scene(c, int(decision["channel"]))
                        m3_engage.prepare(
                            self.game,
                            c,
                            viewer,
                            state,
                            scene,
                            PlayInput(
                                play=play,
                                context="Test native response availability.",
                                trigger_confirmed=True,
                                heat=0,
                                target_actor=attacker,
                                piloting=bool(actor.piloting),
                            ),
                            actor_ref=ref,
                        )
                except (ValueError, WorkflowError):
                    continue
                plays.append((play, label))
        return (
            dict(
                id=decision["id"],
                revision=decision["revision"],
                kind=decision["kind"],
                title="Answer the Gorgon",
                response=True,
                fields=[],
                plays=plays,
                heat=[actor.heat] if actor.heat >= 5 else list(range(actor.heat + 1)),
            )
            if plays
            else None
        )

    def respond_with_play(self, viewer, key, scene, data):
        decision = self.game.decision(viewer, data["id"])
        if decision["kind"] != "gorgon_response_play" or decision["revision"] != data["revision"]:
            raise WorkflowError("Open the original owned Gorgon response.")
        view = self.response_view(viewer, decision)
        if (
            not view
            or data["play"] not in {play for play, _ in view["plays"]}
            or data["heat"] not in view["heat"]
        ):
            raise WorkflowError("Choose an available response and the original actor's Heat.")
        actor = ActorRef.model_validate(decision["body"]["actor"])
        parent = decision["parent"]
        attacker = ActorRef.model_validate(decision["body"]["attacker"])
        play = data["play"]
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        prepared = PlayInput(
            play=play,
            heat=data["heat"],
            context=data["account"],
            trigger_confirmed=True,
            parent=parent,
            target_actor=attacker if play == "engage" else None,
            piloting=bool(actual.piloting) if actor.kind == "pilot" or play == "engage" else False,
        )

        def scoped(c):
            self.session.observer._scene(c, scene, viewer)
            if parent not in self.session.reactions.alternate_action_ids(c, scene):
                raise WorkflowError("Use the exact original alternate Play in this scene.")

        with self.store.source_guard(scoped):
            if actor.kind == "pilot":
                return self.game.begin(
                    viewer,
                    key,
                    int(decision["channel"]),
                    state.sheets[actor.entity].revision,
                    prepared,
                )
            if actor.kind == "external_pilot" and actual.girl == "harpy":
                service = ActorPlayService(self.game)
                view = service.preview(viewer, int(decision["channel"]), actor)
                judge = view["adjudicator"]["ref"]
                return service.begin(
                    viewer,
                    key,
                    int(decision["channel"]),
                    actor,
                    actual.source_sha256,
                    ActorRef.model_validate(judge) if judge else None,
                    view["cast_revision"],
                    prepared,
                )
        raise WorkflowError("This original response needs its own actual role control.")
