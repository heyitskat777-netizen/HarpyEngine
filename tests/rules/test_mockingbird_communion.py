"""Actual Call guest/relay choices keep one original receipt and actual human ownership."""

import asyncio
from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_dive import choose
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_mockingbird_communion import open_call
from girlframe.engine import m3_physical
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_world_state import Board, World
from girlframe.services import m3_mockingbird_call as call
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_mockingbird_communion import CallService
from girlframe.services.onboarding import WorkflowError


def source(
    store,
    monkeypatch,
    *,
    board=True,
    relay=False,
    core=False,
    tmp_path=None,
    prevoid_frame=False,
    npc_guest=False,
):
    game, worker, gateway = ready(store, (4, 5))
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    if core:
        from test_enforcer_requisitions import approved
        from test_janus_core import facts
        from test_janus_core_service import change

        from girlframe.engine.m3_janus import CORE
        from girlframe.services.m3_janus import JanusService

        approved(store, game, tmp_path, monkeypatch, extra=(CORE,))
        store.policy = store.policy.model_copy(
            update={
                "m3_approval": store.policy.m3_approval.model_copy(
                    update={"subsystems": store.policy.m3_approval.subsystems | {"playbooks"}}
                )
            }
        )
        cores = JanusService(game)
        actual = cores.request(PLAYER, str(uuid4()), 3)["id"]
        change(cores, OTHER, actual, facts=facts())
        change(cores, ADMIN, actual, approve=True, account="Actual original Core body reviewed")
    with store.transaction() as c:
        canon = state(game)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        if relay:
            from test_world import gorgon

            canon.world = canon.world.model_copy(
                update={"gorgons": (gorgon("benevolent", "actual-nearby", revealed=True),)}
            )
        for owner, mode in ((2, "piloting"), (3, "outside_frame")):
            actor = current_ref(canon, owner)
            view = resolve(
                canon, actor, profiles(c, store.campaign_id), require_current_profile=False
            )
            canon = m3_physical.initial(
                canon,
                profiles(c, store.campaign_id),
                InitialPlacement(
                    actor=actor,
                    frame_instance=view.frame_instance,
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    mode=mode,
                    account="Actual source body and own Frame",
                    facts_confirmed=True,
                ),
                "actual-body-" + str(owner),
                "actual-facts-" + str(owner),
                "actual-review-" + str(owner),
            )
        if prevoid_frame:
            assets = [x for x in canon.sheets["3"].assets if x.family == "frame"]
            for asset in assets[:-1]:
                asset.void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_source_bodies", canon)
    target = current_ref(state(game), 3)
    if npc_guest:
        from test_cast_service import change

        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_world_state import Npc
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_cast import CastService
        from girlframe.services.m3_missions import MissionService
        from girlframe.services.m3_npc_roles import NpcRoleService
        from girlframe.services.m3_world import WorldService

        store.policy = store.policy.model_copy(
            update={
                "m3_approval": store.policy.m3_approval.model_copy(
                    update={"subsystems": store.policy.m3_approval.subsystems | {"world"}}
                )
            }
        )
        roles = NpcRoleService(WorldService(MissionService(store)))
        offered = roles.offer(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id="actual-call-guest",
                name="Actual NPC guest",
                jobs=("civilian",),
                detail="An actual existing person",
                controller=3,
                cell=(0, 0),
                revealed=True,
            ),
        )
        roles.respond(OTHER, str(uuid4()), offered["id"], state(game).revision, "accept")
        target = ActorRef(kind="npc", entity="actual-call-guest")
        change(CastService(ActorService(MissionService(store))), OTHER, "join", target)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual owned Call",
            trigger_confirmed=True,
            heat=0,
            piloting=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    if board:
        choose(game, PLAYER, call.BOARD)
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"target": target.token},
            text="My actual invitation and physical contact at the cockpit",
        )
    if relay:
        from girlframe.engine.m3_actor_state import ActorRef

        choose(game, PLAYER, call.RELAY)
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"target": ActorRef(kind="gorgon", entity="actual-nearby").token},
            text="Actual private message through my Frame",
        )
    return game, worker, gateway, identity


def respond(service, viewer, session_id, operation, **data):
    return service.respond(
        viewer,
        str(uuid4()),
        session_id,
        service.get(viewer, session_id)["revision"],
        operation,
        dict(account="My actual owned source response", **data),
    )


