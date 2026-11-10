from support import *
import json
out={}
for label,addresses in [('old',[0x8e3048,0x5a10308]),('new',[0x9d9ba8,0x5b52a80,0x5b52420])]:
    e=load(label);im=imports(e);sym=section_bytes(e,'.dynsym');names=section_bytes(e,'.dynstr')
    syms=[]
    for off in range(0,len(sym),24):
        no,info,other,shndx,val,size=struct.unpack_from('<IBBHQQ',sym,off);syms.append({'name':names[no:].split(b'\0',1)[0].decode(),'value':hex(val),'info':info,'section':shndx})
    literals=[]
    for va in addresses:
        val=qword(e,va);sec=next(k for k,s in e.sections.items() if s[3]<=va<s[3]+s[5])
        literals.append({'address':hex(va),'section':sec,'value':hex(val),'plt':im.get(val),'symbol':[s for s in syms if val and int(s['value'],16)==val]})
    s=e.sections['.text'];cancel=0x7223c0 if label=='old' else 0x77b640
    out[label]={'literals':literals,'imports':{hex(k):v for k,v in im.items()},'dynamics':[{'at':hex(a),'tag':t,'value':hex(v)} for a,t,v in dynamics(e) if t in (12,25,27)],'init_array_hex':section_bytes(e,'.init_array').hex()}
# A raw address literal search is deliberately candidate evidence, not proof of
# absence of all computed indirect calls/cancellations.
old=load('old');out['old']['cancel_address_literal_offsets']=[]
needle=struct.pack('<Q',0x7223c0);start=0
while True:
    off=old.data.find(needle,start)
    if off<0:break
    out['old']['cancel_address_literal_offsets'].append(hex(off));start=off+1
needed={v for fn in json.loads((W/'QIDI_Q2_SCREEN_QUEUE_FEASIBILITY_20261028/VALIDATION.json').read_text())['queue_dependency_calls'].values() for row in fn if (v:=row['import'])}
available=set(out['old']['imports'].values());assert not needed-available,needed-available
out['required_imports_present']=sorted(needed)
assert not (R/'BINDINGS.json').exists()
(R/'BINDINGS.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({k:{a:v[a] for a in ('literals','dynamics','cancel_address_literal_offsets') if a in v} for k,v in out.items() if isinstance(v,dict)}))
