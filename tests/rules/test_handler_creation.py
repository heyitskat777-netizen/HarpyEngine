"""Source-backed Handler creation and owned starting relationships, not runtime certification."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_state import Draft, GearDetail, StartingBond
from girlframe.engine.m3_world_state import Board, Npc, World
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError


def ready(store):
    _, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"playbooks"},
                }
            ),
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={
                    "handler_creation": "owned_shared_choices_preserve_existing",
                }
            ),
        }
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(-2, -2), maximum=(2, 2)),
            locations=(),
            npcs=(
                Npc(
                    id="actual-npc",
                    name="PRIVATE_NPC",
                    jobs=("guard",),
                    detail="Private original NPC",
                    controller=1,
                    cell=(0, 0),
                    bonds={"handler:1": 1},
                ),
            ),
        )
        game.event(c, 1, "actual-handler-npc-source", "synthetic.world", canon)
    return HandlerCreationService(store), game


def complete(svc, playbook="Mistress"):
    preview = svc.view(ADMIN)
    pilots = [ActorRef.model_validate(x["ref"]) for x in preview["pilots"]]
    choices = tuple(
        StartingBond(
            pilot=ref,
            rank="ace" if index == 0 else "dog",
            depth=2 if playbook == "Mistress" and index == 1 else 1,
            history="SHARED_HISTORY_" + str(index),
            prompt=index if playbook == "Trainer" else None,
        )
        for index, ref in enumerate(pilots[: 1 if playbook == "Scientist" else 2])
    )
    return Draft(
        playbook=playbook,
        name="Actual Handler",
        appearance="PRIVATE_APPEARANCE",
        outfit="PRIVATE_OUTFIT",
        background="PRIVATE_BACKGROUND",
        gear=(
            GearDetail(kind="weapon", description="PRIVATE_WEAPON"),
            GearDetail(kind="studio", description="PRIVATE_STUDIO"),
        ),
        starting=choices,
        surveilled=("actual-npc",) if playbook == "Insurgent" else (),
        sympathizer="actual-npc" if playbook == "Insurgent" else None,
    )


def save(svc, draft, key=None):
    preview = svc.view(ADMIN)
    return svc.save(ADMIN, key or str(uuid4()), preview["revision"], preview["appointment"], draft)


def agree(svc):
    result = svc.propose(ADMIN, "actual-handler-proposals", svc.view(ADMIN)["revision"])
    for identity in result["ids"]:
        owner = int(svc.get_agreement(ADMIN, identity)["proposal"]["bond"]["pilot"]["entity"])
        viewer = PLAYER if owner == 2 else OTHER
        data = svc.get_agreement(viewer, identity)
        svc.answer(viewer, "actual-response-" + identity, identity, data["revision"], True)
    return result["ids"]


@pytest.mark.parametrize(
    "playbook",
    ["Mistress", "Dogrunner", "Scientist", "Frantic", "Insurgent", "Trainer", "Advocate"],
)
def test_all_seven_actual_starting_variants_save_reopen_agree_and_activate(ledger, playbook):
    svc, game = ready(ledger)
    original = state(game)
    draft = complete(svc, playbook)
    saved = save(svc, draft)
    assert not saved["activated"] and state(game).handler_persona is None
    restarted = HandlerCreationService(ledger)
    assert restarted.view(ADMIN)["draft"] == draft.model_dump(mode="json")
    agree(restarted)
    preview = restarted.view(ADMIN)
    result = restarted.activate(
        ADMIN, "actual-handler-activation", preview["revision"], preview["game_revision"], True
    )
    assert (
        restarted.activate(
            ADMIN, "actual-handler-activation", preview["revision"], preview["game_revision"], True
        )
        == result
    )
    after = state(game)
    assert after.handler_persona.draft == draft
    assert after.handler_persona.id != "1" and after.handler_persona.owner == 1
    assert after.sheets == original.sheets and after.handler_tags == original.handler_tags
    assert after.handler_heat == original.handler_heat
    assert len(after.world.npcs) == 1  # Gear never spawns fictional personnel or transport.
    if playbook == "Mistress":
        assert depth(after, current_ref(after, 1), current_ref(after, 3)) == 2
    if playbook == "Trainer":
        assert [x.phrases for x in after.handler_persona.conditioning] == [
            ("sit", "heel"),
            ("hunt",),
        ]
    if playbook == "Insurgent":
        assert {x.label for x in after.world.npcs[0].tags} == {"Surveilled", "Sympathizer"}
    with ledger.engine.connect() as c:
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))


def test_shared_agreement_does_not_expose_handler_secrets_or_accept_on_other_humans_behalf(ledger):
    svc, game = ready(ledger)
    save(svc, complete(svc, "Insurgent"))
    proposals = svc.propose(ADMIN, "private-proposals", svc.view(ADMIN)["revision"])
    identity = proposals["ids"][0]
    shared = svc.get_agreement(PLAYER, identity)
    assert "SHARED_HISTORY" in str(shared)
    assert all(
        x not in str(shared) for x in ("PRIVATE_", "Insurgent", "actual-npc", "sympathizer", "gear")
    )
    with pytest.raises(WorkflowError):
        svc.answer(ADMIN, "forged-player-consent", identity, shared["revision"], True)
    with pytest.raises(WorkflowError):
        svc.get_agreement(OTHER, identity)
    preview = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="Every original Girl"):
        svc.activate(
            ADMIN, "no-consent-activation", preview["revision"], preview["game_revision"], True
        )
    assert state(game).handler_persona is None


def test_changed_shared_history_invalidates_old_acceptance_but_private_gear_edit_does_not(ledger):
    svc, game = ready(ledger)
    draft = complete(svc)
    save(svc, draft)
    ids = agree(svc)
    save(svc, draft.model_copy(update={"appearance": "Changed private appearance"}))
    assert not svc.get_agreement(PLAYER, ids[0])["stale"]
    changed = draft.starting[0].model_copy(update={"history": "Changed shared history"})
    save(svc, draft.model_copy(update={"starting": (changed, draft.starting[1])}))
    assert svc.get_agreement(PLAYER, ids[0])["stale"]
    preview = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="Every original Girl"):
        svc.activate(
            ADMIN, "stale-consent-activation", preview["revision"], preview["game_revision"], True
        )
    assert state(game).handler_persona is None


def test_paused_activation_is_blocked_but_owned_drafts_and_agreements_remain_available(ledger):
    svc, game = ready(ledger)
    ledger.safety(OTHER, "pause-handler-creation", ledger.status(OTHER)["revision"], pause=True)
    save(svc, complete(svc))
    agree(svc)
    preview = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        svc.activate(
            ADMIN, "paused-handler-activation", preview["revision"], preview["game_revision"], True
        )
    assert state(game).handler_persona is None


def test_legacy_stronger_bond_is_preserved_and_incomplete_creation_cannot_activate(ledger):
    svc, game = ready(ledger)
    save(svc, Draft(name="Partially named Handler"))
    with pytest.raises(WorkflowError, match="Complete Handler"):
        svc.propose(ADMIN, "incomplete-proposals", svc.view(ADMIN)["revision"])
    with ledger.transaction() as c:
        canon = state(game)
        canon.bonds["1:2"] = 2
        game.event(c, 1, "real-existing-bond", "synthetic.bond", canon)
    save(svc, complete(svc, "Scientist"))
    agree(svc)
    preview = svc.view(ADMIN)
    svc.activate(
        ADMIN, "preserve-existing-bond", preview["revision"], preview["game_revision"], True
    )
    from girlframe.engine.m3_actor_bonds import current_ref, depth

    current = state(game)
    assert depth(current, current_ref(current, 1), current_ref(current, 2)) == 2


def test_scientist_can_choose_dog_and_other_relative_ranks_are_preserved(ledger):
    svc, game = ready(ledger)
    draft = complete(svc, "Scientist")
    draft = draft.model_copy(
        update={"starting": (draft.starting[0].model_copy(update={"rank": "dog"}),)}
    )
    save(svc, draft)
    agree(svc)
    preview = svc.view(ADMIN)
    svc.activate(
        ADMIN, "scientist-starting-dog", preview["revision"], preview["game_revision"], True
    )
    assert state(game).order == (3, 2)


def test_changed_original_girl_or_handler_appointment_cannot_reuse_old_shared_requests(ledger):
    from girlframe.services.handler_setup import HandlerService

    svc, game = ready(ledger)
    draft = complete(svc)
    save(svc, draft)
    identities = agree(svc)
    original = svc.view(ADMIN)
    appointments = HandlerService(ledger)
    with ledger.engine.connect() as c:
        revision = appointments.current(c)[0]
    appointments.appoint(ADMIN, "remove-handler-appointment", revision, None)
    with ledger.engine.connect() as c:
        revision = appointments.current(c)[0]
    appointments.appoint(ADMIN, "new-handler-appointment", revision, 1)
    assert svc.get_agreement(PLAYER, identities[0])["stale"]
    with pytest.raises(WorkflowError, match="STALE_HANDLER"):
        svc.save(
            ADMIN,
            "reuse-old-handler-appointment",
            original["revision"],
            original["appointment"],
            draft,
        )
    # A fresh appointment has a distinct draft/persona even for the same account.
    save(svc, draft)
    assert svc.view(ADMIN)["persona_id"] != original["persona_id"]
    current = svc.view(ADMIN)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].character_id = str(uuid4())
        game.event(c, 1, "replaced-original-girl", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_ACTOR"):
        svc.activate(
            ADMIN, "old-girl-cannot-activate", current["revision"], state(game).revision, True
        )
    assert state(game).handler_persona is None


def test_activation_concurrent_retry_and_failure_after_canonical_write_are_atomic(
    ledger, monkeypatch
):
    svc, game = ready(ledger)
    save(svc, complete(svc))
    agree(svc)
    preview = svc.view(ADMIN)
    original = state(game).model_dump_json()
    emit = svc.game.event

    def fail(*args, **kwargs):
        emit(*args, **kwargs)
        raise RuntimeError("Synthetic post-canon failure")

    monkeypatch.setattr(svc.game, "event", fail)
    with pytest.raises(RuntimeError, match="post-canon"):
        svc.activate(
            ADMIN, "retry-handler-activation", preview["revision"], preview["game_revision"], True
        )
    assert state(game).model_dump_json() == original
    monkeypatch.setattr(svc.game, "event", emit)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: svc.activate(
                    ADMIN,
                    "retry-handler-activation",
                    preview["revision"],
                    preview["game_revision"],
                    True,
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert state(game).handler_persona.id == preview["persona_id"]


def test_forged_shared_acceptance_has_no_owned_response_source_and_cannot_activate(ledger):
    svc, game = ready(ledger)
    save(svc, complete(svc))
    identity = svc.propose(
        ADMIN, "actual-unanswered-handler-proposals", svc.view(ADMIN)["revision"]
    )["ids"][0]
    table = t.m3["m3_required_work"]
    with ledger.transaction() as c:
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == ledger.campaign_id, table.c.id == identity
                )
            )
            .mappings()
            .one()
        )
        body = json.loads(row["body_json"]) | {"decision": "accepted"}
        c.execute(
            table.insert().values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json", "state")},
                revision=row["revision"] + 1,
                body_json=json.dumps(body),
                state="resolved",
            )
        )
    with pytest.raises(WorkflowError):
        svc.get_agreement(PLAYER, identity)
    preview = svc.view(ADMIN)
    with pytest.raises(WorkflowError, match="SOURCE_HANDLER_AGREEMENT_MISSING"):
        svc.activate(
            ADMIN,
            "forged-acceptance-activation",
            preview["revision"],
            preview["game_revision"],
            True,
        )
    assert state(game).handler_persona is None


def test_missing_ruling_and_registry_preserve_readable_progress_without_activation(
    ledger, monkeypatch, tmp_path
):
    svc, game = ready(ledger)
    save(svc, complete(svc))
    agree(svc)
    preview = svc.view(ADMIN)
    policy = ledger.policy
    ledger.policy = policy.model_copy(
        update={
            "owner_m3_rulings": policy.owner_m3_rulings.model_copy(
                update={"handler_creation": None}
            )
        }
    )
    with pytest.raises(WorkflowError, match="UNRESOLVED_RULING"):
        svc.activate(
            ADMIN, "missing-handler-ruling", preview["revision"], preview["game_revision"], True
        )
    assert svc.view(ADMIN)["draft"] == preview["draft"]
    ledger.policy = policy
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "missing.json"))
    assert svc.view(ADMIN)["draft"] == preview["draft"]
    with pytest.raises(WorkflowError, match="registry is unavailable"):
        svc.activate(
            ADMIN, "missing-handler-registry", preview["revision"], preview["game_revision"], True
        )
    assert state(game).handler_persona is None
