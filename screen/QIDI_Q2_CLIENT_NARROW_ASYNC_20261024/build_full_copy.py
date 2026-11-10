"""One-shot offline ELF integration; never executes or deploys the output."""
from pathlib import Path
import struct,json,hashlib
R=Path(__file__).resolve().parent;W=R.parent
OUT=R/'qidiclient.CANDIDATE_NOT_INSTALLED'
assert not OUT.exists(),'Candidate already built; inspect saved results instead of rebuilding'
src=W/'QIDI_Q2_CLIENT_REA_REVIEW_20261024/inputs/qidiclient'
original=src.read_bytes();fragment=(R/'fragment.arm64.elf').read_bytes()
assert hashlib.sha256(original).hexdigest()=='21d0c448a1c0f6d974e4a10d8ba787fe26a7bf7b5e30c2638b5c5dbce9029af3'
v=json.loads((R/'VERIFICATION.json').read_text());assert v['passed']
assert hashlib.sha256(fragment).hexdigest()==v['fragment_sha256']
def elf(d):
 h=list(struct.unpack_from('<16sHHIQQQIHHHHHH',d));assert h[1:3]==[2,183]
 p=[list(struct.unpack_from('<IIQQQQQQ',d,h[5]+i*h[9])) for i in range(h[10])]
 s=[list(struct.unpack_from('<IIQQQQIIQQ',d,h[6]+i*h[11])) for i in range(h[12])]
 n=s[h[13]];names=d[n[4]:n[4]+n[5]]
 byname={names[x[0]:].split(b'\0',1)[0].decode():i for i,x in enumerate(s)}
 return h,p,s,names,byname
def align(x,n):return (x+n-1)//n*n
def header_entries(d,s):
 b=d[s[4]:s[4]+s[5]];assert b[:4]==bytes([1,0x1b,3,0x3b])
 count=struct.unpack_from('<I',b,8)[0];assert len(b)==12+8*count
 return [(s[3]+a,s[3]+f) for a,f in struct.iter_unpack('<ii',b[12:])]
h,ph,sh,names,si=elf(original);fh,fp,fs,fn,fsi=elf(fragment)
orig_entries=header_entries(original,sh[si['.eh_frame_hdr']])
extra_entries=header_entries(fragment,fs[fsi['.eh_frame_hdr']]);assert len(extra_entries)==1
entries=sorted(orig_entries+extra_entries);assert len({x[0] for x in entries})==len(entries)
text=fs[fsi['.text']];data_start=0x8001000;code_start=0x8000000
assert text[3]==code_start and text[5]==88
base=align(len(original),0x10000);ro_off=base+0x1000
ro_segment=next(p for p in fp if p[0]==1 and p[3]==data_start and p[1]==4)
ro_bytes=fragment[ro_segment[2]:ro_segment[2]+ro_segment[5]]
hdr_rel=align(len(ro_bytes),8);hdr_va=data_start+hdr_rel;hdr_off=ro_off+hdr_rel
old_eh=sh[si['.eh_frame']][3]
merged=bytes([1,0x1b,3,0x3b])+struct.pack('<iI',old_eh-(hdr_va+4),len(entries))
merged+=b''.join(struct.pack('<ii',a-hdr_va,f-hdr_va) for a,f in entries)
has_phdr=any(p[0]==6 for p in ph)
new_count=len(ph)+2+(not has_phdr)
pht_rel=align(hdr_rel+len(merged),8);pht_va=data_start+pht_rel;pht_off=ro_off+pht_rel
pht_size=new_count*56;ro_size=pht_rel+pht_size
new_loads=[[1,5,base,code_start,code_start,text[5],text[5],0x10000],
           [1,4,ro_off,data_start,data_start,ro_size,ro_size,0x10000]]
for p in ph:
 if p[0]==1:
  assert all(not(p[3]<q[3]+q[6] and q[3]<p[3]+p[6]) for q in new_loads)
new_phdr=[6,4,pht_off,pht_va,pht_va,pht_size,pht_size,8]
changed_eh=0
for i,p in enumerate(ph):
 if p[0]==6:ph[i]=new_phdr
 elif p[0]==0x6474e550:
  ph[i]=[p[0],4,hdr_off,hdr_va,hdr_va,len(merged),len(merged),4];changed_eh+=1
