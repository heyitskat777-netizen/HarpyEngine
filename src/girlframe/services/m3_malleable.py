"""Private original-giver forcing and finite human-authored NPC fact producers."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_malleable as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Malleable source")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _giver(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    actual = _native(game, c, state, actor)
    if not has_rule(state.sheets[actor.entity], rules.RULE, "STIM-BLISSED"):
        raise WorkflowError("Use the actual original native Malleable giver")
    return actual


def _npc(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        actor.kind != "npc"
        or actual.rules != "npc"
        or actual.offstage_source is not None
        or actual.custody is not None
        or actual.cell is None
    ):
        raise WorkflowError("Use the actual present ordinary NPC body")
    return actual


def _audit(game: GameService, c: Connection, event: str, kind: str, controller: int) -> None:
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if row is None or row.kind != kind or row.actor_id != str(controller):
        raise WorkflowError("Recover the original human-authored canonical fact")


def _alteration_subject(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    if actor.kind == "pilot":
        actual = _native(game, c, state, actor)
        if current_ref(state, actual.controller) != actor:
            raise WorkflowError("Use the actual affected player's current original character")
        return actual
    return _npc(game, c, state, actor)


def prove_alteration(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Alteration:
    value = _record(state, rules.Alteration, identity)
    born = _history(c, game, value.event)
    prefix = "m3.malleable_player" if value.subject.kind == "pilot" else "m3.malleable_npc"
    _audit(game, c, value.event, prefix + "_alteration", value.controller)
    actual = _alteration_subject(game, c, born, value.subject)
    if (
        value not in rules.records(born, rules.Alteration)
        or value.cast not in born.scene_casts
        or value.vessel != actual.vessel_id
        or value.controller != actual.controller
        or not value.account.strip()
        or not any(
            x.actor == value.subject and x.controller == value.controller for x in value.cast.roles
        )
    ):
        raise WorkflowError("Recover the actual NPC controller's original altered-state account")
    for end in rules.records(state, rules.AlterationEnd):
        if end.alteration != identity:
            continue
        _audit(game, c, end.event, prefix + "_alteration_end", end.controller)
        ended = _history(c, game, end.event)
        if (
            end not in rules.records(ended, rules.AlterationEnd)
            or _alteration_subject(game, c, ended, value.subject).controller != end.controller
        ):
            raise WorkflowError("Recover the actual current NPC controller's ending fact")
    return value


def _altered(
    game: GameService, c: Connection, state: GameState, recipient: ActorRef
) -> tuple[Literal["dose", "stim", "npc", "pilot"], str] | None:
    if recipient.kind == "pilot":
        from girlframe.engine import m3_dose_up as dose
        from girlframe.engine import m3_stim_sex as stim
        from girlframe.services.m3_dose_up import prove_tag
        from girlframe.services.m3_stim_sex import prove_drug_tag

        # A legitimately consumed presentation Tag does not end source physiology.
        # Its original drug record and original clock remain the only authority.
        for drug in dose.records(state, dose.DrugTag):
            if drug.target != recipient or dose.expired(state, drug.dose):
                continue
            prove_tag(game, c, state, int(recipient.entity), drug.tag)
            original = _history(c, game, drug.event)
            if (
                _native(game, c, original, recipient).vessel_id
                == _native(game, c, state, recipient).vessel_id
            ):
                return "dose", drug.id
        for sex_drug in stim.records(state, stim.Drug):
            if sex_drug.target == recipient and stim.active(state, sex_drug):
                if not isinstance(sex_drug.tag, TagState):
                    raise WorkflowError("Preserve the actual Pilot drug Tag type")
                prove_drug_tag(game, c, state, int(recipient.entity), sex_drug.tag)
                return "stim", sex_drug.id
    if recipient.kind == "npc":
        from girlframe.services.m3_npc_dose import active_drug

        npc_drug = active_drug(game, c, state, recipient)
        if npc_drug is not None:
            return "dose", npc_drug
        from girlframe.services.m3_stim_npc import active_drug as active_stim_drug

        npc_stim = active_stim_drug(game, c, state, recipient)
        if npc_stim is not None:
            return "stim", npc_stim
    if recipient.kind in ("pilot", "npc"):
        actual = _alteration_subject(game, c, state, recipient)
        for value in rules.records(state, rules.Alteration):
            if (
                value.subject == recipient
                and value.vessel == actual.vessel_id
                and not any(
                    x.alteration == value.id for x in rules.records(state, rules.AlterationEnd)
                )
            ):
                prove_alteration(game, c, state, value.id)
                return ("pilot" if recipient.kind == "pilot" else "npc"), value.id
    return None


def stage_birth(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    giver: ActorRef,
    recipient: ActorRef,
    tag_id: str,
    event: str,
) -> bool:
    """Called only during a genuine Tag birth, before the canonical event is saved."""
    from girlframe.engine.m3_ankou_pulse import npc_move

    if npc_move(before, after, recipient, tag_id, event):
        return False  # This original Tag moved; its setter did not give a new one.
    if tag_id.startswith(("dose-up:", "stim-sex-drug:")):
        return False
    if recipient.kind not in ("pilot", "npc"):
        return False
    if any(x.id == tag_id for x in actor_tags(before, recipient)):
        raise WorkflowError("Never retroactively qualify an existing Tag")
    sheet = before.sheets.get(giver.entity) if giver.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != giver.incarnation
        or not has_rule(sheet, rules.RULE, "STIM-BLISSED")
    ):
        return False
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    first = _giver(game, c, before, giver)
    other = (
        _native(game, c, before, recipient)
        if recipient.kind == "pilot"
        else _npc(game, c, before, recipient)
    )
    altered = _altered(game, c, before, recipient)
    if altered is None:
        return False
    tag = next((x for x in actor_tags(after, recipient) if x.id == tag_id), None)
    if tag is None:
        raise WorkflowError("Qualify only the actual newly applied Tag")
    if isinstance(tag, TagState):
        if (
            tag.giver != first.controller
            or tag.giver_actor != giver
            or tag.giver_character != giver.incarnation
        ):
            raise WorkflowError("Preserve the original Tag giver's real character and controller")
    elif getattr(tag, "giver_entity", None) != giver.model_dump_json():
        raise WorkflowError("Preserve the actual WorldTag setter")
    birth = rules.Birth(
        id=tag_id,
        giver=giver,
        recipient=recipient,
        giver_controller=first.controller,
        recipient_controller=other.controller,
        event=event,
        altered_kind=altered[0],
        altered_id=altered[1],
        tag=tag.model_dump_json(),
    )
    previous = next((x for x in rules.records(after, rules.Birth) if x.id == tag_id), None)
    if previous is not None:
        if previous != birth:
            raise WorkflowError("Preserve the exact original birth recipient, giver and event")
        return True
    rules.put(after, birth)
    return True


def prove_birth(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Birth:
    value = _record(state, rules.Birth, identity)
    born = _history(c, game, value.event)
    if value not in rules.records(born, rules.Birth):
        raise WorkflowError("Recover the actual original birth eligibility")
    seq = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    )
    history = t.m2["m2_state_history"]
    prior = (
        c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, history.c.event_id == t.events.c.id)
            .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < seq)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if seq is not None
        else None
    )
    if prior is None:
        raise WorkflowError("Recover the actual canonical state before this Tag was born")
    before = GameState.model_validate_json(prior)
    if any(x.id == identity for x in actor_tags(before, value.recipient)):
        raise WorkflowError("An existing Tag cannot acquire retroactive eligibility")
    first = _giver(game, c, born, value.giver)
    other = (
        _native(game, c, born, value.recipient)
        if value.recipient.kind == "pilot"
        else _npc(game, c, born, value.recipient)
    )
    tag = next((x for x in actor_tags(born, value.recipient) if x.id == identity), None)
    if (
        tag is None
        or tag.model_dump_json() != value.tag
        or first.controller != value.giver_controller
        or other.controller != value.recipient_controller
        or identity.startswith(("dose-up:", "stim-sex-drug:"))
    ):
        raise WorkflowError("Recover the exact original Tag and actual source participants")
    altered = _altered(game, c, before, value.recipient)
    if altered != (value.altered_kind, value.altered_id):
        raise WorkflowError("Recover the actual birth-time altered state")
    return value


def stage_deprogram(
    game: GameService,
    c: Connection,
    state: GameState,
    subject: ActorRef,
    tags: tuple[str, ...],
    event: str,
) -> tuple[GameState, bool]:
    """Root's real Handler/OffDuty producer proves period, employment and work facts."""
    for value in rules.records(state, rules.Birth):
        if value.recipient == subject:
            prove_birth(game, c, state, value.id)
    return rules.deprogram(state, subject, tags, event)


