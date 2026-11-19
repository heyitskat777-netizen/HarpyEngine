"""Private, source-owned Harpy intimacy and a genuine opportunity to escape."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import Field
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_harpy_bond_void import is_harpy
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_void import FINAL
from girlframe.engine.m3_void_state import VoidThreshold
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_flirt import conversation
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "harpy.harpy.sex-play"
KIND = "harpy_intimacy"


class Encounter(Model):
    id: str
    scene: str
    channel: int
    gm: int
    appointment: str
    harpy: ActorRef
    controller: int
    girl: ActorRef
    owner: int
    bond: int = Field(ge=0, le=2)
    frame: str | None = None
    phase: Literal["consent", "escape", "void", "rebirth", "threshold", "complete"] = "consent"
    consent: str | None = None
    action: str | None = None
    binding: str | None = None
    ruling: str | None = None
    escaped: bool | None = None
    void_event: str | None = None
    void_asset: str | None = None
    rebirth_event: str | None = None
    work: str | None = None
    kiss: str | None = None


def records(state: GameState) -> tuple[Encounter, ...]:
    return tuple(
        Encounter.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, case: Encounter) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)]
    state.facts.append(dict(kind=KIND, id=case.id, body=case.model_dump_json()))


class HarpyIntimacyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(RULE)

    def _where(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
    ) -> tuple[SceneCast, ActorView, tuple[int, str], dict[str, ActorView]]:
        cast = _cast(self.game, c, state, channel)
        current = MedicalService(self.store)._handler(c)
        bound = profiles(c, self.store.campaign_id)
        source = resolve(state, actor, bound, require_current_profile=False)
        if (
            not is_harpy(state, actor)
            or source.offstage_source
            or source.cell is None
            or source.custody not in (None, "free")
            or harpy(state, actor).body_incapacitated
            or is_helpless(state, actor)
            or cast.facilitator != current[0]
            or not any(x.actor == actor and x.controller == source.controller for x in cast.roles)
        ):
            raise WorkflowError("Recover the actual local Harpy and facilitator")
        people = {}
        for role in cast.roles:
            if role.actor.kind != "pilot" or role.controller == source.controller:
                continue
            try:
                target = resolve(state, role.actor, bound, require_current_profile=False)
                conversation(state, actor, target.ref)
            except ValueError:
                continue
            if (
                target.rules == "girl_frame"
                and target.controller == role.controller
                and not target.offstage_source
                and target.cell == source.cell
            ):
                people[target.ref.token] = target
        return cast, source, current, people

    def _source(
        self,
        c: Connection,
        state: GameState,
        case: Encounter,
    ) -> tuple[SceneCast, ActorView]:
        cast, source, actual, people = self._where(c, state, case.channel, case.harpy)
        girl = people.get(case.girl.token)
        if (
            girl is None
            or girl.controller != case.owner
            or source.controller != case.controller
            or cast.id != case.scene
            or actual != (case.gm, case.appointment)
        ):
            raise WorkflowError("Recover the original participants and actual private scene")
        if case.kiss:
            from girlframe.services.m3_harpy_kiss import prove_encounter

            prove_encounter(self.game, c, state, case)
        return cast, girl

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
                "m3.harpy_intimacy",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        case: Encounter,
        step: str,
        event: str,
        *,
        event_index: int = 0,
    ) -> dict[str, Any]:
        put(state, case)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.harpy_intimacy_" + step,
            state,
            event_id=event,
            event_index=event_index,
            encounter=case.id,
        )
        return dict(id=case.id, state=case.phase)

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            _, source, _, people = self._where(c, state, channel, actor)
            if source.controller != viewer.user_id:
                raise WorkflowError(
                    "Only the original actual Harpy may invite the other participant"
                )
            return dict(revision=state.revision, people={k: x.label for k, x in people.items()})

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, source, (gm, appointment), people = self._where(c, state, channel, actor)
            girl = people.get(target)
            if (
                state.revision != revision
                or source.controller != viewer.user_id
                or girl is None
                or any(
                    x.harpy == actor and x.girl == girl.ref and x.phase != "complete"
                    for x in records(state)
                )
            ):
                raise WorkflowError("Choose the actual original counterpart in the current scene")
            event = str(uuid4())
            case = Encounter(
                id=event,
                scene=cast.id,
                channel=channel,
                gm=gm,
                appointment=appointment,
                harpy=actor,
                controller=source.controller,
                girl=girl.ref,
                owner=girl.controller,
                bond=depth(state, actor, girl.ref),
                frame=girl.frame_instance,
            )
            return self._save(c, state, viewer, key, case, "offered", event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                target=target,
            ),
            operation,
        )

    def _step(self, case: Encounter, viewer: GuildViewer) -> str | None:
        if case.owner != viewer.user_id or case.phase in ("threshold", "complete"):
            return None
        if case.phase == "escape" and case.action is not None:
            return None
        return case.phase

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> tuple[Encounter, str]:
        case = next((x for x in records(state) if x.id == identity), None)
        step = self._step(case, viewer) if case else None
        if case is None or step is None:
            raise WorkflowError("This original private Harpy choice is unavailable")
        return case, step

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        pending = [
            (case.id, step)
            for case in records(state)
            if (step := self._step(case, viewer)) is not None
        ]
        if not pending:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        return tuple(pending)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._case(state, viewer, identity)
            _, girl = self._source(c, state, case)
            return dict(
                revision=state.revision,
                step=step,
                channel=case.channel,
                assets=_void_choices(state, girl) if step == "void" else {},
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        choice: str,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case, expected = self._case(state, viewer, identity)
            require_scene_clear(self.game, c, case.channel)
            if state.revision != revision or step != expected:
                raise WorkflowError("STALE_HARPY_CHOICE: reopen the original private decision")
            _, girl = self._source(c, state, case)
            event = str(uuid4())
            if step == "consent" and choice in ("accept", "decline"):
                case = case.model_copy(
                    update=dict(
                        consent=event if choice == "accept" else None,
                        phase="escape" if choice == "accept" else "complete",
                    )
                )
            elif step == "escape" and choice == "stay":
                state, case = _result(state, case, event, escaped=False)
            elif step == "escape" and choice == "withdraw":
                case = case.model_copy(update=dict(phase="complete"))
            elif step == "void":
                state, case = _gain(state, case, girl, choice, account, event)
            elif step == "rebirth" and choice == "begin":
                case = _begin_transformation(state, case, girl, event)
            else:
                raise WorkflowError("Use the original supported private response")
            saved = self._save(c, state, viewer, key, case, step, event)
            if case.void_event == event and case.work is not None:
                self._materialize(c, case, event, "harpy_intimacy", case.work.rsplit(":", 1)[-1])
            if case.rebirth_event == event and case.work is not None:
                self._materialize(c, case, event, "harpy_intimacy_rebirth", "girl")
            return saved

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, step=step, choice=choice, account=account),
            operation,
        )

    def _materialize(
        self,
        c: Connection,
        case: Encounter,
        event: str,
        reason: str,
        family: str,
    ) -> None:
        assert case.work is not None
        related(
            c,
            self.store,
            dict(campaign_id=self.store.campaign_id, scene_id=case.scene),
            case.work,
            case.owner,
            case.owner,
            "void_threshold",
            dict(
                owner=case.girl.model_dump(mode="json"),
                character=case.girl.incarnation,
                source_action=None,
                source_pdf=19,
                reason=reason,
                case=case.id,
                details=dict(family=family),
            ),
            event,
        )


def _void_choices(state: GameState, girl: ActorView) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if not x.void and (x.family == "girl" or girl.piloting is True)
    }


def _gain(
    state: GameState, case: Encounter, girl: ActorView, asset: str, account: str, event: str
) -> tuple[GameState, Encounter]:
    if (
        asset not in _void_choices(state, girl)
        or not 0 < len(account.strip()) <= 1200
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Choose the actual ordinary Void gain after the failed original escape")
    family = next(x.family for x in effective_assets(state, girl.ref) if x.id == asset)
    state, effects = alter(
        state,
        girl.ref,
        asset,
        account.strip(),
        case.action or case.id,
        event,
        piloting=girl.piloting is True,
    )
    work = (
        f"{case.id}:intimacy:void:{family}"
        if any(
            x.kind == f"{family}_void_threshold"
            or family == "frame"
            and x.kind == "mockingbird_resist"
            for x in effects
        )
        and any(x.id == asset and x.void for x in effective_assets(state, girl.ref))
        else None
    )
    return state, case.model_copy(
        update=dict(
            phase="threshold" if work else "complete", void_asset=asset, void_event=event, work=work
        )
    )


def _begin_transformation(
    state: GameState, case: Encounter, girl: ActorView, event: str
) -> Encounter:
    body = next((x for x in state.placements if x.actor == case.girl), None)
    if (
        case.bond != 2
        or not case.consent
        or case.escaped is not False
        or not case.frame
        or girl.frame_instance != case.frame
        or girl.inside_frame is None
        or girl.frame_scrapped
        or body is None
        or not body.vitals_active
        or body.incapacitated
        or body.frame_cell is None
        or body.frame_instance != case.frame
        or any(x.actor == girl.ref and x.stage not in FINAL for x in state.void_thresholds)
    ):
        raise WorkflowError("Recover the actual original Girl and her affected Frame")
    work = f"{case.id}:intimacy:apometanoia"
    state.void_thresholds.append(
        VoidThreshold(
            id="void:" + work,
            actor=girl.ref,
            frame_instance=case.frame,
            family="girl",
            source_event=event,
            source_works=(work,),
            source_action=case.action,
            sheet_json=state.sheets[girl.ref.entity].model_dump_json(),
            stage="questions" if girl.occupied_frame_instance == case.frame else "allured",
        )
    )
    return case.model_copy(update=dict(phase="threshold", rebirth_event=event, work=work))


def _result(
    state: GameState,
    case: Encounter,
    event: str,
    *,
    escaped: bool,
) -> tuple[GameState, Encounter]:
    if depth(state, case.harpy, case.girl) != case.bond:
        raise WorkflowError("Resolve the changed original Bond with the human GM")
    if case.bond < 2:
        state = change(state, case.harpy, case.girl, 1, event)
    phase = "complete" if escaped else "rebirth" if case.bond == 2 else "void"
    return state, case.model_copy(update=dict(phase=phase, ruling=event, escaped=escaped))


def prepare_keep(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    initial = next((x for x in records(state) if x.id == prepared.source_work), None)
    if initial is None:
        return None
    service = HarpyIntimacyService(game)
    service._gate(c, viewer)
    case, step = service._case(state, viewer, initial.id)
    if (
        step != "escape"
        or prepared.play != "keep_your_head"
        or prepared.parent
        or prepared.target
        or prepared.target_actor
        or prepared.order_id
        or prepared.witnessed
        or case.channel != channel
    ):
        raise WorkflowError("Use the original Girl’s actual private escape Play")
    cast, _ = service._source(c, state, case)
    return dict(
        kind=KIND,
        case=case.id,
        actor=case.girl.model_dump(mode="json"),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        gm=case.gm,
        appointment=case.appointment,
        audience=sorted({case.gm, case.controller, case.owner}),
    )


def bind_keep(state: GameState, scope: dict[str, Any], identity: str, event: str) -> None:
    case = next(x for x in records(state) if x.id == scope["case"])
    put(state, case.model_copy(update=dict(action=identity, binding=event)))


def validate_keep(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> Encounter:
    scope = action["data"]["harpy_gaze_keep"]
    case = next((x for x in records(state) if x.id == scope["case"]), None)
    if (
        case is None
        or not case.consent
        or case.phase != "escape"
        or case.action != action["id"]
        or not case.binding
    ):
        raise WorkflowError("Recover the original consent and actual escape Play")
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == case.binding,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.play_confirmed",
            t.events.c.actor_id == case.girl.entity,
        )
    )
    cast, _ = HarpyIntimacyService(game)._source(c, state, case)
    if (
        raw is None
        or case not in records(GameState.model_validate_json(raw))
        or action["actor_id"] != case.girl.entity
        or action["scene_id"] != case.scene
        or scope["actor"] != case.girl.model_dump(mode="json")
        or scope["gm"] != case.gm
        or scope["appointment"] != case.appointment
        or scope["cast_sha256"] != fingerprint(cast)
        or any(
            action["data"].get(x) != sorted({case.gm, case.controller, case.owner})
            for x in ("private_audience", "participants")
        )
    ):
        raise WorkflowError("Recover the original private escape scope and adjudicator")
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
    escaped = action["data"]["result"].get("enough")
    if type(escaped) is not bool or not action["data"].get("receipt"):
        raise WorkflowError("Resolve the actual original escape roll and human ruling")
    state, marked = _result(state, case, event, escaped=escaped)
    previous = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    HarpyIntimacyService(game)._save(
        c,
        state,
        viewer,
        key,
        marked,
        "escape_resolved",
        str(uuid4()),
        event_index=previous + 1 if previous is not None else 0,
    )


def prove_void(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    case = next((x for x in records(state) if x.id == body.get("case")), None)
    rebirth = body.get("reason") == "harpy_intimacy_rebirth"
    if (
        case is None
        or not case.consent
        or case.girl != actor
        or case.escaped is not False
        or (case.bond == 2) != rebirth
        or (case.rebirth_event if rebirth else case.void_event) != row["event_id"]
        or case.work != row["id"]
        or case.scene != row["scene_id"]
        or (
            rebirth
            and not any(
                x.actor == actor and x.frame_instance == case.frame and row["id"] in x.source_works
                for x in state.void_thresholds
            )
        )
    ):
        raise WorkflowError("Recover the actual original failed escape and transformation source")
    event_kind = c.scalar(
        sa.select(t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == row["event_id"],
            t.events.c.actor_id == actor.entity,
        )
    )
    if event_kind != ("m3.harpy_intimacy_rebirth" if rebirth else "m3.harpy_intimacy_void"):
        raise WorkflowError("Recover the actual original response event")


def void_audience(
    game: GameService,
    c: Connection,
    state: GameState,
    body: dict[str, Any],
) -> tuple[int, ...]:
    case = next((x for x in records(state) if x.id == body.get("case")), None)
    if case is None:
        return ()
    current = MedicalService(game.store)._handler(c)
    return (case.owner, case.gm) if current == (case.gm, case.appointment) else (case.owner,)


def settle(
    game: GameService,
    c: Connection,
    body: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    state = load_state(c, game.store.campaign_id)
    case = next((x for x in records(state) if x.id == body.get("case")), None)
    if case is None or case.phase != "threshold":
        return
    put(state, case.model_copy(update=dict(phase="complete")))
    previous = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        viewer.user_id if viewer else case.owner,
        key,
        "m3.harpy_intimacy_settled",
        state,
        event_id=str(uuid4()),
        event_index=previous + 1 if previous is not None else 0,
        encounter=case.id,
        source_event=event,
    )
