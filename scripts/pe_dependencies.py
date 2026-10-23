"""Inspect PE imports and exports without relying on the build machine DLL search path."""
import struct
from pathlib import Path
import re

def layout(b):
 pe=struct.unpack_from('<I',b,60)[0];n=struct.unpack_from('<H',b,pe+6)[0];size=struct.unpack_from('<H',b,pe+20)[0];opt=pe+24
 is64=struct.unpack_from('<H',b,opt)[0]==0x20b;dd=opt+(112 if is64 else 96);sections=[]
 for i in range(n):
  p=opt+size+i*40;vs,va,raw,off=struct.unpack_from('<IIII',b,p+8);sections.append((va,max(vs,raw),off))
 def pos(r):
  for va,sz,off in sections:
   if va<=r<va+sz:return off+r-va
  return r
 def string(r):
  p=pos(r);return b[p:b.index(b'\0',p)].decode()
 return dd,pos,string,is64

def imports(b):
 dd,pos,string,is64=layout(b);r=struct.unpack_from('<I',b,dd+8)[0];out={}
 if not r:return out
 p=pos(r)
 while any(b[p:p+20]):
  oft,ts,fc,name,ft=struct.unpack_from('<IIIII',b,p);dll=string(name).lower();entries=[];t=pos(oft or ft);step=8 if is64 else 4
  while True:
   v=struct.unpack_from('<Q' if is64 else '<I',b,t)[0]
   if not v:break
   if not v & (1<<(step*8-1)):entries.append(string(v+2))
   t+=step
  out[dll]=entries;p+=20
 return out

def exports(b):
 dd,pos,string,_=layout(b);r=struct.unpack_from('<I',b,dd)[0]
 if not r:return set()
 p=pos(r);count=struct.unpack_from('<I',b,p+24)[0];names=pos(struct.unpack_from('<I',b,p+32)[0])
 return {string(struct.unpack_from('<I',b,names+i*4)[0]) for i in range(count)}


def verify_msvc(app):
    """Every MSVC import must resolve app-locally, including imported symbols."""
    app = Path(app)
    for folder in (app / 'engine', app / 'runtime'):
        dlls = {file.name.lower(): exports(file.read_bytes()) for file in folder.glob('*.dll')
                if re.fullmatch(r'(?:msvcp|vcruntime|concrt)[a-z0-9_]+\.dll', file.name.lower())}
        for file in folder.rglob('*'):
            if not file.is_file() or file.suffix.lower() not in ('.exe', '.dll', '.pyd'):
                continue
            for name, symbols in imports(file.read_bytes()).items():
                if not re.fullmatch(r'(?:msvcp|vcruntime|concrt)[a-z0-9_]+\.dll', name):
                    continue
                if name not in dlls or not set(symbols) <= dlls[name]:
                    raise RuntimeError('Missing app-local MSVC DLL or symbol: ' + file.name + ' -> ' + name)
