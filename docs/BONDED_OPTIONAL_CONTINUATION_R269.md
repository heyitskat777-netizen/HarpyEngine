# Bonded low-result optional continuation (r269)

## Printed source and demonstrated code mismatch

Freshly inspected the authorized Girl Frame 2026-09-01 PDF, PDF page59,
printed page57. The low result allows the counterpart to lower Status and
unmark an Identity if she continues, or weaken the Bond if she stops.
The r268 service only offered continue-with-both or stop, and required an
actually marked available Identity to continue. Thus a counterpart with no
marks could not continue at all. The existing focused low test used marks=True,
so did not establish this ordinary unmarked route.

## Bounded implementation and interpretation

Add an explicit counterpart-owned `continue_without_benefits` option. It
retains the real low roll, cost, source, and consent history, completes with no
Status/Bond/Identity mutation, and rejects any accompanying Identity selection.
The historical `continue` still takes both benefits with one actual available
marked Identity. `stop` still weakens the Bond. No invented marks, consent,
resource gains, or silent mechanical substitutes are introduced. Both native
rolled and existing diceless projections share this result logic and labels;
the new focused test covers only genuine native rolled Pair use.

The none-or-existing-both option is a delegated interpretation of “can,” not
independent printed-rule certification. Independent Status-only or Identity-only
benefits are alternative readings not added here. Root owns the matching
CAMPAIGN_RULINGS/registry note and digest update; printed clarity review and
legitimate production approval remain pending. Existing mid choices remain
unchanged: zero requests succeeds, but nonzero requests currently require
matching marked Identities. Whether those unmarks are benefits rather than costs
needs separate reconciliation; this patch does not certify that branch.

## Evidence and limits

Authored test_bonded_optional_continuation.py uses genuine source proposal,
separate counterpart consent, native low roll, and mocked native choice callback.
It checks absent marks, wrong-owner/contradictory-Identity atomic rejection,
unchanged Status/Bond/Identities, saved choice/source proof and service reopen,
original receipt and no new dice. Fixtures synthesize world/setup and temporary
rule approvals. Form values are directly supplied; not real Discord navigation.
Worker did not run pytest. Root must record executed outcomes. No full regression,
AI Director, privacy audit, process restart or restore proof is implied.
