"""Source-backed native DoctorDoctor roll and actual owned medical choices."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

PLAYS = {"nanobot_injection": rules.NANO, "doctor_support": rules.SUPPORT}


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


def owned(game: "GameService", c: Connection, state: GameState, actor: ActorRef, rule: str) -> bool:
    registry = Access(game.store).registry
    assert registry is not None
    registry.require_available(rule)
    if rule in (rules.NANO, rules.TRACK):
        rules.sheet(state, actor)
        return True
    receipt = rules.held(state, actor, rule)
    if receipt is None:
        return False
    purchase_proof(c, game.store, receipt)
    return True


def authorize(
    game: "GameService", c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=action is not None)
    if action is None:
        return
    meta = action["data"]["doctor"]
    state = load_state(c, game.store.campaign_id)
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or viewer.user_id not in meta["table"]
        or meta["registry"] != approval.registry_sha256
    ):
        raise WorkflowError("Use this actual original Doctor action's owned source response")
    cast = _cast(game, c, state, int(action["channel_id"]))
    if fingerprint(cast) != meta["cast_sha256"]:
        raise WorkflowError("Recover the original source cast before this Doctor response")
    actor = ActorRef.model_validate(meta["actor"])
    rules.sheet(state, actor, source_frame=meta["frame"] if meta.get("track_event") else None)
    target = ActorRef.model_validate(meta["target"])
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if target.kind == "npc":
        from girlframe.services.m3_doctor_npc import contact as npc_contact
        from girlframe.services.m3_doctor_npc import support_contact

        play = action["data"]["play"]
        contact = (support_contact if play == "doctor_support" else npc_contact)(
            game, c, state, actor, target
        )
        if (
            play not in PLAYS
            or actual.rules != "npc"
            or actual.controller != meta["target_controller"]
            or actual.vessel_id != meta.get("target_vessel")
            or contact != meta.get("npc_contact")
        ):
            raise WorkflowError(
                "Recover the original NPC counterpart, controller and reachable body"
            )


def _legacy_npc(state: GameState, target: ActorRef) -> bool:
    from girlframe.engine.m3_npc_resources import original

    return target.kind == "npc" and original(state, target) is None


def require_nanobot_patient(
    target: ActorRef, game: "GameService", c: Connection, state: GameState
) -> None:
    """Every possible rolled result needs the actual patient's resource provider."""
    if target.kind == "npc":
        from girlframe.services.m3_npc_resources import prove

        prove(game, c, state, target)


