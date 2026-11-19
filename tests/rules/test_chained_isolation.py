"""Quality Time cannot create the Chained Darling's new Bond under her actual Handler."""

import asyncio

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_ancillary_orders import open_order_response
from girlframe.discord_adapter.m3_chained_isolation import open_isolation
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_chained_darling import RULE as PLACEMENT
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_discipline import AncillaryDisciplineService
from girlframe.services.m3_ancillary_orders import AncillaryOrderService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_chained_isolation import RULE, IsolationService, pending
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("choice", ("tag", "order"), ids=("original-tag", "actual-order"))
def test_isolation_blocks_real_quality_time_bond_and_keeps_original_alternative_pending(
    ledger,
    tmp_path,
    monkeypatch,
    choice,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE, PLACEMENT))
    missions = MissionService(ledger)
    setup = AncillaryService(missions)
    cast = CastService(ActorService(missions))
    change(cast, ADMIN, "join", REBEL)

    def create(viewer, book, name):
        identity = setup.invite(
            ADMIN,
            "invite-" + name,
            state(game).revision,
            viewer.user_id,
            "city0",
            "group",
        )["id"]

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original owned object.")

        draft = ancillary.Draft(
            name=name,
            book=book,
            frame_catalogue="JANUS",
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
        )
        made = setup.respond(viewer, "create-" + name, identity, state(game).revision, draft)
        actor = ActorRef.model_validate(made["actor"])
        change(cast, viewer, "join", actor)
        return actor

    chained = create(PLAYER, "CHAINED DARLING", "Exact original Chained Darling")
    other = create(OTHER, "WARBOY", "Actual separate member")
    cadre = AncillaryCadreService(game)
    created = cadre.propose(
        ADMIN,
        "group",
        900,
        state(game).revision,
        REBEL.token,
        (other.token, chained.token),
    )
    for viewer, role in ((ADMIN, "handler"), (OTHER, other.token), (PLAYER, chained.token)):
        cadre.approve(viewer, "approved-" + role, created["id"], state(game).revision, role, True)

    discipline = AncillaryDisciplineService(game)
    role_service = RolePunishmentService(game)
    work = discipline.start(ADMIN, "source-start", 900, state(game).revision, chained.token)["id"]
    inst = Instruction(
        kind="quality_time",
        details_json=Details(kind="quality_time", tag="Original critique").model_dump_json(),
    )
    role_service.change(ADMIN, "source-instruction", work, state(game).revision, instruction=inst)
    role_service.change(
        ADMIN,
        "source-scene",
        work,
        state(game).revision,
        scene="We have the original private discipline conversation.",
    )
    role_service.change(PLAYER, "original-attendance", work, state(game).revision, attest=True)
    role_service.change(
        ADMIN,
        "commit-actual-quality-time",
        work,
        state(game).revision,
        execute=True,
        account="The participants completed the conversation.",
    )
    midway = state(game)
    assert depth(midway, chained, REBEL) == 0
    assert pending(midway, work) and midway.role_punishments[0].completion_event is None
    assert any(
        x.identity == work and x.task == "m3_chained_isolation"
        for x in InboxService(ledger).items(ADMIN)
    )
    service = IsolationService(game)
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, work)
    if choice == "order":
        placement = ChainedPlacementService(game)
        request = placement.propose(
            PLAYER, "pilot", 900, chained, state(game).revision, "piloting", "I pilot the Frame."
        )
        placement.decide(ADMIN, "see-pilot", request["id"], state(game).revision, True)
        movement = MovementService(game)
        movement.move(
            PLAYER, "away", state(game).revision, 900, chained, (0, 3), frame=True, account="I go."
        )
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_isolation(click, service, work),
            dict(choice=(choice,), tag="Isolated in the Cadre" if choice == "tag" else ""),
            94800,
        )
    )
    if choice == "order":
        assert pending(state(game), work)
        ledger.engine.dispose()
        inbox = InboxService(ledger)
        (item,) = [x for x in inbox.items(PLAYER) if x.task == "m3_ancillary_order"]
        orders = AncillaryOrderService(game)
        with pytest.raises(WorkflowError, match="unavailable"):
            orders.get(OTHER, item.identity)
        with pytest.raises(WorkflowError, match="Use physical movement"):
            orders.act(
                PLAYER, "claim-follow", item.identity, state(game).revision, "follow",
                account="I am there.",
            )
        assert pending(state(game), work)
        movement.move(
            PLAYER, "back", state(game).revision, 900, chained, (0, 4), frame=True,
            account="I pilot back to the Handler's square.",
        )
        request = placement.propose(
            PLAYER, "out", 900, chained, state(game).revision, "outside_frame", "I step out."
        )
        placement.decide(ADMIN, "see-exit", request["id"], state(game).revision, True)
        asyncio.run(
            submit_form(
                PLAYER,
                lambda click: open_order_response(click, orders, item.identity),
                dict(choice=("follow",), account="I go to the original Handler's side."),
                94802,
            )
        )
    final = state(game)
    assert not pending(final, work) and final.role_punishments[0].completion_event
    tags = {"Original critique"} | ({"Isolated in the Cadre"} if choice == "tag" else set())
    assert {x.label for x in ancillary.find(final, chained).tags} == tags
    assert depth(final, chained, REBEL) == 0
