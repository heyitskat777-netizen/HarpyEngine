"""An original Escape roll through private native controls and real base consequences."""

import asyncio

import pytest
from test_cast_service import change as cast_change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_physical_operations import place
from test_world_service import ready

from girlframe.discord_adapter.m3_escape import open_escape, open_escape_choice
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_escape import RULE, EscapeService, records
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("faces, tier", [((1, 2), "low"), ((4, 4), "mid"), ((6, 5), "high")])
def test_escape_original_base_outcome_applies_actual_owned_consequence(ledger, faces, tier):
    world, game = ready(ledger)
    game.dice.faces = faces
    personnel = ActorRef(kind="npc", entity="actual-base-attendant")
    world.npc(
        ADMIN,
        "attendant",
        state(game).revision,
        Npc(
            id=personnel.entity,
            name="Attendant",
            jobs=("base_personnel",),
            detail="An actual local crew member.",
            controller=ADMIN.user_id,
            cell=(0, 0),
        ),
    )
    with ledger.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.sheets["2"].heat = 2
        game.event(c, ADMIN.user_id, "establish-original-base", "synthetic.position", canon)
    cast = CastService(ActorService(world.missions))
    cast_change(cast, ADMIN, "join", personnel)
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
    original = state(game)
    girl, friend = current_ref(original, 2), current_ref(original, 3)
    service = EscapeService(game)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_escape(click, service, 900, girl),
            dict(heat="1", account="The table has agreed on the original private Escape scene."),
            91700,
        )
    )
    (case,) = records(state(game))
    assert case.roll.result == tier and case.roll.heat == 1 and game.dice.calls == 1

    def native(viewer, values, sequence):
        asyncio.run(
            submit_form(
                viewer, lambda click: open_escape_choice(click, service, case.id), values, sequence
            )
        )

    if tier == "low":
        removed = original.sheets["2"].identities[0].id
        native(PLAYER, dict(choice=(removed,)), 91704)
        final = state(game)
        assert all(x.id != removed for x in final.sheets["2"].identities)
        assert final.placements == original.placements
    elif tier == "mid":
        native(ADMIN, dict(choice=(friend.token,), account="The original friend finds her."), 91708)
        founded = state(game)
        assert depth(founded, girl, friend) == 2 and is_helpless(founded, girl, friend)
        assert next(x for x in founded.placements if x.actor == girl).incapacitated
        with pytest.raises(WorkflowError, match="unavailable"):
            service.get(PLAYER, case.id)
        ledger.engine.dispose()
        native(
            OTHER,
            dict(choice=("save",), account="The original friend gets her to safety.", tag="Found"),
            91712,
        )
        final = state(game)
        assert not is_helpless(final, girl, friend)
        assert not next(x for x in final.placements if x.actor == girl).incapacitated
        tag = next(x for x in final.sheets["2"].tags if x.label == "Found")
        assert tag.giver_actor == friend and PLAYER.user_id in status_groups(final)[-1]
    else:
        native(
            ADMIN,
            dict(choice=(personnel.token,), account="Actual base staff carry her to sickbay."),
            91716,
        )
        care = state(game)
        assert all(x.damaged for x in care.sheets["2"].assets if x.family == "girl")
        assert PLAYER.user_id in status_groups(care)[-1]
        assert next(x for x in care.placements if x.actor == girl).custody == personnel
        native(ADMIN, dict(choice=("release",), account="The original restraint has ended."), 91720)
        final = state(game)
        assert next(x for x in final.placements if x.actor == girl).custody is None
    assert records(final)[0].resolved and final.sheets["2"].heat == 1
    assert [x for x in final.sheets["2"].assets if x.family == "frame"] == [
        x for x in original.sheets["2"].assets if x.family == "frame"
    ]
