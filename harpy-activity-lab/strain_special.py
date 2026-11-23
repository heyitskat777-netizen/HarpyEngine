"""Activity entry forms for Strain effects with dedicated native services."""

from girlframe.discord_adapter.m2_forms import Field
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_fuel_shortage import FuelService
from girlframe.services.m3_patrol_harpy import PatrolHarpyService
from girlframe.services.m3_prisoner_escape import PrisonerEscapeService
from girlframe.services.m3_void_frame_entry import VoidFrameEntryService
from girlframe.services.onboarding import WorkflowError

FUEL = "strain.budget.high.1.2"
PRISONER = "strain.rebellion.low.4.2"
ENTRY = "strain.void.low.1.2"
PATROL = "strain.void.low.3.1"
RULES = (FUEL, PRISONER, ENTRY, PATROL)
ACCOUNT = Field("account", "Actual circumstances", paragraph=True)
CONFIRM = Field("confirm", "Confirm this step", (("yes", "Confirm"),))


def special_form(strain, viewer, source, channels):
    identity = source["id"]
    rule = source["rule_id"]
    if rule == FUEL:
        service = FuelService(strain.game)
        data = service.view(viewer, identity)
        if data["can_arm"]:
            return (
                lambda _: [CONFIRM],
                lambda actor, key, _: service.arm(
                    actor, key, identity, data["revision"]
                ),
                "Arm the shortage for the next actual Cadre battle. HarpyEngine will assign the loss when that battle is declared.",
            )
    elif rule == ENTRY:
        service = VoidFrameEntryService(strain)
        data = service.view(viewer, identity)
        if data["type"] == "arm" and data["state"] == "pending":
            return (
                lambda _: [ACCOUNT],
                lambda actor, key, values: service.arm(
                    actor,
                    key,
                    identity,
                    data["revision"],
                    data["game_revision"],
                    values["account"],
                ),
                "Record the circumstances. HarpyEngine picks the original pilot once and binds the obligation to its next actual Frame entry.",
            )
    elif rule == PRISONER:
        service = PrisonerEscapeService(strain)
        data = service.view(viewer, identity)
        if data["type"] == "start" and data["state"] == "pending":
            candidates = {row["id"]: row for row in data["candidates"]}
            if not candidates or not channels:
                raise WorkflowError(
                    "An actual held Foundation prisoner and a bound scene are required."
                )

            def start(actor, key, values):
                return service.start(
                    actor,
                    key,
                    identity,
                    data["work_revision"],
                    data["revision"],
                    int(values["channel"][0]),
                    ActorRef.model_validate(candidates[values["prisoner"][0]]["actor"]),
                    values["account"],
                )

            return (
                lambda _: [
                    Field(
                        "prisoner",
                        "Actual held prisoner",
                        tuple(
                            (token, row["label"]) for token, row in candidates.items()
                        ),
                    ),
                    Field("channel", "Bound scene", channels),
                    ACCOUNT,
                ],
                start,
                "Record the breakout attempt. The prisoner’s controller keeps ownership of its movement.",
            )
        if data["type"] != "start":
            return prisoner_outcome(service, data)
    elif rule == PATROL:
        return patrol_form(PatrolHarpyService(strain), viewer, identity)
    raise WorkflowError(
        "This Strain effect is waiting for its assigned native continuation."
    )


def prisoner_outcome(service, data):
    held = {"held:" + row["id"]: row for row in data["grips"]}
    failed = (
        {"failed:" + row["id"]: row for row in data["movements"]}
        if data["can_fail"]
        else {}
    )
    options = tuple((key, row["label"]) for key, row in (held | failed).items())
    if not options:
        raise WorkflowError(
            "Waiting for actual prisoner movement or an eligible performance in the source scene."
        )

    def submit(actor, key, values):
        choice = values["outcome"][0]
        if choice in held:
            hold = held[choice]
            return service.record_dealt(
                actor,
                key,
                data["id"],
                data["revision"],
                hold["action"],
                hold["id"],
                values["account"],
            )
        return service.resolve_failure(
            actor,
            key,
            data["id"],
            data["revision"],
            failed[choice]["id"],
            values["account"],
        )

    return (
        lambda _: [Field("outcome", "Actual evidence", options), ACCOUNT],
        submit,
        "File the result against the original breakout attempt.",
    )


def patrol_form(service, viewer, identity):
    data = service.get(viewer, identity)
    if data["can_roll"]:
        return (
            lambda _: [CONFIRM],
            lambda actor, key, _: service.roll(
                actor, key, identity, data["revision"], data["game_revision"]
            ),
            "Roll the additional sighting die once. HarpyEngine records the result for the original observer.",
        )
    if not (
        data["can_stage"] and data["observers"] and data["harpies"] and data["channels"]
    ):
        raise WorkflowError(
            "An actual joined patrol pilot, a Harpy with an established body, and a source scene are required."
        )
    observers = {
        ActorRef.model_validate(row["ref"]).token: row for row in data["observers"]
    }
    harpies = {
        ActorRef.model_validate(row["ref"]).token: row for row in data["harpies"]
    }

    def stage(actor, key, values):
        return service.stage(
            actor,
            key,
            identity,
            data["revision"],
            data["game_revision"],
            ActorRef.model_validate(observers[values["observer"][0]]["ref"]),
            ActorRef.model_validate(harpies[values["harpy"][0]]["ref"]),
            int(values["channel"][0]),
            values["account"],
        )

    return (
        lambda _: [
            Field(
                "observer",
                "Actual patrol pilot",
                tuple((token, row["label"]) for token, row in observers.items()),
            ),
            Field(
                "harpy",
                "Actual Harpy",
                tuple((token, row["label"]) for token, row in harpies.items()),
            ),
            Field(
                "channel",
                "Source scene",
                tuple((str(row["id"]), row["label"]) for row in data["channels"]),
            ),
            ACCOUNT,
        ],
        stage,
        "Record the actual visual contact. Its additional roll is a separate saved step.",
    )
