"""Director referrals over the source inventory; admission remains with native services."""

import re

from girlframe.ai.play_review import PlayReferral
from girlframe.engine.m2 import PLAY_IDS
from girlframe.engine.m3_consume import PLAYS as CONSUME
from girlframe.engine.m3_handler_play_state import BASIC, EXTRA
from girlframe.engine.m3_red_queen import PLAYS as RED_QUEEN
from girlframe.engine.m3_wyvern import PLAYS as WYVERN
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest, load_registry

NATIVE_RULES = {
    **{x: "play.basic." + x for x in (*PLAY_IDS, "receive_orders")},
    **{
        x: "play.basic." + x
        for x in (
            "go_off_duty",
            "void_observation",
            "all_out_assault",
            "go_for_the_core",
            "put_someone_beneath_you",
            "dive_deep",
            "defeat",
        )
    },
    "enforcement_initiative": "frame.enforcer.enforcement-initiative",
    "mockingbird_person": "girl.mockingbird.bad-at-being-a-person",
    "mockingbird_sex": "girl.mockingbird.sex-play",
    "snoop": "frame.enforcer.snoop",
    "brutalize": "girl.alpha.brutalize",
    "alpha_sex": "girl.alpha.sex-play",
    "am_scrutinized": "girl.am.scrutinized",
    "am_just_code": "girl.am.just-code",
    "nanobot_injection": "frame.doctordoctor.nanobot-injection",
    "doctor_support": "frame.doctordoctor.here-for-support",
    "dose_up": "girl.stim-blissed.dose-up",
    "princess_sex": "girl.princess.sex-play",
    "stim_sex": "girl.stim-blissed.sex-play",
    "old_dog_new_pups": "girl.oldgen.old-dog-new-pups",
    "oldgen_sex": "girl.oldgen.sex-play",
    "casualty_sex": "girl.casualty.sex-play",
    "vatgrown_sex": "girl.vatgrown.sex-play",
    "newgirl_sex": "girl.newgirl.sex-play",
    "easy_target": "girl.newgirl.easy-target",
    "unassuming_doll": "girl.vatgrown.unassuming-doll",
    "prince_performer": "frame.prince.performer",
    "ankou_processor": "frame.ankou.processor-core",
    "changeling_blank_slate": "frame.changeling.blank-slate",
    "changeling_body_of_clay": "frame.changeling.body-of-clay",
    "bonded_side": "girl.bonded.always-by-her-side",
    "bonded_sex": "girl.bonded.sex-play",
    "living_battery": "frame.janus.living-battery",
    "pandora_birth": "frame.janus.pandora",
    **CONSUME,
    **RED_QUEEN,
    **WYVERN,
    "handler_brief": "play.handler.brief",
    "handler_punish": "handler.handler.punish-them",
    "handler_escalate": "handler.handler.escalate-the-situation",
    "handler_support": "handler.handler.introduce-the-support",
    "handler_mess": "handler.handler.mess-with-their-status-tags-or-assets",
    "handler_expectation": "handler.handler.place-an-expectation-on-them",
    "handler_off_duty": "handler.handler.handler-off-duty",
    "handler_tracker_intercept": "handler-advancement.handler-advancement.tracker-implants",
    "handler_tracker_voyeur": "handler-advancement.handler-advancement.tracker-implants",
    "handler_contaminant_warp": "handler-advancement.handler-advancement.contaminant-zone",
    "gorgon_attack": "gorgon.gorgon.attack",
    "gorgon_collateral": "gorgon.gorgon.collateral-damage",
    "gorgon_warp": "gorgon.gorgon.warp",
}


