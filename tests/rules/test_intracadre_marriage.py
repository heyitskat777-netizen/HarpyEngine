"""Actual declaration, pooled rewards, exact payment and witnessed allocated discipline."""

import asyncio
import json
from uuid import uuid4

import pytest
import test_mission_service as mission_fixture
from handler_award_scenario import ordinary_pr_award
from test_creation import selected
from test_creation_review import ready as creation_ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger
from test_m2_game import (
    Dice,
    Gateway,
    ReleaseApproval,
    answer,
    pass_tags,
    registry_digest,
    state,
    tick,
)
from test_mission_ui import current
from test_punishment_service import submit
from test_requisition_service import selected as installation

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.discord_adapter.m3_intracadre_marriage import open_marriage
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_intracadre_marriage as rules
from girlframe.engine.bonds import BondProposal
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_intracadre_marriage import MarriageService, prove_flow
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

FOUR = GuildViewer(4, 200, True, False)


def interaction(owner=1, channel=900):
    result = current(owner, int(uuid4().int % 1000000000))
    result.channel_id = channel
    return result


def third_draft(store):
    seed(store, FOUR, callsign="Actual outsider", notes="OUTSIDER_PRIVATE_NOTES")
    store.save_draft(
        FOUR,
        str(uuid4()),
        store.draft(FOUR)["revision"],
        DraftInput(
            callsign="Actual outsider",
            girl_playbook="MOCKINGBIRD",
            frame_playbook="THE ENFORCER",
            notes="OUTSIDER_PRIVATE_NOTES",
        ),
    )
    bonds = BondService(store)
    bond = bonds.propose(
        FOUR,
        str(uuid4()),
        store.draft(FOUR)["revision"],
        store.draft(PLAYER)["revision"],
        BondProposal(target_id=2, prompt=0),
    )
    bonds.decide(PLAYER, str(uuid4()), bond["id"], 1, "accept")
    creation = CreationService(store)
    draft = creation.get(FOUR)
    selected_draft = selected("MOCKINGBIRD", "THE ENFORCER").model_copy(
        update={"shared_tokens": draft.draft.shared_tokens}
    )
    creation.save(FOUR, str(uuid4()), draft.revision, store.draft(FOUR)["revision"], selected_draft)
    handler = HandlerService(store)
    handler.rank(
        ADMIN,
        str(uuid4()),
        handler.roster(ADMIN)["revision"],
        tuple(
            PilotRef(user_id=x.user_id, character_revision=store.draft(x)["revision"])
            for x in (PLAYER, OTHER, FOUR)
        ),
    )


def third_presence(store, game):
    physical = PhysicalService(store)
    own = physical.preview(FOUR)
    proposal = physical.propose(
        FOUR,
        str(uuid4()),
        own["game_revision"],
        InitialPlacement(
            actor=current_ref(state(game), 4),
            frame_instance=own["frame_instance"],
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode="outside_frame",
            account="My actual original body and starting Frame are here",
            facts_confirmed=True,
        ),
    )
    physical.decide(ADMIN, str(uuid4()), proposal["id"], 1, "accept", "Actual initial body facts")


def setup_three(store, girl="MOCKINGBIRD", frame="JANUS-B", faces=(4, 5)):
    review, creation, _ = creation_ready(store, girl, frame)
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    current_creation = creation.get(OTHER)
    draft = selected("MOCKINGBIRD", "JANUS-B").model_copy(
        update={"shared_tokens": current_creation.draft.shared_tokens}
    )
    creation.save(OTHER, str(uuid4()), 0, store.draft(OTHER)["revision"], draft)
    incoming = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    current_creation = creation.get(OTHER)
    review.select_bond(
        OTHER,
        str(uuid4()),
        current_creation.revision,
        store.draft(OTHER)["revision"],
        current_creation.draft,
        incoming.id,
    )
    third_draft(store)
    game = GameService(store, dice=Dice(faces))
    for owner in (PLAYER, OTHER, FOUR):
        value = review.get(owner)
        assert value.sheet.ready_for_rules_review, value.sheet.issues
        review.save(owner, str(uuid4()), value.saved_revision, value.fingerprint)
        game.activate(owner, str(uuid4()), review.get(owner).fingerprint)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for owner in (PLAYER, OTHER, FOUR, ADMIN):
        game.join_scene(owner, str(uuid4()), 900)
    return game, GameWorker(game), Gateway(), game.dice


