"""Start native specialist Plays through the original HarpyEngine scene controls."""

import json

from alpha_controls import BRUTALIZE
from am_scene_controls import PLAYS as AM_PLAYS
from am_scene_controls import SOURCE_OPERATIONS as AM_OPERATIONS
from am_scene_controls import AmControls
from doll_controls import OPERATIONS as DOLL_OPERATIONS
from doll_controls import DollControls
from easy_target_controls import OPERATIONS as EASY_OPERATIONS
from easy_target_controls import EasyTargetControls
from native_scene_forms import (
    BARELY,
    BONDED_SIDE,
    BONDED_SOURCE,
    CASUALTY_PARTS,
    CONSUME_PLAYS,
    DOCTOR_PLAYS,
    DOSE,
    DOSE_CONTACT,
    ENFORCEMENT,
    HANDLER_TRACKER,
    HANDLER_WARP,
    NATIVE_TITLES,
    PANDORA,
    PROCESSOR,
    PROCESSOR_PROPOSAL,
    PROCESSOR_UNLINK,
    TRACKER_MOMENT,
    form_fields,
    heat_options,
)
from prince_controls import OPERATIONS as PRINCE_OPERATIONS
from prince_controls import PERFORMER, PrinceControls
from wyvern_controls import PLAYS as WYVERN_PLAYS
from wyvern_controls import SOURCE_OPERATIONS as WYVERN_SOURCE_OPERATIONS
from wyvern_controls import WyvernControls

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine import (
    m3_alpha,
    m3_ankou,
    m3_bonded,
    m3_casualty,
    m3_doctor,
    m3_dose_up,
    m3_wyvern,
)
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_clone_am import additional_identities
from girlframe.engine.m3_enforcer import initiative
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import SOURCE_RULE
from girlframe.engine.m3_prince import current_fanbase
from girlframe.engine.m3_tracker_implants import PLAYS as TRACKER_LABELS
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_alpha import preview as alpha_preview
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_ankou import prepare as prepare_processor
from girlframe.services.m3_ankou import require_rule as require_processor
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_bonded import BondedService
from girlframe.services.m3_bonded import prepare as prepare_bonded
from girlframe.services.m3_casualty import CasualtyService
from girlframe.services.m3_consume import ConsumeService
from girlframe.services.m3_consume import prepare as prepare_consume
from girlframe.services.m3_contaminant_zone import warp_options
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_doctor import prepare as prepare_doctor
from girlframe.services.m3_dose_up import DoseUpService
from girlframe.services.m3_enforcement_initiative import preview as enforcement_preview
from girlframe.services.m3_handler_book_orders import book_rule_available
from girlframe.services.m3_handler_plays import HandlerPlayService, _ordinary_scene_idle
from girlframe.services.m3_janus_pandora import prepare as prepare_birth
from girlframe.services.m3_tracker_implants import TrackerService
from girlframe.services.onboarding import WorkflowError