def prepare(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    *,
    channel: int,
) -> dict[str, Any]:
    authorize(game, c, viewer)
    actor = current_ref(state, viewer.user_id)
    if (
        prepared.play not in PLAYS
        or prepared.target_actor is None
        or prepared.target is not None
        or prepared.parent
        or prepared.source_work
        or prepared.off_duty_id
        or prepared.order_id
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError("Use the actual native Doctor ability and typed on-screen patient")
    if not owned(game, c, state, actor, PLAYS[prepared.play]):
        raise WorkflowError("Acquire the actual native Doctor ability first")
    target = prepared.target_actor
    if prepared.play == "doctor_support" and target == actor:
        raise WorkflowError("Hide behind another actual person")
    actual = resolve(state, target, profiles(c, game.store.campaign_id))
    contact = None
    if target.kind == "npc":
        from girlframe.services.m3_doctor_care import npc_targets
        from girlframe.services.m3_doctor_npc import contact as npc_contact
        from girlframe.services.m3_doctor_npc import support_contact

        if (
            actual.rules != "npc"
            or actual.offstage_source
            or target.token
            not in {row["token"] for row in npc_targets(game, viewer, channel, state.revision)}
        ):
            raise WorkflowError("Choose an actual visible current NPC patient from this scene")
        contact = (support_contact if prepared.play == "doctor_support" else npc_contact)(
            game, c, state, actor, target
        )
        if prepared.play == "nanobot_injection":
            require_nanobot_patient(target, game, c, state)
    elif target.kind != "pilot" or actual.rules != "girl_frame":
        raise WorkflowError("This native medical port requires an actual original Pilot")
    cast = _cast(game, c, state, channel)
    if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles) or not any(
        x.actor == target and x.controller == actual.controller for x in cast.roles
    ):
        raise WorkflowError("Both actual original people must join this source scene")
    own = resolve(state, actor, profiles(c, game.store.campaign_id))
    if own.cell is not None and actual.cell is not None and own.cell != actual.cell:
        raise WorkflowError("Perform actual reachable care; this Play does not move either body")
    from girlframe.services.m3_battle import _scene_judge

    judge, controller, source = _scene_judge(game, c, state, cast)
    gm, appointment = MedicalService(game.store)._handler(c)
    assert game.store.policy.m3_approval is not None
    if cast.facilitator is None:
        raise WorkflowError("Join the actual scene facilitator before this shared Play")
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        frame=rules.frame_id(state, actor),
        target_controller=actual.controller,
        target_vessel=actual.vessel_id,
        npc_contact=contact,
        actor_controller=viewer.user_id,
        judge=controller,
        judge_actor=judge.model_dump(mode="json") if judge else None,
        judge_source=source,
        procedural_gm=gm,
        appointment=appointment,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted({x.controller for x in cast.roles} | {cast.facilitator}),
        registry=game.store.policy.m3_approval.registry_sha256,
        choices=[],
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    authorize(game, c, viewer, action)
    meta = action["data"]["doctor"]
    actor, target = ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])
    if action["data"]["play"] == "nanobot_injection":
        if meta.get("track_event"):
            raise WorkflowError("The actual Nanobot use already paid its one track mark")
        if (
            actor != target
            and rules.held(state, actor, rules.NURSE) is not None
            and owned(game, c, state, actor, rules.NURSE)
        ):
            _copy(state, rules.nurse(state, actor, target, meta["roll_event"]))
        rules.mark(state, actor, "nanobot_injection", meta["roll_event"])
        meta["track_event"] = meta["roll_event"]


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"]["doctor"]
    level = action["data"]["result"]["tier"]
    target = ActorRef.model_validate(meta["target"])
    if action["data"]["play"] == "doctor_support":
        if level == "low":
            game.request(c, action, meta["judge"], "doctor_handler")
        else:
            if level == "mid":
                rules.put(
                    state,
                    "doctor_protection",
                    rules.Protection(
                        id=action["id"],
                        doctor=ActorRef.model_validate(meta["actor"]),
                        frame=meta["frame"],
                        protector=target,
                        controller=meta["target_controller"],
                        source_action=action["id"],
                        source_event=action["data"].get("response_event", meta["roll_event"]),
                        phase="protecting",
                    ),
                )
            game.request(
                c,
                action,
                meta["target_controller"],
                "doctor_support_response",
                dict(may_refuse=level == "high"),
            )
        return
    if target.kind == "npc":
        from girlframe.services.m3_doctor_npc import award_heat

        amount = (
            5
            if level == "high"
            else int(action["data"]["receipt"]["heat"])
            if level == "mid"
            else 0
        )
        action["data"]["result"]["npc_heat"] = award_heat(
            game,
            c,
            state,
            target,
            amount,
            action["id"],
            action["data"].get("response_event", meta["roll_event"]),
        )
        if level == "low":
            game.request(
                c,
                action,
                meta["target_controller"],
                "doctor_patient",
                dict(repair=1, identity=False),
            )
        else:
            game.request(c, action, meta["actor_controller"], "doctor_nanobot_benefits")
        return
    if level == "low":
        game.request(
            c, action, meta["target_controller"], "doctor_patient", dict(repair=1, identity=False)
        )
    else:
        from girlframe.engine.m3_leviathan_obsession import allowed_gain

        amount = 5 if level == "high" else int(action["data"]["receipt"]["heat"])
        patient = state.sheets[target.entity]
        patient.heat += allowed_gain(state, target, amount, "Nanobot Injection", meta["roll_event"])
        patient.revision += 1
        game.request(c, action, meta["actor_controller"], "doctor_nanobot_benefits")


