"""Real Newgirl Sex outcomes, original group Mentors and actual learned discovery."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, setup_three
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_trainee import discipline
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_newgirl_sex as rules
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_mentorship import active_mentors
from girlframe.services.creation import CreationService
from girlframe.services.inbox import InboxService
from girlframe.services.m3_mentor import MentorService
from girlframe.services.m3_mentorship import original_mentors
from girlframe.services.m3_newgirl_sex import NewgirlSexService, prove
from girlframe.services.m3_trainee import TraineeService
from girlframe.services.onboarding import WorkflowError

PEOPLE = (PLAYER, OTHER, FOUR, ADMIN)


def ready(store, tmp_path, monkeypatch, *, top=False):
    import test_intracadre_marriage as marriage_fixture
    import test_mission_service as fixture

    original_third = marriage_fixture.third_draft

    def third_with_actual_cadre_history(actual_store):
        original_third(actual_store)
        creation = CreationService(actual_store)
        own = creation.get(PLAYER)
        draft = own.draft.model_copy(
            update={
                "prior_missions": tuple(
                    PriorMission(user_id=uid, character_revision=row["revision"], missions=0)
                    for uid, row in creation.cadre(PLAYER).items()
                ),
                "cadre_discussed": True,
            }
        )
        creation.save(
            PLAYER, str(uuid4()), own.revision, actual_store.draft(PLAYER)["revision"], draft
        )

    monkeypatch.setattr(marriage_fixture, "third_draft", third_with_actual_cadre_history)
    monkeypatch.setattr(fixture, "setup_game", setup_three)
    _, game = service(store, girl="NEWGIRL", frame="THE ENFORCER")
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, "girl.newgirl.mentor", "girl.newgirl.trainee"),
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        for owner in (2, 3, 4):
            actual = place(actual, owner, mode="outside_frame")
        actual.order = (2, 3, 4) if top else (3, 4, 2)
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_intimacy_context", actual)
    return game, GameWorker(game), Gateway(), NewgirlSexService(game)


def invite(game, controls, partners=(3,), *, native=False):
    before = state(game)
    calls = game.dice.calls
    if not native:
        identity = controls.invite(
            PLAYER,
            str(uuid4()),
            900,
            tuple(current_ref(before, x) for x in partners),
            before.revision,
            "PRIVATE_NEWGIRL_SOURCE actual voluntary intimacy together",
        )["id"]
    else:
        from girlframe.discord_adapter.m3_newgirl_sex import open_newgirl_sex

        async def start():
            interaction = current(2, 98001)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_newgirl_sex(interaction, controls)
            menu = interaction.edit_original_response.call_args.kwargs["view"]
            menu.values["source"] = ("invite",)
            opened = current(2, 98002)
            await menu.confirm.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                partners=tuple(current_ref(before, x).token for x in partners),
                account="PRIVATE_NEWGIRL_SOURCE our actual voluntary intimacy together",
            )
            response = current(2, 98003)
            await form.confirm.callback(response)
            assert form.completed, response.edit_original_response.call_args_list

        asyncio.run(start())
        identity = rules.records(state(game), rules.Session)[-1].id
    for partner in partners:
        human = OTHER if partner == 3 else FOUR
        controls.confirm(
            human,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "My own actual voluntary participation, authored by me",
        )
    assert game.dice.calls == calls
    return identity


def roll(game, worker, gateway, identity, faces):
    game.dice.faces = faces
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            heat=before.sheets["2"].heat if before.sheets["2"].heat >= 5 else 0,
            context="Actual voluntarily confirmed performed intimacy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    tick(worker, gateway, 3)
    for human in PEOPLE:
        answer(game, human, "tag_window", options=("pass",))
    return action


def choose(game, viewer, kind, partner, *, options=(), text="", asset=None, native=False):
    rows = game.choices(viewer)
    with game.store.engine.connect() as c:
        row = next(
            x
            for x in rows
            if x["kind"] == kind
            and json.loads(
                c.scalar(
                    sa.select(t.m2["m2_choices"].c.body_json).where(
                        t.m2["m2_choices"].c.id == x["id"]
                    )
                )
            )["partner"]["entity"]
            == str(partner)
        )
    if not native:
        return game.respond(
            viewer,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=options, text=text, denied=(asset,) if asset else ()),
        )
    from girlframe.discord_adapter.m3_newgirl_sex import open_choice

    async def select():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, row["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=options, text=text, asset=(asset,) if asset else ())
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(select())


def complete(game, worker, gateway, controls, identity, action):
    assert controls.view(PLAYER, identity)["phase"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with game.store.engine.connect() as c:
        assert prove(game, c, state(game), identity).completed_event
    tick(worker, gateway, 5)


def test_mid_actual_respect_answer_real_bond_and_status_once(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = invite(game, controls, native=True)
    before = state(game)
    action = roll(game, worker, gateway, identity, (4, 5))
    choose(game, PLAYER, "newgirl_sex_ask", 3, text="Do you respect me?", native=True)
    choose(
        game,
        OTHER,
        "newgirl_sex_respect",
        3,
        options=("yes",),
        text="Yes, I respect you",
        native=True,
    )
    final = state(game)
    assert depth(final, current_ref(final, 2), current_ref(final, 3)) == 2
    assert final.order.index(2) == before.order.index(2) - 1
    assert final.sheets["3"].assets == before.sheets["3"].assets
    complete(game, worker, gateway, controls, identity, action)


def test_mid_no_actual_new_mentor_discovery_receipt_optional_tag_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = invite(game, controls, (4,))
    action = roll(game, worker, gateway, identity, (4, 5))
    choose(game, PLAYER, "newgirl_sex_ask", 4, text="Do you actually respect me?")
    choose(game, FOUR, "newgirl_sex_respect", 4, options=("no",), text="I do not respect you yet")
    complete(game, worker, gateway, controls, identity, action)
    assert active_mentors(state(game), current_ref(state(game), 2)) == (
        current_ref(state(game), 4),
    )
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, identity)
    found = controls.disclose(
        PLAYER,
        str(uuid4()),
        identity,
        current_ref(before, 4),
        current_ref(before, 3),
        before.revision,
        "PRIVATE_ACTUAL_DISCLOSURE I tell the present third Girl about this actual Mentor intimacy",
        channel=900,
    )["id"]
    frozen = state(game)
    with pytest.raises(WorkflowError):
        controls.learn(PLAYER, str(uuid4()), found, frozen.revision, "Cannot impersonate observer")
    with pytest.raises(WorkflowError):
        controls.learn(OTHER, str(uuid4()), found, frozen.revision - 1, "Stale source response")
    assert state(game) == frozen
    controls.learn(
        OTHER,
        str(uuid4()),
        found,
        state(game).revision,
        "I actually learned that they had this intimacy; this is my own received knowledge",
    )
    key, rev = str(uuid4()), state(game).revision
    args = (PLAYER, key, found, rev, "Known Mentor indiscretion")
    result = controls.discovery_tag(*args)
    assert controls.discovery_tag(*args) == result
    tag = next(x for x in state(game).sheets["4"].tags if x.label == "Known Mentor indiscretion")
    assert tag.giver_actor == current_ref(before, 2)
    with pytest.raises(WorkflowError):
        controls.view(FOUR, found)
    with ledger.engine.connect() as c:
        payload = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_ACTUAL_DISCLOSURE" not in payload

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(OTHER) if x.identity == found and x.task == "m3_newgirl_sex"
        )
        interaction = current(3, 98010)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(interaction, item)
        assert (
            "PRIVATE_ACTUAL_DISCLOSURE"
            in interaction.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(reopen())


def test_high_actual_partner_asset_damage_real_source_and_mentor(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = invite(game, controls)
    before = state(game)
    action = roll(game, worker, gateway, identity, (6, 6))
    asset = next(x.id for x in before.sheets["2"].assets if x.family == "girl" and not x.damaged)
    choose(
        game,
        OTHER,
        "newgirl_sex_damage",
        3,
        options=("damage",),
        asset=asset,
        text="I actually damage this selected Asset to put her in her place",
        native=True,
    )
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).damaged
    assert active_mentors(state(game), current_ref(state(game), 2)) == (
        current_ref(state(game), 3),
    )
    complete(game, worker, gateway, controls, identity, action)


def test_high_declined_damage_real_newgirl_tag_and_lower_partner_status(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = invite(game, controls)
    before = state(game)
    action = roll(game, worker, gateway, identity, (6, 6))
    choose(
        game,
        OTHER,
        "newgirl_sex_damage",
        3,
        options=("decline",),
        text="I actually decline harming her",
    )
    choose(game, PLAYER, "newgirl_sex_mark", 3, text="Left visibly impressed", native=True)
    assert state(game).order.index(3) == before.order.index(3) + 1
    assert state(game).sheets["2"].assets == before.sheets["2"].assets
    tag = next(x for x in state(game).sheets["3"].tags if x.label == "Left visibly impressed")
    assert tag.giver_actor == current_ref(before, 2)
    complete(game, worker, gateway, controls, identity, action)


def test_low_actual_enjoyment_partner_tag_and_optional_singleton_mentor(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    identity = invite(game, controls, (4,))
    action = roll(game, worker, gateway, identity, (1, 1))
    choose(
        game,
        PLAYER,
        "newgirl_sex_enjoyed",
        4,
        text="I actually tell her I enjoyed myself",
        native=True,
    )
    choose(
        game,
        FOUR,
        "newgirl_sex_low",
        4,
        options=("mentor",),
        text="My willing new apprentice",
        native=True,
    )
    assert active_mentors(state(game), current_ref(state(game), 2)) == (
        current_ref(state(game), 4),
    )
    assert next(
        x for x in state(game).sheets["2"].tags if x.label == "My willing new apprentice"
    ).giver_actor == current_ref(state(game), 4)
    complete(game, worker, gateway, controls, identity, action)
    # Ordinary single-partner refusal retains the genuine existing fourth Mentor.
    declined = invite(game, controls, (3,))
    declined_action = roll(game, worker, gateway, declined, (1, 1))
    choose(
        game,
        PLAYER,
        "newgirl_sex_enjoyed",
        3,
        text="I actually tell this other person I enjoyed myself",
    )
    choose(
        game,
        OTHER,
        "newgirl_sex_low",
        3,
        options=("decline",),
        text="Affectionate without mentorship",
    )
    assert active_mentors(state(game), current_ref(state(game), 2)) == (
        current_ref(state(game), 4),
    )
    complete(game, worker, gateway, controls, declined, declined_action)


def test_group_all_original_mentors_real_tag_rank_naming_selected_teaching_and_owed_duty_after_swap(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, top=True)
    identity = invite(game, controls, (3, 4), native=True)
    action = roll(game, worker, gateway, identity, (1, 1))
    for partner, human in ((3, OTHER), (4, FOUR)):
        choose(
            game,
            PLAYER,
            "newgirl_sex_enjoyed",
            partner,
            text="I tell this actual partner I enjoyed myself",
        )
        choose(
            game,
            human,
            "newgirl_sex_low",
            partner,
            options=("decline",),
            text="Mentor lesson " + str(partner),
        )
    complete(game, worker, gateway, controls, identity, action)
    original = state(game)
    learner, third, fourth = (current_ref(original, x) for x in (2, 3, 4))
    assert active_mentors(original, learner) == (third, fourth)
    assert higher(original, 3, 2) and higher(original, 4, 2)
    assert not higher(original, 2, 3) and not higher(original, 2, 4)
    with ledger.engine.connect() as c:
        assert original_mentors(game, c, original, learner)[0] == (third, fourth)
    naming = MentorService(game)
    naming.name(OTHER, str(uuid4()), learner, state(game).revision, "THIRD'S APPRENTICE")
    naming.name(FOUR, str(uuid4()), learner, state(game).revision, "FOURTH'S APPRENTICE")
    tag = next(x for x in state(game).sheets["2"].tags if x.label == "Mentor lesson 4")
    for repeat in (False, True):
        game.dice.faces = (3, 4)
        keep = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Actual danger and my Mentor's lesson",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        answer(
            game,
            PLAYER,
            "tag_window",
            options=("tag",),
            denied=(tag.id,),
            number=1,
            text="My actual Mentor's Tag helps my evasion",
        )
        for human in (OTHER, FOUR, ADMIN):
            answer(game, human, "tag_window", options=("pass",))
        if repeat:
            with pytest.raises(WorkflowError, match="Mentor"):
                answer(game, PLAYER, "tag_resolution", options=("reject",))
            answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=("identity:0",))
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual evasion adjudication")
        assert game.inspect(PLAYER, keep)["state"] == "complete"
        tick(worker, gateway, 5)
        if not repeat:
            game.close_scene(ADMIN, str(uuid4()), 900)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in PEOPLE:
                game.join_scene(human, str(uuid4()), 900)
    trainee = TraineeService(game)
    lesson = trainee.record_teaching(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        "The actual fourth Mentor demonstrates an important stance",
        mentor=fourth,
    )["id"]
    trainee.choose(
        PLAYER,
        str(uuid4()),
        lesson,
        state(game).revision,
        "challenge",
        account="I actually challenge this fourth Mentor's teaching",
    )
    # Actual immediate source work blocks a new Sex Play; complete it before the later swap.
    successor = invite(game, controls, (3,))
    before_block = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="REQUIRED_FOLLOWUP"):
        roll(game, worker, gateway, successor, (4, 5))
    assert state(game) == before_block and game.dice.calls == calls
    case = trainee.punish(FOUR, str(uuid4()), lesson, state(game).revision)["case"]
    discipline(game, case, FOUR, PLAYER)
    completed_lesson = trainee.view(PLAYER, lesson)
    assert completed_lesson["phase"] == "complete"
    # Source-prices remain real: the7 Heat discipline requires spending all;2+7 is mid.
    new_action = roll(game, worker, gateway, successor, (1, 1))
    choose(game, PLAYER, "newgirl_sex_ask", 3, text="Do you respect me now?")
    choose(game, OTHER, "newgirl_sex_respect", 3, options=("no",), text="Not yet")
    complete(game, worker, gateway, controls, successor, new_action)
    assert active_mentors(state(game), learner) == (third,)
    assert not trainee.view(FOUR, lesson)["actionable"]
    after_lesson = trainee.view(PLAYER, lesson)
    assert after_lesson["phase"] == "complete"
    assert after_lesson["teaching"] == completed_lesson["teaching"]
    assert after_lesson["case"] == completed_lesson["case"]
