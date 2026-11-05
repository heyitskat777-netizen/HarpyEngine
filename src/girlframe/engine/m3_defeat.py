"""Defeat changes actual resources; every further owned consequence remains explicit."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import (
    AssetState,
    GameState,
    IdentityState,
    Obligation,
    pair_key,
    shift_status,
)
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_choices import Context, plan
from girlframe.engine.m3_core import install
from girlframe.engine.m3_defeat_state import Alternative, Consequence, Decision
from girlframe.engine.m3_identity_slots import bind

PLAY: Literal["defeat"] = "defeat"


class Outcome(Model):
    state: GameState
    followups: tuple[Consequence, ...] = ()
    deferred: bool = False


def modifier(state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]) -> int:
    actual = resolve(state, actor, bindings, require_current_profile=False)
    if actor.kind != "pilot" or actual.rules != "girl_frame":
        raise ValueError("Defeat requires the actual original Girl and her surviving resources")
    return sum(x.family == "girl" and not x.damaged for x in actual.assets)


def amnesia(state: GameState, owner: str, slot: int | None, source: str) -> None:
    sheet = state.sheets[owner].model_copy(deep=True)
    from girlframe.engine.m3_leviathan_obsession import require_unlocked

    require_unlocked(sheet.identities, (x.id for x in sheet.identities if not x.protected))
    defaults = CATALOG[sheet.girl]["identities"]
    pair = next((x for x in sheet.identities if x.paired), None)
    if slot is None or (pair is not None and pair.slot == slot):
        raise ValueError(
            "Choose an ordinary starting slot for Amnesiac; preserve the protected Pair"
        )
    extras = [x for x in sheet.identities if x.protected and not x.paired]
    locked = {x.slot for x in sheet.identities if x.id in sheet.sedation_locked}
    if sheet.sedation_locked and not sheet.sedation_period:
        raise ValueError("Recover the actual Sedation period before resetting Identities")
    identities = []
    for index, label in enumerate(defaults):
        if pair is not None and pair.slot == index:
            identities.append(pair)
        else:
            identities.append(
                IdentityState(
                    id=str(uuid5(NAMESPACE_URL, source + ":amnesia:" + str(index))),
                    name="Amnesiac" if index == slot else label,
                    slot=index,
                    marked=index in locked,
                )
            )
    sheet.identities = identities + extras
    sheet.sedation_locked = tuple(
        x.id for x in sheet.identities if x.slot in locked or x.id in sheet.sedation_locked
    )
    sheet.revision += 1
    state.sheets[owner] = sheet


def alternative(state: GameState, actor: ActorRef, offer: Alternative, source: str) -> None:
    offer = Alternative.model_validate_json(offer.model_dump_json())
    sheet = state.sheets[actor.entity]
    if (
        not offer.account.strip()
        or offer.permissions_lost > sheet.permissions
        or len(set(offer.assets_removed)) != len(offer.assets_removed)
        or len(set(offer.identities_removed)) != len(offer.identities_removed)
    ):
        raise ValueError("Review the actual Handler offer against current original resources")
    assets = [x for x in sheet.assets if x.id in offer.assets_removed]
    identities = [x for x in sheet.identities if x.id in offer.identities_removed]
    from girlframe.engine.m3_leviathan_obsession import require_identity_change

    require_identity_change(state, actor, offer.identities_removed)
    if (
        len(assets) != len(offer.assets_removed)
        or any(x.void or x.intrinsic for x in assets)
        or len(identities) != len(offer.identities_removed)
        or any(x.protected for x in identities)
    ):
        raise ValueError("An alternative cannot remove protected or nonexistent resources")
    if not (assets or identities or offer.permissions_lost or offer.tag.strip()):
        raise ValueError("The Handler must offer actual ruinous consequences, not acknowledgement")
    lost_last = any(x.family == "girl" for x in assets) and not any(
        x.family == "girl" and not x.damaged and x.id not in offer.assets_removed
        for x in sheet.assets
    )
    placement = next((x for x in state.placements if x.actor == actor), None)
    outside = placement.mode == "outside_frame" if placement else offer.outside_frame
    if lost_last and outside is None:
        raise ValueError(
            "Confirm the actual original Girl's Frame context before removing her last Asset"
        )
    if lost_last and placement and offer.outside_frame not in (None, outside):
        raise ValueError("The offer cannot contradict the original Girl's known Frame occupancy")
    helpless = lost_last and outside is True
    if helpless:
        if offer.helpless_foe is None or offer.helpless_foe == actor:
            raise ValueError("Removing the last usable Girl Asset requires the actual opposing foe")
        bindings = tuple(
            ProfileBinding(
                owner=x.owner,
                character_id=x.character_id,
                profile_revision=x.source_profile_revision,
            )
            for x in state.sheets.values()
            if x.character_id is not None
        )
        resolve(state, offer.helpless_foe, bindings, require_current_profile=False)
    elif offer.helpless_foe is not None:
        raise ValueError("Helplessness requires the last usable Girl Asset loss outside her Frame")
    sheet.permissions -= offer.permissions_lost
    sheet.assets = [x for x in sheet.assets if x.id not in offer.assets_removed]
    sheet.identities = [x for x in sheet.identities if x.id not in offer.identities_removed]
    sheet.sedation_locked = tuple(
        x for x in sheet.sedation_locked if x not in offer.identities_removed
    )
    if offer.tag.strip():
        from girlframe.engine.m2 import TagState

        assert state.handler is not None
        sheet.tags.append(
            TagState(
                id=source + ":alternative-tag",
                label=offer.tag.strip(),
                giver=state.handler,
                observers=(int(actor.entity), state.handler),
            )
        )
    sheet.revision += 1
    if helpless:
        from girlframe.engine.m3_actor_bonds import make_helpless

        assert offer.helpless_foe is not None
        changed = make_helpless(state, actor, offer.helpless_foe, source)
        for field in GameState.model_fields:
            setattr(state, field, getattr(changed, field))


def apply(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    total: int,
    decision: Decision,
    action: str,
    source_event: str,
    *,
    offer: Alternative | None = None,
    prior_event: str | None = None,
) -> Outcome:
    decision = Decision.model_validate_json(decision.model_dump_json())
    contract = plan(PLAY, Context(total=total))
    contract.groups[0].select("actor", decision.options)
    modifier(original, actor, bindings)
    if not decision.account.strip() or not action or not source_event:
        raise ValueError("Record the actual original Defeat and human-owned consequence")
    if any(
        x.get("kind") == "defeat_resolved" and x.get("action") == action for x in original.facts
    ):
        raise ValueError("This original Defeat has already applied its consequences")
    selected = set(decision.options)
    expected = {
        "girl_asset": "new_girl_and_frame_void_assets_heat4",
        "frame_asset": "new_girl_and_frame_void_assets_heat4",
        "rescuer": "pilot_rescue_deepen_bond",
        "tag_giver": "another_girl_gives_tag",
        "girl_playbook": "change_girl_playbook",
        "amnesiac_slot": "amnesia_reset_and_replace",
    }
    for name, option in expected.items():
        if (getattr(decision, name) is not None) != (option in selected):
            raise ValueError("Supply exactly the details belonging to the selected Defeat effects")
    if "handler_ruinous_alternative" in selected and offer is None:
        if original.handler is None:
            raise ValueError("The actual current Handler must author the alternative")
        return Outcome(
            state=original,
            deferred=True,
            followups=(
                Consequence(
                    kind="alternative",
                    owner=ActorRef(kind="handler", entity=str(original.handler)),
                ),
            ),
        )
    if offer is not None and "handler_ruinous_alternative" not in selected:
        raise ValueError("An unrelated Handler offer cannot alter this result")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets[actor.entity]
    followups: list[Consequence] = []
    if "new_girl_and_frame_void_assets_heat4" in selected:
        for family, chosen in (("girl", decision.girl_asset), ("frame", decision.frame_asset)):
            assert chosen is not None
            from girlframe.engine.m3_janus_storage import ids as stored_ids

            result = install(
                state.sheets[actor.entity],
                AssetState(
                    id=action + ":void:" + family,
                    family="girl" if family == "girl" else "frame",
                    name=chosen.name.strip(),
                    description=chosen.description.strip(),
                    void=True,
                ),
                replace=chosen.replace,
                effective_void=stored_ids(state, actor),
                state=state,
            )
            state.sheets[actor.entity] = result.sheet
            from girlframe.engine.m3_girl_runtime_state import has_rule
            from girlframe.engine.m3_janus_storage import full_family

            if full_family(state, actor, family) and not (
                family == "girl"
                and has_rule(result.sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
            ):
                followups.append(
                    Consequence(
                        kind="void_threshold",
                        owner=actor,
                        source_pdf=19,
                        details={"family": family},
                    )
                )
        sheet = state.sheets[actor.entity]
        from girlframe.engine.m3_leviathan_obsession import allowed_gain

        sheet.heat = min(sheet.heat, 4) + allowed_gain(
            state, actor, max(0, 4 - sheet.heat), "Defeat sets Heat to four", source_event
        )
    if "escape_cockpit_choose_location" in selected:
        from girlframe.engine.m3_physical import escape_cockpit

        state = escape_cockpit(
            state, bindings, actor, source_event, decision.account, prior_event=prior_event
        )
    if "pilot_rescue_deepen_bond" in selected:
        from girlframe.engine.m3_physical import rescue_to_cockpit

        assert decision.rescuer is not None
        rescuer = resolve(state, decision.rescuer, bindings, require_current_profile=False)
        if decision.rescuer.kind != "pilot" or decision.rescuer == actor or not rescuer.alive:
            raise ValueError("Choose another actual surviving Girl to rescue you")
        state = rescue_to_cockpit(
            state,
            bindings,
            actor,
            decision.rescuer,
            source_event,
            decision.account,
            prior_event=prior_event,
        )
        from girlframe.engine.m3_actor_bonds import change as change_bond

        refs = {actor, decision.rescuer}
        key = pair_key(int(actor.entity), int(decision.rescuer.entity))
        if any({edge.first, edge.second} == refs for edge in state.actor_bonds):
            state = change_bond(state, actor, decision.rescuer, 1, source_event)
        elif state.bonds.get(key, 0) >= 2:
            from girlframe.engine.m3_leviathan_obsession import allowed_gain

            for who in (actor.entity, decision.rescuer.entity):
                actual_ref = actor if who == actor.entity else decision.rescuer
                state.sheets[who].heat += allowed_gain(
                    state, actual_ref, 2, "Intense Bond rescue overflow", source_event
                )
                state.sheets[who].revision += 1
        else:
            state.bonds[key] = state.bonds.get(key, 0) + 1
    if contract.level == "high" or "handler_rescue_swap_girl_play_on_waking" in selected:
        from girlframe.engine.m3_physical import handler_rescue

        if state.handler is None:
            raise ValueError("Resolve the original Handler before recording this rescue")
        state = handler_rescue(
            state,
            bindings,
            actor,
            ActorRef(kind="handler", entity=str(state.handler)),
            source_event,
            decision.account,
            prior_event=prior_event,
            injured="handler_rescue_swap_girl_play_on_waking" in selected,
        )
    sheet = state.sheets[actor.entity]
    if "handler_rescue_swap_girl_play_on_waking" in selected:
        sheet.medical_state = "unconscious_injured"
        followups.append(Consequence(kind="medical_wake", owner=actor))
    if "lower_status" in selected:
        shift_status(state, int(actor.entity), -1)
    if "another_girl_gives_tag" in selected:
        assert decision.tag_giver is not None
        if decision.tag_giver == actor or decision.tag_giver.kind != "pilot":
            raise ValueError("Invite another actual Girl to optionally give the Tag")
        resolve(state, decision.tag_giver, bindings, require_current_profile=False)
        followups.append(Consequence(kind="tag_gift", owner=decision.tag_giver))
    if "post_mission_punishment" in selected:
        state.obligations.append(
            Obligation(
                id=action + ":post-mission-punishment",
                kind="punishment",
                owner=int(actor.entity),
                target=state.handler,
                action=action,
                details={
                    "cause": "defeat",
                    "source_pdf": "29",
                    "character_id": str(actor.incarnation),
                },
            )
        )
    if "lose_frame_choose_later" in selected:
        frame_id = (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)
        )
        state.facts.append(
            dict(
                kind="destroyed_frame",
                actor=actor.model_dump_json(),
                frame=frame_id,
                assets=sheet.model_dump_json(),
                action=action,
                source_event=source_event,
            )
        )
        sheet.assets = [x for x in sheet.assets if x.family != "frame"]
        sheet.frame_scrapped = True
        if "death" not in selected:
            followups.append(
                Consequence(
                    kind="frame_replacement",
                    owner=actor,
                    details={"frame": frame_id, "next_off_duty": "true"},
                )
            )
    if "change_girl_playbook" in selected:
        selected_book = decision.girl_playbook
        if (
            selected_book is None
            or selected_book == sheet.girl
            or selected_book not in CATALOG
            or CATALOG[selected_book]["family"] != "girl"
        ):
            raise ValueError("Choose a different enabled base Girl playbook")
        if "amnesia_reset_and_replace" in selected:
            sheet = bind(sheet)
            state.sheets[actor.entity] = sheet
        from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime

        sheet, fact = change_playbook_runtime(sheet, selected_book, source_event)
        state.sheets[actor.entity] = sheet
        state.facts.append(fact)
    if "amnesia_reset_and_replace" in selected:
        if "change_girl_playbook" not in selected:
            state.sheets[actor.entity] = bind(state.sheets[actor.entity])
        amnesia(state, actor.entity, decision.amnesiac_slot, action)
    if offer is not None:
        alternative(state, actor, offer, source_event)
    if "death" in selected:
        followups.append(Consequence(kind="death", owner=actor))
    state.sheets[actor.entity].revision += 1
    state.facts.append(
        dict(
            kind="defeat_resolved",
            action=action,
            actor=actor.model_dump_json(),
            source_event=source_event,
            account=decision.account,
        )
    )
    return Outcome(state=state, followups=tuple(followups))
