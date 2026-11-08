"""Real original lock, actual selected Harpy birth and original-person consent/rejection."""

import json
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_void_service import five_no, respond

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_tag_permissions import MARKER, can_reject
from girlframe.engine.m3_world_state import Board, World
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def reborn_with_lock(
    store,
    *,
    locker_converts=False,
    retain=True,
    frame="JANUS-B",
    configure=None,
    retained_plays=None,
):
    _, game = service(store, girl="ALPHA", frame=frame)
    if configure:
        configure(game)
    policy = store.policy
    store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays", "world"}}
            ),
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
        }
    )
    worker, gateway = GameWorker(game), Gateway()
    with store.transaction() as c:
        canon = state(game)
        actor = current_ref(canon, 2)
        victim = current_ref(canon, 3) if locker_converts else actor
        tag = TagState(
            id="actual-old-giver-tag",
            label="PRIVATE_ORIGINAL_TAG",
            giver=1,
            giver_actor=current_ref(canon, 1),
            observers=(1, 2, 3),
            marked=True,
        )
        canon.sheets[victim.entity].tags.append(tag)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        view = resolve(canon, actor, profiles(c, store.campaign_id), require_current_profile=False)
        canon = physical.initial(
            canon,
            profiles(c, store.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=view.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="inside_frame",
                account="Actual original Girl and Frame facts",
                facts_confirmed=True,
            ),
            "actual-retained-original-body",
            "actual-retained-placement-proposal",
            "actual-retained-placement-confirm",
        )
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[:-1]:
            asset.void = True
        last = frames[-1].id
        game.event(c, 1, str(uuid4()), "synthetic.prior_tag_and_frame_facts", canon)
    game.dice.faces = (6, 6) if locker_converts else (1, 1)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual source confrontation locks an existing Tag",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER if locker_converts else OTHER,
        "beneath_select",
        options=("status", "lock_tag") if locker_converts else ("lock_tag",),
        fields={"locked_tag": tag.id},
        text="Actual source locker chooses the existing Tag",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    permission = next(x for x in state(game).obligations if x.kind == "tag_rejection_permission")
    assert permission.owner == (2 if locker_converts else 3) and permission.owner != tag.giver
    tick(worker, gateway, 6)
    game.dice.faces = (4, 5)
    game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            heat=0,
            context="Actual final original Frame corruption",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "dive_select",
        options=("void_and_unmark_all",),
        text="Actual final corruption",
    )
    answer(
        game, PLAYER, "dive_effect", fields={"asset": last}, text="Actual Frame Asset becomes Void"
    )
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_void_threshold")
    work = json.loads(choice["body_json"])["work_id"]
    void = VoidService(store)
    five_no(void, work)
    view = void.get(PLAYER, work)
    package = view["rebirth_choice"] | dict(
        retained_tags=[tag.id] if retain and not locker_converts else [],
        account="Actual selected birth choices",
    )
    if retained_plays:
        available = [x["id"] for x in view["plays"] if x["id"] not in retained_plays]
        package["retained_plays"] = list(retained_plays) + available[: 4 - len(retained_plays)]
    respond(void, work, "save_rebirth", dict(choice=package, account="Actual owned choices"))
    respond(void, work, "rebirth", dict(choice=package, account="Actual original conversion"))
    tick(worker, gateway, 7)
    body = state(game).harpy_states[-1]
    return (
        game,
        worker,
        gateway,
        ActorRef(kind="external_pilot", entity=body.id),
        permission.id,
        tag.id,
    )


def test_actual_converted_bearer_keeps_restriction_and_only_original_locker_can_consent(ledger):
    game, _, _, actor, identity, tag = reborn_with_lock(ledger)
    service = PermissionService(ledger)
    assert not can_reject(state(game), actor, tag)
    data = service.get(OTHER, identity)
    assert data["can_consent"] and data["bearer_actor"] == actor.model_dump(mode="json")
    assert service.for_tag(PLAYER, actor, tag)[0]["id"] == identity
    with pytest.raises(WorkflowError):
        service.get(ADMIN, identity)
    with pytest.raises(WorkflowError):
        service.grant(PLAYER, str(uuid4()), identity, data["source_sha256"], True)
    service.grant(OTHER, str(uuid4()), identity, data["source_sha256"], True)
    assert can_reject(state(game), actor, tag)
    assert any(x.id == tag for x in state(game).harpy_states[-1].tags)
    marker = json.loads(state(game).career_archives[-1].links_json)[MARKER]
    assert marker["retained_tag_ids"] == [tag]


def test_actual_converted_locker_retains_own_consent_without_current_pc_proxy(ledger):
    game, _, _, actor, identity, tag = reborn_with_lock(ledger, locker_converts=True)
    assert "2" not in state(game).sheets
    service = PermissionService(ledger)
    data = service.get(PLAYER, identity)
    assert data["can_consent"] and data["locker_actor"] == actor.model_dump(mode="json")
    with pytest.raises(WorkflowError):
        service.grant(ADMIN, str(uuid4()), identity, data["source_sha256"], True)
    service.grant(PLAYER, str(uuid4()), identity, data["source_sha256"], True)
    assert can_reject(state(game), current_ref(state(game), 3), tag)


