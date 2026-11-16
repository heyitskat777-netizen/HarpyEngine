"""Native Play exercise for the disposable Director demo; choices are fixture-owned."""

import json


def resolve_keep_trial(
    service,
    game,
    worker,
    gateway,
    dice,
    viewer,
    scene,
    number,
    episode,
    append,
    *,
    source_id,
    source_revision,
    narration,
):
    from test_ledger import ADMIN, OTHER, PLAYER
    from test_m2_game import state, tick

    from girlframe.engine.m2 import ChoiceAnswer, PlayInput
    from girlframe.services.director_adjudication import DirectorAdjudicationService
    from girlframe.services.onboarding import WorkflowError

    # Test RNG schedule only. Neither GM nor Handler providers choose dice faces.
    dice.faces = ((2, 3), (4, 5), (6, 6))[episode]
    old_calls = dice.calls
    prepared = PlayInput(
        play="keep_your_head",
        context=narration,
        trigger_confirmed=True,
        heat=0,
    )
    sheet_revision = state(game).sheets[str(viewer.user_id)].revision
    key = f"trial-play:{number}"
    begun = game.begin(viewer, key, 900, sheet_revision, prepared)
    action = begun["action_id"]
    assert dice.calls == old_calls
    append(
        "Engine",
        "engine_workflow",
        "scene_lock",
        "The Pilot fixture explicitly confirms Keep Your Head, trigger/context and Heat=0. "
        "The engine creates the action; no dice are consumed before the scene lock.",
        action_id=action,
    )
    tick(worker, gateway)
    rolled = game.inspect(viewer, action)
    assert dice.calls == old_calls + 1 and rolled["state"] == "tag_window"
    assert rolled["result"] is None
    append(
        "Engine",
        "engine_workflow",
        "dice_receipt",
        f"Actual engine 2d6 receipt: {rolled['receipt']['faces']}. "
        "Tag responses and printed choices are still pending; no completed outcome yet.",
        action_id=action,
        receipt_id=rolled["receipt"]["id"],
    )

    def submit(author, kind, payload):
        choice = next(x for x in game.choices(author) if x["kind"] == kind)
        command_key = "trial-choice:" + choice["id"]
        result = game.respond(author, command_key, choice["id"], choice["revision"], payload)
        assert (
            game.respond(author, command_key, choice["id"], choice["revision"], payload) == result
        )
        assert dice.calls == old_calls + 1
        return choice["id"]

    for author in (PLAYER, OTHER, ADMIN):
        submit(author, "tag_window", ChoiceAnswer(options=("pass",)))
    append(
        "Participants",
        "scripted_choice",
        "tag_choices",
        "All three test participants explicitly pass their actual Tag-response choices. "
        "The GM supplies no player choice.",
        action_id=action,
    )
    choice = next(x for x in game.choices(viewer) if x["kind"] == "actor_keep")
    decision = game.decision(viewer, choice["id"])
    tier = decision["result"]["tier"]
    payload = {
        "low": ChoiceAnswer(options=("tough",)),
        "mid": ChoiceAnswer(options=("tough", "in_control"), denied=("desperate",)),
        "high": ChoiceAnswer(text=f"SYNTHETIC_EXERCISE_STEADY_{number}"),
    }[tier]
    append(
        "Engine",
        "engine_workflow",
        "actor_choice_required",
        f"The actual {tier}-tier actor_keep choice is pending for the original Pilot. "
        "A rolled tier does not choose the Pilot's traits or Tag.",
        action_id=action,
        choice_id=choice["id"],
    )
    submit(viewer, "actor_keep", payload)
    append(
        "Pilot",
        "scripted_choice",
        "actor_choice",
        "The test Pilot explicitly submits their printed options: " + payload.model_dump_json(),
        action_id=action,
    )
    assert game.inspect(viewer, action)["result"] is None
    try:
        service.review_play(viewer, f"pending-review:{number}", scene, action)
    except WorkflowError as error:
        assert "PLAY_PENDING" in str(error)
    else:
        raise AssertionError("A GM result was allowed before the actual Handler answered")
    handler_choice = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
    adjudicator = DirectorAdjudicationService(service)
    before_judgment = state(game).model_dump_json()
    ruling = adjudicator.adjudicate(
        viewer, f"adjudication:{number}", scene, source_id, source_revision, action
    )
    assert (
        adjudicator.adjudicate(
            viewer, f"adjudication:{number}", scene, source_id, source_revision, action
        )
        == ruling
    )
    assert state(game).model_dump_json() == before_judgment
    proposal = ruling["proposal"]
    append(
        "GM",
        "engine",
        "fictional_adjudication",
        f"Proposed GM ruling: {proposal['verdict']}. {proposal['reasoning']} "
        f"{proposal['narration']} Native owner confirmation is still pending.",
        action_id=action,
        source_refs=proposal["source_refs"],
        disposition=proposal["verdict"],
        adjudication_id=ruling["id"],
    )
    assert proposal["enough"] is not None
    append(
        "Engine",
        "engine_workflow",
        "handler_choice_required",
        "Keep Your Head now requires its original Handler's enough/not-enough ruling. "
        "The engine blocks completion and final GM readback until that owner answers.",
        action_id=action,
        choice_id=handler_choice["id"],
    )
    # The fixture controller confirms the GM-computed verdict, never a tier-based flag.
    submit(
        ADMIN,
        "handler_keep",
        ChoiceAnswer(
            flag=proposal["enough"], text=proposal["reasoning"] + "\n" + proposal["narration"]
        ),
    )
    append(
        "Handler",
        "scripted_choice",
        "required_handler_ruling",
        f"The test Handler controller explicitly confirms the GM's {proposal['verdict']} "
        "ruling through the original handler_keep choice. This is owner confirmation, "
        "not a separately scripted success/failure decision.",
        action_id=action,
    )
    tick(worker, gateway, 5)
    complete = game.inspect(viewer, action)
    assert complete["state"] == "complete" and dice.calls == old_calls + 1
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    before_review = state(game).model_dump_json()
    review = service.review_play(viewer, f"play-review:{number}", scene, action)
    assert service.review_play(viewer, f"play-review:{number}", scene, action) == review
    assert game.begin(viewer, key, 900, sheet_revision, prepared) == begun
    assert game.roll(viewer, "m2.confirmed_roll:" + action, action) == game.roll(
        viewer, "m2.confirmed_roll:" + action, action
    )
    assert state(game).model_dump_json() == before_review and dice.calls == old_calls + 1
    assert "SYNTHETIC_PRIVATE_REQUIRED_HANDLER_OUTCOME" not in json.dumps(review)
    assert review["adjudication_id"] == ruling["id"]
    assert review["verdict"] == proposal["verdict"]
    append(
        "GM",
        "engine",
        "completed_play",
        review["reply"]["text"],
        action_id=action,
        receipt_id=review["proof"]["receipt_id"],
        source_refs=review["reply"]["source_refs"],
        disposition="answer",
        reply_id=review["id"],
    )
    return {
        "proof": review["proof"],
        "review_id": review["id"],
        "play": "keep_your_head",
        "required_handler_choice_id": handler_choice["id"],
        "source_id": review["source_id"],
        "rng_calls": 1,
        "heat_chosen": 0,
        "choices_origin": "explicit_test_owners",
        "adjudication": proposal,
        "adjudication_id": ruling["id"],
        "lock_released": True,
    }
