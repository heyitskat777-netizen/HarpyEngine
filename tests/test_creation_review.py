import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_creation import selected
from test_inbox import request
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.discord_adapter.cadre_history import HistoryView, MissionSelect
from girlframe.discord_adapter.creation import CreationView
from girlframe.discord_adapter.creation_review import ReviewView, SectionSelect, pages
from girlframe.discord_adapter.handler_setup import ConfirmSetup, RulingSelect, RulingsView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.creation import AssetChoice, CreationDraft
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import (
    DesireChoice,
    GirlDetails,
    InitialConditions,
    NpcInvestor,
    StandardChoice,
)
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.drafts import DraftInput
from girlframe.engine.fanbase import Fanbase
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.pair_assets import PairNames
from girlframe.engine.shared_setup import CallsignChoice, CourtChoice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.shared_setup import SharedSetupService

ledger = ledger_fixture


def ready(store, girl="MOCKINGBIRD", frame="JANUS-B"):
    store.policy = store.policy.model_copy(update={"owner_initial_conditions": InitialConditions()})
    seed(store)
    seed(store, OTHER)
    store.save_draft(
        PLAYER,
        "profile",
        1,
        DraftInput(
            callsign="SYNTH", girl_playbook=girl, frame_playbook=frame, notes="OWNER_PROFILE_SECRET"
        ),
    )
    store.join(ADMIN, "handler-join")
    handler = HandlerService(store)
    handler.appoint(ADMIN, "appoint", 0, ADMIN.user_id)
    if girl == "NEWGIRL":
        handler.mentor(
            ADMIN,
            "nominate",
            1,
            PilotRef(user_id=2, character_revision=2),
            PilotRef(user_id=3, character_revision=1),
        )
    bonds = BondService(store)
    row = bonds.propose(
        PLAYER, "bond", 2, 1, BondProposal(target_id=3, prompt=0, context="SHARED_BOND_CONTEXT")
    )
    bonds.decide(OTHER, "accept-bond", row["id"], 1, "accept")
    shared = SharedSetupService(store)
    if girl == "NEWGIRL":
        choice = shared.propose(
            OTHER,
            "name",
            2,
            "callsign",
            shared.prepare(OTHER, 2, "callsign"),
            CallsignChoice(callsign="MENTOR_NAME"),
        )
        shared.decide(PLAYER, "accept-name", choice["id"], 1, "accept")
    if frame == "THE RED QUEEN":
        choice = shared.propose(
            PLAYER,
            "court",
            3,
            "court",
            shared.prepare(PLAYER, 3, "court"),
            CourtChoice(role="The Knight"),
        )
        shared.decide(OTHER, "accept-court", choice["id"], 1, "accept")
    if girl == "BONDED":
        PairService(store).choose(
            OTHER,
            "pair-names",
            row["id"],
            2,
            0,
            PairNames(names=tuple(CATALOG["BONDED"]["assets"][:2])),
        )
    creation = CreationService(store)
    current = creation.get(PLAYER)
    data = selected(girl, frame)
    update = {
        "shared_tokens": current.draft.shared_tokens,
        "pair_source_token": current.draft.pair_source_token,
    }
    if current.pair_choice:
        update["pair_asset_descriptions"] = tuple(
            AssetChoice(name=x, description="PRIVATE_ASSET_DETAIL")
            for x in current.pair_choice.names
        )
    if girl == "NEWGIRL":
        update["prior_missions"] = tuple(
            PriorMission(user_id=uid, character_revision=data["revision"], missions=0)
            for uid, data in creation.cadre(PLAYER).items()
        )
        update["cadre_discussed"] = True
    if frame == "THE PRINCE":
        update["fanbase"] = Fanbase(
            demographics=("Young girls", "Online shippers"),
            demanded=("Kind", "Intelligent"),
            rejected=("Dangerous", "Girly"),
        )
    if girl == "OLDGEN":
        update["girl_details"] = GirlDetails(maxims=(0, 1))
    elif girl == "PRINCESS":
        update["girl_details"] = GirlDetails(own_standard=StandardChoice(slot=0))
        coordinated = CoordinationService(store)
        for actor, role in ((OTHER, "princess_peer"), (ADMIN, "princess_handler")):
            request = coordinated.propose(
                actor,
                "standard-" + role,
                PLAYER.user_id,
                role,
                coordinated.prepare(actor, PLAYER.user_id, role),
                StandardChoice(slot=1),
            )
            coordinated.decide(PLAYER, "accept-" + role, request["id"], 1, "accept")
    elif girl == "VATGROWN":
        update["girl_details"] = GirlDetails(
            investors=tuple(
                NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                for x in data.npc_bonds
            )
        )
        coordinated = CoordinationService(store)
        request = coordinated.propose(
            ADMIN,
            "handler-desires",
            PLAYER.user_id,
            "vatgrown_handler",
            coordinated.prepare(ADMIN, PLAYER.user_id, "vatgrown_handler"),
            DesireChoice(slots=(1,)),
        )
        coordinated.decide(PLAYER, "accept-handler-desires", request["id"], 1, "accept")
    data = data.model_copy(update=update)
    creation.save(PLAYER, "creation", 0, 2, data, expected_pair_token=data.pair_source_token)
    expected = handler.roster(ADMIN)["revision"]
    handler.rank(
        ADMIN,
        "rank",
        expected,
        (PilotRef(user_id=2, character_revision=2), PilotRef(user_id=3, character_revision=1)),
    )
    handler.rulings(ADMIN, "rulings", expected + 1, CreationRulings())
    return CreationReviewService(store), creation, handler


