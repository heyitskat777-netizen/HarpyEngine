"""Actual low Defeat → new Girl baseline → original human-owned setup."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_defeat_service import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current
from test_standards import compile_three

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_girl_transition import open_transition
from girlframe.engine.creation_details import DesireChoice, StandardChoice
from girlframe.engine.m2 import IdentityState, TagState, higher, mark_identity
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import PlaySwap, relation_current
from girlframe.engine.m3_girl_transition_state import Investor, Plan
from girlframe.engine.m3_world_state import Board, Npc, StartingNpcLink, World
from girlframe.services.m3_girl_transition import GirlTransitionService
from girlframe.services.m3_standards import StandardsService
from girlframe.services.onboarding import WorkflowError


def changed(store, book="STIM-BLISSED", extra=()):
    game, worker, gateway, _, identity = rolled(store, faces=(1, 1))
    before = state(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("change_girl_playbook",) + extra,
        fields={"girl_playbook": book},
        text="Actual Defeat changes this same Girl's book",
    )
    tick(worker, gateway, 6)
    service = GirlTransitionService(store)
    tasks = service.tasks(PLAYER)
    return service, game, tasks[0]["id"] if tasks else None, before


def configure(service, identity, plan):
    data = service.get(PLAYER, identity)
    return service.configure(
        PLAYER, "configure-actual-transition", identity, data["revision"], plan
    )


def finish(service, identity, key="finish-actual-transition"):
    data = service.get(PLAYER, identity)
    return service.finalize(PLAYER, key, identity, data["revision"], data["game_revision"])


@pytest.mark.parametrize("book", ["STIM-BLISSED", "CASUALTY", "ALPHA", "AM"])
def test_actual_change_keeps_resources_and_finishes_rule_configuration_without_free_starting_grants(
    ledger, book
):
    service, game, identity, before = changed(ledger, book)
    assert identity
    actual = state(game).sheets["2"]
    assert actual.girl == book and actual.character_id == before.sheets["2"].character_id
    assert actual.assets == before.sheets["2"].assets
    assert actual.identities == before.sheets["2"].identities
    assert (
        actual.heat == before.sheets["2"].heat
        and actual.permissions == before.sheets["2"].permissions
    )
    with ledger.engine.connect() as c:
        assert game.immediate_work(c, 2)
    configure(service, identity, Plan(account="Actual new native rule baseline"))
    result = finish(service, identity)
    assert result["complete"]
    after = state(game).sheets["2"]
    assert (
        after.assets == before.sheets["2"].assets
        and after.identities == before.sheets["2"].identities
    )
    if book == "CASUALTY":
        assert len(after.girl_runtime.setup.body_parts) == 9
    with ledger.engine.connect() as c:
        profile = c.scalar(
            sa.select(t.characters.c.public_json).where(
                t.characters.c.campaign_id == ledger.campaign_id, t.characters.c.user_id == "2"
            )
        )
    assert json.loads(profile)["girl_playbook"] == book
    with ledger.engine.connect() as c:
        assert not game.immediate_work(c, 2)


def test_oldgen_owned_maxims_preserve_marks_and_protected_resources(ledger):
    service, game, identity, before = changed(ledger, "OLDGEN")
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].identities.append(
            IdentityState(id="protected-extra", name="Protected", protected=True, marked=True)
        )
        canon.sheets["2"].tags.append(TagState(id="kept-tag", label="Keep", giver=3, marked=True))
        canon.sheets["2"].maxims_marked = (4,)
        game.event(c, 1, "actual-retained-extra", "synthetic.state", canon)
    with pytest.raises(WorkflowError):
        configure(service, identity, Plan(account="New maxims", maxims=(1,)))
    configure(service, identity, Plan(account="New maxims", maxims=(1, 4)))
    finish(service, identity)
    after = state(game).sheets["2"]
    assert after.girl_runtime.setup.maxims == (1, 4) and after.maxims_marked == (4,)
    assert next(x for x in after.identities if x.id == "protected-extra").marked
    assert after.tags[-1].marked and after.assets == before.sheets["2"].assets


def test_newgirl_handler_assignment_mentor_call_and_original_owner_finalize(ledger):
    service, game, identity, before = changed(ledger, "NEWGIRL")
    configure(service, identity, Plan(account="Actual newly assigned trainee"))
    data = service.get(ADMIN, identity)
    peer = next(x["ref"] for x in data["people"] if x["ref"]["entity"] == "3")
    with pytest.raises(WorkflowError):
        service.assign(
            PLAYER,
            "not-assignment-owner",
            identity,
            data["revision"],
            ActorRef.model_validate_json(json.dumps(peer)),
        )
    service.assign(
        ADMIN,
        "actual-assigned-mentor",
        identity,
        data["revision"],
        ActorRef.model_validate_json(json.dumps(peer)),
    )
    data = service.get(OTHER, identity)
    assert data["can_respond"] and "plan" not in data
    service.respond(
        OTHER, "mentor-owned-new-callsign", identity, data["revision"], callsign="SORROW"
    )
    assert state(game).sheets["2"].mentor is None
    finish(service, identity)
    canon = state(game)
    assert canon.sheets["2"].mentor == 3 and canon.sheets["2"].callsign == "SORROW"
    assert depth(canon, current_ref(canon, 2), current_ref(canon, 3)) >= 1
    assert higher(canon, 3, 2) and not higher(canon, 2, 3)
    canon.sheets["3"].character_id = "replacement-of-the-original-mentor"
    canon.order = (2, 3)
    assert not relation_current(canon.sheets["2"], "mentor", canon)
    assert higher(canon, 2, 3)


def test_bonded_actual_pair_owns_acceptance_owner_owns_protected_identity(ledger):
    service, game, identity, before = changed(ledger, "BONDED")
    canon = state(game)
    peer = current_ref(canon, 3)
    configure(
        service,
        identity,
        Plan(
            account="Actual new Pair", pair=peer, paired_identity=canon.sheets["2"].identities[0].id
        ),
    )
    data = service.get(OTHER, identity)
    with pytest.raises(WorkflowError):
        service.respond(ADMIN, "not-the-pair", identity, data["revision"], accepted=True)
    service.respond(OTHER, "actual-pair-response", identity, data["revision"], accepted=True)
    finish(service, identity)
    canon = state(game)
    sheet = canon.sheets["2"]
    assert sheet.pair == 3 and sheet.assets == before.sheets["2"].assets
    paired = next(x for x in sheet.identities if x.paired)
    assert paired.name == "Hers" and paired.protected
    assert depth(canon, current_ref(canon, 2), peer) == 2
    assert mark_identity(sheet, paired.id, 5, 2, state=canon) == 2
    paired.marked = False
    canon.sheets["3"].character_id = "different-person"
    with pytest.raises(ValueError, match="original Pair"):
        mark_identity(sheet, paired.id, 5, 2, state=canon)
    assert not paired.marked


def test_princess_requires_actual_three_standards_without_starting_ace_reset(ledger):
    service, game, identity, before = changed(ledger, "PRINCESS")
    configure(service, identity, Plan(account="Actual Princess baseline"))
    assert service.get(PLAYER, identity)["needs_standards"]
    with pytest.raises(WorkflowError):
        finish(service, identity)
    standards = StandardsService(ledger)
    data = standards.preview(PLAYER)
    peer = ActorRef.model_validate_json(json.dumps(data["peers"][0]["ref"]))
    sid = standards.start(
        PLAYER, "actual-new-princess-self", data["game_revision"], peer, StandardChoice(slot=0)
    )["id"]
    compile_three(standards, sid)
    finish(service, identity)
    assert state(game).order == before.order
    assert len(state(game).sheets["2"].girl_runtime.standards) == 3


def test_native_newgirl_controls_save_reopen_assign_and_finalize(ledger):
    service, game, identity, before = changed(ledger, "NEWGIRL")

    async def run():
        owner = current(2, 29501)
        await owner.response.defer(ephemeral=True)
        await open_transition(owner, service, identity)
        view = owner.edit_original_response.call_args.kwargs["view"]
        assert not await view.interaction_check(current(3))
        await view.configure_button.callback(current(2, 29502))
        form = owner.edit_original_response.call_args.kwargs.get("view")
        # The callback's own interaction receives its private form.
        actual = current(2, 29503)
        await actual.response.defer(ephemeral=True)
        from girlframe.discord_adapter.m3_girl_transition import open_configuration

        await open_configuration(actual, service, service.get(PLAYER, identity))
        form = actual.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual Newgirl details")
        await form.confirm.callback(current(2, 29504))
        assert form.completed
        handler = current(1, 29505)
        await handler.response.defer(ephemeral=True)
        await open_transition(handler, service, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        options = form.fields[0].options
        form.values.update(mentor=(options[0][0],))
        await form.confirm.callback(current(1, 29506))
        assert form.completed
        mentor = current(3, 29507)
        await mentor.response.defer(ephemeral=True)
        await open_transition(mentor, service, identity)
        form = mentor.edit_original_response.call_args.kwargs["view"]
        form.values.update(callsign="SORROW")
        await form.confirm.callback(current(3, 29508))
        assert form.completed

    asyncio.run(run())
    finish(service, identity)
    assert state(game).sheets["2"].callsign == "SORROW"


def test_vatgrown_retained_actual_npc_investors_and_handler_own_desires(ledger):
    service, game, identity, before = changed(ledger, "VATGROWN")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(0, 0), maximum=(2, 2)),
            locations=(),
            npcs=(
                Npc(
                    id="actual-investor",
                    name="Existing investor",
                    cell=(1, 1),
                    jobs=("scientist",),
                    detail="Actual retained starting NPC",
                    controller=1,
                    bonds={"pilot:2": 1},
                ),
            ),
            starting_npc_links=(
                StartingNpcLink(
                    owner=2,
                    character_id=canon.sheets["2"].character_id,
                    slot=0,
                    npc="actual-investor",
                ),
            ),
        )
        game.event(c, 1, "actual-retained-npc-context", "synthetic.state", canon)
    plan = Plan(
        account="Actual experiment baseline",
        dna_basis="Actual established DNA basis",
        investors=(Investor(npc="actual-investor", desires=DesireChoice(slots=(0, 2))),),
    )
    configure(service, identity, plan)
    data = service.get(ADMIN, identity)
    assert data["can_respond"] and "plan" not in data
    service.respond(
        ADMIN,
        "handler-original-investment-desires",
        identity,
        data["revision"],
        desires=DesireChoice(slots=(1, 3)),
    )
    finish(service, identity)
    setup = state(game).sheets["2"].girl_runtime.setup
    assert setup.investors == plan.investors and setup.handler_desires.slots == (1, 3)
    assert setup.dna_basis == plan.dna_basis
    assert len(state(game).world.npcs) == 1
    assert state(game).sheets["2"].assets == before.sheets["2"].assets


def test_transition_pause_and_exact_once_finalization_rollback_do_not_reset_resources(
    ledger, monkeypatch
):
    service, game, identity, before = changed(ledger, "OLDGEN")
    ledger.safety(OTHER, "pause-transition", ledger.status(OTHER)["revision"], pause=True)
    configure(service, identity, Plan(account="Actual setup during pause", maxims=(1, 2)))
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        finish(service, identity)
    ledger.safety(OTHER, "resume-transition", ledger.status(OTHER)["revision"], pause=False)
    prior = state(game)
    save = service._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic failure after source state and profile writes")

    monkeypatch.setattr(service, "_save", fail)
    with pytest.raises(RuntimeError):
        finish(service, identity, "failed-transition-write")
    assert state(game) == prior
    monkeypatch.setattr(service, "_save", save)
    data = service.get(PLAYER, identity)

    def submit(key):
        try:
            return service.finalize(PLAYER, key, identity, data["revision"], data["game_revision"])
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("finish-transition-a", "finish-transition-b")))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert state(game).sheets["2"].assets == before.sheets["2"].assets
    assert not service.tasks(PLAYER)


def test_same_account_new_cid_and_forged_appended_pair_response_cannot_supply_consent(ledger):
    service, game, identity, _ = changed(ledger, "BONDED")
    canon = state(game)
    configure(
        service,
        identity,
        Plan(
            account="Actual Pair source",
            pair=current_ref(canon, 3),
            paired_identity=canon.sheets["2"].identities[0].id,
        ),
    )
    data = service.get(OTHER, identity)
    service.respond(OTHER, "actual-declined-pair", identity, data["revision"], accepted=False)
    assert not service.get(PLAYER, identity)["can_finalize"]
    with ledger.transaction() as c:
        row, body, _ = service._source(c, identity)
        body["entries"]["pair"]["data"]["accepted"] = True
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json")},
                revision=row["revision"] + 1,
                body_json=json.dumps(body),
            )
        )
    with pytest.raises(WorkflowError, match="SOURCE_GIRL_TRANSITION_MISSING"):
        service.get(PLAYER, identity)
    assert state(game).sheets["2"].pair is None


def test_new_baseline_keeps_explicit_acquisitions_and_protected_extras_on_later_change(ledger):
    from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime, has_rule

    service, game, identity, _ = changed(ledger, "AM")
    configure(service, identity, Plan(account="Actual AM without a limiter reset"))
    finish(service, identity)
    sheet = state(game).sheets["2"]
    sheet.identities.append(
        IdentityState(id="locked-existing", name="Actual protected extra", protected=True)
    )
    runtime = sheet.girl_runtime
    sheet.girl_runtime = runtime.model_copy(
        update={
            "swaps": (
                PlaySwap(
                    removed_rule="girl.am.just-code",
                    acquired_rule="girl.princess.objectively-beautiful",
                    source_playbook="PRINCESS",
                    source_event="actual-acquisition-source",
                ),
            )
        }
    )
    changed_sheet, fact = change_playbook_runtime(sheet, "MOCKINGBIRD", "actual-new-epoch")
    assert changed_sheet.identities == sheet.identities
    assert changed_sheet.assets == sheet.assets
    assert has_rule(changed_sheet, "girl.princess.objectively-beautiful", "PRINCESS")
    assert changed_sheet.girl_runtime.setup == sheet.girl_runtime.setup
    assert changed_sheet.girl_runtime.baseline_event == "actual-new-epoch"
    assert fact["prior_runtime"] == sheet.girl_runtime.model_dump_json()


def test_owned_native_full_review_pages_and_reopened_maxim_choices_are_preserved(ledger):
    from girlframe.discord_adapter.m3_girl_transition import open_configuration

    service, game, identity, _ = changed(ledger, "OLDGEN")
    account = "*" * 1200
    configure(service, identity, Plan(account=account, maxims=(1, 2)))

    async def run():
        interaction = current(2, 29601)
        await interaction.response.defer(ephemeral=True)
        data = service.get(PLAYER, identity)
        await open_configuration(interaction, service, data)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert form.values["account"] == account and form.values["maxims"] == ("1", "2")
        await open_transition(interaction, service, identity)
        menu = interaction.edit_original_response.call_args.kwargs["view"]
        review_interaction = current(2, 29602)
        await menu.finish.callback(review_interaction)
        view = review_interaction.edit_original_response.call_args.kwargs["view"]
        assert len(view.pages) > 1 and view.apply.disabled
        assert not await view.interaction_check(current(3, 29603))
        assert "\\*" in view.text()
        while view.index < len(view.pages) - 1:
            await view.next.callback(current(2, 29604 + view.index))
        assert not view.apply.disabled
        await view.apply.callback(current(2, 29620))

    asyncio.run(run())
    assert state(game).sheets["2"].girl_runtime.setup.maxims == (1, 2)


def test_mentor_tag_privilege_stops_for_a_replacement_with_same_discord_account(ledger):
    from girlframe.engine.m3_girl_runtime_state import mentor_tag
    from girlframe.engine.m3_girl_transition_state import GirlSetup

    service, game, identity, _ = changed(ledger, "NEWGIRL")
    canon = state(game)
    sheet = canon.sheets["2"]
    original = current_ref(canon, 3)
    sheet.mentor = 3
    sheet.girl_runtime = sheet.girl_runtime.model_copy(
        update={
            "setup": GirlSetup(
                epoch=sheet.girl_runtime.baseline_event,
                book="NEWGIRL",
                source_event="actual-source",
                account="Actual mentor context",
                mentor=original,
            )
        }
    )
    tag = TagState(id="mentor-tag", label="Actual Mentor's tag", giver=3, giver_actor=original)
    assert mentor_tag(sheet, tag, canon)
    canon.sheets["3"].character_id = "new-person-same-discord-account"
    assert not mentor_tag(sheet, tag, canon)


def test_existing_protected_paired_identity_cannot_be_duplicated_or_replaced_by_other_chooser(
    ledger,
):
    service, game, identity, _ = changed(ledger, "BONDED")
    with ledger.transaction() as c:
        canon = state(game)
        protected = canon.sheets["2"].identities[0]
        protected.paired = protected.protected = True
        protected.name = "Previous owner-held Paired Identity"
        game.event(c, 1, "retained-old-paired-identity", "synthetic.state", canon)
    canon = state(game)
    with pytest.raises(WorkflowError, match="already protected Paired"):
        configure(
            service,
            identity,
            Plan(
                account="Cannot duplicate a protected identity",
                pair=current_ref(canon, 3),
                paired_identity=canon.sheets["2"].identities[1].id,
            ),
        )
    configure(
        service,
        identity,
        Plan(
            account="Own existing Pair slot",
            pair=current_ref(canon, 3),
            paired_identity=canon.sheets["2"].identities[0].id,
        ),
    )
    data = service.get(OTHER, identity)
    service.respond(
        OTHER, "actual-pair-kept-existing-slot", identity, data["revision"], accepted=True
    )
    finish(service, identity)
    assert len([x for x in state(game).sheets["2"].identities if x.paired]) == 1
