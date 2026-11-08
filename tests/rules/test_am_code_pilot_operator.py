"""Real other Pilot circuits, personal secret authority and genuine damage response."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
import test_creation_review
import test_m2_game
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_am import open_choice as open_am_choice
from girlframe.discord_adapter.m3_am_code import open_choice, open_code
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_code as code
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.m3_am_code import CodeService, prove_code_discovery
from girlframe.services.m3_am_scrutinized import (
    pilot_order_authority,
    valid_pilot_order,
)
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.onboarding import WorkflowError


def high(store, tmp_path, monkeypatch, *, marked=False, shield=False, body=False):
    seed = test_creation_review.seed
    selected = test_m2_game.selected

    def ordinary_seed(target, viewer=PLAYER):
        if viewer != OTHER:
            return seed(target, viewer)
        target.join(viewer, "join-3")
        target.save_draft(
            viewer,
            "draft-3",
            0,
            DraftInput(
                callsign="Actual operator",
                girl_playbook="MOCKINGBIRD",
                frame_playbook="THE ENFORCER",
                notes="PRIVATE_OPERATOR_NOTE",
            ),
        )

    monkeypatch.setattr(test_creation_review, "seed", ordinary_seed)
    monkeypatch.setattr(
        test_m2_game, "selected", lambda *_: selected("MOCKINGBIRD", "THE ENFORCER")
    )
    _, game = service(store, girl="AM", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(am.RULE, code.RULE))
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        if shield:
            canon.world = canon.world.model_copy(
                update=dict(
                    gorgons=canon.world.gorgons
                    + (gorgon("sprite", "actual-nearby-protector", revealed=True),)
                )
            )
        canon = place(place(canon, 2, mode="outside_frame"), 3, mode="outside_frame")
        if marked:
            canon.sheets["2"].tags.append(
                TagState(
                    id="actual-old-marked-tag",
                    label="Past defiance",
                    giver=3,
                    giver_actor=current_ref(canon, 3),
                    marked=True,
                    observers=(3,),
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_circuit_bodies", canon)
    source = CodeService(game)
    original = state(game)
    operator = current_ref(original, 3)
    candidate = next(
        x
        for x in source.menu(PLAYER, 900)["operators"]
        if x["ref"] == operator.model_dump(mode="json")
    )
    assert not am.discoveries(original)

    async def contact():
        owner = current(2, 975001)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_code(owner, source, channel=900)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=("operator:" + candidate["id"],))
        target = current(2, 975002)
        await menu.confirm.callback(target)
        form = target.edit_original_response.call_args.kwargs["view"]
        assert not any(x.key == "records_subject" for x in form.fields)
        form.values.update(account="Actual other Pilot circuit contact")
        result = current(2, 975003)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)
        identity = code.sessions(state(game))[0].id
        with pytest.raises(WorkflowError):
            source.confirm(ADMIN, str(uuid4()), identity, state(game).revision, "Not the operator")
        actual = current(3, 975004)
        actual.channel_id = 900
        await actual.response.defer(ephemeral=True)
        await open_code(actual, source, channel=900)
        menu = actual.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=("confirm:" + identity,))
        target = current(3, 975005)
        await menu.confirm.callback(target)
        form = target.edit_original_response.call_args.kwargs["view"]
        assert not any(x.key in ("operator_human", "operator_lower") for x in form.fields)
        form.values.update(account="My actual hands access this same AM's actual circuits")
        result = current(3, 975006)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)
        return identity

    identity = asyncio.run(contact())
    maintenance = code.session(state(game), identity)
    assert (
        maintenance.operator == operator
        and maintenance.controller == 3
        and maintenance.operator_lower
    )
    assert (
        maintenance.operator_vessel and maintenance.operator_frame and maintenance.operator_position
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    before = state(game)
    selected = code.choices(before, current_ref(before, 2))[0]
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=maintenance.root,
            source_work=identity,
            target_actor=operator,
            gain=1,
            identity=selected.id,
            heat=1,
            trigger_confirmed=True,
            context="This actual other Pilot operates my circuits",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, OTHER, ADMIN):
        if not any(x["kind"] == "tag_window" for x in game.choices(human)):
            continue
        if marked and human == OTHER:
            answer(
                game,
                human,
                "tag_window",
                options=("tag",),
                denied=("actual-old-marked-tag",),
                number=1,
                text="Past defiance matters to this actual circuit connection",
            )
        else:
            answer(game, human, "tag_window", options=("pass",))
    if marked:
        assert not am.discoveries(state(game))
        answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(selected.id,))
    fresh = state(game)
    record = code.session(fresh, identity)
    assert fresh.order == before.order and record.new_discovery and game.dice.calls == 1
    with store.engine.connect() as c:
        assert (
            prove_code_discovery(game, c, fresh, game.action(c, action)).id == record.new_discovery
        )
        if marked:
            response = t.m2["m2_responses"]
            choices = t.m2["m2_choices"]
            assert (
                c.scalar(
                    sa.select(choices.c.kind)
                    .join(response, choices.c.id == response.c.choice_id)
                    .where(
                        response.c.event_id
                        == am.discovery(fresh, record.new_discovery).proposed_event
                    )
                )
                == "tag_resolution"
            )
    row = next(x for x in game.choices(OTHER) if x["kind"] == "am_code_options")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("backup",))
        )
    for unsupported in ("branch", "records"):
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                row["id"],
                row["revision"],
                ChoiceAnswer(options=(unsupported,)),
            )

    async def backup():
        owner = current(3, 975007)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert set(dict(next(x for x in form.fields if x.key == "options").options)) == {
            "identities",
            "backup",
            "body",
        }
        form.values.update(options=("body", "backup") if body else ("backup",))
        result = current(3, 975008)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)

    asyncio.run(backup())
    return game, source, record.new_discovery, action, maintenance.root, worker, gateway


def test_other_original_pilot_marked_tag_high_secret_real_lower_pilot_order(
    ledger, tmp_path, monkeypatch
):
    game, source, identity, action, root, worker, gateway = high(
        ledger, tmp_path, monkeypatch, marked=True
    )
    before = state(game)
    value = am.discovery(before, identity)
    receipt = copy.deepcopy(game.inspect(PLAYER, action)["receipt"])
    assert not higher(before, 3, 2)

    async def keep_secret():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
        owner = current(2, 975015)
        await owner.response.defer(ephemeral=True)
        await open_am_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=("secret",), account="Please keep this actual adjustment secret")
        result = current(2, 975016)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)

    asyncio.run(keep_secret())
    assert depth(state(game), value.actor, value.discoverer) >= 1
    assert state(game).order == before.order and game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        authority = pilot_order_authority(game, c, state(game), 3, 2)
        assert authority["issuer"] == value.discoverer.model_dump(mode="json")
        assert pilot_order_authority(game, c, state(game), 3, 1) is None
    order = game.issue_order(
        OTHER, "real-source-pilot-order", 900, 2, "Keep my secret and remain here"
    )
    with ledger.engine.connect() as c:
        table = t.m2["m2_orders"]
        row = dict(
            c.execute(sa.select(table).where(table.c.id == order["order_id"])).mappings().one()
        )
        assert row["issuer_id"] == "3" and "npc_order" not in json.loads(row["body_json"])
        assert json.loads(row["body_json"])["am_secret"] == authority
        assert valid_pilot_order(game, c, state(game), row)
        revoked = state(game).model_copy(deep=True)
        am.put(
            revoked,
            am.discovery(revoked, identity).model_copy(
                update=dict(report_event="actual-revocation")
            ),
        )
        with pytest.raises(WorkflowError):
            valid_pilot_order(game, c, revoked, row)
        successor = state(game).model_copy(deep=True)
        successor.sheets["3"].character_id = "another-original-person"
        with pytest.raises((WorkflowError, ValueError)):
            valid_pilot_order(game, c, successor, row)
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    with ledger.engine.connect() as c:
        assert (
            game.valid_order(c, state(game), 2, 900, order["order_id"])["id"] == order["order_id"]
        )
        with pytest.raises(WorkflowError):
            game.valid_order(c, revoked, 2, 900, order["order_id"])
    game.dice.faces = (4, 5)
    refused = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            parent=order["action_id"],
            order_id=order["order_id"],
            heat=0,
            trigger_confirmed=True,
            context="My original AM refuses this actual Pilot's secret-based Order",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_disobey",
        options=("tag_heat",),
        number=1,
        text="Still my own original AM",
    )
    answer(game, ADMIN, "handler_disobey", flag=False)
    assert (
        game.inspect(PLAYER, refused)["state"]
        == game.inspect(PLAYER, order["action_id"])["state"]
        == "complete"
    )
    assert game.dice.calls == 2 and game.inspect(PLAYER, action)["receipt"] == receipt
    tick(worker, gateway, 5)
    known = source.menu(PLAYER, 900)
    assert any(
        x["id"] == identity and x["operator"] == value.discoverer.model_dump(mode="json")
        for x in known["known"]
    )
    final = state(game)
    assert game.rebuild() > 0 and state(game) == final


def test_other_pilot_real_asset_damage_waits_sprite_work_and_original_human_response(
    ledger, tmp_path, monkeypatch
):
    game, source, identity, action, root, worker, gateway = high(
        ledger, tmp_path, monkeypatch, shield=True
    )
    before = state(game)
    value = am.discovery(before, identity)
    original = before.sheets["3"].model_copy(deep=True)
    asset = next(x for x in original.assets if x.family == "girl" and not x.damaged)

    async def choose_damage():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
        owner = current(2, 975017)
        await owner.response.defer(ephemeral=True)
        await open_am_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        labels = dict(next(x for x in form.fields if x.key == "options").options)
        assert "Damage an operator Asset" in labels["violence"] and "Kill" not in labels["violence"]
        form.values.update(
            options=("violence",), account="Actual physical damage to the operator's hardware"
        )
        result = current(2, 975018)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)

    asyncio.run(choose_damage())

    # Missing terminal Frame/battle context remains an adapter gap, before mutation.
    from girlframe.services.m3_am_scrutinized import apply_pilot_damage, projection

    with ledger.engine.connect() as c:
        held = game.action(c, action)
        terminal = state(game).model_copy(deep=True)
        frames = [x for x in terminal.sheets["3"].assets if x.family == "frame"]
        for other in frames[1:]:
            other.damaged = True
        detail = projection(game, c, terminal, held, {"kind": "am_pilot_damage"})
        assert frames[0].id not in {x["id"] for x in detail["assets"]}
        unchanged = terminal.model_dump_json()
        with pytest.raises(WorkflowError, match="SOURCE_FRAME_CONSEQUENCE_REQUIRED"):
            apply_pilot_damage(
                game,
                c,
                terminal,
                copy.deepcopy(held),
                {"kind": "am_pilot_damage"},
                ChoiceAnswer(options=(frames[0].id,), text="No fabricated battle"),
            )
        assert terminal.model_dump_json() == unchanged

    async def damage():
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_pilot_damage")
        owner = current(2, 975009)
        await owner.response.defer(ephemeral=True)
        await open_am_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(asset=(asset.id,), account="Actual strike to this original Asset")
        result = current(2, 975010)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)

    asyncio.run(damage())
    assert not next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    assert not any(x["kind"] == "am_pilot_response" for x in game.choices(OTHER))
    workrow = next(x for x in game.choices(ADMIN) if x["kind"] == "battle_sprite_intercept")
    work = json.loads(workrow["body_json"])["work_id"]
    sprite = SpriteService(ledger)
    data = sprite.get(ADMIN, work)
    sprite.respond(
        ADMIN,
        str(uuid4()),
        work,
        data["revision"],
        data["game_revision"],
        None,
        None,
        "Actual protector declines this blow",
    )
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    assert game.inspect(PLAYER, action)["state"] != "complete"

    async def reply():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "am_pilot_response")
        owner = current(3, 975011)
        await owner.response.defer(ephemeral=True)
        await open_am_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values.update(
            account="I recoil from my damaged actuator, remaining my own original Girl"
        )
        result = current(3, 975012)
        await form.confirm.callback(result)
        assert form.completed, str(result.edit_original_response.call_args)

    asyncio.run(reply())
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    assert game.dice.calls == 1 and state(game).sheets["3"].identities == original.identities
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))

    async def history():
        owner = current(2, 975013)
        await owner.response.defer(ephemeral=True)
        await open_code(owner, source, channel=900)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=("response:" + value.code_origin,))
        result = current(2, 975014)
        await menu.confirm.callback(result)
        assert "damaged actuator" in str(result.edit_original_response.call_args)

    asyncio.run(history())


def test_actual_pilot_body_choice_separates_handler_facts_operator_effect_and_am_return(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_am_body import open_body
    from girlframe.discord_adapter.m3_am_body import open_choice as open_body_choice
    from girlframe.engine import m3_am_body as bodies
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_am_body import BodyService, prove, prove_preparation

    game, _, _, action, _, worker, gateway = high(ledger, tmp_path, monkeypatch, body=True)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    actual = state(game)
    maintenance = next(x for x in code.sessions(actual) if x.action == action)
    operator = current_ref(actual, 3)
    actor = current_ref(actual, 2)
    original_pose = next(x for x in actual.placements if x.actor == actor)
    service = BodyService(game)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "am_code_body")
    assert "body" in maintenance.selected_options and maintenance.controller == 3
    with ledger.engine.connect() as c:
        task = next(x for x in service._tasks(c, ADMIN) if x["phase"] == "prepare")
        assert task["id"] == maintenance.id and task["pending"]
        assert not any(x["phase"] == "prepare" for x in service._tasks(c, OTHER))

    async def waiting_and_actual_handler_facts():
        own = current(3, 995001)
        await own.response.defer(ephemeral=True)
        await open_body_choice(own, game, row["id"])
        assert "waiting" in own.edit_original_response.call_args.kwargs["content"]
        assert not own.edit_original_response.call_args.kwargs.get("view")
        own = current(1, 995002)
        await own.response.defer(ephemeral=True)
        await open_body(own, service, maintenance.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            vessel="actual-pilot-programmed-puppet",
            label="Actual supplied replacement hardware",
            source="PRIVATE_HANDLER_ACTUAL_LOCAL_PROCESSOR_AND_EMPTY_HARDWARE_SOURCE",
            processing=("yes",),
            unoccupied=("yes",),
            medical=("fit",),
            mind_assets=(),
            assets=(
                "Prepared arm | Actual supplied actuator | intact | clear\n"
                "Prepared casing | Actual supplied casing | intact | clear"
            ),
        )
        confirmation = current(1, 995003)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(waiting_and_actual_handler_facts())
    (prepared,) = bodies.preparations(state(game))
    assert prepared.controller == 3 and prepared.operator == operator
    assert prepared.fact_author.entity == "1" and prepared.fact_appointment
    with ledger.engine.connect() as c:
        assert prove_preparation(game, c, state(game), prepared.id) == prepared
        forged = state(game).model_copy(deep=True)
        bodies.put(
            forged,
            "am_body_prepared",
            prepared.id,
            prepared.model_copy(update=dict(fact_author=None, fact_appointment=None)),
        )
        with pytest.raises(WorkflowError):
            prove_preparation(game, c, forged, prepared.id)
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=(prepared.id,), text="Cannot impersonate the actual Pilot operator"
            ),
        )
    calls = game.dice.calls

    async def actual_operator():
        own = current(3, 995004)
        await own.response.defer(ephemeral=True)
        await open_body_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1))
        form.values.update(
            body=(prepared.id,),
            account=(
                "My actual hands transfer this same original AM into the real prepared "
                "processing body; "
                "its original body remains physically hooked up"
            ),
        )
        confirmation = current(3, 995005)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(actual_operator())
    swapped = state(game)
    (swap,) = bodies.swaps(swapped)
    assert swap.controller == 3 and swap.operator == operator and swap.actor == actor
    assert swap.new_vessel == prepared.spec.vessel and game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert prove(game, c, swapped, swap.id) == swap
        actual_body = resolve(swapped, actor, profiles(c, ledger.campaign_id))
        assert actual_body.vessel_id == prepared.spec.vessel
        assert {x.id for x in prepared.spec.assets} <= {x.id for x in actual_body.assets}
        response = t.m2["m2_responses"]
        assert (
            c.scalar(sa.select(response.c.actor_id).where(response.c.event_id == swap.event)) == "3"
        )
    assert service.view(ADMIN, swap.id)["can_record_connection"]
    assert not service.view(OTHER, swap.id)["can_record_connection"]
    with pytest.raises(WorkflowError):
        service.connection(
            OTHER,
            "operator-is-not-fact-author",
            swap.id,
            swapped.revision,
            False,
            "Not the actual original Handler's factual source",
        )

    # Close the genuine new-discovery consequence before unrelated new-body gameplay.
    answer(
        game,
        PLAYER,
        "am_select",
        options=("secret",),
        text="Please keep this actual circuit adjustment secret",
    )
    tick(worker, gateway, 5)
    game.dice.faces = (1, 1)
    performed = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            trigger_confirmed=True,
            context="This actual new processing body's actuator performs the real interaction",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, performed)["receipt"]
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual physical counterattack")
    damaged = prepared.spec.assets[0]
    answer(game, PLAYER, "beneath_details", denied=(damaged.id,))
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, performed)["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == damaged.id).damaged

    async def actual_handler_hookup():
        for index, operation in enumerate(("disconnect", "connect")):
            own = current(1, 995006 + 2 * index)
            await own.response.defer(ephemeral=True)
            await open_body(own, service, swap.id)
            form = own.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                operation=(operation,),
                account=(
                    "Actual original/new hardware connection is " + operation + "ed in this scene"
                ),
            )
            confirmation = current(1, 995007 + 2 * index)
            await form.confirm.callback(confirmation)
            assert form.completed, str(confirmation.edit_original_response.call_args)
            if operation == "disconnect":
                with pytest.raises((WorkflowError, ValueError), match="hooked"):
                    service.return_body(PLAYER, str(uuid4()), swap.id, state(game).revision)

    asyncio.run(actual_handler_hookup())
    with pytest.raises(WorkflowError):
        service.return_body(OTHER, "operator-does-not-own-am-return", swap.id, state(game).revision)

    async def original_am_returns():
        own = current(2, 995010)
        await own.response.defer(ephemeral=True)
        await open_body(own, service, swap.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(operation=("return",))
        confirmation = current(2, 995011)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(original_am_returns())
    final = state(game)
    assert bodies.swap(final, swap.id).returned_event and current_ref(final, 2) == actor
    assert (
        next(x for x in final.placements if x.actor == actor).vessel_id == original_pose.vessel_id
    )
    parked = next(x for x in bodies.bodies(final) if x.vessel == prepared.spec.vessel)
    assert next(x for x in parked.assets if x.id == damaged.id).damaged
    with ledger.engine.connect() as c:
        assert prove(game, c, final, swap.id).operator == operator
        author = c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == prepared.event))
        assert author == "1"
    assert game.dice.calls == calls + 1
    assert service.view(ADMIN, swap.id)["swap"]["returned_event"]
