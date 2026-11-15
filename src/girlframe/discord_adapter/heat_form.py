"""Read-only Heat projection for native Play forms; services still validate costs."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast

import discord

from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_girl_runtime_state import has_rule


class HeatForm(NativeForm):
    def __init__(
        self,
        owner: int,
        title: str,
        instructions: str,
        fields: list[Field],
        submit: Callable[[discord.Interaction, dict[str, Any]], Awaitable[str | None]],
        *,
        resources: dict[str, Any],
        refresh: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        no_heat_plays: tuple[str, ...] = (),
        fixed_no_heat: bool = False,
        disposal_key: str = "disposable_heat",
        disposal_allowed: bool | None = None,
        disposal_plays: tuple[str, ...] | None = None,
        identity_plays: tuple[str, ...] | None = None,
        minimum_spend: int = 0,
        paired_allowed: bool | None = None,
        values: dict[str, Any] | None = None,
    ):
        self.templates = fields.copy()
        self.resources, self.refresh_resources = resources, refresh
        self.no_heat_plays = no_heat_plays
        self.fixed_no_heat, self.disposal_key = fixed_no_heat, disposal_key
        self.disposal_allowed, self.disposal_plays = disposal_allowed, disposal_plays
        self.identity_plays, self.minimum_spend = identity_plays, minimum_spend
        self.paired_allowed = paired_allowed
        super().__init__(owner, title, instructions, fields, submit, values=values)

    def selected(self, key: str) -> str | None:
        value = self.values.get(key)
        result = value[0] if isinstance(value, (tuple, list)) and value else value
        return result if isinstance(result, str) and result != "none" else None

    def project(self) -> list[Field]:
        resource = self.resources
        identities = [*resource.get("identities", []), *resource.get("additional_identities", [])]
        eligible = {x["id"]: x for x in identities if not x["marked"]}
        identity = eligible.get(self.selected("identity") or "")
        if self.identity_plays is not None and self.selected("play") not in self.identity_plays:
            identity = None
            self.values.pop("identity", None)
        if identity is None and self.selected("identity") is not None:
            self.values.pop("identity", None)
        paired = bool(
            identity
            and identity.get("paired")
            and has_rule(resource, "girl.bonded.bonded-pair", "BONDED")
        )
        if self.paired_allowed is not None:
            paired = bool(identity and identity.get("paired") and self.paired_allowed)
        play = self.selected("play")
        disposal = bool(
            identity
            and (
                has_rule(resource, "girl.stim-blissed.disposable-psyche", "STIM-BLISSED")
                or self.selected("learned_psyche")
            )
        )
        if self.disposal_allowed is not None:
            disposal = bool(identity and self.disposal_allowed)
        if self.disposal_plays is not None and play not in self.disposal_plays:
            disposal = False
        if not identity:
            self.values.pop("gain", None)
        if not paired:
            self.values.pop("pair_share", None)
            self.values.pop("share", None)
        if not disposal:
            self.values.pop(self.disposal_key, None)
        if play != "disobey_orders":
            self.values.pop("witnessed", None)
        gain_values = ("5",) if paired else ("1", "2", "3")
        if self.selected("gain") not in gain_values:
            self.values.pop("gain", None)
        share_key = "share" if any(x.key == "share" for x in self.templates) else "pair_share"
        if self.selected(share_key) not in tuple(str(x) for x in range(6)):
            self.values.pop(share_key, None)
        gain = int(self.selected("gain") or 0) if identity else 0
        share = int(self.selected(share_key) or 0) if paired and gain else 0
        extra = int(self.selected(self.disposal_key) or 0) if disposal else 0
        if extra not in (0, 3, 4):
            self.values.pop(self.disposal_key, None)
            extra = 0
        available = max(0, int(resource["heat"]) + gain - share + extra)
        spends = (
            (0,)
            if self.fixed_no_heat
            or play in self.no_heat_plays
            or play == "flirt"
            and self.selected("kicked_puppy_basis") == "damaged"
            else ((available,) if available >= 5 else tuple(range(available + 1)))
        )
        spends = tuple(x for x in spends if x >= self.minimum_spend)
        result = []
        for field in self.templates:
            if field.key == "witnessed" and play != "disobey_orders":
                continue
            if field.key == "gain":
                if not identity:
                    continue
                field = replace(field, options=tuple((x, x) for x in gain_values))
            if field.key in ("share", "pair_share"):
                if not paired:
                    continue
                field = replace(
                    field,
                    label="Of the 5 Paired Heat, give your Pair",
                    options=tuple((str(x), str(x)) for x in range(6)),
                )
            if field.key == self.disposal_key and not disposal:
                continue
            if field.key == "identity":
                if self.identity_plays is not None and play not in self.identity_plays:
                    continue
                field = replace(
                    field,
                    options=tuple(
                        (key, label)
                        for key, label in field.options
                        if key == "none" or key in eligible
                    ),
                )
                if not field.options:
                    continue
            if field.key == "heat":
                field = replace(
                    field,
                    label=f"Heat to spend (available: {available})",
                    options=tuple((str(x), str(x)) for x in spends)
                    or (("unavailable", "No Heat available for this Play"),),
                )
                if self.selected("heat") not in {str(x) for x in spends}:
                    self.values.pop("heat", None)
            result.append(field)
        return result

    def controls(self) -> None:
        key = self.fields[self.index].key
        self.fields = self.project()
        self.index = next(
            (i for i, x in enumerate(self.fields) if x.key == key),
            min(self.index, len(self.fields) - 1),
        )
        self.option_page = min(
            self.option_page, max(0, (len(self.fields[self.index].options) - 1) // 25)
        )
        super().controls()

    async def present(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner:
            await self.interaction_check(interaction)
            return
        if self.refresh_resources is not None:
            self.resources = await self.refresh_resources()
        await super().present(interaction)

    @discord.ui.button(label="Review & Confirm", style=discord.ButtonStyle.success, row=3)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        if not await self.interaction_check(interaction):
            return
        chosen = self.values.copy()
        if self.refresh_resources is not None:
            self.resources = await self.refresh_resources()
        self.controls()
        if self.values != chosen:
            await reply(
                interaction,
                "Resources or available options changed. "
                "Review your choices before confirming again.",
                self,
            )
            return
        callback = cast(
            Callable[[NativeForm, discord.Interaction, discord.ui.Button[Any]], Awaitable[None]],
            NativeForm.confirm,
        )
        await callback(self, interaction, button)
