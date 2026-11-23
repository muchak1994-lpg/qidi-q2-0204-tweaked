# Swap / zram na QIDI Q2 - raport z badania (2026-11-22)

Plik NIEŚLEDZONY: nie commitować, nie wysyłać na GitHub (decyzja właściciela). Napisany bez żadnego kontaktu z drukarką
(zero SSH, curl, Moonrakera, Klippera): tylko pliki na dysku, kod Valve Oil, archiwa z wcześniejszych sesji i strony w sieci.
Nic nie pobrano (żadnego jądra, obrazu ani źródeł).

Oznaczenia: **DOWÓD** = widziane na prawdziwej drukarce Q2 lub w kodzie/pliku, który można otworzyć; **WNIOSEK** = wynika
z dowodów, ale nikt tego nie sprawdził wprost; **HIPOTEZA** = prawdopodobne, niesprawdzone; **BRAK DANYCH** = nie wiemy.

---

## 0. Wynik w pięciu zdaniach

1. Jądro Q2 prawie na pewno jest zbudowane **bez swapu w ogóle** (bez opcji `CONFIG_SWAP`). Na Q2 nie ma nawet pliku `/proc/swaps`
   (DOWÓD z odczytu 23.10.2026). Bez tego nie da się włączyć żadnego swapu: ani zram, ani pliku na eMMC, ani zswap.
