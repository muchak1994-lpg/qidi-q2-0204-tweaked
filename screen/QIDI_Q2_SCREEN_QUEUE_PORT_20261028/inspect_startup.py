from support import *
import json,sys
e=load('old');sys.path.insert(0,str(W/'QIDI_Q2_FOREIGN_SCREEN_STATIC_20261018/deps'))
import capstone
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN)
entry=struct.unpack_from('<Q',e.data,24)[0];start=list(md.disasm(read(e,entry,128),entry))
regs={};init=None
for i in start:
    if i.mnemonic=='adrp':
        r,v=i.op_str.split(', ');regs[r]=int(v[1:],16)
    elif i.mnemonic=='add':
        parts=i.op_str.split(', ')
        if len(parts)==3 and parts[1] in regs and parts[2].startswith('#'):regs[parts[0]]=regs[parts[1]]+int(parts[2][1:],0)
    elif i.mnemonic in ('movz','movk'):
        parts=i.op_str.split(', ');shift=int(parts[2].split('#')[1],0) if len(parts)==3 else 0
        reg=parts[0];value=int(parts[1][1:],0)<<shift
        regs[reg]=value if i.mnemonic=='movz' else (regs[reg]&~(65535<<shift))|value
    elif i.mnemonic=='bl':
        if imports(e).get(int(i.op_str[1:],16))=='__libc_start_main':init=regs['x3'];break
assert init is not None
body=list(md.disasm(e.body(init),init));out={'entry':hex(entry),'init_argument_x3':hex(init),'entry_instructions':[{'at':hex(i.address),'op':i.mnemonic,'args':i.op_str} for i in start],'init_instructions':[{'at':hex(i.address),'op':i.mnemonic,'args':i.op_str} for i in body]}
assert not (R/'STARTUP.json').exists();(R/'STARTUP.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out))
