"""Owner-approved GM discretion for shared world outcomes; no fabricated player replies."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.ai.gm_outcomes import TableOutcome
from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.services.director_context import DirectorContextService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def gm_owner(state: GameState, action: dict[str, Any]) -> int:
    cast = next((x for x in state.scene_casts if x.id == action["scene_id"] and x.open), None)
    owner = cast.facilitator if cast else None
    if owner is None:
        owner = action["data"].get("battle", {}).get("procedural_gm", state.handler)
    if owner is None:
        raise WorkflowError("TABLE_GM_UNAVAILABLE: recover the actual scene GM.")
    return int(owner)


def _require(game: GameService, state: GameState, action: dict[str, Any], owner: int) -> None:
    if (
        game.store.policy.owner_table_outcomes != "gm_discretion"
        or gm_owner(state, action) != owner
    ):
        raise WorkflowError("TABLE_GM_REQUIRED: this source needs its actual GM and owner policy.")


def _supersede(
    game: GameService, c: Connection, action: dict[str, Any], kinds: tuple[str, ...]
) -> None:
    table = t.m2["m2_choices"]
    for row in game.pending(c, action["id"]):
        if row["kind"] in kinds:
            c.execute(
                table.update()
                .where(table.c.campaign_id == game.store.campaign_id, table.c.id == row["id"])
                .values(state="superseded_by_gm", revision=row["revision"] + 1)
            )


def apply_assault(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    vast: bool,
    account: str,
    event: str,
) -> None:
    from girlframe.services.m3_battle import assault_table_outcome, proved_judge

    _require(game, state, action, owner)
    proved_judge(game, c, action)
    meta = action["data"]["battle"]
    if action["data"]["play"] != "all_out_assault" or meta.get("assault_applied"):
        raise WorkflowError("TABLE_OUTCOME_CLOSED: preserve the already applied native result.")
    _supersede(game, c, action, ("battle_assault_table", "battle_gm_table"))
    meta["gm_table_outcome"] = dict(owner=owner, vast_advantage=vast, account=account, event=event)
    assault_table_outcome(game, c, state, action, vast, event)


def apply_wyvern(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    answers: dict[str, str],
    account: str,
    event: str,
) -> None:
    from girlframe.engine import m3_wyvern as rules
    from girlframe.services.m3_wyvern import _advance_exploration, prove_source

    _require(game, state, action, owner)
    source = prove_source(game, c, state, action["id"])
    if source.play != "wyvern_explore" or source.answers_closed_event or not source.unmarked_event:
        raise WorkflowError("TABLE_OUTCOME_CLOSED: use the actual open exploration answers.")
    if set(answers) != set(source.questions) or not all(
        0 < len(v.strip()) <= 1200 for v in answers.values()
    ):
        raise WorkflowError("TABLE_ANSWER_COVERAGE: answer every actual source question.")
    for question in rules.records(state, rules.Question):
        if question.id not in source.questions:
            continue
        rules.put(
            state,
            rules.Answer(
                id=str(uuid4()),
                question=question.id,
                author=owner,
                text=answers[question.id],
                event=event,
            ),
        )
        rules.put(state, question.model_copy(update={"closed_event": event}))
    rules.put(state, source.model_copy(update={"answers_closed_event": event}))
    action["data"]["wyvern"]["gm_table_outcome"] = dict(
        owner=owner, answers=answers, account=account, event=event
    )
    _supersede(game, c, action, ("wyvern_answers_done", "wyvern_gm_outcome"))
    _advance_exploration(game, c, state, action)


def table_source(
    game: GameService, c: Connection, state: GameState, scene: str, action: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    owner = gm_owner(state, action)
    _require(game, state, action, owner)
    if action["scene_id"] != scene or action["state"] in ("complete", "aborted"):
        raise WorkflowError("STALE_TABLE_SOURCE: use its actual open scene action.")
    pending = game.pending(c, action["id"])
    kinds = {r["kind"] for r in pending}
    if not kinds & {
        "battle_assault_table",
        "battle_gm_table",
        "wyvern_answers_done",
        "wyvern_gm_outcome",
    }:
        raise WorkflowError("TABLE_NOT_READY: preserve original question/actor choices first.")
    return {"action": action, "pending": pending}, str(owner)


def adjudicate(
    context: DirectorContextService,
    viewer: GuildViewer,
    key: str,
    scene: str,
    action_id: str,
    revision: int,
    decision: TableOutcome,
) -> dict[str, Any]:
    game, store = context.observations.game, context.store

    def authorize(c: Connection) -> None:
        context.observations._scope()
        context._build(c, viewer, scene, actor=None)
        game.unpaused(c)
        action = game.action(c, action_id)
        if action["data"].get("battle"):
            from girlframe.services.m3_battle import authorize as battle_authorize

            battle_authorize(game, c, viewer, action)
        elif action["data"].get("wyvern"):
            from girlframe.services.m3_wyvern import authorize as wyvern_authorize

            wyvern_authorize(game, c, viewer, action)
        else:
            raise WorkflowError("UNSUPPORTED_TABLE_SOURCE: retain the actual native table stage.")

    def operation(c: Connection) -> dict[str, Any]:
        state = load_state(c, store.campaign_id)
        action = game.action(c, action_id)
        _, owner = table_source(game, c, state, scene, action)
        if state.revision != revision or owner != str(viewer.user_id):
            raise WorkflowError("STALE_TABLE_GM: refresh the actual source GM context.")
        lock = game.lock(c, action["channel_id"])
        if not lock or lock["state"] != "held":
            raise WorkflowError("TABLE_LOCK_REQUIRED: retain the actual native scene lock.")
        game.action_characters(c, action, state)
        from girlframe.services.p1_facilitator import require_scene_clear
        from girlframe.services.p1_source_pause import require_clear

        require_scene_clear(game, c, int(action["channel_id"]), action)
        require_clear(game, c, int(action["channel_id"]), action=action)
        event = str(uuid4())
        action["data"]["response_event"] = event
        if action["data"]["play"] == "all_out_assault":
            if decision.vast_advantage is None or decision.answers:
                raise WorkflowError(
                    "TABLE_OUTCOME_SHAPE: Assault needs its actual advantage judgment."
                )
            apply_assault(
                game,
                c,
                state,
                action,
                viewer.user_id,
                decision.vast_advantage,
                decision.account,
                event,
            )
        else:
            if decision.vast_advantage is not None:
                raise WorkflowError(
                    "TABLE_OUTCOME_SHAPE: exploration needs its actual question answers."
                )
            apply_wyvern(
                game, c, state, action, viewer.user_id, decision.answers, decision.account, event
            )
        game.save_action(c, action)
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.gm_table_outcome",
            state,
            event_id=event,
            action_id=action_id,
        )
        if action["data"].get("battle"):
            from girlframe.services.m3_battle import synchronize

            synchronize(game, c, action, event, viewer, key)
        else:
            from girlframe.services.m3_wyvern import intercept_finish

            state = load_state(c, store.campaign_id)
            intercept_finish(game, c, state, action)
            game.save_action(c, action)
        return {"action_id": action_id, "state": action["state"], "gm_discretion": True}

    return store._write(
        viewer,
        key,
        "gm.table_outcome",
        {
            "scene": scene,
            "action": action_id,
            "revision": revision,
            "decision": decision.model_dump(mode="json"),
        },
        operation,
        authorize=authorize,
        auto_audit=False,
    )
