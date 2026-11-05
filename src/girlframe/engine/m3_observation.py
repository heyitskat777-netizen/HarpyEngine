"""Source-owned Void Observation decisions over the real Off-Duty period."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, Obligation, TagState, shift_status, tier
from girlframe.engine.m3_adjudication_state import Decision
from girlframe.engine.m3_choices import HIDDEN_VOID, OBSERVATION, OFF_DUTY
from girlframe.engine.m3_observation_state import Details, Kind, Observation, Outcome
from girlframe.engine.m3_off_duty import Period, Progress, Roll, Scene, clone, current
from girlframe.engine.m3_reprogram import apply as reprogram


def context(period: Period, subject: int) -> tuple[Progress, Observation]:
    progress = period.progress.get(str(subject))
    if (
        progress is None
        or progress.career_ended is not None
        or str(subject) in period.ended_characters
        or progress.observation is None
        or subject not in period.pilots
    ):
        raise ValueError("Resume the actual Handler-recorded Observation order")
    return progress, progress.observation


def order(
    period: Period,
    expected: int,
    actor: int,
    subject: int,
    state: GameState,
    suspects_hiding: bool,
    account: str,
    source: str,
) -> tuple[Period, GameState]:
    current(period, expected, active=period.phase == "active")
    if (
        actor != period.handler
        or state.handler != actor
        or subject not in period.pilots
        or str(subject) in period.ended_characters
    ):
        raise ValueError("Only the current Handler records its actual suspicion for a current Girl")
    progress = Progress.model_validate_json(
        period.progress.get(str(subject), Progress()).model_dump_json()
    )
    if progress.action_id or progress.roll or progress.observation or progress.recovered:
        raise ValueError("Record Observation before this Girl's Off-Duty Play is reserved")
    if (
        type(suspects_hiding) is not bool
        or not account.strip()
        or len(account) > 1200
        or not source.strip()
    ):
        raise ValueError("Record the Handler's actual suspicion and explicit hiding decision")
    updated, canon = clone(period), GameState.model_validate_json(state.model_dump_json())
    debts = [
        x.id
        for x in canon.obligations
        if x.kind == "void_observation" and x.owner == subject and x.state == "pending"
    ]
    if not debts:
        identity = str(uuid5(NAMESPACE_URL, source + ":observation"))
        canon.obligations.append(
            Obligation(
                id=identity,
                kind="void_observation",
                owner=subject,
                action=source,
                details={"source_pdf": "28"},
            )
        )
        debts.append(identity)
    progress.observation = Observation(
        source_event=source, obligations=tuple(debts), suspects_hiding=suspects_hiding
    )
    updated.progress[str(subject)] = progress
    updated.revision += 1
    return updated, canon


def modifier(state: GameState, subject: int) -> int:
    sheet = state.sheets.get(str(subject))
    if sheet is None or subject not in state.order or sheet.frame_scrapped:
        raise ValueError("Observation requires its actual current Girl and Frame")
    from girlframe.engine.m3_janus_storage import effective_for_owner

    return sum(x.void for x in effective_for_owner(state, subject))


def review_hiding(
    period: Period, expected: int, actor: int, subject: int, suspected: bool, source: str
) -> Period:
    current(period, expected, active=period.phase == "active")
    _, observation = context(period, subject)
    if actor != period.handler or type(suspected) is not bool or not source.strip():
        raise ValueError("Only the actual Handler records its hiding suspicion")
    if observation.actor_choices is not None or observation.handler_choices is not None:
        raise ValueError("The available list is committed when the first human submits choices")
    updated = clone(period)
    saved = context(updated, subject)[1]
    saved.suspects_hiding = suspected
    saved.hiding_review_event = source
    updated.revision += 1
    return updated


def lower_before_roll(period: Period, subject: int, state: GameState) -> GameState:
    progress, observation = context(period, subject)
    if progress.roll is not None:
        raise ValueError("Status was already lowered with this saved Observation roll")
    if not observation.obligations or not all(
        any(
            x.id == identity
            and x.owner == subject
            and x.kind == "void_observation"
            and x.state == "pending"
            for x in state.obligations
        )
        for identity in observation.obligations
    ):
        raise ValueError("Recover the actual Observation obligations before rolling")
    updated = GameState.model_validate_json(state.model_dump_json())
    shift_status(updated, subject, -1)
    return updated


def roll(
    period: Period,
    expected: int,
    actor: int,
    state: GameState,
    faces: tuple[int, int] | None,
    *,
    adjudication: Decision | None = None,
) -> Period:
    current(period, expected)
    progress, _ = context(period, actor)
    if progress.roll is not None or progress.recovered:
        raise ValueError("Resume the same Observation receipt instead of rerolling")
    amount = modifier(state, actor)
    if adjudication is not None and (
        adjudication.required.actor.entity != str(actor)
        or adjudication.required.actor.incarnation != state.sheets[str(actor)].character_id
        or adjudication.required.source_id != period.id
    ):
        raise ValueError("The manual decision belongs to the original Observation patient")
    updated = clone(period)
    updated.progress[str(actor)].roll = Roll(
        faces=faces,
        adjudication=adjudication,
        modifier=0 if adjudication else amount,
        total=adjudication.total if adjudication else sum(faces or ()) + amount,
        source="void_assets",
    )
    updated.revision += 1
    return updated


def choices(period: Period, subject: int, actor: int) -> tuple[tuple[str, ...], int]:
    progress, observation = context(period, subject)
    if progress.roll is None or progress.roll.stage != "choices":
        raise ValueError("Finish the actual Observation roll and Tag choices first")
    if actor not in (subject, period.handler):
        raise ValueError("Only this Girl or its Handler chooses these consequences")
    own = actor == subject
    saved = observation.actor_choices if own else observation.handler_choices
    if saved is not None:
        raise ValueError("This human's Observation choices are already saved")
    count = 1 if own else {"low": 0, "mid": 1, "high": 2}[tier(progress.roll.total)]
    used = {x.kind for x in observation.outcomes}
    return tuple(
        x
        for x in OBSERVATION + (HIDDEN_VOID if observation.suspects_hiding else ())
        if x not in used
    ), count


def choose(
    period: Period, expected: int, actor: int, subject: int, values: tuple[Kind, ...], source: str
) -> Period:
    current(period, expected)
    available, count = choices(period, subject, actor)
    if (
        len(values) != count
        or len(set(values)) != count
        or not set(values) <= set(available)
        or not source.strip()
    ):
        raise ValueError("Choose the exact distinct Observation consequences owned by you")
    updated = clone(period)
    observation = updated.progress[str(subject)].observation
    assert observation is not None
    outcomes = observation.outcomes + tuple(
        Outcome(id=str(uuid5(NAMESPACE_URL, source + ":" + kind)), kind=kind, chooser=actor)
        for kind in values
    )
    proposed = observation.model_copy(
        update={
            "actor_choices" if actor == subject else "handler_choices": values,
            "outcomes": outcomes,
        }
    )
    updated.progress[str(subject)].observation = Observation.model_validate_json(
        proposed.model_dump_json()
    )
    updated.revision += 1
    return updated


def all_chosen(period: Period, subject: int) -> bool:
    progress, observation = context(period, subject)
    return bool(
        progress.roll
        and progress.roll.stage == "choices"
        and observation.actor_choices is not None
        and (tier(progress.roll.total) == "low" or observation.handler_choices is not None)
    )


def outcome(period: Period, subject: int, identity: str) -> Outcome:
    _, observation = context(period, subject)
    selected = next((x for x in observation.outcomes if x.id == identity and not x.resolved), None)
    if selected is None:
        raise ValueError("Resume an actual unapplied Observation consequence")
    return selected


def apply(
    period: Period,
    expected: int,
    state: GameState,
    actor: int,
    subject: int,
    identity: str,
    details: Details,
    source: str,
    *,
    allow_duplicate_labels: bool,
    npc_confirmed_by: int | None = None,
) -> tuple[Period, GameState]:
    current(period, expected)
    selected = outcome(period, subject, identity)
    kind = selected.kind
    owner = (
        subject
        if kind == "reprogram"
        else period.handler
        if kind
        in (
            "public_display_tag",
            "assigned_observer",
            "medical_probing",
            "hospital_stay",
            "director_or_rival_arrives",
        )
        else selected.chooser
    )
    if actor != owner or not details.account.strip() or not source.strip():
        raise ValueError("Only the actual consequence decision owner supplies these details")
    allowed = {
        "remove_girl_void_asset": {"asset"},
        "remove_frame_void_asset": {"asset"},
        "assigned_observer": {"npc"},
        "public_display_tag": {"tag"},
        "reprogram": {"identity", "slot"},
        "director_or_rival_arrives": {"npc"},
    }.get(kind, set())
    empty = Details(account=details.account)
    if any(
        getattr(details, key) != getattr(empty, key)
        for key in Details.model_fields
        if key not in allowed | {"account"}
    ):
        raise ValueError("Use only details relevant to this actual consequence")
    if kind == "moderate_punishment":
        raise ValueError("Resolve the actual Moderate Punishment through its discipline task")
    updated, canon = clone(period), GameState.model_validate_json(state.model_dump_json())
    sheet = canon.sheets[str(subject)]
    if kind in ("remove_girl_void_asset", "remove_frame_void_asset"):
        family = "girl" if kind == "remove_girl_void_asset" else "frame"
        from girlframe.engine.m3_janus_storage import effective_for_owner

        asset = next(
            (
                x
                for x in effective_for_owner(canon, subject)
                if x.id == details.asset and x.family == family and x.void
            ),
            None,
        )
        if asset is None:
            raise ValueError("Choose an actual current Void Asset of the specified family")
        sheet.assets = [x for x in sheet.assets if x.id != asset.id]
        sheet.revision += 1
    elif kind == "reprogram":
        if details.identity is None:
            raise ValueError("The affected player chooses its actual retained Identity")
        canon.sheets[str(subject)] = reprogram(
            sheet,
            details.identity,
            details.slot,
            source,
            allow_duplicate_labels=allow_duplicate_labels,
        )
    elif kind == "become_dog":
        canon.order = tuple(x for x in canon.order if x != subject) + (subject,)
        sheet.status_marked = False
        sheet.revision += 1
    elif kind in ("harpy_candidate_tag", "public_display_tag"):
        label = "Harpy Candidate" if kind == "harpy_candidate_tag" else details.tag.strip()
        if not label:
            raise ValueError("The Handler plays the general populace and supplies the actual Tag")
        sheet.tags.append(
            TagState(
                id=str(uuid5(NAMESPACE_URL, source + ":tag")),
                label=label,
                giver=period.handler,
                observers=(period.handler, subject),
            )
        )
        sheet.revision += 1
    elif kind in ("assigned_observer", "director_or_rival_arrives"):
        npc = (
            next(
                (
                    x
                    for x in canon.world.npcs
                    if x.id == details.npc and x.alive and x.captive_of is None
                ),
                None,
            )
            if canon.world
            else None
        )
        allowed_jobs = (
            {"handler", "guard"} if kind == "assigned_observer" else {"handler", "director"}
        )
        if (
            npc is None
            or not set(npc.jobs) & allowed_jobs
            or ("director" in npc.jobs and npc.controller == period.handler)
        ):
            raise ValueError(
                "Select the actual available printed NPC role with its correct human controller"
            )
        if npc.controller != period.handler and npc_confirmed_by != npc.controller:
            raise ValueError("UNRESOLVED_HUMAN_ROLE: this NPC needs its own human's response")
        # Appearance/assignment is not an invented conversation or scene attestation.
        canon.facts.append(
            {
                "kind": "observation_npc",
                "outcome": identity,
                "npc": npc.id,
                "subject": str(subject),
                "operation": kind,
            }
        )
    elif kind not in ("medical_probing", "hospital_stay"):
        raise ValueError("UNSUPPORTED_RULE: this consequence requires its typed resolver")
    canon.facts.append(
        {
            "kind": "observation_consequence",
            "outcome": identity,
            "subject": str(subject),
            "consequence": kind,
            "source_event": source,
        }
    )
    saved = outcome(updated, subject, identity)
    saved.resolved, saved.source_event = True, source
    updated.revision += 1
    return updated, canon


def scene(
    period: Period,
    expected: int,
    actor: int,
    kind: str,
    participants: tuple[int, ...],
    summary: str,
    *,
    extra_participants: frozenset[int] = frozenset(),
    required_participants: frozenset[int] = frozenset(),
) -> Period:
    current(period, expected)
    progress, observation = context(period, actor)
    if (
        not all_chosen(period, actor)
        or progress.scene is not None
        or actor not in participants
        or not set(participants) - {actor}
        or not set(participants) <= set(period.pilots) | {period.handler} | extra_participants
        or not required_participants <= set(participants)
    ):
        raise ValueError("Choose your scene after both humans have made their actual selections")
    legal = set(OFF_DUTY["low"]) | {"observation:" + x.kind for x in observation.outcomes}
    if kind not in legal:
        raise ValueError("Choose one selected consequence as your scene or a printed harsh scene")
    if kind in OFF_DUTY["low"] and not (set(participants) - {actor}) & (
        set(period.pilots) | {period.handler}
    ):
        raise ValueError("A printed harsh scene requires another Girl or the Handler")
    updated = clone(period)
    updated.progress[str(actor)].scene = Scene(
        kind=kind, participants=participants, summary=summary
    )
    updated.revision += 1
    return updated


def scene_roles(
    period: Period, state: GameState, subject: int, kind: str | None = None
) -> frozenset[int]:
    _, observation = context(period, subject)
    kinds = {"assigned_observer", "director_or_rival_arrives"}
    if kind is not None and kind.removeprefix("observation:") not in kinds:
        return frozenset()
    selected = {
        x.id
        for x in observation.outcomes
        if x.kind in kinds and (kind is None or "observation:" + x.kind == kind)
    }
    records = [
        x
        for x in state.facts
        if x.get("kind") == "observation_npc" and x.get("outcome") in selected
    ]
    people = (
        frozenset(
            n.controller
            for n in state.world.npcs
            if n.alive and any(x.get("npc") == n.id for x in records)
        )
        if state.world
        else frozenset()
    )
    if kind is not None and selected and not people:
        raise ValueError("Resolve the actual NPC assignment/appearance before making it your scene")
    return people


def complete(period: Period, subject: int) -> bool:
    progress, observation = context(period, subject)
    return bool(
        all_chosen(period, subject)
        and all(x.resolved for x in observation.outcomes)
        and progress.scene
        and set(progress.scene.participants) == set(progress.scene.acknowledgements)
    )