def effects(state: GameState, target: ActorRef, doctor: int) -> list[dict[str, str]]:
    if target.kind == "npc":
        from girlframe.services.m3_doctor_npc import effects as npc_effects

        return npc_effects(state, target)
    sheet = state.sheets[target.entity]
    from girlframe.engine.m3_beneath import rejection_blocked
    from girlframe.engine.m3_girl_runtime_state import mentor_tag

    result = [
        dict(id="tag:" + x.id, label="Remove Tag: " + x.label)
        for x in sheet.tags
        if doctor in (*x.observers, x.giver, sheet.owner)
        and not mentor_tag(sheet, x, state)
        and not rejection_blocked(state, sheet.owner, x.id)
    ]
    from girlframe.engine.m3_ankou import helpless as ankou_helpless
    from girlframe.services.m3_doctor_stim import effects as stim_effects

    # Generic recovery only clears these actual sources. Other playbook physiology
    # needs its own consumer, not a successful response that leaves the effect intact.
    if (
        sheet.helpless_against
        or any(x.active and x.subject == target for x in state.helpless_conditions)
        or ankou_helpless(state, target)
    ):
        result.append(dict(id="helpless", label="Remove actual Helplessness"))
    result.extend(stim_effects(state, target))
    from girlframe.engine.m3_enforcer import conditioning

    if conditioning(state, target):
        result.append(dict(id="conditioning", label="Remove actual Obedience Conditioning"))
    return result


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    meta = action["data"]["doctor"]
    target = ActorRef.model_validate(meta["target"])
    body = json.loads(row["body_json"])
    if action["data"]["play"] == "doctor_support":
        # Protection does not authorize browsing the counterpart's medical effects.
        return dict(kind=row["kind"], npc=target.kind == "npc")
    if _legacy_npc(state, target):
        return dict(
            kind=row["kind"],
            minimum=1,
            maximum=1,
            effects=effects(state, target, meta["actor_controller"]),
            assets=[],
            identities=[],
            repair=0,
            modular=[],
            identity=False,
            npc=True,
            effect=body.get("effect"),
            unsupported=body.get("unsupported"),
        )
    if target.kind == "npc":
        from girlframe.services.m3_doctor_npc import patient_options

        try:
            available = patient_options(game, c, state, target)
        except (ValueError, WorkflowError) as exc:
            return dict(kind=row["kind"], npc=True, unsupported=str(exc))
        recovered = bool(body.get("unsupported"))
        heat_only = recovered and bool(action["data"]["result"].get("doctor_care"))
        legacy_benefits = recovered and not heat_only and action["data"]["result"]["tier"] != "low"
        repair = body.get("repair", 1 if recovered and not heat_only and not legacy_benefits else 0)
        patient_choice = (
            row["kind"] == "doctor_patient" and int(row["actor_id"]) == meta["target_controller"]
        )
        return dict(
            kind=row["kind"],
            minimum=2 if action["data"]["result"]["tier"] == "high" else 1,
            maximum=2,
            effects=effects(state, target, meta["actor_controller"]),
            assets=[dict(id=x["id"], label=x["name"]) for x in available["assets"] if x["damaged"]]
            if patient_choice and repair
            else [],
            identities=[
                dict(id=x["id"], label=x["name"]) for x in available["identities"] if x["marked"]
            ]
            if patient_choice and body.get("identity")
            else [],
            repair=repair,
            modular=[],
            identity=body.get("identity", False),
            npc=True,
            effect=body.get("effect"),
            heat_only=heat_only,
            legacy_benefits=legacy_benefits,
            unsupported=None,
        )
    patient = state.sheets[target.entity]
    from girlframe.services.m3_modular import repair_options

    return dict(
        kind=row["kind"],
        minimum=2 if action["data"]["result"]["tier"] == "high" else 1,
        maximum=2,
        effects=effects(state, target, meta["actor_controller"]),
        assets=[
            dict(id=x.id, label=x.name)
            for x in patient.assets
            if x.damaged and (x.family == "girl" or not patient.frame_scrapped)
        ],
        identities=[
            dict(id=x.id, label=x.name)
            for x in patient.identities
            if x.marked and x.id not in patient.sedation_locked
        ],
        repair=body.get("repair", 0),
        modular=repair_options(game, c, state, target) if body.get("repair") else [],
        identity=body.get("identity", False),
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    meta = action["data"]["doctor"]
    target = ActorRef.model_validate(meta["target"])
    event = action["data"]["response_event"]
    if row["kind"] == "doctor_handler":
        raise WorkflowError("Complete the actual source-owned Handler Play, not an acknowledgment")
    elif row["kind"] == "doctor_support_response":
        if (
            answer.options not in (("protect",), ("refuse",))
            or set(answer.fields) - {"bond"}
            or answer.denied
            or answer.number is not None
            or answer.member is not None
            or answer.flag is not None
            or answer.text
        ):
            raise WorkflowError("Choose the actual protection decision and optional Bond")
        refusing = answer.options == ("refuse",)
        if refusing and action["data"]["result"]["tier"] != "high":
            raise WorkflowError("The mid result requires actual protection")
        actor = ActorRef.model_validate(meta["actor"])
        rules.put(
            state,
            "doctor_protection",
            rules.Protection(
                id=action["id"],
                doctor=actor,
                frame=meta["frame"],
                protector=target,
                controller=meta["target_controller"],
                source_action=action["id"],
                source_event=event,
                phase="refused" if refusing else "protecting",
            ),
        )
        if answer.fields.get("bond") == "yes" and not refusing:
            from girlframe.engine.m3_actor_bonds import change

            _copy(state, change(state, target, actor, 1, event))
        elif answer.fields.get("bond") not in (None, "no"):
            raise WorkflowError("Only an actual protector may choose to deepen this Bond")
        if refusing:
            game.request(c, action, meta["actor_controller"], "doctor_support_refused")
    elif row["kind"] == "doctor_support_refused":
        if (
            answer.denied
            or answer.fields
            or answer.number is not None
            or answer.member is not None
            or answer.flag is not None
        ):
            raise WorkflowError("Choose only the actual original refusal consequence")
        if answer.options == ("status",) and not answer.text and target.kind == "pilot":
            from girlframe.engine.m2 import shift_status

            shift_status(state, int(target.entity), -1)
        elif answer.options == ("tag",) and answer.text.strip():
            from girlframe.engine.m2 import TagState

            actor = ActorRef.model_validate(meta["actor"])
            if target.kind == "npc":
                from girlframe.engine.m3_mockingbird import give_tag

                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, game.store.campaign_id),
                        target,
                        actor,
                        answer.text,
                        "doctor:" + row["id"],
                        event,
                        tuple(meta["table"]),
                    ),
                )
            else:
                state.sheets[target.entity].tags.append(
                    TagState(
                        id="doctor:" + row["id"],
                        label=answer.text,
                        giver=int(actor.entity),
                        giver_actor=actor,
                        giver_character=actor.incarnation,
                        observers=tuple(meta["table"]),
                    )
                )
        else:
            raise WorkflowError("Give the original NPC a Tag, or lower an actual Pilot's Status")
    elif row["kind"] == "doctor_nanobot_benefits":
        if _legacy_npc(state, target):
            from girlframe.services.m3_doctor_npc import select

            if (
                action["data"]["result"]["tier"] != "mid"
                or answer.options != ("remove",)
                or set(answer.fields) != {"effect"}
                or answer.denied
                or answer.number is not None
                or answer.member is not None
                or answer.flag is not None
                or answer.text
            ):
                raise WorkflowError("Choose the genuine NPC mid-result removal, not sheet benefits")
            npc_selected = select(game, c, state, target, answer.fields["effect"])
            meta["choices"] = ["remove"]
            game.request(
                c, action, meta["target_controller"], "doctor_patient", dict(effect=npc_selected)
            )
            return
        minimum = 2 if action["data"]["result"]["tier"] == "high" else 1
        if (
            len(answer.options) not in range(minimum, 3)
            or len(set(answer.options)) != len(answer.options)
            or not set(answer.options) <= {"repair", "remove", "identity"}
            or set(answer.fields) - {"effect"}
            or answer.denied
            or answer.number is not None
            or answer.member is not None
            or answer.flag is not None
            or answer.text
        ):
            raise WorkflowError("Choose the actual result's distinct Nanobot benefits")
        if "remove" in answer.options:
            selected = answer.fields.get("effect")
            if selected not in {x["id"] for x in effects(state, target, meta["actor_controller"])}:
                raise WorkflowError("Select an actual supported ongoing effect to remove")
            if target.kind == "npc":
                from girlframe.services.m3_doctor_npc import select

                npc_selected = select(game, c, state, target, selected)
            elif selected.startswith("tag:"):
                patient = state.sheets[target.entity]
                patient.tags = [x for x in patient.tags if x.id != selected.removeprefix("tag:")]
                ChoiceEngine(game).tag_resolved(state, patient.owner, selected.removeprefix("tag:"))
                patient.revision += 1
            elif selected.startswith("stim_helpless:"):
                from girlframe.services.m3_doctor_stim import remove

                remove(game, c, state, target, selected, event, action["id"])
            elif selected == "helpless":
                from girlframe.engine.m3_actor_bonds import clear_helpless

                _copy(state, clear_helpless(state, target, event))
            else:
                patient = state.sheets[target.entity]
                state.facts.append(
                    dict(
                        kind="doctor_removed_conditioning",
                        actor=target.model_dump_json(),
                        frame=patient.frame_runtime.id
                        if patient.frame_runtime
                        else "initial:" + str(target.incarnation),
                        event=event,
                        source_action=action["id"],
                    )
                )
        elif answer.fields:
            raise WorkflowError("Do not select an effect without the removal benefit")
        meta["choices"] = list(answer.options)
        game.request(
            c,
            action,
            meta["target_controller"],
            "doctor_patient",
            dict(
                repair=2 if "repair" in answer.options else 0,
                identity="identity" in answer.options,
                **(
                    {"effect": npc_selected}
                    if target.kind == "npc" and "remove" in answer.options
                    else {}
                ),
            ),
        )
    elif row["kind"] == "doctor_patient":
        body = json.loads(row["body_json"])
        if _legacy_npc(state, target):
            from girlframe.services.m3_doctor_npc import remove as remove_npc_drug

            if body.get("unsupported"):
                raise WorkflowError(body["unsupported"])
            if (
                int(row["actor_id"]) != meta["target_controller"]
                or action["data"]["result"]["tier"] != "mid"
                or meta["choices"] != ["remove"]
                or not body.get("effect")
                or answer.options != ("confirm",)
                or answer.denied
                or answer.fields
                or answer.number is not None
                or answer.flag is not None
                or answer.member is not None
                or answer.text
            ):
                raise WorkflowError("Only the original NPC controller confirms this actual removal")
            remove_npc_drug(game, c, state, target, body["effect"], event, action["id"])
            action["data"]["result"]["doctor_care"] = dict(
                patient=target.model_dump(mode="json"),
                benefits=meta["choices"],
                effect=body["effect"]["id"],
                assets=[],
            )
            # Legacy actions may have rolled before NPC admission was closed.
            # Keep their real, confirmed removal, but never certify treatment
            # while the printed Heat award still has no actual resource port.
            heat = action["data"]["result"].get("npc_heat", {})
            required_gain = int(action["data"]["receipt"]["heat"])
            if required_gain > int(heat.get("applied_gain", 0)):
                game.request(
                    c,
                    action,
                    meta["target_controller"],
                    "doctor_patient",
                    dict(
                        unsupported="The confirmed NPC effect removal is preserved, but the "
                        "mandatory Nanobot Heat award remains pending without an actual NPC "
                        "resource outcome port. Do not repeat the removal or invent Heat."
                    ),
                )
            elif not game.pending(c, action["id"]):
                ChoiceEngine(game).finish(c, state, action)
            return
        if target.kind == "npc":
            from girlframe.services.m3_doctor_npc import apply_patient, award_heat

            if (
                answer.denied
                or answer.number is not None
                or answer.flag is not None
                or answer.member is not None
                or answer.text
                or set(answer.fields) - {"identity"}
            ):
                raise WorkflowError("Choose only the actual NPC patient's owned treatment details")
            level = action["data"]["result"]["tier"]
            amount = (
                5
                if level == "high"
                else int(action["data"]["receipt"]["heat"])
                if level == "mid"
                else 0
            )
            action["data"]["result"]["npc_heat"] = award_heat(
                game, c, state, target, amount, action["id"], event
            )
            recovered = bool(body.get("unsupported"))
            heat_only = recovered and bool(action["data"]["result"].get("doctor_care"))
            if recovered and (heat_only or level != "low"):
                if answer.options != ("confirm",) or answer.fields:
                    raise WorkflowError("Confirm recovery of this original NPC result")
                if not heat_only:
                    game.request(c, action, meta["actor_controller"], "doctor_nanobot_benefits")
                    return
            else:
                repair = int(body.get("repair", 1 if recovered else 0))
                legacy_removal = bool(body.get("effect")) and "repair" not in body
                if legacy_removal and (answer.options != ("confirm",) or answer.fields):
                    raise WorkflowError("The original NPC controller confirms the actual removal")
                if not body.get("identity", False) and answer.fields.get("identity"):
                    raise WorkflowError("This result did not select Identity unmarking")
                care = apply_patient(
                    game,
                    c,
                    state,
                    target,
                    assets=() if legacy_removal else answer.options,
                    repair=repair,
                    identity=answer.fields.get("identity"),
                    effect=body.get("effect"),
                    event=event,
                    action=action["id"],
                )
                action["data"]["result"]["doctor_care"] = dict(
                    **care, patient=target.model_dump(mode="json"), benefits=meta["choices"]
                )
            if not game.pending(c, action["id"]):
                ChoiceEngine(game).finish(c, state, action)
            return
        if (
            answer.denied
            or answer.number is not None
            or answer.flag is not None
            or answer.member is not None
            or answer.text
        ):
            raise WorkflowError("Choose only your actual owned Nanobot repair/Identity details")
        if set(answer.fields) - {"identity", "modular"}:
            raise WorkflowError("Choose only an actual Identity")
        from girlframe.engine.m3_modular import Replacement

        replacements: tuple[Replacement, ...] = ()
        if "modular" in answer.fields:
            from pydantic import TypeAdapter

            from girlframe.services.m3_modular import entitlement

            replacements = TypeAdapter(tuple[Replacement, ...]).validate_json(
                answer.fields["modular"]
            )
            if (
                not body["repair"]
                or not replacements
                or not {x.asset for x in replacements} <= set(answer.options)
                or entitlement(game, c, state, target) is None
            ):
                raise WorkflowError(
                    "Use only actual awarded repairs and your own Modular entitlement"
                )
        if body["repair"]:
            before = state.sheets[target.entity].model_copy(deep=True)
            rules.repair(state, target, answer.options, body["repair"])
            if replacements:
                from girlframe.engine.m3_modular import replace_repaired

                replace_repaired(
                    state,
                    target,
                    before,
                    replacements,
                    None,
                    source="doctor:" + action["id"] + ":" + row["id"],
                )
        elif answer.options:
            raise WorkflowError("This result did not select repair")
        if body["identity"]:
            rules.unmark(state, target, answer.fields.get("identity"))
        elif answer.fields.get("identity"):
            raise WorkflowError("This result did not select Identity unmarking")
        action["data"]["result"]["doctor_care"] = dict(
            patient=target.model_dump(mode="json"),
            benefits=meta["choices"],
            assets=list(answer.options),
        )
        if not game.pending(c, action["id"]):
            ChoiceEngine(game).finish(c, state, action)
    else:
        raise WorkflowError("Use the original source-owned Doctor consequence")
    if action["data"]["play"] == "doctor_support" and not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)


