"""Offline integration into exact installed28b baseline; no deployment."""
from support import *
import json
e=load('old');original=e.data;report=json.loads((R/'FRAGMENT.json').read_text())
code=(R/'fragment.code').read_bytes();ro=bytearray((R/'fragment.ro').read_bytes())
assert hashlib.sha256(code).hexdigest()==report['code_sha256']
assert hashlib.sha256(ro).hexdigest()==report['ro_sha256']
CODE=int(report['code_base'],16);DATA=int(report['data_base'],16);RO=int(report['ro_base'],16)
def align(n,a):return (n+a-1)//a*a
h=list(struct.unpack_from('<16sHHIQQQIHHHHHH',original))
ph=[list(struct.unpack_from('<IIQQQQQQ',original,h[5]+i*h[9])) for i in range(h[10])]
sh=[list(struct.unpack_from('<IIQQQQIIQQ',original,h[6]+i*h[11])) for i in range(h[12])]
s=sh[h[13]];names=original[s[4]:s[4]+s[5]]
indices={names[s[0]:].split(b'\0',1)[0].decode():i for i,s in enumerate(sh)}
eh=e.sections['.eh_frame_hdr'];old_entries=[(eh[3]+a,eh[3]+f) for a,f in struct.iter_unpack('<ii',section_bytes(e,'.eh_frame_hdr')[12:])]
entries=sorted(old_entries+[(int(a,16),int(f,16)) for a,f in report['unwind_entries']])
assert len(entries)==len(old_entries)+7 and len({a for a,_ in entries})==len(entries)
init=e.sections['.init_array']
# Original fixed ET_EXEC init pointers require no relocation at the old slots.
for relname in ('.rela.dyn','.rela.plt'):
    for addr,info,addend in struct.iter_unpack('<QQq',section_bytes(e,relname)):
        assert not init[3]<=addr<init[3]+init[5]
hdr_rel=align(len(ro),8);hdr_va=RO+hdr_rel
merged=bytes([1,0x1b,3,0x3b])+struct.pack('<iI',e.sections['.eh_frame'][3]-(hdr_va+4),len(entries))
merged+=b''.join(struct.pack('<ii',a-hdr_va,f-hdr_va) for a,f in entries)
ro.extend(bytes(hdr_rel-len(ro)));ro.extend(merged)
assert sum(p[0]==6 for p in ph)==1
new_count=len(ph)+3
pht_rel=align(len(ro),8);pht_va=RO+pht_rel;pht_size=new_count*56
ro.extend(bytes(pht_rel-len(ro)));ro.extend(bytes(pht_size))
base=align(len(original),0x10000);code_off=base;data_off=base+0x10000;ro_off=base+0x20000
new_loads=[[1,5,code_off,CODE,CODE,len(code),len(code),0x10000],
           [1,6,data_off,DATA,DATA,0,0x1000,0x10000],
           [1,4,ro_off,RO,RO,len(ro),len(ro),0x10000]]
for p in ph:
    if p[0]==1:
        assert all(not(p[3]<n[3]+n[6] and n[3]<p[3]+p[6]) for n in new_loads)
for i,p in enumerate(ph):
    if p[0]==6:ph[i]=[6,4,ro_off+pht_rel,pht_va,pht_va,pht_size,pht_size,8]
    elif p[0]==0x6474e550:ph[i]=[p[0],4,ro_off+hdr_rel,hdr_va,hdr_va,len(merged),len(merged),4]
ph.extend(new_loads);assert len(ph)==new_count
assert [p[3] for p in ph if p[0]==1]==sorted(p[3] for p in ph if p[0]==1)
for i,p in enumerate(ph):struct.pack_into('<IIQQQQQQ',ro,pht_rel+56*i,*p)
out=bytearray(original);out.extend(bytes(ro_off+len(ro)-len(out)))
out[code_off:code_off+len(code)]=code;out[ro_off:ro_off+len(ro)]=ro
edits=[]
def edit_va(a,b,meaning):
    off=e.off(a);before=bytes(out[off:off+len(b)]);out[off:off+len(b)]=b
    edits.append({'va':hex(a),'offset':off,'before':before.hex(),'after':b.hex(),'meaning':meaning})
