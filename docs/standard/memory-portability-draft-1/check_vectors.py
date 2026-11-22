"""Candidate conformance oracle, not a provider or production importer.
Run: python check_vectors.py. Requires jsonschema (repository dependency).
"""
import hashlib, json, re
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
P=Path(__file__).parent
SCHEMA=json.loads((P/'schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)
def unique(items):
 if len(items)!=len(set(items)): raise ValueError('duplicate identifier')
def check(case):
 e,s,r=case['export'],case['selection'],case['receipt']
 for doc in (e,s,r): Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(doc)
 # Require explicit offset; do not depend on optional jsonschema format packages.
 times=[e['exported_at']]
 for rec in e['records']:
  if rec['state']=='included': times.extend([rec['metadata']['created_at'],rec['metadata']['updated_at']])
 for value in times:
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})',value): raise ValueError('timestamp syntax')
  datetime.fromisoformat(value.replace('Z','+00:00'))
 # Fixture transport is deterministic bytes, not a proposed universal JSON canonicalization.
 raw=json.dumps(e,ensure_ascii=False,separators=(',',':')).encode('utf-8')
 digest=hashlib.sha256(raw).hexdigest()
 if s['export_sha256']!=digest or r['export_sha256']!=digest: raise ValueError('export integrity mismatch')
 if s['source_subject']!=e['subject_id']: raise ValueError('source subject mismatch')
 for k in ('selection_id','destination_provider','destination_subject'):
  if s[k]!=r[k]: raise ValueError('selection binding mismatch')
 ids=[x['record_id'] for x in e['records']]; unique(ids)
 if e['retained_record_count']!=len(ids): raise ValueError('inventory mismatch')
 bids=[x['blob_id'] for x in e['blobs']]; unique(bids)
 selected=s['selected_record_ids']; unique(selected)
 if not set(selected)<=set(ids): raise ValueError('unknown selected record')
 outcomes=[x['record_id'] for x in r['outcomes']]; unique(outcomes)
 if set(outcomes)!=set(selected): raise ValueError('missing or unselected outcome')
 available={x['record_id']:x for x in e['records']}
 blobs={x['blob_id']:x for x in e['blobs']}
 for x in e['records']:
  if x['state']=='included':
   if not set(x['content']['blob_ids'])<=set(bids): raise ValueError('undeclared media')
   if x['content']['text'] is None and not x['content']['blob_ids']: raise ValueError('empty content')
 for b in e['blobs']:
  if b['state']=='included':
   data=bytes.fromhex(case['blob_hex'].get(b['path'],''))
   if len(data)!=b['byte_length'] or hashlib.sha256(data).hexdigest()!=b['sha256']: raise ValueError('blob integrity mismatch')
 for o in r['outcomes']:
  rec=available[o['record_id']]
  if o['status'] in ('imported','transformed'):
   if rec['state']!='included' or not o['destination_record_ids']: raise ValueError('false success')
   missing=any(blobs[b]['state']!='included' for b in rec['content']['blob_ids'])
   if missing and o['status']=='imported': raise ValueError('missing media not accounted')
  elif o['destination_record_ids']: raise ValueError('failed outcome has destination')
  if o['status']=='transformed' and not o['transformation']: raise ValueError('undisclosed transformation')
  if o['status']!='transformed' and o['transformation'] is not None: raise ValueError('unexpected transformation')
 return True
if __name__=='__main__':
 vectors=json.loads((P/'vectors.json').read_text(encoding='utf-8'))
 for v in vectors:
  try: check(v['case']); accepted=True
  except (ValueError, ValidationError): accepted=False
  if accepted!=v['accept']: raise AssertionError(v['id'])
  print(('PASS '+v['id']))
 print(f'{len(vectors)} candidate vectors passed; no live provider/interoperability certification.')
