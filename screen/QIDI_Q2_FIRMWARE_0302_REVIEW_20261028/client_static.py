from pathlib import Path
import sys,struct,bisect,json,hashlib,re
R=Path(__file__).resolve().parent;W=R.parent
sys.path.insert(0,str(W/'QIDI_Q2_FOREIGN_SCREEN_STATIC_20261018/deps'))
import capstone
class Elf:
 def __init__(self,path):
  self.data=path.read_bytes();h=struct.unpack_from('<16sHHIQQQIHHHHHH',self.data);assert h[0][:6]==b'\x7fELF\x02\x01' and h[2]==183
  raw=[struct.unpack_from('<IIQQQQIIQQ',self.data,h[6]+i*h[11]) for i in range(h[12])];s=raw[h[13]];names=self.data[s[4]:s[4]+s[5]];self.sections={names[v[0]:].split(b'\0',1)[0].decode():v for v in raw}
  s=self.sections['.eh_frame_hdr'];b=self.data[s[4]:s[4]+s[5]];assert b[:4]==bytes([1,0x1b,3,0x3b]);self.functions=[s[3]+struct.unpack_from('<i',b,12+8*i)[0] for i in range(struct.unpack_from('<I',b,8)[0])]
 def off(self,va):
  s=next(s for s in self.sections.values() if s[1]!=8 and s[3]<=va<s[3]+s[5]);return s[4]+va-s[3]
 def va(self,off):
  s=next(s for s in self.sections.values() if s[1]!=8 and s[4]<=off<s[4]+s[5]);return s[3]+off-s[4]
 def body(self,va):
  i=self.functions.index(va);end=self.functions[i+1];return self.data[self.off(va):self.off(va)+end-va]
 def strings(self):
  s=self.sections['.rodata'];return {v.decode() for v in re.findall(rb'[\x20-\x7e]{5,}',self.data[s[4]:s[4]+s[5]])}
old=Elf(W/'QIDI_Q2_FIRMWARE_DIFF_20261021/selected/new/home/qidi/QIDI_Client/bin/qidiclient');new=Elf(R/'changed-files/home/qidi/QIDI_Client/bin/qidiclient')
assert hashlib.sha256(new.data).hexdigest()=='c222bb9c77df6fe714e974f915834841be96c291bb75d44cd6f4d371e174f423'
pattern=old.body(0x77d550)[:36];hits=[];off=0
while True:
 off=new.data.find(pattern,off)
 if off<0:break
 va=new.va(off)
 if va in new.functions:hits.append(va)
 off+=1
assert len(hits)==1
callback=hits[0];idx=new.functions.index(callback);md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN);rows=[];lines=[]
for i,name in enumerate(['async_callback','async_create_candidate','async_cancel_candidate']):
 va=new.functions[idx+i];body=new.body(va);ins=list(md.disasm(body,va));row={'name':name,'address':hex(va),'bytes':len(body),'instructions':[{'address':hex(x.address),'mnemonic':x.mnemonic,'operands':x.op_str} for x in ins]};rows.append(row);lines.append(name+' '+hex(va));lines += ['%08x %-8s %s'%(x.address,x.mnemonic,x.op_str) for x in ins]
# Also inspect only the timer creator called by async_create, rather than a full
# disassembly of the90MB binary. Its initialization/publication order is relevant.
creator=rows[1];calls=[int(i['operands'][1:],16) for i in creator['instructions'] if i['mnemonic']=='bl' and i['operands'].startswith('#0x')]
for va in calls:
 if va not in new.functions:continue
 body=new.body(va)
 if len(body)>600:continue
 ins=list(md.disasm(body,va));lines.append('async_create called '+hex(va));lines += ['%08x %-8s %s'%(x.address,x.mnemonic,x.op_str) for x in ins]
a=old.strings();b=new.strings();added=sorted(b-a);removed=sorted(a-b)
interesting=lambda s:any(k.lower() in s.lower() for k in ['G28','filament','slot16','last_load_slot','home','box','page','nozzle'])
strings={'added_count':len(added),'removed_count':len(removed),'added_interesting':[s for s in added if interesting(s)],'removed_interesting':[s for s in removed if interesting(s)],'commands_present_both':sorted(s for s in a&b if 'slot16' in s or 'last_load_slot' in s)}
out={'ELF_SHA256':hashlib.sha256(new.data).hexdigest(),'callback_first36_bytes_identical':True,'functions':rows,'direct_calls_from_async_creator':[hex(v) for v in calls],'strings':strings,'native_execution':False,'all_callers_or_locks_reviewed':False,'printer_contact':False}
assert not (R/'CLIENT_STATIC.json').exists();(R/'CLIENT_STATIC.json').write_text(json.dumps(out,indent=2),encoding='utf-8');(R/'CLIENT_ASYNC.txt').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'callback':hex(callback),'creator':rows[1]['address'],'functions':len(new.functions),'string_diff':strings},ensure_ascii=False))
