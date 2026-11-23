"""An actual Psychologist's directive gives one original Girl a real owned Identity."""

import asyncio

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_world_service import ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_cast import open_cast
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_journalist import PSYCHOLOGIST, questions
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_journalist import JournalistService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("capacity", [True, False])
def test_native_psychologist_grants_an_actual_identity_and_respects_owned_slots(
    ledger, tmp_path, monkeypatch, capacity
):
    world, game = ready(ledger)
    npc = ActorRef(kind="npc", entity="original-psychologist")
    world.npc(
        ADMIN,
        "psychologist",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Original psychologist",
            detail="An actual clinician.",
            jobs=("psychologist",),
            cell=(0, 0),
            controller=1,
        ),
    )
    change(CastService(ActorService(world.missions)), ADMIN, "join", npc)
    with ledger.transaction() as c:
        canon = state(game)
        sheet = canon.sheets["2"]
        protected = sheet.identities[0]
        protected.marked = True
        sheet.sedation_locked = (protected.id,)
        if not capacity:
            sheet.identities.pop()
        game.event(c, 1, "original-slots", "synthetic.identity_slots", canon)
    service = JournalistService(game)
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        service.targets(ADMIN, 900, npc, job="psychologist")
    approved(ledger, game, tmp_path, monkeypatch, extra=(PSYCHOLOGIST,))
    cast = CastService(ActorService(MissionService(ledger)))
    label, directive = "Patient", "Record the results before you leave."
    baseline = state(game).sheets["2"]

    async def ask():
        click = current(ADMIN.user_id, 89960)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_cast(click, cast)
        menu = click.edit_original_response.call_args.kwargs["view"]
        token = next(x for x, _ in menu.options if x.startswith("psychologist:"))
        edit = current(ADMIN.user_id, 89961)
        await edit.response.defer(ephemeral=True)
        await menu.open_item(edit, token)
        form = edit.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        form.values.update(girl=("2",), question=directive, identity=label)
        confirm = current(ADMIN.user_id, 89962)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    asyncio.run(ask())
    (request,) = questions(state(game))
    work, revision = request.id, state(game).revision
    assert state(game).sheets["2"] == baseline
    visible = service.view(PLAYER, work)
    assert visible["identity_label"] == label and visible["needs_replacement"] is capacity
    assert service.view(ADMIN, work)["replacements"] == ()
    assert protected.id not in dict(visible["replacements"])
    assert not any(x.identity == work for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError, match="actual addressed Girl"):
        service.respond(ADMIN, "forged-choice", work, revision, "answer", "")
    with pytest.raises(WorkflowError, match="own Identity slot"):
        service.respond(PLAYER, "forged-slot", work, revision, "answer", "", replace=protected.id)
    with pytest.raises(WorkflowError, match="pending for human review"):
        service.respond(PLAYER, "hold-review", work, revision, "decline", "")
    replacement = visible["replacements"][0][0] if capacity else None

    async def receive():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(PLAYER) if x.identity == work)
        assert "Psychologist" in item.title
        click = current(PLAYER.user_id, 89963)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, PLAYER.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and label in form.instructions
        form.values["response"] = ("answer",)
        if replacement is not None:
            form.values["replace"] = (replacement,)
        confirm = current(PLAYER.user_id, 89964)
        await form.confirm.callback(confirm)
        assert form.completed, confirm.edit_original_response.call_args

    asyncio.run(receive())
    assert (
        service.respond(PLAYER, "89964", work, revision, "answer", "", replace=replacement)[
            "response"
        ]
        == "answer"
    )
    ledger.engine.dispose()
    after = state(game).sheets["2"]
    added = next(x for x in after.identities if x.id == work + ":identity")
    assert added.name == label and len(after.identities) == 4
    assert protected in after.identities and after.sedation_locked == (protected.id,)
    assert {x.id for x in after.identities} == (
        {x.id for x in baseline.identities} - {replacement}
    ) | {added.id}
    assert after.tags == baseline.tags and after.heat == baseline.heat and game.dice.calls == 0
