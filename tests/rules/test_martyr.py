"""One source-paid Martyr death, original-human native response and actual next preparation."""

import asyncio
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current
from test_strain import facts

from girlframe.discord_adapter.m3_martyr import open_memorial, open_purchase
from girlframe.engine import m3_martyr as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_martyr import MartyrService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService


def test_martyr_native_death_memorial_and_next_budget_preparation(ledger, tmp_path, monkeypatch):
    _, game = service(ledger, girl="ALPHA", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "playbooks"}}
            )
        }
    )
    strain = StrainService(OffDutyService(MissionService(ledger)))
    strain.configure(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        "falling_apart",
        frozenset({"void", "rebellion", "budget"}),
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", actual)
    source = MartyrService(game)

    async def buy():
        own = current(2, 999301)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual native Autocrat Martyr acquisition")
        await form.confirm.callback(current(2, 999302))
        assert form.completed

    asyncio.run(buy())
    before = state(game)
    actor = current_ref(before, 2)
    assert before.sheets["2"].permissions == 0 and rules.held(before, actor)
    receipt = rules.held(before, actor)
    assert receipt is not None
    storage = StorageService(ledger)
    with ledger.engine.connect() as c:
        assert storage._reduction(c, receipt.source_event) is None
    event = str(uuid4())
    with ledger.transaction() as c:
        ended = end_in_transaction(
            c,
            game,
            before,
            actor,
            reason="death",
            source_event=event,
            account="Actual unprevented original death",
            archive_id=str(uuid4()),
        )
        game.event(c, 2, str(uuid4()), "m3.synthetic_ending", ended, event_id=event)
        synchronize_end(c, game, ended.career_archives[-1])
    after = state(game)
    episode = rules.episodes(after)[-1]
    assert after.strain.levels == {"void": "high", "rebellion": "low", "budget": "low"}
    assert actor.entity not in after.sheets and after.career_archives[-1].actor == actor
    assert rules.budget_death_excluded(after, event)
    # The same proved immediate High→Low source can release an older storage order,
    # even though the next Strain preparation will already start Low.
    with ledger.engine.connect() as c:
        assert storage._reduction(c, receipt.source_event) == event
    assert source.get(PLAYER, episode.id)["can_act"]

    async def memorial():
        own = current(2, 999303)
        await own.response.defer(ephemeral=True)
        await open_memorial(own, source, episode.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            memorial=("hero",),
            account="The Foundation remembers this original Pilot as a righteous hero",
        )
        await form.confirm.callback(current(2, 999304))
        assert form.completed

    asyncio.run(memorial())
    completed = source.get(PLAYER, episode.id)
    assert completed["episode"]["memorial"] == "hero" and not completed["can_act"]
    assert actor.entity not in state(game).sheets and len(state(game).career_archives) == 1
    period = strain.periods.begin(ADMIN, str(uuid4()))["id"]
    current_state = state(game)
    count = sum(any(a.void for a in x.assets) for x in current_state.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period,
        1,
        current_state.revision,
        facts(
            at_least_half_have_void=2 * count >= len(current_state.order),
            no_girl_void=count == 0,
            girl_death_or_severe=False,
        ),
    )
    assert state(game).strain.levels["budget"] == "low"
    assert next(x for x in state(game).strain.requests if x.track == "budget").severity == "low"
