"""Real HTTPS/Playwright CLI journey on disposable staff media fixtures."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import subprocess
import uuid

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from face_moment.infrastructure.object_store import PrivateObjectStore
from face_moment.infrastructure.settings import Settings
from face_moment.inventory.photo_persistence import Photo
from face_moment.platform.staff_datetime import STAFF_TIMEZONE
from face_moment.processing.initial_pending import PhotoPipelineState
from face_moment.serving_control.ingest_target import Spa
from tests.promo.test_public_edge_routes import live_edge, _LiveEdge, _request

ARTIFACTS=Path('.tasks/TASK-119-T3-FT-012-W3')


def test_staff_media_cli_through_real_https(live_edge: _LiveEdge, tmp_path: Path) -> None:
    edge=live_edge
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    store=PrivateObjectStore(Settings.from_env())
    keys=[]
    picture=Image.new('RGB',(640,400),'#376b84')
    draw=ImageDraw.Draw(picture)
    draw.rectangle((0,260,640,400),fill='#84b6bf')
    draw.ellipse((250,60,390,200),fill='#d9b494')
    draw.rounded_rectangle((200,185,440,390),radius=45,fill='#426454')
    original=BytesIO(); picture.save(original,'JPEG')
    small=BytesIO(); picture.resize((320,200)).save(small,'JPEG')
    session_name='media-'+uuid.uuid4().hex[:12]
    transcript=[]
    def cli(*arguments: str) -> str:
        result=subprocess.run(['playwright','cli',f'-s={session_name}',*arguments],capture_output=True,text=True,timeout=90)
        transcript.append(result.stdout+result.stderr)
        assert result.returncode==0 and '### Error' not in result.stdout, result.stdout+result.stderr
        return result.stdout
    try:
        with Session(edge.engine) as session:
            spa=session.get(Spa,edge.spa_id); assert spa
            spa.name='Аква · Тестовая площадка'
            photos=list(session.scalars(select(Photo).where(Photo.spa_id==edge.spa_id).order_by(Photo.id)))
            assert len(photos)==4
            photo_ids=[str(photo.id) for photo in photos]
            for index,photo in enumerate(photos):
                photo.width=640;photo.height=400;photo.original_byte_size=len(original.getvalue())
                state=session.get(PhotoPipelineState,(photo.id,photo.admission_pipeline_revision_id));assert state
                store.put(key=photo.original_object_key,body=original.getvalue());keys.append(photo.original_object_key)
                if index==2:
                    state.status='pending';state.thumbnail_object_key=None
                elif index==3:
                    state.status='no_faces';state.thumbnail_object_key=None
                else:
                    assert state.thumbnail_object_key
                    store.put(key=state.thumbnail_object_key,body=small.getvalue());keys.append(state.thumbnail_object_key)
            session.commit()
        page_path=f'/staff/venue-media?spa_id={edge.spa_id}'
        assert _request(edge.base_url,page_path).status==401
        for role in ('operator','developer','photographer'):
            response=_request(edge.base_url,page_path,cookies=edge.cookies[role])
            assert response.status==200 and b'data-staff-media' in response.body
        # Only fixture cookies enter this temporary file, never logs/artifacts.
        auth=tmp_path/'browser-auth.json'
        auth.write_text(json.dumps({'cookies':[{'name':name,'value':value,'domain':'localhost','path':'/','secure':True,'httpOnly':name=='fm_staff_session','sameSite':'Lax'} for name,value in edge.cookies['developer'].items()],'origins':[]}))
        executable=subprocess.check_output(['node','-e','const {chromium}=require("@playwright/test"); process.stdout.write(chromium.executablePath())'],text=True)
        config=tmp_path/'browser-config.json'
        config.write_text(json.dumps({'browser':{'browserName':'chromium','launchOptions':{'executablePath':executable,'headless':True},'contextOptions':{'ignoreHTTPSErrors':True,'storageState':str(auth),'viewport':{'width':1360,'height':1000}}}}))
        cli('open',edge.base_url+'/staff/photo-inventory','--config='+str(config))
        today=datetime.now(STAFF_TIMEZONE).strftime('%d.%m.%Y')
        code='''async page => {
const check = (ok, message) => { if (!ok) throw new Error(message); };
await page.getByRole('link', {name:'Медиа ↗', exact:true}).click();
await page.locator('#media-rows tr').first().waitFor();
check(await page.locator('#media-rows tr').count() === 3, 'ready/pending visible and no_faces absent');
check(await page.locator('#media-status').textContent() === 'Фотографий: 3', 'count');
check(await page.locator('[data-photo-id="NOFACE"]').count() === 0, 'no_faces hidden');
await page.locator('[data-photo-id="READY"] img').evaluate(img => img.decode());
check(await page.locator('[data-photo-id="READY"] img').evaluate(img => img.naturalWidth) === 320, 'thumbnail dimensions');
await page.screenshot({path:'DESKTOP',fullPage:true});
await page.locator('#media-date-from').fill('01.01.2000');
await page.locator('#media-date-to').fill('01.01.2000');
await page.getByRole('button',{name:'Показать фотографии'}).click();
await page.getByText('За выбранные даты фотографий нет.',{exact:true}).waitFor();
await page.locator('#media-date-from').fill('TODAY');
await page.locator('#media-date-to').fill('TODAY');
await page.getByRole('button',{name:'Показать фотографии'}).click();
await page.locator('#media-rows tr').first().waitFor();
const [original] = await Promise.all([page.waitForEvent('popup'),page.locator('[data-photo-id="READY"] a').click()]);
await original.waitForLoadState();
check(await original.locator('img').evaluate(img => img.naturalWidth) === 640, 'native original dimensions');
check(original.url().endsWith('/original'), 'private original route');
await original.close();
return 'MEDIA_INITIAL_PASS';
}'''.replace('NOFACE',photo_ids[3]).replace('READY',photo_ids[0]).replace('TODAY',today).replace('DESKTOP',str(ARTIFACTS/'media-desktop.png')).replace('MOBILE',str(ARTIFACTS/'media-mobile.png'))
        script=tmp_path/'browser-flow.js';script.write_text(code)
        result=cli('run-code','--filename='+str(script))
        assert '### Result' in result and 'MEDIA_INITIAL_PASS' in result
        row_selector=f'[data-photo-id="{photo_ids[0]}"]'
        cli('run-code', "async page => { await page.route('**/api/inventory/photos/*/visibility',route => route.fulfill({status:403,body:'{}'})); }")
        cli('click',row_selector+' button')
        cli('dialog-accept')
        cli('run-code', f"async page => {{ await page.locator('#media-error').filter({{hasText:'Не удалось удалить'}}).waitFor(); if (await page.locator({json.dumps(row_selector)}).count() !== 1) throw new Error('failed deletion removed row'); await page.unroute('**/api/inventory/photos/*/visibility'); }}")
        cli('click',row_selector+' button')
        cli('dialog-accept')
        final_script = f'''async page => {{
await page.locator({json.dumps(row_selector)}).waitFor({{state:'detached'}});
if (await page.locator('#media-rows tr').count() !== 2) throw new Error('successful deletion count');
await page.setViewportSize({{width:390,height:844}});
await page.screenshot({{path:{json.dumps(str(ARTIFACTS/'media-mobile.png'))},fullPage:true}});
if (!await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)) throw new Error('page overflow');
await page.route('**/api/inventory/venue-media?*',route => route.fulfill({{status:503,body:'{{}}'}}));
await page.getByRole('button',{{name:'Показать фотографии'}}).click();
await page.locator('#media-error').filter({{hasText:'Не удалось загрузить'}}).waitFor();
if (await page.locator('#media-rows tr').count() !== 0) throw new Error('stale list on failure');
return 'MEDIA_UI_PASS';
}}'''
        final_result=cli('run-code',final_script)
        assert '### Result' in final_result and 'MEDIA_UI_PASS' in final_result
        with Session(edge.engine) as session:
            deleted=session.get(Photo,uuid.UUID(photo_ids[0]));assert deleted and not deleted.is_active
            assert store.read(key=deleted.original_object_key)==original.getvalue()
    finally:
        try: cli('close')
        finally:
            (ARTIFACTS/'playwright-cli.log').write_text('\n'.join(transcript))
            for key in keys: store.delete(key=key)
