# Private Activity review of CHANGELING and Red Queen

Source: the official GIRLFRAME rulebook, printed pp. 79–81 and 86–89 (PDF pp. 81–83 and 88–91), SHA-256 `0f8dbaae7f0a254cdbfb4856b9f50c44fd31a97b36234062db4ae7f4874b55f0`. Compared the printed branches with the native services in the bundled HarpyEngine and their Activity forms. This is a scoped implementation review for private play. The canonical independent review fields and the live campaign policy are unchanged.

| Rule | Private Activity behavior |
|---|---|
| Blank Slate, p. 79 | Start from the original speaker's defining words. On a low roll the pilot selects an Identity to erase and the original Handler records the recent memory window. A mid roll deepens the actual Bond. The original speaker may push once, giving a Tag with the native Status consequence. A high roll applies the authoritative erasure rules and grants Blank Slate. Its owner can adopt an Identity the other person actually holds and discloses in conversation. |
| Psych Strings, p. 80 | Native generation accompanies starting and deepened Bonds. The separate Fingers in the Brain and other String spending moves are outside this release. |
| Body of Clay, p. 81 | Requires the actual Requisition and original cockpit. A mid roll gives the owner two changes or a disclosed appearance to copy. A high roll gives the owner three changes and the original Handler one. On a low roll the Handler chooses the changes. The Handler's taste answer raises Status or gives a Tag. |
| Queen's Court, pp. 86–87 | Import the accepted five-AM allocation for the original Frame. Court marking and other Court Plays retain their own gates. |
| AM Transfer, p. 87 | Only the original Red Queen can transfer a self-borne AM from a proved source. HarpyEngine validates a completed intimacy source, an actual weakened Bond, or completed Punishment with higher Status. The source is consumed once. |
| Memory Extraction, p. 89 | Requires the actual Requisition and confirmed, physically co-present restrained brain access. The Queen chooses a memory category. On a high roll the original Handler chooses a distinct second category. The affected controller files the memory details. On mid or high rolls a Court AM replaces eligible linked Identities. A low roll takes the memory alone. A later associated Identity or NPC Tag unlocks the affected controller's restoration and optional AM choice. |

Admission is an explicit, default-empty allowlist in the private Activity policy. The registry digest, package ownership, source proof, Choice ownership and saved roll checks remain in HarpyEngine. Historical records retain their original effects. The private scope does not approve whole playbooks or exceptional body and resource combinations.

## Automated evidence

- Private Activity scope and popup workflows, test_identity_specialists.py: 6 passed. Uses the unmodified bundled registry and the same scoped policy used by the private Activity. Covers high Blank Slate and adoption, the mid overstep, mid Clay with a disclosed appearance, low and high Memory Extraction, and AM Transfer from a proved Bond operation. Exercises original choice owners, duplicate commands and persisted roll receipts.
- Focused native branch tests in test_changeling.py, test_changeling_mid_push.py, test_changeling_clay_copy.py, and test_red_queen.py: 12 passed, 18 unrelated cases deselected. Uses synthetic campaign ledgers. The Windows run uses UTF-8 and allows loopback for asyncio while Discord interactions are faked.
- Private startup preflight: all eight saved Activity policy digests matched the bundled registry. No campaign writes were performed by the preflight.
