from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_requisition_state import Installation
from girlframe.engine.m3_requisitions import asset_name, purchase

canon, ledger = canon_fixture, ledger_fixture


def selected(**kwargs):
    return Installation(
        from_frame="THE RED QUEEN",
        index=3,
        description="Actual installed gear",
        account="Actual installation in the Conversation",
        trigger_confirmed=True,
        **kwargs,
    )


def buy(canon, choice=None, identity=None, source=None, ref=None, expected=None):
    actor = ref or ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    return purchase(
        canon,
        actor,
        bindings(canon),
        expected or resolve(canon, actor, bindings(canon)).source_sha256,
        choice or selected(),
        identity or str(uuid4()),
        source or str(uuid4()),
    )


def test_each_printed_base_frame_asset_and_janus_b_label_is_selectable():
    for frame, book in CATALOG.items():
        if book["family"] != "frame":
            continue
        for index, name in enumerate(book["assets"]):
            choice = Installation(
                from_frame=frame,
                index=index,
                description="Gear",
                account="Installed",
                trigger_confirmed=True,
            )
            assert asset_name(choice) == name
    assert (
        asset_name(
            Installation(
                from_frame="JANUS-B",
                index=0,
                description="Gear",
                account="Installed",
                trigger_confirmed=True,
            )
        )
        == CATALOG["JANUS"]["assets"][0]
    )


def test_installation_charges_once_preserves_other_resources_and_records_actual_provenance(canon):
    canon.sheets["2"].permissions = 2
    before = canon.sheets["2"].model_dump()
    state = buy(canon, identity="purchase", source="event")
    acquired = state.sheets["2"].assets[-1]
    assert acquired.name == "The Crown" and acquired.family == "frame"
    assert not acquired.void and not acquired.damaged
    assert state.sheets["2"].permissions == 1 and canon.sheets["2"].model_dump() == before
    assert (
        state.sheets["3"] == canon.sheets["3"]
        and state.order == canon.order
        and state.bonds == canon.bonds
    )
    receipt = state.requisitions[-1]
    assert (
        receipt.source_event == "event" and receipt.price == 1 and receipt.asset_id == acquired.id
    )
    assert receipt.frame_instance == "initial:" + canon.sheets["2"].character_id
    with pytest.raises(ValueError, match="already"):
        buy(state, identity="purchase")
    with pytest.raises(ValueError, match="already"):
        buy(state, source="event")


def test_custom_installation_is_an_asset_and_does_not_grant_playbooks_intrinsic_rules_or_void(
    canon,
):
    canon.sheets["2"].permissions = 1
    old = canon.sheets["2"].model_dump(exclude={"assets", "permissions", "revision"})
    state = buy(
        canon,
        Installation(
            name="My custom gear",
            description="An owner-authored ordinary Asset",
            account="Actually installed",
            trigger_confirmed=True,
        ),
    )
    assert state.sheets["2"].assets[-1].name == "My custom gear"
    assert state.sheets["2"].model_dump(exclude={"assets", "permissions", "revision"}) == old
    assert not state.sheets["2"].assets[-1].void


def test_asset_cap_requires_explicit_non_void_replacement_in_actual_frame_family(canon):
    sheet = canon.sheets["2"]
    sheet.permissions = 3
    while len([x for x in sheet.assets if x.family == "frame"]) < 5:
        sheet.assets.append(AssetState(id=str(uuid4()), name="Extra", family="frame"))
    frame = next(x for x in sheet.assets if x.family == "frame")
    girl = next(x for x in sheet.assets if x.family == "girl")
    frame.void = True
    for replacement in (None, girl.id, frame.id, "foreign"):
        with pytest.raises(ValueError, match="non-Void"):
            buy(canon, selected(replace=replacement))
    legal = next(x for x in sheet.assets if x.family == "frame" and not x.void)
    state = buy(canon, selected(replace=legal.id))
    assert len([x for x in state.sheets["2"].assets if x.family == "frame"]) == 5
    assert any(x.id == frame.id for x in state.sheets["2"].assets)
    assert not any(x.id == legal.id for x in state.sheets["2"].assets)
    assert sheet.permissions == 3


@pytest.mark.parametrize("frame,index", [("MOCKINGBIRD", 0), ("ancillary", 0), ("JANUS", 1000)])
def test_non_frame_ancillary_and_invented_catalog_entries_fail(frame, index):
    with pytest.raises(ValueError):
        asset_name(
            Installation(
                from_frame=frame,
                index=index,
                description="Gear",
                account="Installed",
                trigger_confirmed=True,
            )
        )


@pytest.mark.parametrize(
    "data",
    [
        dict(name="", description="Gear"),
        dict(name="Custom", from_frame="JANUS", index=0, description="Gear"),
        dict(name="Custom", description=" "),
        dict(name="Custom", description="Gear", void=True),
        dict(name="Custom", description="Gear", price=0),
    ],
)
def test_installation_rejects_forged_price_void_unrelated_fields_and_blank_details(data):
    with pytest.raises(ValidationError):
        Installation(**data, account="Actual installation", trigger_confirmed=True)


def test_no_funds_stale_resources_wrong_actor_and_scrapped_frame_preserve_state(canon):
    with pytest.raises(ValueError, match="available Permission"):
        buy(canon)
    canon.sheets["2"].permissions = 1
    with pytest.raises(ValueError, match="STALE_REQUISITION"):
        buy(canon, expected="0" * 64)
    with pytest.raises(ValueError, match="STALE_REQUISITION"):
        buy(canon, ref=ActorRef(kind="npc", entity="2"))
    canon.sheets["2"].frame_scrapped = True
    with pytest.raises(ValueError, match="STALE_REQUISITION"):
        buy(canon)
    assert canon.sheets["2"].permissions == 1 and not canon.requisitions
