"""Source-backed transitions; every voluntary choice is supplied by its human owner."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import (
    FLIRT_QUESTIONS,
    MANEUVERS,
    QUESTIONS,
    TRAITS,
    ChoiceAnswer,
    GameState,
    IdentityState,
    PilotSheet,
    TagState,
    higher,
    pair_key,
    shift_status,
    tier,
)
from girlframe.engine.m3_girl_runtime_state import (
    has_rule,
    keep_automatic,
    mentor_tag,
    relation_current,
)
from girlframe.engine.m3_intracadre_marriage import is_dog
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def picks(
    values: tuple[str, ...], allowed: set[str], minimum: int, maximum: int | None = None
) -> None:
    require(
        minimum <= len(values) <= (minimum if maximum is None else maximum)
        and set(values) <= allowed,
        "Choose the exact legal options for this result.",
    )


class ChoiceEngine:
    def __init__(self, game: "GameService"):
        self.game = game

    def duplicate_labels(self) -> bool:
        policy = self.game.store.policy
        return bool(
            policy.m3_approval is not None
            and policy.owner_m3_rulings is not None
            and policy.owner_m3_rulings.identity_duplicate_labels == "distinct_ids"
        )

    def add_tag(
        self, state: GameState, action: dict[str, Any], owner: int, giver: int, label: str
    ) -> TagState:
        require(bool(label.strip()), "A human-authored Tag label is required.")
        tag = TagState(
            id=str(uuid4()),
            label=label.strip(),
            giver=giver,
            observers=tuple(action["data"]["participants"]),
        )
        state.sheets[str(owner)].tags.append(tag)
        state.sheets[str(owner)].revision += 1
        return tag

    def prove_tag_setter(self, c: Connection, state: GameState, owner: int, tag: TagState) -> None:
        from girlframe.services.m3_cute_uniforms import prove_tag

        prove_tag(self.game, c, state, owner, tag)
        from girlframe.services.m3_bomb_collar import prove_tag as prove_collar_tag

        prove_collar_tag(self.game, c, state, owner, tag)
        if tag.id.startswith(("stim-sex-drug:", "stim-sex-effect:")):
            from girlframe.services.m3_stim_sex import prove_drug_tag as prove_stim_tag

            prove_stim_tag(self.game, c, state, owner, tag)
        if tag.id.startswith("dose-up:"):
            from girlframe.services.m3_dose_up import prove_tag as prove_drug_tag

            prove_drug_tag(self.game, c, state, owner, tag)
        if tag.gm_setter_appointment is not None or tag.gm_setter_event is not None:
            from girlframe.engine.m3_actor_bonds import current_ref
            from girlframe.services.m3_tag_setters import ooc_setter

            ooc_setter(c, self.game.store, current_ref(state, owner), tag)

    def tag_resolved(self, state: GameState, owner: int, tag: str) -> None:
        from girlframe.engine.m3_control_ritual import remove

        remove(state, owner, tag)
        for item in state.obligations:
            if (
                item.owner == owner
                and item.details.get("tag") == tag
                and item.kind in ("reject_tag", "cannot_refuse_until_tag_resolved")
            ):
                item.state = "fulfilled"

    def malleable_resolved(
        self, c: Connection, state: GameState, owner: int, tag: str, event: str
    ) -> None:
        """Consume this source's actual Tag resolution without another human's answer."""
        from girlframe.engine import m3_malleable as malleable
        from girlframe.services.m3_malleable import prove_birth

        birth = prove_birth(self.game, c, state, tag)
        performed = next(
            (
                x
                for x in malleable.records(state, malleable.Forced)
                if x.birth == tag and x.event == event
            ),
            None,
        )
        sheet = state.sheets.get(str(owner))
        require(
            birth.recipient.kind == "pilot"
            and birth.recipient.entity == str(owner)
            and performed is not None
            and sheet is not None
            and not any(x.id == tag for x in sheet.tags),
            "Resolve only this actual giver-forced consumed Tag.",
        )
        table = t.m2["m2_choices"]
        touched = {}
        for row in c.execute(
            sa.select(table).where(
                table.c.campaign_id == self.game.store.campaign_id,
                table.c.state.in_(("pending", "submitted")),
            )
        ).mappings():
            body = json.loads(row["body_json"])
            if body.get("tag") != tag or row["kind"] not in ("tag_resolution", "paired_tag"):
                continue
            action = self.game.action(c, row["action_id"])
            require(
                action["actor_id"] == str(owner)
                and action["data"]["play"]
                in ("keep_your_head", "check_sensors", "engage", "disobey_orders", "flirt")
                and not any(
                    action["data"].get(k)
                    for k in (
                        "actor_basic",
                        "gorgon_play",
                        "m3",
                        "mockingbird",
                        "alpha",
                        "alpha_sex",
                        "stim_sex",
                        "princess_sex",
                        "janus",
                        "dose_up",
                        "beneath",
                        "defeat",
                        "dive",
                        "battle",
                        "enforcement",
                        "doctor",
                        "am_code",
                        "am_scrutinized",
                    )
                ),
                "SOURCE_MALLEABLE_RESOLUTION_REQUIRED: preserve this specialised Tag source.",
            )
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == row["id"],
                )
                .values(
                    state="completed_by_malleable",
                    revision=row["revision"] + 1,
                    body_json=json.dumps(body | {"malleable_event": event, "malleable_birth": tag}),
                )
            )
            action["data"].setdefault("malleable_resolutions", []).append(
                dict(choice=row["id"], birth=tag, event=event, author=birth.giver_controller)
            )
            action["data"]["response_event"] = event
            touched[action["id"]] = action
        self.tag_resolved(state, owner, tag)
        for action in touched.values():
            if not self.game.pending(c, action["id"]):
                self.results(c, state, action)
            self.game.save_action(c, action)

    def unmark(
        self,
        c: Connection,
        state: GameState,
        sheet: PilotSheet,
        ids: tuple[str, ...],
        maximum: int,
    ) -> None:
        from girlframe.engine.m3_clone_am import additional_identities, unmark_additional
        from girlframe.services.m3_clone_am import prove_additional

        additional = additional_identities(state, sheet.owner)
        extra = tuple(x.id for x in additional if x.marked)
        from girlframe.engine.m3_oldgen import marked_maxims, unmark_maxim
        from girlframe.services.m3_oldgen import prove_unmark

        maxims = dict(marked_maxims(state, sheet.owner))
        picks(
            ids,
            {x.id for x in sheet.identities if x.marked and x.id not in sheet.sedation_locked}
            | set(extra)
            | set(maxims),
            0,
            maximum,
        )
        for token in ids:
            if token in maxims:
                prove_unmark(self.game, c, state, sheet.owner, token)
                require(unmark_maxim(state, sheet.owner, token), "Recover the actual marked maxim.")
        selected_extra = tuple(x for x in ids if x in extra)
        if selected_extra:
            prove_additional(self.game, c, state, sheet.owner)
            unmark_additional(state, sheet.owner, selected_extra)
        for entry in sheet.identities:
            if entry.id in ids:
                entry.marked = False

    def bond(
        self, state: GameState, first: int, second: int, delta: int, source_event: str
    ) -> None:
        from girlframe.engine.m3_actor_bonds import change, current_ref

        refs = (current_ref(state, first), current_ref(state, second))
        if any({edge.first, edge.second} == set(refs) for edge in state.actor_bonds):
            changed = change(state, *refs, 1 if delta > 0 else -1, source_event)
            for name in GameState.model_fields:
                setattr(state, name, getattr(changed, name))
            return
        key = pair_key(first, second)
        old = state.bonds.get(key, 0)
        if old == 2 and delta == 1:
            for uid in (first, second):
                state.sheets[str(uid)].heat += 2
                state.sheets[str(uid)].revision += 1
        else:
            state.bonds[key] = min(max(old + delta, 0), 2)

    def answered(self, action: dict[str, Any], kind: str, actor: int) -> ChoiceAnswer:
        return ChoiceAnswer.model_validate_json(
            json.dumps(action["data"]["choices"][kind + ":" + str(actor)])
        )

    def apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        request: dict[str, Any],
        answer: ChoiceAnswer,
    ) -> None:
        kind = request["kind"]
        owner = int(request["actor_id"])
        actor = int(action["actor_id"])
        sheet = state.sheets.get(str(owner))
        body = json.loads(request["body_json"])
        if kind.startswith("vat_doll_") and action["data"].get("vatgrown"):
            from girlframe.services.m3_vatgrown import apply_choice as apply_doll

            apply_doll(self.game, c, state, action, request, answer)
            return
        if kind.startswith("oldgen_sex_") and action["data"].get("oldgen_sex"):
            from girlframe.services.m3_oldgen_sex import apply_choice as apply_oldgen_sex

            apply_oldgen_sex(self.game, c, state, action, request, answer)
            return
        if kind.startswith("prince_"):
            from girlframe.services.m3_prince import apply_choice as apply_prince

            apply_prince(self.game, c, state, action, request, answer)
            return
        if kind.startswith("wyvern_"):
            from girlframe.services.m3_wyvern import apply as apply_wyvern

            apply_wyvern(self.game, c, state, action, request, answer)
            if not self.game.pending(c, action["id"]):
                self.finish(c, state, action)
            return
        if kind.startswith("bonded_"):
            from girlframe.services.m3_bonded import apply_choice as apply_bonded

            require(
                apply_bonded(self.game, c, state, action, request, answer),
                "Use the original owned Bonded choice",
            )
            if not self.game.pending(c, action["id"]):
                self.finish(c, state, action)
            return
        if kind.startswith("consume_"):
            from girlframe.services.m3_consume import apply as apply_consume

            apply_consume(self.game, c, state, action, request, answer)
            return
        if kind.startswith("casualty_"):
            from girlframe.services.m3_casualty import apply_choice as apply_casualty_sex

            apply_casualty_sex(self.game, c, state, action, request, answer)
            return
        if kind.startswith("vat_sex_") and action["data"].get("vatgrown_sex"):
            from girlframe.services.m3_vatgrown_plays import apply_choice as apply_vatgrown_sex

            apply_vatgrown_sex(self.game, c, state, action, request, answer)
            return
        if kind.startswith("newgirl_sex_") and action["data"].get("newgirl_sex"):
            from girlframe.services.m3_newgirl_sex import apply_choice as apply_newgirl_sex

            apply_newgirl_sex(self.game, c, state, action, request, answer)
            return
        if kind.startswith("easy_target_") and action["data"].get("easy_target"):
            from girlframe.services.m3_easy_target import apply as apply_easy_target

            apply_easy_target(self.game, c, state, action, request, answer)
            return
        if kind.startswith("oldgen_") and action["data"].get("oldgen"):
            from girlframe.services.m3_oldgen import apply_choice as apply_oldgen

            apply_oldgen(self.game, c, state, action, request, answer)
            return
        if kind.startswith("stim_sex_") and action["data"].get("stim_sex"):
            from girlframe.services.m3_stim_sex import apply_choice as apply_stim

            require(
                apply_stim(self.game, c, state, action, request, answer),
                "Resolve this exact actual Stim source choice.",
            )
            return
        if kind.startswith("ankou_feedback_") and action["data"].get("ankou_feedback"):
            from girlframe.services.m3_ankou_feedback import apply as apply_ankou

            apply_ankou(self.game, c, state, action, request, answer)
            return
        if kind.startswith("princess_sex_") and action["data"].get("princess_sex"):
            from girlframe.services.m3_princess_sex import apply as apply_princess

            apply_princess(self.game, c, state, action, request, answer)
            return
        if kind in ("dose_up_components", "dose_up_target_low"):
            from girlframe.services.m3_dose_up import apply_choice as apply_dose_choice

            require(
                apply_dose_choice(self.game, c, state, action, request, answer),
                "Recover the original Dose Up choice",
            )
            return
        if kind in ("gender_partner_tag_resolution", "gender_animal_tag"):
            from girlframe.services.m3_gender_designation import apply_choice

            require(
                apply_choice(self.game, c, state, action, request, answer),
                "Recover the original designation response",
            )
            return
        if kind == "reign_group_tag_resolution":
            from girlframe.services.m3_reign_terror import resolution as resolve_reign_tag

            resolve_reign_tag(self.game, c, state, action, request, answer)
            return
        if kind == "sidearm_reconsider":
            from girlframe.services.m3_hidden_sidearm import apply_response as apply_sidearm

            apply_sidearm(self.game, c, state, action, request, answer)
            return
        if kind in ("secretary_gunpoint", "secretary_gunpoint_resolution"):
            from girlframe.services.m3_secretary import apply_response, refresh_after_response

            phase = apply_response(self.game, c, state, action, request, answer)
            if phase == "withdrawn":
                require(
                    action["data"].get("receipt") is None,
                    "A known rolled action cannot become an unrolled withdrawal",
                )
                action["data"]["result"] = dict(withdrawn=True, source="secretary_gunpoint")
                action["state"] = "complete"
                self.game.queue(
                    c,
                    action,
                    "outcome",
                    dict(
                        play=action["data"]["play"],
                        callsign=self.original_callsign(state, action),
                        receipt=None,
                        total=None,
                        tier=None,
                        withdrawn=True,
                        source="secretary_gunpoint",
                    ),
                )
            elif phase in ("released", "proceeded"):
                refresh_after_response(self.game, c, state, action)
                action["state"] = "ready_to_roll"
            return
        if kind == "budget_asset_calamity":
            from girlframe.services.m3_budget_sabotage import apply as apply_asset_calamity

            apply_asset_calamity(self.game, c, state, action, request, answer)
            return
        if kind.startswith("am_code_") and action["data"].get("am_code"):
            from girlframe.services.m3_am_code import apply as apply_code

            apply_code(self.game, c, state, action, request, answer)
            return
        if kind.startswith("am_") and action["data"].get("am_scrutinized"):
            from girlframe.services.m3_am_scrutinized import apply as apply_am

            apply_am(self.game, c, state, action, request, answer)
            return
        if kind.startswith("alpha_sex_") and action["data"].get("alpha_sex"):
            from girlframe.services.m3_alpha_sex import apply as apply_alpha_sex

            apply_alpha_sex(self.game, c, state, action, request, answer)
            return
        if kind.startswith("alpha_") and action["data"].get("alpha"):
            from girlframe.services.m3_alpha import apply as apply_alpha

            apply_alpha(self.game, c, state, action, request, answer)
            return
        if kind == "actor_disobey" and answer.options == ("remove_broken",):
            from girlframe.services.m3_alpha import remove_choice

            if remove_choice(self.game, c, state, action, request, answer):
                return
        if kind.startswith("janus_") and action["data"].get("janus"):
            from girlframe.services.m3_janus_play import apply as apply_janus

            apply_janus(self.game, c, state, action, request, answer)
            return
        if kind.startswith("snoop_") and action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import apply as apply_snoop

            apply_snoop(self.game, c, state, action, request, answer)
            return
        if kind in (
            "enforcer_firepower",
            "enforcer_firepower_context",
            "enforcer_firepower_confirm",
        ):
            from girlframe.services.m3_enforcer_firepower import apply as apply_firepower

            apply_firepower(self.game, c, state, action, request, answer)
            return
        if kind.startswith("doctor_") and action["data"].get("doctor"):
            from girlframe.services.m3_doctor import apply as apply_doctor

            apply_doctor(self.game, c, state, action, request, answer)
            return
        if (
            kind.startswith("mockingbird_")
            and kind not in ("mockingbird_risk", "mockingbird_void_threshold")
            and action["data"].get("mockingbird")
        ):
            from girlframe.services.m3_mockingbird_plays import apply as apply_mock_play

            apply_mock_play(self.game, c, state, action, request, answer)
            return
        if kind in ("mockingbird_risk", "mockingbird_void_threshold"):
            from girlframe.services.m3_mockingbird import apply as apply_mockingbird

            apply_mockingbird(self.game, c, state, action, request, answer)
            return
        if kind == "enforcer_master_dog":
            from girlframe.services.m3_enforcer_requisitions import apply_master

            apply_master(self.game, c, state, action, request, answer)
            return
        if kind in ("tag_marker_selection", "tag_marker_agreement"):
            from girlframe.services.m3_tag_markers import apply_discussion

            apply_discussion(self.game, c, state, action, request, answer)
            return
        if kind.startswith("engage_"):
            from girlframe.services.m3_engage import apply as apply_engage

            apply_engage(self.game, c, state, action, request, answer)
            return
        if kind.startswith("battle_") and action["data"].get("engage"):
            from girlframe.services.m3_battle import apply_damage_response

            apply_damage_response(self.game, c, state, action, request, answer)
            return
        if kind.startswith("battle_") and action["data"].get("battle"):
            from girlframe.services.m3_battle import apply as apply_battle

            apply_battle(self.game, c, state, action, request, answer)
            return
        if kind.startswith("enforcer_") and action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import apply as apply_enforcement

            apply_enforcement(self.game, c, state, action, request, answer)
            return
        if kind.startswith("dive_") and action["data"].get("dive"):
            from girlframe.services.m3_dive import apply as apply_dive

            apply_dive(self.game, c, state, action, request, answer)
            return
        if kind.startswith("defeat_") and action["data"].get("defeat"):
            from girlframe.services.m3_defeat import apply as apply_defeat

            apply_defeat(self.game, c, state, action, request, answer)
            return
        if kind.startswith("beneath_") and action["data"].get("beneath"):
            from girlframe.services.m3_beneath import apply as apply_beneath

            apply_beneath(self.game, c, state, action, request, answer)
            return
        if kind == "control_ritual_create":
            from girlframe.services.m3_control_ritual import choose

            choose(self.game, c, state, action, body, answer)
            if not self.game.pending(c, action["id"]):
                self.finish(c, state, action)
            return
        if kind == "tag_window":
            self.tag_proposal(c, state, action, owner, answer)
            if not any(
                x["kind"] == "tag_window" and x["state"] == "pending"
                for x in self.game.pending(c, action["id"])
            ):
                self.close_tag_window(c, state, action)
            return
        acting = state.sheets[str(actor)]
        if kind == "tag_resolution":
            require(
                not str(body["tag"]).startswith("bomb-collar:"),
                "A bomb collar cannot be embraced or rejected",
            )
            if answer.options == ("reject",):
                from girlframe.engine.m3_actor_bonds import current_ref
                from girlframe.services.m3_vatgrown_plays import rejection_allowed

                require(
                    rejection_allowed(state, current_ref(state, actor)),
                    "A Vatgrown cannot reject this marked Tag.",
                )
            from girlframe.services.m3_cute_uniforms import resolve_choice

            if resolve_choice(self.game, c, state, action, body, answer):
                if answer.options != ("reject",):
                    self.tag_resolved(state, actor, body["tag"])
                self.results(c, state, action)
                return
            from girlframe.engine.m3_control_ritual import save_tag
            from girlframe.engine.m3_control_ritual import tags as ritual_tags

            tag = next(
                (x for x in acting.tags + ritual_tags(state, actor) if x.id == body["tag"]), None
            )
            require(tag is not None, "The marked Tag is no longer available.")
            assert tag is not None
            self.prove_tag_setter(c, state, actor, tag)
            picks(answer.options, {"reject", "embrace"}, 1)
            if answer.options == ("reject",):
                from girlframe.engine.m3_beneath import rejection_blocked

                require(
                    not rejection_blocked(state, actor, tag.id),
                    "TAG_CONSENT_REQUIRED: its setter must consent to rejecting this Tag.",
                )
                require(
                    not (mentor_tag(acting, tag, state)),
                    "A Newgirl cannot reject a Tag given by its Mentor.",
                )
                tag.rejection_pending = True
                save_tag(state, actor, tag)
                self.game.obligation(state, action, "reject_tag", actor, tag=tag.id)
            else:
                picks(answer.denied, {x.id for x in acting.identities if not x.protected}, 1)
                from girlframe.engine.m3_leviathan_obsession import require_unlocked

                require_unlocked(acting.identities, answer.denied)
                require(
                    self.duplicate_labels()
                    or not any(
                        x.name.casefold() == tag.label.casefold() for x in acting.identities
                    ),
                    "UNSUPPORTED_RULE: duplicate Identity labels need explicit review.",
                )
                replacement = IdentityState(
                    id=str(uuid4()),
                    name=tag.label,
                    marked=bool(set(answer.denied) & set(acting.sedation_locked)),
                    slot=next(x.slot for x in acting.identities if x.id == answer.denied[0]),
                )
                acting.identities = [x for x in acting.identities if x.id not in answer.denied] + [
                    replacement
                ]
                if replacement.marked:
                    acting.sedation_locked = tuple(
                        x for x in acting.sedation_locked if x not in answer.denied
                    ) + (replacement.id,)
                acting.tags = [x for x in acting.tags if x.id != tag.id]
                self.tag_resolved(state, actor, tag.id)
            acting.revision += 1
            self.results(c, state, action)
            return
        if kind == "paired_tag":
            picks(answer.options, {"yes", "no"}, 1)
            tag = next((x for x in acting.tags if x.id == body["tag"]), None)
            require(tag is not None, "This marked Tag changed.")
            assert tag is not None
            if answer.options == ("yes",):
                paired = next((x for x in acting.identities if x.paired), None)
                require(paired is not None, "The Paired Identity is unavailable.")
                assert paired is not None
                require(
                    self.duplicate_labels()
                    or not any(
                        x.name.casefold() == tag.label.casefold() and not x.paired
                        for x in acting.identities
                    ),
                    "UNSUPPORTED_RULE: duplicate Paired Identity labels need review.",
                )
                paired.name = tag.label
                paired.marked = paired.id in acting.sedation_locked
                acting.tags = [x for x in acting.tags if x.id != tag.id]
                self.tag_resolved(state, actor, tag.id)
                acting.revision += 1
                self.results(c, state, action)
            elif body["already_marked"]:
                self.game.request(c, action, actor, "tag_resolution", {"tag": tag.id})
            else:
                self.results(c, state, action)
            return
        if kind == "followthrough_confirm":
            require(
                answer.flag is not None and bool(answer.text.strip()),
                "The target must confirm or decline the described follow-through.",
            )
            item = next(x for x in state.obligations if x.id == action["data"]["obligation_id"])
            require(
                item.state == "pending" and item.target == owner, "This follow-through changed."
            )
            if answer.flag:
                self.bond(state, actor, owner, 1, action["data"]["response_event"])
                item.state = "fulfilled"
            action["data"]["result"].update(confirmed=answer.flag, response=answer.text)
            self.finish(c, state, action)
            return
        result = action["data"]["result"]
        level = result.get("tier")
        if kind == "actor_keep":
            from girlframe.services.m3_cute_uniforms import apply_keep_result, validate_keep_choice

            validate_keep_choice(action, answer)
            apply_keep_result(action)
            from girlframe.services.m3_enforcer_requisitions import keep_extras
            from girlframe.services.m3_nightmare import automatic as nightmare_automatic

            pavlov = keep_extras(self.game, c, state, action, answer)
            automatic = keep_automatic(acting) | pavlov | nightmare_automatic(action)
            if level == "mid":
                picks(answer.options, set(TRAITS), 2)
                picks(answer.denied, set(TRAITS) - set(answer.options) - automatic, 1)
            elif level == "low":
                picks(answer.options, set(TRAITS), 1)
                require(not answer.denied, "Negative traits are fixed by the low result.")
            else:
                require(
                    not answer.options and not answer.denied, "The high result's traits are fixed."
                )
                self.add_tag(state, action, actor, actor, answer.text)
            positives = set(TRAITS[:-1]) if level == "high" else set(answer.options)
            negatives = (
                {"in_control"}
                if level == "high"
                else set(TRAITS) - positives - automatic
                if level == "low"
                else set(answer.denied)
            )
            positives |= automatic
            if has_rule(acting, "girl.oldgen.elder-bitch", "OLDGEN") and answer.flag:
                positives.add("experienced")
            if acting.frame == "WYVERN 0.4" and action["data"]["prepared"]["piloting"]:
                from girlframe.engine.m3_actor_bonds import current_ref
                from girlframe.engine.m3_wyvern import CHASSIS
                from girlframe.services.m3_wyvern import big_enough, require_rule

                actual = current_ref(state, actor)
                require_rule(self.game, c, state, actual, CHASSIS)
                require(big_enough(state, actual), "Use the actual original piloted Wyvern chassis")
                positives.add("big_enough")
            result.update(positive=sorted(positives), negative=sorted(negatives))
            self.game.request(c, action, state.handler, "handler_keep")
            return
        if kind == "handler_keep":
            require(
                answer.flag is not None and bool(answer.text.strip()),
                "The Handler must answer whether it is enough and explain the outcome.",
            )
            result.update(enough=answer.flag, ruling=answer.text)
            self.finish(c, state, action)
            return
        if kind == "actor_sensors":
            count = {"low": 1, "mid": 2, "high": 3}[level]
            from girlframe.services.p1_consume_hooks import smell_question

            smell = smell_question(self.game, c, state, action)
            ordinary = tuple(x for x in answer.options if x != "consume_smell")
            require(
                "consume_smell" not in answer.options or smell is not None,
                "Acquire the actual Human Hound source first",
            )
            picks(ordinary, set(QUESTIONS), 1 if level == "low" else 0, count)
            require(
                set(answer.fields) <= {"q1", "q2", "q3"}
                and all(x.strip() for x in answer.fields.values()),
                "Provide valid custom questions.",
            )
            require(
                len(ordinary) + len(answer.fields) == count
                and (level != "low" or not answer.fields),
                "Choose the printed question count; low results use listed questions only.",
            )
            result["questions"] = list(ordinary) + [answer.fields[x] for x in sorted(answer.fields)]
            if "consume_smell" in answer.options:
                result["questions"].append(smell)
            result["off_list"] = bool(answer.fields)
            self.game.request(c, action, state.handler, "handler_sensors")
            return
        if kind == "handler_sensors":
            expected = {"a" + str(i + 1) for i in range(len(result["questions"]))}
            require(
                set(answer.fields) == expected and all(x.strip() for x in answer.fields.values()),
                "The Handler must supply each required answer.",
            )
            if level == "high" and result["off_list"]:
                picks(answer.options, {"incomplete_information", "punishment_later"}, 1)
                if "punishment_later" in answer.options:
                    self.game.obligation(
                        state,
                        action,
                        "punishment",
                        actor,
                        state.handler,
                        cause="off-list Check Sensors question",
                    )
            else:
                require(not answer.options, "No extra consequence is required for these questions.")
            result.update(answers=answer.fields, consequence=list(answer.options))
            self.finish(c, state, action)
            return
        if kind == "actor_engage":
            count = {"low": 1, "mid": 2, "high": 3}[level]
            picks(answer.options, set(MANEUVERS), count)
            require(
                set(answer.fields) == set(answer.options), "Choose an Asset for every maneuver."
            )
            assets = {x.id: x for x in acting.assets if not x.damaged}
            require(
                set(answer.fields.values()) <= set(assets), "Use currently undamaged owned Assets."
            )
            if level != "mid":
                picks(answer.denied, set(answer.fields.values()), 1)
                used = assets[answer.denied[0]]
                if (
                    used.family == "frame"
                    and action["data"]["prepared"]["piloting"]
                    and len([x for x in acting.assets if x.family == "frame" and not x.damaged])
                    == 1
                ):
                    raise WorkflowError(
                        "UNSUPPORTED_RULE: damaging the final Frame Asset needs "
                        "Defeat; staff recovery is required."
                    )
                if (
                    used.family == "girl"
                    and not action["data"]["prepared"]["piloting"]
                    and len([x for x in acting.assets if x.family == "girl" and not x.damaged]) == 1
                ):
                    raise WorkflowError(
                        "UNSUPPORTED_RULE: last-Asset defeat needs an identified "
                        "opponent; staff recovery is required."
                    )
                used.damaged = True
            else:
                require(not answer.denied, "This tier does not damage an Asset.")
            result.update(maneuvers=answer.fields, damaged=list(answer.denied))
            acting.revision += 1
            self.finish(c, state, action)
            return
        if kind == "actor_disobey":
            if level == "mid":
                picks(answer.options, {"tag_heat", "reject_tag", "follow"}, 1)
                option = answer.options[0]
                if option == "tag_heat":
                    require(answer.number in (1, 2), "Choose one or two Heat.")
                    self.add_tag(state, action, actor, actor, answer.text)
                    acting.heat += int(answer.number or 0)
                elif option == "reject_tag":
                    from girlframe.services.m3_cute_uniforms import reject_tag as reject_uniform
                    from girlframe.services.m3_cute_uniforms import tags as uniform_tags

                    available = acting.tags + uniform_tags(state, actor)
                    picks(answer.denied, {x.id for x in available}, 1)
                    rejected = next(x for x in available if x.id == answer.denied[0])
                    self.prove_tag_setter(c, state, actor, rejected)
                    from girlframe.engine.m3_beneath import rejection_blocked

                    require(
                        not rejection_blocked(state, actor, rejected.id),
                        "TAG_CONSENT_REQUIRED: its setter must consent to rejecting this Tag.",
                    )
                    require(
                        not (mentor_tag(acting, rejected, state)),
                        "A Newgirl cannot reject a Mentor Tag.",
                    )
                    if not reject_uniform(
                        self.game, c, state, action, rejected, action["data"]["response_event"]
                    ):
                        acting.tags = [x for x in acting.tags if x.id != rejected.id]
                    self.tag_resolved(state, actor, rejected.id)
                else:
                    require(
                        answer.member in action["data"]["participants"]
                        and answer.member != actor
                        and str(answer.member) in state.sheets,
                        "Choose another active Pilot in this scene.",
                    )
                    self.game.request(c, action, answer.member, "follow_disobey")
            elif level == "high":
                require(
                    answer.flag is True,
                    "Confirm immediate action without thinking, as this tier requires.",
                )
                acting.heat += 2
            else:
                raise WorkflowError("Low Disobey results have no successful refusal choice.")
            acting.revision += 1
            result["can_disobey"] = True
            from girlframe.services.m3_control_ritual import offer as offer_ritual

            offer_ritual(self.game, c, state, action)
            self.game.request(c, action, state.handler, "handler_disobey")
            return
        if kind == "follow_disobey":
            require(
                answer.flag is not None,
                "The other player decides whether to follow immediately without thinking.",
            )
            result["follower"] = owner
            result["followed"] = answer.flag
            if not self.game.pending(c, action["id"]):
                self.finish(c, state, action)
            return
        if kind == "handler_disobey":
            require(
                answer.flag is not None, "The Handler must record whether it discovers the refusal."
            )
            if answer.flag:
                self.game.obligation(
                    state,
                    action,
                    "punishment",
                    actor,
                    state.handler,
                    cause="Disobey Orders",
                    outcome=level,
                )
            result["handler_knows"] = answer.flag
            if not self.game.pending(c, action["id"]):
                self.finish(c, state, action)
            return
        if kind == "actor_flirt":
            from girlframe.engine.m3_kicked_puppy import QUESTION, QUESTION_TEXT
            from girlframe.services.m3_kicked_puppy import questions as kicked_questions

            picks(answer.options, set(kicked_questions(self.game, c, state, action)), 1)
            self.unmark(c, state, acting, answer.denied, 2)
            result["question"] = answer.options[0]
            if result["question"] == QUESTION:
                result["question_text"] = QUESTION_TEXT
            if level == "high":
                require(
                    answer.fields.get("extra") in ("escape", "handler", "owe")
                    and bool(answer.text.strip()),
                    "Choose one printed high-tier branch and describe how you go too far.",
                )
                result["extra"] = answer.fields["extra"]
                result["too_far"] = answer.text
            acting.revision += 1
            target = int(action["data"]["prepared"]["target"])
            self.game.request(c, action, target, "target_flirt")
            return
        if kind == "target_flirt":
            require(bool(answer.text.strip()), "The target player must provide its own answer.")
            assert sheet is not None
            self.unmark(c, state, sheet, answer.denied, 1 if level == "low" else 2)
            sheet.revision += 1
            result["target_answer"] = answer.text
            if level == "low":
                picks(answer.options, set(FLIRT_QUESTIONS), 0, 1)
                if answer.options:
                    result["return_question"] = answer.options[0]
                    self.game.request(c, action, actor, "actor_flirt_answer")
                else:
                    self.finish(c, state, action)
            else:
                if (
                    result["question"] == "intimacy"
                    and state.bonds.get(pair_key(actor, owner), 0) == 2
                ):
                    require(
                        answer.flag is True,
                        "Consent is not inferred. Use safety pause for an unwanted interaction.",
                    )
                self.game.obligation(
                    state, action, "flirt_followthrough", actor, owner, wanted=answer.text
                )
                extra = result.get("extra")
                if extra == "escape":
                    self.game.request(c, action, owner, "flirt_escape")
                elif extra == "handler":
                    required = self.game.request(c, action, state.handler, "handler_brief")
                    approval = self.game.store.policy.m3_approval
                    if approval is not None and "plays" in approval.subsystems:
                        from girlframe.engine.m3_actor_state import ActorRef
                        from girlframe.services.m3_handler_plays import request_from_play

                        bindings = action["data"].get("character_ids")
                        if bindings is None:
                            bindings = self.game.legacy_action_bindings(c, action)
                        affected = tuple(
                            ActorRef(kind="pilot", entity=str(uid), incarnation=bindings[str(uid)])
                            for uid in (actor, owner)
                        )
                        updated, grant = request_from_play(
                            self.game,
                            c,
                            state,
                            action,
                            required,
                            "flirt.high.handler",
                            action["data"]["response_event"],
                            targets=affected,
                        )
                        for field in GameState.model_fields:
                            setattr(state, field, getattr(updated, field))
                        action["data"]["handler_play_m3"] = grant
                elif extra == "owe":
                    self.game.request(c, action, owner, "flirt_owe_tag")
                else:
                    self.finish(c, state, action)
            return
        if kind == "actor_flirt_answer":
            require(bool(answer.text.strip()), "The actor must answer the other player's question.")
            result["actor_answer"] = answer.text
            self.finish(c, state, action)
            return
        if kind == "flirt_escape":
            picks(answer.options, {"helpless", "damage", "play"}, 1)
            assert sheet is not None
            if answer.options == ("damage",):
                picks(answer.denied, {x.id for x in sheet.assets if not x.damaged}, 1)
                next(x for x in sheet.assets if x.id == answer.denied[0]).damaged = True
                result["escaped"] = True
                self.finish(c, state, action)
            elif answer.options == ("play",):
                self.game.request(c, action, owner, "escape_play")
            else:
                sheet.helpless_against = tuple(sorted(set(sheet.helpless_against) | {actor}))
                result["helpless"] = owner
                self.finish(c, state, action)
            sheet.revision += 1
            return
        if kind == "handler_brief":
            require(
                not body.get("handler_grant"),
                "Use the actual source-owned Handler Play; a text Brief cannot complete it.",
            )
            require(
                answer.options == ("brief",) and bool(answer.text.strip()),
                "The Handler must choose Brief Them and supply the situation information.",
            )
            state.facts.append(
                {
                    "action": action["id"],
                    "kind": "handler_brief",
                    "text": answer.text,
                    "scene": action["scene_id"],
                }
            )
            result["handler_play"] = "handler_brief"
            result["handler_text"] = answer.text
            self.finish(c, state, action)
            return
        if kind == "flirt_owe_tag":
            self.add_tag(state, action, actor, owner, answer.text)
            self.game.obligation(
                state,
                action,
                "cannot_refuse_until_tag_resolved",
                actor,
                owner,
                tag=acting.tags[-1].id,
            )
            self.finish(c, state, action)
            return
        if kind == "order_response":
            if answer.options == ("consume_follow",):
                from girlframe.services.m3_consume import begin_order_pursuit

                begin_order_pursuit(
                    self.game, c, state, action, answer, action["data"]["response_event"]
                )
                return
            from girlframe.services.m3_gender_designation import order_no

            order_no(self.game, c, state, action, answer)
            if answer.options == ("disobey",):
                from girlframe.engine.m3_actor_bonds import current_ref as am_original
                from girlframe.engine.m3_am import require_freedom

                require_freedom(state, am_original(state, actor), "refuse")
            picks(
                answer.options,
                {"obedient", "immediate", "hesitant", "mouthing_off", "gritted_teeth", "disobey"},
                1,
            )
            table = t.m2["m2_orders"]
            status = "disobey" if answer.options == ("disobey",) else "followed"
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == action["data"]["order_id"],
                )
                .values(state=status)
            )
            result["response"] = answer.options[0]
            if status == "disobey":
                self.game.request(
                    c, action, actor, "order_disobey", {"order_id": action["data"]["order_id"]}
                )
            else:
                self.finish(c, state, action)
            return
        if kind in ("escape_play", "order_disobey", "beneath_response_play"):
            raise WorkflowError(
                "Start the required response Play from its wizard; a text answer cannot replace it."
            )
        raise WorkflowError("UNSUPPORTED_RULE: this response has no audited transition.")

    def tag_proposal(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        owner: int,
        answer: ChoiceAnswer,
    ) -> None:
        from girlframe.services import m3_tag_markers as markers
        from girlframe.services.m3_dose_up import self_tag as drug_self_tag
        from girlframe.services.m3_kicked_puppy import self_tag as kicked_self_tag
        from girlframe.services.m3_stim_sex import self_tag as stim_self_tag

        actor = int(action["actor_id"])
        sheet = state.sheets[str(actor)]
        from girlframe.services.m3_bomb_collar import tags as collar_tags
        from girlframe.services.m3_control_ritual import candidates
        from girlframe.services.m3_control_ritual import self_tag as ritual_self_tag
        from girlframe.services.m3_cute_uniforms import tags as uniform_tags

        available_tags = (
            sheet.tags
            + candidates(state, action, owner)
            + uniform_tags(state, actor)
            + collar_tags(state, actor)
        )
        from girlframe.services.m3_reign_terror import candidates as reign_candidates
        from girlframe.services.m3_reign_terror import propose as propose_reign

        available_tags += reign_candidates(self.game, c, state, action)
        picks(answer.options, {"pass", "tag", "gender_man", "starvation"}, 1)
        require(
            set(answer.fields) <= {"status", "marker"}, "Choose only supported source-role fields."
        )
        marker = (
            markers.select(self.game, c, state, action, owner, answer.fields.get("marker"))
            if answer.options in (("tag",), ("starvation",)) or "marker" in answer.fields
            else None
        )
        if answer.options == ("pass",):
            require(
                not answer.denied and set(answer.fields) <= {"status", "marker"},
                "A pass does not modify a Tag.",
            )
        elif answer.options == ("starvation",):
            from girlframe.services.p1_consume_hooks import starvation

            require(
                marker is not None
                and starvation(self.game, c, state, action, marker.actor) is not None,
                "Use only the actual available starvation source and original marker",
            )
            require(
                not answer.denied and answer.number in (None, -1) and bool(answer.text.strip()),
                "Starvation is a fixed -1 source; explain its actual relevance",
            )
        elif answer.options == ("gender_man",):
            from girlframe.services.m3_gender_designation import propose_man_tag

            propose_man_tag(self.game, c, state, action, owner, answer)
        else:
            picks(
                answer.denied,
                {
                    x.id
                    for x in available_tags
                    if (owner in x.observers or owner == actor)
                    and x.scene_used != action["scene_id"]
                },
                1,
            )
            tag = next(x for x in available_tags if x.id == answer.denied[0])
            reign = propose_reign(self.game, c, state, action, owner, tag)
            if not reign:
                self.prove_tag_setter(c, state, actor, tag)
            require(
                reign
                or owner != actor
                or mentor_tag(sheet, tag, state)
                or (
                    has_rule(sheet, "girl.princess.objectively-beautiful", "PRINCESS")
                    and action["data"]["play"] == "flirt"
                )
                or kicked_self_tag(self.game, c, state, action, owner, tag)
                or ritual_self_tag(self.game, c, state, action, owner, tag)
                or drug_self_tag(self.game, c, state, action, owner, tag)
                or stim_self_tag(self.game, c, state, action, owner, tag),
                "Only another player or a printed self-mark exception can mark this Girl Tag.",
            )
            require(
                answer.number in (-1, 1) and bool(answer.text.strip()),
                "Choose a direction and explain relevance.",
            )
        if (
            owner == actor
            and has_rule(sheet, "girl.alpha.nothing-more-than-a-hound", "ALPHA")
            and state.order
            and is_dog(state, actor)
            and not sheet.status_marked
        ):
            require(
                set(answer.fields) <= {"status", "marker"},
                "Choose only the supported Dog Status modifier.",
            )
            require(
                answer.fields.get("status", "0") in ("-1", "0", "1"),
                "Choose a legal Dog Status modifier.",
            )
            if answer.fields.get("status", "0") != "0":
                sheet.status_marked = True
                sheet.revision += 1
                action["data"]["modifiers"].append(
                    {"source": "alpha_status", "amount": int(answer.fields["status"])}
                )
        elif set(answer.fields) - {"marker"}:
            raise WorkflowError("This actor has no supported Status-mark modifier.")
        if answer.options in (("tag",), ("starvation",)):
            assert marker is not None
            markers.capture(self.game, c, state, action, marker)

    def close_tag_window(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        from girlframe.engine.m3_tag_markers import modifier
        from girlframe.services import m3_tag_markers as markers

        actor = int(action["actor_id"])
        sheet = state.sheets[str(actor)]
        proposals = []
        for person in action["data"]["participants"]:
            answer = self.answered(action, "tag_window", person)
            if answer.options in (("tag",), ("gender_man",), ("starvation",)):
                try:
                    marker = markers.saved(self.game, c, state, action, person)
                except WorkflowError:
                    markers.reopen(self.game, c, action, person)
                    return
                proposals.append((person, answer, marker))
        selected = None
        discussion = action["data"].get("tag_marker_discussion")
        if discussion and discussion.get("ready"):
            proposal = next(
                x for x in discussion["proposals"] if x["id"] == discussion["candidate"]
            )
            selected = next((x for x in proposals if x[0] == proposal["controller"]), None)
            require(selected is not None, "Recover the original discussed Tag proposal.")
        elif len(proposals) > 1 and any(
            x[2].actor is None or x[2].actor.kind not in ("pilot", "handler") for x in proposals
        ):
            markers.begin_discussion(self.game, c, action, proposals)
            return
        else:
            for entry in proposals:
                if selected is None:
                    selected = entry
                    continue
                require(
                    entry[2].actor is not None and selected[2].actor is not None,
                    "Only actual ranked bodies have Status priority",
                )
                assert entry[2].actor is not None and selected[2].actor is not None
                if higher(state, int(entry[2].actor.entity), int(selected[2].actor.entity)):
                    selected = entry
        if selected and len(proposals) > 1 and not (discussion and discussion.get("ready")):
            assert selected[2].actor is not None
            tied = [
                entry
                for entry in proposals
                if entry[2].actor is not None
                and not higher(state, int(selected[2].actor.entity), int(entry[2].actor.entity))
            ]
            if len({entry[2].actor for entry in tied}) > 1:
                markers.begin_discussion(self.game, c, action, tied)
                return
        if selected:
            person, answer, marker = selected
            if answer.options == ("starvation",):
                from girlframe.services.m3_consume import acting, mark_starvation
                from girlframe.services.m3_enforcement_initiative import _cast

                original = acting(state, action)
                require(
                    original is not None and marker.actor is not None,
                    "Recover the actual original starvation bodies",
                )
                assert original is not None and marker.actor is not None
                amount = mark_starvation(
                    self.game,
                    c,
                    state,
                    original,
                    marker.actor,
                    _cast(self.game, c, state, int(action["channel_id"])),
                    action["data"]["response_event"],
                )
                action["data"]["modifiers"].append(
                    dict(source="consume_starvation", amount=amount, actor=person, text=answer.text)
                )
                self.results(c, state, action)
                return
            if answer.options == ("gender_man",):
                from girlframe.services.m3_gender_designation import apply_man_tag

                require(
                    apply_man_tag(self.game, c, state, action, person, marker, answer),
                    "Recover the actual partner Tag source",
                )
                if not self.game.pending(c, action["id"]):
                    self.results(c, state, action)
                return
            from girlframe.services.m3_reign_terror import mark as mark_reign

            if mark_reign(self.game, c, state, action, answer.denied[0], person, marker, answer):
                return
            from girlframe.engine.m3_control_ritual import save_tag
            from girlframe.services.m3_bomb_collar import (
                prove_tag as prove_collar_tag,
            )
            from girlframe.services.m3_bomb_collar import (
                save_tag as save_collar_tag,
            )
            from girlframe.services.m3_bomb_collar import tags as collar_tags
            from girlframe.services.m3_control_ritual import candidates
            from girlframe.services.m3_control_ritual import self_tag as ritual_self_tag
            from girlframe.services.m3_cute_uniforms import tags as uniform_tags

            tag = next(
                x
                for x in sheet.tags
                + candidates(state, action, actor)
                + uniform_tags(state, actor)
                + collar_tags(state, actor)
                if x.id == answer.denied[0]
            )
            from girlframe.services.m3_cute_uniforms import (
                prove_tag as prove_uniform_tag,
            )
            from girlframe.services.m3_cute_uniforms import (
                save_tag as save_uniform_tag,
            )

            uniform = prove_uniform_tag(self.game, c, state, actor, tag)
            collar = prove_collar_tag(self.game, c, state, actor, tag)
            if uniform:
                action["data"].setdefault("cute_uniform_tags", []).append(tag.id)
            ritual = ritual_self_tag(self.game, c, state, action, person, tag)
            require(
                not ritual or person == actor,
                "Only the original Girl marks her own Control Ritual",
            )
            require(
                tag.scene_used != action["scene_id"], "This Tag was already used in this scene."
            )
            old = tag.marked
            tag.marked = True
            tag.scene_used = action["scene_id"]
            sheet.revision += 1
            save_tag(state, actor, tag)
            save_uniform_tag(state, actor, tag)
            save_collar_tag(state, actor, tag)
            amount = modifier(
                state, markers.roller(state, action), marker, 1 if answer.number == 1 else -1
            )
            action["data"]["tag_marker_applied"] = dict(
                actor=marker.actor.model_dump(mode="json") if marker.actor else None,
                controller=person,
                tag=tag.id,
                amount=amount,
                source_actor_sha256=marker.source_actor_sha256,
            )
            action["data"]["modifiers"].append(
                {
                    "source": "control_ritual" if ritual else "girl_tag",
                    "tag": tag.id,
                    "actor": person,
                    "amount": amount,
                }
            )
            self.set_total(action)
            from girlframe.services.m3_easy_target import observe_assistance

            observe_assistance(self.game, c, state, action, action["data"]["response_event"])
            if collar:
                self.results(c, state, action)
                return
            if (
                has_rule(sheet, "girl.bonded.bonded-pair", "BONDED")
                and relation_current(sheet, "pair", state)
                and marker.actor is not None
                and marker.actor.kind == "pilot"
                and sheet.pair == int(marker.actor.entity)
            ):
                self.game.request(
                    c, action, person, "paired_tag", {"tag": tag.id, "already_marked": old}
                )
                return
            if old:
                self.game.request(c, action, actor, "tag_resolution", {"tag": tag.id})
                return
        self.results(c, state, action)

    def set_total(self, action: dict[str, Any]) -> None:
        total = action["data"]["receipt"]["pre_total"] + sum(
            x["amount"] for x in action["data"]["modifiers"]
        )
        from girlframe.engine.m3_gender_designation import man_floor

        minimum = man_floor(action)
        if minimum is not None:
            total = max(total, minimum)
        override = action["data"].get("casualty_override")
        if override is not None:
            total = max(total, int(override["total"]))
        override = action["data"].get("prince_override")
        if override is not None:
            total = max(total, int(override["total"]))
        cap = action["data"].get("consume_disobey_limit")
        if cap is not None:
            total = min(total, int(cap["cap"]))
        action["data"]["result"].update(total=total, tier=tier(total))

    def results(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        self.set_total(action)
        from girlframe.services.m3_consume import apply_disobey_limit, intercept_targeted_results

        apply_disobey_limit(self.game, c, state, action)
        if intercept_targeted_results(self.game, c, state, action):
            return
        from girlframe.services.m3_casualty import intercept_results as intercept_casualty

        if intercept_casualty(self.game, c, state, action):
            return
        from girlframe.services.m3_prince import intercept_bad_girl

        if intercept_bad_girl(self.game, c, state, action):
            return
        from girlframe.services.m3_enforcer_requisitions import intercept_results

        if intercept_results(self.game, c, state, action):
            return
        from girlframe.services.m3_mockingbird import intercept_results as intercept_risk

        if intercept_risk(self.game, c, state, action):
            return
        action["state"] = "awaiting_choices"
        actor = int(action["actor_id"])
        play = action["data"]["play"]
        level = action["data"]["result"]["tier"]
        if action["data"].get("prince"):
            from girlframe.services.m3_prince import results as prince_results

            prince_results(self.game, c, state, action)
            return
        if action["data"].get("wyvern"):
            from girlframe.services.m3_wyvern import results as wyvern_results

            wyvern_results(self.game, c, state, action)
            return
        if action["data"].get("bonded"):
            from girlframe.services.m3_bonded import results as bonded_results

            bonded_results(self.game, c, state, action)
            return
        if action["data"].get("consume"):
            from girlframe.services.m3_consume import results as consume_results

            consume_results(self.game, c, state, action)
            return
        if action["data"].get("dose_up"):
            from girlframe.services.m3_dose_up import results as results_dose

            results_dose(self.game, c, state, action)
            return
        if action["data"].get("am_code"):
            from girlframe.services.m3_am_code import results as results_code

            results_code(self.game, c, state, action)
            return
        if action["data"].get("am_scrutinized"):
            from girlframe.services.m3_am_scrutinized import results as results_am

            results_am(self.game, c, state, action)
            return
        if action["data"].get("vatgrown"):
            from girlframe.services.m3_vatgrown import results as results_doll

            results_doll(self.game, c, state, action)
            return
        if action["data"].get("oldgen_sex"):
            from girlframe.services.m3_oldgen_sex import results as results_oldgen_sex

            results_oldgen_sex(self.game, c, state, action)
            return
        if action["data"].get("casualty_sex"):
            from girlframe.services.m3_casualty import results as results_casualty_sex

            results_casualty_sex(self.game, c, state, action)
            return
        if action["data"].get("vatgrown_sex"):
            from girlframe.services.m3_vatgrown_plays import results as results_vatgrown_sex

            results_vatgrown_sex(self.game, c, state, action)
            return
        if action["data"].get("newgirl_sex"):
            from girlframe.services.m3_newgirl_sex import results as results_newgirl_sex

            results_newgirl_sex(self.game, c, state, action)
            return
        if action["data"].get("easy_target"):
            from girlframe.services.m3_easy_target import results as results_easy_target

            results_easy_target(self.game, c, state, action)
            return
        if action["data"].get("oldgen"):
            from girlframe.services.m3_oldgen import results as results_oldgen

            results_oldgen(self.game, c, state, action)
            return
        if action["data"].get("stim_sex"):
            from girlframe.services.m3_stim_sex import results as results_stim

            results_stim(self.game, c, state, action)
            return
        if action["data"].get("princess_sex"):
            from girlframe.services.m3_princess_sex import results as princess_results

            princess_results(self.game, c, state, action)
            return
        if action["data"].get("alpha_sex"):
            from girlframe.services.m3_alpha_sex import results as results_alpha_sex

            results_alpha_sex(self.game, c, state, action)
            return
        if action["data"].get("alpha"):
            from girlframe.services.m3_alpha import results as alpha_results

            alpha_results(self.game, c, state, action)
            return
        if action["data"].get("janus"):
            from girlframe.services.m3_janus_play import results as janus_results

            janus_results(self.game, c, state, action)
            return
        if action["data"].get("doctor"):
            from girlframe.services.m3_doctor import results as doctor_results

            doctor_results(self.game, c, state, action)
            return
        if action["data"].get("snoop"):
            from girlframe.services.m3_enforcer_snoop import results as snoop_results

            snoop_results(self.game, c, state, action)
            return
        if action["data"].get("mockingbird"):
            from girlframe.services.m3_mockingbird_plays import results as mock_play_results

            mock_play_results(self.game, c, state, action)
            return
        if play == "engage" and action["data"].get("engage"):
            from girlframe.services.m3_engage import results as engage_results

            engage_results(self.game, c, state, action)
            return
        if play in ("all_out_assault", "go_for_the_core") and action["data"].get("battle"):
            from girlframe.services.m3_battle import results as battle_results

            battle_results(self.game, c, action)
            return
        if play == "enforcement_initiative" and action["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import results as enforcement_results

            enforcement_results(self.game, c, state, action)
            return
        if play == "dive_deep" and action["data"].get("dive"):
            from girlframe.services.m3_dive import results as dive_results

            dive_results(self.game, c, action)
            return
        if play == "defeat" and action["data"].get("defeat"):
            from girlframe.services.m3_defeat import results as defeat_results

            defeat_results(self.game, c, action)
            return
        if play == "put_someone_beneath_you" and action["data"].get("beneath"):
            from girlframe.services.m3_beneath import results as beneath_results

            beneath_results(self.game, c, action)
            return
        if play in ("go_off_duty", "void_observation") and action["data"].get("m3"):
            action["data"]["m3_finished"] = True
            self.finish(c, state, action)
            return
        if play == "disobey_orders":
            if action["data"]["prepared"]["witnessed"]:
                shift_status(state, actor, -1)
            if level == "low":
                action["data"]["result"]["can_disobey"] = False
                self.game.request(c, action, state.handler, "handler_disobey")
                return
        if play == "flirt" and level == "low":
            target = int(action["data"]["prepared"]["target"])
            self.bond(state, actor, target, -1, action["data"]["response_event"])
            self.game.request(c, action, target, "target_flirt")
            return
        kind = {
            "keep_your_head": "actor_keep",
            "check_sensors": "actor_sensors",
            "engage": "actor_engage",
            "disobey_orders": "actor_disobey",
            "flirt": "actor_flirt",
        }[play]
        self.game.request(c, action, actor, kind)

    def finish(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        if action["data"].get("virus_order"):
            from girlframe.services.m3_virus_orders import finish_order

            finish_order(self.game, c, state, action)
            return
        if action["data"]["play"] == "disobey_orders" and action["data"]["result"].get(
            "can_disobey"
        ):
            from girlframe.services.m3_control_ritual import offer as offer_ritual

            offer_ritual(self.game, c, state, action)
        if any(x["kind"] == "control_ritual_create" for x in self.game.pending(c, action["id"])):
            return
        require(not self.game.pending(c, action["id"]), "Mandatory decisions remain pending.")
        if action["data"].get("void_keep"):
            from girlframe.services.m3_void_keep import finish_keep

            if not finish_keep(self.game, c, state, action):
                return
        from girlframe.services.m3_wyvern import intercept_finish as wyvern_intercept_finish

        if wyvern_intercept_finish(self.game, c, state, action):
            return
        from girlframe.services.m3_bonded import intercept_finish as bonded_intercept_finish

        if bonded_intercept_finish(self.game, c, state, action):
            return
        from girlframe.services.m3_consume import intercept_finish as consume_intercept_finish
        from girlframe.services.m3_consume import offer_partake

        if action["data"]["play"] == "dive_deep" and action["data"].get("receipt"):
            offer_partake(self.game, c, state, action, action["data"]["response_event"])
            if self.game.pending(c, action["id"]):
                return
        if consume_intercept_finish(self.game, c, state, action):
            return
        from girlframe.services.m3_mockingbird import intercept_finish

        if intercept_finish(self.game, c, state, action):
            return
        action["state"] = "complete"
        self.game.queue(
            c,
            action,
            "outcome",
            {
                "play": action["data"]["play"],
                "callsign": self.original_callsign(state, action),
                "receipt": action["data"]["receipt"],
                "total": action["data"]["result"].get("total"),
                "tier": action["data"]["result"].get("tier"),
                "asset_calamities": action["data"]["result"].get("asset_calamities", []),
                "forced_presentations": action["data"]["result"].get("forced_presentations", []),
                **(
                    {"blocked_before_roll": True}
                    if action["data"]["result"].get("blocked_before_roll")
                    else {}
                ),
            },
        )
        if (
            action["data"].get("prince_demands")
            or action["data"].get("prince_demand_attempt")
            or action["data"].get("play") == "disobey_orders"
        ):
            from girlframe.services.m3_prince import sync_finished

            sync_finished(self.game, c, state, action, action["data"]["response_event"])
        if any(
            action["data"].get(k)
            for k in ("bonded_child", "wyvern_child", "wyvern_pin_response", "wyvern_replacement")
        ):
            return
        if action["data"].get("consume_child"):
            # Its actual source is completed after this canonical child event exists.
            return
        if action["data"].get("vatgrown_leaving") and action["data"]["result"].get("can_disobey"):
            from girlframe.services.m3_vatgrown_support import finish_departure

            finish_departure(self.game, c, state, action, action["data"]["response_event"])
        if action["data"].get("ankou_feedback_child"):
            from girlframe.services.m3_ankou_feedback import complete_child as complete_ankou

            require(
                complete_ankou(self.game, c, state, action, action["data"]["response_event"]),
                "Complete the actual Feedback child and source.",
            )
            return
        if action["data"].get("easy_target_child"):
            from girlframe.services.m3_easy_target import complete_child as complete_easy_child

            require(
                complete_easy_child(self.game, c, state, action, action["data"]["response_event"]),
                "Complete this original Easy Target performance and source",
            )
            return
        if action["data"].get("princess_child"):
            from girlframe.services.m3_princess_sex import complete_child

            require(
                complete_child(self.game, c, state, action, action["data"]["response_event"]),
                "Complete this exact source-owned counterpart Play.",
            )
            return
        if action["data"].get("secretary_response"):
            from girlframe.services.m3_secretary import finish_response

            finish_response(self.game, c, state, action)
            parent = self.game.action(c, action["parent_id"])
            self.game.save_action(c, parent, state="awaiting_choices")
            return
        if any(
            action["data"].get(key)
            for key in (
                "battle_counter_source",
                "dormant_dive_source",
                "gorgon_counter_source",
                "alpha_counter_source",
                "alpha_sex_counter_source",
            )
        ):
            # Settle this exact counter only after its real saved completion event.
            return
        if (
            action["parent_id"]
            and not action["data"].get("void_keep")
            and not action["data"].get("defeat", {}).get("source_work")
        ):
            parent = self.game.action(c, action["parent_id"])
            requests = [
                x
                for x in self.game.pending(c, parent["id"])
                if x["actor_id"] == action["actor_id"]
                and x["kind"]
                in (
                    "escape_play",
                    "order_disobey",
                    "am_prepare",
                    "am_code_prepare",
                    "beneath_response_play",
                    "beneath_defeat",
                    "required_defeat",
                )
            ]
            require(len(requests) == 1, "The parent response linkage changed.")
            table = t.m2["m2_choices"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == requests[0]["id"],
                )
                .values(state="completed_by_child", revision=requests[0]["revision"] + 1)
            )
            parent["data"]["result"]["response_play"] = action["id"]
            if requests[0]["kind"] == "escape_play":
                parent["data"]["result"]["escaped"] = True
            if not self.game.pending(c, parent["id"]):
                if parent["data"].get("actor_basic"):
                    from girlframe.services.m3_actor_plays import ActorPlayService

                    ActorPlayService(self.game).finish(c, state, parent)
                else:
                    self.finish(c, state, parent)
            self.game.save_action(c, parent)

    def original_callsign(self, state: GameState, action: dict[str, Any]) -> str:
        sheet = state.sheets.get(action["actor_id"])
        if sheet is not None:
            return sheet.callsign
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_careers import original_sheet

        character = action["data"].get("character_ids", {}).get(action["actor_id"])
        return original_sheet(
            state, ActorRef(kind="pilot", entity=action["actor_id"], incarnation=character)
        ).callsign
