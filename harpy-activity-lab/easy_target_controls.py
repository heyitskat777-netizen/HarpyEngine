"""Easy Target original reactions, factual effects, and assigned scene Plays."""

import sqlalchemy as sa

from girlframe.database import tables
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_easy_target import easy_target_choice_fields
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle import resource_sha
from girlframe.engine.m3_battle_state import Context, Declaration
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_easy_target import EasyTargetService, prepare
from girlframe.services.onboarding import WorkflowError

EASY = rules.PLAY
FAILURE = "easy_target_protection_failure"
FAILURE_TAG = "easy_target_protection_failure_tag"
OPERATIONS = frozenset((EASY, FAILURE, FAILURE_TAG))
SOURCE_KIND = "easy_target_child"
CHILD_ACTION = "easy_target_child_play"
BATTLE_ACTION = "easy_target_battle"
ASSAULT = "all_out_assault"
ENGAGE = "engage"
FLIRT = "flirt"
ANSWERS = frozenset(
    (
        "easy_target_select",
        "easy_target_tag",
        "easy_target_react",
        "easy_target_validate",
        "easy_target_bond",
        "easy_target_judge",
        "easy_target_failure",
        "easy_target_contempt",
        SOURCE_KIND,
    )
)
DIRECT_CHILDREN = frozenset(
    (
        "npc_hurt",
        "npc_protect",
        "npc_use",
        "pilot_use",
        "handler_use",
        "handler_protect",
        "pilot_protect",
        "protection_cohort",
        "use_cohort",
        "hurt_cohort",
    )
)
CHILD_PLAYS = {"keep_your_head": "Keep Your Head", "check_sensors": "Check Your Sensors"}
SELECTS = frozenset(("select", "urge", "primary", "play", "yes", "performance", "outcome"))


class EasyTargetControls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.service = EasyTargetService(game)

    def forms(self, viewer, state, sheet, card):
        try:
            menu = self.service.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return
        if menu["revision"] != state.revision:
            return
        if (
            menu["can_start"]
            and sheet
            and sheet.heat > 0
            and not any(row.play == EASY for row in sheet.blocked_plays)
        ):
            try:
                with self.game.store.engine.connect() as c:
                    prepare(
                        self.game,
                        c,
                        viewer,
                        state.model_copy(deep=True),
                        PlayInput(
                            play=EASY,
                            heat=1,
                            context="Eligibility preview",
                            trigger_confirmed=True,
                        ),
                        self.channel,
                    )
            except (ValueError, WorkflowError):
                pass
            else:
                spends = (sheet.heat,) if sheet.heat >= 5 else range(1, sheet.heat + 1)
                yield card(
                    EASY,
                    sheet.revision,
                    "Easy Target",
                    [
                        Field(
                            "heat",
                            "Heat to spend",
                            tuple((str(amount), str(amount)) for amount in spends),
                        ),
                        Field(
                            "context", "Describe the actual mistake or statement", paragraph=True
                        ),
                    ],
                )
        for task in menu["tasks"]:
            try:
                source = self.service.view(viewer, task["id"])
            except (ValueError, WorkflowError):
                continue
            if source["source"]["cast"]["channel"] != self.channel:
                continue
            if source.get("can_report_failure"):
                yield card(
                    f"{FAILURE}:{task['id']}",
                    state.revision,
                    "Report failed protection",
                    [
                        Field("attempt", "Actual attempted prevention", paragraph=True),
                        Field("occurred", "What actually happened", paragraph=True),
                    ],
                    label="File the original factual ruling",
                )
            if source.get("can_failure_tag"):
                yield card(
                    f"{FAILURE_TAG}:{task['id']}",
                    state.revision,
                    "Protection failed · Give a Tag?",
                    [
                        Field(
                            "give",
                            "Give the original protector a Tag?",
                            (("yes", "Give a Tag"), ("no", "Decline")),
                        ),
                        Field("account", "The Tag or your explicit decline", paragraph=True),
                    ],
                    label="File your choice",
                )

    def perform(self, viewer, key, operation, revision, values):
        name, _, identity = operation.partition(":")
        if name == EASY and values.keys() == {"heat", "context"}:
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=EASY,
                    heat=int(values["heat"]),
                    context=values["context"],
                    trigger_confirmed=True,
                ),
            )
        if name in (FAILURE, FAILURE_TAG):
            source = self.service.view(viewer, identity)
            if source["source"]["cast"]["channel"] != self.channel:
                raise WorkflowError("Return to the original protection source.")
            if name == FAILURE and values.keys() == {"attempt", "occurred"}:
                return self.service.fail_protection(
                    viewer,
                    key,
                    identity,
                    revision,
                    values["attempt"],
                    values["occurred"],
                )
            if (
                name == FAILURE_TAG
                and values.keys() == {"give", "account"}
                and values["give"] in ("yes", "no")
            ):
                return self.service.failure_tag(
                    viewer,
                    key,
                    identity,
                    revision,
                    values["give"] == "yes",
                    values["account"],
                )
        raise ValueError("Use the fields from the original Easy Target record.")


