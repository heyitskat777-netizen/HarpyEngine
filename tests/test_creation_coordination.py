import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_creation_review import ready
from test_inbox import request
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.discord_adapter.creation import CreationView
from girlframe.discord_adapter.creation_coordination import (
    ChoiceSelect,
    ChooserView,
    CustomStandardModal,
)
from girlframe.discord_adapter.creation_details import DetailSelect, DetailsView, OwnStandardModal
from girlframe.discord_adapter.creation_review import pages
from girlframe.discord_adapter.inbox import InboxBackButton, InboxView
from girlframe.discord_adapter.npc_bonds import NpcSelect, NpcView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import CreationDraft
from girlframe.engine.creation_details import (
    BODY_PARTS,
    DESIRES,
    MAXIMS,
    STANDARDS,
    DesireChoice,
    GirlDetails,
    InitialConditions,
    NpcInvestor,
    StandardChoice,
)
from girlframe.engine.creation_review import ReviewSheet
from girlframe.engine.drafts import DraftInput
from girlframe.services.bonds import BondService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture


def setup(store, girl="PRINCESS"):
    seed(store)
    seed(store, OTHER)
    store.save_draft(
        PLAYER,
        "girl-profile",
        1,
        DraftInput(
            callsign="SYNTH",
            girl_playbook=girl,
            frame_playbook="CHANGELING",
            notes="PRIVATE_OWNER_NOTES",
        ),
    )
    store.join(ADMIN, "handler-join")
    handler = HandlerService(store)
    handler.appoint(ADMIN, "appoint", 0, ADMIN.user_id)
    bond_service = BondService(store)
    bond = bond_service.propose(PLAYER, "bond", 2, 1, BondProposal(target_id=3, prompt=0))
    bond_service.decide(OTHER, "bond-accept", bond["id"], 1, "accept")
    return CoordinationService(store), bond, handler


def propose(service, role="princess_peer", key="choice"):
    author = OTHER if role == "princess_peer" else ADMIN
    choice = (
        DesireChoice(slots=(0, 1))
        if role == "vatgrown_handler"
        else StandardChoice(slot=9, custom="PRIVATE_STANDARD_CANARY")
    )
    return service.propose(author, key, 2, role, service.prepare(author, 2, role), choice)


@pytest.mark.parametrize("role", ["princess_peer", "princess_handler", "vatgrown_handler"])
def test_exact_chooser_authority_and_handler_without_fake_pilot_profile(ledger, role):
    service, bond, handler = setup(ledger, "VATGROWN" if role == "vatgrown_handler" else "PRINCESS")
    author = OTHER if role == "princess_peer" else ADMIN
    context = service.prepare(author, 2, role)
    if author == ADMIN:
        assert context["author_revision"] == 0
        with ledger.engine.connect() as c:
            assert (
                c.scalar(sa.select(t.characters.c.id).where(t.characters.c.user_id == "1")) is None
            )
    for actor in (
        PLAYER,
        GuildViewer(4, 200, True, True),
        GuildViewer(author.user_id, 999, True, True),
    ):
        with pytest.raises(WorkflowError):
            service.prepare(actor, 2, role)
    row = propose(service, role)
    service.decide(PLAYER, "accept", row["id"], 1, "accept")
    with ledger.engine.connect() as c:
        choice = service.accepted(c, 2)[0]
        assert choice.role == role and choice.author == author.user_id and choice.owner == 2
    assert "PRIVATE_OWNER_NOTES" not in json.dumps(service.get(author, row["id"]))
    stranger = GuildViewer(5, 200, True, True)
    ledger.join(stranger, "stranger-join")
    with pytest.raises(WorkflowError):
        service.get(stranger, row["id"])
    with pytest.raises(WorkflowError):
        service.decide(author, "self-accept", row["id"], 2, "accept")


