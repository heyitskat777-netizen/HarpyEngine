"""Approved optional character creation with an original, private human choice."""

import asyncio

import pytest
from test_battle_service import prepared
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_ancillary import open_offer
from girlframe.engine import m3_ancillary as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

REBEL = ActorRef(kind="npc", entity="rebel-handler")
PATRON = ActorRef(kind="npc", entity="foundation-patron")
HARPY = ActorRef(kind="external_pilot", entity="captive-harpy")


def scenario(ledger):
    game, *_ = prepared(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "playbooks", "plays"})
            )
        )
    )
    with ledger.transaction() as connection:
        canon = state(game)
        canon.world = update(
            canon.world,
            factions=(Faction(id="group", name="Synthetic group", kind="rebel", cells=((0, 4),)),),
            npcs=(
                Npc(
                    id=REBEL.entity,
                    name="Disclosed Rebel contact",
                    cell=(0, 4),
                    jobs=("handler",),
                    detail="Synthetic role sponsor",
                    controller=1,
                    faction="group",
                ),
                Npc(
                    id=PATRON.entity,
                    name="Disclosed Patron",
                    cell=(0, 0),
                    jobs=("patron",),
                    detail="Synthetic role Patron",
                    controller=1,
                ),
            ),
            pilots=(
                AdversaryPilot(
                    id=HARPY.entity,
                    name="Disclosed captive",
                    cell=(0, 4),
                    kind="harpy",
                    girl="HARPY",
                    frame="HARPY",
                    controller=1,
                    faction="group",
                    custody="captured",
                    custodian=1,
                    custody_event="synthetic-harpy-custody",
                    assets=(
                        Asset(
                            id="harpy-resource",
                            name="Unrelated gear",
                            family="girl",
                            description="Owned gear",
                        ),
                    ),
                ),
            ),
        )
        game.event(connection, 1, "synthetic-ancillary-world", "synthetic.ancillary_world", canon)
    return game


def enable(ledger, game, tmp_path, monkeypatch):
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(rules.RULE, *(x.rule for x in rules.STARTERS.values())),
    )
    registry = load_registry().model_copy(
        update=dict(enabled_modules=frozenset({"core", "ancillary"}))
    )
    path = tmp_path / "approved-synthetic-ancillary.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(m3_approval=approval.model_copy(update=dict(registry_sha256=digest(registry))))
    )


@pytest.mark.parametrize("enable_module", [False, True])
def test_default_policy_blocks_ancillary_character_creation(
    ledger, tmp_path, monkeypatch, enable_module
):
    game = scenario(ledger)
    if enable_module:
        registry = load_registry().model_copy(
            update=dict(enabled_modules=frozenset({"core", "ancillary"}))
        )
        path = tmp_path / "synthetic-unreviewed-ancillary.json"
        path.write_text(registry.model_dump_json())
        monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
        approval = ledger.policy.m3_approval
        ledger.policy = ledger.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(update=dict(registry_sha256=digest(registry)))
            )
        )
    service = AncillaryService(MissionService(ledger))
    assert service.invite_options(ADMIN) is None
    with pytest.raises(
        WorkflowError, match="UNSUPPORTED_RULE" if enable_module else "MODULE_DISABLED"
    ):
        service.invite(ADMIN, "disabled", state(game).revision, PLAYER.user_id, "base0")
    assert not rules.records(state(game)) and not rules.offers(state(game))


