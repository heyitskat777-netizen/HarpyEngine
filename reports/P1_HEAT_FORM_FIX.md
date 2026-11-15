# Available Heat and conditional Play questions

Owner request: explain Paired Heat, show only available spending choices and ask
whether a Foundation member witnessed a refusal only for Disobey Orders.

Paired Heat is the existing Bonded rule: mark an eligible Paired Identity for5
Heat and choose how much goes to the actual Pair. Ordinary Identities grant1–3.
The Play wizard now hides the Pair split unless a Paired Identity is selected,
and hides the witness question outside Disobey Orders; switching Plays clears
the earlier witness answer. The producer also guards the witnessed flag by Play.

A small native HeatForm derives choices from the actual resource snapshot plus
selected Identity gain, less Pair share, plus eligible selected disposal. It
removes optimistic unselected gains, invalidated spending choices and inapplicable
mark/share controls. Ordinary spend-all at5+is retained. Available balance is
refreshed on render/confirmation where the existing resource getter is used;
source-bound delegated forms retain their original revision/owner and service
checks. No read or selector commits Heat, marks an Identity or rolls dice.

Consumers: Pilot Play, actual-role/Harpy Plays, battle/Dormant, Alpha counters,
collar survival, Bonded, Changeling, Clone AM, Easy Target, Prince, Princess,
Red Queen, Stim and Vatgrown forms. Source-specific no-Heat Nightmare and damaged
Asset bases stay explicit; Alpha marking/disposal is limited to its legal counter
Plays. Stim's disposal field alias and Princess's actual counterpart resources
are explicit. Princess's private child projection adds only its derived Paired
eligibility flag, without exposing a controller's private sheet as a substitute.
Already source-bounded unrelated forms keep their current special budgets.

Local verification: two initial native/split/stale-budget checks passed1.45s.
Final integrated normal selection passed5cases in9.01s: actual Pilot wizard,
Paired split and changed balance, explicit no-Heat/disposal alias/zero balance,
and two existing actual Princess/Stim delegated-resource flows. Changed-file
Ruff/format (22Python files) and source mypy (21files) pass. A worker integrated
four separately owned consumers; root owns the helper/integration/checks.
CI includes these five cases beside the prior focused packet. No full regression
or human acceptance is claimed. Runtime version is bumped to0.1.3; exact CI and
deployment evidence will be added after the release gate.

Bounded component review found one concrete freshness issue: Clone AM's fresh
actor preview was overwritten with older outer-menu Heat. The final consumer
uses that actual actor's shared clone-sheet balance and refreshes the same source
on render/confirmation. Its real native-menu test passes after opening the menu,
changing shared Heat and refreshing again (1passed,2.25s). A missing acknowledgement
in the test's direct callback invocation caused its first transport assertion to
fail; the test was corrected, with original failure retained privately. No other
concrete blocker was identified in the bounded review. CI includes this case;
the earlier5normal passes remain scoped evidence, not full regression.

Final confirmation safeguard: if a refresh invalidates a selected Identity or
spending choice, show the changed controls and require explicit confirmation
again. Never silently omit an intended mark and commit a different Play. The
three Heat-form normal cases pass after this guard (3passed,1.33s), including an
Identity marked elsewhere while the form is open. Original service transactions,
revision checks and idempotency remain unchanged.

Focused CI43698787612 at49d0e26reported60passed/13failed: the new confirmation
guard treated ignored gain/share defaults as changed intent in existing native
Harpy/Princess flows. First targeted correction left12failures; the complete
semantic correction preserves the existing rule that gain without an Identity
has no effect, and zero share/disposal defaults have no effect. Actual selected
Identity loss or invalidated spending still requires renewed confirmation. All13
original failed nodes plus the3stale/budget cases then passed together:
16passed in27.06s. No existing tests were removed or weakened; failures/artifacts
are retained privately. A new exact-commit focused gate is required before startup.


Final exact runtime source: `d2b4c853981ea7b00ced572aedbe1f16e11f44dd`,v0.1.3.
[Focused CI43699349660](https://github.com/heyitskat777-netizen/HarpyEngine/actions/runs/43699349660)
passed73tests/0failures/errors/skips in104.782s, including all original13failures,
the3budget/intent checks and actual Clone shared-balance freshness. Static checks,
CLI, registry/planning and repository checks pass. No full regression repeated.

Deployment completed after successful authentication preflight: old process
stopped gracefully, fresh0600consistent backup retained, new exact frozen source
started with byte-identical private campaign policy. One process, Running v0.1.3
presence,19guild commands and the preserved global launch are verified. Schema
0020and the optional second-Bond policy remain unchanged. No player action or
fictional Heat transaction was fabricated for live verification. Human UI results
remain pending: reopen /play, check ordinary0Heat→only0spend, optional Identity gain,
actual Paired split where eligible, and witness question only for Disobey Orders.