def replacement_work(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    event: str,
    context: dict[str, Any],
) -> None:
    sheet = state.sheets.get(actor.entity)
    if sheet is None or not sheet.frame_scrapped or sheet.frame != rules.BOOK:
        return
    identity = str(
        uuid5(
            NAMESPACE_URL,
            "girlframe:doctor-scrap:"
            + actor.token
            + ":"
            + str(sheet.frame_runtime.id if sheet.frame_runtime else "initial"),
        )
    )
    if c.scalar(
        sa.select(t.m3["m3_required_work"].c.id).where(
            t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
            t.m3["m3_required_work"].c.id == identity,
        )
    ):
        return
    related(
        c,
        game.store,
        context,
        identity,
        int(actor.entity),
        int(actor.entity),
        "doctor_frame_replacement",
        dict(
            source_pdf=71,
            immediate=True,
            origin_frame=sheet.frame,
            origin_frame_id=sheet.frame_runtime.id if sheet.frame_runtime else None,
            origin_fingerprint=sheet.source_fingerprint,
            origin_character_id=actor.incarnation,
        ),
        event,
    )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["doctor"]
    if action["data"]["play"] == "doctor_support":
        if action["data"].get("result", {}).get("tier") == "low":
            rows = [x for x in game.pending(c, action["id"]) if x["kind"] == "doctor_handler"]
            if rows and not json.loads(rows[0]["body_json"]).get("handler_grant"):
                from girlframe.services.m3_handler_plays import request_from_play

                state = load_state(c, game.store.campaign_id)
                grant_event = str(uuid4())
                changed, _ = request_from_play(
                    game,
                    c,
                    state,
                    action,
                    rows[0]["id"],
                    "doctor_support.low",
                    grant_event,
                    targets=(ActorRef.model_validate(meta["actor"]),),
                )
                game.event(
                    c,
                    action["actor_id"],
                    str(uuid5(NAMESPACE_URL, "doctor-handler:" + action["id"])),
                    "m3.doctor_handler_required",
                    changed,
                    event_id=grant_event,
                )
        return
    if meta.get("track_event") == event:
        replacement_work(
            game,
            c,
            load_state(c, game.store.campaign_id),
            ActorRef.model_validate(meta["actor"]),
            event,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
        )