@pytest.mark.parametrize("girl", [x for x, v in CATALOG.items() if v["family"] == "girl"])
def test_all_girl_review_branches_and_activation_gate(ledger, girl):
    service, creation, handler = ready(ledger, girl)
    review = service.get(PLAYER)
    assert review.sheet.ready_for_rules_review
    assert [x.code for x in review.sheet.issues] == ["independent_review"]
    assert review.sheet.status == "Ace"
    assert len(review.sheet.creation.identities) == 4
    assert review.sheet.state == "draft_rules_unverified"
    assert "OWNER_PROFILE_SECRET" not in review.sheet.model_dump_json()
    if girl == "NEWGIRL":
        assert (
            review.sheet.activation_callsign == "MENTOR_NAME" and review.sheet.callsign == "SYNTH"
        )
    if girl == "BONDED":
        assert len(review.sheet.creation.pair_asset_descriptions) == 2
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        service.activate(PLAYER)


@pytest.mark.parametrize(
    "frame", [x for x, v in CATALOG.items() if v["family"] == "frame"] + ["JANUS-B"]
)
def test_all_frame_review_branches_explicit_rulings_and_extra_identities(ledger, frame):
    service, _, _ = ready(ledger, frame=frame)
    sheet = service.get(PLAYER).sheet
    assert sheet.ready_for_rules_review
    assert sheet.rulings.provenance == "handler_confirmed_campaign_ruling"
    assert sheet.access == (
        "Room with a bunk",
        "Combat knife",
        "Pilot suit and civilian outfit",
        "Surgically implanted neural link",
    )
    if frame == "THE PRINCE":
        assert len(sheet.creation.fanbase.additional_identities) == 2
    if frame == "THE RED QUEEN":
        allocation = next(x.allocation for x in sheet.shared if x.kind == "court")
        assert list(allocation.values()).count(2) == 4


def test_missing_choices_rulings_and_short_game_are_explicit(ledger):
    seed(ledger)
    service = CreationReviewService(ledger)
    codes = {x.code for x in service.get(PLAYER).sheet.issues}
    assert {
        "creation",
        "save_creation",
        "handler",
        "status",
        "starting_bond",
        "starting_resources",
        "independent_review",
    } <= codes
    seed(ledger, OTHER)
    ledger.join(ADMIN, "handler")
    handler = HandlerService(ledger)
    handler.appoint(ADMIN, "appoint", 0, 1)
    assert handler.view(PLAYER)["creation_rulings"] is None
    handler.rulings(ADMIN, "short", 1, CreationRulings(requisition_mode="short_game_unimplemented"))
    assert "starting_requisition" in {x.code for x in service.get(PLAYER).sheet.issues}
    assert not service.get(PLAYER).sheet.ready_for_rules_review
    handler.rulings(ADMIN, "clear", 2, None)
    assert "starting_resources" in {x.code for x in service.get(PLAYER).sheet.issues}


