"""Actual source conversations and individually attested Mockingbird triggers."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_mockingbird_state import (
    CAPABILITIES,
    PERSON,
    SEX,
    Conversation,
    Party,
    Trigger,
)
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

PLAY_RULES = {PERSON: rules.PERSON, SEX: rules.SEX}


def _copy(state: GameState, changed: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))


def _trigger(state: GameState, identity: str) -> Trigger:
    value = next((x for x in state.mockingbird.triggers if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Mockingbird trigger")
    return value


def _living_person(state: GameState, original: ActorRef) -> ActorRef:
    if original.kind == "pilot":
        sheet = state.sheets.get(original.entity)
        if sheet is not None and sheet.character_id == original.incarnation:
            return original
        for body in state.harpy_states:
            current = ActorRef(kind="external_pilot", entity=body.id)
            if body.alive and rules.same_person(state, original, current):
                return current
        raise ValueError("The original person ended; a successor cannot own this conversation")
    return original


def _conversation(state: GameState, action: dict[str, Any]) -> Conversation:
    value = next((x for x in state.mockingbird.conversations if x.action == action["id"]), None)
    if value is None:
        raise WorkflowError("Recover the original conversation's actual capability choice")
    return value


def _save_conversation(state: GameState, value: Conversation) -> None:
    state.mockingbird = state.mockingbird.model_copy(
        update={
            "conversations": tuple(
                value if x.id == value.id else x for x in state.mockingbird.conversations
            )
        }
    )


def sex_ready() -> bool:
    # Whole-book source remains gated until every tier and target port is validated.
    return False


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
    actor_ref: ActorRef | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_battle import _cast

    if prepared.play == SEX and not sex_ready():
        raise WorkflowError(
            "UNSUPPORTED_RULE: actual Sex Play target outcome ports remain in development"
        )
    Access(game.store).authorize(c, viewer, "plays", director_response=actor_ref is not None)
    try:
        load_registry().require_available(PLAY_RULES[prepared.play])
    except (KeyError, ValueError) as error:
        raise WorkflowError(str(error)) from None
    value = _trigger(state, prepared.source_work or "")
    actor = actor_ref or ActorRef(
        kind="pilot",
        entity=str(viewer.user_id),
        incarnation=game.character_binding(c, state, viewer.user_id, require_current_profile=False),
    )
    bound = profiles(c, game.store.campaign_id)
    actual = resolve(state, actor, bound, require_current_profile=False)
    cast = _cast(game, c, state, channel)
    if (
        value.play != prepared.play
        or value.actor != actor
        or value.channel != channel
        or value.state != "ready"
        or actual.controller != viewer.user_id
        or not rules.owns(state, actor, PLAY_RULES[prepared.play])
        or cast.id != value.scene
        or fingerprint(cast) != value.cast_sha256
        or prepared.target is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.target_actor not in (None, value.parties[0].actor)
    ):
        raise WorkflowError("Use the actual owned ready trigger in its unchanged original scene")
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    if (
        event is None
        or event["kind"] != "m3.mockingbird_trigger"
        or event["actor_id"] != str(viewer.user_id)
        or source is None
        or not any(x.id == value.id and x.actor == actor for x in source.mockingbird.triggers)
    ):
        raise WorkflowError(
            "SOURCE_MOCKINGBIRD_TRIGGER_MISSING: recover the actual owner declaration"
        )
    table = t.m2["m2_actions"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(table.c.body_json, "$.mockingbird.trigger") == value.id,
            table.c.state != "aborted",
        )
    ):
        raise WorkflowError("Resume this actual trigger's existing Play; it cannot be rolled twice")
    for party in value.parties:
        counterpart = resolve(state, party.actor, bound, require_current_profile=False)
        if prepared.play == SEX and (
            counterpart.ref.kind == "external_pilot" and counterpart.girl != "harpy"
        ):
            raise WorkflowError(
                "UNSUPPORTED_RULE: establish this original role's actual Void target runtime first"
            )
        if counterpart.controller != party.controller or not counterpart.alive:
            raise WorkflowError("Recover the actual original interlocutor and their controller")
    from girlframe.services.m3_battle import _scene_judge
    from girlframe.services.m3_medical import MedicalService

    judge, judge_controller, judge_source = _scene_judge(game, c, state, cast)
    _, appointment = MedicalService(game.store)._handler(c)
    return dict(
        actor=actor.model_dump(mode="json"),
        trigger=value.id,
        play=prepared.play,
        parties=[x.model_dump(mode="json") for x in value.parties],
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
        ),
        applied=False,
        phase="rolled",
        judge=judge.model_dump(mode="json") if judge else None,
        judge_controller=judge_controller,
        judge_source=judge_source,
        appointment=appointment,
        followups=[],
    )


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_battle import _cast

    meta = action["data"]["mockingbird"]
    value = _trigger(state, meta["trigger"])
    ref = ActorRef.model_validate(meta["actor"])
    current = _cast(game, c, state, int(action["channel_id"]))
    if (
        value.state != "ready"
        or fingerprint(current) != meta["cast_sha256"]
        or not rules.owns(state, ref, PLAY_RULES[value.play])
    ):
        raise WorkflowError("STALE_MOCKINGBIRD: recover the actual trigger, rule and original cast")
    state.mockingbird = state.mockingbird.model_copy(
        update={
            "triggers": tuple(
                x.model_copy(update={"state": "started", "action": action["id"]})
                if x.id == value.id
                else x
                for x in state.mockingbird.triggers
            )
        }
    )


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"]["mockingbird"]["play"] == PERSON:
        game.request(c, action, int(action["actor_id"]), "mockingbird_person_capabilities")
    else:
        from girlframe.services.m3_mockingbird_sex import results as sex_results

        sex_results(game, c, state, action)


def _finish(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    action["data"]["mockingbird"]["applied"] = True
    state.mockingbird = state.mockingbird.model_copy(
        update={
            "triggers": tuple(
                x.model_copy(update={"state": "complete"})
                if x.id == action["data"]["mockingbird"]["trigger"]
                else x
                for x in state.mockingbird.triggers
            )
        }
    )
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    else:
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).finish(c, state, action)


def _party(action: dict[str, Any], ref: ActorRef) -> Party:
    return next(
        Party.model_validate(x)
        for x in action["data"]["mockingbird"]["parties"]
        if x["actor"] == ref.model_dump(mode="json")
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if row["kind"].startswith("mockingbird_sex_") or row["kind"] in (
        "mockingbird_handler_void",
        "mockingbird_handler_girl_void",
    ):
        from girlframe.services.m3_mockingbird_sex import apply as apply_sex

        apply_sex(game, c, state, action, row, answer)
        return
    meta = action["data"]["mockingbird"]
    actor = ActorRef.model_validate(meta["actor"])
    event = action["data"]["response_event"]
    parties = tuple(Party.model_validate(x) for x in meta["parties"])
    if row["kind"] == "mockingbird_person_capabilities":
        if (
            str(row["actor_id"]) != str(action["actor_id"])
            or answer.denied
            or answer.fields
            or answer.text
            or answer.flag is not None
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError("The actual speaker chooses only their printed capabilities")
        changed, conversation = rules.choose_capabilities(
            state,
            actor,
            action["id"],
            event,
            action["data"]["result"]["tier"],
            answer.options,
            parties,
        )
        _copy(state, changed)
        if action["data"]["result"]["tier"] == "mid" or not conversation.unavailable:
            _finish(game, c, state, action)
        else:
            game.request(
                c,
                action,
                parties[0].controller,
                "mockingbird_person_tag",
                dict(giver=parties[0].actor.model_dump(mode="json")),
            )
        return
    conversation = _conversation(state, action)
    if row["kind"] == "mockingbird_person_tag":
        giver = ActorRef.model_validate(json.loads(row["body_json"])["giver"])
        if (
            str(_party(action, giver).controller) != str(row["actor_id"])
            or not answer.text.strip()
            or len(answer.text) > 120
            or answer.options
            or answer.denied
            or answer.fields
            or answer.flag is not None
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError(
                "The original interlocutor authors the actual missing-capability Tag"
            )
        conversation = conversation.model_copy(
            update={
                "giver": giver,
                "proposed_tag": answer.text,
                "agreements": tuple(
                    x.model_copy(
                        update={
                            "decision": "accepted" if x.actor == giver else "pending",
                            "event": event if x.actor == giver else None,
                        }
                    )
                    for x in parties
                ),
            }
        )
        _save_conversation(state, conversation)
        if len(parties) == 1:
            _commit_tag(game, c, state, action, conversation, event)
        else:
            for party in parties:
                if party.actor != giver:
                    game.request(
                        c,
                        action,
                        party.controller,
                        "mockingbird_person_agreement",
                        dict(party=party.actor.model_dump(mode="json")),
                    )
        return
    if row["kind"] == "mockingbird_person_agreement":
        party_ref = ActorRef.model_validate(json.loads(row["body_json"])["party"])
        if (
            str(_party(action, party_ref).controller) != str(row["actor_id"])
            or answer.flag is None
            or answer.options
            or answer.denied
            or answer.fields
            or answer.text
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError("Each actual interlocutor accepts or rejects the exact shared Tag")
        if not answer.flag:
            choices = t.m2["m2_choices"]
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.action_id == action["id"],
                    choices.c.kind == "mockingbird_person_agreement",
                    choices.c.state == "pending",
                )
                .values(state="superseded", revision=choices.c.revision + 1)
            )
            conversation = conversation.model_copy(update={"proposed_tag": "", "agreements": ()})
            _save_conversation(state, conversation)
            assert conversation.giver is not None
            game.request(
                c,
                action,
                _party(action, conversation.giver).controller,
                "mockingbird_person_tag",
                dict(giver=conversation.giver.model_dump(mode="json")),
            )
        else:
            conversation = conversation.model_copy(
                update={
                    "agreements": tuple(
                        x.model_copy(update={"decision": "accepted", "event": event})
                        if x.actor == party_ref
                        else x
                        for x in conversation.agreements
                    )
                }
            )
            _save_conversation(state, conversation)
            if all(x.decision == "accepted" for x in conversation.agreements):
                assert conversation.giver is not None
                game.request(
                    c,
                    action,
                    _party(action, conversation.giver).controller,
                    "mockingbird_person_commit",
                )
        return
    if row["kind"] == "mockingbird_person_commit":
        if (
            answer.flag is not True
            or answer.options
            or answer.denied
            or answer.fields
            or answer.text
            or answer.member is not None
            or answer.number is not None
        ):
            raise WorkflowError("The actual Tag author explicitly commits the agreed Tag")
        _commit_tag(game, c, state, action, conversation, event)
        return
    raise WorkflowError("Use the exact original Mockingbird owned response")


def _commit_tag(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: Conversation,
    event: str,
) -> None:
    assert value.giver is not None
    if not all(x.decision == "accepted" for x in value.agreements):
        raise WorkflowError("Every actual original interlocutor must agree to the exact Tag")
    identity = "mock:" + value.id
    _copy(
        state,
        rules.give_tag(
            state,
            profiles(c, game.store.campaign_id),
            value.actor,
            value.giver,
            value.proposed_tag,
            identity,
            event,
            tuple(action["data"]["participants"]),
        ),
    )
    _save_conversation(state, value.model_copy(update={"tag": identity}))
    _finish(game, c, state, action)


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    if row["kind"].startswith("mockingbird_sex_") or row["kind"] in (
        "mockingbird_handler_void",
        "mockingbird_handler_girl_void",
    ):
        from girlframe.services.m3_mockingbird_sex import projection as project_sex

        return project_sex(game, c, state, action, row)
    meta = action["data"]["mockingbird"]
    level = action["data"]["result"]["tier"]
    if row["kind"] == "mockingbird_person_capabilities":
        return dict(
            minimum=0 if level == "low" else 3 if level == "mid" else 4,
            maximum=2 if level == "low" else 3 if level == "mid" else 4,
            capabilities=list(CAPABILITIES),
            extras={
                ActorRef.model_validate(x["actor"]).token: list(
                    rules.starry_capabilities(
                        state,
                        ActorRef.model_validate(meta["actor"]),
                        ActorRef.model_validate(x["actor"]),
                    )
                )
                for x in meta["parties"]
            },
        )
    value = _conversation(state, action)
    return dict(
        unavailable=list(value.unavailable),
        proposed_tag=value.proposed_tag,
        all_agreed=all(x.decision == "accepted" for x in value.agreements),
    )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_mockingbird_void import synchronize as synchronize_void

    synchronize_void(game, c, action, event)


class MockingbirdService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        play: Literal["mockingbird_person", "mockingbird_sex"],
        targets: tuple[ActorRef, ...],
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            load_registry().require_available(PLAY_RULES[play])

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, actor, bound, require_current_profile=False)
            if (
                actual.controller != viewer.user_id
                or not rules.owns(state, actor, PLAY_RULES[play])
                or not targets
                or len(set(targets)) != len(targets)
                or actor in targets
                or not account.strip()
                or len(account) > 1200
                or not all(any(x.actor == ref for x in cast.roles) for ref in (actor, *targets))
            ):
                raise WorkflowError(
                    "Declare the actual owned printed trigger with original scene counterparts"
                )
            parties = tuple(
                Party(
                    actor=ref,
                    controller=resolve(state, ref, bound, require_current_profile=False).controller,
                )
                for ref in targets
            )
            if play == PERSON and any(
                not value.ended_event
                and rules.same_person(state, value.actor, actor)
                and any(
                    rules.same_person(state, party.actor, target)
                    for party in value.counterparts
                    for target in targets
                )
                for value in state.mockingbird.conversations
            ):
                raise WorkflowError(
                    "Finish the actual ongoing conversation before rolling its capabilities again"
                )
            identity, event = str(uuid4()), str(uuid4())
            value = Trigger(
                id=identity,
                play=play,
                actor=actor,
                parties=parties,
                scene=cast.id,
                channel=channel,
                cast_sha256=fingerprint(cast),
                source_event=event,
                account=account,
                state="ready" if play == PERSON else "proposed",
            )
            state.mockingbird = state.mockingbird.model_copy(
                update={"triggers": (*state.mockingbird.triggers, value)}
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_trigger",
                state,
                event_id=event,
                trigger=identity,
            )
            return dict(id=identity, state=value.state)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_trigger",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                play=play,
                targets=[x.model_dump(mode="json") for x in targets],
                account=account,
            ),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def attest(
        self, viewer: GuildViewer, key: str, identity: str, party: ActorRef, accept: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _trigger(state, identity)
            owned = next((x for x in value.parties if x.actor == party), None)
            actual = resolve(
                state, party, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                value.state != "proposed"
                or owned is None
                or owned.decision != "pending"
                or owned.controller != viewer.user_id
                or actual.controller != viewer.user_id
            ):
                raise WorkflowError(
                    "Only this original counterpart's real controller attests the actual trigger"
                )
            event = str(uuid4())
            parties = tuple(
                x.model_copy(
                    update={"decision": "accepted" if accept else "declined", "event": event}
                )
                if x.actor == party
                else x
                for x in value.parties
            )
            value = value.model_copy(
                update={
                    "parties": parties,
                    "state": "declined"
                    if not accept
                    else "ready"
                    if all(x.decision == "accepted" for x in parties)
                    else "proposed",
                }
            )
            state.mockingbird = state.mockingbird.model_copy(
                update={
                    "triggers": tuple(
                        value if x.id == identity else x for x in state.mockingbird.triggers
                    )
                }
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_trigger_attested",
                state,
                event_id=event,
                trigger=identity,
                party=party.model_dump(mode="json"),
                accept=accept,
            )
            return dict(id=identity, state=value.state)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_trigger_attested",
            dict(id=identity, party=party.model_dump(mode="json"), accept=accept),
            operation,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
            auto_audit=False,
        )

    def preview(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        from girlframe.services.m3_battle import _cast

        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            actual = resolve(state, actor, bound, require_current_profile=False)
            if actual.controller != viewer.user_id or not any(x.actor == actor for x in cast.roles):
                raise WorkflowError("Choose your actual owned original role in this scene")
            plays = []
            for play, rule in PLAY_RULES.items():
                try:
                    load_registry().require_available(rule)
                except ValueError:
                    continue
                if rules.owns(state, actor, rule):
                    plays.append(play)
            return dict(
                actor=actor.model_dump(mode="json"),
                plays=plays,
                sheet_revision=state.sheets[actor.entity].revision
                if actor.kind == "pilot"
                else None,
                heat=actual.heat,
                identities=[x.model_dump(mode="json") for x in actual.identities if not x.marked],
                targets=[
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        token=role.actor.token,
                        label=resolve(
                            state, role.actor, bound, require_current_profile=False
                        ).label,
                    )
                    for role in cast.roles
                    if role.actor != actor
                ],
                cast_revision=cast.revision,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in state.mockingbird.triggers:
            if value.state in ("started", "complete", "declined"):
                continue
            try:
                owner = resolve(
                    state,
                    value.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
            except ValueError:
                if any(x.actor == value.actor for x in state.career_archives):
                    continue
                raise
            own = owner == viewer.user_id
            parties = [
                x
                for x in value.parties
                if x.controller == viewer.user_id and x.decision == "pending"
            ]
            if own or parties:
                result.append(
                    dict(
                        id=value.id,
                        kind="mockingbird_trigger",
                        state=value.state,
                        actionable=bool(own and value.state == "ready" or parties),
                    )
                )
        for conversation in state.mockingbird.conversations:
            if conversation.ended_event:
                continue
            try:
                owner = resolve(
                    state,
                    conversation.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
            except ValueError:
                actual_harpy = next(
                    (
                        x
                        for x in state.harpy_states
                        if x.alive
                        and rules.same_person(
                            state, conversation.actor, ActorRef(kind="external_pilot", entity=x.id)
                        )
                    ),
                    None,
                )
                if actual_harpy is None:
                    continue
                owner = actual_harpy.controller
            if (
                any(x.controller == viewer.user_id for x in conversation.counterparts)
                or owner == viewer.user_id
            ):
                result.append(
                    dict(
                        id=conversation.id,
                        kind="mockingbird_conversation",
                        state="ongoing",
                        actionable=True,
                    )
                )
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            trigger = next((x for x in state.mockingbird.triggers if x.id == identity), None)
            conversation = next(
                (x for x in state.mockingbird.conversations if x.id == identity), None
            )
            if trigger:
                actual = resolve(
                    state,
                    trigger.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                own = actual.controller == viewer.user_id
                if not own and not any(x.controller == viewer.user_id for x in trigger.parties):
                    raise WorkflowError(
                        "Only actual original participants may review this private trigger"
                    )
                table = t.m2["m2_actions"]
                action = c.scalar(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        sa.func.json_extract(table.c.body_json, "$.mockingbird.trigger")
                        == identity,
                        table.c.state != "aborted",
                    )
                )
                return dict(
                    id=identity,
                    kind="mockingbird_trigger",
                    body=trigger.model_dump(mode="json"),
                    owner=own,
                    action=action,
                )
            if conversation:
                bound = profiles(c, self.store.campaign_id)
                current_actor = _living_person(state, conversation.actor)
                owner = (
                    resolve(state, current_actor, bound, require_current_profile=False).controller
                    == viewer.user_id
                )
                if not owner and not any(
                    x.controller == viewer.user_id for x in conversation.counterparts
                ):
                    raise WorkflowError(
                        "Only actual original interlocutors may review this private conversation"
                    )
                labels = {}
                for party in conversation.counterparts:
                    current_party = _living_person(state, party.actor)
                    label = resolve(
                        state, current_party, bound, require_current_profile=False
                    ).label
                    labels[party.actor.token] = label + " (" + party.actor.kind + ")"
                return dict(
                    id=identity,
                    kind="mockingbird_conversation",
                    body=conversation.model_dump(mode="json")
                    | {"allowed": list(rules.conversation_capabilities(state, conversation))},
                    owner=owner,
                    current_actor=current_actor.model_dump(mode="json"),
                    party_labels=labels,
                )
            raise WorkflowError("This original Mockingbird request is unavailable")

    def release(
        self, viewer: GuildViewer, key: str, identity: str, party: ActorRef, allow: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = next((x for x in state.mockingbird.conversations if x.id == identity), None)
            current_party = _living_person(state, party)
            actual = resolve(
                state,
                current_party,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                value is None
                or not value.low
                or value.ended_event
                or actual.controller != viewer.user_id
                or not any(
                    x.actor == party and x.controller == viewer.user_id for x in value.counterparts
                )
            ):
                raise WorkflowError(
                    "Only the actual original interlocutor allows or refuses departure"
                )
            event = str(uuid4())
            released = tuple(x for x in value.released if x != party)
            if allow:
                released = (*released, party)
            _save_conversation(
                state,
                value.model_copy(
                    update={"released": released, "release_events": (*value.release_events, event)}
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_conversation_release",
                state,
                event_id=event,
                conversation=identity,
                party=party.model_dump(mode="json"),
                allow=allow,
            )
            return dict(id=identity, allowed=allow)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_conversation_release",
            dict(id=identity, party=party.model_dump(mode="json"), allow=allow),
            operation,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
            auto_audit=False,
        )

    def end(self, viewer: GuildViewer, key: str, identity: str, actor: ActorRef) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = next((x for x in state.mockingbird.conversations if x.id == identity), None)
            current = _living_person(state, value.actor) if value else None
            if value is None or value.ended_event or current != actor:
                raise WorkflowError("Reopen the actual current conversation and original person")
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError("Only the actual speaker ends this conversation")
            rules.require_departure(state, actor, identity)
            event = str(uuid4())
            _save_conversation(state, value.model_copy(update={"ended_event": event}))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_conversation_ended",
                state,
                event_id=event,
                conversation=identity,
                original_actor=actor.model_dump(mode="json"),
            )
            return dict(id=identity, ended=True)

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_conversation_ended",
            dict(id=identity, actor=actor.model_dump(mode="json")),
            operation,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
            auto_audit=False,
        )


def post_synchronize(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    """Only after the actual owned response exists may an already-complete source coalesce."""
    from girlframe.services.m3_handler_girl_void import finish_initial_allure

    state = load_state(c, game.store.campaign_id)
    for body in action["data"]["mockingbird"].get("followups", ()):
        if body.get("kind") != "mockingbird_handler_girl_void":
            continue
        episode = next((x for x in state.handler_girl_void if x.work == body["id"]), None)
        if episode and episode.phase == "allure" and episode.source_event == event:
            finish_initial_allure(game, c, body["id"], event, viewer, key)
    current = game.action(c, action["id"])
    action.clear()
    action.update(current)
