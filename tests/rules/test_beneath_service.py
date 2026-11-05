"""Source-owned social choices inside the actual roll/Tag/lock transaction protocol."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


def ready(store, faces=(4, 5)):
    _, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            ),
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
        }
    )
    game.dice.faces = faces
    return game, GameWorker(game), Gateway()


def start(game, key=None):
    return game.begin(
        PLAYER,
        key or str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="PRIVATE_ACTUAL_SOCIAL_TRIGGER",
            trigger_confirmed=True,
        ),
    )["action_id"]


def rolled(store, faces=(4, 5)):
    game, worker, gateway = ready(store, faces)
    identity = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, identity


def test_mid_actual_roll_owner_choice_replay_and_restart_preserve_one_tag_and_status_effect(ledger):
    game, worker, gateway, identity = rolled(ledger)
    assert game.dice.calls == 1 and not game.choices(OTHER)
    selected = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_select")
    before = state(game)
    result = answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "PRIVATE_SOCIAL_TAG"},
        text="Actual confrontation",
    )
    assert result["state"] == "complete"
    after = state(game)
    assert len(after.sheets["3"].tags) == len(before.sheets["3"].tags) + 1
    assert after.sheets["3"].tags[-1].giver == 2
    assert GameService(ledger).inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_SOCIAL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "cannot-answer-another-owner",
            selected["id"],
            selected["revision"],
            ChoiceAnswer(options=("tag", "status")),
        )


def test_high_pin_requires_actual_pinned_human_response_before_play_completes(ledger):
    game, _, _, identity = rolled(ledger, (6, 6))
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "pin"),
        fields={"tag": "Pinned"},
        text="Actual pin",
    )
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_choices"
    assert not game.choices(PLAYER)
    answer(game, OTHER, "beneath_pin_response", text="PRIVATE_ACTUAL_TARGET_RESPONSE")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert not state(game).sheets["3"].helpless_against


def test_low_counter_damage_preserves_affected_players_private_asset_choice(ledger):
    game, _, _, identity = rolled(ledger, (1, 1))
    assert not game.choices(PLAYER)
    projection = game.decision(OTHER, game.choices(OTHER)[0]["id"])
    assert "assets" not in projection["beneath"] and "bonds" not in projection["beneath"]
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    before = state(game)
    asset = next(x for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    assert not game.choices(OTHER) and game.choices(PLAYER)[0]["kind"] == "beneath_details"
    answer(game, PLAYER, "beneath_details", denied=(asset.id,))
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).damaged
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_bond_effect_waits_for_original_affected_human_and_exposes_no_private_peers_to_chooser(
    ledger,
):
    game, _, _, identity = rolled(ledger)
    projection = game.decision(PLAYER, game.choices(PLAYER)[0]["id"])
    assert "bonds" not in projection["beneath"]
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "bond"),
        fields={"tag": "Insult"},
        text="Actual insult",
    )
    pending = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_details")
    own = game.decision(OTHER, pending["id"])
    token = own["beneath"]["bonds"][0]["token"]
    before = state(game)
    answer(game, OTHER, "beneath_details", fields={"bond": token})
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).bonds != before.bonds


def test_missing_scoped_approval_or_private_choice_ruling_cannot_sample_dice(ledger):
    game, _, _ = ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": None}
            )
        }
    )
    with pytest.raises(WorkflowError, match="UNRESOLVED_RULING"):
        start(game)
    assert game.dice.calls == 0
