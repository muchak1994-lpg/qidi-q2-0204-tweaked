"""Shared, non-executing ELF readers for this offline port only."""
from pathlib import Path
import ast, bisect, hashlib, struct
R=Path(__file__).resolve().parent;W=R.parent
tree=ast.parse((W/'QIDI_Q2_FIRMWARE_0302_REVIEW_20261028/client_static.py').read_text(encoding='utf-8'))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Elf'],type_ignores=[]),'<cached reader>','exec'))
PATHS={
    'old':('QIDI_Q2_CLIENT_VERSION_ENTRY_20261026/qidiclient.VERSION_ENTRY_PRIVATE_DO_NOT_INSTALL','2b0ef3b449b8d2e319f3c972325681f116ba1a479c688993752f1b40cb853e6a'),
    'new':('QIDI_Q2_FIRMWARE_0302_REVIEW_20261028/changed-files/home/qidi/QIDI_Client/bin/qidiclient','c222bb9c77df6fe714e974f915834841be96c291bb75d44cd6f4d371e174f423'),
}
def load(label):
    path,digest=PATHS[label];e=Elf(W/path)
    assert hashlib.sha256(e.data).hexdigest()==digest
    return e
def read(e,va,n):
    off=e.off(va);return e.data[off:off+n]
def qword(e,va):return struct.unpack('<Q',read(e,va,8))[0]
def imports(e):
    ns=e.sections['.dynstr'];names=e.data[ns[4]:ns[4]+ns[5]];sym=e.sections['.dynsym'];symbols=[]
    for off in range(sym[4],sym[4]+sym[5],sym[9]):
        no=struct.unpack_from('<I',e.data,off)[0];symbols.append(names[no:].split(b'\0',1)[0].decode())
    rel=e.sections['.rela.plt'];plt=e.sections['.plt'];im={}
    for i,off in enumerate(range(rel[4],rel[4]+rel[5],rel[9])):
        _,info,_=struct.unpack_from('<QQq',e.data,off);im[plt[3]+32+i*16]=symbols[info>>32]
    return im
def uleb(b,i):
    v=0;s=0
    while True:
        w=b[i];i+=1;v|=(w&127)<<s
        if not w&128:return v,i
        s+=7;assert s<64
def encoded_uleb(n):
    b=bytearray()
    while n>=128:b.append((n&127)|128);n>>=7
    b.append(n);return b
def section_bytes(e,name):
    s=e.sections[name];return e.data[s[4]:s[4]+s[5]]
def dynamics(e):
    s=e.sections['.dynamic'];return [(s[3]+i,)+struct.unpack_from('<qQ',e.data,s[4]+i) for i in range(0,s[5],16)]
