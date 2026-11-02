"""Generate a traceable test-case catalog for Codex and independent regtesting.
This is planning data, not a fake test run."""
import json
from pathlib import Path
CASES={
'M0':[
('M0-001','Fresh clone installs reproducibly without credentials','Setup works from pinned dependency lock and Python requirement.'),
('M0-002','Engine domain has no Discord or OpenAI imports','Static module import-boundary test.'),
('M0-003','Tests and help CLI run offline','No external HTTP/Discord/OpenAI network dependency.'),
('M0-004','Repository contains no secrets, official PDFs or live saves','Secret scan and forbidden source path scan.'),
('M0-005','CI and local commands are reproducible','ruff/pytest with actual captured output.')],
'M1':[
('M1-001','Fresh database migration','Tables and foreign keys created, migration version persisted.'),
('M1-002','New campaign and member bind guild/user snowflakes','Authority uses IDs rather than display names.'),
('M1-003','Create Girl draft and own private sheet','Only owner sees private synthetic field.'),
('M1-004','Other user cannot inspect owner private sheet','Secret canary absent from all outputs.'),
('M1-005','Two campaigns with identical callsign are isolated','Cross-campaign query/mutation denied.'),
('M1-006','Basic 2d6 real dice receipt','Faces in 1..6, total computed, OS RNG used in production.'),
('M1-007','Duplicate interaction retries exactly same roll','One DB receipt and one event after duplicate + restart.'),
('M1-008','Same interaction ID with different payload rejected','Typed idempotency conflict; no state changes.'),
('M1-009','Concurrent expected-revision mutation','One success, other STALE_REVISION, no lost update.'),
('M1-010','Crash after commit before Discord send','Outbox retries; DB event not duplicated.'),
('M1-011','Crash after Discord send before ACK persistence','At-least-once delivery reconciliation; game state not duplicated.'),
('M1-012','Rebuild projections after restart','Event/roll/sheet projections match original exactly.'),
('M1-013','Fake player cannot act as another PC','Server-side ownership check, no UI-only security.'),
('M1-014','Original Discord message edit does not mutate canon','Source link remains, committed events immutable.'),
('M1-015','Invalid source-message claim to be system authority','Ignored as game text, no escalation.'),
('M1-016','Private sheet and ledger pagination','No leaking hidden data in errors or pages.'),
('M1-017','Fake Discord integration end-to-end command sequence','create→join→GirlDraft→sheet→basic roll→ledger.'),
('M1-018','Backup restore and migration smoke','Restore to new location returns identical journal/rolls.'),
('M1-019','No fake official Play claim','Roll is labeled test primitive, not Flirt/Engage.'),
('M1-020','Safety pause command works without AI','Scene or campaign OOC pause persists correctly.')],
'M2':[
('M2-001','/play legal selections reflect current sheet','Only implemented Play IDs/eligible targets offered.'),
('M2-002','Heat cannot exceed available resources','Rejects negative/too-large spend.'),
('M2-003','Heat 5+ forced full spend','Published rule enforced for appropriate acting trigger.'),
('M2-004','Identity marking is pre-roll','1–3 Heat gain when eligible before dice sampled.'),
('M2-005','Post-roll Tag modifies only legal roll','Not applied before dice, cannot mark multiple Girl Tags.'),
('M2-006','Repeated click does not reroll','Full receipt stable across view and bot restart.'),
('M2-007','Pending other-human choice authenticated','Only target player may submit answer.'),
('M2-008','Pending question survives days and expired ephemeral UI','Resume via /choice or durable bot message.'),
('M2-009','Published 11+ choices and 7− effects exact','No substituted Tag or missing mandatory Handler action.'),
('M2-010','Unimplemented Play blocks cleanly','UNSUPPORTED_RULE, no roll, no guessed effect.'),
('M2-011','Direct superior order required for Disobey Orders','Fails if only generic disagreement.'),
('M2-012','Disobey Orders 7− halts refusal','No contrary narrative accepted.'),
('M2-013','Flirt target answer comes from target player','No AI authored reply or unilateral Bond improvement.'),
('M2-014','Stale Play wizard target/Heat selection','Refresh or typed error without double-spend.'),
('M2-015','Result pending choices cannot publish final state','Choice-owner and options count enforced.')],
'M3':[
('M3-001','Status swap and one-use maxim','Oldgen gain exchange and consume only once.'),
('M3-002','Go Off-Duty Status modifiers and 7− scene','Dog/Wing/Ace and on-screen harsh scene.'),
('M3-003','Princess Show Dog both extra choices','Printed second selection/NPC Bond not dropped.'),
('M3-004','Dog mission-end Punishment','Applies even if not in mission; absent PC choice respected.'),
('M3-005','Budget High 6 second-column recursion','Compulsory extra rolls/endgame; cannot park indefinitely.'),
('M3-006','Low Rebellion escaped prisoner escalation','Mandatory Strain rise if unresolved.'),
('M3-007','Void/Gorgon movement and placement','No invented map square; exact eligible movements.'),
('M3-008','Flirt 11+ all official extra options','Never swap arbitrary Tag for printed choice.'),
('M3-009','Director due price and breach consequence','No consequence-free expiration.'),
('M3-010','Harpy medical, custody, Core consent separate','No implied conversion from medical help.'),
('M3-011','Requisitions and Permissions triggers','All participants and Ace bonuses exact.'),
('M3-012','Per-Playbook and Frame Assets','All agreed printed roles and exceptions tested.'),
('M3-013','All published table rows tracked','Each Low/High Strain table branch has source fixture.'),
('M3-014','Full rule registry coverage report','No unsupported Play incorrectly marked verified.')],
'M4':[
('M4-001','Concurrent independent scene progress','MAUL-like scene can wait while another progresses.'),
('M4-002','Location temporal conflict rejected','One Girl cannot be in incompatible scenes at same fictional time.'),
('M4-003','Private fact revealed only to one real Player','Backend projection hides from others.'),
('M4-004','GM secret not automatically known to Handler','Knowledge grant has explicit source and witness.'),
('M4-005','Message context canon proposal not automatic commit','GM/facilitator validates contested fiction.'),
('M4-006','Event correction preserves original and descendants','No silent rewrite of roll/canon.'),
('M4-007','Safety pause stops associated scene','No fictional penalty or automated narration.'),
('M4-008','Scene pending choice survives restart','DB state restores and recipient receives same required action.'),
('M4-009','Late message not retroactive knowledge','In-world timestamps and dependency barriers enforced.')],
'M5':[
('M5-001','AI JSON proposal schema validation','Unknown effect/target/invalid schema rejected.'),
('M5-002','Prompt-injection in user dialogue','No privileged instructions follow from chat text.'),
('M5-003','Escaped Harpy custody contradiction','GM proposal rejected without new committed capture.'),
('M5-004','GM cannot generate player dialogue/choices','Human PC speech/consent remains absent.'),
('M5-005','Model outage leaves pending GM ruling','No silent canonical success or reroll.'),
('M5-006','Stale model proposal rejected','State revision check before commit.'),
('M5-007','Basic game queries perform zero AI calls','/sheet, /roll basic, /ledger bypass model.'),
('M5-008','Private facts filtered from NPC/player output','GM-only canary never appears in user-facing output.')],
'M6':[
('M6-001','Handler never reads GM-only canary','Different knowledge projection than GM.'),
('M6-002','Handler direct order source/provenance','Issuer, exact words, recipient, scene and time recorded.'),
('M6-003','Handler cannot choose for human Girl','Human owns order response, Heat and legal Play options.'),
('M6-004','Handler Punishment legal trigger/option','Authoritative Engine validates her choice.'),
('M6-005','Handler overdue obligation has consequences','Staged or explicitly breached, never erased by model.'),
('M6-006','GM and Handler voice/authority distinct','Discord projections labeled; provenance checks.'),
('M6-007','Handler can be mistaken without changing canon','False assertion not world event unless witnessed/validated.')],
'M7':[
('M7-001','Three real human players, complete mission','Independent acceptance, Plays and mission-end rewards/punishments.'),
('M7-002','Complete Off-Duty with Strain cascade','No incomplete mandatory followups.'),
('M7-003','Mid-game restart and player offlining','All pending choices, scenes and rolls recover.'),
('M7-004','Conflict remains human-generated','No fake consent, player speech or forced interpersonal resolution.'),
('M7-005','Canonical event/replay audit','Every mechanical value traces to receipts and choices.'),
('M7-006','Security, retention, backup and cost review','Export/delete, access permissions, spending caps, abuse handling.'),
('M7-007','Usability/mobile pilot report','3–5 human player feedback, major UI blockers resolved.'),
('M7-008','Public-release restrictions explicitly documented','No rights/age-policy claims unless reviewed.')]
}
output=[]
for milestone,cases in CASES.items():
 for cid,title,expected in cases:
  output.append({'id':cid,'milestone':milestone,'title':title,'expected':expected,
      'evidence_required':['test_name','executed_command','actual_result','log_or_trace','git_commit'],
      'status':'NOT_RUN','severity_if_failed':'BLOCKER' if (cid.startswith(('M0','M1','M2','M3')) and any(x in title.lower() for x in ['private','human','duplicate','roll','secret','mission-end','reboot','status swap','recursion','canonical','disobey','outage','concurrent','schema'])) else 'HIGH'})
Path(__file__).with_name('REGRESSION_CASES.json').write_text(json.dumps({'schema_version':1,'status':'planning_only_not_executed','cases':output},indent=2)+'\n')
print('Generated',len(output),'planned cases, by milestone', {k:len(v) for k,v in CASES.items()})
