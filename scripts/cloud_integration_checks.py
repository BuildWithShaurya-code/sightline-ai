#!/usr/bin/env python3
"""Opt-in integration check against configured private cloud services.
Creates only random-owner synthetic fixtures, never consumes an owner's queued job,
and removes its own remote records/objects in finally. Requires private model access.
Run with SIGHTLINE_RUN_CLOUD_CHECKS=1 and server variables set in a private shell.
"""
import os,sys,uuid,json,base64
from pathlib import Path
if os.environ.get('SIGHTLINE_RUN_CLOUD_CHECKS') != '1':
    raise SystemExit('Cloud checks are opt-in. Read docs/CLOUD_DEPLOYMENT.md first.')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import cv2,numpy as np,httpx,psycopg
from app.config import get_settings
from app.db.postgres import CloudDatabase
from app.core.identity import owner_id
from app.services.cloud_video import CloudVideoService
from app.services.cloud_storage import CloudStorage,hydrate_model
from app.services.inference_service import InferenceService
from app.services.video_worker import VideoWorker
from app.db.database import DatabaseManager
s=get_settings();db=DatabaseManager.get_instance();store=CloudStorage(s)
owner=str(uuid.uuid4());owner_id.set(owner);ids=[];keys=[]
video=Path('/tmp/sightline-synthetic-cloud-test.avi')
writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),5,(160,120))
for i in range(10): writer.write(np.full((120,160,3),i*4,dtype=np.uint8))
writer.release()
try:
 service=CloudVideoService(); ticket=service.begin(owner,video.name,video.stat().st_size);ids.append(ticket['sourceId'])
 source=db.get_source(ids[0]);keys.append(('source-videos',source['storage_key']))
 r=httpx.put(ticket['uploadUrl'],content=video.read_bytes(),headers={'content-type':'video/x-msvideo','x-upsert':'false'},timeout=30);r.raise_for_status()
 assert service.complete(owner,ids[0])['sourceId']==ids[0]
 assert service.complete(owner,ids[0])['sourceId']==ids[0]
 job=db.create_analysis_job(owner,ids[0],['mask'],idempotency_key='cloud_pipeline_'+owner)
 hydrate_model(s);inference=InferenceService.get_instance();inference.load_and_verify_model()
 worker_settings=s.model_copy(update={'cloud_worker':True});worker_db=CloudDatabase(worker_settings)
 try:
  worker=VideoWorker(worker_id='cloud_test_'+uuid.uuid4().hex,db=worker_db,inference_service=inference)
  claimed=worker_db.claim_next_queued_job(worker.worker_id,job_id=job['id'])
  if claimed:
   assert claimed['id']==job['id']
   result=worker.process_job_sync(claimed['id'])
   assert result['status']=='completed'
  else:
   # A production daemon may claim this exact fixture first. Poll only our own job.
   import time
   deadline=time.monotonic()+120
   while db.get_job(job['id'])['status'] in ('queued','processing') and time.monotonic()<deadline:
    time.sleep(1)
  assert db.get_job(job['id'])['status']=='completed'
  # A deliberately synthetic record checks evidence persistence, separate from model predictions.
  sid='test_evidence_'+uuid.uuid4().hex;ids.append(sid);jid='job_'+uuid.uuid4().hex;inc='INC-TEST-'+uuid.uuid4().hex;ev='ev_'+uuid.uuid4().hex
  jpeg=cv2.imencode('.jpg',np.zeros((120,160,3),dtype=np.uint8))[1].tobytes()
  evidence=[{'id':ev,'source_id':sid,'user_id':owner,'storage_key':'unused-local-cache','video_offset_seconds':0,'media_dimensions':{'width':160,'height':120},'image_data_url':'data:image/jpeg;base64,'+base64.b64encode(jpeg).decode()}]
  db.finalize_analysis_results(jid,{'id':inc,'source_id':sid,'user_id':owner,'title':'Synthetic integration fixture','reason':'Test fixture'},evidence,[],new_source={'id':sid,'user_id':owner,'original_filename':'synthetic.jpg','storage_bucket':'evidence-frames','storage_key':'pending'},new_job={'id':jid,'source_id':sid,'user_id':owner,'targets':['mask'],'status':'processing'})
  keys.append(('evidence-frames',evidence[0]['storage_key']))
  saved=db.get_incident(inc,owner);url=saved['frames'][0]['imageDataUrl']
  assert url.startswith(s.supabase_url) and httpx.get(url,timeout=20).status_code==200
  stored=db.get_connection().execute('SELECT image_data_url FROM evidence WHERE id=?',(ev,)).fetchone()
  assert stored['image_data_url'] is None
  owner_id.set(str(uuid.uuid4()));assert db.get_incident(inc) is None
  owner_id.set(owner)
  print(json.dumps({'signed_direct_upload':'passed','video_validation_and_edit_retry':'passed','durable_claim_and_real_model_analysis':'passed','private_evidence_storage':'passed','fresh_signed_evidence':'passed','no_base64_in_database':'passed','evidence_account_separation':'passed'}),flush=True)
 finally: worker_db.close_all();inference.cleanup()
finally:
 db.close_all()
 with psycopg.connect(s.cloud_database_url.get_secret_value(),sslmode='verify-full',sslrootcert=str(s.cloud_database_ca),prepare_threshold=None,connect_timeout=10) as conn:
  for sid in ids:
   conn.execute('DELETE FROM sightline.sources WHERE id=%s AND user_id=%s',(sid,owner))
 for bucket,key in keys: store.bucket(bucket).remove([key])
 video.unlink(missing_ok=True)
