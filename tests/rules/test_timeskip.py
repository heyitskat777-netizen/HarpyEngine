"""The original table's Timeskip and its first four actual canonical steps."""

import asyncio

import pytest
from test_creation import selected
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service as mission_service
from test_world import initial as initial_world

from girlframe.discord_adapter.m3_careers import open_replacement
from girlframe.discord_adapter.m3_girl_transition import open_configuration
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_timeskip import open_timeskip
from girlframe.discord_adapter.m3_world import open_world
from girlframe.engine.bonds import BondProposal
from girlframe.engine.cadre_history import PriorMission
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.engine.shared_setup import CallsignChoice
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.m3_careers import CareerService
from girlframe.services.m3_girl_transition import GirlTransitionService, baseline_id
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_timeskip import RULE, Arrival, TimeskipService, records
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.shared_setup import SharedSetupService


def test_native_timeskip_agreement_and_ordered_world_changes(ledger):
    missions, game = mission_service(ledger, girl="NEWGIRL")
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(subsystems=policy.subsystems | {"world", "strain", "playbooks"})
            )
        )
    )
    world = WorldService(missions)
    quads = initial_world()
    world.initialize(
        ADMIN,
        "world-initialize",
        state(game).revision,
        quads.board,
        quads.locations,
        quads.gorgons[0],
    )
    world.faction(
        ADMIN,
        "original-rebels",
        state(game).revision,
        Faction(id="old-rebels", kind="rebel", name="Old Rebels", cells=((6, 6),)),
    )
    world.npc(
        ADMIN,
        "inside-base",
        state(game).revision,
        Npc(
            id="inside",
            name="Inside",
            jobs=("base_personnel",),
            detail="An actual occupant of the original base.",
            controller=ADMIN.user_id,
            cell=(2, 0),
        ),
    )
    world.npc(
        ADMIN,
        "outside-base",
        state(game).revision,
        Npc(
            id="outside",
            name="Outside",
            jobs=("civilian",),
            detail="Shares the map square, physically outside the base.",
            controller=ADMIN.user_id,
            cell=(2, 0),
        ),
    )
    service = TimeskipService(game)
    with pytest.raises(WorkflowError):
        service.start_menu(ADMIN)
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=policy.model_copy(
                update=dict(
                    subsystems=policy.subsystems | {"plays"},
                    activity_specialist_rules=policy.activity_specialist_rules | {RULE},
                )
            )
        )
    )

    async def launch(current):
        await open_world(current, world)
        picker = current.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker) and "timeskip" in dict(picker.options)
        await picker.open_item(current, "timeskip")

    asyncio.run(submit_form(ADMIN, launch, dict(duration=("12",)), 93300))
    (case,) = records(state(game))
    assert case.months == 12 and case.step == "agreement"
    assert any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))
    initial = state(game).revision
    key = asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_timeskip(click, service, case.id),
            dict(vote=("accept",)),
            93304,
            wrong_owner=True,
        )
    )
    assert service.vote(PLAYER, key, case.id, initial, True)["step"] == "agreement"
    with pytest.raises(WorkflowError, match="STALE_TIMESKIP"):
        service.vote(OTHER, "stale-duration", case.id, initial, True)
    asyncio.run(
        submit_form(
            OTHER,
            lambda click: open_timeskip(click, service, case.id),
            dict(vote=("accept",)),
            93308,
        )
    )
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(PLAYER, case.id)
    assert not any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))

    async def ruin(current, site):
        await open_timeskip(current, service, case.id)
        picker = current.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker) and site in dict(picker.options)
        await picker.open_item(current, site)

    arrival = dict(
        kind=("dormant",),
        type=("jackdaw",),
        name="Private ruins Gorgon",
        assets="Horns\nMirrors\nTail",
        weakness="The horns protect its Core.",
        account="The original site was destroyed during the agreed interval.",
    )
    asyncio.run(submit_form(ADMIN, lambda click: ruin(click, "city0"), arrival, 93312))
    assert records(state(game))[0].step == "city_foundation"
    ledger.engine.dispose()
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_timeskip(click, service, case.id),
            dict(name="New City", cell="1,3", account="A new city established by the table."),
            93316,
        )
    )
    with pytest.raises(WorkflowError, match="STALE_TIMESKIP"):
        service.ruin(
            ADMIN,
            "stale-ruin",
            case.id,
            initial,
            "base1",
            Arrival(
                kind="benevolent", type="incubus", name="Late", assets=("a", "b"), weakness="C"
            ),
            (),
            "Old form",
        )
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: ruin(click, "base1"),
            arrival | dict(name="Private base Gorgon", occupants=("inside",)),
            93320,
        )
    )
    final = state(game)
    (settled,) = records(final)
    assert (
        settled.step == "newgirl" and settled.city_ruin == "city0" and settled.base_ruin == "base1"
    )
    assert final.world is not None
    locations = {x.id: x for x in final.world.locations}
    assert locations["city0"].condition == locations["base1"].condition == "destroyed"
    assert locations[settled.city].name == "New City"
    newcomers = {x.name: x for x in final.world.gorgons if x.id != "secret"}
    assert newcomers["Private ruins Gorgon"].cell == locations["city0"].cell
    assert newcomers["Private base Gorgon"].cell == locations["base1"].cell
    assert {x.id: x.alive for x in final.world.npcs} == {"inside": False, "outside": True}
    StrainService(OffDutyService(world.missions)).configure(
        ADMIN, "timeskip-initialize-strain", final.revision, "business_as_usual", frozenset()
    )
    final = state(game)
    assert final.strain is not None
    assert {x.entity for x in final.strain.triggers if x.kind == "structure_destroyed"} == {
        "city0",
        "base1",
    }
    assert "Private base Gorgon" not in str(world.get(PLAYER))

    original_girl = final.sheets["2"]
    assert original_girl.girl == "NEWGIRL"
    assert not service.get(ADMIN, case.id)["can_continue"]
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, case.id)
    assert any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_timeskip(click, service, case.id),
            dict(book=("OLDGEN",)),
            93324,
        )
    )
    adopted = state(game)
    ref = settled.graduates[0]
    assert adopted.sheets["2"].girl == "OLDGEN"
    assert adopted.sheets["2"].assets == original_girl.assets
    assert adopted.sheets["2"].character_id == original_girl.character_id
    assert not service.get(ADMIN, case.id)["can_continue"]
    (adopted_timeskip,) = records(adopted)
    source = baseline_id(case.id, adopted_timeskip.baselines[ref.token])
    transitions = GirlTransitionService(ledger)
    own_baseline = transitions.get(PLAYER, source)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_configuration(click, transitions, own_baseline),
            dict(account="The original Newgirl grew into an Oldgen.", maxims=("1", "4")),
            93328,
        )
    )
    current = transitions.get(PLAYER, source)
    transitions.finalize(
        PLAYER, "graduate-confirm", source, current["revision"], current["game_revision"]
    )
    assert service.get(ADMIN, case.id)["can_continue"]
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_timeskip(click, service, case.id),
            dict(confirm=("continue",)),
            93332,
        )
    )
    finished = state(game)
    assert records(finished)[0].step == "death"
    assert finished.sheets["2"].girl_runtime.setup.maxims == (1, 4)

    def native(actor, values, sequence):
        asyncio.run(
            submit_form(
                actor, lambda click: open_timeskip(click, service, case.id), values, sequence
            )
        )

    native(ADMIN, dict(choice=(ref.token,)), 93336)
    for viewer, sequence in ((ADMIN, 93340), (OTHER, 93344), (PLAYER, 93348)):
        assert "2" in state(game).sheets
        native(viewer, dict(choice=("yes",)), sequence)
    death = state(game)
    (lost,) = records(death)
    assert lost.step == "replacement"
    assert lost.death == ref and "2" not in death.sheets
    assert any(x.actor == ref and x.ending == "death" for x in death.career_archives)
    assert not service.get(ADMIN, case.id)["can_continue"]
    careers = CareerService(ledger)
    with pytest.raises(WorkflowError, match="must be a Newgirl"):
        careers.begin_replacement(
            PLAYER,
            "wrong-book",
            lost.death_archive,
            death.revision,
            DraftInput(callsign="Replacement", girl_playbook="OLDGEN", frame_playbook="JANUS"),
        )
    with pytest.raises(WorkflowError, match="original human"):
        careers.get(OTHER, lost.death_archive)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_replacement(click, careers, lost.death_archive),
            dict(callsign="Replacement", girl=("NEWGIRL",), frame=("JANUS",)),
            93352,
        )
    )
    pending = state(game)
    assert not service.get(ADMIN, case.id)["can_continue"]
    correction = HandlerService(ledger)
    fresh_revision, mentor_revision = (
        ledger.draft(viewer)["revision"] for viewer in (PLAYER, OTHER)
    )
    new_ref = PilotRef(user_id=PLAYER.user_id, character_revision=fresh_revision)
    mentor_ref = PilotRef(user_id=OTHER.user_id, character_revision=mentor_revision)
    correction.mentor(
        ADMIN, "new-mentor", correction.roster(ADMIN)["revision"], new_ref, mentor_ref
    )
    contacts = BondService(ledger)
    request = contacts.propose(
        PLAYER,
        "new-bond",
        fresh_revision,
        mentor_revision,
        BondProposal(target_id=OTHER.user_id, prompt=0, context="The new Girl knows her Mentor."),
    )
    contacts.decide(OTHER, "accept-new-bond", request["id"], 1, "accept")
    shared = SharedSetupService(ledger)
    name = shared.propose(
        OTHER,
        "new-name",
        PLAYER.user_id,
        "callsign",
        shared.prepare(OTHER, PLAYER.user_id, "callsign"),
        CallsignChoice(callsign="REPLACEMENT"),
    )
    shared.decide(PLAYER, "accept-new-name", name["id"], 1, "accept")
    creation = CreationService(ledger)
    draft = creation.get(PLAYER)
    chosen = selected("NEWGIRL", "JANUS").model_copy(
        update=dict(
            shared_tokens=draft.draft.shared_tokens,
            cadre_discussed=True,
            prior_missions=tuple(
                PriorMission(user_id=uid, character_revision=entry["revision"], missions=0)
                for uid, entry in creation.cadre(PLAYER).items()
            ),
        )
    )
    creation.save(PLAYER, "save-new-girl", draft.revision, fresh_revision, chosen)
    correction.rank(ADMIN, "new-rank", correction.roster(ADMIN)["revision"], (mentor_ref, new_ref))
    careers.assign_status(
        ADMIN,
        "newgirl-status",
        PLAYER.user_id,
        pending.incarnation_bindings[-1].character,
        state(game).revision,
        1,
    )
    review = CreationReviewService(ledger)
    ready = review.get(PLAYER)
    assert ready.sheet.ready_for_rules_review, ready.sheet.issues
    review.save(PLAYER, "save-new-review", ready.saved_revision, ready.fingerprint)
    game.activate(PLAYER, "activate-timeskip-newgirl", review.get(PLAYER).fingerprint)
    assert service.get(ADMIN, case.id)["can_continue"]
    native(ADMIN, dict(confirm=("continue",)), 93356)
    replaced = state(game)
    assert records(replaced)[0].step == "base_foundation"
    assert replaced.sheets["2"].character_id != ref.incarnation
    assert replaced.order == (3, 2)
    assert replaced.sheets["2"].girl == "NEWGIRL" and replaced.sheets["2"].mentor == OTHER.user_id

    native(ADMIN, dict(name="New Base", cell="3,3", account="A new Foundation base."), 93360)
    (base_case,) = records(state(game))
    assert base_case.step == "base_contacts"
    for viewer, sequence in ((PLAYER, 93364), (OTHER, 93368), (ADMIN, 93372)):
        native(
            viewer,
            dict(
                name="Contact " + str(viewer.user_id),
                job=("mechanic",),
                detail="Repairs and maintains equipment in the base.",
                acquaintance="The original player records how they know this contact.",
            ),
            sequence,
        )
    final = state(game)
    (populated,) = records(final)
    assert populated.step == "rebel_succession"
    assert set(populated.base_contacts) == {"1", "2", "3"}
    assert final.world is not None
    base = next(x for x in final.world.locations if x.id == populated.new_base)
    assert base.name == "New Base" and base.kind == "base" and base.foundation_operational
    contacts = tuple(x for x in final.world.npcs if x.id in populated.base_contacts.values())
    assert len(contacts) == 3
    assert all(x.cell == base.cell and x.controller == ADMIN.user_id and x.alive for x in contacts)
    assert not any(x.task == "m3_timeskip" for x in InboxService(ledger).items(PLAYER))

    native(
        ADMIN,
        dict(
            fallen=("old-rebels",),
            name="New Rebels",
            cell="6,6",
            handler="Their actual Handler",
            girl="Their actual Girl",
            frame=("JANUS",),
            body_asset="Marked Scout Uniform",
            frame_asset="Signal Intercept Array",
            account="The original group dissolved, and a separate group rose in the refuge.",
        ),
        93376,
    )
    after = state(game)
    (new_groups,) = records(after)
    assert new_groups.step == "identities"
    assert {x.entity for x in new_groups.rewrite_targets} == {"2", "3"}
    assert after.world is not None
    groups = {x.id: x for x in after.world.factions}
    assert not groups["old-rebels"].active and groups[new_groups.new_group].active
    handler = next(x for x in after.world.npcs if x.id == new_groups.new_rebel_handler)
    rebel = next(x for x in after.world.pilots if x.id == new_groups.new_rebel_girl)
    assert groups[rebel.faction].leader == handler.id
    assert handler.jobs == ("handler",) and handler.faction == rebel.faction
    assert rebel.kind == "rebel" and rebel.frame == "JANUS"
    assert {x.family for x in rebel.assets} == {"girl", "frame"}
    assert "Their actual Handler" not in str(world.get(PLAYER))

    with ledger.transaction() as c:
        original = state(game)
        player, other = (current_ref(original, actor.user_id) for actor in (PLAYER, OTHER))
        tagged = give_tag(original, player, other, "Cautious", "actual-tag", "old-tag", (2, 3))
        game.event(
            c, OTHER.user_id, "timeskip-source-tag", "synthetic.tag", tagged, event_id="actual-tag"
        )
    assert {x.entity for x in records(state(game))[0].rewrite_targets} == {"2", "3"}
    choices = service.get(PLAYER, case.id)
    assert choices["tags"] == {"old-tag": "Cautious"}
    assert "Cautious" not in str(service.get(OTHER, case.id))
    earlier = state(game)
    for viewer, seq in ((PLAYER, 93380), (OTHER, 93384)):
        prior = earlier.sheets[str(viewer.user_id)]
        first, second = prior.identities[:2]
        own_tag = viewer == PLAYER
        native(
            viewer,
            dict(
                identity1=(first.id,),
                source1=(("0" if own_tag else "alternative"),),
                alternative1="" if own_tag else "Still serving",
                identity2=(second.id,),
                source2=("alternative",),
                alternative2="Learned patience",
            ),
            seq,
        )
        after = state(game).sheets[str(viewer.user_id)]
        assert after.identities[0].id != first.id and after.identities[1].id != second.id
        assert after.identities[2:] == prior.identities[2:]
        assert after.identities[0].slot == first.slot and after.identities[1].slot == second.slot
        assert after.identities[0].name == ("Cautious" if own_tag else "Still serving")
        assert after.identities[1].name == "Learned patience"
        if own_tag:
            assert not any(x.id == "old-tag" for x in after.tags)
    (rewritten,) = records(state(game))
    assert rewritten.step == "benefits" and len(rewritten.rewrites) == 2
