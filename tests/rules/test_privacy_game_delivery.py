"""Actual private-room Play receipts remain private after closing and worker restart."""

import json

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_off_duty_cycle import activate
from test_scene_requisition_service import agree_and_enter, pay, propose, setup

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


class PrivateGateway(Gateway):
    def __init__(self):
        super().__init__()
        self.private = {}
        self.blocked = set()

    async def publish_private(self, recipient, payload, nonce):
        if recipient in self.blocked:
            raise OSError("Synthetic closed DMs")
        self.private[(recipient, nonce)] = payload
        return 2000 + len(self.private)

    async def find_private(self, recipient, nonce):
        return 2000 if (recipient, nonce) in self.private else None


def playing(store):
    service, cycle, game, period = setup(store)
    pay(service)
    activate(cycle, game, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]
    propose(service, identity)
    agree_and_enter(service, identity)
    game.dice = Dice((4, 5))
    action = game.begin(
        PLAYER,
        "private-real-play",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="PRIVATE_ACTUAL_ROOM_DANGER",
            trigger_confirmed=True,
        ),
    )
    return service, game, identity, action["action_id"]


def test_actual_private_play_delivers_only_original_two_dms_after_room_closes_and_restart(ledger):
    service, game, room, action = playing(ledger)
    gateway = PrivateGateway()
    tick(GameWorker(game), gateway, 3)
    for person in (PLAYER, OTHER, ADMIN):
        answer(game, person, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual precautions suffice")
    latest = service.scene_get(OTHER, room)
    service.close_scene(
        OTHER, "end-my-private-participation", room, latest["revision"], "Actual voluntary end"
    )
    tick(GameWorker(GameService(ledger)), gateway, 12)
    assert {recipient for recipient, _ in gateway.private} == {2, 3}
    assert all(x["kind"] == "control" for x in gateway.messages.values())
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        outbox = list(
            c.execute(
                sa.select(t.m2["m2_outbox"]).where(t.m2["m2_outbox"].c.action_id == action)
            ).mappings()
        )
        assert outbox and {json.loads(x["body_json"])["private_recipient"] for x in outbox} == {
            2,
            3,
        }
        assert all(x["state"] == "sent" for x in outbox)
    with pytest.raises(WorkflowError, match="PRIVACY_CLOSED"):
        game.begin(
            PLAYER,
            "cannot-reuse-closed-room",
            900,
            state(game).sheets["2"].revision,
            PlayInput(play="keep_your_head", heat=0, context="Later play", trigger_confirmed=True),
        )


def test_blocked_dm_is_reconciled_for_that_recipient_and_never_published_to_channel(ledger):
    _, game, _, action = playing(ledger)
    gateway = PrivateGateway()
    gateway.blocked.add(2)
    tick(GameWorker(game), gateway, 8)
    assert {recipient for recipient, _ in gateway.private} == {3}
    assert all(x["kind"] == "control" for x in gateway.messages.values())
    with ledger.engine.connect() as c:
        jobs = list(
            c.execute(
                sa.select(t.m2["m2_outbox"]).where(t.m2["m2_outbox"].c.action_id == action)
            ).mappings()
        )
        assert {json.loads(x["body_json"])["private_recipient"]: x["state"] for x in jobs} == {
            2: "review",
            3: "sent",
        }
    assert game.dice.calls == 1