def test_review_fingerprint_staleness_exact_replay_and_private_history(ledger):
    service, creation, _ = ready(ledger)
    first = service.get(PLAYER)
    assert first == service.get(PLAYER)
    result = service.save(PLAYER, "save-review", 0, first.fingerprint)
    assert result == service.save(PLAYER, "save-review", 0, first.fingerprint)
    assert service.get(PLAYER).saved_current
    assert service.saved(PLAYER) == first.sheet
    restarted = CreationReviewService(OnboardingStore(ledger.engine, ledger.policy))
    assert restarted.saved(PLAYER) == first.sheet
    current = creation.get(PLAYER)
    creation.save(
        PLAYER,
        "change-appearance",
        current.revision,
        current.character_revision,
        current.draft.model_copy(update={"girl_appearance": "PRIVATE_REVIEW_CANARY"}),
    )
    assert not service.get(PLAYER).saved_current
    assert service.saved(PLAYER) == first.sheet
    with pytest.raises(WorkflowError, match="STALE_REVIEW"):
        service.save(PLAYER, "save-review", 0, first.fingerprint)
    latest = service.get(PLAYER)
    service.save(PLAYER, "new-review", 1, latest.fingerprint)
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.creation_reviews)) == 2
        assert all(
            "PRIVATE_REVIEW_CANARY" not in text and "SHARED_BOND_CONTEXT" not in text
            for text in c.execute(sa.select(t.events.c.payload_json)).scalars()
        )
        assert all(
            "PRIVATE_REVIEW_CANARY" not in text
            for text in c.execute(sa.select(t.commands.c.outcome_json)).scalars()
        )
    for statement in (
        t.creation_reviews.delete(),
        t.creation_reviews.update().values(body_json="{}"),
    ):
        with ledger.engine.begin() as c:
            with pytest.raises(IntegrityError):
                c.execute(statement)


def test_dependency_changes_withdrawal_roster_and_handler_rulings_stale_reviews(ledger):
    service, _, handler = ready(ledger)
    original = service.get(PLAYER)
    service.save(PLAYER, "saved", 0, original.fingerprint)
    bond = original.sheet.bonds[0]
    BondService(ledger).decide(OTHER, "withdraw", bond.id, bond.revision, "withdraw")
    assert not service.get(PLAYER).saved_current
    assert "starting_bond" in {x.code for x in service.get(PLAYER).sheet.issues}
    with pytest.raises(WorkflowError, match="STALE_REVIEW"):
        service.save(PLAYER, "old", 1, original.fingerprint)
    before = service.get(PLAYER)
    handler.rulings(ADMIN, "clear-rulings", handler.roster(ADMIN)["revision"], None)
    assert before.fingerprint != service.get(PLAYER).fingerprint
    seed(ledger, GuildViewer(8, 200, True, False))
    assert "status" in {x.code for x in service.get(PLAYER).sheet.issues}


def test_rules_authority_stale_versions_replay_and_reset(ledger):
    service, _, handler = ready(ledger)
    expected = handler.roster(ADMIN)["revision"]
    for viewer in (PLAYER, OTHER, GuildViewer(1, 999, True, True)):
        with pytest.raises(WorkflowError):
            handler.rulings(viewer, "forged", expected, CreationRulings())
    with pytest.raises(WorkflowError, match="STALE_REVISION"):
        handler.rulings(ADMIN, "stale", 0, CreationRulings())
    saved = handler.rulings(ADMIN, "confirmed", expected, CreationRulings())
    assert saved == handler.rulings(ADMIN, "confirmed", expected, CreationRulings())
    handler.appoint(ADMIN, "revoke", expected + 1, None)
    assert handler.view(PLAYER)["creation_rulings"] is None
    with pytest.raises(WorkflowError):
        handler.rulings(ADMIN, "confirmed", expected, CreationRulings())
    assert service.get(PLAYER).sheet.rulings is None


