"""Activity inputs for learned abilities proved by the native source."""

import json
from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
from off_duty_followups import OffDutyFollowups
from specialist_scene import SpecialistScene
from test_disposable_psyche import real_period
from test_enforcer_requisitions import approved
from test_identity_specialists import option, popup, press, respond, scoped, suggestions
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_mockingbird_risk import begin as risk_ready
from test_scene_beneath_followups import adapter, submit
from test_show_dog_activity import card as appearance_card
from test_show_dog_activity import select as appearance_value
from test_show_dog_activity import submit as appearance_payload
from test_vatgrown_plays import _learn_daily_source, ready

from girlframe.engine import m3_am_code, m3_casualty, m3_dose_up, m3_malleable
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_learned_play_state import active_hound_status
from girlframe.engine.m3_mockingbird import CALL, give_tag
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_am_code import CodeService
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_casualty import CasualtyService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_learned_plays import (
    BEAUTIFUL,
    ELDER,
    HOUND,
    ITCHING,
    PSYCHE,
    SHOW_DOG,
    keep_rider_rule,
)
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def projection(scene, viewer, play):
    game = scene.game
    sheet = game.sheet(viewer)
    if play == "keep_your_head":
        return scene.view(viewer, sheet, False)
    native = game.scene_info(viewer, 900)
    locked = bool(native["lock"] and native["lock"]["state"] != "released")
    off_duty = scene.off_duty_status(viewer) if play in ("go_off_duty", "void_observation") else {}
    return scene.play_options(viewer, native, sheet, state(game), locked, False, off_duty)[play]


def give_original_tag(game, label):
    source = str(uuid4())
    identity = str(uuid4())
    actual = state(game)
    with game.store.transaction() as c:
        changed = give_tag(
            actual,
            profiles(c, game.store.campaign_id),
            current_ref(actual, 2),
            current_ref(actual, 3),
            label,
            identity,
            source,
            (2, 3),
        )
        game.event(
            c,
            OTHER.user_id,
            str(uuid4()),
            "synthetic.original_owned_tag",
            changed,
            event_id=source,
        )
    return identity


def projected_choice(scene, viewer, play, kind):
    return next(row for row in projection(scene, viewer, play)["choices"] if row["kind"] == kind)


