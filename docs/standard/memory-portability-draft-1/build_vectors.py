import copy,hashlib,json
from pathlib import Path
P=Path(__file__).parent
meta={'kind':'conversation','created_at':'2026-11-13T00:00:00Z','updated_at':'2026-11-13T00:00:00Z','context':{'game_id':'game-a','run_id':'run-1','save_id':None},'provenance':{'source_kind':'player','source_id':'speaker-1','player_edited':False,'derived_from':[]},'associations':[],'access_constraints':[],'retention_constraints':[],'confidentiality_style':'Prefer private conversation; not a hard migration prohibition.','extensions':{}}
e={'profile':'memory-portability-draft-1','export_id':'exp-1','source_provider':'provider-a','subject_id':'player-a','companion_id':'companion-1','snapshot_id':'snapshot-1','exported_at':'2026-11-13T00:00:00Z','retained_record_count':2,'records':[{'record_id':'r1','revision':'1','state':'included','metadata':meta,'content':{'media_type':'text/plain','text':'We completed game A together.','blob_ids':[]}},{'record_id':'r2','revision':'1','state':'restricted','reason_code':'disclosure_not_authorized','explanation':'Inventory stub only; content cannot be exported to this recipient.'}],'blobs':[]}
s={'profile':e['profile'],'selection_id':'sel-1','export_sha256':'','source_subject':'player-a','destination_provider':'provider-b','destination_subject':'player-b','selected_record_ids':['r1','r2']}
r={'profile':e['profile'],'selection_id':'sel-1','export_sha256':'','destination_provider':'provider-b','destination_subject':'player-b','outcomes':[{'record_id':'r1','status':'imported','reason_code':'ok','explanation':'Retained with metadata.','destination_record_ids':['dest-1'],'transformation':None},{'record_id':'r2','status':'rejected','reason_code':'source_restricted','explanation':'No source content available.','destination_record_ids':[],'transformation':None}]}
base={'export':e,'selection':s,'receipt':r,'blob_hex':{}}
v=[]
def add(name,accept,mutate=lambda c:None,rehash=True):
 c=copy.deepcopy(base); mutate(c)
 digest=hashlib.sha256(json.dumps(c['export'],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 c['selection']['export_sha256']=digest;c['receipt']['export_sha256']=digest
 if not rehash:c['receipt']['export_sha256']='0'*64
 v.append({'id':name,'accept':accept,'case':c})
add('complete-inventory-with-explicit-restriction',True)
add('soft-confidentiality-does-not-forbid-export',True)
add('inventory-silent-omission',False,lambda c:c['export']['records'].pop())
add('duplicate-record-id',False,lambda c:c['export']['records'][1].update(record_id='r1'))
add('wrong-destination',False,lambda c:c['receipt'].update(destination_provider='other'))
add('missing-outcome',False,lambda c:c['receipt']['outcomes'].pop())
add('unselected-outcome',False,lambda c:c['selection'].update(selected_record_ids=['r1']))
add('false-restricted-success',False,lambda c:c['receipt']['outcomes'][1].update(status='imported',destination_record_ids=['bad']))
add('integrity-mismatch',False,rehash=False)
add('undeclared-blob',False,lambda c:c['export']['records'][0]['content'].update(blob_ids=['b1']))
def blob(c):
 c['export']['records'][0]['content']['blob_ids']=['b1']
 c['export']['blobs']=[{'blob_id':'b1','state':'included','path':'blobs/b1','media_type':'audio/ogg','byte_length':3,'sha256':hashlib.sha256(b'abc').hexdigest()}]
 c['blob_hex']={'blobs/b1':b'abc'.hex()}
add('media-byte-integrity',True,blob)
def badblob(c):blob(c);c['blob_hex']['blobs/b1']='00'
add('corrupt-media',False,badblob)
def missing(c):
 blob(c);c['export']['blobs'][0]={'blob_id':'b1','state':'unavailable','reason_code':'lost','explanation':'Media unavailable at export.'};c['blob_hex']={}
add('missing-media-not-full-success',False,missing)
def transformed(c):
 missing(c);c['receipt']['outcomes'][0].update(status='transformed',transformation='Text imported without missing audio; metadata preserved.')
add('missing-media-truthful-partial-import',True,transformed)
add('transformation-not-described',False,lambda c:c['receipt']['outcomes'][0].update(status='transformed'))
add('unknown-top-level-field',False,lambda c:c['selection'].update(automatic_consent=True))
add('invalid-timestamp',False,lambda c:c['export'].update(exported_at='yesterday'))
add('unknown-selected-id',False,lambda c:c['selection'].update(selected_record_ids=['r404']))
add('duplicate-selected-id',False,lambda c:c['selection'].update(selected_record_ids=['r1','r1']))
def empty(c):
 c['export'].update(records=[],retained_record_count=0)
 c['selection']['selected_record_ids']=[]
 c['receipt']['outcomes']=[]
add('empty-retained-inventory',True,empty)
(P/'vectors.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
