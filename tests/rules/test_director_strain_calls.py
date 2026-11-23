"""Fictional phone powers use separate owners, private receipt and native effects."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import D6, prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_custom_strain import RULE as CUSTOM_RULE
from girlframe.engine.m3_custom_strain import Design, Slot, occurrences, replacements
from girlframe.engine.m3_director_strain import RULE, Command, calls
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_director_strain import DirectorStrainService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def phone_scene(store, tmp_path, monkeypatch, extra=(), high=frozenset(), *, prepare_period=True):
    original, game = ready(store)
    policy = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": policy.model_copy(update={"subsystems": policy.subsystems | {"world"}})
        }
    )
    board = initial()
    world = WorldService(original.missions)
    world.initialize(
        ADMIN, "phone-map", state(game).revision, board.board, board.locations, board.gorgons[0]
    )
    director = ActorRef(kind="npc", entity="original-caller")
    roles = NpcRoleService(world)
    offer = roles.offer(
        ADMIN,
        "appoint-fictional-caller",
        state(game).revision,
        Npc(
            id=director.entity,
            name="The real Director",
            detail="Calls from her office.",
            jobs=("director",),
            cell=(0, 0),
            controller=OTHER.user_id,
        ),
    )
    roles.respond(OTHER, "join-fictional-office", offer["id"], state(game).revision, "accept")
    change(CastService(ActorService(original.missions)), OTHER, "join", director)
    with pytest.raises(WorkflowError, match="implementation and review"):
        DirectorStrainService(original).view(OTHER, 900, director)
    period = None
    if prepare_period:
        period = prepared(original, game, high)
    else:
        original.configure(
            ADMIN, "phone-scenario", state(game).revision, "business_as_usual", frozenset()
        )
    approved(store, game, tmp_path, monkeypatch, extra=(RULE, *extra))
    missions = MissionService(store)
    return StrainService(OffDutyService(missions), dice=D6(5)), game, period, director


def native_phone(strain, director, mode, number, **values):
    async def run():
        cast = CastService(ActorService(strain.missions))
        opening = current(OTHER.user_id, number)
        opening.channel_id = 900
        await opening.response.defer(ephemeral=True)
        await open_cast(opening, cast)
        role_menu = opening.edit_original_response.call_args.kwargs["view"]
        action = next(x for x, _ in role_menu.options if x == "phone:" + director.token)
        choose = current(OTHER.user_id, number + 1)
        await choose.response.defer(ephemeral=True)
        await role_menu.open_item(choose, action)
        modes = choose.edit_original_response.call_args.kwargs["view"]
        edit = current(OTHER.user_id, number + 2)
        await edit.response.defer(ephemeral=True)
        await modes.open_item(edit, mode)
        form = edit.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(values)
        confirm = current(OTHER.user_id, number + 3)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    asyncio.run(run())


def test_director_severity_and_event_are_native_distinct_powers(ledger, tmp_path, monkeypatch):
    strain, game, period, director = phone_scene(ledger, tmp_path, monkeypatch)
    service = DirectorStrainService(strain)
    requests = {x.track: x.id for x in state(game).strain.requests}
    strain.roll(ADMIN, "pre-call-budget-die", requests["budget"], 1, state(game).revision)
    before = state(game)
    account = "PRIVATE_DIRECTOR_ACCOUNT"
    command = Command(mode="severity", track="budget", severity="high", account=account)
    with pytest.raises(WorkflowError, match="original joined fictional Director"):
        service.call(ADMIN, "handler-cannot-call", 900, before.revision, director, command)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.call(OTHER, "stale-call", 900, before.revision - 1, director, command)
    ledger.safety(PLAYER, "pause-call", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.call(OTHER, "paused-call", 900, before.revision, director, command)
    ledger.safety(PLAYER, "resume-call", ledger.status(PLAYER)["revision"], pause=False)
    native_phone(
        strain, director, "severity", 39700, track=("budget",), severity=("high",), account=account
    )
    saved = service.call(OTHER, "39703", 900, before.revision, director, command)
    assert saved["effect"] is None and len(calls(state(game))) == 1
    assert state(game).strain.levels["budget"] == "high"
    assert state(game).strain.events == before.strain.events
    assert strain.work(ADMIN, requests["budget"])["body"]["severity"] == "low"

    native_phone(
        strain,
        director,
        "severity",
        39710,
        track=("rebellion",),
        severity=("high",),
        account=account,
    )
    row = strain.work(ADMIN, requests["rebellion"])
    assert row["revision"] == 2 and row["body"]["severity"] == "high"
    with pytest.raises(WorkflowError, match="STALE_WORK"):
        strain.roll(ADMIN, "old-rebellion", requests["rebellion"], 1, state(game).revision)
    assert strain.dice.calls == 1
    command = Command(
        mode="trigger",
        track="rebellion",
        severity="low",
        account=account,
        slot=Slot(track="rebellion", severity="low", face=1, column=2),
    )
    revision = state(game).revision
    native_phone(strain, director, "trigger", 39720, event=(command.target_rule,), account=account)
    record = service.call(OTHER, "39723", 900, revision, director, command)
    effect = record["effect"]
    assert effect and not state(game).refusal_bonuses
    assert len(calls(state(game))) == 3 and strain.dice.calls == 1
    effects = EffectService(strain)
    with pytest.raises(WorkflowError):
        effects.get(OTHER, effect)
    assert effects.get(ADMIN, effect)["off_duty_id"] == period
    receipt = effects.apply(
        ADMIN,
        "apply-phone-effect",
        effect,
        1,
        state(game).revision,
        Choice(rule_id=command.target_rule or "", account="Actual change to next disobedience"),
    )
    assert receipt["state"] == "resolved" and state(game).refusal_bonuses[-1].id == effect
    ledger.engine.dispose()
    assert service.receipt(ADMIN, record["id"]).command.account == account
    assert service.receipt(OTHER, record["id"]).effect == effect
    assert not any(x.task == "m3_director_strain_call" for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError, match="original participants"):
        service.receipt(PLAYER, record["id"])

    async def read():
        inbox = InboxService(ledger)
        card = next(x for x in inbox.items(ADMIN) if x.identity == record["id"])
        click = current(ADMIN.user_id, 39730)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, card)
        assert "PRIVATE" in str(click.edit_original_response.call_args)

    asyncio.run(read())
    change(CastService(ActorService(strain.missions)), OTHER, "withdraw", director)
    with pytest.raises(WorkflowError, match="joined fictional Director"):
        service.call(OTHER, "call-after-withdrawal", 900, state(game).revision, director, command)


def test_director_replaces_unrolled_printed_slot_without_picking_its_column(
    ledger, tmp_path, monkeypatch
):
    strain, game, period, director = phone_scene(
        ledger, tmp_path, monkeypatch, extra=(CUSTOM_RULE,)
    )
    service, world = DirectorStrainService(strain), WorldService(strain.missions)
    for identity, revealed in (("public-tech", True), ("private-tech", False)):
        world.npc(
            ADMIN,
            "new-" + identity,
            state(game).revision,
            Npc(
                id=identity,
                name=identity,
                cell=(0, 0),
                detail="Actual local technician.",
                jobs=("mechanic",),
                controller=1,
                revealed=revealed,
            ),
        )
    view = service.view(OTHER, 900, director)
    assert tuple(x[0] for x in view["targets"]) == ("public-tech",)
    before = state(game)
    selected = Slot(track="budget", severity="low", face=5, column=2)
    design = Design(
        title="Score a safety failure",
        tag="Under scrutiny",
        npc="public-tech",
        account="The technicians are called to account.",
    )
    command = Command(
        mode="replace",
        track="budget",
        severity="low",
        slot=selected,
        design=design,
        account=design.account,
    )
    with pytest.raises(WorkflowError, match="known eligible"):
        service.call(
            OTHER,
            "unknown-npc",
            900,
            before.revision,
            director,
            command.model_copy(
                update={"design": design.model_copy(update={"npc": "private-tech"})}
            ),
        )
    assert state(game) == before
    native_phone(
        strain,
        director,
        "replace",
        39740,
        event=("strain.budget.low.5.2",),
        title=design.title,
        tag=design.tag,
        npc=(design.npc,),
        account=design.account,
    )
    saved = service.call(OTHER, "39743", 900, before.revision, director, command)
    (replacement,) = replacements(state(game))
    assert (
        replacement.actor == director and replacement.roll is None and replacement.id == saved["id"]
    )
    assert replacement.period == period and state(game).strain == before.strain
    assert not occurrences(state(game)) and strain.dice.calls == 0
    work = next(x.id for x in state(game).strain.requests if x.track == "budget")
    assert strain.roll(ADMIN, "roll-custom-phone", work, 1, state(game).revision)["face"] == 5
    assert strain.work(ADMIN, work)["custom_columns"] == {"2": design.title}
    with pytest.raises(WorkflowError):
        strain.choose(OTHER, "director-cannot-choose", work, 2, state(game).revision, 2)
    receipt = strain.choose(ADMIN, "choose-phone-replacement", work, 2, state(game).revision, 2)
    assert receipt["rule_id"] == CUSTOM_RULE and not receipt["effects_pending"]
    actual = state(game)
    assert actual.strain.events[-1].rule_id == "strain.budget.low.5.2"
    assert not actual.world.rooms and strain.dice.calls == 1
    assert occurrences(actual)[0].replaces == replacement.id
    assert actual.world.npcs[-2].tags[-1].label == design.tag


def test_director_creates_and_immediately_rolls_a_persistent_track(ledger, tmp_path, monkeypatch):
    from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
    from test_strain import facts

    from girlframe.discord_adapter.m3_director_strain import track_design
    from girlframe.engine.m3_named_strain import rolls, tables
    from girlframe.engine.m3_void_rift import RULE as RIFT
    from girlframe.engine.m3_void_rift import rifts
    from girlframe.services.m3_custom_strain import CustomStrainService
    from girlframe.services.m3_named_strain import NamedStrainService
    from girlframe.services.m3_off_duty_cycle import CycleService

    strain, game, period, director = phone_scene(
        ledger, tmp_path, monkeypatch, extra=(CUSTOM_RULE,), high=frozenset({"void"})
    )
    world, effects = WorldService(strain.missions), EffectService(strain)
    npc = Npc(
        id="radio-engineer",
        name="Radio engineer",
        jobs=("mechanic",),
        cell=(0, 0),
        detail="The base engineer has handled the earlier outages.",
        controller=1,
        revealed=True,
    )
    world.npc(ADMIN, "introduce-radio-engineer", state(game).revision, npc)
    void = next(x for x in state(game).strain.requests if x.track == "void")
    strain.dice.face = 6
    strain.roll(ADMIN, "rift-die", void.id, 1, state(game).revision)
    strain.dice.face = 1
    strain.choose(ADMIN, "rift-column", void.id, 2, state(game).revision, 1)
    effects.apply(
        ADMIN,
        "rift-first",
        void.id + ":effect",
        1,
        state(game).revision,
        Choice(
            rule_id=RIFT,
            account="The first Gorgon emerges",
            gorgon=gorgon("dormant", "first-rift", (1, 1)),
        ),
    )
    faces = "\n".join(f"{i}A | Tag {i}A | {i}B | Tag {i}B" for i in range(1, 7))
    name, account = "Radio interference", "Original effects from the failed radio network."
    design = track_design(name, npc.id, faces)
    command = Command(mode="create_track", new_track=design, account=account)
    revision = state(game).revision
    calls_before = strain.dice.calls
    strain.dice.face = 5
    with monkeypatch.context() as injected:
        injected.setattr("girlframe.services.m3_strain.StrainService", lambda _: strain)
        native_phone(
            strain,
            director,
            "create_track",
            39750,
            name=name,
            npc=(npc.id,),
            faces=faces,
            account=account,
        )
    phone = DirectorStrainService(strain)
    receipt = phone.call(OTHER, "39753", 900, revision, director, command)
    work = receipt["effect"]
    assert receipt["face"] == 5 and strain.dice.calls == calls_before + 1
    actual = state(game)
    (table,), (rolled,) = tables(actual), rolls(actual)
    assert table.design == design and rolled.id == work and rolled.track == table.id
    assert rolled.source == receipt["id"] and rolled.column is None
    assert actual.world.npcs[-1].tags == ()
    arrival = rifts(actual)[0].arrivals[-1]
    assert arrival.roll == work and not arrival.performed
    named = NamedStrainService(strain)
    assert not any(x.identity == work for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        named.view(OTHER, work)
    with pytest.raises(WorkflowError, match="choosing one actual column"):
        named.advance(ADMIN, "duplicate-die", work, actual.revision, 1, None)
    assert strain.dice.calls == calls_before + 1

    async def inbox_choose():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == work)
        assert item.task == "m3_named_strain"
        click = current(ADMIN.user_id, 39754)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, ADMIN.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].options == (("1", "5A"), ("2", "5B"))
        form.values["option"] = ("2",)
        await form.confirm.callback(current(ADMIN.user_id, 39755))
        assert form.completed

    asyncio.run(inbox_choose())
    assert named.advance(ADMIN, "39755", work, actual.revision, 1, 2)["column"] == 2
    assert state(game).world.npcs[-1].tags[-1].label == "Tag 5B"
    assert strain.dice.calls == calls_before + 1
    ledger.engine.dispose()
    assert named.view(ADMIN, work)["status"] == "resolved"
    effects.apply(
        ADMIN,
        "rift-arrival-from-named",
        arrival.work,
        1,
        state(game).revision,
        Choice(
            rule_id=RIFT,
            account="The last Gorgon emerges",
            gorgon=gorgon("dormant", "last-rift", (2, 1)),
        ),
    )
    authored = CustomStrainService(strain)
    for request in state(game).strain.requests:
        authored.author(
            ADMIN,
            "replaced-" + request.track,
            period,
            state(game).revision,
            "instead_of_roll",
            Design(
                title="Routine check", tag="Checked " + request.track, npc=npc.id, account=account
            ),
            work=request.id,
        )
    change(CastService(ActorService(strain.missions)), OTHER, "withdraw", director)
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    following = strain.periods.begin(ADMIN, "next-named-period")["id"]
    after = state(game)
    present = sum(any(a.void for a in x.assets) for x in after.sheets.values())
    strain.prepare(
        ADMIN,
        "schedule-persistent-track",
        following,
        1,
        after.revision,
        facts(at_least_half_have_void=present * 2 >= len(after.order), no_girl_void=not present),
    )
    work = following + ":named-strain:" + table.id
    assert named.view(ADMIN, work)["face"] is None
    strain.dice.face = 2
    revision = state(game).revision
    second = named.advance(ADMIN, "next-named-die", work, revision, 1, None)
    assert second == named.advance(ADMIN, "next-named-die", work, revision, 1, None)
    assert second["face"] == 2
    named.advance(ADMIN, "apply-next-named-column", work, state(game).revision, 2, 1)
    assert state(game).world.npcs[-1].tags[-1].label == "Tag 2A"
    assert strain.dice.calls == calls_before + 2


def test_director_can_roll_a_new_track_before_the_first_off_duty(ledger, tmp_path, monkeypatch):
    from girlframe.discord_adapter.m3_director_strain import track_design
    from girlframe.engine.m3_named_strain import rolls
    from girlframe.services.m3_named_strain import NamedStrainService

    strain, game, period, actor = phone_scene(
        ledger, tmp_path, monkeypatch, extra=(CUSTOM_RULE,), prepare_period=False
    )
    assert period is None
    WorldService(strain.missions).npc(
        ADMIN,
        "known-radio-tech",
        state(game).revision,
        Npc(
            id="radio",
            name="Radio technician",
            cell=(0, 0),
            detail="Known from the base.",
            jobs=("mechanic",),
            controller=1,
            revealed=True,
        ),
    )
    faces = "\n".join(f"{i}A | Tag {i}A | {i}B | Tag {i}B" for i in range(1, 7))
    command = Command(
        mode="create_track",
        new_track=track_design("Signal", "radio", faces),
        account="The Director describes the new complication.",
    )
    phone = DirectorStrainService(strain)
    result = phone.call(OTHER, "no-period-call", 900, state(game).revision, actor, command)
    work = result["effect"]
    assert rolls(state(game))[0].period_id is None and not state(game).strain.periods
    with pytest.raises(WorkflowError, match="does not already exist"):
        phone.call(OTHER, "repeat-track-name", 900, state(game).revision, actor, command)
    assert strain.dice.calls == 1
    named = NamedStrainService(strain)
    assert any(
        x.identity == work and x.task == "m3_named_strain"
        for x in InboxService(ledger).items(ADMIN)
    )
    assert (
        named.advance(ADMIN, "first-periodless-choice", work, state(game).revision, 1, 1)["column"]
        == 1
    )
    assert state(game).world.npcs[-1].tags[-1].label == "Tag 5A"