@pytest.mark.parametrize(
    ("teacher", "play", "rule", "trait"),
    [
        ("PRINCESS", "keep_your_head", BEAUTIFUL, "sexy"),
        ("PRINCESS", "flirt", BEAUTIFUL, None),
        ("ALPHA", "keep_your_head", ITCHING, "vicious"),
        ("OLDGEN", "keep_your_head", ELDER, "experienced"),
    ],
)
def test_owned_keep_and_flirt_lessons_are_selectable_and_spent_once(
    ledger,
    tmp_path,
    monkeypatch,
    teacher,
    play,
    rule,
    trait,
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher=teacher)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, rule),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    tag = give_original_tag(game, "Actual learned composure") if play == "flirt" else None
    scene = adapter(game)
    view = projection(scene, PLAYER, play)
    private = "learned_keep_rider"
    assert lesson.id in dict(view["lessons"][private])
    assert not projection(scene, OTHER, play).get("lessons")
    payload = {
        "context": "The original owner uses the earned lesson.",
        "confirmed": True,
        "character_revision": view["character_revision"],
        "heat": view["lesson_heat"][0],
        private: lesson.id,
    }

    def start(viewer, key, data):
        if play == "keep_your_head":
            return scene.perform(viewer, key, "keep-start", data)
        target = OTHER if viewer == PLAYER else PLAYER
        return scene.perform_scene(
            viewer,
            key,
            "scene-start",
            data | {"play": play, "target": str(target.user_id)},
        )

    with pytest.raises(WorkflowError):
        start(
            OTHER,
            "foreign-lesson",
            payload | {"character_revision": game.sheet(OTHER)["revision"]},
        )
    game.dice.faces = (4, 4)
    calls = game.dice.calls
    opened = start(PLAYER, "owned-one-use-lesson", payload)
    assert start(PLAYER, "owned-one-use-lesson", payload) == opened
    identity = opened["action_id"]
    tick(worker, gateway, 3)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    if tag:
        tag_window = projected_choice(adapter(fresh), PLAYER, play, "tag_window")
        assert fresh.decision(PLAYER, tag_window["id"])["learned_keep_rule"] == BEAUTIFUL
        fields = {row["key"]: row for row in tag_window["schema"]}
        assert tag in dict(fields["denied"]["options"])
        markers = fields.get("fields.marker")
        markers = {"marker": markers["options"][0][0]} if markers else {}
        proposal = {
            "options": ["tag"],
            "denied": [tag],
            "number": 1,
            "text": "Actual composure changes this encounter.",
            "fields": markers,
        }
        with pytest.raises(WorkflowError):
            submit(adapter(fresh), OTHER, tag_window, proposal)
        saved = submit(adapter(fresh), PLAYER, tag_window, proposal, key="own-actual-tag")
        assert submit(adapter(fresh), PLAYER, tag_window, proposal, key="own-actual-tag") == saved
        for viewer in (OTHER, ADMIN):
            answer(fresh, viewer, "tag_window", options=("pass",))
        assert next(row for row in state(fresh).sheets["2"].tags if row.id == tag).marked
    else:
        pass_tags(fresh)
    kind = "actor_keep" if play == "keep_your_head" else "actor_flirt"
    step = next(row for row in fresh.choices(PLAYER) if row["kind"] == kind)
    with ledger.engine.connect() as c:
        assert keep_rider_rule(fresh, c, state(fresh), fresh.action(c, identity)) == rule
    if play == "keep_your_head":
        assert fresh.decision(PLAYER, step["id"])["learned_keep_rule"] == rule
        card = projected_choice(adapter(fresh), PLAYER, play, kind)
        fields = {row["key"]: row for row in card["fields"]}
        negative = "sexy" if rule == ITCHING else "vicious"
        assert negative in dict(fields["denied"]["options"])
        response = {"options": ["tough", "desperate"], "denied": [negative]}
        if rule == ELDER:
            assert fields["flag"]["label"] == "Also choose experienced?"
            response["flag"] = True
        adapter(fresh).perform(
            PLAYER,
            "finish-earned-keep",
            "keep-choice",
            {
                **{name: card[name] for name in ("id", "role", "revision")},
                "answer": response,
            },
        )
        answer(
            fresh,
            ADMIN,
            "handler_keep",
            flag=True,
            text="The actual effort was enough.",
        )
        assert trait in fresh.inspect(PLAYER, identity)["result"]["positive"]
    else:
        answer(fresh, PLAYER, kind, options=("name",))
        answer(fresh, OTHER, "target_flirt", text="I offer my own answer.")
    assert fresh.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == calls + 1
    assert not projection(adapter(fresh), PLAYER, play).get("lessons")


def test_learned_psyche_lists_actual_removable_identities_and_costs(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, PSYCHE),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, PSYCHE)
    scene = adapter(game)
    data = projection(scene, PLAYER, "keep_your_head")
    assert lesson.id in dict(data["lessons"]["learned_psyche"])
    assert not projection(scene, OTHER, "keep_your_head").get("lessons")
    mark = next(row for row in data["lesson_marks"] if "1" in row["amounts"])
    heat = mark["amounts"]["1"]["3"][-1]
    payload = {
        "context": "I mark the actual chosen Identity to hold my nerve.",
        "confirmed": True,
        "character_revision": data["character_revision"],
        "learned_psyche": lesson.id,
        "identity": mark["id"],
        "gain": 1,
        "disposable_heat": 3,
        "heat": heat,
    }
    before = state(game).sheets["2"].heat
    calls = game.dice.calls
    game.dice.faces = (4, 4)
    opened = scene.perform(PLAYER, "remove-original-identity", "keep-start", payload)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert scene.perform(PLAYER, "remove-original-identity", "keep-start", payload) == opened
    saved = state(game).sheets["2"]
    assert mark["id"] not in {row.id for row in saved.identities}
    assert saved.heat == before + 1 + 3 - heat
    assert game.inspect(PLAYER, opened["action_id"])["receipt"] and game.dice.calls == calls + 1


