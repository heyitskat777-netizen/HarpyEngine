"""Genuine psychic contact into existing owned Girl Sex sources, never borrowed outcomes."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as mental
from girlframe.engine import m3_changeling_sex as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_changeling import (
    _live,
    _owned_brain_choice,
    prove_fingers,
    require_rule,
    settle_fingers,
)
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def current_participant(
    game: GameService, c: Connection, state: GameState, original: mental.BrainRef
) -> mental.BrainRef:
    """A source role follows only its positively proved same physical Brain."""
    return _live(game, c, state, original)


def _role_brain(value: rules.Link, role: ActorRef) -> mental.BrainRef:
    brain = next((x for x in (value.initiator, value.counterpart) if x.actor == role), None)
    if brain is None:
        raise WorkflowError("Keep the original actual psychic source role")
    return brain


def _participants(
    game: GameService, c: Connection, state: GameState, value: rules.Link
) -> dict[str, mental.BrainRef]:
    return {
        x.actor.token: current_participant(game, c, state, x)
        for x in (value.initiator, value.counterpart)
    }


def am_participants(
    game: GameService, c: Connection, state: GameState, source: rules.UnrolledAMSex
) -> dict[str, mental.BrainRef]:
    """Current endpoints keyed by immutable source roles; no AM/Gender entitlement transfer."""
    prove_source_link(
        game, c, state, source.link, source.id, source.actor, source.target, rules.RULES["AM"]
    )
    return _participants(game, c, state, prove(game, c, state, source.link))


def _consent(game: GameService, c: Connection, state: GameState, use: mental.Fingers) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == use.consent_event
            )
        )
        .mappings()
        .first()
    )
    scope = _history(c, game, str(row["id"])) if row else None
    if (
        row is None
        or scope is None
        or row["kind"] != "m3.changeling_sex_consented"
        or row["actor_id"] != str(current_participant(game, c, scope, use.subject).controller)
    ):
        raise WorkflowError(
            "Preserve the original actual counterpart's separate voluntary acceptance"
        )
    born = mental.get(_history(c, game, row["id"]), use.id)
    if born.consent_event != row["id"] or born.sex_outcome is not None or born.action is not None:
        raise WorkflowError("Acceptance is an actual invitation answer, not performed Sex")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Link:
    value = rules.get(state, identity)
    use = prove_fingers(game, c, state, value.use)
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != "m3.changeling_sex_linked"
        or row["actor_id"] != str(value.controller)
    ):
        raise WorkflowError("Recover the actual original human-authored source link")
    born = rules.get(_history(c, game, value.event), value.id)
    mutable = {
        "session",
        "source_event",
        "action",
        "bound_event",
        "completed_event",
        "completion_source",
        "outcome",
    }
    if born.model_dump(exclude=mutable) != value.model_dump(exclude=mutable):
        raise WorkflowError("Preserve the actual rule, performer, brains and original initiation")
    if (
        use.kind != "sex"
        or value.initiator != use.brain
        or value.counterpart != use.subject
        or {value.performer, value.partner} != {use.actor, use.target}
    ):
        raise WorkflowError("Use the real original psychic participants, never a controller proxy")
    _consent(game, c, state, use)
    origin = _history(c, game, use.event)
    require_rule(game, c, origin, use.actor, mental.MINDFUCK)
    return value


def admit_contact(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
    identity: str | None,
) -> bool:
    if identity is None:
        return False
    value = prove(game, c, state, identity)
    if (value.performer, value.partner, value.rule) != (actor, target, rule):
        raise WorkflowError("Use only this exact genuine Girl source and original participants")
    if value.completed_event is None:
        _live(game, c, state, value.initiator)
        _live(game, c, state, value.counterpart)
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    book = next((name for name, candidate in rules.RULES.items() if candidate == rule), None)
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or book is None
        or not has_rule(sheet, rule, book)
    ):
        raise WorkflowError("Psychic contact grants no borrowed Girl rule or substitute resources")
    return True


def bind_source(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    session: str,
    rule: str,
    event: str,
) -> None:
    value = prove(game, c, state, identity)
    if value.session or value.completed_event or value.rule != rule:
        raise WorkflowError("Bind one actual specialized source to the consumed initiation")
    admit_contact(game, c, state, value.performer, value.partner, rule, identity)
    rules.put(state, value.model_copy(update=dict(session=session, source_event=event)))


def prove_source_link(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    session: str,
    actor: ActorRef,
    target: ActorRef,
    rule: str,
) -> None:
    value = prove(game, c, state, identity)
    if (value.session, value.performer, value.partner, value.rule) != (
        session,
        actor,
        target,
        rule,
    ) or value.source_event is None:
        raise WorkflowError("Keep the exact genuine specialized invitation/source binding")
    bound = rules.get(_history(c, game, value.source_event), identity)
    if (bound.session, bound.source_event) != (session, value.source_event):
        raise WorkflowError("Recover the actual canonical specialized source birth")


def for_play(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.Link | None:
    source = action["data"].get("prepared", {}).get("source_work")
    value = next((item for item in rules.records(state) if item.session == source), None)
    if value is None:
        return None
    prove_source_link(
        game, c, state, value.id, value.session or "", value.performer, value.partner, value.rule
    )
    if (
        str(action["actor_id"]) != value.performer.entity
        or action["data"]["play"]
        != rules.PLAYS[next(name for name, rule in rules.RULES.items() if rule == value.rule)]
    ):
        raise WorkflowError("The real source performer makes her actual Girl-specific Play")
    return value


def bind_action(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = for_play(game, c, state, action)
    if value is None:
        return
    if value.action or value.completed_event:
        raise WorkflowError("Bind only the one actual source Action")
    action["data"]["changeling_remote"] = dict(
        id=value.use,
        link=value.id,
        actor=value.performer.model_dump(mode="json"),
        target=value.partner.model_dump(mode="json"),
    )
    rules.put(state, value.model_copy(update=dict(action=action["id"], bound_event=event)))
    use = mental.get(state, value.use)
    if use.action:
        raise WorkflowError("Never replace an existing actual remote Sex Action")
    mental.put(state, use.model_copy(update=dict(action=action["id"])))


def _source(game: GameService, c: Connection, state: GameState, value: rules.Link) -> Any:
    session = value.session or ""
    if value.rule == rules.RULES["ALPHA"]:
        from girlframe.services.m3_alpha_sex import prove as actual_1

        return actual_1(game, c, state, session)
    elif value.rule == rules.RULES["PRINCESS"]:
        from girlframe.services.m3_princess_sex import prove as actual_2

        return actual_2(game, c, state, session)
    elif value.rule == rules.RULES["STIM-BLISSED"]:
        from girlframe.services.m3_stim_sex import prove as actual_3

        return actual_3(game, c, state, session)
    elif value.rule == rules.RULES["OLDGEN"]:
        from girlframe.services.m3_oldgen_sex import prove as actual_4

        return actual_4(game, c, state, session)
    elif value.rule == rules.RULES["CASUALTY"]:
        from girlframe.services.m3_casualty import prove_sex as actual_5

        return actual_5(game, c, state, session)
    elif value.rule == rules.RULES["VATGROWN"]:
        from girlframe.services.m3_vatgrown_plays import prove as actual_6

        return actual_6(game, c, state, session)
    elif value.rule == rules.RULES["NEWGIRL"]:
        from girlframe.services.m3_newgirl_sex import prove as actual_7

        return actual_7(game, c, state, session)
    elif value.rule == rules.RULES["BONDED"]:
        from girlframe.services.m3_bonded import prove as actual_8

        return actual_8(game, c, state, session)
    elif value.rule == rules.RULES["MOCKINGBIRD"]:
        from girlframe.services.m3_mockingbird_plays import _trigger

        trigger = _trigger(state, session)
        if (
            trigger.changeling_source != value.id
            or trigger.actor != value.performer
            or len(trigger.parties) != 1
            or trigger.parties[0].actor != value.partner
        ):
            raise WorkflowError(
                "Preserve the actual Mockingbird source and sole psychic counterpart"
            )
        born = _trigger(_history(c, game, trigger.source_event), session)
        if born.changeling_source != value.id or born.actor != trigger.actor:
            raise WorkflowError("Recover the original human-authored Mockingbird invitation")
        return trigger
    elif value.rule == rules.RULES["AM"]:
        return prove_am_source(game, c, state, session)
    else:
        raise WorkflowError("Use an actual implemented Girl source")


def complete_source(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    session: str,
    event: str,
) -> None:
    value = prove(game, c, state, identity)
    if value.completed_event:
        return
    if value.session != session:
        raise WorkflowError("Complete only this actual bound source session")
    source = _source(game, c, state, value)
    phase = source.state if value.rule == rules.RULES["MOCKINGBIRD"] else source.phase
    if phase not in ("complete", "declined"):
        return
    action_id = source.action
    if phase == "declined":
        if action_id:
            raise WorkflowError("An actually declined invitation cannot have a performed Action")
    elif action_id:
        action = game.action(c, action_id)
        if action["state"] != "complete":
            return
        if action["data"].get("changeling_remote", {}).get("link") != value.id:
            raise WorkflowError("Complete the actual original Action and all of its owed effects")
        _roll_source(game, c, action)
    elif (
        value.rule not in (rules.RULES["BONDED"], rules.RULES["AM"])
        or not source.effect_event
        or not source.completed_event
    ):
        raise WorkflowError("Prove the genuine nonrolling source without inventing an Action")
    cause = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    fresh = str(uuid4()) if cause else event
    rules.put(
        state,
        value.model_copy(
            update=dict(
                completed_event=fresh,
                completion_source=event,
                outcome="declined" if phase == "declined" else "performed",
            )
        ),
    )
    use = mental.get(state, value.use)
    mental.put(
        state,
        use.model_copy(
            update=dict(
                sex_event=fresh,
                sex_outcome="declined" if phase == "declined" else "performed",
                action=action_id,
            )
        ),
    )
    settle_fingers(game, c, state, value.use, fresh)
    if cause:
        index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.command_key == cause["command_key"],
            )
        )
        game.event(
            c,
            cause["actor_id"],
            cause["command_key"],
            "m3.changeling_sex_completed",
            state,
            event_id=fresh,
            event_index=0 if index is None else index + 1,
            link=value.id,
            session=session,
            source_event=event,
        )


def sex_complete(game: GameService, c: Connection, state: GameState, use: mental.Fingers) -> bool:
    value = next((item for item in rules.records(state) if item.use == use.id), None)
    if value is None or value.completed_event is None:
        return False
    prove(game, c, state, value.id)
    source = _source(game, c, state, value)
    phase = source.state if value.rule == rules.RULES["MOCKINGBIRD"] else source.phase
    return bool(phase == ("declined" if value.outcome == "declined" else "complete"))


class ChangelingSexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        channel: int,
        account: str,
        *,
        route: str = "pair",
        delegated_rule: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            use = prove_fingers(self.game, c, state, identity)
            _consent(self.game, c, state, use)
            _live(self.game, c, state, use.brain)
            _live(self.game, c, state, use.subject)
            performer, partner = use.actor, use.target
            if state.sheets[performer.entity].girl == "AM":
                other_sheet = state.sheets.get(partner.entity) if partner.kind == "pilot" else None
                if other_sheet is not None and other_sheet.girl != "AM":
                    performer, partner = partner, performer
            sheet = state.sheets.get(performer.entity) if performer.kind == "pilot" else None
            actual = resolve(
                state, performer, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            scene = _cast(self.game, c, state, channel)
            if (
                sheet is None
                or sheet.girl not in rules.RULES
                or actual.controller != viewer.user_id
                or state.revision != revision
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "The actual Girl performer authors her genuine source; no AM extra roll"
                )
            if not {performer, partner} <= {role.actor for role in scene.roles}:
                raise WorkflowError(
                    "Both actual humans must join the real remote source scene; "
                    "no fabricated attendance"
                )
            rule = rules.RULES[sheet.girl]
            if not has_rule(sheet, rule, sheet.girl):
                raise WorkflowError("Use only the actual performer's own printed Sex rule")
            if sheet.girl != "BONDED" and (route != "pair" or delegated_rule is not None):
                raise WorkflowError("Only real Bonded source choices select a Pair route")
            if route not in ("pair", "seven", "delegated"):
                raise WorkflowError("Select an actual printed Bonded route")
            if sheet.girl == "BONDED":
                from girlframe.services.m3_bonded import current_pair_sex_rules, original_pair

                pair, _ = original_pair(self.game, c, state, performer, rules.RULES["BONDED"])
                if (partner == pair) != (route == "pair"):
                    raise WorkflowError("Choose the actual Pair or a genuine non-Pair source route")
                if route == "delegated":
                    if (
                        delegated_rule not in current_pair_sex_rules(state, pair)
                        or delegated_rule == rules.RULES["BONDED"]
                    ):
                        raise WorkflowError(
                            "Choose the actual Pair's genuinely owned noncycling Sex rule"
                        )
                    gate = Access(self.store)
                    assert gate.registry is not None
                    gate.registry.require_available(delegated_rule)
                elif delegated_rule is not None:
                    raise WorkflowError("Only real delegation chooses the actual Pair's rule")
            link_id = rules.identity(use.id)
            old = next((item for item in rules.records(state) if item.id == link_id), None)
            if old:
                raise WorkflowError(
                    "Reopen the existing actual source instead of proposing it twice"
                )
            event = str(uuid4())
            value = rules.Link(
                id=link_id,
                use=use.id,
                initiator=use.brain,
                counterpart=use.subject,
                performer=performer,
                partner=partner,
                rule=rule,
                event=event,
                controller=viewer.user_id,
                account=account,
                route=cast(Literal["pair", "seven", "delegated"], route),
                delegated_rule=delegated_rule,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.changeling_sex_linked",
                state,
                event_id=event,
                link=value.id,
            )
            return dict(id=value.id)

        result = self.store._write(
            viewer,
            key,
            "m3.changeling_sex_linked",
            dict(
                revision=revision,
                use=identity,
                channel=channel,
                account=account,
                route=route,
                delegated_rule=delegated_rule,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, result["id"])
        if value.session is None:
            self._invite(viewer, key + ":girl-source", value, channel, state.revision)
            with self.store.engine.connect() as c:
                value = prove(self.game, c, load_state(c, self.store.campaign_id), value.id)
        return dict(id=value.id, session=value.session, rule=value.rule)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        rows = []
        for value in rules.records(state):
            people = _participants(self.game, c, state, value)
            if viewer.user_id not in {x.controller for x in people.values()}:
                continue
            pending = value.session is None and viewer.user_id == value.controller
            if value.session and not value.completed_event:
                source = _source(self.game, c, state, value)
                phase = source.state if value.rule == rules.RULES["MOCKINGBIRD"] else source.phase
                partner = people[value.partner.token].controller
                pending = (
                    phase in ("invited", "proposed")
                    and viewer.user_id == partner
                    or phase == "accepted"
                    and viewer.user_id == value.controller
                )
                if isinstance(source, rules.UnrolledAMSex) and phase == "accepted":
                    pending = any(
                        people[actor.token].controller == viewer.user_id
                        and not any(
                            performance.source == source.id and performance.actor == actor
                            for performance in rules.performances(state)
                        )
                        for actor in (source.actor, source.target)
                    )
                if isinstance(source, rules.UnrolledAMSex) and phase == "effects":
                    from girlframe.services.p1_unrolled_sex import tasks as gift_tasks

                    pending = any(
                        gift["pending"] for gift in gift_tasks(self.game, c, state, source, viewer)
                    )
            rows.append(
                dict(
                    id=value.id,
                    label="Actual psychic Sex source",
                    revision=state.revision,
                    phase="resolved" if value.completed_event else "pending",
                    pending=bool(pending and not value.completed_event),
                )
            )
        return rows

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            value = next(
                (
                    item
                    for item in rules.records(state)
                    if item.id == identity or item.use == identity
                ),
                None,
            )
            use = prove_fingers(self.game, c, state, value.use if value else identity)
            people = tuple(
                current_participant(self.game, c, state, x) for x in (use.brain, use.subject)
            )
            if viewer.user_id not in {x.controller for x in people}:
                raise WorkflowError(
                    "Only the original actual psychic participants read this private source"
                )
            if use.kind != "sex":
                raise WorkflowError("Use the real original remote Sex initiation")
            origin = _history(c, self.game, use.event)
            performer = value.performer if value else use.actor
            if value is None and origin.sheets[use.actor.entity].girl == "AM":
                other = origin.sheets.get(use.target.entity) if use.target.kind == "pilot" else None
                if other is not None and other.girl != "AM":
                    performer = use.target
            try:
                actual = resolve(
                    state,
                    performer,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                controller, label = actual.controller, actual.label
            except ValueError:
                controller, label = None, "Original source performer"
            result: dict[str, Any] = dict(
                id=identity,
                use=use.id,
                revision=state.revision,
                accepted=use.consent_event is not None,
                outcome=use.sex_outcome,
                can_start=value is None
                and use.consent_event is not None
                and use.sex_event is None
                and viewer.user_id == controller,
                performer=performer.model_dump(mode="json"),
                performer_label=label,
                book=origin.sheets[performer.entity].girl,
                source=None,
            )
            if value:
                prove(self.game, c, state, value.id)
                result["link"] = value.model_dump(mode="json")
                if value.session:
                    source = _source(self.game, c, state, value)
                    result["source"] = dict(
                        id=value.session,
                        rule=value.rule,
                        phase=source.state
                        if value.rule == rules.RULES["MOCKINGBIRD"]
                        else source.phase,
                        action=source.action,
                    )
            return result

    def _am_write(
        self, viewer: GuildViewer, key: str, kind: str, request: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "plays", director_response=True)
            assert gate.registry is not None
            gate.registry.require_available(rules.RULES["AM"])
            self.game.unpaused(c)

        return self.store._write(
            viewer, key, kind, request, operation, auto_audit=False, authorize=authorize
        )

    def am_invite(
        self, viewer: GuildViewer, key: str, value: rules.Link, channel: int, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            current = prove(self.game, c, state, value.id)
            admit_contact(
                self.game,
                c,
                state,
                current.performer,
                current.partner,
                rules.RULES["AM"],
                current.id,
            )
            if (
                current.session
                or current.controller != viewer.user_id
                or state.revision != revision
            ):
                raise WorkflowError("Use the actual original current AM no-extra-roll source")
            other_sheet = (
                state.sheets.get(current.partner.entity)
                if current.partner.kind == "pilot"
                else None
            )
            if other_sheet is not None and other_sheet.girl != "AM":
                raise WorkflowError(
                    "The actual other Girl makes her genuine existing Sex Play instead"
                )
            if current.partner.kind not in ("pilot", "npc"):
                raise WorkflowError(
                    "SOURCE_COUNTERPART_SEX_REQUIRED: use the actual Handler, "
                    "Harpy or Gorgon source adapter"
                )
            scene = _cast(self.game, c, state, channel)
            people = (current.initiator, current.counterpart)
            if not {current.performer, current.partner} <= {role.actor for role in scene.roles}:
                raise WorkflowError("Use the actual voluntarily joined source roles")
            event, identity = str(uuid4()), str(uuid4())
            source = rules.UnrolledAMSex(
                id=identity,
                link=current.id,
                actor=current.performer,
                target=current.partner,
                controllers={brain.actor.token: brain.controller for brain in people},
                vessels={brain.actor.token: brain.vessel for brain in people},
                cast=scene,
                event=event,
                account=current.account,
            )
            rules.put_am(state, source)
            bind_source(self.game, c, state, current.id, identity, current.rule, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.changeling_am_invited",
                state,
                event_id=event,
                source=identity,
            )
            return dict(id=identity, revision=state.revision)

        return self._am_write(
            viewer,
            key,
            "m3.changeling_am_invited",
            dict(link=value.id, channel=channel, revision=revision),
            operation,
        )

    def am_respond(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        accepted: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = prove_am_source(self.game, c, state, identity)
            link = prove(self.game, c, state, source.link)
            actual = current_participant(self.game, c, state, _role_brain(link, source.target))
            _owned_brain_choice(
                self.game, c, state, viewer, _role_brain(link, source.target), source.cast
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError(
                    "Only the current human of the original actual counterpart answers"
                )
            _live(self.game, c, state, prove(self.game, c, state, source.link).counterpart)
            if (
                state.revision != revision
                or source.phase != "invited"
                or viewer.user_id != actual.controller
                or type(accepted) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original counterpart answers this separate AM source"
                )
            event = str(uuid4())
            rules.put_am(
                state,
                source.model_copy(
                    update=dict(
                        phase="accepted" if accepted else "declined",
                        consent_event=event,
                        consent_account=account,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.changeling_am_consented",
                state,
                event_id=event,
                source=identity,
                accepted=accepted,
            )
            complete_source(self.game, c, state, source.link, identity, event)
            return dict(id=identity, revision=state.revision)

        return self._am_write(
            viewer,
            key,
            "m3.changeling_am_consented",
            dict(source=identity, revision=revision, accepted=accepted, account=account),
            operation,
        )

    def am_perform(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        actor: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = prove_am_source(self.game, c, state, identity)
            link = prove(self.game, c, state, source.link)
            people = _participants(self.game, c, state, link)
            performer = people[source.actor.token]
            own = state.sheets.get(source.actor.entity) if source.actor.kind == "pilot" else None
            if (
                performer.actor != source.actor
                or own is None
                or own.character_id != source.actor.incarnation
                or own.girl != "AM"
                or not has_rule(own, rules.RULES["AM"], "AM")
            ):
                raise WorkflowError(
                    "SOURCE_CURRENT_AM_PERFORMER_REQUIRED: no reset NPC inherits the Girl rule"
                )
            role = next(
                (
                    original
                    for original in (source.actor, source.target)
                    if people[original.token].actor == actor
                ),
                None,
            )
            if role is None:
                raise WorkflowError("Use the actual current person for this original source role")
            actual = people[role.token]
            _owned_brain_choice(self.game, c, state, viewer, _role_brain(link, role), source.cast)
            if actual.controller != viewer.user_id:
                raise WorkflowError(
                    "The actual original role's current human authors its performance"
                )
            if (
                state.revision != revision
                or source.phase != "accepted"
                or actual.vessel != source.vessels.get(role.token)
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "Each original role's actual human attests the real performed psychic scene"
                )
            _live(self.game, c, state, link.initiator)
            _live(self.game, c, state, link.counterpart)
            if any(
                value.source == identity and value.actor == role
                for value in rules.performances(state)
            ):
                raise WorkflowError(
                    "Preserve each actual role's original factual performed-scene account"
                )
            event = str(uuid4())
            rules.put_am(
                state,
                rules.AMPerformance(
                    id=identity + ":" + role.token,
                    source=identity,
                    actor=role,
                    performed_by=actor if actor != role else None,
                    controller=viewer.user_id,
                    account=account,
                    event=event,
                ),
            )
            performed = {
                value.actor for value in rules.performances(state) if value.source == identity
            }
            if performed == {source.actor, source.target}:
                source = source.model_copy(update=dict(phase="effects", effect_event=event))
                rules.put_am(state, source)
                from girlframe.services.p1_unrolled_sex import offer

                offer(self.game, c, state, source, event)
            provenance: dict[str, Any] = (
                {"source_role": role.model_dump(mode="json")} if actor != role else {}
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.changeling_am_performed",
                state,
                event_id=event,
                source=identity,
                person=actor.model_dump(mode="json"),
                **provenance,
            )
            synchronize_am(self.game, c, state, identity, event)
            return dict(id=identity, revision=state.revision)

        return self._am_write(
            viewer,
            key,
            "m3.changeling_am_performed",
            dict(
                source=identity,
                revision=revision,
                person=actor.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def view_am(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            source = prove_am_source(self.game, c, state, identity)
            people = _participants(self.game, c, state, prove(self.game, c, state, source.link))
            if viewer.user_id not in {x.controller for x in people.values()}:
                raise WorkflowError(
                    "Only actual original source humans read these private accounts"
                )
            from girlframe.services.p1_unrolled_sex import tasks

            performed = [value for value in rules.performances(state) if value.source == identity]
            return dict(
                id=identity,
                revision=state.revision,
                body=source.model_dump(mode="json"),
                performances=[value.model_dump(mode="json") for value in performed],
                can_answer=source.phase == "invited"
                and viewer.user_id == people[source.target.token].controller,
                perform=[
                    people[actor.token].actor.model_dump(mode="json")
                    for actor in (source.actor, source.target)
                    if source.phase == "accepted"
                    and people[actor.token].controller == viewer.user_id
                    and not any(value.actor == actor for value in performed)
                ],
                current_participants=[x.model_dump(mode="json") for x in people.values()],
                unrolled_gender=tasks(self.game, c, state, source, viewer),
            )

    def _invite(
        self, viewer: GuildViewer, key: str, value: rules.Link, channel: int, revision: int
    ) -> None:
        if value.rule == rules.RULES["ALPHA"]:
            from girlframe.services.m3_alpha_sex import SexService

            SexService(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["PRINCESS"]:
            from girlframe.services.m3_princess_sex import SexService as Princess

            Princess(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["STIM-BLISSED"]:
            from girlframe.services.m3_stim_sex import SexService as Stim

            Stim(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["OLDGEN"]:
            from girlframe.services.m3_oldgen_sex import OldgenSexService

            OldgenSexService(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["CASUALTY"]:
            from girlframe.services.m3_casualty import CasualtyService

            CasualtyService(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["VATGROWN"]:
            from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService

            VatgrownPlaysService(self.game).invite(
                viewer,
                key,
                channel,
                value.partner,
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["NEWGIRL"]:
            from girlframe.services.m3_newgirl_sex import NewgirlSexService

            NewgirlSexService(self.game).invite(
                viewer,
                key,
                channel,
                (value.partner,),
                revision,
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["MOCKINGBIRD"]:
            from girlframe.services.m3_mockingbird_plays import MockingbirdService

            MockingbirdService(self.game).propose(
                viewer,
                key,
                channel,
                value.performer,
                "mockingbird_sex",
                (value.partner,),
                value.account,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["BONDED"]:
            from girlframe.services.m3_bonded import BondedService

            BondedService(self.game).propose(
                viewer,
                key,
                channel,
                revision,
                "sex",
                value.account,
                target=value.partner,
                route=value.route,
                delegated_rule=value.delegated_rule,
                changeling_source=value.id,
            )
        elif value.rule == rules.RULES["AM"]:
            self.am_invite(viewer, key, value, channel, revision)
        else:
            raise WorkflowError("Use the actual counterpart's source; no generic AM Sex roll")


def synchronize_action(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    if action["state"] != "complete":
        return
    state = load_state(c, game.store.campaign_id)
    value = for_play(game, c, state, action)
    if value is None and action.get("parent_id"):
        value = next(
            (item for item in rules.records(state) if item.action == action["parent_id"]), None
        )
    if value is None and action["data"].get("bonded_child"):
        from girlframe.engine import m3_bonded as bonded

        child = next(
            (
                item
                for item in bonded.records(state, bonded.Child)
                if item.id == action["data"]["bonded_child"].get("child")
                and item.child == action["id"]
                and item.completed_event
            ),
            None,
        )
        if child:
            value = next(
                (item for item in rules.records(state) if item.session == child.source), None
            )
    if value is None or value.completed_event:
        return
    source = _source(game, c, state, value)
    if (source.state if value.rule == rules.RULES["MOCKINGBIRD"] else source.phase) != "complete":
        return
    complete_source(game, c, state, value.id, value.session or "", event)


def synchronize_session(
    game: GameService, c: Connection, state: GameState, session: str, event: str
) -> None:
    value = next((item for item in rules.records(state) if item.session == session), None)
    if value is None or value.completed_event:
        return
    complete_source(game, c, state, value.id, session, event)


def prove_am_source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.UnrolledAMSex:
    source = rules.am_source(state, identity)
    birth = _history(c, game, source.event)
    original = rules.am_source(birth, identity)
    mutable = {"phase", "consent_event", "consent_account", "effect_event", "completed_event"}
    if original.model_dump(exclude=mutable) != source.model_dump(exclude=mutable):
        raise WorkflowError("Preserve actual AM source brains, roles and original proposal")
    prove_source_link(
        game, c, state, source.link, source.id, source.actor, source.target, rules.RULES["AM"]
    )
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source.event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != "m3.changeling_am_invited"
        or row["actor_id"] != str(source.controllers[source.actor.token])
    ):
        raise WorkflowError("Recover the actual original AM source invitation")
    if source.phase != "invited" and source.consent_event is None:
        raise WorkflowError("A genuine source response must precede either performance or decline")
    if source.consent_event:
        consent = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == source.consent_event,
                )
            )
            .mappings()
            .first()
        )
        answered_state = _history(c, game, source.consent_event)
        answered = rules.am_source(answered_state, identity)
        consent_subject = current_participant(
            game,
            c,
            answered_state,
            _role_brain(prove(game, c, answered_state, source.link), source.target),
        )
        if (
            consent is None
            or consent["kind"] != "m3.changeling_am_consented"
            or consent["actor_id"] != str(consent_subject.controller)
            or answered.consent_event != source.consent_event
            or answered.phase not in ("accepted", "declined")
            or source.phase == "declined"
            and answered.phase != "declined"
            or source.phase not in ("invited", "declined")
            and answered.phase != "accepted"
        ):
            raise WorkflowError("Preserve the counterpart's real separate original answer")
    performances = [value for value in rules.performances(state) if value.source == identity]
    if len({value.actor for value in performances}) != len(performances):
        raise WorkflowError("Each actual role supplies its own actual performance once")
    for value in performances:
        scope = _history(c, game, value.event)
        current = current_participant(
            game, c, scope, _role_brain(prove(game, c, scope, source.link), value.actor)
        )
        if (
            value.actor not in (source.actor, source.target)
            or value.controller != current.controller
            or (value.performed_by or value.actor) != current.actor
            or current.vessel != source.vessels[value.actor.token]
            or not value.account.strip()
            or value not in rules.performances(_history(c, game, value.event))
        ):
            raise WorkflowError("Prove the actual role-specific human performance record")
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
                )
            )
            .mappings()
            .first()
        )
        if (
            event is None
            or event["kind"] != "m3.changeling_am_performed"
            or event["actor_id"] != str(value.controller)
            or json.loads(event["payload_json"]).get("person")
            != current.actor.model_dump(mode="json")
        ):
            raise WorkflowError("A performance account is not an inferred consent or generic ack")
    if source.effect_event and (
        {value.actor for value in performances} != {source.actor, source.target}
        or source.effect_event not in {value.event for value in performances}
    ):
        raise WorkflowError(
            "Actual no-roll source effects require both original factual performances"
        )
    return source


def synchronize_am(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    source = prove_am_source(game, c, state, identity)
    if source.phase != "effects":
        return
    from girlframe.engine.p1_unrolled_sex import gifts

    if any(value.source == identity and value.tag is None for value in gifts(state)):
        return
    fresh = str(uuid4())
    rules.put_am(state, source.model_copy(update=dict(phase="complete", completed_event=fresh)))
    cause = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .one()
    )
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == cause["command_key"],
        )
    )
    game.event(
        c,
        cause["actor_id"],
        cause["command_key"],
        "m3.changeling_am_completed",
        state,
        event_id=fresh,
        event_index=0 if index is None else index + 1,
        source=identity,
        source_event=event,
    )
    complete_source(game, c, state, source.link, identity, fresh)


def preflight_initiation(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, target: ActorRef
) -> None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation or sheet.girl not in rules.RULES:
        raise WorkflowError("SOURCE_GIRL_SEX_REQUIRED: use the real original Girl source")
    gate = Access(game.store)
    if gate.registry is None:
        raise WorkflowError("Recover the reviewed actual Girl source registry")
    gate.registry.require_available(rules.RULES[sheet.girl])
    allowed = {"pilot"}
    if sheet.girl == "VATGROWN":
        allowed |= {"npc", "handler"}
    elif sheet.girl == "MOCKINGBIRD":
        allowed |= {"npc", "handler", "external_pilot", "gorgon"}
    elif sheet.girl == "AM":
        allowed |= {"npc"}
    if target.kind not in allowed:
        raise WorkflowError(
            "SOURCE_COUNTERPART_SEX_REQUIRED: implement the actual counterpart's "
            "source before consuming a String"
        )
    if sheet.girl == "AM" and target.kind == "pilot":
        other = state.sheets.get(target.entity)
        if other is None or other.character_id != target.incarnation:
            raise WorkflowError("Preserve the actual original counterpart Girl")
        if other.girl != "AM":
            gate.registry.require_available(rules.RULES[other.girl])
        if other.girl != "AM" and not has_rule(other, rules.RULES[other.girl], other.girl):
            raise WorkflowError("The actual counterpart must hold her genuine mandatory Sex rule")
