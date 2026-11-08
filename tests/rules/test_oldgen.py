"""Actual maxim resources and the three printed advice outcomes, with owned sources."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_oldgen as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_oldgen import OldgenService, prove_advice
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="OLDGEN", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, rules.ADVICE))
    with store.transaction() as c:
        actual = state(game)
        actual.order = (3, 2)
        actual.sheets["2"].heat = 3
        actual.sheets["3"].identities[0].marked = True
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_prior_status_heat_and_marked_Identity", actual
        )
    return game, GameWorker(game), Gateway(), OldgenService(game)


def advice(game, worker, gateway, faces):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            target=3,
            heat=1,
            context="I give actual concrete advice about this danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return identity


def native_choice(game, viewer, kind, text, unmark=()):
    from girlframe.discord_adapter.m3_oldgen import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    decision = game.decision(viewer, row["id"])

    async def submit():
        interaction = current(viewer.user_id, uuid4().int % 1000000000)
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, decision)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = text
        if unmark:
            form.values["unmark"] = unmark
        response = current(viewer.user_id, uuid4().int % 1000000000)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())


def test_actual_base_maxims_heat_tag_and_real_shared_unmark_opportunity(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    first, second = rules.base_maxims(state(game), 2)
    before = state(game)
    key = str(uuid4())
    payload = (
        PLAYER,
        key,
        first.id,
        current_ref(before, 3),
        "reinforce",
        900,
        before.revision,
        "PRIVATE_REINFORCEMENT Another Girl's actual action satisfies my maxim",
    )
    result = controls.use(*payload)
    assert controls.use(*payload) == result
    assert state(game).sheets["3"].heat == before.sheets["3"].heat + 2
    assert first.slot in state(game).sheets["2"].maxims_marked
    controls.use(
        PLAYER,
        str(uuid4()),
        second.id,
        current_ref(state(game), 3),
        "reject",
        900,
        state(game).revision,
        "PRIVATE_REJECTION Her actual conduct rejects my maxim",
        tag="Actual maxim rejection Tag",
    )
    assert state(game).sheets["3"].tags[-1].giver_actor == current_ref(state(game), 2)
    assert len(rules.marked_maxims(state(game), 2)) == 2
    with pytest.raises(WorkflowError):
        controls.view(OTHER, first.id)
    game.dice.faces = (4, 4)
    play = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt", target=3, heat=0, context="An actual conversation", trigger_confirmed=True
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    tokens = tuple(x[0] for x in rules.marked_maxims(state(game), 2))
    answer(game, PLAYER, "actor_flirt", options=("name",), denied=tokens)
    answer(game, OTHER, "target_flirt", text="My actual own answer")
    assert game.inspect(PLAYER, play)["state"] == "complete"
    assert not state(game).sheets["2"].maxims_marked
    with ledger.engine.connect() as c:
        assert "PRIVATE_REINFORCEMENT" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    assert game.dice.calls == 1


@pytest.mark.parametrize("faces,tier", [((1, 1), "low"), ((3, 4), "mid"), ((5, 5), "high")])
def test_actual_advice_printed_outcome_owned_one_use_and_high_rewrite(
    ledger, tmp_path, monkeypatch, faces, tier
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    action = advice(game, worker, gateway, faces)
    assert state(game).sheets["2"].heat == before.sheets["2"].heat - 1
    if tier == "low":
        assert not any(x["kind"] == "oldgen_write_maxim" for x in game.choices(PLAYER))
        native_choice(
            game,
            OTHER,
            "oldgen_low_maxim",
            "PRIVATE_PUP_MAXIM Don't trust this old advice",
            ("identity:0",),
        )
        assert not state(game).sheets["3"].identities[0].marked
        assert state(game).order == before.order
        author, subject = OTHER, current_ref(state(game), 2)
    else:
        assert state(game).order == (2, 3)
        native_choice(
            game, PLAYER, "oldgen_write_maxim", "PRIVATE_TARGET_MAXIM Follow the safe route"
        )
        row = next(x for x in game.choices(OTHER) if x["kind"] == "oldgen_listen")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                row["id"],
                row["revision"],
                ChoiceAnswer(text="Cannot forge listening"),
            )
        with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
            game.begin(
                OTHER,
                str(uuid4()),
                901,
                state(game).sheets["3"].revision,
                PlayInput(
                    play="keep_your_head",
                    heat=0,
                    context="Cannot evade actual listening by another channel",
                    trigger_confirmed=True,
                ),
            )
        native_choice(game, OTHER, "oldgen_listen", "I actually sit down and hear the advice")
        author, subject = PLAYER, current_ref(state(game), 3)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    actual = state(game)
    maxim = rules.records(actual, rules.Maxim)[-1]
    assert maxim.owner == current_ref(actual, author.user_id) and maxim.subject == subject
    with ledger.engine.connect() as c:
        assert prove_advice(game, c, actual, action).maxim == maxim.id
    wrong = current_ref(actual, author.user_id)
    with pytest.raises((WorkflowError, ValueError)):
        controls.use(
            author,
            str(uuid4()),
            maxim.id,
            wrong,
            "reinforce",
            900,
            actual.revision,
            "Cannot use against its author",
        )
    if tier == "high":
        with pytest.raises(WorkflowError):
            controls.record_poor(
                PLAYER,
                str(uuid4()),
                maxim.id,
                900,
                actual.revision,
                "Cannot invent Handler adjudication",
            )
        poor = controls.record_poor(
            ADMIN,
            str(uuid4()),
            maxim.id,
            900,
            actual.revision,
            "PRIVATE_POOR_FACT She actually rejected the route maxim and was trapped as a result",
        )
        prior = state(game)
        selected = controls.view(PLAYER, maxim.id)["replacements"][0]["id"]
        original = game.event

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic rollback")

        monkeypatch.setattr(game, "event", fail)
        with pytest.raises(RuntimeError):
            controls.use(
                PLAYER,
                "high-rewrite-retry",
                maxim.id,
                subject,
                "reject",
                900,
                prior.revision,
                "Actual rejected maxim consequence",
                replaced=selected,
                name="PRIVATE_REAL_REWRITTEN_IDENTITY",
                poor=poor["id"],
            )
        assert state(game) == prior
        monkeypatch.setattr(game, "event", original)
        args = (
            PLAYER,
            "high-rewrite-retry",
            maxim.id,
            subject,
            "reject",
            900,
            prior.revision,
            "Actual rejected maxim consequence",
        )
        kwargs = dict(replaced=selected, name="PRIVATE_REAL_REWRITTEN_IDENTITY", poor=poor["id"])
        result = controls.use(*args, **kwargs)
        assert OldgenService(game).use(*args, **kwargs) == result
        old = next(x for x in prior.sheets["3"].identities if x.id == selected)
        changed = next(x for x in state(game).sheets["3"].identities if x.id == selected)
        assert changed.name == "PRIVATE_REAL_REWRITTEN_IDENTITY"
        assert changed.slot == old.slot and changed.marked == old.marked
        assert state(game).sheets["3"].tags == prior.sheets["3"].tags
    else:
        controls.use(
            author,
            str(uuid4()),
            maxim.id,
            subject,
            "reinforce",
            900,
            actual.revision,
            "The actual named subject reinforces its one-use maxim",
        )
        assert state(game).sheets[subject.entity].heat == actual.sheets[subject.entity].heat + 2
    assert not controls.view(author, maxim.id)["available"]
    if tier == "high":

        async def reopen_history():
            from girlframe.discord_adapter.m3_oldgen import open_oldgen

            interaction = current(author.user_id, 99981)
            interaction.channel_id = 999
            await interaction.response.defer(ephemeral=True)
            saved = state(game)
            await open_oldgen(interaction, OldgenService(game), maxim.id)
            message = interaction.edit_original_response.call_args.kwargs["content"]
            assert maxim.text in message and "used" in message
            assert state(game) == saved

        asyncio.run(reopen_history())
    with pytest.raises((WorkflowError, ValueError)):
        controls.use(
            author,
            str(uuid4()),
            maxim.id,
            subject,
            "reinforce",
            900,
            state(game).revision,
            "Cannot use a one-use maxim twice",
        )
    assert game.dice.calls == 1