def test_actual_marriage_shared_grant_approved_other_body_purchase_caught_flirt_and_punishment(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(mission_fixture, "setup_game", setup_three)
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    third_presence(ledger, game)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE))
    service = MarriageService(ledger, game)
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    first, second = current_ref(state(game), 2), current_ref(state(game), 3)
    before = state(game)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError):
        service.declare(
            ADMIN,
            str(uuid4()),
            award.id,
            before.revision,
            first,
            second,
            first,
            first,
            "No actual M3 approval",
        )
    ledger.policy = policy
    assert state(game).model_dump_json() == before.model_dump_json()

    async def declare():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_advancement(own, HandlerAdvancementService(ledger), award.id)
        menu = own.edit_original_response.call_args.kwargs["view"]
        more = next(x for x in menu.children if isinstance(x, AcquireMore))
        next_step = interaction()
        await next_step.response.defer(ephemeral=True)
        await more.callback(next_step)
        chooser = next_step.edit_original_response.call_args.kwargs["view"]
        chooser.values.update(advancement=("marriage",))
        selected_view = interaction()
        await chooser.confirm.callback(selected_view)
        assert chooser.completed
        form = selected_view.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            award=(award.id,),
            first=(first.token,),
            second=(second.token,),
            financial=("first",),
            status=("first",),
            account="I tell these two original Girls they are partners now",
        )
        confirmed = interaction()
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(declare())
    source = rules.acquisitions(state(game))[0]
    canon = state(game)
    assert (source.first, source.second, source.financial, source.punished) == (
        first,
        second,
        first,
        second,
    )
    assert depth(canon, first, second) == min(2, depth(before, first, second) + 1)
    assert rules.rank(canon, 2) == rules.rank(canon, 3)
    assert not higher(canon, 2, 3) and not higher(canon, 3, 2)
    assert {x for group in rules.status_groups(canon) for x in group} == set(canon.order)

    missions = MissionService(ledger)
    offered = missions.offer(ADMIN, str(uuid4()), "The real supply sortie is completed", (2, 3, 4))
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.respond(FOUR, str(uuid4()), offered["id"], 3, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 4)
    opening = rules.available(state(game), first)
    missions.end(ADMIN, str(uuid4()), offered["id"], 5, True)
    rewarded = state(game)
    flows = [x for x in rules.records(rewarded, rules.PermissionFlow) if x.kind == "grant"]
    assert len(flows) == 3 and all(x.wallet == first for x in flows)
    assert {x.beneficiary for x in flows} == {first, second}
    assert (
        rules.available(rewarded, second) == opening + 3 and rewarded.sheets["3"].permissions == 0
    )
    discipline = PunishmentService(ledger)
    dog = next(x for x in missions.get(ADMIN, offered["id"])["work"] if x["kind"] == "punishment")
    assert dog["subject"] == 4
    submit(discipline, ADMIN, dog["id"], Details(kind="stimulant_injection"), str(uuid4()))
    mission = missions.get(ADMIN, offered["id"])
    missions.complete(ADMIN, str(uuid4()), offered["id"], mission["mission"]["revision"])

    async def request_payment():
        own = interaction(3)
        await own.response.defer(ephemeral=True)
        await open_marriage(own, service, source.id)
        request_menu = own.edit_original_response.call_args.kwargs["view"]
        step = interaction(3)
        await step.response.defer(ephemeral=True)
        await request_menu.open_item(step, "request")
        categories = step.edit_original_response.call_args.kwargs["view"]
        step2 = interaction(3)
        await step2.response.defer(ephemeral=True)
        await categories.open_item(step2, "Basic purchases")
        products = step2.edit_original_response.call_args.kwargs["view"]
        step3 = interaction(3)
        await step3.response.defer(ephemeral=True)
        await products.open_item(step3, "asset_installment")
        form = step3.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            product=("0",), account="Install this actual printed-price product on my own Frame"
        )
        await form.confirm.callback(interaction(3))
        assert form.completed

    asyncio.run(request_payment())
    quote = rules.records(state(game), rules.PaymentQuote)[0]
    inbox = InboxService(ledger)
    waiting = next(x for x in inbox.items(OTHER) if x.identity == quote.id)
    incoming = next(x for x in inbox.items(PLAYER) if x.identity == quote.id)
    assert waiting.state == "pending" and not waiting.incoming
    assert incoming.state == "pending" and incoming.incoming
    assert inbox.page(OTHER, "waiting", selected_key=waiting.key).item.identity == quote.id
    before_denial = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.approve_payment(OTHER, str(uuid4()), quote.id, state(game).revision, "Not my funds")
    requisitions = RequisitionService(game)
    view = requisitions.view(OTHER)
    with pytest.raises((ValueError, WorkflowError)):
        requisitions.buy(OTHER, str(uuid4()), second, view["source_sha256"], installation())
    assert state(game).model_dump_json() == before_denial

    async def approve():
        own = interaction(2)
        await own.response.defer(ephemeral=True)
        await open_marriage(own, service, quote.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="I choose to spend one shared Permission on this exact product")
        await form.confirm.callback(interaction(2))
        assert form.completed

    asyncio.run(approve())
    approved_total = rules.available(state(game), first)
    view = requisitions.view(OTHER)
    key = str(uuid4())
    purchased = requisitions.buy(OTHER, key, second, view["source_sha256"], installation())
    assert requisitions.buy(OTHER, key, second, view["source_sha256"], installation()) == purchased
    paid = state(game)
    payment = next(x for x in rules.records(paid, rules.PermissionFlow) if x.quote == quote.id)
    assert payment.beneficiary == second and payment.wallet == first and payment.amount == 1
    assert rules.available(paid, second) == approved_total - 1
    assert any(x.id == purchased["asset_id"] for x in paid.sheets["3"].assets)
    fresh = requisitions.view(OTHER)
    with pytest.raises((ValueError, WorkflowError)):
        requisitions.buy(OTHER, str(uuid4()), second, fresh["source_sha256"], installation())
    assert state(game).model_dump_json() == paid.model_dump_json()
    with ledger.engine.connect() as c:
        missing = paid.model_copy(deep=True)
        missing.facts = [x for x in missing.facts if x.get("id") != payment.id]
        with pytest.raises(WorkflowError, match="FLOW_REQUIRED"):
            prove_flow(game, c, before, missing, second, payment.event, payment.source, 1)

    with pytest.raises(WorkflowError):
        service.view(FOUR, source.id)
    assert "OUTSIDER_PRIVATE_NOTES" not in json.dumps(service.view(PLAYER, source.id))
    game.dice.faces = (3, 3)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=4,
            heat=0,
            context="An actual outsider interaction",
            trigger_confirmed=True,
        ),
    )["action_id"]

    class ActualGateway(Gateway):
        async def actor(self, identity):
            return FOUR if identity == 4 else await super().actor(identity)

    worker = GameWorker(game)
    gateway = ActualGateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, FOUR, "tag_window", options=("pass",))
    if any(x["kind"] == "actor_flirt" for x in game.choices(PLAYER)):
        answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, FOUR, "target_flirt", text="My own actual response")
    tick(worker, gateway, 4)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert not rules.records(state(game), rules.Caught)
    observed = next(x for x in service.witnessed_flirts(OTHER, source.id) if x["id"] == action)
    before_punishment = state(game)
    with pytest.raises(WorkflowError):
        service.report_caught(
            FOUR,
            str(uuid4()),
            source.id,
            action,
            current_ref(state(game), 4),
            "A witness outside the supported original parties",
        )
    assert state(game).model_dump_json() == before_punishment.model_dump_json()
    caught_key = str(uuid4())
    caught = service.report_caught(
        OTHER,
        caught_key,
        source.id,
        action,
        ActorRef.model_validate(observed["observer"]),
        "I actually witnessed the outsider Flirt in this scene",
    )
    assert (
        service.report_caught(
            OTHER,
            caught_key,
            source.id,
            action,
            ActorRef.model_validate(observed["observer"]),
            "I actually witnessed the outsider Flirt in this scene",
        )
        == caught
    )
    work = discipline.get(ADMIN, caught["work"])
    assert work["subject_id"] == "3"
    submit(discipline, ADMIN, caught["work"], Details(kind="stimulant_injection"), str(uuid4()))
    final = state(game)
    assert final.sheets["3"].heat == before_punishment.sheets["3"].heat + 7
    assert final.sheets["2"].heat == before_punishment.sheets["2"].heat
    assert discipline.get(ADMIN, caught["work"])["state"] == "resolved"

    async def reopen():
        saved = interaction(3, 991)
        await saved.response.defer(ephemeral=True)
        await open_marriage(saved, MarriageService(ledger), caught["id"])
        text = saved.edit_original_response.call_args.kwargs["content"]
        assert "actually witnessed" in text and "original-pair notice" in text

    asyncio.run(reopen())
