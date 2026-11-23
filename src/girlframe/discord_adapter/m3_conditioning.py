"""Native consent, owned roll and effect choices for Conditioning."""

import asyncio
from typing import Any, cast

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_conditioning as rules
from girlframe.services.m3_conditioning import END, ConditioningService, Step

LABELS = {
    "replace": "Replace one Identity",
    "teach": "Teach Identities into empty slots",
    "embrace": "Embrace existing Tags",
    "erase": "Erase two Identities",
    "bond": "Establish an Intense Bond and weaken shared Bonds",
    "excise": "Excise a Girl Asset",
    "tag": "Give a Tag",
    "word": "Teach a word that can make the trainee Helpless",
}


async def open_invite(
    interaction: discord.Interaction, service: ConditioningService, channel: int
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.menu, viewer, channel)

    async def send(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.invite,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            channel,
            data["scene"],
            data["cast"],
        )
        return "Private request saved. The trainee can accept or decline in their Inbox."

    form = NativeForm(
        viewer.user_id,
        "Request Conditioning",
        "Invite " + clean(data["trainee"]) + " privately.",
        [Field("decision", "Send request", (("request", "Ask to begin Conditioning"),))],
        send,
    )
    await reply(interaction, form.text(), form)


async def open_speech(
    interaction: discord.Interaction, service: ConditioningService, channel: int
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.speech, viewer, channel)
    sources = {
        f"{identity}:{index}": (identity, index, phrase)
        for identity, index, phrase in data["sources"]
    }
    if not sources:
        await reply(
            interaction, "No unused Conditioning word is available for this original scene."
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        identity, index, _ = sources[values["source"][0]]
        await asyncio.to_thread(
            service.speak,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            data["scene"],
            data["revision"],
            identity,
            index,
        )
        return (
            "The word was heard in this private scene. "
            "This Helplessness lasts until a successful refusal."
        )

    form = NativeForm(
        viewer.user_id,
        "Speak a Conditioning word",
        "Confirm the word your original trainer actually speaks to its trainee.",
        [
            Field(
                "source",
                "Choose the word your trainer spoke",
                tuple((key, row[2]) for key, row in sources.items()),
            )
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


def _choice_form(kind: str, resource: dict[str, Any]) -> list[Field]:
    identities = resource["identities"]
    if kind == "replace":
        return [
            Field("identity", "Actual Identity to replace", identities),
            Field("label", "New Identity"),
        ]
    if kind == "erase":
        return [Field("erase", "Actual Identities to erase", identities, 2, 2)]
    if kind == "teach":
        fields = [Field("label", "First Identity")]
        if resource["vacancies"] >= 2:
            fields.append(Field("extra", "Optional second Identity", required=False))
        return fields
    if kind == "embrace":
        return [
            Field("first_tag", "Actual Tag"),
            Field("first_replace", "Identity to replace", identities, minimum=0, required=False),
            Field("second_tag", "Optional second Tag", resource["tags"], minimum=0, required=False),
            Field(
                "second_replace",
                "Identity to replace for the second Tag",
                identities,
                minimum=0,
                required=False,
            ),
        ]
    if kind == "bond":
        options = tuple((x.token, label) for x, label in resource["bonds"])
        return (
            [
                Field(
                    "weaken",
                    "Shared existing Bonds to weaken",
                    options,
                    0,
                    len(options),
                    required=False,
                )
            ]
            if options
            else []
        )
    if kind == "excise":
        return [
            Field("asset", "Actual Girl Asset to remove", resource["assets"]),
            Field("extra", "Optional new Girl Asset", required=False),
        ]
    if kind == "word":
        return [Field("label", "The word the trainer arms")]
    return [Field("label", "New Tag")]


def _effect(kind: str, values: dict[str, Any], resource: dict[str, Any]) -> rules.Choice:
    account = values["account"]
    if kind == "replace":
        return rules.Replace(account=account, identity=values["identity"][0], label=values["label"])
    if kind == "erase":
        return rules.Erase(account=account, identities=values["erase"])
    if kind == "teach":
        return rules.Teach(
            account=account,
            labels=tuple(label for label in (values["label"], values.get("extra")) if label),
        )
    if kind == "embrace":
        choices = tuple(
            rules.TagChoice(tag=values[f"{side}_tag"][0], replace=_one(values, f"{side}_replace"))
            for side in ("first", "second")
            if values.get(f"{side}_tag")
        )
        return rules.Embrace(account=account, choices=choices)
    if kind == "bond":
        refs = {x.token: x for x, _ in resource["bonds"]}
        return rules.Bond(account=account, weaken=tuple(refs[x] for x in values.get("weaken", ())))
    if kind == "excise":
        return rules.Excise(
            account=account, asset=values["asset"][0], replacement=values.get("extra") or None
        )
    if kind == "word":
        return rules.Word(account=account, phrase=values["label"])
    return rules.Tag(account=account, label=values["label"])


def _one(values: dict[str, Any], key: str) -> str | None:
    return values[key][0] if values.get(key) else None


async def open_request(
    interaction: discord.Interaction, service: ConditioningService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    phase = data["phase"]
    if phase in END:
        await reply(interaction, "Conditioning " + phase + ".")
        return
    resource = data["resources"]
    options = [("withdraw", "Withdraw from Conditioning")]
    summary = "Only the original participants can review this private request."
    if data["roll"] is not None:
        summary += "\nSaved total: " + str(data["roll"]["total"])
    if data.get("blocked"):
        summary += "\n" + clean(data["blocked"])
    elif data["can_act"]:
        if phase == "offered":
            options.insert(0, ("consent", "Accept the request"))
        elif phase == "consented":
            options.insert(0, ("roll", "Roll for Conditioning"))
        elif phase == "choices":
            summary += "\nEffects remaining: " + str(data["remaining"])
            available = {
                "replace": bool(resource["identities"]),
                "teach": resource["vacancies"] > 0,
                "embrace": bool(resource["tags"])
                and bool(resource["identities"] or resource["vacancies"]),
                "erase": len(resource["identities"]) >= 2,
                "bond": True,
                "excise": bool(resource["assets"]),
                "tag": True,
                "word": True,
            }
            options = [(kind, label) for kind, label in LABELS.items() if available[kind]] + options
        elif phase == "confirm":
            options.insert(0, ("confirm", "Describe my response and apply the effects"))
            for word in data["words"]:
                summary += "\nConditioning word · " + clean(word)
            for label, action, name in data["changes"]:
                summary += "\n" + action + " " + label + " · " + clean(name)
            for kind, account in data["choices"]:
                summary += "\n" + LABELS[kind] + " · " + clean(account)[:130]

    async def select(current: discord.Interaction, selection: str) -> None:
        step: Step = "choose" if selection in LABELS else cast(Step, selection)
        prompt = "This submission belongs to the original participant."
        if step == "choose":
            fields = _choice_form(selection, resource)
            if selection == "embrace":
                fields[0] = Field("first_tag", "Actual first Tag", resource["tags"])
                if not resource["identities"]:
                    fields = [x for x in fields if not x.key.endswith("_replace")]
            fields.append(
                Field("account", "Describe your part of the Conversation", paragraph=True)
            )
        elif step == "confirm":
            fields = [Field("account", "Describe your own response", paragraph=True)]
            if data["roll"]["total"] <= 7:
                fields.append(Field("identity", "Optional new Identity", required=False))
                if not resource["vacancies"] and resource["identities"]:
                    fields.append(
                        Field(
                            "replace",
                            "If writing an Identity, choose its slot",
                            resource["identities"],
                            0,
                            required=False,
                        )
                    )
        elif step == "consent":
            prompt = (
                "You may withdraw before applying the effects. If you proceed, the trainer "
                "will see your eligible Identities, Tags and ordinary Girl Assets."
            )
            fields = [
                Field(
                    "sharing",
                    "Share eligible existing Bonds with this trainer?",
                    (("private", "Keep other Bonds private"), ("share", "Share eligible Bonds")),
                )
            ]
        else:
            fields = [Field("decision", "Confirm", (("yes", "Confirm " + step),))]

        async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
            new = (
                rules.IdentityChoice(name=values["identity"], replace=_one(values, "replace"))
                if step == "confirm" and values.get("identity")
                else None
            )
            effect = _effect(selection, values, resource) if step == "choose" else None
            result = await asyncio.to_thread(
                service.advance,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                step,
                choice=effect,
                account=values.get("account") if step == "confirm" else None,
                new_identity=new,
                share_bonds=_one(values, "sharing") == "share",
            )
            return f"Conditioning {result['phase']}. Check the private Inbox to continue."

        form = NativeForm(viewer.user_id, "Conditioning", prompt, fields, submit)
        await reply(current, form.text(), form)

    await Picker(viewer.user_id, summary[:1600], tuple(options), select).show(interaction)
