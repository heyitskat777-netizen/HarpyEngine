"""Owned eye-contact choices and a Tag from a broken original promise."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_harpy_advancements import MANIC_PIXIE
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import advancement_source, scene_harpy
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_gaze"
CHOICES = {
    "hands": "Take the Harpy’s hands",
    "promise": "Make a promise",
    "focus": "Lose track of everything else",
    "keep": "Keep Your Head",
}


class Gaze(Model):
    event: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    advancement: str
    target: ActorRef
    target_controller: int
    account: str
    choices: tuple[str, ...] = ()
    reply: str | None = None
    promise: str | None = None
    response: str | None = None
    broken: str | None = None
    tagged: str | None = None
    keep_action: str | None = None
    keep_binding: str | None = None
    keep_event: str | None = None
    enough: bool | None = None
    void_event: str | None = None
    void_asset: str | None = None
    void_work: str | None = None


def records(state: GameState) -> tuple[Gaze, ...]:
    return tuple(Gaze.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class GazeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(MANIC_PIXIE)

    def _targets(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        source: ActorView,
    ) -> dict[str, ActorView]:
        bound = profiles(c, self.store.campaign_id)
        result = {}
        for role in cast.roles:
            if role.actor.kind != "pilot":
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                girl.alive
                and girl.rules == "girl_frame"
                and girl.controller == role.controller
                and girl.controller != source.controller
                and girl.offstage_source is None
                and girl.cell == source.cell
                and girl.inside_frame is False
            ):
                result[girl.ref.token] = girl
        return result

    def targets(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            source, _ = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, MANIC_PIXIE)
            return dict(
                revision=state.revision,
                targets={
                    key: target.label
                    for key, target in self._targets(c, state, cast, source).items()
                },
            )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_gaze_choice",
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._gate(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    @staticmethod
    def _put(state: GameState, case: Gaze) -> None:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.event)]
        state.facts.append(dict(kind=KIND, id=case.event, body=case.model_dump_json()))

    def _persist(
        self,
        c: Connection,
        state: GameState,
        case: Gaze,
        event: str,
        viewer: GuildViewer,
        key: str,
        step: str,
    ) -> dict[str, Any]:
        self._put(state, case)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.harpy_gaze_" + step,
            state,
            event_id=event,
            source=case.event,
        )
        return dict(id=case.event, event=event)

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError("Reopen the actual gaze and describe the encounter")
            cast = _cast(self.game, c, state, channel)
            source, receipt = scene_harpy(
                self.game, c, state, viewer.user_id, cast, actor, MANIC_PIXIE
            )
            actual = self._targets(c, state, cast, source).get(target)
            if actual is None or any(
                x.harpy == actor and x.target == actual.ref and not x.response
                for x in records(state)
            ):
                raise WorkflowError("Use the actual present girl and original gaze")
            event = str(uuid4())
            case = Gaze(
                event=event,
                scene=cast.id,
                channel=channel,
                harpy=actor,
                controller=source.controller,
                advancement=receipt,
                target=actual.ref,
                target_controller=actual.controller,
                account=account.strip(),
            )
            return self._persist(c, state, case, event, viewer, key, "offered")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                target=target,
                account=account,
            ),
            operation,
        )

    def _step(self, state: GameState, case: Gaze, viewer: GuildViewer) -> str | None:
        if viewer.user_id != case.target_controller and not (
            viewer.user_id == case.controller and case.broken and not case.tagged
        ):
            return None
        original = state.sheets.get(case.target.entity)
        if original is None or original.character_id != case.target.incarnation:
            return None
        if viewer.user_id == case.target_controller:
            if not case.response:
                return "choose"
            if "keep" in case.choices:
                if not case.keep_action:
                    return "keep"
                if case.enough is False and not case.void_event:
                    return "void"
            return "break" if case.promise and not case.broken else None
        return "tag"

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[Gaze, str], ...]:
        pending = tuple((x, step) for x in records(state) if (step := self._step(state, x, viewer)))
        if pending:
            try:
                self._gate(c, viewer)
            except (WorkflowError, ValueError):
                return ()
        return pending

    def _case(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Gaze, str]:
        case = next((x for x in records(state) if x.event == identity), None)
        step = self._step(state, case, viewer) if case else None
        if case is None or step is None:
            raise WorkflowError("This private original gaze decision is unavailable")
        history = t.m2["m2_state_history"]

        def receipt(event: str, kind: str, author: int) -> Gaze | None:
            raw = c.scalar(
                sa.select(history.c.body_json)
                .join(t.events, t.events.c.id == history.c.event_id)
                .where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.harpy_gaze_" + kind,
                    t.events.c.actor_id == str(author),
                )
            )
            return (
                next(
                    (x for x in records(GameState.model_validate_json(raw)) if x.event == identity),
                    None,
                )
                if raw
                else None
            )

        chosen = case.model_copy(
            update=dict(
                keep_action=None,
                keep_binding=None,
                keep_event=None,
                enough=None,
                void_event=None,
                void_asset=None,
                void_work=None,
            )
        )
        original = chosen.model_copy(
            update=dict(
                choices=(), reply=None, promise=None, response=None, broken=None, tagged=None
            )
        )
        if (
            receipt(case.event, "offered", case.controller) != original
            or (
                case.response
                and receipt(case.response, "choose", case.target_controller)
                != chosen.model_copy(update=dict(broken=None, tagged=None))
            )
            or (
                case.broken
                and receipt(case.broken, "break", case.target_controller)
                != chosen.model_copy(update=dict(tagged=None))
            )
        ):
            raise WorkflowError("Recover the actual original gaze and promise receipts")
        return case, step

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._case(c, state, viewer, identity)
            result = dict(
                revision=state.revision,
                step=step,
                account=case.account,
                promise=case.promise,
                channel=case.channel,
            )
            if step == "void":
                result["assets"] = self._eligible_void(c, state, case)
            return result

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        choices: tuple[str, ...] = (),
        account: str = "",
        promise: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            case, expected = self._case(c, state, viewer, identity)
            if state.revision != revision or step != expected:
                raise WorkflowError("Reopen the actual original choice")
            event = str(uuid4())
            if step == "choose":
                cast = _cast(self.game, c, state, case.channel)
                source, receipt = scene_harpy(
                    self.game,
                    c,
                    state,
                    case.controller,
                    cast,
                    case.harpy,
                    MANIC_PIXIE,
                )
                if (
                    len(set(choices)) != 2
                    or len(choices) != 2
                    or not set(choices) <= set(CHOICES)
                    or ("promise" in choices) != bool(promise.strip())
                    or not 0 < len(account.strip()) <= 1200
                    or len(promise.strip()) > 1200
                    or cast.id != case.scene
                    or receipt != case.advancement
                    or case.target.token not in self._targets(c, state, cast, source)
                ):
                    raise WorkflowError(
                        "Make two actual original gaze choices with the owned consequences"
                    )
                updated = case.model_copy(
                    update=dict(
                        choices=choices,
                        reply=account.strip(),
                        promise=promise.strip() or None,
                        response=event,
                    )
                )
            elif step == "void" and not promise:
                updated = self._gain_void(c, state, case, choices, account, event)
            elif step == "break" and not (choices or account or promise):
                updated = case.model_copy(update=dict(broken=event))
            elif step == "tag" and not choices and not promise and 0 < len(account.strip()) <= 1200:
                harpy = resolve(
                    state,
                    case.harpy,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if (
                    not harpy.alive
                    or harpy.controller != case.controller
                    or advancement_source(
                        self.game,
                        c,
                        state,
                        case.harpy,
                        case.controller,
                        MANIC_PIXIE,
                    )
                    != case.advancement
                ):
                    raise WorkflowError(
                        "Use the original living Harpy that heard the broken promise"
                    )
                state = give_tag(
                    state,
                    case.target,
                    case.harpy,
                    account.strip(),
                    event,
                    "gaze:" + identity,
                    tuple(sorted({case.controller, case.target_controller})),
                )
                updated = case.model_copy(update=dict(tagged=event))
            else:
                raise WorkflowError("Use the original owned response to this gaze or promise")
            result = self._persist(c, state, updated, event, viewer, key, step)
            if step == "void" and updated.void_work:
                self._materialize_void(c, updated, event)
            return result

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                choices=choices,
                account=account,
                promise=promise,
            ),
            operation,
        )

    def _eligible_void(self, c: Connection, state: GameState, case: Gaze) -> dict[str, str]:
        girl = resolve(
            state, case.target, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        return {
            x.id: x.name
            for x in effective_assets(state, girl.ref)
            if not x.void and (x.family == "girl" or girl.piloting is True)
        }

    def _gain_void(
        self,
        c: Connection,
        state: GameState,
        case: Gaze,
        choices: tuple[str, ...],
        account: str,
        event: str,
    ) -> Gaze:
        from girlframe.engine.m3_void import FINAL

        if (
            case.enough is not False
            or not case.keep_event
            or not case.keep_action
            or len(choices) != 1
            or choices[0] not in self._eligible_void(c, state, case)
            or not 0 < len(account.strip()) <= 1200
            or any(x.actor == case.target and x.stage not in FINAL for x in state.void_thresholds)
        ):
            raise WorkflowError(
                "Choose the actual ordinary Void gain from the failed Keep Your Head"
            )
        action = self.game.action(c, case.keep_action)
        if (
            action["state"] != "complete"
            or action["data"].get("harpy_gaze_keep", {}).get("case") != case.event
            or action["data"]["result"].get("enough") is not False
        ):
            raise WorkflowError("Recover the actual failed original Play before applying Void")
        girl = resolve(
            state, case.target, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        selected = choices[0]
        family = next(x.family for x in state.sheets[girl.ref.entity].assets if x.id == selected)
        updated, effects = alter(
            state,
            girl.ref,
            selected,
            account.strip(),
            action["id"],
            event,
            piloting=girl.piloting is True,
        )
        for field in GameState.model_fields:
            setattr(state, field, getattr(updated, field))
        applied = any(x.id == selected and x.void for x in effective_assets(state, girl.ref))
        work = None
        if applied and any(
            x.kind == f"{family}_void_threshold"
            or family == "frame"
            and x.kind == "mockingbird_resist"
            for x in effects
        ):
            work = f"{case.event}:gaze:void:{family}"
        return case.model_copy(
            update=dict(
                void_asset=selected if applied else None,
                void_event=event,
                void_work=work,
            )
        )

    def _materialize_void(self, c: Connection, case: Gaze, event: str) -> None:
        assert case.void_work is not None
        related(
            c,
            self.store,
            dict(campaign_id=self.store.campaign_id, scene_id=case.scene),
            case.void_work,
            case.target_controller,
            case.target_controller,
            "void_threshold",
            dict(
                owner=case.target.model_dump(mode="json"),
                character=case.target.incarnation,
                source_action=None,
                source_pdf=19,
                reason="harpy_gaze",
                case=case.event,
                details=dict(family=case.void_work.rsplit(":", 1)[-1]),
            ),
            event,
        )


def prepare_keep(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work:
        return None
    initial = next((x for x in records(state) if x.event == prepared.source_work), None)
    if initial is None:
        return None
    service = GazeService(game)
    service._gate(c, viewer)
    case, step = service._case(c, state, viewer, initial.event)
    if (
        step != "keep"
        or prepared.play != "keep_your_head"
        or prepared.parent
        or prepared.target
        or prepared.target_actor
        or prepared.order_id
        or prepared.witnessed
        or channel != case.channel
    ):
        raise WorkflowError("Use this exact original Girl and her actual Keep Your Head choice")
    cast = _cast(game, c, state, channel)
    gm, appointment = MedicalService(game.store)._handler(c)
    source, advancement = scene_harpy(
        game,
        c,
        state,
        case.controller,
        cast,
        case.harpy,
        MANIC_PIXIE,
    )
    if (
        cast.id != case.scene
        or cast.facilitator != gm
        or advancement != case.advancement
        or case.target.token not in service._targets(c, state, cast, source)
    ):
        raise WorkflowError("Recover the actual original gaze and adjudicator")
    return dict(
        case=case.event,
        actor=case.target.model_dump(mode="json"),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        gm=gm,
        appointment=appointment,
        audience=sorted({gm, case.controller, case.target_controller}),
    )


def bind_keep(state: GameState, scope: dict[str, Any], identity: str, event: str) -> None:
    case = next(x for x in records(state) if x.event == scope["case"])
    GazeService._put(state, case.model_copy(update=dict(keep_action=identity, keep_binding=event)))


def validate_keep(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> Gaze:
    scope = action["data"]["harpy_gaze_keep"]
    case = next((x for x in records(state) if x.event == scope["case"]), None)
    if (
        case is None
        or case.keep_action != action["id"]
        or case.keep_binding is None
        or "keep" not in case.choices
    ):
        raise WorkflowError("Recover the original gaze-bound Play")
    cast = _cast(game, c, state, case.channel)
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == case.keep_binding,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.play_confirmed",
            t.events.c.actor_id == case.target.entity,
        )
    )
    expected = sorted({scope["gm"], case.controller, case.target_controller})
    if (
        raw is None
        or case not in records(GameState.model_validate_json(raw))
        or case.target.model_dump(mode="json") != scope["actor"]
        or action["actor_id"] != case.target.entity
        or action["scene_id"] != case.scene
        or fingerprint(cast) != scope["cast_sha256"]
        or MedicalService(game.store)._handler(c) != (scope["gm"], scope["appointment"])
        or any(action["data"].get(k) != expected for k in ("private_audience", "participants"))
    ):
        raise WorkflowError("Recover the actual original gaze receipt and private source table")
    return case


def finish_keep(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    state = load_state(c, game.store.campaign_id)
    case = validate_keep(game, c, state, action)
    enough = action["data"]["result"].get("enough")
    if type(enough) is not bool or not action["data"].get("receipt"):
        raise WorkflowError("Apply the original human ruling and actual saved roll first")
    recorded = str(uuid4())
    updated = case.model_copy(update=dict(keep_event=recorded, enough=enough))
    GazeService._put(state, updated)
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        viewer.user_id,
        key,
        "m3.harpy_gaze_keep_resolved",
        state,
        event_id=recorded,
        event_index=index + 1 if index is not None else 0,
        source=case.event,
        action_id=action["id"],
        source_event=event,
    )


def prove_void(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    case = next((x for x in records(state) if x.event == body.get("case")), None)
    if (
        case is None
        or case.target != actor
        or case.enough is not False
        or not case.keep_action
        or case.void_event != row["event_id"]
        or case.void_work != row["id"]
        or case.scene != row["scene_id"]
        or case.void_asset is None
    ):
        raise WorkflowError("Recover the actual failed gaze Play and original owned Void gain")
    action = game.action(c, case.keep_action)
    marker = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == case.void_event,
        )
    ).first()
    if (
        action["state"] != "complete"
        or action["data"].get("harpy_gaze_keep", {}).get("case") != case.event
        or action["data"]["result"].get("enough") is not False
        or not action["data"].get("receipt")
        or not marker
        or tuple(marker) != ("m3.harpy_gaze_void", actor.entity)
    ):
        raise WorkflowError("Recover the original failure and owned action receipt")


def void_audience(
    game: GameService,
    c: Connection,
    state: GameState,
    body: dict[str, Any],
) -> list[int]:
    case = next((x for x in records(state) if x.event == body.get("case")), None)
    if case is None or case.keep_action is None:
        raise WorkflowError("Recover the original private gaze consequence")
    scope = game.action(c, case.keep_action)["data"].get("harpy_gaze_keep")
    if (
        not scope
        or scope.get("case") != case.event
        or MedicalService(game.store)._handler(c) != (scope["gm"], scope["appointment"])
    ):
        raise WorkflowError("Recover the actual original human GM appointment")
    return sorted({case.target_controller, scope["gm"]})
