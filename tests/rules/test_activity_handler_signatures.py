"""Use the Activity signature endpoint without introducing new mechanical authority."""

from contextlib import contextmanager

import pytest
from test_director_activity_scene import activity_adapter
from test_handler_creation import ready
from test_insurgent_loyalty import create_insurgent
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, state, tick
from test_trainer_phrases import create_trainer

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.activity_handler_signatures import native_signature
from girlframe.services.m3_insurgent_loyalty import REVEAL, WATCH, labels
from girlframe.services.m3_trainer_phrases import HEAR, SPEAK
from girlframe.services.onboarding import WorkflowError


class ActivityScene:
    def __init__(self, game):
        self.game = game
        self.app = activity_adapter.local_fixture_director(game, activity_shadow=True)
        self.worker, self.gateway = GameWorker(game), Gateway()
        with game.store.engine.connect() as connection:
            self.scene = game.scene(connection, 900)["id"]

    def flush(self):
        tick(self.worker, self.gateway, 5)

    def view(self, viewer):
        return self.app.read(viewer, self.scene, "handler-native-work")["signatures"]

    def choice(self, viewer, kind):
        return next(x for x in self.view(viewer)["choices"] if x["kind"] == kind)

    def write(self, viewer, key, **data):
        return self.app.write(viewer, key, self.scene, "handler-native", data)

    def respond(self, viewer, key, choice, **data):
        return self.write(
            viewer,
            key,
            action="signature-response",
            id=choice["id"],
            revision=choice["revision"],
            answer=data,
        )

    @contextmanager
    def signature(self):
        with self.game.store.engine.connect() as connection:
            scene = self.game.scene(connection, 900)
            current = state(self.game)
            yield native_signature(
                self.game, connection, scene, current_ref(current, 1), current_ref(current, 3)
            )


def test_insurgent_activity_confirms_observed_dissent_and_separate_owned_disclosure(ledger):
    _, game = ready(ledger)
    create_insurgent(ledger, game)
    game.dice = Dice((4, 5))
    desk = ActivityScene(game)

    def refuse(index, witnessed):
        desk.write(
            ADMIN,
            f"order:{index}",
            action="signature-direct-order",
            id=desk.scene,
            revision=desk.view(ADMIN)["game_revision"],
            target="3",
            text="Report to the desk.",
        )
        desk.flush()
        response = desk.choice(OTHER, "order_response")
        desk.respond(OTHER, f"refuse:{index}", response, options=["disobey"])
        child = desk.choice(OTHER, "order_disobey")
        desk.write(
            OTHER,
            f"refusal:{index}",
            action="signature-child",
            id=child["id"],
            revision=child["revision"],
            sheet_revision=child["sheet_revision"],
            text="I refuse to report to the desk.",
            heat=0,
            witnessed=False,
        )
        desk.flush()
        for viewer in (ADMIN, PLAYER, OTHER):
            window = desk.choice(viewer, "tag_window")
            desk.respond(viewer, f"pass:{index}:{viewer.user_id}", window, options=["pass"])
        desk.respond(
            OTHER,
            f"disobey:{index}",
            desk.choice(OTHER, "actor_disobey"),
            options=["tag_heat"],
            number=1,
            text="Defiant",
        )
        desk.respond(ADMIN, f"heard:{index}", desk.choice(ADMIN, "handler_disobey"), flag=witnessed)

    refuse(1, False)
    assert not desk.view(ADMIN)["choices"]
    with desk.signature() as offered:
        assert not offered
    desk.flush()
    refuse(2, True)
    watch = desk.choice(ADMIN, WATCH)
    with desk.signature() as offered:
        (signature,) = offered
        assert signature.play == "rebel_sympathizers"
        assert signature.control == watch["id"] and signature.destination == "signature_choice"
    assert desk.view(ADMIN)["handler"] and not desk.view(PLAYER)["handler"]
    with pytest.raises(WorkflowError):
        desk.respond(OTHER, "false-witness", watch, flag=True, text="Not my choice.")
    desk.respond(ADMIN, "own-witness", watch, flag=True, text="I witnessed her actual dissent.")
    desk.flush()
    refuse(3, True)
    disclose = desk.choice(OTHER, REVEAL)
    assert not desk.view(PLAYER)["choices"]
    assert not desk.view(ADMIN)["choices"]
    desk.respond(OTHER, "own-disclosure", disclose, flag=True, text="I sympathize with that cause.")
    final = state(game)
    girl = current_ref(final, 3)
    assert [x.status for x in labels(final, girl)] == ["surveilled", "sympathizer"]
    assert all(
        set(x.observers) == {1, 3}
        for x in final.sheets["3"].tags
        if x.label in ("Surveilled", "Sympathizer")
    )
    assert any(x.kind == "punishment" and x.owner == 3 for x in final.obligations)


