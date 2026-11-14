"""Real Harpy Beneath normal tiers and original owned resources; synthetic approval only."""

import asyncio
from uuid import uuid4

import pytest
from test_harpy_flirt import native_answer, pass_tags, submit_form
from test_harpy_flirt import prepared as flirt_prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.discord_adapter.m3_harpy_beneath import open_beneath
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_harpy_resources import assets as actual_assets
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.onboarding import WorkflowError


def prepared(store, **kwargs):
    result = flirt_prepared(store, **kwargs)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"discipline"}}
            )
        }
    )
    return result


def start_native(game, ref, worker, gateway):
    target = current_ref(state(game), 3)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda i: open_beneath(i, game, ref),
            dict(
                context="Actual Harpy puts this original Girl beneath her",
                target=(target.token,),
                heat=("0",),
                gain=("1",),
            ),
            989000,
        )
    )
    with game.store.engine.connect() as c:
        identity = game.lock(c, 900)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return identity


def test_native_harpy_mid_actual_tag_and_status_no_controller_sheet_receipt_retry(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(4, 5))
    with ledger.transaction() as c:
        prior = state(game)
        prior.order = (3, 2)
        game.event(c, 1, str(uuid4()), "synthetic.prior_real_status_order", prior)
    before = state(game)
    identity = start_native(game, ref, worker, gateway)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    row, key = native_answer(
        game,
        PLAYER,
        "harpy_beneath_select",
        dict(
            options=("tag", "status"),
            text="My insult sticks",
            **{"fields.tag": "Actual typed Harpy Tag"},
        ),
        989100,
    )
    after = state(game)
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert after.sheets["3"].tags[-1].giver_actor == ref
    assert after.order.index(3) > before.order.index(3)
    assert after.sheets["2"] == before.sheets["2"]
    assert game.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == 1
    assert (
        len(
            [
                x
                for x in after.facts
                if x.get("kind") == "harpy_beneath" and x.get("action") == identity
            ]
        )
        == 1
    )
    game.respond(
        PLAYER,
        key,
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=("tag", "status"),
            text="My insult sticks",
            fields={"tag": "Actual typed Harpy Tag"},
        ),
    )
    assert state(game) == after