class PlayCatalog:
    def __init__(self, registry: Registry | None = None):
        self.registry = registry if registry is not None else load_registry()
        self.digest = digest(self.registry)
        for identity in NATIVE_RULES.values():
            self.registry.entry(identity)  # A typo must not silently create a new rule.

    def get(self, identity: str) -> PlayReferral:
        rule = self.registry.entry(NATIVE_RULES.get(identity, identity))
        native = [key for key, value in NATIVE_RULES.items() if value == rule.id]
        play = identity if identity in NATIVE_RULES else native[0] if len(native) == 1 else rule.id
        title = rule.title
        if play.startswith("handler_"):
            title = dict((*BASIC, *EXTRA))[play.removeprefix("handler_")]
            if play == "handler_off_duty":
                title = "Handler Go Off-Duty"
        if play in ("handler_tracker_intercept", "handler_tracker_voyeur"):
            title = "Intercept Them" if play.endswith("intercept") else "Play Voyeur"
        elif rule.id.endswith("sex-play"):
            title = rule.id.split(".")[1].replace("-", " ").title() + " Sex Play"
        elif play == "check_sensors":
            title = "Check Your Sensors"
        elif play == "engage":
            title = "Engage"
        enabled = rule.module in self.registry.enabled_modules
        adapter = (
            "module_disabled"
            if not enabled
            else "structured_native"
            if play in PLAY_IDS
            else "native_owner_review"
            if play in NATIVE_RULES
            else "manual_source_review"
        )
        return PlayReferral(
            play_id=play, rule_id=rule.id, title=title, adapter=adapter, module_enabled=enabled
        )

    def all(self) -> tuple[PlayReferral, ...]:
        routes = {self.get(e.id).play_id: self.get(e.id) for e in self.registry.entries}
        routes.update({key: self.get(key) for key in NATIVE_RULES})
        return tuple(routes[key] for key in sorted(routes))

    def recognize(self, text: str) -> tuple[PlayReferral, ...]:
        """Explicit declarations only; ambiguity is retained for GM clarification."""
        text = text.strip()
        declaration = re.search(
            r"\b(?:declare|roll|resolve|request)\b|"
            r"^(?:gm\s*[:,]\s*)?(?:(?:i|we)\s+)?(?:call|choose)\b",
            text,
            re.I,
        )
        if declaration is None:
            return ()
        if re.search(r"\b(?:not|never|don't|won't)\b", text[: declaration.start()], re.I):
            return ()
        goal = re.search(r"\s+to\s+", text[declaration.end() :], re.I)
        if goal is not None:
            text = text[: declaration.end() + goal.start()]
        # Typed IDs take precedence over similarly named source headings.
        explicit = []
        for identity in (*NATIVE_RULES, *(e.id for e in self.registry.entries)):
            match = re.search(r"\b" + re.escape(identity) + r"\b", text[declaration.end() :], re.I)
            if match is not None and not re.search(
                r"\b(?:not|never|don't|won't)\b", text[declaration.end() :][: match.start()], re.I
            ):
                route = self.get(identity)
                explicit.append(
                    (declaration.end() + match.start(), declaration.end() + match.end(), route)
                )
        matches: list[tuple[int, int, PlayReferral]] = []
        for route in self.all():
            entry = self.registry.entry(route.rule_id)
            labels = {route.play_id, route.rule_id, *entry.aliases}
            # Shared Sex Play headings need a playbook; the bare heading stays ambiguous.
            if (
                route.play_id in NATIVE_RULES
                or entry.kind == "play"
                or entry.id.endswith("sex-play")
            ):
                labels.update((entry.title, route.title))
            for label in labels:
                pattern = re.escape(label).replace(r"\ ", r"[ _-]+")
                for match in re.finditer(r"\b" + pattern + r"\b", text, re.I):
                    if match.start() < declaration.end():
                        continue
                    prefix = text[declaration.end() : match.start()].casefold()
                    if re.search(r"\b(?:not|never|don't|won't)\b", prefix):
                        continue
                    matches.append((match.start(), match.end(), route))
        selected = {
            route.play_id: route
            for start, end, route in matches
            if not any(a <= start and b >= end and (a, b) != (start, end) for a, b, _ in matches)
            and not any(
                a <= start and b >= end and exact.play_id != route.play_id
                for a, b, exact in explicit
            )
        }
        # Generic basic headings select their ordinary entry, not same-named Harpy variants.
        for key, value in tuple(selected.items()):
            if not value.rule_id.startswith("play.basic.") and any(
                other.rule_id.startswith("play.basic.")
                and self.registry.entry(other.rule_id).title
                == self.registry.entry(value.rule_id).title
                for other in selected.values()
            ):
                selected.pop(key)
        return tuple(selected[key] for key in sorted(selected))

    @staticmethod
    def declared(text: str) -> bool:
        match = re.search(
            r"\b(?:i|we)\s+(?:declare|roll|request|call|choose)\b|"
            r"^(?:gm\s*[:,]?\s*)?(?:declare|roll|resolve|request|call|choose)\b",
            text.strip(),
            re.I,
        )
        return bool(
            match is not None
            and (re.match(r"gm\s*[:,]", text.strip(), re.I) or re.search(r"\bplay\b", text, re.I))
            and not re.search(r"\b(?:not|never|don't|won't)\b", text[: match.start()], re.I)
        )
