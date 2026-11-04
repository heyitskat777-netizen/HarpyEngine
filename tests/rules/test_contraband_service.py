"""Actual random source, original recipient, concealed Assets and private history."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import start, state
from test_strain_effect_service import pending, selected
from test_supply_service import Selector

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.database.connection import create_database_engine
from girlframe.database.maintenance import copy_database
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_core import install
from girlframe.engine.m3_requisition_state import GirlAsset
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.inbox import InboxService
from girlframe.services.ledger import CampaignLedger
from girlframe.services.m2_game import GameService
from girlframe.services.m3_contraband import ContrabandService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import OnboardingStore, WorkflowError

ledger = ledger_fixture


def ready(store, *, index=0, apply=True, public=False):
    effects, game, period, first = pending(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    selector = Selector(index)
    effects = EffectService(effects.strain, selector=selector)
    effects.apply(ADMIN, "actual-void", first, 1, state(game).revision, selected())
    if public:
        with store.transaction() as c:
            canon = state(game)
            canon.sheets["2"].public_fields = ("assets", "asset_descriptions")
            game.event(c, 2, "synthetic-public-assets-consent", "synthetic.public_sheet", canon)
    request = next(x for x in state(game).strain.requests if x.track == "rebellion")
    effects.strain.dice.face = 2
    effects.strain.roll(ADMIN, "actual-rebellion-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "actual-rebellion-column", request.id, 2, state(game).revision, 2)
    identity = request.id + ":effect"
    if apply:
        schedule(effects, game, identity)
    return ContrabandService(game), effects, game, identity, selector


def schedule(effects, game, identity, key="actual-private-find", **values):
    return effects.apply(
        ADMIN,
        key,
        identity,
        1,
        state(game).revision,
        Choice(
            rule_id="strain.rebellion.low.2.2",
            account="PRIVATE_HANDLER_SOURCE_ACCOUNT",
            target="base0",
            **values,
        ),
    )


def decide(service, identity, *, viewer=PLAYER, taken=True, key=None, choice=None, data=None):
    data = data or service.get(viewer, identity)
    return service.respond(
        viewer,
        key or str(uuid4()),
        identity,
        data["find_sha256"],
        data["actor_sha256"],
        taken,
        (
            choice
            or GirlAsset(name="PRIVATE_CONTRABAND_ITEM", description="PRIVATE_ITEM_DESCRIPTION")
        )
        if taken
        else None,
        "PRIVATE_OWNER_FIND_ACCOUNT" if taken else "",
    )


def test_actual_draw_creates_one_private_original_recipient_and_handler_cannot_view_it(ledger):
    svc, effects, game, identity, selector = ready(ledger)
    find = state(game).contraband_finds[0]
    assert selector.calls == 1 and selector.sizes == [2] and find.actor.entity == "2"
    assert find.actor.incarnation == state(game).sheets["2"].character_id
    assert find.taken is None and len(svc.list(PLAYER)) == 1
    for viewer in (OTHER, ADMIN):
        assert svc.list(viewer) == []
        with pytest.raises(WorkflowError, match="original recipient"):
            svc.get(viewer, identity)
        with pytest.raises(WorkflowError):
            decide(svc, identity, viewer=viewer)
    projection = effects.get(ADMIN, identity)
    assert "population" not in str(projection) and find.label not in str(projection)
    assert "index" not in str(projection) and "recipient" not in str(projection)
    items = InboxService(ledger).items(PLAYER)
    assert any(
        x.identity == identity and x.task == "m3_contraband" and x.state == "pending" for x in items
    )
    assert not any(x.task == "m3_contraband" for x in InboxService(ledger).items(ADMIN))
    assert not any(x.task == "m3_contraband" for x in InboxService(ledger).items(OTHER))


def test_actual_source_replay_is_one_draw_and_private_claim_does_not_charge_permissions(ledger):
    svc, effects, game, identity, selector = ready(ledger, apply=False)
    expected = state(game).revision
    choice = Choice(
        rule_id="strain.rebellion.low.2.2", account="Actual private find", target="base0"
    )
    first = effects.apply(ADMIN, "one-source", identity, 1, expected, choice)
    assert effects.apply(ADMIN, "one-source", identity, 1, expected, choice) == first
    before = state(game)
    data = svc.get(PLAYER, identity)
    outcome = decide(svc, identity, key="one-claim", data=data)
    assert decide(svc, identity, key="one-claim", data=data) == outcome
    after = state(game)
    assert after.sheets["2"].permissions == before.sheets["2"].permissions
    assert after.sheets["3"] == before.sheets["3"] and after.bonds == before.bonds
    asset = after.sheets["2"].assets[-1]
    assert asset.family == "girl" and asset.concealed and not asset.void and not asset.damaged
    assert asset.intrinsic is None and selector.calls == 1 and game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_outbox"])) == 0
    assert any(
        x.identity == identity and x.state == "accepted" for x in InboxService(ledger).items(PLAYER)
    )


@pytest.mark.parametrize("index", (-1, 2, True))
def test_invalid_random_index_does_not_create_a_recipient_or_resolve_source(ledger, index):
    _, effects, game, identity, selector = ready(ledger, index=index, apply=False)
    before = state(game)
    with pytest.raises(WorkflowError):
        schedule(effects, game, identity)
    assert state(game) == before and selector.calls == 1 and not state(game).contraband_finds
    assert effects.get(ADMIN, identity)["state"] == "pending"


def test_forged_recipient_or_unrelated_choices_fail_before_drawing(ledger):
    _, effects, game, identity, selector = ready(ledger, apply=False)
    with pytest.raises(WorkflowError, match="unrelated choices"):
        schedule(effects, game, identity, victim="2")
    assert selector.calls == 0 and not state(game).contraband_finds


def test_claim_respects_girl_cap_void_protection_and_actual_replacement_family(ledger):
    svc, _, game, identity, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets["2"]
        for index in range(2):
            sheet = install(
                sheet, AssetState(id="extra:" + str(index), family="girl", name="Extra")
            ).sheet
        sheet.assets[0].void = True
        canon.sheets["2"] = sheet
        game.event(c, 2, "synthetic-full-girl-assets", "synthetic.equipment", canon)
    before = state(game)
    for replacement in (None, "girl:0", "frame:0", "foreign"):
        with pytest.raises(WorkflowError, match="non-Void"):
            decide(
                svc,
                identity,
                choice=GirlAsset(name="Contraband", description="Actual item", replace=replacement),
            )
        assert state(game) == before
    decide(
        svc,
        identity,
        choice=GirlAsset(
            name="Enormous", description="A custom ordinary Girl item", replace="girl:1"
        ),
    )
    assets = [x for x in state(game).sheets["2"].assets if x.family == "girl"]
    assert len(assets) == 4 and any(x.id == "girl:0" and x.void for x in assets)
    assert not any(x.id == "girl:1" for x in assets)
    assert assets[-1].name == "Enormous" and assets[-1].intrinsic is None


def test_pause_and_known_play_block_acquisition_but_owned_decline_is_ooc(ledger):
    svc, _, game, identity, _ = ready(ledger)
    before = state(game)
    ledger.safety(OTHER, "pause-find", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        decide(svc, identity)
    ledger.safety(OTHER, "resume-find", ledger.status(OTHER)["revision"], pause=False)
    start(game)
    with pytest.raises(WorkflowError, match="pending Plays"):
        decide(svc, identity)
    ledger.safety(OTHER, "pause-decline", ledger.status(OTHER)["revision"], pause=True)
    decide(svc, identity, taken=False)
    assert state(game).sheets == before.sheets and state(game).contraband_finds[0].taken is False


def test_concealed_asset_stays_out_of_other_public_views_until_owned_explicit_sharing(ledger):
    svc, _, game, identity, _ = ready(ledger, public=True)
    decide(svc, identity)
    assert "PRIVATE_CONTRABAND_ITEM" in str(game.sheet(PLAYER))
    for viewer in (ADMIN, OTHER):
        public = game.sheet(viewer, 2)
        assert public["assets"] and "PRIVATE_CONTRABAND_ITEM" not in str(public)
        assert "PRIVATE_ITEM_DESCRIPTION" not in str(public)
    data = svc.get(PLAYER, identity)
    assert data["can_share"]
    with pytest.raises(WorkflowError):
        svc.share(OTHER, "not-my-item", identity, data["actor_sha256"])
    outcome = svc.share(PLAYER, "share-actual-item", identity, data["actor_sha256"])
    assert svc.share(PLAYER, "share-actual-item", identity, data["actor_sha256"]) == outcome
    assert "PRIVATE_CONTRABAND_ITEM" in str(game.sheet(OTHER, 2))
    assert "PRIVATE_OWNER_FIND_ACCOUNT" not in str(game.sheet(OTHER, 2))


def test_source_draw_failure_rolls_back_private_find_and_source_work(ledger, monkeypatch):
    _, effects, game, identity, selector = ready(ledger, apply=False)
    before = state(game)
    original = effects.strain._save

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic source failure")

    monkeypatch.setattr(effects.strain, "_save", fail)
    with pytest.raises(RuntimeError):
        schedule(effects, game, identity)
    assert state(game) == before and effects.get(ADMIN, identity)["state"] == "pending"
    monkeypatch.setattr(effects.strain, "_save", original)
    schedule(effects, game, identity)
    assert selector.calls == 2 and len(state(game).contraband_finds) == 1


def test_claim_event_failure_rolls_back_asset_private_decision_and_command_then_retry(
    ledger, monkeypatch
):
    svc, _, game, identity, selector = ready(ledger)
    before = state(game)
    data = svc.get(PLAYER, identity)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic claim event failure")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        decide(svc, identity, data=data, key="retry-claim")
    assert state(game) == before
    monkeypatch.setattr(game, "event", original)
    decide(svc, identity, data=data, key="retry-claim")
    assert len([x for x in state(game).sheets["2"].assets if x.id == "contraband:" + identity]) == 1
    assert selector.calls == 1


def test_concurrent_same_claim_is_once_and_fresh_stale_claim_does_not_duplicate(ledger):
    svc, _, game, identity, selector = ready(ledger)
    data = svc.get(PLAYER, identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: decide(svc, identity, key="same-claim", data=data), range(2))
        )
    assert results[0] == results[1]
    with pytest.raises(WorkflowError, match="STALE_CONTRABAND"):
        decide(svc, identity, data=data)
    assert (
        selector.calls == 1
        and len([x for x in state(game).sheets["2"].assets if x.id.startswith("contraband:")]) == 1
    )


@pytest.mark.parametrize("field", ("index", "base", "source_event"))
def test_mutated_draw_or_source_cannot_give_another_human_private_access_or_an_asset(ledger, field):
    svc, _, game, identity, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        old = canon.contraband_finds[0]
        canon.contraband_finds[0] = old.model_copy(
            update={field: 1 if field == "index" else "foreign"}
        )
        game.event(c, 1, "synthetic-source-corruption", "synthetic.source", canon)
    viewer = OTHER if field == "index" else PLAYER
    with pytest.raises(WorkflowError, match="SOURCE_CONTRABAND"):
        svc.get(viewer, identity)
    assert not any(x.id.startswith("contraband:") for x in state(game).sheets["3"].assets)


def test_private_backup_rebuild_preserves_draw_concealment_and_owned_history(ledger, tmp_path):
    svc, _, game, identity, selector = ready(ledger, public=True)
    decide(svc, identity)
    expected = state(game)
    destination = tmp_path / "private-contraband-backup.db"
    copy_database(Path(ledger.engine.url.database), destination)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(destination)))
    try:
        store = OnboardingStore(engine, ledger.policy)
        restored_game = GameService(store)
        restored_game.rebuild()
        restored = ContrabandService(restored_game)
        assert state(restored_game) == expected and restored.get(PLAYER, identity)["taken"] is True
        assert restored.get(PLAYER, identity)["concealed"] is True
        assert "PRIVATE_CONTRABAND_ITEM" not in str(restored_game.sheet(ADMIN, 2))
        assert not restored.list(ADMIN) and selector.calls == 1
    finally:
        engine.dispose()


def test_known_absent_girl_cannot_be_teleported_or_excluded_from_random_population(ledger):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_physical import PhysicalService

    _, effects, game, identity, selector = ready(ledger, apply=False)
    physical = PhysicalService(ledger)
    data = physical.preview(PLAYER)
    proposal = physical.propose(
        PLAYER,
        "actual-away-proposal",
        data["game_revision"],
        InitialPlacement(
            actor=ActorRef.model_validate(data["actor"]),
            frame_instance=data["frame_instance"],
            girl_cell=(5, 5),
            frame_cell=(5, 5),
            mode="outside_frame",
            account="Actual original position away from the base",
            facts_confirmed=True,
        ),
    )
    physical.decide(
        ADMIN, "actual-away-review", proposal["id"], 1, "accept", "Original actual facts"
    )
    before = state(game)
    with pytest.raises(WorkflowError, match="cannot move a known absent Girl"):
        schedule(effects, game, identity)
    assert state(game) == before and selector.calls == 0
    assert effects.get(ADMIN, identity)["state"] == "pending"


def test_policy_revocation_and_missing_registry_preserve_private_saved_reads(
    ledger, monkeypatch, tmp_path
):
    svc, _, game, identity, selector = ready(ledger)
    before = state(game)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    assert svc.get(PLAYER, identity)["taken"] is None and len(svc.list(PLAYER)) == 1
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        decide(svc, identity)
    ledger.policy = policy
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing-source-registry.json"))
    assert svc.get(PLAYER, identity)["taken"] is None and len(svc.list(PLAYER)) == 1
    with pytest.raises(WorkflowError, match="source registry is unavailable"):
        decide(svc, identity)
    assert state(game) == before and selector.calls == 1


def test_private_claim_event_and_item_details_never_appear_in_other_members_ledger_or_export(
    ledger,
):
    svc, _, game, identity, _ = ready(ledger, public=True)
    decide(svc, identity)
    ledger_service = CampaignLedger(ledger)
    for viewer in (ADMIN, OTHER):
        assert not any(
            x["kind"] == "m3.contraband_decided" for x in ledger_service.list_events(viewer)
        )
        assert "PRIVATE_CONTRABAND_ITEM" not in str(game.sheet(viewer, 2))
    exported = json.dumps(ledger_service.public_export())
    assert "PRIVATE_CONTRABAND" not in exported and "PRIVATE_OWNER_FIND_ACCOUNT" not in exported


def test_changed_character_cannot_inherit_original_find_and_saved_history_remains_owned(ledger):
    svc, _, game, identity, _ = ready(ledger)
    with ledger.transaction() as c:
        c.execute(
            t.characters.update()
            .where(t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2")
            .values(id=str(uuid4()))
        )
    assert not svc.get(PLAYER, identity)["eligible"]
    with pytest.raises(WorkflowError):
        decide(svc, identity)
    assert state(game).contraband_finds[0].taken is None


def test_second_uniform_index_selects_the_other_actual_girl_and_only_updates_her_sheet(ledger):
    svc, _, game, identity, selector = ready(ledger, index=1)
    before = state(game)
    assert not svc.list(PLAYER) and svc.list(OTHER)[0]["id"] == identity
    decide(svc, identity, viewer=OTHER)
    after = state(game)
    assert after.sheets["2"] == before.sheets["2"]
    assert len(after.sheets["3"].assets) == len(before.sheets["3"].assets) + 1
    assert after.contraband_finds[0].actor.entity == "3" and selector.calls == 1


def test_same_human_in_another_campaign_cannot_read_or_claim_the_original_private_find(ledger):
    from girlframe.services.read_only_bot import GuildViewer

    svc, _, game, identity, selector = ready(ledger)
    original = svc.get(PLAYER, identity)
    foreign = str(uuid4())
    with ledger.transaction() as c:
        c.execute(t.campaigns.insert().values(id=foreign, guild_id="999", revision=0))
        c.execute(
            t.members.insert().values(campaign_id=foreign, user_id="2", role="player", active=True)
        )
    policy = ledger.policy.model_copy(update={"campaign_id": foreign, "guild_id": 999})
    other = ContrabandService(GameService(OnboardingStore(ledger.engine, policy)))
    viewer = GuildViewer(2, 999, True, True)
    assert other.list(viewer) == []
    with pytest.raises(WorkflowError, match="original recipient"):
        other.get(viewer, identity)
    with pytest.raises(WorkflowError, match="original recipient"):
        decide(other, identity, viewer=viewer, data=original)
    assert state(game).contraband_finds[0].taken is None and selector.calls == 1
