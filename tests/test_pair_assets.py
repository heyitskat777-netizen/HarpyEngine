import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import discord
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from test_creation import selected
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables as t
from girlframe.discord_adapter.creation import CreationView, DetailsModal, description_assets
from girlframe.discord_adapter.pair_assets import PairView
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import AssetChoice, CreationDraft
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.drafts import DraftInput
from girlframe.engine.frame_setup import FrameSetup, HarpyCore
from girlframe.engine.pair_assets import PairNames
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.pair_assets import PairService
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture
NAMES = tuple(CATALOG["BONDED"]["assets"][:2])
ALTERNATIVE = tuple(CATALOG["BONDED"]["assets"][2:4])


def ready(ledger):
    seed(ledger)
    seed(ledger, OTHER)
    ledger.save_draft(
        PLAYER,
        "bonded",
        1,
        DraftInput(
            callsign="SYNTH",
            girl_playbook="BONDED",
            frame_playbook="JANUS-B",
            notes="PRIVATE_OWNER_NOTES",
        ),
    )
    bonds = BondService(ledger)
    bond = bonds.propose(PLAYER, "pair", 2, 1, BondProposal(target_id=OTHER.user_id, prompt=0))
    bonds.decide(OTHER, "accept", bond["id"], 1, "accept")
    return PairService(ledger), bonds, bond["id"]


def choose(service, identity, key="choose", expected=0, names=NAMES):
    return service.choose(OTHER, key, identity, 2, expected, PairNames(names=names))


@pytest.mark.parametrize(
    "frame", [k for k, v in CATALOG.items() if v["family"] == "frame"] + ["JANUS-B"]
)
def test_verified_frame_baselines_and_roundtrip(frame):
    data = selected(frame=frame)
    assert CreationDraft.model_validate_json(data.model_dump_json()) == data
    baseline = data.frame_setup
    assert baseline.schema_version == 1
    assert baseline.frame == ("JANUS" if frame == "JANUS-B" else frame)
    assert not hasattr(baseline, "heat")
    if frame in ("JANUS", "JANUS-B"):
        assert baseline.harpy_core.tags == (
            "Drugged",
            "Restrained",
            "Muzzled",
            "Recovering from Surgery",
        )
        with pytest.raises(ValueError):
            HarpyCore(name="Invented name")
        with pytest.raises(ValueError):
            CreationDraft.model_validate(
                data.model_dump()
                | {
                    "frame_setup": FrameSetup(
                        frame="JANUS", source_pdf_pages=(68,), harpy_core=HarpyCore(tags=())
                    )
                }
            )
    if frame == "CONSUME":
        assert baseline.starvation_levels == ("Quiet", "Gnawing", "Ravenous") and baseline.pending
    if frame == "DOCTORDOCTOR MK. II":
        assert baseline.obsolescence_capacity == 8 and baseline.pending
    if frame == "THE RED QUEEN":
        assert (
            len(baseline.am_roles) == 5
            and baseline.default_am_self == 4
            and baseline.default_am_other == 1
            and baseline.pending
        )


def test_pair_option_and_owner_authority(ledger):
    service, bonds, identity = ready(ledger)
    for names in [
        (),
        (NAMES[0],),
        (NAMES[0], NAMES[0]),
        ("Invented", NAMES[0]),
        (*NAMES, ALTERNATIVE[0]),
    ]:
        with pytest.raises(ValueError):
            PairNames(names=names)
    seed(ledger, ADMIN)
    for actor in (PLAYER, ADMIN):
        with pytest.raises(WorkflowError):
            service.choose(actor, "forged", identity, 2, 0, PairNames(names=NAMES))
    result = choose(service, identity)
    assert result == choose(service, identity)
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        choose(service, identity, names=ALTERNATIVE)
    creation = CreationService(ledger)
    progress = creation.get(PLAYER)
    assert progress.pair_choice.names == NAMES
    with pytest.raises(ValueError):
        CreationDraft.model_validate(
            progress.draft.model_dump() | {"girl_assets": (AssetChoice(name=NAMES[0]),)}
        )
    with pytest.raises(WorkflowError):
        creation.save(
            PLAYER,
            "forged-description-names",
            0,
            2,
            progress.draft.model_copy(
                update={"pair_asset_descriptions": (AssetChoice(name=ALTERNATIVE[0]),)}
            ),
            expected_pair_token=progress.pair_choice.token,
        )
    assert "PRIVATE_OWNER_NOTES" not in json.dumps(service.prepare(OTHER, identity))
    assert "private_json" not in service.prepare(OTHER, identity)


