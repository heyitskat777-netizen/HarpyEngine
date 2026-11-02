"""Validate the planning handoff, never claim a running bot has been tested.

Usage: python verification/verify_handoff.py
Dependencies: jsonschema>=4, stdlib.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
import jsonschema

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=[
 'AGENTS.md','README_START_HERE.md','docs/PRODUCT_AND_SCOPE.md','docs/ARCHITECTURE.md',
 'docs/STORAGE_EVENT_MODEL.md','docs/DISCORD_UX.md','docs/RULES_PORT_PLAN.md',
 'docs/AI_GM_HANDLER.md','docs/SECURITY_OPS.md','docs/MILESTONE_MASTER_PLAN.md',
 'docs/DECISIONS_RISKS.md','docs/PLATFORM_SOURCES.md','verification/REGRESSION_CASES.json',
 'verification/REGRESSION_CHAT_HANDOFF.md','verification/REVIEW_VERDICT_TEMPLATE.md',
 'work_orders/REVIEWER_REPORT_TEMPLATE.md',
 'reference/RULES_SOURCE_HANDOFF.md','reference/UI_MOCKUP_DESIGN_NOTES.md',
 'contracts/event_envelope.schema.json','contracts/roll_receipt.schema.json',
 'contracts/pending_choice.schema.json','contracts/ai_proposal.schema.json',
 'fixtures/synthetic_event.json','fixtures/synthetic_roll.json',
 'fixtures/synthetic_pending_choice.json','fixtures/synthetic_ai_proposal.json',
]
REQUIRED += [f'work_orders/CODEX_M{i}_{name}.md' for i,name in enumerate([
'START','ENGINE_LEDGER','PLAY_WIZARD','RULES','SCENES','GM','HANDLER','PILOT'])]
errors=[]
for item in REQUIRED:
 p=ROOT/item
 if not p.exists() or p.stat().st_size<100:errors.append(f'Missing or empty: {item}')
for name in ('event_envelope','roll_receipt','pending_choice','ai_proposal'):
 schema=json.loads((ROOT/'contracts'/f'{name}.schema.json').read_text())
 jsonschema.Draft202012Validator.check_schema(schema)
 fixture_name={'event_envelope':'synthetic_event','roll_receipt':'synthetic_roll','pending_choice':'synthetic_pending_choice','ai_proposal':'synthetic_ai_proposal'}[name]
 item=json.loads((ROOT/'fixtures'/f'{fixture_name}.json').read_text())
 jsonschema.validate(instance=item,schema=schema,format_checker=jsonschema.FormatChecker())
 if name=='roll_receipt':
  if item['kind']=='2d6' and (len(item['faces'])!=2 or any(not 1<=f<=6 for f in item['faces'])): errors.append('Bad 2d6 sample')
  if item['total']!=sum(item['faces'])+item['modifier_total']:errors.append('Bad sample roll total')
# Negative control: a Handler proposal with GM-world access must be rejected.
from copy import deepcopy
proposal_schema=json.loads((ROOT/'contracts/ai_proposal.schema.json').read_text())
invalid=deepcopy(json.loads((ROOT/'fixtures/synthetic_ai_proposal.json').read_text()))
invalid['role']='handler';invalid['knowledge_scope']='gm_world'
try:
 jsonschema.validate(instance=invalid,schema=proposal_schema)
 errors.append('Handler proposal with GM-world scope incorrectly validated')
except jsonschema.ValidationError:
 pass
cat=json.loads((ROOT/'verification/REGRESSION_CASES.json').read_text())
ids=[x['id'] for x in cat['cases']]
if len(ids)!=len(set(ids)):errors.append('Duplicate test case id')
if len(ids)<70:errors.append('Insufficient regression coverage')
if set(x['milestone'] for x in cat['cases'])!=set(f'M{i}' for i in range(8)):errors.append('Missing milestone test cases')
if any(x['status']!='NOT_RUN' for x in cat['cases']):errors.append('Some planning cases falsely marked as executed')
if not all((ROOT/'work_orders'/f).stat().st_size>250 for f in [f'CODEX_M{i}_{n}.md' for i,n in enumerate(['START','ENGINE_LEDGER','PLAY_WIZARD','RULES','SCENES','GM','HANDLER','PILOT'])]):errors.append('Missing work order')
if any(p.suffix.lower()=='.pdf' for p in ROOT.rglob('*')):errors.append('Copyrighted PDF in handoff')
for p in ROOT.rglob('*'):
 if p.suffix in ('.json','.md') and p.is_file() and p.name!='REGRESSION_CASES.json':
  txt=p.read_text(encoding='utf8')
  if re.search(r'(sk-[A-Za-z0-9_-]{20,}|mfa\.[A-Za-z0-9_-]{20,})',txt):errors.append(f'Looks like token credential in {p.relative_to(ROOT)}')
  if '2190-03-17' in txt and p.relative_to(ROOT).parts[0]=='fixtures':errors.append('Live campaign timestamp in synthetic fixture')
print(f'Planning package check: {len(REQUIRED)} required files, {len(cat["cases"])} planned cases, 4 JSON Schemas and 4 synthetic fixtures.')
if errors:
 for e in errors:print('ERROR:',e)
 sys.exit(1)
print('PASS: files present, example contracts validated, milestones covered, examples synthetic, and no forbidden PDFs.')
print('IMPORTANT: This verifies PLANNING PACKAGE ONLY. It DOES NOT assert any running bot, game engine or Discord integration passes.')
