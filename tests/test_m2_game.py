"""Synthetic approval exercises M2; no live release approval is manufactured."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_creation import selected
from test_creation_review import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import ChoiceAnswer, PlayInput, ReleaseApproval, TagState
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.creation import CreationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


class Dice:
    def __init__(self, faces=(4, 5)):
        self.faces = faces
        self.calls = 0

    def roll(self):
        self.calls += 1
        return self.faces


class Gateway:
    def __init__(self):
        self.values = {
            ("role", "200"): {"allow": 1024, "deny": 0},
            ("role", "42"): {"allow": 2048, "deny": 0},
        }
        self.original = json.loads(json.dumps({k[0] + k[1]: v for k, v in self.values.items()}))
        self.messages = {}
        self.fail = None

    async def snapshot(self, channel, participants):
        if self.fail == "snapshot":
            raise OSError()
        return {
            "everyone_id": 200,
            "bot_id": 100,
            "overwrites": [{"kind": k[0], "id": k[1], **v} for k, v in self.values.items()],
        }

    async def overwrite(self, channel, target):
        return self.values.get((target["kind"], str(target["id"])))

    async def set_overwrite(self, channel, target, value):
        if self.fail == "lock":
            raise OSError()
        key = (target["kind"], str(target["id"]))
        if value is None:
            self.values.pop(key, None)
        else:
            self.values[key] = value

    async def publish(self, channel, payload, nonce):
        if self.fail == "publish":
            raise OSError()
        self.messages[nonce] = payload
        return len(self.messages) + 1000

    async def find(self, channel, nonce):
        return 1000 if nonce in self.messages else None

    async def actor(self, identity):
        return {1: ADMIN, 2: PLAYER, 3: OTHER}[identity]


def setup_game(store, girl="MOCKINGBIRD", frame="JANUS-B", faces=(4, 5)):
    review, creation, _ = ready(store, girl, frame)
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic test only",
                reference="fixture; not certification",
            ),
        }
    )
    # Both players choose the same mutual starting agreement explicitly.
    current = creation.get(OTHER)
    draft = selected("MOCKINGBIRD", "JANUS-B").model_copy(
        update={"shared_tokens": current.draft.shared_tokens}
    )
    creation.save(OTHER, "other-build", 0, 1, draft)
    other_review = CreationReviewService(store)
    current_review = other_review.get(OTHER)
    incoming = next(x for x in current_review.sheet.bonds if not x.outgoing)
    current = creation.get(OTHER)
    other_review.select_bond(OTHER, "other-bond", current.revision, 1, current.draft, incoming.id)
    dice = Dice(faces)
    game = GameService(store, dice=dice)
    for viewer in (PLAYER, OTHER):
        current_review = review.get(viewer)
        review.save(
            viewer,
            "review-" + str(viewer.user_id),
            current_review.saved_revision,
            current_review.fingerprint,
        )
        current_review = review.get(viewer)
        assert current_review.sheet.ready_for_rules_review
        game.activate(viewer, "activate-" + str(viewer.user_id), current_review.fingerprint)
    game.bind_scene(ADMIN, "bind", 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, "join-scene-" + str(viewer.user_id), 900)
    return game, GameWorker(game), Gateway(), dice


def state(game):
    with game.store.engine.connect() as c:
        return load_state(c, game.store.campaign_id)


def start(game, **kwargs):
    data = dict(play="keep_your_head", context="Synthetic danger", trigger_confirmed=True, heat=0)
    data.update(kwargs)
    return game.begin(
        PLAYER, str(uuid4()), 900, state(game).sheets["2"].revision, PlayInput(**data)
    )["action_id"]


def answer(game, viewer, kind, **kwargs):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    return game.respond(viewer, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(**kwargs))


def pass_tags(game):
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))


def tick(worker, gateway, n=1):
    async def run():
        for _ in range(n):
            await worker.tick(gateway)

    asyncio.run(run())


def test_activation_and_prelock_no_rng(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    action = start(game)
    assert dice.calls == 0
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(PLAYER, "early", action)
    tick(worker, gateway)
    assert dice.calls == 1
    assert game.inspect(PLAYER, action)["state"] == "tag_window"
    with pytest.raises(WorkflowError, match="Already activated"):
        game.activate(PLAYER, "reset", CreationReviewService(ledger).get(PLAYER).fingerprint)


@pytest.mark.parametrize(
    "faces,positive,negative,tag",
    [
        ((2, 3), ("tough",), (), ""),
        ((4, 5), ("tough", "in_control"), ("desperate",), ""),
        ((6, 6), (), (), "SYNTHETIC_TAG"),
    ],
)
def test_keep_three_tiers_and_handler_ownership(ledger, faces, positive, negative, tag):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    action = start(game)
    tick(worker, gateway)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(
            OTHER, "forge", row["id"], 1, ChoiceAnswer(options=positive, denied=negative, text=tag)
        )
    answer(game, PLAYER, "actor_keep", options=positive, denied=negative, text=tag)
    assert game.inspect(PLAYER, action)["result"] is None
    assert game.inspect(PLAYER, action)["state"] != "complete"
    answer(game, ADMIN, "handler_keep", flag=True, text="SYNTHETIC_HANDLER_PRIVATE")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original
    assert "SYNTHETIC_HANDLER_PRIVATE" not in json.dumps(gateway.messages)
    assert dice.calls == 1


@pytest.mark.parametrize(
    "heat,gain,spend,valid",
    [
        (0, 0, -1, False),
        (0, 0, 1, False),
        (5, 0, 4, False),
        (5, 0, 5, True),
        (2, 3, 4, False),
        (2, 3, 5, True),
        (0, 3, 2, True),
    ],
)
def test_heat_identity_before_roll_and_forced_spend(ledger, heat, gain, spend, valid):
    from pydantic import ValidationError

    game, worker, gateway, dice = setup_game(ledger)
    with ledger.transaction() as c:
        saved = load_state(c, ledger.campaign_id)
        saved.sheets["2"].heat = heat
        game.event(c, PLAYER.user_id, str(uuid4()), "synthetic.seed", saved)
    args = {"heat": spend, "gain": gain, "identity": "identity:0" if gain else None}
    if not valid:
        with pytest.raises((WorkflowError, ValidationError)):
            start(game, **args)
        assert dice.calls == 0
        assert state(game).sheets["2"].heat == heat
    else:
        action = start(game, **args)
        assert state(game).sheets["2"].heat == heat
        tick(worker, gateway)
        assert state(game).sheets["2"].heat == heat + gain - spend
        assert dice.calls == 1
        first = game.inspect(PLAYER, action)["receipt"]
        assert game.roll(PLAYER, "replay-roll", action)["receipt"] == first
        assert dice.calls == 1


@pytest.mark.parametrize("failure", ["snapshot", "lock", "publish"])
def test_lock_failure_no_rng_spend_or_fake_completion(ledger, failure):
    game, worker, gateway, dice = setup_game(ledger)
    action = start(game, identity="identity:0", gain=3, heat=2)
    gateway.fail = failure
    tick(worker, gateway, 2)
    assert dice.calls == 0 and state(game).sheets["2"].heat == 0
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "review"
    assert game.inspect(PLAYER, action)["receipt"] is None
    game.abort(ADMIN, "abort", action)
    gateway.fail = None
    tick(worker, gateway, 4)
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original


@pytest.mark.parametrize("faces,count", [((2, 3), 1), ((4, 5), 2), ((6, 6), 3)])
def test_engage_exact_counts_and_used_asset_damage(ledger, faces, count):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    action = start(game, play="engage")
    tick(worker, gateway)
    pass_tags(game)
    choices = ("pin", "advance", "protect")[:count]
    with pytest.raises(WorkflowError):
        answer(
            game,
            PLAYER,
            "actor_engage",
            options=choices + ("cover",),
            fields={x: "girl:0" for x in choices},
        )
    if count != 2:
        with pytest.raises(WorkflowError):
            answer(
                game,
                PLAYER,
                "actor_engage",
                options=choices,
                fields={x: "girl:0" for x in choices},
                denied=("girl:1",),
            )
    answer(
        game,
        PLAYER,
        "actor_engage",
        options=choices,
        fields={x: "girl:0" for x in choices},
        denied=() if count == 2 else ("girl:0",),
    )
    assert state(game).sheets["2"].assets[0].damaged == (count != 2)
    assert game.inspect(PLAYER, action)["state"] == "complete"


@pytest.mark.parametrize("faces,count", [((2, 3), 1), ((4, 5), 2), ((6, 6), 3)])
def test_sensors_exact_questions_and_human_answers(ledger, faces, count):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    action = start(game, play="check_sensors")
    tick(worker, gateway)
    pass_tags(game)
    from girlframe.engine.m2 import QUESTIONS

    answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:count])
    assert game.inspect(PLAYER, action)["result"] is None
    with pytest.raises(WorkflowError):
        answer(
            game, ADMIN, "handler_sensors", fields={"a1": "incomplete"}
        ) if count > 1 else answer(game, ADMIN, "handler_sensors", fields={})
    answer(
        game,
        ADMIN,
        "handler_sensors",
        fields={"a" + str(i + 1): "Human answer " + str(i) for i in range(count)},
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_one_postroll_tag_bond_bonus_and_observer_auth(ledger, depth):
    game, worker, gateway, dice = setup_game(ledger)
    with ledger.transaction() as c:
        saved = load_state(c, ledger.campaign_id)
        saved.bonds["2:3"] = depth
        saved.sheets["2"].tags.append(
            TagState(id="tag1", label="Observed", giver=3, observers=(1, 2, 3))
        )
        game.event(c, 2, "add-tag", "synthetic.tag", saved)
    action = start(game)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("tag1",),
        number=1,
        text="Relevant because of the fiction",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    data = game.inspect(PLAYER, action)
    assert len(data["modifiers"]) == 1
    assert data["modifiers"][0]["amount"] == (1 if depth == 0 else 2)
    assert data["receipt"]["pre_total"] == 9
    assert state(game).sheets["2"].tags[0].marked


@pytest.mark.parametrize("faces", [(2, 3), (4, 5), (6, 6)])
def test_disobey_requires_recorded_superior_order_and_low_halts(ledger, faces):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    with pytest.raises(WorkflowError, match="recorded direct order"):
        start(game, play="disobey_orders")
    with pytest.raises(WorkflowError, match="superior"):
        game.issue_order(OTHER, "bad-order", 900, 2, "No authority")
    root = game.issue_order(ADMIN, "order", 900, 2, "Synthetic order")
    tick(worker, gateway)
    answer(game, PLAYER, "order_response", options=("disobey",))
    child = game.begin(
        PLAYER,
        "child",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="Refusal",
            trigger_confirmed=True,
            heat=0,
            order_id=root["order_id"],
            parent=root["action_id"],
            witnessed=True,
        ),
    )["action_id"]
    tick(worker, gateway)
    pass_tags(game)
    assert state(game).order == (3, 2)
    if sum(faces) <= 7:
        assert not any(x["kind"] == "actor_disobey" for x in game.choices(PLAYER))
    elif sum(faces) <= 10:
        answer(game, PLAYER, "actor_disobey", options=("tag_heat",), number=2, text="Defiant")
    else:
        answer(game, PLAYER, "actor_disobey", flag=True)
    answer(game, ADMIN, "handler_disobey", flag=True)
    assert game.inspect(PLAYER, child)["result"]["can_disobey"] == (sum(faces) > 7)
    assert game.inspect(PLAYER, root["action_id"])["state"] == "complete"
    assert any(x.kind == "punishment" for x in state(game).obligations)


@pytest.mark.parametrize(
    "faces,extra",
    [((2, 3), None), ((4, 5), None), ((6, 6), "owe"), ((6, 6), "handler"), ((6, 6), "escape")],
)
def test_flirt_all_tiers_full_high_branches_and_target_ownership(ledger, faces, extra):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    action = start(game, play="flirt", target=3)
    tick(worker, gateway)
    pass_tags(game)
    if sum(faces) > 7:
        answer(
            game,
            PLAYER,
            "actor_flirt",
            options=("name",),
            fields={"extra": extra} if extra else {},
            text="Too far" if extra else "",
        )
    row = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
    with pytest.raises(WorkflowError, match="another player"):
        game.respond(PLAYER, "fake-target", row["id"], 1, ChoiceAnswer(text="Forged"))
    answer(game, OTHER, "target_flirt", text="SYNTHETIC_PRIVATE_TARGET")
    if extra == "owe":
        answer(game, OTHER, "flirt_owe_tag", text="Owed")
    elif extra == "handler":
        with pytest.raises(WorkflowError):
            answer(game, ADMIN, "handler_brief", text="Missing actual play")
        answer(
            game,
            ADMIN,
            "handler_brief",
            options=("brief",),
            text="Situation supplied by human Handler",
        )
    elif extra == "escape":
        answer(game, OTHER, "flirt_escape", options=("damage",), denied=("girl:0",))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).bonds["2:3"] == (0 if sum(faces) <= 7 else 1)
    assert "SYNTHETIC_PRIVATE_TARGET" not in json.dumps(gateway.messages)
    if sum(faces) > 7:
        assert any(x.kind == "flirt_followthrough" for x in state(game).obligations)


def test_nested_escape_play_is_real_roll_then_mutual_followthrough(ledger):
    game, worker, gateway, dice = setup_game(ledger, faces=(6, 6))
    action = start(game, play="flirt", target=3)
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game, PLAYER, "actor_flirt", options=("name",), fields={"extra": "escape"}, text="Too far"
    )
    answer(game, OTHER, "target_flirt", text="A new name")
    answer(game, OTHER, "flirt_escape", options=("play",))
    child = game.begin(
        OTHER,
        "escape",
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            context="Escape now",
            trigger_confirmed=True,
            heat=0,
            parent=action,
        ),
    )["action_id"]
    tick(worker, gateway)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", text="Escape tag")
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough to escape")
    assert dice.calls == 2
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, action)["result"]["response_play"] == child
    tick(worker, gateway, 8)
    item = next(x for x in game.own_obligations(PLAYER) if x["kind"] == "flirt_followthrough")
    follow = game.fulfill(PLAYER, "fulfill", 900, item["id"], "I give the requested name")[
        "action_id"
    ]
    tick(worker, gateway)
    assert state(game).bonds["2:3"] == 1
    row = next(x for x in game.choices(OTHER) if x["kind"] == "followthrough_confirm")
    with pytest.raises(WorkflowError):
        game.respond(PLAYER, "forge-confirm", row["id"], 1, ChoiceAnswer(flag=True, text="fake"))
    answer(game, OTHER, "followthrough_confirm", flag=True, text="I confirm")
    assert state(game).bonds["2:3"] == 2 and game.inspect(PLAYER, follow)["state"] == "complete"


def test_stale_forms_pauses_replay_restart_and_unsupported_no_rng(ledger):
    from girlframe.services.read_only_bot import GuildViewer

    game, worker, gateway, dice = setup_game(ledger)
    with pytest.raises(WorkflowError, match="UNSUPPORTED_RULE"):
        start(game, play="not_implemented")
    with pytest.raises(WorkflowError, match="STALE_SHEET"):
        game.begin(
            PLAYER,
            "stale",
            900,
            999,
            PlayInput(play="engage", context="No", trigger_confirmed=True, heat=0),
        )
    action = start(game)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    tick(worker, gateway)
    assert dice.calls == 0
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    tick(worker, gateway)
    row = game.choices(PLAYER)[0]
    response = ChoiceAnswer(options=("pass",))
    first = game.respond(PLAYER, "same-click", row["id"], 1, response)
    replacement = GameService(ledger, dice=dice)
    assert replacement.respond(PLAYER, "same-click", row["id"], 1, response) == first
    assert (
        replacement.roll(PLAYER, "same-roll-after-restart", action)["receipt"]
        == game.inspect(PLAYER, action)["receipt"]
    )
    assert dice.calls == 1
    with pytest.raises(WorkflowError, match="STALE_CHOICE"):
        replacement.respond(PLAYER, "stale-new-click", row["id"], 1, response)
    with pytest.raises(WorkflowError):
        replacement.choices(GuildViewer(2, 999, True, False))
    with pytest.raises(WorkflowError):
        replacement.choices(GuildViewer(2, 200, False, False))


def test_permission_drift_and_restore_preserve_unrelated_staff_changes(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    action = start(game)
    tick(worker, gateway)
    gateway.values[("role", "42")]["allow"] |= 1 << 20
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough")
    tick(worker, gateway, 6)
    assert gateway.values[("role", "42")] == {"allow": 2048 | (1 << 20), "deny": 0}
    with pytest.raises(WorkflowError, match="STALE_ACTION"):
        game.abort(ADMIN, "old-abort", action)
    # A new lock detects new allow-overwrites rather than rolling through permission drift.
    fresh = start(game)
    gateway.values[("role", "77")] = {"allow": 0, "deny": 0}
    tick(worker, gateway)
    gateway.values[("role", "77")]["allow"] |= 1 << 11
    tick(worker, gateway)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "review"
    game.abort(ADMIN, "abort-drift", fresh)
    tick(worker, gateway)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "review"  # conflict, never clobber staff


def test_backup_rebuild_immutable_private_history_and_public_sheet(ledger, tmp_path):
    from sqlalchemy.exc import IntegrityError

    from girlframe.config import Settings
    from girlframe.database.connection import create_database_engine
    from girlframe.database.maintenance import copy_database
    from girlframe.services.onboarding import OnboardingStore

    game, worker, gateway, dice = setup_game(ledger)
    action = start(game, identity="identity:0", gain=2, heat=2)
    tick(worker, gateway)
    original = state(game).model_dump_json()
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game).model_dump_json() == original
    target = tmp_path / "m2-backup.db"
    copy_database(Path(ledger.engine.url.database), target)
    engine = create_database_engine(Settings(database_url="sqlite:///" + str(target)))
    restored = GameService(OnboardingStore(engine, ledger.policy), dice=dice)
    assert restored.inspect(PLAYER, action) == game.inspect(PLAYER, action)
    assert restored.choices(OTHER) == game.choices(OTHER)
    assert dice.calls == 1
    with ledger.transaction() as c:
        with pytest.raises(IntegrityError):
            c.execute(t.m2["m2_receipts"].delete())
    public = game.sheet(ADMIN, 2)
    assert "review" not in public and "heat" not in public and "identities" not in public
    assert "OWNER_PROFILE_SECRET" not in json.dumps(public)
    with ledger.engine.connect() as c:
        events = " ".join(
            c.scalars(sa.select(t.events.c.payload_json).where(t.events.c.kind.like("m2.%")))
        )
    assert "PRIVATE" not in events and "context" not in events
    engine.dispose()


def test_live_default_gate_and_active_editor_protection(ledger):
    from girlframe.engine.drafts import DraftInput

    game, worker, gateway, dice = setup_game(ledger)
    with pytest.raises(WorkflowError, match="ACTIVE_CHARACTER"):
        ledger.save_draft(
            PLAYER,
            "reset-draft",
            2,
            DraftInput(callsign="RESET", girl_playbook="ALPHA", frame_playbook="JANUS-B"),
        )
    creation = CreationService(ledger)
    current = creation.get(PLAYER)
    with pytest.raises(WorkflowError, match="ACTIVE_CHARACTER"):
        creation.save(PLAYER, "reset-builder", current.revision, 2, current.draft)
    ledger.policy = ledger.policy.model_copy(update={"m2_approval": None})
    with pytest.raises(WorkflowError, match="M2_REVIEW_PENDING"):
        start(game)
    assert dice.calls == 0


def test_stale_root_cannot_abort_new_root_and_duplicate_confirm_race(ledger):
    from concurrent.futures import ThreadPoolExecutor

    game, worker, gateway, dice = setup_game(ledger)
    old = start(game)
    game.abort(ADMIN, "abort-old", old)
    tick(worker, gateway, 3)
    current = start(game)
    with pytest.raises(WorkflowError, match="STALE_ACTION"):
        game.abort(ADMIN, "stale-abort", old)
    with ThreadPoolExecutor(max_workers=2) as pool:

        def roll_early(key):
            try:
                return game.roll(PLAYER, key, current)
            except WorkflowError:
                return None

        assert list(pool.map(roll_early, ("race-1", "race-2"))) == [None, None]
    assert dice.calls == 0
    tick(worker, gateway)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda k: game.roll(PLAYER, k, current), ("race-3", "race-4")))
    assert dice.calls == 1


@pytest.mark.parametrize("girl", [x for x, v in CATALOG.items() if v["family"] == "girl"])
def test_every_girl_activation_preserves_source_and_printed_exceptions(ledger, girl):
    review, creation, _ = ready(ledger, girl)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(), reviewer="synthetic", reference="fixture"
            ),
        }
    )
    game = GameService(ledger)
    current = review.get(PLAYER)
    review.save(PLAYER, "save-review", 0, current.fingerprint)
    game.activate(PLAYER, "activate", current.fingerprint, ("appearance",))
    sheet = game.sheet(PLAYER)
    assert len([x for x in sheet["identities"] if not x["protected"] or x["paired"]]) == 4
    assert all(not x["marked"] for x in sheet["identities"])
    assert all(not x["damaged"] for x in sheet["assets"]) and sheet["heat"] == 0
    assert sheet["review"]["initial_conditions"]
    if girl == "NEWGIRL":
        assert sheet["callsign"] == "MENTOR_NAME"
        assert CreationReviewService(ledger).get(PLAYER).fingerprint == current.fingerprint
        ledger.queue_sync(PLAYER, "retry-nickname")
        assert "MENTOR_NAME" in ledger.sync_job(PLAYER)["desired_json"]
    if girl == "BONDED":
        assert sum(x["paired"] and x["protected"] for x in sheet["identities"]) == 1
    if girl == "MOCKINGBIRD":
        assert sum(x["void"] for x in sheet["assets"]) == 1
    public = game.sheet(OTHER, 2)
    assert "appearance" in public and "review" not in public and "identities" not in public


@pytest.mark.parametrize(
    "frame", [x for x, v in CATALOG.items() if v["family"] == "frame"] + ["JANUS-B"]
)
def test_every_frame_activation_retains_baseline(ledger, frame):
    review, _, _ = ready(ledger, frame=frame)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(), reviewer="synthetic", reference="fixture"
            ),
        }
    )
    game = GameService(ledger)
    current = review.get(PLAYER)
    review.save(PLAYER, "review", 0, current.fingerprint)
    game.activate(PLAYER, "activate", current.fingerprint)
    sheet = game.sheet(PLAYER)
    assert sheet["review"]["rulings"]["starting_heat"] == 0
    if frame == "THE PRINCE":
        assert len(sheet["identities"]) == 6
    if frame == "WYVERN 0.4":
        assert any(x["name"] == "Enormous" for x in sheet["assets"])


def test_campaign_isolation_and_delivery_uncertainty_no_reroll(ledger):
    from girlframe.services.ledger import CampaignLedger
    from girlframe.services.onboarding import OnboardingStore
    from girlframe.services.read_only_bot import GuildViewer

    game, worker, gateway, dice = setup_game(ledger)
    other = CampaignLedger(
        OnboardingStore(
            ledger.engine,
            ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201}),
        )
    )
    other_viewer = GuildViewer(2, 201, True, False)
    other.join(other_viewer, "join-other-campaign")
    unrelated = GameService(other)
    action = start(game)
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="Unknown action"):
        unrelated.inspect(other_viewer, action)
    assert unrelated.choices(other_viewer) == []
    first = game.inspect(PLAYER, action)["receipt"]
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Human ruling")
    gateway.fail = "publish"
    tick(worker, gateway, 2)
    assert dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] == first
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "held"
    gateway.fail = None
    game.retry_recovery(ADMIN, "reconcile", action)
    tick(worker, gateway, 6)
    assert dice.calls == 1


def test_helpless_requires_explicit_recovery_and_no_silent_timeout(ledger):
    game, worker, gateway, dice = setup_game(ledger, faces=(6, 6))
    start(game, play="flirt", target=3)
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game, PLAYER, "actor_flirt", options=("name",), fields={"extra": "escape"}, text="Too far"
    )
    answer(game, OTHER, "target_flirt", text="A name")
    answer(game, OTHER, "flirt_escape", options=("helpless",))
    assert state(game).sheets["3"].helpless_against == (2,)
    with pytest.raises(WorkflowError):
        game.recover_helpless(
            OTHER, "too-soon", state(game).sheets["3"].revision, "A moment alone", None
        )
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError, match="Helplessness"):
        game.begin(
            OTHER,
            "helpless-play",
            900,
            state(game).sheets["3"].revision,
            PlayInput(play="engage", context="Defense", trigger_confirmed=True, heat=0),
        )
    game.recover_helpless(
        OTHER, "recover", state(game).sheets["3"].revision, "A genuine moment alone", None
    )
    assert not state(game).sheets["3"].helpless_against
    assert dice.calls == 1


def test_repeated_tag_across_scenes_embrace_and_reject_followthrough(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    with ledger.transaction() as c:
        saved = load_state(c, ledger.campaign_id)
        saved.sheets["2"].tags.append(
            TagState(id="repeat", label="Repeated Tag", giver=3, observers=(1, 2, 3), marked=True)
        )
        game.event(c, 2, "tag-seed", "synthetic.tag", saved)
    start(game)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("repeat",),
        number=-1,
        text="Fictional relevance",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, PLAYER, "tag_resolution", options=("reject",))
    assert state(game).sheets["2"].tags[0].rejection_pending
    answer(game, PLAYER, "actor_keep", options=("tough",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough")
    tick(worker, gateway, 5)
    item = next(x for x in game.own_obligations(PLAYER) if x["kind"] == "reject_tag")
    game.fulfill(
        PLAYER,
        "reject-opportunity",
        900,
        item["id"],
        "I act against the Tag at this first opportunity",
    )
    tick(worker, gateway, 4)
    assert not state(game).sheets["2"].tags
    assert not game.own_obligations(PLAYER)


def test_independent_scenes_and_one_winner_per_channel(ledger):
    from concurrent.futures import ThreadPoolExecutor

    game, worker, gateway, dice = setup_game(ledger)
    game.leave_scene(OTHER, "leave", 900)
    game.bind_scene(ADMIN, "bind-second", 901)
    game.join_scene(OTHER, "join-other-scene", 901)
    game.join_scene(ADMIN, "handler-other-scene", 901)
    sheet = state(game).sheets["2"]

    def attempt(key):
        try:
            return game.begin(
                PLAYER,
                key,
                900,
                sheet.revision,
                PlayInput(play="engage", context="Test", trigger_confirmed=True, heat=0),
            )
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("confirm-a", "confirm-b")))
    assert sum(x is not None for x in results) == 1
    game.begin(
        OTHER,
        "other-scene-play",
        901,
        state(game).sheets["3"].revision,
        PlayInput(play="engage", context="Other scene", trigger_confirmed=True, heat=0),
    )
    tick(worker, gateway, 2)
    assert dice.calls == 2
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == game.lock(c, 901)["state"] == "held"
    with pytest.raises(WorkflowError):
        game.leave_scene(PLAYER, "leave-locked", 900)


@pytest.mark.parametrize("locked", [False, True])
def test_newgirl_self_mark_and_nonrejectable_mentor_tag(ledger, locked):
    game, worker, gateway, dice = setup_game(ledger, girl="NEWGIRL")
    with ledger.transaction() as c:
        saved = load_state(c, ledger.campaign_id)
        if locked:
            saved.sheets["2"].identities[0].marked = True
            saved.sheets["2"].sedation_locked = ("identity:0",)
            saved.sheets["2"].sedation_period = "off-duty-test"
        saved.sheets["2"].tags.append(
            TagState(id="mentor", label="Mentored", giver=3, observers=(1, 2, 3), marked=True)
        )
        game.event(c, 2, "mentor-tag", "synthetic.tag", saved)
    start(game)
    tick(worker, gateway)
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=("mentor",),
        number=1,
        text="Mentor Tag applies",
    )
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    with pytest.raises(WorkflowError, match="cannot reject"):
        answer(game, PLAYER, "tag_resolution", options=("reject",))
    answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=("identity:0",))
    assert any(x.name == "Mentored" for x in state(game).sheets["2"].identities)
    assert len(state(game).sheets["2"].identities) == 4
    if locked:
        updated = state(game).sheets["2"]
        replacement = next(x for x in updated.identities if x.name == "Mentored")
        assert replacement.marked and updated.sedation_locked == (replacement.id,)
        assert updated.sedation_period == "off-duty-test"


@pytest.mark.parametrize("consequence", ["incomplete_information", "punishment_later"])
def test_high_sensors_offlist_requires_real_handler_choice(ledger, consequence):
    game, worker, gateway, dice = setup_game(ledger, faces=(6, 6))
    action = start(game, play="check_sensors")
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_sensors",
        fields={
            "q1": "First custom question",
            "q2": "Second custom question",
            "q3": "Third custom question",
        },
    )
    answers = {"a1": "First human answer", "a2": "Second human answer", "a3": "Third human answer"}
    with pytest.raises(WorkflowError):
        answer(game, ADMIN, "handler_sensors", fields=answers)
    answer(game, ADMIN, "handler_sensors", options=(consequence,), fields=answers)
    assert game.inspect(PLAYER, action)["result"]["consequence"] == [consequence]
    assert any(x.kind == "punishment" for x in state(game).obligations) == (
        consequence == "punishment_later"
    )


@pytest.mark.parametrize("branch", ["reject_tag", "follow"])
def test_disobey_remaining_mid_branches_require_owned_choices(ledger, branch):
    game, worker, gateway, dice = setup_game(ledger)
    with ledger.transaction() as c:
        saved = load_state(c, ledger.campaign_id)
        saved.sheets["2"].tags.append(
            TagState(id="removable", label="Tag", giver=3, observers=(1, 2, 3))
        )
        game.event(c, 2, "seed-removable", "synthetic.tag", saved)
    root = game.issue_order(ADMIN, "issue", 900, 2, "Direct order")
    tick(worker, gateway)
    answer(game, PLAYER, "order_response", options=("disobey",))
    game.begin(
        PLAYER,
        "refuse",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="disobey_orders",
            context="Refuse",
            trigger_confirmed=True,
            heat=0,
            parent=root["action_id"],
            order_id=root["order_id"],
        ),
    )
    tick(worker, gateway)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_disobey",
        options=(branch,),
        denied=("removable",) if branch == "reject_tag" else (),
        member=3 if branch == "follow" else None,
    )
    answer(game, ADMIN, "handler_disobey", flag=False)
    if branch == "follow":
        assert game.inspect(PLAYER, root["action_id"])["state"] != "complete"
        answer(game, OTHER, "follow_disobey", flag=False)
    else:
        assert not state(game).sheets["2"].tags
    assert game.inspect(PLAYER, root["action_id"])["state"] == "complete"


def test_transaction_failure_does_not_publish_receipt_or_spend(ledger, monkeypatch):
    game, worker, gateway, dice = setup_game(ledger)
    action = start(game, identity="identity:0", gain=2, heat=2)
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    original = game.event

    def crash(*args, **kwargs):
        raise RuntimeError("Synthetic commit fault")

    monkeypatch.setattr(game, "event", crash)
    with pytest.raises(RuntimeError):
        game.roll(PLAYER, "crash-before-commit", action)
    assert game.inspect(PLAYER, action)["receipt"] is None
    assert not state(game).sheets["2"].identities[0].marked and state(game).sheets["2"].heat == 0
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 0
    monkeypatch.setattr(game, "event", original)
    game.roll(PLAYER, "crash-before-commit", action)
    assert game.inspect(PLAYER, action)["receipt"] is not None


def test_paired_heat_and_bond_cap_are_explicit_owner_choices(ledger):
    from girlframe.engine.m2 import mark_identity, spend_heat
    from girlframe.services.m2_choices import ChoiceEngine

    game, worker, gateway, dice = setup_game(ledger)
    saved = state(game)
    sheet = saved.sheets["2"]
    sheet.identities[0].paired = True
    with pytest.raises(ValueError):
        mark_identity(sheet, sheet.identities[0].id, 3, 0)
    assert mark_identity(sheet, sheet.identities[0].id, 5, 2) == 2
    assert sheet.heat == 3
    spend_heat(sheet, 2)
    assert sheet.heat == 1
    saved.bonds["2:3"] = 2
    ChoiceEngine(game).bond(saved, 2, 3, 1)
    assert saved.sheets["2"].heat == 3 and saved.sheets["3"].heat == 2
