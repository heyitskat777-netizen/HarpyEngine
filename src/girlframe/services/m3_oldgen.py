"""Original human-owned maxim triggers, advice choices and factual poor outcomes."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_oldgen as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_malleable import _audit
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("oldgen_write_maxim", "oldgen_low_maxim", "oldgen_listen")


def require_listened(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer
) -> None:
    actions = t.m2["m2_actions"]
    for row in c.execute(
        sa.select(actions.c.id).where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.state.not_in(("complete", "aborted")),
            sa.func.json_extract(actions.c.body_json, "$.oldgen.counterpart") == viewer.user_id,
            sa.func.json_extract(actions.c.body_json, "$.oldgen.phase").in_(
                ("writing", "listening")
            ),
        )
    ):
        action = game.action(c, row.id)
        _, total = _roll_source(game, c, action)
        if total >= 8:
            meta = action["data"]["oldgen"]
            target = ActorRef.model_validate(meta["target"])
            if target != current_ref(state, viewer.user_id):
                continue
            if meta["phase"] == "listening":
                prove_advice(game, c, state, action["id"])
            raise WorkflowError(
                "REQUIRED_FOLLOWUP: perform your original actual advice listening first"
            )


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Oldgen source")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def _oldgen(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    rule: str,
    *,
    action_id: str | None = None,
) -> Any:
    actual = _native(game, c, state, actor)
    if state.sheets[actor.entity].girl == "OLDGEN" and has_rule(
        state.sheets[actor.entity], rule, "OLDGEN"
    ):
        return actual
    from girlframe.services.m3_learned_plays import available

    if rule == rules.ADVICE and available(game, c, state, actor, rule, action_id) is not None:
        return actual
    raise WorkflowError("Use an actual owned Oldgen rule or its proven one-use advice lesson")


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
    *,
    action_id: str | None = None,
) -> dict[str, Any]:
    _access(game, c, viewer, rules.ADVICE)
    actor = current_ref(state, viewer.user_id)
    _oldgen(game, c, state, actor, rules.ADVICE, action_id=action_id)
    from girlframe.services.m3_required_plays import direct_nomination

    nominated = direct_nomination(game, c, state, actor, prepared, channel)
    if (
        prepared.target is None
        or prepared.target == viewer.user_id
        or prepared.parent
        or prepared.off_duty_id
        or (prepared.source_work and not nominated)
    ):
        raise WorkflowError("Give actual advice to another native Girl in the ordinary scene")
    target = current_ref(state, prepared.target)
    other = _native(game, c, state, target)
    cast = _cast(game, c, state, channel)
    handler = active_handler(state)
    if handler is None or not all(
        any(x.actor == ref and x.controller == owner for x in cast.roles)
        for ref, owner in ((actor, viewer.user_id), (target, other.controller))
    ):
        raise WorkflowError(
            "Use the actual original adviser, recipient and Handler in the real cast"
        )
    if cast not in state.scene_casts:
        state.scene_casts.append(cast)
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        caster=viewer.user_id,
        counterpart=other.controller,
        handler_controller=state.handler,
        handler=handler.model_dump(mode="json"),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({x.controller for x in cast.roles} | {state.handler}),
        registry=game.store.policy.m3_approval.registry_sha256,
        phase="unrolled",
    )


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["oldgen"]
    expected = prepare(
        game,
        c,
        viewer,
        state,
        PlayInput.model_validate(action["data"]["prepared"]),
        int(action["channel_id"]),
        action_id=action["id"],
    )
    if any(meta.get(k) != v for k, v in expected.items() if k != "phase"):
        raise WorkflowError("Reopen actual unchanged advice before spending Heat or rolling")


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["oldgen"]
    if meta["phase"] != "unrolled":
        raise WorkflowError("Resume the actual original advice result without rerolling")
    _, total = _roll_source(game, c, action)
    meta["phase"] = "writing"
    if total >= 8:
        shift_status(state, meta["caster"], 1)
        game.request(c, action, meta["caster"], "oldgen_write_maxim")
    else:
        game.request(c, action, meta["counterpart"], "oldgen_low_maxim")


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    meta, kind = action["data"]["oldgen"], row["kind"]
    if (
        not answer.text.strip()
        or len(answer.text) > 1200
        or answer.options
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Supply your actual maxim or performed listening account")
    event = action["data"]["response_event"]
    if kind == "oldgen_listen":
        if (
            int(row["actor_id"]) != meta["counterpart"]
            or meta["phase"] != "listening"
            or answer.denied
        ):
            raise WorkflowError(
                "Only the actual original advice recipient records performed listening"
            )
        meta["listen_event"], meta["listen_choice"] = event, row["id"]
    else:
        rolled, total = _roll_source(game, c, action)
        low = total <= 7
        chooser = meta["counterpart"] if low else meta["caster"]
        if (
            kind != ("oldgen_low_maxim" if low else "oldgen_write_maxim")
            or int(row["actor_id"]) != chooser
            or meta["phase"] != "writing"
            or len(answer.text) > 300
            or (answer.denied and not low)
        ):
            raise WorkflowError("Only the printed original maxim author supplies this result")
        actor, target = (ActorRef.model_validate(meta[k]) for k in ("actor", "target"))
        if low:
            ChoiceEngine(game).unmark(c, state, state.sheets[target.entity], answer.denied, 1)
        value = rules.Maxim(
            id="oldgen-maxim:" + action["id"],
            owner=target if low else actor,
            subject=actor if low else target,
            text=answer.text.strip(),
            event=event,
            advice=action["id"],
            high=total >= 11,
        )
        rules.put(state, value)
        rules.put(
            state,
            rules.Advice(
                id=action["id"],
                actor=actor,
                target=target,
                caster=meta["caster"],
                counterpart=meta["counterpart"],
                handler=meta["handler_controller"],
                cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
                total=total,
                heat=action["data"]["prepared"]["heat"],
                roll_event=rolled,
                event=event,
                maxim=value.id,
                choice=row["id"],
            ),
        )
        if not low:
            meta["phase"] = "listening"
            game.request(c, action, meta["counterpart"], "oldgen_listen")
            return
    meta["phase"] = "complete"
    ChoiceEngine(game).finish(c, state, action)


def detail(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    options: list[tuple[str, str]] = []
    if row["kind"] == "oldgen_low_maxim":
        person = int(row["actor_id"])
        options = [
            (x.id, x.name)
            for x in state.sheets[str(person)].identities
            if x.marked and x.id not in state.sheets[str(person)].sedation_locked
        ]
        options.extend(rules.marked_maxims(state, person))
    return dict(kind=row["kind"], unmark=options, maximum=1)


def prove_advice(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Advice:
    value = _record(state, rules.Advice, identity)
    action = game.action(c, identity)
    born = _history(c, game, value.event)
    rolled, total = _roll_source(game, c, action)
    meta = action["data"].get("oldgen")
    if (
        meta is None
        or action["data"]["prepared"]["play"] != rules.PLAY
        or value not in rules.records(born, rules.Advice)
        or value.actor != ActorRef.model_validate(meta["actor"])
        or value.target != ActorRef.model_validate(meta["target"])
        or value.roll_event != rolled
        or value.total != total
        or value.heat != action["data"]["prepared"]["heat"]
        or value.cast != SceneCast.model_validate_json(json.dumps(meta["cast"]))
        or value.handler != meta["handler_controller"]
    ):
        raise WorkflowError("Recover actual original advice, paid Heat, roll and human source")
    from girlframe.services.m3_learned_plays import prove_consumed

    if not prove_consumed(game, c, state, action, rules.ADVICE, rolled):
        _oldgen(game, c, _history(c, game, rolled), value.actor, rules.ADVICE)
    owner = value.counterpart if total <= 7 else value.caster
    answer = _response(
        game,
        c,
        identity,
        value.choice,
        value.event,
        owner,
        "oldgen_low_maxim" if total <= 7 else "oldgen_write_maxim",
    )
    maxim = _record(born, rules.Maxim, value.maxim)
    if (
        maxim.text != answer.text.strip()
        or maxim.owner != (value.target if total <= 7 else value.actor)
        or maxim.subject != (value.actor if total <= 7 else value.target)
        or maxim.high != (total >= 11)
    ):
        raise WorkflowError("Recover the original author's target-only one-use maxim")
    if meta["phase"] == "complete" and total >= 8:
        _response(
            game,
            c,
            identity,
            meta["listen_choice"],
            meta["listen_event"],
            value.counterpart,
            "oldgen_listen",
        )
    return value


def prove_unmark(
    game: GameService, c: Connection, state: GameState, owner: int, token: str
) -> None:
    actor = current_ref(state, owner)
    _oldgen(game, c, state, actor, rules.RULE)
    if token not in {x[0] for x in rules.marked_maxims(state, owner)}:
        raise WorkflowError("Unmark only an actual marked current chosen base maxim")


def _maxim(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Maxim:
    value = rules.get(state, identity)
    if value.advice:
        advice = prove_advice(game, c, state, value.advice)
        original = _record(state, rules.Maxim, identity)
        if advice.maxim != value.id or original not in rules.records(
            _history(c, game, value.event), rules.Maxim
        ):
            raise WorkflowError("Recover the exact original authored one-use maxim")
        advice_rewrites = tuple(
            x
            for x in rules.records(state, rules.AdviceMaximRewrite)
            if x.owner == value.owner and x.maxim == value.id
        )
        if advice_rewrites:
            from girlframe.services.m3_oldgen_sex import prove_maxim_rewrite

            latest_advice = advice_rewrites[-1]
            prove_maxim_rewrite(
                game,
                c,
                state,
                int(value.owner.entity),
                value.id,
                latest_advice.after,
                latest_advice.event,
            )
    else:
        _oldgen(game, c, state, value.owner, rules.RULE)
        rewrites = tuple(
            x
            for x in rules.records(state, rules.MaximRewrite)
            if x.owner == value.owner and x.slot == value.slot
        )
        if rewrites:
            from girlframe.services.m3_oldgen_sex import prove_maxim_rewrite

            latest = rewrites[-1]
            prove_maxim_rewrite(
                game,
                c,
                state,
                int(latest.owner.entity),
                "oldgen:" + str(latest.slot),
                latest.after,
                latest.event,
            )
    return value


class OldgenService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def record_poor(
        self, viewer: GuildViewer, key: str, maxim: str, channel: int, expected: int, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual rejection and how it actually went poorly")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _maxim(self.game, c, state, maxim)
            advice = prove_advice(self.game, c, state, value.advice or "")
            cast = _cast(self.game, c, state, channel)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or not value.high
                or viewer.user_id != advice.handler
                or state.handler != advice.handler
                or cast.facilitator != advice.handler
                or not all(
                    any(x.actor == ref for x in cast.roles) for ref in (value.owner, value.subject)
                )
            ):
                raise WorkflowError(
                    "Only this actual original Handler records the genuine high-maxim outcome"
                )
            event, identity = str(uuid4()), str(uuid4())
            rules.put(
                state,
                rules.PoorOutcome(
                    id=identity,
                    maxim=maxim,
                    handler=viewer.user_id,
                    cast=cast,
                    event=event,
                    account=account,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.oldgen_poor_outcome",
                state,
                event_id=event,
                poor=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.oldgen_poor_outcome",
            dict(maxim=maxim, channel=channel, expected=expected, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer, rules.ADVICE),
        )

    def use(
        self,
        viewer: GuildViewer,
        key: str,
        maxim: str,
        subject: ActorRef,
        kind: Literal["reinforce", "reject"],
        channel: int,
        expected: int,
        account: str,
        *,
        tag: str = "",
        replaced: str | None = None,
        name: str = "",
        poor: str | None = None,
    ) -> dict[str, Any]:
        if (
            not account.strip()
            or len(account) > 1200
            or kind not in ("reinforce", "reject")
            or (kind == "reinforce" and (tag or replaced or name or poor))
            or (kind == "reject" and bool(tag.strip()) == bool(replaced))
            or (replaced is None and (name or poor))
        ):
            raise WorkflowError("Record actual maxim relevance and exactly its printed consequence")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _maxim(self.game, c, state, maxim)
            first = _native(self.game, c, state, value.owner)
            other = _native(self.game, c, state, subject)
            cast = _cast(self.game, c, state, channel)
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or first.controller != viewer.user_id
                or value.owner == subject
                or not all(
                    any(x.actor == ref and x.controller == human for x in cast.roles)
                    for ref, human in ((value.owner, viewer.user_id), (subject, other.controller))
                )
            ):
                raise WorkflowError(
                    "Use this actual original owner's maxim and other Girl in the real scene"
                )
            if poor:
                fact = _record(state, rules.PoorOutcome, poor)
                born = _history(c, self.game, fact.event)
                advice = prove_advice(self.game, c, state, value.advice or "")
                _audit(self.game, c, fact.event, "m3.oldgen_poor_outcome", fact.handler)
                if (
                    fact not in rules.records(born, rules.PoorOutcome)
                    or fact.maxim != value.id
                    or fact.handler != advice.handler
                ):
                    raise WorkflowError(
                        "Recover the actual original Handler's exact rejected/poor outcome"
                    )
            event, identity = str(uuid4()), str(uuid4())
            use = rules.Use(
                id=identity,
                maxim=value.id,
                owner=value.owner,
                subject=subject,
                kind=kind,
                event=event,
                account=account,
                tag=identity if tag else None,
                replaced=replaced,
                replacement=replaced,
                poor=poor,
            )
            from girlframe.services.m2_choices import ChoiceEngine

            rules.mark(
                state, value, use, name=name, duplicates=ChoiceEngine(self.game).duplicate_labels()
            )
            if tag:
                state = give_tag(
                    state,
                    profiles(c, self.store.campaign_id),
                    subject,
                    value.owner,
                    tag.strip(),
                    identity,
                    event,
                    tuple(sorted({x.controller for x in cast.roles})),
                )
            self.game.event(
                c, viewer.user_id, key, "m3.oldgen_maxim_used", state, event_id=event, use=identity
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.oldgen_maxim_used",
            dict(
                maxim=maxim,
                subject=subject.model_dump(mode="json"),
                kind=kind,
                channel=channel,
                expected=expected,
                account=account,
                tag=tag,
                replaced=replaced,
                name=name,
                poor=poor,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(
                self.game,
                c,
                viewer,
                rules.ADVICE if maxim.startswith("oldgen-maxim:") else rules.RULE,
            ),
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            try:
                cast = _cast(self.game, c, state, channel)
            except WorkflowError:
                cast = None
            subjects = []
            for role in cast.roles if cast is not None else ():
                if role.actor.kind != "pilot":
                    continue
                actual = _native(self.game, c, state, role.actor)
                subjects.append(dict(ref=role.actor.model_dump(mode="json"), label=actual.label))
            values = [
                x for sheet in state.sheets.values() for x in rules.base_maxims(state, sheet.owner)
            ] + [rules.get(state, x.id) for x in rules.records(state, rules.Maxim)]
            from girlframe.services.m3_learned_plays import available

            own = state.sheets.get(str(viewer.user_id))
            lesson = (
                available(self.game, c, state, current_ref(state, viewer.user_id), rules.ADVICE)
                if own
                and own.character_id
                and not (own.girl == "OLDGEN" and has_rule(own, rules.ADVICE, "OLDGEN"))
                else None
            )
            return dict(
                revision=state.revision,
                scene_available=cast is not None,
                can_advise=cast is not None
                and own is not None
                and (
                    own.girl == "OLDGEN"
                    and has_rule(own, rules.ADVICE, "OLDGEN")
                    or lesson is not None
                ),
                learned_advice=lesson is not None,
                subjects=subjects,
                maxims=[
                    dict(
                        id=x.id,
                        text=x.text,
                        subject=x.subject.model_dump(mode="json") if x.subject else None,
                        available=rules.available(state, x),
                    )
                    for x in values
                    if x.owner.entity == str(viewer.user_id)
                    and x.owner == current_ref(state, viewer.user_id)
                ],
                poor=[
                    dict(id=x.id, maxim=x.maxim)
                    for x in rules.records(state, rules.PoorOutcome)
                    if rules.get(state, x.maxim).owner.entity == str(viewer.user_id)
                ],
                adjudicate=[
                    dict(id=x.id, text=x.text)
                    for x in rules.records(state, rules.Maxim)
                    if cast is not None and x.high and viewer.user_id == state.handler
                ],
                history=self._tasks(c, viewer),
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _maxim(self.game, c, state, identity)
            if viewer.user_id != int(value.owner.entity):
                raise WorkflowError(
                    "Only the actual maxim owner sees necessary private replacement fields"
                )
            return dict(
                id=identity,
                revision=state.revision,
                text=value.text,
                available=rules.available(state, value),
                status="available"
                if rules.available(state, value)
                else "marked"
                if value.slot is not None
                else "used",
                subject=value.subject.model_dump(mode="json") if value.subject else None,
                replacements=[
                    dict(id=x.id, name=x.name) for x in rules.replacements(state, value.subject)
                ]
                if value.high and value.subject
                else [],
                poor=[x.id for x in rules.records(state, rules.PoorOutcome) if x.maxim == value.id],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                label="Your one-use maxim: " + rules.get(state, x.id).text,
                pending=rules.available(state, x),
                revision=state.revision,
            )
            for x in rules.records(state, rules.Maxim)
            if x.owner.entity == str(viewer.user_id)
        ]
