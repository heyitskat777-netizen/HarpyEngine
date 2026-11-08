"""Girl-rules Handler Void uses real source Assets, never a fake Pilot or foreign Frame."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_world import initial

from girlframe.engine import m3_handler_girl_void as rules
from girlframe.engine.m2 import AssetState, DirectorContext, IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_girl_void_state import ExistingAsset
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_world_state import Npc


def source(canon):
    body = active_handler(canon)
    judge = ActorRef(kind="npc", entity="actual-director")
    canon.world = initial().model_copy(
        update={
            "npcs": (
                Npc(
                    id=judge.entity,
                    name="Actual Director",
                    controller=3,
                    jobs=("director",),
                    detail="Actual separate adjudicator",
                    cell=(0, 0),
                ),
            )
        }
    )
    canon.director_contexts.append(
        DirectorContext(
            id="actual-girl-context",
            handler=1,
            directors=(judge.entity,),
            source_works=("actual-director-source",),
            source_event="actual-context-source",
            body_actor=body,
            identities=[
                IdentityState(id="actual-one", name="Composed"),
                IdentityState(id="actual-two", name="Defiant"),
            ],
        )
    )
    actor = ActorRef(kind="handler", entity="1", incarnation="actual-girl-context")
    return rules.require(
        canon,
        actor,
        work="actual-girl-void-source",
        event="actual-sex-effect",
        appointment="actual-appointment",
        judge=3,
        judge_actor=judge,
        caster=current_ref(canon, 2),
        caster_controller=2,
    ), actor


def test_factual_owned_steps_preserve_actual_body_resources(
    canon,
):
    (state, identity), actor = source(canon)
    before = state.model_dump_json()
    assert state.handler_girl_void[-1].phase == "facts" and not rules.girl_assets(state, actor)
    proposed = rules.propose(
        state,
        identity,
        ExistingAsset(
            id="actual-existing-object",
            name="Established cybernetic eye",
            description="An existing optical implant",
            evidence="Actual old body capability and source",
            damaged=True,
            proposal_event="actual-owner-factual-proposal",
        ),
    )
    assert state.model_dump_json() == before
    reviewed = rules.review(
        proposed,
        identity,
        "actual-judge-factual-review",
        allow=True,
        account="This real existing implant and damage are confirmed",
    )
    assert reviewed.handler_girl_void[-1].phase == "asset"
    asset = rules.girl_assets(reviewed, actor)[0]
    assert asset.damaged and not asset.void and len(reviewed.held_items) == 1
    with pytest.raises(ValueError):
        rules.corrupt(
            reviewed, identity, asset.id, "Cannot skip the actual caster's target choice", "bad"
        )
    selected = rules.select_asset(reviewed, identity, asset.id, "actual-caster-selection")
    changed = rules.corrupt(
        selected,
        identity,
        asset.id,
        "The actual implant fractures into impossible lenses",
        "actual-patient-rewrite",
    )
    effect = changed.handler_girl_void[-1]
    assert effect.allure and effect.phase == "allure" and effect.assigned_frame is None
    assert effect.asset_choice_event == "actual-caster-selection"
    assert effect.corruption_event == "actual-patient-rewrite"
    assert (
        rules.girl_assets(changed, actor)[0].void and rules.girl_assets(changed, actor)[0].damaged
    )
    assert changed.sheets == state.sheets and changed.world == state.world
    assert changed.placements == state.placements and changed.frame_locks == state.frame_locks
    assert (
        changed.handler_heat == state.handler_heat
        and changed.director_contexts == state.director_contexts
    )
    assert changed.held_items[0].origin_asset_json == reviewed.held_items[0].origin_asset_json
    assert changed.held_items[0].state_event == "actual-patient-rewrite"


def test_factual_rejection_does_not_cancel_forced_void_or_grant_any_resource(canon):
    (state, identity), actor = source(canon)
    state = rules.propose(
        state,
        identity,
        ExistingAsset(
            id="unproved",
            name="Unproved proposed Asset",
            description="An unproved description",
            evidence="Unproved owner facts",
            proposal_event="proposal",
        ),
    )
    changed = rules.review(
        state,
        identity,
        "actual-factual-correction",
        allow=False,
        account="No actual prior ownership facts establish this object",
    )
    assert (
        changed.handler_girl_void[-1].phase == "facts"
        and not changed.handler_girl_void[-1].corruption_event
    )
    assert not changed.held_items and not rules.girl_assets(changed, actor)
    assert changed.handler_girl_void[-1].work == "actual-girl-void-source"


def test_real_cap_is_rechecked_at_review_without_free_or_repaired_fifth_asset(canon):
    (state, identity), actor = source(canon)
    state = rules.propose(
        state,
        identity,
        ExistingAsset(
            id="actual-proposal",
            name="Established device",
            description="Actual preexisting device",
            evidence="Actual source",
            proposal_event="proposal",
        ),
    )
    for i in range(4):
        asset = AssetState(
            id="existing-" + str(i),
            family="girl",
            name="Established " + str(i),
            description="Actual capability",
        )
        state.held_items.append(
            HeldItem(
                id="actual-object-" + str(i),
                holder=actor,
                source_owner=actor,
                name=asset.name,
                description=asset.description,
                source_event="actual-prior-custody",
                asset_json=asset.model_dump_json(),
                asset_id=asset.id,
                asset_owner=actor,
            )
        )
    before = state.model_dump_json()
    with pytest.raises(ValueError, match="four"):
        rules.review(state, identity, "review", allow=True, account="Actual attempted fifth")
    assert state.model_dump_json() == before and len(rules.girl_assets(state, actor)) == 4
