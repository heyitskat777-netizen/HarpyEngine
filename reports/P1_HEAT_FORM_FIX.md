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
