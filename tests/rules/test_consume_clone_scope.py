"""Real Frame-hosted Clone source has no separate Eat body; native targets remain."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_consume import ready
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_clone_am as clones
from girlframe.engine import m3_consume as consume
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_clone_am import CloneService
from girlframe.services.m3_consume_clone import require_physical_target
from girlframe.services.m3_consume_support import context
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def purchased_copy(store, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(store, tmp_path, monkeypatch)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(consume.STARVATION, consume.EAT, *consume.REQUISITIONS, clones.RULE),
    )
    with store.transaction() as c:
        before = state(game)
        before.sheets["3"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.prior_actual_clone_permissions", before)
    source = CloneService(game)
    data = source.menu(OTHER)
    purchase = (
        OTHER,
        str(uuid4()),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual existing original Frame gains its own artificial brain copy",
        "THE PRINCE",
    )
    saved = source.buy(*purchase)
    assert source.buy(*purchase) == saved
    (copy,) = clones.copies(state(game))
    cast_change(CastService(ActorService(MissionService(store))), OTHER, "join", copy.ref)
    return game, controls, copy.ref


def test_paid_frame_hosted_copy_is_not_an_eat_body_before_any_cost_or_roll(
    ledger, tmp_path, monkeypatch
):
    game, controls, copy = purchased_copy(ledger, tmp_path, monkeypatch)
    before = state(game)
    with ledger.engine.connect() as c:
        actual = resolve(before, copy, profiles(c, ledger.campaign_id))
        assert actual.rules == "clone_am" and actual.inside_frame and actual.vessel_id is None
        lock = game.lock(c, 900)
        with pytest.raises(WorkflowError, match="SOURCE_CLONE_BODY_REQUIRED.*without a separately"):
            require_physical_target(game, c, before, copy)
    assert copy.token not in {x["token"] for x in controls.menu(PLAYER, 900)["targets"]}
    key = str(uuid4())
    for _ in range(2):
        with pytest.raises(WorkflowError, match="SOURCE_CLONE_BODY_REQUIRED.*without a separately"):
            game.begin(
                PLAYER,
                key,
                900,
                before.sheets["2"].revision,
                PlayInput(
                    play="consume_eat",
                    target_actor=copy,
                    heat=1,
                    context="I try to put jaws around the actual copy itself",
                    trigger_confirmed=True,
                ),
            )
    assert state(game) == before and game.dice.calls == 0
    assert clones.current(state(game), copy) == clones.current(before, copy)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900) == lock
        assert not game.pending_actions(c)


def test_copy_host_does_not_replace_or_block_actual_embodied_native_eat_target(
    ledger, tmp_path, monkeypatch
):
    game, controls, copy = purchased_copy(ledger, tmp_path, monkeypatch)
    before = state(game)
    physical = current_ref(before, 3)
    available = {x["token"] for x in controls.menu(PLAYER, 900)["targets"]}
    assert physical.token in available and copy.token not in available
    with ledger.engine.connect() as c:
        require_physical_target(game, c, before, physical)
        facts = context(
            game, c, before, current_ref(before, 2), physical, _cast(game, c, before, 900)
        )
        assert (
            facts["target_vessel"]
            == resolve(before, physical, profiles(c, ledger.campaign_id)).vessel_id
        )
    # Normal admission is the original physical person, never an automatic proxy.
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="consume_eat",
            target_actor=physical,
            heat=1,
            context="I actually lunge at this co-present original body",
            trigger_confirmed=True,
        ),
    )["action_id"]
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["data"]["consume"]["target"] == physical.model_dump(mode="json")
    assert clones.current(state(game), copy) == clones.current(before, copy)
    assert game.dice.calls == 0
