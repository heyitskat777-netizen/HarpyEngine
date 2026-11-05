"""Actual-role Plays use the existing transactional lock, dice, receipt and choice pipeline."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actor_plays as rules
from girlframe.engine import m3_cast
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, tier
from girlframe.engine.m3_actor_resources import Commitment, commit
from girlframe.engine.m3_actor_state import ActorRef, ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_policy import RULESET
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class ActorPlayService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

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
            if actor is None or actor.rules != "handler_girl":
                raise WorkflowError("This consumer requires your actual Handler Girl-rules role.")
            judge = m3_cast.adjudicator(
                state, cast, profiles(c, self.store.campaign_id), acting=ref
            )
            return {
                "actor": actor.model_dump(mode="json"),
                "adjudicator": {"ref": judge.ref.model_dump(mode="json"), "label": judge.label},
                "cast_revision": cast.revision,
                "game_revision": state.revision,
            }

    def begin(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        ref: ActorRef,
        expected: str,
        adjudicator: ActorRef,
        cast_revision: int,
        prepared: PlayInput,
        *,
        rejection: str | None = None,
    ) -> dict[str, Any]:
        prepared = PlayInput.model_validate_json(prepared.model_dump_json())
        if (
            prepared.play != ("actor_reject_tag" if rejection else "keep_your_head")
            or prepared.target is not None
            or prepared.parent is not None
            or prepared.off_duty_id is not None
            or prepared.piloting
            or prepared.order_id is not None
            or prepared.witnessed
        ):
            raise WorkflowError("UNSUPPORTED_RULE: select an implemented actual-role Play.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast, actors = self.actors(c, state, channel)
            actor = next((x for x in actors if x.ref == ref), None)
            from girlframe.services.m3_scene_requisitions import guard

            guard(c, self.store, cast.id, ref)
            judge = m3_cast.adjudicator(
                state, cast, profiles(c, self.store.campaign_id), acting=ref
            )
            if (
                actor is None
                or actor.controller != viewer.user_id
                or actor.rules != "handler_girl"
                or actor.source_sha256 != expected
                or judge.ref != adjudicator
                or cast.revision != cast_revision
            ):
                raise ValueError("STALE_ACTOR: confirm your actual resources and Director first")
            if self.game.pending_actions(c):
                raise ValueError("SCENE_BUSY: finish or recover the pending Play first")
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise ValueError("SCENE_BUSY: restore the existing scene lock first")
            commitment = Commitment(
                heat=prepared.heat,
                identity=prepared.identity,
                gain=prepared.gain,
                pair_share=prepared.pair_share,
            )
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
            identity = str(uuid4())
            approval = self.store.policy.m3_approval
            assert approval is not None
            participants = sorted(
                {x.controller for x in actors} | {cast.facilitator or judge.controller}
            )
            data = {
                "actor_basic": {
                    "ref": ref.model_dump(mode="json"),
                    "adjudicator": judge.ref.model_dump(mode="json"),
                    "adjudicator_controller": judge.controller,
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
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=cast.id,
                    parent_id=None,
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
            if lock:
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
            return {"action_id": identity, "state": "acquiring"}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.actor_play_confirmed",
                dict(
                    channel=channel,
                    ref=ref.model_dump(mode="json"),
                    expected=expected,
                    adjudicator=adjudicator.model_dump(mode="json"),
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
        meta = action["data"]["actor_basic"]
        ref = ActorRef.model_validate(meta["ref"])
        cast, actors = self.actors(c, state, int(action["channel_id"]), fresh=False)
        actor = next((x for x in actors if x.ref == ref), None)
        judge = m3_cast.adjudicator(state, cast, profiles(c, self.store.campaign_id), acting=ref)
        if (
            cast.id != action["scene_id"]
            or cast.revision != meta["cast_revision"]
            or actor is None
            or actor.controller != int(action["actor_id"])
            or actor.rules != "handler_girl"
            or judge.ref != ActorRef.model_validate(meta["adjudicator"])
            or judge.controller != meta["adjudicator_controller"]
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
        if meta.get("rejection"):
            item = next(x for x in state.obligations if x.id == meta["rejection"])
            if item.state != "pending":
                raise ValueError("This rejection has already resolved")
            rules.reject(state, actor.ref, item.details["tag"])
            item.state = "fulfilled"
            self.finish(c, state, action)
        else:
            committed = commit(
                state,
                actor.ref,
                profiles(c, self.store.campaign_id),
                Commitment.model_validate(meta["commitment"]),
                meta["source_sha256"],
            )
            if committed.followups:
                raise ValueError(
                    "UNSUPPORTED_RULE: this actual-role follow-up needs its owned resolver"
                )
            state = committed.state
            faces = self.game.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise ValueError("Dice source returned invalid faces")
            receipt = dict(
                id=str(uuid4()),
                action_id=action["id"],
                faces=list(faces),
                heat=meta["commitment"]["heat"],
                pre_total=sum(faces) + meta["commitment"]["heat"],
                rng_source=self.game.rng_source,
                rolled_utc=datetime.now(UTC).isoformat(),
                ruleset=RULESET,
            )
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
            c, viewer.user_id, key, "m3.actor_play_advanced", state, action_id=action["id"]
        )
        return {"action_id": action["id"], "receipt": action["data"]["receipt"]}

    def finish(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        if self.game.pending(c, action["id"]):
            raise ValueError("Mandatory actual-role responses remain pending")
        action["state"] = "complete"
        self.game.queue(
            c,
            action,
            "outcome",
            dict(
                play=action["data"]["play"],
                callsign="Handler",
                receipt=action["data"]["receipt"],
                total=action["data"]["result"].get("total"),
                tier=action["data"]["result"].get("tier"),
            ),
        )

    def results(self, c: Connection, action: dict[str, Any]) -> None:
        total = action["data"]["receipt"]["pre_total"] + sum(
            x["amount"] for x in action["data"]["modifiers"]
        )
        action["data"]["result"].update(total=total, tier=tier(total))
        action["state"] = "awaiting_choices"
        self.game.request(c, action, int(action["actor_id"]), "actor_keep")

    def select_tag(
        self, c: Connection, state: GameState, action: dict[str, Any], selected: dict[str, Any]
    ) -> None:
        ref = ActorRef.model_validate(action["data"]["actor_basic"]["ref"])
        # Revalidate the actual proposal and Bond immediately before applying it.
        amount = rules.proposal(
            state,
            ref,
            ActorRef.model_validate(selected["ref"]),
            selected["controller"],
            profiles(c, self.store.campaign_id),
            selected["tag"],
            action["scene_id"],
            selected["direction"],
            selected["account"],
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
            self.results(c, action)

    def apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
    ) -> None:
        actor = self.validate(c, state, action)
        owner, kind = int(row["actor_id"]), row["kind"]
        body, meta = json.loads(row["body_json"]), action["data"]["actor_basic"]
        judge = meta["adjudicator_controller"]
        if kind == "tag_window":
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
                cast, actors = self.actors(c, state, int(action["channel_id"]), fresh=False)
                proposer = next(
                    (
                        x
                        for x in actors
                        if x.controller == owner and x.ref.token == answer.fields.get("as_actor")
                    ),
                    None,
                )
                if (
                    proposer is None
                    or set(answer.fields) != {"as_actor"}
                    or answer.flag is not None
                    or answer.member
                ):
                    raise ValueError("Choose one of your actual cast roles for this proposal")
                rules.proposal(
                    state,
                    actor.ref,
                    proposer.ref,
                    owner,
                    profiles(c, self.store.campaign_id),
                    answer.denied[0],
                    action["scene_id"],
                    answer.number or 0,
                    answer.text,
                )
                action["data"].setdefault("tag_proposals", []).append(
                    dict(
                        id=row["id"],
                        controller=owner,
                        ref=proposer.ref.model_dump(mode="json"),
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
                    self.results(c, action)
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
            tag = next(x for x in state.handler_tags if x.id == body["tag"])
            if answer.options == ("embrace",):
                rules.embrace(state, actor.ref, tag.id, answer.denied)
            elif answer.options == ("reject",) and not answer.denied:
                tag.rejection_pending = True
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
            self.results(c, action)
        elif kind == "actor_keep" and owner == actor.controller:
            result = rules.keep(action["data"]["result"]["tier"], answer)
            if action["data"]["result"]["tier"] == "high":
                rules.add_tag(state, actor.ref, answer.text, tuple(action["data"]["participants"]))
            action["data"]["result"].update(result)
            self.game.request(c, action, judge, "handler_keep")
        elif kind == "handler_keep" and owner == judge:
            if answer.flag is None or not answer.text.strip():
                raise ValueError("The actual Director must answer whether it is enough and explain")
            action["data"]["result"].update(enough=answer.flag, ruling=answer.text)
            self.finish(c, state, action)
        else:
            raise ValueError("This actual-role response is unavailable or belongs to another role")

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        state = load_state(c, self.store.campaign_id)
        actor = self.validate(c, state, action)
        cast, actual = self.actors(c, state, int(action["channel_id"]), fresh=False)
        own = actor.controller == viewer.user_id
        selected = action["data"].get("tag_candidate")
        proposals = action["data"].get("tag_proposals", [])
        return dict(row) | {
            "actor_basic": True,
            "body": json.loads(row["body_json"]),
            "play": action["data"]["play"],
            "result": action["data"]["result"],
            "actor": actor.controller,
            "own": {
                "girl": None,
                "assets": [],
                "identities": [x.model_dump(mode="json") for x in actor.identities],
            }
            if own
            else None,
            "tags": [
                x.model_dump(mode="json")
                for x in state.handler_tags
                if own or viewer.user_id in x.observers
            ],
            "roles": [
                {"token": x.ref.token, "label": x.label}
                for x in actual
                if x.controller == viewer.user_id and x.rules in ("girl_frame", "npc", "director")
            ],
            "proposals": [
                {
                    "id": x["id"],
                    "label": next(t.label for t in state.handler_tags if t.id == x["tag"]),
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
