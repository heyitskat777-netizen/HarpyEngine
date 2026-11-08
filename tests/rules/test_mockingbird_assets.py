"""Call classification preserves source resources and actual current-Frame cap privilege."""

import pytest
from test_actors import bindings
from test_asset_properties import wyvern as wyvern
from test_ledger import ledger as ledger

from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_assets import counts_toward_limit
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_mockingbird_assets import classify


def change(canon, selected, replaced=(), *, step=0, event="actual-call-classification"):
    actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    return classify(
        canon,
        bindings(canon),
        actor,
        selected,
        replaced,
        action="actual-dive",
        step=step,
        event=event,
        account="Actual source Call changes asset families",
    )


def test_intrinsic_moves_both_ways_and_never_grants_girl_or_new_frame_free_slot(wyvern):
    from girlframe.engine.m2 import GameState

    canon = GameState(sheets={"2": wyvern}, order=(2,), handler=1)
    original = next(x for x in wyvern.assets if x.intrinsic)
    moved, _ = change(canon, {original.id: "girl"})
    actual = next(x for x in moved.sheets["2"].assets if x.id == original.id)
    assert actual.family == "girl" and actual.intrinsic == original.intrinsic
    assert actual.classification_event == "actual-call-classification"
    assert counts_toward_limit(moved.sheets["2"], actual)
    restored, _ = change(moved, {original.id: "frame"}, step=1, event="actual-return")
    back = next(x for x in restored.sheets["2"].assets if x.id == original.id)
    assert not counts_toward_limit(restored.sheets["2"], back)
    moved.sheets["2"].frame_runtime = FrameRuntime(
        id="actual-replacement", generation=1, source_work="actual-source-replacement"
    )
    after, _ = change(moved, {original.id: "frame"}, step=2, event="after-real-frame-replacement")
    assert counts_toward_limit(
        after.sheets["2"], next(x for x in after.sheets["2"].assets if x.id == original.id)
    )
    assert original.family == "frame" and original.classification_event is None


def test_batch_swap_and_real_overflow_replacements_are_atomic(wyvern):
    from girlframe.engine.m2 import GameState

    canon = GameState(sheets={"2": wyvern}, order=(2,), handler=1)
    sheet = canon.sheets["2"]
    for i in range(3):
        sheet.assets.append(
            AssetState(
                id="frame-extra-" + str(i), family="frame", name="Actual extra Frame capability"
            )
        )
    girl = next(x for x in sheet.assets if x.family == "girl")
    frame = next(x for x in sheet.assets if x.family == "frame" and not x.intrinsic)
    before = canon.model_dump_json()
    changed, _ = change(canon, {girl.id: "frame", frame.id: "girl"})
    assert len(changed.sheets["2"].assets) == len(sheet.assets)
    assert canon.model_dump_json() == before
    with pytest.raises(ValueError, match="excess"):
        change(canon, {girl.id: "frame"})
    good, _ = change(canon, {girl.id: "frame"}, (frame.id,))
    assert frame.id not in {x.id for x in good.sheets["2"].assets}
    sheet.assets[next(i for i, x in enumerate(sheet.assets) if x.id == frame.id)].void = True
    with pytest.raises(ValueError, match="non-Void"):
        change(canon, {girl.id: "frame"}, (frame.id,))


def test_empty_family_never_becomes_an_all_void_threshold_and_replay_cannot_repeat(wyvern):
    from girlframe.engine.m2 import GameState

    canon = GameState(sheets={"2": wyvern}, order=(2,), handler=1)
    girls = {x.id: "frame" for x in wyvern.assets if x.family == "girl"}
    changed, followups = change(canon, girls)
    assert not any(x.family == "girl" for x in changed.sheets["2"].assets)
    assert not followups
    with pytest.raises(ValueError, match="source step"):
        change(changed, {})
