"""Deferred actual no-roll AM/Bonded source, with original bodies and human authors."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from m3_policy_scenario import configure_m3_fixture
from test_creation import selected
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, state
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.discord_adapter.m3_bonded_am import open_bonded_am
from girlframe.discord_adapter.m3_bonded_support import open_delegated
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_bonded_am as rules
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation import AssetChoice
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import InitialConditions
from girlframe.engine.creation_review import CreationRulings
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.pair_assets import PairNames
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_bonded import BondedService
from girlframe.services.m3_bonded_am import BondedAMService, prove
from girlframe.services.onboarding import WorkflowError


def actual_three(store):
    """Real original Bonded + Pair-AM + other-AM creation; no replaced sheet/subtype."""
    store.policy = store.policy.model_copy(
        update={
            "owner_initial_conditions": InitialConditions(),
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
        }
    )
    for viewer, book in ((PLAYER, "BONDED"), (OTHER, "AM"), (FOUR, "AM")):
        seed(store, viewer, callsign="Actual " + str(viewer.user_id))
        store.save_draft(
            viewer,
            str(uuid4()),
            store.draft(viewer)["revision"],
            DraftInput(
                callsign="Actual " + str(viewer.user_id),
                girl_playbook=book,
                frame_playbook="THE ENFORCER",
                notes="PRIVATE original creation",
            ),
        )
    store.join(ADMIN, str(uuid4()))
    handler = HandlerService(store)
    handler.appoint(ADMIN, str(uuid4()), 0, ADMIN.user_id)
    bonds = BondService(store)
    sources = {}
    for actor, target in ((PLAYER, OTHER), (OTHER, FOUR), (FOUR, PLAYER)):
        row = bonds.propose(
            actor,
            str(uuid4()),
            store.draft(actor)["revision"],
            store.draft(target)["revision"],
            BondProposal(
                target_id=target.user_id, prompt=0, context="My actual original starting Bond"
            ),
        )
        bonds.decide(target, str(uuid4()), row["id"], 1, "accept")
        sources[actor.user_id] = row["id"]
    from girlframe.services.pair_assets import PairService

    PairService(store).choose(
        OTHER,
        str(uuid4()),
        sources[2],
        2,
        0,
        PairNames(names=tuple(CATALOG["BONDED"]["assets"][:2])),
    )
    creation, review = CreationService(store), CreationReviewService(store)
    for viewer, book in ((PLAYER, "BONDED"), (OTHER, "AM"), (FOUR, "AM")):
        progress = creation.get(viewer)
        data = selected(book, "THE ENFORCER").model_copy(
            update={
                "shared_tokens": progress.draft.shared_tokens,
                "pair_source_token": progress.draft.pair_source_token,
                "pair_asset_descriptions": tuple(
                    AssetChoice(name=x, description="Actual Pair-picked body Asset")
                    for x in progress.pair_choice.names
                )
                if progress.pair_choice
                else (),
            }
        )
        creation.save(
            viewer,
            str(uuid4()),
            progress.revision,
            store.draft(viewer)["revision"],
            data,
            expected_pair_token=data.pair_source_token,
        )
        progress = creation.get(viewer)
        review.select_bond(
            viewer,
            str(uuid4()),
            progress.revision,
            store.draft(viewer)["revision"],
            progress.draft,
            sources[viewer.user_id],
        )
    rank = handler.roster(ADMIN)["revision"]
    handler.rank(
        ADMIN,
        str(uuid4()),
        rank,
        tuple(
            PilotRef(user_id=x.user_id, character_revision=store.draft(x)["revision"])
            for x in (PLAYER, OTHER, FOUR)
        ),
    )
    handler.rulings(ADMIN, str(uuid4()), rank + 1, CreationRulings())
    game = GameService(store, dice=Dice((4, 5)))
    for viewer in (PLAYER, OTHER, FOUR):
        checked = review.get(viewer)
        assert checked.sheet.ready_for_rules_review, checked.sheet.issues
        review.save(viewer, str(uuid4()), checked.saved_revision, checked.fingerprint)
        game.activate(viewer, str(uuid4()), review.get(viewer).fingerprint)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, FOUR, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    return game


def native(service, viewer, *, parent=None, identity=None, operation=None, **values):
    async def run():
        opened = current(viewer.user_id, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        if parent is not None:
            await open_delegated(opened, service.game, parent)
        else:
            await open_bonded_am(opened, service, identity=identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        forbidden = current(3, int(uuid4().int % 1000000000))
        assert not await form.interaction_check(forbidden)
        if operation:
            form.values["operation"] = (operation,)
            selected = current(viewer.user_id, int(uuid4().int % 1000000000))
            selected.channel_id = 900
            await form.confirm.callback(selected)
            assert form.completed, selected.edit_original_response.call_args_list
            form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, int(uuid4().int % 1000000000))
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return str(submitted.id)

    return asyncio.run(run())


# AUTHORED NOT RUN during the bounded P1 adapter assignment.
def test_actual_native_bonded_am_two_owned_performances_no_roll_and_private_original_pair(
    ledger, tmp_path, monkeypatch
):
    game = actual_three(ledger)
    configure_m3_fixture(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(*bonded.RULES, rules.RULE))
    with ledger.transaction() as c:
        original = state(game)
        original.world = initial()
        for owner in (2, 3, 4):
            original = place(original, owner, mode="outside_frame", cell=(0, 0))
        game.event(c, 1, str(uuid4()), "synthetic.actual_original_legal_body_positions", original)
    controls, source = BondedAMService(game), BondedService(game)
    before = state(game)
    parent = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        before.revision,
        "sex",
        "PRIVATE actual non-Pair encounter, no circuit access",
        target=current_ref(before, 4),
        route="delegated",
        delegated_rule=rules.RULE,
    )["id"]
    source.confirm(
        FOUR,
        str(uuid4()),
        parent,
        state(game).revision,
        True,
        "My own voluntary participation; no circuit access",
    )
    native(
        controls, PLAYER, parent=parent, account="Actual original participants; no borrowed body"
    )
    actual = next(x for x in rules.sources(state(game)) if x.bonded_source == parent)
    with pytest.raises(WorkflowError, match="SOURCE_PAUSE_NOT_ACKNOWLEDGED"):
        controls.perform(PLAYER, str(uuid4()), actual.id, state(game).revision, "Not performed yet")
    gateway = Gateway()
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    before_performance = state(game)
    native(
        controls,
        PLAYER,
        identity=actual.id,
        operation="perform",
        account="PRIVATE_BONDED actual performed participation without circuit access",
        circuits=("no",),
    )
    assert rules.source(state(game), actual.id).phase == "active"
    assert bonded.get(state(game), parent).phase == "bound"
    revision = state(game).revision
    untouched = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="SOURCE_CIRCUITS_REQUIRED"):
        controls.perform(
            FOUR,
            str(uuid4()),
            actual.id,
            revision,
            "Not a fabricated Code source",
            circuits_touched=True,
        )
    assert state(game).model_dump_json() == untouched
    key = native(
        controls,
        FOUR,
        identity=actual.id,
        operation="perform",
        account="PRIVATE_AM actual own performed participation without touching circuits",
        circuits=("no",),
    )
    replay = controls.perform(
        FOUR,
        key,
        actual.id,
        revision,
        "PRIVATE_AM actual own performed participation without touching circuits",
        circuits_touched=False,
    )
    assert replay["id"] == actual.id
    after = state(game)
    assert len([x for x in rules.performances(after) if x.source == actual.id]) == 2
    assert rules.source(after, actual.id).phase == "complete"
    assert bonded.get(after, parent).phase == "complete"
    assert game.dice.calls == 0
    for owner in ("2", "3", "4"):
        assert after.sheets[owner].heat == before_performance.sheets[owner].heat
        assert after.sheets[owner].identities == before_performance.sheets[owner].identities
        assert after.sheets[owner].assets == before_performance.sheets[owner].assets
    assert controls.view(PLAYER, actual.id)["no_additional_roll"]
    assert controls.view(FOUR, actual.id)["source"]["action"] is None
    with pytest.raises(WorkflowError):
        controls.view(OTHER, actual.id)
    with ledger.engine.connect() as c:
        assert prove(game, c, after, actual.id).completed_event
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_actions"])
                .where(
                    t.m2["m2_actions"].c.campaign_id == ledger.campaign_id,
                )
            )
            == 0
        )
        link = next(x for x in bonded.records(after, bonded.Delegation) if x.source == parent)
        assert link.action is None and link.session == actual.id and link.completed_event
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    assert controls.view(PLAYER, actual.id)["pause"]["state"] == "closed"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    assert "PRIVATE_AM" not in json.dumps(gateway.messages)

    async def reopen_saved_parent():
        opened = current(PLAYER.user_id, int(uuid4().int % 1000000000))
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_delegated(opened, game, parent)
        content = opened.edit_original_response.call_args.kwargs["content"]
        assert "complete" in content and "PRIVATE_AM" in content

    asyncio.run(reopen_saved_parent())
