"""Real Pair and earned lesson source; prior nonnative book is explicit fixture context."""

from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from test_bonded import pass_tags, pick, propose, ready, roll, show, submit
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_vatgrown_plays import native_choice

from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m3_bonded import original_pair, prove
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService, prove_learned_play
from girlframe.services.onboarding import WorkflowError


def test_earned_side_uses_original_pair_once_without_copying_paired_resources(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, paired_target=True
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vat.SEX))
    original = state(game)
    actor, teacher = current_ref(original, 2), current_ref(original, 4)
    with ledger.engine.connect() as connection:
        pair, pair_source = original_pair(game, connection, original, actor)
    # Scope is learning/use, not Girl-transition certification. The independently
    # real reviewed Pair and protected slot predate this saved nonnative context.
    with ledger.transaction() as connection:
        prior = state(game)
        prior.sheets["2"].girl = "VATGROWN"
        prior.sheets["2"].heat = 1
        ordinary = next(x for x in prior.sheets["4"].identities if not x.protected)
        ordinary.name = "My actual distinct teacher Identity"
        game.event(connection, 1, str(uuid4()), "synthetic.prior_nonnative_pair_context", prior)
    assert not has_rule(state(game).sheets["2"], bonded.SIDE, "BONDED")
    baseline_pair = state(game).sheets["2"].pair
    protected = tuple(x.model_dump() for x in state(game).sheets["2"].identities if x.paired)
    assets = state(game).sheets["2"].assets
    source = VatgrownPlaysService(game)
    session = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "My original counterpart teaches only her actual chosen rule",
    )["id"]
    source.respond(
        FOUR,
        str(uuid4()),
        session,
        state(game).revision,
        True,
        "I voluntarily confirm this actual teaching source",
    )
    game.dice.faces = (5, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=session,
            heat=1,
            context="The actual mutually confirmed source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    replacement = next(x for x in actual.sheets["2"].identities if not x.protected)
    taught = next(
        x for x in actual.sheets["4"].identities if x.name == "My actual distinct teacher Identity"
    )
    native_choice(
        game,
        FOUR,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(bonded.SIDE,),
        account="My actual Always By Her Side, not my Pair or protected Identity",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert lesson.actor == actor and lesson.teacher == teacher and lesson.rule_id == bonded.SIDE
    assert game.inspect(PLAYER, action)["state"] == "complete"
    source.send_away(
        FOUR,
        str(uuid4()),
        session,
        state(game).revision,
        "The original counterpart ends this required stay",
    )
    tick(worker, gateway, 6)
    before_use = state(game)
    assert before_use.sheets["2"].pair == baseline_pair
    assert tuple(x.model_dump() for x in before_use.sheets["2"].identities if x.paired) == protected
    assert before_use.sheets["2"].assets == assets
    with ledger.engine.connect() as connection:
        assert prove_learned_play(game, connection, before_use, lesson.id) == lesson
        assert original_pair(game, connection, before_use, actor, bonded.SIDE) == (
            pair,
            pair_source,
        )
    menu_data = controls.menu(PLAYER, 900)
    assert menu_data["available"] == ["side"]
    menu = show(controls)
    form = submit(menu, PLAYER, {"source": ("side",)}, 99101)
    submit(
        form,
        PLAYER,
        {
            "apart": ("yes",),
            "account": "I want to be with my actual original Pair; we are apart",
        },
        99102,
    )
    identity = bonded.records(state(game), bonded.Source)[-1].id
    calls = game.dice.calls
    side_action = roll(game, worker, gateway, identity, (6, 6))
    pick(
        game,
        PLAYER,
        "bonded_side",
        ("arrive", "weapon"),
        weapon_name="An actual loose iron bar",
        weapon_description="Found and carried, not an Asset",
    )
    tick(worker, gateway, 3)
    after = state(game)
    use = next(x for x in after.sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
    assert use.claimed_action == side_action and use.rolled_event
    assert game.dice.calls == calls + 1
    assert after.sheets["2"].pair == baseline_pair and after.sheets["2"].assets == assets
    item = next(
        x
        for x in after.held_items
        if x.id == "bonded-weapon:" + str(uuid5(NAMESPACE_URL, identity))
    )
    assert item.holder == actor and item.source_owner == actor
    assert item.factual_source_action == side_action and item.weapon
    assert item.asset_id is None and item.asset_json is None
    assert item.confirmed_event == item.source_event and item.confirmed_by == actor
    with ledger.engine.connect() as connection:
        from girlframe.services.m3_bonded_support import prove_found_weapon

        assert prove(game, connection, after, identity).phase == "complete"
        prove_found_weapon(game, connection, after, item)
    with pytest.raises(WorkflowError):
        propose(controls, game, "side")
    receipt = game.inspect(PLAYER, side_action)["receipt"]
    assert game.roll(PLAYER, "same-side-receipt", side_action)["receipt"] == receipt
    assert game.dice.calls == calls + 1
