"""Voluntary Princess tiers retain real owners, source Tags and one actual child."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_gender_designation import acquire, assign
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_princess_sex import open_choice, open_princess
from girlframe.engine import m3_gender_designation as gender
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_princess_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.inbox import InboxService
from girlframe.services.m3_gender_designation import GenderDesignationService
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    import test_mission_service

    original = test_mission_service.setup_game
    monkeypatch.setattr(
        test_mission_service,
        "setup_game",
        lambda *a, **kw: original(*a, **(kw | {"girl": "PRINCESS"})),
    )
    game, worker, gateway = ordinary_pr_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE, gender.RULE))
    return game, worker, gateway, SexService(game)


def source(service, *, native=False):
    game = service.game
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "PRIVATE_ACTUAL voluntary original interaction",
    )["id"]
    if native:

        async def run():
            first = current(3, 83001)
            first.channel_id = 900
            await first.response.defer(ephemeral=True)
            await open_princess(first, service, identity)
            form = first.edit_original_response.call_args.kwargs["view"]
            assert "every actor-owned decision" in form.instructions
            form.values.update(accept=("yes",), account="My actual voluntary source confirmation")
            await form.confirm.callback(current(3, 83002))
            assert form.completed

        asyncio.run(run())
    else:
        service.confirm(
            OTHER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "Actual counterpart owns this disclosed voluntary confirmation",
        )
    return identity


def roll(game, worker, gateway, service, faces, *, native=False):
    tick(worker, gateway, 5)
    identity = source(service, native=native)
    game.dice = Dice(faces)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Actual confirmed voluntary interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    return identity, action


def test_actual_native_princess_tiers_gender_and_true_counterpart_child(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    own, other = current_ref(state(game), 2), current_ref(state(game), 3)
    before = depth(state(game), own, other)
    identity, low = roll(game, worker, gateway, service, (2, 3), native=True)
    pass_tags(game)
    with pytest.raises(WorkflowError):
        row = next(x for x in game.choices(OTHER) if x["kind"] == "princess_sex_low_tag")
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(text="Cannot author another human's Tag"),
        )
    answer(game, OTHER, "princess_sex_low_tag", text="PRIVATE_LOW imperfection")
    assert depth(state(game), own, other) == max(0, before - 1)
    assert rules.get(state(game), identity).phase == "complete"
    assert game.inspect(PLAYER, low)["state"] == "complete"

    for response, giving in (("agree", False), ("refuse", False), ("refuse", True)):
        identity, action = roll(game, worker, gateway, service, (4, 4))
        pass_tags(game)
        answer(game, PLAYER, "princess_sex_favour", text="PRIVATE_FAVOUR pass the actual note")
        answer(
            game,
            OTHER,
            "princess_sex_favour_reply",
            options=(response,),
            text="My own performed speech: " + response,
        )
        if response == "refuse":
            answer(
                game,
                PLAYER,
                "princess_sex_optional_tag",
                options=("give" if giving else "decline",),
                text="PRIVATE_REFUSED stubborn" if giving else "",
            )
        value = rules.get(state(game), identity)
        assert value.response == response and bool(value.tag) == giving
        assert game.inspect(PLAYER, action)["state"] == "complete"

    designation = GenderDesignationService(ledger)
    acquired = acquire(game)
    assign(designation, acquired, (own,), "man")
    assign(designation, acquired, (other,), "animal")
    partner_tag = next(
        x.id for x in state(game).sheets["3"].tags if x.label == "PRIVATE_REFUSED stubborn"
    )
    identity, parent = roll(game, worker, gateway, service, (4, 4))
    original_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, PLAYER, "tag_window", options=("gender_man",), denied=(partner_tag,))
    with ledger.engine.connect() as c:
        assert game.action(c, parent)["data"]["result"]["total"] == 11
    assert not any(x["kind"] == "princess_sex_direct" for x in game.choices(PLAYER))
    answer(game, OTHER, "gender_animal_tag", text="PRIVATE_ANIMAL actual partner Tag")
    assert (
        next(
            x for x in state(game).sheets["2"].tags if x.label.startswith("PRIVATE_ANIMAL")
        ).giver_actor
        == other
    )
    answer(
        game,
        PLAYER,
        "princess_sex_direct",
        options=("keep_your_head",),
        text="Actual immediate danger: maintain composure under pressure",
    )
    value = rules.get(state(game), identity)
    direction = rules.direction(state(game), value.direction)
    details = service.view(PLAYER, identity)
    assert details["child"]["sheet_revision"] == state(game).sheets["3"].revision
    assert "review" not in details["child"] and "notes" not in details["child"]
    args = (
        PLAYER,
        "83005",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=direction.id,
            parent=parent,
            heat=0,
            context=direction.context,
            trigger_confirmed=True,
        ),
    )
    with pytest.raises(WorkflowError):
        game.begin(OTHER, str(uuid4()), *args[2:])

    async def native_child():
        current_choice = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_child")
        first = current(2, 83004)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_choice(first, game, current_choice["id"])
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=("0",), gain=("0",), identity=())
        response = current(2, 83005)
        response.channel_id = 900
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args

    asyncio.run(native_child())
    child = rules.direction(state(game), direction.id).child
    assert game.begin(*args)["action_id"] == child
    observed = []
    actual_actor = gateway.actor

    async def actor(identity):
        observed.append(identity)
        return await actual_actor(identity)

    gateway.actor = actor
    game.dice = Dice((4, 4))
    tick(worker, gateway, 3)
    assert 2 in observed and game.dice.calls == 1
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["character_ids"]["3"] == other.incarnation
    for owner in (ADMIN, PLAYER):
        own_row = next(
            x
            for x in game.choices(owner)
            if x["kind"] == "tag_window" and x["actor_id"] == str(owner.user_id)
        )
        game.respond(
            owner, str(uuid4()), own_row["id"], own_row["revision"], ChoiceAnswer(options=("pass",))
        )
    row = next(
        x for x in game.choices(PLAYER) if x["kind"] == "tag_window" and x["actor_id"] == "3"
    )
    game.respond(PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("pass",)))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    assert not any(x.identity == row["id"] for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("tough", "sexy"), denied=("in_control",)),
        )
    reply = (
        PLAYER,
        str(uuid4()),
        row["id"],
        row["revision"],
        ChoiceAnswer(options=("tough", "sexy"), denied=("in_control",)),
    )
    result = game.respond(*reply)
    assert game.respond(*reply) == result
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual Handler finds this sufficient")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event
    assert game.inspect(PLAYER, parent)["receipt"] == original_receipt
    assert game.dice.calls == 1
    with pytest.raises(WorkflowError):
        game.begin(PLAYER, str(uuid4()), *args[2:])
    tick(worker, gateway, 8)
    assert not any(
        x in json.dumps(gateway.messages)
        for x in ("PRIVATE_FAVOUR", "PRIVATE_LOW", "PRIVATE_ANIMAL")
    )
    assert any(x.identity == identity for x in InboxService(ledger).items(PLAYER))
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.id == rules.direction(state(game), direction.id).completed_event,
                    t.events.c.campaign_id == ledger.campaign_id,
                )
            )
            .mappings()
            .one()
        )
        assert row["actor_id"] == "1"  # The Handler's own sufficiency decision stays theirs.


# Deferred P1 additions: authoring only; no pytest run during this source extension.
def _directed_native(game, identity, play, *, target=None, order_id=None):
    async def run():
        request = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_direct")
        opened = current(2, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, request["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(play=(play,), text="My actual immediate legal directive and trigger")
        if target is not None:
            form.values["target"] = (target.token,)
        if order_id is not None:
            form.values["order_id"] = (order_id,)
        submitted = current(2, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())
    return rules.direction(state(game), rules.get(state(game), identity).direction)


def _prepare_directed_native(game, service, session_id, **values):
    async def run():
        request = next(x for x in game.choices(PLAYER) if x["kind"] == "princess_sex_child")
        opened = current(2, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, request["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 83998))
        form.values.update(values)
        submitted = current(2, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())
    return rules.direction(state(game), service.view(PLAYER, session_id)["direction"]).child


def _pass_directed_tags(game):
    # Actual performer-owned rows are authored by Princess; other humans remain themselves.
    while True:
        found = False
        for viewer in (PLAYER, OTHER, ADMIN):
            for row in game.choices(viewer):
                if row["kind"] == "tag_window":
                    game.respond(
                        viewer,
                        str(uuid4()),
                        row["id"],
                        row["revision"],
                        ChoiceAnswer(options=("pass",)),
                    )
                    found = True
        if not found:
            return


def test_high_native_directed_flirt_keeps_original_performer_resources_and_real_target_answer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_tags(game)
    original = state(game)
    princess, performer = current_ref(original, 2), current_ref(original, 3)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    direction = _directed_native(game, identity, "flirt", target=princess)
    assert direction.actor == performer and direction.target == princess
    with ledger.engine.connect() as c:
        from girlframe.services.m3_princess_sex import child_source

        with pytest.raises(WorkflowError):
            child_source(
                game,
                c,
                OTHER,
                state(game),
                PlayInput(
                    play="flirt",
                    source_work=direction.id,
                    parent=parent,
                    target=2,
                    heat=0,
                    context=direction.context,
                    trigger_confirmed=True,
                ),
                900,
            )
    own = state(game).sheets["3"]
    marked = next(x for x in own.identities if not x.marked and not x.protected and not x.paired)
    heat = own.heat + 3 if own.heat + 3 >= 5 else 3
    game.dice = Dice((2, 3))
    child = _prepare_directed_native(
        game,
        service,
        identity,
        heat=(str(heat),),
        identity=(marked.id,),
        gain=("3",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["actor_id"] == "3" and actual["parent_id"] == parent
        assert actual["data"]["prepared"]["target"] == 2
        assert actual["data"]["character_ids"]["3"] == performer.incarnation
        assert actual["data"]["result"]["tier"] == "mid"
    after = state(game)
    assert next(x for x in after.sheets["3"].identities if x.id == marked.id).marked
    assert after.sheets["3"].heat == own.heat + 3 - heat
    assert after.sheets["2"].identities == original.sheets["2"].identities
    actor_row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt")
    assert actor_row["actor_id"] == "3"
    assert not any(x["id"] == actor_row["id"] for x in game.choices(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            actor_row["id"],
            actor_row["revision"],
            ChoiceAnswer(options=("name",)),
        )
    key = str(uuid4())
    args = PLAYER, key, actor_row["id"], actor_row["revision"], ChoiceAnswer(options=("name",))
    replied = game.respond(*args)
    assert game.respond(*args) == replied and game.dice.calls == 1
    target_row = next(x for x in game.choices(PLAYER) if x["kind"] == "target_flirt")
    assert target_row["actor_id"] == "2"  # A real target choice, not performer authorship.
    game.respond(
        PLAYER,
        str(uuid4()),
        target_row["id"],
        target_row["revision"],
        ChoiceAnswer(text="PRIVATE_DIRECTED: my own actual answer and wanted followthrough"),
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert service.view(OTHER, identity)["phase"] == "complete"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        result = game.action(c, child)["data"]["result"]
        assert result["target_answer"].startswith("PRIVATE_DIRECTED")
    assert any(
        x.kind == "flirt_followthrough" and x.action == child for x in state(game).obligations
    )
    tick(worker, gateway, 8)
    assert "PRIVATE_DIRECTED" not in json.dumps(gateway.messages)


def test_high_directed_sensors_retains_actual_handler_answers_and_closes_real_parent(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6))
    pass_tags(game)
    direction = _directed_native(game, identity, "check_sensors")
    assert direction.target is None and direction.order_id is None
    # Old Keep records omit the new optional fields; no legacy source is rewritten.
    legacy = direction.model_copy(update={"play": "keep_your_head"})
    assert "target" not in legacy.model_dump(mode="json")
    assert "order_id" not in legacy.model_dump(mode="json")
    game.dice = Dice((4, 5))
    child = _prepare_directed_native(
        game,
        service,
        identity,
        heat=("0",),
        identity=(),
        gain=("0",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    answer(
        game,
        PLAYER,
        "actor_sensors",
        fields={
            "q1": "What actual immediate danger is present?",
            "q2": "What is actually useful here?",
        },
    )
    handler_row = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_sensors")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            handler_row["id"],
            handler_row["revision"],
            ChoiceAnswer(fields={"a1": "Cannot invent the Handler answer", "a2": "Nor this"}),
        )
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={"a1": "The actual doorway is exposed", "a2": "The actual cover"},
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event and game.dice.calls == 1


def test_high_directed_beneath_applies_actual_tag_and_status_from_real_performer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6))
    pass_tags(game)
    princess, performer = current_ref(state(game), 2), current_ref(state(game), 3)
    direction = _directed_native(game, identity, "put_someone_beneath_you", target=princess)
    game.dice = Dice((4, 5))
    child = _prepare_directed_native(
        game,
        service,
        identity,
        heat=("0",),
        identity=(),
        gain=("0",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "PRIVATE_DIRECTED: actual demonstrated inferiority"},
        text="The actual counterpart puts the actual target beneath her",
    )
    tag = next(x for x in state(game).sheets["2"].tags if x.label.startswith("PRIVATE_DIRECTED"))
    assert tag.giver_actor == performer
    from girlframe.engine.m2 import higher

    assert higher(state(game), 3, 2)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event and game.dice.calls == 1


def test_high_directed_engage_records_actual_performer_asset_maneuvers(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6))
    pass_tags(game)
    princess, performer = current_ref(state(game), 2), current_ref(state(game), 3)
    direction = _directed_native(game, identity, "engage", target=princess)
    game.dice = Dice((4, 5))
    child = _prepare_directed_native(
        game,
        service,
        identity,
        heat=("0",),
        identity=(),
        gain=("0",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    with ledger.engine.connect() as c:
        asset = next(
            x
            for x in resolve(state(game), performer, profiles(c, ledger.campaign_id)).assets
            if not x.damaged
        )
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="The actual performer advances using her own real capability and takes cover",
    )
    from girlframe.engine.m3_engage import Maneuver

    effects = [
        Maneuver.model_validate_json(x["body"])
        for x in state(game).facts
        if x.get("kind") == "engage_maneuver"
    ]
    assert len(effects) == 2 and all(
        x.actor == performer and x.opponent == princess for x in effects
    )
    assert all(x.asset == asset.id and x.source_action == child for x in effects)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event and game.dice.calls == 1


def test_high_directed_assault_uses_actual_review_and_declared_target_asset(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6))
    pass_tags(game)
    princess, performer = current_ref(state(game), 2), current_ref(state(game), 3)
    direction = _directed_native(game, identity, "all_out_assault", target=princess)
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_battle import resource_sha
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_battle import BattleService

    with ledger.engine.connect() as c:
        bound = profiles(c, ledger.campaign_id)
        actual, target = (
            resolve(state(game), performer, bound),
            resolve(state(game), princess, bound),
        )
    own = next(x for x in actual.assets if not x.damaged)
    opposing = next(x for x in target.assets if not x.damaged)
    declaration = Declaration(
        play="all_out_assault",
        actor=performer,
        target=princess,
        attacking_asset=own.id,
        target_asset=opposing.id,
        actor_sha256=resource_sha(state(game), performer, bound),
        target_sha256=resource_sha(state(game), princess, bound),
        account="The actual counterpart attacks this real target with this owned capability",
    )
    battle = BattleService(ledger)
    proposed = battle.propose(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        declaration,
        parent=parent,
        source_work=direction.id,
    )["id"]
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="The actual source Handler confirms the genuine opening and reach",
    )
    game.dice = Dice((4, 5))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="all_out_assault",
            source_work=direction.id,
            parent=parent,
            target_actor=princess,
            attacking_asset=own.id,
            target_asset=opposing.id,
            battle_context=proposed,
            heat=0,
            context=direction.context,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    while True:
        row = next((x for x in game.choices(PLAYER) if x["kind"] == "battle_assault_table"), None)
        if row is None:
            row = next(
                (x for x in game.choices(ADMIN) if x["kind"] == "battle_assault_table"), None
            )
            human = ADMIN
        else:
            human = PLAYER
        if row is None:
            break
        game.respond(
            human,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(flag=False, text="My actual table assessment of this attack"),
        )
    assert next(x for x in state(game).sheets["2"].assets if x.id == opposing.id).damaged
    assert not next(x for x in state(game).sheets["3"].assets if x.id == own.id).damaged
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert rules.direction(state(game), direction.id).completed_event and game.dice.calls == 1


def test_high_directed_disobey_requires_real_completed_order_ancestry_and_keeps_it_intact(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = setup(ledger, tmp_path, monkeypatch)
    tick(worker, gateway, 5)
    issued = game.issue_order(
        ADMIN,
        str(uuid4()),
        900,
        3,
        "Maintain the actual assigned position",
    )
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("disobey",))
    game.dice = Dice((6, 6))
    original_refusal = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="disobey_orders",
            parent=issued["action_id"],
            order_id=issued["order_id"],
            heat=0,
            context="My actual first refusal",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, original_refusal)["state"] == "ready_to_roll":
        game.roll(OTHER, str(uuid4()), original_refusal)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", flag=True)
    answer(
        game,
        ADMIN,
        "handler_disobey",
        flag=False,
        text="The fictional Handler has not learned of this actual refusal",
    )
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    tick(worker, gateway, 8)
    identity, parent = roll(game, worker, gateway, service, (6, 6))
    pass_tags(game)
    direction = _directed_native(game, identity, "disobey_orders", order_id=issued["order_id"])
    assert direction.order_id == issued["order_id"] and direction.target is None
    game.dice = Dice((4, 5))
    child = _prepare_directed_native(
        game,
        service,
        identity,
        heat=("0",),
        identity=(),
        gain=("0",),
        witnessed=("no",),
    )
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, child)["state"] == "ready_to_roll":
        game.roll(PLAYER, str(uuid4()), child)
    _pass_directed_tags(game)
    answer(
        game,
        PLAYER,
        "actor_disobey",
        options=("tag_heat",),
        number=1,
        text="PRIVATE_DIRECTED: actual resolute refusal",
    )
    answer(
        game,
        ADMIN,
        "handler_disobey",
        flag=False,
        text="The actual source Handler again determines whether the fiction makes this known",
    )
    assert any(x.label.startswith("PRIVATE_DIRECTED") for x in state(game).sheets["3"].tags)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    with ledger.engine.connect() as c:
        actual = game.action(c, child)
        assert actual["parent_id"] == parent and actual["actor_id"] == "3"
        assert actual["data"]["prepared"]["order_id"] == issued["order_id"]
    assert rules.direction(state(game), direction.id).completed_event and game.dice.calls == 1