def test_choice_models_reject_invalid_owner_fields_and_allow_same_standard_for_each_author():
    assert (
        len(STANDARDS) == 10 and len(MAXIMS) == 10 and len(DESIRES) == 11 and len(BODY_PARTS) == 9
    )
    for invalid in [(), (0, 0), (11,), (0, 1, 2), (-1,)]:
        with pytest.raises(ValueError):
            DesireChoice(slots=invalid)
    for invalid in [dict(slot=9), dict(slot=0, custom="invented"), dict(slot=10)]:
        with pytest.raises(ValueError):
            StandardChoice(**invalid)
    with pytest.raises(ValueError):
        GirlDetails(maxims=(0, 0))
    with pytest.raises(ValueError):
        GirlDetails(maxims=(10,))
    for girl, details in [
        ("MOCKINGBIRD", GirlDetails(maxims=(0, 1))),
        ("OLDGEN", GirlDetails(own_standard=StandardChoice(slot=0))),
        (
            "VATGROWN",
            GirlDetails(investors=(NpcInvestor(npc_slot=3, desires=DesireChoice(slots=(0,))),)),
        ),
    ]:
        with pytest.raises(ValueError):
            CreationDraft(girl_playbook=girl, frame_playbook="JANUS-B", girl_details=details)
        assert InitialConditions().permissions == 0
    with pytest.raises(ValueError):
        InitialConditions(assets_damaged=True)


def test_role_replacement_withdrawal_profile_staleness_and_revoked_replay(ledger):
    service, bond, handler = setup(ledger)
    peer = propose(service)
    accepted = service.decide(PLAYER, "accept-peer", peer["id"], 1, "accept")
    assert accepted == service.decide(PLAYER, "accept-peer", peer["id"], 1, "accept")
    BondService(ledger).decide(OTHER, "withdraw-bond", bond["id"], 2, "withdraw")
    assert service.get(PLAYER, peer["id"])["stale"]
    with pytest.raises(WorkflowError, match="STALE_AUTHORITY"):
        service.decide(PLAYER, "accept-peer", peer["id"], 1, "accept")
    service.decide(PLAYER, "withdraw-peer", peer["id"], 2, "withdraw")
    own = propose(service, "princess_handler", "handler-choice")
    handler.appoint(ADMIN, "revoke", 1, None)
    assert service.get(PLAYER, own["id"])["stale"]
    with pytest.raises(WorkflowError, match="STALE_AUTHORITY"):
        service.decide(PLAYER, "old-handler", own["id"], 1, "accept")
    handler.appoint(ADMIN, "reappoint", 2, 1)
    # Same person, new appointment token; old requests do not revive.
    assert service.get(PLAYER, own["id"])["stale"]
    fresh = propose(service, "princess_handler", "fresh-handler")
    ledger.save_draft(
        PLAYER,
        "profile-edit",
        2,
        DraftInput(callsign="SYNTH_CHANGED", girl_playbook="PRINCESS", frame_playbook="CHANGELING"),
    )
    assert service.get(PLAYER, fresh["id"])["stale"]


def test_duplicate_requests_decision_states_and_exact_interaction_replay(ledger):
    service, _, _ = setup(ledger)
    row = propose(service)
    assert row == propose(service)
    with pytest.raises(WorkflowError, match="already covers"):
        propose(service, key="duplicate")
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        service.propose(
            OTHER,
            "choice",
            2,
            "princess_peer",
            service.prepare(OTHER, 2, "princess_peer"),
            StandardChoice(slot=0),
        )
    service.decide(PLAYER, "decline", row["id"], 1, "decline")
    next_row = propose(service, key="new-choice")
    service.decide(OTHER, "cancel", next_row["id"], 1, "withdraw")
    with pytest.raises(WorkflowError):
        service.decide(PLAYER, "old-accept", next_row["id"], 1, "accept")


