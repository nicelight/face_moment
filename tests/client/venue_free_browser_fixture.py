"""Native HTTPS staff app with disposable PostgreSQL and ephemeral TLS identity."""
import json
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone
import uvicorn
from sqlalchemy.orm import Session
from face_moment.entrypoints.backend import create_app
from face_moment.platform.auth.principals import StaffRole, provision_staff_user
from face_moment.processing import PipelineCode, PipelineRevisionRepository
from face_moment.serving_control.ingest_target import IngestTargetRepository
from tests.pipeline_compatibility import PIPELINE_COMPATIBILITY
from tests.disposable_postgresql import disposable_postgresql_engine

with disposable_postgresql_engine('task131_browser') as engine, tempfile.TemporaryDirectory() as temporary:
    with Session(engine) as session:
        revision = PipelineRevisionRepository(session).publish_eligible(pipeline_code=PipelineCode.OPENCV_SFACE,
            validated_at=datetime.now(timezone.utc), **PIPELINE_COMPATIBILITY)
        IngestTargetRepository(session).configure_spa(name='Existing paid', timezone='UTC',serving_pipeline_revision_id=revision.id)
        session.commit()
        for role in (StaffRole.OPERATOR,StaffRole.DEVELOPER):
            provision_staff_user(session, username=f'free-{role.value}',password='browser-fixture-password',role=role)
    cert,key = str(Path(temporary)/'cert.pem'),str(Path(temporary)/'key.pem')
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',key,'-out',cert],check=True,capture_output=True)
    app=create_app();app.state.role_state['session_factory']=lambda:Session(engine)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen(128)
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',ssl_keyfile=key,ssl_certfile=cert))
        worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]});worker.start()
        print(json.dumps({'url':f'https://127.0.0.1:{listener.getsockname()[1]}'}),flush=True)
        try:sys.stdin.readline()
        finally:server.should_exit=True;worker.join(timeout=15)
print('DISPOSABLE_DB_CLEANED',flush=True)
