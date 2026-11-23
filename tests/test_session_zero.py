"""Session Zero group consent, actual sheet sources, and the private native download."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from test_creation_review import ready, selected
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.discord_adapter.session_zero import HandlerModal, SessionZeroView, open_panel
from girlframe.engine.session_zero import CharacterNotes, HandlerProfile
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.session_zero import SessionZeroService

OUTSIDE = GuildViewer(4, 200, True, False)
FACILITATOR = GuildViewer(5, 200, True, True)
PROFILE = HandlerProfile(
    member=ADMIN.user_id,
    player_name="Synthetic Handler Player",
    name="Anwen",
    archetype="Advocate",
    appearance="Practical uniform and a very bright scarf",
    personality="Patient, curious, stubborn",
)


def reviewed_sheets(store):
    review, creation, _ = ready(store)
    current = creation.get(OTHER)
    draft = selected("MOCKINGBIRD", "JANUS-B").model_copy(
        update={"shared_tokens": current.draft.shared_tokens}
    )
    creation.save(OTHER, "other-build", current.revision, current.character_revision, draft)
    counterpart = next(x for x in review.get(OTHER).sheet.bonds if not x.outgoing)
    current = creation.get(OTHER)
    review.select_bond(
        OTHER,
        "other-choose-bond",
        current.revision,
        current.character_revision,
        current.draft,
        counterpart.id,
    )
    for viewer in (PLAYER, OTHER):
        saved = review.get(viewer)
        assert saved.sheet.ready_for_rules_review
        review.save(viewer, f"review-{viewer.user_id}", saved.saved_revision, saved.fingerprint)
    return review, creation


def group(service):
    service.set_group(ADMIN, "start-group", 0, (1, 2, 3))
    service.propose(PLAYER, "proposal", 1, PROFILE)
    return service.view(PLAYER)["proposal"]


def approve(service, proposal):
    for viewer in (ADMIN, PLAYER, OTHER):
        service.decide(viewer, f"approve-{viewer.user_id}", proposal, approve=True)


def interaction(user, identity=501):
    request = MagicMock()
    request.user = MagicMock(spec=discord.Member)
    request.user.id = user
    request.user.guild_permissions = discord.Permissions(administrator=user == 1)
    request.id = identity
    request.guild_id = 200
    request.response.is_done.return_value = False
    request.response.defer = AsyncMock(
        side_effect=lambda **_: request.response.is_done.configure_mock(return_value=True)
    )
    request.edit_original_response = AsyncMock()
    return request


def test_group_approves_exact_handler_proposal_before_existing_authority_can_appoint(ledger):
    for viewer in (ADMIN, PLAYER, OTHER, OUTSIDE, FACILITATOR):
        ledger.join(viewer, f"member-{viewer.user_id}")
    service = SessionZeroService(ledger)
    proposal = group(service)
    service.decide(PLAYER, "first-approval", proposal, approve=True)
    with pytest.raises(WorkflowError, match="group-approved"):
        service.appoint(ADMIN, "premature", 0, proposal, ADMIN.user_id)
    service.propose(
        OTHER,
        "revised-proposal",
        service.view(OTHER)["revision"],
        PROFILE.model_copy(update={"personality": "Patient and quietly funny"}),
    )
    view = service.view(ADMIN)
    assert view["approvals"] == 0 and proposal != view["proposal"]
    with pytest.raises(WorkflowError, match="STALE_PROPOSAL"):
        service.decide(OTHER, "old-proposal", proposal, approve=True)
    with pytest.raises(WorkflowError, match="group"):
        service.decide(OUTSIDE, "not-in-group", view["proposal"], approve=True)
    approve(service, view["proposal"])
    limited = service.view(FACILITATOR)
    assert limited["can_appoint"] and "profile" not in limited
    assert "sheets" not in limited and "goals" not in limited
    result = service.appoint(
        FACILITATOR, "approved-appointment", 0, view["proposal"], ADMIN.user_id
    )
    assert result["operation"] == "campaign.handler_appointed"
    assert service.handler.appointment_preview(ADMIN)["handler_id"] == ADMIN.user_id
    assert service.view(PLAYER)["handler_ready"] == ADMIN.user_id
    assert service.view(PLAYER)["sheets"] == {2: "missing", 3: "missing"}
    with pytest.raises(WorkflowError, match="Save a character draft"):
        service.attach(PLAYER, "no-sheet", service.view(PLAYER)["revision"])


def test_saved_sheets_gate_generation_and_private_notes_reach_only_group_download(ledger):
    review, creation = reviewed_sheets(ledger)
    ledger.join(OUTSIDE, "join-outsider")
    ledger.join(FACILITATOR, "join-facilitator")
    service = SessionZeroService(ledger)
    approve(service, group(service))
    prepared = service.view(PLAYER)
    with pytest.raises(WorkflowError, match="Every listed Pilot"):
        service.generate(PLAYER, prepared["revision"])
    with pytest.raises(WorkflowError, match="Attach your current"):
        service.notes(PLAYER, "no-attached-input", prepared["revision"], CharacterNotes(goal="Try"))
    service.attach(PLAYER, "first-sheet", prepared["revision"])
    service.notes(
        PLAYER,
        "first-input",
        service.view(PLAYER)["revision"],
        CharacterNotes(
            goal="Recover a missing teammate",
            hook="A divisive rescue request",
            spotlight="A sincere talk with the Handler",
        ),
    )
    service.attach(OTHER, "second-sheet", service.view(OTHER)["revision"])
    service.goals(
        ADMIN,
        "goal-draft",
        service.view(ADMIN)["revision"],
        "Find who abandoned the rescue attempt.",
    )
    approved = service.view(PLAYER)
    assert approved["can_generate"]
    # A private source edit invalidates its exact live review fingerprint.
    progress = creation.get(PLAYER)
    creation.save(
        PLAYER, "changed-source", progress.revision, progress.character_revision, progress.draft
    )
    assert service.view(OTHER)["sheets"][2] == "refresh"
    with pytest.raises(WorkflowError, match="current character sheet"):
        service.generate(OTHER, approved["revision"])
    changed = review.get(PLAYER)
    review.save(PLAYER, "fresh-review", changed.saved_revision, changed.fingerprint)
    service.attach(PLAYER, "fresh-attachment", service.view(PLAYER)["revision"])
    ledger.engine.dispose()
    restarted = SessionZeroService(ledger)
    exact_revision = restarted.view(OTHER)["revision"]
    sheet = restarted.generate(OTHER, exact_revision)
    assert "Anwen" in sheet and "Advocate" in sheet
    assert "Played by Synthetic Handler Player" in sheet
    assert "Patient, curious, stubborn" in sheet
    assert sheet.count("Saved character review") == 2
    assert "Recover a missing teammate" in sheet and "A divisive rescue request" in sheet
    assert "Find who abandoned the rescue attempt" in sheet
    assert "OWNER_PROFILE_SECRET" not in sheet and "SHARED_BOND_CONTEXT" not in sheet
    assert not any(label in sheet for label in ("sheets_json", "dependency_tokens", "notes_json"))
    for viewer in (OUTSIDE, FACILITATOR, GuildViewer(2, 999, True, True)):
        with pytest.raises(WorkflowError):
            restarted.generate(viewer, exact_revision)
    assert "Recover a missing teammate" not in str(restarted.store.public_export())
    restarted.set_group(ADMIN, "change-group", exact_revision, (1, 3, 4))
    assert "Recover a missing teammate" not in str(restarted.view(OUTSIDE))
    with pytest.raises(WorkflowError, match="group"):
        restarted.generate(PLAYER, exact_revision)


def test_native_generate_button_sends_private_file_from_real_active_sheets(ledger, monkeypatch):
    game, *_ = setup_game(ledger)
    service = SessionZeroService(ledger)
    approve(service, group(service))
    current = service.view(PLAYER)
    reading = state(game)
    with pytest.raises(WorkflowError, match="Every listed Pilot"):
        service.generate(PLAYER, current["revision"])
    service.attach(PLAYER, "active-first", current["revision"])
    service.attach(OTHER, "active-second", service.view(OTHER)["revision"])
    assert state(game) == reading

    async def allowed(*args):
        return True

    monkeypatch.setattr("girlframe.discord_adapter.session_zero.action_gate", allowed)

    async def run():
        request = interaction(PLAYER.user_id)
        await open_panel(request, service)
        view = request.edit_original_response.call_args.kwargs["view"]
        assert isinstance(view, SessionZeroView)
        assert not view.generate.disabled
        assert request.response.defer.call_args.kwargs["ephemeral"]
        assert [x["component"]["type"] for x in HandlerModal(view).to_components()] == [
            5,
            3,
            4,
            4,
            4,
        ]
        click = interaction(PLAYER.user_id, 502)
        delivered = {}

        async def capture(**kwargs):
            (attachment,) = kwargs["attachments"]
            delivered.update(filename=attachment.filename, sheet=attachment.fp.read().decode())

        click.edit_original_response = AsyncMock(side_effect=capture)
        await view.generate.callback(click)
        assert click.response.defer.call_args.kwargs["ephemeral"]
        assert delivered["filename"] == "session-zero.md"
        assert delivered["sheet"].count("Active character sheet") == 2
        assert "OWNER_PROFILE_SECRET" not in delivered["sheet"]

    asyncio.run(run())
