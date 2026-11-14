"""Real Stim cocktails, actual human choices, temporary Tags and low Punishment."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_dose_up as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_dose_up import DoseUpService, prove
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    _, game = service(store, girl="STIM-BLISSED", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE, rules.SELF_RULE))
    with store.transaction() as c:
        original = state(game)
        original.world = initial()
        original = place(original, 2, mode="outside_frame")
        original = place(original, 3, mode="outside_frame")
        original.sheets["2"].heat = 3
        original.sheets["2"].tags.append(
            TagState(id="unrelated", label="Existing private Tag", giver=3, observers=(2,))
        )
        game.event(c, 1, str(uuid4()), "synthetic.prior_physical_dosing_context", original)
    return game, GameWorker(game), Gateway(), DoseUpService(store, game)


def dose(game, worker, gateway, *, faces, heat=0, source=None, order=None):
    game.dice.faces = faces
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="dose_up",
            heat=heat,
            target_actor=current_ref(before, 3) if source else None,
            source_work=source,
            order_id=order,
            context="I actually inject the prepared combat cocktail",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    tick(worker, gateway, 3)
    pass_tags(game)
    return action


def native_choice(game, viewer, components):
    from girlframe.discord_adapter.m3_dose_up import open_choice

    row = next(x for x in game.choices(viewer) if x["kind"].startswith("dose_up_"))
    decision = game.decision(viewer, row["id"])

    async def choose():
        interaction = current(viewer.user_id, int(uuid4().int % 1000000000))
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, decision)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["components"] = components
        response = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(choose())


def contact(service, game, *, native=False):
    if native:
        from girlframe.discord_adapter.m3_dose_up import open_dose_up

        async def source():
            interaction = current(2, 98701)
            interaction.channel_id = 900
            await interaction.response.defer(ephemeral=True)
            await open_dose_up(interaction, service)
            menu = interaction.edit_original_response.call_args.kwargs["view"]
            menu.values["action"] = ("contact",)
            opened = current(2, 98702)
            await menu.confirm.callback(opened)
            form = opened.edit_original_response.call_args.kwargs["view"]
            form.values.update(
                target=(current_ref(state(game), 3).token,),
                account="My hand actually reaches her exposed vein in this scene",
            )
            await form.confirm.callback(current(2, 98703))
            assert form.completed and game.dice.calls == 0

        asyncio.run(source())
        return rules.records(state(game), rules.Contact)[-1].id
    return service.record_contact(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "My hand actually reaches her exposed vein in this scene",
    )["id"]


def test_ordered_mid_actual_self_drug_mark_repeated_response_two_real_scenes_and_private_history(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    original = state(game)
    issued = game.issue_order(ADMIN, str(uuid4()), 900, 2, "Dose yourself now", dose_up=True)
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    tick(worker, gateway, 5)
    action = dose(game, worker, gateway, faces=(3, 4), heat=1, order=issued["order_id"])
    assert not any(x["kind"] == "dose_up_components" for x in game.choices(PLAYER))
    native_choice(game, ADMIN, ("quick", "strong"))
    actual = state(game)
    value = rules.records(actual, rules.Dose)[-1]
    assert value.total == 8 and value.heat == 1 and value.order == issued["order_id"]
    assert [x.role for x in value.selections] == ["issuer"]
    assert actual.sheets["2"].heat == original.sheets["2"].heat - 1
    assert actual.sheets["3"] == original.sheets["3"]
    assert actual.sheets["2"].identities == original.sheets["2"].identities
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert len(rules.drug_tags(actual, current_ref(actual, 2))) == 2
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, action) == value
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError):
        dose(game, worker, gateway, faces=(3, 4), order=issued["order_id"])
    tag = next(x for x in actual.sheets["2"].tags if x.id.endswith(":quick"))
    for scene_number in (1, 2):
        before = state(game)
        keep = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            before.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="The heightened reactions help my real evasion",
                trigger_confirmed=True,
            ),
        )["action_id"]
        game.dice.faces = (3, 4)
        tick(worker, gateway, 3)
        answer(
            game,
            PLAYER,
            "tag_window",
            options=("tag",),
            denied=(tag.id,),
            number=1,
            text="The actual Upper:Quick cocktail heightens my reactions",
        )
        answer(game, OTHER, "tag_window", options=("pass",))
        answer(game, ADMIN, "tag_window", options=("pass",))
        if scene_number == 2:
            answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=("identity:0",))
        answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual evasion adjudication")
        assert game.inspect(PLAYER, keep)["state"] == "complete"
        tick(worker, gateway, 5)
        game.close_scene(ADMIN, str(uuid4()), 900)
        assert (
            len([x for x in rules.records(state(game), rules.SceneEnd) if x.dose == action])
            == scene_number
        )
        if scene_number == 1:
            assert not rules.expired(state(game), action)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (PLAYER, OTHER, ADMIN):
                game.join_scene(human, str(uuid4()), 900)
    final = state(game)
    assert rules.expired(final, action)
    assert not any(x.id.startswith("dose-up:") for x in final.sheets["2"].tags)
    assert any(x.id == "unrelated" for x in final.sheets["2"].tags)
    assert any(x.name == rules.LABELS["quick"] for x in final.sheets["2"].identities)
    assert controls.view(PLAYER, action)["phase"] == "expired"
    assert (
        next(
            x
            for x in InboxService(ledger).items(PLAYER)
            if x.identity == action and x.task == "m3_dose_up"
        ).state
        == "established"
    )
    assert not any(
        x.identity == action and x.task == "m3_dose_up" for x in InboxService(ledger).items(OTHER)
    )

    async def reopen():
        from girlframe.discord_adapter.inbox import InboxView

        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(PLAYER) if x.identity == action and x.task == "m3_dose_up"
        )
        interaction = current(2, 98710)
        interaction.channel_id = 901
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(interaction, item)
        content = interaction.edit_original_response.call_args.kwargs["content"]
        assert "expired" in content and "Upper:Quick" in content

    asyncio.run(reopen())
    assert game.dice.calls == 3


def test_high_actual_other_contact_three_distinct_owned_tags_and_replay(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    source = contact(controls, game, native=True)
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.record_contact(
            OTHER,
            str(uuid4()),
            900,
            current_ref(before, 2),
            before.revision,
            "Cannot alias another Girl's source",
        )
    action = dose(game, worker, gateway, faces=(6, 6), source=source)
    native_choice(game, PLAYER, ("calm", "bliss"))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "dose_up_components")
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("sense",))
        )
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("calm",))
        )
    assert state(game).model_dump_json() == snapshot
    key = str(uuid4())
    reply = game.respond(ADMIN, key, row["id"], row["revision"], ChoiceAnswer(options=("sense",)))
    assert (
        game.respond(ADMIN, key, row["id"], row["revision"], ChoiceAnswer(options=("sense",)))
        == reply
    )
    final = state(game)
    value = rules.records(final, rules.Dose)[-1]
    assert [x.chooser for x in value.selections] == [2, 1]
    assert {x.label for x in final.sheets["3"].tags} >= {
        rules.LABELS[x] for x in ("calm", "bliss", "sense")
    }
    assert final.sheets["2"].model_dump(exclude={"revision"}) == before.sheets["2"].model_dump(
        exclude={"revision"}
    )
    assert all(
        x.giver_actor == current_ref(final, 2) and x.observers == (1, 2, 3)
        for x in final.sheets["3"].tags
    )
    assert controls.view(OTHER, action)["components"] == [
        rules.LABELS[x] for x in ("calm", "bliss", "sense")
    ]
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_self_handler_one_component_actual_tags_and_two_scene_expiry(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    action = dose(game, worker, gateway, faces=(1, 1), heat=1)
    receipt = game.inspect(PLAYER, action)["receipt"]
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "dose_up_components")
    detail = game.decision(ADMIN, row["id"])["detail"]
    assert detail["role"] == "handler" and (detail["minimum"], detail["maximum"]) == (1, 2)
    assert not any(x["kind"].startswith("dose_up_") for x in game.choices(PLAYER))
    snapshot = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(options=("calm",))
        )
    assert state(game).model_dump_json() == snapshot
    native_choice(game, ADMIN, ("calm",))
    actual = state(game)
    value = next(x for x in rules.records(actual, rules.Dose) if x.id == action)
    assert value.actor == value.target == current_ref(actual, 2)
    assert value.total == 3 and value.heat == 1
    assert [(x.role, x.chooser, x.components) for x in value.selections] == [
        ("handler", 1, ("calm",))
    ]
    assert value.recipient_choice is None and value.punishment is None
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["3"] == before.sheets["3"]
    drugs = [x for x in rules.drug_tags(actual, value.target) if x.dose == action]
    assert len(drugs) == 1
    drug = drugs[0]
    assert drug.component == "calm" and drug.event == value.event
    assert any(x.id == drug.id and x.label == rules.LABELS["calm"] for x in actual.sheets["2"].tags)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, action) == value
    tick(worker, gateway, 5)
    for scene_number in (1, 2):
        game.close_scene(ADMIN, str(uuid4()), 900)
        ends = [x for x in rules.records(state(game), rules.SceneEnd) if x.dose == action]
        assert len(ends) == scene_number
        assert rules.expired(state(game), action) == (scene_number == 2)
        if scene_number == 1:
            assert any(x.id == drug.id for x in state(game).sheets["2"].tags)
            game.bind_scene(ADMIN, str(uuid4()), 900)
            for human in (PLAYER, OTHER, ADMIN):
                game.join_scene(human, str(uuid4()), 900)
    final = state(game)
    assert not any(x.id == drug.id for x in final.sheets["2"].tags)
    assert any(x.id == "unrelated" for x in final.sheets["2"].tags)
    assert next(x for x in rules.records(final, rules.Dose) if x.id == action) == value
    assert controls.view(PLAYER, action)["phase"] == "expired"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1


def test_low_other_real_recipient_dose_then_handler_components(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = dose(game, worker, gateway, faces=(1, 1), source=contact(controls, game))
    native_choice(game, OTHER, ("dose",))
    native_choice(game, ADMIN, ("talk", "sense"))
    assert {x.component for x in rules.records(state(game), rules.DrugTag)} == {"talk", "sense"}
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_low_other_real_punishment_instead_no_drugs_and_actual_parent_chat_closure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action = dose(game, worker, gateway, faces=(1, 1), source=contact(controls, game))
    native_choice(game, OTHER, ("punish",))
    source = state(game)
    case = source.role_punishments[-1]
    assert case.source_kind == "dose_up" and case.executor == current_ref(source, 3)
    assert case.subject == current_ref(source, 2) and not rules.records(source, rules.DrugTag)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    role = RolePunishmentService(game)

    def change(viewer, **values):
        return role.change(
            viewer, str(uuid4()), case.id, role.get(viewer, case.id)["revision"], **values
        )

    details = Details(kind="stimulant_injection")
    change(
        OTHER, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(OTHER, scene="The original recipient actually administers her chosen injection")
    change(PLAYER, attest=True)
    change(
        OTHER,
        execute=True,
        account="I administer the actual stimulant Punishment instead of the cocktail",
    )
    final = state(game)
    completed = next(x for x in final.role_punishments if x.id == case.id)
    assert completed.effect_event and completed.completion_event
    assert final.sheets["2"].heat == source.sheets["2"].heat + 7
    assert not rules.records(final, rules.DrugTag)
    assert controls.view(PLAYER, action)["punishment"] == case.id
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
