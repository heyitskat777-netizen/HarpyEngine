"""Real prisoners, actual execution effects and controller-owned enemy Tag resources."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_handler_ordinary import finish_keep, mark
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_mission_ui import current
from test_secretary import ready as ordinary_award
from test_strain import facts
from test_strain_service import D6

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_reign_terror import open_terror
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine import m3_reign_terror as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_resources import rebel_inventory
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_reign_terror import ReignTerrorService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def native(service, viewer=ADMIN, identity=None, **values):
    async def run():
        own = current(viewer.user_id, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_terror(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        confirmed = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def ready(store, tmp_path, monkeypatch):
    game, _, worker, gateway = ordinary_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE, rules.RULE))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(subsystems=store.policy.m3_approval.subsystems | {"strain"})
            )
        )
    )
    missions = MissionService(store)
    world = WorldService(missions)
    actors = ActorService(missions)
    faction = Faction(
        id="actual-rebel-group", name="Actual Rebel Group", kind="rebel", cells=((1, 1),)
    )
    world.faction(ADMIN, str(uuid4()), state(game).revision, faction)
    enemy = AdversaryPilot(
        id="actual-enemy-girl",
        name="Actual Rebel Girl",
        kind="rebel",
        girl="MOCKINGBIRD",
        frame="WYVERN 0.4",
        controller=1,
        cell=(0, 0),
        faction=faction.id,
        revealed=True,
        assets=(
            Asset(
                id="enemy-girl",
                name="Actual Rebel armour",
                description="Actual Girl armour",
                family="girl",
            ),
            Asset(
                id="enemy-frame",
                name="Actual Rebel Frame",
                description="Actual installed Frame capability",
                family="frame",
            ),
        ),
    )
    assert "rebel_resources_json" not in enemy.model_dump_json()
    actors.introduce_rebel(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        enemy,
        actual=True,
        account="The world author introduces its actual original Rebel Girl and group membership",
    )
    ref = ActorRef(kind="external_pilot", entity=enemy.id)
    with pytest.raises(WorkflowError, match="another human"):
        actors.confirm_rebel_inventory(
            OTHER,
            str(uuid4()),
            state(game).revision,
            ref,
            (),
            0,
            "Someone else's mind",
            actual=True,
        )
    service = ReignTerrorService(store, game)
    inventory_id = "reign-inventory:" + enemy.id
    native(
        service,
        identity=inventory_id,
        identity0="Its actual mistrust",
        identity1="Its actual unit loyalty",
        identity2="Its actual survivor outlook",
        identity3="Its actual ambition",
        marked=("1",),
        heat="2",
        actual=("actual",),
        account="I confirm this actual Rebel Girl's current resources and marks",
    )
    with pytest.raises(WorkflowError, match="unknown inventory"):
        actors.confirm_rebel_inventory(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            ref,
            (),
            0,
            "Cannot reset current resources",
            actual=True,
        )
    assert rebel_inventory(state(game), ref).heat == 2
    strain = StrainService(OffDutyService(missions), dice=D6(1))
    strain.configure(
        ADMIN, str(uuid4()), state(game).revision, "disaster_management", frozenset({"rebellion"})
    )
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    native(service, award=(award.id,), account="Actual held advancement buys Reign of Terror")
    receipt = rules.acquisitions(state(game))[0]
    for number in range(4):
        world.npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id="actual-prisoner-" + str(number),
                name="Actual prisoner " + str(number),
                jobs=("prisoner",),
                controller=1,
                cell=(0, 0),
                faction=faction.id,
                detail="An actual living prisoner in Foundation custody",
            ),
        )
    game.dice = Dice((3, 4))
    return game, service, worker, gateway, receipt, ref, actors, strain


def execute(service, game, number, choice):
    before = {x.id: x.alive for x in state(game).world.npcs}
    values = dict(
        prisoner=("actual-prisoner-" + str(number),),
        choice=(choice,),
        actual=("actual",),
        account="My original Handler actually executes this actual Foundation prisoner here",
    )
    if choice == "girl_tag":
        values.update(
            girl=(current_ref(state(game), 2).token,), label="Terrorized by the execution"
        )
    native(service, identity=rules.acquisitions(state(game))[0].id, **values)
    result = rules.executions(state(game))[-1]
    assert (
        before[result.prisoner.entity]
        and not next(x for x in state(game).world.npcs if x.id == result.prisoner.entity).alive
    )
    return result


def scene(game, actors, enemy, channel):
    casts = CastService(actors)
    if channel != 900:
        game.close_scene(ADMIN, str(uuid4()), channel - 1)
        game.bind_scene(ADMIN, str(uuid4()), channel)
        for viewer in (ADMIN, PLAYER, OTHER):
            game.join_scene(viewer, str(uuid4()), channel)
    change(casts, ADMIN, "join", current_ref(state(game), 1), channel=channel)
    change(casts, ADMIN, "join", enemy, channel=channel)


def engage(game, worker, gateway, enemy, channel, tag, *, other_tag=None):
    action = game.begin(
        PLAYER,
        str(uuid4()),
        channel,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            target_actor=enemy,
            heat=0,
            context="I actually engage this original member enemy Pilot",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")
    data = game.decision(PLAYER, row["id"])
    assert tag in data["reign_enemy_tag_ids"]
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(tag,),
        number=1,
        text="This actual member's Underfunded group makes this attack effective",
    )
    if other_tag:
        answer(
            game,
            OTHER,
            "tag_window",
            options=("tag",),
            denied=(other_tag,),
            number=-1,
            text="The acting Girl's actual fear of this execution gets in its way",
        )
    else:
        answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert len([x for x in saved["data"]["modifiers"] if x.get("tag")]) == 1
        assert saved["data"]["modifiers"][-1]["tag"] == tag
    return action


def finish_engage(game, worker, gateway, action):
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="I actually take cover and advance against this original enemy",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"


def resolve_enemy(game, choice, replace=None):
    async def run():
        row = next(x for x in game.choices(ADMIN) if x["kind"] == "reign_group_tag_resolution")
        own = current(1, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values["choice"] = (choice,)
        if replace:
            form.values["replace"] = (replace,)
        confirmed = current(1, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def test_actual_execution_three_effects_member_tag_identity_and_own_girl_resolution(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway, receipt, enemy, actors, strain = ready(
        ledger, tmp_path, monkeypatch
    )
    low = execute(service, game, 0, "rebellion_low")
    assert (
        low.rebellion_before == "high"
        and strain.get(ADMIN)["strain"]["levels"]["rebellion"] == "low"
    )
    funded = execute(service, game, 1, "underfunded")
    own = execute(service, game, 2, "girl_tag")
    assert next(x for x in state(game).world.factions if x.id == funded.group).underfunded
    member = rules.member_tags(state(game))[0]
    scene(game, actors, enemy, 900)
    first = engage(game, worker, gateway, enemy, 900, member.id, other_tag=own.tag)
    assert not next(x for x in state(game).sheets["2"].tags if x.id == own.tag).marked
    finish_engage(game, worker, gateway, first)
    before = rules.member_tags(state(game))
    redundant = execute(service, game, 3, "underfunded")
    assert redundant.condition == funded.condition and rules.member_tags(state(game)) == before
    scene(game, actors, enemy, 901)
    second = engage(game, worker, gateway, enemy, 901, member.id)
    inventory = rebel_inventory(state(game), enemy)
    replaced = inventory.identities[0].id
    resolve_enemy(game, "embrace", replaced)
    after = rebel_inventory(state(game), enemy)
    assert after.heat == 2 and len(after.identities) == 4
    assert replaced not in {x.id for x in after.identities}
    assert any(x.name == "Underfunded" for x in after.identities)
    finish_engage(game, worker, gateway, second)
    channel = 901
    for next_channel in (902, 903):
        game.close_scene(ADMIN, str(uuid4()), channel)
        game.bind_scene(ADMIN, str(uuid4()), next_channel)
        for viewer in (ADMIN, PLAYER, OTHER):
            game.join_scene(viewer, str(uuid4()), next_channel)
        action = mark(game, worker, gateway, next_channel, own.tag)
        if next_channel == 903:
            replacement = state(game).sheets["2"].identities[0].id
            answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(replacement,))
        finish_keep(game, worker, gateway, action)
        channel = next_channel
    assert any(x.name == "Terrorized by the execution" for x in state(game).sheets["2"].identities)
    period = strain.periods.begin(ADMIN, str(uuid4()))
    canon = state(game)
    count = sum(any(x.void for x in sheet.assets) for sheet in canon.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        1,
        canon.revision,
        facts(at_least_half_have_void=2 * count >= len(canon.order), no_girl_void=count == 0),
    )
    request = next(x for x in state(game).strain.requests if x.track == "rebellion")
    assert request.severity == "low"
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    assert next(x for x in state(game).strain.events if x.id == request.id).severity == "low"
    assert not state(game).career_archives


def test_actual_enemy_owned_rejection_is_real_external_action_with_lock_and_history(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway, receipt, enemy, actors, _ = ready(ledger, tmp_path, monkeypatch)
    execute(service, game, 0, "underfunded")
    tag = rules.member_tags(state(game))[0]
    scene(game, actors, enemy, 900)
    first = engage(game, worker, gateway, enemy, 900, tag.id)
    finish_engage(game, worker, gateway, first)
    scene(game, actors, enemy, 901)
    second = engage(game, worker, gateway, enemy, 901, tag.id)
    resolve_enemy(game, "reject")
    finish_engage(game, worker, gateway, second)
    before = state(game).sheets.copy()
    native(
        service,
        identity=tag.id,
        channel=("901",),
        actual=("actual",),
        account="My Rebel Girl rejects this label by performing its actual original defiant action",
    )
    tick(worker, gateway, 5)
    actual = state(game)
    assert next(x for x in rules.member_tags(actual) if x.id == tag.id).phase == "rejected"
    assert all(x.state == "fulfilled" for x in actual.obligations if x.kind == "reign_reject_tag")
    assert actual.sheets == before
    with ledger.engine.connect() as c:
        assert game.lock(c, 901)["state"] == "released"
    inbox = InboxService(ledger)
    assert any(x.task == "m3_reign_terror" and x.identity == receipt.id for x in inbox.items(ADMIN))
