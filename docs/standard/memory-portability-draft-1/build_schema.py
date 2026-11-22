import json
from pathlib import Path
P=Path(__file__).parent
s={'type':'string','minLength':1}
timestamp={'type':'string','format':'date-time'}
n={'type':'integer','minimum':0,'maximum':9007199254740991}
def obj(**kw):
 return {'type':'object','additionalProperties':False,'properties':kw,'required':list(kw)}
def arr(x): return {'type':'array','items':x}
def enum(*x): return {'enum':list(x)}
def ref(x): return {'$ref':'#/$defs/'+x}
D={}
D['Context']=obj(game_id={'type':['string','null']},run_id={'type':['string','null']},save_id={'type':['string','null']})
D['Metadata']=obj(kind=enum('conversation','scene','summary','preference','other'),created_at=timestamp,updated_at=timestamp,context=ref('Context'),provenance=obj(source_kind=enum('player','game','agent','import','unknown'),source_id={'type':['string','null']},player_edited={'type':'boolean'},derived_from=arr(s)),associations=arr(s),access_constraints=arr(s),retention_constraints=arr(s),confidentiality_style={'type':['string','null']},extensions={'type':'object'})
D['Content']=obj(media_type=s,text={'type':['string','null']},blob_ids=arr(s))
D['Record']={'oneOf':[obj(record_id=s,revision=s,state=enum('included'),metadata=ref('Metadata'),content=ref('Content')),obj(record_id=s,revision=s,state=enum('restricted','unavailable'),reason_code=s,explanation=s)]}
D['Blob']={'oneOf':[obj(blob_id=s,state=enum('included'),path={'type':'string','pattern':'^blobs/[A-Za-z0-9_-]+$'},media_type=s,byte_length=n,sha256={'type':'string','pattern':'^[0-9a-f]{64}$'}),obj(blob_id=s,state=enum('restricted','unavailable'),reason_code=s,explanation=s)]}
D['Export']=obj(profile=enum('memory-portability-draft-1'),export_id=s,source_provider=s,subject_id=s,companion_id=s,snapshot_id=s,exported_at=timestamp,retained_record_count=n,records=arr(ref('Record')),blobs=arr(ref('Blob')))
D['Selection']=obj(profile=enum('memory-portability-draft-1'),selection_id=s,export_sha256={'type':'string','pattern':'^[0-9a-f]{64}$'},source_subject=s,destination_provider=s,destination_subject=s,selected_record_ids=arr(s))
D['Outcome']=obj(record_id=s,status=enum('imported','transformed','rejected','unresolved'),reason_code=s,explanation=s,destination_record_ids=arr(s),transformation={'type':['string','null']})
D['Receipt']=obj(profile=enum('memory-portability-draft-1'),selection_id=s,export_sha256={'type':'string','pattern':'^[0-9a-f]{64}$'},destination_provider=s,destination_subject=s,outcomes=arr(ref('Outcome')))
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:g2a:candidate:memory-portability-draft-1','oneOf':[ref('Export'),ref('Selection'),ref('Receipt')],'$defs':D}
(P/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
