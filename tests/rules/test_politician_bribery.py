"""Real Cadre political aid and all three source-owned String cash-outs."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_strain import facts
from test_strain_service import D6

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireBribery, open_advancement
from girlframe.discord_adapter.m3_politician_bribery import open_bribery
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_politician_bribery as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Location
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_politician_bribery import (
    BriberyService,
    cause_action,
    prove_cause,
    prove_string,
)
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError


def interaction(uid=1, channel=900):
    own = current(uid, int(uuid4().int % 1000000000))
    own.channel_id = channel
    return own


def native(service, identity, uid, mode, **values):
    async def run():
        own = interaction(uid)
        await own.response.defer(ephemeral=True)
        await open_bribery(own, service, identity)
        picker = own.edit_original_response.call_args.kwargs["view"]
        step = interaction(uid)
        await step.response.defer(ephemeral=True)
        await picker.open_item(step, mode)
        form = step.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        confirmed = interaction(uid)
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args
        return confirmed

    return asyncio.run(run())


def test_actual_cadre_political_aid_budget_tag_and_causal_job_loss_with_saved_history(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE))
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={
                    "subsystems": ledger.policy.m3_approval.subsystems
                    | {"strain", "world", "plays", "economy"}
                }
            )
        }
    )
    # Synthetic initial campaign geography, before the real source acquisition.
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = canon.world.model_copy(
            update={
                "locations": (
                    *canon.world.locations,
                    Location(id="city-a", name="Actual capital", kind="city", cell=(0, 1)),
                    Location(id="city-b", name="Actual port", kind="city", cell=(1, 1)),
                )
            }
        )
        game.event(c, 1, "political-initial-cities", "synthetic.initial_geography", canon)
    service = BriberyService(ledger)
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def buy():
        own = interaction()
        await own.response.defer(ephemeral=True)
        await open_advancement(own, HandlerAdvancementService(ledger), award.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in form.children if isinstance(x, AcquireBribery))
        step = interaction()
        await step.response.defer(ephemeral=True)
        await button.callback(step)
        acquisition = step.edit_original_response.call_args.kwargs["view"]
        acquisition.values.update(
            award=(award.id,),
            politicians="\n".join(
                ("Actual capital" if i < 3 else "Actual port")
                + " | Minister "
                + str(i)
                + " | Public relations | "
                + ("0,0" if i < 3 else "1,0")
                for i in range(6)
            ),
            account="Actual original political officeholders in both Cities",
        )
        confirmed = interaction()
        await acquisition.confirm.callback(confirmed)
        assert acquisition.completed, confirmed.edit_original_response.call_args

    asyncio.run(buy())
    source = rules.acquisitions(state(game))[0]
    politicians = [x.npc.id for x in source.politicians]
    original_resources = state(game).sheets
    for index, sphere in enumerate(rules.SPHERES):
        uid = 2 if index % 2 == 0 else 3
        native(
            service,
            source.id,
            uid,
            "assign",
            npc=(politicians[index],),
            sphere=(sphere,),
            feelings="PRIVATE_FEELINGS_" + str(uid),
        )
        assert (
            depth(
                state(game),
                current_ref(state(game), uid),
                ActorRef(kind="npc", entity=politicians[index]),
            )
            == 1
        )
    assert rules.complete_assignments(state(game), source)
    assert all("feelings" not in x for x in service.menu(ADMIN, source.id)["assignments"])
    assert state(game).sheets == original_resources
    casts = CastService(ActorService(MissionService(ledger)))
    # Genuine completed owned action is reused as one aid source and the later cause.
    game.dice = Dice((4, 5))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I actually expose hospital procurement records during this political aid",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The genuine exposure and evidence delivery succeed",
    )
    tick(worker, gateway, 8)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    change(casts, ADMIN, "join", ActorRef(kind="npc", entity=politicians[0]))
    with ledger.engine.connect() as c:
        proxy = game.action(c, action)
        proxy["data"]["actor_basic"] = {
            "ref": ActorRef(kind="npc", entity=politicians[0]).model_dump(mode="json")
        }
        with monkeypatch.context() as patch:
            patch.setattr(game, "action", lambda *_: proxy)
            with pytest.raises(WorkflowError, match="controlled NPC/copy alias"):
                cause_action(game, c, state(game), source, "pilot_play", action)
    for number in range(5):
        native(
            service,
            source.id,
            2,
            "aid",
            npc=(politicians[0],),
            scene=("900",),
            activity="Actual healthcare aid episode "
            + str(number)
            + ": I deliver the documented public findings",
            benefit="Actual medical committee receives distinct verified evidence packet "
            + str(number),
            action=action if number == 0 else "",
        )
        aid = rules.records(state(game), rules.Aid)[-1]
        assert len(rules.available(state(game), source.id, politicians[0])) == number
        with pytest.raises(WorkflowError):
            service.confirm_aid(
                PLAYER, str(uuid4()), aid.id, state(game).revision, "Not the real source judge"
            )
        native(
            service,
            source.id,
            1,
            "benefit:" + aid.id,
            account="As actual source judge I record this distinct performed committee benefit "
            + str(number),
        )
    assert len(rules.available(state(game), source.id, politicians[0])) == 5
    first_aid = rules.records(state(game), rules.Aid)[0]
    with pytest.raises(WorkflowError):
        service.record_aid(
            PLAYER,
            str(uuid4()),
            source.id,
            state(game).revision,
            politicians[0],
            900,
            first_aid.activity,
            first_aid.benefit,
            action=action,
        )
    # Natural High Budget and actual unrolled requests; cash-out changes the real next die.
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(6))
    strain.configure(
        ADMIN, str(uuid4()), state(game).revision, "disaster_management", frozenset({"budget"})
    )
    period = strain.periods.begin(ADMIN, str(uuid4()))
    canon = state(game)
    void_count = sum(any(x.void for x in sheet.assets) for sheet in canon.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        1,
        canon.revision,
        facts(
            at_least_half_have_void=2 * void_count >= len(canon.order), no_girl_void=void_count == 0
        ),
    )
    assert state(game).strain.levels["budget"] == "high"
    preserved_nonbudget = [x for x in state(game).strain.requests if x.track != "budget"]
    native(
        service,
        source.id,
        1,
        "budget",
        politician=(politicians[0],),
        account="Three genuine Strings produce actual Budget relief",
    )
    assert state(game).strain.levels["budget"] == "low"
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    assert request.severity == "low"
    with ledger.engine.connect() as c:
        row = strain._row(c, request.id)
    rolled = strain.roll(ADMIN, str(uuid4()), request.id, row["revision"], state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, rolled["revision"], state(game).revision, 2)
    work = request.id + ":effect"
    assert (
        next(x for x in state(game).strain.events if x.id == request.id).rule_id == rules.JOB_LOSS
    )
    native(
        service,
        source.id,
        1,
        "tag",
        politician=(politicians[0],),
        target=(politicians[2],),
        label="Actually compromised by political favors",
        account="One String inflicts this actual NPC Tag",
    )
    tagged = next(x for x in state(game).world.npcs if x.id == politicians[2])
    assert tagged.tags[-1].label == "Actually compromised by political favors"
    assert tagged.tags[-1].giver_entity == source.handler.model_dump_json()
    victim = next(x for x in state(game).world.npcs if x.id == politicians[1])
    assert not victim.bonds  # Real canonical BondEdge, no fabricated legacy player alias.
    consequence = "The documented hospital disclosure makes the original contact face dismissal"
    native(
        service,
        source.id,
        1,
        "cause",
        work=work,
        original=(victim.id,),
        jobs="civilian",
        consequence=consequence,
        kind=("pilot_play",),
        cause=action,
        account="The source judge links the actual disclosure to this particular pending dismissal",
    )
    cause = rules.records(state(game), rules.Causation)[0]
    with ledger.engine.connect() as c:
        prove_cause(game, c, state(game), cause.id)
        prove_string(game, c, state(game), rules.records(state(game), rules.Earned)[0].id)
    forged = state(game).model_copy(deep=True)
    next(x for x in forged.facts if x.get("id") == cause.id)["body"] = cause.model_copy(
        update={"cause_event": source.event}
    ).model_dump_json()
    with ledger.engine.connect() as c, pytest.raises(WorkflowError):
        prove_cause(game, c, forged, cause.id)
    before_reserve = state(game)
    native(service, source.id, 1, "reserve:" + cause.id, politician=(politicians[0],))
    assert not rules.available(state(game), source.id, politicians[0])
    with pytest.raises(WorkflowError):
        service.cash(
            ADMIN,
            str(uuid4()),
            source.id,
            state(game).revision,
            politicians[0],
            "tag",
            "Cannot double spend",
            target=politicians[1],
            label="Forged overspend",
        )
    # After a real event, interruption rolls back employment, cash-out and source history.
    effects = EffectService(strain)
    real_event = effects.game.event

    def interrupted(*args, **kwargs):
        real_event(*args, **kwargs)
        raise WorkflowError("INTERRUPTED_POLITICAL_EFFECT")

    before_effect = state(game)
    with monkeypatch.context() as patch:
        patch.setattr(effects.game, "event", interrupted)
        with pytest.raises(WorkflowError, match="INTERRUPTED_POLITICAL_EFFECT"):
            effects.apply(
                ADMIN,
                str(uuid4()),
                cause.work,
                cause.work_revision,
                before_effect.revision,
                Choice.model_validate_json(cause.choice_json),
            )
    assert state(game) == before_effect
    completed = native(service, source.id, 1, "finish:" + cause.id, confirm=("actual",))
    completed_state = state(game)
    service.finish_scapegoat(ADMIN, str(completed.id), cause.id, before_effect.revision)
    assert state(game) == completed_state
    after = state(game)
    assert next(x for x in after.world.npcs if x.id == victim.id) == victim
    scapegoat = next(x for x in after.world.npcs if x.id == politicians[0])
    assert scapegoat.employment == "unemployed" and scapegoat.jobs == ("civilian",)
    assert [x.kind for x in rules.records(after, rules.Cashout)] == ["budget", "tag", "scapegoat"]
    with ledger.engine.connect() as c:
        actual = list(
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == work)
                .order_by(t.m3["m3_required_work"].c.revision)
            ).mappings()
        )
        assert actual[-1]["state"] == "resolved"
        assert json.loads(actual[-1]["body_json"])["choice"]["target"] == victim.id
        assert json.loads(actual[0]["body_json"])["source_work"] == request.id
    assert [x for x in after.strain.requests if x.track != "budget"] == preserved_nonbudget
    assert before_reserve.sheets == after.sheets

    async def reopen():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_politician_bribery" and x.identity == source.id
        )
        own = interaction(channel=902)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        text = own.edit_original_response.call_args.kwargs["content"]
        assert "scapegoat" in text and "available Strings 0" in text
        assert "PRIVATE_FEELINGS" not in text

    asyncio.run(reopen())
    with ledger.engine.connect() as c:
        payloads = " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_FEELINGS" not in payloads and consequence not in payloads
    saved = state(game)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    game.rebuild()
    assert state(game) == saved
    assert service.menu(ADMIN, source.id)["cashouts"][-1]["kind"] == "scapegoat"
