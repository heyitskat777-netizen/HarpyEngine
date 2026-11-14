"""Finite learned Bonded parent to genuine original Pair Mockingbird child binding."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_alpha_sex import Session as AlphaSession
from girlframe.engine.m3_casualty import SexSession as CasualtySession
from girlframe.engine.m3_learned_play_state import LearnedSexLink
from girlframe.engine.m3_mockingbird_state import Trigger
from girlframe.engine.m3_newgirl_sex import Session as NewgirlSession
from girlframe.engine.m3_oldgen_sex import Session as OldgenSession
from girlframe.engine.m3_princess_sex import Session as PrincessSession
from girlframe.engine.m3_stim_sex import Session as StimSession
from girlframe.engine.m3_vatgrown_plays import Session as VatgrownSession
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def lesson_id(state: GameState, parent: str | None) -> str | None:
    return rules.get(state, parent).learned_source if parent is not None else None


def binding_child(
    game: "GameService",
    c: Connection,
    state: GameState,
    parent: rules.Source,
    lesson: LearnedSexLink,
) -> (
    Trigger
    | PrincessSession
    | NewgirlSession
    | OldgenSession
    | StimSession
    | AlphaSession
    | VatgrownSession
    | CasualtySession
):
    if parent.delegated_rule == "girl.casualty.sex-play":
        from girlframe.services.m3_learned_bonded_casualty import binding_child as casualty_child

        return casualty_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.vatgrown.sex-play":
        from girlframe.services.m3_learned_bonded_vatgrown import binding_child as vatgrown_child

        return vatgrown_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.alpha.sex-play":
        from girlframe.services.m3_learned_bonded_alpha import binding_child as alpha_child

        return alpha_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.stim-blissed.sex-play":
        from girlframe.services.m3_learned_bonded_stim import binding_child as stim_child

        return stim_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.oldgen.sex-play":
        from girlframe.services.m3_learned_bonded_oldgen import binding_child as oldgen_child

        return oldgen_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.newgirl.sex-play":
        from girlframe.services.m3_learned_bonded_newgirl import binding_child as newgirl_child

        return newgirl_child(game, c, state, parent, lesson)
    if parent.delegated_rule == "girl.princess.sex-play":
        from girlframe.services.m3_learned_bonded_princess import binding_child as princess_child

        return princess_child(game, c, state, parent, lesson)
    from girlframe.services.m3_mockingbird_plays import _trigger

    links = [x for x in rules.records(state, rules.Delegation) if x.source == parent.id]
    if len(links) != 1:
        raise WorkflowError("Recover the exact original Pair-rule child binding")
    link = links[0]
    original_link = next(
        (
            x
            for x in rules.records(_history(c, game, link.event), rules.Delegation)
            if x.id == link.id
        ),
        None,
    )
    child = _trigger(state, link.session)
    original = _trigger(_history(c, game, child.source_event), child.id)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == link.event,
            )
        )
        .mappings()
        .first()
    )
    if (
        parent.route != "delegated"
        or parent.delegated_rule != "girl.mockingbird.sex-play"
        or parent.learned_source != lesson.id
        or parent.id != lesson.session
        or (link.actor, link.target, link.rule)
        != (parent.actor, parent.target, parent.delegated_rule)
        or original_link is None
        or any(
            getattr(link, x) != getattr(original_link, x)
            for x in ("id", "source", "session", "rule", "actor", "target", "event")
        )
        or child.play != "mockingbird_sex"
        or child.actor != lesson.actor
        or child.bonded_source != parent.id
        or child.learned_source is not None
        or child.learned_sex_source is not None
        or child.changeling_source is not None
        or child.source_event != link.event
        or not child.parties
        or len({x.actor for x in child.parties}) != len(child.parties)
        or any(
            x.actor == child.actor
            or not any(
                r.actor == x.actor and r.controller == x.controller for r in parent.cast.roles
            )
            for x in child.parties
        )
        or child.parties[0].actor != lesson.target
        or child.parties[0].controller != parent.controllers.get(lesson.target.token)
        or [(x.actor, x.controller) for x in child.parties]
        != [(x.actor, x.controller) for x in original.parties]
        or any(
            getattr(child, x) != getattr(original, x)
            for x in (
                "id",
                "play",
                "actor",
                "scene",
                "channel",
                "cast_sha256",
                "source_event",
                "account",
                "learned_source",
                "learned_sex_source",
                "bonded_source",
                "changeling_source",
            )
        )
        or original.action is not None
        or original.state != "proposed"
        or any(x.decision != "pending" or x.event is not None for x in original.parties)
        or audit is None
        or audit["kind"] != "m3.mockingbird_trigger"
        or audit["actor_id"] != lesson.actor.entity
        or json.loads(audit["payload_json"]).get("trigger") != child.id
    ):
        raise WorkflowError(
            "Preserve the real original Pair-rule child and independent participants"
        )
    final_answer = False
    for party in child.parties:
        if party.decision != "accepted" or party.event is None:
            raise WorkflowError("Every actual child counterpart must independently consent")
        response = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == party.event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(response["payload_json"]) if response else {}
        answered = _trigger(_history(c, game, party.event), child.id)
        if (
            response is None
            or response["kind"] != "m3.mockingbird_trigger_attested"
            or response["actor_id"] != str(party.controller)
            or payload.get("trigger") != child.id
            or payload.get("accept") is not True
            or payload.get("party") != party.actor.model_dump(mode="json")
            or party not in answered.parties
            or [(x.actor, x.controller) for x in answered.parties]
            != [(x.actor, x.controller) for x in original.parties]
            or any(x.decision not in ("pending", "accepted") for x in answered.parties)
            or any(x.decision == "accepted" and x not in child.parties for x in answered.parties)
            or any(
                getattr(answered, k) != getattr(original, k)
                for k in (
                    "actor",
                    "play",
                    "scene",
                    "channel",
                    "cast_sha256",
                    "source_event",
                    "account",
                    "bonded_source",
                    "learned_source",
                    "learned_sex_source",
                    "changeling_source",
                )
            )
            or answered.state
            != ("ready" if all(x.decision == "accepted" for x in answered.parties) else "proposed")
            or answered.action is not None
            or child.action is None
        ):
            raise WorkflowError(
                "Preserve each child's actual independent confirmation before its Action"
            )
        final_answer = final_answer or answered.parties == child.parties
    if not final_answer:
        raise WorkflowError("Recover the final all-participant acceptance before the Action")
    assert child.action is not None
    action = game.action(c, child.action)
    meta = action["data"].get("mockingbird", {})
    if (
        str(action["actor_id"]) != lesson.actor.entity
        or action["scene_id"] != child.scene
        or int(action["channel_id"]) != child.channel
        or action["data"].get("play") != child.play
        or action["data"].get("prepared", {}).get("source_work") != child.id
        or meta.get("trigger") != child.id
        or meta.get("bonded_source") != parent.id
        or meta.get("bonded_lesson") != lesson.id
        or meta.get("learned_sex_source") is not None
        or meta.get("learned_source") is not None
        or meta.get("actor") != lesson.actor.model_dump(mode="json")
        or meta.get("parties") != [x.model_dump(mode="json") for x in child.parties]
    ):
        raise WorkflowError("Bind the parent lesson only to this actual child's one Action")
    return child


def prove_effect_child(
    game: "GameService", c: Connection, state: GameState, child: Trigger, action: dict[str, Any]
) -> bool:
    """Positive canonical consumed parent proof, not a global borrowed rule flag."""
    meta = action["data"]["mockingbird"]
    identity = meta.get("bonded_lesson")
    if identity is None:
        return False
    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_learned_sex import prove

    lesson = prove(game, c, state, identity)
    if (
        child.bonded_source != lesson.session
        or lesson.rule_id != rules.SEX
        or lesson.action != action["id"]
        or lesson.roll_event is None
        or lesson.receipt_sha256 is None
        or lesson.released_event is not None
    ):
        raise WorkflowError("Use the original consumed parent lesson and this child receipt")
    parent = rules.get(state, lesson.session)
    actual = binding_child(game, c, state, parent, lesson)
    if actual != child:
        raise WorkflowError("Preserve this exact independently confirmed child")
    prove_delegation(
        game,
        c,
        state,
        parent.id,
        child.id,
        lesson.actor,
        lesson.target,
        "girl.mockingbird.sex-play",
    )
    return True
