"""Actual paid Snoop, private source answers and one original physical-effect event."""

from uuid import uuid4

from test_enforcement_initiative import ready
from test_enforcer_requisitions import approved, buy
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_enforcer_requisitions import SNOOP
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_enforcer_snoop import prepare, preview
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService

ledger = ledger_fixture


def test_source_prepare_allows_actual_absent_owner_without_casting_or_moving_them(
    ledger, tmp_path, monkeypatch
):
    game, _, _ = ready(ledger, tmp_path, monkeypatch)
    service = approved(ledger, game, tmp_path, monkeypatch)
    buy(service, SNOOP)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    casts = CastService(ActorService(MissionService(ledger)))
    source = casts.view(OTHER, 900)
    target = current_ref(state(game), 3)
    casts.change(
        OTHER,
        str(uuid4()),
        900,
        source["game_revision"],
        source["cast_revision"],
        "withdraw",
        target,
    )
    before = state(game)
    value = PlayInput(
        play="snoop",
        heat=0,
        target_actor=target,
        context="Actual target-owned property stored here; target body absent",
        trigger_confirmed=True,
    )
    with ledger.engine.connect() as c:
        meta = prepare(game, c, PLAYER, value, before, channel=900)
    assert meta["target_controller"] == 3 and 3 not in meta["table"]
    assert target.model_dump(mode="json") not in [x["actor"] for x in meta["cast"]["roles"]]
    assert state(game).model_dump_json() == before.model_dump_json() and game.dice.calls == 0
    assert any(
        x["ref"] == target.model_dump(mode="json") for x in preview(game, PLAYER, 900)["targets"]
    )


