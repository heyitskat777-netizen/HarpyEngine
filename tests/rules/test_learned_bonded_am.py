"""Real original AM Pair, earned Bonded lesson and independently performed no-roll source."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_bonded import pass_tags
from test_bonded_am import native
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_learned_bonded_sex import actual_retained_pair_vatgrown
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.database import tables as t
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_am as am
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_girl_transition_state import Plan
from girlframe.engine.m3_learned_play_state import learned_sex_links
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_bonded import pair_lineage
from girlframe.services.m3_bonded_am import BondedAMService
from girlframe.services.m3_bonded_am import prove as prove_child
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("withdraw_after_use", [False, True])
def test_original_pair_am_learned_no_roll_owned_performances_and_once_use(
    ledger, tmp_path, monkeypatch, withdraw_after_use
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
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, vat.SEX, am.RULE))
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
            fields={"girl_playbook": "AM"},
            text="My owned actual AM transition",
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
            Plan(account="My actual AM body and original people"),
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
    service = BondedAMService(game)
    assert current_ref(state(game), 4) == teacher
    assert state(game).sheets["4"].girl == "AM"
    assert state(game).sheets["3"].girl == "AM"
    with ledger.engine.connect() as c:
        assert pair_lineage(game, c, state(game), actor) == original_pair
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert not has_rule(state(game).sheets["2"], am.RULE, "AM")
    assert not has_rule(state(game).sheets["2"], "girl.am.just-code", "AM")

    async def invitation():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("am",),
            account="PRIVATE_LEARNED_AM: my actual original Pair's source",
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, sent.edit_original_response.call_args_list
        return learned_sex_links(state(game))[-1]

    refused = asyncio.run(invitation())
    controls.confirm(
        FOUR,
        str(uuid4()),
        refused.session,
        state(game).revision,
        False,
        "I decline my original parent participation",
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)

    def open_source():
        link = asyncio.run(invitation())
        controls.confirm(
            FOUR,
            str(uuid4()),
            link.session,
            state(game).revision,
            True,
            "My own consent, without inferring a performance",
        )
        native(
            service,
            PLAYER,
            parent=link.session,
            account="Actual original bodies; no circuits or performance are invented",
        )
        child = next(x for x in am.sources(state(game)) if x.bonded_source == link.session)
        return link, child

    unused, child = open_source()
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    with pytest.raises(WorkflowError):
        service.withdraw(
            OTHER,
            str(uuid4()),
            child.id,
            state(game).revision,
            "The Pair is not this scene's participant",
        )
    native(
        service,
        FOUR,
        identity=child.id,
        operation="withdraw",
        account="My actual withdrawal before either performance",
    )
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), unused.id).released_kind == "delegation_withdrawn"
        assert lessons(game, c, state(game), actor, bonded.SEX)
        assert prove_child(game, c, state(game), child.id).phase == "withdrawn"
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert service.view(PLAYER, child.id)["source"]["phase"] == "withdrawn"

    final, child = open_source()
    with pytest.raises(WorkflowError, match="SOURCE_PAUSE_NOT_ACKNOWLEDGED"):
        service.perform(
            PLAYER, str(uuid4()), child.id, state(game).revision, "Not actually performed yet"
        )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    before = state(game)
    calls = game.dice.calls
    with ledger.engine.connect() as c:
        actions_before = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
    # The counterpart may perform first; only her own explicit participation is recorded.
    native(
        service,
        FOUR,
        identity=child.id,
        operation="perform",
        circuits=("no",),
        account="PRIVATE_AM: my actual separate participation",
    )
    with ledger.engine.connect() as c:
        used = prove(game, c, state(game), final.id)
        assert (
            used.used_event and not used.action and not used.roll_event and not used.receipt_sha256
        )
        assert not lessons(game, c, state(game), actor, bonded.SEX)
    assert am.source(state(game), child.id).phase == "active"
    assert bonded.get(state(game), final.session).phase == "bound"
    untouched = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SOURCE_CIRCUITS_REQUIRED"):
        service.perform(
            PLAYER,
            str(uuid4()),
            child.id,
            state(game).revision,
            "No fabricated circuit access",
            circuits_touched=True,
        )
    assert state(game).model_dump_json() == untouched
    if withdraw_after_use:
        native(
            service,
            PLAYER,
            identity=child.id,
            operation="withdraw",
            account="I withdraw after the actual first performance, without a lesson refund",
        )
        assert am.source(state(game), child.id).phase == "withdrawn"
        assert bonded.get(state(game), final.session).phase == "withdrawn"
    else:
        revision = state(game).revision
        key = native(
            service,
            PLAYER,
            identity=child.id,
            operation="perform",
            circuits=("no",),
            account="PRIVATE_LEARNER: my actual original participation",
        )
        service.perform(
            PLAYER,
            key,
            child.id,
            revision,
            "PRIVATE_LEARNER: my actual original participation",
            circuits_touched=False,
        )
        assert am.source(state(game), child.id).phase == "complete"
        assert bonded.get(state(game), final.session).phase == "complete"
    after = state(game)
    assert game.dice.calls == calls
    for owner in ("2", "3", "4"):
        assert after.sheets[owner].heat == before.sheets[owner].heat
        assert after.sheets[owner].identities == before.sheets[owner].identities
        assert after.sheets[owner].assets == before.sheets[owner].assets
    with ledger.engine.connect() as c:
        final_link = prove(game, c, after, final.id)
        assert final_link.used_event == used.used_event and final_link.released_event is None
        assert not lessons(game, c, after, actor, bonded.SEX)
        assert prove_child(game, c, after, child.id).id == child.id
        assert pair_lineage(game, c, after, actor) == original_pair
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == actions_before
        )
    assert service.view(PLAYER, child.id)["no_additional_roll"]
    with pytest.raises(WorkflowError):
        service.view(OTHER, child.id)
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert service.view(PLAYER, child.id)["pause"]["state"] == "closed"
    assert "PRIVATE_AM" not in json.dumps(gateway.messages)
    assert not has_rule(after.sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(after.sheets["2"], am.RULE, "AM")
