"""Private native Conditioning proposals and original-participant confirmation."""

from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_conditioning as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, is_helpless
from girlframe.engine.m3_actor_state import ActorView, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.situational_conditioning"
Step = Literal["consent", "roll", "choose", "confirm", "withdraw"]
END = ("complete", "withdrawn")


class ConditioningService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.cast = CastService(ActorService(MissionService(self.store)))
        self.access = Access(self.store)

    def enabled(self) -> bool:
        approval = self.store.policy.m3_approval
        registry = self.access.registry
        if approval is None or registry is None or "plays" not in approval.subsystems:
            return False
        return approval.registry_sha256 == digest(registry) and registry.entry(rules.RULE).verified

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        self.access.authorize(c, viewer, "plays")
        if not self.enabled():
            raise WorkflowError("Conditioning requires its scoped rules approval.")

    def _duplicates(self) -> bool:
        return ChoiceEngine(self.game).duplicate_labels()

    def _scope(
        self, c: Connection, state: GameState, channel: int
    ) -> tuple[SceneCast, tuple[ActorView, ActorView]]:
        cast, _ = self.cast._current(c, state, channel)
        bindings = profiles(c, self.store.campaign_id)
        refs = [(x.actor, x.controller) for x in cast.roles]
        if len(refs) != 2 or (
            cast.facilitator is not None and cast.facilitator not in {uid for _, uid in refs}
        ):
            raise WorkflowError("Use the actual private scene with only the two participants.")
        result = []
        for ref, controller in refs:
            try:
                actor = resolve(state, ref, bindings, require_current_profile=False)
            except ValueError:
                raise WorkflowError(
                    "Recover both original participants and their current bodies."
                ) from None
            member = HandlerService(self.store)._member(c, controller)
            revealed_npc = ref.kind != "npc" or bool(
                state.world and any(x.id == ref.entity and x.revealed for x in state.world.npcs)
            )
            if (
                not member
                or actor.controller != controller
                or not actor.alive
                or actor.rules not in ("girl_frame", "handler", "npc")
                or not revealed_npc
                or actor.inside_frame is True
                or actor.custody not in (None, "free")
                or actor.offstage_source
                or is_helpless(state, ref)
                or (ref.kind == "pilot" and state.sheets[ref.entity].medical_state != "fit")
            ):
                raise WorkflowError(
                    "Both original participants must be available to consent freely."
                )
            result.append(actor)
        first, second = result
        if (
            first.controller == second.controller
            or (first.cell is not None and second.cell is not None and first.cell != second.cell)
            or not any(x.rules == "girl_frame" for x in result)
        ):
            raise WorkflowError(
                "Use separate controllers and original participants in the same place."
            )
        return cast, (first, second)

    def _get(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> rules.Conditioning:
        value = rules.find(state, identity)
        if value is None or viewer.user_id not in (
            value.trainee_controller,
            value.trainer_controller,
        ):
            raise WorkflowError("This private request belongs to its original two participants.")
        original = rules.find(_history(c, self.game, value.offer), identity)
        if (
            original is None
            or original.event != value.offer
            or original.phase != "offered"
            or (
                original.scene,
                original.channel,
                original.source_cast,
                original.trainee,
                original.trainer,
                original.trainee_controller,
                original.trainer_controller,
            )
            != (
                value.scene,
                value.channel,
                value.source_cast,
                value.trainee,
                value.trainer,
                value.trainee_controller,
                value.trainer_controller,
            )
        ):
            raise WorkflowError("Recover the original private Conditioning offer.")
        return value

    def _current(self, c: Connection, state: GameState, value: rules.Conditioning) -> None:
        cast, actors = self._scope(c, state, value.channel)
        if (
            cast.id != value.scene
            or {x.source_event for x in cast.roles} != set(value.source_cast)
            or {(x.ref, x.controller) for x in actors}
            != {
                (value.trainee, value.trainee_controller),
                (value.trainer, value.trainer_controller),
            }
        ):
            raise WorkflowError("Reopen the original private scene before continuing.")
        require_scene_clear(self.game, c, value.channel)
        require_clear(self.game, c, value.channel)
        lock = self.game.lock(c, value.channel)
        if lock and lock["state"] != "released":
            raise WorkflowError("Finish the pending Play in this original scene.")

    @staticmethod
    def _owner(value: rules.Conditioning) -> int:
        return value.trainer_controller if value.phase == "choices" else value.trainee_controller

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast, actors = self._scope(c, state, channel)
            own = next((x for x in actors if x.controller == viewer.user_id), None)
            other = next((x for x in actors if x.controller != viewer.user_id), None)
            if own is None or other is None or other.rules != "girl_frame":
                raise WorkflowError("Only the actual trainer may invite the other participant.")
            return dict(
                revision=state.revision,
                scene=cast.id,
                cast=(cast.roles[0].source_event, cast.roles[1].source_event),
                trainee=other.label,
            )

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        channel: int,
        original_scene: str,
        original_cast: tuple[str, str],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast, actors = self._scope(c, state, channel)
            trainer = next((x for x in actors if x.controller == viewer.user_id), None)
            trainee = next((x for x in actors if x.controller != viewer.user_id), None)
            if (
                trainer is None
                or trainee is None
                or trainee.rules != "girl_frame"
                or expected != state.revision
                or cast.id != original_scene
                or tuple(x.source_event for x in cast.roles) != original_cast
                or any(
                    x.phase not in END and x.trainee == trainee.ref for x in rules.records(state)
                )
            ):
                raise WorkflowError(
                    "Reopen this original scene or resolve the existing Conditioning request."
                )
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Conditioning(
                id=identity,
                scene=cast.id,
                channel=channel,
                source_cast=(cast.roles[0].source_event, cast.roles[1].source_event),
                trainee=trainee.ref,
                trainer=trainer.ref,
                trainee_controller=trainee.controller,
                trainer_controller=trainer.controller,
                offer=event,
                event=event,
                phase="offered",
            )
            self._current(c, state, value)
            return self._save(c, viewer, key, state, value)

        return self.store._write(
            viewer,
            key,
            EVENT,
            dict(
                operation="invite",
                expected=expected,
                channel=channel,
                scene=original_scene,
                cast=original_cast,
            ),
            operation,
            authorize=lambda c: self._authorize(c, viewer),
            auto_audit=False,
        )

    def _save(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        state: GameState,
        value: rules.Conditioning,
    ) -> dict[str, Any]:
        rules.put(state, value)
        self.game.event(
            c,
            viewer.user_id,
            key,
            EVENT,
            state,
            event_id=value.event,
            conditioning_id=value.id,
        )
        return dict(id=value.id, phase=value.phase, event=value.event)

    def tasks(
        self, c: Connection, viewer: GuildViewer, state: GameState
    ) -> list[rules.Conditioning]:
        self.game.authorize(c, viewer, game=False)
        return [
            self._get(c, state, viewer, x.id)
            for x in rules.records(state)
            if x.phase not in END and viewer.user_id in (x.trainee_controller, x.trainer_controller)
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = self._get(c, state, viewer, identity)
            basic: dict[str, Any] = dict(
                id=value.id,
                phase=value.phase,
                revision=state.revision,
                owner=self._owner(value),
                can_act=viewer.user_id == self._owner(value) and value.phase not in END,
                remaining=(value.roll.count - len(value.choices)) if value.roll else None,
                roll=dict(total=value.roll.total, faces=value.roll.faces) if value.roll else None,
                resources=None,
            )
            if value.phase in ("choices", "confirm") and basic["can_act"]:
                try:
                    self._current(c, state, value)
                    interim = rules.preview(
                        state, value, value.event, allow_duplicates=self._duplicates()
                    )
                except (WorkflowError, ValueError) as exc:
                    return basic | dict(blocked=str(exc))
                sheet = interim.sheets[value.trainee.entity]
                bindings = profiles(c, self.store.campaign_id)
                basic["resources"] = dict(
                    identities=tuple(
                        (x.id, x.name) for x in sheet.identities if rules.removable(sheet, x)
                    ),
                    tags=tuple((x.id, x.label) for x in sheet.tags if not x.rejection_pending),
                    assets=tuple((x.id, x.name) for x in sheet.assets if rules.excisable(sheet, x)),
                    bonds=tuple(
                        (x, resolve(state, x, bindings, require_current_profile=False).label)
                        for x in value.shared_bonds
                        if depth(interim, value.trainee, x) > 0
                    ),
                    vacancies=4 - rules.ordinary_count(sheet),
                )
                if value.phase == "confirm":
                    basic["choices"] = tuple((x.kind, x.account) for x in value.choices)
                    before = state.sheets[value.trainee.entity]
                    changes: list[tuple[str, str, str]] = []
                    for label, prior, after in (
                        (
                            "Identity",
                            {x.id: x.name for x in before.identities},
                            {x.id: x.name for x in sheet.identities},
                        ),
                        (
                            "Tag",
                            {x.id: x.label for x in before.tags},
                            {x.id: x.label for x in sheet.tags},
                        ),
                        (
                            "Girl Asset",
                            {x.id: x.name for x in before.assets},
                            {x.id: x.name for x in sheet.assets},
                        ),
                    ):
                        changes.extend(
                            (label, action, names[key])
                            for action, names, other in (
                                ("Remove", prior, after),
                                ("Add", after, prior),
                            )
                            for key in names
                            if key not in other
                        )
                    basic["changes"] = changes
            return basic

    def advance(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        step: Step,
        *,
        choice: rules.Choice | None = None,
        account: str | None = None,
        new_identity: rules.IdentityChoice | None = None,
        share_bonds: bool = False,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            if step == "withdraw":
                self.game.authorize(c, viewer, game=False)
            else:
                self._authorize(c, viewer)
            self._get(c, load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = self._get(c, state, viewer, identity)
            if state.revision != expected or value.phase in END:
                raise WorkflowError(
                    "This choice is stale. Reopen the original Conditioning request."
                )
            event = str(uuid4())
            if step == "withdraw":
                return self._save(
                    c,
                    viewer,
                    key,
                    state,
                    value.model_copy(update=dict(phase="withdrawn", event=event)),
                )
            self.game.unpaused(c)
            self._current(c, state, value)
            required = dict(
                consent="offered", roll="consented", choose="choices", confirm="confirm"
            )
            if viewer.user_id != self._owner(value) or value.phase != required[step]:
                raise WorkflowError(
                    "This choice belongs to the actual participant at the current step."
                )
            sheet = state.sheets[value.trainee.entity]
            update: dict[str, Any] = dict(event=event)
            if step == "consent":
                update.update(
                    phase="consented",
                    shared_bonds=rules.shareable_bonds(state, value) if share_bonds else (),
                )
            elif step == "roll":
                trainer_bonus: Literal[1, 2, 3] = (
                    1 if value.trainer.kind == "npc" else 2 if value.trainer.kind == "pilot" else 3
                )
                roll = rules.Roll(
                    faces=self.game.dice.roll(),
                    trainer_bonus=trainer_bonus,
                    identity_bonus=1 if len(sheet.identities) < 4 else 0,
                )
                update.update(phase="choices", roll=roll)
            elif step == "choose":
                if choice is None or value.roll is None:
                    raise WorkflowError(
                        "Choose one actual Conditioning effect from the saved roll."
                    )
                if isinstance(choice, rules.Embrace):
                    for selected in choice.choices:
                        tag = next((x for x in sheet.tags if x.id == selected.tag), None)
                        if tag is not None:
                            ChoiceEngine(self.game).prove_tag_setter(c, state, sheet.owner, tag)
                choices = (*value.choices, choice)
                if len(choices) > value.roll.count:
                    raise WorkflowError("The original roll has no more trainer choices.")
                update.update(
                    choices=choices,
                    phase="confirm" if len(choices) == value.roll.count else "choices",
                )
                rules.preview(
                    state,
                    value.model_copy(update=update),
                    event,
                    allow_duplicates=self._duplicates(),
                )
            else:
                if account is None:
                    raise WorkflowError("The original trainee supplies their own response.")
                update.update(
                    phase="complete", account=rules.text(account, 1200), low_identity=new_identity
                )
                state = rules.preview(
                    state,
                    value,
                    event,
                    allow_duplicates=self._duplicates(),
                    low_identity=new_identity,
                )
            return self._save(c, viewer, key, state, value.model_copy(update=update))

        try:
            return self.store._write(
                viewer,
                key,
                EVENT,
                dict(
                    id=identity,
                    expected=expected,
                    operation=step,
                    account=account,
                    choice=choice.model_dump(mode="json") if choice else None,
                    new_identity=new_identity.model_dump(mode="json") if new_identity else None,
                    share_bonds=share_bonds,
                ),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None