def test_owner_descriptions_staleness_withdrawal_and_private_restart(ledger):
    service, bonds, identity = ready(ledger)
    choose(service, identity)
    creation = CreationService(ledger)
    progress = creation.get(PLAYER)
    draft = selected("BONDED").model_copy(
        update={
            "pair_source_token": progress.pair_choice.token,
            "pair_asset_descriptions": tuple(
                AssetChoice(name=name, description="PRIVATE_PAIR_DESCRIPTION") for name in NAMES
            ),
        }
    )
    creation.save(PLAYER, "owner-save", 0, 2, draft, expected_pair_token=progress.pair_choice.token)
    restored = CreationService(OnboardingStore(ledger.engine, ledger.policy)).get(PLAYER)
    assert restored.draft == draft
    assert restored.draft.missing(restored.pair_choice.names) == []
    assert "PRIVATE_PAIR_DESCRIPTION" not in json.dumps(service.prepare(OTHER, identity))
    assert "PRIVATE_PAIR_DESCRIPTION" not in json.dumps(ledger.public_export())
    with ledger.engine.connect() as c:
        assert all(
            "PRIVATE_PAIR_DESCRIPTION" not in text
            for text in c.execute(sa.select(t.events.c.payload_json)).scalars()
        )
    choose(service, identity, "changed", 1, ALTERNATIVE)
    with pytest.raises(WorkflowError, match="STALE_PAIR"):
        creation.save(
            PLAYER, "stale-owner", 1, 2, draft, expected_pair_token=restored.pair_choice.token
        )
    assert creation.get(PLAYER).draft.pair_asset_descriptions == ()
    bonds.decide(OTHER, "withdraw", identity, 2, "withdraw")
    assert creation.get(PLAYER).pair_choice is None
    with pytest.raises(WorkflowError):
        choose(service, identity)  # Revoked Pair authority also blocks inbox replay.


def test_pair_concurrency_rollback_immutability_isolation_and_backup(ledger, monkeypatch, tmp_path):
    from pathlib import Path

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database

    service, bonds, identity = ready(ledger)
    original = ledger._audit

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Synthetic failure")

    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_audit", fail)
        with pytest.raises(RuntimeError):
            choose(service, identity)
    assert service.prepare(OTHER, identity)["revision"] == 0

    def competing(index):
        try:
            return choose(service, identity, str(index), names=NAMES if index == 0 else ALTERNATIVE)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(competing, (0, 1)))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert any("STALE_REVISION" in x for x in results if isinstance(x, str))
    for mutation in (
        t.pair_asset_revisions.delete(),
        t.pair_asset_revisions.update().values(names_json="[]"),
    ):
        with ledger.engine.begin() as c:
            with pytest.raises(IntegrityError):
                c.execute(mutation)
    path = tmp_path / "pair-backup.db"
    copy_database(Path(ledger.engine.url.database), path)
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path}"))
    try:
        assert PairService(OnboardingStore(engine, ledger.policy)).prepare(
            OTHER, identity
        ) == service.prepare(OTHER, identity)
    finally:
        engine.dispose()
    other = OnboardingStore(
        ledger.engine, ledger.policy.model_copy(update={"guild_id": 300, "campaign_id": uuid4()})
    )
    viewer = GuildViewer(3, 300, True, False)
    seed(other, viewer)
    with pytest.raises(WorkflowError):
        PairService(other).prepare(viewer, identity)
    ledger.save_draft(
        OTHER,
        "changed-profile",
        1,
        DraftInput(callsign="OTHER", girl_playbook="ALPHA", frame_playbook="JANUS-B"),
    )
    with pytest.raises(WorkflowError):
        service.prepare(OTHER, identity)


def test_native_pair_selection_owner_descriptions_and_member_guards(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *a, **kw: True)
    service, bonds, identity = ready(ledger)

    def request(viewer, key):
        result = MagicMock()
        result.user = MagicMock(spec=discord.Member)
        result.user.id = viewer.user_id
        result.user.guild_permissions = discord.Permissions.none()
        result.guild_id, result.id = 200, key
        result.response.is_done.return_value = True
        result.response.edit_message = AsyncMock()
        result.response.defer = AsyncMock()
        result.edit_original_response = AsyncMock()
        return result

    async def run():
        view = PairView(service, OTHER.user_id, service.prepare(OTHER, identity))
        assert not await view.interaction_check(request(PLAYER, 200))
        selector = next(x for x in view.children if isinstance(x, discord.ui.Select))
        selector._values = list(NAMES)
        await selector.callback(request(OTHER, 201))
        await view.confirm.callback(request(OTHER, 202))
        creation = CreationService(ledger)
        parent = CreationView(creation, PLAYER.user_id, creation.get(PLAYER))
        readonly = next(
            x for x in parent.children if isinstance(x, discord.ui.Select) and x.row == 0
        )
        assert readonly.disabled and sum(x.default for x in readonly.options) == 2
        assert {x.name for x in description_assets(parent)} == set(NAMES)
        modal = DetailsModal(parent, assets=True)
        for field in modal.fields:
            field._value = "PRIVATE_UI_DESCRIPTION"
        await modal.on_submit(request(PLAYER, 203))
        await parent.save.callback(request(PLAYER, 204))
        assert len(creation.get(PLAYER).draft.pair_asset_descriptions) == 2
        assert parent.progress.pair_choice is not None
        assert creation.get(PLAYER).draft.girl_assets == ()
        facts = request(PLAYER, 205)
        await parent.frame_details.callback(facts)
        rendered = facts.response.edit_message.call_args.kwargs
        assert rendered["view"] is parent and "Separate unnamed Harpy Core" in rendered["content"]
        assert "PRIVATE_UI_DESCRIPTION" not in rendered["content"]

    asyncio.run(run())
