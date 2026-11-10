from support import *
import json
metadata=json.loads((R/'PORT_METADATA.json').read_text());bindings=json.loads((R/'BINDINGS.json').read_text())
# Remove irrelevant undefined-symbol matches introduced by the first reporter
# comparing literal zero with symbol value zero. No target data is changed.
for v in bindings.values():
    if isinstance(v,dict):
        for l in v.get('literals',[]):
            if l['value']=='0x0':l['symbol']=[]
(R/'BINDINGS.json').write_text(json.dumps(bindings,indent=2),encoding='utf-8')
out={}
for label,tag in [('old','04'),('new','03.02')]:
    e=load(label);syms=section_bytes(e,'.dynsym');names=section_bytes(e,'.dynstr');rel=section_bytes(e,'.rela.plt');got={}
    for off in range(0,len(rel),24):
        addr,info,addend=struct.unpack_from('<QQq',rel,off);no=struct.unpack_from('<I',syms,(info>>32)*24)[0];got[names[no:].split(b'\0',1)[0].decode()]=addr
    rows={}
    for fn,entry in metadata[tag]['entries'].items():
        if entry['lsda'] is None:continue
        addr=int(entry['lsda'],16);b=read(e,addr,160);assert b[0]==0xff
        typ=b[1];p=2;typebase=None
        if typ!=0xff:
            n,p=uleb(b,p);typebase=p+n;assert typ==0x9b
        csenc=b[p];p+=1;assert csenc==1
        n,p=uleb(b,p);end=p+n;calls=[]
        while p<end:
            start,p=uleb(b,p);length,p=uleb(b,p);landing,p=uleb(b,p);action,p=uleb(b,p)
            calls.append({'start':start,'length':length,'landing':landing,'action':action})
        assert p==end
        # The constructor's type table contains only null (catch-all) here.
        if typebase is not None:
            assert b[typebase-4:typebase]==bytes(4)
            size=typebase
        else:
            assert not any(x['action'] for x in calls)
            size=end
        rows[fn]={'address':hex(addr),'bytes':size,'hex':b[:size].hex(),'calls':calls,'type_encoding':typ,'catch_all_type_only':typebase is not None,'LPStart_omitted':True}
    out[label]={'personality_got':hex(got['__gxx_personality_v0']),'exception_tables':rows}
out['notes']=['ELF .data pointers must use section/program mappings; naive VA-minus-0x400000 is valid only for selected text/rodata, not all data. The exploratory command read wrong DSO/personality bytes; this output and mapped BINDINGS supersede it.','No runtime or binary mutation in this prerequisite.']
assert not (R/'EXCEPTIONS.json').exists()
(R/'EXCEPTIONS.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'exceptions':out,'binding_literals':{k:v['literals'] for k,v in bindings.items() if isinstance(v,dict)}}))
