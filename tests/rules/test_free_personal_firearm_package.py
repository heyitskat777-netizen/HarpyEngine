"""Actual quoted free package, owned capacity choice, immutable source and later benefits."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_replacement import supplied
from test_replacement_service import pending, propose, quote

from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_personal_firearm import RULE
from girlframe.services.m3_personal_firearm import proof
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch, *, full=False, all_void=False):
    replacement, game, _, work = pending(store)
    acquisition = approved(store, game, tmp_path, monkeypatch)
    replacement.missions.access.registry = acquisition.registry
    if full:
        with store.transaction() as c:
            canon = state(game)
            canon.sheets["2"].assets = [
                x for x in canon.sheets["2"].assets if x.family != "girl"
            ] + [
                AssetState(
                    id=f"original-girl-{i}",
                    family="girl",
                    name=f"Actual original {i}",
                    description="Existing original Girl Asset",
                    void=all_void,
                )
                for i in range(4)
            ]
            game.event(c, 1, str(uuid4()), "synthetic.established_original_girl_assets", canon)
    proposed = propose(replacement, work)
    quote(replacement, proposed["package_id"], supplied(additional_rules=(RULE,)))
    return replacement, game, work


def arguments(service, work):
    current = service.get(PLAYER, work)
    return work, current["revision"], current["game_revision"], current["package_revision"]


def test_real_owner_free_package_issues_once_preserves_resources_and_proves_original_source(
    ledger, tmp_path, monkeypatch
):
    service, game, work = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    args = arguments(service, work)
    with pytest.raises(WorkflowError):
        service.apply(OTHER, "wrong-owner", *args)
    assert state(game).model_dump_json() == before.model_dump_json()
    result = service.apply(PLAYER, "owned-real-free-issue", *args)
    assert service.apply(PLAYER, "owned-real-free-issue", *args) == result
    actual = state(game)
    assert len(actual.personal_firearms) == 1
    grant = actual.personal_firearms[0]
    assert grant.source_work == work and grant.purchase is None
    assert len(grant.issues) == 1
    pistol = next(x for x in actual.sheets["2"].assets if x.id == grant.issues[0].asset)
    assert pistol.family == "girl" and not pistol.damaged and not pistol.void
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions
    assert actual.sheets["2"].identities == before.sheets["2"].identities
    assert actual.sheets["2"].heat == before.sheets["2"].heat
    with ledger.engine.connect() as c:
        proof(c, ledger, grant)
        with pytest.raises(WorkflowError):
            proof(c, ledger, grant.model_copy(update={"source_work": "not-the-owned-package"}))


def test_capacity_choice_is_original_owners_real_asset_and_failure_is_atomic(
    ledger, tmp_path, monkeypatch
):
    service, game, work = ready(ledger, tmp_path, monkeypatch, full=True)
    args = arguments(service, work)
    before = state(game).model_dump_json()
    for key, choice in (("missing", None), ("wrong", "not-an-owned-girl")):
        with pytest.raises(WorkflowError):
            service.apply(PLAYER, key, *args, firearm_replace=choice)
        assert state(game).model_dump_json() == before
    service.apply(PLAYER, "actual-owner-cap-choice", *args, firearm_replace="original-girl-1")
    actual = state(game)
    grant = actual.personal_firearms[-1]
    assert grant.issues[0].replaces_asset == "original-girl-1"
    assert len([x for x in actual.sheets["2"].assets if x.family == "girl"]) == 4
    assert not any(x.id == "original-girl-1" for x in actual.sheets["2"].assets)
    with ledger.engine.connect() as c:
        proof(c, ledger, grant)


def test_full_void_girl_cannot_replace_void_or_silently_get_free_extra_slot(
    ledger, tmp_path, monkeypatch
):
    service, game, work = ready(ledger, tmp_path, monkeypatch, full=True, all_void=True)
    data = service.get(PLAYER, work)
    assert data["firearm"]["needs_replacement"] and not data["firearm"]["replacements"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.apply(
            PLAYER,
            "no-void-replacement",
            *arguments(service, work),
            firearm_replace="original-girl-0",
        )
    assert state(game).model_dump_json() == before


def test_failed_final_work_write_rolls_back_pistol_profile_sync_and_source_then_retries_once(
    ledger, tmp_path, monkeypatch
):
    import sqlalchemy as sa

    from girlframe.database import tables as t

    service, game, work = ready(ledger, tmp_path, monkeypatch, full=True)
    args = arguments(service, work)
    before = state(game).model_dump_json()

    def snapshot():
        with ledger.engine.connect() as c:
            return {
                table.name: [dict(row) for row in c.execute(sa.select(table)).mappings()]
                for table in (
                    t.characters,
                    t.character_sync,
                    t.events,
                    t.m2["m2_state_history"],
                    t.m3["m3_required_work"],
                )
            }

    saved = snapshot()
    original = service._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic final replacement work failure after actual issue")

    monkeypatch.setattr(service, "_save", fail)
    with pytest.raises(RuntimeError):
        service.apply(PLAYER, "retry-real-free-pf", *args, firearm_replace="original-girl-1")
    assert state(game).model_dump_json() == before and snapshot() == saved
    monkeypatch.setattr(service, "_save", original)
    service.apply(PLAYER, "retry-real-free-pf", *args, firearm_replace="original-girl-1")
    assert len(state(game).personal_firearms) == 1


def test_native_cap_confirmation_belongs_to_original_owner_and_stale_quote_does_not_issue(
    ledger, tmp_path, monkeypatch
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_replacement import PackageReview

    service, game, work = ready(ledger, tmp_path, monkeypatch, full=True)

    async def run():
        review = PackageReview(2, service, service.get(PLAYER, work))
        assert not await review.interaction_check(current(3))
        owner = current(2, 97201)
        await owner.response.defer(ephemeral=True)
        await review.confirm.callback(owner)
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not state(game).personal_firearms and state(game).sheets["2"].frame_scrapped
        assert not await form.interaction_check(current(3))
        form.values = {"replace": ("original-girl-1",)}
        await form.confirm.callback(current(2, 97202))
        assert form.completed
        assert len(state(game).personal_firearms) == 1
        assert state(game).personal_firearms[-1].issues[0].replaces_asset == "original-girl-1"

    asyncio.run(run())


def test_stale_free_package_revision_cannot_issue_old_pistol_or_spend_capacity(
    ledger, tmp_path, monkeypatch
):
    service, game, work = ready(ledger, tmp_path, monkeypatch, full=True)
    args = arguments(service, work)
    package = service.get(PLAYER, work)["package_id"]
    quote(service, package, supplied(additional_rules=(RULE,)), key="new-real-quote")
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.apply(PLAYER, "stale-real-free-issue", *args, firearm_replace="original-girl-1")
    assert state(game).model_dump_json() == before and not state(game).personal_firearms


def test_old_paid_grant_serialization_and_saved_source_rebuild_keep_exact_bytes(
    ledger, tmp_path, monkeypatch
):
    import hashlib

    from test_personal_firearm_service import purchase, setup

    from girlframe.engine.m2 import GameState

    firearm, _, game, _ = setup(ledger, tmp_path, monkeypatch)
    purchase(firearm)
    actual = state(game)
    raw = actual.model_dump_json()
    assert "source_work" not in actual.personal_firearms[0].model_dump_json()
    assert GameState.model_validate_json(raw).model_dump_json() == raw
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    game.rebuild()
    assert hashlib.sha256(state(game).model_dump_json().encode()).hexdigest() == fingerprint
    with ledger.engine.connect() as c:
        proof(c, ledger, state(game).personal_firearms[0])


def finish_source_mission(service, game):
    from test_ledger import ADMIN

    from girlframe.engine.m3_punishments import Details
    from girlframe.services.m3_punishments import PunishmentService

    # The Doctor's real failed mission is settled through its actual Punishments;
    # completing the replacement never waives these independent source causes.
    mission = service.missions.list(ADMIN)[0]
    service.missions.complete(ADMIN, str(uuid4()), mission["id"], mission["revision"])
    for work in service.missions.get(ADMIN, mission["id"])["work"]:
        if work["kind"] != "punishment":
            continue
        discipline = PunishmentService(service.store, service.missions.access.registry)
        data = discipline.get(ADMIN, work["id"])
        discipline.apply(
            ADMIN,
            str(uuid4()),
            work["id"],
            data["revision"],
            data["game_revision"],
            Details(kind="stimulant_injection"),
        )
    current = service.missions.get(ADMIN, mission["id"])
    service.missions.complete(ADMIN, str(uuid4()), mission["id"], current["mission"]["revision"])
    assert service.missions.get(ADMIN, mission["id"])["pending_count"] == 0


def test_actual_free_source_lost_pistol_real_eight_roll_owned_reissue_preserves_free_entitlement(
    ledger, tmp_path, monkeypatch
):
    import test_strain_effect_service
    from test_ledger import ADMIN
    from test_off_duty_cycle import activate, prepared, roll_for
    from test_personal_firearm_service import lose, sync
    from test_strain_service import D6

    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_personal_firearm import PersonalFirearmService
    from girlframe.services.m3_strain import StrainService

    replacement, game, work = ready(ledger, tmp_path, monkeypatch)
    replacement.apply(PLAYER, "actual-free-initial-issue", *arguments(replacement, work))
    finish_source_mission(replacement, game)
    firearm = PersonalFirearmService(game, replacement.missions.access.registry)
    lose(firearm)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "world", "plays", "economy"}}
            )
        }
    )
    strain = StrainService(OffDutyService(replacement.missions), dice=D6(1))
    # Reuse the existing full real Strain/owned-effects fixture against this SAME
    # source campaign, replacing only its test constructor (never a production effect).
    monkeypatch.setattr(test_strain_effect_service, "ready", lambda *args, **kwargs: (strain, game))
    cycle, same_game, period = prepared(ledger)
    assert same_game is game
    activate(cycle, game, period)
    action = roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(firearm, period)
    task = firearm.return_tasks(PLAYER)[0]
    data = firearm.return_get(PLAYER, task["id"])
    assert data["total"] == 8
    before = state(game)
    result = firearm.claim(
        PLAYER,
        "free-source-real-return",
        task["id"],
        data["revision"],
        take=True,
        account="Actual Foundation replacement after loss",
        expected=data["expected"],
    )
    assert (
        firearm.claim(
            PLAYER,
            "free-source-real-return",
            task["id"],
            data["revision"],
            take=True,
            account="Actual Foundation replacement after loss",
            expected=data["expected"],
        )
        == result
    )
    actual = state(game)
    grant = actual.personal_firearms[0]
    assert grant.source_work == work and grant.purchase is None and len(grant.issues) == 2
    assert grant.issues[0].asset != grant.issues[1].asset
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions
    assert game.inspect(PLAYER, action)["receipt"]["faces"] == [2, 2]
    with ledger.engine.connect() as c:
        proof(c, ledger, grant)
    assert not firearm.return_tasks(ADMIN)


def test_actual_free_package_grant_survives_paid_selected_retention_without_second_issue(
    ledger, tmp_path, monkeypatch
):
    from test_frame_swap import selection, synthetic_registry
    from test_frame_swap_service import configured, pay
    from test_ledger import ADMIN
    from test_world import initial

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_physical import initial as place
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.services.m3_access import digest
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_frame_swap import FrameSwapService

    replacement, game, work = ready(ledger, tmp_path, monkeypatch)
    replacement.apply(PLAYER, "free-original-frame-and-pistol", *arguments(replacement, work))
    finish_source_mission(replacement, game)
    registry = synthetic_registry()
    path = tmp_path / "synthetic-source-reviewed-free-retention.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={"m3_approval": approval.model_copy(update={"registry_sha256": digest(registry)})}
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon.sheets["2"].permissions = 10
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        canon = place(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=canon.sheets["2"].frame_runtime.id,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="Actual original body beside delivered new Frame",
                facts_confirmed=True,
            ),
            "actual-free-source-body",
            "actual-initial-placement",
            "Actual known position",
        )
        game.event(c, ADMIN.user_id, str(uuid4()), "synthetic.existing_funds_position", canon)
    swap = FrameSwapService(game, registry)
    identity = configured(swap, game, "JANUS-B")
    assert selection(state(game), "JANUS-B").retained_rule == RULE
    before = state(game)
    pay(swap, identity)
    actual = state(game)
    grant = actual.personal_firearms[0]
    assert actual.sheets["2"].frame == "JANUS-B"
    assert actual.sheets["2"].permissions == before.sheets["2"].permissions - 4
    assert grant.source_work == work and grant.purchase is None
    assert grant.frame_instance != before.personal_firearms[0].frame_instance
    assert grant.issues == before.personal_firearms[0].issues and len(grant.issues) == 1
    assert len(actual.personal_firearms) == 1
    with ledger.engine.connect() as c:
        proof(c, ledger, grant)
    game.rebuild()
    assert state(game).model_dump_json() == actual.model_dump_json()
