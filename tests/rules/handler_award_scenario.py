"""Shared real ordinary Handler campaign, Session and successful PR award scenario."""

from uuid import uuid4

from test_enforcer_requisitions import approved
from test_handler_ordinary import session_native, setup
from test_ledger import ADMIN, PLAYER
from test_m2_game import state
from test_physical_operations import place

from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_world_state import Location
from girlframe.services.m3_handler_pr import HandlerPRService


def ordinary_pr_award(store, tmp_path, monkeypatch):
    game, ordinary, worker, gateway = setup(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE,))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"world", "discipline"}}
            )
        }
    )
    with store.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.world = canon.world.model_copy(
            update=dict(
                locations=(
                    Location(id="base0", name="Actual briefing room", cell=(0, 0), kind="base"),
                    Location(id="base1", name="Actual personnel office", cell=(1, 0), kind="base"),
                ),
                npcs=(canon.world.npcs[0].model_copy(update=dict(cell=(1, 0))),),
            )
        )
        game.event(c, 1, "actual-handler-award-initial-facts", "synthetic.initial_facts", canon)
    session_native(ordinary, "Actual Handler advancement Session", 41000)
    pr = HandlerPRService(store)
    event = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual Foundation media fundraiser",
        "Real Foundation photoshoot and public interview",
        (current_ref(state(game), 2),),
    )["id"]
    for viewer, hosting, account in (
        (ADMIN, True, "I actually hosted the Foundation presentation"),
        (PLAYER, False, "I actually posed and spoke in the public Foundation feature"),
    ):
        pr.activity(viewer, str(uuid4()), event, state(game).revision, account, hosting=hosting)
    pr.submit_result(ADMIN, str(uuid4()), event, state(game).revision, "Actual event is performed")
    pr.resolve(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        True,
        "The actual Foundation fundraiser and public feature succeeded",
    )
    return game, worker, gateway
