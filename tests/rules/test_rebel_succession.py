"""The new Foundation's sentence and surviving approval must reach actual canon."""

import asyncio

import pytest
from test_handler_creation import agree, complete
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_strain_service import prepared, ready
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_rebel_succession import RULE, successions
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_rebel_succession import SuccessionService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_new_foundation_endgame_executes_and_requires_exact_approved_successor(ledger):
    strain, game = ready(ledger, face=6)
    approval, policy = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays", "playbooks"})
            ),
            owner_m3_rulings=policy.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    authority = GuildViewer(4, 200, True, False)
    ledger.join(authority, "new-foundation-authority")
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN,
        "new-foundation-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    group = Faction(id="new-foundation", name="New Foundation", kind="rebel", cells=((0, 4),))
    worlds.faction(ADMIN, "original-new-foundation", state(game).revision, group)
    roles = NpcRoleService(worlds)
    judge = Npc(
        id="new-foundation-judge",
        name="Foundation Judge",
        jobs=("director",),
        controller=4,
        detail="Independent original court authority",
        cell=(0, 0),
        revealed=True,
        faction=group.id,
    )
    offer = roles.offer(ADMIN, "offer-court-controller", state(game).revision, judge)
    roles.respond(authority, "answer-court-controller", offer["id"], state(game).revision, "accept")
    with ledger.transaction() as c:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, "succession-void-fixture", "synthetic.no_void_assets", canon)
    period = prepared(strain, game, high=frozenset({"rebellion"}))
    number = 0
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, f"court-roll-{number}", request.id, 1, state(game).revision)
        strain.choose(ADMIN, f"court-cascade-{number}", request.id, 2, state(game).revision, 2)
        number += 1
    selected = strain.choose(
        ADMIN,
        "new-foundation-slot",
        request.id,
        1,
        state(game).revision,
        7,
        endgame=True,
        faction=group.id,
    )
    assert selected["rule_id"] == RULE
    work = request.id + ":effect"
    effects = EffectService(strain)
    for index, request in enumerate(tuple(state(game).strain.requests)):
        if request.track == "void":
            face, column, choice = (
                2,
                1,
                Choice(
                    rule_id="strain.void.low.2.1",
                    account="Unrelated arrival.",
                    gorgon=gorgon("dormant", "court-other-gorgon", (0, 1)),
                ),
            )
        elif request.track == "rebellion":
            face, column, choice = (
                1,
                2,
                Choice(rule_id="strain.rebellion.low.1.2", account="Control slips."),
            )
        else:
            face, column, choice = (
                5,
                2,
                Choice(rule_id="strain.budget.low.5.2", account="Unrelated room.", rooms=((2, 3),)),
            )
        strain.dice.face = face
        strain.roll(ADMIN, f"court-other-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, f"court-other-column-{index}", request.id, 2, state(game).revision, column
        )
        effects.apply(
            ADMIN,
            f"court-other-effect-{index}",
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )

    inbox = InboxService(ledger)

    async def native(viewer, number, **values):
        click = current(viewer.user_id, number)
        await click.response.defer(ephemeral=True)
        cards = [
            x for x in inbox.items(viewer) if x.identity == work and x.task == "m3_rebel_succession"
        ]
        assert len(cards) == 1
        await InboxView(inbox, viewer.user_id).route(click, cards[0])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm), click.edit_original_response.call_args
        form.values.update(values)
        submitted = current(viewer.user_id, number + 1)
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.edit_original_response.call_args,
            submitted.followup.send.call_args,
        )

    service = SuccessionService(strain)
    cycle = CycleService(strain.periods)
    original = active_handler(state(game))
    asyncio.run(native(ADMIN, 43700, judge=(judge.id,)))
    assert next(x for x in state(game).world.factions if x.id == group.id).kind == "foundation"
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    with pytest.raises(WorkflowError, match="original participants"):
        service.get(PLAYER, work)
    with pytest.raises(WorkflowError, match="actual original owner"):
        service.respond(
            ADMIN,
            "cannot-pass-own-sentence",
            work,
            state(game).revision,
            "sentence",
            ideals="No",
            account="No",
        )
    ideals, sentence = "PRIVATE_FOUNDATION_IDEALS", "The original court imposes the sentence."
    revision = state(game).revision
    asyncio.run(native(authority, 43710, choice=("sentence",), ideals=ideals, account=sentence))
    assert (
        service.respond(
            authority, "43711", work, revision, "sentence", ideals=ideals, account=sentence
        )["decision"]
        == "sentence"
    )
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    ledger.engine.dispose()
    assert (
        active_handler(state(game)) is None and state(game).handler_archives[-1].actor == original
    )
    with pytest.raises(WorkflowError, match="exact approved successor"):
        strain.periods.begin(ADMIN, "blocked-before-successor")
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == "pending"

    creation = HandlerCreationService(ledger)
    draft = complete(creation, "Advocate").model_copy(update=dict(background="PRIVATE_DOSSIER"))
    preview = creation.view(ADMIN)
    creation.save(
        ADMIN,
        "new-foundation-draft",
        preview["revision"],
        preview["appointment"],
        draft,
        generation=preview["generation"],
    )
    agree(creation, generation=preview["generation"])
    preview = creation.view(ADMIN)
    with pytest.raises(WorkflowError, match="exact successor draft"):
        creation.activate(
            ADMIN, "no-court-approval", preview["revision"], state(game).revision, True
        )
    asyncio.run(native(ADMIN, 43720, choice=("pledge",), account="I agree to the new terms."))
    assert "PRIVATE_DOSSIER" not in str(service.get(authority, work))
    asyncio.run(native(authority, 43730, choice=("refuse",)))
    asyncio.run(
        native(
            ADMIN,
            43740,
            choice=("pledge",),
            account="I undertake the authority's exact published terms.",
        )
    )
    asyncio.run(native(authority, 43750, choice=("approve",)))
    preview = creation.view(ADMIN)
    creation.save(
        ADMIN,
        "changed-after-approval",
        preview["revision"],
        preview["appointment"],
        draft.model_copy(update={"background": "Changed private dossier"}),
        generation=preview["generation"],
    )
    preview = creation.view(ADMIN)
    assert not service.get(ADMIN, work)["approved"]
    with pytest.raises(WorkflowError, match="exact successor draft"):
        creation.activate(ADMIN, "old-approval", preview["revision"], state(game).revision, True)
    asyncio.run(native(ADMIN, 43760, choice=("pledge",), account="I attest to the amended draft."))
    asyncio.run(native(authority, 43770, choice=("approve",)))
    preview = creation.view(ADMIN)
    creation.activate(
        ADMIN, "activate-approved-successor", preview["revision"], state(game).revision, True
    )
    after = state(game)
    (complete_case,) = successions(after)
    assert complete_case.replacement == active_handler(after) and active_handler(after) != original
    assert complete_case.completed == after.handler_persona.source_event
    assert after.handler_fatal_sources[-1].source_work == work
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == "resolved"
    assert strain.periods.begin(ADMIN, "authorized-after-court")["phase"] == "preparing"
