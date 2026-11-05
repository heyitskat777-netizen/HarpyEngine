"""Actual-role Plays use the existing transactional lock, dice, receipt and choice pipeline."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actor_plays as rules
from girlframe.engine import m3_cast
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, tier
from girlframe.engine.m3_actor_resources import Commitment, Committed, commit
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_policy import RULESET
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class Judge(NamedTuple):
    ref: ActorRef | None
    controller: int
    label: str
    appointment: str | None = None


class ActorPlayService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _judge(self, c: Connection, state: GameState, cast: SceneCast, acting: ActorRef) -> Judge:
        if acting.kind == "external_pilot" and cast.adjudicator is None:
            from girlframe.services.m3_medical import MedicalService

            human, appointment = MedicalService(self.store)._handler(c)
            if cast.facilitator != human or state.handler != human:
                raise WorkflowError("Recover this scene's actual original human GM.")
            return Judge(None, human, "Handler (rules adjudication)", appointment)
        actual = m3_cast.adjudicator(
            state, cast, profiles(c, self.store.campaign_id), acting=acting
        )
        return Judge(actual.ref, actual.controller, actual.label)

    def _eligible_play(
        self, state: GameState, actor: ActorRef, *, rejection: bool, play: str = "keep_your_head"
    ) -> None:
        if actor.kind != "external_pilot":
            return
        from girlframe.engine.m3_actor_bonds import is_helpless
        from girlframe.engine.m3_harpy_defeat import harpy

        actual = harpy(state, actor)
        if actual.body_incapacitated:
            raise WorkflowError("The actual Harpy body is incapacitated.")
        if not rejection and (
            any(x.play == play for x in actual.blocked_plays)
            or play == "keep_your_head"
            and is_helpless(state, actor)
        ):
            raise WorkflowError("This actual Harpy cannot make the defensive Keep Your Head Play.")

    def saved(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            table = t.m2["m2_actions"]
            rows = c.execute(
                sa.select(table.c.id, table.c.revision, table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.actor_id == str(viewer.user_id),
                    table.c.state == "aborted",
                )
            )
            return [
                dict(id=identity, revision=revision, rolled=bool(data["receipt"]))
                for identity, revision, body in rows
                if (data := json.loads(body)).get("actor_basic") and data.get("actor_recovery")
            ]

    def recover(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, *, cancel: bool = False
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            action = self.game.action(c, identity)
            if not action["data"].get("actor_basic") or int(action["actor_id"]) != viewer.user_id:
                raise WorkflowError("Only the actual acting human may recover this Play")
            self.authorize(c, viewer, action)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            action = self.game.action(c, identity)
            saved = action["data"].get("actor_recovery")
            lock = self.game.lock(c, action["channel_id"])
            if (
                action["state"] != "aborted"
                or action["revision"] != expected
                or saved is None
                or saved["root"] != identity
                or lock is None
                or lock["state"] != "released"
                or lock["action_id"] != identity
            ):
                raise WorkflowError("Restore chat and refresh your actual saved Play first")
            if cancel:
                if action["data"]["receipt"]:
                    raise WorkflowError(
                        "A known roll cannot be discarded, refunded or rolled again"
                    )
                del action["data"]["actor_recovery"]
                self.game.save_action(c, action)
            else:
                self.validate(c, load_state(c, self.store.campaign_id), action)
                choices = t.m2["m2_choices"]
                for item in saved["choices"]:
                    result = c.execute(
                        choices.update()
                        .where(
                            choices.c.campaign_id == self.store.campaign_id,
                            choices.c.action_id == identity,
                            choices.c.id == item["id"],
                            choices.c.revision == item["revision"],
                            choices.c.state == "aborted",
                        )
                        .values(state=item["state"], revision=item["revision"] + 1)
                    )
                    if result.rowcount != 1:
                        raise WorkflowError(
                            "The saved response changed; explicit recovery is required"
                        )
                del action["data"]["actor_recovery"]
                self.game.save_action(c, action, state=saved["state"])
                locks = t.m2["m2_locks"]
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == action["channel_id"],
                    )
                    .values(state="acquiring", body_json="{}", lease_until=0, claim_token=None)
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.actor_play_recovered",
                action_id=identity,
                cancelled_unrolled=cancel,
            )
            return {
                "action_id": identity,
                "receipt_preserved": bool(action["data"]["receipt"]),
                "cancelled_unrolled": cancel,
            }

        try:
            return self.store._write(
                viewer,
                key,
                "m3.actor_play_recovered",
                dict(action_id=identity, expected=expected, cancel=cancel),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def authorize(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
    ) -> None:
        from girlframe.services.m3_access import Access

        Access(self.store).authorize(c, viewer, "plays", director_response=True)
        if action is not None:
            approval = self.store.policy.m3_approval
            assert approval is not None
            if action["data"]["actor_basic"]["registry"] != approval.registry_sha256:
                raise WorkflowError("M3_POLICY_CHANGED: explicitly recover this saved Play.")
            if viewer.user_id not in action["data"]["participants"]:
                raise WorkflowError("This actual-role Play is unavailable to you.")

    def actors(
        self, c: Connection, state: GameState, channel: int, *, fresh: bool = True
    ) -> tuple[SceneCast, tuple[ActorView, ...]]:
        scene = self.game.scene(c, channel)
        cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        if cast is None:
            raise ValueError("Join your actual role and select its Director in /mission cast")
        bindings = profiles(c, self.store.campaign_id)
        actual = tuple(
            resolve(state, x.actor, bindings, require_current_profile=fresh) for x in cast.roles
        )
        for actor in actual:
            m3_cast.validate_role(cast, actor)
        if (
            state.handler is None
            or HandlerService(self.store).current(c)[1].handler_id != state.handler
        ):
            raise ValueError("STALE_HANDLER: recover the actual Handler appointment")
        return cast, actual

    def preview(self, viewer: GuildViewer, channel: int, ref: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast, actors = self.actors(c, state, channel)
            actor = next(
                (x for x in actors if x.ref == ref and x.controller == viewer.user_id), None
            )
            if actor is None or not (
                actor.rules == "handler_girl"
                or actor.ref.kind == "external_pilot"
                and actor.girl == "harpy"
            ):
                raise WorkflowError("Select your actual Handler Girl-rules role or Harpy body.")
            judge = self._judge(c, state, cast, ref)
            from girlframe.engine.m3_enforcer_requisitions import PAVLOV, SNOOP
            from girlframe.engine.m3_harpy_defeat import harpy
            from girlframe.services.m3_battle import _visible
            from girlframe.services.m3_enforcement_initiative import preview as initiative_preview
            from girlframe.services.m3_enforcer_requisitions import owned
            from girlframe.services.m3_enforcer_snoop import _targets as snoop_targets

            initiative = initiative_preview(self.game, viewer, channel, actor_ref=ref)

            return {
                "actor": actor.model_dump(mode="json"),
                "adjudicator": {
                    "ref": judge.ref.model_dump(mode="json") if judge.ref else None,
                    "label": judge.label,
                },
                "cast_revision": cast.revision,
                "game_revision": state.revision,
                "opponents": [
                    {"ref": x.ref.model_dump(mode="json"), "token": x.ref.token, "name": x.label}
                    for x in actors
                    if x.ref != ref and _visible(state, x.ref, viewer.user_id)
                ],
                "pavlov": owned(c, self.game, state, ref, PAVLOV) is not None,
                "snoop_targets": snoop_targets(self.game, c, state, ref)
                if owned(c, self.game, state, ref, SNOOP) is not None
                else [],
                "enforcement_targets": initiative["targets"] if initiative["available"] else [],
                "forbidden_plays": [x.play for x in harpy(state, ref).blocked_plays]
                if actor.girl == "harpy"
                else [],
                "retained_plays": list(getattr(harpy(state, ref), "plays", ()))
                if actor.girl == "harpy"
                else [],
            }

    def begin(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        ref: ActorRef,
        expected: str,
        adjudicator: ActorRef | None,
        cast_revision: int,
        prepared: PlayInput,
        *,
        rejection: str | None = None,
    ) -> dict[str, Any]:
        prepared = PlayInput.model_validate_json(prepared.model_dump_json())
        battle_play = prepared.play in ("all_out_assault", "go_for_the_core")
        mockingbird_play = prepared.play in ("mockingbird_person", "mockingbird_sex")
        if battle_play:
            from girlframe.engine.m3_plays import HEAT_IDS

            if prepared.play not in HEAT_IDS:
                raise WorkflowError("M3_REVIEW_PENDING: actual-role combat remains release-gated")
        if (
            (
                prepared.play != "actor_reject_tag"
                if rejection
                else prepared.play
                not in (
                    "keep_your_head",
                    "dive_deep",
                    "check_sensors",
                    "engage",
                    "go_off_duty",
                    "mockingbird_person",
                    "mockingbird_sex",
                    "snoop",
                    "enforcement_initiative",
                    "all_out_assault",
                    "go_for_the_core",
                )
            )
            or prepared.target is not None
            or prepared.parent is not None
            and rejection is not None
            or prepared.off_duty_id is not None
            or prepared.piloting
            and not (
                battle_play
                or prepared.play in ("engage", "snoop", "enforcement_initiative")
                or mockingbird_play
            )
            or prepared.order_id is not None
            or prepared.witnessed
            or prepared.target_actor is not None
            and not (
                battle_play
                or prepared.play in ("engage", "snoop", "enforcement_initiative")
                or mockingbird_play
            )
            or prepared.source_work is not None
            and prepared.play != "dive_deep"
            and not mockingbird_play
        ):
            raise WorkflowError("UNSUPPORTED_RULE: select an implemented actual-role Play.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast, actors = self.actors(c, state, channel)
            actor = next((x for x in actors if x.ref == ref), None)
            from girlframe.services.m3_scene_requisitions import guard

            guard(c, self.store, cast.id, ref, continuation=prepared.parent is not None)
            judge = self._judge(c, state, cast, ref)
            if (
                actor is None
                or actor.controller != viewer.user_id
                or not (
                    actor.rules == "handler_girl"
                    or actor.ref.kind == "external_pilot"
                    and actor.girl == "harpy"
                )
                or actor.source_sha256 != expected
                or judge.ref != adjudicator
                or cast.revision != cast_revision
            ):
                raise ValueError("STALE_ACTOR: confirm your actual resources and Director first")
            parent = self.game.action(c, prepared.parent) if prepared.parent else None
            counter = None
            dive = None
            battle = None
            engage = None
            dormant_source = None
            required_adjudication = None
            harpy_rest = None
            mockingbird = None
            snoop = None
            enforcement = None
            gorgon_counter = None
            if battle_play:
                from girlframe.services.m3_battle import prepare

                if actor.girl != "harpy":
                    raise ValueError("Use the actual Harpy's own combat role and resources")
                battle = prepare(self.game, c, viewer, state, self.game.scene(c, channel), prepared)
                if battle["actor"] != ref.model_dump(mode="json"):
                    raise ValueError("The declared combatant must be this exact Harpy body")
            if prepared.play == "engage":
                from girlframe.services.m3_engage import prepare as prepare_engage

                engage = prepare_engage(
                    self.game,
                    c,
                    viewer,
                    state,
                    self.game.scene(c, channel),
                    prepared,
                    actor_ref=ref,
                )
            if prepared.play == "snoop":
                from girlframe.services.m3_enforcer_snoop import prepare as prepare_snoop

                snoop = prepare_snoop(
                    self.game, c, viewer, prepared, state, channel=channel, actor_ref=ref
                )
            if prepared.play == "enforcement_initiative":
                from girlframe.services.m3_enforcement_initiative import prepare as prepare_enforcer

                enforcement = prepare_enforcer(
                    self.game, c, viewer, prepared, state, channel=channel, actor_ref=ref
                )
            if prepared.play == "go_off_duty":
                from girlframe.services.m3_harpy_rest import prepare as prepare_rest

                harpy_rest = prepare_rest(self.game, c, viewer, state, cast, prepared, ref)
            if mockingbird_play:
                from girlframe.services.m3_mockingbird_plays import prepare as prepare_mockingbird

                mockingbird = prepare_mockingbird(
                    self.game, c, viewer, prepared, state, channel=channel, actor_ref=ref
                )
            if prepared.play == "dive_deep":
                from girlframe.services.m3_dive import prepare_actor

                dive = prepare_actor(self.game, c, viewer, state, cast, prepared, ref)
                if prepared.source_work:
                    from girlframe.services.m3_battle_dormant import prepare_dive_source

                    dormant_source = prepare_dive_source(
                        self.game, c, viewer, prepared, state, channel
                    )
                from girlframe.services.m3_adjudication import prepare_required_dive

                required_adjudication = prepare_required_dive(
                    self.game,
                    c,
                    viewer,
                    prepared,
                    state,
                    actor=ref,
                    channel=channel,
                    source=dormant_source,
                )
            if parent is not None:
                from girlframe.services.m3_battle import validate_counter_child

                if parent["scene_id"] != cast.id or int(parent["channel_id"]) != channel:
                    raise ValueError("Continue this counter-Play in its original source scene")
                if parent["data"].get("gorgon_play"):
                    from girlframe.services.m3_gorgon_play import validate_child

                    gorgon_counter = validate_child(self.game, c, parent, ref, prepared)
                elif dormant_source is None:
                    counter = validate_counter_child(self.game, c, parent, ref, prepared)
            if self.game.pending_actions(c) and parent is None:
                raise ValueError("SCENE_BUSY: finish or recover the pending Play first")
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released" and parent is None:
                raise ValueError("SCENE_BUSY: restore the existing scene lock first")
            commitment = Commitment(
                heat=prepared.heat,
                identity=prepared.identity,
                gain=prepared.gain,
                pair_share=prepared.pair_share,
            )
            if required_adjudication is None:
                self._eligible_play(state, ref, rejection=rejection is not None, play=prepared.play)
            elif actor.ref.kind == "external_pilot":
                from girlframe.engine.m3_harpy_defeat import harpy

                if harpy(state, actor.ref).body_incapacitated:
                    raise WorkflowError("The actual Harpy body is incapacitated.")
            if prepared.play == "check_sensors":
                if actor.girl != "harpy" or commitment != Commitment(heat=0):
                    raise ValueError("A Harpy asks honest Sensor questions without dice or Heat")
            elif not rejection and required_adjudication is None and harpy_rest is None:
                commit(state, ref, profiles(c, self.store.campaign_id), commitment, expected)
            if rejection:
                item = next((x for x in state.obligations if x.id == rejection), None)
                if (
                    item is None
                    or item.kind != "actor_reject_tag"
                    or item.state != "pending"
                    or item.owner != viewer.user_id
                    or ActorRef.model_validate_json(item.details["actor"]) != ref
                    or commitment != Commitment(heat=0)
                ):
                    raise ValueError(
                        "Choose your actual owed Tag rejection without spending resources"
                    )
                if ref.kind == "external_pilot":
                    from girlframe.services.m3_tag_permissions import PermissionService

                    PermissionService(self.store).authorize_rejection(
                        c, viewer, state, ref, item.details["tag"]
                    )
            identity = str(uuid4())
            approval = self.store.policy.m3_approval
            assert approval is not None
            participants = sorted(
                {x.controller for x in actors} | {cast.facilitator or judge.controller}
            )
            data = {
                "actor_basic": {
                    "ref": ref.model_dump(mode="json"),
                    "label": actor.label,
                    "adjudicator": judge.ref.model_dump(mode="json") if judge.ref else None,
                    "adjudicator_controller": judge.controller,
                    "adjudicator_appointment": judge.appointment,
                    "cast_revision": cast.revision,
                    "registry": approval.registry_sha256,
                    "source_sha256": expected,
                    "commitment": commitment.model_dump(mode="json"),
                    "rejection": rejection,
                },
                "prepared": prepared.model_dump(mode="json"),
                "play": prepared.play,
                "participants": participants,
                "handler": state.handler,
                "receipt": None,
                "modifiers": [],
                "result": {},
                "choices": {},
            }
            from girlframe.engine.m3_handler_consequences import active_handler

            handler = active_handler(state)
            data["tag_context"] = dict(
                actor=ref.model_dump(mode="json"),
                handler=handler.model_dump(mode="json") if handler else None,
                cast=cast.model_dump(mode="json"),
                cast_sha256=fingerprint(cast),
                table=participants,
            )
            if dive is not None:
                data["dive"] = dive
            if battle is not None:
                data["battle"] = battle
            if engage is not None:
                data["engage"] = engage
            if snoop is not None:
                data["snoop"] = snoop
            if enforcement is not None:
                data["enforcement"] = enforcement
            if prepared.play == "keep_your_head":
                from girlframe.services.m3_enforcer_requisitions import prepare_keep

                data["enforcer_keep"] = prepare_keep(self.game, c, state, ref, prepared)
            if dormant_source is not None:
                data["dormant_dive_source"] = dormant_source
            if required_adjudication is not None:
                data["adjudication"] = required_adjudication
            if harpy_rest is not None:
                data["harpy_off_duty"] = harpy_rest
            if mockingbird is not None:
                data["mockingbird"] = mockingbird
            if parent is not None and counter is not None:
                data["battle_counter_source"] = dict(
                    choice=counter["id"],
                    actor=ref.model_dump(mode="json"),
                    attacker=parent["data"]["battle"]["actor"],
                )
            if parent is not None and gorgon_counter is not None:
                data["gorgon_counter_source"] = dict(
                    choice=gorgon_counter["id"],
                    actor=ref.model_dump(mode="json"),
                    attacker=parent["data"]["gorgon_play"]["actor"],
                )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=cast.id,
                    parent_id=prepared.parent,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            values = dict(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            table = t.m2["m2_locks"]
            if parent is not None:
                self.game.save_action(c, self.game.action(c, identity), state="ready_to_roll")
            elif lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.game.event(c, viewer.user_id, key, "m3.actor_play_confirmed", action_id=identity)
            return {"action_id": identity, "state": "ready_to_roll" if parent else "acquiring"}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.actor_play_confirmed",
                dict(
                    channel=channel,
                    ref=ref.model_dump(mode="json"),
                    expected=expected,
                    adjudicator=adjudicator.model_dump(mode="json") if adjudicator else None,
                    cast_revision=cast_revision,
                    prepared=prepared.model_dump(mode="json"),
                    rejection=rejection,
                ),
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def validate(self, c: Connection, state: GameState, action: dict[str, Any]) -> ActorView:
        from girlframe.services.m3_harpy_defeat import (
            owned_director_procedure,
            source_actor_continuation,
        )

        continued = source_actor_continuation(self.game, c, state, action)
        if continued is not None:
            return continued
        continued = owned_director_procedure(self.game, c, state, action)
        if continued is not None:
            return continued
        meta = action["data"]["actor_basic"]
        ref = ActorRef.model_validate(meta["ref"])
        cast, actors = self.actors(c, state, int(action["channel_id"]), fresh=False)
        actor = next((x for x in actors if x.ref == ref), None)
        source = action["data"].get("tag_context")
        old_judge = ActorRef.model_validate(meta["adjudicator"]) if meta["adjudicator"] else None
        procedural = (
            action["data"]["play"] == "check_sensors"
            and bool(action["data"]["result"].get("questions"))
        ) or (action["data"]["play"] == "keep_your_head" and "positive" in action["data"]["result"])
        if (
            ref.kind == "external_pilot"
            and actor is not None
            and actor.girl == "harpy"
            and actor.controller == int(action["actor_id"])
            and procedural
            and source is not None
            and old_judge is not None
        ):
            from girlframe.services.m3_harpy_defeat import ended_director_judge

            original = SceneCast.model_validate_json(json.dumps(source["cast"]))
            if (
                fingerprint(original) == source["cast_sha256"]
                and original.revision == meta["cast_revision"]
                and ended_director_judge(
                    self.game,
                    c,
                    state,
                    original,
                    cast,
                    old_judge,
                    meta["adjudicator_controller"],
                )
            ):
                return actor
        judge = self._judge(c, state, cast, ref)
        if (
            cast.id != action["scene_id"]
            or cast.revision != meta["cast_revision"]
            or actor is None
            or actor.controller != int(action["actor_id"])
            or not (
                actor.rules == "handler_girl"
                or actor.ref.kind == "external_pilot"
                and actor.girl == "harpy"
            )
            or judge.ref
            != (ActorRef.model_validate(meta["adjudicator"]) if meta["adjudicator"] else None)
            or judge.controller != meta["adjudicator_controller"]
            or judge.appointment != meta.get("adjudicator_appointment")
        ):
            raise ValueError("STALE_CAST: explicitly recover the saved actual roles and responses")
        return actor

    def roll(
        self, c: Connection, viewer: GuildViewer, key: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        self.authorize(c, viewer, action)
        state = load_state(c, self.store.campaign_id)
        actor = self.validate(c, state, action)
        meta = action["data"]["actor_basic"]
        if action["data"].get("harpy_off_duty"):
            from girlframe.services.m3_harpy_rest import prepare as prepare_rest

            cast, _ = self.actors(c, state, int(action["channel_id"]), fresh=False)
            current = prepare_rest(
                self.game,
                c,
                viewer,
                state,
                cast,
                PlayInput.model_validate(action["data"]["prepared"]),
                actor.ref,
            )
            if current != action["data"]["harpy_off_duty"]:
                raise WorkflowError("STALE_HARPY_REST: refresh the actual original hide resources")
        if action["data"].get("adjudication"):
            from girlframe.engine.m3_harpy_defeat import harpy
            from girlframe.services.m3_adjudication import reserve_request

            if actor.ref.kind == "external_pilot" and harpy(state, actor.ref).body_incapacitated:
                raise WorkflowError("The actual Harpy body is incapacitated.")
            return reserve_request(self.game, c, viewer, action, key=key)
        self._eligible_play(
            state,
            actor.ref,
            rejection=bool(meta.get("rejection")),
            play=action["data"]["play"],
        )
        if action["data"]["play"] == "check_sensors":
            if actor.girl != "harpy":
                raise ValueError("Only the actual Harpy uses the diceless Sensor adjustment")
            action["state"] = "awaiting_choices"
            action["data"]["result"]["questions"] = action["data"]["prepared"]["context"]
            self.game.request(c, action, meta["adjudicator_controller"], "harpy_sensor_answers")
        elif meta.get("rejection"):
            item = next(x for x in state.obligations if x.id == meta["rejection"])
            if item.state != "pending":
                raise ValueError("This rejection has already resolved")
            if actor.ref.kind == "external_pilot":
                from girlframe.services.m3_tag_permissions import PermissionService

                PermissionService(self.store).authorize_rejection(
                    c, viewer, state, actor.ref, item.details["tag"]
                )
            rules.reject(state, actor.ref, item.details["tag"])
            item.state = "fulfilled"
            self.finish(c, state, action)
        else:
            if action["data"].get("mockingbird"):
                from girlframe.services.m3_mockingbird_plays import pre_roll as mockingbird_pre_roll

                mockingbird_pre_roll(self.game, c, state, action)
            if action["data"].get("snoop"):
                from girlframe.services.m3_enforcer_snoop import pre_roll as snoop_pre_roll

                snoop_pre_roll(self.game, c, viewer, state, action)
            if action["data"].get("enforcement"):
                from girlframe.services.m3_enforcement_initiative import (
                    pre_roll as enforcer_pre_roll,
                )

                action["data"]["enforcement"]["roll_event"] = str(uuid4())
                enforcer_pre_roll(self.game, c, viewer, state, action)
            if action["data"].get("engage"):
                from girlframe.services.m3_engage import pre_roll as engage_pre_roll

                engage_pre_roll(self.game, c, state, action)
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import pre_roll as battle_pre_roll

                battle_pre_roll(self.game, c, state, action)
            if action["data"].get("dive"):
                from girlframe.services.m3_dive import pre_roll

                pre_roll(self.game, c, viewer, state, action)
            committed = (
                Committed(state=state)
                if action["data"].get("harpy_off_duty")
                else commit(
                    state,
                    actor.ref,
                    profiles(c, self.store.campaign_id),
                    Commitment.model_validate(meta["commitment"]),
                    meta["source_sha256"],
                )
            )
            if committed.followups:
                raise ValueError(
                    "UNSUPPORTED_RULE: this actual-role follow-up needs its owned resolver"
                )
            state = committed.state
            base_modifier = 0
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import modifier as battle_modifier

                base_modifier = battle_modifier(state, action)
            faces = self.game.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise ValueError("Dice source returned invalid faces")
            receipt = dict(
                id=str(uuid4()),
                action_id=action["id"],
                faces=list(faces),
                heat=meta["commitment"]["heat"],
                pre_total=sum(faces) + meta["commitment"]["heat"] + base_modifier,
                rng_source=self.game.rng_source,
                rolled_utc=datetime.now(UTC).isoformat(),
                ruleset=RULESET,
            )
            if action["data"].get("battle"):
                receipt["pre_modifiers"] = [
                    dict(source="target_undamaged_assets", amount=base_modifier)
                ]
            c.execute(
                t.m2["m2_receipts"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    action_id=action["id"],
                    id=receipt["id"],
                    body_json=json.dumps(receipt, sort_keys=True),
                )
            )
            action["data"]["receipt"] = receipt
            action["state"] = "tag_window"
            for person in action["data"]["participants"]:
                self.game.request(c, action, person, "tag_window")
            self.game.queue(
                c,
                action,
                "receipt",
                dict(receipt=receipt, callsign=actor.label, play=action["data"]["play"]),
            )
        self.game.save_action(c, action)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.rolled" if action["data"].get("battle") else "m3.actor_play_advanced",
            state,
            action_id=action["id"],
            event_id=action["data"]["battle"]["roll_event"]
            if action["data"].get("battle")
            else action["data"]["enforcement"]["roll_event"]
            if action["data"].get("enforcement")
            else None,
        )
        return {"action_id": action["id"], "receipt": action["data"]["receipt"]}

    def finish(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        if self.game.pending(c, action["id"]):
            raise ValueError("Mandatory actual-role responses remain pending")
        from girlframe.services.m3_mockingbird import intercept_finish

        if intercept_finish(self.game, c, state, action):
            return
        action["state"] = "complete"
        self.game.queue(
            c,
            action,
            "outcome",
            dict(
                play=action["data"]["play"],
                callsign=action["data"]["actor_basic"].get("label")
                or resolve(
                    state,
                    ActorRef.model_validate(action["data"]["actor_basic"]["ref"]),
                    profiles(c, self.store.campaign_id),
                    require_alive=False,
                    require_current_profile=False,
                ).label,
                receipt=action["data"]["receipt"],
                total=action["data"]["result"].get("total"),
                tier=action["data"]["result"].get("tier"),
            ),
        )

    def synchronize(
        self, c: Connection, action: dict[str, Any], event: str, viewer: GuildViewer, key: str
    ) -> None:
        if (
            action["state"] == "complete"
            and action.get("parent_id")
            and action["data"].get("battle_counter_source")
        ):
            from girlframe.services.m3_battle import complete_counter_play

            complete_counter_play(self.game, c, action, event, viewer, key)
        elif action["state"] == "complete" and action["data"].get("gorgon_counter_source"):
            from girlframe.services.m3_gorgon_play import complete_response

            complete_response(self.game, c, action, event, viewer, key)

    def results(
        self, c: Connection, action: dict[str, Any], *, state: GameState | None = None
    ) -> None:
        total = action["data"]["receipt"]["pre_total"] + sum(
            x["amount"] for x in action["data"]["modifiers"]
        )
        action["data"]["result"].update(total=total, tier=tier(total))
        action["state"] = "awaiting_choices"
        from girlframe.services.m3_mockingbird import intercept_results

        state = state or load_state(c, self.store.campaign_id)
        if intercept_results(self.game, c, state, action):
            return
        if action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import results as enforcer_results

            enforcer_results(self.game, c, state, action)
        elif action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import results as snoop_results

            snoop_results(self.game, c, state, action)
        elif action["data"].get("mockingbird"):
            from girlframe.services.m3_mockingbird_plays import results as mockingbird_results

            mockingbird_results(self.game, c, state, action)
        elif action["data"].get("harpy_off_duty"):
            from girlframe.services.m3_harpy_rest import results as rest_results

            rest_results(self.game, c, state, action)
        elif action["data"].get("battle"):
            if action["data"]["play"] == "all_out_assault":
                from girlframe.services.m3_engage import start_assault_extra

                start_assault_extra(self.game, c, action)
            else:
                from girlframe.services.m3_battle import results as battle_results

                battle_results(self.game, c, action)
        elif action["data"].get("engage"):
            from girlframe.services.m3_engage import results as engage_results

            engage_results(self.game, c, state, action)
        elif action["data"].get("dive"):
            from girlframe.services.m3_dive import results

            results(self.game, c, action)
        else:
            self.game.request(c, action, int(action["actor_id"]), "actor_keep")

    def select_tag(
        self, c: Connection, state: GameState, action: dict[str, Any], selected: dict[str, Any]
    ) -> None:
        ref = ActorRef.model_validate(action["data"]["actor_basic"]["ref"])
        from girlframe.services.m3_tag_markers import current as current_markers

        saved_marker = selected.get("marker")
        if saved_marker is not None and not any(
            marker.model_dump(mode="json") == saved_marker
            for marker in current_markers(self.game, c, state, action, selected["controller"])
        ):
            action["data"]["tag_proposals"] = [
                p for p in action["data"]["tag_proposals"] if p["id"] != selected["id"]
            ]
            action["data"].pop("tag_candidate", None)
            action["data"].pop("tag_consensus", None)
            action["state"] = "tag_window"
            self.game.request(c, action, selected["controller"], "tag_window")
            return
        # Revalidate the actual proposal and Bond immediately before applying it.
        amount = rules.proposal(
            state,
            ref,
            ActorRef.model_validate(selected["ref"]) if selected["ref"] else None,
            selected["controller"],
            profiles(c, self.store.campaign_id),
            selected["tag"],
            action["scene_id"],
            selected["direction"],
            selected["account"],
            ooc_controller=selected["controller"]
            if saved_marker is not None and saved_marker["actor"] is None
            else None,
        )
        repeated = rules.mark(state, ref, selected["tag"], action["scene_id"])
        action["data"]["modifiers"].append(
            {
                "source": "girl_tag",
                "amount": amount,
                "tag": selected["tag"],
                "actor_ref": selected["ref"],
            }
        )
        if repeated:
            self.game.request(
                c, action, int(action["actor_id"]), "tag_resolution", {"tag": selected["tag"]}
            )
        else:
            self.results(c, action, state=state)

    def apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
        *,
        viewer: GuildViewer | None = None,
    ) -> None:
        actor = self.validate(c, state, action)
        owner, kind = int(row["actor_id"]), row["kind"]
        body, meta = json.loads(row["body_json"]), action["data"]["actor_basic"]
        judge = meta["adjudicator_controller"]
        if kind.startswith("snoop_") and action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import apply as snoop_apply

            snoop_apply(self.game, c, state, action, row, answer)
        elif kind.startswith("enforcer_") and action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import apply as enforcer_apply

            enforcer_apply(self.game, c, state, action, row, answer)
        elif kind.startswith("harpy_off_duty_"):
            from girlframe.services.m3_harpy_rest import respond as rest_respond

            rest_respond(self.game, c, state, action, row, answer)
        elif (
            kind.startswith("mockingbird_")
            and action["data"].get("mockingbird")
            and kind not in ("mockingbird_risk", "mockingbird_void_threshold")
        ):
            from girlframe.services.m3_mockingbird_plays import apply as book_apply

            book_apply(self.game, c, state, action, row, answer)
        elif kind in ("mockingbird_risk", "mockingbird_void_threshold"):
            from girlframe.services.m3_mockingbird import apply as mockingbird_apply

            mockingbird_apply(self.game, c, state, action, row, answer)
        elif kind.startswith("engage_"):
            from girlframe.services.m3_engage import apply as engage_apply

            engage_apply(self.game, c, state, action, row, answer)
        elif action["data"].get("engage") and kind.startswith("battle_"):
            from girlframe.services.m3_battle import apply_damage_response

            apply_damage_response(self.game, c, state, action, row, answer)
        elif action["data"].get("battle") and kind.startswith("battle_"):
            from girlframe.services.m3_battle import apply as battle_apply

            battle_apply(self.game, c, state, action, row, answer)
        elif action["data"].get("dive") and kind.startswith("dive_"):
            from girlframe.services.m3_dive import apply

            apply(self.game, c, state, action, row, answer)
        elif kind == "tag_window":
            if answer.options == ("pass",):
                if (
                    answer.denied
                    or answer.fields
                    or answer.number is not None
                    or answer.flag is not None
                    or answer.member
                ):
                    raise ValueError("A pass does not commit a Tag or another role's modifier")
            elif answer.options == ("tag",) and len(answer.denied) == 1:
                from girlframe.services.m3_tag_markers import current as current_markers

                marker = next(
                    (
                        x
                        for x in current_markers(self.game, c, state, action, owner)
                        if x.token == answer.fields.get("as_actor")
                        or x.actor is not None
                        and x.actor.token == answer.fields.get("as_actor")
                    ),
                    None,
                )
                if (
                    marker is None
                    or set(answer.fields) != {"as_actor"}
                    or answer.flag is not None
                    or answer.member
                ):
                    raise ValueError("Choose one of your actual cast roles for this proposal")
                rules.proposal(
                    state,
                    actor.ref,
                    marker.actor,
                    owner,
                    profiles(c, self.store.campaign_id),
                    answer.denied[0],
                    action["scene_id"],
                    answer.number or 0,
                    answer.text,
                    ooc_controller=marker.controller if marker.actor is None else None,
                )
                action["data"].setdefault("tag_proposals", []).append(
                    dict(
                        id=row["id"],
                        controller=owner,
                        ref=marker.actor.model_dump(mode="json") if marker.actor else None,
                        marker=marker.model_dump(mode="json"),
                        tag=answer.denied[0],
                        direction=answer.number,
                        account=answer.text,
                    )
                )
            else:
                raise ValueError("Pass or propose exactly one observed Tag")
            if not any(x["kind"] == "tag_window" for x in self.game.pending(c, action["id"])):
                proposals = action["data"].get("tag_proposals", [])
                if len(proposals) == 1:
                    self.select_tag(c, state, action, proposals[0])
                elif proposals:
                    self.game.request(c, action, judge, "actor_tag_selection")
                else:
                    self.results(c, action, state=state)
        elif kind == "actor_tag_selection" and owner == judge:
            selected = next(
                (x for x in action["data"]["tag_proposals"] if answer.options == (x["id"],)), None
            )
            if selected is None:
                raise ValueError("Propose one of the saved actual Tag proposals for discussion")
            action["data"]["tag_candidate"] = selected["id"]
            action["data"]["tag_consensus"] = {str(judge): True}
            for person in action["data"]["participants"]:
                if person != judge:
                    self.game.request(c, action, person, "actor_tag_agreement")
        elif kind == "actor_tag_agreement":
            if answer.flag is None:
                raise ValueError("Record your own agreement or disagreement")
            action["data"]["tag_consensus"][str(owner)] = answer.flag
            if not any(x["kind"] == kind for x in self.game.pending(c, action["id"])):
                if all(action["data"]["tag_consensus"].values()):
                    self.select_tag(
                        c,
                        state,
                        action,
                        next(
                            x
                            for x in action["data"]["tag_proposals"]
                            if x["id"] == action["data"]["tag_candidate"]
                        ),
                    )
                else:
                    self.game.request(c, action, judge, "actor_tag_selection")
        elif kind == "tag_resolution" and owner == actor.controller:
            tag = next(x for x in rules.tags(state, actor.ref) if x.id == body["tag"])
            if answer.options == ("embrace",):
                rules.embrace(state, actor.ref, tag.id, answer.denied)
            elif answer.options == ("reject",) and not answer.denied:
                if actor.ref.kind == "external_pilot":
                    from girlframe.services.m3_tag_permissions import PermissionService

                    if viewer is None or viewer.user_id != owner:
                        raise ValueError("Use the actual authenticated Tag bearer's response")
                    PermissionService(self.store).authorize_rejection(
                        c, viewer, state, actor.ref, tag.id
                    )
                rules.defer_rejection(state, actor.ref, tag.id)
                self.game.obligation(
                    state,
                    action,
                    "actor_reject_tag",
                    actor.controller,
                    actor=actor.ref.model_dump_json(),
                    tag=tag.id,
                )
            else:
                raise ValueError(
                    "Choose to embrace or take action to reject the actual repeated Tag"
                )
            self.results(c, action, state=state)
        elif kind == "harpy_sensor_answers" and owner == judge:
            if (
                actor.girl != "harpy"
                or action["data"]["play"] != "check_sensors"
                or answer.flag is not True
                or not answer.text.strip()
                or answer.options
                or answer.denied
                or answer.fields
                or answer.number is not None
                or answer.member is not None
            ):
                raise ValueError("The actual adjudicator answers every question honestly")
            action["data"]["result"].update(answers=answer.text, honest_attested=True)
            self.finish(c, state, action)
        elif kind == "actor_keep" and owner == actor.controller:
            from girlframe.services.m3_enforcer_requisitions import keep_extras

            extra = keep_extras(self.game, c, state, action, answer)
            ordinary = answer.model_copy(
                update={
                    "fields": {
                        k: v for k, v in answer.fields.items() if not k.startswith("pavlov_")
                    }
                }
            )
            result = (
                rules.harpy_keep(state, actor.ref, action["data"]["result"]["tier"], ordinary)
                if actor.girl == "harpy"
                else rules.keep(action["data"]["result"]["tier"], ordinary)
            )
            result["positive"] = sorted(set(result["positive"]) | extra)
            if action["data"]["result"]["tier"] == "high":
                rules.add_tag(state, actor.ref, answer.text, tuple(action["data"]["participants"]))
            action["data"]["result"].update(result)
            self.game.request(c, action, judge, "handler_keep")
        elif kind == "handler_keep" and owner == judge:
            if answer.flag is None or not answer.text.strip():
                raise ValueError("The actual rules adjudicator must answer whether it is enough")
            action["data"]["result"].update(enough=answer.flag, ruling=answer.text)
            self.finish(c, state, action)
        else:
            raise ValueError("This actual-role response is unavailable or belongs to another role")

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.services.m3_tag_markers import current as current_markers

        state = load_state(c, self.store.campaign_id)
        actor = self.validate(c, state, action)
        cast, actual = self.actors(c, state, int(action["channel_id"]), fresh=False)
        own = actor.controller == viewer.user_id
        selected = action["data"].get("tag_candidate")
        proposals = action["data"].get("tag_proposals", [])
        result = dict(row) | {
            "actor_basic": True,
            "body": json.loads(row["body_json"]),
            "play": action["data"]["play"],
            "result": action["data"]["result"],
            "enforcer_keep": action["data"].get("enforcer_keep"),
            "harpy_off_duty": bool(action["data"].get("harpy_off_duty")),
            "actor": actor.controller,
            "own": {
                "girl": "harpy" if actor.girl == "harpy" else None,
                "harpy": actor.girl == "harpy",
                "retained_plays": list(getattr(harpy(state, actor.ref), "plays", ()))
                if actor.girl == "harpy"
                else [],
                "assets": [x.model_dump(mode="json") for x in actor.assets],
                "identities": [x.model_dump(mode="json") for x in actor.identities],
            }
            if own
            else None,
            "tags": [
                x.model_dump(mode="json")
                for x in rules.tags(state, actor.ref)
                if own or viewer.user_id in x.observers
            ],
            "roles": [
                {"token": marker.token, "label": marker.label}
                for marker in current_markers(self.game, c, state, action, viewer.user_id)
            ]
            if row["kind"] == "tag_window"
            else [],
            "proposals": [
                {
                    "id": x["id"],
                    "label": next(
                        t.label for t in rules.tags(state, actor.ref) if t.id == x["tag"]
                    ),
                    "direction": x["direction"],
                    "account": x["account"],
                }
                for x in proposals
                if x["id"] == selected or row["kind"] == "actor_tag_selection"
            ],
            "participants": action["data"]["participants"],
            "pilots": [],
            "labels": {},
            "parent": action["id"],
            "channel": int(action["channel_id"]),
            "context": action["data"]["prepared"]["context"],
        }
        if action["data"].get("dive") and row["kind"].startswith("dive_"):
            from girlframe.services.m3_dive import projection

            result["dive"] = projection(self.game, c, viewer, state, action, row)
        if action["data"].get("battle") and row["kind"].startswith("battle_"):
            from girlframe.services.m3_battle import projection as battle_projection

            result["battle"] = battle_projection(self.game, c, state, action, row)
        if row["kind"].startswith("engage_"):
            from girlframe.services.m3_engage import projection as engage_projection

            result["engage"] = engage_projection(self.game, c, state, action, row)
        if action["data"].get("harpy_off_duty"):
            from girlframe.services.m3_harpy_rest import projection as rest_projection

            result.update(rest_projection(state, action, row))
        if (
            row["kind"].startswith("mockingbird_")
            and action["data"].get("mockingbird")
            and row["kind"] not in ("mockingbird_risk", "mockingbird_void_threshold")
        ):
            from girlframe.services.m3_mockingbird_plays import projection as book_projection

            result["mockingbird_play"] = book_projection(self.game, c, state, action, row)
        elif row["kind"] in ("mockingbird_risk", "mockingbird_void_threshold"):
            from girlframe.services.m3_mockingbird import projection as mockingbird_projection

            result["mockingbird"] = mockingbird_projection(self.game, c, state, action, row)
        if action["data"].get("engage") and row["kind"].startswith("battle_"):
            from girlframe.services.m3_battle import damage_projection

            result["battle"] = damage_projection(self.game, c, state, action, row)
        if row["kind"] == "tag_resolution" and actor.ref.kind == "external_pilot":
            from girlframe.engine.m3_tag_permissions import can_reject

            result["rejection_blocked"] = not can_reject(state, actor.ref, result["body"]["tag"])
        if row["kind"].startswith("snoop_") and action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import projection as snoop_projection

            result["snoop"] = snoop_projection(self.game, c, viewer, state, action, row)
        if row["kind"].startswith("enforcer_") and action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import (
                projection as enforcer_projection,
            )

            result["enforcement"] = enforcer_projection(self.game, c, viewer, state, action, row)
        return result