2. Moduły zram z Valve Oil niczego tu nie dadzą, nawet gdyby się załadowały: Valve Oil robi swap na Max 4 / Plus 5 / Smart 5, których
   jądra swap **mają** (tylko bez zram). Q2 ma starsze jądro (#1, luty 2025) i inną konfigurację.
3. Jedyna droga do swapu to **wymiana jądra** (partycja `boot` na eMMC). To zmiana, której nie da się zrobić jako zwykły moduł
   tego projektu i która może zostawić drukarkę niedziałającą. Nie polecam jej jako funkcji dla użytkowników.
4. Zacinanie kamery, rozłączenia Fluidd i błędy klatek timelapse przy ~30-40 MB wolnej pamięci to najpewniej ten sam mechanizm,
   który Valve Oil opisał na Max 4 (Klipper czeka kilka sekund, bo jądro wyrzuca z pamięci kod programów i czyta go z eMMC).
   To jest **WNIOSEK z analogii**, na Q2 nie zmierzony (patrz sekcja 7: jak to sprawdzić bez ryzyka).
5. Co da się zrobić na obecnym jądrze: zmniejszyć zużycie pamięci (głównie AI w `algo_app`), ustawić `oom_score_adj`, ewentualnie
   mały nadzorca pamięci. To są małe poprawki, nie zastępują swapu. Szczegóły w sekcji 4.

---

## 1. Co wiemy o Q2 (z źródłami)

| Fakt | Status | Źródło |
|---|---|---|
| SoC: Rockchip RK3308 (4 rdzenie wg zlecenia; u Max 4/Plus 5 to RK3308B-S z Cortex-A35), `compatible` = `rockchip,rk3308bs-evb-amic-v11 rockchip,rk3308` (to samo co Max 4 i Plus 5) | DOWÓD | `QIDI_Q2_historia_do_20261110.zip` -> `QIDI_Q2_TMC_INSTALL_20261028/ARCHIVED.json`; Valve Oil `openspec/observations/qidi-platform.md` (Max 4/Plus 5/Smart 5) |
| Pamięć: `MemTotal` 498 752 kB (487 MB), CMA 32 768 kB, brak swapu (`SwapTotal 0`) | DOWÓD | `QIDI_Q2_AI_BALANCED_LIVE_20261017/*.json`, `QIDI_Q2_AI_BOOT_COMM_LIVE_20261018/boot-readonly-*.json` |
| Jądro: `Linux linaro-alip 5.10.160 #1 SMP PREEMPT Thu Feb 27 14:22:34 CST 2025 aarch64`; wiersz poleceń w stylu Androida (`androidboot.*`, `root=PARTUUID=...`) | DOWÓD | `QIDI_Q2_TMC_INSTALL_20261028/AFTER_PRIVATE.json` (log Xorg), ten sam plik |
| **`/proc/swaps` nie istnieje** | DOWÓD | `QIDI_Q2_RAM_DETAIL_20261023/RESULT_PL.md` ("/proc/swaps nie istnieje: pierwszy pomocniczy odczyt zakładał jego obecność i przerwał się") |
| W `/proc/kallsyms` tylko słaby symbol `__arm64_sys_swapon`, brak `swap_writepage` i `zram_init` | DOWÓD pośredni (relacja ze zlecenia; surowego pliku kallsyms nie ma na dysku) | zlecenie tej sesji |
| Brak PSI (`/proc/pressure`), brak kontrolera pamięci w cgroup (`/proc/cgroups`: tylko cpuset, cpu, cpuacct, devices, freezer; `cgroup.controllers`: `cpuset cpu`), brak przestrzeni nazw sieci | DOWÓD | `QIDI_Q2_AI_IMAGE_TEST_20261015/RESULT.md` + `memory-control-evidence.json`; `RESULT_PL.md` z 23.10 |
| Brak `/proc/config.gz` | DOWÓD | `QIDI_Q2_AI_IMAGE_TEST_20261015/memory-control-evidence.json` (`kernel_memory_config: null`) |
| Aktualizacje QIDI (02.04, 03.02) **nie zawierają jądra**: to pakiety Debiana (`control.tar.xz` + `data.tar.xz`), w środku 8 695 / 8 819 pozycji, zero `/boot`, `/lib/modules`, `*.ko`; `preinst`/`postinst` nie zapisują partycji | DOWÓD (przejrzane w tej sesji: `work/stock/data.tar.xz` z 02.04 i `downloads/QD_Q2_01.01.03.02_...zip`) | pliki na dysku |
| Jądro pochodzi więc z fabrycznego obrazu eMMC (u nas `KLP_IMG_QD_Q2_V1.0.1_20250505_Release`, 1,9 GB w 7z, 5,66 GB po rozpakowaniu, link w wiki QIDI -> Google Drive) | WNIOSEK | `docs/RECOVERY.md`; wiki.qidi3d.com/en/Memo/flash-emmc |
| `MemoryHigh=200M` / `MemoryMax=250M` w `algo_app.service` **nie działają** (nie ma kontrolera pamięci) | WNIOSEK z dowodu wyżej (zgadza się z `RESULT.md` z 16.10) | `work/stock/.../algo_app.service` |
| Dolny próg pamięci jądra: `min` 703 stron = ok. 2,8 MB (`min_free_kbytes` ok. 2806) | DOWÓD | `QIDI_Q2_RAM_DETAIL_20261023/KERNEL_MEMORY_READ.json` (zoneinfo) |
| `tmpfs`/`Shmem` w spoczynku ok. 0,7 MB; w druku nie mierzone | DOWÓD (spoczynek) | `native-*.json` z 17.10 |
| `workingset_refault_file` = 4 314 403 w jednym zrzucie zoneinfo (spoczynek, czas pracy nieznany) | DOWÓD (liczba), znaczenie HIPOTEZA | `KERNEL_MEMORY_READ.json` |
| Prawdziwy kill przez OOM: 24.10.2026 09:05 zabity `python3` (root, anon 219 656 kB); który to był proces - nie ustalono | DOWÓD (log), przyczyna BRAK DANYCH | `QIDI_Q2_CLIENT_TRIAL_20261024/PREPARE_FAILURE_CHECK.json` |
| `algo_app`: w spoczynku PSS ok. 90 MB, w druku RSS ok. 190-215 MB (wg właściciela: ~210 MB, wolne 30-40 MB); model makaronu ok. +114 MB, obce przedmioty ok. +17 MB | DOWÓD / dane właściciela | `RAM_DETAIL` z 23.10; `CLAUDE.local.md` |
| Root `/` zamontowany `sync` (świadoma decyzja) - małe zapisy wolne (ok. 2,5 ms) | DOWÓD | `docs/FIXES.md`, `PAMIEC_02.04_do_importu.md` |

---

## 2. Pytanie 1: czy jądro Q2 ma swap / zram i jak to poznać bez drukarki

**Odpowiedź: swapu nie ma (DOWÓD silny), zram nie ma (DOWÓD: brak `zram_init` w kallsyms wg relacji; nie ma modułów).**

Dlaczego brak pliku `/proc/swaps` i słaby symbol `swapon` to prawie pewny dowód (sprawdziłem w kodzie Linuksa 5.10.160 z Rockchipa,
w tym samym drzewie, które Valve Oil przypina w `scripts/build_kernel_modules.py`, commit `709c51c6...`):

- `mm/Makefile` linia 70: `obj-$(CONFIG_SWAP) += page_io.o swap_state.o swapfile.o swap_slots.o`. Bez `CONFIG_SWAP` plik `swapfile.c` w ogóle się nie kompiluje.
- `mm/swapfile.c` linie 2886-2891: to właśnie tam `procswaps_init()` tworzy `/proc/swaps`. Brak pliku = brak tego kodu.
- `kernel/sys_ni.c` linie 274-275: `COND_SYSCALL(swapon); COND_SYSCALL(swapoff);` - to rodzi **słaby** symbol `__arm64_sys_swapon`, który
  znika (staje się zwykłym, mocnym), gdy jest prawdziwy `swapfile.c`. Q2 ma tylko słaby: czyli prawdziwego `swapon` nie ma.
- `swap_writepage` jest w `page_io.c` (też tylko z `CONFIG_SWAP`): brak w kallsyms, spójnie.
- `CONFIG_SWAP` jest opcją "tak/nie" (nie "moduł"), więc **nie da się jej dołożyć modułem**. Jądro trzeba zbudować od nowa.

Zastrzeżenie: źródła QIDI nie są publiczne (BRAK DANYCH, patrz 6), więc sprawdziłem to na drzewie Rockchipa/Armbian o tej samej
wersji 5.10.160; QIDI mogło coś zmienić, ale jedna nasza obserwacja (brak `/proc/swaps`) wystarcza.

**Jak to rozpoznać z samego pliku jądra, gdyby go kiedyś mieć (bez drukarki):**
1. Obraz z paczek QIDI odpada (nie zawiera jądra, patrz tabela). Jądro jest tylko na partycji `boot` fabrycznego obrazu eMMC albo na żywej drukarce.
   Wg Valve Oil (na Max 4 / Plus 5) `boot` to obraz w formacie Android boot image z `Image` skompresowanym LZ4. Na Q2 to HIPOTEZA
   (wskazuje na to wiersz poleceń `androidboot.*`).
2. Z obrazu wyciąga się `Image` (rozpakować LZ4) i szuka w nim napisów, które występują tylko przy `CONFIG_SWAP`:
   `Adding %uk swap on %s` , `Unable to find swap-space signature`, nagłówek `Filename ... Type ... Size ... Used ... Priority`
   oraz nazwy `swap_ra` / `swap_ra_hit` w tekstach liczników `/proc/vmstat`. Dla zram: `zram%d`, `zram: Added device`.
   Wystarczy `strings` i `grep`; Ghidra nie jest tu potrzebna (jest przydatna dopiero do porównań kodu, jak w `docs/BOX_CODE_AUDIT.md`).
3. Wbudowanej konfiguracji (`IKCONFIG`) nie ma (brak `/proc/config.gz`), więc `config` z obrazu się nie odczyta.
4. Dokładniej: tablicę symboli (`kallsyms`) można wyciągnąć z `Image` tak, jak zrobił to Valve Oil (czytają `__ksymtab_strings`).
   Albo po prostu na żywej drukarce: `grep -c swap_writepage /proc/kallsyms` (sekcja 7).

Ponieważ już mamy dwa niezależne dowody z żywej drukarki (brak `/proc/swaps`, słaby `swapon`), **pobieranie 1,9 GB obrazu tylko po to,
żeby to samo potwierdzić, nie jest potrzebne**. Obraz byłby potrzebny dopiero do budowy własnego jądra (sekcja 4, droga E).

---

## 3. Pytanie 2: czy moduły zram z Valve Oil mogłyby się załadować na Q2

**Krótko: nie, i nie ma po co. Technicznie `insmod` mógłby się udać, ale to byłoby gorsze (patrz niżej).**

Co robi Valve Oil (`kernel/README.md`, `scripts/build_kernel_modules.py`, `installer/package.yaml` klucz `zram_swap`):
- Jądra Max 4 / Plus 5 / Smart 5 mają swap, nie mają zram. Moduły `lz4_compress`, `lz4_decompress`, `lz4`, `zsmalloc`, `zram` są zbudowane
  z drzewa Armbian `linux-rockchip` (5.10.160) na konfiguracji `kernel/qidi_kernel_defconfig`, którą odtworzyli z `/proc/kallsyms` drukarki
  (po zbudowaniu ich `Image` różni się od `Image` QIDI o 66 bajtów).
- Jądro **nie ma `MODVERSIONS`**: przy ładowaniu sprawdzany jest tylko ciąg vermagic `5.10.160 SMP preempt mod_unload aarch64`,
  który **nie zawiera numeru ani daty builda**. Czyli jądro nie obroni się samo przed modułem zbudowanym pod inny układ struktur.
  Dlatego Valve Oil sam pilnuje dokładnej wersji: `/proc/sys/kernel/osrelease` i `/proc/sys/kernel/version` muszą być jednym z trzech
  znanych buildów (`#4` Max 4, `#3` Plus 5, `#15` Smart 5), inaczej niczego nie ładuje. Dla `#3` i `#15` sprawdzili osobno, że `Image` różni się od `#4`
  tylko napisem wersji i identyfikatorem builda (173 bajty / 76 bajtów), a wszystkie symbole mają te same nazwy i adresy.
- Q2 ma **inny, starszy build**: `#1 ... Thu Feb 27 14:22:34 CST 2025` (Max 4 `#4` jest z września 2025). Nikt nie porównał jego `Image` z
  `#4`. Mamy za to dowód, że **różni się realnie, a nie tylko napisem**: Max 4 / Plus 5 mają swap (Valve Oil odczytał go z ich kallsyms i na nim testował),
  a Q2 nie ma. Różnice w konfiguracji = możliwe różne układy struktur wewnątrz jądra.

Co by było po `insmod` na Q2 (WNIOSEK, nie testowane, i nie powinno być testowane na drukarce):
- vermagic pasuje (ten sam ciąg), więc jądro mogłoby moduły przyjąć; brak `MODVERSIONS` oznacza, że nic by ich nie zatrzymało.
- Powstałoby urządzenie blokowe `/dev/zram0`, ale `swapon` na Q2 zwróci błąd "funkcja niezaimplementowana" (to atrapa `sys_ni_syscall`).
  Czyli efekt dla pamięci: zero. A ryzyko: zły układ struktur = zawieszenie albo "oops" jądra w czasie druku.
- Zram jako zwykły dysk w RAM (np. na `/tmp`) też nic nie da: `tmpfs`/`Shmem` to ok. 0,7 MB w spoczynku, czyli nie ma czego kompresować
  (głównym zużyciem są "anonimowe" sterty programów, nie pliki w pamięci).

Zbudowanie **własnych** modułów pod dokładny build Q2 (droga a) wymaga: (1) dokładnej konfiguracji jądra Q2 (nie mamy; odtwarza się ją z kallsyms
+ obrazu `Image`, jak zrobił Valve Oil, kilka dni pracy), (2) i tak jądra z `CONFIG_SWAP`, którego Q2 nie ma. Punkt (2) przekreśla drogę a).