def test_transaction_rollback_concurrency_immutability_backup_and_isolation(
    ledger, tmp_path, monkeypatch
):
    service, _, _ = setup(ledger)
    original = ledger._audit

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(ledger, "_audit", fail)
    with pytest.raises(RuntimeError):
        propose(service)
    with ledger.engine.connect() as c:
        assert service._latest(c, 2) == []
    monkeypatch.setattr(ledger, "_audit", original)
    row = propose(service)

    def decide(value):
        try:
            return service.decide(PLAYER, value, row["id"], 1, value)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(decide, ("accept", "decline")))
    assert sum(isinstance(x, dict) for x in results) == 1
    for mutation in (
        t.coordination_revisions.delete(),
        t.coordination_revisions.update().values(choice_json="{}"),
    ):
        with ledger.engine.begin() as c:
            with pytest.raises(IntegrityError):
                c.execute(mutation)
    with ledger.engine.connect() as c:
        assert all(
            "PRIVATE_STANDARD_CANARY" not in text
            for text in c.execute(sa.select(t.events.c.payload_json)).scalars()
        )
        assert all(
            "PRIVATE_STANDARD_CANARY" not in text
            for text in c.execute(sa.select(t.commands.c.outcome_json)).scalars()
        )
    path = tmp_path / "coordination-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        other = CoordinationService(OnboardingStore(engine, ledger.policy))
        assert other.get(PLAYER, row["id"]) == service.get(PLAYER, row["id"])
    finally:
        engine.dispose()
    other_store = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    foreign = GuildViewer(2, 300, True, False)
    seed(other_store, foreign)
    with pytest.raises(WorkflowError):
        CoordinationService(other_store).get(foreign, row["id"])
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.get(PLAYER, row["id"])


def test_inbox_party_roles_tasks_dedup_review_effects_and_generic_decision(ledger):
    service, _, _ = setup(ledger)
    source = InboxService(ledger)
    assert any(x.task == "coordinate" for x in source.items(ADMIN))
    assert any(x.task == "coordinate" for x in source.items(OTHER))
    assert any(x.task == "girl_details" for x in source.items(PLAYER))
    row = propose(service)
    assert not any(x.task == "coordinate" for x in source.items(OTHER))
    item = next(x for x in source.items(PLAYER) if x.source == "coordination")
    assert item.primary and item.incoming and item.category == "playbook"
    outgoing = next(x for x in source.items(OTHER) if x.source == "coordination")
    assert outgoing.primary is None and outgoing.secondary == "withdraw"
    source.decide(PLAYER, "accept-through-inbox", item, "accept")
    sheet = CreationReviewService(ledger).get(PLAYER).sheet
    assert len(sheet.coordination) == 1
    assert "princess_handler" in {x.code for x in sheet.issues}
    assert "own_standard" in {x.code for x in sheet.issues}
    assert not any(x.task == "coordinate" for x in source.items(OTHER))
    assert service.get(PLAYER, row["id"])["state"] == "accepted"


@pytest.mark.parametrize("girl", ["PRINCESS", "OLDGEN", "VATGROWN"])
def test_owner_details_persist_and_missing_shared_choice_blocks_readiness(ledger, girl):
    review, creation, _ = ready(ledger, girl)
    progress = creation.get(PLAYER)
    assert review.get(PLAYER).sheet.ready_for_rules_review
    creation.save(
        PLAYER, "clear-own", 1, 2, progress.draft.model_copy(update={"girl_details": None})
    )
    assert not review.get(PLAYER).sheet.ready_for_rules_review
    assert any(x.task == "girl_details" for x in InboxService(ledger).items(PLAYER))
    if girl == "PRINCESS":
        accepted = review.get(PLAYER).sheet.coordination[0]
        CoordinationService(ledger).decide(
            PLAYER, "withdraw-standard", accepted.id, accepted.revision, "withdraw"
        )
        assert "princess_" in " ".join(x.code for x in review.get(PLAYER).sheet.issues)


