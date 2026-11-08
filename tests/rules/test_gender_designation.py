"""Actual legal assignments reach ordinary Orders, partner Tags, intimacy and discipline."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_handler_ordinary import finish_keep, mark
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_punishment_service import submit

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.engine import m3_gender_designation as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_mockingbird as mockingbird
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_gender_designation import GenderDesignationService, paid
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_mockingbird_plays import MockingbirdService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def interaction(owner=1, channel=900):
    value = current(owner, int(uuid4().int % 1000000000))
    value.channel_id = channel
    return value


def acquire(game):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def run():
        first = interaction()
        await first.response.defer(ephemeral=True)
        await open_advancement(first, HandlerAdvancementService(game.store), award.id)
        view = first.edit_original_response.call_args.kwargs["view"]
        more = next(x for x in view.children if isinstance(x, AcquireMore))
        second = interaction()
        await second.response.defer(ephemeral=True)
        await more.callback(second)
        chooser = second.edit_original_response.call_args.kwargs["view"]
        chooser.values.update(advancement=("gender",))
        third = interaction()
        await chooser.confirm.callback(third)
        assert chooser.completed, third.edit_original_response.call_args
        form = third.edit_original_response.call_args.kwargs["view"]
        form.values.update(award=(award.id,), account="PRIVATE_LEGAL_SOURCE actual held Award")
        fourth = interaction()
        await form.confirm.callback(fourth)
        assert form.completed, fourth.edit_original_response.call_args

    asyncio.run(run())
    return rules.acquisitions(state(game))[0]


def assign(service, acquisition, refs, gender):
    return service.designate(
        ADMIN,
        str(uuid4()),
        acquisition.id,
        state(service.game).revision,
        tuple(refs),
        gender,
        "PRIVATE_LEGAL_ASSIGNMENT " + gender,
    )


def new_scene(game, channel):
    game.close_scene(ADMIN, str(uuid4()), channel - 1)
    game.bind_scene(ADMIN, str(uuid4()), channel)
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), channel)


def spoken_no_native(service, man, scene, revision, account):
    async def run():
        inbox = InboxService(service.store)
        law = rules.current(state(service.game), current_ref(state(service.game), 2))
        item = next(
            x
            for x in inbox.items(PLAYER)
            if x.task == "m3_gender_designation" and x.identity == law.id
        )
        start = interaction(2, 901)
        await start.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(start, item)
        select = start.edit_original_response.call_args.kwargs["view"]
        select.values.update(scene=(scene,))
        next_step = interaction(2, 901)
        await select.confirm.callback(next_step)
        assert select.completed, next_step.edit_original_response.call_args
        form = next_step.edit_original_response.call_args.kwargs["view"]
        form.values.update(man=(man.token,), account=account)
        final = interaction(2, 901)
        await form.confirm.callback(final)
        assert form.completed, final.edit_original_response.call_args
        return (PLAYER, str(final.id), revision, scene, man, account)

    return asyncio.run(run())


def test_actual_rolled_man_marking_pair_owns_native_protected_slot_conversion(
    ledger, tmp_path, monkeypatch
):
    """Deferred real roll → actual Pair-owned conversion → genuine Sex consequence."""
    from test_bonded import actual_man_game
    from test_intracadre_marriage import FOUR

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.engine import m3_bonded as bonded
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_bonded import original_pair
    from girlframe.services.m3_gender_designation import prove_man_paired

    game, worker, gateway, _ = actual_man_game(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(*bonded.RULES, ordinary.RULE, rules.RULE, mockingbird.SEX),
    )
    gender = GenderDesignationService(ledger)
    acquisition = rules.acquisitions(state(game))[0]
    assign(gender, acquisition, (current_ref(state(game), 3),), "man")
    before = state(game)
    man, owner = current_ref(before, 3), current_ref(before, 2)
    with ledger.engine.connect() as c:
        assert original_pair(game, c, before, owner)[0] == man
    # Only prior ordinary Tag context is synthetic; the law/source/dice/choice are genuine.
    with ledger.transaction() as c:
        event = str(uuid4())
        actual = mockingbird.give_tag(
            state(game),
            profiles(c, ledger.campaign_id),
            owner,
            man,
            "Actual rolled Paired meaning",
            "rolled-man-paired-tag",
            event,
            (2, 3),
        )
        game.event(
            c, 3, str(uuid4()), "synthetic.prior_observed_ordinary_Tag", actual, event_id=event
        )
    trigger = MockingbirdService(game).propose(
        OTHER, str(uuid4()), 900, man, SEX, (owner,), "Our actual mutually performed intimacy"
    )
    MockingbirdService(game).attest(PLAYER, str(uuid4()), trigger["id"], owner, True)
    game.dice = Dice((2, 3))
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            heat=0,
            context="Actual original native Sex source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    original_receipt = game.inspect(OTHER, action)["receipt"]
    assert original_receipt["faces"] == [2, 3] and game.dice.calls == 1
    for who in (PLAYER, FOUR, ADMIN):
        answer(game, who, "tag_window", options=("pass",))
    paired_before = next(
        x.model_copy(deep=True) for x in state(game).sheets["2"].identities if x.paired
    )
    answer(game, OTHER, "tag_window", options=("gender_man",), denied=("rolled-man-paired-tag",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "gender_partner_paired")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), choice["id"], choice["revision"], ChoiceAnswer(options=("no",))
        )
    assert not any(x["kind"].startswith("mockingbird_sex") for x in game.choices(OTHER))
    with ledger.engine.connect() as c:
        assert game.action(c, action)["data"]["result"]["total"] == 11

    async def convert_native():
        interaction_value = interaction(3, 900)
        await interaction_value.response.defer(ephemeral=True)
        await open_choice(interaction_value, game, choice["id"])
        form = interaction_value.edit_original_response.call_args.kwargs["view"]
        form.values.update(convert=("yes",))
        response = current(3, 89500)
        response.channel_id = 900
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(convert_native())
    game.respond(OTHER, "89500", choice["id"], choice["revision"], ChoiceAnswer(options=("yes",)))
    actual = state(game)
    paired = next(x for x in actual.sheets["2"].identities if x.id == paired_before.id)
    assert paired.name == "Actual rolled Paired meaning" and paired.slot == paired_before.slot
    assert paired.protected == paired_before.protected and paired.paired
    assert paired.marked == (paired.id in actual.sheets["2"].sedation_locked)
    assert not any(x.id == "rolled-man-paired-tag" for x in actual.sheets["2"].tags)
    work = rules.paired_works(actual)[0]
    with ledger.engine.connect() as c:
        proved, decision = prove_man_paired(game, c, actual, work.id)
        assert proved.marker == man and decision and decision.convert
    assert gender.menu(PLAYER, work.id)["phase"] == "converted"
    with pytest.raises(WorkflowError):
        gender.menu(ADMIN, work.id)
    # The original high source still owes its genuine physiological consequence.
    with ledger.engine.connect() as c:
        asset = next(
            x
            for x in resolve(actual, owner, profiles(c, ledger.campaign_id)).assets
            if x.family == "girl" and not x.void
        )
    answer(game, OTHER, "mockingbird_sex_infect", fields={"asset": asset.id})
    answer(
        game,
        PLAYER,
        "mockingbird_sex_rewrite",
        text="Actual original Girl Asset rewritten by the Void",
    )
    tick(worker, gateway, 5)
    assert game.inspect(OTHER, action)["state"] == "complete"
    assert game.inspect(OTHER, action)["receipt"] == original_receipt and game.dice.calls == 1
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).void


def test_actual_three_legal_categories_orders_partner_tag_sex_reassignment_and_punishment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE, mockingbird.SEX)
    )
    service = GenderDesignationService(ledger)
    initial = state(game)
    actor, man = current_ref(initial, 2), current_ref(initial, 3)
    source = acquire(game)
    assert awards.awards(state(game))[0].acquired_rule == rules.RULE
    with ledger.engine.connect() as c:
        assert paid(game, c, state(game), source.id) == source
    assign(service, source, (actor,), "animal")
    assign(service, source, (man,), "man")
    assert state(game).order == initial.order
    assert rules.presentation(state(game), man) == dict(legal_gender="man", legal_pronouns="he/him")
    assert rules.presentation(state(game), actor)["legal_pronouns"] is None
    with pytest.raises(WorkflowError):
        service.designate(
            OTHER,
            str(uuid4()),
            source.id,
            state(game).revision,
            (actor,),
            "woman",
            "Another person cannot assign the Cadre",
        )

    # The naturally lower Girl gives this actual Animal an otherwise-invalid superior Order.
    assert initial.order.index(2) < initial.order.index(3)
    order = game.issue_order(
        OTHER, str(uuid4()), 900, 2, "Actual directed order to the legal Animal"
    )
    tick(worker, gateway)
    answer(game, PLAYER, "order_response", options=("disobey",))
    assert not rules.speeches(state(game))  # Disobey is not invented spoken No.
    game.dice = Dice((4, 5))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="Actual Animal refusal",
            trigger_confirmed=True,
            heat=0,
            order_id=order["order_id"],
            parent=order["action_id"],
            witnessed=False,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_disobey",
        options=("tag_heat",),
        number=2,
        text="PRIVATE_PARTNER_TAG actual defiance",
    )
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, order["action_id"])["state"] == "complete"
    partner_tag = next(
        x.id for x in state(game).sheets["2"].tags if x.label.startswith("PRIVATE_PARTNER_TAG")
    )

    # Ordinary marking is preserved; this source Tag now needs the partner's repeated response.
    marked = mark(game, worker, gateway, 900, partner_tag)
    finish_keep(game, worker, gateway, marked)
    tick(worker, gateway, 4)
    new_scene(game, 901)
    assert next(x for x in state(game).sheets["2"].tags if x.id == partner_tag).marked

    # Genuine mutually attested performed intimacy. Low dice become11 only after the one Tag choice.
    source_sex = MockingbirdService(game)
    trigger = source_sex.propose(
        OTHER,
        str(uuid4()),
        901,
        man,
        SEX,
        (actor,),
        "Actual original participants' already-performed intimacy",
    )
    source_sex.attest(PLAYER, str(uuid4()), trigger["id"], actor, True)
    game.dice = Dice((2, 3))
    play = game.begin(
        OTHER,
        str(uuid4()),
        901,
        state(game).sheets["3"].revision,
        PlayInput(
            play=SEX,
            source_work=trigger["id"],
            context="Actual source-owned Sex",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    before_tags = game.inspect(OTHER, play)
    assert before_tags["receipt"]["faces"] == [2, 3]
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, OTHER, "tag_window", options=("gender_man",), denied=(partner_tag,))
    with ledger.engine.connect() as c:
        assert game.action(c, play)["data"]["result"]["total"] == 11
    assert not any(x["kind"].startswith("mockingbird_sex") for x in game.choices(OTHER))
    old_identity = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(
        game, PLAYER, "gender_partner_tag_resolution", options=("embrace",), denied=(old_identity,)
    )
    assert not any(x.id == partner_tag for x in state(game).sheets["2"].tags)
    assert any(x.name.startswith("PRIVATE_PARTNER_TAG") for x in state(game).sheets["2"].identities)
    assert len(rules.gifts(state(game))) == 1
    gift_choice = next(x for x in game.choices(PLAYER) if x["kind"] == "gender_animal_tag")
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            gift_choice["id"],
            gift_choice["revision"],
            ChoiceAnswer(text="Cannot author the Animal's Tag"),
        )
    tag_args = (
        PLAYER,
        str(uuid4()),
        gift_choice["id"],
        gift_choice["revision"],
        ChoiceAnswer(text="PRIVATE_ANIMAL_TAG actual non-Animal partner"),
    )
    tag_response = game.respond(*tag_args)
    assert game.respond(*tag_args) == tag_response
    tag = next(x for x in state(game).sheets["3"].tags if x.label.startswith("PRIVATE_ANIMAL_TAG"))
    assert tag.giver_actor == actor and not tag.marked and tag.scene_used is None
    asset = next(x.id for x in state(game).sheets["2"].assets if not x.void)
    answer(game, OTHER, "mockingbird_sex_infect", fields={"asset": asset})
    answer(game, PLAYER, "mockingbird_sex_rewrite", text="Actual owner-authored Void alteration")
    tick(worker, gateway, 5)
    assert game.inspect(OTHER, play)["state"] == "complete"
    assert game.dice.calls == 1 and game.inspect(OTHER, play)["receipt"] == before_tags["receipt"]
    assert rules.gifts(state(game))[0].tag == tag.id

    assign(service, source, (actor,), "woman")
    assert rules.presentation(state(game), actor) == dict(
        legal_gender="woman", legal_pronouns="she/her"
    )
    assert state(game).sheets["2"].character_id == initial.sheets["2"].character_id
    assert state(game).sheets["2"].callsign == initial.sheets["2"].callsign
    with ledger.engine.connect() as c:
        scene = game.scene(c, 901)["id"]
    rev = state(game).revision
    args = spoken_no_native(
        service,
        man,
        scene,
        rev,
        "PRIVATE_SPOKEN_NO I actually told this Man No in character",
    )
    value = rules.speeches(state(game))[-1]
    result = dict(id=value.id, punishment=value.punishment)
    assert service.record_no(*args) == result
    with pytest.raises(WorkflowError):
        service.record_no(PLAYER, str(uuid4()), rev, scene, man, "Stale speech cannot duplicate")
    before_heat = state(game).sheets["2"].heat
    discipline = PunishmentService(ledger)
    submit(
        discipline,
        ADMIN,
        result["punishment"],
        Details(kind="stimulant_injection"),
        "actual-designation-punishment",
    )
    assert discipline.get(ADMIN, result["punishment"])["state"] == "resolved"
    assert state(game).sheets["2"].heat == before_heat + 7
    assert rules.gifts(state(game))[0].tag == tag.id  # Reassignment erases no actual source effect.

    inbox = InboxService(ledger)
    card = next(x for x in inbox.items(PLAYER) if x.identity == result["id"])

    async def history():
        followup = interaction(2, 901)
        await followup.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(followup, card)
        assert "PRIVATE_SPOKEN_NO" in followup.edit_original_response.call_args.kwargs[
            "content"
        ].replace("\\", "")

    asyncio.run(history())
    with ledger.engine.connect() as c:
        payloads = list(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_SPOKEN_NO" not in str(payloads)
        assert "PRIVATE_LEGAL_ASSIGNMENT" not in str(payloads)
        order_table = t.m2["m2_orders"]
        actual = c.scalar(
            sa.select(order_table.c.body_json).where(order_table.c.id == order["order_id"])
        )
        assert json.loads(actual)["gender_designation"]["target_designation"]