def bl(pc,dest,link=True):
    diff=dest-pc;assert diff%4==0 and -(1<<27)<=diff<(1<<27)
    return struct.pack('<I',(0x94000000 if link else 0x14000000)|((diff//4)&0x3ffffff))
edit_va(0x722330,bl(0x722330,int(report['enqueue'],16),False),'all original async entry calls -> QIDI enqueue')
for pc in (0x5b2008,0x5b7188):
    assert read(e,pc,4)==bl(pc,0x726b90)
    edit_va(pc,bl(pc,int(report['GUI_adapter'],16)),'under existing GUI lock: drain then original timer handler')
dynamic_changes=0
for a,t,v in dynamics(e):
    if t==25:
        assert v==init[3];edit_va(a+8,struct.pack('<Q',int(report['init_array']['address'],16)),'DT_INIT_ARRAY: queue constructor before existing entries');dynamic_changes+=1
    elif t==27:
        assert v==init[5];edit_va(a+8,struct.pack('<Q',report['init_array']['bytes']),'DT_INIT_ARRAYSZ: one added constructor');dynamic_changes+=1
assert dynamic_changes==2
def add_section(name,kind,flags,va,offset,size,alignment=4):
    global names
    ni=len(names);names+=name.encode()+b'\0';sh.append([ni,kind,flags,va,offset,size,0,0,alignment,0])
sh[indices['.eh_frame_hdr']][3:6]=[hdr_va,ro_off+hdr_rel,len(merged)]
sh[indices['.init_array']][3:6]=[int(report['init_array']['address'],16),ro_off+int(report['init_array']['address'],16)-RO,report['init_array']['bytes']]
# New constructor array is fixed-address read-only data, no loader writes.
sh[indices['.init_array']][2]=2
add_section('.q2_queue_text',1,6,CODE,code_off,len(code),16)
add_section('.q2_queue_state',8,3,DATA,data_off,0x1000,8)
add_section('.q2_queue_ro',1,2,RO,ro_off,len(ro),8)
add_section('.q2_queue_program_headers',1,2,pht_va,ro_off+pht_rel,pht_size,8)
names_off=len(out);out.extend(names);sh[h[13]][4:6]=[names_off,len(names)]
sh_off=align(len(out),8);out.extend(bytes(sh_off-len(out)))
for s in sh:out.extend(struct.pack('<IIQQQQIIQQ',*s))
h[5]=ro_off+pht_rel;h[6]=sh_off;h[10]=len(ph);h[12]=len(sh)
struct.pack_into('<16sHHIQQQIHHHHHH',out,0,*h)
allowed=set(range(64))
for x in edits:allowed.update(range(x['offset'],x['offset']+len(bytes.fromhex(x['after']))))
changes=[i for i,(a,b) in enumerate(zip(original,out)) if a!=b]
assert all(i in allowed for i in changes)
inverse=bytearray(out[:len(original)]);inverse[:64]=original[:64]
for x in edits:inverse[x['offset']:x['offset']+len(bytes.fromhex(x['before']))]=bytes.fromhex(x['before'])
assert bytes(inverse)==original
name='qidiclient.QUEUE_PORT_LAPTOP_ONLY';assert not (R/name).exists()
(R/name).write_bytes(out)
result={'candidate':name,'candidate_sha256':hashlib.sha256(out).hexdigest(),'bytes':len(out),'parent_sha256':PATHS['old'][1],'new_code_segments_WX':False,'new_rw_executable':False,'original_edits':edits,'original_changed_bytes':len(changes),'inverse_exact_parent':True,'old_unwind_entries':len(old_entries),'new_unwind_entries':len(entries),'all_original_unwind_pairs_preserved':True,'old28_and28b_code_preserved':True,'old_data_preserved_except_two_dynamic_values':True,'original_init_array_has_no_relocation_slots':True,'DT_NEEDED_unchanged':True,'build_id_still_parent_not_candidate_identity':True,'runtime_executed':False,'printer_contact':False,'deployable_release':False}
(R/'CANDIDATE.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='original_edits'}))
