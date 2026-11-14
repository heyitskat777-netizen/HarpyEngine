"""One ordinary high-Protector arrival, private projection and voluntary Tag flow."""

from uuid import uuid4

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_wyvern import buy, free_chat, ready, roll

from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.m3_wyvern import _tasks
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def test_high_protector_late_arrival_has_private_owned_approach_and_parting_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    buy(controls, rules.PROTECT)
    target = current_ref(state(game), 3)
    roll(game, worker, gateway, play="wyvern_protector", target=target, faces=(6, 6))
    free_chat(worker, gateway)
    shield = rules.records(state(game), rules.Shield)[-1]
    newcomer = GuildViewer(4, 200, True, False)
    ledger.join(newcomer, "late-human-joins")
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="late-approacher",
            name="Late approaching person",
            jobs=("civilian",),
            detail="Arrives after the protection was established",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles = NpcRoleService(world)
    invitation = roles.offer_transfer(
        ADMIN, str(uuid4()), state(game).revision, "late-approacher", newcomer.user_id
    )
    # An offer alone must not make the recipient eligible for the shield's private controls.
    assert next(x for x in state(game).world.npcs if x.id == "late-approacher").controller == 1
    with pytest.raises(WorkflowError, match="private audience"):
        controls.view(newcomer, shield.id)
    accepted = roles.respond(
        newcomer, str(uuid4()), invitation["id"], state(game).revision, "accept"
    )
    assert accepted["state"] == "accepted"
    assert next(x for x in state(game).world.npcs if x.id == "late-approacher").controller == 4
    actor = ActorRef(kind="npc", entity="late-approacher")
    source = rules.records(state(game), rules.Session)[-1]
    assert actor not in [x.actor for x in source.cast.roles]
    saved = controls.view(newcomer, shield.id)
    assert set(saved) == {"id", "kind", "revision", "source", "approachers"}
    assert saved["source"] == {"high": True, "ended_event": None}
    assert [x["token"] for x in saved["approachers"]] == [actor.token]
    with pytest.raises(WorkflowError, match="private audience"):
        controls.view(newcomer, source.id)
    with ledger.engine.connect() as c:
        assert any(
            x["id"] == shield.id and x["pending"] for x in _tasks(game, c, state(game), newcomer)
        )
    with pytest.raises(WorkflowError, match="human controls"):
        controls.approach(PLAYER, str(uuid4()), shield.id, state(game).revision, actor, "Forged")
    attempt = controls.approach(
        newcomer, str(uuid4()), shield.id, state(game).revision, actor, "I try to get to them"
    )
    payload = (newcomer, "late-voluntary-parting-tag", attempt["id"], state(game).revision)
    controls.give_up(*payload, tag="Immovable")
    controls.give_up(*payload, tag="Immovable")
    assert len([x for x in state(game).sheets["2"].tags if x.giver_actor == actor]) == 1
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"cell": (9, 9)}) if x.id == actor.entity else x
                    for x in canon.world.npcs
                )
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.late_approacher_departed", canon)
    with pytest.raises(WorkflowError, match="private audience"):
        controls.view(newcomer, shield.id)
    with pytest.raises(WorkflowError, match="co-present"):
        controls.approach(newcomer, str(uuid4()), shield.id, state(game).revision, actor, "Too far")