def test_learned_call_uses_dive_and_actual_asset_choices(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="MOCKINGBIRD")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, CALL),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, CALL)
    scene = adapter(game)
    view = projection(scene, PLAYER, "dive_deep")
    assert lesson.id in dict(view["lessons"]["learned_call"])
    assert not projection(scene, OTHER, "dive_deep").get("lessons")
    payload = {
        "play": "dive_deep",
        "context": "I use my taught connection to reclassify actual equipment.",
        "confirmed": True,
        "character_revision": view["character_revision"],
        "target": None,
        "learned_call": lesson.id,
        "heat": 0,
    }
    with pytest.raises(WorkflowError):
        scene.perform_scene(
            OTHER,
            "borrowed-call",
            "scene-start",
            payload | {"character_revision": game.sheet(OTHER)["revision"]},
        )
    calls = game.dice.calls
    game.dice.faces = (4, 4)
    started = scene.perform_scene(PLAYER, "owned-learned-call", "scene-start", payload)
    assert scene.perform_scene(PLAYER, "owned-learned-call", "scene-start", payload) == started
    tick(worker, gateway, 3)
    pass_tags(game)
    identity = started["action_id"]
    original = game.inspect(PLAYER, identity)["receipt"]
    before = {row.id: row.family for row in state(game).sheets["2"].assets}
    option = projected_choice(scene, PLAYER, "dive_deep", "dive_select")
    assert "call_reclassify_assets" in dict(option["fields"][0]["options"])
    submit(
        scene,
        PLAYER,
        option,
        {
            "options": ["call_reclassify_assets"],
            "text": "I switch the family of these two original Assets.",
        },
    )
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    effect = projected_choice(adapter(fresh), PLAYER, "dive_deep", "dive_effect")
    eligible = dict(next(row for row in effect["fields"] if row["key"] == "options")["options"])
    girl = next(value for value in eligible if before[value] == "girl")
    frame = next(value for value in eligible if before[value] == "frame")
    with pytest.raises(WorkflowError):
        submit(adapter(fresh), OTHER, effect, {"options": [girl, frame]})
    submit(adapter(fresh), PLAYER, effect, {"options": [girl, frame]})
    saved = {row.id: row.family for row in state(fresh).sheets["2"].assets}
    assert saved == (before | {girl: "frame", frame: "girl"})
    assert fresh.inspect(PLAYER, identity)["receipt"] == original and game.dice.calls == calls + 1
    assert not projection(adapter(fresh), PLAYER, "dive_deep").get("lessons")


