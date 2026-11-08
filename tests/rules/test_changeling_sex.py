"""Actual remote Girl source and distinct no-roll AM normal; deferred P1 evidence."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_changeling import buy, define, ready, roll
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current as interaction
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_changeling as mental
from girlframe.engine import m3_changeling_sex as rules
from girlframe.engine import m3_gender_designation as gender
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import p1_unrolled_sex as unrolled
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.m3_changeling_sex import ChangelingSexService, prove
from girlframe.services.m3_gender_designation import GenderDesignationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_pr import HandlerPRService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_oldgen_sex import OldgenSexService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_unrolled_sex import give as give_unrolled
from girlframe.services.p1_unrolled_sex import prove as prove_unrolled

ledger = ledger_fixture


def test_actual_remote_oldgen_source_keeps_real_consent_roll_cost_effects_and_retry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            mental.BLANK,
            mental.STRINGS,
            mental.FINGERS,
            mental.MINDFUCK,
            rules.RULES["OLDGEN"],
        ),
    )
    buy(game, controls, mental.MINDFUCK)
    roll(game, worker, gateway, source=define(game, controls))
    tick(worker, gateway, 5)
    original_permissions = {key: value.copy() for key, value in gateway.values.items()}
    caster, target = current_ref(state(game), 2), current_ref(state(game), 3)
    node = next(
        value
        for value in mental.records(state(game), mental.String)
        if value.actor == caster and value.spent_event is None
    )
    MovementService(game).move(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        (1, 0),
        account="My real original body moves away before this actual remote initiation",
    )
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        node.id,
        "sex",
        "I spend the real String to initiate mental Sex with the actual original other person",
    )["id"]
    controls.counter(OTHER, str(uuid4()), state(game).revision, used, "pass")
    controls.consent(OTHER, str(uuid4()), state(game).revision, used, True)
    bridge = ChangelingSexService(game)
    with pytest.raises(WorkflowError):
        bridge.view(ADMIN, used)
    args = (
        PLAYER,
        "one-real-remote-source",
        state(game).revision,
        used,
        900,
        "My real Oldgen source retains its own genuine invitation and effects",
    )
    linked = bridge.start(*args)
    assert bridge.start(*args) == linked
    original = OldgenSexService(game)
    # Initial psychic consent does not manufacture this downstream source response.
    with pytest.raises(WorkflowError):
        original.respond(
            PLAYER,
            str(uuid4()),
            linked["session"],
            state(game).revision,
            True,
            "I cannot answer for the other actual human",
        )
    original.respond(
        OTHER,
        str(uuid4()),
        linked["session"],
        state(game).revision,
        True,
        "My actual separate response to this original Oldgen source",
    )
    before = state(game)
    identity = next(value.id for value in before.sheets["2"].identities if not value.marked)
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="oldgen_sex",
            context="Our actual consented mental source at distinct cells",
            trigger_confirmed=True,
            source_work=linked["session"],
            target_actor=target,
            identity=identity,
            gain=1,
            heat=1,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    row = next(value for value in game.choices(PLAYER) if value["kind"] == "oldgen_sex_effects")
    response = (
        PLAYER,
        "actual-remote-oldgen-effects",
        row["id"],
        row["revision"],
        ChoiceAnswer(options=("tag", "status"), fields={"tag": "Trusted at a distance"}),
    )
    game.respond(*response)
    game.respond(*response)
    canon = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(value for value in canon.sheets["2"].identities if value.id == identity).marked
    assert canon.sheets["2"].heat == before.sheets["2"].heat
    assert (
        next(
            value for value in canon.sheets["3"].tags if value.label == "Trusted at a distance"
        ).giver_actor
        == caster
    )
    assert game.dice.calls == 2  # Actual Blank Slate and actual Oldgen Sex, no extra remote roll.
    with ledger.engine.connect() as c:
        link = prove(game, c, canon, linked["id"])
        assert link.completed_event and link.action == action and link.performer == caster
    assert mental.get(canon, used).sex_outcome == "performed"
    assert mental.get(canon, used).completed_event
    assert mental.record(canon, mental.String, node.id).spent_by == used
    tick(worker, gateway, 5)
    assert gateway.values == original_permissions


def am_ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="AM", frame=mental.FRAME)
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            mental.STRINGS,
            mental.FINGERS,
            mental.WEB,
            mental.MINDFUCK,
            rules.RULES["AM"],
            ordinary.RULE,
            gender.RULE,
        ),
    )
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    with store.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.world = initial()
        canon.sheets["2"].permissions = 10
        game.event(c, 1, str(uuid4()), "synthetic.original_AM_body_and_resources", canon)
    npc = Npc(
        id="original-human-civilian",
        name="Actual civilian",
        jobs=("civilian",),
        controller=3,
        cell=(0, 0),
        revealed=True,
    )
    missions = MissionService(store)
    WorldService(missions).npc(ADMIN, str(uuid4()), state(game).revision, npc)
    cast = CastService(ActorService(missions))
    current = cast.view(OTHER, 900)
    target = ActorRef(kind="npc", entity=npc.id)
    cast.change(
        OTHER, str(uuid4()), 900, current["game_revision"], current["cast_revision"], "join", target
    )
    controls = ChangelingService(game)
    controls.body_fact(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 2),
        "girl",
        "Actual original AM physical brain in her real original mechanical body",
    )
    controls.body_fact(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        "human_npc",
        "I witness this actual original civilian's biological body and brain",
    )
    buy(game, controls, mental.WEB)
    buy(game, controls, mental.MINDFUCK)
    access = controls.access(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        current_ref(state(game), 2),
        target,
        "unexpecting",
        "I witness actual close bodily access to the real brain while this "
        "civilian does not expect it",
    )["id"]
    controls.implant(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        access,
        "I actually implant the three source Strings through that original bodily access",
    )
    return game, GameWorker(game), Gateway(), controls, target


def designate_actual_animal(game):
    HandlerOrdinaryService(game.store).record_session(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual AM legal-source Session",
        "The actual original facilitator begins this Session",
    )
    pr = HandlerPRService(game.store)
    event = pr.plan(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "Actual Foundation media event",
        "The original Handler and AM actually host and participate in a Foundation feature",
        (current_ref(state(game), 2),),
    )["id"]
    pr.activity(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        "I actually host the Foundation feature",
        hosting=True,
    )
    pr.activity(
        PLAYER,
        str(uuid4()),
        event,
        state(game).revision,
        "My actual original AM role actually participates in the public feature",
    )
    pr.submit_result(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        "The actual original participants have performed the planned public event",
    )
    result = pr.resolve(
        ADMIN,
        str(uuid4()),
        event,
        state(game).revision,
        True,
        "The actual authorized original adjudicator records the successful Foundation result",
    )
    law = GenderDesignationService(game.store)
    acquisition = law.buy(
        ADMIN,
        str(uuid4()),
        result["award"],
        state(game).revision,
        "Spend this actual earned and held Award on Gender Designation Request",
    )["id"]
    actor = current_ref(state(game), 2)
    law.designate(
        ADMIN,
        str(uuid4()),
        acquisition,
        state(game).revision,
        (actor,),
        "animal",
        "The actual original Handler legally designates this real original AM an Animal",
    )
    return acquisition


def test_actual_am_npc_remote_no_extra_roll_requires_separate_role_performance_not_consent(
    ledger, tmp_path, monkeypatch
):
    game, _, _, controls, target = am_ready(ledger, tmp_path, monkeypatch)
    caster = current_ref(state(game), 2)
    designate_actual_animal(game)
    assert gender.current(state(game), caster).gender == "animal"
    nodes = [
        value
        for value in mental.records(state(game), mental.String)
        if value.actor == caster and value.subject.actor == target
    ]
    assert len(nodes) == 3
    MovementService(game).move(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        caster,
        (1, 0),
        account="I actually leave the original civilian before using mental contact",
    )
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[0].id,
        "sex",
        "I initiate actual remote Sex through the existing physical brain String",
    )["id"]
    controls.consent(OTHER, str(uuid4()), state(game).revision, used, True)
    bridge = ChangelingSexService(game)
    linked = bridge.start(
        PLAYER,
        "actual-am-no-extra-roll-source",
        state(game).revision,
        used,
        900,
        "A real AM source with the original civilian; no counterfeit Girl Play",
    )
    source = rules.am_source(state(game), linked["session"])
    assert source.phase == "invited" and source.action is None
    bridge.am_respond(
        OTHER,
        str(uuid4()),
        state(game).revision,
        source.id,
        True,
        "My actual separate civilian-role voluntary source answer",
    )
    assert rules.am_source(state(game), source.id).effect_event is None
    bridge.am_perform(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        source.id,
        caster,
        "My actual original AM role participates in the performed psychic scene",
    )
    assert rules.am_source(state(game), source.id).phase == "accepted"
    assert mental.get(state(game), used).sex_outcome is None
    with pytest.raises(WorkflowError):
        bridge.am_perform(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            source.id,
            target,
            "I cannot fabricate the civilian controller's actual performed-scene account",
        )
    bridge.am_perform(
        OTHER,
        str(uuid4()),
        state(game).revision,
        source.id,
        target,
        "My actual original civilian role also participated in this performed psychic scene",
    )
    pending = state(game)
    assert rules.am_source(pending, source.id).phase == "effects"
    assert rules.get(pending, linked["id"]).completed_event is None
    assert mental.get(pending, used).sex_outcome is None
    gift = next(value for value in unrolled.gifts(pending) if value.source == source.id)
    assert gift.source_kind == "changeling_am" and gift.animal == caster and gift.target == target
    inbox = InboxService(ledger)
    own = next(
        item
        for item in inbox.items(PLAYER)
        if item.task == "m3_changeling_sex" and item.identity == linked["id"]
    )
    waiting = next(
        item
        for item in inbox.items(OTHER)
        if item.task == "m3_changeling_sex" and item.identity == linked["id"]
    )
    assert own.incoming and own.state == "pending"
    assert not waiting.incoming and waiting.state == "waiting"
    assert not any(
        item.task == "m3_changeling_sex" and item.identity == linked["id"]
        for item in inbox.items(ADMIN)
    )
    with pytest.raises(WorkflowError):
        bridge.view_am(ADMIN, source.id)
    with pytest.raises(WorkflowError):
        give_unrolled(
            game,
            ADMIN,
            str(uuid4()),
            gift.id,
            pending.revision,
            "The unrelated Handler cannot author the Animal's source Tag",
        )
    assert state(game).model_dump_json() == pending.model_dump_json()
    other_view = bridge.view_am(OTHER, source.id)
    assert other_view["unrolled_gender"][0]["state"] == "owed"
    assert other_view["unrolled_gender"][0]["waiting"]
    assert not other_view["unrolled_gender"][0]["pending"]

    async def native_gift():
        current = interaction(2, uuid4().int % 1000000000)
        current.channel_id = 999  # Private durable source reopen needs no new scene.
        await current.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(current, own)
        form = current.edit_original_response.call_args.kwargs["view"]
        assert form.owner == 2 and any(field.key == "gift" for field in form.fields)
        form.values.update(gift=(gift.id,), tag="PRIVATE_REAL_ANIMAL_GIFT Original partner")
        response = interaction(2, uuid4().int % 1000000000)
        response.channel_id = 999
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(native_gift())
    canon = state(game)
    given = next(value for value in unrolled.gifts(canon) if value.id == gift.id)
    with ledger.engine.connect() as c:
        assert prove_unrolled(game, c, canon, gift.id) == given
    tag = next(
        value
        for npc in canon.world.npcs
        if npc.id == target.entity
        for value in npc.tags
        if value.id == given.tag
    )
    assert tag.label == "PRIVATE_REAL_ANIMAL_GIFT Original partner"
    assert ActorRef.model_validate_json(tag.giver_entity) == caster
    completed_view = bridge.view_am(OTHER, source.id)
    assert completed_view["unrolled_gender"][0]["state"] == "given"
    assert completed_view["unrolled_gender"][0]["tag_label"] == tag.label
    assert not completed_view["unrolled_gender"][0]["waiting"]
    assert rules.am_source(canon, source.id).phase == "complete"

    async def private_completed_reopen():
        from girlframe.discord_adapter.ledger import clean

        item = next(
            item
            for item in inbox.items(OTHER)
            if item.task == "m3_changeling_sex" and item.identity == linked["id"]
        )
        assert item.state == "established" and not item.incoming
        current = interaction(3, uuid4().int % 1000000000)
        current.channel_id = 999
        await current.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(current, item)
        history = current.edit_original_response.call_args.kwargs["view"]
        text = "".join(page.body for page in history.pages)
        assert clean(tag.label) in text and "Mandatory Animal Tag given" in text

    asyncio.run(private_completed_reopen())
    assert len([value for value in rules.performances(canon) if value.source == source.id]) == 2
    assert (
        mental.get(canon, used).sex_outcome == "performed"
        and mental.get(canon, used).action is None
    )
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(sa.func.count())
            .select_from(t.m2["m2_actions"])
            .where(t.m2["m2_actions"].c.campaign_id == ledger.campaign_id)
        )
    # A different real String may initiate a genuinely declined source; consumption persists.
    declined = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[1].id,
        "sex",
        "A separate actual initiation, owned by its actual counterpart",
    )["id"]
    controls.consent(OTHER, str(uuid4()), state(game).revision, declined, False)
    assert mental.get(state(game), declined).sex_outcome == "declined"
    assert mental.get(state(game), declined).completed_event
    assert mental.record(state(game), mental.String, nodes[1].id).spent_by == declined