---

## 4. Pytanie 3: realistyczne drogi

| Droga | Da się? | Dowód / uzasadnienie |
|---|---|---|
| **a) Moduły zram pod build Q2 + `insmod`, bez flashowania** | **NIE** | Brak `CONFIG_SWAP`: `swapon` nie istnieje (sekcje 2 i 3). Moduły zasilałyby tylko dysk w RAM. |
| **b) Plik swap na eMMC** | **NIE** | Ten sam powód. Poza tym, nawet gdyby swap był: zapisy na eMMC przy `iowait` 23-29 % i `/` w trybie `sync` byłyby wolne, a eMMC się zużywa (HIPOTEZA; zram jest tu dużo lepszy). |
| **c) zswap** | **NIE** | zswap to pośrednik przy zrzucaniu stron do swapu, więc też wymaga `CONFIG_SWAP` (a jeszcze `FRONTSWAP`/`ZSWAP` w jądrze). `mm/Makefile`: `frontswap.o`, `zswap.o` osobne opcje. |
| **d) Zmniejszenie zużycia pamięci na obecnym jądrze** | **TAK, ale to półśrodki** | Patrz niżej. |
| **e) Własne jądro (`CONFIG_SWAP`+`ZRAM`) wgrane na partycję `boot`** | Teoretycznie tak | Patrz niżej: trudne, ryzykowne, nie jako funkcja projektu. |