def rolled(store, tmp_path, monkeypatch, faces=(4, 5), before_roll=None, target=None):
    game, worker, gateway = ready(store, tmp_path, monkeypatch, faces)
    service = approved(store, game, tmp_path, monkeypatch)
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", canon)
    buy(service, SNOOP)
    if before_roll:
        before_roll(game)
    canon = state(game)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        canon.sheets["2"].revision,
        PlayInput(
            play="snoop",
            heat=0,
            target_actor=target or current_ref(canon, 3),
            trigger_confirmed=True,
            context="Actual accessible stored property in this scene; owner need not be present",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    return game, worker, gateway, identity


def ordinary(game, question, name):
    answer(
        game,
        OTHER,
        "snoop_answer",
        text="Private actual printed finding",
        fields=dict(name=name, description="Existing ordinary property stored in this actual room"),
    )
    answer(
        game,
        ADMIN,
        "snoop_object_fact",
        flag=True,
        text="Actual object already exists and is accessible in this source room",
    )


def test_mid_real_bond_private_finding_and_actual_ordinary_object_transfer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, identity = rolled(ledger, tmp_path, monkeypatch)
    original = state(game)
    answer(game, PLAYER, "snoop_select", options=("valuable", "rebel_evidence"))
    assert depth(state(game), current_ref(original, 2), current_ref(original, 3)) == min(
        2, depth(original, current_ref(original, 2), current_ref(original, 3)) + 1
    )
    ordinary(game, "valuable", "Actual stored keepsake")
    answer(game, OTHER, "snoop_answer", text="PRIVATE_REBEL_FINDING")
    answer(game, PLAYER, "snoop_capacity")
    if any(x["kind"] == "snoop_body_context" for x in game.choices(OTHER)):
        answer(
            game,
            OTHER,
            "snoop_body_context",
            flag=False,
            text="Actual original body outside its cockpit, location stays unknown",
        )
    actual = state(game)
    item = next(x for x in actual.held_items if x.name == "Actual stored keepsake")
    assert item.holder == current_ref(original, 2) and item.location_mode == "carried"
    assert item.source_owner == current_ref(original, 3) and item.asset_json is None
    assert actual.placements == original.placements
    with ledger.engine.connect() as c:
        assert prove_item(c, game, actual, item.id) == item
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_low_requires_missed_answer_and_does_not_deepen_bond(ledger, tmp_path, monkeypatch):
    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (1, 1))
    original = state(game)
    answer(game, PLAYER, "snoop_select", options=("illegal",))
    answer(game, OTHER, "snoop_answer", text="PRIVATE_ILLEGAL_FINDING")
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(game, OTHER, "snoop_answer", text="PRIVATE_GLAD_MISSED")
    actual = state(game)
    assert actual.actor_bonds == original.actor_bonds
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_high_ordinary_personal_property_is_really_ruined_not_mechanical_or_mid_bond(
    ledger, tmp_path, monkeypatch
):
    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (6, 6))
    original = state(game)
    answer(game, PLAYER, "snoop_select", options=("personal",))
    ordinary(game, "personal", "Actual ordinary personal letter")
    answer(
        game, ADMIN, "snoop_relevance", text="No mechanical Assets actually relevant in this room"
    )
    if any(x["kind"] == "snoop_body_context" for x in game.choices(OTHER)):
        answer(
            game,
            OTHER,
            "snoop_body_context",
            flag=False,
            text="Actual original body outside its cockpit, location stays unknown",
        )
    actual = state(game)
    item = next(x for x in actual.held_items if x.name == "Actual ordinary personal letter")
    assert (
        item.condition == "ruined"
        and item.asset_json is None
        and item.holder == current_ref(original, 3)
    )
    assert item.state_event and item.state_event != item.source_event
    assert actual.actor_bonds == original.actor_bonds
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_high_all_relevant_vacant_frame_assets_damage_without_remote_owner_defeat(
    ledger, tmp_path, monkeypatch
):
    from test_physical_operations import place

    from girlframe.engine.m3_actor_state import ActorRef

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (6, 6))
    service = approved(ledger, game, tmp_path, monkeypatch)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].permissions = 3
        canon = place(canon, 3, mode="outside_frame", cell=(0, 0))
        canon = place(canon, 2, mode="outside_frame", cell=(1, 0), frame_cell=(0, 0))
        game.event(c, 1, str(uuid4()), "synthetic.actual_vacant_frame_positions", canon)
    view = service.acquisition_view(OTHER, "frame_grafting")
    service.buy_rule(
        OTHER,
        str(uuid4()),
        ActorRef.model_validate(view["actor"]),
        view["source_sha256"],
        "frame_grafting",
        SNOOP,
        "Actual original paid graft",
    )
    before = state(game)
    owner = current_ref(before, 2)
    identity = game.begin(
        OTHER,
        str(uuid4()),
        900,
        before.sheets["3"].revision,
        PlayInput(
            play="snoop",
            heat=0,
            target_actor=owner,
            trigger_confirmed=True,
            context="Actual owner-absent equipment room; original Frame parked here",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "snoop_select", options=("illegal",))
    answer(game, PLAYER, "snoop_answer", text="Actual private illegal property finding")
    relevant = tuple(x.id for x in before.sheets["2"].assets if x.family == "frame")
    assert relevant
    answer(
        game,
        ADMIN,
        "snoop_relevance",
        options=relevant,
        text="Every actual Frame Asset here is relevant; original Girl is elsewhere",
    )
    after = state(game)
    assert all(x.damaged for x in after.sheets["2"].assets if x.family == "frame")
    assert after.placements == before.placements
    assert after.sheets["2"].frame_runtime == before.sheets["2"].frame_runtime
    assert not any(x["kind"] == "snoop_damage_consequence" for x in game.choices(PLAYER))
    assert game.inspect(OTHER, identity)["state"] == "complete" and game.dice.calls == 1


def test_real_mechanical_theft_settles_actual_mockingbird_threshold_without_fake_ack(
    ledger, tmp_path, monkeypatch
):
    from test_items import carried_asset

    chosen = {}

    def prepare_item(game):
        with ledger.transaction() as c:
            canon = state(game)
            girls = [x for x in canon.sheets["3"].assets if x.family == "girl"]
            item = next(x for x in girls if not x.void)
            chosen["asset"] = item.id
            for other in girls:
                other.void = other.id != item.id
            game.event(c, 3, str(uuid4()), "synthetic.actual_prior_girl_corruption", canon)
        carried_asset(game, OTHER, item)

    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, before_roll=prepare_item)
    original = state(game)
    owner = current_ref(original, 3)
    answer(game, PLAYER, "snoop_select", options=("valuable",))
    answer(
        game,
        OTHER,
        "snoop_answer",
        text="Actual carried detachable original equipment",
        fields=dict(item="asset:" + chosen["asset"]),
    )
    answer(game, PLAYER, "snoop_capacity")
    answer(
        game,
        OTHER,
        "snoop_body_context",
        flag=False,
        text="Actual body outside its cockpit; no body movement",
    )
    actual = state(game)
    assert chosen["asset"] not in {x.id for x in actual.sheets["3"].assets}
    transfer = actual.item_transfers[-1]
    assert transfer.source_kind == "enforcer_snoop" and transfer.source == owner
    assert transfer.recipient == current_ref(original, 2)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    pending = next(x for x in game.choices(OTHER) if x["kind"] == "snoop_item_void_threshold")
    work = game.decision(OTHER, pending["id"])["body"]["work_id"]
    from test_void_service import respond

    from girlframe.services.m3_void import VoidService

    void = VoidService(ledger)
    respond(
        void,
        work,
        "propose_occupancy",
        dict(mode="outside_frame", account="Actual original target outside its cockpit"),
        viewer=OTHER,
    )
    respond(
        void,
        work,
        "confirm_occupancy",
        dict(account="Actual original physical facts independently confirmed; no travel"),
        viewer=ADMIN,
    )
    actual = state(game)
    assert any(x.actor == owner and x.stage == "prevented" for x in actual.void_thresholds)
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_absent_owner_real_private_native_response_replay_and_rebuild(
    ledger, tmp_path, monkeypatch
):
    import asyncio
    import json

    import pytest
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_enforcer_snoop import open_snoop
    from girlframe.engine.m2 import ChoiceAnswer
    from girlframe.services.onboarding import WorkflowError

    def absent(game):
        ledger.policy = ledger.policy.model_copy(
            update={
                "m3_approval": ledger.policy.m3_approval.model_copy(
                    update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
                )
            }
        )
        casts = CastService(ActorService(MissionService(ledger)))
        data = casts.view(OTHER, 900)
        casts.change(
            OTHER,
            str(uuid4()),
            900,
            data["game_revision"],
            data["cast_revision"],
            "withdraw",
            current_ref(state(game), 3),
        )

    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, (1, 1), before_roll=absent)
    answer(game, PLAYER, "snoop_select", options=("rebel_evidence",))
    request = next(x for x in game.choices(OTHER) if x["kind"] == "snoop_answer")

    async def native():
        interaction = current(3, 909030)
        await interaction.response.defer(ephemeral=True)
        await open_snoop(interaction, game, request["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2, 909031))
        assert "answer" in {x.key for x in form.fields}

    asyncio.run(native())
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            request["id"],
            request["revision"],
            ChoiceAnswer(text="Not target's response"),
        )
    assert state(game) == before
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_enforcer_requisitions import MASTER
    from girlframe.services.m3_enforcer_requisitions import EnforcerRequisitionService

    buying = EnforcerRequisitionService(game)
    buy_view = buying.acquisition_view(OTHER, "frame_grafting")
    with pytest.raises(WorkflowError):
        buying.buy_rule(
            OTHER,
            str(uuid4()),
            ActorRef.model_validate(buy_view["actor"]),
            buy_view["source_sha256"],
            "frame_grafting",
            MASTER,
            "Cannot swap/acquire during original Snoop source",
        )
    assert state(game) == before
    ledger.safety(OTHER, str(uuid4()), ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            request["id"],
            request["revision"],
            ChoiceAnswer(text="Paused original answer"),
        )
    assert state(game) == before
    ledger.safety(OTHER, str(uuid4()), ledger.status(OTHER)["revision"], pause=False)
    key = str(uuid4())
    response = ChoiceAnswer(text="PRIVATE_ABSENT_OWNER_REBEL_FINDING")
    first = game.respond(OTHER, key, request["id"], request["revision"], response)
    assert game.respond(OTHER, key, request["id"], request["revision"], response) == first
    answer(game, OTHER, "snoop_answer", text="PRIVATE_ABSENT_OWNER_MISSED_FINDING")
    assert game.inspect(OTHER, identity)["state"] == "complete"
    assert "PRIVATE_ABSENT_OWNER_REBEL_FINDING" in json.dumps(game.inspect(OTHER, identity))
    old = state(game).model_dump_json()
    game.rebuild()
    assert state(game).model_dump_json() == old and game.dice.calls == 1


def test_high_real_handler_item_damage_waits_actual_handler_replacement_before_completion(
    ledger, tmp_path, monkeypatch
):
    from test_handler_items import held

    from girlframe.services.m3_handler_consequences import HandlerConsequenceService

    game, worker, gateway, body, item = held(ledger, tmp_path, monkeypatch, (6, 6))
    service = approved(ledger, game, tmp_path, monkeypatch)
    buy(service, SNOOP)
    before = state(game)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="snoop",
            heat=0,
            target_actor=body,
            trigger_confirmed=True,
            context="Actual original Handler's carried apparatus accessible in source scene",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "snoop_select", options=("illegal",))
    answer(game, ADMIN, "snoop_answer", text="Actual private original Handler finding")
    answer(
        game,
        ADMIN,
        "snoop_relevance",
        options=(item.asset_id,),
        text="Actual held mechanical apparatus relevant; normal Handler would lose an Asset",
    )
    actual = state(game)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    consequence = actual.handler_consequences[-1]
    assert consequence.trigger == "asset_damage" and consequence.actor == body
    handler = HandlerConsequenceService(ledger)
    data = handler.get(ADMIN, consequence.id)
    handler.respond(
        ADMIN,
        str(uuid4()),
        consequence.id,
        data["game_revision"],
        "injury",
        "Actual original Handler suffers a persistent source injury",
    )
    assert state(game).handler_injuries[-1].consequence == consequence.id
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_mid_existing_intense_npc_bond_keeps_actual_depth_and_grants_only_real_counterpart_heat(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_actor_bonds import set_depth
    from girlframe.engine.m3_actor_state import ActorRef

    npc = ActorRef(kind="npc", entity="known-guard")

    def prior(game):
        with ledger.transaction() as c:
            canon = state(game)
            event = str(uuid4())
            canon = set_depth(canon, current_ref(canon, 2), npc, 2, event)
            game.event(
                c, 1, str(uuid4()), "synthetic.actual_prior_intense_npc_bond", canon, event_id=event
            )

    game, _, _, identity = rolled(ledger, tmp_path, monkeypatch, before_roll=prior, target=npc)
    before = state(game)
    answer(game, PLAYER, "snoop_select", options=("rebel_evidence",))
    answer(game, ADMIN, "snoop_answer", text="Actual original NPC's private printed finding")
    after = state(game)
    assert depth(after, current_ref(after, 2), npc) == 2
    assert after.sheets["2"].heat == before.sheets["2"].heat + 2
    assert "heat" not in next(x for x in after.world.npcs if x.id == npc.entity).model_dump()
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