class NativeSceneRolls:
    def __init__(self, game, channel):
        self.game, self.channel = game, channel
        self.doctor = DoctorService(game)
        self.dose = DoseUpService(game.store, game)
        self.consume = ConsumeService(game)
        self.ankou = AnkouService(game)
        self.bonded = BondedService(game)
        self.casualty = CasualtyService(game)
        self.trackers = TrackerService(game.store)
        self.handler_plays = HandlerPlayService(game.store)
        self.wyvern = WyvernControls(game, channel)
        self.prince = PrinceControls(game, channel)
        self.am = AmControls(game, channel)
        self.doll = DollControls(game, channel)
        self.easy_target = EasyTargetControls(game, channel)

    @staticmethod
    def card(identity, revision, instruction, fields, *, label="Confirm and start Play"):
        return {
            "id": identity,
            "revision": revision,
            "action": "specialist_scene",
            "instruction": instruction,
            "operations": [
                {
                    "id": identity,
                    "label": label,
                    "fields": form_fields(fields),
                }
            ],
        }

    def view(self, viewer):
        try:
            with self.game.store.engine.connect() as connection:
                self.game.authorize(connection, viewer, game=False)
                scene = self.game.scene(connection, self.channel)
                self.game.unpaused(connection)
                self.game.scene_unpaused(connection, scene["id"])
                lock = self.game.lock(connection, self.channel)
                state = load_state(connection, self.game.store.campaign_id)
        except WorkflowError:
            return []
        cards = [
            self.card(
                f"{operation}:{identity}", revision, title, fields, label="File your response"
            )
            for operation, identity, revision, title, fields in self.wyvern.assigned(viewer, state)
        ]
        locked = bool(lock and lock["state"] != "released")
        sheet = state.sheets.get(str(viewer.user_id))
        cards.extend(
            self.doll.forms(
                viewer,
                state,
                sheet,
                self.card,
                can_start=viewer.user_id in scene["participants"] and not locked,
                locked=locked,
            )
        )
        if viewer.user_id in scene["participants"] or viewer.user_id == state.handler:
            cards.extend(self.am.forms(viewer, state, sheet, locked, self.card))
            cards.extend(self.am.reset_cards(viewer, state, self.card))
            if not locked:
                cards.extend(self.easy_target.forms(viewer, state, sheet, self.card))
        if locked:
            return cards
        if viewer.user_id == state.handler:
            if part_damage := self.casualty_card(viewer, state, scene):
                cards.append(part_damage)
            cards.extend(self.handler_source_cards(viewer, state))
        if sheet is None or not sheet.character_id or viewer.user_id not in scene["participants"]:
            return cards
        actor = current_ref(state, viewer.user_id)
        cards.extend(self.body_moment_cards(viewer, state, actor))
        blocked = {item.play for item in sheet.blocked_plays}
        if ENFORCEMENT not in blocked and initiative(state, actor):
            preview = enforcement_preview(self.game, viewer, self.channel)
            if preview["available"]:
                cards.append(self.enforcement_card(preview))
        if DOSE not in blocked and has_rule(sheet, m3_dose_up.RULE, "STIM-BLISSED"):
            cards.extend(self.dose_cards(viewer, state, sheet))
        if (
            BRUTALIZE not in blocked
            and has_rule(sheet, m3_alpha.RULE, "ALPHA")
            and (brutality := self.brutalize_card(viewer, sheet))
        ):
            cards.append(brutality)
        if BONDED_SIDE not in blocked and has_rule(sheet, m3_bonded.SIDE, "BONDED"):
            cards.extend(self.bonded_cards(viewer, state, sheet, actor))
        if BARELY not in blocked and (repair := self.barely_card(viewer, state, sheet)):
            cards.append(repair)
        if sheet.frame == "CONSUME" and not sheet.frame_scrapped:
            cards.extend(self.consume_cards(viewer, state, sheet))
        if (
            sheet.frame == "JANUS"
            and not sheet.frame_scrapped
            and (birth := self.pandora_card(viewer, state, sheet))
        ):
            cards.append(birth)
        if (
            (sheet.frame == "THE PRINCE" or current_fanbase(state, actor))
            and not sheet.frame_scrapped
            and PERFORMER not in blocked
        ):
            cards.extend(self.prince.forms(viewer, state, sheet, self.card))
        if sheet.frame == m3_ankou.FRAME and not sheet.frame_scrapped:
            cards.extend(self.processor_cards(viewer, state, sheet))
        if sheet.frame == m3_wyvern.FRAME and not sheet.frame_scrapped:
            cards.extend(
                self.card(identity, revision, title, fields, label=label)
                for identity, revision, title, fields, label in self.wyvern.starters(
                    viewer, state, sheet
                )
            )
        if sheet.frame == m3_doctor.BOOK and not sheet.frame_scrapped:
            try:
                menu = self.doctor.menu(viewer, self.channel)
            except (ValueError, WorkflowError):
                pass
            else:
                cards.extend(self.doctor_cards(viewer, menu, state, sheet))
        return cards

    def handler_source_cards(self, viewer, state):
        try:
            tracked = self.trackers.play_options(viewer, self.channel)
        except (ValueError, WorkflowError):
            tracked = {"sources": [], "revision": state.revision}
        if tracked["revision"] != state.revision:
            return []
        cards = []
        for operation, play in HANDLER_TRACKER.items():
            sources = tuple(
                (
                    json.dumps([row["tracker"], row["moment"]]),
                    row["label"] + (" · " + row["moment"][-8:] if row["moment"] else ""),
                )
                for row in tracked["sources"]
                if row["play"] == play
            )
            if sources:
                cards.append(
                    self.card(
                        operation,
                        state.revision,
                        dict(TRACKER_LABELS)[play],
                        [
                            Field(
                                "source",
                                "Private observation source"
                                if play.endswith("voyeur")
                                else "Tracked person",
                                sources,
                            ),
                        ],
                        label="Prepare the native Handler effect",
                    )
                )
        try:
            with self.game.store.engine.connect() as c:
                _ordinary_scene_idle(c, self.game)
                cast = _cast(self.game, c, state, self.channel)
                handler = active_handler(state)
                zones = (
                    warp_options(self.game, c, state, handler)
                    if any(
                        row.actor == handler and row.controller == viewer.user_id
                        for row in cast.roles
                    )
                    else []
                )
        except (ValueError, WorkflowError):
            zones = []
        if zones:
            cards.append(
                self.card(
                    HANDLER_WARP,
                    state.revision,
                    "Contaminant Zone · Warp",
                    [
                        Field(
                            "zone",
                            "Your intact quarantined zone",
                            tuple((zone["id"], zone["label"]) for zone in zones),
                        ),
                    ],
                    label="Prepare the native Handler effect",
                )
            )
        return cards

    def body_moment_cards(self, viewer, state, actor):
        try:
            menu = self.trackers.menu(viewer)
            if menu["owner"] or menu["game_revision"] != state.revision:
                return []
            if menu["actor"] != actor.model_dump(mode="json") or not any(
                str(self.channel) == row["id"] for row in menu["scenes"]
            ):
                return []
        except (ValueError, WorkflowError):
            return []
        # The body owner receives this form without any implant lookup or disclosure.
        return [
            self.card(
                TRACKER_MOMENT,
                state.revision,
                "Record a private moment",
                [
                    Field("context", "Describe your current fictional moment", paragraph=True),
                ],
                label="File the private moment",
            )
        ]

    def bonded_cards(self, viewer, state, sheet, actor):
        try:
            menu = self.bonded.menu(viewer, self.channel)
            if menu["revision"] != state.revision or "side" not in menu["available"]:
                return []
            with self.game.store.engine.connect() as c:
                sources = []
                for source in m3_bonded.records(state, m3_bonded.Source):
                    if (
                        source.kind != "side"
                        or source.actor != actor
                        or source.cast.channel != self.channel
                    ):
                        continue
                    try:
                        prepare_bonded(
                            self.game,
                            c,
                            viewer,
                            state,
                            PlayInput(
                                play=BONDED_SIDE,
                                context="Eligibility preview",
                                trigger_confirmed=True,
                                heat=0,
                                source_work=source.id,
                            ),
                            self.channel,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    sources.append((source.id, source.account))
        except (ValueError, WorkflowError):
            return []
        if not sources:
            return [
                self.card(
                    BONDED_SOURCE,
                    state.revision,
                    "Always By Her Side · " + menu["pair_label"],
                    [
                        Field(
                            "apart",
                            "I want to be with my actual Pair and we are apart",
                            (("yes", "Confirm the trigger"),),
                        ),
                        Field("context", "Record the actual situation", paragraph=True),
                    ],
                    label="File the original Pair source",
                )
            ]
        fields = [
            Field("source", "Filed Pair source", tuple(sources)),
            Field("heat", "Heat to spend", tuple((str(n), str(n)) for n in range(sheet.heat + 6))),
            Field("context", "Describe the actual trigger", paragraph=True),
        ]
        identities = tuple(
            (item.id, item.name)
            for item in (*sheet.identities, *additional_identities(state, sheet.owner))
            if not item.marked
        )
        if identities:
            fields.extend(
                (
                    Field("identity", "Optional Identity to mark", identities, required=False),
                    Field(
                        "gain",
                        "Heat gained from marking",
                        tuple((str(n), str(n)) for n in (1, 2, 3, 5)),
                        required=False,
                    ),
                    Field(
                        "share",
                        "Paired Identity Heat to give your Pair",
                        tuple((str(n), str(n)) for n in range(6)),
                        required=False,
                    ),
                )
            )
        return [self.card(BONDED_SIDE, sheet.revision, "Always By Her Side", fields)]

    def casualty_card(self, viewer, state, scene):
        try:
            if not book_rule_available(self.game, SOURCE_RULE):
                return None
            Access(self.game.store).registry.require_available(m3_casualty.GOD)
            menu = self.casualty.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return None
        if menu["revision"] != state.revision:
            return None
        targets = tuple(
            (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"])
            for row in menu["damage_targets"]
            if int(row["ref"]["entity"]) in scene["participants"]
        )
        if not targets:
            return None
        return self.card(
            CASUALTY_PARTS,
            state.revision,
            "Damage an original Casualty part",
            [
                Field("actor", "Original Casualty in this scene", targets),
                Field(
                    "part",
                    "Original part",
                    tuple((part, m3_casualty.LABELS[part]) for part in m3_casualty.PARTS),
                ),
                Field(
                    "condition",
                    "Actual condition",
                    (
                        ("broken", "Broken"),
                        ("destroyed", "Destroyed"),
                        ("removed", "Removed"),
                    ),
                ),
                Field("context", "Describe the actual effect", paragraph=True),
            ],
            label="File the part damage",
        )

    def barely_card(self, viewer, state, sheet):
        native = has_rule(sheet, BARELY, "CASUALTY")
        if not native and not (
            sheet.girl_runtime
            and any(
                row.rule_id == BARELY and not row.used_event
                for row in sheet.girl_runtime.learned_plays
            )
        ):
            return None
        try:
            with self.game.store.engine.connect() as c:
                gate = Access(self.game.store)
                gate.authorize(c, viewer, "plays", director_response=True)
                gate.registry.require_available(BARELY)
            menu = self.casualty.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return None
        if (
            menu["revision"] != state.revision
            or not menu["barely_available"]
            or not menu["assets"]
            or not menu["identities"]
        ):
            return None
        fields = [
            Field(
                "identity",
                "Original Identity to erase",
                tuple((x["id"], x["label"]) for x in menu["identities"]),
            ),
            Field(
                "asset",
                "Owned damaged Asset to repair",
                tuple((x["id"], x["label"]) for x in menu["assets"]),
            ),
            Field("account", "Describe the actual sacrifice", paragraph=True),
        ]
        if menu["barely_lessons"]:
            fields.insert(
                0,
                Field(
                    "lesson",
                    "Original one-use lesson",
                    tuple((x["id"], x["label"]) for x in menu["barely_lessons"]),
                ),
            )
        return self.card(
            BARELY,
            state.revision,
            NATIVE_TITLES[BARELY],
            fields,
            label="Confirm Identity erasure and repair",
        )

    def brutalize_card(self, viewer, sheet):
        preview = alpha_preview(self.game, viewer, self.channel)
        if not preview["available"]:
            return None
        identities = tuple((item.id, item.name) for item in sheet.identities if not item.marked)
        fields = [
            Field(
                "target",
                "Actual target",
                tuple(
                    (ActorRef.model_validate(row["ref"]).model_dump_json(), row["label"])
                    for row in preview["targets"]
                ),
            ),
            Field(
                "heat",
                "Heat to spend",
                tuple((str(n), str(n)) for n in range(sheet.heat + 6))
                if identities
                else heat_options(sheet.heat),
            ),
            Field("context", "Describe the actual confrontation", paragraph=True),
        ]
        if identities:
            fields.extend(
                (
                    Field("identity", "Optional Identity to mark", identities, required=False),
                    Field(
                        "gain",
                        "Heat gained from marking",
                        tuple((str(n), str(n)) for n in range(6)),
                        required=False,
                    ),
                )
            )
        return self.card(BRUTALIZE, sheet.revision, "Brutalize", fields)

    def enforcement_card(self, preview):
        contexts = (("yes", "Piloting"), ("no", "Outside the Frame"))
        if preview["piloting"] is not None:
            contexts = (contexts[0 if preview["piloting"] else 1],)
        fields = [
            Field(
                "target",
                "Person taken hold of",
                tuple(
                    (
                        ActorRef.model_validate(actor["ref"]).model_dump_json(),
                        actor["label"],
                    )
                    for actor in preview["targets"]
                ),
            ),
            Field("heat", "Heat to spend", heat_options(preview["heat"])),
            Field("piloting", "Frame context", contexts),
            Field("context", "Describe the actual contact", paragraph=True),
        ]
        return self.card(ENFORCEMENT, preview["sheet_revision"], "Enforcement Initiative", fields)

    def doctor_cards(self, viewer, menu, state, sheet):
        if menu["revision"] != state.revision:
            return []
        cards = []
        blocked = {item.play for item in sheet.blocked_plays}
        with self.game.store.engine.connect() as c:
            for choice in menu["choices"]:
                play = choice["id"]
                if play not in DOCTOR_PLAYS or play in blocked:
                    continue
                npc_targets = (
                    "npc_nanobot_targets" if play == "nanobot_injection" else "npc_support_targets"
                )
                targets = []
                for row in menu["targets"] + menu[npc_targets]:
                    target = ActorRef.model_validate(row["ref"])
                    try:
                        prepare_doctor(
                            self.game,
                            c,
                            viewer,
                            PlayInput(
                                play=play,
                                target_actor=target,
                                trigger_confirmed=True,
                                context="Eligibility preview",
                                heat=0,
                            ),
                            state,
                            channel=self.channel,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    targets.append((target.model_dump_json(), row["label"]))
                if targets:
                    fields = [
                        Field("target", "Actual patient or protector", tuple(targets)),
                        Field("heat", "Heat to spend", heat_options(menu["heat"])),
                        Field(
                            "context",
                            "Describe the actual medical trigger",
                            paragraph=True,
                        ),
                    ]
                    cards.append(self.card(play, menu["sheet_revision"], choice["label"], fields))
        return cards

    def dose_cards(self, viewer, state, sheet):
        try:
            menu = self.dose.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return []
        if menu["revision"] != state.revision:
            return []
        cards = []
        sources = [("self", "Dose yourself")] if menu["can_dose"] else []
        sources += [
            (json.dumps({"id": row["id"], "target": row["target"]}), row["label"])
            for row in menu["contacts"]
        ]
        if sources:
            native_marking = sheet.girl == "STIM-BLISSED"
            fields = [
                Field("source", "Recipient from the original scene", tuple(sources)),
                Field(
                    "heat",
                    "Heat to spend",
                    tuple(
                        (str(n), str(n)) for n in range(sheet.heat + (8 if native_marking else 1))
                    ),
                ),
                Field("context", "Describe the actual dosing trigger", paragraph=True),
            ]
            if native_marking and (
                identities := tuple(
                    (item.id, item.name) for item in sheet.identities if not item.marked
                )
            ):
                fields.extend(
                    (
                        Field(
                            "identity",
                            "Optional Identity to mark",
                            identities,
                            required=False,
                        ),
                        Field(
                            "gain",
                            "Heat gained from marking",
                            tuple((str(n), str(n)) for n in range(4)),
                            required=False,
                        ),
                        Field(
                            "disposable_heat",
                            "Optional Identity removal",
                            (
                                ("0", "Keep the Identity"),
                                ("3", "Remove it for 3 Heat"),
                                ("4", "Remove it for 4 Heat"),
                            ),
                            required=False,
                        ),
                    )
                )
            if menu["orders"]:
                fields.append(
                    Field(
                        "order",
                        "Actual followed order, for self-dose only",
                        tuple((row["id"], row["label"]) for row in menu["orders"]),
                        required=False,
                    )
                )
            cards.append(self.card(DOSE, sheet.revision, NATIVE_TITLES[DOSE], fields))
        if menu["targets"]:
            fields = [
                Field(
                    "target",
                    "Person within actual reach",
                    tuple(
                        (
                            ActorRef.model_validate(row["ref"]).model_dump_json(),
                            row["label"],
                        )
                        for row in menu["targets"]
                    ),
                ),
                Field("context", "Describe the actual close vein reach", paragraph=True),
            ]
            cards.append(
                self.card(
                    DOSE_CONTACT,
                    state.revision,
                    "Dose Up · Record contact",
                    fields,
                    label="File actual contact",
                )
            )
        return cards

    def consume_cards(self, viewer, state, sheet):
        try:
            menu = self.consume.menu(viewer, self.channel)
        except (ValueError, WorkflowError):
            return []
        if menu["revision"] != state.revision:
            return []
        cards = []
        blocked = {item.play for item in sheet.blocked_plays}
        with self.game.store.engine.connect() as c:
            for play, title in menu["plays"]:
                if play not in CONSUME_PLAYS or play in blocked:
                    continue
                eating = play == "consume_eat"
                choices = menu["targets"] if eating else [None]
                targets = []
                for row in choices:
                    target = ActorRef.model_validate(row["ref"]) if row else None
                    try:
                        prepare_consume(
                            self.game,
                            c,
                            viewer,
                            state.model_copy(deep=True),
                            PlayInput(
                                play=play,
                                trigger_confirmed=True,
                                heat=0,
                                context="Eligibility preview",
                                target_actor=target,
                            ),
                            self.channel,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    targets.append((target.model_dump_json(), row["label"]) if target else None)
                if not targets:
                    continue
                fields = [
                    Field(
                        "context",
                        "Describe the lunge" if eating else "Describe the impulse",
                        paragraph=True,
                    )
                ]
                if eating:
                    limit = 0 if menu["hunger"] == "Ravenous" else menu["heat"]
                    fields = [
                        Field("target", "Actual lunge target", tuple(targets)),
                        Field("heat", "Heat to spend", heat_options(limit)),
                        *fields,
                    ]
                cards.append(self.card(play, menu["sheet_revision"], title, fields))
        return cards

    def pandora_card(self, viewer, state, sheet):
        if any(item.play == PANDORA for item in sheet.blocked_plays):
            return None
        try:
            with self.game.store.engine.connect() as c:
                prepare_birth(
                    self.game,
                    c,
                    viewer,
                    PlayInput(
                        play=PANDORA,
                        trigger_confirmed=True,
                        context="Eligibility preview",
                        heat=sheet.heat if sheet.heat >= 5 else 0,
                    ),
                    state,
                    channel=self.channel,
                )
        except (ValueError, WorkflowError):
            return None
        return self.card(
            PANDORA,
            sheet.revision,
            "PANDORA · Birth",
            [
                Field("heat", "Heat to spend", heat_options(sheet.heat)),
                Field("context", "Describe the actual birth", paragraph=True),
            ],
        )

    def processor_cards(self, viewer, state, sheet):
        if any(item.play == PROCESSOR for item in sheet.blocked_plays):
            return []
        try:
            menu = self.ankou.menu(viewer, self.channel)
            actor = ActorRef.model_validate(menu["actor"])
            with self.game.store.engine.connect() as c:
                require_processor(self.game, c, state, actor, m3_ankou.PROCESSOR)
                sources = []
                for record in m3_ankou.records(state, m3_ankou.Proposal):
                    if (
                        record.actor != actor
                        or record.action
                        or record.cast.channel != self.channel
                    ):
                        continue
                    try:
                        prepare_processor(
                            self.game,
                            c,
                            viewer,
                            state,
                            PlayInput(
                                play=PROCESSOR,
                                source_work=record.id,
                                heat=0,
                                context="Eligibility preview",
                                trigger_confirmed=True,
                            ),
                            self.channel,
                        )
                    except (ValueError, WorkflowError):
                        continue
                    sources.append((record.id, record.account))
        except (ValueError, WorkflowError):
            return []
        if menu["revision"] != state.revision:
            return []
        cards = []
        links = [
            value
            for value in m3_ankou.records(state, m3_ankou.Processor)
            if value.actor == actor and not value.unlinked_event
        ]
        if links:
            owned = [
                (value.id, "Original Processor link")
                for value in links
                if value.cast.channel == self.channel and value.completed_event
            ]
            if owned:
                cards.append(
                    self.card(
                        PROCESSOR_UNLINK,
                        state.revision,
                        "Processor Core · Unlink",
                        [
                            Field("source", "Link to end", tuple(owned)),
                            Field("context", "Describe the actual unlink", paragraph=True),
                        ],
                        label="End the original link",
                    )
                )
            return cards
        if menu["people"]:
            cards.append(
                self.card(
                    PROCESSOR_PROPOSAL,
                    state.revision,
                    "Processor Core · Establish range",
                    [
                        Field(
                            "cadre",
                            "Exempt your Cadre?",
                            (("yes", "Exempt"), ("no", "Do not exempt")),
                        ),
                        Field(
                            "exempt",
                            "One additional exempt person",
                            tuple(
                                (
                                    ActorRef.model_validate(row["ref"]).model_dump_json(),
                                    row["label"],
                                )
                                for row in menu["people"]
                            ),
                            required=False,
                        ),
                        Field("context", "Describe the actual source", paragraph=True),
                    ],
                    label="File range and exemptions",
                )
            )
        if sources:
            identities = tuple(
                (item["id"], item["label"]) for item in menu["identities"] if not item["marked"]
            )
            fields = [
                Field("source", "Filed range and exemptions", tuple(sources)),
                Field(
                    "heat",
                    "Heat to spend",
                    tuple((str(n), str(n)) for n in range(sheet.heat + (4 if identities else 1))),
                ),
                Field("context", "Confirm the actual trigger", paragraph=True),
            ]
            if identities:
                fields.extend(
                    (
                        Field(
                            "identity",
                            "Optional Identity to mark",
                            identities,
                            required=False,
                        ),
                        Field(
                            "gain",
                            "Heat gained from marking",
                            (("1", "1"), ("2", "2"), ("3", "3")),
                            required=False,
                        ),
                    )
                )
            cards.append(self.card(PROCESSOR, sheet.revision, NATIVE_TITLES[PROCESSOR], fields))
        return cards

    def perform(self, viewer, key, op, revision, values):
        if op.partition(":")[0] in {*WYVERN_PLAYS, *WYVERN_SOURCE_OPERATIONS}:
            return self.wyvern.perform(viewer, key, op, revision, values)
        if op.partition(":")[0] in {*AM_PLAYS, *AM_OPERATIONS}:
            return self.am.perform(viewer, key, op, revision, values)
        if not all(isinstance(value, str) for value in values.values()):
            raise ValueError("Use the fields from the current Play.")
        if op.partition(":")[0] in DOLL_OPERATIONS:
            return self.doll.perform(viewer, key, op, revision, values)
        if op.partition(":")[0] in EASY_OPERATIONS:
            return self.easy_target.perform(viewer, key, op, revision, values)
        if op in PRINCE_OPERATIONS:
            return self.prince.perform(viewer, key, op, revision, values)
        if op in HANDLER_TRACKER and values.keys() == {"source"}:
            source = json.loads(values["source"])
            if (
                not isinstance(source, list)
                or len(source) != 2
                or not isinstance(source[0], str)
                or not (source[1] is None or isinstance(source[1], str))
            ):
                raise ValueError("Choose a current tracker source.")
            receipt = self.trackers.start_play(
                viewer,
                key,
                revision,
                source[0],
                HANDLER_TRACKER[op],
                self.channel,
                moment=source[1],
            )
            return receipt | {"handler_effect": HANDLER_TRACKER[op]}
        if op == HANDLER_WARP and values.keys() == {"zone"}:
            with self.game.store.engine.connect() as c:
                scene = self.game.scene(c, self.channel)
            receipt = self.handler_plays.start_warp(
                viewer,
                key,
                revision,
                values["zone"],
                scene=scene["id"],
            )
            return receipt | {"handler_effect": "contaminant_warp"}
        if op == TRACKER_MOMENT and values.keys() == {"context"}:
            return self.trackers.record_moment(
                viewer, key, revision, self.channel, values["context"]
            )
        if (
            op == BONDED_SOURCE
            and values.keys() == {"apart", "context"}
            and values["apart"] == "yes"
        ):
            return self.bonded.propose(
                viewer, key, self.channel, revision, "side", values["context"], apart=True
            )
        if op == BONDED_SIDE:
            required = {"source", "heat", "context"}
            if not required <= values.keys() or values.keys() - required - {
                "identity",
                "gain",
                "share",
            }:
                raise ValueError("Use the exact original Pair source and costs.")
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=BONDED_SIDE,
                    trigger_confirmed=True,
                    source_work=values["source"],
                    heat=int(values["heat"]),
                    context=values["context"],
                    identity=values.get("identity") or None,
                    gain=int(values.get("gain") or "0"),
                    pair_share=int(values.get("share") or "0"),
                ),
            )
        if op == BARELY and values.keys() in (
            {"identity", "asset", "account"},
            {"identity", "asset", "account", "lesson"},
        ):

            def guard(c):
                scene = self.game.scene(c, self.channel)
                self.game.scene_unpaused(c, scene["id"])
                if viewer.user_id not in scene["participants"]:
                    raise WorkflowError("Use your current pilot's scene to file this repair.")

            with self.game.store.source_guard(guard):
                return self.casualty.barely(
                    viewer,
                    key,
                    revision,
                    values["identity"],
                    values["asset"],
                    values["account"],
                    lesson=values.get("lesson"),
                )
        if op == CASUALTY_PARTS and values.keys() == {"actor", "part", "condition", "context"}:
            actor = ActorRef.model_validate_json(values["actor"])

            def guard(c):
                scene = self.game.scene(c, self.channel)
                self.game.scene_unpaused(c, scene["id"])
                if actor.kind != "pilot" or int(actor.entity) not in scene["participants"]:
                    raise WorkflowError(
                        "Choose the original Casualty who participated in this scene."
                    )

            with self.game.store.source_guard(guard):
                return self.casualty.damage_part(
                    viewer,
                    key,
                    revision,
                    actor,
                    values["part"],
                    values["condition"],
                    values["context"],
                    handler_play=True,
                )
        if op == DOSE_CONTACT and values.keys() == {"target", "context"}:
            return self.dose.record_contact(
                viewer,
                key,
                self.channel,
                ActorRef.model_validate_json(values["target"]),
                revision,
                values["context"],
            )
        if op == DOSE:
            return self.begin_dose(viewer, key, revision, values)
        if op == "consume_feral" and values.keys() == {"context"}:
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=op,
                    trigger_confirmed=True,
                    heat=0,
                    context=values["context"],
                ),
            )
        if op == PANDORA and values.keys() == {"heat", "context"}:
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=PANDORA,
                    trigger_confirmed=True,
                    heat=int(values["heat"]),
                    context=values["context"],
                ),
            )
        if op in (PROCESSOR, PROCESSOR_PROPOSAL, PROCESSOR_UNLINK):
            return self.perform_processor(viewer, key, op, revision, values)
        if op == BRUTALIZE:
            required = {"target", "heat", "context"}
            if not required <= values.keys() or values.keys() - required - {"identity", "gain"}:
                raise ValueError("Use the current Brutalize form.")
            return self.game.begin(
                viewer,
                key,
                self.channel,
                revision,
                PlayInput(
                    play=BRUTALIZE,
                    trigger_confirmed=True,
                    target_actor=ActorRef.model_validate_json(values["target"]),
                    heat=int(values["heat"]),
                    context=values["context"],
                    identity=values.get("identity") or None,
                    gain=int(values.get("gain") or "0"),
                ),
            )
        required = {"target", "heat", "context"} | ({"piloting"} if op == ENFORCEMENT else set())
        if op not in {ENFORCEMENT, "consume_eat", *DOCTOR_PLAYS} or values.keys() != required:
            raise ValueError("Confirm the contact and use the current Play fields.")
        if op == ENFORCEMENT and values["piloting"] not in ("yes", "no"):
            raise ValueError("Choose the actual Frame context.")
        return self.game.begin(
            viewer,
            key,
            self.channel,
            revision,
            PlayInput(
                play=op,
                target_actor=ActorRef.model_validate_json(values["target"]),
                trigger_confirmed=True,
                heat=int(values["heat"]),
                context=values["context"],
                piloting=values.get("piloting") == "yes",
            ),
        )

    def begin_dose(self, viewer, key, revision, values):
        required = {"source", "heat", "context"}
        if not required <= values.keys() or values.keys() - required - {
            "identity",
            "gain",
            "disposable_heat",
            "order",
        }:
            raise ValueError("Use the current Dose Up record and cost fields.")
        source = None if values["source"] == "self" else json.loads(values["source"])
        return self.game.begin(
            viewer,
            key,
            self.channel,
            revision,
            PlayInput(
                play=DOSE,
                trigger_confirmed=True,
                context=values["context"],
                heat=int(values["heat"]),
                identity=values.get("identity") or None,
                gain=int(values.get("gain") or "0"),
                disposable_heat=int(values.get("disposable_heat") or "0"),
                source_work=source["id"] if source else None,
                target_actor=ActorRef.model_validate(source["target"]) if source else None,
                order_id=values.get("order") or None,
            ),
        )

    def perform_processor(self, viewer, key, op, revision, values):
        if op == PROCESSOR_PROPOSAL and values.keys() in (
            {"cadre", "context"},
            {"cadre", "context", "exempt"},
        ):
            if values["cadre"] not in ("yes", "no"):
                raise ValueError("Choose the actual Cadre exemption.")
            exempt = values.get("exempt")
            return self.ankou.propose_processor(
                viewer,
                key,
                self.channel,
                revision,
                values["context"],
                exempt_cadre=values["cadre"] == "yes",
                exempt=ActorRef.model_validate_json(exempt) if exempt else None,
            )
        if op == PROCESSOR_UNLINK and values.keys() == {"source", "context"}:
            return self.ankou.unlink(viewer, key, revision, values["source"], values["context"])
        required = {"source", "heat", "context"}
        if (
            op != PROCESSOR
            or not required <= values.keys()
            or values.keys() - required - {"identity", "gain"}
        ):
            raise ValueError("Use the fields from the current Processor Core record.")
        return self.game.begin(
            viewer,
            key,
            self.channel,
            revision,
            PlayInput(
                play=PROCESSOR,
                context=values["context"],
                trigger_confirmed=True,
                heat=int(values["heat"]),
                identity=values.get("identity"),
                gain=int(values.get("gain") or "0"),
                source_work=values["source"],
            ),
        )
