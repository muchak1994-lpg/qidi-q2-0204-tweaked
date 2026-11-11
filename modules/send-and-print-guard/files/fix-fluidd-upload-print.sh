#!/bin/sh
exec python3 -I -B - <<'Q2_SEND_PRINT_GUARD'
# SPDX-License-Identifier: GPL-3.0-only
"""Installed timer payload: refuse unknown firmware and never start a print."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.request import urlopen
from urllib.parse import urlencode

ANCHORS = {'/home/qidi/update/firmware_manifest.json': 'e1ed69645b01446733bbb19916d31d5f67d52c730dfe732470067b24376f45d1', '/home/qidi/QIDI_Client/bin/qidiclient': '21d0c448a1c0f6d974e4a10d8ba787fe26a7bf7b5e30c2638b5c5dbce9029af3'}
CLIENT_PATH = '/home/qidi/QIDI_Client/bin/qidiclient'
APPROVED_CLIENTS = frozenset((ANCHORS[CLIENT_PATH], 'e6b0c3e95cdbf6db52a9a3c2638a0c5cbf76a8ee7096e749727631a26a8f4c51', '2b0ef3b449b8d2e319f3c972325681f116ba1a479c688993752f1b40cb853e6a', 'da4b3c9f9ca38660b10d452ee307285558317a02c4346c9650a5e05c7aa2e7b9'))
APPROVED_CLIENTS = APPROVED_CLIENTS | frozenset(('4696c85ac42494da75faa6157e3a2500c6e4cb321356f0e79cda7c5ffedc904a', 'a20fa3205095eb5d6a4d3135ed67efc3da3de4b220cabe92d7c5d38d2882bb9f', 'ab1b93fdf945fe99cca76bcebb85e900cff0f4078bbe938d030870aadc8ba218', 'b58a7131cf1e525f6373ed401d3ea2c57110061404db44600e3e5a81c7e08423',))  # q2-update-check-off v0.2.0
APPROVED_CLIENTS = APPROVED_CLIENTS | frozenset(('08ef92701e3cabf57f82296250a9db4655c5d54ddc139f412e8ddf6ea813b46e',))  # q2-night-light v0.1.0
APPROVED_CLIENTS = APPROVED_CLIENTS | frozenset(('765ce96ff6b067299cfe59623315577c3737a63c98a64460cba8931a105dcbe1',))  # screen-drying-layout
APPROVED_CLIENTS = APPROVED_CLIENTS | frozenset(('e1e8f86202d81017a81b47c2f102beb1efaa42ae280912ea5c80fd101e750206',))  # screen-drying-autoshow
APPROVED_CLIENTS = APPROVED_CLIENTS | frozenset(('d89cf168cc85eb016761229e84891e542fdab828017741d8eeaa35e8362af2a2', '8118524fce7781985dbd87bbbbd99c5a21391ddab187d57444c7d2f0db3de1d4', 'dc7fdb930fb7cc537cd2d138d676b44799bf09436e2893fa4eb37e7f3c5ec52e', '08cf7bd57944cc365586140f94315c35730f96253a53285e8b5c3221ba8214b3', '08f3ea55c97ca9b242134637a6591ec954878ac2c9f83dab28d9840b8a9a309b', '73248c6545f3b3e6cf2a80274592e8aa0be74d5325c7ecf930f632067ac66c94', '972124ad4e21b9dde39949ac199cdb350f7889c6f6a3fac952dc85f0a2c328b2', 'cbbafe14d9d5c490e53c5ba03758ced8dc98d0f75d6043647eb067e134934340', '9a3337b7a42b86f23f09cb1176abca65b665fb0b71df16ee752f2ac10d3149c2', '7e1da3ecfb6b1b181956efc337e6cf55ff65992b6c4803685b09162cce181b32', 'd89ca138d9354931e808c78a962324700d66c9e156ec79f6450b6237fba7c3fb', '73e9056a0dce3279c18ae7504ac5fe5dc35e00d2743fc4f23367a403b7163e91', '47e10bdd1b690c82303a77606f9524ad49e1c7d8b9f74e4f7f940a70e221f809', 'b38f5927df619d25732287e39ed91fe7f2a4833390695843cdb61af77b224712', '94e15d2a42536b5b017b81628a6e355e37edf5b01dc60de4c0fbf50c2232d6b7', 'd0fb703c06e8813616076c25c8f758cbd57494808fc9aa13fdfd98886b0e3cb1', 'a75c1cb45b955e72644db57fe2da2d7f1b4bdd0d4659fe45fd4384213b2be5ec', 'dc60b8f05939095115e7124ac582513a3040188adbbd9185e8d012b5719b7fc6', '574af9eea24349b68a31d565ffdcf9e0bb84055964398eff45783a2158c9e41e', '3fb85d2401763822c4c68051ee969abd835a0791db9321cf13cb91c2d2eb6b7e', 'ea428f8ee420c7ae7ee64c261f62e306935ffcf7d39f559c8de216d0815c5ae0', '687fb1fd78799a79df8da29455c15ca3e6da6fd2c06e3ffc34efaf8363d3d213', '4ec1069e2c894b5d794429c1eba9f6a5e0ba48aa7e6b4a84c5e7c271a2f7917b', '3e750cc9fee535ecc92219efd663220e7081c4f5e7256e832e208f6891110811', '2480ecb027d402120baae051dc66d41b09d5c9822295d5926cf0d43df18d118e', '35e1b3460b767101ed5b0f383b11605d058dd90904ce351d70ee52412529559d', '918cc226bb9c91378da6f4b60e6fded82ea0d089cd45961da9d2759074df5cad'))  # every --skip combination of the screen byte-edit modules
ORIGINAL_HASH = '178b2e076d3a75716819ee13f9ea1f0c92e536546c8b2adafde8632f6723710c'
PATCHED_HASH = '525ced9d13daba6a4e22ef802e117af14df29de6443b939b43436cdab184a968'

DIRECTORY_HASH = '17bacbe56fef22215db71dad33a4c5226fe060d63e3eebd3db0005e5d6ccc48e'
COMBINED_HASH = 'f399bd76d598f9835ecac11d15e775757325bc10a009694f87aca9e53ea2a1e2'

REPAIR_TARGETS = {"178b2e076d3a75716819ee13f9ea1f0c92e536546c8b2adafde8632f6723710c":"525ced9d13daba6a4e22ef802e117af14df29de6443b939b43436cdab184a968","17bacbe56fef22215db71dad33a4c5226fe060d63e3eebd3db0005e5d6ccc48e":"f399bd76d598f9835ecac11d15e775757325bc10a009694f87aca9e53ea2a1e2","6b31c9e9cce60363af46357944f0f9ed47bc05f6d774eaa87831c01f8bd48d10":"7e2323ffe2edae0060660b706c034f90ed36c07d9ca6944bc03f833664b5104f","e0488a72973f62cce4e3dc7ec1b939c4540817ec5ac40d42beacee21e1933525":"f2495e9d5ccbc3effbe4fd28f47adf1527b28e954cf6c6b1bc2c615fe12d0167","937f14b42ef84748037d26df50d8604b8e94e79687cb9f5914a69ae978744b0e":"47f9b5a9025dac211b6cec73ef611b3cc70109020dca622e42a08ca3c1648394","03b806babf3a48fdf15c1808e11f5f79ff4454e843b2c3d094e89c819797c9e3":"60c0b2a9b1907fea130a6b04cdae976a670e2710e6ff6d6f5e9c1946817e68dc","860b1e78292814bed37e07cf14945dd5a4555f7b78d125b018d3bfe0941d8c97":"216e03136359e1b69209db883fea9e6f6c9ba676d8a5a4d7cbbc952865d55b05","410a5545d2b7cf16f53afb03bd46e35742b8c0c4e70edf0d71ea06abcbef429d":"e20c63a844c837037857d14fcb9dad4a3967720a11fcc4799a511a0d09b34aab","5d77b62f89eba29d2fe5194dec4879c579bef8e8bc456d67c52449ac2c7cb735":"234050514bf3b77353f5c07438abbd341c1fa0b5d9e222cd403dff453d7d6e32","2d731f6164dbb0053906002ddbc48ebfb1148d1171074986cef418ad60bbc06e":"eb20821fef68a4eff92f73fe42207177e5a4e1d84f956fe6d5518006e1a05406","967d078f129f0910ae25ab784d3570b4689e3d6e1bfb9404dba49aa70a663bd4":"249bb21f0f12f79553df4df199d729764b9bebce8c522f09da26543b3bd127c8","570e3ec59c1e3c50d5778c84ab72b6af658e93a6719de63b54691704b74a37d7":"704781e8f93c9bab0891f067346757aacd65278d7bce507d49d05cc7f6aaaf1d","77a0e78588e34db625d536bf463ed83385163cf33d78bdf2827b67e210affd14":"5ecc4e92c43939750681598e847608c6d02d78b2a0347d124779dfe7e1edcbe5","305be91111b0da4ce87dcb7019f1782d5edec38a29edc3acd4f47982b6beb391":"335cbe65b55a07793ab48ea873b1aaab0c54a775ebbc12976ade0326e452741e","81e7492c6653506f4af71d389a2a5cadf82835b9b6388d3d439f2408ca2f5d2d":"1b8a92da2a1cf4518a32f7841e6b0c8eeec3197c8dec84cf5c41ccbe5998a39a","bcabaf1fb8d55cafab1387558ea470bf3c45e15c5557426afd884bcf2756f689":"e7434087227e4eac2694efd4bc5ace6eb694442eadcf3f5bf4fcfe1b70d45fc0","f052f256589295ee86ad7b0c81233866520780870873ebab3b6adb21d34694f8":"ccab84f9e1419b71c90c1a2b4d68119f67e2ba34f0cf468f6201d291119e67aa","df26630f9ceae52f37967da758d95937f76c0ad76ad8b8699c86389c6a2aced4":"3d2b7c481f2a537ded938c3a57b18ee560d700bcfe37254d800fbeebd1377067","65211da019a21fb5192772770fd54f2bb6b2a326b9abf96d8a6bb6f165eaacb4":"82483097a2263e3edcb0327972a22688397a632c0d054222bf24168dd026e1f5","4a8db9a8930b3728ad1ce89f6c92f86c5da02826fb272a688a613b4a1572b786":"d8f9893e43a38a25d1683b6b5b9a1bf5c4a91be2339af1bd3fa68102e5d4aaab","5f3eb796ffb02f976185c1cd220e19a304c01d3242c115059e96f6c67f89737c":"b1e7368b4ac13183f53ba65d3706d3f31c35ec07f8526872eb04f4d9fc2765ed","8931b17a84a0e809811e7a941ada7b820fe2117b611bcfe465f8763eca68bcb3":"e5477d251f6cace9a4784b97a8c87b1b1375fa5ed642b8577c7ca10474ccead5","b714d210f0b6f82fa594429da1aca44ef4cc38bab906d2ae2314ec25001857bd":"0e64bf2abe7ad0df608eee3be150a926ec99a83646919148dd37a1794f767637","0efd03a0c08e8b4b65ca44c4170e75070c6b98e71862283eb140b59aff3d86a1":"f7de2cb2cfbc83a039e90fff703ef59b493fef0b840dbbbcb94d93b0b7cfa87d","cc69ecbcd768dc139ee740df5b5b7377a802136433c9509b06a373906d631e9f":"7b767d7c96945c5e1d4cb152fbd8d0746e34e762e16f996c1180d81dd02138fe","a535e4eaf08b34e8d1f5e04f188594b6d6ba44fb3a03336e71174ab501b8ca19":"c2d69ebba75e49e2fdc3d8a0d3a499554ae9e5730095870928163535ca3a333a","81a25a62702cbd9691f64d6b2d8cc51bfecbbd9400be77d3333a19e32c8dd6be":"04dcea5020e8230c41fe8ef2e14ea0ee759b86174b52b23e5a34e9d4bd01b140","f646ee363ac823e2e0c6e367bf6d1df5db1d50b78aea874c6e879c1ac4586913":"c24773e060610e12a4c08e63a8649e67ca55a598d8bcf729f13098a51fb0366d","f7f2dfd8c11f70c5111efbf474c3d7a834f50d99a11bd252e070f193be3fac69":"52d162432ab8937f7cd4bc121188619aca91293f5074c617703b19268b6dffbe","6e8504d3aa30bc8b8e68b9b730da2e00506bd27770f9bd37429a3e0e1834a82c":"96bfaa3c3850073588add5076ecd7a6331331a89df471ca344fd3537b04222dd","afdc29079f046ff88487ea7cbef7a043c3c9d9299a4b9fff86229dae70cee1a1":"cf8197f87f236baeef8164cb250538bc97b9e53457d4afb62c279808680b6735","e776dac4d12873f7f495c3657e9c88624ccf01325b62fc3d815aa0eac4c5f677":"7dae0eae01298bf9ac0b7c822a78e077526aa06e807e99f14fd8621eb154057e","caeb8df1ca33ee8ef381a5ffbf056ca2c8d4ac3281a5af94b5076feb76c23aa7":"1b06111d44cb504d63cbb3ac003974d4cdfeb3423c658b8aee3ae1e4a760be79","f274a6a6cc925a27bfa045aba9b9c6b0be938052b6233ac8b76794836198f8d7":"5f09d00da3f39fc52cb8a313f10aa915f931f208654596278825180404a83cf6","f3b8510702fcb5150c272f442a6ceb39fafad7152a8176c2755d023417c9898b":"aeec84f4c2989a129b865fd7f28a5af92a13af466bc32e6126503c79148d419a","6e1abbbb59e86b9a09c7ff78f6b85f1229a8a08620b94f4832c9247ec07ebb33":"c2636c991a4eb6cb684d63a1f476bb32b0a82ca31480d19de2ec7eb0c014e886","5cf6046666ebbfcb6954ab1f4d03f2e1f4fe1b3b92d535b3571d2a1098ecfea5":"1ed05274e7e12c45381d6828db578d71365f193f72dbc1fe712688e3e94d9de7","8afdabc91438b2f9cb731b36ab0fceb11c54a746bf3525032ff100b075c8ae66":"a430c58d8cf925e511395c9ddc721a34e5ebbe272a5fc569491b43fdf3ceb28f","fc601a2427bb20547c3cce07cc89e7ce10b1e0986016a38732027d277ea4280d":"55f756b1e8c2d622b6638c90e1c904300a5aecb94c7d0ccc73ed86799f094c81","f6d1f2d210759b792fe3c59576515f5ebdc5f617986d41519ee969863c870821":"f8e77619af19076fdf339b25c362505b958f6b36c6c732710a8a8cb77ebf67f7","e124483825b265d0e8094954ad1354f907e716194c230b8d3cb158d613d28c17":"dacf8d395ff36722da78c60a7c0dfdf4f43195d1a9bc859b03ef62ea84314d70","5b2f1c916aa6a2d74183316166c182ff15a940b868d7f6f2e466ea4937ac524a":"00d680bb770dc11f11b50dbe7841adc6f5f7c5d624b57cd24db515ccc86abbe5","09d0cead36619c4e8295c2073d10da8011d7615f2ea5bf061b51f54d56689207":"345fb6e4801b8c5cf40b706a6fbb6649c84258b5b51a9190d9241b1cb9505919","22587d4cc5ff6064f6d3477368b28850055dc115479f74077a19be4a795d64cc":"c5a84b814c6ba8c4d65db942cd50603fdc81d368ba964d4c7c7f6338b5c469a8","3c63d871fec6e65c4b0dd3ce93a82c5f8c0fca3d525818301fe91a0a0b4f6bba":"68f7014aa7bb8782c3b8603646ee5c31311518c9e878917bff81e770a7743296","ceef5fd9411fc1c163034667c4703bd0cddd82c992df0713b72fc4148d8429e5":"06cbfbd9244de4d95d3bf76ee902017ae2d44eb3f3e5a379795aebd845c471ed","b0e31a5e0cffa80348d906315af2a48336001692cf16be0e7f1ceaf9fe4e3ed3":"64324e745ad82ee947b3f27d1f9f6d121e895bb9de41587e47b8fac88c9a5e2f","b968c68f40221c45a44ed41c245016ebbd4b124f90e2f7fdfbc4d0120f74c3a8":"926a12bc0de33e22a6105b214fb4d9a9df1a9cab63d3c9208ae6fd7fd3539745","7a32360b346da13d2f4b7ce5c925d37cff5e8333ce116333ad1cb7a15284b35d":"2c1f24cbf8ff4f91e2858acf747d6d7c987a1e8a61a9c4d12ad7d590092640ce","c4f55b6b19012c2a11a85fb8c9acd8bc3f826a87aba4577af89514b71e4d22b0":"4c6da76f6878ed2c8760a781cc08de7463d6921e022979660f44f62a7bdd7e42","f5c9f35330765b345a5ffe101e64215675e7c51c0d5fa2ee4def34b68cae94f6":"d774079f081283460c5f2bfd23141beaac87a575e39ee4a4185ba6c298ee8814","47d4ff040283bafa6e42729ea222da2ee4906c7fccbcf66bbf85ccc86edb5588":"753f8fbc0cc9564837b9f2c8fdd3ae334830073b0871dcc3ff5362a54ae56313","78b774e89940e6dfd50aa3c12a71fc50ca53e5e4a393c11b143596eea89f542d":"db80bf5ea577e97e92e5b3f47c97da067f63952b4a8dd2efbc27eab5f8448f98","1fad0793974cf20c4c41805bb71008aa2a15ddd41a3bbc6e9b9b5d86a2aa0806":"f3073ab0a249069195f215e77398c36cb11a98f995a7858b8eb589d47924697e","9f34c159cc39f7fff90e02c711fdbdb779c9aeab72f9f56cb1e8ecebf9e87e75":"0ebcc80df31c6f0853d1190d0cd9d5ac9b070b2e3a351792672cff2208e6de41","49d67b5ab1d7418dc9384c7dbd2974db9e86e0784b806566170db69b22d5f8f6":"eea2eaae90fdf1a3e7ab864d883bf9487cd4b0dad393dab5f62f6a97fb9e3c4f","4a8ddb144aff9ec307d4a3e2ae421e042c86b2dbe9f89e13ae94de453041d07e":"f8cf936703c0db5c3907e5ec6237845ff93f1ad2fc3029a251ef5ef7309ac437","cb7e9a2cf7f2de27b33a91b3fb0f1c31dfef3ce6c285ce15e6db4f8c3cff6372":"21c8a0cfe038236ae66a019496c05a8b2c72c324ae5596a7dbb82004cffc292e","be50d83a5b316ac92e7ba60949232131fcd707c25656d093b65264907d615d81":"9cf7f4b388e5016556e13e27a1446d68eb5a78f2d1576df0549384d995f3c9d2","3ede02b907d4839f97329a70eb31b4001b2096a280a1e5de1e0ddaa2b90cf754":"6340d156e8b300ee273ded33cc23ec1bc9fd927e8ffa91132df33213b85a9d16","8bc28ff68b4321826b2c3cd35ec12a7517d766f049d6d85d9a36c746a939ad79":"8433d0995d823362ffc9f56d1b2cf61fa6031a7c24b9b6e862a09e721b33eff4","37e7593565380b5385a367eabda8006f59b27e4b0fb57f5868e3af88f1c858a6":"2847af49a374eb386a9b162d789a5f9c2c1f6f5c826303b158c76c46535303b8","88a54f4a00498938da7fb29e1927517eaa55e7fdc43373e637af3af2a779861e":"8bd6c13eae9d53fd3b02e467d51a92a6c2de65c6dc1899caeabd06e476ed4860","cd7366b002f890a34ffc0d683d455c9f244f8328ed8f36b25ba2022650509f1f":"b903e24226e2f52cd45befa8751282985726946965539bd0279dca1be43fd543","13f3a654bb05291093292a9d7265a7c76df475a5b707e4e033e7c67ab679917f":"d4328fb8690da6f2b4645671d4c819ac8612ba65f6781a5462807f0fdfe68774","0f230bf4905e09166f77358ea3cdec2c1c8cf0014e6d1a4d2edaff72f0cacb6c":"5306c2ff467013ecece4319062ffc748de1c09e8162060cc7fae4c2a68df5af6","2961e756517f6d358719ed6905a4cab4f8d2174220c9eae20cd1140a0a9cb2dc":"975e655169accfbc2ffee87d7a71194c87a6be8425609b5f5e64f74fb8619608","7ff2c2e42e1d45b1a5b1d853954465c2f4b3ea4bd770a68aabe8aac14f0469ad":"d70b555914c7b31836fe58a8e9aec535283fc4f4d7b7a923ad22dd02b16fe456","a92ba6ded75f4cda13c240453e5816f3ca9b94676469e8b9d947cd91e1682498":"c97e7a31072ec05c9aeb79a8d70c8e4f3ab356bb55ad2634136397deaedbc4f0","d403e7c94c900eef3422c93d5d0d7971858d816959248e9ad01ec287fe4c53e4":"8db207582cf52bac4e5f6bd2ea77154d0f9ee57f59ef84a98f23c4ab52c73c4e","cec3625d2d402946850c69b2ee9084d6482ec0c9ad0fe465621a9d480adb176e":"d1157f16f1724ee139791f181c5e9693213a25b0a18344aebe1a0b45a0f28e07"}
ALREADY_FIXED = set(REPAIR_TARGETS.values())
ALREADY_FIXED = ALREADY_FIXED | {'5283e69f0101288d518f16d0b456b625b3d2f57d56f4f3cc3edee448970c788c'}  # q2-fluidd-reconnect v0.1.0


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def main():
    for name, checksum in ANCHORS.items():
        p = Path(name)
        if not p.is_file() or p.is_symlink() or sha(p) not in (APPROVED_CLIENTS if name == CLIENT_PATH else (checksum,)):
            raise RuntimeError('Firmware/update detected: ' + name + '; automatic repair stopped')
    root = Path('/home/qidi/fluidd')
    html = (root / 'index.html').read_text()
    matches = re.findall(r'src="([^"]*index-[^"]+\.js)"', html)
    if len(matches) != 1:
        raise RuntimeError('Unknown active Fluidd bundle')
    target = root / matches[0].lstrip('./')
    expected = root / 'assets/index-DlFvHGAh.js'
    if target != expected or target.is_symlink() or not target.is_file():
        raise RuntimeError('Active bundle changed; repair stopped')
    checksum = sha(target)
    if checksum in ALREADY_FIXED:
        print('Already fixed; no changes')
        return
    if checksum not in REPAIR_TARGETS:
        raise RuntimeError('Bundle differs from the known original; repair stopped')
    base = 'http://127.0.0.1:7125'
    with urlopen(base + '/printer/objects/query?webhooks&print_stats&pause_resume&virtual_sdcard&motion_report&heaters', timeout=5) as r:
        s = json.load(r)['result']['status']
    if (s['webhooks']['state'] != 'ready' or s['print_stats']['state'] not in ('standby', 'complete', 'cancelled')
            or s['pause_resume']['is_paused'] or s['virtual_sdcard']['is_active']):
        raise RuntimeError('Printer busy; repair deferred')
    for key in ['live_velocity', 'live_extruder_velocity']:
        value = float(s['motion_report'][key])
        if not math.isfinite(value) or abs(value) > 1e-5:
            raise RuntimeError('Printer moving; repair deferred')
    names = s['heaters']['available_heaters']
    if names:
        with urlopen(base + '/printer/objects/query?' + urlencode([(n, '') for n in names]), timeout=5) as r:
            heaters = json.load(r)['result']['status']
        if any(float(heaters[n]['target']) != 0 for n in names):
            raise RuntimeError('Heater target active; repair deferred')
    before = target.read_bytes()
    broken = (b'this.$store.getters["files/getCanPrint"]("gcodes",t)'
              b'&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}}saveConfigAndRestart')
    fixed = (b'this.$store.getters["files/getCanPrint"]("gcodes",t)'
             b'&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}'
             b'else this.uploadFile(e,"","gcodes",!0)}saveConfigAndRestart')
    if before.count(broken) != 1:
        raise RuntimeError('Unexpected JavaScript; repair stopped')
    after = before.replace(broken, fixed, 1)
    expected_hash = REPAIR_TARGETS[checksum]
    if hashlib.sha256(after).hexdigest() != expected_hash:
        raise RuntimeError('Patched bundle checksum mismatch')
    st = target.stat()
    fd, temporary = tempfile.mkstemp(prefix='.q2-send-print-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(after)
            os.fchmod(f.fileno(), st.st_mode & 0o7777)
            os.fchown(f.fileno(), st.st_uid, st.st_gid)
            f.flush();os.fsync(f.fileno())
        if target.read_bytes() != before:
            raise RuntimeError('Bundle changed while preparing repair')
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('Send & Print fixed; no print started')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP: ' + str(error), file=sys.stderr)
        sys.exit(1)

Q2_SEND_PRINT_GUARD
