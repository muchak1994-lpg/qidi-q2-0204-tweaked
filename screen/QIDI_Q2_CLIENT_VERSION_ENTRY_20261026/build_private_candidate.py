"""One additional BL to the existing client28 async publication wrapper.

Private laptop candidate only. No transport, installer, hooks or services.
"""
from pathlib import Path
import hashlib,json,struct,sys
R=Path(__file__).resolve().parent;W=R.parent
src=W/'QIDI_Q2_CLIENT_NARROW_ASYNC_20261024/qidiclient.CANDIDATE_NOT_INSTALLED'
old=src.read_bytes();sha=lambda x:hashlib.sha256(x).hexdigest()
assert sha(old)=='e6b0c3e95cdbf6db52a9a3c2638a0c5cbf76a8ee7096e749727631a26a8f4c51'
site,target=0x51cf80,0x8000000;off=site-0x400000
assert old[off:off+4].hex()=='ec140894'
displacement=target-site;assert displacement%4==0 and -(1<<27)<=displacement<(1<<27)
instruction=struct.pack('<I',0x94000000|((displacement>>2)&0x3ffffff))
out=bytearray(old);out[off:off+4]=instruction
assert out[:off]==old[:off] and out[off+4:]==old[off+4:]
inverse=bytearray(out);inverse[off:off+4]=old[off:off+4];assert inverse==old
h=struct.unpack_from('<16sHHIQQQIHHHHHH',old)
ph=[struct.unpack_from('<IIQQQQQQ',old,h[5]+i*h[9]) for i in range(h[10])]
def mapping(a,n):
 row=next(p for p in ph if p[0]==1 and p[3]<=a and a+n<=p[3]+p[5]);assert row[1]&1
 return row[2]+a-row[3]
assert mapping(site,4)==off;wrapper_offset=mapping(target,88)
fragment=(W/'QIDI_Q2_CLIENT_NARROW_ASYNC_20261024/fragment.arm64.elf').read_bytes();fh=struct.unpack_from('<16sHHIQQQIHHHHHH',fragment)
fps=[struct.unpack_from('<IIQQQQQQ',fragment,fh[5]+i*fh[9]) for i in range(fh[10])]
frag=next(p for p in fps if p[0]==1 and p[3]==target and p[1]&1)
assert old[wrapper_offset:wrapper_offset+88]==fragment[frag[2]:frag[2]+88]
sys.path.insert(0,str(W/'QIDI_Q2_FOREIGN_SCREEN_STATIC_20261018/deps'));import capstone
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM);md.detail=True
decoded=list(md.disasm(instruction,site));assert len(decoded)==1 and decoded[0].mnemonic=='bl' and decoded[0].operands[0].imm==target
file=R/'qidiclient.VERSION_ENTRY_PRIVATE_DO_NOT_INSTALL';assert not file.exists();file.write_bytes(out)
report={'scope':'PRIVATE candidate only. Static validation, not full native runtime/hardware/print acceptance. No deployment permission implied.',
 'file':file.name,'bytes':len(out),'parent_sha256':sha(old),'candidate_sha256':sha(out),'only_changed_instruction':hex(site),
 'old_bytes':old[off:off+4].hex(),'new_bytes':instruction.hex(),'decoded':decoded[0].mnemonic+' '+decoded[0].op_str,
 'BL_return_address':hex(site+4),'destination_existing28_wrapper':hex(target),'displacement_bytes':displacement,
 'all_other_bytes_identical':True,'inverse_sha256':sha(inverse),'ELF_headers_segments_imports_unwind_metadata_unchanged':True,
 'existing_88B_wrapper_matches_original_fragment':True,'history_patch_preserved':True,
 'original_async_allocation_failure_and_fatal_OOM_semantics_not_fixed':True,
 'known_GUI_firmware_refresh_other_branch_unmodified':True,'all_possible_indirect_GUI_entries_excluded':False,
 'no_UI_foreign_hide_edits':True,'native_full_runtime_verified':False,'printer_contact':False,'installer_built':False}
(R/'PRIVATE_CANDIDATE.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
