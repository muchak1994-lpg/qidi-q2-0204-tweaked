"""ONE new candidate startup/active-UI trial using the cached device fixture.

Never invokes earlier trial scripts. No real network, printer or host devices.
"""
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,struct,signal,threading,fcntl,socket,resource
R=Path(__file__).resolve().parent;W=R.parent;OLD=W/'QIDI_Q2_NATIVE_GUI_SANDBOX_20261018'
resource.setrlimit(resource.RLIMIT_CORE,(0,0));sys.path.insert(0,str(OLD))
def inside(run):
    from mock_moonraker import Mock,make_server
    assert os.readlink('/proc/self/ns/net')!=os.environ['Q2_HOST_NETNS']
    assert socket.if_nameindex()==[(1,'lo')]
    assert os.statvfs(W).f_flag&os.ST_RDONLY and not os.statvfs(run).f_flag&os.ST_RDONLY
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        v=fcntl.ioctl(s.fileno(),0x8913,struct.pack('16sH14x',b'lo',0));flags=struct.unpack_from('H',v,16)[0]|1
        fcntl.ioctl(s.fileno(),0x8914,struct.pack('16sH14x',b'lo',flags))
    data=json.loads((OLD/'MOCK_DATA.json').read_text());mock=Mock(data,run/'rpc.jsonl');server=make_server(mock)
    for target in (server.serve_forever,mock.heartbeat):threading.Thread(target=target,daemon=True).start()
    sdk=W/'QIDI_Q2_RECOVERY_PACKAGE/tools/sysroot'
    cmd=[sdk/'usr/bin/qemu-aarch64','-cpu','cortex-a53','-R','0x100000000','-L',OLD/'runtime/sysroot','-E','LD_LIBRARY_PATH=/opt/q2-libs','-E','LD_PRELOAD='+str(OLD/'runtime/virtual_devices.so'),'/opt/q2-libs/ld-2.31.so','--library-path','/opt/q2-libs','/home/qidi/QIDI_Client/bin/qidiclient']
    env=dict(os.environ,LD_LIBRARY_PATH=str(sdk/'usr/lib/x86_64-linux-gnu'),HOME='/home/qidi')
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(25,25))
    def tap(x,y):
        for pressed in (1,0):
            with (run/'event0').open('ab') as f:
                for typ,code,val in [(3,0,x),(3,1,y),(1,330,pressed),(0,0,0)]:f.write(struct.pack('<qqHHi',0,0,typ,code,val))
            time.sleep(.12)
        mock.record('queue_trial_touch',x=x,y=y)
    schedule=[(7,'boot',None),(10,'settings',(22,191)),(13,'firmware',(360,188)),(17,'versions_before',None),(19,'version_update',None),(24,'versions_after',None),(26,'back',(66,18)),(29,'after_back',None)]
    start=time.monotonic();actions=set();samples=[]
    with (run/'client.stdout').open('w') as out,(run/'client.stderr').open('w') as err:
        p=subprocess.Popen([str(x) for x in cmd],cwd='/home/qidi/QIDI_Client/bin',env=env,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        try:
            while p.poll() is None and time.monotonic()-start<31:
                elapsed=time.monotonic()-start
                for at,name,coords in schedule:
                    if elapsed<at or name in actions:continue
                    actions.add(name);(run/(name+'.raw')).write_bytes((run/'fb0').read_bytes()[:522240])
                    if name=='version_update':
                        delta={}
                        for n,v in [('mcu','02.01.01.19'),('mcu THR','02.02.01.18')]:
                            value=dict(mock.data['status'].get(n,{}));value['mcu_version']=v;mock.data['status'][n]=value;delta[n]=value
                        mock.publish('notify_status_update',[delta,time.monotonic()]);mock.record('queue_trial_version_update',delta=delta)
                    if coords:tap(*coords)
                rss=0
                for line in Path('/proc/'+str(p.pid)+'/status').read_text().splitlines():
                    if line.startswith('VmRSS:'):rss=int(line.split()[1])
                samples.append({'elapsed':round(elapsed,3),'rss_kib':rss});time.sleep(.2)
        finally:
            stopped_running=p.poll() is None
            if stopped_running:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=4)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=4)
            server.shutdown();server.server_close()
    result={'new_candidate_sha256':hashlib.sha256(Path('/home/qidi/QIDI_Client/bin/qidiclient').read_bytes()).hexdigest(),'isolated_network_loopback_only':True,'host_filesystem_readonly_except_run':True,'real_devices_hidden':True,'full_client_executed':True,'actions':sorted(actions),'alive_at_controlled_stop':stopped_running,'exit_code':p.returncode,'elapsed_s':round(time.monotonic()-start,3),'max_sampled_rss_kib':max((s['rss_kib'] for s in samples),default=0),'samples':samples,'printer_contact':False,'production_kernel_loader_acceptance':False}
    (run/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)
def outer():
    run=R/'full-client-once';run.mkdir(exist_ok=False);home=run/'home';home.mkdir();(run/'root').mkdir()
    for sub in ['printer_data/config','printer_data/gcodes','printer_data/logs','printer_data/database','printer_data/databasebak','printer_data/.cache','video','download','update']:(home/sub).mkdir(parents=True,exist_ok=True)
    (home/'printer_data/config/printer.cfg').write_text('# LOCAL QUEUE TEST, NO HARDWARE\n')
    (run/'fb0').write_bytes(bytes(4*1024*1024));(run/'event0').write_bytes(b'');(run/'brightness').write_text('255\n')
    candidate=R/'qidiclient.QUEUE_PORT_LAPTOP_ONLY';assert hashlib.sha256(candidate.read_bytes()).hexdigest()==json.loads((R/'CANDIDATE.json').read_text())['candidate_sha256']
    cmd=['bwrap','--die-with-parent','--unshare-all','--uid','0','--gid','0','--new-session','--cap-add','CAP_NET_ADMIN','--ro-bind','/','/','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run','--tmpfs','/sys','--tmpfs','/home','--tmpfs','/opt','--bind',str(run),str(run),'--bind',str(run/'root'),'/root','--dir','/home/qidi','--bind',str(home),'/home/qidi','--ro-bind',str(OLD/'assets/home/qidi/QIDI_Client'),'/home/qidi/QIDI_Client','--tmpfs','/home/qidi/QIDI_Client/bin','--ro-bind',str(candidate),'/home/qidi/QIDI_Client/bin/qidiclient','--dir','/sys/class/backlight/backlight','--bind',str(run/'brightness'),'/sys/class/backlight/backlight/brightness','--bind',str(run/'fb0'),'/dev/fb0','--dir','/dev/input','--bind',str(run/'event0'),'/dev/input/event0','--ro-bind',str(OLD/'runtime/lib'),'/opt/q2-libs','--setenv','Q2_HOST_NETNS',os.readlink('/proc/self/ns/net'),'--setenv','PYTHONDONTWRITEBYTECODE','1','--chdir',str(R),'/usr/bin/python3','-B',str(Path(__file__).resolve()),'--inside',str(run)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=48)
    (run/'launcher.json').write_text(json.dumps({'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=2),encoding='utf-8');print(p.stdout,flush=True);print(p.stderr[-1600:],flush=True);raise SystemExit(p.returncode)
if __name__=='__main__':
    if len(sys.argv)>1:inside(Path(sys.argv[2]))
    else:outer()