@pytest.mark.parametrize(
    "teacher,rule,field",
    [
        ("PRINCESS", SHOW_DOG, "learned_show_dog"),
        ("STIM-BLISSED", PSYCHE, "learned_psyche"),
    ],
)
def test_learned_off_duty_work_survives_reopening_for_its_owner(
    ledger,
    tmp_path,
    monkeypatch,
    teacher,
    rule,
    field,
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher=teacher)
    extra = (vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, rule)
    if rule == PSYCHE:
        extra += (m3_malleable.RULE,)
    approved(ledger, game, tmp_path, monkeypatch, extra=extra)
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    label = "Private original Tag for rebuilding"
    tag = give_original_tag(game, label) if rule == PSYCHE else None
    _, period = real_period(MissionService(ledger), game)
    scene = adapter(game)
    view = projection(scene, PLAYER, "go_off_duty")
    assert view["period"] == period and lesson.id in dict(view["lessons"][field])
    assert field not in projection(scene, OTHER, "go_off_duty").get("lessons", {})
    payload = {
        "play": "go_off_duty",
        "context": "I spend actual time at the original base.",
        "confirmed": True,
        "character_revision": view["character_revision"],
        "target": None,
        "period": period,
        field: lesson.id,
    }
    game.dice.faces = (2, 2)
    calls = game.dice.calls
    action = scene.perform_scene(PLAYER, "owned-off-duty-lesson", "scene-start", payload)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    pass_tags(game)
    original = game.inspect(PLAYER, action)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    desk = OffDutyFollowups(fresh)
    kind = "disposable_psyche" if rule == PSYCHE else "show_dog"
    summary = desk.view(PLAYER)
    work = next(row for row in summary["work"] if row["kind"] == kind)
    assert work["source_action"] == action
    assert not any(row["id"] == work["id"] for row in (desk.view(OTHER) or {}).get("work", []))
    if kind == "show_dog":
        scope = appearance_card(desk, PLAYER, work["id"])
        target = appearance_value(
            scope,
            "message",
            "target",
            lambda value: json.loads(value)["entity"] == str(OTHER.user_id),
        )
        data = appearance_payload(
            scope,
            "message",
            {
                "target": target,
                "account": "I pass this private request during the official visit.",
                "message": "LEARNED_APPEARANCE_PRIVATE",
            },
        )
    else:
        assert tag in dict(work["tags"])
        replacements = [work["identities"][0][0]] if work["count"] == 4 else []
        data = {key: summary[key] for key in ("period", "revision", "game_revision")} | {
            "action": kind,
            "answer": {
                "id": work["id"],
                "work_revision": work["revision"],
                "tags": [tag],
                "replacements": replacements,
            },
        }
    with pytest.raises(WorkflowError):
        desk.perform(OTHER, "wrong-off-duty-owner", data)
    with pytest.raises(WorkflowError):
        desk.perform(PLAYER, "wrong-off-duty-period", data | {"period": "different-period"})
    saved = desk.perform(PLAYER, "complete-off-duty-work", data)
    assert desk.perform(PLAYER, "complete-off-duty-work", data) == saved
    if kind == "show_dog":
        assert "LEARNED_APPEARANCE_PRIVATE" in json.dumps(desk.show_dog.correspondence(OTHER))
        assert "LEARNED_APPEARANCE_PRIVATE" not in json.dumps(desk.show_dog.correspondence(ADMIN))
    else:
        reopened = desk.view(PLAYER)
        receipt = next(row for row in reopened["work"] if row["id"] == work["id"])
        assert receipt["phase"] == "converted" and receipt["identities"] == [label]
    assert fresh.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == calls + 1


def test_earned_barely_opens_original_repair_and_spends_once(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="CASUALTY")
    repair = m3_casualty.BARELY
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, repair),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, repair)
    actual = state(game)
    actor = current_ref(actual, PLAYER.user_id)
    hit = next(row for row in actual.sheets["2"].assets if row.family == "girl")
    handler = HandlerPlayService(ledger)
    grant = handler.start(ADMIN, "actual-prior-damage", actual.revision, (actor,))["id"]
    handler.submit(
        ADMIN,
        "file-actual-damage",
        grant,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            target=actor,
            asset=hit.id,
            account="An actual prior effect damaged this Asset.",
        ),
    )
    scene = SpecialistScene(game, 900)
    card = popup(scene, PLAYER, repair)
    assert suggestions(game, PLAYER)[repair]["control"] == card[0]["id"]
    assert option(card, "lesson") == lesson.id
    erased = option(card, "identity")
    assert option(card, "asset") == hit.id
    params = {
        "identity": erased,
        "asset": hit.id,
        "lesson": lesson.id,
        "account": "I offer a private Identity to repair my own Asset.",
    }
    with pytest.raises(WorkflowError):
        press(scene, OTHER, card, params)
    calls = game.dice.calls
    saved = press(scene, PLAYER, card, params, key="owner-repairs")
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    service = CasualtyService(fresh)
    assert press(SpecialistScene(fresh, 900), PLAYER, card, params, key="owner-repairs") == saved
    assert service.view(PLAYER, saved["id"])["record"]["account"] == params["account"]
    with pytest.raises(WorkflowError):
        service.view(OTHER, saved["id"])
    assert repair not in suggestions(fresh, PLAYER)
    actual = state(fresh)
    assert erased not in {row.id for row in actual.sheets["2"].identities}
    assert not next(row for row in actual.sheets["2"].assets if row.id == hit.id).damaged
    assert game.dice.calls == calls and m3_casualty.body(actual, actor) is None


