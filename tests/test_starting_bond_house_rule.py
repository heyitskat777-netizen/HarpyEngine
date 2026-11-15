"""Synthetic normal setup, explicit test exemption and release-version checks."""

import asyncio
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import discord
import pytest
from test_creation_review import ready
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger
from test_start_dashboard_ui import current

from girlframe import __version__
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.discord_adapter.creation_review import ConfirmBond, ReviewView, StartingBondSelect
from girlframe.discord_adapter.handler_setup import ConfirmSetup
from girlframe.engine.bonds import BondProposal
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.bonds import BondService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer, ReadOnlyBotService
from girlframe.services.start_dashboard import StartDashboardService


def approve(store):
    store.policy = store.policy.model_copy(
        update={
            "owner_starting_bond_count": 2,
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic only",
                reference="offline test, not campaign approval",
            ),
        }
    )


def test_two_real_bonds_native_selection_saved_review_activation_and_withdrawal(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    review, creation, handler = ready(ledger)
    approve(ledger)
    third = GuildViewer(4, PLAYER.guild_id, True, False)
    seed(ledger, third, callsign="SYNTH_THIRD")
    handler.rank(
        ADMIN,
        "three-status",
        handler.roster(ADMIN)["revision"],
        (
            PilotRef(user_id=2, character_revision=2),
            PilotRef(user_id=3, character_revision=1),
            PilotRef(user_id=4, character_revision=1),
        ),
    )
    assert "additional_starting_bond" in {x.code for x in review.get(PLAYER).sheet.issues}
    bonds = BondService(ledger)
    primary = review.get(PLAYER).sheet.bonds[0]
    draft = creation.get(PLAYER)
    review.select_bond(PLAYER, "primary-choice", draft.revision, 2, draft.draft, primary.id)
    proposal = bonds.propose(
        PLAYER,
        "second-proposal",
        2,
        1,
        BondProposal(target_id=4, prompt=1, context="Shared synthetic second relationship"),
    )
    assert not review.get(PLAYER).sheet.ready_for_rules_review
    bonds.decide(third, "second-accept", proposal["id"], 1, "accept")
    assert StartDashboardService(ledger).snapshot(PLAYER)["character"]["next_route"] == "review"

    async def select():
        view = ReviewView(review, PLAYER.user_id)
        await view.present(current(PLAYER, 89501))
        assert view.second_bond in view.children
        picker = StartingBondSelect(view, view.current, additional=True)
        assert {x.value for x in picker.options} == {"clear", proposal["id"]}
        picker._values = [proposal["id"]]
        prompt = current(PLAYER, 89502)
        await picker.callback(prompt)
        confirmation = prompt.response.edit_message.call_args.kwargs["view"]
        assert isinstance(confirmation, ConfirmBond)
        assert creation.get(PLAYER).draft.additional_starting_bond_id is None
        assert not await confirmation.interaction_check(current(OTHER, 89503))
        await confirmation.confirm.callback(current(PLAYER, 89504))

    asyncio.run(select())
    selected = review.get(PLAYER)
    assert selected.sheet.ready_for_rules_review and selected.sheet.required_starting_bonds == 2
    assert selected.sheet.primary_starting_bond.id == primary.id
    assert selected.sheet.creation.additional_starting_bond_id == proposal["id"]
    review.save(PLAYER, "two-review", selected.saved_revision, selected.fingerprint)
    saved = review.get(PLAYER)
    game = GameService(ledger)
    result = game.activate(PLAYER, "two-activate", saved.fingerprint)
    assert game.activate(PLAYER, "two-activate", saved.fingerprint) == result
    with ledger.engine.connect() as c:
        state = load_state(c, ledger.campaign_id)
        assert {x.counterpart for x in state.sheets["2"].review.bonds} == {3, 4}
        assert len(state.bonds) == 2
    with pytest.raises(WorkflowError, match="Already activated"):
        handler.bond_test(
            ADMIN,
            "no-active-bypass",
            handler.roster(ADMIN)["revision"],
            PilotRef(user_id=2, character_revision=2),
            True,
        )
    bonds.decide(third, "second-withdraw", proposal["id"], 2, "withdraw")
    assert "additional_starting_bond" in {x.code for x in review.get(PLAYER).sheet.issues}


def test_handler_test_bypass_is_explicit_reversible_private_and_creates_no_bonds(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    review, _, handler = ready(ledger)
    approve(ledger)
    row = BondService(ledger).list(PLAYER)[0]
    BondService(ledger).decide(PLAYER, "withdraw-original", row["id"], row["revision"], "withdraw")
    pilot = PilotRef(user_id=2, character_revision=2)
    with pytest.raises(WorkflowError, match="Handler"):
        handler.bond_test(OTHER, "not-authorized", handler.roster(ADMIN)["revision"], pilot, True)

    async def grant():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            command = bot.tree.get_command("campaign", guild=discord.Object(id=200)).get_command(
                "bond_test"
            )
            preview = current(ADMIN, 89601)
            await command.callback(preview, current(PLAYER, 89602).user, True)
            form = preview.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, ConfirmSetup)
            assert not review.get(PLAYER).sheet.starting_bond_test_bypass
            await form.confirm.callback(current(ADMIN, 89603))

    asyncio.run(grant())
    bypassed = review.get(PLAYER)
    assert bypassed.sheet.starting_bond_test_bypass and not bypassed.sheet.bonds
    assert bypassed.sheet.ready_for_rules_review
    review.save(PLAYER, "test-review", bypassed.saved_revision, bypassed.fingerprint)
    expected = handler.roster(ADMIN)["revision"]
    result = handler.bond_test(ADMIN, "remove-test", expected, pilot, False)
    assert handler.bond_test(ADMIN, "remove-test", expected, pilot, False) == result
    revoked = review.get(PLAYER)
    assert not revoked.saved_current and not revoked.sheet.starting_bond_test_bypass
    with pytest.raises(WorkflowError, match="STALE_OR_INCOMPLETE"):
        GameService(ledger).activate(PLAYER, "no-stale-test", bypassed.fingerprint)
    expected = handler.roster(ADMIN)["revision"]
    handler.bond_test(ADMIN, "grant-again", expected, pilot, True)
    latest = review.get(PLAYER)
    review.save(PLAYER, "test-review-fresh", latest.saved_revision, latest.fingerprint)
    GameService(ledger).activate(PLAYER, "test-activation", latest.fingerprint)
    with ledger.engine.connect() as c:
        state = load_state(c, ledger.campaign_id)
        assert not state.bonds and state.sheets["2"].review.starting_bond_test_bypass


def test_package_and_presence_use_the_same_release_version():
    from girlframe.discord_adapter.presence import activity

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["hatch"]["version"]["path"] == "src/girlframe/__init__.py"
    assert activity("running").name == f"Running v{__version__}"
    assert activity("restarting").name == f"Restarting v{__version__}"


def test_optional_second_bond_does_not_block_review_or_activation(ledger):
    review, _, _ = ready(ledger)
    approve(ledger)
    ledger.policy = ledger.policy.model_copy(update={"owner_second_starting_bond_optional": True})
    snapshot = review.get(PLAYER)
    assert snapshot.sheet.required_starting_bonds == 1
    assert snapshot.sheet.optional_second_starting_bond
    assert snapshot.sheet.creation.additional_starting_bond_id is None
    assert snapshot.sheet.ready_for_rules_review

    async def show():
        view = ReviewView(review, PLAYER.user_id)
        await view.present(current(PLAYER, 89701))
        assert view.second_bond in view.children and "optional" in view.second_bond.label

    asyncio.run(show())
    review.save(PLAYER, "optional-review", snapshot.saved_revision, snapshot.fingerprint)
    GameService(ledger).activate(PLAYER, "optional-activation", snapshot.fingerprint)
    with ledger.engine.connect() as c:
        state = load_state(c, ledger.campaign_id)
        assert len(state.bonds) == 1 and len(state.sheets["2"].review.bonds) == 1
