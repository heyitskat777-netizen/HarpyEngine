"""A Warboy reaffirms an owned Tag against one source-backed Helpless condition."""

import asyncio
from uuid import uuid4

import pytest
from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_harpy_flirt import submit_form
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.discord_adapter.m3_warboy_hate import open_conditioned_hate
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_warboy_hate import RULE, ConditionedHateService, records
from girlframe.services.onboarding import WorkflowError


def test_warboy_conditioned_hate_marks_owned_tag_and_clears_only_actual_new_source(
    ledger, tmp_path, monkeypatch
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN, "warboy", state(game).revision, PLAYER.user_id, "city0", "group"
    )["id"]

    def own(name):
        return ancillary.NamedAsset(name=name, description="Original synthetic owned gear")

    wanted = current_ref(state(game), OTHER.user_id)
    draft = ancillary.Draft(
        name="Synthetic Warboy",
        book="WARBOY",
        wanted=wanted,
        frame_catalogue="JANUS",
        girl_assets=tuple(own(x) for x in ancillary.STARTERS["WARBOY"].assets[:2]),
        frame_assets=tuple(own(x) for x in ancillary.frame_assets("WARBOY", "JANUS")[:2]),
    )
    result = creation.respond(PLAYER, "original-warboy", invitation, state(game).revision, draft)
    actor = ActorRef.model_validate(result["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    handler = active_handler(state(game))
    event = str(uuid4())
    independent = str(uuid4())
    with ledger.transaction() as c:
        canon = state(game)
        (warboy,) = ancillary.records(canon)
        tag = TagState(
            id="existing-tag", label="Hard to impress", giver=OTHER.user_id, giver_actor=wanted
        )
        ancillary.put(canon, warboy.model_copy(update=dict(tags=(tag,))))
        older = make_helpless(canon, actor, handler, independent)
        game.event(
            c,
            ADMIN.user_id,
            "existing-source",
            "synthetic.independent",
            older,
            event_id=independent,
        )
    with ledger.transaction() as c:
        canon = state(game)
        actual = make_helpless(canon, actor, wanted, event)
        game.event(
            c,
            OTHER.user_id,
            "original-source",
            "synthetic.fresh_scene_condition",
            actual,
            event_id=event,
            scene_id=game.scene(c, 900)["id"],
        )
    service = ConditionedHateService(game)
    source = next(x for x in state(game).helpless_conditions if x.source_events == (event,))
    inbox = InboxService(ledger)
    assert any(x.identity == source.id and x.task == "m3_warboy_hate" for x in inbox.items(PLAYER))
    with pytest.raises(WorkflowError, match="unavailable"):
        service.get(OTHER, source.id)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda click: open_conditioned_hate(click, service, source.id),
            dict(
                choice=("existing-tag",), account="I immediately stand firm and reject the insult."
            ),
            93450,
        )
    )
    assert is_helpless(state(game), actor, wanted)
    assert any(x.identity == source.id and x.task == "m3_warboy_hate" for x in inbox.items(ADMIN))
    ledger.engine.dispose()
    asyncio.run(
        submit_form(
            ADMIN,
            lambda click: open_conditioned_hate(click, service, source.id),
            dict(choice=("yes",)),
            93454,
        )
    )
    final = state(game)
    (resolved,) = records(final)
    assert resolved.accepted and resolved.original.source_events == (event,)
    assert not is_helpless(final, actor, wanted) and is_helpless(final, actor, handler)
    tag = ancillary.records(final)[0].tags[0]
    assert tag.marked and tag.scene_used == resolved.scene
