"""Real original Pair, earned Bonded lesson and actual Casualty bodies through Defeat."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_bonded import pass_tags, ready
from test_casualty import choose
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_vatgrown_plays import _learned_sex_interaction, native_choice

from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.discord_adapter.m3_casualty import open_casualty
from girlframe.discord_adapter.m3_learned_sex import open_learned_sex
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_casualty as casualty
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
from girlframe.services.m3_casualty import CasualtyService, _session, prove_parts
from girlframe.services.m3_casualty import prove_sex as prove_child
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_learned_sex import lessons, prove
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_vatgrown_plays import VatgrownPlaysService
from girlframe.services.onboarding import WorkflowError


def test_original_pair_casualty_learned_delegation_body_consent_cancel_and_once_receipt(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, paired_target=True, native_pair_book="VATGROWN"
    )
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(*bonded.RULES, vat.SEX, casualty.SEX, casualty.GOD),
    )
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            ),
        }
    )
    actor, teacher = current_ref(state(game), 2), current_ref(state(game), 4)
    with ledger.engine.connect() as c:
        original_pair = pair_lineage(game, c, state(game), actor)
    # Native Bonded uses her actual Pair's Vatgrown Play to earn the real lesson.
    parent = controls.propose(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        "sex",
        "My original Pair's actual Vatgrown learning rule",
        target=teacher,
        route="delegated",
        delegated_rule=vat.SEX,
    )["id"]
    controls.confirm(FOUR, str(uuid4()), parent, state(game).revision, True, "My parent consent")
    source = VatgrownPlaysService(game)
    proposal = source.invite(
        PLAYER,
        str(uuid4()),
        900,
        teacher,
        state(game).revision,
        "The original teacher supplies her chosen lesson",
        bonded_source=parent,
    )["id"]
    source.respond(
        FOUR, str(uuid4()), proposal, state(game).revision, True, "My separate child consent"
    )
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
    assert controls.view(PLAYER, parent)["phase"] == "complete"
    with ledger.engine.connect() as c:
        assert not lessons(game, c, state(game), actor, bonded.SEX)

    # Both original people genuinely change to Casualty, each through her own
    # actual last-Frame-Asset loss, Defeat choice and independently finalized setup.
    physical = PhysicalService(ledger)
    transition = GirlTransitionService(ledger)
    service = CasualtyService(game)
    for owner, opponent in ((OTHER, PLAYER), (PLAYER, OTHER)):
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
            fields={"girl_playbook": "CASUALTY"},
            text="My owned actual Casualty transition",
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
            Plan(account="My actual Casualty body and original people"),
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
        service.body(owner, str(uuid4()))
    with ledger.engine.connect() as c:
        original_body = prove_parts(game, c, state(game), actor)
        assert pair_lineage(game, c, state(game), actor) == original_pair
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert state(game).sheets["3"].girl == "CASUALTY"
    assert state(game).sheets["2"].girl == "CASUALTY"
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")

    async def invite():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_learned_sex(opened, game, identity=lesson.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            nonpair=(teacher.token,),
            pair_rule=("casualty",),
            account="PRIVATE_LEARNED_CASUALTY: my actual original Pair's rule",
        )
        sent = _learned_sex_interaction()
        await form.confirm.callback(sent)
        assert form.completed, (sent.response.events, sent.edit_original_response.call_args_list)
        link = learned_sex_links(state(game))[-1]
        controls.confirm(
            FOUR,
            str(uuid4()),
            link.session,
            state(game).revision,
            True,
            "My own parent participation, not a child answer",
        )
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, link.session)
        delegation = next(
            x for x in bonded.records(state(game), bonded.Delegation) if x.source == link.session
        )
        return link, delegation.session

    async def consent(child, accept):
        opened = _learned_sex_interaction(4)
        await opened.response.defer(ephemeral=True)
        await open_casualty(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            accept=("yes" if accept else "no",), account="My separate original child answer"
        )
        response = _learned_sex_interaction(4)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    refused, child = asyncio.run(invite())
    asyncio.run(consent(child, False))
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), refused.id).released_kind == "delegation_declined"
        assert lessons(game, c, state(game), actor, bonded.SEX)
    assert service.view(PLAYER, child)["phase"] == "declined"
    withdrawn, child = asyncio.run(invite())
    with pytest.raises(WorkflowError):
        service.withdraw_learned(OTHER, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_casualty(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["operation"] = ("withdraw",)
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), withdrawn.id).released_kind == "delegation_withdrawn"

    async def start(child):
        available = state(game).sheets["2"].heat
        assert available >= 1
        spend = min(available, 5)
        total = 8 - spend
        assert 2 <= total <= 12
        game.dice.faces = (max(1, total - 6), min(6, total - 1))
        opened = _learned_sex_interaction()
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, _session(state(game), child).bonded_source)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["operation"] = ("continue",)
        sent = _learned_sex_interaction()
        await menu.confirm.callback(sent)
        form = sent.edit_original_response.call_args.kwargs["view"]
        form.values.update(heat=(str(spend),), account="My actual original-body source")
        response = _learned_sex_interaction()
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        return _session(state(game), child).action

    abandoned, child = asyncio.run(invite())
    asyncio.run(consent(child, True))
    calls = game.dice.calls
    action = asyncio.run(start(child))
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert saved["cancellable"] and not saved["rolled"]
    recovery.recover(PLAYER, str(uuid4()), action, saved["revision"], cancel=True)
    assert game.dice.calls == calls
    assert service.view(PLAYER, child)["phase"] == "cancelled"
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), abandoned.id).released_kind == "owner_cancelled"
        assert lessons(game, c, state(game), actor, bonded.SEX)

    final, child = asyncio.run(invite())
    before_consent = state(game)
    with pytest.raises(WorkflowError):
        service.confirm(OTHER, str(uuid4()), child, before_consent.revision, True, "Not my answer")
    assert state(game) == before_consent
    asyncio.run(consent(child, True))
    before = state(game)
    action = asyncio.run(start(child))
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "casualty_roll_push", options=("skip",))
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
        FOUR,
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
        text="PRIVATE_CASUALTY_TAG: my impression of her hesitation",
    )
    choose(game, FOUR, "casualty_mutual_tag", native=True, text="My own impression of her hands")
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, final.session)["phase"] == "complete"
    result = _session(state(game), child)
    assert result.phase == "complete" and result.effect_event
    assert len(state(game).sheets["2"].tags) == len(before.sheets["2"].tags) + 1
    assert len(state(game).sheets["4"].tags) == len(before.sheets["4"].tags) + 1
    with ledger.engine.connect() as c:
        assert pair_lineage(game, c, state(game), actor) == original_pair
        assert prove_child(game, c, state(game), child) == result
        assert prove_parts(game, c, state(game), actor) == original_body
        used = prove(game, c, state(game), final.id)
        assert used.action == action and used.roll_event and used.receipt_sha256
        grant = next(
            x for x in state(game).sheets["2"].girl_runtime.learned_plays if x.id == lesson.id
        )
        assert grant.claimed_action == action and grant.rolled_event == used.roll_event
        assert not lessons(game, c, state(game), actor, bonded.SEX)
        assert prove(game, c, state(game), refused.id).released_event
        assert prove(game, c, state(game), withdrawn.id).released_event
        assert prove(game, c, state(game), abandoned.id).released_event
        actual_action = game.action(c, action)
        assert actual_action["data"]["casualty_sex"]["bonded_lesson"] == final.id
        assert "learned_source" not in actual_action["data"]["casualty_sex"]
        assert actual_action["data"]["result"]["tier"] == "mid"
    assert game.dice.calls == calls + 1
    assert not has_rule(state(game).sheets["2"], bonded.SEX, "BONDED")
    assert not has_rule(state(game).sheets["2"], bonded.PAIR, "BONDED")
    assert "PRIVATE_CASUALTY_TAG" not in json.dumps(gateway.messages)
    assert "PRIVATE_LEARNED_CASUALTY" not in json.dumps(gateway.messages)
    with pytest.raises(WorkflowError):
        service.view(ADMIN, child)
