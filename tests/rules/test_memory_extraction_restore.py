"""A real later embraced Identity restores a Pilot's low-result lost memory."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, answer, state, tick
from test_red_queen import buy, initialize, ready, roll

from girlframe.database import tables as t
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_am_memory import can_recall
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_low_pilot_restores_only_from_owned_genuine_later_identity(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(controls)
    buy(controls, rules.MEMORY)
    before = state(game)
    target = current_ref(before, OTHER.user_id)
    original = before.sheets["3"].identities[0]
    context = controls.record_context(
        OTHER,
        str(uuid4()),
        900,
        before.revision,
        "brain",
        current_ref(before, PLAYER.user_id),
        target,
        "The actual original body is restrained and its brain is accessed",
    )["id"]
    action = roll(
        game, worker, gateway, play="red_queen_memory", faces=(2, 3), target=target, source=context
    )
    answer(
        game,
        PLAYER,
        "red_queen_memory_category",
        options=("person",),
        text="Her instructor",
        fields={"years": "not_year"},
    )
    answer(game, OTHER, "red_queen_memory_links", fields={"memories0": "Her instructor's lessons"})
    tick(worker, gateway, 5)
    loss = next(x for x in rules.records(state(game), rules.Extraction) if x.session == action)
    assert loss.low and loss.am is None and not loss.identities
    assert any(
        (x.id, x.name, x.marked) == (original.id, original.name, original.marked)
        for x in state(game).sheets["3"].identities
    )
    assert not can_recall(state(game), target, loss.memories[0], learned_revision=before.revision)
    with pytest.raises(WorkflowError, match="genuinely follow"):
        controls.restore_memory(
            OTHER,
            "old-association",
            state(game).revision,
            loss.id,
            loss.event,
            original.id,
            None,
            "An old Identity",
        )

    # A real Handler Play supplies a Tag, then two actually witnessed markings
    # produce the target's own embrace choice in a later scene.
    handler = HandlerPlayService(ledger)
    grant = handler.start(ADMIN, "associated-tag-source", state(game).revision, (target,))["id"]
    handler.submit(
        ADMIN,
        "associated-tag",
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="tag",
            target=target,
            tag="Her instructor's student",
            account="The Handler observed the associated conduct",
        ),
    )
    tag = next(x.id for x in state(game).sheets["3"].tags if x.id == grant + ":tag")
    association_event = association_id = None
    for channel in (900, 901):
        if channel == 901:
            game.close_scene(ADMIN, "close-old-scene", 900)
            game.bind_scene(ADMIN, "new-scene", channel)
            for viewer in (ADMIN, PLAYER, OTHER):
                game.join_scene(viewer, str(uuid4()), channel)
        game.dice = Dice((4, 4))
        play = game.begin(
            OTHER,
            str(uuid4()),
            channel,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                trigger_confirmed=True,
                context="Act from her later associated self-description",
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        for viewer in (PLAYER, OTHER):
            answer(game, viewer, "tag_window", options=("pass",))
        answer(
            game,
            ADMIN,
            "tag_window",
            options=("tag",),
            denied=(tag,),
            number=1,
            text="The actual associated Tag applies here",
        )
        if channel == 901:
            answer(game, OTHER, "tag_resolution", options=("embrace",), denied=(original.id,))
            current = state(game)
            association_id = next(
                x.id for x in current.sheets["3"].identities if x.name == "Her instructor's student"
            )
            with ledger.engine.connect() as c:
                history = t.m2["m2_state_history"]
                association_event = c.scalar(
                    sa.select(history.c.event_id).where(
                        history.c.campaign_id == ledger.campaign_id,
                        history.c.revision == current.revision,
                    )
                )
        answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="The declared action succeeds")
        tick(worker, gateway, 5)
        assert game.inspect(OTHER, play)["state"] == "complete"
    assert association_event and association_id
    args = (
        state(game).revision,
        loss.id,
        association_event,
        association_id,
        None,
        "Her new Identity genuinely recalls her original instructor",
    )
    with pytest.raises(WorkflowError, match="affected person"):
        controls.restore_memory(PLAYER, "wrong-restorer", *args)
    restored = controls.restore_memory(OTHER, "restore-memory", *args)
    assert controls.restore_memory(OTHER, "restore-memory", *args) == restored
    final = rules.get(state(game), rules.Extraction, loss.id)
    assert final.restored_event and final.selected_am is None
    assert can_recall(state(game), target, loss.memories[0], learned_revision=before.revision)
