"""Actual awakened Dormant cost and a real required Dive keep the attack root held."""

from uuid import uuid4

import pytest
from test_battle_pipeline import dormant_source, table
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.services.inbox import InboxService
from girlframe.services.m3_battle_dormant import DormantService
from girlframe.services.onboarding import WorkflowError


def pay(service, game, work):
    data = service.get(PLAYER, work)
    return service.alter(
        PLAYER,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        data["assets"][0]["id"],
        "Actual dormant corruption of this existing Asset",
        piloting=True,
    )


def test_actual_dormant_void_is_owned_pause_safe_replay_safe_and_parent_waits(ledger, monkeypatch):
    game, worker, gateway, root, work = dormant_source(ledger, monkeypatch)
    service = DormantService(ledger, game)
    data = service.get(PLAYER, work)
    assert (
        next(x for x in InboxService(ledger).items(PLAYER) if x.identity == work).task
        == "m3_dormant"
    )
    with pytest.raises(WorkflowError):
        service.alter(
            OTHER,
            str(uuid4()),
            work,
            data["revision"],
            data["game_revision"],
            data["assets"][0]["id"],
            "Not mine",
            piloting=True,
        )
    before = state(game)
    ledger.safety(OTHER, "pause-dormant", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        pay(service, game, work)
    assert state(game) == before and game.dice.calls == 1
    ledger.safety(OTHER, "resume-dormant", ledger.status(OTHER)["revision"], pause=False)
    current = service.get(PLAYER, work)
    key = str(uuid4())
    args = (
        PLAYER,
        key,
        work,
        current["revision"],
        current["game_revision"],
        current["assets"][0]["id"],
        "Actual dormant corruption of this existing Asset",
    )
    outcome = service.alter(*args, piloting=True)
    committed = state(game).model_dump_json()
    assert service.alter(*args, piloting=True) == outcome
    assert state(game).model_dump_json() == committed
    assert outcome["phase"] == "complete"
    after = state(game)
    assert (
        sum(x.void for x in after.sheets["2"].assets)
        == sum(x.void for x in before.sheets["2"].assets) + 1
    )
    assert game.inspect(PLAYER, root)["state"] != "complete" and game.dice.calls == 1
    table(game)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_actual_close_requires_second_real_dive_roll_owned_question_and_exact_root_completion(
    ledger, monkeypatch
):
    game, worker, gateway, root, work = dormant_source(ledger, monkeypatch, close=True)
    service = DormantService(ledger, game)
    assert pay(service, game, work)["phase"] == "dive"
    data = service.get(PLAYER, work)
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            data["sheet_revision"],
            PlayInput(
                play="keep_your_head",
                parent=root,
                source_work=work,
                heat=0,
                trigger_confirmed=True,
                context="Cannot replace the mandatory Dive",
            ),
        )
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        data["sheet_revision"],
        PlayInput(
            play="dive_deep",
            parent=root,
            source_work=work,
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual forced close connection",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual connection",
    )
    identity = next(x for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "dive_effect", fields={"identity": identity.id}, text="What did you see?")
    for human in (ADMIN, PLAYER, OTHER):
        answer(
            game, human, "dive_table_answer", text="My actual source answer " + str(human.user_id)
        )
    assert (
        game.inspect(PLAYER, child)["state"] == "complete"
        and service.get(PLAYER, work)["state"] == "resolved"
    )
    assert game.inspect(PLAYER, root)["state"] != "complete"
    table(game)
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_real_dormant_threshold_conversion_retains_actual_forced_harpy_dive_debt(
    ledger, monkeypatch
):
    from test_void_service import five_no, respond

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, root, work = dormant_source(
        ledger, monkeypatch, close=True, prevoid_frame=True, girl="ALPHA"
    )
    service = DormantService(ledger, game)
    data = service.get(PLAYER, work)
    selected = next(x for x in data["assets"] if x["family"] == "frame")
    assert (
        service.alter(
            PLAYER,
            str(uuid4()),
            work,
            data["revision"],
            data["game_revision"],
            selected["id"],
            "Actual final Frame Void alteration",
            piloting=True,
        )["phase"]
        == "thresholds"
    )
    body = service.get(PLAYER, work)["body"]
    threshold = body["thresholds"][0]
    void = VoidService(ledger)
    five_no(void, threshold)
    offered = void.get(PLAYER, threshold)
    choice = offered["rebirth_choice"] | dict(
        new_identities=["Actual reborn self"], account="Actual irreversible rebirth"
    )
    respond(void, threshold, "rebirth", dict(choice=choice, account="Actual original rebirth"))
    current = service.get(PLAYER, work)
    assert current["phase"] == "dive" and current["can_act"]
    assert current["original"]["kind"] == "pilot" and current["actor"]["kind"] == "external_pilot"
    assert current["actor"] == ActorRef(
        kind="external_pilot", entity=state(game).harpy_states[-1].id
    ).model_dump(mode="json")
    assert game.inspect(PLAYER, root)["state"] != "complete" and game.dice.calls == 1
    from girlframe.services.m3_actor_plays import ActorPlayService

    service.resume_converted_role(PLAYER, str(uuid4()), work, current["revision"])
    actual = ActorRef.model_validate(current["actor"])
    actors = ActorPlayService(game)
    source = actors.preview(PLAYER, 900, actual)
    game.dice.faces = (4, 5)
    child = actors.begin(
        PLAYER,
        str(uuid4()),
        900,
        actual,
        source["actor"]["source_sha256"],
        None,
        source["cast_revision"],
        PlayInput(
            play="dive_deep",
            heat=0,
            parent=root,
            source_work=work,
            context="Actual transformed Harpy forced connection",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("erase_identity_and_table_question",),
        text="Actual source connection",
    )
    ordinary = next(x for x in state(game).harpy_states[-1].identities if not x.protected)
    answer(game, PLAYER, "dive_effect", fields={"identity": ordinary.id}, text="What remains?")
    for human in (ADMIN, PLAYER, OTHER):
        answer(game, human, "dive_table_answer", text="My actual answer " + str(human.user_id))
    assert game.inspect(PLAYER, child)["state"] == "complete"
    table(game)
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 2


def test_actual_low_dormant_rebirth_preserves_owned_nonbody_handler_play_without_successor_damage(
    ledger, monkeypatch
):
    import json

    import sqlalchemy as sa
    from test_void_service import five_no, respond

    from girlframe.database import tables as t
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, root, work = dormant_source(
        ledger, monkeypatch, close=False, prevoid_frame=True, girl="ALPHA", faces=(1, 1)
    )
    service = DormantService(ledger, game)
    source = service.get(PLAYER, work)
    selected = next(x for x in source["assets"] if x["family"] == "frame")
    assert (
        service.alter(
            PLAYER,
            str(uuid4()),
            work,
            source["revision"],
            source["game_revision"],
            selected["id"],
            "Actual final original Frame Void alteration",
            piloting=True,
        )["phase"]
        == "thresholds"
    )
    threshold = service.get(PLAYER, work)["body"]["thresholds"][0]
    void = VoidService(ledger)
    five_no(void, threshold)
    choice = void.get(PLAYER, threshold)["rebirth_choice"] | dict(
        new_identities=["Actual reborn self"], account="Actual source-proved original rebirth"
    )
    respond(
        void,
        threshold,
        "rebirth",
        dict(choice=choice, account="Actual irreversible original rebirth"),
    )
    canon = state(game)
    assert (
        "2" not in canon.sheets and canon.harpy_states[-1].origin == canon.career_archives[-1].actor
    )
    assert service.get(PLAYER, work)["state"] == "resolved"
    grant = next(x for x in canon.handler_plays if x.source_action == root)
    assert grant.nonbody_only and grant.targets == (canon.harpy_states[-1].origin,)
    handler = HandlerPlayService(ledger)
    menu = handler.get(ADMIN, grant.id)
    assert set(dict(menu["plays"])) == {"brief", "escalate", "support", "expectation"}
    with pytest.raises(WorkflowError):
        handler.submit(
            ADMIN,
            str(uuid4()),
            grant.id,
            canon.revision,
            "mess",
            Effect(
                kind="damage",
                target=canon.harpy_states[-1].origin,
                asset=json.loads(canon.career_archives[-1].sheet_json)["assets"][0]["id"],
                account="No successor damage",
            ),
        )
    before = state(game).harpy_states[-1]
    handler.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        state(game).revision,
        "brief",
        Effect(
            kind="brief",
            account="Actual source-scoped tactical information after the original assault",
        ),
    )
    assert state(game).harpy_states[-1] == before
    assert game.inspect(PLAYER, root)["state"] == "complete" and game.dice.calls == 1
    with ledger.engine.connect() as c:
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        ended = (
            c.execute(
                sa.select(choices).where(
                    choices.c.action_id == root, choices.c.kind == "battle_low_damage"
                )
            )
            .mappings()
            .one()
        )
        assert ended["state"] == "completed_original_ended"
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(responses)
                .where(responses.c.choice_id == ended["id"])
            )
            == 0
        )
        assert json.loads(ended["body_json"])["actor"] == before.origin.model_dump(mode="json")
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