def test_actual_risk_cost_follows_only_its_original_owner_and_raw_roll(ledger, monkeypatch):
    game, _, _, action = risk_ready(ledger, monkeypatch)
    original = game.inspect(PLAYER, action)["receipt"]
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scene = adapter(fresh)
    choice = projected_choice(scene, PLAYER, "keep_your_head", "mockingbird_risk")
    operations = {row["id"]: row["fields"] for row in choice["risk_operations"]}
    assert operations["mockingbird_risk"] == []
    payment = {row["key"]: row for row in operations["risk_alter_asset"]}
    asset = payment["asset"]["options"][0][0]
    assert "9" in dict(payment["total"]["options"])
    request = {name: choice[name] for name in ("id", "revision", "role")} | {
        "answer": {
            "number": 9,
            "fields": {"asset": asset},
            "text": "I accept this actual Void cost.",
        },
    }
    with pytest.raises(WorkflowError):
        scene.perform(OTHER, "wrong-risk-owner", "keep-choice", request)
    assert not any(
        row["id"] == choice["id"] for row in projection(scene, OTHER, "keep_your_head")["choices"]
    )
    saved = scene.perform(PLAYER, "real-risk-payment", "keep-choice", request)
    assert scene.perform(PLAYER, "real-risk-payment", "keep-choice", request) == saved
    assert next(row for row in state(fresh).sheets["2"].assets if row.id == asset).void
    assert fresh.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == 1
    assert projected_choice(scene, PLAYER, "keep_your_head", "actor_keep")


def test_earned_hound_can_mark_status_without_a_tag(ledger, tmp_path, monkeypatch):
    rank = HandlerService.rank
    monkeypatch.setattr(
        HandlerService,
        "rank",
        lambda service, viewer, key, rev, order: rank(
            service,
            viewer,
            key,
            rev,
            tuple(sorted(order, key=lambda row: row.user_id != OTHER.user_id)),
        ),
    )
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="ALPHA")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, HOUND),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, HOUND)
    scene = adapter(game)
    assert state(game).order == (3, 2)
    game.dice.faces = (4, 4)
    calls = game.dice.calls
    opened = scene.perform(
        PLAYER,
        "hound-keep",
        "keep-start",
        {
            "context": "I actually keep my composure as a Dog.",
            "confirmed": True,
            "character_revision": game.sheet(PLAYER)["revision"],
        },
    )["action_id"]
    tick(worker, gateway, 3)
    receipt = game.inspect(PLAYER, opened)["receipt"]
    window = projected_choice(scene, PLAYER, "keep_your_head", "tag_window")
    options = {row["key"]: dict(row["options"] or []) for row in window["schema"]}
    assert "fields.status" in options and "1" in options["fields.status"]
    assert "pass" in options["options"]
    request = {name: window[name] for name in ("id", "role", "revision")} | {
        "answer": {"options": ["pass"], "fields": {"status": "1"}},
    }
    with pytest.raises(WorkflowError):
        scene.perform(OTHER, "wrong-status-actor", "keep-choice", request)
    saved = scene.perform(PLAYER, "hound-actor-status", "keep-choice", request)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    actual = state(fresh)
    mark = active_hound_status(actual, current_ref(actual, PLAYER.user_id))
    assert mark.lesson == lesson.id and actual.sheets["2"].status_marked
    assert adapter(fresh).perform(PLAYER, "hound-actor-status", "keep-choice", request) == saved
    assert fresh.inspect(PLAYER, opened)["receipt"] == receipt and game.dice.calls == calls + 1