def test_newgirl_history_authority_stale_roster_and_missing_discussion(ledger):
    service, creation, _ = ready(ledger, "NEWGIRL")
    progress = creation.get(PLAYER)
    with pytest.raises(ValueError):
        PriorMission(user_id=3, character_revision=1, missions=2)
    with pytest.raises(ValueError):
        CreationDraft(girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B", cadre_discussed=True)
    with pytest.raises(ValueError):
        CreationDraft(
            girl_playbook="NEWGIRL",
            frame_playbook="JANUS-B",
            prior_missions=(PriorMission(user_id=3, missions=0),) * 2,
        )
    forged = progress.draft.model_copy(
        update={"prior_missions": (PriorMission(user_id=999, missions=0),)}
    )
    with pytest.raises(WorkflowError, match="STALE_CADRE"):
        creation.save(PLAYER, "forged-history", 1, 2, forged)
    seed(ledger, GuildViewer(8, 200, True, False))
    assert "cadre_history" in {x.code for x in service.get(PLAYER).sheet.issues}
    with pytest.raises(WorkflowError, match="every current"):
        creation.save(PLAYER, "stale-history", 1, 2, progress.draft)
    draft = progress.draft.model_copy(update={"cadre_discussed": False})
    creation.save(PLAYER, "undiscussed", 1, 2, draft)
    assert "cadre_discussion" in {x.code for x in service.get(PLAYER).sheet.issues}


def test_review_concurrency_rollback_backup_and_isolation(ledger, tmp_path, monkeypatch):
    service, _, _ = ready(ledger)
    current = service.get(PLAYER)
    original_audit = ledger._audit

    def fail(*args, **kwargs):
        original_audit(*args, **kwargs)
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(ledger, "_audit", fail)
    with pytest.raises(RuntimeError):
        service.save(PLAYER, "rollback", 0, current.fingerprint)
    assert service.saved(PLAYER) is None
    monkeypatch.setattr(ledger, "_audit", original_audit)

    def save(key):
        try:
            return service.save(PLAYER, key, 0, current.fingerprint)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, ("one", "two")))
    assert sum(isinstance(x, dict) for x in results) == 1
    path = tmp_path / "review-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        assert (
            CreationReviewService(OnboardingStore(engine, ledger.policy)).saved(PLAYER)
            == current.sheet
        )
    finally:
        engine.dispose()
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    foreign = GuildViewer(2, 300, True, False)
    seed(other, foreign)
    assert CreationReviewService(other).saved(foreign) is None
    with pytest.raises(WorkflowError):
        service.get(foreign)
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    for action in (
        lambda: service.get(PLAYER),
        lambda: service.saved(PLAYER),
        lambda: service.save(PLAYER, "one", 0, current.fingerprint),
    ):
        with pytest.raises(WorkflowError):
            action()


