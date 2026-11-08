"""Synthetic actual-source Handler effects; never automatic player dialogue or consent."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_world_service import ready as world_ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays, open_play
from girlframe.engine import m3_handler_plays as rules
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_careers import stamp_tag_givers
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    _, game = world_ready(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    return HandlerPlayService(store), game


def begin(svc, game, targets=(2,)):
    canon = state(game)
    result = svc.start(
        ADMIN, str(uuid4()), canon.revision, tuple(current_ref(canon, x) for x in targets)
    )
    return result["id"]


def test_brief_threat_expectation_are_real_owned_saved_facts_not_player_responses(ledger):
    svc, game = ready(ledger)
    for kind, extra in (
        ("brief", {}),
        ("escalate", dict(detail="A real approaching signal", stakes="The relay will fail")),
        (
            "expectation",
            dict(detail="Keep the relay intact", stakes="Foundation discipline for abandonment"),
        ),
    ):
        identity = begin(svc, game)
        data = svc.get(ADMIN, identity)
        effect = Effect(kind=kind, account="Actual source information for the scene", **extra)
        result = svc.submit(ADMIN, kind, identity, data["game_revision"], kind, effect)
        assert svc.submit(ADMIN, kind, identity, data["game_revision"], kind, effect) == result
        saved = rules.record(state(game), identity)
        assert saved.state == "complete" and saved.effect == effect
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_responses"])) == 0
    assert not svc.tasks(ADMIN)


def test_mess_changes_actual_status_and_gives_source_bound_tag_once(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game, (3,))
    canon = state(game)
    target = current_ref(canon, 3)
    svc.submit(
        ADMIN,
        "raise-actual",
        identity,
        canon.revision,
        "mess",
        Effect(kind="status", account="Actual performance", target=target, status=1),
    )
    assert state(game).order[0] == 3
    identity = begin(svc, game, (3,))
    canon = state(game)
    outcome = svc.submit(
        ADMIN,
        "new-tag",
        identity,
        canon.revision,
        "mess",
        Effect(kind="tag", account="Actual visible conduct", target=target, tag="Observed"),
    )
    tagged = next(x for x in state(game).sheets["3"].tags if x.id == identity + ":tag")
    assert tagged.giver_actor == current_ref(canon, 1) and outcome["state"] == "complete"
    assert tagged.gm_setter_appointment is None


def test_source_targets_membership_pause_and_races_do_not_silently_apply(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game)
    canon = state(game)
    effect = Effect(
        kind="tag", account="Actual assertion", target=current_ref(canon, 3), tag="Wrong target"
    )
    with pytest.raises(WorkflowError, match="another original"):
        svc.submit(ADMIN, "wrong-target", identity, canon.revision, "mess", effect)
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, identity)
    assert state(game) == canon
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.submit(
            ADMIN,
            "paused",
            identity,
            canon.revision,
            "brief",
            Effect(kind="brief", account="Cannot apply while paused"),
        )
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    svc.submit(
        ADMIN,
        "real",
        identity,
        canon.revision,
        "brief",
        Effect(kind="brief", account="Actual information"),
    )
    with pytest.raises(WorkflowError):
        svc.submit(
            ADMIN,
            "second-effect",
            identity,
            state(game).revision,
            "brief",
            Effect(kind="brief", account="Cannot spend grant twice"),
        )


def test_introduce_support_creates_owned_revealed_employee_without_borrowing_other_human(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game)
    canon = state(game)
    assert canon.world
    npc = Npc(
        id="support-technician",
        name="Technician",
        jobs=("mechanic",),
        detail="A regular employee",
        controller=ADMIN.user_id,
        cell=canon.world.locations[0].cell,
        revealed=True,
        employment="foundation",
    )
    svc.submit(
        ADMIN,
        "real-support",
        identity,
        canon.revision,
        "support",
        Effect(kind="support", account="Arrives to support the fight", npc=npc),
    )
    assert state(game).world.npcs[-1] == npc
    identity = begin(svc, game)
    before = state(game)
    with pytest.raises(WorkflowError, match="own control"):
        svc.submit(
            ADMIN,
            "cannot-own-other",
            identity,
            before.revision,
            "support",
            Effect(
                kind="support",
                account="No fabricated ownership",
                npc=npc.model_copy(update={"id": "other-technician", "controller": PLAYER.user_id}),
            ),
        )
    assert state(game) == before


def test_new_ooc_tag_requires_actual_event_gm_appointment_not_arbitrary_marker(ledger):
    from girlframe.services.m3_medical import MedicalService

    svc, game = ready(ledger)
    canon = state(game)
    with ledger.engine.connect() as c:
        appointment = MedicalService(ledger)._handler(c)[1]
    tag = TagState(
        id="ooc-proven",
        label="From the actual human GM",
        giver=1,
        gm_setter_appointment=appointment,
    )
    altered = canon.model_copy(deep=True)
    altered.sheets["2"].tags.append(tag)
    with pytest.raises(ValueError, match="authenticated GM appointment"):
        stamp_tag_givers(canon, altered, "actual-event")
    with ledger.transaction() as c:
        event = game.event(c, 1, "actual-ooc", "m3.synthetic_ooc_tag", altered)
    actual = next(x for x in state(game).sheets["2"].tags if x.id == tag.id)
    assert actual.gm_setter_event == event and actual.giver_actor is None
    with ledger.transaction() as c:
        before = state(game)
        before.sheets["2"].tags.append(tag.model_copy(update={"id": "forged-other-human"}))
        with pytest.raises(ValueError, match="authenticated GM appointment"):
            game.event(c, 2, "forged-ooc", "m3.synthetic_invalid_ooc_tag", before)


def test_native_owned_basic_menu_and_real_effect_form(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game)

    async def run():
        interaction = current(1)
        await interaction.response.defer(ephemeral=True)
        await open_handler_plays(interaction, svc)
        hub = interaction.edit_original_response.call_args.kwargs["view"]
        assert "off_duty" in dict(hub.options)
        assert not await hub.interaction_check(current(2))
        await open_play(interaction, svc, identity)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(interaction, "expectation")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            account="Actual instruction",
            detail="Stay with the Cadre",
            stakes="Actual review afterwards",
        )
        await form.confirm.callback(current(1, 77881))
        assert form.completed

    asyncio.run(run())
    assert rules.record(state(game), identity).effect.detail == "Stay with the Cadre"


def counter(store, svc, game):
    from test_m2_game import start

    from girlframe.engine.m3_careers import end
    from girlframe.services.m3_handler_plays import request_handler_play

    action_id = start(game)
    with store.transaction() as c:
        action = game.action(c, action_id)
        # Trusted synthetic producer for the pure/source bridge; actual Battle owns
        # the real Core roll/tier/printed selection end-to-end test.
        action["data"]["play"] = "go_for_the_core"
        game.save_action(c, action)
        canon = state(game)
        chooser, victim = current_ref(canon, 3), current_ref(canon, 2)
        choice = game.request(
            c,
            action,
            3,
            "battle_counter",
            dict(actor=chooser.model_dump(mode="json"), attacker=victim.model_dump(mode="json")),
        )
        event = str(uuid4())
        canon, identity = request_handler_play(
            game,
            c,
            action_id,
            choice,
            "go_for_the_core.high",
            chooser,
            3,
            victim,
            event,
            state=canon,
            final_original=True,
        )
        sheet = canon.sheets["3"]
        canon = end(
            canon,
            chooser,
            reason="death",
            source_event=event,
            account="The real original's final counter",
            archive_id="counter-original",
            profile_id=sheet.character_id,
            profile_revision=sheet.source_profile_revision,
        )
        game.event(
            c, 3, "source-final-counter", "m3.synthetic_actual_final_counter", canon, event_id=event
        )
        c.execute(
            t.m2["m2_responses"]
            .insert()
            .values(
                campaign_id=store.campaign_id,
                choice_id=choice,
                actor_id="3",
                event_id=event,
                answer_json=json.dumps(dict(options=["target_dies_with_handler_play"])),
            )
        )

    return identity


def test_counter_is_source_bound_to_dying_original_and_never_appoints_chooser_gm(
    ledger, monkeypatch
):
    import sys
    import types
    from unittest.mock import Mock

    callback = Mock()
    monkeypatch.setitem(
        sys.modules,
        "girlframe.services.m3_battle",
        types.SimpleNamespace(complete_handler_play=callback),
    )
    svc, game = ready(ledger)
    identity = counter(ledger, svc, game)
    before = state(game)
    assert before.handler == 1 and "3" not in before.sheets
    with pytest.raises(WorkflowError):
        svc.get(ADMIN, identity)
    data = svc.get(OTHER, identity)
    target = rules.record(before, identity).targets[0]
    effect = Effect(
        kind="tag",
        account="The original's last act against the actual attacker",
        target=target,
        tag="Last word",
    )
    result = svc.submit(
        OTHER, "actual-source-counter", identity, data["game_revision"], "mess", effect
    )
    assert result["state"] == "complete" and callback.call_count == 1
    after = state(game)
    tag = next(x for x in after.sheets["2"].tags if x.id == identity + ":tag")
    assert tag.giver_actor == before.career_archives[-1].actor
    assert after.handler == 1 and "3" not in after.sheets
    assert after.career_archives == before.career_archives
    with pytest.raises(WorkflowError):
        svc.start(OTHER, "not-global-gm", after.revision, (target,))


def test_forced_handler_death_has_real_fatal_source_without_fabricated_assets_choice(ledger):
    from test_m2_game import start

    from girlframe.services.m3_handler_consequences import force_end_handler

    svc, game = ready(ledger)
    untouched = begin(svc, game)
    action_id = start(game)
    with ledger.transaction() as c:
        action = game.action(c, action_id)
        action["data"]["play"] = "go_for_the_core"
        game.save_action(c, action)
        canon = state(game)
        actual = current_ref(canon, 1)
        event = str(uuid4())
        changed = force_end_handler(
            game,
            c,
            canon,
            actual,
            source_action=action_id,
            source_choice=None,
            clause="go_for_the_core.mid",
            event=event,
            account="The printed fatal source actually ends this body",
        )
        game.event(
            c, 2, "actual-forced-death", "m3.synthetic_actual_core_fatal", changed, event_id=event
        )
    after = state(game)
    assert after.handler == 1 and after.handler_archives[-1].actor == actual
    assert len(after.handler_fatal_sources) == 1 and not after.handler_consequences
    assert after.handler_fatal_sources[0].source_event == after.handler_archives[-1].source_event

    stale = svc.get(ADMIN, untouched)
    assert stale["stale"]
    with pytest.raises(WorkflowError, match="body context changed"):
        svc.submit(
            ADMIN,
            "cannot-use-old-persona",
            untouched,
            state(game).revision,
            "brief",
            Effect(kind="brief", account="No revival"),
        )
    svc.withdraw(ADMIN, "withdraw-old-draft", untouched, state(game).revision)
    assert rules.record(state(game), untouched).state == "withdrawn"
    assert game.inspect(PLAYER, action_id)["state"] != "complete"


def test_handler_go_off_duty_uses_complete_real_period_scene_and_status_review(ledger):
    from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, recover_both

    cycle, game, period = prepared(ledger)
    svc = HandlerPlayService(ledger)
    identity = begin(svc, game)
    svc.submit(
        ADMIN,
        "actual-period-link",
        identity,
        state(game).revision,
        "off_duty",
        Effect(
            kind="off_duty",
            account="The actual Handler will attend the Cadre's base scene",
            off_duty=period,
        ),
    )
    assert rules.record(state(game), identity).state == "awaiting_effect"
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    assert rules.record(state(game), identity).state == "awaiting_effect"
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    grant = rules.record(state(game), identity)
    assert grant.state == "complete" and grant.effect.off_duty == period
    assert cycle.periods.current(PLAYER) is None


def test_punish_uses_actual_instruction_scene_attendance_effect_and_followups(ledger):
    from test_role_punishments import change

    from girlframe.engine.m3_punishments import Details
    from girlframe.engine.m3_role_punishment_state import Instruction
    from girlframe.services.m3_role_punishments import RolePunishmentService

    svc, game = ready(ledger)
    identity = begin(svc, game)
    before = state(game)
    result = svc.submit(
        ADMIN,
        "source-handler-discipline",
        identity,
        before.revision,
        "punish",
        Effect(
            kind="punish",
            account="Actual source discipline",
            target=current_ref(before, 2),
            executor=current_ref(before, 1),
        ),
    )
    assert (
        result["state"] == "awaiting_effect"
        and state(game).sheets["2"].heat == before.sheets["2"].heat
    )
    case_id = rules.record(state(game), identity).followups[0]
    service = RolePunishmentService(game)
    details = Details(kind="stimulant_injection")
    change(
        service,
        ADMIN,
        case_id,
        instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
    )
    change(service, ADMIN, case_id, scene="The actual Handler carries out the discipline on screen")
    with pytest.raises(WorkflowError):
        change(service, ADMIN, case_id, execute=True, account="Cannot invent patient attendance")
    change(service, PLAYER, case_id, attest=True)
    change(
        service,
        ADMIN,
        case_id,
        execute=True,
        account="The actual source injection was administered",
    )
    after = state(game)
    assert after.sheets["2"].heat == 7
    assert rules.record(after, identity).state == "complete"
    assert after.role_punishments[-1].completion_event


def test_only_original_counter_owner_can_explicitly_decline_optional_last_act(ledger, monkeypatch):
    import sys
    import types
    from unittest.mock import Mock

    callback = Mock()
    monkeypatch.setitem(
        sys.modules,
        "girlframe.services.m3_battle",
        types.SimpleNamespace(complete_handler_play=callback),
    )
    svc, game = ready(ledger)
    identity = counter(ledger, svc, game)
    before = state(game)
    with pytest.raises(WorkflowError):
        svc.decline(ADMIN, "not-my-counter", identity, before.revision)
    result = svc.decline(OTHER, "actual-own-decline", identity, before.revision)
    assert svc.decline(OTHER, "actual-own-decline", identity, before.revision) == result
    after = state(game)
    grant = rules.record(after, identity)
    assert grant.state == "declined" and grant.effect is None and grant.declined_event
    assert callback.call_count == 1 and after.career_archives == before.career_archives
    assert after.sheets == before.sheets and after.handler == before.handler
    assert not svc.tasks(OTHER)


def test_handler_asset_damage_uses_actual_owned_physical_source_and_real_asset(ledger):
    from test_physical_service import decide, propose

    from girlframe.services.m3_physical import PhysicalService

    svc, game = ready(ledger)
    physical = PhysicalService(ledger)
    proposed = propose(physical)
    decide(physical, proposed["id"])
    identity = begin(svc, game)
    before = state(game)
    asset = next(x for x in before.sheets["2"].assets if x.family == "frame" and not x.damaged)
    target = current_ref(before, 2)
    result = svc.submit(
        ADMIN,
        "actual-handler-damage",
        identity,
        before.revision,
        "mess",
        Effect(
            kind="damage",
            account="Actual source damage to the owned Frame Asset",
            target=target,
            asset=asset.id,
        ),
    )
    after = state(game)
    assert result["state"] == "complete" and rules.record(after, identity).state == "complete"
    assert next(x for x in after.sheets["2"].assets if x.id == asset.id).damaged
    assert after.placements == before.placements and after.order == before.order
    with pytest.raises(WorkflowError):
        svc.submit(
            ADMIN,
            "cannot-damage-twice",
            identity,
            after.revision,
            "mess",
            Effect(
                kind="damage", account="No duplicate grant spend", target=target, asset=asset.id
            ),
        )


def test_last_frame_damage_waits_for_real_source_defeat_before_handler_play_completes(ledger):
    from test_m2_game import Dice, Gateway, answer, pass_tags, tick
    from test_physical_service import decide, propose

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m3_physical import PhysicalService

    svc, game = ready(ledger)
    physical = PhysicalService(ledger)
    decide(physical, propose(physical)["id"])
    target = current_ref(state(game), 2)
    frames = [x.id for x in state(game).sheets["2"].assets if x.family == "frame"]
    for i, asset in enumerate(frames):
        identity = begin(svc, game)
        svc.submit(
            ADMIN,
            "actual-frame-damage-" + str(i),
            identity,
            state(game).revision,
            "mess",
            Effect(
                kind="damage", account="Actual cumulative Frame damage", target=target, asset=asset
            ),
        )
    grant = rules.record(state(game), identity)
    assert grant.state == "awaiting_effect" and len(grant.followups) == 1
    work_id = grant.followups[0]
    game.dice = Dice((3, 3))
    action = game.begin(
        PLAYER,
        "actual-damage-defeat",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            context="Actual mandatory Defeat after Handler damage",
            trigger_confirmed=True,
            source_work=work_id,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    assert rules.record(state(game), identity).state == "awaiting_effect"
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="Escape the actual defeated Frame",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert rules.record(state(game), identity).state == "complete"
    assert game.dice.calls == 1


def test_handler_damage_waits_for_actual_handler_owned_replacement_and_persists_injury(ledger):
    from girlframe.services.m3_handler_consequences import HandlerConsequenceService

    svc, game = ready(ledger)
    before = state(game)
    target = current_ref(before, 1)
    identity = svc.start(ADMIN, "source-would-damage-handler", before.revision, (target,))["id"]
    svc.submit(
        ADMIN,
        "actual-would-damage",
        identity,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="Actual source would damage this Handler",
            target=target,
            opponent=current_ref(before, 2),
        ),
    )
    staged = rules.record(state(game), identity)
    assert staged.state == "awaiting_effect" and staged.followups
    consequence = state(game).handler_consequences[-1]
    body = HandlerConsequenceService(ledger)
    data = body.get(ADMIN, consequence.id)
    with pytest.raises(WorkflowError):
        body.respond(
            PLAYER,
            "cannot-choose-injury",
            consequence.id,
            data["game_revision"],
            "injury",
            "No other person's choice",
        )
    body.respond(
        ADMIN,
        "own-real-injury",
        consequence.id,
        data["game_revision"],
        "injury",
        "The actual Handler suffers a persistent injured arm",
    )
    after = state(game)
    assert rules.record(after, identity).state == "complete"
    assert after.handler_injuries[-1].actor == target
    assert (
        after.handler_injuries[-1].description
        == "The actual Handler suffers a persistent injured arm"
    )
    assert after.handler_persona == before.handler_persona and not after.handler_archives


def test_source_notice_reaches_only_affected_original_humans_without_private_npc_details(ledger):
    svc, game = ready(ledger)
    identity = begin(svc, game)
    canon = state(game)
    npc = Npc(
        id="notice-worker",
        name="Visible technician",
        jobs=("mechanic",),
        detail="PRIVATE_GM_NPC_DETAIL",
        controller=1,
        cell=canon.world.locations[0].cell,
        revealed=True,
    )
    svc.submit(
        ADMIN,
        "actual-visible-support",
        identity,
        canon.revision,
        "support",
        Effect(kind="support", account="A technician arrives with a repair cart", npc=npc),
    )
    with ledger.engine.connect() as c:
        assert svc._notices(c, PLAYER)[0]["id"] == identity
        assert not svc._notices(c, OTHER)
    notice = svc.notice(PLAYER, identity)
    assert notice["account"] == "A technician arrives with a repair cart"
    assert notice["employee"] == {"name": "Visible technician"}
    assert "PRIVATE" not in str(notice) and "source_fingerprint" not in str(notice)
    with pytest.raises(WorkflowError):
        svc.notice(OTHER, identity)
    before = state(game)

    async def run():
        from girlframe.discord_adapter.m3_handler_plays import open_notice

        interaction = current(2)
        await interaction.response.defer(ephemeral=True)
        await open_notice(interaction, svc, identity)
        text = interaction.edit_original_response.call_args.kwargs["content"]
        assert "repair cart" in text and "PRIVATE" not in text

    asyncio.run(run())
    assert state(game) == before


def test_same_handler_lobotomy_uses_real_saved_surgery_and_patient_response(ledger):
    from test_role_punishments import change

    from girlframe.engine.m3_lobotomy_state import Plan
    from girlframe.engine.m3_punishments import Details
    from girlframe.engine.m3_role_punishment_state import Instruction
    from girlframe.services.m3_lobotomy import LobotomyService
    from girlframe.services.m3_role_punishments import RolePunishmentService

    svc, game = ready(ledger)
    identity = begin(svc, game)
    before = state(game)
    svc.submit(
        ADMIN,
        "handler-surgery-source",
        identity,
        before.revision,
        "punish",
        Effect(
            kind="punish",
            account="Actual severe discipline",
            target=current_ref(before, 2),
            executor=current_ref(before, 1),
        ),
    )
    case_id = rules.record(state(game), identity).followups[0]
    role = RolePunishmentService(game)
    details = Details(kind="lobotomization")
    change(
        role,
        ADMIN,
        case_id,
        instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
    )
    change(role, ADMIN, case_id, scene="Actual inflictor and patient scene for the chosen surgery")
    change(role, PLAYER, case_id, attest=True)
    result = change(role, ADMIN, case_id, execute=True, account="Begin the actual selected surgery")
    assert (
        result["state"] == "surgery_pending"
        and rules.record(state(game), identity).state == "awaiting_effect"
    )
    surgery = LobotomyService(ledger)
    plan = Plan(
        options=("name",),
        room="Actual room",
        restraints="Actual restraints",
        tools="Actual tools",
        new_name="RENAMED",
    )
    surgery.prepare(ADMIN, "own-actual-plan", result["surgery"], state(game).revision, plan)
    surgery.respond(
        PLAYER,
        "own-patient-description",
        result["surgery"],
        state(game).revision,
        {"name": "The actual original patient supplies the printed description"},
    )
    surgery.finish(ADMIN, "actual-complete-surgery", result["surgery"])
    after = state(game)
    assert (
        after.sheets["2"].callsign == "RENAMED"
        and rules.record(after, identity).state == "complete"
    )
    assert after.role_punishments[-1].completion_event and after.lobotomies[-1].phase == "applied"
