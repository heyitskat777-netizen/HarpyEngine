"""A directed native Newgirl keeps her resources and other people's actual decisions."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_creation import selected
from test_creation_review import ready as creation_ready
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_princess_oldgen_advice import pass_directed
from test_princess_sex import _directed_native, _prepare_directed_native, roll
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_easy_target import open_choice
from girlframe.engine import m3_easy_target as easy
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.bonds import BondProposal
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_intracadre_marriage import rank
from girlframe.engine.shared_setup import CallsignChoice
from girlframe.services.bonds import BondService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_easy_target import prove
from girlframe.services.m3_princess_sex import SexService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.shared_setup import SharedSetupService


def ready(store, tmp_path, monkeypatch):
    review, creation, handler = creation_ready(
        store, girl="PRINCESS", frame="THE ENFORCER", other_girl="NEWGIRL"
    )
    third_draft(store)
    handler.mentor(
        ADMIN,
        str(uuid4()),
        handler.roster(ADMIN)["revision"],
        PilotRef(user_id=3, character_revision=store.draft(OTHER)["revision"]),
        PilotRef(user_id=4, character_revision=store.draft(FOUR)["revision"]),
    )
    bonds = BondService(store)
    mentor_bond = bonds.propose(
        OTHER,
        str(uuid4()),
        store.draft(OTHER)["revision"],
        store.draft(FOUR)["revision"],
        BondProposal(
            target_id=4, prompt=0, context="The actual assigned Mentor accepts this relationship"
        ),
    )
    bonds.decide(FOUR, str(uuid4()), mentor_bond["id"], 1, "accept")
    shared = SharedSetupService(store)
    naming = shared.propose(
        FOUR,
        str(uuid4()),
        3,
        "callsign",
        shared.prepare(FOUR, 3, "callsign"),
        CallsignChoice(callsign="Actual newcomer"),
    )
    shared.decide(OTHER, str(uuid4()), naming["id"], 1, "accept")
    draft = creation.get(OTHER)
    creation.save(
        OTHER,
        str(uuid4()),
        draft.revision,
        store.draft(OTHER)["revision"],
        selected("NEWGIRL", "JANUS-B").model_copy(
            update={
                "shared_tokens": draft.draft.shared_tokens,
                "prior_missions": tuple(
                    PriorMission(user_id=uid, character_revision=data["revision"], missions=0)
                    for uid, data in creation.cadre(OTHER).items()
                ),
                "cadre_discussed": True,
            }
        ),
    )
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
        }
    )
    game = GameService(store, dice=Dice((6, 6)))
    for viewer in (PLAYER, OTHER, FOUR):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review, saved.sheet.issues
        review.save(viewer, str(uuid4()), saved.saved_revision, saved.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    configure_m3_fixture(store)
    approved(store, game, tmp_path, monkeypatch, extra=(princess.RULE, easy.RULE))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={
                    "subsystems": store.policy.m3_approval.subsystems | {"world"},
                }
            ),
        }
    )
    with store.transaction() as connection:
        actual = state(game)
        actual.world = initial()
        for owner in (2, 3, 4):
            actual = place(actual, owner, mode="outside_frame")
        actual.sheets["3"].heat = 3
        game.event(connection, 1, str(uuid4()), "synthetic.original_newgirl_resources", actual)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    gateway = Gateway()

    async def actor(identity):
        return {1: ADMIN, 2: PLAYER, 3: OTHER, 4: FOUR}[identity]

    gateway.actor = actor
    return game, GameWorker(game), gateway, SexService(game)


def choose(game, viewer, kind, **values):
    async def run():
        row = next(x for x in game.choices(viewer) if x["kind"] == kind)
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def test_native_directed_easy_target_real_request_performance_and_recipient_judgment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_directed(game)
    direction = _directed_native(game, identity, easy.PLAY)
    before = state(game)
    game.dice = Dice((4, 4))
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    tick(worker, gateway, 3)
    pass_directed(game)
    after = state(game)
    assert after.sheets["3"].heat == before.sheets["3"].heat - 1
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == 1
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "easy_target_select")
    assert row["actor_id"] == "3"
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=(current_ref(after, 4).token,),
                text="Not my directed decision",
            ),
        )
    target = current_ref(after, 4)
    choose(
        game, PLAYER, "easy_target_select", select=(target.token,), account="The actual observer"
    )
    row = next(x for x in game.choices(FOUR) if x["kind"] == "easy_target_tag")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Not my Tag")
        )
    choose(game, FOUR, "easy_target_tag", account="PRIVATE_EASY_TAG actual vulnerability")
    tag = state(game).sheets["3"].tags[-1]
    assert tag.giver_actor == target
    context = "PRIVATE_EASY_TASK I perform the actual demanding drill"
    choose(
        game,
        FOUR,
        "easy_target_react:" + target.token,
        urge=("request",),
        play=("keep_your_head",),
        context=context,
        account="PRIVATE_EASY_URGE My actual request",
    )
    choose(
        game,
        ADMIN,
        "easy_target_validate:" + target.token,
        yes=("yes",),
        account="The actual performance has its real printed trigger",
    )
    work = next(x for x in easy.records(state(game), easy.Reaction) if x.session == child)
    assert not princess.direction(state(game), direction.id).completed_event
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    # A separately requested Play retains its real Newgirl performer. It is not
    # another Princess directive or a fabricated immediate-source completion.
    game.dice = Dice((4, 4))
    performance = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            parent=child,
            source_work=work.id,
            context=context,
            heat=0,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_directed(game)
    answer(game, OTHER, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual completed endurance")
    assert game.inspect(OTHER, performance)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    status = rank(state(game), 3)
    row = next(x for x in game.choices(FOUR) if x["kind"] == "easy_target_judge:" + target.token)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(flag=True, text="Not my judgment"),
        )
    choose(
        game,
        FOUR,
        "easy_target_judge:" + target.token,
        yes=("yes",),
        account="PRIVATE_EASY_JUDGMENT The real task was done well",
    )
    assert rank(state(game), 3) == max(0, status - 1)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    receipt = game.inspect(PLAYER, child)["receipt"]
    calls = game.dice.calls
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == calls
    with ledger.engine.connect() as connection:
        actual = prove(game, connection, state(game), work.id)
        assert actual.controller == 4 and actual.children == (performance,)
        directed = princess.direction(state(game), direction.id)
        audit = (
            connection.execute(sa.select(t.events).where(t.events.c.id == directed.completed_event))
            .mappings()
            .one()
        )
        assert audit["actor_id"] == "4"
        assert audit["kind"] == "m3.princess_directed_easy_target_completed"
        action = game.action(connection, child)
        assert action["actor_id"] == "3" and action["parent_id"] == parent
        assert action["data"]["easy_target"]["caster"] == 3
        assert action["data"]["princess_child"]["author"] == 2
    tick(worker, gateway, 8)
    assert "PRIVATE_EASY_" not in json.dumps(gateway.messages)


def test_native_directed_easy_target_use_keeps_princess_owned_bond_after_actual_performance(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    identity, parent = roll(game, worker, gateway, service, (6, 6), native=True)
    pass_directed(game)
    direction = _directed_native(game, identity, easy.PLAY)
    game.dice = Dice((4, 4))
    child = _prepare_directed_native(game, service, identity, heat=("1",), gain=("0",), identity=())
    tick(worker, gateway, 3)
    pass_directed(game)
    original = state(game)
    newcomer, reactor = current_ref(original, 3), current_ref(original, 4)
    before_bond = depth(original, newcomer, reactor)
    princess_bond = depth(original, current_ref(original, 2), reactor)
    choose(
        game, PLAYER, "easy_target_select", select=(reactor.token,), account="The actual reactor"
    )
    choose(game, FOUR, "easy_target_tag", account="PRIVATE_USE_TAG easily drawn in")
    context = "PRIVATE_USE_TASK I endure the actual difficult test she uses me for"
    choose(
        game,
        FOUR,
        "easy_target_react:" + reactor.token,
        urge=("use",),
        play=("keep_your_head",),
        context=context,
        account="PRIVATE_USE_URGE My own actual urge to use her",
    )
    choose(
        game,
        ADMIN,
        "easy_target_validate:" + reactor.token,
        yes=("yes",),
        account="The actual test has its real printed trigger",
    )
    work = next(x for x in easy.records(state(game), easy.Reaction) if x.session == child)
    assert not any(x["kind"].startswith("easy_target_bond:") for x in game.choices(PLAYER))
    game.dice = Dice((4, 4))
    performance = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            parent=child,
            source_work=work.id,
            context=context,
            heat=0,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_directed(game)
    answer(game, OTHER, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual use performance is finished")
    assert game.inspect(OTHER, performance)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    kind = "easy_target_bond:" + reactor.token
    row = next(x for x in game.choices(PLAYER) if x["kind"] == kind)
    assert row["actor_id"] == newcomer.entity
    assert not any(x["id"] == row["id"] for x in game.choices(OTHER))
    assert not any(x["id"] == row["id"] for x in game.choices(FOUR))
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    for viewer in (OTHER, FOUR):
        with pytest.raises(WorkflowError):
            game.respond(
                viewer,
                str(uuid4()),
                row["id"],
                row["revision"],
                ChoiceAnswer(flag=True, text="Not my directed Bond decision"),
            )
    choose(game, PLAYER, kind, yes=("yes",), account="PRIVATE_USE_BOND Deepen her actual Bond")
    final = state(game)
    assert depth(final, newcomer, reactor) == min(2, before_bond + 1)
    assert depth(final, current_ref(final, 2), reactor) == princess_bond
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert service.view(PLAYER, identity)["phase"] == "complete"
    with ledger.engine.connect() as connection:
        actual = prove(game, connection, final, work.id)
        assert actual.urge == "use" and actual.consequence == "bond"
        assert actual.children == (performance,) and actual.controller == FOUR.user_id
        response = (
            connection.execute(
                sa.select(t.m2["m2_responses"]).where(t.m2["m2_responses"].c.choice_id == row["id"])
            )
            .mappings()
            .one()
        )
        assert response["actor_id"] == str(PLAYER.user_id)
        assert actual.completed_event == response["event_id"]
        completed = princess.direction(final, direction.id).completed_event
        audit = (
            connection.execute(sa.select(t.events).where(t.events.c.id == completed))
            .mappings()
            .one()
        )
        assert audit["kind"] == "m3.princess_directed_easy_target_completed"
        assert audit["actor_id"] == str(PLAYER.user_id)
    receipt, calls = game.inspect(PLAYER, child)["receipt"], game.dice.calls
    assert game.roll(PLAYER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == calls
    tick(worker, gateway, 8)
    assert "PRIVATE_USE_" not in json.dumps(gateway.messages)
