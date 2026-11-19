"""A known Warboy's pronouns apply through the actual native Tag window."""

from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_warboy_boy import KIND, RULE, identifier


def test_warboy_pronouns_on_sheet_and_native_scoped_tag_receipt(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(RULE,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    offer = creation.invite(
        ADMIN, "boy-invite", state(game).revision, PLAYER.user_id, "city0", "group"
    )
    marker = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Original gear.")

    draft = ancillary.Draft(
        name="Original independent Warboy",
        book="WARBOY",
        wanted=marker,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["WARBOY"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("WARBOY", "JANUS")[:2]),
    )
    created = creation.respond(PLAYER, "boy-create", offer["id"], state(game).revision, draft)
    actor = ActorRef.model_validate(created["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    assert ActorService(missions).inspect(PLAYER, actor)["pronouns"] == "he/him"

    MovementService(game).move(
        OTHER,
        "actual-local-marker-moves",
        state(game).revision,
        900,
        marker,
        (0, 4),
        frame=True,
        account="I arrive in the same square.",
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            pilots=tuple(
                x.model_copy(update=dict(revealed=True)) if x.id == actor.entity else x
                for x in canon.world.pilots
            ),
        )
        game.event(c, ADMIN.user_id, "known-warboy", "synthetic.role_disclosure", canon)

    plays = ActorPlayService(game)
    game.dice = Dice((4, 4))
    preview = plays.preview(PLAYER, 900, actor)
    action = plays.begin(
        PLAYER,
        "boy-original-play",
        900,
        actor,
        preview["actor"]["source_sha256"],
        None,
        preview["cast_revision"],
        PlayInput(
            play="keep_your_head",
            context="I talk over their challenge.",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    for viewer in (PLAYER, ADMIN, OTHER):
        (row,) = [x for x in game.choices(viewer) if x["kind"] == "tag_window"]
        decision = game.decision(viewer, row["id"])
        if viewer == OTHER:
            assert identifier(actor) in {x["id"] for x in decision["tags"]}
            answer = ChoiceAnswer(
                options=("tag",),
                denied=(identifier(actor),),
                number=-1,
                text="They recognise and answer my challenge by pronouns.",
                fields={"as_actor": marker.token},
            )
        else:
            assert identifier(actor) not in {x["id"] for x in decision["tags"]}
            answer = ChoiceAnswer(options=("pass",))
        game.respond(viewer, "boy-tag-" + str(viewer.user_id), row["id"], row["revision"], answer)

    with ledger.engine.connect() as c:
        saved = game.action(c, action)
    assert saved["data"]["result"]["total"] == 7
    assert saved["data"]["modifiers"][0]["source"] == "warboy_pronouns"
    assert [x["action"] for x in state(game).facts if x.get("kind") == KIND] == [action]
    assert not ancillary.find(state(game), actor).tags
