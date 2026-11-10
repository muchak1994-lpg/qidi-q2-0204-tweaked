"""Relocate QIDI's selected native queue code, never execute or deploy it.

No replacement queue algorithm. Instruction counts/CFI/LSDA are preserved;
only PC-relative addresses and existing-client import bindings change.
"""
from support import *
import json,sys
sys.path.insert(0,str(W/'QIDI_Q2_FOREIGN_SCREEN_STATIC_20261018/deps'))
import capstone
old=load('old');new=load('new');md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN)
meta=json.loads((R/'PORT_METADATA.json').read_text())
exc=json.loads((R/'EXCEPTIONS.json').read_text())
CODE=0x08100000;DATA=0x08110000;RO=0x08120000
RAW=CODE+0x1800;ADAPTER=CODE+0x1900;CTOR=CODE+0x1060
blocks=[(0x5cd320,CODE+0x320,0x530,'QIDI queue destructor/growth/enqueue/drain'),(0x459060,CTOR,240,'QIDI queue static constructor'),(0x722330,RAW,144,'original04 async, bypass entry routing')]
old_imports={v:k for k,v in imports(old).items()};new_imports=imports(new)
def location(a):
    for src,dst,n,_ in blocks:
        if src<=a<src+n:return dst+a-src
    raise AssertionError('unmapped code target '+hex(a))
