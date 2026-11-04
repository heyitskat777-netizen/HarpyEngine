"""Source-backed transitions; every voluntary choice is supplied by its human owner."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

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

    def tag_resolved(self, state: GameState, owner: int, tag: str) -> None:
        for item in state.obligations:
            if (
                item.owner == owner
                and item.details.get("tag") == tag
                and item.kind in ("reject_tag", "cannot_refuse_until_tag_resolved")
            ):
                item.state = "fulfilled"

    def unmark(self, sheet: PilotSheet, ids: tuple[str, ...], maximum: int) -> None:
        picks(
            ids,
            {x.id for x in sheet.identities if x.marked and x.id not in sheet.sedation_locked},
            0,
            maximum,
        )
        for entry in sheet.identities:
            if entry.id in ids:
                entry.marked = False

    def bond(self, state: GameState, first: int, second: int, delta: int) -> None:
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
        acting = state.sheets[str(actor)]
        body = json.loads(request["body_json"])
        if kind == "tag_window":
            self.tag_proposal(c, state, action, owner, answer)
            if not any(
                x["kind"] == "tag_window" and x["state"] == "pending"
                for x in self.game.pending(c, action["id"])
            ):
                self.close_tag_window(c, state, action)
            return
        if kind == "tag_resolution":
            tag = next((x for x in acting.tags if x.id == body["tag"]), None)
            require(tag is not None, "The marked Tag is no longer available.")
            assert tag is not None
            picks(answer.options, {"reject", "embrace"}, 1)
            if answer.options == ("reject",):
                require(
                    not (acting.girl == "NEWGIRL" and tag.giver == acting.mentor),
                    "A Newgirl cannot reject a Tag given by its Mentor.",
                )
                tag.rejection_pending = True
                self.game.obligation(state, action, "reject_tag", actor, tag=tag.id)
            else:
                picks(answer.denied, {x.id for x in acting.identities if not x.protected}, 1)
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
                self.bond(state, actor, owner, 1)
                item.state = "fulfilled"
            action["data"]["result"].update(confirmed=answer.flag, response=answer.text)
            self.finish(c, state, action)
            return
        result = action["data"]["result"]
        level = result.get("tier")
        if kind == "actor_keep":
            automatic = (
                {"sexy"}
                if acting.girl == "PRINCESS"
                else {"vicious"}
                if acting.girl == "ALPHA"
                else set()
            )
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
            if acting.girl == "OLDGEN" and answer.flag:
                positives.add("experienced")
            if acting.frame == "WYVERN 0.4" and action["data"]["prepared"]["piloting"]:
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
            picks(answer.options, set(QUESTIONS), 1 if level == "low" else 0, count)
            require(
                set(answer.fields) <= {"q1", "q2", "q3"}
                and all(x.strip() for x in answer.fields.values()),
                "Provide valid custom questions.",
            )
            require(
                len(answer.options) + len(answer.fields) == count
                and (level != "low" or not answer.fields),
                "Choose the printed question count; low results use listed questions only.",
            )
            result["questions"] = list(answer.options) + [
                answer.fields[x] for x in sorted(answer.fields)
            ]
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
                    picks(answer.denied, {x.id for x in acting.tags}, 1)
                    rejected = next(x for x in acting.tags if x.id == answer.denied[0])
                    require(
                        not (acting.girl == "NEWGIRL" and rejected.giver == acting.mentor),
                        "A Newgirl cannot reject a Mentor Tag.",
                    )
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
            picks(answer.options, set(FLIRT_QUESTIONS), 1)
            self.unmark(acting, answer.denied, 2)
            result["question"] = answer.options[0]
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
            self.unmark(sheet, answer.denied, 1 if level == "low" else 2)
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
                    self.game.request(c, action, state.handler, "handler_brief")
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
        if kind in ("escape_play", "order_disobey"):
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
        actor = int(action["actor_id"])
        sheet = state.sheets[str(actor)]
        picks(answer.options, {"pass", "tag"}, 1)
        if answer.options == ("pass",):
            require(
                not answer.denied and set(answer.fields) <= {"status"},
                "A pass does not modify a Tag.",
            )
        else:
            picks(
                answer.denied,
                {
                    x.id
                    for x in sheet.tags
                    if (owner in x.observers or owner == actor)
                    and x.scene_used != action["scene_id"]
                },
                1,
            )
            tag = next(x for x in sheet.tags if x.id == answer.denied[0])
            require(
                owner != actor
                or (sheet.girl == "NEWGIRL" and tag.giver == sheet.mentor)
                or (sheet.girl == "PRINCESS" and action["data"]["play"] == "flirt"),
                "Only another player or a printed self-mark exception can mark this Girl Tag.",
            )
            require(
                answer.number in (-1, 1) and bool(answer.text.strip()),
                "Choose a direction and explain relevance.",
            )
        if (
            owner == actor
            and sheet.girl == "ALPHA"
            and state.order
            and state.order[-1] == actor
            and not sheet.status_marked
        ):
            require(
                set(answer.fields) <= {"status"}, "Choose only the supported Dog Status modifier."
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
        elif answer.fields:
            raise WorkflowError("This actor has no supported Status-mark modifier.")

    def close_tag_window(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        actor = int(action["actor_id"])
        sheet = state.sheets[str(actor)]
        proposals = []
        for person in action["data"]["participants"]:
            answer = self.answered(action, "tag_window", person)
            if answer.options == ("tag",):
                proposals.append((person, answer))
        selected = None
        for entry in proposals:
            if selected is None or higher(state, entry[0], selected[0]):
                selected = entry
        if selected:
            person, answer = selected
            tag = next(x for x in sheet.tags if x.id == answer.denied[0])
            require(
                tag.scene_used != action["scene_id"], "This Tag was already used in this scene."
            )
            old = tag.marked
            tag.marked = True
            tag.scene_used = action["scene_id"]
            sheet.revision += 1
            depth = state.bonds.get(pair_key(actor, person), 0)
            bonus = 2 if depth == 1 else int(state.intense_tag_bonus or 1) if depth == 2 else 1
            action["data"]["modifiers"].append(
                {
                    "source": "girl_tag",
                    "tag": tag.id,
                    "actor": person,
                    "amount": bonus * int(answer.number or 0),
                }
            )
            self.set_total(action)
            if sheet.girl == "BONDED" and sheet.pair == person:
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
        action["data"]["result"].update(total=total, tier=tier(total))

    def results(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        self.set_total(action)
        action["state"] = "awaiting_choices"
        actor = int(action["actor_id"])
        play = action["data"]["play"]
        level = action["data"]["result"]["tier"]
        if play == "go_off_duty" and action["data"].get("m3"):
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
            self.bond(state, actor, target, -1)
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
        require(not self.game.pending(c, action["id"]), "Mandatory decisions remain pending.")
        action["state"] = "complete"
        self.game.queue(
            c,
            action,
            "outcome",
            {
                "play": action["data"]["play"],
                "callsign": state.sheets[action["actor_id"]].callsign,
                "receipt": action["data"]["receipt"],
                "total": action["data"]["result"].get("total"),
                "tier": action["data"]["result"].get("tier"),
            },
        )
        if action["parent_id"]:
            parent = self.game.action(c, action["parent_id"])
            requests = [
                x
                for x in self.game.pending(c, parent["id"])
                if x["actor_id"] == action["actor_id"]
                and x["kind"] in ("escape_play", "order_disobey")
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
            self.finish(c, state, parent)
            self.game.save_action(c, parent)
