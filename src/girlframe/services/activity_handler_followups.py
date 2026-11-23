"""Activity forms for the native continuations of three Handler signature Plays."""

import json
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_advocate_alone, m3_frantic_breakdown
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import DRESS_RULE, Effect
from girlframe.services.activity_handler_signatures import ActivitySignatureChoices
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_advocate_alone import AdvocateAloneService
from girlframe.services.m3_advocate_empathy import CHOICE, REWARDS
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ActivityHandlerFollowups:
    def __init__(self, session: DirectorSessionService):
        self.session = session
        self.store = session.store
        self.advocate = AdvocateAloneService(self.store, session.game)
        self.frantic = FranticBreakdownService(self.store, session.game)
        self.dress = HandlerPlayService(self.store)
        self.signatures = ActivitySignatureChoices(session)

    def _matches(
        self, c: Connection, viewer: GuildViewer, scene: str, kind: str, identity: str
    ) -> bool:
        self.session.observer._scene(c, scene, viewer)
        state = load_state(c, self.store.campaign_id)
        if kind == "advocate":
            return any(
                x.id == identity and x.scene == scene for x in m3_advocate_alone.records(state)
            )
        if kind == "frantic":
            return any(
                x.id == identity and x.scene == scene for x in m3_frantic_breakdown.records(state)
            )
        return any(
            x.id == identity
            and x.clause == DRESS_RULE
            and x.scope.scene_id == scene
            and x.chooser_controller == viewer.user_id
            for x in state.handler_plays
        )

    def _order_choice(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == self.store.campaign_id,
                    choices.c.id == identity,
                    choices.c.actor_id == str(viewer.user_id),
                    choices.c.kind.in_(("order_response", CHOICE)),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This private Order choice belongs to its original controller.")
        return dict(row)

    def read(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.session.observer._scene(c, scene, viewer)
            state = load_state(c, self.store.campaign_id)
            conversations = [
                x
                for x in m3_advocate_alone.records(state)
                if x.scene == scene and str(viewer.user_id) in (x.handler.entity, x.girl.entity)
            ]
            private = {x.id for x in conversations}
            breakdowns = {x.id for x in m3_frantic_breakdown.records(state) if x.scene == scene}
            advocate = [x for x, _ in self.advocate._tasks(c, viewer, state) if x in private]
            frantic = [x["id"] for x in self.frantic._tasks(c, viewer) if x["id"] in breakdowns]
            dress = [
                (x.id, x.targets[0])
                for x in state.handler_plays
                if x.scope.scene_id == scene
                and x.clause == DRESS_RULE
                and x.chooser_controller == viewer.user_id
                and x.state == "pending"
            ]
            orders = {x.effect.order for x in conversations if x.effect}
            order_rows = t.m2["m2_orders"]
            choices = []
            for item in self.session.game.pending_choices(c, viewer):
                if item["kind"] not in ("order_response", CHOICE):
                    continue
                action = self.session.game.action(c, item["action_id"])
                order_id = action["data"].get("order_id")
                if order_id in orders:
                    raw = c.scalar(
                        sa.select(order_rows.c.body_json).where(
                            order_rows.c.campaign_id == self.store.campaign_id,
                            order_rows.c.id == order_id,
                        )
                    )
                    if raw is None:
                        continue
                    choices.append(
                        dict(
                            id=item["id"],
                            revision=item["revision"],
                            kind=item["kind"],
                            order=json.loads(raw)["text"],
                        )
                    )
        return {
            "advocate": [self.advocate.get(viewer, x) | {"id": x} for x in advocate],
            "frantic": [self.frantic.get(viewer, x) for x in frantic],
            "dress": [
                dict(id=x, target=target.model_dump(mode="json"), revision=state.revision)
                for x, target in dress
            ],
            "orders": choices,
            "signatures": self.signatures.read(viewer, scene),
        }

    def write(
        self, viewer: GuildViewer, key: str, scene: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        operation, identity, expected = data.get("action"), data.get("id"), data.get("revision")
        if (
            not isinstance(identity, str)
            or type(expected) is not int
            or not isinstance(operation, str)
        ):
            raise ValueError("Choose original signature work and its current revision.")
        fields = {"action", "id", "revision"}
        extras = {
            "advocate-answer": {"text"},
            "advocate-issue": {"message", "tag"},
            "frantic-choose": {"options", "office", "moderate"},
            "frantic-discover": {"text"},
            "dress-submit": {"text", "tag", "target"},
            "private-order": {"choice", "text", "tag"},
            "signature-response": {"answer"},
            "signature-child": {"sheet_revision", "text", "heat", "witnessed"},
            "signature-direct-order": {"text", "target"},
            "hunt-declare": {"attacking_asset", "target_asset", "text"},
            "hunt-confirm": {"opening", "reach", "outside_permission", "indirect", "text"},
            "hunt-roll": {"sheet_revision", "heat", "piloting"},
            "conditioning-order": {"phrase", "text", "target", "counterpart", "actor"},
            "conditioning-leave": {"target"},
        }
        if operation not in extras or data.keys() != fields | extras[operation]:
            raise ValueError("Complete the printed signature fields.")
        for name in ("text", "message", "tag"):
            if name in data and (
                not isinstance(data[name], str)
                or len(data[name]) > (120 if name == "tag" else 1200)
            ):
                raise ValueError("Use bounded native text.")
        kind = operation.partition("-")[0]

        if operation == "hunt-declare":
            if not all(isinstance(data[item], str) for item in ("attacking_asset", "target_asset")):
                raise ValueError("Choose actual Hunt Assets.")
            return self.signatures.hunt_declare(
                viewer,
                key,
                scene,
                identity,
                expected,
                data["attacking_asset"],
                data["target_asset"],
                data["text"],
            )
        if operation in ("hunt-confirm", "hunt-roll"):
            if operation == "hunt-confirm" and not all(
                type(data[name]) is bool
                for name in ("opening", "reach", "outside_permission", "indirect")
            ):
                raise ValueError("Confirm the printed Hunt battlefield facts.")
            if operation == "hunt-roll" and (
                type(data["sheet_revision"]) is not int
                or type(data["heat"]) is not int
                or type(data["piloting"]) is not bool
            ):
                raise ValueError("Confirm your original Hunt roll fields.")
            return self.signatures.hunt_continue(viewer, key, scene, identity, expected, data)
        if operation == "signature-response":
            answer = data["answer"]
            if not isinstance(answer, dict):
                raise ValueError("Choose the original decision fields.")
            member = answer.get("member")
            if (
                isinstance(member, str)
                and member.isascii()
                and member.isdecimal()
                and len(member) <= 20
            ):
                answer = answer | {"member": int(member)}
            return self.signatures.respond(
                viewer,
                key,
                scene,
                identity,
                expected,
                ChoiceAnswer.model_validate_json(json.dumps(answer)),
            )
        if operation == "signature-child":
            if (
                type(data["sheet_revision"]) is not int
                or type(data["heat"]) is not int
                or type(data["witnessed"]) is not bool
            ):
                raise ValueError("Confirm your own current sheet and the printed Play fields.")
            return self.signatures.child(
                viewer,
                key,
                scene,
                identity,
                expected,
                data["sheet_revision"],
                data["text"],
                data["heat"],
                data["witnessed"],
            )
        if operation == "signature-direct-order":
            target = data["target"]
            if (
                identity != scene
                or not isinstance(target, str)
                or not target.isascii()
                or not target.isdecimal()
            ):
                raise ValueError("Choose the original Girl in this scene.")
            return self.signatures.issue(
                viewer,
                key,
                scene,
                expected,
                int(target),
                None,
                data["text"],
                None,
                None,
            )
        if operation == "conditioning-leave":
            target = data["target"]
            if (
                identity != scene
                or not isinstance(target, str)
                or not target.isascii()
                or not target.isdecimal()
            ):
                raise ValueError("Choose the original Girl in this scene.")
            return self.signatures.leave(viewer, key, scene, expected, int(target))
        if operation == "conditioning-order":
            if identity != scene or not isinstance(data["phrase"], str):
                raise ValueError("Choose the original scene and a printed phrase.")
            target, other, actor = data["target"], data["counterpart"], data["actor"]
            if (
                not isinstance(target, str)
                or not target.isascii()
                or not target.isdecimal()
                or (
                    other is not None
                    and (not isinstance(other, str) or not other.isascii() or not other.isdecimal())
                )
                or (actor is not None and (not isinstance(actor, str) or len(actor) > 160))
            ):
                raise ValueError("Choose original actors in the scene.")
            return self.signatures.issue(
                viewer,
                key,
                scene,
                expected,
                int(target),
                data["phrase"],
                data["text"],
                int(other) if other is not None else None,
                actor,
            )
        if operation == "private-order":
            if not isinstance(data["choice"], str):
                raise ValueError("Choose a printed response.")

            def order_guard(c: Connection) -> None:
                self.session.observer._scene(c, scene, viewer)
                row = self._order_choice(c, viewer, identity)
                action = self.session.game.action(c, row["action_id"])
                state = load_state(c, self.store.campaign_id)
                source = next(
                    (
                        x
                        for x in m3_advocate_alone.records(state)
                        if x.scene == scene
                        and x.effect
                        and x.effect.order == action["data"].get("order_id")
                    ),
                    None,
                )
                if source is None or str(viewer.user_id) not in (
                    source.handler.entity,
                    source.girl.entity,
                ):
                    raise WorkflowError("Recover the original private Order and controller.")
                if row["kind"] == CHOICE and data["choice"] not in REWARDS:
                    raise WorkflowError("Choose an original Advocate response.")

            return self.session.game.respond(
                viewer,
                key,
                identity,
                expected,
                ChoiceAnswer(
                    options=(data["choice"],),
                    text=data["text"],
                    fields={"tag": data["tag"]},
                ),
                source_authorize=order_guard,
            )

        def guard(c: Connection) -> None:
            if not self._matches(c, viewer, scene, kind, identity):
                raise WorkflowError("HANDLER_PLAY_SOURCE: recover the original scene and role.")

        if operation == "advocate-issue":
            # Native Order startup performs an additional read before its guarded write.
            with self.store.engine.connect() as c:
                guard(c)
        with self.store.source_guard(guard):
            if operation == "advocate-answer":
                return self.advocate.answer(viewer, key, identity, expected, data["text"])
            if operation == "advocate-issue":
                return self.advocate.issue(
                    viewer, key, identity, expected, data["message"], data["tag"]
                )
            if operation == "frantic-discover":
                return self.frantic.discover(viewer, key, identity, expected, data["text"])
            if operation == "frantic-choose":
                options = data["options"]
                if not isinstance(options, list) or any(
                    not isinstance(x, str) or x not in m3_frantic_breakdown.OPTIONS for x in options
                ):
                    raise ValueError("Choose printed breakdown options.")
                return self.frantic.select(
                    viewer,
                    key,
                    identity,
                    expected,
                    tuple(cast(list[m3_frantic_breakdown.Option], options)),
                    office=ActorRef.model_validate(data["office"]) if data["office"] else None,
                    moderate=ActorRef.model_validate(data["moderate"])
                    if data["moderate"]
                    else None,
                )
            return self.dress.submit(
                viewer,
                key,
                identity,
                expected,
                "dress_them_down",
                Effect(
                    kind="dress_them_down",
                    account=data["text"],
                    tag=data["tag"],
                    target=ActorRef.model_validate(data["target"]),
                    dress_steps=("competency",),
                ),
            )
