"""Actual paid same-copy Identity erasure, without deleting or regenerating the person."""

from uuid import uuid4

import pytest
from test_changeling import define, ready, roll
from test_enforcer_requisitions import approved
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_changeling as rules
from girlframe.engine import m3_clone_am as clone
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_clone_residency import residence
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_clone_am import CloneService, prove_copy


def test_high_blank_erases_actual_copy_identity_preserving_same_person_and_resources(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.BLANK, rules.STRINGS, rules.FINGERS, *rules.REQUISITIONS, clone.RULE),
    )
    service = CloneService(game)
    menu = service.menu(PLAYER)
    service.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        current_ref(state(game), 2),
        menu["frame"],
        "Actual paid copy for this native Blank Slate",
        "THE PRINCE",
    )
    before = state(game)
    born = clone.copies(before)[0]
    old_frame = residence(before, born.ref)
    with ledger.engine.connect() as c:
        prove_copy(game, c, before, born.ref)
    action = roll(game, worker, gateway, source=define(game, controls), faces=(6, 6))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    after = state(game)
    saved = clone.current(after, born.ref)
    assert saved.ref == born.ref and saved.original == born.original
    assert saved.receipt == born.receipt and saved.source_event == born.source_event
    assert saved.identity == born.identity and saved.identity_erased_event
    assert saved.tags == born.tags and after.actor_bonds == before.actor_bonds
    assert residence(after, saved.ref) == old_frame
    assert after.requisitions == before.requisitions
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.sheets["2"].heat == before.sheets["2"].heat - 1
    assert clone.additional_identities(after, 2) == ()
    assert any(x.name == "Blank Slate" for x in after.sheets["2"].identities)
    with ledger.engine.connect() as c:
        prove_copy(game, c, after, saved.ref)
        actual = resolve(after, saved.ref, profiles(c, ledger.campaign_id))
        assert actual.alive and actual.identities == ()
    assert service.view(PLAYER)["identity"] is None
    with pytest.raises(ValueError):
        clone.mark_additional(after, after.sheets["2"], born.identity.id, 1)
    with pytest.raises(ValueError):
        clone.unmark_additional(after, 2, (born.identity.id,))
    assert len([x for x in after.facts if x.get("kind") == "clone_identity_erased"]) == 1
    assert game.dice.calls == 1


def test_low_copy_erasure_then_real_tag_reacquisition_survives_service_reopen(
    ledger, tmp_path, monkeypatch
):
    """No invented replacement: the same purchased copy earns and embraces a real Tag."""
    from test_actor_play_service import pass_tags
    from test_changeling import respond
    from test_clone_am import cast_copy, finish_keep, start
    from test_ledger import ADMIN, OTHER
    from test_m2_game import Gateway, answer, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import ChoiceAnswer
    from girlframe.engine.m3_identity_slots import bind
    from girlframe.services.m2_game import GameService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.BLANK, rules.STRINGS, rules.FINGERS, *rules.REQUISITIONS, clone.RULE),
    )
    service = CloneService(game)
    menu = service.menu(PLAYER)
    service.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        current_ref(state(game), 2),
        menu["frame"],
        "Actual paid copy for chosen low erasure and subsequent same-copy Tag growth",
        "THE PRINCE",
    )
    before = state(game)
    (born,) = clone.copies(before)
    statement = define(game, controls)
    speech = rules.record(state(game), rules.Speech, statement)
    action = roll(game, worker, gateway, source=statement, faces=(1, 1))
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "changeling_low_erase")
    assert born.identity.id in dict(game.decision(PLAYER, choice["id"])["detail"]["identities"])
    respond(
        game,
        PLAYER,
        "changeling_low_erase",
        ChoiceAnswer(
            denied=(born.identity.id,), text="I choose my actual additional copy Identity"
        ),
    )
    erased = state(game)
    assert clone.current(erased, born.ref).identity_erased_event
    # Erasure normalizes legacy ordinary slots through bind(); it does not replace
    # any original Identity. Compare the complete resources with that canonical shape.
    original_identities = bind(before.sheets["2"]).identities
    assert erased.sheets["2"].identities == original_identities
    assert game.inspect(PLAYER, action)["state"] != "complete"
    respond(
        game,
        ADMIN,
        "changeling_recent",
        ChoiceAnswer(
            fields={"start_event": speech.event},
            text="The definition started these recent fictional minutes; retain OOC history",
        ),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)

    # Reconstruct services against the saved DB, not a constructed replacement snapshot.
    game = GameService(game.store, dice=game.dice)
    worker, gateway = GameWorker(game), Gateway()
    assert CloneService(game).view(PLAYER)["identity"] is None
    cast_copy(game, born.ref)
    action = start(game, born.ref, faces=(6, 6))
    tick(worker, gateway, 3)
    pass_tags(game)
    finish_keep(game, high=True)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    (tag,) = clone.tags(state(game), born.ref)
    for second in (False, True):
        if second:
            game.close_scene(ADMIN, str(uuid4()), 900)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for viewer in (PLAYER, OTHER, ADMIN):
                game.join_scene(viewer, str(uuid4()), 900)
            cast_copy(game, born.ref)
        action = start(game, born.ref, faces=(2, 3))
        tick(worker, gateway, 3)
        answer(game, ADMIN, "tag_window", options=("pass",))
        answer(game, PLAYER, "tag_window", options=("pass",))
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=(tag.id,),
            number=1,
            fields={"as_actor": current_ref(state(game), 3).token},
            text="I observed this same copy's Tag and it applies here",
        )
        if second:
            row = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_resolution")
            decision = game.decision(PLAYER, row["id"])
            assert decision["copy_identity_cap"] == 1 and not decision["own"]["identities"]
            answer(game, PLAYER, "tag_resolution", options=("embrace",))
        finish_keep(game)
        tick(worker, gateway, 5)
        assert game.inspect(PLAYER, action)["state"] == "complete"

    reopened = GameService(game.store, dice=game.dice)
    saved_state = state(reopened)
    saved = clone.current(saved_state, born.ref)
    assert (saved.ref, saved.original, saved.receipt, saved.source_event) == (
        born.ref,
        born.original,
        born.receipt,
        born.source_event,
    )
    assert saved.identity.name == tag.label and saved.identity.id != born.identity.id
    assert saved.identity_erased_event is None and not saved.tags
    assert residence(saved_state, saved.ref) == residence(before, born.ref)
    assert saved_state.sheets["2"].identities == original_identities
    assert saved_state.sheets["2"].heat == before.sheets["2"].heat - 1
    assert saved_state.requisitions == before.requisitions
    assert len([x for x in saved_state.facts if x.get("kind") == "clone_identity_erased"]) == 1
    with ledger.engine.connect() as c:
        prove_copy(reopened, c, saved_state, saved.ref)
        assert resolve(saved_state, saved.ref, profiles(c, ledger.campaign_id)).alive
    assert reopened.dice.calls == 4