def needs_child(detail):
    return detail["kind"] == SOURCE_KIND and not any(detail[key] for key in DIRECT_CHILDREN)


def choice_fields(detail):
    if needs_child(detail):
        raise WorkflowError(
            "Complete the genuine assigned Play or join the matching assisted action."
        )
    return easy_target_choice_fields(detail)


def unsupported_work(detail):
    work = detail.get("work")
    if not work or not work["play"] or detail["kind"] not in (SOURCE_KIND, "easy_target_validate"):
        return None
    if not work["performer"] or work["performer"]["kind"] != "pilot":
        return "HarpyEngine needs a native Play adapter for the original non-pilot performer."
    if work["play"] == "disobey_orders":
        return (
            "Disobey Orders requires its own recorded Order. "
            "HarpyEngine's Easy Target source cannot bind that Order."
        )
    if work["urge"] == "hurt" and work["play"] != ASSAULT:
        return "This Hurt reaction requires the original physical All-Out Assault."
    if work["urge"] == "protect" and work["play"] != ENGAGE:
        return "This protection reaction requires an actual Engage maneuver."
    if work["play"] == ASSAULT and work["urge"] != "hurt":
        return "HarpyEngine can link an Assault to this source only for the original Hurt reaction."
    if work["play"] not in {*CHILD_PLAYS, ENGAGE, FLIRT, ASSAULT}:
        return "HarpyEngine has no supported Activity form for this saved Easy Target Play."
    return None


def child_fields(game, viewer, detail, choice):
    work = detail["work"]
    if work["urge"] == "cohort":
        return choice["revision"], "Awaiting your positive Tag on the primary's Play", []
    sheet = game.sheet(viewer)
    heat = Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet["heat"] + 1)))
    if work["play"] in CHILD_PLAYS:
        return sheet["revision"], CHILD_PLAYS[work["play"]], [heat]
    if work["play"] == ENGAGE and work["urge"] == "protect":
        return sheet["revision"], "Engage · Protect the original pilot", [heat]
    if work["play"] in (FLIRT, ENGAGE):
        view = BattleService(game.store).preview(viewer, detail["channel"])
        targets = tuple(
            (ActorRef.model_validate(row["ref"]).model_dump_json(), row["name"])
            for row in view["actors"]
            if row["ref"] != work["performer"]
            and (work["play"] == ENGAGE or row["ref"]["kind"] == "pilot")
        )
        label = "Flirt" if work["play"] == FLIRT else "Engage"
        if not targets:
            return sheet["revision"], label + " · Awaiting an eligible participant", []
        return (
            sheet["revision"],
            label,
            [
                Field("target", "Original scene participant", targets),
                heat,
            ],
        )
    if work["play"] == ASSAULT:
        battle = BattleService(game.store)
        view = battle.preview(viewer, detail["channel"])
        open_ids = {task["id"] for task in battle.tasks(viewer)}
        if any(
            value["source_choice"] == choice["id"] and value["id"] in open_ids
            for value in view["contexts"]
        ):
            return None
        actor = next((row for row in view["actors"] if row["ref"] == work["performer"]), None)
        target = next((row for row in view["actors"] if row["ref"] == detail["newgirl"]), None)
        if not actor or not target or not actor["assets"] or not target["assets"]:
            return view["revision"], "All-Out Assault · Awaiting intact Assets", []
        return (
            view["revision"],
            "Declare All-Out Assault on " + target["name"],
            [
                Field("attacking_asset", "Your intact attacking Asset", asset_options(actor)),
                Field("target_asset", "The opposing intact Asset", asset_options(target)),
            ],
        )
    return None


def asset_options(actor):
    return tuple((asset["id"], asset["name"]) for asset in actor["assets"])


def begin_child(game, viewer, key, action, revision, source, values):
    with game.store.engine.connect() as c:
        state = load_state(c, game.store.campaign_id)
        work = next(
            (
                row
                for row in rules.records(state, rules.Reaction)
                if row.id == source and row.session == action["id"]
            ),
            None,
        )
        if work is None or not work.performer:
            raise WorkflowError("Use the original required Easy Target performance.")
        target = rules.get(state, rules.Session, work.session).actor
        if work.play == ASSAULT:
            if work.controller != viewer.user_id:
                raise WorkflowError("The original performer owns this Assault declaration.")
            if values.keys() != {"attacking_asset", "target_asset"}:
                raise ValueError("Select the actual Assets for the required Assault.")
            history = tables.m2["m2_state_history"]
            raw = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == game.store.campaign_id,
                    history.c.revision == revision,
                )
            )
            if not raw:
                raise WorkflowError("Reopen the original Assault form.")
            original = GameState.model_validate_json(raw)
            bound = profiles(c, game.store.campaign_id)
            declaration = Declaration(
                play=ASSAULT,
                actor=work.performer,
                target=target,
                actor_sha256=resource_sha(original, work.performer, bound),
                target_sha256=resource_sha(original, target, bound),
                account=work.context,
                **values,
            )
    channel = int(action["channel_id"])
    if work.play == ASSAULT:
        return BattleService(game.store).propose(
            viewer, key, revision, channel, declaration, parent=work.session
        )
    if work.play in (FLIRT, ENGAGE) and work.urge != "protect":
        if values.keys() != {"heat", "target"}:
            raise ValueError("Select an actual participant in the original scene.")
        target = ActorRef.model_validate_json(values["target"])
        if work.play == FLIRT and target.kind != "pilot":
            raise ValueError("Select the original pilot for this Flirt response.")
    elif work.play not in {*CHILD_PLAYS, ENGAGE} or values.keys() != {"heat"}:
        raise WorkflowError("Use the original required Easy Target performance.")
    return game.begin(
        viewer,
        key,
        channel,
        revision,
        PlayInput(
            play=work.play,
            parent=action["id"],
            source_work=work.id,
            context=work.context,
            target_actor=target if work.play == ENGAGE else None,
            target=int(target.entity) if work.play == FLIRT else None,
            heat=int(values["heat"]),
            trigger_confirmed=True,
        ),
    )