def test_changeling_anchors_and_legacy_review_compatibility(ledger):
    service, creation, _ = ready(ledger, frame="CHANGELING")
    current = service.get(PLAYER)
    anchors = current.sheet.psych_strings
    assert {x.kind for x in anchors} == {"pilot", "npc_role"}
    assert len(anchors) == len(current.sheet.bonds) + len(current.sheet.creation.npc_bonds)
    assert any(x.reference == "3" for x in anchors)
    legacy = current.sheet.model_dump(mode="json")
    legacy["source_version"] = "m2-creation-review-1"
    for key in ("coordination", "psych_strings", "initial_conditions"):
        legacy.pop(key)
    assert (
        ReviewSheet.model_validate_json(json.dumps(legacy)).source_version == "m2-creation-review-1"
    )
    assert any("CHANGELING" in text for text in pages(current, "Frame and resources"))
    assert current.sheet.source_version == "m2-creation-review-2"


def test_native_chooser_dropdown_custom_text_send_and_owner_guards(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, _, _ = setup(ledger)

    async def run():
        view = ChooserView(
            service, 3, 2, "princess_peer", service.prepare(OTHER, 2, "princess_peer")
        )
        await view.render(request(OTHER, 1))
        assert view.send.disabled
        assert not await view.interaction_check(request(PLAYER, 2))
        menu = next(x for x in view.children if isinstance(x, ChoiceSelect))
        menu._values = ["9"]
        await menu.callback(request(OTHER, 3))
        modal = CustomStandardModal(view)
        modal.text._value = "SYNTHETIC_CUSTOM_STANDARD"
        await modal.on_submit(request(OTHER, 4))
        assert not view.send.disabled
        await view.send.callback(request(OTHER, 5, view.send.custom_id))
        with ledger.engine.connect() as c:
            rows = service._latest(c, 2)
        assert (
            rows[0]["state"] == "pending" and "SYNTHETIC_CUSTOM_STANDARD" in rows[0]["choice_json"]
        )
        assert len(view.to_components()) <= 5

    asyncio.run(run())


@pytest.mark.parametrize("girl", ["PRINCESS", "OLDGEN", "VATGROWN"])
def test_native_owner_choices_custom_maxims_investors_and_saved_resume(ledger, girl):
    review, creation, _ = ready(ledger, girl)

    async def run():
        parent = CreationView(creation, 2, creation.get(PLAYER))
        view = DetailsView(parent)
        await view.render(request(PLAYER, 1))
        assert not await view.interaction_check(request(OTHER, 2))
        if girl == "PRINCESS":
            menu = next(x for x in view.children if isinstance(x, DetailSelect))
            menu._values = ["9"]
            await menu.callback(request(PLAYER, 3))
            modal = OwnStandardModal(view)
            modal.text._value = "SYNTHETIC_OWN_STANDARD"
            await modal.on_submit(request(PLAYER, 4))
            assert parent.draft.girl_details.own_standard.custom == "SYNTHETIC_OWN_STANDARD"
        elif girl == "OLDGEN":
            menu = next(x for x in view.children if isinstance(x, DetailSelect))
            menu._values = ["2", "3"]
            await menu.callback(request(PLAYER, 3))
            assert parent.draft.girl_details.maxims == (2, 3)
        else:
            menu = next(
                x for x in view.children if isinstance(x, DetailSelect) and x.kind == "desires"
            )
            menu._values = ["2", "3"]
            await menu.callback(request(PLAYER, 3))
            assert parent.draft.girl_details.investors[0].desires.slots == (2, 3)
        assert len(view.to_components()) <= 5
        creation.save(PLAYER, "save-edits", 1, 2, parent.draft)
        assert creation.get(PLAYER).draft.girl_details == parent.draft.girl_details
        assert review.get(PLAYER).sheet.ready_for_rules_review

    asyncio.run(run())


def test_changing_npc_roles_clears_only_incompatible_investor_choices(ledger):
    _, creation, _ = ready(ledger, "VATGROWN")

    async def run():
        parent = CreationView(creation, 2, creation.get(PLAYER))
        view = NpcView(parent)
        menu = next(x for x in view.children if isinstance(x, NpcSelect))
        menu._values = ["3"]
        await menu.callback(request(PLAYER, 1))
        assert parent.draft.npc_bonds[0].slot == 3
        assert parent.draft.girl_details.investors == ()

    asyncio.run(run())


def test_native_inbox_routes_chooser_and_owner_details_with_back(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, _, _ = setup(ledger)

    async def run():
        inbox = InboxService(ledger)
        view = InboxView(inbox, 3)
        item = next(x for x in inbox.items(OTHER) if x.task == "coordinate")
        interaction = request(OTHER, 1)
        await view.route(interaction, item)
        chooser = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(chooser, ChooserView)
        assert any(isinstance(x, InboxBackButton) for x in chooser.children)
        owner_view = InboxView(inbox, 2)
        owner_item = next(x for x in inbox.items(PLAYER) if x.task == "girl_details")
        interaction = request(PLAYER, 2)
        await owner_view.route(interaction, owner_item)
        details = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(details, DetailsView)
        assert any(isinstance(x, InboxBackButton) for x in details.children)

    asyncio.run(run())


def test_three_princess_choosers_may_select_the_same_printed_standard(ledger):
    review, _, _ = ready(ledger, "PRINCESS")
    coordination = CoordinationService(ledger)
    for original in review.get(PLAYER).sheet.coordination:
        coordination.decide(
            PLAYER, "withdraw-" + original.role, original.id, original.revision, "withdraw"
        )
        author = OTHER if original.role == "princess_peer" else ADMIN
        row = coordination.propose(
            author,
            "replace-" + original.role,
            2,
            original.role,
            coordination.prepare(author, 2, original.role),
            StandardChoice(slot=0),
        )
        coordination.decide(PLAYER, "accept-replacement-" + original.role, row["id"], 1, "accept")
    sheet = review.get(PLAYER).sheet
    assert sheet.ready_for_rules_review
    assert all(
        x.standard.slot == sheet.creation.girl_details.own_standard.slot for x in sheet.coordination
    )


def test_unapproved_initial_conditions_stay_unresolved_and_role_contract_rejects_forgery(ledger):
    from girlframe.engine.creation_details import AcceptedCoordination

    review, _, _ = ready(ledger)
    assert review.get(PLAYER).sheet.initial_conditions == InitialConditions()
    ledger.policy = ledger.policy.model_copy(update={"owner_initial_conditions": None})
    assert "initial_conditions" in {x.code for x in review.get(PLAYER).sheet.issues}
    for role, choice in (
        ("princess_peer", {"desires": DesireChoice(slots=(0,))}),
        ("vatgrown_handler", {"standard": StandardChoice(slot=0)}),
    ):
        with pytest.raises(ValueError):
            AcceptedCoordination(
                id=str(uuid4()), revision=1, role=role, author=3, owner=2, **choice
            )


def test_old_send_button_cannot_submit_a_newer_chooser_selection(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, _, _ = setup(ledger)

    async def run():
        view = ChooserView(
            service, 3, 2, "princess_peer", service.prepare(OTHER, 2, "princess_peer")
        )
        view.slots = (0,)
        await view.render(request(OTHER, 1))
        old_id = view.send.custom_id
        view.slots, view.generation = (1,), 1
        await view.render(request(OTHER, 2))
        await view.send.callback(request(OTHER, 3, old_id))
        with ledger.engine.connect() as c:
            assert service._latest(c, 2) == []
        await view.send.callback(request(OTHER, 4, view.send.custom_id))
        with ledger.engine.connect() as c:
            assert service.parsed(service._latest(c, 2)[0]).standard.slot == 1

    asyncio.run(run())