def test_trainer_activity_issues_an_installed_phrase_and_records_only_owned_speech(ledger):
    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=True)
    desk = ActivityScene(game)
    with desk.signature() as offered:
        (signature,) = offered
        assert signature.play == "conditioning_phrases"
        assert signature.control == str(OTHER.user_id)
        assert signature.destination == "conditioning_phrase"
    view = desk.view(ADMIN)
    target = next(x for x in view["targets"] if x["id"] == "3")
    assert "speak" in dict(target["phrases"])
    command = {
        "action": "conditioning-order",
        "id": desk.scene,
        "revision": view["game_revision"],
        "target": target["id"],
        "phrase": "speak",
        "text": "Give me your account.",
        "counterpart": None,
        "actor": None,
    }
    with pytest.raises(WorkflowError):
        desk.write(ADMIN, "uninstalled", **(command | {"phrase": "hunt", "actor": "fake"}))
    issued = desk.write(ADMIN, "actual-speak", **command)
    assert desk.write(ADMIN, "actual-speak", **command) == issued
    desk.flush()
    desk.respond(
        OTHER, "real-obedience", desk.choice(OTHER, "order_response"), options=["immediate"]
    )
    speak = desk.choice(OTHER, SPEAK)
    with pytest.raises(WorkflowError):
        desk.respond(ADMIN, "invented-speech", speak, text="Not the Girl's actual account.")
    desk.respond(OTHER, "girl-speaks", speak, text="PRIVATE_OWNED_ACCOUNT")
    heard = desk.choice(ADMIN, HEAR)
    assert heard["text"] == "PRIVATE_OWNED_ACCOUNT"
    assert not desk.view(PLAYER)["choices"]
    desk.respond(ADMIN, "real-hearing", heard, flag=True)
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"