def test_native_review_sections_private_save_old_click_and_close(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, creation, _ = ready(ledger)

    async def run():
        view = ReviewView(service, 2)
        await view.present(request(PLAYER, 1))
        assert view.activate.disabled and len(view.to_components()) <= 5
        assert not await view.interaction_check(request(OTHER, 2))
        menu = next(x for x in view.children if isinstance(x, SectionSelect))
        menu._values = ["Assets"]
        await menu.callback(request(PLAYER, 3))
        assert view.section == "Assets"
        original_id = view.save.custom_id
        await view.save.callback(request(PLAYER, 4, original_id))
        assert view.current.saved_revision == 1
        await view.save.callback(request(PLAYER, 5, original_id))
        assert service.get(PLAYER).saved_revision == 1
        await view.activate.callback(request(PLAYER, 6))
        assert service.get(PLAYER).sheet.state == "draft_rules_unverified"
        await view.close.callback(request(PLAYER, 7))
        reopened = ReviewView(service, 2)
        await reopened.present(request(PLAYER, 8))
        assert reopened.current.saved_current

    asyncio.run(run())


def test_native_newgirl_mission_choices_reset_attestation_and_save(ledger):
    service, creation, _ = ready(ledger, "NEWGIRL")

    async def run():
        parent = CreationView(creation, 2, creation.get(PLAYER))
        view = HistoryView(parent, creation.cadre(PLAYER))
        await view.render(request(PLAYER, 1))
        assert parent.draft.cadre_discussed
        menu = next(x for x in view.children if isinstance(x, MissionSelect))
        menu._values = ["1"]
        await menu.callback(request(PLAYER, 2))
        assert not parent.draft.cadre_discussed
        assert not await view.interaction_check(request(OTHER, 3))
        await view.discussed.callback(request(PLAYER, 4))
        assert parent.draft.cadre_discussed
        draft = parent.draft
        creation.save(PLAYER, "new-history", 1, 2, draft)
        assert creation.get(PLAYER).draft.prior_missions == draft.prior_missions
        assert service.get(PLAYER).sheet.ready_for_rules_review

    asyncio.run(run())


def test_native_ruling_dropdown_requires_confirmation(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    _, _, handler = ready(ledger)

    async def run():
        old = handler.view(ADMIN)["revision"]
        view = RulingsView(handler, 1, old)
        assert not await view.interaction_check(request(PLAYER, 1))
        menu = next(x for x in view.children if isinstance(x, RulingSelect))
        menu._values = ["unresolved"]
        interaction = request(ADMIN, 2)
        await menu.callback(interaction)
        assert handler.view(ADMIN)["revision"] == old
        confirm = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(confirm, ConfirmSetup)
        await confirm.confirm.callback(request(ADMIN, 3))
        assert handler.view(ADMIN)["creation_rulings"] is None

    asyncio.run(run())


def test_review_pages_preserve_long_private_text_without_discord_overflow(ledger):
    service, creation, _ = ready(ledger)
    progress = creation.get(PLAYER)
    data = progress.draft.model_copy(
        update={
            "girl_assets": tuple(
                AssetChoice(name=x.name, description="*" * 700) for x in progress.draft.girl_assets
            ),
            "frame_assets": tuple(
                AssetChoice(name=x.name, description="~" * 700) for x in progress.draft.frame_assets
            ),
        }
    )
    creation.save(PLAYER, "long", 1, 2, data)
    output = pages(service.get(PLAYER), "Assets")
    assert len(output) > 1 and all(len(x) <= 3600 for x in output)
    assert sum(x.count("*") for x in output) == 1400


def test_mutual_incoming_bond_can_be_explicitly_selected_in_two_pilot_cadre(ledger):
    service, creation, _ = ready(ledger)
    creation.save(OTHER, "other-creation", 0, 1, selected())
    current = service.get(OTHER)
    assert "starting_bond" in {x.code for x in current.sheet.issues}
    incoming = next(x for x in current.sheet.bonds if not x.outgoing)
    args = (
        OTHER,
        "choose-incoming",
        current.sheet.creation_revision,
        current.sheet.character_revision,
        current.sheet.creation,
        incoming.id,
    )
    result = service.select_bond(*args)
    assert result == service.select_bond(*args)
    assert service.get(OTHER).sheet.ready_for_rules_review
    BondService(ledger).decide(
        PLAYER, "withdraw-incoming", incoming.id, incoming.revision, "withdraw"
    )
    stale = service.get(OTHER)
    assert "starting_bond" in {x.code for x in stale.sheet.issues}
    service.select_bond(
        OTHER,
        "clear-choice",
        stale.sheet.creation_revision,
        stale.sheet.character_revision,
        stale.sheet.creation,
        None,
    )
    assert creation.get(OTHER).draft.starting_bond_id is None


def test_starting_bond_selection_rejects_wrong_depth_unknown_and_stale_version(ledger):
    service, creation, _ = ready(ledger, "BONDED")
    creation.save(OTHER, "other-creation", 0, 1, selected())
    other = service.get(OTHER)
    intense = other.sheet.bonds[0]
    with pytest.raises(WorkflowError, match="role/depth"):
        service.select_bond(OTHER, "wrong-depth", 1, 1, other.sheet.creation, intense.id)
    own = service.get(PLAYER)
    with pytest.raises(WorkflowError, match="STALE_BOND"):
        service.select_bond(PLAYER, "unknown", 1, 2, own.sheet.creation, str(uuid4()))
    with pytest.raises(WorkflowError, match="STALE_REVISION"):
        service.select_bond(PLAYER, "old-version", 0, 2, own.sheet.creation, intense.id)


def test_owner_approved_defaults_are_trusted_policy_not_synthetic_handler_consent(ledger):
    seed(ledger)
    defaults = CreationRulings(provenance="owner_approved_campaign_ruling")
    policy = ledger.policy.model_copy(update={"owner_creation_rulings": defaults})
    policy = type(policy).model_validate_json(policy.model_dump_json())
    store = OnboardingStore(ledger.engine, policy)
    service = CreationReviewService(store)
    with ledger.engine.connect() as c:
        before = c.scalar(sa.select(sa.func.count()).select_from(t.events))
    assert service.get(PLAYER).sheet.rulings == defaults
    assert "starting_resources" not in {x.code for x in service.get(PLAYER).sheet.issues}
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.events)) == before
    with pytest.raises(ValueError):
        type(policy).model_validate(
            policy.model_dump() | {"owner_creation_rulings": CreationRulings()}
        )
    store.join(ADMIN, "join-admin")
    handler = HandlerService(store)
    handler.appoint(ADMIN, "appoint", 0, 1)
    with pytest.raises(WorkflowError, match="provenance"):
        handler.rulings(ADMIN, "forge-owner", 1, defaults)
    handler.rulings(ADMIN, "unresolved-override", 1, None)
    assert service.get(PLAYER).sheet.rulings is None


