"""Genuine Casualty body → native Bonded → independent refusal/withdrawal release."""

import asyncio
import json
from uuid import uuid4

import pytest
import test_bonded
from test_bonded import FOUR, pass_tags, ready
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_vatgrown_plays import _learned_sex_interaction

from girlframe.discord_adapter.m3_casualty import open_casualty
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_casualty as casualty
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_transition_state import Plan
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_casualty import CasualtyService, _session, prove_parts
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_native_pair_casualty_refusal_and_owner_withdrawal_after_genuine_body_transition(
    ledger, tmp_path, monkeypatch
):
    original_game = test_bonded.bonded_game

    def casualty_game(store, **kwargs):
        kwargs["girl"] = "CASUALTY"
        return original_game(store, **kwargs)

    monkeypatch.setattr(test_bonded, "bonded_game", casualty_game)
    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, native_pair_book="CASUALTY"
    )
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, casualty.SEX, casualty.GOD))
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
    service = CasualtyService(game)
    service.body(PLAYER, str(uuid4()))
    with ledger.engine.connect() as c:
        body_before = prove_parts(game, c, state(game), current_ref(state(game), 2))
    physical = PhysicalService(ledger)
    transition = GirlTransitionService(ledger)
    service = CasualtyService(game)
    for owner, opponent in ((PLAYER, OTHER),):
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
            if any(x["kind"] == "casualty_roll_push" for x in game.choices(owner)):
                answer(game, owner, "casualty_roll_push", options=("skip",))
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
        if any(x["kind"] == "casualty_roll_push" for x in game.choices(owner)):
            answer(game, owner, "casualty_roll_push", options=("skip",))
        answer(
            game,
            owner,
            "defeat_select",
            options=("change_girl_playbook",),
            fields={"girl_playbook": "BONDED"},
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
            Plan(
                account="My actual Bonded transition with retained Casualty body",
                pair=current_ref(state(game), 3),
                paired_identity=state(game).sheets["2"].identities[0].id,
            ),
        )
        info = transition.get(OTHER, task["id"])
        transition.respond(OTHER, str(uuid4()), task["id"], info["revision"], accepted=True)
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
    actor = current_ref(state(game), 2)
    assert state(game).sheets["2"].girl == "BONDED"
    with ledger.engine.connect() as c:
        assert prove_parts(game, c, state(game), actor).vessel == body_before.vessel
    rolls = game.dice.calls
    heat = state(game).sheets["2"].heat

    def invite():
        parent = controls.propose(
            PLAYER,
            str(uuid4()),
            900,
            state(game).revision,
            "sex",
            "PRIVATE_NATIVE_CASUALTY original Pair rule",
            target=current_ref(state(game), 4),
            route="delegated",
            delegated_rule=casualty.SEX,
        )["id"]
        controls.confirm(
            FOUR, str(uuid4()), parent, state(game).revision, True, "My parent consent"
        )
        child = service.invite(
            PLAYER,
            str(uuid4()),
            900,
            current_ref(state(game), 4),
            state(game).revision,
            "Separate actual child invitation",
            bonded_source=parent,
        )["id"]
        return parent, child

    parent, child = invite()
    service.confirm(FOUR, str(uuid4()), child, state(game).revision, False, "I decline")
    assert service.view(PLAYER, child)["phase"] == "declined"
    assert controls.view(PLAYER, parent)["phase"] == "declined"
    parent, child = invite()
    service.confirm(FOUR, str(uuid4()), child, state(game).revision, True, "My actual consent")
    accepted = _session(state(game), child)
    with pytest.raises(WorkflowError):
        service.withdraw_learned(FOUR, str(uuid4()), child, state(game).revision)

    async def withdraw():
        opened = _learned_sex_interaction(2)
        await opened.response.defer(ephemeral=True)
        await open_casualty(opened, service, child)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert any(option[0] == "withdraw" for field in form.fields for option in field.options)
        form.values.update(operation=("withdraw",))
        response = _learned_sex_interaction(2)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(withdraw())
    assert service.view(PLAYER, child)["phase"] == "withdrawn"
    assert controls.view(PLAYER, parent)["phase"] == "withdrawn"
    ended = _session(state(game), child)
    assert (ended.consent_event, ended.consent_account) == (
        accepted.consent_event,
        accepted.consent_account,
    )
    assert ended.action is None and game.dice.calls == rolls
    assert state(game).sheets["2"].heat == heat
    assert invite()[0] != parent
    assert "PRIVATE_NATIVE_CASUALTY" not in json.dumps(gateway.messages)
