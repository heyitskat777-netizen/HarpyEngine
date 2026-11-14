"""An unrelated real Bond can be rewritten without changing the original marriage."""

import asyncio
import json
from uuid import uuid4

import pytest
import test_mission_service as mission_fixture
from handler_award_scenario import ordinary_pr_award
from test_ankou import current, feedback_source
from test_ankou_feedback import begin_mark, choose
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, setup_three, third_presence
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou as ankou
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_intracadre_marriage as marriage
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_intracadre_marriage import MarriageService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("mode", ["relay", "last_identity"])
def test_married_ankou_rewrites_only_actual_outsider_bond_and_preserves_marriage(
    ledger, tmp_path, monkeypatch, mode
):
    monkeypatch.setattr(
        mission_fixture,
        "setup_game",
        lambda store, **kwargs: setup_three(store, girl="OLDGEN", frame=ankou.FRAME),
    )
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    third_presence(ledger, game)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(ordinary.RULE, marriage.RULE, feedback.RULE, ankou.RELAY, *ankou.REQUISITIONS),
    )
    original_actor = gateway.actor

    async def actual_actor(identity):
        return FOUR if identity == 4 else await original_actor(identity)

    gateway.actor = actual_actor
    actor, spouse, outsider = (current_ref(state(game), uid) for uid in (2, 3, 4))
    assert depth(state(game), actor, outsider) > 0  # genuine accepted creation Bond
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    MarriageService(ledger, game).declare(
        ADMIN,
        str(uuid4()),
        award.id,
        state(game).revision,
        actor,
        spouse,
        actor,
        actor,
        "These two original Girls are now partners",
    )
    established = marriage.marriage_for(state(game), actor)
    assert established is not None
    spouse_depth = depth(state(game), actor, spouse)
    shared_status = marriage.status_groups(state(game))
    permissions = {uid: state(game).sheets[uid].permissions for uid in ("2", "3", "4")}
    game.dice = Dice((4, 4))

    def finish_keep(action):
        for viewer in (PLAYER, OTHER, FOUR, ADMIN):
            answer(game, viewer, "tag_window", options=("pass",))
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual sufficient source result")
        tick(worker, gateway, 3)
        assert game.inspect(PLAYER, action)["state"] == "complete"

    if mode == "relay":
        sequence = feedback_source(game, AnkouService(game), gateway)
        step = ankou.get(state(game), ankou.FeedbackStep, sequence.steps[0])
        source_id = step.id

        def cut(target):
            return sequences.choose(
                game,
                PLAYER,
                str(uuid4()),
                source_id,
                state(game).revision,
                "bond",
                target,
                "PRIVATE_UNRELATED_BOND: actual emotional distance",
                name="PRIVATE_UNRELATED_ASSET",
                in_battle=False,
            )
    else:
        unmarked = [x.id for x in state(game).sheets["2"].identities if not x.marked]
        for identity in unmarked[:-1]:
            action = begin_mark(game, identity)
            tick(worker, gateway, 3)
            finish_keep(action)
        game.dice = Dice((4, 4))
        action = begin_mark(game, unmarked[-1])
        tick(worker, gateway, 3)
        source = next(x for x in feedback.sources(state(game)) if x.action == action)
        source_id = source.id

        def cut(target):
            return choose(game, "bond", target, name="PRIVATE_UNRELATED_ASSET")

    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SOURCE_MARRIAGE_BOND_REQUIRED"):
        cut(spouse)
    assert state(game).model_dump_json() == snapshot
    before_heat = state(game).sheets["2"].heat
    assets_before = {x.id for x in state(game).sheets["2"].assets}
    if mode == "last_identity":

        async def native_cut():
            row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
            interaction = current()
            await interaction.response.defer(ephemeral=True)
            await open_choice(interaction, game, row["id"])
            form = interaction.edit_original_response.call_args.kwargs["view"]
            bond_targets = dict(next(x for x in form.fields if x.key == "bond_target").options)
            assert outsider.token in bond_targets and spouse.token not in bond_targets
            assert spouse.token in dict(next(x for x in form.fields if x.key == "target").options)
            form.values.update(
                effect=("bond",),
                bond_target=(outsider.token,),
                name="PRIVATE_UNRELATED_ASSET",
                account="PRIVATE_UNRELATED_BOND: actual emotional distance",
            )
            submitted = current()
            await form.confirm.callback(submitted)
            assert form.completed

        asyncio.run(native_cut())
    else:
        cut(outsider)
    after = state(game)
    assert depth(after, actor, outsider) == 0
    added = [x for x in after.sheets["2"].assets if x.id not in assets_before]
    assert len(added) == 1 and added[0].name == "PRIVATE_UNRELATED_ASSET"
    assert after.sheets["2"].heat == before_heat
    assert marriage.marriage_for(after, actor) == established
    assert depth(after, actor, spouse) == spouse_depth
    assert marriage.status_groups(after) == shared_status
    assert {uid: after.sheets[uid].permissions for uid in permissions} == permissions
    assert marriage.wallet(after, spouse) == actor
    if mode == "relay":
        assert ankou.get(after, ankou.FeedbackSequence, sequence.id).completed_event
        assert game.dice.calls == 0
        asyncio.run(SourcePauseWorker(game).tick(gateway))
    else:
        tick(worker, gateway, 3)
        finish_keep(action)
        assert game.dice.calls == 1
        assert feedback.get(state(game), source_id).rolled_event
    tick(worker, gateway, 3)
    assert not any(
        secret in json.dumps(gateway.messages)
        for secret in ("PRIVATE_UNRELATED_BOND", "PRIVATE_UNRELATED_ASSET")
    )
