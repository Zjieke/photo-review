"""Read-only activity inventory. No media downloads, changes, or model inference."""
import json,time
from pathlib import Path
import osxphotos
from PIL import Image,ImageOps
from app_paths import STATE_DIR as ROOT, OUT, ensure_data_dirs

def main():
 ensure_data_dirs(OUT.parent)
 existing={r['uuid']:r for r in json.loads((OUT/'full_results.json').read_text())} if (OUT/'full_results.json').exists() else {}
 items=[];media={};thumbs=OUT/'previews';thumbs.mkdir(exist_ok=True)
 for p in sorted(osxphotos.PhotosDB().photos(),key=lambda p:p.date):
  if p.hidden:continue
  isvideo=bool(p.ismovie);original=p.path
  if original and not Path(original).is_file():original=None
  thumbnail=existing.get(p.uuid,{}).get('thumbnail','')
  if not thumbnail:
   preview=next((x for x in p.path_derivatives if Path(x).is_file() and Path(x).suffix.lower() in ('.jpg','.jpeg','.png')),None)
   if preview:
    try:
     with Image.open(preview) as im:
      im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((960,960));im.save(thumbs/f'{p.uuid}.jpg',quality=80)
     thumbnail=f'previews/{p.uuid}.jpg'
    except Exception:pass
  size=p.original_filesize
  try:size=int(size) if size is not None and int(size)>0 else None
  except (ValueError,TypeError):size=None
  local_size=Path(original).stat().st_size if original else 0
  items.append(dict(uuid=p.uuid,filename=p.original_filename,date=p.date.isoformat(),day=p.date.date().isoformat(),kind='video' if isvideo else 'photo',screenshot=bool(p.screenshot),favorite=bool(p.favorite),hidden=bool(p.hidden),deletable=not (p.favorite or p.hidden),bytes=size,local_bytes=local_size,thumbnail=thumbnail,available=bool(original)))
  if original:media[p.uuid]={'path':original,'kind':'video' if isvideo else 'photo'}
 payload=dict(updated_at=time.time(),size_basis='原始照片及独立视频的文件大小；不含实况附带视频、编辑副本和缓存。不是预计可释放的磁盘空间。',items=items)
 for path,obj in [(ROOT/'activity_inventory.json',payload),(ROOT/'activity_media_paths.json',media)]:
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False));tmp.replace(path)
 print(json.dumps(dict(items=len(items),videos=sum(r['kind']=='video' for r in items),bytes=sum(r['bytes'] or 0 for r in items),size_unknown=sum(r['bytes'] is None for r in items)),ensure_ascii=False))

if __name__=='__main__':main()