def test_earned_dose_uses_only_the_learners_actual_cost_and_components(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="STIM-BLISSED")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, m3_dose_up.RULE),
    )
    _learn_daily_source(game, worker, gateway, controls, m3_dose_up.RULE)
    scene = SpecialistScene(game, 900)
    item = popup(scene, PLAYER, "dose_up")
    assert option(item, "source") == "self"
    assert suggestions(game, PLAYER)["dose_up"]["control"] == item[0]["id"]
    before = state(game)
    calls = game.dice.calls
    game.dice.faces = (3, 4)
    started = press(
        scene,
        PLAYER,
        item,
        {
            "source": "self",
            "heat": "1",
            "context": "I use this earned dose on my own body.",
        },
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    action = started["action_id"]
    original = game.inspect(PLAYER, action)["receipt"]
    scope = scoped(game, PLAYER, "dose_up_components")
    components = {"components": ["quick", "strong"]}
    with pytest.raises(WorkflowError):
        respond(scope, OTHER, "dose_up_components", components)
    filed = respond(scope, PLAYER, "dose_up_components", components, key="earned-dose-components")
    assert (
        respond(
            scope,
            PLAYER,
            "dose_up_components",
            components,
            key="earned-dose-components",
        )
        == filed
    )
    actual = state(game)
    applied = m3_dose_up.records(actual, m3_dose_up.Dose)[-1]
    assert applied.id == action and applied.actor == applied.target == current_ref(
        before, PLAYER.user_id
    )
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert actual.sheets["3"] == before.sheets["3"]
    assert game.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == calls + 1
    assert "dose_up" not in suggestions(game, PLAYER)


@pytest.mark.parametrize(
    ("rule", "native"),
    [
        ("girl.am.scrutinized", "am_scrutinized"),
        (m3_am_code.RULE, "am_just_code"),
    ],
)
def test_am_lesson_preserves_sheet_ownership_without_creating_an_am_source(
    ledger,
    tmp_path,
    monkeypatch,
    rule,
    native,
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="AM")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            vat.EXPERIMENT,
            vat.INVESTMENT,
            vat.SEX,
            "girl.am.scrutinized",
            m3_am_code.RULE,
        ),
    )
    lesson = _learn_daily_source(game, worker, gateway, controls, rule)
    actual = state(game)
    assert lesson.actor == current_ref(actual, PLAYER.user_id)
    assert actual.sheets["2"].girl == "VATGROWN"
    assert native not in suggestions(game, PLAYER)
    if native == "am_scrutinized":
        service = ScrutinyService(game)
        assert not service.menu(PLAYER, 900)["targets"]
        with pytest.raises(WorkflowError, match="actual new ordinary NPC discovery"):
            service.propose(
                PLAYER,
                "borrowed-am-discovery",
                900,
                current_ref(actual, OTHER.user_id),
                actual.revision,
                "Trying to use a different pilot's native AM role.",
            )
    else:
        service = CodeService(game)
        menu = service.menu(PLAYER, 900)
        assert not menu["known"] and not menu["operators"]
        with pytest.raises(WorkflowError, match="actual co-present first-time"):
            service.propose_operator(
                PLAYER,
                "borrowed-am-circuit",
                900,
                current_ref(actual, OTHER.user_id),
                actual.revision,
                "Trying to borrow a native AM circuit.",
            )
    assert state(game) == actual