class MalleableService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store = store
        self.game = game or GameService(store)

    def classify_intoxication_tag(
        self, viewer: GuildViewer, key: str, tag: str, expected: int, account: str
    ) -> dict[str, Any]:
        from girlframe.services.m3_malleable_self_tag import record

        return record(self.game, viewer, key, tag, expected, account)

    def force(
        self, viewer: GuildViewer, key: str, identity: str, replaced: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("Reopen current actual replacement controls")
            value = prove_birth(self.game, c, state, identity)
            first = _giver(self.game, c, state, value.giver)
            if viewer.user_id != value.giver_controller or first.controller != viewer.user_id:
                raise WorkflowError("Only the original actual giver chooses forced embrace")
            _native(self.game, c, state, value.recipient)
            from girlframe.services.m2_choices import ChoiceEngine

            engine = ChoiceEngine(self.game)
            tag = next(
                (x for x in state.sheets[value.recipient.entity].tags if x.id == value.id), None
            )
            if tag is None:
                raise WorkflowError("The original qualified Tag is already consumed")
            engine.prove_tag_setter(c, state, int(value.recipient.entity), tag)
            event = str(uuid4())
            changed = rules.force(
                state, value, replaced, str(uuid4()), event, duplicates=engine.duplicate_labels()
            )
            engine.malleable_resolved(c, changed, int(value.recipient.entity), value.id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.malleable_forced",
                changed,
                event_id=event,
                birth=identity,
                replaced=replaced,
            )
            return dict(id=identity, event=event)

        return self.store._write(
            viewer,
            key,
            "m3.malleable_forced",
            dict(id=identity, replaced=replaced, expected=expected),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def _fact(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        expected: int,
        account: str,
        *,
        ending: str | None = None,
        player: bool = False,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual altered state or its actual ending")
        if (subject.kind == "pilot") != player:
            raise WorkflowError("Use only the original player or NPC fact producer")
        prefix = "m3.malleable_player" if player else "m3.malleable_npc"
        kind = prefix + ("_alteration_end" if ending else "_alteration")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays and reopen the actual source context")
            actual = _alteration_subject(self.game, c, state, subject)
            cast = _cast(self.game, c, state, channel)
            if actual.controller != viewer.user_id or not any(
                x.actor == subject and x.controller == viewer.user_id for x in cast.roles
            ):
                raise WorkflowError(
                    "Only the actual affected player or current NPC controller supplies this fact"
                )
            event, identity = str(uuid4()), str(uuid4())
            if ending:
                value = prove_alteration(self.game, c, state, ending)
                if value.subject != subject or any(
                    x.alteration == ending for x in rules.records(state, rules.AlterationEnd)
                ):
                    raise WorkflowError("End the actual original still-active alteration")
                rules.put(
                    state,
                    rules.AlterationEnd(
                        id=identity,
                        alteration=ending,
                        controller=viewer.user_id,
                        event=event,
                        account=account,
                    ),
                )
            else:
                if any(
                    x.subject == subject
                    and not any(
                        y.alteration == x.id for y in rules.records(state, rules.AlterationEnd)
                    )
                    for x in rules.records(state, rules.Alteration)
                ):
                    raise WorkflowError("End the existing actual altered state first")
                rules.put(
                    state,
                    rules.Alteration(
                        id=identity,
                        subject=subject,
                        controller=viewer.user_id,
                        cast=cast,
                        vessel=actual.vessel_id,
                        event=event,
                        account=account,
                    ),
                )
            if cast not in state.scene_casts:
                state.scene_casts.append(cast)
            self.game.event(
                c, viewer.user_id, key, kind, state, event_id=event, alteration=identity
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            kind,
            dict(
                channel=channel,
                subject=subject.model_dump(mode="json"),
                expected=expected,
                account=account,
                ending=ending,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def record_player_alteration(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        expected: int,
        account: str,
        *,
        ending: str | None = None,
    ) -> dict[str, Any]:
        """Only the affected human attests their original character's actual condition."""
        return self._fact(
            viewer, key, channel, subject, expected, account, ending=ending, player=True
        )

    def record_npc_alteration(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        return self._fact(viewer, key, channel, subject, expected, account)

    def end_npc_alteration(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        alteration: str,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        return self._fact(viewer, key, channel, subject, expected, account, ending=alteration)

    def give_npc_tag(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        subject: ActorRef,
        label: str,
        expected: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            before = load_state(c, self.store.campaign_id)
            if before.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays and reopen the actual Tag source")
            giver = current_ref(before, viewer.user_id)
            first, other = _giver(self.game, c, before, giver), _npc(self.game, c, before, subject)
            cast = _cast(self.game, c, before, channel)
            if (
                first.cell is None
                or first.cell != other.cell
                or not all(
                    any(x.actor == actor and x.controller == controller for x in cast.roles)
                    for actor, controller in ((giver, viewer.user_id), (subject, other.controller))
                )
            ):
                raise WorkflowError("Use the original giver and NPC in their actual shared scene")
            event, identity = str(uuid4()), str(uuid4())
            after = give_tag(
                before,
                profiles(c, self.store.campaign_id),
                subject,
                giver,
                label.strip(),
                identity,
                event,
                tuple(sorted({x.controller for x in cast.roles})),
            )
            eligible = stage_birth(self.game, c, before, after, giver, subject, identity, event)
            self.game.event(
                c, viewer.user_id, key, "m3.malleable_npc_tag", after, event_id=event, tag=identity
            )
            return dict(id=identity, eligible=eligible)

        return self.store._write(
            viewer,
            key,
            "m3.malleable_npc_tag",
            dict(
                channel=channel,
                subject=subject.model_dump(mode="json"),
                label=label,
                expected=expected,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove_birth(self.game, c, state, identity)
            if viewer.user_id != value.giver_controller:
                raise WorkflowError("Only the original giver reads necessary replacement fields")
            _giver(self.game, c, state, value.giver)
            from girlframe.services.m2_choices import ChoiceEngine

            options = rules.legal_replacements(
                state, value, duplicates=ChoiceEngine(self.game).duplicate_labels()
            )
            forced = next(
                (x for x in rules.records(state, rules.Forced) if x.birth == identity), None
            )
            return dict(
                id=identity,
                revision=state.revision,
                label=json.loads(value.tag)["label"],
                phase="embraced"
                if forced
                else "npc_protected"
                if value.recipient.kind == "npc"
                else "available"
                if options
                else "unavailable",
                replacements=[dict(id=x.id, name=x.name) for x in options],
                pending=bool(options),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                label="Your Malleable Tag: " + json.loads(x.tag)["label"],
                pending=not any(y.birth == x.id for y in rules.records(state, rules.Forced))
                and x.recipient.kind == "pilot",
                revision=state.revision,
            )
            for x in rules.records(state, rules.Birth)
            if x.giver_controller == viewer.user_id
        ]

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            npcs = []
            for role in cast.roles:
                if role.actor.kind != "npc":
                    continue
                try:
                    actual = _npc(self.game, c, state, role.actor)
                except (ValueError, WorkflowError):
                    continue
                npcs.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        label=actual.label,
                        controller=actual.controller,
                    )
                )
            alterations = [
                dict(id=x.id, subject=x.subject.model_dump(mode="json"))
                for x in rules.records(state, rules.Alteration)
                if any(npc["ref"] == x.subject.model_dump(mode="json") for npc in npcs)
                if not any(y.alteration == x.id for y in rules.records(state, rules.AlterationEnd))
            ]
            can_give = False
            try:
                _giver(self.game, c, state, current_ref(state, viewer.user_id))
                can_give = True
            except (ValueError, WorkflowError):
                pass
            own = None
            try:
                actor = current_ref(state, viewer.user_id)
                actual = _alteration_subject(self.game, c, state, actor)
                if (
                    actor.kind == "pilot"
                    and actual.controller == viewer.user_id
                    and any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
                ):
                    active = next(
                        (
                            x
                            for x in rules.records(state, rules.Alteration)
                            if x.subject == actor
                            and not any(
                                y.alteration == x.id
                                for y in rules.records(state, rules.AlterationEnd)
                            )
                        ),
                        None,
                    )
                    if active is not None:
                        prove_alteration(self.game, c, state, active.id)
                    own = dict(
                        ref=actor.model_dump(mode="json"), active=active.id if active else None
                    )
            except (ValueError, WorkflowError):
                pass
            own_tags = []
            if can_give:
                from girlframe.services.m3_malleable_self_tag import origin

                for tag in state.sheets[str(viewer.user_id)].tags:
                    if any(x.id == tag.id for x in rules.records(state, rules.IntoxicationTag)):
                        continue
                    try:
                        origin(self.game, c, state, viewer.user_id, tag)
                    except (ValueError, WorkflowError):
                        continue
                    own_tags.append(dict(id=tag.id, label=tag.label))
            return dict(
                revision=state.revision,
                intoxication_candidates=own_tags,
                own_alteration=own,
                npcs=npcs,
                alterations=alterations,
                can_give=can_give,
                history=self._tasks(c, viewer),
            )