### d) Co można zrobić bez swapu (każda pozycja: do sprawdzenia pomiarem, żadna nie jest sprawdzona na Q2)

1. **`swappiness`**: bez swapu nic nie robi (jądro nie ma gdzie zrzucić stron anonimowych; zostaje mu wyrzucanie kodu programów i cache plików). Nie ruszać.
2. **cgroup `memory.high` / `memory.min` dla Klippera i Moonrakera**: **niemożliwe**, bo jądro nie ma kontrolera pamięci (DOWÓD). Z tego samego powodu
   `MemoryHigh=200M` / `MemoryMax=250M` w `algo_app.service` jest bez efektu: `algo_app` może urosnąć powyżej 250 MB bez żadnego hamulca (zgadza się z obserwacją 214 MB).
3. **`oom_score_adj`**: działa (jądro ma zabójcę OOM, były prawdziwe zabicia). Ustawić `algo_app` na np. +500, a Klippera/Moonrakera na -500..-900,
   żeby przy braku pamięci zginęło AI, a nie Klipper. Uwaga: `algo_app` ma `Restart=always`, `RestartSec=15`, a start AI dokłada ok. +100 MB, więc przy stale
   zajętej pamięci mógłby się zapętlić (zabity -> start -> zabity). **HIPOTEZA**, wymaga przemyślenia. Chroni tylko przy samym OOM, nie przy zwolnieniach przed OOM.
4. **Zmniejszenie AI** (największa dźwignia, ale decyzja właściciela, który zostawił AI włączone): model makaronu ok. +114 MB, obce przedmioty ok. +17 MB.
   Wyłączenie jednego z nich daje więcej wolnej pamięci niż jakikolwiek "tuning". Koszt: utrata wykrywania.
5. **Restart `algo_app` po druku** (z notatek: ok. 100 MB mniej po restarcie): pomaga na spoczynku, ale zacinanie dzieje się **w druku**, więc to
   nie leczy problemu. Nie polecam jako leku.
