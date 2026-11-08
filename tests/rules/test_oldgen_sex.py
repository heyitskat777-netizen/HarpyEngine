"""Actual voluntary Oldgen sources and the four printed result paths."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_oldgen import ready as oldgen_ready
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.engine import m3_oldgen as maxims
from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.services.m3_oldgen import OldgenService
from girlframe.services.m3_oldgen_sex import OldgenSexService, prove, prove_effect
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    game, worker, gateway, oldgen = oldgen_ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, maxims.RULE, maxims.ADVICE))
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        actual = place(actual, 3, mode="outside_frame")
        game.event(c, 1, str(uuid4()), "synthetic.original_actual_Oldgen_bodies", actual)
    first = maxims.base_maxims(state(game), 2)[0]
    oldgen.use(
        PLAYER,
        str(uuid4()),
        first.id,
        current_ref(state(game), 3),
        "reinforce",
        900,
        state(game).revision,
        "Actual prior reinforcement marks this real maxim",
    )
    return game, worker, gateway, OldgenSexService(game), first


def native_choice(game, viewer, kind, options, *, fields=None, text=""):
    from girlframe.discord_adapter.m3_oldgen_sex import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    decision = game.decision(viewer, row["id"])

    async def submit():
        interaction = current(viewer.user_id, uuid4().int % 1000000000)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, decision)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["effects"] = options
        if fields:
            for key, value in fields.items():
                form.values[key] = (value,) if key == "maxim" else value
        if text:
            form.values["text"] = text
        response = current(viewer.user_id, uuid4().int % 1000000000)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())


def source(game, worker, gateway, service, faces, *, stale=False):
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "PRIVATE_ACTUAL_SOURCE My actual voluntary interaction",
    )["id"]
    with pytest.raises(WorkflowError):
        service.respond(
            PLAYER,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "Cannot answer for the counterpart",
        )
    if stale:
        prior = state(game)
        with pytest.raises(WorkflowError):
            service.respond(
                OTHER,
                str(uuid4()),
                identity,
                prior.revision - 1,
                True,
                "Stale source cannot authorize spending or rolling",
            )
        assert state(game) == prior and game.dice.calls == 0
    service.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "PRIVATE_ACTUAL_CONFIRM My own actual voluntary source",
    )
    game.dice.faces = faces
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=current_ref(before, 3),
            heat=1,
            context="Actual confirmed voluntary interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    return identity, action


def test_native_low_result_rewrites_actual_advice_without_reviving_spent_use(
    ledger, tmp_path, monkeypatch
):
    from test_oldgen import advice
    from test_oldgen import native_choice as advice_choice

    game, worker, gateway, service, _ = setup(ledger, tmp_path, monkeypatch)
    advice(game, worker, gateway, (4, 4))
    advice_choice(game, PLAYER, "oldgen_write_maxim", "PRIVATE_ORIGINAL_TARGET_ONLY_MAXIM")
    advice_choice(game, OTHER, "oldgen_listen", "I actually hear the advice")
    tick(worker, gateway, 5)
    original = maxims.records(state(game), maxims.Maxim)[-1]
    controls = OldgenService(game)
    controls.use(
        PLAYER,
        str(uuid4()),
        original.id,
        original.subject,
        "reinforce",
        900,
        state(game).revision,
        "The intended Girl reinforces my actual one-use maxim",
    )
    before = state(game)
    assert not maxims.available(before, original)
    identity, action = source(game, worker, gateway, service, (1, 1))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "oldgen_sex_rewrite")
    assert (original.id, original.text) in game.decision(OTHER, row["id"])["detail"]["rewrite"]
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("rewrite",), fields={"maxim": original.id}, text="Forged"),
        )
    native_choice(
        game,
        OTHER,
        "oldgen_sex_rewrite",
        ("rewrite",),
        fields={"maxim": original.id},
        text="PRIVATE_REWRITTEN_TARGET_ONLY_MAXIM",
    )
    actual = state(game)
    rewritten = maxims.get(actual, original.id)
    assert rewritten.text == "PRIVATE_REWRITTEN_TARGET_ONLY_MAXIM"
    assert rewritten.model_dump(exclude={"text"}) == original.model_dump(exclude={"text"})
    assert not maxims.available(actual, rewritten)
    assert maxims.records(actual, maxims.Use) == maxims.records(before, maxims.Use)
    assert controls.view(PLAYER, original.id)["text"] == rewritten.text
    assert controls.view(PLAYER, original.id)["status"] == "used"
    assert (
        next(x for x in controls.menu(PLAYER, 900)["maxims"] if x["id"] == original.id)["text"]
        == rewritten.text
    )
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, original.id)
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, identity).phase == "complete"
        for effect in rules.records(actual, rules.Effect):
            prove_effect(game, c, actual, effect.id)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with pytest.raises((WorkflowError, ValueError)):
        controls.use(
            PLAYER,
            str(uuid4()),
            original.id,
            original.subject,
            "reinforce",
            900,
            actual.revision,
            "Text cannot create a second use",
        )


@pytest.mark.parametrize(
    "branch,faces", [("low", (1, 1)), ("mid", (3, 4)), ("yes", (5, 5)), ("no", (5, 5))]
)
def test_actual_oldgen_sex_all_printed_result_paths(ledger, tmp_path, monkeypatch, branch, faces):
    game, worker, gateway, service, original_maxim = setup(ledger, tmp_path, monkeypatch)
    identity, action = source(game, worker, gateway, service, faces, stale=branch == "low")
    before = state(game)
    token = "oldgen:" + str(original_maxim.slot)
    if branch == "low":
        assert not game.choices(PLAYER)
        native_choice(
            game,
            OTHER,
            "oldgen_sex_rewrite",
            ("rewrite",),
            fields={"maxim": token},
            text="PRIVATE_REWRITTEN_MAXIM We protect one another",
        )
        actual = state(game)
        rewritten = maxims.get(actual, original_maxim.id)
        assert rewritten.text == "PRIVATE_REWRITTEN_MAXIM We protect one another"
        assert (
            rewritten.slot == original_maxim.slot
            and original_maxim.slot in actual.sheets["2"].maxims_marked
        )
        assert OldgenService(game).view(PLAYER, original_maxim.id)["text"] == rewritten.text
    elif branch == "mid":
        native_choice(
            game,
            PLAYER,
            "oldgen_sex_effects",
            ("tag", "status"),
            fields={"tag": "PRIVATE_ACTUAL_MID_TAG"},
        )
        actual = state(game)
        tag = actual.sheets["3"].tags[-1]
        assert tag.label == "PRIVATE_ACTUAL_MID_TAG" and tag.giver_actor == current_ref(actual, 2)
        assert actual.order == (2, 3)
    elif branch == "yes":
        bond = depth(before, current_ref(before, 2), current_ref(before, 3))
        native_choice(
            game, PLAYER, "oldgen_sex_effects", ("unmark", "bond"), fields={"maxim": token}
        )
        assert original_maxim.slot not in state(game).sheets["2"].maxims_marked
        assert depth(state(game), current_ref(before, 2), current_ref(before, 3)) == min(
            2, bond + 1
        )
        creep = next(x for x in game.choices(OTHER) if x["kind"] == "oldgen_sex_creep")
        question = game.decision(OTHER, creep["id"])["detail"]
        assert not question["maxims"] and not question["rewrite"]
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER, str(uuid4()), creep["id"], creep["revision"], ChoiceAnswer(options=("no",))
            )
        native_choice(game, OTHER, "oldgen_sex_creep", ("yes",))
        row = next(x for x in game.choices(OTHER) if x["kind"] == "oldgen_sex_effects")
        prior = state(game)
        original = game.event

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic commit failure")

        monkeypatch.setattr(game, "event", fail)
        with pytest.raises(RuntimeError):
            game.respond(
                OTHER,
                "reciprocal-retry",
                row["id"],
                row["revision"],
                ChoiceAnswer(options=("helpless",)),
            )
        assert state(game) == prior
        monkeypatch.setattr(game, "event", original)
        result = game.respond(
            OTHER,
            "reciprocal-retry",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("helpless",)),
        )
        assert (
            game.respond(
                OTHER,
                "reciprocal-retry",
                row["id"],
                row["revision"],
                ChoiceAnswer(options=("helpless",)),
            )
            == result
        )
        assert is_helpless(state(game), current_ref(before, 2), current_ref(before, 3))
        assert is_helpless(state(game), current_ref(before, 2), current_ref(before, 1))
    else:
        native_choice(
            game,
            PLAYER,
            "oldgen_sex_effects",
            ("helpless", "tag"),
            fields={"tag": "PRIVATE_ACTUAL_HIGH_TAG"},
        )
        native_choice(game, OTHER, "oldgen_sex_creep", ("no",))
        native_choice(game, PLAYER, "oldgen_sex_effects", ("status",))
        assert is_helpless(state(game), current_ref(before, 3))
        assert state(game).order == (2, 3)
        assert (
            len([x for x in rules.records(state(game), rules.Effect) if x.session == identity]) == 3
        )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    actual = state(game)
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, identity).phase == "complete"
        for effect in rules.records(actual, rules.Effect):
            prove_effect(game, c, actual, effect.id)
        assert "PRIVATE_ACTUAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        service.view(ADMIN, identity)
    if branch == "yes":
        with pytest.raises(WorkflowError, match="Helpless"):
            game.begin(
                PLAYER,
                str(uuid4()),
                900,
                actual.sheets["2"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=0,
                    context="Cannot act while physiologically helpless",
                    trigger_confirmed=True,
                ),
            )
        game.recover_helpless(
            PLAYER,
            "actual-recovery",
            actual.sheets["2"].revision,
            "I actually take a moment alone to recover",
            None,
        )
        assert not is_helpless(state(game), current_ref(state(game), 2))
        saved = state(game)

        async def reopen():
            from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex

            interaction = current(2, 99282)
            interaction.channel_id = 999
            await interaction.response.defer(ephemeral=True)
            await open_oldgen_sex(interaction, OldgenSexService(game), identity)
            assert "complete" in interaction.edit_original_response.call_args.kwargs["content"]

        asyncio.run(reopen())
        assert state(game) == saved
    assert game.dice.calls == 1