class DoctorService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            value = rules.sheet(state, actor)
            result: dict[str, Any] = dict(
                actor=actor.model_dump(mode="json"),
                frame=rules.frame_id(state, actor),
                revision=state.revision,
                sheet_revision=value.revision,
                heat=value.heat,
                permissions=value.permissions,
                track=value.obsolescence_marked,
                choices=[],
                targets=[],
                nurse_targets=[],
                wings_assets=[],
            )
            from girlframe.services.m3_doctor_requisitions import options
            from girlframe.services.m3_doctor_wings import replacements

            result["wings_replacements"] = replacements(state, actor)

            result["acquisitions"], result["held"] = options(self.game, c, state, actor)
            try:
                if owned(self.game, c, state, actor, rules.NANO):
                    result["choices"].append(
                        dict(id="nanobot_injection", label="Nanobot Injection")
                    )
            except (WorkflowError, ValueError):
                pass
            try:
                if owned(self.game, c, state, actor, rules.SUPPORT):
                    result["choices"].append(dict(id="doctor_support", label="Here for Support"))
            except (WorkflowError, ValueError):
                pass
            from girlframe.services.m3_doctor_care import npc_targets

            result["nurse_targets"] = npc_targets(self.game, viewer, channel, state.revision)
            from girlframe.services.m3_doctor_npc import contact as npc_contact
            from girlframe.services.m3_doctor_npc import support_contact

            result["npc_nanobot_targets"] = []
            result["npc_support_targets"] = []
            for row in result["nurse_targets"]:
                if rules.SUPPORT in result["held"]:
                    try:
                        support_contact(
                            self.game, c, state, actor, ActorRef.model_validate(row["ref"])
                        )
                    except (WorkflowError, ValueError):
                        pass
                    else:
                        result["npc_support_targets"].append(row)
                try:
                    npc_contact(self.game, c, state, actor, ActorRef.model_validate(row["ref"]))
                    require_nanobot_patient(
                        ActorRef.model_validate(row["ref"]), self.game, c, state
                    )
                except (WorkflowError, ValueError):
                    continue
                result["npc_nanobot_targets"].append(row)
            cast = _cast(self.game, c, state, channel)
            for role in cast.roles:
                if role.actor.kind != "pilot":
                    continue
                actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                if role.actor != actor and actual.rules == "girl_frame":
                    result["nurse_targets"].append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            token=role.actor.token,
                            label=actual.label,
                        )
                    )
                if actual.rules == "girl_frame":
                    result["targets"].append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            token=role.actor.token,
                            label=actual.label,
                        )
                    )
                    if role.actor != actor:
                        for asset in state.sheets[role.actor.entity].assets:
                            if asset.family == "frame" and asset.damaged:
                                result["wings_assets"].append(
                                    dict(
                                        token=role.actor.token + ":" + asset.id,
                                        ref=role.actor.model_dump(mode="json"),
                                        id=asset.id,
                                        label=actual.label + " — " + asset.name,
                                    )
                                )
            return result
