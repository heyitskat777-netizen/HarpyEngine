"""A genuinely cast Handler is a Feedback counterpart, never just a facilitator."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless, set_depth
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou_feedback import _handler_counterpart, prove
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def actual_handler_source(ledger, tmp_path, monkeypatch, *, bond=False):
    _, game, worker, gateway, _, service = ready(ledger, tmp_path, monkeypatch)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        previous = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, previous)
    target = active_handler(state(game))
    assert target is not None
    casts = CastService(ActorService(MissionService(ledger)))
    # Facilitation alone is not fictional presence. Actual source-owned cast
    # operations leave the original Pilot and the separately joined Handler only.
    change(casts, ADMIN, "join", target)
    change(casts, OTHER, "withdraw", current_ref(state(game), OTHER.user_id))
    if bond:
        with ledger.transaction() as c:
            canon = state(game)
            event = str(uuid4())
            canon = set_depth(canon, current_ref(canon, PLAYER.user_id), target, 1, event)
            game.event(c, 1, str(uuid4()), "synthetic.prior_handler_bond", canon, event_id=event)
    before = state(game)
    game.dice = Dice((4, 4))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="engage",
            target_actor=target,
            identity=identities[-1],
            gain=1,
            heat=1,
            context="PRIVATE_HANDLER_FEEDBACK: hold this actual Handler back",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    value = next(x for x in rules.sources(state(game)) if x.action == action)
    assert {x.actor for x in value.cast.roles} == {value.actor, target}
    assert value.cast.facilitator == ADMIN.user_id
    assert value.heat_before == before.sheets["2"].heat
    assert state(game).sheets["2"].heat == value.heat_committed == 0
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), value.id) == value
    return game, worker, gateway, service, action, value, target


def finish_handler_engage(game, worker, gateway, action, *, expected_calls=1):
    committed = state(game).sheets["2"].model_copy(deep=True)
    tick(worker, gateway, 3)
    assert game.dice.calls == expected_calls
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and receipt["pre_total"] == 9
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="I use the actual remaining Asset to cover and advance",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets["2"].identities == committed.identities
    assert state(game).sheets["2"].heat == committed.heat
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == expected_calls
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        source = next(x for x in rules.sources(state(game)) if x.action == action)
        assert prove(game, c, state(game), source.id).receipt == receipt["id"]
    assert "PRIVATE_HANDLER" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_handler_only_engage_feedback_owned_purpose_and_refusal(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, service, action, source, target = actual_handler_source(
        ledger, tmp_path, monkeypatch
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    people = game.decision(PLAYER, row["id"])["ankou_feedback"]["people"]
    assert len(people) == 1 and people[0]["ref"] == target.model_dump(mode="json")
    assert people[0]["reprisal_supported"]
    # The separate source-bound Handler Engage normal covers tear/reprisal.

    async def native_choice():
        interaction = current(PLAYER.user_id, 99601)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "purpose/Bond only" not in str(form.fields)
        form.values.update(
            effect=("purpose",),
            target=(target.token,),
            account="PRIVATE_HANDLER_REQUEST: give me a purpose",
        )
        await form.confirm.callback(current(PLAYER.user_id, 99602))
        assert form.completed

    asyncio.run(native_choice())
    response = next(x for x in game.choices(ADMIN) if x["kind"] == "ankou_feedback_purpose")
    private = game.decision(ADMIN, response["id"])["ankou_feedback"]
    assert private["identities"] == private["assets"] == [] and private["heat"] is None
    assert "prepared" not in service.view(ADMIN, source.id)
    with pytest.raises(WorkflowError):
        service.view(OTHER, source.id)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            response["id"],
            response["revision"],
            ChoiceAnswer(flag=True, text="This person cannot answer for the Handler"),
        )
    with ledger.engine.connect() as c:
        stale = state(game).model_copy(deep=True)
        stale.handler = OTHER.user_id
        with pytest.raises(WorkflowError, match="original Handler body"):
            _handler_counterpart(game, c, stale, source, target)
    result = ChoiceAnswer(
        flag=given,
        text="PRIVATE_HANDLER_PURPOSE: protect the wounded" if given else "I refuse this request",
    )
    key = str(uuid4())
    first = game.respond(ADMIN, key, response["id"], response["revision"], result)
    assert game.respond(ADMIN, key, response["id"], response["revision"], result) == first
    assert game.dice.calls == 0
    if not given:
        assert is_helpless(state(game), source.actor, target)
        assert rules.get(state(game), source.id).phase == "ended"
        stopped = game.inspect(PLAYER, action)
        assert stopped["state"] == "complete" and stopped["receipt"] is None
        assert stopped["result"]["blocked_before_roll"]
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        assert game.dice.calls == 0
    else:
        replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
        value = rules.get(state(game), source.id)
        purpose = next(x for x in state(game).sheets["2"].identities if x.id == value.new_identity)
        assert not purpose.marked and purpose.name == result.text
        finish_handler_engage(game, worker, gateway, action)
    assert state(game).handler_heat == 0
    assert "PRIVATE_HANDLER" not in json.dumps(gateway.messages)


def test_handler_only_feedback_rewrites_actual_bond_once(ledger, tmp_path, monkeypatch):
    game, worker, gateway, _, action, source, target = actual_handler_source(
        ledger, tmp_path, monkeypatch, bond=True
    )
    before = state(game)
    assert depth(before, source.actor, target) == 1
    choose(game, "bond", target, name="PRIVATE_HANDLER_BOND_ASSET")
    assert depth(state(game), source.actor, target) == 0
    created = next(x for x in state(game).sheets["2"].assets if x.id == source.id + ":bond")
    assert created.family == "girl" and created.name == "PRIVATE_HANDLER_BOND_ASSET"
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert state(game).handler_tags == before.handler_tags
    assert state(game).handler_heat == before.handler_heat
    assert game.dice.calls == 0
    finish_handler_engage(game, worker, gateway, action)
