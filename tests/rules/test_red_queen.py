"""Red Queen printed normals. Only the named mid-Court native smoke may run during P1."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current as native_current
from test_physical_operations import place
from test_trainee import discipline
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_red_queen import open_choice, open_red_queen
from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m2 import PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.services.m3_red_queen import RedQueenService, prove_am, prove_court, prove_extraction
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def current(user=2, identity=500):
    value = native_current(user, identity)
    value.channel_id = 900
    return value


def ready(store, tmp_path, monkeypatch, *, inside=True):
    _, game = service(store, girl="OLDGEN", frame=rules.FRAME)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.COURT, rules.TRANSFER, rules.CONSULT, *rules.REQUISITIONS),
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = initial()
        canon = place(
            place(canon, 2, mode="piloting" if inside else "outside_frame"), 3, mode="outside_frame"
        )
        canon.sheets["2"].permissions = 30
        canon.sheets["2"].heat = 4
        canon.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.actual_court_bodies_resources_and_rank", canon)
    return game, GameWorker(game), Gateway(), RedQueenService(game)


def native(controls, operation, **values):
    async def run():
        interaction = current(2, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_red_queen(interaction, controls)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        assert not await menu.interaction_check(current(3))
        menu.values["operation"] = (operation,)
        selected = current(2, int(uuid4().int % 1000000000))
        await menu.confirm.callback(selected)
        if operation == "initialize":
            assert menu.completed
            return
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(2, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def native_choice(game, viewer, kind, **values):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def run():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list

    asyncio.run(run())


def initialize(controls):
    return controls.initialize(PLAYER, str(uuid4()), state(controls.game).revision)["id"]


def am(game, role):
    return next(x for x in rules.records(state(game), rules.CourtAM) if x.role == role)


def roll(
    game, worker, gateway, *, play="red_queen_consult", faces=(3, 4), target=None, source=None
):
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=play,
            context="I actually perform the printed Court trigger in its original source",
            trigger_confirmed=True,
            heat=1,
            target_actor=target,
            source_work=source,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    return identity


def buy(controls, rule):
    return controls.buy(
        PLAYER,
        str(uuid4()),
        state(controls.game).revision,
        rule,
        "I acquire this genuine printed Court Requisition",
    )["id"]


def test_native_queen_mark_consult_mid_real_decree_discipline_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    native(controls, "initialize")
    court = rules.court(state(game), current_ref(state(game), 2))
    queen = am(game, "The Queen")
    assert queen.bearer == current_ref(state(game), 2)
    native(
        controls,
        "mark:" + queen.id,
        kind=("status",),
        counterpart=("none",),
        instruction="",
        amount=("1",),
        roll=("none",),
    )
    assert higher(state(game), 2, 3) and not higher(original, 2, 3)
    before = state(game)
    bad = (OTHER, "not-the-queen", 900, before.revision, am(game, "The Doll").id, "doll")
    with pytest.raises(WorkflowError):
        controls.mark(*bad)
    assert state(game) == before
    game.dice.faces = (3, 4)
    native(
        controls,
        "play:red_queen_consult",
        heat=("1",),
        identity=("none",),
        gain=("0",),
        context="I consult the Court inside this actual original cockpit",
    )
    # The real source Action is discovered from its actual pending scene lock.
    with ledger.engine.connect() as c:
        lock = game.lock(c, 900)
        identity = lock["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), identity)
    pass_tags(game)
    native_choice(
        game,
        PLAYER,
        "red_queen_consult",
        options=(queen.id,),
        text="No member may deliberately damage the Cadre stores",
    )
    actual = state(game)
    assert not rules.get(actual, rules.CourtAM, queen.id).marked_event
    decree = rules.records(actual, rules.Decree)[-1]
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 5)
    target = current_ref(actual, 3)
    key = "actual-decree-breach-once"
    args = (
        PLAYER,
        key,
        actual.revision,
        decree.id,
        target,
        "I know her deliberate damage of the stores breaches my exact Decree",
    )
    result = controls.report_breach(*args)
    assert controls.report_breach(*args) == result
    breach = rules.get(state(game), rules.Breach, result["id"])
    case = next(x for x in state(game).role_punishments if x.source_work == breach.id)
    discipline(game, case.id, PLAYER, OTHER)
    final = state(game)
    assert rules.get(final, rules.Breach, breach.id).completed_event
    assert final.sheets["3"].heat == actual.sheets["3"].heat + 7
    assert controls.view(OTHER, breach.id)["source"]["account"] == args[-1]
    assert controls.view(PLAYER, identity)["source"]["completed_event"]
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, breach.id)
    with ledger.engine.connect() as c:
        prove_court(game, c, final, court.id)
        prove_am(game, c, final, queen.id)
    game.rebuild()
    assert state(game) == final


@pytest.mark.parametrize("faces,high", [((2, 3), False), ((5, 5), True)])
def test_consult_other_tiers_real_recall_queen_transfer_and_handler_advice_orders(
    ledger, tmp_path, monkeypatch, faces, high
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    identity = roll(game, worker, gateway, faces=faces)
    knight = am(game, "The Knight")
    fields = {"advice": knight.id} if high else {"queen": current_ref(state(game), 3).token}
    answer(
        game,
        PLAYER,
        "red_queen_consult",
        options=(knight.id,),
        text="A genuine high-result Decree" if high else "",
        fields=fields,
    )
    records = [x for x in rules.records(state(game), rules.Advice) if x.session == identity]
    assert len(records) == (1 if high else 4)
    for value in records:
        assert value.author == 1
        controls.answer_advice(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            value.id,
            "Follow the actual advice of " + rules.get(state(game), rules.CourtAM, value.am).role,
        )
        answer(game, PLAYER, "order_response", options=("obedient",))
    final = state(game)
    assert all(x.order for x in rules.records(final, rules.Advice) if x.session == identity)
    assert am(game, "The Queen").bearer == current_ref(final, 2 if high else 3)


def test_consort_deepening_personality_copy_and_traitor_actual_helpless_consumer(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    target = current_ref(state(game), 3)
    buy(controls, rules.PERSONALITY)
    result = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Consort").id,
        "bond",
        counterpart=target,
    )
    source = rules.get(state(game), rules.Mark, result["id"])
    assert depth(state(game), source.target, target) == 2
    copied = controls.copy_personality(
        PLAYER, str(uuid4()), state(game).revision, target, source.event
    )
    assert rules.get(state(game), rules.CourtAM, copied["id"]).person == target
    controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Traitor").id,
        "helpless",
        counterpart=target,
    )
    assert is_helpless(state(game), current_ref(state(game), 2), target)
    calls = game.dice.calls
    with pytest.raises(WorkflowError):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                context="The true existing Helpless consumer blocks me",
                trigger_confirmed=True,
                heat=0,
            ),
        )
    assert game.dice.calls == calls


@pytest.mark.parametrize(
    "faces,questions",
    [((2, 3), ("where",)), ((3, 4), ("where", "flinch", "void")), ((5, 5), tuple(rules.QUESTIONS))],
)
def test_panopticon_real_distant_private_answers_and_printed_reciprocals(
    ledger, tmp_path, monkeypatch, faces, questions
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    buy(controls, rules.PANOPTICON)
    game.leave_scene(OTHER, str(uuid4()), 900)
    canon = state(game)
    actor, target = current_ref(canon, 2), current_ref(canon, 3)
    context = controls.record_context(
        PLAYER,
        str(uuid4()),
        900,
        canon.revision,
        "distant",
        actor,
        target,
        "I actually observe her at a distance; she is not in my source scene",
    )["id"]
    identity = roll(
        game,
        worker,
        gateway,
        play="red_queen_panopticon",
        faces=faces,
        target=target,
        source=context,
    )
    answer(game, PLAYER, "red_queen_questions", options=questions)
    answer(
        game,
        OTHER,
        "red_queen_answers",
        fields={key: "PRIVATE_ACTUAL_ANSWER " + key for key in questions},
    )
    if faces == (2, 3):
        answer(game, OTHER, "red_queen_reciprocal", options=("ashamed",))
        answer(
            game,
            PLAYER,
            "red_queen_reciprocal_answer",
            fields={"ashamed": "My own actual reciprocal answer"},
        )
    elif faces == (5, 5):
        answer(game, OTHER, "red_queen_tag", flag=True, text="Obviously watching me")
        assert any(x.label == "Obviously watching me" for x in state(game).sheets["2"].tags)
    assert (
        controls.view(OTHER, identity)["source"]["replies"]["answer:where"]
        == "PRIVATE_ACTUAL_ANSWER where"
    )
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, context)
    assert target not in [
        x.actor for x in rules.get(state(game), rules.Session, identity).cast.roles
    ]


@pytest.mark.parametrize("faces", [(2, 3), (3, 4), (5, 5)])
def test_memory_categories_actual_linked_identity_removal_and_real_recall_consumer(
    ledger, tmp_path, monkeypatch, faces
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(controls)
    buy(controls, rules.MEMORY)
    before = state(game)
    actor, target = current_ref(before, 2), current_ref(before, 3)
    original = before.sheets["3"].identities[0]
    context = controls.record_context(
        OTHER,
        str(uuid4()),
        900,
        before.revision,
        "brain",
        actor,
        target,
        "The actual source body is restrained and her brain is being accessed",
    )["id"]
    identity = roll(
        game, worker, gateway, play="red_queen_memory", faces=faces, target=target, source=context
    )
    selected = am(game, "The Consort")
    answer(
        game,
        PLAYER,
        "red_queen_memory_category",
        options=("person",),
        text="The remembered instructor",
        fields={"am": selected.id, "years": "not_year"},
    )
    if faces == (5, 5):
        answer(
            game,
            ADMIN,
            "red_queen_memory_handler",
            options=("place",),
            text="The remembered training hall",
            fields={"years": "not_year"},
        )
    fields = {
        "memories0": "Her instructor taught her this original technique",
        "identities0": original.id,
    }
    if faces == (5, 5):
        fields.update(memories1="Her actual memory of that training hall", identities1=original.id)
    answer(game, OTHER, "red_queen_memory_links", fields=fields)
    final = state(game)
    losses = [x for x in rules.records(final, rules.Extraction) if x.session == identity]
    assert len(losses) == (2 if faces == (5, 5) else 1)
    assert original.id not in {x.id for x in final.sheets["3"].identities}
    assert len([x for x in final.sheets["3"].identities if x.name == "The Consort"]) == 1
    from girlframe.engine.m3_am_memory import can_recall

    assert not can_recall(final, target, losses[0].memories[0], learned_revision=before.revision)
    assert final.sheets["3"].permissions == before.sheets["3"].permissions
    with ledger.engine.connect() as c:
        for loss in losses:
            prove_extraction(game, c, final, loss.id)


def test_consort_actual_forced_flirt_child_real_tag_and_permission_restore(
    ledger, tmp_path, monkeypatch
):
    from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(controls)
    target = current_ref(state(game), 3)
    result = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Consort").id,
        "flirt",
        counterpart=target,
    )
    original = rules.get(state(game), rules.Mark, result["id"])
    assert original.work and not original.completed_event
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    game.dice.faces = (5, 5)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            context="I actually perform the Consort-required Flirt",
            trigger_confirmed=True,
            heat=1,
            target=3,
            source_work=original.id,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    game.roll(PLAYER, str(uuid4()), child)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="Actual limits",
    )
    answer(game, OTHER, "target_flirt", text="My actual response to her Flirt")
    answer(game, OTHER, "flirt_owe_tag", text="Actually acting like a Consort")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert rules.get(state(game), rules.Mark, original.id).completed_event
    assert any(x.label == "Actually acting like a Consort" for x in state(game).sheets["2"].tags)
    tick(worker, gateway, 5)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert gateway.values == gateway.original


def test_knight_actual_source_bound_assault_damages_original_asset(ledger, tmp_path, monkeypatch):
    import json

    from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
    from girlframe.engine.m3_battle_state import Declaration
    from girlframe.services.m3_battle import BattleService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    original = state(game)
    target = current_ref(original, 2)
    result = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        original.revision,
        am(game, "The Knight").id,
        "assault",
        counterpart=target,
    )
    source = rules.get(state(game), rules.Mark, result["id"])
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    battle = BattleService(ledger)
    data = battle.preview(OTHER, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    victim = next(x for x in data["actors"] if x["ref"] == target.model_dump(mode="json"))
    declaration = Declaration.model_validate_json(
        json.dumps(
            dict(
                play="all_out_assault",
                actor=actor["ref"],
                target=victim["ref"],
                attacking_asset=actor["assets"][0]["id"],
                target_asset=victim["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=victim["sha256"],
                account="The Knight actually strikes the Queen-selected target",
            )
        )
    )
    context = battle.propose(
        OTHER, str(uuid4()), data["revision"], 900, declaration, source_work=source.id
    )["id"]
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        context,
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="The actual source opening and range",
    )
    game.dice.faces = (5, 5)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="all_out_assault",
            context="I actually perform the required Knight assault",
            trigger_confirmed=True,
            heat=0,
            target_actor=target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            source_work=source.id,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    game.roll(OTHER, str(uuid4()), action)
    pass_tags(game)
    assert next(
        x for x in state(game).sheets["2"].assets if x.id == declaration.target_asset
    ).damaged
    assert game.inspect(OTHER, action)["state"] == "complete"
    assert rules.get(state(game), rules.Mark, source.id).completed_event


def test_doll_real_known_disobey_caps_final_result_preserving_raw_receipt(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    result = controls.mark(
        PLAYER, str(uuid4()), 900, state(game).revision, am(game, "The Doll").id, "doll"
    )
    root = game.issue_order(ADMIN, str(uuid4()), 900, 2, "Hold the actual assigned station")
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("disobey",))
    game.dice.faces = (6, 6)
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="I actually disobey the real instruction",
            trigger_confirmed=True,
            heat=0,
            order_id=root["order_id"],
            parent=root["action_id"],
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    game.roll(PLAYER, str(uuid4()), child)
    pass_tags(game)
    answer(game, ADMIN, "handler_disobey", flag=False)
    actual = game.inspect(PLAYER, child)
    assert actual["receipt"]["pre_total"] == 12 and actual["result"]["total"] <= 7
    assert actual["result"]["can_disobey"] is False and actual["state"] == "complete"
    assert rules.get(state(game), rules.Mark, result["id"]).used_action == child
    assert game.dice.calls == 1


def test_regiment_real_lower_rank_order_and_assigned_tag_double_modifier(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    buy(controls, rules.REGIMENT)
    assert not higher(state(game), 2, 3)
    result = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Knight").id,
        "order",
        instruction="Guard the actual assigned hatch",
    )
    issued = game.issue_order(PLAYER, str(uuid4()), 900, 3, "Guard the actual assigned hatch")
    assert rules.get(state(game), rules.Mark, result["id"]).order == issued["order_id"]
    tick(worker, gateway, 3)
    answer(game, OTHER, "order_response", options=("obedient",))
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    from girlframe.services.m3_red_queen import regiment_amount

    with ledger.engine.connect() as c:
        assert (
            regiment_amount(
                game, c, state(game), current_ref(state(game), 2), current_ref(state(game), 3), 1
            )
            == 2
        )
        assert (
            regiment_amount(
                game, c, state(game), current_ref(state(game), 2), current_ref(state(game), 3), -1
            )
            == -2
        )


@pytest.mark.parametrize("kind", ["girl", "npc", "city", "base"])
def test_actual_accusation_director_endorsement_and_real_typed_consequence(
    ledger, tmp_path, monkeypatch, kind
):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world import require_usable
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_red_queen_accusation import official_allegations
    from girlframe.services.m3_world import WorldService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    world = WorldService(MissionService(ledger))
    director = Npc(
        id="actual-source-director",
        name="Actual Foundation Director",
        jobs=("director",),
        cell=(0, 0),
        detail="An actual human-controlled Director holds this office",
        controller=1,
        revealed=True,
        employment="foundation",
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, director)
    director_ref = ActorRef(kind="npc", entity=director.id)
    if kind == "npc":
        target = Npc(
            id="actual-accused-npc",
            name="Actual official",
            jobs=("politician",),
            cell=(0, 0),
            detail="A real original human-controlled official",
            controller=1,
            revealed=True,
            employment="foundation",
        )
        world.npc(ADMIN, str(uuid4()), state(game).revision, target)
        identifier = target.id
        effect = "npc_tag"
        detail = {"label": "Officially accused of negligence"}
        ref = ActorRef(kind="npc", entity=target.id)
    elif kind == "girl":
        identifier = "3"
        effect = "punishment"
        detail = {"kind": "stimulant_injection"}
        ref = current_ref(state(game), 3)
    else:
        location = next(
            x
            for x in state(game).world.locations
            if x.kind == kind and x.allegiance == "foundation" and x.operational
        )
        identifier = location.id
        effect = "administrative_closure"
        detail = {"account": "Actual Director administratively closes this facility pending review"}
        ref = identifier
    purchase = buy(controls, rules.ACCUSATION)
    before = state(game)
    result = controls.accuse(
        PLAYER,
        "levy-accusation-once",
        before.revision,
        purchase,
        kind,
        identifier,
        "The actual subject has committed a formally alleged misdeed",
        "I request this exact genuine supported consequence",
        consequence_kind=effect,
        consequence_detail=detail,
        director=director_ref,
    )
    source = rules.get(state(game), rules.Accusation, result["id"])
    assert source.director == director_ref and source.director_controller == 1
    assert not rules.held(state(game), current_ref(state(game), 2), rules.ACCUSATION)
    assert official_allegations(state(game), kind, ref)[0]["allegation"] == source.allegation
    unchanged = state(game)
    with pytest.raises(WorkflowError):
        controls.endorse(OTHER, str(uuid4()), unchanged.revision, source.id)
    assert state(game) == unchanged
    args = (ADMIN, "true-director-endorses-once", unchanged.revision, source.id)
    endorsed = controls.endorse(*args)
    assert controls.endorse(*args) == endorsed
    if kind == "girl":
        case = next(x for x in state(game).role_punishments if x.source_work == source.id)
        discipline(game, case.id, PLAYER, OTHER)
        assert state(game).sheets["3"].heat == before.sheets["3"].heat + 7
    elif kind == "npc":
        npc = next(x for x in state(game).world.npcs if x.id == identifier)
        assert npc.tags[-1].label == detail["label"]
        assert npc.tags[-1].giver_entity == director_ref.model_dump_json()
    else:
        actual = next(x for x in state(game).world.locations if x.id == identifier)
        assert not actual.operational and actual.condition == location.condition
        with pytest.raises(ValueError):
            require_usable(state(game).world, actual.cell)
    assert rules.get(state(game), rules.Accusation, source.id).completed_event
    assert controls.view(PLAYER, source.id)["source"]["director"] == director_ref.model_dump(
        mode="json"
    )
    with pytest.raises(WorkflowError):
        controls.view(OTHER, source.id)


def test_low_real_npc_memory_genuine_new_tag_restoration_and_owned_am_assignment(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_am_memory import can_recall
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(controls)
    missions = MissionService(ledger)
    world = WorldService(missions)
    for name, job in (("real-memory-npc", "politician"), ("real-memory-director", "director")):
        world.npc(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            Npc(
                id=name,
                name=name,
                jobs=(job,),
                cell=(0, 0),
                detail="Actual source human-controlled person",
                controller=1,
                revealed=True,
                employment="foundation",
            ),
        )
    target = ActorRef(kind="npc", entity="real-memory-npc")
    director = ActorRef(kind="npc", entity="real-memory-director")
    cast_service = CastService(ActorService(missions))
    view = cast_service.view(ADMIN, 900)
    cast_service.change(
        ADMIN, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", target
    )
    buy(controls, rules.MEMORY)
    before = state(game)
    context = controls.record_context(
        ADMIN,
        str(uuid4()),
        900,
        before.revision,
        "brain",
        current_ref(before, 2),
        target,
        "This actual NPC body is restrained and her brain is actually accessed",
    )["id"]
    action = roll(
        game, worker, gateway, play="red_queen_memory", faces=(2, 3), target=target, source=context
    )
    answer(
        game,
        PLAYER,
        "red_queen_memory_category",
        options=("person",),
        text="The actual forgotten colleague",
        fields={"am": am(game, "The Consort").id, "years": "not_year"},
    )
    answer(
        game,
        ADMIN,
        "red_queen_memory_links",
        fields={"memories0": "The actual NPC memory of her colleague", "identities0": ""},
    )
    loss = next(x for x in rules.records(state(game), rules.Extraction) if x.session == action)
    assert not can_recall(state(game), target, loss.memories[0], learned_revision=before.revision)
    assert not loss.identities and set(state(game).sheets) == set(before.sheets)
    assert not rules.assigned(state(game), target)
    tick(worker, gateway, 5)
    purchase = buy(controls, rules.ACCUSATION)
    allegation = controls.accuse(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        purchase,
        "npc",
        target.entity,
        "The actual official mishandled records",
        "Give the actual associated reminder Tag",
        consequence_kind="npc_tag",
        consequence_detail={"label": "Her forgotten colleague handled these records"},
        director=director,
    )
    controls.endorse(ADMIN, str(uuid4()), state(game).revision, allegation["id"])
    actual = rules.get(state(game), rules.Accusation, allegation["id"])
    tag = next(x for x in state(game).world.npcs if x.id == target.entity).tags[-1]
    queen = am(game, "The Queen")
    controls.restore_memory(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        loss.id,
        actual.endorsement_event,
        tag.id,
        queen.id,
        "This actual new Tag is associated with the genuinely lost colleague memory",
    )
    final = state(game)
    assert can_recall(final, target, loss.memories[0], learned_revision=before.revision)
    assert rules.get(final, rules.CourtAM, queen.id).bearer == target
    assert any(
        x.label == "The Queen"
        for x in next(x for x in final.world.npcs if x.id == target.entity).tags
    )
    assert set(final.sheets) == set(before.sheets)


def test_judgement_actual_handler_watching_real_tag_then_status_reduction_once(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    buy(controls, rules.PANOPTICON)
    buy(controls, rules.JUDGEMENT)
    cast_service = CastService(ActorService(MissionService(ledger)))
    view = cast_service.view(ADMIN, 900)
    cast_service.change(
        ADMIN,
        str(uuid4()),
        900,
        view["game_revision"],
        view["cast_revision"],
        "join",
        active_handler(state(game)),
    )
    canon = state(game)
    actor, target = current_ref(canon, 2), current_ref(canon, 3)
    watched = controls.record_context(
        ADMIN,
        str(uuid4()),
        900,
        canon.revision,
        "watching",
        actor,
        target,
        "The actual Handler is watching this real Tag-giving",
    )["id"]
    observation = controls.record_context(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        "distant",
        actor,
        target,
        "I actually observe her from the far end of the same broad scene",
    )["id"]
    roll(
        game,
        worker,
        gateway,
        play="red_queen_panopticon",
        faces=(3, 4),
        target=target,
        source=observation,
    )
    answer(
        game,
        PLAYER,
        "red_queen_questions",
        options=(),
        fields={"tag": "Under actual Court scrutiny"},
    )
    tick(worker, gateway, 5)
    tag = next(x for x in state(game).sheets["3"].tags if x.label == "Under actual Court scrutiny")
    before = state(game)
    args = (PLAYER, "actual-judgement-once", before.revision, watched, tag.id)
    result = controls.judge(*args)
    assert controls.judge(*args) == result
    assert higher(state(game), 2, 3) and not higher(before, 2, 3)
    with pytest.raises(WorkflowError):
        controls.judge(PLAYER, str(uuid4()), state(game).revision, watched, tag.id)


def test_personality_actual_copy_advice_optional_and_signed_real_roll_modifier(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, inside=False)
    initialize(controls)
    buy(controls, rules.PERSONALITY)
    target = current_ref(state(game), 3)
    marked = controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        am(game, "The Consort").id,
        "bond",
        counterpart=target,
    )
    source = rules.get(state(game), rules.Mark, marked["id"])
    copied = controls.copy_personality(
        PLAYER, str(uuid4()), state(game).revision, target, source.event
    )["id"]
    advice = controls.request_advice(PLAYER, str(uuid4()), 900, state(game).revision, copied)["id"]
    controls.answer_advice(
        OTHER,
        str(uuid4()),
        state(game).revision,
        advice,
        "My own optional advice is to remain composed",
    )
    assert not rules.get(state(game), rules.Advice, advice).order
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            context="I actually Flirt against this original copied person",
            trigger_confirmed=True,
            heat=0,
            target=3,
        ),
    )["action_id"]
    controls.mark(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        copied,
        "modifier",
        counterpart=target,
        amount=1,
        roll=action,
    )
    tick(worker, gateway, 3)
    game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="My own actual reply to the Flirt")
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        from girlframe.services.m3_red_queen import prove_personality_modifier

        assert prove_personality_modifier(game, c, state(game), actual) == 1
        assert actual["data"]["receipt"]["pre_total"] == 7
        assert actual["data"]["result"]["total"] == 8
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_consult_all_advice_owned_orders_complete_original_play(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    identity = roll(game, worker, gateway, faces=(2, 3))
    receipt = game.inspect(PLAYER, identity)["receipt"]
    knight = am(game, "The Knight")
    native_choice(
        game,
        PLAYER,
        "red_queen_consult",
        options=(knight.id,),
        text="",
        queen=(current_ref(state(game), 3).token,),
    )
    records = [x for x in rules.records(state(game), rules.Advice) if x.session == identity]
    assert len(records) == 4
    assert {x.am for x in records} == {
        x.id for x in rules.assigned(state(game), current_ref(state(game), 2))
    }
    assert am(game, "The Queen").bearer == current_ref(state(game), 3)
    for index, value in enumerate(records):
        assert not rules.get(state(game), rules.Session, identity).completed_event
        before = state(game)
        with pytest.raises(WorkflowError, match="actual requested human"):
            controls.answer_advice(PLAYER, str(uuid4()), before.revision, value.id, "Forged")
        assert state(game) == before
        instruction = "Follow actual advice from " + rules.get(before, rules.CourtAM, value.am).role

        async def give_advice(advice_id=value.id, text=instruction):
            interaction = current(1, int(uuid4().int % 1000000000))
            await interaction.response.defer(ephemeral=True)
            await open_red_queen(interaction, controls, advice_id)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert not await form.interaction_check(current(2))
            form.values["instruction"] = text
            submitted = current(1, int(uuid4().int % 1000000000))
            await form.confirm.callback(submitted)
            assert form.completed, submitted.edit_original_response.call_args_list

        asyncio.run(give_advice())
        advice = rules.get(state(game), rules.Advice, value.id)
        assert advice.order and advice.instruction == instruction
        with ledger.engine.connect() as c:
            table = t.m2["m2_orders"]
            row = c.execute(table.select().where(table.c.id == advice.order)).mappings().one()
            body = json.loads(row["body_json"])
            assert row["issuer_id"] == "1" and row["target_id"] == "2"
            assert row["state"] == "awaiting_response"
            assert body["red_queen"]["id"] == value.id and body["text"] == instruction
        if index < len(records) - 1:
            before_pending = state(game)
            with pytest.raises(WorkflowError, match="preceding Court Order"):
                controls.answer_advice(
                    ADMIN,
                    str(uuid4()),
                    before_pending.revision,
                    records[index + 1].id,
                    "Do not bypass her unanswered Order",
                )
            assert state(game) == before_pending
        answer(game, PLAYER, "order_response", options=("obedient",))
        assert game.inspect(PLAYER, identity)["receipt"] == receipt
        assert game.dice.calls == 1
        if index < len(records) - 1:
            assert game.inspect(PLAYER, identity)["state"] != "complete"
    final = state(game)
    assert rules.get(final, rules.Session, identity).completed_event
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    orders = [rules.get(final, rules.Advice, x.id).order for x in records]
    assert len(set(orders)) == 4
    with ledger.engine.connect() as c:
        table = t.m2["m2_orders"]
        rows = c.execute(table.select().where(table.c.id.in_(orders))).mappings().all()
        assert len(rows) == 4 and all(x["state"] == "followed" for x in rows)
    assert controls.view(PLAYER, identity)["source"]["completed_event"]
    game.rebuild()
    assert state(game) == final
