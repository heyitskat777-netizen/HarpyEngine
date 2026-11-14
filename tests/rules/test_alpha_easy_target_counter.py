"""Native Newgirl counters use a real mistake, owned responses and consequences."""

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
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.discord_adapter.m3_easy_target import open_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_easy_target as easy
from girlframe.engine.bonds import BondProposal
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_intracadre_marriage import rank
from girlframe.engine.shared_setup import CallsignChoice
from girlframe.services.bonds import BondService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_alpha import counter_plays
from girlframe.services.m3_alpha_easy_target import counter
from girlframe.services.m3_easy_target import prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.shared_setup import SharedSetupService


def ready(store, tmp_path, monkeypatch):
    review, creation, handler = creation_ready(
        store, girl="ALPHA", frame="THE ENFORCER", other_girl="NEWGIRL"
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
    game = GameService(store, dice=Dice((1, 1)))
    for viewer in (PLAYER, OTHER, FOUR):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review, saved.sheet.issues
        review.save(viewer, str(uuid4()), saved.saved_revision, saved.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    configure_m3_fixture(store)
    approved(store, game, tmp_path, monkeypatch, extra=(alpha.RULE, easy.RULE))
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
    return game, GameWorker(game), gateway


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


def opportunity(store, tmp_path, monkeypatch, faces, *, broken=True):
    game, worker, gateway = ready(store, tmp_path, monkeypatch)
    original = state(game)
    attacker, newcomer = (current_ref(original, owner) for owner in (2, 3))
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=newcomer,
            heat=0,
            context="PRIVATE_EASY_COUNTER The Alpha actually tears into the Newgirl",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_directed(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_low", options=("counter_broken" if broken else "counter_only",))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    assert any(x.identity == row["id"] for x in InboxService(store).items(OTHER))
    before = state(game)
    prepared = PlayInput(
        play=easy.PLAY,
        parent=parent,
        heat=1,
        context="PRIVATE_EASY_COUNTER I actually say something foolish under this pressure",
        trigger_confirmed=True,
    )
    with store.engine.connect() as c:
        assert easy.PLAY in counter_plays(game, c, before, game.action(c, parent), newcomer)
        with pytest.raises(WorkflowError):
            counter(game, c, before, attacker, prepared, 900)
        with pytest.raises(WorkflowError):
            counter(game, c, before, newcomer, prepared.model_copy(update={"target": 2}), 900)
    calls = game.dice.calls

    async def native():
        opened = current(3, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert easy.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(current(2, uuid4().int % 1000000000))
        form.values.update(play=(easy.PLAY,), heat=("1",), context=prepared.context)
        submitted = current(3, uuid4().int % 1000000000)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native())
    with store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == store.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "3",
            )
        )
        actual = game.action(c, child)
        assert actual["data"]["alpha_counter_source"]["choice"] == row["id"]
        assert actual["data"]["easy_target"]["caster"] == 3
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert game.dice.calls == calls
    game.dice.faces = faces
    tick(worker, gateway, 4)
    pass_directed(game)
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert game.dice.calls == calls + 1
    assert not alpha.conditions(state(game), attacker, newcomer)
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    return game, worker, gateway, parent, child, attacker, newcomer


def test_native_newgirl_counter_waits_for_actual_request_and_owned_judgment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, child, attacker, newcomer = opportunity(
        ledger, tmp_path, monkeypatch, (3, 4)
    )
    choose(game, OTHER, "easy_target_select", select=(attacker.token,), account="The real Alpha")
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "easy_target_tag")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Not my Tag")
        )
    choose(game, PLAYER, "easy_target_tag", account="PRIVATE_EASY_COUNTER an obvious soft spot")
    assert state(game).sheets["3"].tags[-1].giver_actor == attacker
    context = "PRIVATE_EASY_COUNTER I withstand the Alpha's genuine demanded drill"
    choose(
        game,
        PLAYER,
        "easy_target_react:" + attacker.token,
        urge=("request",),
        play=("keep_your_head",),
        context=context,
        account="My own actual reaction to her mistake",
    )
    choose(
        game,
        ADMIN,
        "easy_target_validate:" + attacker.token,
        yes=("yes",),
        account="The demanded drill actually meets the printed trigger",
    )
    work = next(x for x in easy.records(state(game), easy.Reaction) if x.session == child)
    assert game.inspect(OTHER, child)["state"] != "complete"
    assert not alpha.conditions(state(game), attacker, newcomer)
    game.dice.faces = (4, 4)
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
    tick(worker, gateway, 4)
    pass_directed(game)
    answer(game, OTHER, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual completed endurance")
    assert game.inspect(OTHER, performance)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    status = rank(state(game), 3)
    row = next(
        x for x in game.choices(PLAYER) if x["kind"] == "easy_target_judge:" + attacker.token
    )
    with pytest.raises(WorkflowError):
        game.decision(OTHER, row["id"])
    choose(
        game,
        PLAYER,
        row["kind"],
        yes=("yes",),
        account="PRIVATE_EASY_COUNTER She performed my actual request well",
    )
    final = state(game)
    assert rank(final, 3) == max(0, status - 1)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert alpha.conditions(final, attacker, newcomer)
    with ledger.engine.connect() as c:
        source = prove(game, c, final, work.id)
        assert source.actor == attacker and source.controller == 2
        assert source.children == (performance,) and source.completed_event
        completed = game.action(c, child)["data"]["alpha_counter_completed"]
        assert c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == completed)) == "2"
        assert c.scalar(
            sa.select(t.m2["m2_responses"].c.event_id).where(
                t.m2["m2_responses"].c.choice_id == row["id"]
            )
        )
    receipt, calls = game.inspect(OTHER, child)["receipt"], game.dice.calls
    assert game.roll(OTHER, str(uuid4()), child)["receipt"] == receipt
    assert game.dice.calls == calls
    tick(worker, gateway, 8)
    assert "PRIVATE_EASY_COUNTER" not in json.dumps(gateway.messages)


