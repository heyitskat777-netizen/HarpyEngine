"""Actual Stim Sex sources, all printed outcomes and usable lasting consequences."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import ready as psyche_ready
from test_disposable_psyche import real_period
from test_dose_up import ready as dose_ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import call, finish_routine, movement, roll_for

from girlframe.database import tables as t
from girlframe.engine import m3_disposable_psyche as psyche
from girlframe.engine import m3_stim_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_dose_up import SELF_RULE
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.services.inbox import InboxService
from girlframe.services.m3_disposable_psyche import PsycheService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_stim_sex import SexService, order_authority, valid_order
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch, *, lower=False, native=False, period_context=False):
    if period_context:
        _, game, worker, gateway, _ = psyche_ready(store, tmp_path, monkeypatch)
    else:
        game, worker, gateway, _ = dose_ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, SELF_RULE, psyche.RULE))
    if lower:
        with store.transaction() as c:
            actual = state(game)
            actual.order = (3, 2)
            game.event(c, 1, str(uuid4()), "synthetic.actual_prior_Status", actual)
    service = SexService(game)
    if native:
        from girlframe.discord_adapter.m3_stim_sex import open_stim

        async def invite():
            interaction = current(2, 99101)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_stim(interaction, service)
            menu = interaction.edit_original_response.call_args.kwargs["view"]
            menu.values["source"] = ("invite",)
            opened = current(2, 99102)
            await menu.confirm.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                target=(current_ref(state(game), 3).token,),
                account="PRIVATE_STIM_PROPOSAL actual voluntary interaction",
            )
            await form.confirm.callback(current(2, 99103))
            assert form.completed

        asyncio.run(invite())
        identity = rules.records(state(game), rules.Session)[-1].id
    else:
        identity = service.invite(
            PLAYER,
            str(uuid4()),
            900,
            current_ref(state(game), 3),
            state(game).revision,
            "PRIVATE_STIM_PROPOSAL actual voluntary interaction",
        )["id"]
    with pytest.raises(WorkflowError):
        service.respond(
            PLAYER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "Cannot speak for the other person",
        )
    if native:

        async def consent():
            from girlframe.discord_adapter.inbox import InboxView

            inbox = InboxService(store)
            item = next(
                x for x in inbox.items(OTHER) if x.identity == identity and x.task == "m3_stim_sex"
            )
            interaction = current(3, 99104)
            interaction.channel_id = 901
            await interaction.response.defer(ephemeral=True)
            await InboxView(inbox, 3).route(interaction, item)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                accept=("yes",), account="PRIVATE_STIM_CONFIRM My own actual voluntary source"
            )
            await form.confirm.callback(current(3, 99105))
            assert form.completed

        asyncio.run(consent())
    else:
        service.respond(
            OTHER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "PRIVATE_STIM_CONFIRM My own actual voluntary source",
        )
    assert game.dice.calls == 0
    return game, worker, gateway, service, identity


def rolled(
    store, tmp_path, monkeypatch, faces, *, heat=0, lower=False, native=False, period_context=False
):
    game, worker, gateway, service, identity = setup(
        store, tmp_path, monkeypatch, lower=lower, native=native, period_context=period_context
    )
    before = state(game)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=current_ref(before, 3),
            heat=heat,
            context="Our actual voluntarily confirmed intimacy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, service, identity, action


def choose(game, viewer, kind, options, *, tag="", native=False):
    if not native:
        return answer(game, viewer, kind, options=options, text=tag)
    from girlframe.discord_adapter.m3_stim_sex import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def own():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=options, tag=tag)
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    return asyncio.run(own())


def keep(game, worker, gateway, viewer, *, drug=None):
    game.dice.faces = (3, 4) if drug else (4, 5)
    current_heat = state(game).sheets[str(viewer.user_id)].heat
    actual_spend = current_heat if current_heat >= 5 else 0
    action = game.begin(
        viewer,
        str(uuid4()),
        900,
        state(game).sheets[str(viewer.user_id)].revision,
        PlayInput(
            play="keep_your_head",
            heat=actual_spend,
            context="Actual danger in this real subsequent scene",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, OTHER, ADMIN):
        if drug and human == PLAYER:
            answer(
                game,
                human,
                "tag_window",
                options=("tag",),
                denied=(drug,),
                number=1,
                text="The actual drug changes these reactions",
            )
        else:
            answer(game, human, "tag_window", options=("pass",))
    row = next(x for x in game.choices(viewer) if x["kind"] == "actor_keep")
    level = game.decision(viewer, row["id"])["result"]["tier"]
    if level == "high":
        answer(game, viewer, "actor_keep", text="An actual successful evasion impression")
    elif level == "mid":
        answer(game, viewer, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    else:
        answer(game, viewer, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual danger adjudication")
    assert game.inspect(viewer, action)["state"] == "complete"
    tick(worker, gateway, 5)
    return action


def close_and_reopen(game):
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)


def test_mid_real_lower_status_order_drug_tag_consumer_expiry_and_private_saved_source(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, identity, action = rolled(
        ledger, tmp_path, monkeypatch, (3, 4), heat=1, lower=True, native=True
    )
    choose(game, PLAYER, "stim_sex_drug", ("quick",), native=True)
    choose(game, PLAYER, "stim_sex_effects", ("orders",), native=True)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert state(game).sheets["2"].heat == 2 and not higher(state(game), 2, 3)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert order_authority(game, c, state(game), 2, 3)
    order = game.issue_order(PLAYER, str(uuid4()), 900, 3, "Remain with the group while recovering")
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        row = dict(
            c.execute(
                sa.select(t.m2["m2_orders"]).where(t.m2["m2_orders"].c.id == order["order_id"])
            )
            .mappings()
            .one()
        )
        assert valid_order(game, c, state(game), row)
    answer(game, OTHER, "order_response", options=("obedient",))
    tick(worker, gateway, 5)
    assert game.inspect(OTHER, order["action_id"])["state"] == "complete"
    drug = rules.records(state(game), rules.Drug)[-1]
    close_and_reopen(game)
    keep(game, worker, gateway, OTHER, drug=drug.id)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert rules.expired(state(game), drug.id) and not any(
        x.id == drug.id for x in state(game).sheets["3"].tags
    )
    with ledger.engine.connect() as c:
        assert order_authority(game, c, state(game), 2, 3) is None
        assert valid_order(game, c, state(game), row)
    with pytest.raises(WorkflowError):
        service.view(ADMIN, identity)
    assert service.view(PLAYER, identity)["drugs"][0]["expired"]
    assert "PRIVATE_STIM_CONFIRM" not in json.dumps(gateway.messages)

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.identity == identity and x.task == "m3_stim_sex"
        )
        interaction = current(2, 99110)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        assert "expired" in interaction.edit_original_response.call_args.kwargs["content"]

    asyncio.run(reopen())


def test_high_reciprocal_real_effects_helpless_self_mark_and_disposable_consumer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, identity, action = rolled(
        ledger, tmp_path, monkeypatch, (6, 6), period_context=True
    )
    before = state(game)
    choose(game, PLAYER, "stim_sex_drug", ("calm",))
    choose(game, PLAYER, "stim_sex_drug", ("strong",))
    choose(game, PLAYER, "stim_sex_effects", ("helpless", "bond"))
    choose(game, OTHER, "stim_sex_effects", ("tag",), tag="Lasting shared impression", native=True)
    actual = state(game)
    assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == min(
        2, depth(before, current_ref(before, 2), current_ref(before, 3)) + 1
    )
    assert is_helpless(actual, current_ref(actual, 3))
    assert any(
        x.label == "Lasting shared impression" and x.giver_actor == current_ref(actual, 3)
        for x in actual.sheets["2"].tags
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    saved = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="Helpless"):
        game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Cannot make a defensive Keep while drug-Helpless",
                trigger_confirmed=True,
            ),
        )
    assert state(game).model_dump_json() == saved and game.dice.calls == 1
    own_drug = next(
        x for x in rules.records(actual, rules.Drug) if x.target == current_ref(actual, 2)
    )
    keep(game, worker, gateway, PLAYER, drug=own_drug.id)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "world", "playbooks"}}
            )
        }
    )
    cycle, period = real_period(MissionService(ledger), game)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    rebuilding = PsycheService(ledger, game)
    work = next(x for x in rebuilding.menu(PLAYER)["tasks"] if x["pending"])
    chosen = psyche.TagSelection(tag=own_drug.id, replace=state(game).sheets["2"].identities[0].id)
    rebuilding.convert(PLAYER, str(uuid4()), work["id"], state(game).revision, (chosen,))
    new_id = psyche.conversions(state(game))[-1].created[0].id
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    tick(worker, gateway, 5)
    close_and_reopen(game)
    keep(game, worker, gateway, PLAYER)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert not is_helpless(state(game), current_ref(state(game), 3))
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)
    keep(game, worker, gateway, OTHER)
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    assert any(
        x.id == new_id and x.name == "Upper:Strong" for x in state(game).sheets["2"].identities
    )
    assert any(x.label == "Lasting shared impression" for x in state(game).sheets["2"].tags)
    assert all(x["expired"] for x in service.view(PLAYER, identity)["drugs"])


@pytest.mark.parametrize("take", [False, True])
def test_low_actual_counterpart_three_effects_optional_self_drug_and_source_retry(
    ledger, tmp_path, monkeypatch, take
):
    game, worker, gateway, service, identity, action = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    choose(game, OTHER, "stim_sex_drug", ("talk",), native=True)
    choose(
        game,
        OTHER,
        "stim_sex_effects",
        ("helpless", "orders", "tag"),
        tag="An actual lasting low-result impression",
    )
    row = next(x for x in game.choices(OTHER) if x["kind"] == "stim_sex_optional")
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("take",))
        )
    assert state(game).model_dump_json() == snapshot
    key = str(uuid4())
    response = ChoiceAnswer(options=("take",) if take else ("decline",))
    reply = game.respond(OTHER, key, row["id"], row["revision"], response)
    assert game.respond(OTHER, key, row["id"], row["revision"], response) == reply
    if take:
        choose(game, OTHER, "stim_sex_drug", ("bliss",))
    actual = state(game)
    assert len(rules.records(actual, rules.Drug)) == (2 if take else 1)
    assert is_helpless(actual, current_ref(actual, 2))
    assert not is_helpless(actual, current_ref(actual, 3))
    assert len(rules.records(actual, rules.Effect)) == 3
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert any(
        x.label == "An actual lasting low-result impression"
        and x.giver_actor == current_ref(actual, 3)
        for x in actual.sheets["2"].tags
    )
    tick(worker, gateway, 5)
    order = game.issue_order(OTHER, str(uuid4()), 900, 2, "Stay here until you recover")
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, order["action_id"])["state"] == "complete"
    close_and_reopen(game)
    keep(game, worker, gateway, OTHER)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert not is_helpless(state(game), current_ref(state(game), 2))
    assert all(x["expired"] for x in service.view(OTHER, identity)["drugs"])
    assert any(
        x.label == "An actual lasting low-result impression" for x in state(game).sheets["2"].tags
    )
