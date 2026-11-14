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
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
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
    # The independent source-registry release gate remains authoritative.
    return True


def authorize_response(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=True)
    meta = action["data"].get("mockingbird", {})
    if meta.get("play") not in (PERSON, SEX) or viewer.user_id not in meta.get("table", ()):
        raise WorkflowError("Only the original source-table human owns this Mockingbird response")
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if receipt is None or json.loads(receipt) != action["data"].get("receipt"):
        raise WorkflowError("Recover this original Play's actual immutable receipt")
    from girlframe.services.m3_mockingbird_effects import source_trigger

    source_trigger(
        game, c, action, load_state(c, game.store.campaign_id), handler_required=meta["play"] == SEX
    )


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
        or not _owned_trigger_rule(game, c, state, value)
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
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        if value.play != SEX or len(value.parties) != 1:
            raise WorkflowError("Use the exact actual psychic Sex source")
        prove_source_link(
            game,
            c,
            state,
            value.changeling_source,
            value.id,
            value.actor,
            value.parties[0].actor,
            PLAY_RULES[value.play],
        )
    if value.bonded_source is not None:
        from girlframe.services.m3_bonded import prove_delegation

        prove_delegation(
            game,
            c,
            state,
            value.bonded_source,
            value.id,
            value.actor,
            value.parties[0].actor,
            PLAY_RULES[value.play],
        )
        born = (
            next((x for x in source.mockingbird.triggers if x.id == value.id), None)
            if source
            else None
        )
        if born is None or born.bonded_source != value.bonded_source:
            raise WorkflowError("Preserve the immutable original borrowed Sex source")
    if (
        event is None
        or event["kind"] != "m3.mockingbird_trigger"
        or event["actor_id"] != str(viewer.user_id)
        or source is None
        or not any(
            x.id == value.id
            and x.actor == actor
            and x.bonded_source == value.bonded_source
            and x.learned_source == value.learned_source
            and x.learned_sex_source == value.learned_sex_source
            for x in source.mockingbird.triggers
        )
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
    if prepared.play == SEX:
        from girlframe.engine.m3_handler_consequences import active_handler
        from girlframe.engine.m3_mockingbird_sex import assets as counterpart_assets

        if judge is None and active_handler(state) is None:
            raise WorkflowError(
                "Establish the actual fictional Handler for the printed "
                "conditional consequence first"
            )
        primary = resolve(state, value.parties[0].actor, bound, require_current_profile=False)
        if primary.rules not in (
            "handler",
            "director",
            "handler_girl",
            "npc",
        ) and not counterpart_assets(state, primary.ref):
            raise WorkflowError(
                "This actual counterpart needs its real Void target resources before rolling"
            )
    from girlframe.services.m3_learned_bonded_delegation import lesson_id

    parent_lesson = lesson_id(state, value.bonded_source)
    return (
        dict(
            actor=actor.model_dump(mode="json"),
            trigger=value.id,
            play=prepared.play,
            parties=[x.model_dump(mode="json") for x in value.parties],
            cast=cast.model_dump(mode="json"),
            cast_sha256=fingerprint(cast),
            table=sorted(
                {x.controller for x in cast.roles}
                | ({cast.facilitator} if cast.facilitator else set())
            ),
            applied=False,
            phase="rolled",
            judge=judge.model_dump(mode="json") if judge else None,
            judge_controller=judge_controller,
            judge_source=judge_source,
            appointment=appointment,
            followups=[],
        )
        | (
            {"learned_sex_source": value.learned_sex_source}
            if value.learned_sex_source is not None
            else {}
        )
        | ({"learned_source": value.learned_source} if value.learned_source is not None else {})
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | ({"bonded_lesson": parent_lesson} if parent_lesson is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any]) -> None:
    """Bind only the explicit learned or delegated source after its Action was inserted."""
    from girlframe.services.m3_learned_bonded_delegation import lesson_id

    meta = action["data"]["mockingbird"]
    if meta.get("learned_sex_source") is None and meta.get("bonded_source") is None:
        return
    value = _trigger(state, meta["trigger"])
    if meta.get("bonded_source") is not None:
        from girlframe.engine import m3_bonded as bonded

        parent = bonded.get(state, meta["bonded_source"])
        if (
            value.bonded_source != parent.id
            or parent.actor != value.actor
            or parent.route != "delegated"
            or parent.phase != "bound"
            or parent.delegated_rule != PLAY_RULES[value.play]
            or not value.parties
            or value.parties[0].actor != parent.target
            or parent.learned_source != meta.get("bonded_lesson")
            or value.learned_sex_source is not None
            or value.changeling_source is not None
            or not any(
                x.source == parent.id
                and x.session == value.id
                and x.actor == value.actor
                and x.target == parent.target
                and x.rule == parent.delegated_rule
                for x in bonded.records(state, bonded.Delegation)
            )
        ):
            raise WorkflowError("Bind only the exact genuine original Pair-rule child")
    if (
        value.play != SEX
        or value.state != "ready"
        or value.action is not None
        or value.learned_sex_source != meta.get("learned_sex_source")
        or (
            meta.get("bonded_lesson") is not None
            and (
                value.bonded_source is None
                or value.learned_sex_source is not None
                or lesson_id(state, value.bonded_source) != meta["bonded_lesson"]
            )
        )
        or action["data"]["prepared"].get("source_work") != value.id
        or str(action["actor_id"]) != value.actor.entity
    ):
        raise WorkflowError("Bind only this exact actual accepted intimacy source Action")
    state.mockingbird = state.mockingbird.model_copy(
        update={
            "triggers": tuple(
                x.model_copy(update=dict(action=action["id"])) if x.id == value.id else x
                for x in state.mockingbird.triggers
            )
        }
    )


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_battle import _cast

    meta = action["data"]["mockingbird"]
    value = _trigger(state, meta["trigger"])
    ref = ActorRef.model_validate(meta["actor"])
    current = _cast(game, c, state, int(action["channel_id"]))
    if (
        value.state != "ready"
        or value.actor != ref
        or fingerprint(current) != meta["cast_sha256"]
        or not _owned_trigger_rule(game, c, state, value, action)
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
        "mockingbird_redirect_handler_void",
        "mockingbird_redirect_handler_girl_void",
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
        "mockingbird_redirect_handler_void",
        "mockingbird_redirect_handler_girl_void",
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
    from girlframe.services.m3_mockingbird_effects import synchronize as synchronize_effects

    synchronize_effects(game, c, action, event)

    if action["data"].get("play") == SEX:
        state = load_state(c, game.store.campaign_id)
        source = _trigger(state, action["data"]["mockingbird"]["trigger"])
        if source.changeling_source is not None:
            from girlframe.services.m3_changeling_sex import synchronize_session

            synchronize_session(game, c, state, source.id, event)


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
        *,
        primary: ActorRef | None = None,
        bonded_source: str | None = None,
        changeling_source: str | None = None,
        learned_source: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            load_registry().require_available(PLAY_RULES[play])

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast
            from girlframe.services.m3_enforcement_initiative import _known_target

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, actor, bound, require_current_profile=False)
            if learned_source is not None and (
                play != SEX
                or not targets
                or bonded_source is not None
                or changeling_source is not None
            ):
                raise WorkflowError("Use one actual learned source and its real counterparts")
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import admit_contact

                if play != SEX or len(targets) != 1 or bonded_source is not None:
                    raise WorkflowError("Use a genuine single original psychic Sex counterpart")
                admit_contact(
                    self.game, c, state, actor, targets[0], PLAY_RULES[play], changeling_source
                )
            if (
                actual.controller != viewer.user_id
                or not _owned_source_rule(
                    self.game,
                    c,
                    state,
                    actor,
                    play,
                    targets,
                    bonded_source,
                    lesson_id=learned_source,
                )
                or not targets
                or len(set(targets)) != len(targets)
                or actor in targets
                or not account.strip()
                or len(account) > 1200
                or not all(any(x.actor == ref for x in cast.roles) for ref in (actor, *targets))
                or not all(
                    _known_target(
                        state,
                        actor,
                        ref,
                        resolve(state, ref, bound, require_current_profile=False).controller,
                    )
                    for ref in targets
                )
            ):
                raise WorkflowError(
                    "Declare the actual owned printed trigger with original scene counterparts"
                )
            ordered = targets
            if play == SEX:
                if (
                    primary is not None
                    and primary not in targets
                    or len(targets) > 1
                    and primary is None
                ):
                    raise WorkflowError(
                        "Choose the actual primary counterpart explicitly "
                        "for this group interaction"
                    )
                if primary is not None:
                    ordered = (primary, *(x for x in targets if x != primary))
            elif primary is not None:
                raise WorkflowError(
                    "A primary intimacy counterpart belongs only to this actual Play"
                )
            if bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded

                parent = bonded.get(state, bonded_source)
                if ordered[0] != parent.target or any(
                    not any(role.actor == ref for role in parent.cast.roles) for ref in ordered
                ):
                    raise WorkflowError("Keep the original parent counterpart primary and cast")
            parties = tuple(
                Party(
                    actor=ref,
                    controller=resolve(state, ref, bound, require_current_profile=False).controller,
                    label=resolve(state, ref, bound, require_current_profile=False).label,
                )
                for ref in ordered
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
            lesson = _person_lesson(self.game, c, state, actor) if play == PERSON else None
            value = Trigger(
                id=identity,
                learned_source=lesson.id if lesson else None,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
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
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_trigger_invitation

                link = reserve_trigger_invitation(self.game, c, state, value, learned_source)
                value = value.model_copy(update=dict(learned_sex_source=link))
                if cast not in state.scene_casts:
                    state.scene_casts.append(cast)
            state.mockingbird = state.mockingbird.model_copy(
                update={"triggers": (*state.mockingbird.triggers, value)}
            )
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(
                    self.game, c, state, changeling_source, value.id, PLAY_RULES[play], event
                )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import bind_delegation

                bind_delegation(
                    self.game, c, state, bonded_source, identity, PLAY_RULES[play], event
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
            )
            | ({"learned_source": learned_source} if learned_source is not None else {})
            | ({"primary": primary.model_dump(mode="json")} if primary is not None else {})
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def withdraw(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        """Withdraw only an unrolled technical proposal; no other human's answer is supplied."""

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = _trigger(state, identity)
            actual = c.execute(
                sa.select(t.events.c.actor_id, t.events.c.kind, t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            ).first()
            if (
                value.state not in ("ready", "proposed")
                or actual is None
                or actual.kind != "m3.mockingbird_trigger"
                or actual.actor_id != str(viewer.user_id)
                or json.loads(actual.payload_json).get("trigger") != identity
            ):
                raise WorkflowError(
                    "Only the original author can withdraw this unrolled factual proposal"
                )
            actions = t.m2["m2_actions"]
            if c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    sa.func.json_extract(actions.c.body_json, "$.mockingbird.trigger") == identity,
                    actions.c.state != "aborted",
                )
            ):
                raise WorkflowError(
                    "Recover/cancel the actual prepared Play before withdrawing its source"
                )
            event = str(uuid4())
            from girlframe.services.m3_required_mockingbird import withdraw_link

            withdraw_link(self.game, c, state, value, event)
            state.mockingbird = state.mockingbird.model_copy(
                update={
                    "triggers": tuple(
                        x.model_copy(update={"state": "withdrawn"}) if x.id == identity else x
                        for x in state.mockingbird.triggers
                    )
                }
            )
            if value.learned_sex_source is not None:
                from girlframe.services.m3_learned_sex import withdraw_invitation

                withdraw_invitation(self.game, c, state, value, event)
            from girlframe.services.m3_bonded_delegation_release import release_mockingbird

            release_mockingbird(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mockingbird_trigger_withdrawn",
                state,
                event_id=event,
                trigger=identity,
            )
            return dict(id=identity, state="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.mockingbird_trigger_withdrawn",
            dict(id=identity),
            operation,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
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
            from girlframe.services.m3_learned_sex import record_trigger_consent

            record_trigger_consent(self.game, c, state, value, accept, event)
            if not accept:
                from girlframe.services.m3_bonded_delegation_release import release_mockingbird

                release_mockingbird(self.game, c, state, identity, viewer.user_id, event)
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
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
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

    def preview(
        self,
        viewer: GuildViewer,
        channel: int,
        actor: ActorRef,
        *,
        learned_source: str | None = None,
    ) -> dict[str, Any]:
        from girlframe.services.m3_battle import _cast
        from girlframe.services.m3_enforcement_initiative import _known_target

        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            actual = resolve(state, actor, bound, require_current_profile=False)
            if actual.controller != viewer.user_id or not any(x.actor == actor for x in cast.roles):
                raise WorkflowError("Choose your actual owned original role in this scene")
            from girlframe.services.m3_learned_sex import admit_offer

            learned_sex = admit_offer(self.game, c, state, actor, rules.SEX, learned_source)
            if learned_source is not None and not learned_sex:
                raise WorkflowError("Reopen your actual available intimacy lesson")
            plays = []
            for play, rule in PLAY_RULES.items():
                try:
                    load_registry().require_available(rule)
                except ValueError:
                    continue
                if (
                    (play == SEX and learned_sex)
                    or _permanent_rule(state, actor, play)
                    or (play == PERSON and _person_lesson(self.game, c, state, actor) is not None)
                ):
                    plays.append(play)
            return dict(
                actor=actor.model_dump(mode="json"),
                plays=plays,
                learned_sex=learned_sex,
                learned_person=_person_lesson(self.game, c, state, actor) is not None,
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
                    and _known_target(state, actor, role.actor, role.controller)
                ],
                cast_revision=cast.revision,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        from girlframe.services.m3_learned_sex import cancelled

        for value in state.mockingbird.triggers:
            from girlframe.services.m3_learned_bonded_delegation import lesson_id

            if cancelled(
                self.game,
                c,
                state,
                value.learned_sex_source or lesson_id(state, value.bonded_source),
            ):
                continue
            if value.state in ("started", "complete", "declined", "withdrawn"):
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
                from girlframe.services.m3_learned_bonded_delegation import lesson_id
                from girlframe.services.m3_learned_sex import cancelled
                from girlframe.services.m3_learned_sex import prove as prove_sex

                if trigger.learned_sex_source is not None:
                    prove_sex(self.game, c, state, trigger.learned_sex_source)
                return dict(
                    id=identity,
                    kind="mockingbird_trigger",
                    lesson_cancelled=cancelled(
                        self.game,
                        c,
                        state,
                        trigger.learned_sex_source or lesson_id(state, trigger.bonded_source),
                    ),
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
        if body.get("kind") not in (
            "mockingbird_handler_girl_void",
            "mockingbird_redirect_handler_girl_void",
        ):
            continue
        episode = next((x for x in state.handler_girl_void if x.work == body["id"]), None)
        if episode and episode.phase == "allure" and episode.source_event == event:
            finish_initial_allure(game, c, body["id"], event, viewer, key)
    current = game.action(c, action["id"])
    action.clear()
    action.update(current)


def _owned_source_rule(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    play: str,
    targets: tuple[ActorRef, ...],
    bonded_source: str | None,
    *,
    lesson_id: str | None = None,
) -> bool:
    if lesson_id is not None:
        from girlframe.services.m3_learned_sex import admit_offer

        return (
            play == SEX
            and bool(targets)
            and bonded_source is None
            and admit_offer(game, c, state, actor, rules.SEX, lesson_id)
        )
    if bonded_source is None:
        return _permanent_rule(state, actor, play) or (
            play == PERSON and _person_lesson(game, c, state, actor) is not None
        )
    if play != SEX or not targets:
        raise WorkflowError("Use this actual original Pair Sex source")
    from girlframe.services.m3_bonded import admit_delegation

    return admit_delegation(game, c, state, actor, targets[0], PLAY_RULES[play], bonded_source)


def _permanent_rule(state: GameState, actor: ActorRef, play: str) -> bool:
    """Keep actual native/permanent rights distinct from a temporary lesson."""
    if actor.kind != "pilot":
        return rules.owns(state, actor, PLAY_RULES[play])
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return False
    from girlframe.engine.m3_girl_runtime_state import has_rule

    runtime = sheet.girl_runtime
    own = sheet.model_copy(
        update={
            "girl_runtime": runtime.model_copy(update={"learned_plays": ()}) if runtime else None
        }
    )
    return has_rule(own, PLAY_RULES[play], "MOCKINGBIRD")


def _person_lesson(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> LearnedPlayUse | None:
    if _permanent_rule(state, actor, PERSON):
        return None
    from girlframe.services.m3_learned_plays import available

    return available(game, c, state, actor, rules.PERSON)


def prove_learned_trigger(
    game: "GameService",
    c: Connection,
    state: GameState,
    trigger: Trigger,
    action: dict[str, Any] | None = None,
) -> bool:
    """One real source birth and its own lesson/receipt, never generic book authority."""
    if trigger.learned_source is None:
        return False
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_learned_plays import available, prove_consumed

    original = _history(c, game, trigger.source_event)
    declared = _trigger(original, trigger.id)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == trigger.source_event,
        )
    ).first()
    lesson = available(game, c, original, trigger.actor, rules.PERSON)
    if (
        trigger.play != PERSON
        or trigger.actor.kind != "pilot"
        or trigger.bonded_source is not None
        or trigger.changeling_source is not None
        or declared.model_copy(update={"state": trigger.state, "action": trigger.action}) != trigger
        or audit is None
        or audit.kind != "m3.mockingbird_trigger"
        or audit.actor_id != trigger.actor.entity
        or json.loads(audit.payload_json).get("trigger") != trigger.id
        or lesson is None
        or lesson.id != trigger.learned_source
    ):
        raise WorkflowError("Prove the actual original conversation and exact one-use lesson")
    if action is None:
        current = available(game, c, state, trigger.actor, rules.PERSON)
        if current is None or current.id != trigger.learned_source:
            raise WorkflowError(
                "This exact conversation lesson is spent or reserved; resume its Play"
            )
        return True
    meta = action["data"].get("mockingbird", {})
    claimed = action["data"].get("learned_play", {})
    if (
        str(action["actor_id"]) != trigger.actor.entity
        or meta.get("trigger") != trigger.id
        or meta.get("learned_source") != trigger.learned_source
        or claimed.get("id") != trigger.learned_source
        or claimed.get("rule_id") != rules.PERSON
        or action["data"]["prepared"]["source_work"] != trigger.id
        or action["data"]["prepared"]["play"] != PERSON
        or trigger.action not in (None, action["id"])
    ):
        raise WorkflowError("Use the exact real conversation Action's own learning reservation")
    if action["data"].get("receipt"):
        event, _ = _roll_source(game, c, action)
        if trigger.action != action["id"] or not prove_consumed(
            game, c, state, action, rules.PERSON, event
        ):
            raise WorkflowError("Preserve this lesson's exact committed conversation receipt")
    else:
        reserved = available(game, c, state, trigger.actor, rules.PERSON, action["id"])
        if reserved is None or reserved.id != trigger.learned_source:
            raise WorkflowError("Recover this original conversation's own unrolled lesson")
    return True


def _owned_trigger_rule(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: Trigger,
    action: dict[str, Any] | None = None,
) -> bool:
    if value.learned_sex_source is not None:
        return prove_learned_sex_trigger(game, c, state, value, action)
    if value.learned_source is not None:
        return prove_learned_trigger(game, c, state, value, action)
    if value.play == PERSON:
        return _permanent_rule(state, value.actor, value.play)
    return _owned_source_rule(
        game,
        c,
        state,
        value.actor,
        value.play,
        tuple(x.actor for x in value.parties),
        value.bonded_source,
    )


def prove_learned_sex_trigger(
    game: "GameService",
    c: Connection,
    state: GameState,
    trigger: Trigger,
    action: dict[str, Any] | None = None,
) -> bool:
    """Positive actual intimacy source; Person's distinct published lesson stays unchanged."""
    if trigger.learned_sex_source is None:
        return False
    from girlframe.services.m3_learned_sex import admit_group_source, prove

    if (
        trigger.play != SEX
        or not trigger.parties
        or trigger.learned_source is not None
        or trigger.bonded_source is not None
        or trigger.changeling_source is not None
    ):
        raise WorkflowError("Preserve the exact original learned intimacy source")
    admit_group_source(
        game,
        c,
        state,
        trigger.actor,
        tuple(x.actor for x in trigger.parties),
        rules.SEX,
        trigger.learned_sex_source,
    )
    value = prove(game, c, state, trigger.learned_sex_source)
    if value.session != trigger.id:
        raise WorkflowError("Use the exact actual learned trigger")
    if action is not None and (
        value.action != action["id"]
        or action["data"].get("mockingbird", {}).get("learned_sex_source") != value.id
        or action["data"]["prepared"].get("source_work") != trigger.id
        or str(action["actor_id"]) != trigger.actor.entity
    ):
        raise WorkflowError("Keep the actual original learned intimacy Action")
    return True
