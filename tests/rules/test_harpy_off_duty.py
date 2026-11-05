"""Harpy Off-Duty owns real hide/navigation/recovery without a ranked Cadre period."""

import json
from uuid import uuid4

import pytest
from test_harpy_actor_plays import begin, pass_tags, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_harpy_defeat import harpy, offstage_travel, update
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("faces", [(1, 1), (4, 4), (6, 6)])
def test_real_harpy_all_tiers_hide_adjust_and_repair_without_pc_resources_or_repeat_return_recovery(
    ledger, faces
):
    svc, game, cast, actor = ready(ledger, faces=faces, heat=4)
    with ledger.transaction() as c:
        canon = state(game)
        canon = update(
            canon,
            actor,
            identities=(
                HarpyIdentity(id="actual-free", name="Free", protected=True, marked=True),
                HarpyIdentity(id="actual-old-self", name="Old self", marked=True),
            ),
        )
        canon.world = canon.world.model_copy(
            update={
                "pilots": tuple(
                    x.model_copy(
                        update={
                            "assets": tuple(
                                y.model_copy(update={"damaged": True}) for y in x.assets
                            )
                        }
                    )
                    if x.id == actor.entity
                    else x
                    for x in canon.world.pilots
                )
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.existing_harpy_resources", canon)
    original = state(game)
    all_pc = {k: x.model_dump_json() for k, x in original.sheets.items()}
    action = begin(svc, actor, play="go_off_duty", context="Actual Harpy Off-Duty hide")
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    with ledger.engine.connect() as c:
        receipt = game.action(c, action)["data"]["receipt"]
    assert receipt["faces"] == list(faces) and receipt["pre_total"] == sum(faces)
    assert receipt["heat"] == 0 and game.dice.calls == 1
    names = ["Chosen self " + str(x) for x in range(7)]
    answer(
        game,
        PLAYER,
        "harpy_off_duty_hide",
        flag=True,
        fields={
            "identities": json.dumps(names),
            "navigation": "The actual owned route into Voidspace",
        },
        text="My real Harpy hides within Voidspace",
    )
    before_review = state(game)
    rest = before_review.harpy_rests[-1]
    route = next(x for x in before_review.harpy_travels if x.id == rest.route)
    assert route.state == "proposed" and route.destination is None and route.travels_frame
    assert next(x for x in before_review.world.pilots if x.id == actor.entity).assets[0].damaged
    assert game.inspect(PLAYER, action)["state"] != "complete"
    service = HarpyDefeatService(ledger, game)
    with pytest.raises(WorkflowError):
        service.review_route(
            OTHER,
            str(uuid4()),
            route.id,
            before_review.revision,
            allow=True,
            account="Not my owned review",
        )
    service.review_route(
        ADMIN,
        str(uuid4()),
        route.id,
        state(game).revision,
        allow=True,
        account="Actual source judge confirms this owned navigation",
    )
    canon = state(game)
    assert canon.harpy_rests[-1].phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert harpy(canon, actor).cell is None and harpy(canon, actor).frame_cell is None
    assert not next(x for x in canon.world.pilots if x.id == actor.entity).assets[0].damaged
    assert harpy(canon, actor).heat == 4
    assert [x.name for x in harpy(canon, actor).identities] == ["Free", *names]
    assert all(not x.marked for x in harpy(canon, actor).identities)
    assert {k: x.model_dump_json() for k, x in canon.sheets.items()} == all_pc
    assert canon.order == original.order and game.dice.calls == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert offstage_travel(canon, actor).off_duty_action == action
    returned = service.propose_route(
        PLAYER,
        str(uuid4()),
        canon.revision,
        actor,
        return_of=route.id,
        destination=(1, 1),
        account="My actual return",
        navigation="My actual return path",
    )
    # Damage while truly away is factual; returning must not repeat the recovery effect.
    # The actual stable recovery receipt cannot be issued again by a return.
    completion = canon.harpy_rests[-1].completion_event
    service.review_route(
        ADMIN,
        str(uuid4()),
        returned["id"],
        state(game).revision,
        allow=True,
        account="Actual reviewed known return cell",
    )
    final = state(game)
    assert final.harpy_rests[-1].completion_event == completion
    assert harpy(final, actor).cell == (1, 1) and game.dice.calls == 1


def test_native_harpy_hide_uses_owned_identity_and_real_judge_review_with_pause_and_reproposal(
    ledger,
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.discord_adapter.m3_actor_plays import open_actor_play

    svc, game, _, actor = ready(ledger, faces=(4, 4))

    async def start():
        caller = current(2, 99701)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_actor_play(caller, game, actor)
        menu = caller.edit_original_response.call_args.kwargs["view"]
        assert "go_off_duty" in dict(menu.options)
        await menu.open_item(caller, "go_off_duty")
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not {"heat", "identity", "gain"} & {x.key for x in form.fields}
        form.values.update(context="My actual owned hide", confirm=("yes",))
        await form.confirm.callback(current(2, 99702))
        assert form.completed

    asyncio.run(start())
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    request = next(x for x in game.choices(PLAYER) if x["kind"] == "harpy_off_duty_hide")
    action = request["action_id"]

    async def propose(identity):
        caller = current(2, identity)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        request = next(x for x in game.choices(PLAYER) if x["kind"] == "harpy_off_duty_hide")
        await open_choice(caller, game, request["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        form.values.update(
            identities="Free\nLiving Dream",
            account="Actual hide",
            navigation="Actual owned crossing into Voidspace",
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, identity + 1))
        assert form.completed

    asyncio.run(propose(99703))
    first = state(game).harpy_rests[-1].route

    async def reject():
        caller = current(1, 99705)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        request = next(x for x in game.choices(ADMIN) if x["kind"] == "harpy_off_duty_route")
        await open_choice(caller, game, request["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(
            allow=("no",), account="This proposed navigation needs a factual correction"
        )
        await form.confirm.callback(current(1, 99706))
        assert form.completed

    asyncio.run(reject())
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert state(game).harpy_rests[-1].phase == "rejected"
    assert offstage_travel(state(game), actor) is None
    asyncio.run(propose(99707))
    route = state(game).harpy_rests[-1].route
    assert route != first
    service = HarpyDefeatService(ledger, game)
    ledger.safety(OTHER, "pause-real-hide", ledger.status(OTHER)["revision"], pause=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.review_route(
            ADMIN,
            str(uuid4()),
            route,
            state(game).revision,
            allow=True,
            account="Actual reviewed navigation",
        )
    assert state(game).model_dump_json() == before and game.dice.calls == 1
    ledger.safety(OTHER, "resume-real-hide", ledger.status(OTHER)["revision"], pause=False)
    expected, key = state(game).revision, str(uuid4())
    result = service.review_route(
        ADMIN, key, route, expected, allow=True, account="Actual reviewed navigation"
    )
    snapshot = state(game).model_dump_json()
    assert (
        service.review_route(
            ADMIN, key, route, expected, allow=True, account="Actual reviewed navigation"
        )
        == result
    )
    assert state(game).model_dump_json() == snapshot
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_actual_original_death_closes_only_impossible_hide_without_repair_or_human_answer(ledger):
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_harpy_defeat import die
    from girlframe.services.m3_harpy_rest import synchronize_endings

    svc, game, _, actor = ready(ledger, faces=(4, 4))
    action = begin(svc, actor, play="go_off_duty", context="Actual original hide source")
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "harpy_off_duty_hide",
        flag=True,
        fields={
            "identities": json.dumps(["Free", "Chosen self"]),
            "navigation": "Actual proposed crossing",
        },
        text="Actual source-owned hide",
    )
    old = state(game)
    rest, route = old.harpy_rests[-1], old.harpy_travels[-1]
    with ledger.transaction() as c:
        ended = die(old, actor, "actual-different-fatal-source")
        game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.actual_original_death",
            ended,
            event_id="actual-different-fatal-source",
        )
        synchronize_endings(game, c, "actual-different-fatal-source")
    canon = state(game)
    assert canon.harpy_rests[-1].phase == "ended"
    assert canon.harpy_rests[-1].identities == rest.identities
    assert canon.harpy_travels[-1].state == "ended"
    assert canon.harpy_travels[-1].ended_event == "actual-different-fatal-source"
    assert harpy(canon, actor).identities == harpy(old, actor).identities
    assert harpy(canon, actor).cell == harpy(old, actor).cell
    assert offstage_travel(canon, actor) is None
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        closed = (
            c.execute(
                sa.select(choices).where(
                    choices.c.action_id == action, choices.c.kind == "harpy_off_duty_route"
                )
            )
            .mappings()
            .one()
        )
        assert closed["state"] == "completed_original_ended"
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(responses)
                .where(responses.c.choice_id == closed["id"])
            )
            == 0
        )
    with pytest.raises(WorkflowError):
        HarpyDefeatService(ledger, game).review_route(
            ADMIN,
            str(uuid4()),
            route.id,
            canon.revision,
            allow=True,
            account="No approval can move or heal this ended original",
        )
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