def branch(word,pc,target):
    diff=target-pc;assert diff%4==0 and -(1<<27)<=diff<(1<<27)
    return (word&0xfc000000)|((diff//4)&0x3ffffff)
def adrp(word,pc,page):
    imm=(page-(pc&~4095))//4096;assert -(1<<20)<=imm<(1<<20)
    return (word&~0x60ffffe0)|((imm&3)<<29)|(((imm>>2)&0x7ffff)<<5)
def adrp_target(word,pc):
    imm=((word>>5)&0x7ffff)<<2 | ((word>>29)&3)
    if imm&0x100000:imm-=0x200000
    return (pc&~4095)+(imm<<12)
def internal_target(word,pc,bits,shift):
    imm=(word>>shift)&((1<<bits)-1)
    if imm&(1<<(bits-1)):imm-=1<<bits
    return pc+4*imm
code=bytearray(0x2000);changes=[];disasm=[]
for src,dst,n,label in blocks:
    e=old if src==0x722330 else new
    source=read(e,src,n);output=bytearray(source)
    for i,(w,) in enumerate(struct.iter_unpack('<I',source)):
        a=src+4*i;p=dst+4*i;changed=w;reason=None
        if w&0x7c000000==0x14000000:
            target=internal_target(w,a,26,0)
            if src==0x722330:
                # The original04 calls remain original04 calls.
                to=target
            elif target in new_imports:
                to=old_imports[new_imports[target]]
            elif target==0x77b5b0:to=RAW
            else:to=location(target)
            changed=branch(w,p,to);reason='direct branch'
        elif w&0x9f000000==0x90000000:
            target=adrp_target(w,a)
            if src==0x722330:
                assert target==0x722000;page=target
            else:
                page={0x7b6f000:DATA,0x9d9000:RO,0x9c4000:RO,0x5b52000:0x5a10000,0x5cd000:CODE}[target]
            changed=adrp(w,p,page);reason='ADRP'
        elif w&0xff000010==0x54000000:
            to=internal_target(w,a,19,5);assert location(to)-p==to-a
        elif w&0x7e000000==0x34000000:
            to=internal_target(w,a,19,5);assert location(to)-p==to-a
        elif w&0x7e000000==0x36000000:
            to=internal_target(w,a,14,5);assert location(to)-p==to-a
        elif w&0x9f000000==0x10000000 or w&0x3b000000==0x18000000:
            raise AssertionError('unexpected ADR/literal load '+hex(a))
        if a==0x4590e0:
            assert w&0xffc00000==0x91000000 and (w>>10)&4095==0x420
            changed=(w&~(4095<<10))|(0x308<<10);reason='existing04 DSO handle offset'
        if changed!=w:
            struct.pack_into('<I',output,4*i,changed)
            changes.append({'source':hex(a),'destination':hex(p),'before':hex(w),'after':hex(changed),'reason':reason})
    code[dst-CODE:dst-CODE+n]=output
    disasm.append('\n'+label+' '+hex(dst))
    disasm += ['%08x %-8s %s'%(x.address,x.mnemonic,x.op_str) for x in md.disasm(bytes(output),dst)]

# Small adapter: caller already owns GUI mutex. Drain then preserve original
# timer-handler result. A separate FDE covers the new frame for unwinding.
adapter=struct.pack('<IIIIII',0xa9bf7bfd,0x910003fd,branch(0x94000000,ADAPTER+8,location(0x5cd680)),branch(0x94000000,ADAPTER+12,0x726b90),0xa8c17bfd,0xd65f03c0)
code[ADAPTER-CODE:ADAPTER-CODE+len(adapter)]=adapter
disasm.append('\nGUI adapter '+hex(ADAPTER))
disasm += ['%08x %-8s %s'%(x.address,x.mnemonic,x.op_str) for x in md.disasm(adapter,ADAPTER)]
ro=bytearray(0x1000)
string=read(new,0x9c4218,256).split(b'\0',1)[0]+b'\0';assert len(string)<128
ro[0x218:0x218+len(string)]=string
# Native CIE used an indirect pointer to the personality PLT, not a new import.
struct.pack_into('<Q',ro,0xba8,qword(old,0x8e3048))
struct.pack_into('<Q',ro,0xbb0,old_imports['__gxx_personality_v0'])
def append(data,alignment=4):
    pad=(-len(ro))%alignment;ro.extend(bytes(pad));va=RO+len(ro);ro.extend(data);return va
lsdas={}
for fn,entry in exc['new']['exception_tables'].items():
    lsdas[fn]=append(bytes.fromhex(entry['hex']))
simple=bytes.fromhex(meta['04']['entries']['0x722330']['cie_hex'])
assert simple==bytes.fromhex(meta['03.02']['entries']['0x5cd320']['cie_hex'])
simple_va=append(simple)
complex_cie=bytearray.fromhex(meta['03.02']['entries']['0x5cd500']['cie_hex'])
assert complex_cie[9:14]==b'zPLR\0' and complex_cie[18]==0x9b
complex_va=RO+len(ro)+(-len(ro))%4
struct.pack_into('<i',complex_cie,19,RO+0xbb0-(complex_va+19))
assert append(complex_cie)==complex_va
entries=[];fde_reports=[]
for tag in ('03.02','04'):
    for fn,entry in meta[tag]['entries'].items():
        original=int(fn,16);address=location(original);fde=bytearray.fromhex(entry['fde_hex'])
        fdeva=RO+len(ro)+(-len(ro))%4
        cie=complex_va if entry['augmentation']=='zPLR' else simple_va
        struct.pack_into('<I',fde,4,fdeva+4-cie)
        struct.pack_into('<i',fde,8,address-(fdeva+8))
        if entry['lsda']:
            alen,ap=uleb(fde,16);assert alen==4
            struct.pack_into('<i',fde,ap,lsdas[fn]-(fdeva+ap))
        assert append(fde)==fdeva
        entries.append((address,fdeva));fde_reports.append({'old':fn,'new':hex(address),'fde':hex(fdeva),'cie':hex(cie),'range':entry['range'],'LSDA':hex(lsdas[fn]) if entry['lsda'] else None,'CFI_unchanged':True})
# FDE for the adapter, simple zR, SP-based CFA with x29/x30 saved for both BLs.
cfi=bytes.fromhex('410e109d029e0144ddde0e00')
fbody=bytearray(12)+b'\0'+cfi
fbody.extend(bytes((-len(fbody))%4))
fva=RO+len(ro)+(-len(ro))%4
struct.pack_into('<I',fbody,0,fva+4-simple_va)
struct.pack_into('<iI',fbody,4,ADAPTER-(fva+8),len(adapter))
assert append(struct.pack('<I',len(fbody))+fbody)==fva
entries.append((ADAPTER,fva));append(bytes(4))
old_init=section_bytes(old,'.init_array');init_va=append(struct.pack('<Q',CTOR)+old_init,8)
report={'scope':'offline native fragment, not runtime/hardware verified','input_sha256':{k:v[1] for k,v in PATHS.items()},'code_base':hex(CODE),'data_base':hex(DATA),'ro_base':hex(RO),'queue_object':hex(DATA+0x570),'enqueue':hex(location(0x5cd500)),'drain':hex(location(0x5cd680)),'constructor':hex(CTOR),'destructor':hex(location(0x5cd320)),'original_async_copy':hex(RAW),'GUI_adapter':hex(ADAPTER),'relocated_blocks':[{'source':hex(s),'target':hex(d),'bytes':n,'label':l} for s,d,n,l in blocks],'instruction_changes':changes,'unwind_entries':[[hex(a),hex(f)] for a,f in sorted(entries)],'unwind_details':fde_reports,'adapter_new_CFI':cfi.hex(),'init_array':{'address':hex(init_va),'bytes':8+len(old_init),'original_bytes_preserved_after_new_first_entry':True},'code_sha256':hashlib.sha256(code).hexdigest(),'ro_sha256':hashlib.sha256(ro).hexdigest(),'no_new_dynamic_imports':True,'no_new_queue_algorithm':True,'printer_contact':False,'runtime_executed':False}
assert not (R/'FRAGMENT.json').exists()
(R/'fragment.code').write_bytes(code);(R/'fragment.ro').write_bytes(ro)
(R/'FRAGMENT_DISASSEMBLY.txt').write_text('\n'.join(disasm)+'\n',encoding='utf-8')
(R/'FRAGMENT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('instruction_changes','unwind_details','relocated_blocks')}))
