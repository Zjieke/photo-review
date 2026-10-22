"""Resumable local analysis of all still images in the Photos library."""
import collections, concurrent.futures, json, os, sqlite3, time
from pathlib import Path
import osxphotos

ROOT=Path(__file__).resolve().parent; OUT=ROOT.parent/'outputs'

def analyze(row):
    import objc, Vision, Quartz
    from Foundation import NSURL
    with objc.autorelease_pool():
        result=dict(row,ocr='',visual=[],analysis_status='unavailable',thumbnail='')
        if not row['preview']:return result
        try:
            source=Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(row['preview']),None)
            image=Quartz.CGImageSourceCreateThumbnailAtIndex(source,0,{
                Quartz.kCGImageSourceCreateThumbnailFromImageAlways:True,
                Quartz.kCGImageSourceThumbnailMaxPixelSize:1400,
                Quartz.kCGImageSourceCreateThumbnailWithTransform:True})
            if image is None:raise ValueError('无法解码图像')
            dest=OUT/'previews'/f"{row['uuid']}.jpg"
            target=Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(str(dest)), 'public.jpeg',1,None)
            Quartz.CGImageDestinationAddImage(target,image,{Quartz.kCGImageDestinationLossyCompressionQuality:0.80})
            if not Quartz.CGImageDestinationFinalize(target):raise ValueError('无法写入预览')
            result['thumbnail']='previews/'+dest.name
            request=Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setRecognitionLanguages_(['zh-Hans','en-US'])
            request.setUsesLanguageCorrection_(True)
            classification=Vision.VNClassifyImageRequest.alloc().init()
            handler=Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image,None)
            ok,err=handler.performRequests_error_([request,classification],None)
            if not ok:raise ValueError(str(err))
            result['ocr']='\n'.join(str(x.topCandidates_(1)[0].string()) for x in request.results() or [])
            result['visual']=[{'label':str(x.identifier()),'confidence':round(float(x.confidence()),4)} for x in (classification.results() or [])[:8]]
            result['analysis_status']='complete'
        except Exception as e:result.update(analysis_status='failed',error=str(e))
        return result

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'previews').mkdir(exist_ok=True)
    db=osxphotos.PhotosDB();photos=db.photos()
    old=json.loads((OUT/'full_results.json').read_text()) if (OUT/'full_results.json').exists() else []
    numbers={r['uuid']:r['number'] for r in old};next_number=max(numbers.values(),default=0)+1
    rows=[];videos=[]
    for p in sorted(photos,key=lambda p:p.date):
        base=dict(uuid=p.uuid,filename=p.original_filename,date=p.date.isoformat(),favorite=p.favorite,hidden=p.hidden,screenshot=p.screenshot)
        if p.ismovie:videos.append(base);continue
        original=p.path
        if original and not Path(original).is_file():original=None
        preview=original or next((x for x in p.path_derivatives if Path(x).is_file()),None)
        if p.uuid not in numbers:numbers[p.uuid]=next_number;next_number+=1
        rows.append(base|dict(number=numbers[p.uuid],original=original,preview=preview,source='original' if original else 'preview' if preview else 'unavailable'))
    (OUT/'full_inventory.json').write_text(json.dumps(rows,ensure_ascii=False))
    (OUT/'videos_not_analyzed.json').write_text(json.dumps(videos,ensure_ascii=False))
    conn=sqlite3.connect(OUT/'analysis_cache.sqlite3')
    conn.execute('CREATE TABLE IF NOT EXISTS results (uuid TEXT PRIMARY KEY, fingerprint TEXT, data TEXT)')
    def fingerprint(r):
        if not r['preview']:return 'missing'
        s=Path(r['preview']).stat();return f"v1:{r['preview']}:{s.st_size}:{s.st_mtime_ns}"
    existing={u:(f,json.loads(d)) for u,f,d in conn.execute('SELECT uuid,fingerprint,data FROM results')}
    pending=[];results={}
    for r in rows:
        f=fingerprint(r)
        if r['uuid'] in existing and (existing[r['uuid']][0]==f or (existing[r['uuid']][1].get('source')=='preview' and r['source']=='original')) and existing[r['uuid']][1]['analysis_status']=='complete':
            results[r['uuid']]=existing[r['uuid']][1]|{k:r[k] for k in ('number','favorite','hidden','date','screenshot','filename')}
        else:pending.append(r)
    start=time.time()
    def progress():
        summary=dict(library_items=len(photos),photos=len(rows),videos=len(videos),completed=sum(x['analysis_status']=='complete' for x in results.values()),failed=sum(x['analysis_status']=='failed' for x in results.values()),unavailable=sum(x['analysis_status']=='unavailable' for x in results.values()),processed=len(results),pending=len(rows)-len(results),local_originals=sum(r['source']=='original' for r in rows),preview_only=sum(r['source']=='preview' for r in rows),hidden=sum(r['hidden'] for r in rows),elapsed_seconds=round(time.time()-start))
        tmp=OUT/'analysis_progress.tmp';tmp.write_text(json.dumps(summary,ensure_ascii=False,indent=2));tmp.replace(OUT/'analysis_progress.json')
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    progress()
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for row,res in zip(pending,pool.map(analyze,pending,chunksize=5)):
            results[row['uuid']]=res
            conn.execute('INSERT OR REPLACE INTO results VALUES (?,?,?)',(row['uuid'],fingerprint(row),json.dumps(res,ensure_ascii=False)))
            if len(results)%50==0:conn.commit();progress()
    conn.commit();conn.close();progress()
    temp=OUT/'full_results.tmp';temp.write_text(json.dumps([results[r['uuid']] for r in rows],ensure_ascii=False));temp.replace(OUT/'full_results.json')

if __name__=='__main__':main()
