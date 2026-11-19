"""Void-Drunk marks only an actually heard Tag when the original low Dive resolves."""

from test_ancillary_creation import HARPY, REBEL, enable, scenario
from test_cast_service import change
from test_dive import choose
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_void_drunk import KIND, RULE


def test_original_low_dive_retains_handler_choice_and_scoped_acolyte_effect(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN,
        "acolyte-invitation",
        state(game).revision,
        OTHER.user_id,
        "city0",
        "group",
        contacts=(HARPY,),
    )

    def gear(label):
        return ancillary.NamedAsset(name=label, description="Actual original gear.")

    book = "ABYSSAL ACOLYTE"
    draft = ancillary.Draft(
        name="Original Acolyte",
        book=book,
        bond=HARPY,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, "JANUS")[:2]),
    )
    created = creation.respond(
        OTHER, "acolyte-accepts", invitation["id"], state(game).revision, draft
    )
    acolyte = ActorRef.model_validate(created["actor"])
    diver = current_ref(state(game), PLAYER.user_id)
    change(CastService(ActorService(missions)), OTHER, "join", acolyte)
    MovementService(game).move(
        PLAYER,
        "diver-arrives",
        state(game).revision,
        900,
        diver,
        (0, 4),
        frame=True,
        account="I pilot into the square of the original station.",
    )
    original_tag, private = "public-to-acolyte", "private-from-acolyte"
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets[diver.entity].tags.extend(
            (
                TagState(id=original_tag, label="Loud in the link", giver=1, observers=(2, 3)),
                TagState(id=private, label="Unheard", giver=1, observers=(1, 2)),
            )
        )
        game.event(c, ADMIN.user_id, "original-tags", "synthetic.existing_tags", canon)

    game.dice = Dice((2, 3))
    action = game.begin(
        PLAYER,
        "real-low-dive",
        900,
        state(game).sheets[diver.entity].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Follow the original link.",
            trigger_confirmed=True,
            piloting=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    (choice,) = [x for x in game.choices(OTHER) if x["kind"] == "dive_void_drunk"]
    assert game.decision(OTHER, choice["id"])["dive"]["tags"] == {original_tag: "Loud in the link"}
    answer(game, OTHER, "dive_void_drunk", options=("latch",), denied=(original_tag,))
    assert not is_helpless(state(game), diver, acolyte)
    choose(game, ADMIN, "nearby_npcs_gain_void")
    answer(game, ADMIN, "dive_effect", fields={REBEL.entity: "brain"})
    final = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert is_helpless(final, diver, acolyte)
    assert {x.id for x in final.sheets[diver.entity].tags if x.marked} == {original_tag}
    assert any(x.get("kind") == KIND and x.get("action") == action for x in final.facts)