@pytest.mark.parametrize("book", tuple(rules.STARTERS))
def test_approved_ancillary_books_create_independent_actual_roles(
    ledger, tmp_path, monkeypatch, book
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch)
    before = state(game)
    missions = MissionService(ledger)
    service = AncillaryService(missions)
    template = rules.STARTERS[book]
    site, faction = ("base0", None) if template.affiliation == "foundation" else ("city0", "group")
    contacts = (REBEL, HARPY) if faction else (PATRON,)
    with pytest.raises(WorkflowError):
        service.invite(OTHER, "wrong-sponsor", before.revision, 2, site, faction, contacts)
    if book == "SOLDIER":

        async def sponsor():
            click = current(1, 51105)
            await click.response.defer(ephemeral=True)
            options = service.invite_options(ADMIN)
            await open_offer(click, service, options)
            form = click.edit_original_response.call_args.kwargs["view"]
            selecting = str(
                next(i for i, row in enumerate(options["sites"]) if row[:2] == (site, faction))
            )
            form.values.update(controller=("2",), site=(selecting,), contacts=(PATRON.token,))
            await form.confirm.callback(current(1, 51106))
            assert form.completed

        asyncio.run(sponsor())
        (invitation,) = rules.offers(state(game))
        identity = invitation.id
    else:
        identity = service.invite(
            ADMIN, "original-sponsor", before.revision, 2, site, faction, contacts
        )["id"]
    revision = state(game).revision
    inbox = InboxService(ledger)
    assert any(x.identity == identity for x in inbox.items(PLAYER))
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    if book in ("SOLDIER", "MERCENARY", "PRODIGY"):
        bond = current_ref(before, 3)
    elif book in ("REVOLUTIONARY IDEALIST", "ANGEL-WIFE"):
        bond = REBEL
    elif book == "ABYSSAL ACOLYTE":
        bond = HARPY
    else:
        bond = None
    frame_source = "SOLDIER_3" if book == "SOLDIER" else "JANUS"
    frames = rules.frame_assets(book, frame_source)[:2]
    girls = template.assets[:2]
    descriptions = ("First owned Asset", "Second owned Asset")
    draft = rules.Draft(
        name="Synthetic auxiliary actor",
        book=book,
        bond=bond,
        patron=PATRON if book == "MERCENARY" else None,
        wanted=current_ref(before, 3) if book == "WARBOY" else None,
        frame_catalogue=frame_source,
        girl_assets=tuple(
            rules.NamedAsset(name=x, description=y)
            for x, y in zip(girls, descriptions, strict=True)
        ),
        frame_assets=tuple(
            rules.NamedAsset(name=x, description=y)
            for x, y in zip(frames, descriptions, strict=True)
        ),
    )
    with pytest.raises(WorkflowError, match="invited controller"):
        service.respond(OTHER, "wrong-controller", identity, revision, draft)
    with pytest.raises(WorkflowError, match="STALE_ANCILLARY"):
        service.respond(PLAYER, "stale", identity, revision - 1, draft)
    ledger.safety(PLAYER, "paused-creating", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(PLAYER, "pause", identity, revision, draft)
    ledger.safety(PLAYER, "resume-creating", ledger.status(PLAYER)["revision"], pause=False)
    ledger.engine.dispose()
    if book == "SOLDIER":

        async def through_native_inbox():
            click = current(2, 51100)
            await click.response.defer(ephemeral=True)
            item = next(x for x in inbox.items(PLAYER) if x.identity == identity)
            await InboxView(inbox, 2).route(click, item)
            first = click.edit_original_response.call_args.kwargs["view"]
            first.values.update(book=(book,))
            start = current(2, 51101)
            await start.response.defer(ephemeral=True)
            await first.confirm.callback(start)
            second = start.edit_original_response.call_args.kwargs["view"]
            second.values.update(catalogue=(frame_source,), girl_assets=girls)
            choose = current(2, 51102)
            await choose.response.defer(ephemeral=True)
            await second.confirm.callback(choose)
            final = choose.edit_original_response.call_args.kwargs["view"]
            final.values.update(
                name=draft.name,
                frame_assets=frames,
                girl_1=descriptions[0],
                girl_2=descriptions[1],
                frame_1=descriptions[0],
                frame_2=descriptions[1],
                bond=(bond.token,),
            )
            await final.confirm.callback(current(2, 51103))
            assert final.completed

        asyncio.run(through_native_inbox())
    receipt = service.respond(PLAYER, "51103", identity, revision, draft)
    assert receipt == service.respond(PLAYER, "51103", identity, revision, draft)
    ref = ActorRef.model_validate(receipt["actor"])
    after = state(game)
    (made,) = rules.records(after)
    assert made.actor == ref and made.controller == PLAYER.user_id
    assert tuple(x.name for x in made.identities) == template.identities and made.heat == 0
    assert before.sheets == after.sheets
    assert not hasattr(made, "permissions")
    if bond:
        assert depth(after, ref, bond) == 1
    if draft.patron:
        assert depth(after, ref, draft.patron) == 1
    assert not any(x.identity == identity for x in inbox.items(PLAYER))
    actor_service = ActorService(missions)
    actual = actor_service.inspect(PLAYER, ref)["actor"]
    assert actual["rules"] == "ancillary" and actual["frame"] is None
    assert {x["name"] for x in actual["assets"]} == set((*girls, *frames))
    with pytest.raises(WorkflowError):
        actor_service.inspect(OTHER, ref)
    cast = CastService(actor_service)
    change(cast, PLAYER, "join", ref)
    assert any(x["ref"] == receipt["actor"] for x in cast.view(PLAYER, 900)["roles"])