def test_discarded_tag_has_no_consent_claim_and_copied_old_id_fails_closed(ledger):
    game, _, _, actor, identity, tag = reborn_with_lock(ledger, retain=False)
    service = PermissionService(ledger)
    assert not service.get(OTHER, identity)["active"]
    with pytest.raises((ValueError, WorkflowError)):
        service.for_tag(PLAYER, actor, tag)
    from girlframe.engine.m3_void_state import HarpyTag

    with ledger.transaction() as c:
        canon = state(game)
        canon.harpy_states = [
            x.model_copy(
                update={"tags": (*x.tags, HarpyTag(id=tag, label="Copied old ID", giver=1))}
            )
            if x.id == actor.entity
            else x
            for x in canon.harpy_states
        ]
        game.event(c, 1, str(uuid4()), "synthetic.invalid_copied_tag", canon)
    with pytest.raises(ValueError, match="discarded/copied"):
        can_reject(state(game), actor, tag)
    with pytest.raises(WorkflowError, match="discarded/copied"):
        service.get(OTHER, identity)


def test_actual_retained_tag_permission_then_owed_rejection(
    ledger,
):
    from girlframe.services.m3_actor_plays import ActorPlayService
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    game, worker, gateway, actor, identity, tag = reborn_with_lock(ledger)
    cast = CastService(ActorService(MissionService(ledger)))
    current = cast.view(PLAYER, 900)
    cast.change(
        PLAYER, str(uuid4()), 900, current["game_revision"], current["cast_revision"], "join", actor
    )
    plays = ActorPlayService(game)
    view = plays.preview(PLAYER, 900, actor)
    game.dice.faces = (4, 4)
    keep = plays.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual danger to retained original Tag",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway)
    locker = current_ref(state(game), 3)
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=(tag,),
        fields={"as_actor": locker.token},
        number=1,
        text="Original locker actually knows the retained Tag in this scene",
    )
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    with pytest.raises(WorkflowError, match="CONSENT_REQUIRED|consent|locker"):
        answer(game, PLAYER, "tag_resolution", options=("reject",))
    assert not any(x.kind == "actor_reject_tag" for x in state(game).obligations)
    permissions = PermissionService(ledger)
    data = permissions.get(OTHER, identity)
    permissions.grant(OTHER, str(uuid4()), identity, data["source_sha256"], True)
    answer(game, PLAYER, "tag_resolution", options=("reject",))
    assert any(x.id == tag and x.rejection_pending for x in state(game).harpy_states[-1].tags)
    answer(game, PLAYER, "actor_keep", options=("beautiful", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual GM sufficiency ruling")
    assert game.inspect(PLAYER, keep)["state"] == "complete"
    tick(worker, gateway, 6)
    obligation = next(x for x in state(game).obligations if x.kind == "actor_reject_tag")
    before = game.dice.calls
    view = plays.preview(PLAYER, 900, actor)
    rejected = plays.begin(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(
            play="actor_reject_tag",
            heat=0,
            context="Actual original Harpy takes action against the Tag",
            trigger_confirmed=True,
        ),
        rejection=obligation.id,
    )["action_id"]
    assert any(x.id == tag for x in state(game).harpy_states[-1].tags)
    tick(worker, gateway)
    assert game.inspect(PLAYER, rejected)["state"] == "complete"
    assert game.dice.calls == before
    assert not any(x.id == tag for x in state(game).harpy_states[-1].tags)
    assert next(x for x in state(game).obligations if x.id == obligation.id).state == "fulfilled"


@pytest.mark.parametrize("successor", [True, False])
def test_replacement_uid_cannot_inherit_locker_authority_or_forge_a_consent_event(
    ledger, successor
):
    game, _, _, actor, identity, tag = reborn_with_lock(ledger)
    permissions = PermissionService(ledger)
    original = permissions.get(OTHER, identity)
    if successor:
        with ledger.transaction() as c:
            canon = state(game)
            canon.sheets["3"].character_id = str(uuid4())
            game.event(c, 1, str(uuid4()), "synthetic.new_successor_identity", canon)
        current = permissions.get(OTHER, identity)
        assert current["stale"] and not current["can_consent"] and current["active"]
        with pytest.raises(WorkflowError):
            permissions.grant(OTHER, str(uuid4()), identity, original["source_sha256"], True)
    with ledger.transaction() as c:
        canon = state(game)
        next(x for x in canon.obligations if x.id == identity).state = "fulfilled"
        game.event(
            c, 3, str(uuid4()), "m3.tag_rejection_permission_granted", canon, permission_id=identity
        )
    with pytest.raises(WorkflowError, match="SOURCE_CONSENT_MISSING"):
        permissions.get(PLAYER, identity)
    with ledger.engine.connect() as c:
        with pytest.raises(WorkflowError, match="SOURCE_CONSENT_MISSING"):
            permissions.authorize_rejection(c, PLAYER, state(game), actor, tag)


def test_native_retained_tag_request_uses_existing_original_locker_form_and_explicit_response(
    ledger,
):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m3_tag_permissions import open_permission, open_tag_permissions

    game, _, _, actor, identity, tag = reborn_with_lock(ledger)
    service = PermissionService(ledger)

    async def run():
        owner = current(2, 880001)
        await owner.response.defer(ephemeral=True)
        await open_tag_permissions(owner, service, actor, tag)
        assert "locker" in owner.edit_original_response.call_args.kwargs["content"]
        locker = current(3, 880002)
        await locker.response.defer(ephemeral=True)
        await open_permission(locker, service, identity)
        form = locker.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1, 880003))
        form.values["confirm"] = ("yes",)
        await form.confirm.callback(current(3, 880004))
        assert form.completed

    asyncio.run(run())
    assert service.get(PLAYER, identity)["allowed"] and can_reject(state(game), actor, tag)
    assert any(x.id == tag for x in state(game).harpy_states[-1].tags)
