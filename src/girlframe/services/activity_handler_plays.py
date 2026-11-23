"""Preview the grounded Handler Plays supported by an Activity contribution."""

import re

from sqlalchemy import Connection

from girlframe.ai.activity_batch import BatchHandlerPlay, HandlerPlayOpportunity
from girlframe.ai.conversation import HandlerDecision, HandlerRequest
from girlframe.ai.handler_initiative import HandlerInitiative
from girlframe.ai.observation import Observation
from girlframe.engine import m3_advocate_alone
from girlframe.engine.m3_handler_character import BOOK_RULES, SHARED_PLAY_TRIGGERS
from girlframe.engine.m3_handler_play_state import BASIC, DRESS_RULE
from girlframe.services.director_context import DirectorContextService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_book_orders import active_book, private_handler_scene
from girlframe.services.m3_handler_plays import _ordinary_scene_idle, _original_scene
from girlframe.services.onboarding import WorkflowError

_BRIEF_QUESTION = re.compile(
    r"\b(?:brief|objective|scope|status|route|deadline|terms|cleared)\b", re.I
)
_SUPPORT_ARRIVAL = re.compile(
    r"\b(?:frame mechanic|frame technician|maintenance technician)\b[^.!?]{0,70}"
    r"\b(?:arrives|arrived|is here|is at|enters|steps in)\b",
    re.I,
)
_EXPECTATION = re.compile(r"\b(?:report|check in|notify)\b[^.!?]{0,70}\bbefore\b", re.I)
_DRESS_ADMISSION = re.compile(
    r"\bi (?:missed|skipped|left|signed|initiall?ed|ignored|broke)\b", re.I
)


def play_opportunities(
    context: DirectorContextService,
    c: Connection,
    scene: str,
    source: Observation,
    request: HandlerRequest,
    need: HandlerDecision,
    initiative: HandlerInitiative | None,
) -> tuple[HandlerPlayOpportunity, ...]:
    handler = request.context.actor
    policy = context.store.policy.m3_approval
    if handler is None or policy is None or "plays" not in policy.subsystems:
        return ()
    game = context.observations.game
    candidates: list[HandlerPlayOpportunity] = []

    def shared(play: BatchHandlerPlay, refs: tuple[str, ...]) -> None:
        candidates.append(
            HandlerPlayOpportunity(
                play=play,
                title=dict(BASIC)[play],
                trigger=SHARED_PLAY_TRIGGERS[play],
                report_id=source.source_id,
                source_refs=refs,
            )
        )

    try:
        _ordinary_scene_idle(c, game)
    except WorkflowError:
        idle = False
    else:
        idle = True
    if (
        idle
        and need.action == "RESPOND"
        and need.reason
        in (
            "direct_question",
            "scope_boundary",
            "known_update",
            "reviewed_urgent_report",
            "reviewed_indirect_request",
            "reviewed_follow_up",
        )
    ):
        shared_refs = {
            ref.id for ref in context._actor_references(context._current(c, scene), source.actor)
        }
        refs = tuple(ref for ref in request.context.references if ref.id in shared_refs)
        required = need.source_refs
        if set(required) <= shared_refs:
            for ref in refs:
                if ref.id in required or (
                    need.reason == "direct_question"
                    and ref.topic in ("scope", "objective", "briefing", "tactical", "status")
                    and _BRIEF_QUESTION.search(request.question)
                ):
                    shared("brief", required or (ref.id,))
                    break
            for ref in refs:
                if ref.classification == "established_world" and _SUPPORT_ARRIVAL.search(ref.text):
                    evidence = tuple(dict.fromkeys((*required, ref.id)))
                    if len(evidence) <= 3:
                        shared("support", evidence)
                    break
            if _EXPECTATION.search(request.question):
                scope = next((ref.id for ref in refs if ref.topic == "scope"), None)
                if scope:
                    evidence = tuple(dict.fromkeys((*required, scope)))
                    if len(evidence) <= 3:
                        shared("expectation", evidence)

    if initiative is None or request.playbook_profile is None:
        return tuple(candidates)
    book = request.playbook_profile.playbook
    state = load_state(c, context.store.campaign_id)
    channel = int(context.observations._scene(c, scene)["channel_id"])
    play: BatchHandlerPlay
    try:
        if (
            book == "Dogrunner"
            and idle
            and initiative.prompt in ("missed_duty", "direct_reckoning")
        ):
            if not _DRESS_ADMISSION.search(request.question):
                return tuple(candidates)
            _original_scene(c, game, state, channel, handler, source.actor, DRESS_RULE)
            play = "dress_them_down"
        elif book == "Advocate" and initiative.prompt == "room_to_speak_privately":
            if initiative.possible_play is None or not active_book(
                game, c, state, book=book, rule=m3_advocate_alone.RULE
            ):
                return tuple(candidates)
            _, girl = private_handler_scene(game, c, state, channel, handler)
            lock = game.lock(c, channel)
            if (
                girl != source.actor
                or (lock and lock["state"] != "released")
                or any(
                    x.scene == scene and x.handler == handler and x.effect is None
                    for x in m3_advocate_alone.records(state)
                )
            ):
                return tuple(candidates)
            play = "get_them_alone"
        elif book == "Frantic" and initiative.prompt == "handler_overload":
            FranticBreakdownService(context.store, game).roll_scene(
                c, state, int(handler.entity), channel
            )
            play = "break_down"
        else:
            return tuple(candidates)
    except WorkflowError:
        return tuple(candidates)
    signature = next(rule for rule in BOOK_RULES[book] if rule.kind == "Signature Play")
    candidates.append(
        HandlerPlayOpportunity(
            play=play,
            title=signature.title,
            trigger=signature.trigger,
            report_id=source.source_id,
            source_refs=(),
        )
    )
    return tuple(candidates)
