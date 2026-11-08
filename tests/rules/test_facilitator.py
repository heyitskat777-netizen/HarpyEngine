"""Real source requests and human rulings preserve owned effects, receipts and scoped locks."""

import asyncio
import json

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, setup_game, start, state, tick

from girlframe.database import tables as t
from girlframe.delivery.p1_facilitator_worker import FacilitatorWorker
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


class Notices(Gateway):
    def __init__(self):
        super().__init__()
        self.notices = {}
        self.views = []

    async def notice(self, channel, recipient, request, nonce):
        self.notices[nonce] = dict(channel=channel, recipient=recipient.id, request=request)
        return 8100 + len(self.notices)

    async def find_notice(self, channel, nonce):
        return 8101 if nonce in self.notices else None

    async def register_notice(self, message, request):
        self.views.append((message, request))


def rule_id():
    from girlframe.services.m3_access import load_registry

    return next(x.id for x in load_registry().entries if x.title == "Keep Your Head")


def test_known_source_human_ruling_actual_owned_effect_then_scoped_resume(ledger):
    game, worker, _, dice = setup_game(ledger, faces=(4, 5))
    gateway = Notices()
    service = FacilitatorService(game)
    service.configure(ADMIN, "actual-explicit-human", "user", 1)
    action = start(game)
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    request = service.request(
        PLAYER,
        "request-real-source",
        900,
        "action",
        action,
        rule_id(),
        state(game).revision,
        "PRIVATE_REQUEST_REASON retained only in authorized packet",
    )["id"]
    assert (
        service.view(ADMIN, request)["request"]["reason"]
        != "PRIVATE_REQUEST_REASON retained only in authorized packet"
    )
    with pytest.raises(WorkflowError):
        service.view(OTHER, request)
    with pytest.raises(WorkflowError, match="FACILITATOR_REQUIRED"):
        answer(game, PLAYER, "tag_window", options=("pass",))
    notices = FacilitatorWorker(game)
    asyncio.run(notices.tick(gateway))
    assert len(gateway.notices) == 1 and "PRIVATE_REQUEST_REASON" not in json.dumps(gateway.notices)
    before = service.view(PLAYER, request)
    service.change(
        PLAYER, "share-owned-reason", request, before["revision"], state(game).revision, "share"
    )
    current = service.view(ADMIN, request)
    assert "PRIVATE_REQUEST_REASON" in current["request"]["reason"]
    service.change(
        ADMIN,
        "missing-adapter",
        request,
        current["revision"],
        state(game).revision,
        "rule",
        "A missing mechanical adapter cannot be narration-completed",
        adapter="blocked",
    )
    with pytest.raises(WorkflowError):
        current = service.view(PLAYER, request)
        service.change(
            PLAYER,
            "cannot-invent-effect",
            request,
            current["revision"],
            state(game).revision,
            "resume",
        )
    current = service.view(ADMIN, request)
    service.change(
        ADMIN,
        "actual-supported-route",
        request,
        current["revision"],
        state(game).revision,
        "rule",
        "Proceed through the actual original Keep choices",
        adapter="existing_source",
    )
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual printed chooser's answer")
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
    assert game.inspect(PLAYER, action)["state"] == "complete" and dice.calls == 1
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    current = service.view(ADMIN, request)
    payload = (ADMIN, "actual-resume", request, current["revision"], state(game).revision, "resume")
    result = service.change(*payload)
    assert service.change(*payload) == result
    tick(worker, gateway, 4)
    asyncio.run(FacilitatorWorker(game).tick(gateway))
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert dice.calls == 1 and service.view(PLAYER, request)["request"]["status"] == "resolved"


def test_missing_configuration_scene_pause_then_optional_decline_and_restore(ledger):
    game, _, _, dice = setup_game(ledger)
    gateway = Notices()
    service = FacilitatorService(game)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)
    request = service.request(
        PLAYER,
        "unknown-situation",
        900,
        "scene",
        scene["id"],
        rule_id(),
        state(game).revision,
        "An actual optional scene situation",
    )["id"]
    worker = FacilitatorWorker(game)
    asyncio.run(worker.tick(gateway))
    assert (
        not gateway.notices
        and service.view(PLAYER, request)["request"]["status"] == "configuration_required"
    )
    with pytest.raises(WorkflowError, match="FACILITATOR_REQUIRED"):
        start(game)
    service.configure(ADMIN, "designate-human", "user", 1)
    asyncio.run(worker.tick(gateway))
    current = service.view(PLAYER, request)
    service.change(
        PLAYER,
        "decline-optional",
        request,
        current["revision"],
        state(game).revision,
        "decline",
        "No mechanical effect or cost was committed",
    )
    for _ in range(3):
        asyncio.run(worker.tick(gateway))
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    assert dice.calls == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == 0