6. **`vm.min_free_kbytes` (obecnie ok. 2,8 MB), `vm.watermark_scale_factor`, `vm.vfs_cache_pressure`**: zmiany przesuwają, kiedy `kswapd` zaczyna pracę i ile
   pamięci zostaje na cache. Przy braku swapu cache plików (w tym kod Pythona Klippera) jest **jedyną** rzeczą, którą jądro może oddać, więc zwiększenie
   rezerwy wolnej pamięci zabiera właśnie to, czego Klipper potrzebuje. Efekt niejednoznaczny: **HIPOTEZA**, nie zmieniać bez pomiaru
   (`workingset_refault_file`, sekcja 7). `vfs_cache_pressure` dotyczy tylko dentry/inode, efekt mały.
7. **`mlock` kodu Klippera** (wątek: Klipper ma stały, ok. 41 MB zestaw stron; gdyby je "przypiąć", jądro nie mogłoby ich wyrzucać): ciekawe, ale
   łatwo przesadzić. `mlockall(MCL_CURRENT)` przypina też puste stosy wątków (8 MB wirtualne na wątek), więc mogłoby zabrać dziesiątki MB, a jeśli
   łącznie pamięci anonimowej zabraknie, kończy się to OOM zamiast zwolnień. **HIPOTEZA, nie zaczynać bez eksperymentu na stole i bez druku.**
8. **Nadzorca typu `earlyoom`** (działa na `/proc/meminfo`, nie potrzebuje PSI ani swapu): zabijałby `algo_app`, zanim pamięci zabraknie. Ma sens tylko razem z
   pkt 3 i ze sprawdzeniem pętli restartów. Wada: kill AI w trakcie druku = utrata detekcji (ale lepsze niż zatrzymanie Klippera). **HIPOTEZA.**
9. **Zmniejszenie klatek timelapse / wyłączenie kamery w Fluidd w druku**: kamera (crowsnest + ustreamer) to osobne procesy; niższa rozdzielczość lub
   mniej klatek zmniejsza ruch. Nie mierzone (BRAK DANYCH o rozmiarach tych procesów w druku).
10. **Inne rzeczy, które zjadają pamięć w spoczynku** (z `RESULT_PL.md`): `journald` 27 MB, Tailscale 25,8 MB (to dostęp zdalny właściciela). Nic nie ruszać bez pomiaru.
11. **Fragmentacja**: w `dmesg` były trzy błędy `page allocation failure order:7` (wg `RESULT_PL.md`; padło przy zapisie zrzutu awarii klienta). Jądro Valve Oil/Max 4 ma wyłączone
    `CONFIG_COMPACTION` (`kernel/qidi_kernel_defconfig`); dla Q2 nie sprawdzone. Bez własnego jądra nic z tym nie zrobimy.

### e) Własne jądro: co by trzeba (tylko opis, nie rekomendacja)

1. Odtworzyć konfigurację jądra Q2 jak Valve Oil dla Max 4: zdobyć `Image` Q2 (partycja `boot` z fabrycznego obrazu 1,9 GB albo odczyt z drukarki) i `kallsyms`,
   zbudować `rk3308_linux_defconfig` + dodatki, porównać symbole z `Image` (u nich 3 z 37 000 różnic). Do tego dołożyć `SWAP`, `ZRAM`, `ZSMALLOC`, `CRYPTO_LZ4`.
2. Zbudować w Dockerze toolchainem Arm GNU 10.3-2021.07 (ten sam co QIDI), spakować do formatu boot image, zachowując oryginalny dtb/zasoby Q2 (inny ekran).
3. Wgrać na partycję `boot` drukarki (zapis na eMMC jako root). Jeśli jądro się nie uruchomi, drukarka nie wstanie; powrót to RKDevTool przez port USB-C SOC
   (`docs/RECOVERY.md`) albo wyjęcie modułu eMMC i zapis z komputera. Przy niedziałającym jądrze ADB też nie działa, więc potrzebny byłby tryb Maskrom.
4. Moduły QIDI w `/lib/modules` (Wi-Fi, Bluetooth) mają to samo vermagic i nie ma `MODVERSIONS`, więc załadują się, ale ewentualna różnica układu struktur po zmianie
   konfiguracji dałaby awarie trudne do zdiagnozowania (HIPOTEZA; Valve Oil sprawdzał to tylko dla swojego, identycznego jądra).
5. Aktualizacje QIDI (.deb) jądra nie ruszają, więc własne jądro przetrwałoby aktualizację; zginęłoby przy ponownym wgraniu fabrycznego obrazu.
6. Prawnie: jądro to GPL-2.0; źródła QIDI nie są publiczne (Valve Oil: "QIDI publishes neither its kernel source nor its configuration"; w repo `QIDITECH` nie ma jądra,
   sprawdzone listą repozytoriów), więc budujemy z drzewa Armbian, nie z kodu QIDI.

