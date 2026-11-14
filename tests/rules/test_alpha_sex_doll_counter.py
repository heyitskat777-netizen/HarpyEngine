"""Native Alpha sleep opportunity completes a real Doll before owner-owned waking."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_alpha_doll_counter import interaction, ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_vatgrown import choose

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_alpha_sex import open_alpha_choice
from girlframe.engine import m3_alpha_sex as sex
from girlframe.engine import m3_vatgrown as doll
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_alpha_sex import SexService, counter_plays, doll_counter
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_vatgrown import prove
from girlframe.services.onboarding import WorkflowError


def test_native_doll_sleep_opportunity_completes_real_effects_before_wake(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(sex.RULE, doll.RULE))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    casts = CastService(ActorService(MissionService(ledger)))
    view = casts.view(ADMIN, 900)
    handler = current_ref(state(game), 1)
    # Establish the observer's initial physical position before the source begins;
    # joining a scene alone does not fabricate a Handler location.
    with ledger.transaction() as c:
        initial = state(game)
        initial.facts.append(
            dict(
                kind="recorded_handler_recovery_position",
                actor=handler.model_dump_json(),
                cell="[0, 0]",
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.initial_doll_observer_position", initial)
    view = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", handler
    )
    source = SexService(game)
    alpha, actor = current_ref(state(game), 2), current_ref(state(game), 3)
    session = source.invite(
        PLAYER, str(uuid4()), 900, actor, state(game).revision, "Original voluntary source"
    )["id"]
    source.respond(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        True,
        "Original counterpart's voluntary agreement",
    )
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=sex.PLAY,
            target_actor=actor,
            source_work=session,
            heat=0,
            context="Original confirmed source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    assert sex.asleep(state(game), alpha)
    answer(game, OTHER, "alpha_sex_low", options=("play",))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_sex_counter_play")
    prepared = PlayInput(
        play=doll.PLAY,
        parent=parent,
        target_actor=handler,
        heat=1,
        context="PRIVATE_DOLL_SLEEP I fade away while the Handler watches",
        trigger_confirmed=True,
    )
    before = state(game)
    with ledger.engine.connect() as c:
        original = game.action(c, parent)
        assert doll.PLAY in counter_plays(game, c, before, original, actor)
        with pytest.raises(WorkflowError):
            doll_counter(
                game, c, before, actor, prepared.model_copy(update={"target_actor": alpha}), 900
            )
        with pytest.raises(WorkflowError):
            doll_counter(game, c, before, alpha, prepared, 900)
    assert state(game) == before

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert doll.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        choices = dict(next(x for x in form.fields if x.key == "sleeping_doll_observer").options)
        assert handler.token in choices and alpha.token not in choices
        form.values.update(
            play=(doll.PLAY,),
            sleeping_doll_observer=(handler.token,),
            heat=("1",),
            context=prepared.context,
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            disposable_heat=("0",),
        )
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.edit_original_response.call_args_list,
            submitted.response.send_message.call_args_list,
            submitted.followup.send.call_args_list,
        )
        snapshot = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == snapshot

    asyncio.run(native())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        identity = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "3",
            )
        )
        assert game.action(c, identity)["data"]["alpha_sex_counter_source"]["choice"] == row["id"]
    game.dice.faces = (4, 4)
    tick(worker, gateway, 4)
    pass_tags(game)
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert sex.asleep(state(game), alpha)
    choose(game, OTHER, "vat_doll_benefits", ("quiet", "leave"), native=True)
    actual = state(game)
    with ledger.engine.connect() as c:
        proved = prove(game, c, actual, identity)
        assert proved.complete and proved.actor == actor and proved.target == handler
        assert proved.benefits == ("quiet", "leave")
        assert game.action(c, identity)["data"]["alpha_sex_counter_done"]
        assert "PRIVATE_DOLL_SLEEP" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    assert game.inspect(OTHER, identity)["state"] == "complete"
    assert actual.sheets["3"].heat == before.sheets["3"].heat - 1
    assert sex.get(actual, session).phase == "waking" and sex.asleep(actual, alpha)
    answer(game, PLAYER, "alpha_sex_wake", options=("wake",), text="I wake myself")
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert not sex.asleep(state(game), alpha)
