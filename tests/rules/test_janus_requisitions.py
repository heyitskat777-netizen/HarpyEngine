"""Expected source-priced JANUS Requisition consumers, using real owned workflows."""

from uuid import uuid4

from test_enforcer_requisitions import approved
from test_janus_core_service import admitted
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.engine.m3_janus_requisitions import TRAINING
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_janus_requisitions import JanusRequisitionService
from girlframe.services.m3_role_punishments import RolePunishmentService


def training(store, tmp_path, monkeypatch, rule=TRAINING):
    _, game, _, core = admitted(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, rule))
    with store.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", actual)
    service = JanusRequisitionService(game)
    data = service.menu(PLAYER)
    service.buy_rule(
        PLAYER,
        "actual-owned-training",
        data["source_sha256"],
        rule,
        "Actual source-authorized Core Obedience Training",
    )
    return service, game, core


def test_actual_paid_training_removes_control_tag_and_applies_real_nonlethal_punishment(
    ledger, tmp_path, monkeypatch
):
    service, game, core = training(ledger, tmp_path, monkeypatch)
    assert state(game).sheets["2"].permissions == 0
    data = service.tags(PLAYER)
    assert data["trained"]
    tag = next(x["id"] for x in data["tags"] if x["label"] == "Drugged")
    result = service.remove_tag(
        PLAYER,
        str(uuid4()),
        data["revision"],
        tag,
        "Actual authorized removal of the Core's sedative treatment",
    )
    assert result["punishment"] is None
    heat = state(game).janus_cores[-1].heat
    result = service.start_training(
        PLAYER, str(uuid4()), state(game).revision, "Actual nonlethal Core Training scene"
    )
    owned = RolePunishmentService(game)
    case = result["id"]

    def change(viewer, **kwargs):
        data = owned.get(viewer, case)
        return owned.change(viewer, str(uuid4()), case, data["revision"], **kwargs)

    details = Details(kind="stimulant_injection")
    change(
        PLAYER, instruction=Instruction(kind=details.kind, details_json=details.model_dump_json())
    )
    change(PLAYER, scene="Actual Pilot applies the instructed nonlethal treatment to the Core")
    change(OTHER, attest=True)
    change(
        PLAYER, execute=True, account="Actual source-controlled Stimulant Injection administered"
    )
    assert state(game).janus_cores[-1].heat == heat + 7
    assert state(game).role_punishments[-1].completion_event is not None
    # Core basic functioning after actual printed restraint removal uses her own mind,
    # not her human controller's unrelated Girl sheet.
    from test_janus_core_service import cast_core
    from test_m2_game import Gateway, answer, pass_tags, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.services.m3_actor_plays import ActorPlayService

    data = service.tags(PLAYER)
    tag = next(x["id"] for x in data["tags"] if x["label"] == "Restrained")
    service.remove_tag(
        PLAYER, str(uuid4()), data["revision"], tag, "Actually remove the Core restraints"
    )
    cast_core(service, game, core)
    actual = ActorPlayService(game)
    info = actual.preview(OTHER, 900, core)
    other_before = state(game).sheets["3"].model_dump_json()
    action = actual.begin(
        OTHER,
        str(uuid4()),
        900,
        core,
        info["actor"]["source_sha256"],
        None,
        info["cast_revision"],
        PlayInput(
            play="keep_your_head",
            heat=state(game).janus_cores[-1].heat,
            context="Actual Core keeps her own head under pressure",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", text="Actual Core's own composed mental state")
    answer(
        game, ADMIN, "handler_keep", flag=True, text="Actual source adjudication of her response"
    )
    assert game.inspect(OTHER, action)["state"] == "complete"
    assert state(game).sheets["3"].model_dump_json() == other_before


def test_actual_universal_plug_uses_other_original_body_and_earns_optional_tag(
    ledger, tmp_path, monkeypatch
):
    from test_janus_battery import start
    from test_janus_core_service import cast_core
    from test_ledger import ADMIN
    from test_m2_game import Gateway, answer, pass_tags, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_janus_requisitions import UNIVERSAL
    from girlframe.services.m3_frame_control import FrameControlService

    service, game, core = training(ledger, tmp_path, monkeypatch, rule=UNIVERSAL)
    target = current_ref(state(game), 3)
    cast_core(service, game, core)
    contact = FrameControlService(game)
    identity = contact.propose(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 2),
        target,
        "My actual neural jack connects to the other original Girl's spinal port",
    )["id"]
    contact.decide(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "My actual original body accepts this spinal contact",
    )
    contact.decide(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The actual spinal connection and source reach are established",
    )
    game.dice.faces = (4, 5)
    action = start(game, target)
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "janus_select",
        options=("heat", "cognition"),
        number=2,
        fields={"tag": "Actual Universal Plug Tag"},
    )
    actual = state(game)
    assert actual.sheets["3"].tags[-1].label == "Actual Universal Plug Tag"
    assert actual.sheets["3"].tags[-1].giver_actor == current_ref(actual, 2)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert len(actual.janus_cores[-1].tags) == 4