**Moja ocena:** to praca na tygodnie, z realnym ryzykiem niedziałającej drukarki, dla jednej konkretnej drukarki, i nie nadaje się do wspólnego instalatora.
Jedyna rozsądna wersja to eksperyment na **zapasowym module eMMC** (wymienny, ok. 8 GB+, plus czytnik), z obrazem fabrycznym i własnym jądrem, bez
dotykania eMMC właściciela. Do tego moment wymaga zgody na pobranie obrazu (nazwa `KLP_IMG_QD_Q2_V1.0.1_20250505_Release.7z`, źródło: folder Google Drive z wiki QIDI,
1 900 160 385 bajtów wg `docs/RECOVERY.md`) i jest do zrobienia dopiero, gdy właściciel zdecyduje, że warto.

---

## 5. Czy to ma sens jako moduł w `modules/`

- **zram / swap: nie.** Nie ma jak go włączyć na obecnym jądrze; moduł musiałby dostarczać jądro, a tego instalator nie robi i nie powinien.
- **Moduł "diagnostyka pamięci" (tylko odczyt, np. komenda `TWEAKED_MEM_REPORT` w Klipperze albo skrypt na PC)**: tak, mało ryzykowny, zbiera liczniki z `/proc`
  (sekcja 7) i pozwala na końcu rozstrzygnąć, co naprawdę powoduje zacięcia. To najlepszy pierwszy krok.
- **Nadzorca pamięci / `oom_score_adj`**: dopiero po pomiarach i tylko jako opcjonalny moduł.
- **Zgłoszenie do QIDI** (decyzja właściciela, my niczego nie wysyłamy): prośba w `QIDITECH/QIDI_Q2` o włączenie `CONFIG_SWAP` i zram w jądrze Q2, tak jak
  mają Max 4 / Plus 5 / Smart 5 (Valve Oil pokazał, że to usuwa zatrzymania Klippera: najdłuższe opóźnienie 405 ms -> 4 ms, błędy stron +2707 -> +36),
  oraz prośba o źródła jądra (GPL). Nie znalazłem w `QIDITECH/QIDI_Q2` żadnego takiego zgłoszenia (szukałem: kernel, RAM, memory, oom) - BRAK takiego zgłoszenia, więc byłoby pierwsze.

---

## 6. Co wiedzą inni (szukanie w sieci)

- **Valve Oil, PR #195 "Add zram swap..." (2026-11-03)** opisuje dokładnie ten sam objaw na Max 4: 486 MB RAM, bez swapu, `algo_app` 189 MB, dostępne 24-35 MB,
  `kswapd0` zajęty, proces Klippera stał 11 s, kończyło się to `MCU 'mcu' shutdown: Missed scheduling of next digital out event`. To ten sam SoC (RK3308), ta sama pamięć
  i ten sam `algo_app`, więc **mechanizm na Q2 jest bardzo prawdopodobny** (WNIOSEK). Wyniki ich testu (jeden pomiar na jednej drukarce, jądro Max 4):
  najdłuższe opóźnienie timera 405 ms -> 4 ms, główne błędy stron Klippera +2707 -> +36, proces testowy bez zram zabity przez OOM, z zram przeżył.
