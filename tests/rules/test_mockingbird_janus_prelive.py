"""One synthetic native Mockingbird/JANUS dependency flow; no live release approval."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_janus_battery import connected, start
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.engine.m3_mockingbird import NATIVE_RISK, RISK
from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("scope", ("full_parent", "native_cohort"))
def test_native_mockingbird_risk_shifts_actual_janus_battery_before_owned_benefits(
    ledger, tmp_path, monkeypatch, scope
):
    game, worker, gateway, core, contact = connected(ledger, tmp_path, monkeypatch, faces=(1, 1))
    # Reuse genuine reviewed original Core/contact setup, then restrict this
    # synthetic scenario to these three source entries. This file never updates
    # the production registry or claims independent certification.
    data = load_registry().model_dump(mode="json")
    template = next(x for x in data["entries"] if x["id"] == CORE)
    released = {CORE, BATTERY, RISK if scope == "full_parent" else NATIVE_RISK}
    for entry in data["entries"]:
        if entry["id"] in released:
            for key in ("implementation", "source_audit", "contract", "test_evidence"):
                entry[key] = template[key]
            entry.update(
                independent_review="approved",
                reviewer="synthetic fixture only",
                review_reference="Mockingbird/JANUS scenario, not live certification",
            )
        else:
            entry["independent_review"] = "pending"
    registry = Registry.model_validate_json(json.dumps(data))
    assert {x.id for x in registry.entries if x.verified} == released
    source = tmp_path / "synthetic-mockingbird-janus-only.json"
    source.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(source))
    approval = ledger.policy.m3_approval
    assert approval is not None
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "registry_sha256": digest(registry),
                    "native_risk_plays": frozenset({"living_battery"})
                    if scope == "native_cohort"
                    else frozenset(),
                }
            )
        }
    )
    with ledger.transaction() as connection:
        actual = state(game)
        assert actual.sheets["2"].girl == "MOCKINGBIRD"
        marked = actual.sheets["2"].identities[0].id
        actual.sheets["2"].identities[0].marked = True
        game.event(connection, 1, str(uuid4()), "synthetic.prior_actual_identity_mark", actual)
    before = state(game)
    paid = next(x for x in before.sheets["2"].assets if x.family == "frame" and not x.void)
    original_core = before.janus_cores[-1]
    assert original_core.controller == OTHER.user_id and original_core.id != str(OTHER.user_id)
    action = start(game, core)
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [1, 1] and receipt["pre_total"] == 6 and receipt["heat"] == 0
    assert receipt["pre_modifiers"] == [{"source": "battery_tags", "amount": 4}]

    def pending(viewer, kind):
        return next(
            x for x in game.choices(viewer) if x["kind"] == kind and x["action_id"] == action
        )

    def interaction(viewer, number):
        result = current(viewer.user_id, number)
        result.channel_id = 900
        return result

    async def submit(viewer, row, values, number, *, check_other=False):
        caller = interaction(viewer, number)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, row["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        if check_other:
            assert not await form.interaction_check(interaction(OTHER, number + 1))
        form.values.update(values)
        confirmation = interaction(viewer, number + 2)
        await form.confirm.callback(confirmation)
        assert form.completed, confirmation.edit_original_response.call_args_list
        return str(confirmation.id)

    if scope == "native_cohort":
        from girlframe.services.m3_mockingbird import native_released

        with ledger.engine.connect() as c:
            original_action = game.action(c, action)
            assert native_released(game, c, state(game), original_action)
            for key, value in (
                ("play", "dive_deep"),
                ("receipt", None),
                ("actor_basic", {"ref": core.model_dump(mode="json")}),
            ):
                altered = json.loads(json.dumps(original_action))
                altered["data"][key] = value
                assert not native_released(game, c, state(game), altered)
        saved_policy = ledger.policy
        ledger.policy = saved_policy.model_copy(
            update={
                "m3_approval": saved_policy.m3_approval.model_copy(
                    update={"registry_sha256": "0" * 64}
                )
            }
        )
        frozen = state(game)
        with pytest.raises(WorkflowError, match="M3_POLICY_CHANGED|M3_REVIEW_PENDING"):
            row = pending(PLAYER, "mockingbird_risk")
            game.respond(PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer())
        assert state(game) == frozen and game.dice.calls == 1
        ledger.policy = saved_policy
    risk = pending(PLAYER, "mockingbird_risk")
    account = "PRIVATE_PRELIVE_VOID_COST: the original Frame shell grows cold glass veins"
    key = asyncio.run(
        submit(
            PLAYER,
            risk,
            dict(total=("9",), asset=(paid.id,), description=account),
            986100,
            check_other=True,
        )
    )
    shifted = state(game)
    assert {x.id for x in shifted.sheets["2"].assets if x.void} - {
        x.id for x in before.sheets["2"].assets if x.void
    } == {paid.id}
    assert shifted.janus_cores[-1].tags == original_core.tags
    assert not any(x["kind"] == "janus_erase" for x in game.choices(PLAYER))
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as connection:
        # Pending result details remain intentionally hidden by inspect(); this
        # fixture checks the real source before its owned benefits complete.
        assert game.action(connection, action)["data"]["result"]["tier"] == "mid"
    game.respond(
        PLAYER,
        key,
        risk["id"],
        risk["revision"],
        ChoiceAnswer(number=9, fields={"asset": paid.id}, text=account),
    )
    assert state(game) == shifted
    question = "PRIVATE_PRELIVE_BRAIN_QUESTION: what do you perceive through this link?"
    asyncio.run(
        submit(
            PLAYER,
            pending(PLAYER, "janus_select"),
            dict(
                choices=("identities", "question"),
                identities=(marked,),
                heat=("0",),
                question=question,
            ),
            986110,
        )
    )
    assert not next(x for x in state(game).sheets["2"].identities if x.id == marked).marked
    assert not any(x["kind"] == "janus_answer" for x in game.choices(ADMIN))
    answer = "PRIVATE_PRELIVE_CORE_ANSWER: the actual original Core supplies her own response"
    asyncio.run(submit(OTHER, pending(OTHER, "janus_answer"), dict(answer=answer), 986120))
    reopened = GameService(ledger)
    observed = reopened.inspect(PLAYER, action)
    assert observed["state"] == "complete" and observed["receipt"] == receipt
    assert observed["result"]["tier"] == "mid" and observed["result"]["brain_answer"] == answer
    assert "brain_answer" not in reopened.inspect(ADMIN, action)["result"]
    after = state(game)
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["3"] == before.sheets["3"]
    assert after.janus_cores[-1].controller == original_core.controller
    assert after.battery_links[-1].connection == contact and game.dice.calls == 1
    tick(worker, gateway, 5)
    public = str(gateway.messages)
    assert question not in public and answer not in public and account not in public
