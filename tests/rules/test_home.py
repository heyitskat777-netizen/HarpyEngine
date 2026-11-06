"""Actual secret installation, physical shared cockpit, Bond and source-owned Tag effects."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_privileges import change
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_home import open_effect, open_home
from girlframe.engine import m3_home as rules
from girlframe.engine.m2 import Obligation, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_access import Access
from girlframe.services.m3_home import HomeService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ITEMS = ("book", "cards", "bottle")


def ready(store, tmp_path, monkeypatch, frame="WYVERN 0.4"):
    missions, game = service(store, frame=frame)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            ),
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={
                    "beneath_private_choices": "affected_owner",
                    "privilege_restoration": "inflictor_condition_owner_restores",
                }
            ),
        }
    )
    world = initial()
    missions.access = Access(store)
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting",
                account="Actual existing body and Frame",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN, str(uuid4()), proposed["id"], 1, "accept", "Actual original physical facts"
        )
    with store.transaction() as c:
        actual = state(game)
        actor = current_ref(actual, 2)
        other = current_ref(actual, 3)
        actual = set_depth(actual, actor, other, 0, str(uuid4()))
        actual.sheets["2"].permissions = 6
        actual.order = (3, 2)
        actual.sheets["2"].tags.append(
            TagState(
                id="actual-tag",
                label="An actual unwanted Tag",
                giver=3,
                giver_actor=other,
                giver_character=other.incarnation,
                observers=(2, 3),
                marked=True,
                rejection_pending=True,
            )
        )
        actual.obligations.append(
            Obligation(
                id="actual-rejection",
                kind="reject_tag",
                owner=2,
                action="actual-prior-tag",
                details={"tag": "actual-tag"},
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_home_resources", actual)
    return game, HomeService(game)


def rescue_guest(game):
    """Real last-Asset damage and owned Defeat rescue create actual cockpit occupancy."""
    with game.store.transaction() as c:
        actual = state(game)
        frames = [x for x in actual.sheets["3"].assets if x.family == "frame"]
        for asset in frames[1:]:
            asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_guest_damage", actual)
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (1, 1)
    parent = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            piloting=True,
            context="Actual confrontation in my own Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "beneath_select", options=("damage",), text="Actual counterattack")
    answer(game, OTHER, "beneath_details", denied=(frames[0].id,))
    game.dice.faces = (3, 3)
    defeat = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            context="Actual source Defeat",
            trigger_confirmed=True,
            parent=parent,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "defeat_select",
        options=("pilot_rescue_deepen_bond",),
        fields={"rescuer": "2"},
        text="The actual other Pilot rescues me into her present cockpit",
    )
    assert game.inspect(OTHER, defeat)["state"] == "complete"
    tick(worker, gateway, 5)
    return worker, gateway


def test_native_home_secret_purchase_actual_rescue_shared_cockpit_bond_tag_and_restore(
    ledger, tmp_path, monkeypatch
):
    game, home = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    data = home.menu(PLAYER)
    actor = ActorRef.model_validate(data["actor"])
    assert data["price"] == 2 and not data["others"]
    with pytest.raises(ValueError, match="exactly three"):
        home.buy(
            PLAYER,
            str(uuid4()),
            data["revision"],
            actor,
            data["frame"],
            ("book", "book", "cards"),
            "No duplicate secret",
        )
    assert state(game) == before

    async def acquire():
        own = current(2, 994101)
        await own.response.defer(ephemeral=True)
        await open_home(own, home)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "2 Permissions" in form.text()
        form.values.update(items=ITEMS, account="PRIVATE_HOME_INSTALLATION_ACCOUNT")
        await form.confirm.callback(current(2, 994102))
        assert form.completed

    asyncio.run(acquire())
    actual = state(game)
    paid = rules.held(actual, actor)
    assert paid and paid.price == 2 and paid.kind == "ability_unlock"
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    assert home.buy(
        PLAYER,
        "994102",
        data["revision"],
        actor,
        data["frame"],
        ITEMS,
        "PRIVATE_HOME_INSTALLATION_ACCOUNT",
    ) == {"id": paid.id, "cost": 2}
    assert home.menu(OTHER)["items"] == []
    assert not home.menu(PLAYER)["others"]  # Same map cell in separate Frames is insufficient.
    with pytest.raises(ValueError, match="exact owned Frame"):
        with ledger.engine.connect() as c:
            from girlframe.services.m3_actors import profiles

            rules.together(actual, actor, current_ref(actual, 3), profiles(c, ledger.campaign_id))
    worker, gateway = rescue_guest(game)
    actual = state(game)
    other = current_ref(actual, 3)
    assert depth(actual, actor, other) == 1 and home.menu(PLAYER)["others"]

    # Genuine superior-owned discipline withdraws this exact installation while both remain aboard.
    game.dice.faces = (6, 6)
    social = game.begin(
        OTHER,
        str(uuid4()),
        900,
        actual.sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual discipline while we share the cockpit",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "punish"),
        fields={"tag": "Actual discipline"},
        text="Actual discipline",
    )
    work = game.decision(OTHER, game.choices(OTHER)[0]["id"])["body"]["work_id"]
    discipline = PunishmentService(ledger)
    view = discipline.get(OTHER, work)
    discipline.apply(
        OTHER,
        str(uuid4()),
        work,
        view["revision"],
        view["game_revision"],
        Details(
            kind="revoked_privileges", requisition=paid.id, restoration="Actual owner condition"
        ),
    )
    assert game.inspect(OTHER, social)["state"] == "complete"
    tick(worker, gateway, 5)
    removed = state(game)
    view = home.menu(PLAYER)
    assert view["suspended"] and view["items"] == list(ITEMS) and not view["others"]
    with pytest.raises(WorkflowError, match="Restore your original paid Home"):
        home.use(
            PLAYER,
            str(uuid4()),
            removed.revision,
            other,
            "wrong-proof",
            operation="bond",
            account="Cannot use suspended source",
            item="book",
        )
    assert state(game) == removed
    gate = next(x for x in removed.obligations if x.kind == "revoked_requisition")
    restore = PrivilegeService(ledger)
    change(restore, OTHER, gate.id, allow=True)
    change(restore, PLAYER, gate.id, allow=False)
    assert rules.held(state(game), actor) == paid and home.menu(PLAYER)["items"] == list(ITEMS)

    async def deepen_native():
        own = current(2, 994103)
        await own.response.defer(ephemeral=True)
        await open_effect(own, home, "bond")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            other=("3",), item=("book",), account="We share a story from my installed book"
        )
        await form.confirm.callback(current(2, 994104))
        assert form.completed

    calls = game.dice.calls
    asyncio.run(deepen_native())
    assert depth(state(game), actor, other) == 2
    view = home.menu(PLAYER)
    co = view["others"][0]
    before = state(game)
    args = (PLAYER, "actual-intense-overflow", view["revision"], other, co["physical"])
    result = home.use(
        *args, operation="bond", account="We play another round together", item="cards"
    )
    assert (
        home.use(*args, operation="bond", account="We play another round together", item="cards")
        == result
    )
    for uid in ("2", "3"):
        assert state(game).sheets[uid].heat == before.sheets[uid].heat + 2
    # Home removes the action requirement, while the original setter's real lock remains.
    game.dice.faces = (6, 6)
    locked = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual original setter locks her Tag",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "lock_tag"),
        fields={"tag": "Actual lock scene", "locked_tag": "actual-tag"},
        text="The original setter locks her own actual Tag",
    )
    assert game.inspect(OTHER, locked)["state"] == "complete"
    tick(worker, gateway, 5)
    view = home.menu(PLAYER)
    co = view["others"][0]
    denied = state(game)
    with pytest.raises(WorkflowError, match="ORIGINAL_LOCKER_CONSENT_REQUIRED"):
        home.use(
            PLAYER,
            str(uuid4()),
            view["revision"],
            other,
            co["physical"],
            operation="reject",
            account="Home cannot waive actual consent",
            tag="actual-tag",
        )
    assert state(game) == denied
    permission = next(x for x in denied.obligations if x.kind == "tag_rejection_permission")
    permissions = PermissionService(ledger)
    consent = permissions.get(OTHER, permission.id)
    with pytest.raises(WorkflowError, match="original locker"):
        permissions.grant(PLAYER, str(uuid4()), permission.id, consent["source_sha256"], True)
    permissions.grant(OTHER, str(uuid4()), permission.id, consent["source_sha256"], True)
    # The existing Newgirl Mentor restriction also survives this new direct rejection port.
    mentor = state(game).model_copy(deep=True)
    mentor.sheets["2"].girl = "NEWGIRL"
    mentor.sheets["2"].mentor = 3
    original_tag = next(x for x in mentor.sheets["2"].tags if x.id == "actual-tag")
    assert not rules.rejectable(mentor, actor, original_tag)
    calls = game.dice.calls
    view = home.menu(PLAYER)
    co = view["others"][0]
    args = (PLAYER, "actual-home-rejection", view["revision"], other, co["physical"])
    result = home.use(
        *args,
        operation="reject",
        account="The old description does not define me",
        tag="actual-tag",
    )
    assert (
        home.use(
            *args,
            operation="reject",
            account="The old description does not define me",
            tag="actual-tag",
        )
        == result
    )
    final = state(game)
    assert not any(x.id == "actual-tag" for x in final.sheets["2"].tags)
    assert next(x for x in final.obligations if x.id == "actual-rejection").state == "fulfilled"
    assert game.dice.calls == calls and final.sheets["2"].permissions == 4
    assert final.placements == before.placements and final.requisitions == removed.requisitions
    assert all(dict(rules.ITEMS)[item] not in str(game.sheet(OTHER, 2)) for item in ITEMS)
    with ledger.engine.connect() as c:
        visible = str(list(c.scalars(sa.select(t.events.c.payload_json)))) + str(
            list(c.scalars(sa.select(t.m2["m2_outbox"].c.body_json)))
        )
        assert "PRIVATE_HOME_INSTALLATION_ACCOUNT" not in visible
        assert all(dict(rules.ITEMS)[item] not in visible for item in ITEMS)


def test_grafted_home_requires_real_legion_donor_and_preserves_secrets_source(
    ledger, tmp_path, monkeypatch
):
    game, home = ready(ledger, tmp_path, monkeypatch, frame="CONSUME")
    data = home.menu(PLAYER)
    actor = ActorRef.model_validate(data["actor"])
    before = state(game)
    assert data["kind"] == "frame_grafting" and data["price"] == 3
    with pytest.raises(ValueError, match="eligible Class donor"):
        home.buy(
            PLAYER, str(uuid4()), data["revision"], actor, data["frame"], ITEMS, "Actual graft"
        )
    assert state(game) == before
    args = (
        PLAYER,
        "actual-home-graft",
        data["revision"],
        actor,
        data["frame"],
        ITEMS,
        "Actual graft",
        "WYVERN 0.4",
    )
    result = home.buy(*args)
    assert home.buy(*args) == result
    actual = state(game)
    paid = rules.held(actual, actor)
    assert (
        paid
        and paid.kind == "frame_grafting"
        and paid.price == 3
        and paid.donor_frame == "WYVERN 0.4"
    )
    assert (
        actual.sheets["2"].permissions == 3
        and actual.sheets["2"].assets == before.sheets["2"].assets
    )
    corrupted = actual.model_copy(deep=True)
    fact = next(x for x in corrupted.facts if x.get("kind") == "home_installation")
    installed = rules.installed(corrupted, paid)
    fact["body"] = installed.model_copy(
        update={"items": ("movie", "cards", "bottle")}
    ).model_dump_json()
    with (
        ledger.engine.connect() as c,
        pytest.raises(WorkflowError, match="original source-bound secret"),
    ):
        home._source(c, corrupted, paid)
