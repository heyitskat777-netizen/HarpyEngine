"""The selected original marker resolves a Revolutionary's actual repeated Tag."""

import pytest
from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import ChoiceAnswer, IdentityState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import change as change_bond
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import REVOLUTIONARY, AncillaryIntimacyService
from girlframe.services.m3_ancillary_orders import ILLEGAL, AncillaryOrderService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_revolutionary_identity import LOSS, RULE, personal_handler
from girlframe.services.onboarding import WorkflowError


def test_easily_broken_repeated_marker_owns_replacement_and_tracks_original_loss(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE, REVOLUTIONARY, ILLEGAL))
    missions = MissionService(ledger)
    setup = AncillaryService(missions)
    invitation = setup.invite(
        ADMIN,
        "one-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        contacts=(REBEL,),
    )

    def gear(label):
        return ancillary.NamedAsset(name=label, description="Original gear.")

    book = "REVOLUTIONARY IDEALIST"
    draft = ancillary.Draft(
        book=book,
        name="Original Revolutionary",
        bond=REBEL,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
    )
    created = setup.respond(PLAYER, "original-sheet", invitation["id"], state(game).revision, draft)
    actor = ActorRef.model_validate(created["actor"])
    marker = current_ref(state(game), OTHER.user_id)
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    change(cast, ADMIN, "join", REBEL)
    with ledger.transaction() as c:
        canon = state(game)
        canon = change_bond(canon, actor, REBEL, 1, "prior-identity-changes")
        canon = change_bond(canon, actor, marker, 1, "prior-identity-changes")
        source = ancillary.find(canon, actor)
        original = source.identities[-1]
        tag = TagState(
            id="previously-marked",
            label="Self-reliant",
            giver=OTHER.user_id,
            giver_actor=marker,
            observers=(2, 3),
            marked=True,
            scene_used="earlier",
        )
        prior = tuple(
            IdentityState(id="later:" + str(i), name="Later Identity", slot=i) for i in range(3)
        )
        ancillary.put(
            canon, source.model_copy(update=dict(identities=(*prior, original), tags=(tag,)))
        )
        game.event(
            c,
            ADMIN.user_id,
            "prior-identity-changes",
            "synthetic.existing_tag_and_bonds",
            canon,
            event_id="prior-identity-changes",
        )

    game.dice = Dice((5, 5))
    plays = ActorPlayService(game)
    view = plays.preview(PLAYER, 900, actor)
    plays.begin(
        PLAYER,
        "actual-keep",
        900,
        actor,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(
            play="keep_your_head", trigger_confirmed=True, context="I want to keep control.", heat=0
        ),
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    for person in (ADMIN, PLAYER):
        answer(game, person, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=(tag.id,),
        number=-1,
        text="Their earlier label applies to this choice.",
        fields={"as_actor": marker.token},
    )
    (forced,) = [row for row in game.choices(OTHER) if row["kind"] == "tag_resolution"]
    projected = game.decision(OTHER, forced["id"])
    assert original.id in {x["id"] for x in projected["revolutionary_replacement"]}
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, forced["id"])
    game.respond(
        OTHER,
        "owned-replacement",
        forced["id"],
        forced["revision"],
        ChoiceAnswer(options=("embrace",), denied=(original.id,)),
    )
    final = state(game)
    owned = ancillary.find(final, actor)
    assert not owned.tags and any(
        x.name == tag.label and x.slot == original.slot for x in owned.identities
    )
    assert any(x.get("kind") == LOSS and x.get("actor") == actor.token for x in final.facts)
    assert depth(final, actor, REBEL) == 2 and personal_handler(game, final, actor) is None
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("vicious",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The response was enough.")
    tick(worker, gateway, 5)

    placement = ChainedPlacementService(game)
    original = placement.propose(
        PLAYER, "outside", 900, actor, state(game).revision, "outside_frame", "I step outside."
    )
    placement.decide(ADMIN, "confirm-outside", original["id"], state(game).revision, True)
    MovementService(game).move(
        OTHER, "arrive", state(game).revision, 900, marker, (0, 4), frame=True, account="I arrive."
    )
    physical = PhysicalService(ledger)
    physical.operate(
        OTHER,
        "step-outside",
        state(game).revision,
        CockpitAction(
            actor=marker,
            operation="exit",
            expected_position=physical.preview(OTHER)["position_sha256"],
            account="I leave the cockpit.",
            confirmed=True,
        ),
        channel=900,
    )
    orders = AncillaryOrderService(game)
    assert actor.token in orders.menu(ADMIN, 900, REBEL)["people"]
    assert actor.token not in orders.menu(OTHER, 900, marker)["people"]
    intimacy = AncillaryIntimacyService(game)
    source = intimacy.offer(
        PLAYER, "bond-source", 900, actor, state(game).revision, marker.token
    )["id"]
    game.dice = Dice((6, 6))
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll")):
        intimacy.act(viewer, choice + str(viewer.user_id), source, state(game).revision, choice)
    intimacy.act(
        PLAYER, "choose-two", source, state(game).revision, "offer", picks=("tag", "remain")
    )
    intimacy.act(OTHER, "choose-remain", source, state(game).revision, "remain")
    intimacy.act(OTHER, "release", source, state(game).revision, "release")

    reopened = state(game)
    assert depth(reopened, actor, marker) == 2
    assert reopened.handler == ADMIN.user_id and personal_handler(game, reopened, actor) == marker
    assert actor.token not in orders.menu(ADMIN, 900, REBEL)["people"]
    assert actor.token in orders.menu(OTHER, 900, marker)["people"]
    given = orders.issue(
        OTHER, "scoped-order", 900, marker, reopened.revision, actor.token, "Wait."
    )
    with pytest.raises(WorkflowError):
        orders.get(ADMIN, given["id"])
    assert orders.get(PLAYER, given["id"])["instruction"] == "Wait."