- Valve Oil dla Max 4/Plus 5 podaje też: brak kontrolera pamięci w cgroup, brak PSI, brak `/proc/config.gz`, `/` jako `sync` (to samo co Q2).
- **Wiki społeczności Q2** (`qidi-community/q2-wiki`): są strony o flashowaniu, kamerach, siatce, Spoolman itd.; **nic o swapie, zram ani pamięci**.
- **`QIDITECH/QIDI_Q2` (issues)**: nie ma zgłoszenia o swapie/zram/pamięci (wyszukiwanie: memory, oom, kernel). Są zgłoszenia o zawieszeniu ekranu (#7)
  i MCU Boxa (#13), bez związku z pamięcią.
- **Repozytoria QIDITECH** (`QIDI_Q2`, `QIDI_MAX4`, `QIDI_Q1_Pro`, `klipper`, `moonraker`, ...) zawierają Klipper, Moonraker, Fluidd i konfiguracje, **nie jądro**.
- **Obce projekty Q2/Q1 Pro** (`53Aries/Q2-Klipper`, `cedbossneo/q2-offload`, `prestonbrown/helixscreen`): nic o swapie na Q2;
  nie przeglądałem ich do końca (BRAK DANYCH, ale wyniki wyszukiwania "qidi zram" wskazywały wyłącznie na Valve Oil).

Nic z kodu Valve Oil nie trafiło do naszego repozytorium. Gdyby kiedyś trafiło (np. `build_kernel_modules.py` jako wzór), trzeba dopisać źródło
`thelegendtubaguy/Valve-Oil` i licencję GPL-3.0 (moduły jądra: GPL-2.0-only).

---

## 7. Co sprawdzić na drukarce przy bezpiecznym oknie (tylko odczyt)

Wykonać dopiero, gdy nie ma druku i właściciel zezwoli (w tej sesji niczego nie uruchamiałem). Wszystko poniżej niczego nie zmienia;
pełny numer seryjny z wiersza poleceń jądra nie powinien trafić do plików w repozytorium.

**A. Czy jądro ma swap / zram (potwierdzenie dowodów z października)**
```bash
ls -l /proc/swaps 2>&1                               # oczekiwane: No such file or directory
cat /proc/version
cat /proc/sys/kernel/osrelease /proc/sys/kernel/version
sudo -n grep -E ' (swap_writepage|__arm64_sys_swapon|sys_swapon|zram_init|zs_create_pool|zswap_init)$' /proc/kallsyms
sudo -n grep -c . /proc/kallsyms                      # liczba symboli (do porównania z jądrami Max 4 / Plus 5, Valve Oil podaje 42 585 dla Smart 5)
grep -E 'swap_ra|nr_zspages|pswp|oom_kill' /proc/vmstat /proc/zoneinfo | head
cat /proc/cgroups; cat /sys/fs/cgroup/cgroup.controllers; ls /proc/pressure 2>&1
cat /proc/device-tree/compatible | tr '\0' ' '; echo; cat /proc/device-tree/model 2>/dev/null | tr '\0' ' '; echo
sed 's/androidboot.serialno=[^ ]*/androidboot.serialno=X/' /proc/cmdline
ls /lib/modules; ls /lib/modules/$(uname -r) 2>&1 | head
lsmod | head -30
```

**B. Ustawienia pamięci**
```bash
cat /proc/sys/vm/swappiness /proc/sys/vm/min_free_kbytes /proc/sys/vm/vfs_cache_pressure /proc/sys/vm/watermark_scale_factor
cat /proc/sys/vm/overcommit_memory /proc/sys/vm/dirty_ratio /proc/sys/vm/dirty_background_ratio
grep -E 'MemTotal|MemAvailable|MemFree|^Cached|Buffers|Shmem|Mlocked|Unevictable|AnonPages|Slab|SReclaimable|CmaTotal|CmaFree' /proc/meminfo
df -h / /tmp /dev/shm /run /var/log; mount | grep -E ' / | tmpfs '
systemctl is-enabled lightdm 2>&1; systemctl is-active lightdm 2>&1   # w logach było: X nie wstaje (Fatal server error); sprawdzić, czy to się powtarza
```

**C. Układ partycji (do ewentualnej drogi e; tylko odczyt)**
```bash
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
ls -l /dev/block/by-name
sudo -n blockdev --getsize64 /dev/block/by-name/boot
```
Odczyt samej partycji `boot` (kopia do analizy offline, kilkadziesiąt MB; wcześniej zapytać właściciela, plik zostaje na PC, nie do repo):
```bash
ssh <użytkownik>@<adres> "sudo -n dd if=/dev/block/by-name/boot bs=1M status=none | gzip -1" > boot-q2.img.gz
```

**D. Pomiar mechanizmu zacinania (kluczowe; najlepiej w trakcie krótkiego druku, jedno połączenie SSH, wynik na PC, bez plików na drukarce)**
Co 10 s przez 5-10 minut zapisać liczniki i obliczać różnice:
```bash
for i in $(seq 1 60); do
  date +%T
  grep -E '^(pgmajfault|pgfault|workingset_refault_file|workingset_activate_file|pgscan_kswapd|pgscan_direct|pgsteal_kswapd|pgsteal_direct|allocstall_[a-z0-9]+|nr_vmscan_write|oom_kill|pswpin|pswpout) ' /proc/vmstat
  grep -E '^(MemAvailable|MemFree|Cached|Dirty|Writeback):' /proc/meminfo
  grep -E ' mmcblk0 ' /proc/diskstats                 # sektory odczytane vs zapisane
  ps -eLo pid,tid,stat,wchan:24,comm | awk '$3 ~ /^D/' | sort | uniq -c | sort -rn | head -8   # kto stoi w stanie D i na czym
  sleep 10
done
```
Jak to czytać: jeśli rośnie `workingset_refault_file` / `pgmajfault` i wątki `D` stoją na `filemap_fault`, `wait_on_page_bit`, `do_read_cache_page` ->
**zrzucanie kodu z cache, czyli ten sam mechanizm co na Max 4** (hipoteza z sekcji 0 potwierdzona). Jeśli D stoi na `jbd2_*`, `ext4_sync_file`, `wait_on_buffer` i rośnie głównie zapis na `mmcblk0` ->
winne są zapisy synchroniczne (`/` jest `sync`), a nie brak swapu.

**E. Kto ile zajmuje (w druku i w spoczynku)**
```bash
ps -eo pid,rss,vsz,ni,stat,comm --sort=-rss | head -15
for p in $(pgrep -f 'klippy|moonraker|algo_app|qidiclient|ustreamer|crowsnest|journald|tailscaled'); do
  echo "== $p $(cat /proc/$p/comm)"; grep -E 'VmRSS|RssAnon|RssFile|RssShmem|Threads' /proc/$p/status; echo "oom_adj: $(cat /proc/$p/oom_score_adj) score: $(cat /proc/$p/oom_score)"
done
```

Zasady: nie uruchamiać w druku niczego innego poza D i E, jednego połączenia SSH, bez wywoływania Klippera/Moonrakera; nie robić `drop_caches`; skrypty ntfy
(jeśli się coś robi z `algo_app`) jako `sudo -n -u qidi`, zgodnie z `CLAUDE.local.md`.

---

## 8. Rekomendacja

**NIE robić zram/swapu dla Q2 jako funkcji tego projektu.** Jądro Q2 go nie obsługuje, moduły Valve Oil nie pasują i nic nie dadzą, a wymiana jądra jest zbyt ryzykowna.

Robić tylko to, w kolejności:
1. **Zmierzyć**, co faktycznie powoduje zacięcia (sekcja 7, D i E; najlepiej przy najbliższym teście druku). To rozstrzyga, czy walczymy z pamięcią,
   czy z zapisami `sync`, i nie niszczy niczego.
2. **Zgłosić do QIDI** prośbę o włączenie `CONFIG_SWAP` + zram w jądrze Q2 (i o źródła jądra), z danymi Valve Oil (jeśli właściciel chce; my niczego nie wysyłamy).
3. Dopiero po pomiarze rozważyć małe zmiany: kolejność `oom_score_adj`, nadzorca pamięci, zmniejszenie AI (decyzja właściciela), kamera/timelapse.
4. Własne jądro: tylko jako eksperyment na zapasowym module eMMC, jeśli właściciel kiedyś zechce; nie jako moduł i nie dla innych użytkowników.

### Czego nie wiem (ryzyka i luki)

- **Brak surowego `/proc/kallsyms` i obrazu `Image` Q2 na dysku.** Brak swapu opieram na: braku `/proc/swaps` (odczyt z 23.10), relacji o kallsyms ze zlecenia i kodzie 5.10.160.
  To mocne, ale nie widziałem samego jądra.
- Nie wiem, czy **inne Q2** (inna partia, inny obraz fabryczny) mają to samo jądro; mamy jedną drukarkę. Nie wiem, czy QIDI w przyszłości nie dołączy swapu (aktualizacje .deb jądra nie zmieniają,
  więc musiałby to zrobić nowy obraz fabryczny).
- Nie mierzyłem pamięci Q2 w druku w tej sesji (zakaz kontaktu); liczby (210 MB, 30-40 MB) pochodzą od właściciela, a mechanizm z Max 4 (Valve Oil) to **analogia**, nie pomiar na Q2.
- Nie wiem, czy zacięcia kamery/Fluidd/timelapse to brak pamięci, zapisy `sync` na eMMC, obciążenie CPU (load 17 na 4 rdzeniach), czy suma wszystkiego.
- Wartości `vm.swappiness`, `dirty_*`, `watermark_scale_factor` na Q2 nie są znane (znane tylko `min` w zoneinfo).
- Który proces został zabity przez OOM 24.10 - nie ustalono.
- Nie sprawdziłem do końca cudzych projektów dla Q2/Q1 Pro; wyszukiwanie "zram QIDI" dało wyłącznie Valve Oil.
- Cały raport powstał bez dotykania drukarki, więc nic z "TAK, da się" w sekcji 4d nie jest sprawdzone działaniem.

### Źródła

- Valve Oil (GPL-3.0; moduły jądra GPL-2.0-only), lokalna kopia `thr-flash/Valve-Oil`: `kernel/README.md`, `kernel/qidi_kernel_defconfig`, `scripts/build_kernel_modules.py`,
  `installer/package.yaml` (`zram_swap`), `docs/install.md` (sekcja "Zram swap"), `THIRD_PARTY_NOTICES.md`, `openspec/observations/qidi-platform.md`;
  PR #195 `thelegendtubaguy/Valve-Oil` (https://github.com/thelegendtubaguy/Valve-Oil/pull/195).
- Kod Linuksa 5.10.160 (Rockchip/Armbian, commit `709c51c64e1652d4f8c87b1815db86f56d188268`): `mm/Makefile`, `mm/swapfile.c`, `kernel/sys_ni.c`, `include/linux/vm_event_item.h`,
  `drivers/block/zram/Kconfig` (https://github.com/armbian/linux-rockchip).
- Archiwum sesji `QIDI_Q2_historia_do_20261110.zip` (odczyty z Q2 z 15-28.10.2026), pakiety `work/stock/data.tar.xz` (02.04) i `downloads/QD_Q2_01.01.03.02_20261023_Release.zip`.
- Wiki QIDI: https://wiki.qidi3d.com/en/Memo/flash-emmc ; wiki społeczności: https://github.com/qidi-community/q2-wiki ; repozytoria https://github.com/QIDITECH .