def battle_origin(state, identity):
    record = next(
        (
            row
            for row in reversed(state.facts)
            if row.get("kind") == "battle_context" and row["id"] == identity
        ),
        None,
    )
    if record:
        context = Context.model_validate_json(record["body"])
        return context.source_action if context.declaration.play == ASSAULT else None
    return None


def battle_forms(game, viewer):
    battle = BattleService(game.store)
    for task in battle.tasks(viewer):
        origin = task["source_action"]
        if not origin:
            continue
        with game.store.engine.connect() as c:
            parent = game.action(c, origin)
        if parent["data"]["play"] != EASY:
            continue
        source = battle.context(viewer, task["id"])
        if not source["source_work"]:
            continue
        if task["incoming"] and task["state"] == "proposed":
            yes_no = (("yes", "Yes"), ("no", "No"))
            fields = [
                Field("opening", "Is there a genuine opening?", yes_no),
                Field("reach", "Is the original target in reach?", yes_no),
                Field(
                    "outside_permission", "Confirm permission for a body outside its Frame", yes_no
                ),
                Field("indirect", "Is the attack indirect?", yes_no),
                Field("evidence", "Actual opening, reach, and circumstances", paragraph=True),
            ]
            yield (
                task,
                "easy_assault_review",
                "All-Out Assault · Review the opening",
                fields,
                source["context"]["declaration"]["account"],
            )
        elif task["state"] == "confirmed":
            declaration = source["context"]["declaration"]
            actor = next(
                (
                    row
                    for row in battle.preview(viewer, source["channel"])["actors"]
                    if row["ref"] == declaration["actor"]
                ),
                None,
            )
            if actor is not None:
                piloting = "yes" if actor["piloting"] else "no"
                fields = [
                    Field(
                        "piloting",
                        "Original cockpit state",
                        ((piloting, "Piloting" if actor["piloting"] else "On foot or seated"),),
                    )
                ]
                yield (
                    task | {"revision": game.sheet(viewer)["revision"]},
                    "easy_assault_start",
                    "All-Out Assault · Start the original Play",
                    fields,
                    declaration["account"],
                )
        elif task["state"] == "proposed":
            yield task, "", "All-Out Assault · Awaiting the assigned judge", [], None


def advance_battle(game, viewer, key, identity, revision, operation, values):
    battle = BattleService(game.store)
    source = battle.context(viewer, identity)
    context = Context.model_validate(source["context"])
    if (
        not source["source_work"]
        or not context.source_action
        or context.declaration.play != ASSAULT
    ):
        raise WorkflowError("Open the original required Assault.")
    with game.store.engine.connect() as c:
        parent = game.action(c, context.source_action)
    if parent["data"]["play"] != EASY:
        raise WorkflowError("Open the original Easy Target scene.")
    if operation == "easy_assault_review":
        factors = {"opening", "reach", "outside_permission", "indirect"}
        if values.keys() != factors | {"evidence"} or any(
            values[k] not in ("yes", "no") for k in factors
        ):
            raise ValueError("Review the actual named circumstances.")
        return battle.confirm(
            viewer,
            key,
            revision,
            identity,
            evidence=values["evidence"],
            **{k: values[k] == "yes" for k in factors},
        )
    if (
        operation == "easy_assault_start"
        and values.keys() == {"piloting"}
        and values["piloting"] in ("yes", "no")
    ):
        declaration = context.declaration
        return game.begin(
            viewer,
            key,
            source["channel"],
            revision,
            PlayInput(
                play=ASSAULT,
                parent=context.source_action,
                source_work=source["source_work"],
                target_actor=declaration.target,
                attacking_asset=declaration.attacking_asset,
                target_asset=declaration.target_asset,
                battle_context=identity,
                context=declaration.account,
                heat=0,
                trigger_confirmed=True,
                piloting=values["piloting"] == "yes",
            ),
        )
    raise ValueError("Use the original Assault's current step.")
