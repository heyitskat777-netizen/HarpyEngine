"""Genuine original Casualty body, actual damage/Defeat and independently finalized transition."""

from uuid import uuid4

from test_casualty import ready
from test_casualty import tags as pass_tags
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.engine import m3_casualty as casualty
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.creation_details import DesireChoice
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_transition_state import Investor, Plan
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_casualty import prove_parts
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_world import WorldService


def actual_retained_casualty_vatgrown(ledger, tmp_path, monkeypatch):
    import test_creation_review as creation_fixture
    import test_m2_game as game_fixture
    from test_ledger import OTHER

    from girlframe.engine.drafts import DraftInput

    original_seed, original_selected = creation_fixture.seed, game_fixture.selected

    def seed_casualty(store, viewer=PLAYER, callsign="SYNTH_A", notes="PRIVATE_CANARY"):
        if viewer != OTHER:
            return original_seed(store, viewer, callsign, notes)
        store.join(viewer, "join-actual-casualty-teacher")
        return store.save_draft(
            viewer,
            "draft-actual-casualty-teacher",
            0,
            DraftInput(
                callsign="Actual Casualty teacher",
                girl_playbook="CASUALTY",
                frame_playbook="JANUS-B",
                notes=notes,
            ),
        )

    def selected_casualty(girl="MOCKINGBIRD", frame="JANUS-B"):
        return original_selected("CASUALTY" if girl == "MOCKINGBIRD" else girl, frame)

    monkeypatch.setattr(creation_fixture, "seed", seed_casualty)
    monkeypatch.setattr(game_fixture, "selected", selected_casualty)
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(casualty.GOD, casualty.BARELY, casualty.SEX, vat.SEX),
    )
    controls.body(PLAYER, str(uuid4()))
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    actor = current_ref(state(game), 2)
    with ledger.engine.connect() as c:
        original_body = prove_parts(game, c, state(game), actor)
    world = WorldService(MissionService(ledger))
    npc = Npc(
        id="actual-original-investor",
        name="Original scientist",
        jobs=("scientist",),
        detail="My existing creation NPC relationship",
        controller=1,
        cell=(0, 0),
        revealed=True,
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, npc)
    slot = state(game).sheets["2"].review.creation.npc_bonds[0].slot
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, slot, npc.id)
    physical = PhysicalService(ledger)
    with ledger.engine.connect() as c:
        body = resolve(state(game), actor, profiles(c, ledger.campaign_id))
    physical.operate(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        CockpitAction(
            actor=actor,
            operation="pilot",
            expected_position=body.position_sha256,
            confirmed=True,
            account="I enter my actual original Frame",
        ),
        channel=900,
    )
    # Every Frame loss is a real original counterpart-owned counter, not injected damage.
    frame_ids = tuple(
        x.id for x in state(game).sheets["2"].assets if x.family == "frame" and not x.damaged
    )
    for index, asset in enumerate(frame_ids):
        game.dice.faces = (1, 1)
        parent = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="put_someone_beneath_you",
                target=3,
                heat=0,
                piloting=True,
                context="Our actual confrontation in my original Frame",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, OTHER, "beneath_select", options=("damage",), text="My actual counter")
        answer(game, PLAYER, "beneath_details", denied=(asset,))
        if index != len(frame_ids) - 1:
            tick(worker, gateway, 6)
            assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert any(x["kind"] == "beneath_defeat" for x in game.choices(PLAYER))
    defeat = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            context="My actual last Frame Asset was damaged",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("change_girl_playbook",),
        fields={"girl_playbook": "VATGROWN"},
        text="My actual Defeat changes my Girl book",
    )
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, defeat)["state"] == "complete"
    transition = GirlTransitionService(ledger)
    task = next(x for x in transition.tasks(PLAYER) if x["state"] == "pending")
    info = transition.get(PLAYER, task["id"])
    transition.configure(
        PLAYER,
        str(uuid4()),
        task["id"],
        info["revision"],
        Plan(
            account="My actual transition retains original people and resources",
            dna_basis="My established original DNA basis",
            investors=(Investor(npc=npc.id, desires=DesireChoice(slots=(0, 2))),),
        ),
    )
    info = transition.get(ADMIN, task["id"])
    transition.respond(
        ADMIN, str(uuid4()), task["id"], info["revision"], desires=DesireChoice(slots=(1, 3))
    )
    info = transition.get(PLAYER, task["id"])
    transition.finalize(PLAYER, str(uuid4()), task["id"], info["revision"], info["game_revision"])
    actual = state(game)
    assert actual.sheets["2"].girl == "VATGROWN"
    with ledger.engine.connect() as c:
        assert prove_parts(game, c, actual, actor) == original_body
        body = resolve(actual, actor, profiles(c, ledger.campaign_id))
    if body.inside_frame:
        physical.operate(
            PLAYER,
            str(uuid4()),
            actual.revision,
            CockpitAction(
                actor=actor,
                operation="exit",
                expected_position=body.position_sha256,
                confirmed=True,
                account="I leave my actual damaged Frame",
            ),
            channel=900,
        )
    return game, worker, gateway, controls, original_body