def test_actual_guest_accepts_boards_and_asks_each_human_without_another_roll(ledger, monkeypatch):
    game, _, _, identity = source(ledger, monkeypatch)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    with pytest.raises(WorkflowError):
        respond(service, PLAYER, session, "accept")
    original = state(game)
    respond(service, OTHER, session, "accept")
    boarded = state(game)
    guest = current_ref(boarded, 3)
    with ledger.engine.connect() as c:
        view = resolve(
            boarded, guest, profiles(c, ledger.campaign_id), require_current_profile=False
        )
    assert view.inside_frame and view.piloting is False
    assert view.occupied_frame_instance != view.frame_instance
    old = boarded.sheets["3"].identities[0]
    respond(
        service,
        OTHER,
        session,
        "effect",
        option="erase_identity_and_table_question",
        identity=old.id,
        question="What do you actually remember?",
    )
    assert not any(x.id == old.id for x in state(game).sheets["3"].identities)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    for viewer in (ADMIN, PLAYER, OTHER):
        respond(service, viewer, session, "table")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert state(game).sheets["2"].assets == original.sheets["2"].assets
    assert state(game).scene_casts == original.scene_casts


def test_actual_decline_finishes_invitation_without_boarding_or_forcing_guest_effect(
    ledger, monkeypatch
):
    game, _, _, identity = source(ledger, monkeypatch)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(service, OTHER, session, "decline")
    assert state(game).passengers[-1].state == "declined"
    assert state(game).placements[-1].mode == "outside_frame"
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_native_guest_next_form_survives_real_confirm_and_stale_form_cannot_resubmit(
    ledger, monkeypatch
):
    game, _, _, identity = source(ledger, monkeypatch)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(service, OTHER, session, "accept")

    async def run():
        interaction = current(3, 992001)
        await interaction.response.defer(ephemeral=True)
        await open_call(interaction, service, session)
        first = interaction.edit_original_response.call_args.kwargs["view"]
        first.values.update(
            option=("erase_identity_and_table_question",), account="My actual connection"
        )
        next_interaction = current(3, 992002)
        await first.confirm.callback(next_interaction)
        detail = next_interaction.edit_original_response.call_args.kwargs["view"]
        assert first.completed and detail is not first and not detail.completed
        detail.values.update(
            identity=(state(game).sheets["3"].identities[0].id,), detail="My actual question"
        )
        await detail.confirm.callback(current(3, 992003))
        assert detail.completed and service.get(OTHER, session)["phase"] == "table"

    asyncio.run(run())
    assert game.inspect(PLAYER, identity)["state"] != "complete" and game.dice.calls == 1


def test_actual_nearby_gorgon_owns_reply_without_new_roll_cast_or_compelled_truth(
    ledger, monkeypatch
):
    game, _, _, identity = source(ledger, monkeypatch, board=False, relay=True)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    before = state(game)
    assert service.get(ADMIN, session)["message"] == "Actual private message through my Frame"
    assert service.get(OTHER, session)["message"] == ""
    with pytest.raises(WorkflowError):
        respond(service, PLAYER, session, "accept")
    respond(service, ADMIN, session, "accept")
    assert service.get(PLAYER, session)["answer"] == "My actual owned source response"
    assert state(game).world == before.world and state(game).scene_casts == before.scene_casts
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1


def test_actual_guest_invitation_is_pause_safe_and_replay_does_not_reboard_or_reroll(
    ledger, monkeypatch
):
    game, _, _, identity = source(ledger, monkeypatch)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    view = service.get(OTHER, session)
    key = str(uuid4())
    ledger.safety(OTHER, "pause-call", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError):
        service.respond(
            OTHER, key, session, view["revision"], "accept", dict(account="My actual acceptance")
        )
    ledger.safety(OTHER, "resume-call", ledger.status(OTHER)["revision"], pause=False)
    first = service.respond(
        OTHER, key, session, view["revision"], "accept", dict(account="My actual acceptance")
    )
    retry = service.respond(
        OTHER, key, session, view["revision"], "accept", dict(account="My actual acceptance")
    )
    assert first == retry and len(state(game).passengers) == 1
    with pytest.raises(WorkflowError):
        service.respond(
            OTHER,
            str(uuid4()),
            session,
            view["revision"],
            "accept",
            dict(account="Old form cannot board twice"),
        )
    assert game.inspect(PLAYER, identity)["state"] != "complete" and game.dice.calls == 1