def test_native_newgirl_high_counter_keeps_independent_reactions_and_contempt(
    ledger, tmp_path, monkeypatch
):
    game, _, _, parent, child, attacker, newcomer = opportunity(
        ledger, tmp_path, monkeypatch, (5, 5), broken=False
    )
    choose(
        game, OTHER, "easy_target_select", select=(attacker.token,), account="The original Alpha"
    )
    choose(game, PLAYER, "easy_target_tag", account="An actual public mistake")
    status = rank(state(game), 3)
    source = easy.get(state(game), easy.Session, child)
    viewers = {1: ADMIN, 2: PLAYER, 4: FOUR}
    for role in source.cast.roles:
        if role.actor == newcomer:
            continue
        viewer = viewers[role.controller]
        row = next(x for x in game.choices(viewer) if x["kind"].startswith("easy_target_react:"))
        choose(
            game,
            viewer,
            row["kind"],
            urge=("contempt" if viewer == PLAYER else "pass",),
            account="I choose my own printed reaction",
        )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    choose(
        game,
        PLAYER,
        "easy_target_contempt:" + attacker.token,
        performance=("look",),
        account="I actually give her a disgusted look",
    )
    assert rank(state(game), 3) == min(len(state(game).order) - 1, status + 1)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert not alpha.conditions(state(game), attacker, newcomer)


def test_native_newgirl_low_counter_keeps_status_loss_and_actual_contempt(
    ledger, tmp_path, monkeypatch
):
    game, _, _, parent, child, attacker, newcomer = opportunity(
        ledger, tmp_path, monkeypatch, (1, 1)
    )
    assert not any(x["kind"] == "easy_target_select" for x in game.choices(OTHER))
    source = easy.get(state(game), easy.Session, child)
    assert source.total == 3 and source.selected is None and source.tag is None
    rows = []
    viewers = {1: ADMIN, 2: PLAYER, 4: FOUR}
    for role in source.cast.roles:
        if role.actor == newcomer:
            continue
        viewer = viewers[role.controller]
        row = next(x for x in game.choices(viewer) if x["kind"].startswith("easy_target_react:"))
        rows.append((viewer, row["kind"].replace("easy_target_react:", "easy_target_contempt:")))
        choose(
            game,
            viewer,
            row["kind"],
            urge=("contempt",),
            account="I choose my own printed contempt reaction to the actual mistake",
        )
    for viewer, kind in rows:
        assert game.inspect(OTHER, child)["state"] != "complete"
        assert game.inspect(PLAYER, parent)["state"] != "complete"
        assert not alpha.conditions(state(game), attacker, newcomer)
        status = rank(state(game), 3)
        choose(
            game,
            viewer,
            kind,
            performance=("look",),
            account="I actually give her my own disgusted look",
        )
        assert rank(state(game), 3) == min(len(state(game).order) - 1, status + 1)
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert alpha.conditions(state(game), attacker, newcomer)
