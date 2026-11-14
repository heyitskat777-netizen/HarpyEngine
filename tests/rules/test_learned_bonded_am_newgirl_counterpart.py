"""Earned Bonded lesson, original AM Pair and an independent native Newgirl counterpart receipt."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_bonded import pass_tags
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_learned_bonded_sex import actual_retained_pair_vatgrown
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_newgirl_sex import choose
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_am as am
from girlframe.engine import m3_newgirl_sex as newgirl
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_girl_transition_state import Plan
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.engine.m3_mentorship import active_mentors, current_set
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_am_sex import SexService as AMService
from girlframe.services.m3_bonded import BondedService, pair_lineage
from girlframe.services.m3_bonded import prove as prove_parent
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_newgirl_sex import NewgirlSexService, prove_mentor_set
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


def test_original_pair_am_learned_newgirl_receipt_preserves_low_mentor_owner(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls, original_pair = actual_retained_pair_vatgrown(
        ledger, tmp_path, monkeypatch, native_pair_book="AM"
    )
    original_actor = gateway.actor

    async def actual_actor(identity):
        if identity == FOUR.user_id:
            return FOUR
        return await original_actor(identity)

    # Keep the same delivery/permission state; this actual native fourth player
    # can now author her genuine transition Plays through the synthetic gateway.
    monkeypatch.setattr(gateway, "actor", actual_actor)
    approved(
        ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vat.SEX, am.RULE, newgirl.RULE)
    )
    actor, teacher = current_ref(state(game), 2), current_ref(state(game), 4)
    source = VatgrownPlaysService(game)
    proposal = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "Actual original teacher, not her Pair or native passives",
    )["id"]
    source.respond(FOUR, str(uuid4()), proposal, state(game).revision, True, "My own participation")
    ordinary = next(
        x for x in state(game).sheets["2"].identities if not x.protected and not x.marked
    )
    game.dice.faces = (5, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=vat.PLAY,
            source_work=proposal,
            heat=1,
            identity=ordinary.id,
            gain=3,
            trigger_confirmed=True,
            context="My actual learning reinforces " + ordinary.name,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    replacement = next(x for x in actual.sheets["2"].identities if not x.protected)
    retained = {x.name.casefold() for x in actual.sheets["2"].identities if x.id != replacement.id}
    taught = next(
        x
        for x in actual.sheets["4"].identities
        if not x.protected and x.name.casefold() not in retained
    )
    native_choice(
        game,
        FOUR,
        "vat_sex_learn",
        identities=(taught.id,),
        replacements=(replacement.id,),
        play=(bonded.SEX,),
        account="My actual Bonded Sex, without copying my Pair",
    )
    lesson = vat.records(state(game), vat.LearnedPlay)[-1]
    assert lesson.rule_id == bonded.SEX and game.inspect(PLAYER, action)["state"] == "complete"
    # The actual ordinary Identity generates 3 Heat; this source spent 1.
    assert state(game).sheets["2"].heat == 2
    source.send_away(
        FOUR, str(uuid4()), proposal, state(game).revision, "End the actual source stay"
    )
    tick(worker, gateway, 6)
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")

    physical = PhysicalService(ledger)
    transition = GirlTransitionService(ledger)
    for owner, opponent in ((FOUR, OTHER),):
        person = current_ref(state(game), owner.user_id)
        with ledger.engine.connect() as c:
            body = resolve(state(game), person, profiles(c, ledger.campaign_id))
        physical.operate(
            owner,
            str(uuid4()),
            state(game).revision,
            CockpitAction(
                actor=person,
                operation="pilot",
                expected_position=body.position_sha256,
                confirmed=True,
                account="I enter my actual original Frame",
            ),
            channel=900,
        )
        assets = tuple(
            x.id
            for x in state(game).sheets[person.entity].assets
            if x.family == "frame" and not x.damaged
        )
        assert assets
        for index, asset in enumerate(assets):
            game.dice.faces = (1, 1)
            parent = game.begin(
                owner,
                str(uuid4()),
                900,
                state(game).sheets[person.entity].revision,
                PlayInput(
                    play="put_someone_beneath_you",
                    target=opponent.user_id,
                    heat=0,
                    piloting=True,
                    context="Our actual original confrontation",
                    trigger_confirmed=True,
                ),
            )["action_id"]
            tick(worker, gateway, 3)
            pass_tags(game)
            answer(game, opponent, "beneath_select", options=("damage",), text="My actual counter")
            answer(game, owner, "beneath_details", denied=(asset,))
            if index != len(assets) - 1:
                tick(worker, gateway, 6)
                assert game.inspect(owner, parent)["state"] == "complete"
        assert any(x["kind"] == "beneath_defeat" for x in game.choices(owner))
        defeat = game.begin(
            owner,
            str(uuid4()),
            900,
            state(game).sheets[person.entity].revision,
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
            owner,
            "defeat_select",
            options=("change_girl_playbook",),
            fields={"girl_playbook": "NEWGIRL"},
            text="My owned actual Newgirl transition",
        )
        tick(worker, gateway, 6)
        assert game.inspect(owner, defeat)["state"] == "complete"
        task = next(x for x in transition.tasks(owner) if x["state"] == "pending")
        info = transition.get(owner, task["id"])
        transition.configure(
            owner,
            str(uuid4()),
            task["id"],
            info["revision"],
            Plan(account="My actual Newgirl body and original people"),
        )
        info = transition.get(ADMIN, task["id"])
        transition.assign(ADMIN, str(uuid4()), task["id"], info["revision"], original_pair[0])
        info = transition.get(OTHER, task["id"])
        transition.respond(
            OTHER, str(uuid4()), task["id"], info["revision"], callsign="New apprentice"
        )
        info = transition.get(owner, task["id"])
        transition.finalize(
            owner, str(uuid4()), task["id"], info["revision"], info["game_revision"]
        )
        with ledger.engine.connect() as c:
            body = resolve(state(game), person, profiles(c, ledger.campaign_id))
        if body.inside_frame:
            physical.operate(
                owner,
                str(uuid4()),
                state(game).revision,
                CockpitAction(
                    actor=person,
                    operation="exit",
                    expected_position=body.position_sha256,
                    confirmed=True,
                    account="I leave my actual damaged Frame",
                ),
                channel=900,
            )

    assert current_ref(state(game), 4) == teacher
    assert state(game).sheets["4"].girl == "NEWGIRL"
    assert state(game).sheets["3"].girl == "AM"
    with ledger.engine.connect() as c:
        assert pair_lineage(game, c, state(game), actor) == original_pair
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert not has_rule(state(game).sheets["2"], am.RULE, "AM")
    assert not has_rule(state(game).sheets["2"], "girl.am.just-code", "AM")
    service = AMService(game)

    async def invitation():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("am",),
            account="PRIVATE_AM_NEWGIRL: my original Pair's actual source",
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        return learned_sex_links(state(game))[-1]

    final = asyncio.run(invitation())
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.confirm(OTHER, str(uuid4()), final.session, before.revision, True, "Not mine")
    assert state(game) == before
    controls.confirm(
        FOUR, str(uuid4()), final.session, state(game).revision, True, "My separate parent consent"
    )
    assert active_mentors(state(game), teacher) == (original_pair[0],)
    assert not active_mentors(state(game), actor)
    counterpart = NewgirlSexService(game)
    trigger = counterpart.invite(
        FOUR,
        str(uuid4()),
        900,
        (actor,),
        state(game).revision,
        "PRIVATE_AM_NEWGIRL My independently authored native source",
    )["id"]
    # The Newgirl's parent consent never answers the learner's separate native invitation.
    before = state(game)
    with pytest.raises(WorkflowError):
        counterpart.confirm(OTHER, str(uuid4()), trigger, before.revision, True, "Not mine")
    assert state(game) == before
    counterpart.confirm(
        PLAYER, str(uuid4()), trigger, before.revision, True, "My own native source consent"
    )
    before_heat = {uid: sheet.heat for uid, sheet in state(game).sheets.items()}
    calls = game.dice.calls
    game.dice.faces = (1, 1)
    action = game.begin(
        FOUR,
        str(uuid4()),
        900,
        state(game).sheets["4"].revision,
        PlayInput(
            play=newgirl.PLAY,
            source_work=trigger,
            heat=0,
            context="PRIVATE_AM_NEWGIRL My actual native performance",
            trigger_confirmed=True,
        ),
    )["action_id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        service.bind_source(PLAYER, str(uuid4()), final.session, action)
    assert state(game) == before and game.dice.calls == calls
    assert not service.menu(PLAYER, 900, bonded_source=final.session)["sources"]
    tick(worker, gateway, 3)
    pass_tags(game)
    rolled = state(game)
    receipt = game.inspect(FOUR, action)["receipt"]
    assert game.dice.calls == calls + 1
    assert game.inspect(FOUR, action)["state"] != "complete"
    assert any(x["kind"] == "newgirl_sex_enjoyed" for x in game.choices(FOUR))
    balances = {uid: sheet.model_dump() for uid, sheet in rolled.sheets.items()}
    with ledger.engine.connect() as c:
        before_counts = tuple(
            c.scalar(sa.select(sa.func.count()).select_from(t.m2[name]))
            for name in ("m2_actions", "m2_receipts")
        )
    with pytest.raises(WorkflowError):
        service.bind_source(OTHER, str(uuid4()), final.session, action)
    assert state(game) == rolled

    async def bind():
        opened = _learned_sex_interaction()
        opened.channel_id = 901
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, GameService(ledger, dice=game.dice), final.session)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].key == "source"
        assert all(key != "circuits" for key, _ in form.fields[0].options)
        assert any(key == action for key, _ in form.fields[0].options)
        form.values.update(source=(action,))
        sent = _learned_sex_interaction()
        sent.channel_id = 901
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(sent)
        assert state(game) == saved

    asyncio.run(bind())
    used = state(game)
    link = learned_sex_links(used)[-1]
    assert link.id == final.id and link.used_event
    assert link.action is link.roll_event is link.receipt_sha256 is None
    grant = next(x for x in used.sheets["2"].girl_runtime.learned_plays if x.id == lesson.id)
    assert grant.claimed_source == final.session and grant.used_event == link.used_event
    assert grant.claimed_action is None and grant.rolled_event is None
    assert bonded.get(used, final.session).phase == "bound"
    assert not bonded.get(used, final.session).completed_event
    assert game.inspect(FOUR, action)["state"] != "complete"
    assert used.sheets["4"].model_dump() == balances["4"]
    # Only the learner's one-use source metadata changes; no added resources or charge.
    before_own = balances["2"].copy()
    after_own = used.sheets["2"].model_dump()
    for key in ("girl_runtime", "revision"):
        before_own.pop(key)
        after_own.pop(key)
    assert after_own == before_own
    with ledger.engine.connect() as c:
        assert prove(game, c, used, link.id) == link
        assert not lessons(game, c, used, actor, bonded.SEX)
    with pytest.raises(WorkflowError):
        controls.withdraw_learned(PLAYER, str(uuid4()), final.session, used.revision)
    assert state(game) == used

    # Newgirl owns her account; only the actual counterpart chooses the new Mentor result.
    row = next(x for x in game.choices(FOUR) if x["kind"] == "newgirl_sex_enjoyed")
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, row["id"])
    assert state(game) == used
    pair_before = state(game).sheets["3"].model_dump()
    choose(
        game,
        FOUR,
        "newgirl_sex_enjoyed",
        2,
        text="PRIVATE_AM_NEWGIRL my actual enjoyment",
        native=True,
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "newgirl_sex_low")
    with pytest.raises(WorkflowError):
        game.decision(FOUR, row["id"])
    assert controls.view(PLAYER, final.session)["phase"] != "complete"
    choose(
        game,
        PLAYER,
        "newgirl_sex_low",
        2,
        options=("mentor",),
        text="PRIVATE_AM_NEWGIRL my willing apprentice",
        native=True,
    )
    actual = state(game)
    tag = next(
        x for x in actual.sheets["4"].tags if x.label == "PRIVATE_AM_NEWGIRL my willing apprentice"
    )
    assert tag.giver_actor == actor
    assert active_mentors(actual, teacher) == (actor,)
    assert not active_mentors(actual, actor)
    relation = current_set(actual, teacher)
    assert relation and relation.mentors == (actor,)
    with ledger.engine.connect() as c:
        prove_mentor_set(game, c, actual, relation)
    assert actual.sheets["3"].model_dump() == pair_before
    assert game.inspect(FOUR, action)["state"] == "complete"
    assert controls.view(PLAYER, final.session)["phase"] == "complete"
    assert game.inspect(FOUR, action)["receipt"] == receipt and game.dice.calls == calls + 1
    assert {uid: sheet.heat for uid, sheet in actual.sheets.items()} == before_heat
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, final.id).used_event == link.used_event
        parent = prove_parent(game, c, actual, final.session)
        assert parent.action is None and parent.effect_event is None and parent.completed_event
        assert (
            tuple(
                c.scalar(sa.select(sa.func.count()).select_from(t.m2[name]))
                for name in ("m2_actions", "m2_receipts")
            )
            == before_counts
        )
        assert "PRIVATE_AM_NEWGIRL" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    with pytest.raises(WorkflowError):
        controls.view(OTHER, final.session)
    tick(worker, gateway, 6)
    assert "PRIVATE_AM_NEWGIRL" not in json.dumps(gateway.messages)
    saved = state(game)
    service.bind_source(PLAYER, str(uuid4()), final.session, action)
    assert state(game) == saved and game.dice.calls == calls + 1
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, FOUR):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)
    with ledger.engine.connect() as c:
        assert prove(game, c, later, final.id).used_event == link.used_event
        assert prove_parent(game, c, later, final.session).completed_event == parent.completed_event
    assert BondedService(GameService(ledger)).view(PLAYER, final.session)["phase"] == "complete"
