"""Handler-owned saved Strain dice/columns and mandatory source-event scheduling.

Scheduling is not completion of world or sheet effects. There is intentionally
no generic resolver for the resulting event/endgame work or period start gate.
"""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_strain as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_off_duty import clone as clone_period
from girlframe.engine.m3_reactions import mark_obsolescence
from girlframe.engine.m3_strain_state import Request, Scenario, Track
from girlframe.engine.rolls import D6Source, OsD6
from girlframe.services.m2_state import load_state
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class StrainService:
    def __init__(self, periods: OffDutyService, *, dice: D6Source | None = None):
        self.periods, self.store, self.game = periods, periods.store, periods.game
        self.missions = periods.missions
        self.dice = dice if dice is not None else OsD6()
        self.rng_source = "test_injected" if dice is not None else "os"

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        self.missions.access.authorize(c, viewer, "strain")
        self.missions._handler(c, viewer)

    def _state(self, c: Connection, expected: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        if state.revision != expected or self.game.pending_actions(c):
            raise WorkflowError("STALE_STATE: finish pending Plays and reopen the Strain review.")
        return state

    def configure(
        self,
        viewer: GuildViewer,
        key: str,
        game_revision: int,
        scenario: Scenario,
        high: frozenset[Track],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, game_revision)
            if state.strain is not None:
                raise WorkflowError(
                    "The starting scenario is already recorded; do not reset Strain."
                )
            state.strain = rules.initial(scenario, high)
            from girlframe.engine.m3_collateral import install_budget

            install_budget(state)
            self.game.event(c, viewer.user_id, key, "m3.strain_initialized", state)
            return {"game_revision": state.revision, "levels": dict(state.strain.levels)}

        return self.missions._write(
            viewer,
            key,
            "m3.strain_initialized",
            {"game_revision": game_revision, "scenario": scenario, "high": sorted(high)},
            operation,
            lambda c: self._authorize(c, viewer),
        )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] not in (
            "off_duty_strain_start",
            "strain_roll",
            "strain_endgame",
        ):
            raise WorkflowError("Unknown Strain work.")
        return dict(row)

    def _check(
        self,
        c: Connection,
        viewer: GuildViewer,
        row: dict[str, Any],
        revision: int,
    ) -> None:
        if (
            row["owner_id"] != str(viewer.user_id)
            or row["revision"] != revision
            or row["state"] != "pending"
        ):
            raise WorkflowError("STALE_WORK: resume the current Handler's pending Strain work.")
        period = self.periods._get(c, row["off_duty_id"])
        if period.handler != viewer.user_id or period.phase != "preparing":
            raise WorkflowError("Strain start work must belong to the actual preparing period.")

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        event: str,
        body: dict[str, Any],
        *,
        resolved: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved" if resolved else "pending",
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
        )

    def _request(self, c: Connection, root: dict[str, Any], request: Request, event: str) -> None:
        related(
            c,
            self.store,
            root,
            request.id,
            int(root["owner_id"]),
            int(root["owner_id"]),
            "strain_roll" if request.kind == "roll" else "strain_endgame",
            {
                "track": request.track,
                "severity": request.severity,
                "parent": request.parent,
                "stage": "die" if request.kind == "roll" else "endgame",
            },
            event,
        )

    def prepare(
        self,
        viewer: GuildViewer,
        key: str,
        period_id: str,
        period_revision: int,
        game_revision: int,
        facts: rules.StartFacts,
    ) -> dict[str, Any]:
        facts = rules.StartFacts.model_validate_json(facts.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, game_revision)
            period = self.periods._get(c, period_id)
            root = self._row(c, period_id + ":off_duty_strain_start:" + str(viewer.user_id))
            self._check(c, viewer, root, 1)
            if period.revision != period_revision or state.strain is None:
                raise WorkflowError("Choose an initial Strain scenario and refresh the period.")
            from girlframe.services.m3_off_duty import current_original_characters

            originals = current_original_characters(c, self.game, state, period)
            if set(originals) != {
                str(uid) for uid in state.order if str(uid) not in period.ended_characters
            }:
                raise WorkflowError("Resolve the changed canonical roster before Strain start.")
            if any(x["kind"] == "doctor_credit" for x in self.periods._pending(c, period_id)):
                raise WorkflowError(
                    "DoctorDoctor owners record credit before the Budget start trigger."
                )
            from girlframe.engine.m3_janus_storage import effective_assets

            with_void = sum(
                any(
                    a.void
                    for a in effective_assets(
                        state,
                        ActorRef(
                            kind="pilot",
                            entity=str(uid),
                            incarnation=state.sheets[str(uid)].character_id,
                        ),
                    )
                )
                for uid in state.order
            )
            if facts.at_least_half_have_void != (
                2 * with_void >= len(state.order)
            ) or facts.no_girl_void != (with_void == 0):
                raise WorkflowError("The Void trigger review must match current canonical Assets.")
            frames = [
                [a for a in state.sheets[str(uid)].assets if a.family == "frame"]
                for uid in state.order
            ]
            repair_trigger = any(
                assets and all(a.damaged for a in assets) for assets in frames
            ) or (bool(frames) and all(any(a.damaged for a in assets) for assets in frames))
            if repair_trigger and not facts.frame_full_or_all_frames_some_repairs:
                raise WorkflowError("The canonical Frame damage already triggers High Budget.")
            from girlframe.engine.m3_martyr import budget_death_excluded, episodes

            prior_preparation = (
                c.scalar(
                    sa.select(sa.func.max(t.events.c.seq)).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.kind == "m3.strain_start_prepared",
                    )
                )
                or 0
            )
            martyr_deaths = []
            insured_deaths = []
            from girlframe.services.m3_girl_insurance import verify_exclusion

            for archive in state.career_archives:
                if archive.actor.kind != "pilot" or archive.ending not in ("death", "execution"):
                    continue
                actual_seq = c.scalar(
                    sa.select(t.events.c.seq).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == archive.source_event,
                    )
                )
                if actual_seq is None or actual_seq <= prior_preparation:
                    continue
                martyr = budget_death_excluded(state, archive.source_event) and any(
                    x.archive == archive.id and x.actor == archive.actor for x in episodes(state)
                )
                insured = verify_exclusion(self.game, c, state, archive.source_event, archive.id)
                if martyr:
                    martyr_deaths.append(archive.id)
                if insured:
                    insured_deaths.append(archive.id)
                if not (martyr or insured) and not facts.girl_death_or_severe:
                    raise WorkflowError(
                        "An actual non-exempt Girl death requires the Budget death/severe fact"
                    )
            if facts.last_mission_success_no_frame_death_infrastructure_loss:
                history = t.m3["m3_mission_history"]
                body = c.scalar(
                    sa.select(history.c.body_json)
                    .join(t.events, history.c.event_id == t.events.c.id)
                    .where(history.c.campaign_id == self.store.campaign_id)
                    .order_by(t.events.c.seq.desc())
                    .limit(1)
                )
                if (
                    body is None
                    or Mission.model_validate_json(body).success is not True
                    or Mission.model_validate_json(body).phase != "complete"
                ):
                    raise WorkflowError("The last mission does not record a successful outcome.")
            from girlframe.services.m3_contaminant_zone import prove_relief

            prove_relief(self.game, c, state)
            state.strain = rules.start(state.strain, period_id, facts)
            from girlframe.engine.m3_a_bomb_budget import record_write

            budget_event = str(uuid4())
            record_write(
                state,
                source="strain:" + period_id,
                event=budget_event,
                value=state.strain.levels["budget"],
            )
            scrapped = []
            if state.strain.levels["budget"] == "high":
                for uid, sheet in state.sheets.items():
                    if sheet.frame == "DOCTORDOCTOR MK. II" and not sheet.frame_scrapped:
                        result = mark_obsolescence(sheet, "high_budget")
                        state.sheets[uid] = result.sheet
                        if result.replacement_required:
                            scrapped.append(result.sheet)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_start_prepared",
                state,
                event_id=budget_event,
                period_id=period_id,
                levels=dict(state.strain.levels),
                martyr_budget_deaths=martyr_deaths,
                insured_budget_deaths=insured_deaths,
            )
            updated = clone_period(period)
            updated.revision += 1
            self.periods._save(c, updated, event)
            self._save(
                c,
                root,
                event,
                {
                    "source_pdf": 142,
                    "stage": "pending_effects",
                    "facts": facts.model_dump(mode="json"),
                },
            )
            for request in state.strain.requests:
                self._request(c, root, request, event)
            for sheet in scrapped:
                related(
                    c,
                    self.store,
                    root,
                    period_id + ":doctor-replacement:" + str(sheet.owner),
                    sheet.owner,
                    sheet.owner,
                    "doctor_frame_replacement",
                    {
                        "source_pdf": 71,
                        "immediate": True,
                        "source_work": root["id"],
                        "origin_frame": sheet.frame,
                        "origin_frame_id": sheet.frame_runtime.id if sheet.frame_runtime else None,
                        "origin_fingerprint": sheet.source_fingerprint,
                        "origin_character_id": c.scalar(
                            sa.select(t.characters.c.id).where(
                                t.characters.c.campaign_id == self.store.campaign_id,
                                t.characters.c.user_id == str(sheet.owner),
                            )
                        ),
                    },
                    event,
                )
            return {
                "id": period_id,
                "revision": updated.revision,
                "game_revision": state.revision,
                "pending_rolls": len(state.strain.requests),
            }

        return self.missions._write(
            viewer,
            key,
            "m3.strain_start_prepared",
            {
                "id": period_id,
                "period_revision": period_revision,
                "game_revision": game_revision,
                "facts": facts.model_dump(mode="json"),
            },
            operation,
            lambda c: self._authorize(c, viewer),
        )

    def roll(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, viewer, row, revision)
            state = self._state(c, game_revision)
            if state.strain is None:
                raise WorkflowError("Initialize Strain before rolling.")
            if row["kind"] != "strain_roll" or json.loads(row["body_json"]).get("stage") != "die":
                raise WorkflowError("This die is already saved; resume its column choice.")
            state.strain = rules.roll(state.strain, identity, self.dice.roll_d6())
            saved = next(x for x in state.strain.events if x.id == identity)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_die_saved",
                state,
                work_id=identity,
                rng_source=self.rng_source,
            )
            self._save(
                c,
                row,
                event,
                json.loads(row["body_json"])
                | {"stage": "column", "face": saved.face, "rng_source": self.rng_source},
            )
            return {
                "id": identity,
                "revision": revision + 1,
                "game_revision": state.revision,
                "face": saved.face,
            }

        return self.missions._write(
            viewer,
            key,
            "m3.strain_die_saved",
            {"id": identity, "revision": revision, "game_revision": game_revision},
            operation,
            lambda c: self._authorize(c, viewer),
        )

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        option: int,
        *,
        endgame: bool = False,
        faction: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, viewer, row, revision)
            state = self._state(c, game_revision)
            if state.strain is None:
                raise WorkflowError("Initialize Strain before choosing an event.")
            old_requests = {x.id for x in state.strain.requests}
            cascade = False
            if endgame:
                request = next((x for x in state.strain.requests if x.id == identity), None)
                if request and request.track == "rebellion":
                    if not state.world or not any(
                        x.id == faction and x.kind == "rebel" and x.active
                        for x in state.world.factions
                    ):
                        raise WorkflowError("Select the actual active Rebel Group for this Endgame")
                elif faction is not None:
                    raise WorkflowError("Only a Rebel Endgame selects a Rebel Group")
                state.strain = rules.choose_endgame(state.strain, identity, option, faction=faction)
                chosen = next(x for x in state.strain.endgames if x.id == identity)
                rule_id, source_pdf = (
                    chosen.rule_id,
                    {"void": 146, "rebellion": 149, "budget": 152}[chosen.track],
                )
            else:
                if faction is not None:
                    raise WorkflowError("An ordinary event does not select an Endgame group")
                state.strain = rules.choose(state.strain, identity, option)
                selected = next(x for x in state.strain.events if x.id == identity)
                selected_rule = selected.rule_id
                assert selected_rule is not None
                rule_id, source_pdf = (
                    selected_rule,
                    rules.PAGES[(selected.track, selected.severity)],
                )
                cascade = selected.severity == "high" and selected.face == 6 and option == 2
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_option_saved",
                state,
                work_id=identity,
                rule_id=rule_id,
            )
            self._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | {"rule_id": rule_id, "source_pdf": source_pdf},
                resolved=True,
            )
            for request in state.strain.requests:
                if request.id not in old_requests:
                    self._request(c, row, request, event)
            if not cascade:
                related(
                    c,
                    self.store,
                    row,
                    identity + ":effect",
                    viewer.user_id,
                    viewer.user_id,
                    "strain_endgame_effect" if endgame else "strain_event",
                    {"rule_id": rule_id, "source_pdf": source_pdf, "source_work": identity},
                    event,
                )
            return {
                "id": identity,
                "state": "resolved",
                "game_revision": state.revision,
                "rule_id": rule_id,
                "effects_pending": True,
            }

        return self.missions._write(
            viewer,
            key,
            "m3.strain_option_saved",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "option": option,
                "endgame": endgame,
            }
            | ({"faction": faction} if faction is not None else {}),
            operation,
            lambda c: self._authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.missions._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_contaminant_zone import prove_relief

            prove_relief(self.game, c, state)
            return {
                "game_revision": state.revision,
                "strain": (
                    state.strain.model_dump(mode="json")
                    | {
                        "levels": rules.effective_levels(state.strain),
                        "underlying_levels": dict(state.strain.levels),
                    }
                )
                if state.strain
                else None,
            }

    def work(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.missions._handler(c, viewer)
            row = self._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("This Strain review belongs to another Handler.")
            state = load_state(c, self.store.campaign_id)
            period = self.periods._get(c, row["off_duty_id"])
            from girlframe.engine.m3_janus_storage import effective_assets

            count = sum(
                any(
                    a.void
                    for a in effective_assets(
                        state,
                        ActorRef(
                            kind="pilot",
                            entity=str(uid),
                            incarnation=state.sheets[str(uid)].character_id,
                        ),
                    )
                )
                for uid in state.order
            )
            from girlframe.engine.m2 import PilotSheet
            from girlframe.engine.m3_martyr import budget_death_excluded, episodes
            from girlframe.services.m3_girl_insurance import verify_exclusion

            prior = (
                c.scalar(
                    sa.select(sa.func.max(t.events.c.seq)).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.kind == "m3.strain_start_prepared",
                    )
                )
                or 0
            )
            exemptions = []
            for archive in state.career_archives:
                if archive.ending not in ("death", "execution"):
                    continue
                sequence = c.scalar(
                    sa.select(t.events.c.seq).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == archive.source_event,
                    )
                )
                if sequence is None or sequence <= prior:
                    continue
                sources = []
                if budget_death_excluded(state, archive.source_event) and any(
                    x.archive == archive.id and x.actor == archive.actor for x in episodes(state)
                ):
                    sources.append("Martyr")
                if verify_exclusion(self.game, c, state, archive.source_event, archive.id):
                    sources.append("Girl Insurance")
                if sources:
                    exemptions.append(
                        dict(
                            id=archive.id,
                            label=PilotSheet.model_validate_json(archive.sheet_json).callsign
                            + " — "
                            + " + ".join(sources),
                        )
                    )
            return {
                "budget_death_exemptions": exemptions,
                **{k: row[k] for k in ("id", "revision", "kind", "state", "off_duty_id")},
                "body": json.loads(row["body_json"]),
                "game_revision": state.revision,
                "period_revision": period.revision,
                "canonical_facts": {
                    "at_least_half_have_void": 2 * count >= len(state.order),
                    "no_girl_void": count == 0,
                },
                "initialized": state.strain is not None,
                "rebel_groups": [
                    dict(id=x.id, label=x.name)
                    for x in state.world.factions
                    if x.kind == "rebel" and x.active
                ]
                if state.world
                else [],
                "endgame_options": rules.endgame_options(
                    state.strain, json.loads(row["body_json"])["track"]
                )
                if row["kind"] == "strain_endgame" and state.strain
                else (),
            }
