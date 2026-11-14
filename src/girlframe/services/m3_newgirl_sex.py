"""Human-confirmed group intimacy, genuine printed effects and source discovery."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as bonded
from girlframe.engine import m3_newgirl_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import change, current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _native, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "newgirl_sex_ask",
    "newgirl_sex_respect",
    "newgirl_sex_damage",
    "newgirl_sex_mark",
    "newgirl_sex_enjoyed",
    "newgirl_sex_low",
    "newgirl_sex_damage_wait",
)


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _contact(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Session,
    *,
    lesson_id: str | None = None,
    pending_event: str | None = None,
) -> None:
    from girlframe.services.m3_bonded import admit_delegation
    from girlframe.services.m3_changeling_sex import admit_contact
    from girlframe.services.m3_learned_sex import admit_group_source, admit_offer

    if (
        sum(
            x is not None
            for x in (value.changeling_source, value.bonded_source, value.learned_source, lesson_id)
        )
        > 1
    ):
        raise WorkflowError("Keep actual learned, psychic and Bonded sources separate")
    learned = False
    if value.learned_source is not None:
        learned = admit_group_source(
            game,
            c,
            state,
            value.actor,
            value.partners,
            rules.RULE,
            value.learned_source,
            pending_event=pending_event,
        )
    elif lesson_id is not None:
        learned = admit_offer(game, c, state, value.actor, rules.RULE, lesson_id)
    if value.changeling_source is not None and len(value.partners) != 1:
        raise WorkflowError("SOURCE_GROUP_BRAINS_REQUIRED: bind each actual psychic counterpart")
    remote = False
    if value.changeling_source is not None:
        remote = admit_contact(
            game, c, state, value.actor, value.partners[0], rules.RULE, value.changeling_source
        )

    actors = (value.actor, *value.partners)
    if not value.partners or len(set(actors)) != len(actors):
        raise WorkflowError("Use distinct actual original intimacy participants")
    people = [_native(game, c, state, x) for x in actors]
    if (
        not (
            (learned or has_rule(state.sheets[value.actor.entity], rules.RULE, "NEWGIRL"))
            if value.bonded_source is None
            else (
                admit_delegation(
                    game, c, state, value.actor, value.partners[0], rules.RULE, value.bonded_source
                )
            )
        )
        or value.cast.facilitator is None
        or any(
            x.vessel_id is None or (not remote and (x.inside_frame is not False or x.cell is None))
            for x in people
        )
        or (not remote and len({x.cell for x in people}) != 1)
        or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
        or any(
            value.controllers.get(x.ref.token) != x.controller
            or value.vessels.get(x.ref.token) != x.vessel_id
            or not any(r.actor == x.ref and r.controller == x.controller for r in value.cast.roles)
            for x in people
        )
    ):
        raise WorkflowError(
            "Use actual voluntary original native Girls together outside their Frames"
        )


def _consents(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> tuple[rules.Consent, ...]:
    values = tuple(x for x in rules.records(state, rules.Consent) if x.session == value.id)
    if len({x.person for x in values}) != len(values):
        raise WorkflowError("Preserve each original person's separate voluntary response")
    for item in values:
        if (
            item.person not in value.partners
            or item.controller != value.controllers[item.person.token]
            or item not in rules.records(_history(c, game, item.event), rules.Consent)
        ):
            raise WorkflowError("Recover each actual original person's independent confirmation")
        _audit(game, c, item.event, ("m3.newgirl_sex_confirmed",), item.controller)
    return values


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Session:
    value = rules.get(state, identity)
    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import prove_source_link

        prove_source_link(
            game,
            c,
            state,
            value.changeling_source,
            value.id,
            value.actor,
            value.partners[0],
            rules.RULE,
        )

    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_learned_bonded_newgirl import released_parent

    parent_released = released_parent(game, c, state, value)
    if value.bonded_source is not None and not parent_released:
        prove_delegation(
            game,
            c,
            state,
            value.bonded_source,
            value.id,
            value.actor,
            value.partners[0],
            rules.RULE,
        )
    if value.learned_source is not None:
        from girlframe.services.m3_learned_sex import prove as prove_lesson

        link = prove_lesson(game, c, state, value.learned_source)
        from girlframe.engine.m3_learned_play_state import sex_party_refs

        if (
            not value.partners
            or (link.rule_id, link.session, link.actor)
            != (
                rules.RULE,
                value.id,
                value.actor,
            )
            or sex_party_refs(link) != value.partners
        ):
            raise WorkflowError("Preserve the exact actual learned Newgirl source")
    born = rules.get(_history(c, game, value.proposed_event), identity)
    stable = (
        "id",
        "actor",
        "partners",
        "controllers",
        "vessels",
        "cast",
        "registry",
        "mentors_before",
        "mentor_source",
        "proposed_event",
        "proposal",
        "bonded_source",
        "changeling_source",
        "learned_source",
    )
    if any(getattr(value, k) != getattr(born, k) for k in stable):
        raise WorkflowError("Recover the original private Newgirl source people and proposal")
    _audit(game, c, value.proposed_event, ("m3.newgirl_sex_proposed",), int(value.actor.entity))
    original = _history(c, game, value.proposed_event)
    mentors, source = _source_mentors(
        game,
        c,
        original,
        value.actor,
        value.bonded_source,
        learned_source=value.learned_source,
        proposed_event=value.proposed_event,
    )
    if mentors != value.mentors_before or source != value.mentor_source:
        raise WorkflowError("Preserve the actual source-time Mentor lineage")
    responses = _consents(game, c, state, value)
    if not value.action:
        expected_phase = (
            "declined"
            if any(not x.accepted for x in responses)
            else ("accepted" if {x.person for x in responses} == set(value.partners) else "invited")
        )
        withdrawn_unused = (
            value.phase == "withdrawn"
            and (
                parent_released
                or value.learned_source is not None
                and link.released_kind == "withdrawn"
                and link.released_event is not None
            )
            and value.bound_event is None
            and value.effect_event is None
        )
        if value.phase != expected_phase and not withdrawn_unused:
            raise WorkflowError("Recover the actual independent voluntary confirmation state")
    if value.action:
        if {x.person for x in responses if x.accepted} != set(value.partners) or any(
            not x.accepted for x in responses
        ):
            raise WorkflowError(
                "Every actual participant must voluntarily confirm before the Sex roll"
            )
        action = game.action(c, value.action)
        meta = action["data"].get("newgirl_sex", {})
        bound = rules.get(_history(c, game, value.bound_event or ""), identity)
        if (
            bound.action != value.action
            or bound.bound_event != value.bound_event
            or action["data"]["play"] != rules.PLAY
            or action["data"]["prepared"].get("source_work") != value.id
            or meta.get("session") != value.id
            or meta.get("actor") != value.actor.model_dump(mode="json")
            or meta.get("partners") != [x.model_dump(mode="json") for x in value.partners]
            or meta.get("cast_sha256") != fingerprint(value.cast)
        ):
            raise WorkflowError("Recover the real confirmed original Newgirl Sex Play")
        if value.effect_event:
            _, total = _roll_source(game, c, action)
            from girlframe.engine.m2 import tier

            result = rules.get(_history(c, game, value.effect_event), identity)
            ready = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == value.effect_event,
                    )
                )
                .mappings()
                .first()
            )
            payload = json.loads(ready["payload_json"]) if ready else {}
            final_choice = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == payload.get("choice_id"),
                    )
                )
                .mappings()
                .first()
            )
            if (
                ready is None
                or ready["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
                or payload.get("action_id") != value.action
                or final_choice is None
                or final_choice["action_id"] != value.action
                or final_choice["kind"]
                not in ("tag_window", "tag_resolution", "tag_marker_agreement", "gender_animal_tag")
            ):
                raise WorkflowError(
                    "Recover the actual source Tag or Animal consequence completion"
                )
            _response(
                game,
                c,
                value.action,
                final_choice["id"],
                value.effect_event,
                int(final_choice["actor_id"]),
                final_choice["kind"],
            )
            if (
                value.tier != tier(total)
                or result.effect_event != value.effect_event
                or result.tier != value.tier
            ):
                raise WorkflowError("Recover the real source Sex receipt and Tag-window completion")
            for selected in rules.choices(state, value):
                answer = _response(
                    game,
                    c,
                    value.action,
                    selected.id,
                    selected.event,
                    selected.controller,
                    selected.kind,
                )
                prior = next(
                    (
                        x
                        for x in rules.records(_history(c, game, selected.event), rules.Selection)
                        if x.id == selected.id
                    ),
                    None,
                )
                if (
                    prior != selected
                    or selected.partner not in value.partners
                    or answer.options != selected.options
                    or answer.text != selected.text
                    or answer.denied != ((selected.asset,) if selected.asset else ())
                ):
                    raise WorkflowError(
                        "Preserve each actual original participant's owned printed response"
                    )
                expected = (
                    int(value.actor.entity)
                    if selected.kind
                    in ("newgirl_sex_ask", "newgirl_sex_mark", "newgirl_sex_enjoyed")
                    else value.controllers[selected.partner.token]
                )
                if selected.controller != expected:
                    raise WorkflowError(
                        "A controller cannot speak or choose for another participant"
                    )
    if value.effect_event:
        for partner in value.partners:
            partner_rows = [x for x in rules.choices(state, value) if x.partner == partner]
            expected_kinds = (
                ["newgirl_sex_ask", "newgirl_sex_respect"]
                if value.tier == "mid"
                else ["newgirl_sex_enjoyed", "newgirl_sex_low"]
                if value.tier == "low"
                else ["newgirl_sex_damage", "newgirl_sex_mark"]
                if partner_rows and partner_rows[0].options == ("decline",)
                else ["newgirl_sex_damage"]
            )
            if [x.kind for x in partner_rows] != expected_kinds[: len(partner_rows)] or len(
                partner_rows
            ) > len(expected_kinds):
                raise WorkflowError("Preserve each partner's exact printed result sequence")
            if value.phase == "complete" and len(partner_rows) != len(expected_kinds):
                raise WorkflowError("Complete every actual partner's independent source response")
            for item in partner_rows:
                _prove_effect(game, c, value, item)
    if value.completed_event:
        if not value.action or game.action(c, value.action)["state"] != "complete":
            raise WorkflowError(
                "Preserve the genuine completed source action, not an acknowledgment"
            )
        finished = rules.get(_history(c, game, value.completed_event), identity)
        if finished != value or value.phase != "complete":
            raise WorkflowError("Recover the genuine completed original Sex source")
    return value


def _before(game: GameService, c: Connection, event: str) -> GameState:
    seq = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.seq < seq)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover the actual state preceding this Sex consequence")
    return GameState.model_validate_json(body)


def _prove_effect(
    game: GameService, c: Connection, value: rules.Session, selected: rules.Selection
) -> None:
    before, after = _before(game, c, selected.event), _history(c, game, selected.event)
    if selected.kind == "newgirl_sex_damage" and selected.options == ("damage",):
        original = next(
            (x for x in before.sheets[value.actor.entity].assets if x.id == selected.asset), None
        )
        current = next(
            (x for x in after.sheets[value.actor.entity].assets if x.id == selected.asset), None
        )
        staged = {
            x.get("id")
            for x in after.facts
            if x.get("kind") == "battle_damage_stage"
            and x.get("event") == selected.event
            and x.get("source_action") == value.action
        }
        if (
            original is None
            or original.damaged
            or current is None
            or not set(selected.work) <= staged
            or not current.damaged
            and not selected.work
        ):
            raise WorkflowError(
                "Recover the actual original Asset damage and mandatory source work"
            )
        return
    expected = GameState.model_validate_json(before.model_dump_json())
    if selected.kind == "newgirl_sex_respect" and selected.options == ("yes",):
        expected = change(expected, value.actor, selected.partner, 1, selected.event)
        shift_status(expected, int(value.actor.entity), 1)
    if selected.kind in ("newgirl_sex_mark", "newgirl_sex_low"):
        giver, target = (
            (value.actor, selected.partner)
            if selected.kind == "newgirl_sex_mark"
            else (selected.partner, value.actor)
        )
        if selected.tag is None:
            raise WorkflowError("Recover the actual original human-authored Tag")
        expected = give_tag(
            expected,
            profiles(c, game.store.campaign_id),
            target,
            giver,
            selected.text.strip(),
            selected.tag,
            selected.event,
            tuple(
                sorted(
                    {x.controller for x in value.cast.roles}
                    | ({value.cast.facilitator} if value.cast.facilitator is not None else set())
                )
            ),
        )
        if selected.kind == "newgirl_sex_mark":
            shift_status(expected, int(selected.partner.entity), -1)
        from girlframe.engine.m3_careers import stamp_tag_givers

        expected = stamp_tag_givers(before, expected, selected.event)
    if any(
        getattr(expected, k) != getattr(after, k)
        for k in ("sheets", "order", "bonds", "actor_bonds")
    ):
        raise WorkflowError(
            "Recover the exact real Bond/Status/Tag effect of this owned source response"
        )


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    value = prove(game, c, state, prepared.source_work or "")
    if (
        value.phase != "accepted"
        or value.actor != current_ref(state, viewer.user_id)
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.parent
        or prepared.order_id
        or prepared.off_duty_id
        or channel != value.cast.channel
    ):
        raise WorkflowError("Use the actual fully confirmed original group intimacy source")
    _contact(game, c, state, value)
    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover the actual original Handler source")
    # A later independently owned affirmative answer can deepen this Bond.
    # Body facts cannot be recorded while a Play is pending, so prove the
    # potential Psychic Strings prerequisite before binding or charging a roll.
    from girlframe.services.m3_changeling import preflight_deepening
    from girlframe.services.m3_learned_bonded_newgirl import parent_lesson

    for partner in value.partners:
        preflight_deepening(game, c, state, value.actor, partner)

    delegated_lesson = parent_lesson(state, value)
    return (
        dict(
            session=value.id,
            actor=value.actor.model_dump(mode="json"),
            partners=[x.model_dump(mode="json") for x in value.partners],
            cast=value.cast.model_dump(mode="json"),
            cast_sha256=fingerprint(value.cast),
            table=sorted(
                {x.controller for x in value.cast.roles}
                | ({value.cast.facilitator} if value.cast.facilitator is not None else set())
            ),
            handler=handler.model_dump(mode="json"),
            handler_controller=value.cast.facilitator,
        )
        | ({"learned_source": value.learned_source} if value.learned_source is not None else {})
        | ({"bonded_source": value.bonded_source} if value.bonded_source is not None else {})
        | ({"bonded_lesson": delegated_lesson} if delegated_lesson is not None else {})
        | (
            {"changeling_source": value.changeling_source}
            if value.changeling_source is not None
            else {}
        )
    )


def bind(state: GameState, action: dict[str, Any], event: str | None = None) -> None:
    value = rules.get(state, action["data"]["newgirl_sex"]["session"])
    if event is None or value.action:
        raise WorkflowError("Bind the actual source once to its canonical confirmed Play event")
    rules.put(
        state, value.model_copy(update=dict(action=action["id"], bound_event=event, phase="bound"))
    )


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    if viewer.user_id not in action["data"]["newgirl_sex"]["table"]:
        raise WorkflowError("Only the original source table owns this Sex response")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove(game, c, state, action["data"]["newgirl_sex"]["session"])
    if value.phase != "bound" or value.actor != current_ref(state, viewer.user_id):
        raise WorkflowError("Resume the genuine source without another roll")
    _contact(game, c, state, value)


def sex_parties(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ...]:
    value = rules.get(state, action["data"]["newgirl_sex"]["session"])
    return (value.actor, *value.partners)


def _request(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    value: rules.Session,
    partner: ActorRef,
    kind: str,
) -> None:
    owner = (
        int(value.actor.entity)
        if kind in ("newgirl_sex_ask", "newgirl_sex_mark", "newgirl_sex_enjoyed")
        else value.controllers[partner.token]
    )
    game.request(c, action, owner, kind, dict(partner=partner.model_dump(mode="json")))


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = rules.get(state, action["data"]["newgirl_sex"]["session"])
    if value.effect_event:
        raise WorkflowError("Resume saved source choices; never duplicate the Sex result")
    from girlframe.services.m3_gender_designation import offer_animal_tags

    if offer_animal_tags(game, c, state, action):
        action["data"]["gender_sex_deferred"] = True
        return
    value = value.model_copy(
        update=dict(
            effect_event=action["data"]["response_event"],
            tier=action["data"]["result"]["tier"],
            phase="results",
        )
    )
    rules.put(state, value)
    assert value.tier is not None
    kind = {"mid": "newgirl_sex_ask", "high": "newgirl_sex_damage", "low": "newgirl_sex_enjoyed"}[
        value.tier
    ]
    for partner in value.partners:
        _request(game, c, action, value, partner, kind)


def _pending_work(c: Connection, game: GameService, value: rules.Session, state: GameState) -> bool:
    table = t.m3["m3_required_work"]
    rows = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id)
            .order_by(table.c.revision)
        ).mappings()
    }
    roots = {identity for selection in rules.choices(state, value) for identity in selection.work}
    if any(identity not in rows or rows[identity]["state"] != "resolved" for identity in roots):
        return True
    chain = set(roots)
    while True:
        children = {
            identity
            for identity, row in rows.items()
            if json.loads(row["body_json"]).get("source_work") in chain
        }
        if children <= chain:
            break
        chain |= children
    return any(
        row["state"] != "resolved"
        and json.loads(row["body_json"]).get("immediate")
        and (identity in chain or json.loads(row["body_json"]).get("source_action") == value.action)
        for identity, row in rows.items()
    )


def _finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = rules.get(state, action["data"]["newgirl_sex"]["session"])
    if game.pending(c, action["id"]) or value.phase == "complete":
        return
    if _pending_work(c, game, value, state):
        rules.put(state, value.model_copy(update=dict(phase="damage")))
        return
    value = value.model_copy(update=dict(phase="complete", completed_event=event))
    rules.put(state, value)
    mentors = rules.assigned(state, value)
    if mentors:
        from girlframe.services.m3_mentorship import install_mentors

        install_mentors(
            game,
            c,
            state,
            value.actor,
            mentors,
            session=value.id,
            event=event,
            reason="newgirl_sex_group" if len(value.partners) > 1 else "newgirl_sex_replacement",
        )
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    value = prove(game, c, state, action["data"]["newgirl_sex"]["session"])
    partner = ActorRef.model_validate_json(json.dumps(json.loads(row["body_json"])["partner"]))
    kind, event = row["kind"], action["data"]["response_event"]
    owner = (
        int(value.actor.entity)
        if kind in ("newgirl_sex_ask", "newgirl_sex_mark", "newgirl_sex_enjoyed")
        else value.controllers[partner.token]
    )
    if (
        partner not in value.partners
        or int(row["actor_id"]) != owner
        or answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
    ):
        raise WorkflowError("Use only this exact original participant's owned source response")
    tag, asset = None, None
    work: tuple[str, ...] = ()
    if kind in ("newgirl_sex_ask", "newgirl_sex_enjoyed"):
        if answer.options or answer.denied or not answer.text.strip():
            raise WorkflowError("Author your actual spoken question or enjoyment statement")
        _request(
            game,
            c,
            action,
            value,
            partner,
            "newgirl_sex_respect" if kind == "newgirl_sex_ask" else "newgirl_sex_low",
        )
    elif kind == "newgirl_sex_respect":
        if answer.options not in (("yes",), ("no",)) or answer.denied or not answer.text.strip():
            raise WorkflowError("The actual counterpart answers whether they respect her")
        if answer.options == ("yes",):
            _copy(state, change(state, value.actor, partner, 1, event))
            shift_status(state, int(value.actor.entity), 1)
    elif kind == "newgirl_sex_damage":
        if answer.options not in (("damage",), ("decline",)) or not answer.text.strip():
            raise WorkflowError("The actual counterpart chooses whether to put her in her place")
        if answer.options == ("damage",):
            allowed = {x.id for x in state.sheets[value.actor.entity].assets if not x.damaged}
            if len(answer.denied) != 1 or answer.denied[0] not in allowed:
                raise WorkflowError("Choose one actual undamaged owned Newgirl Asset")
            asset = answer.denied[0]
            from girlframe.services.m3_battle import damage_actor

            changed, work = damage_actor(
                game,
                c,
                state,
                target=value.actor,
                asset_id=asset,
                source_action=action["id"],
                source_work=None,
                event=event,
                actor=partner,
                opponent=partner,
                chooser_controller=owner,
                occurrence="newgirl_sex:" + partner.token,
                physical_blow=True,
            )
            _copy(state, changed)
        else:
            if answer.denied:
                raise WorkflowError("Declining damage does not select an Asset")
            _request(game, c, action, value, partner, "newgirl_sex_mark")
    elif kind in ("newgirl_sex_mark", "newgirl_sex_low"):
        options = () if kind == "newgirl_sex_mark" else answer.options
        if (
            answer.denied
            or not answer.text.strip()
            or len(answer.text.strip()) > 120
            or kind == "newgirl_sex_mark"
            and answer.options
            or kind == "newgirl_sex_low"
            and options not in (("mentor",), ("decline",))
        ):
            raise WorkflowError("Author the real ordinary Tag and your own optional Mentor choice")
        giver, recipient = (
            (value.actor, partner) if kind == "newgirl_sex_mark" else (partner, value.actor)
        )
        tag = str(uuid4())
        _copy(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                recipient,
                giver,
                answer.text.strip(),
                tag,
                event,
                tuple(action["data"]["participants"]),
            ),
        )
        if kind == "newgirl_sex_mark":
            shift_status(state, int(partner.entity), -1)
    else:
        raise WorkflowError("Actual required damage work cannot be replaced with an acknowledgment")
    rules.put(
        state,
        rules.Selection(
            id=row["id"],
            session=value.id,
            action=action["id"],
            partner=partner,
            controller=owner,
            kind=kind,
            options=answer.options,
            text=answer.text,
            asset=asset,
            tag=tag,
            work=work,
            event=event,
        ),
    )
    _finish(game, c, state, action, event)
    return True


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    value = prove(game, c, state, action["data"]["newgirl_sex"]["session"])
    if value.phase != "damage" or _pending_work(c, game, value, state):
        return
    finalized = str(uuid4())
    _finish(game, c, state, action, finalized)
    game.event(
        c,
        value.controllers[value.actor.token],
        "newgirl-damage:" + event,
        "m3.newgirl_sex_completed",
        state,
        event_id=finalized,
        session=value.id,
    )

    if value.changeling_source is not None:
        from girlframe.services.m3_changeling_sex import synchronize_session

        synchronize_session(game, c, state, value.id, finalized)


def prove_mentor_set(game: GameService, c: Connection, state: GameState, record: Any) -> None:
    value = prove(game, c, state, record.session)
    expected = rules.assigned(state, value)
    if (
        value.phase != "complete"
        or not value.completed_event
        or record.learner != value.actor
        or tuple(record.mentors) != expected
        or not expected
        or record.source_event != value.completed_event
        or record.reason
        != ("newgirl_sex_group" if len(value.partners) > 1 else "newgirl_sex_replacement")
    ):
        raise WorkflowError("Recover the genuine completed Sex source's exact actual Mentor set")


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = rules.get(state, action["data"]["newgirl_sex"]["session"])
    partner = ActorRef.model_validate_json(json.dumps(json.loads(row["body_json"])["partner"]))
    kind = row["kind"]
    return dict(
        partner=state.sheets[partner.entity].callsign,
        options=(("yes", "I respect her"), ("no", "I do not respect her"))
        if kind == "newgirl_sex_respect"
        else (
            ("damage", "Damage one actual Asset and become her Mentor"),
            ("decline", "Decline damage"),
        )
        if kind == "newgirl_sex_damage"
        else (("mentor", "Become her Mentor"), ("decline", "Keep the current Mentor relationship"))
        if kind == "newgirl_sex_low"
        else (),
        assets=[
            dict(id=x.id, label=x.name)
            for x in state.sheets[value.actor.entity].assets
            if not x.damaged
        ]
        if kind == "newgirl_sex_damage"
        else [],
        label="Your actual respect question"
        if kind == "newgirl_sex_ask"
        else "Your actual enjoyment statement"
        if kind == "newgirl_sex_enjoyed"
        else "Actual ordinary Tag"
        if kind in ("newgirl_sex_mark", "newgirl_sex_low")
        else "Your actual response/account",
    )


def _discovery(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Discovery:
    value = next((x for x in rules.records(state, rules.Discovery) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original discovery source")
    session = prove(game, c, state, value.session)
    first = next(
        (
            x
            for x in rules.records(_history(c, game, value.event), rules.Discovery)
            if x.id == identity
        ),
        None,
    )
    if (
        first is None
        or any(
            getattr(first, k) != getattr(value, k)
            for k in (
                "id",
                "session",
                "mentor",
                "actor",
                "observer",
                "controller",
                "cast",
                "basis",
                "account",
                "event",
            )
        )
        or value.actor != session.actor
        or value.mentor not in rules.eligible_mentors(state, session)
        or value.observer in (session.actor, *session.partners)
    ):
        raise WorkflowError(
            "Preserve the actual source Mentor intimacy and distinct third-party discovery"
        )
    _audit(game, c, value.event, ("m3.newgirl_sex_disclosed",), int(session.actor.entity))
    if value.learned_event:
        learned = next(
            x
            for x in rules.records(_history(c, game, value.learned_event), rules.Discovery)
            if x.id == identity
        )
        _audit(game, c, value.learned_event, ("m3.newgirl_sex_learned",), value.controller)
        if (
            learned.learned_event != value.learned_event
            or learned.learned_account != value.learned_account
            or not value.learned_account.strip()
        ):
            raise WorkflowError("Preserve the actual original recipient-authored knowledge receipt")
    if value.tag_event:
        tagged = next(
            x
            for x in rules.records(_history(c, game, value.tag_event), rules.Discovery)
            if x.id == identity
        )
        _audit(game, c, value.tag_event, ("m3.newgirl_sex_discovery_tag",), int(value.actor.entity))
        if (
            tagged != value
            or not value.learned_event
            or not value.tag
            or not value.tag_label.strip()
        ):
            raise WorkflowError("Recover the optional original Newgirl-authored actual Mentor Tag")
    return value


class NewgirlSexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        partners: tuple[ActorRef, ...],
        revision: int,
        account: str,
        *,
        bonded_source: str | None = None,
        changeling_source: str | None = None,
        learned_source: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Use the actual idle scene and human-authored voluntary source")
            event, identity = str(uuid4()), str(uuid4())
            mentors, source = _source_mentors(
                self.game,
                c,
                state,
                actor,
                bonded_source,
                learned_source=learned_source,
                proposed_event=event,
            )
            cast = _cast(self.game, c, state, channel)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            people = [
                resolve(state, ref, profiles(c, self.store.campaign_id))
                for ref in (actor, *partners)
            ]
            assert self.store.policy.m3_approval is not None
            value = rules.Session(
                id=identity,
                actor=actor,
                bonded_source=bonded_source,
                changeling_source=changeling_source,
                partners=partners,
                controllers={x.ref.token: x.controller for x in people},
                vessels={x.ref.token: x.vessel_id or "" for x in people},
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                mentors_before=mentors,
                mentor_source=source,
                proposed_event=event,
                proposal=account.strip(),
            )
            _contact(self.game, c, state, value, lesson_id=learned_source)
            if learned_source is not None:
                from girlframe.services.m3_learned_sex import reserve_partner_invitation

                source_link = reserve_partner_invitation(self.game, c, state, value, learned_source)
                value = value.model_copy(update=dict(learned_source=source_link))
            rules.put(state, value)
            if changeling_source is not None:
                from girlframe.services.m3_changeling_sex import bind_source

                bind_source(
                    self.game,
                    c,
                    state,
                    changeling_source,
                    value.id,
                    rules.RULE,
                    value.proposed_event,
                )
            if bonded_source is not None:
                from girlframe.services.m3_bonded import bind_delegation

                bind_delegation(self.game, c, state, bonded_source, value.id, rules.RULE, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_proposed",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, revision=state.revision, phase="invited")

        return self._write(
            viewer,
            key,
            "m3.newgirl_sex_proposed",
            dict(
                channel=channel,
                partners=[x.model_dump(mode="json") for x in partners],
                revision=revision,
                account=account,
            )
            | ({"learned_source": learned_source} if learned_source is not None else {})
            | ({"bonded_source": bonded_source} if bonded_source is not None else {})
            | ({"changeling_source": changeling_source} if changeling_source is not None else {}),
            operation,
        )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        """Owner-only unused source release; never a fictional refusal."""

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)

            if (
                state.revision != expected
                or viewer.user_id != int(value.actor.entity)
                or current_ref(state, viewer.user_id) != value.actor
                or (value.learned_source is None and value.bonded_source is None)
                or (
                    value.bonded_source is not None
                    and bonded.get(state, value.bonded_source).changeling_source is not None
                )
                or value.changeling_source is not None
                or value.phase not in ("invited", "accepted")
                or value.action is not None
                or value.effect_event is not None
                or value.bound_event is not None
            ):
                raise WorkflowError(
                    "Only the original owner may withdraw this unused original invitation"
                )
            actions = t.m2["m2_actions"]
            if c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    sa.or_(
                        sa.func.json_extract(actions.c.body_json, "$.newgirl_sex.session")
                        == identity,
                        sa.func.json_extract(actions.c.body_json, "$.prepared.source_work")
                        == identity,
                    ),
                )
            ):
                raise WorkflowError(
                    "Recover the actual original Action; never refund dice or costs"
                )
            from girlframe.services.m3_learned_sex import withdraw_invitation

            event = str(uuid4())
            if value.learned_source is not None:
                withdraw_invitation(self.game, c, state, value, event)
            rules.put(state, value.model_copy(update={"phase": "withdrawn"}))
            if value.bonded_source is not None:
                from girlframe.services.m3_learned_bonded_newgirl import release

                release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_withdrawn",
                state,
                event_id=event,
                session=identity,
            )
            return dict(id=identity, phase="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.newgirl_sex_withdrawn",
            dict(id=identity, expected=expected),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            actor = current_ref(state, viewer.user_id)
            if (
                value.phase != "invited"
                or state.revision != revision
                or actor not in value.partners
                or value.controllers[actor.token] != viewer.user_id
                or not account.strip()
                or len(account) > 1200
                or any(x.person == actor for x in _consents(self.game, c, state, value))
            ):
                raise WorkflowError(
                    "Only each actual original participant confirms their own voluntary source"
                )
            _contact(self.game, c, state, value)
            event = str(uuid4())
            rules.put(
                state,
                rules.Consent(
                    id=identity + ":" + actor.token,
                    session=identity,
                    person=actor,
                    controller=viewer.user_id,
                    accepted=accept,
                    account=account.strip(),
                    event=event,
                ),
            )
            accepted = {
                x.person
                for x in rules.records(state, rules.Consent)
                if x.session == identity and x.accepted
            }
            phase = (
                "declined"
                if not accept
                else "accepted"
                if accepted == set(value.partners)
                else "invited"
            )
            rules.put(state, value.model_copy(update=dict(phase=phase)))
            from girlframe.services.m3_learned_sex import record_partner_consent

            record_partner_consent(self.game, c, state, rules.get(state, identity), event)
            if not accept and value.bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_learned_bonded_newgirl import release

                # Psychic Pair delegation has a separate source lifecycle. Preserve
                # its actual refusal without claiming this native/learned release.
                if bonded.get(state, value.bonded_source).changeling_source is None:
                    release(self.game, c, state, identity, viewer.user_id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_confirmed",
                state,
                event_id=event,
                session=identity,
            )
            if value.changeling_source is not None:
                from girlframe.services.m3_changeling_sex import synchronize_session

                synchronize_session(self.game, c, state, value.id, event)
            return dict(id=identity, revision=state.revision, phase=phase)

        return self._write(
            viewer,
            key,
            "m3.newgirl_sex_confirmed",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
        )

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        mentor: ActorRef,
        observer: ActorRef,
        revision: int,
        account: str,
        *,
        witness: bool = False,
        channel: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                value.phase != "complete"
                or current_ref(state, viewer.user_id) != value.actor
                or state.revision != revision
                or mentor not in rules.eligible_mentors(state, value)
                or observer in (value.actor, *value.partners)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Use real Mentor intimacy and truthful addressed third-party discovery"
                )
            own, other = (_native(self.game, c, state, x) for x in (value.actor, observer))
            cast = _cast(self.game, c, state, channel)
            if (
                own.cell is None
                or own.cell != other.cell
                or not all(
                    any(x.actor == ref for x in cast.roles) for ref in (value.actor, observer)
                )
            ):
                raise WorkflowError(
                    "Use actual present communication, never invented remote contact"
                )
            if witness:
                original = _history(c, self.game, value.bound_event or "")
                if not any(x.actor == observer for x in value.cast.roles):
                    raise WorkflowError(
                        "The actual witness must have their original source-time role"
                    )
                people = [
                    resolve(
                        original,
                        ref,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    for ref in (value.actor, mentor, observer)
                ]
                if any(x.cell is None for x in people) or len({x.cell for x in people}) != 1:
                    raise WorkflowError("Prove the actual source-time witness co-presence")
            event, found = str(uuid4()), str(uuid4())
            rules.put(
                state,
                rules.Discovery(
                    id=found,
                    session=identity,
                    mentor=mentor,
                    actor=value.actor,
                    observer=observer,
                    controller=other.controller,
                    cast=cast,
                    basis="witness" if witness else "disclosure",
                    account=account.strip(),
                    event=event,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_disclosed",
                state,
                event_id=event,
                discovery=found,
            )
            return dict(id=found, revision=state.revision, phase="learning")

        return self._write(
            viewer,
            key,
            "m3.newgirl_sex_disclosed",
            dict(
                id=identity,
                mentor=mentor.model_dump(mode="json"),
                observer=observer.model_dump(mode="json"),
                revision=revision,
                account=account,
                witness=witness,
                channel=channel,
            ),
            operation,
        )

    def learn(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = _discovery(self.game, c, state, identity)
            if (
                state.revision != revision
                or current_ref(state, viewer.user_id) != value.observer
                or value.controller != viewer.user_id
                or value.learned_event
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original recipient records what they actually learned"
                )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(update=dict(learned_event=event, learned_account=account.strip())),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_learned",
                state,
                event_id=event,
                discovery=identity,
            )
            return dict(id=identity, revision=state.revision, phase="known")

        return self._write(
            viewer,
            key,
            "m3.newgirl_sex_learned",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def discovery_tag(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, label: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = _discovery(self.game, c, state, identity)
            if (
                state.revision != revision
                or current_ref(state, viewer.user_id) != value.actor
                or not value.learned_event
                or not label.strip()
                or len(label) > 120
                or any(
                    x.session == value.session and x.mentor == value.mentor and x.tag
                    for x in rules.records(state, rules.Discovery)
                )
            ):
                raise WorkflowError(
                    "Give at most one actual found-out Tag per Mentor and intimacy occurrence"
                )
            event, tag = str(uuid4()), str(uuid4())
            changed = give_tag(
                state,
                profiles(c, self.store.campaign_id),
                value.mentor,
                value.actor,
                label.strip(),
                tag,
                event,
                (int(value.actor.entity), int(value.mentor.entity)),
            )
            rules.put(
                changed,
                value.model_copy(update=dict(tag=tag, tag_event=event, tag_label=label.strip())),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.newgirl_sex_discovery_tag",
                changed,
                event_id=event,
                discovery=identity,
            )
            return dict(id=identity, revision=changed.revision, phase="tagged")

        return self._write(
            viewer,
            key,
            "m3.newgirl_sex_discovery_tag",
            dict(id=identity, revision=revision, label=label),
            operation,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        from girlframe.services.m3_learned_bonded_newgirl import parent_lesson
        from girlframe.services.m3_learned_sex import cancelled

        for value in rules.records(state, rules.Session):
            if viewer.user_id not in value.controllers.values():
                continue
            consented = {
                x.person for x in rules.records(state, rules.Consent) if x.session == value.id
            }
            pending = not cancelled(
                self.game, c, state, value.learned_source or parent_lesson(state, value)
            ) and (
                value.phase == "invited"
                and any(
                    x not in consented and value.controllers[x.token] == viewer.user_id
                    for x in value.partners
                )
                or value.phase == "accepted"
                and viewer.user_id == int(value.actor.entity)
            )
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    phase="cancelled"
                    if cancelled(
                        self.game, c, state, value.learned_source or parent_lesson(state, value)
                    )
                    else value.phase,
                    can_withdraw=(
                        (
                            value.learned_source is not None
                            or (
                                value.bonded_source is not None
                                and bonded.get(state, value.bonded_source).changeling_source is None
                            )
                        )
                        and value.phase in ("invited", "accepted")
                        and value.action is None
                        and viewer.user_id == int(value.actor.entity)
                    ),
                    label="Your actual Newgirl intimacy and original Mentor source",
                    pending=pending,
                )
            )
        for discovery in rules.records(state, rules.Discovery):
            if viewer.user_id in (int(discovery.actor.entity), discovery.controller):
                result.append(
                    dict(
                        id=discovery.id,
                        revision=state.revision,
                        phase="tagged"
                        if discovery.tag
                        else "known"
                        if discovery.learned_event
                        else "learning",
                        label="Your addressed actual Mentor intimacy discovery",
                        pending=not discovery.learned_event
                        and viewer.user_id == discovery.controller,
                    )
                )
        return result

    def menu(
        self, viewer: GuildViewer, channel: int, *, bonded_source: str | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            options = []
            actor = current_ref(state, viewer.user_id)
            from girlframe.services.m3_learned_sex import lessons

            offered = lessons(self.game, c, state, actor, rules.RULE)
            required_partner = None
            if bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_bonded import admit_delegation

                parent = bonded.get(state, bonded_source)
                if parent.target is None:
                    raise WorkflowError("Preserve the original delegated counterpart")
                admit_delegation(self.game, c, state, actor, parent.target, rules.RULE, parent.id)
                required_partner = parent.target
                offered = ()
            if actor.kind == "pilot" and (
                bonded_source is not None
                or offered
                or has_rule(state.sheets[actor.entity], rules.RULE, "NEWGIRL")
            ):
                cast = _cast(self.game, c, state, channel)
                own = _native(self.game, c, state, actor)
                for role in cast.roles:
                    if role.actor.kind != "pilot" or role.actor == actor:
                        continue
                    try:
                        other = _native(self.game, c, state, role.actor)
                    except (WorkflowError, ValueError):
                        continue
                    if (
                        own.cell is not None
                        and own.cell == other.cell
                        and other.inside_frame is False
                    ):
                        options.append(
                            dict(ref=role.actor.model_dump(mode="json"), label=other.label)
                        )
            from girlframe.engine.m3_mentorship import active_mentors

            return dict(
                revision=state.revision,
                partners=options,
                required_partner=required_partner.model_dump(mode="json")
                if required_partner
                else None,
                history=self._tasks(c, viewer),
                lessons=offered,
                mentors=[x.model_dump(mode="json") for x in active_mentors(state, actor)],
                mentor_names=[
                    state.sheets[x.entity].callsign for x in active_mentors(state, actor)
                ],
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if any(x.id == identity for x in rules.records(state, rules.Discovery)):
                discovery = _discovery(self.game, c, state, identity)
                if viewer.user_id not in (int(discovery.actor.entity), discovery.controller):
                    raise WorkflowError(
                        "Only the original recipient and Newgirl read this discovery"
                    )
                return dict(
                    id=identity,
                    revision=state.revision,
                    kind="discovery",
                    actor=int(discovery.actor.entity),
                    observer=discovery.controller,
                    account=discovery.account,
                    learned=discovery.learned_account,
                    tag=discovery.tag_label,
                    can_learn=not discovery.learned_event
                    and viewer.user_id == discovery.controller,
                    can_tag=bool(discovery.learned_event)
                    and not any(
                        x.session == discovery.session and x.mentor == discovery.mentor and x.tag
                        for x in rules.records(state, rules.Discovery)
                    )
                    and viewer.user_id == int(discovery.actor.entity),
                )
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in value.controllers.values():
                raise WorkflowError(
                    "Only original actual participants read this private intimacy source"
                )
            consents = _consents(self.game, c, state, value)
            from girlframe.services.m3_learned_bonded_newgirl import parent_lesson
            from girlframe.services.m3_learned_sex import cancelled

            ended = cancelled(
                self.game, c, state, value.learned_source or parent_lesson(state, value)
            )
            discovery_targets = []
            if value.phase == "complete" and viewer.user_id == int(value.actor.entity):
                try:
                    cast = _cast(self.game, c, state, value.cast.channel)
                    own = _native(self.game, c, state, value.actor)
                    for role in cast.roles:
                        if role.actor.kind != "pilot" or role.actor in (
                            value.actor,
                            *value.partners,
                        ):
                            continue
                        other = _native(self.game, c, state, role.actor)
                        if own.cell is not None and own.cell == other.cell:
                            discovery_targets.append(
                                dict(ref=role.actor.model_dump(mode="json"), label=other.label)
                            )
                except (WorkflowError, ValueError):
                    pass
            return dict(
                discovery_targets=discovery_targets,
                id=identity,
                revision=state.revision,
                kind="session",
                phase="cancelled" if ended else value.phase,
                actor=int(value.actor.entity),
                proposal=value.proposal,
                channel=value.cast.channel,
                partners=[
                    dict(ref=p.model_dump(mode="json"), label=state.sheets[p.entity].callsign)
                    for p in value.partners
                ],
                can_confirm=not ended
                and value.phase == "invited"
                and any(
                    value.controllers[p.token] == viewer.user_id
                    and p not in {x.person for x in consents}
                    for p in value.partners
                ),
                can_roll=not ended
                and value.phase == "accepted"
                and viewer.user_id == int(value.actor.entity),
                action=value.action,
                outcomes=[x.model_dump(mode="json") for x in rules.choices(state, value)],
                mentors=[x.model_dump(mode="json") for x in rules.eligible_mentors(state, value)]
                if value.phase == "complete"
                else [],
            )


def _source_mentors(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    bonded_source: str | None,
    *,
    learned_source: str | None = None,
    proposed_event: str | None = None,
) -> tuple[tuple[ActorRef, ...], str]:
    from girlframe.services.m3_mentorship import original_mentors

    if learned_source is not None:
        from girlframe.engine.m3_mentorship import active_mentors, current_set

        if bonded_source is not None or proposed_event is None:
            raise WorkflowError("Use the actual separate learned invitation event")
        previous = current_set(state, actor)
        mentors = active_mentors(state, actor)
        if previous is not None:
            prove_mentor_set(game, c, state, previous)
            if mentors != previous.mentors:
                raise WorkflowError("Preserve every actual source-proved original Mentor")
        elif mentors:
            raise WorkflowError("SOURCE_MENTOR_PROVENANCE_REQUIRED: prove the actual relationship")
        return mentors, previous.source_event if previous else proposed_event
    if bonded_source is None:
        return original_mentors(game, c, state, actor, required_rule=rules.RULE)
    from girlframe.engine import m3_bonded as bonded
    from girlframe.engine.m3_mentorship import active_mentors
    from girlframe.services.m3_bonded import admit_delegation

    value = bonded.get(state, bonded_source)
    if value.target is None:
        raise WorkflowError("Use the actual delegated counterpart")
    admit_delegation(game, c, state, actor, value.target, rules.RULE, bonded_source)
    mentors = active_mentors(state, actor)
    if value.learned_source is not None:
        from girlframe.engine.m3_mentorship import current_set

        previous = current_set(state, actor)
        if previous is not None:
            prove_mentor_set(game, c, state, previous)
            if mentors != previous.mentors:
                raise WorkflowError("Preserve the actual learned actor's own Mentor lineage")
        elif mentors:
            raise WorkflowError("SOURCE_MENTOR_PROVENANCE_REQUIRED: prove the actual relationship")
    return mentors, value.event