def test_trainer_hunt_activity_keeps_the_original_target_and_owned_battle_choices(ledger):
    from test_physical_operations import place

    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=False, dog_prompt=1)
    game.dice = Dice((4, 5))
    with ledger.transaction() as connection:
        placed = place(place(state(game), 2), 3)
        game.event(connection, 1, "original-hunt-positions", "synthetic.placement", placed)
    desk = ActivityScene(game)
    target = current_ref(state(game), 2)
    view = desk.view(ADMIN)
    recipient = next(x for x in view["targets"] if x["id"] == "3")
    assert target.token in dict(recipient["actors"]["hunt"])
    issued = desk.write(
        ADMIN,
        "issue-hunt",
        action="conditioning-order",
        id=desk.scene,
        revision=view["game_revision"],
        target="3",
        phrase="hunt",
        text="Hunt this actual target.",
        counterpart=None,
        actor=target.token,
    )
    desk.flush()
    desk.respond(
        OTHER, "accepted-hunt-order", desk.choice(OTHER, "order_response"), options=["immediate"]
    )
    choice = desk.choice(OTHER, "trainer_hunt_play")
    with pytest.raises(WorkflowError):
        desk.app.read(PLAYER, desk.scene, "handler-hunt", choice["id"])
    preview = desk.app.read(OTHER, desk.scene, "handler-hunt", choice["id"])
    attacker, defender = preview["actors"]
    assert defender["ref"] == target.model_dump(mode="json")
    attack_id, target_id = attacker["assets"][0]["id"], defender["assets"][0]["id"]
    proposed = desk.write(
        OTHER,
        "declare-hunt",
        action="hunt-declare",
        id=choice["id"],
        revision=preview["revision"],
        attacking_asset=attack_id,
        target_asset=target_id,
        text="I open with the tracked blade against the specified target.",
    )
    assert not desk.view(PLAYER)["hunts"]
    [review] = desk.view(ADMIN)["hunts"]
    assert review["can_confirm"] and review["id"] == proposed["id"]
    decision = dict(
        action="hunt-confirm",
        id=review["id"],
        revision=state(game).revision,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        text="I observed the opening and reach.",
    )
    with pytest.raises(WorkflowError):
        desk.write(OTHER, "not-judge", **decision)
    desk.write(ADMIN, "judge-hunt", **decision)
    [owned] = desk.view(OTHER)["hunts"]
    marked = dict(
        action="hunt-roll",
        id=owned["id"],
        revision=state(game).revision,
        sheet_revision=owned["sheet_revision"],
        heat=0,
        piloting=True,
    )
    action = desk.write(OTHER, "roll-hunt", **marked)
    assert desk.write(OTHER, "roll-hunt", **marked) == action
    desk.flush()
    for member in (ADMIN, PLAYER, OTHER):
        desk.respond(
            member,
            f"hunt-tag:{member.user_id}",
            desk.choice(member, "tag_window"),
            options=["pass"],
        )
    extra = desk.choice(OTHER, "engage_assault_extra")
    assert extra["fields"]
    desk.respond(
        OTHER,
        "earned-hunt-maneuver",
        extra,
        options=["protect"],
        fields={"protect": attack_id},
        text="I cover the withdrawal route.",
    )
    for member in (ADMIN, PLAYER, OTHER):
        desk.respond(
            member,
            f"hunt-table:{member.user_id}",
            desk.choice(member, "battle_assault_table"),
            flag=False,
            text="The defender stays in reach.",
        )
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == target_id).damaged
    assert game.dice.calls == 1


def test_trainer_play_gentle_reaches_the_nominated_girls_own_flirt_answer(ledger):
    _, game = ready(ledger)
    create_trainer(ledger, start_with_speak=True)
    desk = ActivityScene(game)
    issued = desk.write(
        ADMIN,
        "issue-gentle",
        action="conditioning-order",
        id=desk.scene,
        revision=desk.view(ADMIN)["game_revision"],
        target="3",
        phrase="play_gentle",
        text="Approach the person we discussed.",
        counterpart="2",
        actor=None,
    )
    desk.flush()
    desk.respond(
        OTHER, "receive-gentle", desk.choice(OTHER, "order_response"), options=["obedient"]
    )
    choice = desk.choice(OTHER, "trainer_flirt_play")
    desk.write(
        OTHER,
        "start-original-flirt",
        action="signature-child",
        id=choice["id"],
        revision=choice["revision"],
        sheet_revision=choice["sheet_revision"],
        heat=0,
        witnessed=False,
        text="I ask what name she wants to use.",
    )
    desk.flush()
    for viewer in (ADMIN, PLAYER, OTHER):
        desk.respond(
            viewer,
            f"flirt-pass:{viewer.user_id}",
            desk.choice(viewer, "tag_window"),
            options=["pass"],
        )
    desk.respond(OTHER, "ask-original-girl", desk.choice(OTHER, "actor_flirt"), options=["name"])
    reply = desk.choice(PLAYER, "target_flirt")
    with pytest.raises(WorkflowError):
        desk.respond(OTHER, "answer-for-her", reply, text="An invented answer.")
    desk.respond(PLAYER, "my-actual-answer", reply, text="You can call me Lark.")
    assert game.inspect(OTHER, issued["action_id"])["state"] == "complete"
