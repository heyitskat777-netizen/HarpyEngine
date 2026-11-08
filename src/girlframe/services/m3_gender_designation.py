"""Genuine legal assignments and their owned Orders, intimacy, Tag and discipline effects."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gender_designation as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import ChoiceAnswer, GameState, IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services import m3_advancement_acquisition as acquisition_source
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import (
    HandlerAdvancementService,
    _appointment_at,
    _history,
)
from girlframe.services.m3_handler_pr import _audit
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return acquisition_source.prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the original legal-designation acquisition",
        failure="Preserve its genuine held Award and original Handler source",
    )


def designation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Designation:
    value = next((x for x in rules.designations(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual legal assignment")
    receipt = paid(game, c, state, value.acquisition)
    born_state = _history(c, game, value.event)
    born = next((x for x in rules.designations(born_state) if x.id == identity), None)
    _audit(game, c, value.event, "m3.gender_designated", receipt.handler.entity)
    if born != value or value.actor != current_ref(born_state, int(value.actor.entity)):
        raise WorkflowError("Preserve this original Girl's source-owned legal assignment")
    return value


def _current(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> rules.Designation | None:
    value = rules.current(state, actor)
    return designation(game, c, state, value.id) if value else None


def _native(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> None:
    if actor.kind != "pilot" or current_ref(state, int(actor.entity)) != actor:
        raise WorkflowError("Use the actual current original native Girl")
    view = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    if not view.alive or view.rules != "girl_frame":
        raise WorkflowError("This body needs its genuine legal-designation consumer adapter")


def order_authority(
    game: GameService, c: Connection, state: GameState, issuer: int, target: int
) -> dict[str, Any] | None:
    a, b = current_ref(state, issuer), current_ref(state, target)
    source, animal = _current(game, c, state, a), _current(game, c, state, b)
    if not source or not animal or source.gender == "animal" or animal.gender != "animal":
        return None
    _native(game, c, state, a)
    _native(game, c, state, b)
    return dict(
        issuer=a.model_dump(mode="json"),
        target=b.model_dump(mode="json"),
        issuer_designation=source.id,
        target_designation=animal.id,
    )


def valid_order(game: GameService, c: Connection, state: GameState, row: dict[str, Any]) -> bool:
    body = json.loads(row["body_json"]) if "body_json" in row else row
    source = body.get("gender_designation")
    if not isinstance(source, dict):
        return False
    actual = order_authority(game, c, state, int(row["issuer_id"]), int(row["target_id"]))
    return actual == source


def _sex(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    data = action["data"]
    if data.get("casualty_sex") and data["play"] == "casualty_sex":
        from girlframe.services.m3_casualty import sex_parties

        return sex_parties(state, action)
    if data.get("vatgrown_sex") and data["play"] == "vatgrown_sex":
        from girlframe.engine.m3_vatgrown_plays import get as vatgrown_session

        vatgrown_value = vatgrown_session(state, data["vatgrown_sex"]["session"])
        if vatgrown_value.action != action["id"] or not vatgrown_value.consent_event:
            raise WorkflowError("Recover the actual accepted Vatgrown intimacy source")
        return vatgrown_value.actor, vatgrown_value.target
    if action["data"]["play"] == "alpha_sex" and data.get("alpha_sex"):
        from girlframe.engine.m3_alpha_sex import get

        value = get(state, data["alpha_sex"]["session"])
        if value.action != action["id"] or not value.consent_event:
            raise WorkflowError("Recover the real accepted Alpha intimacy source")
        return value.actor, value.target
    if action["data"]["play"] == "mockingbird_sex" and data.get("mockingbird"):
        meta = data["mockingbird"]
        trigger = next((x for x in state.mockingbird.triggers if x.id == meta["trigger"]), None)
        if trigger is None or trigger.action != action["id"] or trigger.state != "started":
            raise WorkflowError("Recover the real performed original intimacy trigger")
        return trigger.actor, trigger.parties[0].actor
    if data.get("oldgen_sex") and data["play"] == "oldgen_sex":
        from girlframe.engine.m3_oldgen_sex import get as oldgen_session

        original = oldgen_session(state, data["oldgen_sex"]["session"])
        if original.action != action["id"] or not original.consent_event:
            raise WorkflowError("Recover the real accepted Oldgen intimacy source")
        return original.actor, original.target
    if data.get("stim_sex") and data["play"] == "stim_sex":
        from girlframe.engine.m3_stim_sex import get as stim_session

        stim = stim_session(state, data["stim_sex"]["session"])
        if stim.action != action["id"] or not stim.consent_event:
            raise WorkflowError("Recover the real accepted Stim intimacy source")
        return stim.actor, stim.target
    if data.get("princess_sex") and data["play"] == "princess_sex":
        from girlframe.engine.m3_princess_sex import get as princess_session

        princess = princess_session(state, data["princess_sex"]["session"])
        if princess.action != action["id"] or not princess.consent_event:
            raise WorkflowError("Recover the real accepted Princess intimacy source")
        return princess.actor, princess.target
    raise WorkflowError("This actual Sex source needs its legal-designation adapter")


def _sex_pairs(state: GameState, action: dict[str, Any]) -> tuple[tuple[ActorRef, ActorRef], ...]:
    if action["data"].get("newgirl_sex") and action["data"]["play"] == "newgirl_sex":
        from girlframe.services.m3_newgirl_sex import sex_parties

        actor, *partners = sex_parties(state, action)
        return tuple((actor, partner) for partner in partners)
    return (_sex(state, action),)


def _selected_partner(
    state: GameState, action: dict[str, Any], tag_id: str
) -> tuple[ActorRef, ActorRef]:
    matches = [
        (actor, partner)
        for actor, partner in _sex_pairs(state, action)
        if any(x.id == tag_id for x in state.sheets[partner.entity].tags)
    ]
    if len(matches) != 1:
        raise WorkflowError("Choose the actual original participant whose Tag is selected")
    return matches[0]


def man_tag_options(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> list[dict[str, Any]]:
    if action["data"]["play"] not in (
        "alpha_sex",
        "mockingbird_sex",
        "princess_sex",
        "stim_sex",
        "oldgen_sex",
        "casualty_sex",
        "vatgrown_sex",
        "newgirl_sex",
    ):
        return []
    result: list[dict[str, Any]] = []
    for actor, partner in _sex_pairs(state, action):
        value = _current(game, c, state, actor)
        if actor.entity != str(owner) or value is None or value.gender != "man":
            continue
        _native(game, c, state, partner)
        result.extend(
            dict(id=x.id, label=x.label, partner=partner.model_dump(mode="json"))
            for x in state.sheets[partner.entity].tags
            if owner in x.observers
            and x.scene_used != action["scene_id"]
            and not x.rejection_pending
        )
    return result


def propose_man_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services import m3_tag_markers as markers

    if (
        answer.options != ("gender_man",)
        or len(answer.denied) != 1
        or answer.number is not None
        or answer.text
        or answer.member is not None
        or answer.flag is not None
        or set(answer.fields) - {"marker"}
        or answer.denied[0] not in {x["id"] for x in man_tag_options(game, c, state, action, owner)}
    ):
        raise WorkflowError("Choose one actual unused partner Tag for this Man's real Sex Play")
    marker = markers.select(game, c, state, action, owner, answer.fields.get("marker"))
    if marker.actor != current_ref(state, owner):
        raise WorkflowError("The actual Man marks his partner's Tag")
    _, partner = _selected_partner(state, action, answer.denied[0])
    from girlframe.engine.m3_girl_runtime_state import has_rule, relation_current

    sheet = state.sheets[partner.entity]
    if (
        any(x.paired for x in sheet.identities)
        or has_rule(sheet, "girl.bonded.bonded-pair", "BONDED")
        and relation_current(sheet, "pair", state)
    ):
        raise WorkflowError("UNSUPPORTED_RULE: the paired partner-Tag conversion needs its adapter")
    markers.capture(game, c, state, action, marker)


def apply_man_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    marker: Any,
    answer: ChoiceAnswer,
) -> bool:
    if answer.options != ("gender_man",):
        return False
    options = man_tag_options(game, c, state, action, owner)
    if marker.actor != current_ref(state, owner) or answer.denied[0] not in {
        x["id"] for x in options
    }:
        raise WorkflowError("The actual Man, partner or unused Tag changed before arbitration")
    actor, partner = _selected_partner(state, action, answer.denied[0])
    value = _current(game, c, state, actor)
    assert value is not None
    tag = next(x for x in state.sheets[partner.entity].tags if x.id == answer.denied[0])
    from girlframe.services.m2_choices import ChoiceEngine

    engine = ChoiceEngine(game)
    engine.prove_tag_setter(c, state, int(partner.entity), tag)
    old = tag.marked
    tag.marked, tag.scene_used = True, action["scene_id"]
    state.sheets[partner.entity].revision += 1
    action["data"]["gender_man"] = dict(
        applied=True,
        designation=value.id,
        actor=actor.model_dump(mode="json"),
        partner=partner.model_dump(mode="json"),
        tag=tag.id,
        event=action["data"]["response_event"],
    )
    # This is the selected ordinary Tag. It has no second additive modifier.
    action["data"]["tag_marker_applied"] = dict(
        actor=actor.model_dump(mode="json"),
        controller=owner,
        tag=tag.id,
        amount=0,
        source_actor_sha256=marker.source_actor_sha256,
    )
    engine.set_total(action)
    if old:
        game.request(
            c,
            action,
            int(partner.entity),
            "gender_partner_tag_resolution",
            dict(tag=tag.id, partner=partner.model_dump(mode="json")),
        )
    return True


def prove_man_result(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    """Prove the selected post-dice source when a later consumer reconstructs its tier."""
    captured = action["data"].get("gender_man")
    if captured is None:
        return None
    original = _history(c, game, captured["event"])
    actor, partner = _selected_partner(original, action, captured["tag"])
    law = designation(game, c, original, captured["designation"])
    selected = action["data"].get("choices", {}).get("tag_window:" + actor.entity, {})
    tag = next((x for x in original.sheets[partner.entity].tags if x.id == captured["tag"]), None)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == captured["event"],
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    choices = t.m2["m2_choices"]
    selection = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    own_choice = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == action["id"],
                choices.c.kind == "tag_window",
                choices.c.actor_id == actor.entity,
            )
        )
        .mappings()
        .first()
    )
    own_event = None
    if own_choice and audit:
        for response in c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.actor_id == actor.entity,
                t.events.c.kind.in_(("m2.choice_resolved", "m3.choice_resolved")),
                t.events.c.seq <= audit["seq"],
            )
        ).mappings():
            original_answer = json.loads(response["payload_json"])
            if (
                original_answer.get("action_id") == action["id"]
                and original_answer.get("choice_id") == own_choice["id"]
            ):
                own_event = response["id"]
    marker = action["data"].get("tag_marker_applied", {})
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        captured.get("applied") is not True
        or law.gender != "man"
        or law.actor != actor
        or rules.current(original, actor) != law
        or captured.get("actor") != actor.model_dump(mode="json")
        or captured.get("partner") != partner.model_dump(mode="json")
        or selected.get("options") != ["gender_man"]
        or selected.get("denied") != [captured["tag"]]
        or tag is None
        or not tag.marked
        or tag.scene_used != action["scene_id"]
        or int(actor.entity) not in tag.observers
        or marker.get("tag") != tag.id
        or marker.get("actor") != actor.model_dump(mode="json")
        or marker.get("amount") != 0
        or audit is None
        or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or payload.get("action_id") != action["id"]
        or selection is None
        or selection["kind"] != "tag_window"
        or selection["action_id"] != action["id"]
        or selection["state"] != "answered"
        or own_choice is None
        or own_choice["state"] != "answered"
        or own_event is None
        or receipt is None
        or json.loads(receipt) != action["data"]["receipt"]
    ):
        raise WorkflowError(
            "Recover the genuine selected Man's partner-Tag result and unchanged roll"
        )
    return 11


def offer_animal_tags(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not rules.designations(state):
        return False
    if action["data"].get("gender_animal_offered"):
        return any(x.action == action["id"] and x.tag is None for x in rules.gifts(state))
    pairs = _sex_pairs(state, action)
    action["data"]["gender_animal_offered"] = True
    for animal, target in tuple(
        edge for actor, partner in pairs for edge in ((actor, partner), (partner, actor))
    ):
        law, other = _current(game, c, state, animal), _current(game, c, state, target)
        if law is None or law.gender != "animal" or other and other.gender == "animal":
            continue
        _native(game, c, state, animal)
        _native(game, c, state, target)
        value = rules.AnimalGift(
            id=action["id"]
            + ":animal:"
            + animal.token
            + (":" + target.token if len(pairs) > 1 else ""),
            action=action["id"],
            animal=animal,
            target=target,
            designation=law.id,
            event=action["data"]["response_event"],
        )
        rules.put(state, value)
        game.request(c, action, int(animal.entity), "gender_animal_tag", dict(gift=value.id))
    return any(x.action == action["id"] and x.tag is None for x in rules.gifts(state))


def animal_gift(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.AnimalGift:
    value = next((x for x in rules.gifts(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Animal's intimacy source")
    original = _history(c, game, value.event)
    born = next((x for x in rules.gifts(original) if x.id == identity), None)
    action = game.action(c, value.action)
    pairs = _sex_pairs(original, action)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.event,
            )
        )
        .mappings()
        .first()
    )
    law = designation(game, c, original, value.designation)
    counterpart = rules.current(original, value.target)
    if (
        born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "action", "animal", "target", "designation", "event")
        )
        or event is None
        or event["kind"] != "m3.choice_resolved"
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or not any({first, second} == {value.animal, value.target} for first, second in pairs)
        or law.actor != value.animal
        or law.gender != "animal"
        or rules.current(original, value.animal) != law
        or counterpart is not None
        and counterpart.gender == "animal"
    ):
        raise WorkflowError("Preserve the actual original Animal, non-Animal and performed Sex")
    if value.tag:
        tagged = _history(c, game, value.tag_event or "")
        saved = next((x for x in rules.gifts(tagged) if x.id == identity), None)
        tag = next((x for x in tagged.sheets[value.target.entity].tags if x.id == value.tag), None)
        _audit(game, c, value.tag_event or "", "m3.choice_resolved", value.animal.entity)
        if saved != value or tag is None or tag.giver_actor != value.animal:
            raise WorkflowError(
                "Recover the actual owned ordinary Tag, not an intimacy acknowledgment"
            )
    return value


def _resume(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if game.pending(c, action["id"]):
        return
    if action["data"].pop("gender_sex_deferred", False):
        if action["data"]["play"] == "alpha_sex":
            from girlframe.services.m3_alpha_sex import results
        elif action["data"]["play"] == "newgirl_sex":
            from girlframe.services.m3_newgirl_sex import results
        elif action["data"]["play"] == "casualty_sex":
            from girlframe.services.m3_casualty import results
        elif action["data"]["play"] == "vatgrown_sex":
            from girlframe.services.m3_vatgrown_plays import results
        elif action["data"]["play"] == "oldgen_sex":
            from girlframe.services.m3_oldgen_sex import results
        elif action["data"]["play"] == "stim_sex":
            from girlframe.services.m3_stim_sex import results
        elif action["data"]["play"] == "princess_sex":
            from girlframe.services.m3_princess_sex import results
        else:
            from girlframe.services.m3_mockingbird_sex import results
        results(game, c, state, action)
        return
    if action["data"].get("gender_animal_offered"):
        if action["data"]["play"] == "alpha_sex":
            if action["data"]["alpha_sex"]["phase"] != "effects":
                return
            from girlframe.services.m3_alpha_sex import _finish
        elif action["data"]["play"] in (
            "princess_sex",
            "stim_sex",
            "oldgen_sex",
            "newgirl_sex",
            "casualty_sex",
            "vatgrown_sex",
        ):
            # Its actual source choices finish their own phase; a Tag reply does not waive them.
            return
        else:
            from girlframe.services.m3_mockingbird_sex import _finish
        _finish(game, c, state, action)
    else:
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).results(c, state, action)


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    body = json.loads(row["body_json"])
    if row["kind"] == "gender_animal_tag":
        value = animal_gift(game, c, state, body["gift"])
        if (
            value is None
            or value.action != action["id"]
            or value.tag
            or row["actor_id"] != value.animal.entity
            or answer.options
            or answer.denied
            or answer.number is not None
            or answer.fields
            or answer.member is not None
            or answer.flag is not None
            or not answer.text.strip()
            or len(answer.text.strip()) > 120
        ):
            raise WorkflowError("The actual Animal authors one ordinary Tag for its real partner")
        designation(game, c, state, value.designation)
        from girlframe.engine.m3_mockingbird import give_tag

        event, tag_id = action["data"]["response_event"], str(uuid4())
        changed = give_tag(
            state,
            profiles(c, game.store.campaign_id),
            value.target,
            value.animal,
            answer.text.strip(),
            tag_id,
            event,
            observers=tuple(action["data"]["participants"]),
        )
        for name in GameState.model_fields:
            setattr(state, name, getattr(changed, name))
        rules.put(state, value.model_copy(update=dict(tag=tag_id, tag_event=event)))
    elif row["kind"] == "gender_partner_tag_resolution":
        if (
            answer.text
            or answer.fields
            or answer.number is not None
            or answer.flag is not None
            or answer.member is not None
        ):
            raise WorkflowError("Use only the actual partner's ordinary embrace/reject decision")
        partner = ActorRef.model_validate(body["partner"])
        _native(game, c, state, partner)
        if row["actor_id"] != partner.entity:
            raise WorkflowError("The actual partner owns its ordinary repeated-Tag resolution")
        sheet = state.sheets[partner.entity]
        tag = next((x for x in sheet.tags if x.id == body["tag"]), None)
        if tag is None or not tag.marked or tag.scene_used != action["scene_id"]:
            raise WorkflowError("Recover the actual partner Tag marked in this source Play")
        from girlframe.services.m2_choices import ChoiceEngine

        engine = ChoiceEngine(game)
        engine.prove_tag_setter(c, state, int(partner.entity), tag)
        if answer.options == ("reject",):
            from girlframe.engine.m3_beneath import rejection_blocked
            from girlframe.engine.m3_girl_runtime_state import mentor_tag
            from girlframe.services.m3_vatgrown_plays import rejection_allowed

            if (
                not rejection_allowed(state, partner, tag)
                or answer.denied
                or rejection_blocked(state, int(partner.entity), tag.id)
                or mentor_tag(sheet, tag, state)
            ):
                raise WorkflowError("Preserve the actual setter's consent and Mentor restrictions")
            tag.rejection_pending = True
            game.obligation(state, action, "reject_tag", int(partner.entity), tag=tag.id)
        elif answer.options == ("embrace",) and len(answer.denied) == 1:
            from girlframe.engine.m3_leviathan_obsession import require_unlocked

            require_unlocked(sheet.identities, answer.denied)
            old = next(
                (x for x in sheet.identities if x.id == answer.denied[0] and not x.protected), None
            )
            if (
                old is None
                or not engine.duplicate_labels()
                and any(x.name.casefold() == tag.label.casefold() for x in sheet.identities)
            ):
                raise WorkflowError(
                    "Choose a real unprotected Identity with the approved label policy"
                )
            replacement = IdentityState(
                id=str(uuid4()),
                name=tag.label,
                slot=old.slot,
                marked=old.id in sheet.sedation_locked,
            )
            sheet.identities = [x for x in sheet.identities if x.id != old.id] + [replacement]
            if replacement.marked:
                sheet.sedation_locked = tuple(x for x in sheet.sedation_locked if x != old.id) + (
                    replacement.id,
                )
            sheet.tags = [x for x in sheet.tags if x.id != tag.id]
            engine.tag_resolved(state, int(partner.entity), tag.id)
        else:
            raise WorkflowError("Choose the partner's actual embrace or rejection")
        sheet.revision += 1
    else:
        return False
    _resume(game, c, state, action)
    return True


def choice_projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any] | None:
    body = json.loads(row["body_json"])
    if row["kind"] == "gender_animal_tag":
        value = next(x for x in rules.gifts(state) if x.id == body["gift"])
        return dict(
            kind=row["kind"],
            target=value.target.model_dump(mode="json"),
            label="Give your actual non-Animal partner an ordinary Tag",
        )
    if row["kind"] == "gender_partner_tag_resolution":
        partner = ActorRef.model_validate(body["partner"])
        return dict(
            kind=row["kind"],
            tag=body["tag"],
            identities=[
                dict(id=x.id, label=x.name)
                for x in state.sheets[partner.entity].identities
                if not x.protected
            ],
        )
    return None


def _speech_context(
    game: GameService,
    c: Connection,
    state: GameState,
    scene: str,
    speaker: ActorRef,
    man: ActorRef,
    cast: SceneCast | None = None,
) -> tuple[rules.Designation, rules.Designation]:
    _native(game, c, state, speaker)
    _native(game, c, state, man)
    if cast is None:
        from girlframe.services.m3_battle import _cast

        table = t.m2["m2_scenes"]
        channel = c.scalar(
            sa.select(table.c.channel_id).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == scene,
                table.c.open.is_(True),
            )
        )
        if channel is None:
            raise WorkflowError("Use your actual open joined communication scene")
        cast = _cast(game, c, state, int(channel))
    woman, male = _current(game, c, state, speaker), _current(game, c, state, man)
    if (
        speaker == man
        or woman is None
        or male is None
        or woman.gender != "woman"
        or male.gender != "man"
        or cast.id != scene
        or not cast.open
        or not all(
            any(x.actor == ref and x.controller == int(ref.entity) for x in cast.roles)
            for ref in (speaker, man)
        )
    ):
        raise WorkflowError(
            "Record your actual directed in-character No to this real Man in your scene"
        )
    return woman, male


def _stage_no(
    game: GameService,
    c: Connection,
    state: GameState,
    speaker: ActorRef,
    man: ActorRef,
    scene: str,
    event: str,
    account: str,
    action: str | None,
) -> rules.SpeechNo:
    woman, male = _speech_context(game, c, state, scene, speaker, man)
    from girlframe.services.m3_battle import _cast

    table = t.m2["m2_scenes"]
    channel = c.scalar(
        sa.select(table.c.channel_id).where(
            table.c.campaign_id == game.store.campaign_id, table.c.id == scene
        )
    )
    if channel is None:
        raise WorkflowError("Recover your actual open joined speech scene")
    cast = _cast(game, c, state, int(channel))
    owner, appointment = MedicalService(game.store)._handler(c)
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is None or handler.entity != str(owner) or not account.strip():
        raise WorkflowError(
            "Recover the actual current Handler and your actual spoken words/context"
        )
    identity = "gender-no:" + event
    value = rules.SpeechNo(
        id=identity,
        speaker=speaker,
        man=man,
        speaker_designation=woman.id,
        man_designation=male.id,
        handler=handler,
        appointment=appointment,
        scene=scene,
        cast=cast,
        event=event,
        account=account.strip(),
        action=action,
        punishment=identity + ":punishment",
    )
    rules.put(state, value)
    from girlframe.services.m3_intracadre_marriage import allocate_punishment

    allocate_punishment(
        game, c, state, speaker, source_event=event, source_id=value.id, work_id=value.punishment
    )
    return value


def speech(game: GameService, c: Connection, state: GameState, identity: str) -> rules.SpeechNo:
    value = next((x for x in rules.speeches(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this actual original spoken No")
    born_state = _history(c, game, value.event)
    born = next((x for x in rules.speeches(born_state) if x.id == identity), None)
    woman, male = _speech_context(
        game, c, born_state, value.scene, value.speaker, value.man, value.cast
    )
    appointment = _appointment_at(c, game, value.event, value.handler)
    from girlframe.engine.m3_handler_consequences import active_handler

    if (
        born != value
        or woman.id != value.speaker_designation
        or male.id != value.man_designation
        or active_handler(born_state) != value.handler
        or value.appointment != appointment
    ):
        raise WorkflowError(
            "Preserve the actual original speech, assignments and Handler consequence"
        )
    if value.action:
        action = game.action(c, value.action)
        if action["data"].get("gender_no") != dict(id=value.id, event=value.event):
            raise WorkflowError("Recover the real owned response that recorded this spoken No")
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == value.event,
                )
            )
            .mappings()
            .first()
        )
        if (
            audit is None
            or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
            or audit["actor_id"] != value.speaker.entity
        ):
            raise WorkflowError("Recover the actual owned native Order response event")
    else:
        _audit(game, c, value.event, "m3.gender_spoken_no", value.speaker.entity)
    return value


def _materialize_no(
    game: GameService, c: Connection, state: GameState, value: rules.SpeechNo
) -> None:
    speech(game, c, state, value.id)
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id, table.c.id == value.punishment
        )
    ):
        return
    from girlframe.engine import m3_intracadre_marriage as marriage

    allocation = next(
        (x for x in marriage.records(state, marriage.Allocation) if x.source_id == value.id), None
    )
    subject = allocation.subject if allocation else value.speaker
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, scene_id=value.scene),
        value.punishment,
        int(value.handler.entity),
        int(subject.entity),
        "punishment",
        dict(
            reason="gender_woman_no",
            speech=value.id,
            source_event=value.event,
            character=subject.incarnation,
            **marriage.allocation_fields(state, value.id),
            original_handler=value.handler.model_dump(mode="json"),
            immediate=True,
            source_pdf=154,
        ),
        value.event,
    )


def order_no(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], answer: ChoiceAnswer
) -> None:
    if answer.fields.get("spoken_no") != "yes":
        return
    table = t.m2["m2_orders"]
    order = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == action["data"]["order_id"],
            )
        )
        .mappings()
        .one()
    )
    value = _stage_no(
        game,
        c,
        state,
        current_ref(state, int(order["target_id"])),
        current_ref(state, int(order["issuer_id"])),
        action["scene_id"],
        action["data"]["response_event"],
        answer.text,
        action["id"],
    )
    action["data"]["gender_no"] = dict(id=value.id, event=value.event)


def synchronize_no(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    captured = action["data"].get("gender_no")
    if captured and captured["event"] == event:
        state = load_state(c, game.store.campaign_id)
        value = next(x for x in rules.speeches(state) if x.id == captured["id"])
        _materialize_no(game, c, state, value)


def validate_punishment_work(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> None:
    body = json.loads(row["body_json"])
    if body.get("reason") != "gender_woman_no":
        return
    value = speech(game, c, state, body["speech"])
    from girlframe.services.m3_intracadre_marriage import original_offender

    subject = ActorRef(kind="pilot", entity=row["subject_id"], incarnation=body["character"])
    offender = original_offender(game, c, state, value.id, value.event, subject)
    if (
        row["id"] != value.punishment
        or offender != value.speaker
        or body.get("source_event") != value.event
        or body.get("character") != subject.incarnation
        or body.get("original_handler") != value.handler.model_dump(mode="json")
    ):
        raise WorkflowError("Recover the actual source-owned Woman's Punishment")
    table = t.m3["m3_required_work"]
    versions = list(
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == row["id"],
                table.c.revision <= row["revision"],
            )
            .order_by(table.c.revision)
        ).mappings()
    )
    executor = value.handler
    frozen = ("reason", "speech", "source_event", "character", "original_handler")
    if not versions or versions[0]["owner_id"] != executor.entity:
        raise WorkflowError("Preserve the original Handler's actual consequence ownership")
    for version in versions:
        saved = json.loads(version["body_json"])
        if any(saved.get(k) != body.get(k) for k in frozen):
            raise WorkflowError("Preserve the immutable original spoken-No source")
        if version["owner_id"] != executor.entity:
            _audit(game, c, version["event_id"], "m3.punishment_delegated", executor.entity)
            if not saved.get("discipline_owner_character"):
                raise WorkflowError("Recover the actual delegated original Pilot")
            executor = ActorRef(
                kind="pilot",
                entity=version["owner_id"],
                incarnation=saved["discipline_owner_character"],
            )
    if executor.entity != row["owner_id"]:
        raise WorkflowError("Recover this actual consequence executor")
    # Completed Execution may genuinely end the original. Its source is historical.
    if row["state"] != "resolved":
        if executor == value.handler and not same_handler_body(state, value.handler):
            raise WorkflowError(
                "The original Handler's consequence cannot be claimed by a successor"
            )
        if current_ref(state, int(value.speaker.entity)) != value.speaker:
            raise WorkflowError("The actual original Woman must receive this consequence")
        if executor.kind == "pilot" and current_ref(state, int(executor.entity)) != executor:
            raise WorkflowError("The actual delegated Pilot must execute this consequence")


def complete_punishment(game: GameService, c: Connection, row: dict[str, Any], event: str) -> None:
    from girlframe.services.m3_girl_insurance import _before

    table = t.m3["m3_required_work"]
    resolved = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == row["id"],
                table.c.event_id == event,
                table.c.state == "resolved",
            )
        )
        .mappings()
        .first()
    )
    if resolved is None or json.loads(resolved["body_json"]).get("applied_event") != event:
        raise WorkflowError("Complete only the genuine canonical Punishment application")
    validate_punishment_work(game, c, _before(game, c, event), row)


class GenderDesignationService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "playbooks", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, handler, appointment, award = acquisition_source.held(
                self.game,
                c,
                viewer,
                award_id,
                revision,
                account,
                failure="Spend one genuine held Award on unowned Gender Designation Request",
            )
            if any(same_handler_body(state, x.handler) for x in rules.acquisitions(state)):
                raise WorkflowError("The original Handler already owns this advancement")
            event = str(uuid4())
            value = rules.Acquisition(
                id="gender-designation:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            acquisition_source.record_spend(state, award, value, rules.RULE)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="held")

        return self._write(
            viewer,
            key,
            "m3.gender_designation_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
        )

    def designate(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        subjects: tuple[ActorRef, ...],
        gender: rules.Gender,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            receipt = paid(self.game, c, state, acquisition)
            HandlerAdvancementService(self.store)._current(
                c, state, receipt.handler, receipt.appointment
            )
            if (
                viewer.user_id != int(receipt.handler.entity)
                or state.revision != revision
                or not subjects
                or len(set(subjects)) != len(subjects)
                or not account.strip()
                or gender not in ("man", "woman", "animal")
            ):
                raise WorkflowError(
                    "The original Handler assigns selected actual current Cadre Girls"
                )
            event, values = str(uuid4()), []
            for ref in subjects:
                _native(self.game, c, state, ref)
                value = rules.Designation(
                    id=str(uuid4()),
                    acquisition=receipt.id,
                    actor=ref,
                    gender=gender,
                    event=event,
                    controller=int(ref.entity),
                    account=account.strip(),
                )
                rules.put(state, value)
                values.append(value.id)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gender_designated",
                state,
                event_id=event,
                designation_ids=values,
            )
            return dict(ids=values, gender=gender)

        return self._write(
            viewer,
            key,
            "m3.gender_designated",
            dict(
                acquisition=acquisition,
                revision=revision,
                subjects=[x.model_dump(mode="json") for x in subjects],
                gender=gender,
                account=account,
            ),
            operation,
        )

    def record_no(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        scene: str,
        man: ActorRef,
        account: str,
        source_action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or source_action is not None:
                raise WorkflowError(
                    "Record your own current speech; linked Orders use their actual response"
                )
            event = str(uuid4())
            value = _stage_no(
                self.game,
                c,
                state,
                current_ref(state, viewer.user_id),
                man,
                scene,
                event,
                account,
                None,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gender_spoken_no",
                state,
                event_id=event,
                speech_id=value.id,
            )
            _materialize_no(self.game, c, state, value)
            return dict(id=value.id, punishment=value.punishment)

        return self._write(
            viewer,
            key,
            "m3.gender_spoken_no",
            dict(
                revision=revision,
                scene=scene,
                man=man.model_dump(mode="json"),
                account=account,
                source_action=source_action,
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            gift = next((x for x in rules.gifts(state) if x.id == identity), None)
            if gift:
                gift_value = animal_gift(self.game, c, state, gift.id)
                if str(viewer.user_id) not in (gift_value.animal.entity, gift_value.target.entity):
                    raise WorkflowError("This is private original intimacy history")
                return dict(
                    kind="gift", revision=state.revision, **gift_value.model_dump(mode="json")
                )
            own_law = next((x for x in rules.designations(state) if x.id == identity), None)
            if own_law:
                designation(self.game, c, state, own_law.id)
                if own_law.actor.entity != str(viewer.user_id):
                    raise WorkflowError("Open your own actual legal-designation control")
                identity = None
            heard = next((x for x in rules.speeches(state) if x.id == identity), None)
            if heard:
                value = speech(self.game, c, state, heard.id)
                if str(viewer.user_id) not in (
                    value.handler.entity,
                    value.speaker.entity,
                    value.man.entity,
                ):
                    raise WorkflowError("This is private original speech history")
                return dict(
                    kind="speech",
                    revision=state.revision,
                    **value.model_dump(mode="json", exclude={"cast"}),
                )
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
                and (identity is None or x.id == identity)
            ]
            held = [
                x
                for x in awards.awards(state)
                if x.phase == "held"
                and x.handler.entity == str(viewer.user_id)
                and (identity is None or x.id == identity)
            ]
            if identity and not receipts and not held:
                raise WorkflowError("Recover your own actual original acquisition or held Award")
            girls = []
            if receipts:
                for sheet in state.sheets.values():
                    if sheet.owner == state.handler:
                        continue
                    ref = current_ref(state, sheet.owner)
                    _native(self.game, c, state, ref)
                    girls.append(
                        dict(
                            ref=ref.model_dump(mode="json"),
                            token=ref.token,
                            label=sheet.callsign,
                            **rules.presentation(state, ref),
                        )
                    )
            scenes = []
            own = next(
                (x for x in rules.designations(state) if x.actor.entity == str(viewer.user_id)),
                None,
            )
            woman = own and rules.current(state, own.actor)
            from girlframe.services.m3_battle import _cast

            scene_table = t.m2["m2_scenes"]
            scene_rows = c.execute(
                sa.select(scene_table).where(
                    scene_table.c.campaign_id == self.store.campaign_id,
                    scene_table.c.open.is_(True),
                )
            ).mappings()
            for scene_row in scene_rows:
                if viewer.user_id not in json.loads(scene_row["participants_json"]):
                    continue
                cast = _cast(self.game, c, state, int(scene_row["channel_id"]))
                if (
                    woman
                    and woman.gender == "woman"
                    and cast.open
                    and any(
                        x.actor.kind == "pilot"
                        and x.actor.entity == str(viewer.user_id)
                        and x.controller == viewer.user_id
                        for x in cast.roles
                    )
                ):
                    men = [
                        dict(
                            ref=x.actor.model_dump(mode="json"),
                            token=x.actor.token,
                            label=state.sheets[x.actor.entity].callsign,
                        )
                        for x in cast.roles
                        if x.actor.kind == "pilot"
                        and rules.current(state, x.actor)
                        and rules.presentation(state, x.actor)["legal_gender"] == "man"
                    ]
                    if men:
                        scenes.append(dict(id=cast.id, channel=cast.channel, men=men))
            return dict(
                kind="acquisition",
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                girls=girls,
                scenes=scenes,
                awards=[dict(id=x.id, label=x.account) for x in held],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        tasks = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Gender Designation Request acquired",
                phase="held",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        tasks += [
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual spoken No — Punishment source",
                phase="recorded",
                pending=False,
            )
            for x in rules.speeches(state)
            if str(viewer.user_id) in (x.handler.entity, x.speaker.entity, x.man.entity)
        ]
        for sheet in state.sheets.values():
            if sheet.owner == viewer.user_id:
                value = rules.current(state, current_ref(state, viewer.user_id))
                if value and value.gender == "woman":
                    tasks.append(
                        dict(
                            id=value.id,
                            revision=state.revision,
                            label="Legal Woman — my actual speech controls",
                            phase="established",
                            pending=False,
                        )
                    )
        tasks += [
            dict(
                id=x.id,
                revision=state.revision,
                label="Animal's actual ordinary Tag source",
                phase="given" if x.tag else "awaiting_owned_tag",
                pending=False,
            )
            for x in rules.gifts(state)
            if str(viewer.user_id) in (x.animal.entity, x.target.entity)
        ]
        return tasks
