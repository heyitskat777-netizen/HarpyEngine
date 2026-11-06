"""Real Harpy capture, physical repossession, actual Mockingbird and genuine award/spend."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_handler_creation import agree, save
from test_handler_creation import complete as handler_package
from test_handler_ordinary import session_native
from test_harpy_defeat import choose
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current
from test_physical_operations import place
from test_void_service import five_no, ready, respond

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import open_advancement
from girlframe.discord_adapter.m3_handler_conversion import open_conversion
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_conversion as rules
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_world_state import Location, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_conversion import HandlerConversionService, prove_repossession
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.onboarding import WorkflowError


def native(service, identity, viewer, number, **values):
    async def run():
        own = current(viewer.user_id, number)
        await own.response.defer(ephemeral=True)
        await open_conversion(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        result = current(viewer.user_id, number + 1)
        await form.confirm.callback(result)
        assert form.completed, (
            result.edit_original_response.call_args_list,
            result.followup.send.call_args_list,
        )

    asyncio.run(run())


def actual_captured(store, tmp_path, monkeypatch):
    void, game, worker, gateway, root, work = ready(store)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, ordinary_rules.RULE))
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": store.policy.m3_approval.model_copy(
                update={"subsystems": store.policy.m3_approval.subsystems | {"playbooks", "world"}}
            ),
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={"handler_creation": "owned_shared_choices_preserve_existing"}
            ),
        }
    )
    five_no(void, work)
    data = void.get(PLAYER, work)
    choice = data["rebirth_choice"] | dict(account="Actual original person reborn as Harpy")
    respond(void, work, "rebirth", dict(choice=choice, account="Actual original rebirth"))
    tick(worker, gateway, 6)
    actor = state(game).void_thresholds[-1].resulting_actor
    assert actor is not None and "2" not in state(game).sheets
    with store.transaction() as c:
        canon = place(state(game), 3, mode="outside_frame")
        canon.world = canon.world.model_copy(
            update={
                "locations": (
                    Location(
                        id="treatment-base", name="Actual Foundation Base", kind="base", cell=(0, 0)
                    ),
                ),
                "npcs": (
                    Npc(
                        id="actual-guard",
                        name="Actual silent guard",
                        jobs=("guard",),
                        detail="The actual original guard",
                        controller=1,
                        cell=(0, 0),
                    ),
                ),
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_base_and_helper", canon)
    creation = HandlerCreationService(store)
    save(creation, handler_package(creation, "Scientist"))
    agree(creation)
    data = creation.view(ADMIN)
    creation.activate(ADMIN, str(uuid4()), data["revision"], data["game_revision"], True)
    with store.transaction() as c:
        canon = state(game)
        scene = game.scene(c, 900)
        canon.scene_casts = [
            SceneCast(
                id=scene["id"],
                channel=900,
                roles=tuple(
                    CastRole(actor=ref, controller=uid, source_event="actual-cast-source")
                    for ref, uid in (
                        (current_ref(canon, 1), 1),
                        (actor, 2),
                        (current_ref(canon, 3), 3),
                    )
                ),
                facilitator=1,
                facilitator_source="actual-cast-source",
            )
        ]
        game.event(c, 1, str(uuid4()), "synthetic.actual_reborn_cast", canon)
    # Genuine existing Handler Plays damage real original Harpy Frame resources.
    plays = HandlerPlayService(store)
    for asset in tuple(harpy(state(game), actor).assets):
        if asset.family != "frame":
            continue
        grant = plays.start(ADMIN, str(uuid4()), state(game).revision, (actor,))
        plays.submit(
            ADMIN,
            str(uuid4()),
            grant["id"],
            state(game).revision,
            "mess",
            Effect(
                kind="damage",
                target=actor,
                asset=asset.id,
                account="Actual hostile action damages this original Frame Asset",
            ),
        )
    defeat = HarpyDefeatService(store, game)
    with store.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "harpy_defeat"
                )
            )
            .mappings()
            .one()
        )
    game.dice = Dice((6, 6))
    action = defeat.begin(PLAYER, str(uuid4()), row["id"], channel=900)["action_id"]
    tick(worker, gateway, 1)
    with store.engine.connect() as c:
        if game.action(c, action)["data"].get("receipt") is None:
            defeat.roll(PLAYER, str(uuid4()), action)
    for viewer in (PLAYER, OTHER, ADMIN):
        choose(defeat, game, viewer, "tag_window", options=("pass",))
    choose(
        defeat,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("foundation",),
        text="Actual shutdown and alive Foundation capture",
    )
    choose(
        defeat,
        game,
        ADMIN,
        "harpy_capture_fact",
        flag=True,
        fields={"captor": current_ref(state(game), 3).token},
        text="Actual present Foundation Girl takes custody of the original Harpy",
    )
    assert defeat.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    return game, worker, gateway, actor


def test_actual_capture_treatment_installs_one_real_mockingbird_then_award_spend_history(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, actor = actual_captured(ledger, tmp_path, monkeypatch)
    service = HandlerConversionService(ledger)
    session_native(HandlerOrdinaryService(ledger), "Actual capture/conversion Session", 39100)
    before = harpy(state(game), actor)
    original_archives = tuple(state(game).career_archives)
    native(service, None, ADMIN, 39110, actor=(actor.entity,))
    identity = rules.records(state(game))[0].id
    with pytest.raises(WorkflowError, match="extraction|transport|treatment"):
        service.complete(PLAYER, str(uuid4()), identity, state(game).revision)
    native(service, identity, OTHER, 39120, account="I actually separate this captured Harpy body")
    assert harpy(state(game), actor).linked  # A source statement alone has no effect.
    native(
        service,
        identity,
        ADMIN,
        39130,
        result=("yes",),
        account="Actual original body extraction completed by its present custodian",
    )
    assert not harpy(state(game), actor).linked
    native(
        service,
        identity,
        OTHER,
        39140,
        destination=("treatment-base",),
        account="Actual separated body carried into the Base medical facility",
    )
    native(
        service,
        identity,
        ADMIN,
        39150,
        result=("yes",),
        account="Actual route completed into the known Foundation Base; Frame stays outside",
    )
    transported = harpy(state(game), actor)
    assert transported.custody == "transported" and transported.frame_cell == before.frame_cell
    assert transported.assets == before.assets
    native(
        service,
        identity,
        ADMIN,
        39160,
        purge="Actual poisons purged without the Frame metabolizing them",
        organs="Actual altered organs studied and excised as needed",
        conditioning="Actual drugs and reprogramming produce the Mockingbird outcome",
        recovery=("awake",),
    )
    assets = tuple(CATALOG["MOCKINGBIRD"]["assets"][:2])
    native(
        service,
        identity,
        PLAYER,
        39170,
        assets=assets,
        void=(assets[0],),
        description1="Actual post-treatment adaptive restraint capability",
        description2="Actual post-treatment altered perception",
        appearance="Actual treated original",
        girl=(current_ref(state(game), 3).token,),
        role=("2",),
        npc=("actual-guard",),
    )
    native(
        service,
        identity,
        ADMIN,
        39180,
        position=("1",),
        account="The original human's exact actual resulting package and Status are reviewed",
    )
    ready = service.menu(PLAYER, identity)
    native(service, identity, PLAYER, 39190, confirm=("confirm",))
    canon = state(game)
    replay = service.complete(PLAYER, "39191", identity, ready["revision"])
    assert replay["phase"] == "complete" and state(game) == canon
    value = rules.completed(canon, identity)
    converted = current_ref(canon, 2)
    sheet = canon.sheets["2"]
    assert value.resulting_actor == converted and converted.incarnation != before.origin.incarnation
    assert tuple(canon.career_archives) == original_archives
    assert not any(x.id == actor.entity for x in canon.harpy_states)
    assert sheet.girl == "MOCKINGBIRD" and tuple(x.name for x in sheet.identities) == tuple(
        CATALOG["MOCKINGBIRD"]["identities"]
    )
    assert [(x.id, x.damaged, x.void) for x in sheet.assets if x.family == "frame"] == [
        (x.id, x.damaged, x.void) for x in before.assets if x.family == "frame"
    ]
    assert len([x for x in sheet.assets if x.family == "girl" and x.void]) == 1
    assert depth(canon, converted, current_ref(canon, 3)) >= 1
    assert depth(canon, converted, ActorRef(kind="npc", entity="actual-guard")) >= 1
    with ledger.engine.connect() as c:
        actual = resolve(canon, converted, profiles(c, ledger.campaign_id))
        assert actual.vessel_id == before.body_vessel and not actual.inside_frame
        assert actual.frame_instance == before.frame_instance and actual.frame_shutdown
        assert frame_position(canon, before.origin, before.frame_instance) == before.frame_cell
        with pytest.raises(ValueError):
            resolve(canon, actor, profiles(c, ledger.campaign_id))
        prove_repossession(service.game, c, canon, identity)
        from girlframe.engine.m3_physical import cockpit_enter

        with pytest.raises(ValueError, match="shut down|shutdown"):
            cockpit_enter(
                canon,
                profiles(c, ledger.campaign_id),
                converted,
                "actual-shutdown-check",
                "Attempt actual original Frame piloting",
                pilot=True,
            )
        snapshot = (
            c.execute(
                sa.select(t.snapshots).where(
                    t.snapshots.c.campaign_id == ledger.campaign_id,
                    t.snapshots.c.user_id == "2",
                    t.snapshots.c.revision == sheet.source_profile_revision,
                )
            )
            .mappings()
            .one()
        )
        assert snapshot["event_id"] == value.completion_event
        assert '"MOCKINGBIRD"' in snapshot["public_json"]
    # Genuine current Girl Heat/Identity/Keep consumer, outside the shutdown original Frame.
    game.dice = Dice((4, 4))
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 901)
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), 901)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        901,
        sheet.revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual post-treatment danger outside Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (ADMIN, PLAYER, OTHER):
        answer(game, viewer, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("tough", "sexy"), denied=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual original Mockingbird result")
    tick(worker, gateway, 4)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    before_permissions = state(game).sheets["2"].permissions
    award = awards.awards(state(game))[0]
    assert (
        award.ordinary_source.trigger == "capture_convert"
        and len(ordinary_rules.marks(state(game))) == 1
    )

    async def spend():
        svc = HandlerAdvancementService(ledger)
        own = current(1, 39200)
        await own.response.defer(ephemeral=True)
        await open_advancement(own, svc, award.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(girls=(converted.token,))
        next_step = current(1, 39201)
        await form.confirm.callback(next_step)
        amounts = next_step.edit_original_response.call_args.kwargs["view"]
        amounts.values.update(
            {converted.token: ("2",)}, account="Actual capture award Permission spend"
        )
        await amounts.confirm.callback(current(1, 39202))
        assert amounts.completed
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_handler_conversion" and x.identity == identity
        )
        viewer = current(2, 39203)
        await viewer.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(viewer, item)

    asyncio.run(spend())
    assert state(game).sheets["2"].permissions == before_permissions + 2
    assert awards.awards(state(game))[0].phase == "spent"
