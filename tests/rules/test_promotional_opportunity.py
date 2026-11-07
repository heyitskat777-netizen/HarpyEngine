"""Actual regional map creation, original rival fate, responsibility and physical intake."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_handler_ordinary import session_native, setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_strain_service import D6, prepared
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_promotional_opportunity as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_storage import get as storage_order
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_void_state import HarpyIdentity
from girlframe.engine.m3_world import destroy
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Asset,
    Board,
    Faction,
    Location,
    Npc,
    base_responsible,
    quadrant12_contains,
)
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_handler_pr import HandlerPRService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_promotional_opportunity import (
    PromotionalOpportunityService,
    prove,
    prove_harpy,
)
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    game, ordinary_service, worker, gateway = setup(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE, awards.RULES[0]))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=store.policy.m3_approval.subsystems
                    | {"world", "discipline", "strain", "plays"}
                )
            )
        )
    )
    with store.transaction() as c:
        canon = state(game)
        old = initial()
        canon.world = canon.world.model_copy(
            update=dict(board=old.board, locations=old.locations, gorgons=old.gorgons)
        )
        game.event(c, 1, str(uuid4()), "synthetic.original_regional_map", canon)
    session_native(ordinary_service, "Actual regional advancement Session", 87800)
    pr = HandlerPRService(store)
    from girlframe.engine.m3_actor_bonds import current_ref

    source = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Foundation regional feature",
        "Actually performed media presentation",
        (current_ref(state(game), 2),),
    )["id"]
    for viewer, hosting in ((ADMIN, True), (PLAYER, False)):
        pr.activity(
            viewer,
            str(uuid4()),
            source,
            state(game).revision,
            "Actual participant performed the Foundation feature",
            hosting=hosting,
        )
    pr.submit_result(
        ADMIN, str(uuid4()), source, state(game).revision, "The real feature was performed"
    )
    pr.resolve(
        ADMIN,
        str(uuid4()),
        source,
        state(game).revision,
        True,
        "The factual Foundation feature succeeded",
    )
    return game, PromotionalOpportunityService(store), worker, gateway


def user(owner=1):
    value = current(owner, int(uuid4().int % 1000000000))
    value.channel_id = 900
    return value


async def submit_form(origin, **values):
    view = origin.edit_original_response.call_args.kwargs["view"]
    view.values.update(values)
    next_step = user(origin.user.id)
    await view.confirm.callback(next_step)
    assert view.completed, next_step.edit_original_response.call_args
    return next_step


def native_acquire(game):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def run():
        start = user()
        await start.response.defer(ephemeral=True)
        await open_advancement(start, HandlerAdvancementService(game.store), award.id)
        button = next(
            x
            for x in start.edit_original_response.call_args.kwargs["view"].children
            if isinstance(x, AcquireMore)
        )
        opened = user()
        await opened.response.defer(ephemeral=True)
        await button.callback(opened)
        step = await submit_form(opened, advancement=("opportunity",))
        step = await submit_form(
            step,
            award=(award.id,),
            boons=("defended_base", "two_cities", "personnel"),
            threats=("dormant", "territory"),
            side=("east",),
            depth="2",
        )
        step = await submit_form(
            step,
            name="Actual rival Handler",
            controller=("3",),
            cell=("3",),
            detail="Original regional office holder",
        )
        step = await submit_form(
            step,
            name="Actual fortified regional Base",
            cell=("0",),
            detail="Actual reinforced walls, protected approaches and staffed watchposts",
            guard="Actual garrison guard",
            controller=("1",),
        )
        step = await submit_form(
            step,
            first="Actual north city",
            cell=("1",),
            second="Actual south city",
            other_cell=("2",),
        )
        step = await submit_form(
            step,
            name="Actual regional Budget administrator",
            controller=("1",),
            cell=("0",),
            job=("base_personnel",),
            detail="Competent loyal regional personnel; actual budget-management superior",
        )
        step = await submit_form(
            step,
            name="Actual dormant regional Gorgon",
            cell=("15",),
            type=("incubus",),
            asset="Actual protective mantle",
            description="A real Core-protecting mantle",
            other1="Actual sensory organ",
            other2="Actual locomotion limbs",
            weakness="The actual source conversational weakness",
        )
        step = await submit_form(step, cells=tuple(str(x) for x in range(15, 23)))
        await submit_form(step, account="PRIVATE_ACTUAL_MAP authored adjoining regional facts")

    asyncio.run(run())
    return rules.acquisitions(state(game))[0]


def rival_death(store, game, source):
    target = ActorRef(kind="npc", entity=source.setup.rival.id)
    plays = HandlerPlayService(store)
    grant = plays.start(ADMIN, str(uuid4()), state(game).revision, (target,))["id"]
    plays.submit(
        ADMIN,
        str(uuid4()),
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            target=target,
            account="The original Handler actually arranges this rival's harm",
        ),
    )
    with store.engine.connect() as c:
        table = t.m3["m3_required_work"]
        work = next(
            dict(x)
            for x in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == store.campaign_id, table.c.kind == "npc_damage"
                )
            ).mappings()
            if json.loads(x["body_json"])["source_work"] == grant
        )
    damage = NpcDamageService(store)
    damage.respond(
        ADMIN,
        str(uuid4()),
        work["id"],
        work["revision"],
        "kill",
        "The actual rival dies from this canonical harm",
    )
    return work["id"]


def test_native_actual_map_rival_downfall_takeover_physical_storage_and_world(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    source = native_acquire(game)
    unlocked = state(game)
    assert unlocked.sheets == before.sheets and unlocked.placements == before.placements == []
    assert unlocked.world.locations[: len(before.world.locations)] == before.world.locations
    assert unlocked.world.npcs[: len(before.world.npcs)] == before.world.npcs
    assert unlocked.world.quadrant12 == before.world.board
    assert not base_responsible(
        unlocked.world, source.setup.defended_base.location.cell, source.handler
    )
    assert not quadrant12_contains(unlocked.world, source.setup.defended_base.location.cell)
    assert not rules.in_responsibility(unlocked, source.setup.rival.cell)
    with ledger.engine.connect() as c:
        assert prove(game, c, unlocked, source.id) == source
    with pytest.raises(WorkflowError):
        service.take_over(
            OTHER, str(uuid4()), source.id, unlocked.revision, "not-a-canonical-death"
        )
    assert state(game) == unlocked
    # Rival13 must never suppress real original12 last-Base loss.
    trial = unlocked.world
    for site in before.world.locations:
        if site.kind == "base":
            result = destroy(trial, site.id, gorgon_cause=False)
            trial = result.world
    assert any(x.kind == "quadrant_lost_handler_outcome" for x in result.followups)
    death = rival_death(ledger, game, source)
    revision = state(game).revision
    args = (ADMIN, str(uuid4()), source.id, revision, death)
    result = service.take_over(*args)
    assert service.take_over(*args) == result
    assert rules.in_responsibility(state(game), source.setup.rival.cell)
    assert base_responsible(
        state(game).world, source.setup.defended_base.location.cell, source.handler
    )

    # Previously UNKNOWN originals receive their first genuine owner+Handler physical review.
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        preview = physical.preview(viewer)
        proposal = physical.propose(
            viewer,
            str(uuid4()),
            state(game).revision,
            InitialPlacement(
                actor=ActorRef.model_validate(preview["actor"]),
                frame_instance=preview["frame_instance"],
                girl_cell=source.setup.defended_base.location.cell,
                frame_cell=source.setup.defended_base.location.cell,
                mode="outside_frame",
                account="Actual previously unknown original Girl and empty Frame are at this Base",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposal["id"],
            1,
            "accept",
            "Actual initial body/Frame facts are correct",
        )
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6())
    period = prepared(strain, game, high=frozenset({"budget"}))
    effects = EffectService(strain)
    incoming = 0
    while any(x.track == "void" for x in state(game).strain.requests):
        request = next(x for x in state(game).strain.requests if x.track == "void")
        if request.kind == "endgame":
            strain.choose(ADMIN, str(uuid4()), request.id, 1, state(game).revision, 6, endgame=True)
            award_service = HandlerAdvancementService(ledger)
            view = award_service.view(ADMIN, request.id + ":effect")
            award_service.claim_void(
                ADMIN,
                str(uuid4()),
                request.id + ":effect",
                state(game).revision,
                view["work_revision"],
                "Actual Void Endgame6 grants its genuine held source Award",
            )
            continue
        high = request.severity == "high"
        strain.dice.face = 6 if high else 1
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2 if high else 1)
        if not high:
            incoming += 1
            effects.apply(
                ADMIN,
                str(uuid4()),
                request.id + ":effect",
                1,
                state(game).revision,
                Choice(
                    rule_id="strain.void.low.1.1",
                    account="Actual Directed Gorgon enters our left map edge",
                    gorgon=gorgon("directed", "actual-entering-gorgon-" + str(incoming), (-3, 0)),
                ),
            )
    for track, face, column in (("rebellion", 1, 2), ("budget", 6, 1)):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        if track == "rebellion":
            effects.apply(
                ADMIN,
                str(uuid4()),
                request.id + ":effect",
                1,
                state(game).revision,
                Choice(rule_id="strain.rebellion.low.1.2", account="Actual control slip"),
            )
        else:
            storage_work = request.id + ":effect"
            effects.apply(
                ADMIN,
                str(uuid4()),
                storage_work,
                1,
                state(game).revision,
                Choice(
                    rule_id="strain.budget.high.6.1",
                    storage_owner=2,
                    target=source.setup.defended_base.location.id,
                    victim=source.setup.personnel[0].id,
                    account="Actual regional superior orders this original empty Frame stored",
                ),
            )
    storage = StorageService(ledger)
    identity = storage_work + ":storage"
    current_state = state(game)
    storage.act(
        PLAYER,
        str(uuid4()),
        identity,
        current_state.revision,
        "store",
        "I actually store my original empty Frame",
    )
    assert storage_order(state(game), identity).entries[-1].action == "store"
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    assert period in state(game).world.completed_off_duty
    assert state(game).world.regions[0].responsible == source.handler
    public, private = (
        WorldService(MissionService(ledger)).get(OTHER),
        WorldService(MissionService(ledger)).get(ADMIN, private=True),
    )
    assert "PRIVATE_ACTUAL_MAP" not in str(public) and "controller" not in str(
        public["world"]["regions"]
    )
    assert "PRIVATE_ACTUAL_MAP" not in str(public) and "regions" in str(private)

    async def history():
        inbox = InboxService(ledger)
        card = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_promotional_opportunity" and x.identity == source.id
        )
        current_user = user()
        await current_user.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(current_user, card)
        assert "responsible" in current_user.edit_original_response.call_args.kwargs["content"]

    asyncio.run(history())


def alternative(source_id, threats):
    bounds = Board(minimum=(11, -3), maximum=(12, 10))
    sites = dict(
        useful=rules.Site(
            location=Location(
                id=source_id + "useful",
                name="Actual useful laboratory",
                cell=(11, -3),
                kind="important",
            ),
            detail="Actual staffed sample analysis benches",
        ),
        mysterious=rules.Site(
            location=Location(
                id=source_id + "mystery",
                name="Actual unexplained ruin",
                cell=(11, -2),
                kind="important",
            ),
            detail="A real sealed ruin with unexplained signals",
        ),
    )
    kwargs = dict(
        rebels=Faction(
            id=source_id + "rebels", name="Actual new faction", kind="rebel", cells=((12, 1),)
        )
    )
    if "erratic" in threats:
        kwargs["erratic"] = gorgon("erratic", source_id + "erratic", (12, 2), revealed=True)
    if "harpy" in threats:
        actor = ActorRef(kind="external_pilot", entity=source_id + "harpy")
        person = AdversaryPilot(
            id=actor.entity,
            name="Actual new active Harpy",
            kind="harpy",
            girl="Harpy",
            frame="Harpy",
            controller=1,
            cell=(12, 3),
            assets=(
                Asset(
                    id=actor.entity + ":body",
                    name="Actual Void body",
                    description="Actual altered flesh",
                    family="girl",
                    void=True,
                ),
                Asset(
                    id=actor.entity + ":frame",
                    name="Actual living Frame",
                    description="Actual linked frame shell",
                    family="frame",
                    void=True,
                ),
            ),
            revealed=True,
        )
        kwargs["harpy"] = rules.HarpySetup(
            person=person,
            facts=NativeHarpyFacts(
                actor=actor,
                linked=True,
                girl_cell=person.cell,
                frame_cell=person.cell,
                heat=0,
                frame_shutdown=False,
                body_incapacitated=False,
                custody="free",
                identities=(HarpyIdentity(id=actor.entity + ":self", name="Actual free identity"),),
                tags=(),
                account="Actual original resources of the active world Harpy",
                facts_confirmed=True,
            ),
        )
    return rules.Setup(
        bounds=bounds,
        boons=("useful", "mysterious", "personnel"),
        threats=threats,
        rival=Npc(
            id=source_id + "rival",
            name="Actual rival",
            jobs=("handler",),
            cell=(11, 1),
            controller=3,
            revealed=True,
            detail="Actual original office",
        ),
        personnel=(
            Npc(
                id=source_id + "staff",
                name="Actual loyal technician",
                jobs=("mechanic",),
                cell=(11, 0),
                controller=1,
                detail="Competent loyal regional mechanic",
            ),
        ),
        account="PRIVATE_OTHER_MAP actual regional facts",
        **sites,
        **kwargs,
    )


@pytest.mark.parametrize("threats", [("rebels", "erratic"), ("rebels", "harpy")])
def test_actual_alternate_sites_rebels_erratic_or_real_harpy_consumer(
    ledger, tmp_path, monkeypatch, threats
):
    game, service, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    award = next(x for x in awards.awards(before) if x.phase == "held")
    setup_value = alternative(award.id, threats)
    args = (ADMIN, str(uuid4()), award.id, before.revision, setup_value)
    if "erratic" in threats:
        actual_event = service.game.event
        interrupted = False

        def interruption(*call_args, **kwargs):
            nonlocal interrupted
            result = actual_event(*call_args, **kwargs)
            if kwargs.get("rule_id") == rules.RULE and not interrupted:
                interrupted = True
                raise RuntimeError("interrupt after actual canonical regional event")
            return result

        monkeypatch.setattr(service.game, "event", interruption)
        with pytest.raises(RuntimeError, match="interrupt after actual"):
            service.acquire(*args)
        assert state(game) == before and not state(game).world.regions
    result = service.acquire(*args)
    assert service.acquire(*args) == result
    assert len(state(game).world.features) == 2
    assert all(x.active for x in state(game).world.factions if x.id == setup_value.rebels.id)
    with ledger.engine.connect() as c:
        source = prove(game, c, state(game), result["id"])
    assert source.setup == setup_value and state(game).sheets == before.sheets
    if setup_value.erratic:
        actual = next(x for x in state(game).world.gorgons if x.id == setup_value.erratic.id)
        assert actual.gorgon_class == "erratic" and actual.assets and actual.core_plan
    if setup_value.harpy:
        actor = setup_value.harpy.facts.actor
        with ledger.engine.connect() as c:
            body = prove_harpy(game, c, state(game), actor)
            assert HarpyDefeatService(ledger, game)._runtime(c, state(game), actor) == body
        casts = CastService(ActorService(MissionService(ledger)))
        change(casts, ADMIN, "join", actor)
        plays = ActorPlayService(game)
        preview = plays.preview(ADMIN, 900, actor)
        game.dice = Dice((4, 4))
        action = plays.begin(
            ADMIN,
            str(uuid4()),
            900,
            actor,
            preview["actor"]["source_sha256"],
            None,
            preview["cast_revision"],
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Actual new Harpy faces real danger",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(
            game, ADMIN, "actor_keep", options=("beautiful", "in_control"), denied=("desperate",)
        )
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual owned human ruling")
        tick(worker, gateway, 5)
        assert game.inspect(ADMIN, action)["state"] == "complete" and game.dice.calls == 1
