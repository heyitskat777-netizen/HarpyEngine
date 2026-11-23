"""The Endgame binds the original living Handler to their new owned Girl."""

import asyncio

import pytest
from test_budget_persistent_tag import source
from test_creation import selected
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.bonds import BondProposal
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_budget_demotion import RULE, demotions
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_state import Draft, GearDetail, StartingBond
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_demotion import DemotionService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_budget_demotion_activates_original_girl_and_distinct_owned_successor(ledger):
    _, game, strain, work, period = source(ledger, option=2, without_void=True)
    approval, policy = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "playbooks"})
            ),
            owner_m3_rulings=policy.model_copy(
                update=dict(handler_creation="owned_shared_choices_preserve_existing")
            ),
        )
    )
    successor = GuildViewer(4, 200, True, False)
    ledger.join(successor, "willing-successor")
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN,
        "demotion-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    assert state(game).strain.endgames[-1].rule_id == RULE
    effects = EffectService(strain)
    for index, request in enumerate(tuple(state(game).strain.requests)):
        if request.track == "void":
            face, column, choice = (
                2,
                1,
                Choice(
                    rule_id="strain.void.low.2.1",
                    account="Unrelated arrival.",
                    gorgon=gorgon("dormant", "demotion-other-void-" + str(index), (0, 1)),
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
        strain.roll(ADMIN, f"demotion-other-roll-{index}", request.id, 1, state(game).revision)
        strain.choose(
            ADMIN, f"demotion-other-column-{index}", request.id, 2, state(game).revision, column
        )
        effects.apply(
            ADMIN,
            f"demotion-other-effect-{index}",
            request.id + ":effect",
            1,
            state(game).revision,
            choice,
        )
    inbox = InboxService(ledger)

    async def native(viewer, number, **values):
        click = current(viewer.user_id, number)
        click.user.guild_permissions.administrator = viewer.is_administrator
        await click.response.defer(ephemeral=True)
        cards = [
            x for x in inbox.items(viewer) if x.identity == work and x.task == "m3_budget_demotion"
        ]
        assert len(cards) == 1
        await InboxView(inbox, viewer.user_id).route(click, cards[0])
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm), click.edit_original_response.call_args
        form.values.update(values)
        submitted = current(viewer.user_id, number + 1)
        submitted.user.guild_permissions.administrator = viewer.is_administrator
        await form.confirm.callback(submitted)
        assert form.completed, (
            submitted.edit_original_response.call_args,
            submitted.followup.send.call_args,
        )

    service = DemotionService(strain)
    old_handler = active_handler(state(game))
    asyncio.run(native(ADMIN, 42500, nominee=("3",), account="First offer"))
    asyncio.run(native(OTHER, 42510, choice=("decline",)))
    cycle = CycleService(strain.periods)
    with pytest.raises(WorkflowError, match="actual Strain|work"):
        activate(cycle, game, period)
    asyncio.run(native(ADMIN, 42520, nominee=("4",), account="PRIVATE_SUCCESSOR_OFFER"))
    with pytest.raises(WorkflowError, match="authorized participants"):
        service.get(OTHER, work)
    with pytest.raises(WorkflowError, match="original invited successor"):
        service.respond(ADMIN, "accept-for-successor", work, state(game).revision, "accept")
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.respond(successor, "stale-succession", work, revision - 1, "accept")
    ledger.safety(PLAYER, "pause-succession", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(successor, "paused-succession", work, revision, "accept")
    ledger.safety(PLAYER, "resume-succession", ledger.status(PLAYER)["revision"], pause=False)
    asyncio.run(native(successor, 42530, choice=("accept",)))
    assert service.respond(successor, "42531", work, revision, "accept")["decision"] == "accept"
    assert active_handler(state(game)) == old_handler
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    assert call(cycle, game, ADMIN, period, "finish", movement(game))["phase"] == "complete"
    ledger.engine.dispose()
    assert active_handler(state(game)) is None
    archive = state(game).handler_archives[-1]
    assert archive.actor == old_handler and archive.alive and archive.ending == "demoted"
    with pytest.raises(WorkflowError, match="original Girl and consenting successor"):
        strain.periods.begin(ADMIN, "before-both-roles")
    with pytest.raises(WorkflowError, match="original Girl's activation"):
        service.respond(ADMIN, "premature-install", work, state(game).revision, "appoint")

    ledger.save_draft(
        ADMIN,
        "prepare-demoted-girl",
        0,
        DraftInput(callsign="ORIGINAL", girl_playbook="MOCKINGBIRD", frame_playbook="JANUS"),
    )
    creation = CreationService(ledger)
    choices = creation.get(ADMIN)
    creation.save(
        ADMIN,
        "owned-girl-draft",
        choices.revision,
        choices.character_revision,
        selected().model_copy(update={"shared_tokens": choices.draft.shared_tokens}),
    )
    bond = BondService(ledger)
    proposal = bond.propose(
        ADMIN,
        "original-girl-bond",
        1,
        2,
        BondProposal(
            target_id=2, prompt=0, context="We met while the original Handler was still in office."
        ),
    )
    bond.decide(PLAYER, "girl-bond-accepted", proposal["id"], 1, "accept")
    setup = HandlerService(ledger)
    roster = setup.roster(ADMIN)
    order = tuple(
        PilotRef(user_id=uid, character_revision=roster["pilots"][uid]["revision"])
        for uid in (*state(game).order, 1)
    )
    setup.rank(ADMIN, "actual-demoted-girl-status", roster["revision"], order)
    review = CreationReviewService(ledger)
    sheet = review.get(ADMIN)
    assert sheet.sheet.ready_for_rules_review, sheet.sheet.issues
    review.save(ADMIN, "original-girl-review", sheet.saved_revision, sheet.fingerprint)
    game.activate(ADMIN, "own-girl-activation", review.get(ADMIN).fingerprint)
    assert state(game).sheets["1"].callsign == "ORIGINAL"
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == "pending"
    asyncio.run(native(ADMIN, 42540, choice=("appoint",)))
    assert state(game).handler == 4 and active_handler(state(game)) is None
    assert state(game).sheets["1"].character_id == demotions(state(game))[0].girl.incarnation
    creation = HandlerCreationService(ledger)
    preview = creation.view(successor)
    draft = Draft(
        playbook="Scientist",
        name="New verified Handler",
        appearance="Coat",
        outfit="Uniform",
        background="Clinic",
        gear=(
            GearDetail(kind="weapon", description="Catalogued"),
            GearDetail(kind="studio", description="Open"),
        ),
        starting=(
            StartingBond(
                pilot=current_ref(state(game), 2),
                rank="ace",
                history="The new Handler asks for a shared history.",
            ),
        ),
    )
    saved = creation.save(
        successor,
        "new-handler-draft",
        preview["revision"],
        preview["appointment"],
        draft,
        generation=preview["generation"],
    )
    (request,) = creation.propose(
        successor, "new-owner-proposals", saved["revision"], generation=preview["generation"]
    )["ids"]
    agreement = creation.get_agreement(PLAYER, request)
    creation.answer(PLAYER, "new-handler-own-agreement", request, agreement["revision"], True)
    preview = creation.view(successor)
    creation.activate(
        successor, "activate-distinct-successor", preview["revision"], state(game).revision, True
    )
    asyncio.run(native(successor, 42550, choice=("complete",)))
    with ledger.engine.connect() as c:
        assert strain._row(c, work)["state"] == "resolved"
    canon = state(game)
    assert active_handler(canon) == demotions(canon)[0].replacement
    assert active_handler(canon).entity == "4" and canon.handler_archives[-1] == archive
    assert strain.periods.begin(successor, "authorized-next-off-duty")["phase"] == "preparing"