def test_native_high_typed_tag_lock_actual_harpy_locker_genuine_permission(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    identity = start_native(game, ref, worker, gateway)
    native_answer(
        game,
        PLAYER,
        "harpy_beneath_select",
        dict(
            options=("tag", "lock_tag"),
            text="The actual insult sticks and cannot be rejected freely",
            **{"fields.tag": "Actual locked Tag", "fields.locked_tag": ("new",)},
        ),
        989200,
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    value = next(
        x for x in state(game).obligations if x.details.get("source_kind") == "harpy_beneath"
    )
    from girlframe.engine.m3_beneath import rejection_blocked

    permissions = PermissionService(ledger)
    assert rejection_blocked(state(game), OTHER.user_id, value.details["tag"])
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="CONSENT_REQUIRED"):
        permissions.authorize_rejection(
            c, OTHER, state(game), current_ref(state(game), OTHER.user_id), value.details["tag"]
        )
    view = permissions.get(PLAYER, value.id)
    with pytest.raises(WorkflowError):
        permissions.grant(OTHER, str(uuid4()), value.id, view["source_sha256"], True)
    permissions.grant(PLAYER, "actual-harpy-locker-consent", value.id, view["source_sha256"], True)
    actual = next(x for x in state(game).obligations if x.id == value.id)
    assert actual.state == "fulfilled"
    assert actual.details["locker_actor"] == ref.model_dump_json()
    assert not rejection_blocked(state(game), OTHER.user_id, value.details["tag"])
    with ledger.engine.connect() as c:
        permissions.authorize_rejection(
            c, OTHER, state(game), current_ref(state(game), OTHER.user_id), value.details["tag"]
        )
    assert game.dice.calls == 1


def test_native_harpy_low_affected_harpy_selects_own_actual_asset_for_counter(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(1, 2))
    identity = start_native(game, ref, worker, gateway)
    before = state(game)
    asset = actual_assets(before, ref)[0].id
    answer(
        game, OTHER, "harpy_beneath_select", options=("damage",), text="My real counter hurts her"
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "harpy_beneath_details")
    with pytest.raises(WorkflowError):
        game.respond(OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(denied=(asset,)))
    answer(game, PLAYER, "harpy_beneath_details", denied=(asset,))
    assert next(x for x in actual_assets(state(game), ref) if x.id == asset).damaged
    assert state(game).sheets["2"] == before.sheets["2"]
    assert state(game).order == before.order and game.dice.calls == 1
    # A last real body Asset requires the real damage/Defeat source rather than
    # being discarded or acknowledged as a generic successful retaliation.
    if game.inspect(PLAYER, identity)["state"] != "complete":
        assert any(x["kind"].startswith("battle_") for x in game.choices(PLAYER))


def test_high_pin_actual_target_owned_response_and_real_required_child(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    identity = start_native(game, ref, worker, gateway)
    answer(
        game,
        PLAYER,
        "harpy_beneath_select",
        options=("tag", "pin"),
        text="I actually pin her",
        fields={"tag": "Pinned down"},
    )
    answer(game, OTHER, "harpy_beneath_pin_response", options=("play",))
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="I make my real pinned response",
            parent=identity,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", text="My actual response Tag")
    answer(game, ADMIN, "handler_keep", flag=True, text="Her response is enough")
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 2


def test_harpy_high_actual_superior_confirms_order_then_real_role_punishment_finishes(
    ledger, tmp_path, monkeypatch
):
    from test_enforcer_requisitions import approved

    from girlframe.engine import m3_harpy_bond_void as sin
    from girlframe.engine.m3_actor_bonds import set_depth
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.services.m3_harpy_bond_void import HarpyBondVoidService

    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    approved(ledger, game, tmp_path, monkeypatch, extra=(sin.RULE,))
    with ledger.transaction() as c:
        prior = state(game)
        event = str(uuid4())
        prior = set_depth(prior, ref, current_ref(prior, 3), 1, event)
        game.event(c, 1, str(uuid4()), "synthetic.prior_harpy_personal_bond", prior, event_id=event)
    identity = start_native(game, ref, worker, gateway)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    issuer = active_handler(state(game))
    before = state(game)
    answer(
        game,
        PLAYER,
        "harpy_beneath_select",
        options=("tag", "punish"),
        text="I act on the actual Handler's command",
        fields={
            "tag": "Under orders",
            "issuer": issuer.token,
            "order": "Give this original Girl Quality Time",
        },
    )
    assert state(game).model_dump(exclude={"revision"}) == before.model_dump(exclude={"revision"})
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(
        game,
        ADMIN,
        "harpy_beneath_order_confirmation",
        flag=True,
        text="I gave this exact order to this actual Harpy against this original Girl",
    )
    case = state(game).role_punishments[-1]
    assert case.executor == ref and case.subject == current_ref(state(game), 3)
    assert case.chooser == ref and case.source_kind == "harpy_beneath"
    service = RolePunishmentService(game)

    def change(viewer, **kw):
        view = service.get(viewer, case.id)
        return service.change(viewer, str(uuid4()), case.id, view["revision"], **kw)

    instruction = Instruction(
        kind="quality_time",
        details_json=Details(
            kind="quality_time", tag="Actual Harpy instruction Tag"
        ).model_dump_json(),
    )
    change(PLAYER, instruction=instruction)
    change(PLAYER, scene="Actual original Harpy and Girl play the instructed scene")
    change(OTHER, attest=True)
    change(PLAYER, execute=True, account="I actually carry out the exact recorded instruction")
    effect = next(x for x in sin.cases(state(game)) if x.source_action == identity)
    assert effect.actor == current_ref(state(game), 3) and effect.harpy == ref
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    row = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_bond_void")
    view = HarpyBondVoidService(game).view(OTHER, effect.id)
    game.respond(
        OTHER,
        str(uuid4()),
        row["id"],
        row["revision"],
        ChoiceAnswer(
            options=(view["assets"][0]["id"],),
            text="Actual required Void after the real Harpy Punishment Bond",
        ),
    )
    assert sin.get(state(game), effect.id).phase == "complete"
    assert game.inspect(PLAYER, identity)["receipt"] == receipt
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).sheets["3"].tags[-1].giver_actor == ref
    assert game.dice.calls == 1


def test_actual_pilot_beneath_original_harpy_has_no_proxy_status_and_typed_tag_bearer(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    before = state(game)
    identity = game.begin(
        OTHER,
        str(uuid4()),
        900,
        before.sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            heat=0,
            context="The original Girl acts against this actual Harpy",
            target_actor=ref,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_beneath_select")
    with pytest.raises(WorkflowError, match="Status|applicable"):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("status", "pin"), text="No fabricated Harpy rank"),
        )
    answer(
        game,
        OTHER,
        "harpy_beneath_select",
        options=("tag", "lock_tag"),
        text="My actual Tag sticks to this Harpy",
        fields={"tag": "Actual Harpy bearer Tag", "locked_tag": "new"},
    )
    after = state(game)
    assert after.order == before.order and after.sheets["2"] == before.sheets["2"]
    assert after.sheets["3"].tags == before.sheets["3"].tags
    lock = next(x for x in after.obligations if x.details.get("source_kind") == "harpy_beneath")
    assert lock.details["bearer_actor"] == ref.model_dump_json()
    assert lock.details["locker_actor"] == current_ref(after, 3).model_dump_json()
    service = PermissionService(ledger)
    view = service.get(OTHER, lock.id)
    service.grant(
        OTHER, "actual-pilot-consents-to-harpy-tag-rejection", lock.id, view["source_sha256"], True
    )
    assert game.inspect(OTHER, identity)["state"] == "complete" and game.dice.calls == 1


def test_native_pilot_mid_fresh_harpy_keeps_source_for_guidance_without_invalid_select(ledger):
    from girlframe.discord_adapter.m3_harpy_beneath import choice_fields

    _, game, _, ref, worker, gateway = prepared(ledger, faces=(4, 4))
    identity = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            heat=0,
            target_actor=ref,
            context="Actual new Harpy without Status or a prior Bond",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "harpy_beneath_select")
    decision = game.decision(OTHER, row["id"])
    assert decision["harpy_beneath"]["base"] == ["tag"]
    assert choice_fields(decision) == []
    assert game.inspect(OTHER, identity)["state"] == "awaiting_choices"
    assert game.inspect(OTHER, identity)["receipt"]["faces"] == [4, 4]
    assert game.dice.calls == 1
    assert not any(x.get("kind") == "harpy_beneath" for x in state(game).facts)
