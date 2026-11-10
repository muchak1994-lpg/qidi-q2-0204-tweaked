"""Fix startup integration: this executable's CSU uses literal array bounds.

Changing only DT_INIT_ARRAY did not change what __libc_csu_init iterates.
Keep failed R1 and its runtime evidence intact. No queue code/test reruns.
"""
from support import *
import json
first=json.loads((R/'CANDIDATE.json').read_text());e=Elf(R/first['candidate']);old=load('old')
assert hashlib.sha256(e.data).hexdigest()==first['candidate_sha256']
fr=json.loads((R/'FRAGMENT.json').read_text());start=int(fr['init_array']['address'],16);end=start+fr['init_array']['bytes']
assert read(e,start+8,80*8)==section_bytes(old,'.init_array')
assert old.sections['.init_array'][3]==0x59e7ad0 and old.sections['.init_array'][5]==640
out=bytearray(e.data);changes=[]
for pc,target,mode in [(0x8bb5dc,end,'adrp'),(0x8bb5e0,end,'add'),(0x8bb5e8,start,'adrp'),(0x8bb5ec,start,'add')]:
    off=e.off(pc);w=struct.unpack_from('<I',out,off)[0]
    if mode=='adrp':
        assert w&0x9f000000==0x90000000
        imm=((target&~4095)-(pc&~4095))//4096;assert -(1<<20)<=imm<(1<<20)
        n=(w&~0x60ffffe0)|((imm&3)<<29)|(((imm>>2)&0x7ffff)<<5)
    else:
        assert w&0xffc00000==0x91000000;n=(w&~(4095<<10))|((target&4095)<<10)
    changes.append({'va':hex(pc),'offset':off,'before':struct.pack('<I',w).hex(),'after':struct.pack('<I',n).hex(),'meaning':'actual static CSU '+mode+' for '+('end' if pc<0x8bb5e4 else 'begin')})
    struct.pack_into('<I',out,off,n)
undo=bytearray(out)
for x in changes:undo[x['offset']:x['offset']+4]=bytes.fromhex(x['before'])
assert bytes(undo)==e.data
name='qidiclient.QUEUE_PORT_R2_LAPTOP_ONLY';assert not (R/name).exists();(R/name).write_bytes(out)
report=dict(first);report.update(candidate=name,candidate_sha256=hashlib.sha256(out).hexdigest(),previous_candidate_sha256=first['candidate_sha256'],previous_candidate_full_start_failed=True,root_cause='main executable __libc_csu_init uses compiled literal begin/end, not new DT_INIT_ARRAY bounds',static_CSU_begin=hex(start),static_CSU_end=hex(end),static_CSU_count=(end-start)//8,original_edits=first['original_edits']+changes,only_R1_changes_are_four_CSU_instructions=True,queue_fragment_unchanged=True,runtime_executed=False)
(R/'CANDIDATE_R2.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
# Independently decode actual resulting addresses in all four instructions.
import sys;sys.path.insert(0,str(W/'QIDI_Q2_FOREIGN_SCREEN_STATIC_20261018/deps'));import capstone
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN);md.detail=True
candidate=Elf(R/name)
for pc,tgt in [(0x8bb5dc,end),(0x8bb5e8,start)]:
    a=next(md.disasm(read(candidate,pc,4),pc));b=next(md.disasm(read(candidate,pc+4,4),pc+4))
    assert a.mnemonic=='adrp' and b.mnemonic=='add'
    assert a.operands[1].imm+b.operands[2].imm==tgt
assert read(candidate,0x8100000,0x2000)==(R/'fragment.code').read_bytes()
assert read(candidate,0x8120000,len((R/'fragment.ro').read_bytes()))==(R/'fragment.ro').read_bytes()
inverse=bytearray(out[:len(old.data)]);inverse[:64]=old.data[:64]
for x in report['original_edits']:inverse[x['offset']:x['offset']+len(bytes.fromhex(x['before']))]=bytes.fromhex(x['before'])
assert bytes(inverse)==old.data
(R/'R2_STATIC_VALIDATION.json').write_text(json.dumps({'candidate_sha256':report['candidate_sha256'],'base_static_validation_reused_no_rerun':True,'all_new_four_instructions_decoded':True,'queue_code_and_EH_LSDA_unchanged':True,'native10_results_reused_no_rerun':True,'static_CSU_reads_exact_new81_array':True,'inverse_exact_installed28b':True,'printer_contact':False},indent=2),encoding='utf-8')
source=(R/'trial_full_client.py').read_text(encoding='utf-8')
for before,after in [('full-client-once','full-client-r2-once'),('qidiclient.QUEUE_PORT_LAPTOP_ONLY',name),('CANDIDATE.json','CANDIDATE_R2.json')]:
    assert source.count(before)==1;source=source.replace(before,after)
assert not (R/'trial_full_client_r2.py').exists();(R/'trial_full_client_r2.py').write_text(source,encoding='utf-8')
print(json.dumps({'candidate':name,'sha256':report['candidate_sha256'],'CSU_begin':hex(start),'CSU_end':hex(end),'count':81,'native_fragment_unchanged':True,'inverse28b':True}))