def test_actual_guest_subsumption_requires_genuine_core_voice_and_real_extraction_then_medical_help(
    ledger, monkeypatch, tmp_path
):
    from girlframe.discord_adapter.m3_passengers import open_passenger
    from girlframe.services.m3_passengers import PassengerService

    game, _, _, identity = source(ledger, monkeypatch, core=True, tmp_path=tmp_path)
    communion = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    original = state(game)
    respond(communion, OTHER, session, "accept")
    respond(
        communion,
        OTHER,
        session,
        "effect",
        option="locked_cockpit_extraction_requires_frame_consent",
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    service = PassengerService(game)
    assert service.get(OTHER, session)["can_consent"]
    with pytest.raises(WorkflowError):
        service.get(ADMIN, session)
    body = next(x for x in state(game).placements if x.actor == current_ref(state(game), 3))
    assert body.subsumed and not body.vitals_active
    assert body.frame_instance != body.occupied_frame_instance
    actor = current_ref(state(game), 2)

    def physical(viewer, operation, **data):
        return service.respond(
            viewer,
            str(uuid4()),
            session,
            service.get(viewer, session)["revision"],
            operation,
            "My actual owned physical action",
            **data,
        )

    physical(OTHER, "consent", allowed=False)
    with pytest.raises(WorkflowError):
        physical(PLAYER, "extract", actor=actor)

    async def actual_buttons():
        core = current(3, 993001)
        await core.response.defer(ephemeral=True)
        await open_passenger(core, service, session)
        form = core.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            operation=("allow",),
            account="The actual Core gives its permitted nonverbal physical response",
        )
        await form.confirm.callback(current(3, 993002))
        assert form.completed
        carrier = current(2, 993003)
        await carrier.response.defer(ephemeral=True)
        await open_passenger(carrier, service, session)
        extract = carrier.edit_original_response.call_args.kwargs["view"]
        extract.values.update(
            operation=("extract",),
            actor=(actor.token,),
            account="My actual body extracts the guest at my cockpit",
        )
        await extract.confirm.callback(current(2, 993004))
        assert extract.completed

    asyncio.run(actual_buttons())
    after = state(game)
    placed = next(x for x in after.placements if x.actor == current_ref(after, 3))
    assert placed.mode == "outside_frame" and not placed.subsumed and not placed.vitals_active
    assert after.sheets["3"].assets == original.sheets["3"].assets
    physical(OTHER, "medical_request")
    with pytest.raises(WorkflowError):
        physical(PLAYER, "medical_confirm")
    physical(ADMIN, "medical_confirm")
    assert next(
        x for x in state(game).placements if x.actor == current_ref(state(game), 3)
    ).vitals_active
    assert game.dice.calls == 1


def test_actual_guest_last_frame_void_finishes_real_owned_frame_growth_before_parent_unlocks(
    ledger, monkeypatch
):
    import sqlalchemy as sa
    from test_void_service import respond as void_respond

    from girlframe.database import tables as t
    from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
    from girlframe.services.m3_void import VoidService

    game, _, _, identity = source(ledger, monkeypatch, prevoid_frame=True)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(service, OTHER, session, "accept")
    unvoid = next(x for x in state(game).sheets["3"].assets if x.family == "frame" and not x.void)
    respond(
        service,
        OTHER,
        session,
        "effect",
        option="void_and_unmark_all",
        asset=unvoid.id,
        description="Actual source guest's own last altered Frame Asset",
    )
    with ledger.engine.connect() as c:
        work = c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.kind == "void_threshold"
            )
        )
    actual = VoidService(ledger)
    assert actual.get(OTHER, work)["stage"] == "abandoned"
    assert service.get(OTHER, session)["phase"] == "threshold"
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    frames = tuple(
        Asset(
            id=x.id,
            name=x.name,
            description=x.description or "Actual transformed source Asset",
            family="gorgon",
            damaged=x.damaged,
            void=True,
        )
        for x in state(game).sheets["3"].assets
        if x.family == "frame"
    )
    grown = Gorgon(
        id="actual-guest-own-frame",
        name="Actual guest's consumed Frame",
        cell=(0, 0),
        position_event="actual-proposed-position",
        gorgon_class="aggressive",
        types=("growth",),
        assets=frames,
        core_plan=CorePlan(assets=(frames[0].id,), weakness="Actual declared weakness"),
    )
    void_respond(
        actual,
        work,
        "abandoned",
        dict(gorgon=grown.model_dump(mode="json"), account="Actual source Frame growth"),
        viewer=ADMIN,
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    after = state(game)
    assert after.sheets["3"].frame_scrapped and not after.sheets["2"].frame_scrapped
    guest = next(x for x in after.placements if x.actor == current_ref(after, 3))
    assert guest.mode == "inside_frame" and guest.occupied_frame_owner == current_ref(after, 2)


def test_actual_npc_guest_keeps_own_body_and_source_handler_owns_world_manifestation(
    ledger, monkeypatch
):
    game, _, _, identity = source(ledger, monkeypatch, npc_guest=True)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    before = state(game)
    respond(service, OTHER, session, "accept")
    value = state(game).mockingbird.calls[-1]
    with ledger.engine.connect() as c:
        actual = resolve(
            state(game), value.guest, profiles(c, ledger.campaign_id), require_current_profile=False
        )
    assert (
        actual.rules == "npc"
        and actual.inside_frame
        and not actual.assets
        and not actual.identities
    )
    respond(service, OTHER, session, "effect", option="nearby_npcs_gain_void")
    with pytest.raises(WorkflowError):
        respond(service, OTHER, session, "npc", manifestations={"actual-call-guest": "bones"})
    respond(service, ADMIN, session, "npc", manifestations={"actual-call-guest": "bones"})
    after = state(game)
    npc = next(x for x in after.world.npcs if x.id == "actual-call-guest")
    assert npc.tags[-1].label == "Void of the bones" and not hasattr(npc, "assets")
    assert after.sheets == before.sheets and game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == 1
