# External Platform References | Verified 2026-11-02

**Discord**
- Interactions initial acknowledgement, followup tokens: https://docs.discord.com/developers/interactions/receiving-and-responding
- Message components and select/reference details: https://docs.discord.com/developers/components/reference
- Application commands: https://docs.discord.com/developers/interactions/application-commands
- Bot gateway/message intents: https://docs.discord.com/developers/events/gateway
- discord.py persistent views and component APIs: https://discordpy.readthedocs.io/en/latest/api.html
- discord.py interactions and ephemeral views: https://discordpy.readthedocs.io/en/stable/interactions/api.html

**OpenAI**
- Responses API and tool outputs: https://developers.openai.com/api/docs/guides/tools
- Strict structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs

**Engineering note:** API and library versions evolve. Codex must inspect current official documentation during M0, pin versions and record any decisions where the platform behavior differs from the verified design. No unverified promise that Discord can render a full custom side panel in ordinary chat, or that a 15-minute interaction token can be used to deliver player prompts days later.

**Licensed game sources:** User-supplied official `GIRL_FRAME_rulebook.pdf` (205 viewer pages) and `GIRL_FRAME_official_sheets.pdf`. Store rule/source page references in the rules registry. Do not redistribute the PDFs in a public repository or duplicate the complete rulebook inside code without rights clearance.

**Local project sources:** user-supplied v1.3.9 candidate consolidated GM source, and v1.3.9 100-turn audit. Both are **experimental**, not the published rules or live campaign data. This package does not embed private canon state or character histories.