def test_actual_pandora_off_duty_birth_creates_handler_authored_obedient_child(
    ledger, tmp_path, monkeypatch
):
    from test_ledger import ADMIN
    from test_m2_game import Gateway, answer, pass_tags, tick
    from test_off_duty_cycle import activate, prepared

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actors import owned_refs
    from girlframe.engine.m3_janus_pandora import ChildProposal, pregnancies
    from girlframe.engine.m3_janus_requisitions import PANDORA
    from girlframe.services.m3_actors import profiles

    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(PANDORA,))
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_pandora_funds", current)
    service = JanusRequisitionService(game)
    data = service.menu(PLAYER)
    service.buy_rule(
        PLAYER,
        str(uuid4()),
        data["source_sha256"],
        PANDORA,
        "Actual PANDORA implanted womb acquisition",
    )
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService

    cycle = CycleService(OffDutyService(MissionService(ledger)))
    activate(cycle, game, period)
    assert pregnancies(state(game))[-1].phase == "inseminated"
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="pandora_birth",
            heat=0,
            trigger_confirmed=True,
            context="Birth the actual child from this original Inseminated Frame",
        ),
    )["action_id"]
    tick(GameWorker(game), Gateway(), 3)
    if game.inspect(PLAYER, action)["state"] != "tag_window":
        game.roll(PLAYER, str(uuid4()), action)
    pass_tags(game)
    proposal = ChildProposal(
        name="Actual source newborn",
        gorgon_type="growth",
        gorgon_class="benevolent",
        assets=("Overgrown Musculature", "Infectious Flagella"),
        descriptions=("Actual newborn muscle", "Actual newborn flagella"),
        core_assets=(0,),
        weakness="Actual Handler-written vulnerable Core",
        account="Handler writes actual obedient vicious child",
    )
    answer(game, ADMIN, "janus_pandora_child", fields={"child": proposal.model_dump_json()})
    actual = state(game)
    child = pregnancies(actual)[-1].child
    assert child is not None and child.kind == "gorgon"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    body = next(x for x in actual.world.gorgons if x.id == child.entity)
    assert len(body.assets) == 2 and body.gorgon_class == "benevolent"
    with ledger.engine.connect() as c:
        assert child in owned_refs(actual, 2, profiles(c, ledger.campaign_id))


def test_actual_pet_qualifying_battery_next_off_duty_carry_and_return(
    ledger, tmp_path, monkeypatch
):
    from test_janus_core import facts
    from test_janus_core_service import cast_core, change
    from test_ledger import ADMIN
    from test_m2_game import Gateway, answer, pass_tags, tick
    from test_off_duty_cycle import activate, prepared

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_janus import has_tag, ref
    from girlframe.engine.m3_janus_requisitions import PET
    from girlframe.services.m3_frame_control import FrameControlService
    from girlframe.services.m3_janus import JanusService
    from girlframe.services.m3_janus_pet import PetService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService
    from girlframe.services.m3_off_duty_cycle import CycleService

    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, PET))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    setup = JanusService(game)
    request = setup.request(PLAYER, str(uuid4()), 3)["id"]
    change(setup, OTHER, request, facts=facts())
    change(setup, ADMIN, request, approve=True, account="Actual source original Core facts")
    core = ref(state(game).janus_cores[-1])
    cast_core(setup, game, core)
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_pet_funds", actual)
    source = JanusRequisitionService(game)
    data = source.menu(PLAYER)
    source.buy_rule(
        PLAYER, str(uuid4()), data["source_sha256"], PET, "Actual acquired Pet entitlement"
    )
    contacts = FrameControlService(game)
    wire = contacts.propose(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 2),
        core,
        "Actual jack reaches and connects to own original Core",
    )["id"]
    contacts.decide(
        ADMIN,
        str(uuid4()),
        wire,
        state(game).revision,
        True,
        "Actual reviewed neural contact through original spinal port",
    )
    game.dice.faces = (2, 2)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="living_battery",
            heat=0,
            target_actor=core,
            trigger_confirmed=True,
            context="Actual qualifying link before the next OffDuty",
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["state"] == "awaiting_choices"
    answer(game, PLAYER, "janus_select", options=("heat", "cognition"), number=1)
    tick(worker, gateway, 5)
    contacts.unplug(
        PLAYER, str(uuid4()), wire, state(game).revision, "Actually unplug before carrying her"
    )
    cycle = CycleService(OffDutyService(MissionService(ledger)))
    activate(cycle, game, period)
    service = PetService(game)
    with ledger.engine.connect() as c:
        task = service._tasks(c, PLAYER)[0]
    before = state(game).janus_cores[-1]
    service.decide(
        PLAYER,
        str(uuid4()),
        task["id"],
        state(game).revision,
        True,
        "I take the actual original Core along with her real Leash and Collar",
    )
    carried = state(game).janus_cores[-1]
    assert not carried.attached and not carried.linked and len(carried.tags) == len(before.tags)
    assert any(x.get("kind") == "janus_pet_leash_and_collar" for x in state(game).facts)
    service.return_core(
        PLAYER,
        str(uuid4()),
        task["id"],
        state(game).revision,
        "I return the same actual body to the original Frame for Foundation care",
    )
    returned = state(game).janus_cores[-1]
    assert returned.attached and returned.linked and has_tag(returned, "drugged")
    assert returned.control_tags and set(returned.control_tags.values()).isdisjoint(
        before.baseline_tags.values()
    )
    assert service.get(PLAYER, task["id"])["outing"]["phase"] == "returned"
