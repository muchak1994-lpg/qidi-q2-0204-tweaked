"""New bounded prerequisite: native queue CIE/FDE/LSDA and import binding."""
from pathlib import Path
import ast,struct,json,hashlib,sys
R=Path(__file__).resolve().parent;W=R.parent
tree=ast.parse((W/'QIDI_Q2_FIRMWARE_0302_REVIEW_20261028/client_static.py').read_text(encoding='utf-8'))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Elf'],type_ignores=[]),'<reader>','exec'))
def uleb(b,i):
    v=0;s=0
    while True:
        w=b[i];i+=1;v|=(w&127)<<s
        if not w&128:return v,i
        s+=7;assert s<64
def ptr(b,p):return p+4+struct.unpack_from('<i',b,p+4)[0]
def imports(e):
    ns=e.sections['.dynstr'];names=e.data[ns[4]:ns[4]+ns[5]];sym=e.sections['.dynsym'];symbols=[]
    for off in range(sym[4],sym[4]+sym[5],sym[9]):
        no=struct.unpack_from('<I',e.data,off)[0];symbols.append(names[no:].split(b'\0',1)[0].decode())
    rel=e.sections['.rela.plt'];plt=e.sections['.plt'];im={}
    for i,off in enumerate(range(rel[4],rel[4]+rel[5],rel[9])):
        _,info,_=struct.unpack_from('<QQq',e.data,off);im[plt[3]+32+i*16]=symbols[info>>32]
    got={};rel=e.sections['.rela.dyn']
    for off in range(rel[4],rel[4]+rel[5],rel[9]):
        addr,info,addend=struct.unpack_from('<QQq',e.data,off)
        got[addr]={'symbol':symbols[info>>32],'type':info&0xffffffff,'addend':addend}
    return im,got
out={}
for label,path,starts in [('04','QIDI_Q2_CLIENT_VERSION_ENTRY_20261026/qidiclient.VERSION_ENTRY_PRIVATE_DO_NOT_INSTALL',[0x722330]),('03.02','QIDI_Q2_FIRMWARE_0302_REVIEW_20261028/changed-files/home/qidi/QIDI_Client/bin/qidiclient',[0x459060,0x5cd320,0x5cd390,0x5cd500,0x5cd680])]:
    e=Elf(W/path);im,got=imports(e);s=e.sections['.eh_frame_hdr'];b=e.data[s[4]:s[4]+s[5]]
    rows={s[3]+a:s[3]+f for a,f in struct.iter_unpack('<ii',b[12:])};entries={}
    for va in starts:
        fde=rows[va];off=e.off(fde);length=struct.unpack_from('<I',e.data,off)[0];raw=e.data[off:off+4+length]
        cie=fde+4-struct.unpack_from('<I',raw,4)[0];co=e.off(cie);cl=struct.unpack_from('<I',e.data,co)[0];cr=e.data[co:co+cl+4]
        # Actual compiler's zPLR/zR layouts, parsed instead of assuming one.
        z=cr.index(0,9);aug=cr[9:z].decode();p=z+1;code,p=uleb(cr,p);data_encoded=cr[p];p+=1;ret,p=uleb(cr,p)
        az,p=uleb(cr,p);ap=p;personality=None;lsda_encoding=None;fde_encoding=None
        for c in aug[1:]:
            if c=='P':
                enc=cr[p];p+=1;assert enc==0x9b
                personality=cie+p+struct.unpack_from('<i',cr,p)[0];p+=4
            elif c=='L':lsda_encoding=cr[p];p+=1
            elif c=='R':fde_encoding=cr[p];p+=1
            else:raise AssertionError(aug)
        assert p==ap+az and fde_encoding==0x1b
        auglen,ap=uleb(raw,16);lsda=None
        if lsda_encoding is not None:
            assert lsda_encoding==0x1b and auglen==4
            lsda=fde+ap+struct.unpack_from('<i',raw,ap)[0]
        entries[hex(va)]={'fde':hex(fde),'fde_hex':raw.hex(),'cie':hex(cie),'cie_hex':cr.hex(),'augmentation':aug,'personality_got':hex(personality) if personality else None,'personality_binding':got.get(personality),'lsda':hex(lsda) if lsda else None,'lsda_first96_hex':e.data[e.off(lsda):e.off(lsda)+96].hex() if lsda else None,'range':struct.unpack_from('<I',raw,12)[0]}
    out[label]={'entries':entries,'imports':{hex(k):v for k,v in im.items()},'got':{hex(k):v for k,v in got.items() if v['symbol'] in ('__gxx_personality_v0','__pthread_key_create','pthread_cancel','__pthread_key_create') or k in (0x9d9ba8,0x8e3048)},'init_array_entries':e.sections['.init_array'][5]//8}
assert not (R/'PORT_METADATA.json').exists()
(R/'PORT_METADATA.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({k:{'entries':v['entries'],'got':v['got'],'init_array_entries':v['init_array_entries']} for k,v in out.items()}))