def test_real_retained_body_earned_casualty_source_consent_withdraw_mid_tags_once_use(
    ledger, tmp_path, monkeypatch
):
    import asyncio
    import json

    import pytest
    from test_casualty import choose
    from test_vatgrown_plays import _learned_sex_interaction, native_choice

    from girlframe.discord_adapter.m3_casualty import open_casualty
    from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_learned_play_state import learned_sex_links
    from girlframe.services.m3_learned_sex import lessons, prove
    from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
    from girlframe.services.onboarding import WorkflowError

    game, worker, gateway, controls, original_body = actual_retained_casualty_vatgrown(
        ledger, tmp_path, monkeypatch
    )
    actor, teacher = current_ref(state(game), 2), current_ref(state(game), 3)
    source = VatgrownPlaysService(game)
    invitation = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "The actual native teacher supplies only her chosen Play",
    )["id"]
    source.respond(OTHER, str(uuid4()), invitation, state(game).revision, True, "My own consent")
    ordinary = next(
        x for x in state(game).sheets["2"].identities if not x.protected and not x.marked
    )
    game.dice.faces = (5, 5)
    taught_action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=invitation,
            heat=1,
            identity=ordinary.id,
            gain=1,
            context="Actual voluntary lesson",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    replacement = next(x for x in actual.sheets["2"].identities if not x.protected)
    retained = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(
        x
        for x in actual.sheets["3"].identities
        if not x.protected and x.name.casefold() not in retained
    )
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(casualty.SEX,),
        account="My actual Sex rule, not my ideal body",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert (
        lesson.rule_id == casualty.SEX
        and game.inspect(PLAYER, taught_action)["state"] == "complete"
    )
    source.send_away(OTHER, str(uuid4()), invitation, state(game).revision, "End my source stay")
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], casualty.SEX, "CASUALTY")
    assert not has_rule(state(game).sheets["2"], casualty.GOD, "CASUALTY")
    assert not has_rule(state(game).sheets["2"], casualty.BARELY, "CASUALTY")

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(_learned_sex_interaction(3))
        form.values.update(
            target=(teacher.token,), account="PRIVATE_LEARNED_CASUALTY real original body"
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        return learned_sex_links(state(game))[-1]

    first = asyncio.run(invite())
    controls.confirm(
        OTHER, str(uuid4()), first.session, state(game).revision, False, "My own refusal"
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), first.id).released_kind == "declined"
    second = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        controls.withdraw_learned(OTHER, str(uuid4()), second.session, state(game).revision)
    controls.withdraw_learned(PLAYER, str(uuid4()), second.session, state(game).revision)
    third = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        controls.confirm(
            PLAYER,
            str(uuid4()),
            third.session,
            state(game).revision,
            True,
            "Cannot answer for another",
        )
    controls.confirm(
        OTHER, str(uuid4()), third.session, state(game).revision, True, "My fresh consent"
    )
    before, calls = state(game), game.dice.calls
    available_heat = before.sheets["2"].heat
    spent_heat = available_heat if available_heat >= 5 else min(1, available_heat)
    raw_total = 8 - spent_heat
    assert 2 <= raw_total <= 12, "Fixture must use legal dice and actual mandatory Heat spending"
    game.dice.faces = (max(1, raw_total - 6), min(6, raw_total - 1))

    async def roll():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_casualty(opened, controls, third.session)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("continue",)
        sent = _learned_sex_interaction()
        await menu.confirm.callback(sent)
        form = sent.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            heat=(str(spent_heat),), account="My actually performed original-body source"
        )
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, (
            response.response.events,
            response.edit_original_response.call_args_list,
        )

    asyncio.run(roll())
    with ledger.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    choose(
        game,
        PLAYER,
        "casualty_present",
        native=True,
        options=("hands",),
        text="I present my actual original hands",
    )
    choose(
        game,
        OTHER,
        "casualty_focus",
        native=True,
        fields={"hands": "hesitate"},
        text="My independently chosen hesitation",
    )
    choose(
        game,
        PLAYER,
        "casualty_mutual_tag",
        native=True,
        text="My actual impression of her hesitation",
    )
    choose(game, OTHER, "casualty_mutual_tag", native=True, text="My own actual impression of her")
    actual = state(game)
    assert controls.view(PLAYER, third.session)["phase"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == calls + 1
    assert actual.sheets["2"].heat == before.sheets["2"].heat - spent_heat
    assert len(actual.sheets["2"].tags) == len(before.sheets["2"].tags) + 1
    assert len(actual.sheets["3"].tags) == len(before.sheets["3"].tags) + 1
    with ledger.engine.connect() as c:
        assert prove_parts(game, c, actual, actor) == original_body
        used = prove(game, c, actual, third.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        assert not lessons(game, c, actual, actor, casualty.SEX)
        assert prove(game, c, actual, second.id).released_kind == "withdrawn"
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, third.session)
    assert "PRIVATE_LEARNED_CASUALTY" not in json.dumps(gateway.messages)
    tick(worker, gateway, 6)