assert changed_eh==1
if not has_phdr:ph.insert(0,new_phdr)
ph.extend(new_loads);assert len(ph)==new_count
assert [p[3] for p in ph if p[0]==1]==sorted(p[3] for p in ph if p[0]==1)
assert not any(p[0]==1 and p[1]&3==3 for p in new_loads)
out=bytearray(original);out.extend(bytes(ro_off+ro_size-len(out)))
out[base:base+text[5]]=fragment[text[4]:text[4]+text[5]]
out[ro_off:ro_off+len(ro_bytes)]=ro_bytes
out[hdr_off:hdr_off+len(merged)]=merged
for i,p in enumerate(ph):struct.pack_into('<IIQQQQQQ',out,pht_off+i*56,*p)
def add_section(name,kind,flags,addr,off,size,alignment):
 global names
 name_at=len(names);names+=name.encode()+b'\0'
 sh.append([name_at,kind,flags,addr,off,size,0,0,alignment,0])
# Existing EH header name now describes the active merged index.
eh_idx=si['.eh_frame_hdr'];sh[eh_idx][3:6]=[hdr_va,hdr_off,len(merged)]
add_section('.q2_async_text',1,6,code_start,base,text[5],32)
for oldname,newname in [('.eh_frame','.q2_async_eh_frame'),('.got','.q2_async_got')]:
 s=fs[fsi[oldname]];assert data_start<=s[3]<data_start+len(ro_bytes)
 add_section(newname,1,2,s[3],ro_off+s[3]-data_start,s[5],8)
add_section('.q2_program_headers',1,2,pht_va,pht_off,pht_size,8)
names_off=len(out);out.extend(names)
sh[h[13]][4:6]=[names_off,len(names)]
sh_off=align(len(out),8);out.extend(bytes(sh_off-len(out)))
for s in sh:out.extend(struct.pack('<IIQQQQIIQQ',*s))
h[5]=pht_off;h[6]=sh_off;h[10]=len(ph);h[12]=len(sh)
struct.pack_into('<16sHHIQQQIHHHHHH',out,0,*h)
# Exact old tail instruction is the sole changed original .text instruction.
ot=sh[si['.text']];site=0x4f7c50;site_off=ot[4]+site-ot[3]
assert out[site_off:site_off+4].hex()==v['original_tail_bytes']
out[site_off:site_off+4]=bytes.fromhex(v['prospective_B_bytes'])
changes=[i for i in range(len(original)) if out[i]!=original[i]]
allowed=set(range(64))|set(range(site_off,site_off+4))
assert all(i in allowed for i in changes)
ch,cp,cs,cn,ci=elf(out)
decoded=header_entries(out,cs[ci['.eh_frame_hdr']]);assert decoded==entries
assert ch[4]==struct.unpack_from('<Q',original,24)[0]
assert ch[10]==new_count and ch[12]==len(sh)
assert any(p[0]==6 and p[2]==ch[5] and p[5]==new_count*56 for p in cp)
for p in cp:
 if p[0]==1:
  assert p[2]+p[5]<=len(out) and p[5]<=p[6]
  assert p[2]%p[7]==p[3]%p[7]
assert original[ot[4]:ot[4]+ot[5]][:site-ot[3]]==out[ot[4]:ot[4]+ot[5]][:site-ot[3]]
assert src.read_bytes()==original
report={'candidate':OUT.name,'original_bytes':len(original),'candidate_bytes':len(out),
 'original_sha256':hashlib.sha256(original).hexdigest(),'candidate_sha256':hashlib.sha256(out).hexdigest(),
 'original_changed_byte_positions':changes,'old_region_changes_only_ELF_header_and_one_B':True,
 'original_entry_preserved':True,'old_unwind_entries':len(orig_entries),'new_unwind_entries':len(entries),
 'new_program_headers':len(ph),'program_header_offset':pht_off,'section_header_offset':sh_off,
 'no_new_dynamic_imports':True,'original_loaded_data_bytes_preserved':True,
 'linked_and_indexed_offline_only':True,'not_executed_or_deployed':True,
 'prototype_policy_abort_and_fatal_OOM_still_pending':True,
 'build_id_note_retained_from_original_NOT_candidate_identity':True}
OUT.write_bytes(out)
(R/'FULL_COPY.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