def test_native_starting_bond_choice_requires_confirmation_and_old_review_rejected(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding
    from girlframe.discord_adapter.creation_review import ConfirmBond, StartingBondSelect

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, creation, _ = ready(ledger)
    creation.save(OTHER, "other-creation", 0, 1, selected())

    async def run():
        view = ReviewView(service, 3)
        await view.present(request(OTHER, 1))
        old_id = view.save.custom_id
        menu = next(x for x in view.children if isinstance(x, StartingBondSelect))
        menu._values = [view.current.sheet.bonds[0].id]
        interaction = request(OTHER, 2)
        await menu.callback(interaction)
        confirm = interaction.response.edit_message.call_args.kwargs["view"]
        assert isinstance(confirm, ConfirmBond)
        assert creation.get(OTHER).draft.starting_bond_id is None
        assert not await confirm.interaction_check(request(PLAYER, 3))
        await confirm.confirm.callback(request(OTHER, 4))
        assert service.get(OTHER).sheet.ready_for_rules_review
        await view.save.callback(request(OTHER, 5, old_id))
        assert service.get(OTHER).saved_revision == 0

    asyncio.run(run())


def test_newgirl_inbox_routes_history_and_removes_task_after_saved_attestation(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding
    from girlframe.discord_adapter.inbox import InboxBackButton, InboxView
    from girlframe.services.inbox import InboxService

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, creation, _ = ready(ledger, "NEWGIRL")
    progress = creation.get(PLAYER)
    creation.save(
        PLAYER, "reset-history", 1, 2, progress.draft.model_copy(update={"cadre_discussed": False})
    )
    inbox = InboxService(ledger)
    item = next(x for x in inbox.items(PLAYER) if x.task == "history")

    async def run():
        parent = InboxView(inbox, 2)
        interaction = request(PLAYER, 1)
        await parent.route(interaction, item)
        history = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(history, HistoryView)
        assert any(isinstance(x, InboxBackButton) for x in history.children)
        await history.discussed.callback(request(PLAYER, 2))
        assert any(isinstance(x, InboxBackButton) for x in history.children)
        progress = history.parent.progress
        creation.save(PLAYER, "attest", progress.revision, 2, history.parent.draft)
        assert not any(x.task == "history" for x in inbox.items(PLAYER))
        assert service.get(PLAYER).sheet.ready_for_rules_review

    asyncio.run(run())


def test_received_court_role_is_in_recipient_sheet_and_withdrawal_stales_it(ledger):
    service, creation, _ = ready(ledger, frame="THE RED QUEEN")
    creation.save(OTHER, "other-creation", 0, 1, selected())
    before = service.get(OTHER)
    received = before.sheet.received_court
    assert len(received) == 1 and received[0].value == "The Knight"
    assert received[0].target_id == OTHER.user_id
    service.save(OTHER, "recipient-review", 0, before.fingerprint)
    SharedSetupService(ledger).decide(
        PLAYER, "withdraw-court", received[0].id, received[0].revision, "withdraw"
    )
    after = service.get(OTHER)
    assert after.sheet.received_court == () and not after.saved_current
    assert service.saved(OTHER).received_court == received
    assert "OWNER_PROFILE_SECRET" not in before.sheet.model_dump_json()


@pytest.mark.parametrize(
    "girl,frame",
    [
        ("NEWGIRL", "THE RED QUEEN"),
        ("NEWGIRL", "THE PRINCE"),
        ("BONDED", "THE PRINCE"),
        ("BONDED", "WYVERN 0.4"),
        ("MOCKINGBIRD", "CONSUME"),
    ],
)
def test_cross_playbook_review_dependencies_and_native_component_limits(ledger, girl, frame):
    service, creation, _ = ready(ledger, girl, frame)
    review = service.get(PLAYER)
    assert review.sheet.ready_for_rules_review
    if girl == "NEWGIRL" and frame == "THE RED QUEEN":
        assert len(review.sheet.creation.shared_tokens) == 2
        assert {x.kind for x in review.sheet.shared} == {"callsign", "court"}

    async def run():
        parent = CreationView(creation, 2, creation.get(PLAYER))
        assert len(parent.to_components()) <= 5
        assert all(len(row["components"]) <= 5 for row in parent.to_components())
        view = ReviewView(service, 2)
        await view.present(request(PLAYER, 1))
        assert len(view.to_components()) <= 5

    asyncio.run(run())
