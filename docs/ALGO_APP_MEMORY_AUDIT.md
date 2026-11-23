# Audyt pamięci `algo_app` (AI) i reszty oprogramowania Q2 - wycieki i rosnące zużycie RAM (2026-11-22)

Plik NIEŚLEDZONY: nie commitować, nie wysyłać na GitHub. Napisany **bez żadnego kontaktu z drukarką** (zero SSH, curl, Moonrakera, Klippera;
drukarka w tym czasie drukowała). Źródła: pliki na dysku (paczka QIDI 02.04 w `work/stock/`, archiwum `QIDI_Q2_historia_do_20261110.zip`),
własny dezasembler bajtkodu Pythona 3.9 i trzy strony w sieci (tylko czytanie). Nic nie pobrano. Niczego w repo nie zmieniono.

**Oznaczenia:** **DOWÓD** = widziane w kodzie/pliku lub w odczycie z prawdziwej drukarki (podane źródło). **WNIOSEK** = wynika z dowodów, ale
nikt nie sprawdził wprost. **HIPOTEZA** = prawdopodobne, niesprawdzone. **BRAK DANYCH** = nie wiemy.

---

## 0. Wynik w ośmiu zdaniach

1. **Kod `algo_app` mamy w całości i da się go czytać.** To Python 3.9 spakowany PyInstallerem (nie natywny, nie Cython). Archiwum nie jest
   zaszyfrowane; własny kod QIDI to 21 małych modułów `src.*`. Ghidra nie była potrzebna. (sekcja 1)
2. **W kodzie aplikacji nie ma nieograniczonych list, kolejek ani cache klatek.** Wszystkie bufory klatek to `deque(maxlen=3)` albo zmienne
   lokalne; jest jedna "bieżąca klatka" na wątek. Nie znalazłem miejsca, które rosłoby liniowo z czasem druku. (sekcja 3)
3. **Dane z 6 prawdziwych sesji (16-17.10.2026, 234 odczyty `process mem`) pokazują schodek, nie wyciek:** ~100 MB w spoczynku, po starcie AI
   szczyt 183-191 MB, potem **płasko ~166-175 MB** przez 6-15 minut ciągłej inferencji (CPU ~99 %). Zero trendu wzrostowego w tych oknach. (sekcja 4)
4. **Główna przyczyna dużego zużycia to rozmiar, nie wyciek:** model makaronu (plik 44,6 MB) kosztuje w RAM **+66-75 MB** (te sesje), a kod
   ładuje go jednorazowo i **nigdy nie zwalnia** (funkcja `detector_release` nie ma żadnego wywołania). Dlatego po pierwszym druku z AI proces
   zostaje "gruby" aż do restartu usługi. To zgadza się z obserwacją 19.11 (skok 68 -> 166 MB i tak do restartu). (sekcje 3, 5)
5. **Najgorsza chwila to ładowanie modelu:** `decrypt_weight` trzyma naraz trzy kopie pliku w pamięci (3 x 44,6 MB = ~134 MB) plus plik
   tymczasowy, a ONNX Runtime dopiero potem buduje swoje struktury. To WNIOSEK z kodu i z szczytu 199,8 MiB izolowanego testu z 16.10;
   próbki z pełnej aplikacji (co 21 s) mogły tego szczytu nie złapać. (sekcja 5)
6. **Powolny "zapadkowy" wzrost po wielu drukach jest możliwy, ale NIEUDOWODNIONY.** Są trzy kandydaci: fragmentacja `malloc` (wiele wątków
   = wiele aren), ładowanie i zwalnianie drugiego modelu (PEI/obce przedmioty) przy każdym druku, otwieranie kamery od nowa co ~2 s. (sekcja 3.2)
7. **Co można zrobić bez zgadywania:** najpierw tylko pomiary do odczytu (sekcja 8; część odpowiedzi leży już w logu
   `/var/log/algo_app/app_*.log` z druku 22.11). Potem, po zgodzie właściciela, drobne zmiany z sekcji 7 (OOM-priorytet, ustawienia `malloc`,
   restart usługi po druku). Poprawianie samego pliku `main` dopiero na końcu i tylko jeśli pomiary je uzasadnią.
8. **Uczciwie:** nie mam żadnych danych z długiego (godziny) druku z pełnym AI poza liczbami podanymi przez właściciela (205-217 MB, wolne 26-48 MB).
   Nie umiem więc powiedzieć, czy po godzinie druku jest +0 MB czy +20 MB względem pierwszych minut.

---

## 1. Gdzie jest kod `algo_app` i czym jest (pytanie 1)

| Fakt | Status | Źródło |
|---|---|---|
| `work/stock/files/usr/local/bin/algo_app/main` (12 864 664 B) to **ELF aarch64 z PyInstallera**; w cookie: `libpython3.9.so.1.0`, wersja formatu PyInstallera 2.1 | DOWÓD | własny odczyt (`pyi_extract.py`), `main` bajty 0..; cookie na offsecie 12 862 533 |
| Archiwum ma 12 pozycji (bootstrap, `main.py` jako skrypt, 4 skrypty runtime-hook) i **jeden `PYZ.pyz` 12,8 MB** z 2180 modułami | DOWÓD | `pyz_list.py` |
| PYZ **nie jest zaszyfrowane**: każdy moduł to zlib + `marshal` kodu Pythona 3.9 | DOWÓD | odczytane wszystkie 2180 (to samo potwierdza `docs`/archiwum z 17.10: "oryginalny czytnik PyInstallera dla wszystkich 2180 modułów") |
| Własny kod QIDI = pakiet **`src`** (21 modułów): `algo_interface`, `api_routes`, `config_handler`, `detect_post_deal`, `detection_deal`, `foreign_check`, `klipper_g28_detector`, `license_check`, `logger_config`, `moonraker_subscribe`, `pei_detector`, `printer_status_control`, `video_input_deal`, `video_save`, `onnx/{target_detection,utils}`, `onnx_cls/*`, `yolo/*`, plus skrypt `main` (sw_version `3.2.0`) | DOWÓD | `pyz_dump.py` |
| Reszta PYZ to biblioteki: sympy, numpy, onnxruntime, pydantic, fastapi, uvicorn, starlette, anyio, websockets, requests, psutil, Crypto, ffmpeg (nakładka na polecenie `ffmpeg`)... | DOWÓD | `pyz_list.py` |
| Biblioteki natywne (`_internal/`) **nie są w paczce QIDI 02.04** (tylko `main`). Na drukarce dokłada je nasz moduł `ai-libraries`: **opencv-python 4.12.0.88** (z własnym FFmpeg), **numpy 2.0.2**, **onnxruntime 1.19.2**, psutil 7.0.0, pycryptodome 3.23.0, websockets 15.0.1 + trochę pakietów Debiana (libpython3.9) | DOWÓD | `modules/ai-libraries/sources.json`; wersje z `QIDI_Q2_AI_IMAGE_TEST_20261015/RESULT.md` |
| Model: `/usr/local/bin/algo_app/weights/algo.enc` (**44 576 416 B**, AES-CBC, klucz wbudowany w aplikację), wejście `[1,3,320,320]`, wyjście `[1,10,2100]`, 6 klas | DOWÓD | `RESULT.md` z 16.10; `src/detection_deal.py:72-86` |
| Drugi model: `weights/algo_pf.enc` (PEI/obce przedmioty, klasyfikator `onnx_cls` 224x224); rozmiar pliku BRAK DANYCH (właściciel podaje ~+17 MB w RAM) | DOWÓD (istnienie) | `src/pei_detector.py:38`, `src/detection_deal.py:96-117` |
| Silnik: **ONNX Runtime** (CPU; `get_available_providers()` = Azure + CPU). Nie RKNN, nie NCNN, nie TFLite | DOWÓD | `src/onnx/target_detection.py:28` |
| Dostawcy wideo: **OpenCV** (`VideoCapture` do kamery, `VideoWriter` mp4v do nagrań) | DOWÓD | `src/video_input_deal.py`, `src/video_save.py:95` |
| Serwer: FastAPI + uvicorn na porcie 9010 (wątek `api`), w pracy usługa jako **root**, `Nice=19`, **`CPUAffinity=3`** (jeden rdzeń), `Restart=always`, `RestartSec=15`, `MemoryHigh=200M`/`MemoryMax=250M` (**nie działają**: brak kontrolera pamięci) | DOWÓD | tekst unitu z `QIDI_Q2_AI_BALANCED_LIVE_20261017/preflight-*.json`; `memory-control-evidence.json` |
| Dekompilatora nie ma; zrobiłem własny: `marshal` 3.9 + dezasembler + "pseudo-źródło" (odtworzone wyrażenia, skoki jako `goto`). Dla 25 plików wynik czytelny, 0 nierozpoznanych opcodów poza 11 w obsłudze wyjątków (próbowałem je czytać ręcznie) | DOWÓD | narzędzia i wyniki skopiowane do folderu notatek: `...\side-session-notes\local_d7d1b547-...\algo_app_tools\` |

**Czego brakuje do pełnej zdekompilowanej wersji:** nic do audytu pamięci; do ewentualnej zmiany kodu istnieje już sprawdzona droga (kandydat
`main` MEDIUM8 z 17.10 przebudowywał indeks PYZ i nagłówki ELF; moduł `ai-libraries` stosuje takie poprawki bajtowe).

---

## 2. Architektura (pytanie 1, cd.)

Wątki zgadzają się z tym, co widać w procesie (`threading.enumerate()` loguje `monitor_all_threads`; w spoczynku 8 wątków, 13 deskryptorów - odczyt z 23.10):

```
MoonrakerSubscribe  --WebSocket ws://127.0.0.1:7125-->  stan druku (print_stats, live_position, save_variables = ustawienia AI)
PrinterStatusControl (co 2 s; co 10 obiegów loguje RSS - stąd log co ~21 s) --> flagi: is_printing, is_printing_begin (warstwa >= 2), pauza, "homing"
video_input_deal   co ~2 s: OTWIERA kamerę od nowa (http://127.0.0.1/webcam/?action=stream), czyta 1 klatkę, zamyka  --> data_output["frame"]
DetectionDeal      bierze klatkę -> (1) ładuje model przy pierwszej okazji (2) ONNX 320x320, ~8-9 s na klatkę --> wynik
detect_pos         rysuje ramki, liczy punkty, zapisuje klatki do 4 nagrywarek (ori/pos/det/layer), wysyła wynik: SAVE_VARIABLE qdc_ai_error_code przez Moonraker
api (uvicorn)      /capture, /detection_res, /history_frames, /get-video-list, /config ... (funkcje zwykłe `def` -> pula wątków AnyIO)
MainThread         pętla co 1 s: license_check (jednorazowo przy starcie sprawdza licencję, potem tylko odczyt flagi)
```

DOWÓD: `main.py` (stub), `src/*.py` (wiersze podane przy poszczególnych punktach). Częstość klatek: wg logu z testu 16.10 **44 klatki w 887 s (~8-9 s/klatkę)**,
proces zajmuje ~1 rdzeń (log: CPU 93-100 %).

---

## 3. Miejsca potencjalnego nieograniczonego wzrostu - przegląd punkt po punkcie (pytanie 2)

### 3.1 Co sprawdziłem i jest OK (DOWÓD z kodu)

| Miejsce | Wynik | Gdzie |
|---|---|---|
| Listy/słowniki/kolejki bez limitu | **Brak.** `deque(maxlen=3)` x3 (`history_frames`, `no_pei_history_frames`, `foreign_history_frames`); reszta to zmienne lokalne albo pojedyncze obiekty. `queue.Queue` w ogóle nie jest używana | `src/detect_post_deal.py:43-45`; przeszukanie `append(`, `deque`, `= []` we wszystkich 21 modułach |
| Cache klatek "najlepsza klatka warstwy" | **Jedna** klatka (`last_layer_best_frame`, nadpisywana); przy zmianie warstwy idzie do `layer_video_saver` i jest zastępowana nową | `src/detect_post_deal.py:~235-262` |
| Bufory klatek między wątkami | po jednym `data_output` na wątek (kopia klatki ~0,9 MB przy 640x480; **~10 takich kopii żyje naraz** = ~9 MB; przy 1080p byłoby ~60 MB - rozdzielczość strumienia: 640x480 wg obrazów testowych) | `video_input_deal.py:229`, `detection_deal.py:~190`, `detect_post_deal.py:~330` |
| Wątki tworzone co jakiś czas | **Nie.** Wszystkie 6 wątków powstaje raz. `MoonrakerSubscribe` używa `asyncio.run` w pętli *tylko po zerwaniu połączenia* (nowa pętla zdarzeń, stara zamknięta) | `moonraker_subscribe.py:290-` |
| Sesje HTTP | `MoonrakerClient` ma **jedną** `requests.Session` na cały czas życia; reszta to `requests.get(...)` z timeoutem 2-3 s (połączenie zamykane po odpowiedzi) | `algo_interface.py:146-150`, `printer_status_control.py` |
| Deskryptory | 13-14 w spoczynku, stabilnie przez 10 min (23.10); `with open(...)` wszędzie | `RAM_DETAIL_20261023/SUMMARY.json` |
| Logi w pamięci | Nie. `RotatingFileHandler` 10 MB x (1+5 kopii) **na każde uruchomienie** (nowy plik `app_<data>.log` przy każdym starcie, stare nigdy nie są kasowane - to dysk, nie RAM; `shmem` w oknach pomiarowych 0,7 MB, więc `/var/log` nie jest tmpfs) | `logger_config.py:80`; `ALLOCATION_CONTEXT.json` (shmem 178 stron) |
| Nagrania `video_*.mp4` | Zapis na dysk (`/home/qidi/video`), limit **1 GiB** na katalog (kasuje najstarsze); przy starcie druku kasuje wszystkie `.mp4`. Segment = 60 s x 20 kl/s = 1200 klatek; przy 1 klatce na 30 s (ustawienie `save_raw_video_interval`) to ~10 godzin w jednym pliku, więc muxer MP4 trzyma indeks tylko kilku tysięcy wpisów (kilkadziesiąt KB) | `video_save.py:12-37, 72-96`; konfig z 16.10 |
| Wiele jednocześnie otwartych nagrywarek | Cztery obiekty `VideoSaver`, ale writer powstaje dopiero przy pierwszym zapisie. Przy ustawieniach z 16.10 aktywne są: `ori` (surowe, 1 kl./30 s) i `layer` (1 kl./warstwę) oraz `det` tylko gdy wykryto makaron. Każdy writer to kontekst kodera mpeg4 | `detect_post_deal.py:24-27, 260, 274, 325`; konfig z 16.10 (**stan na dziś BRAK DANYCH**) |
| Pliki tymczasowe odszyfrowanego modelu | `NamedTemporaryFile(delete=False)` -> `os.unlink` zaraz po załadowaniu. **Jeśli proces zostanie zabity między zapisem a `unlink`, plik (44 MB) zostaje w `/tmp`** (nie ma `PrivateTmp` ani sprzątania w `ExecStartPre`) - patrz 3.2 i sekcja 8 | `detection_deal.py:72-86, 111, 163` |
| Zdarzenia Moonrakera | `notify_status_update` obsługiwane na bieżąco, bez kolejki; nieznane komunikaty tylko logowane | `moonraker_subscribe.py:109-` |

### 3.2 Co może powodować wzrost lub nieoddawanie pamięci (WNIOSEK / HIPOTEZA)

| # | Miejsce | Co robi kod (DOWÓD) | Co z tego wynika | Status |
|---|---|---|---|---|
| A | **Model makaronu nigdy nie jest zwalniany** | `DetectionDeal.detector` ustawiany tylko w `__init__` (None) i przy ładowaniu; `detector_release()` (z `gc.collect()`) jest zdefiniowane w `detection_deal.py:88-95` i **nie ma żadnego wywołania** w całej aplikacji (sprawdzone grepem po wszystkich modułach) | po pierwszym druku z AI proces trzyma +66-75 MB (te logi) do restartu usługi - również gdy AI zostało wyłączone w ustawieniach i gdy nie ma druku. To jest "schodek", który widział właściciel 19.11 | **DOWÓD** (kod + log) |
| B | **Odszyfrowanie modelu = 3 kopie w RAM** | `decrypt_weight`: `ciphertext = f.read()` (44,6 MB) -> `cipher.decrypt` (44,6 MB) -> `unpad` (kopia 44,6 MB) -> zapis do pliku tymczasowego; dopiero potem ORT czyta plik | chwilowy szczyt **~+134 MB** ponad stan sprzed ładowania, w chwili gdy druk już trwa (ładowanie następuje, gdy warstwa >= 2). Izolowany test z 16.10 (próbkowanie co 50 ms) miał szczyt 199,8 MiB, gdy sam proces roboczy bez FastAPI itp. zajmuje ok. 60-70 MB w spoczynku - zgadza się z tym rachunkiem | **WNIOSEK** |
| C | **Wszystkie opcje ONNX Runtime domyślne** poza liczbą wątków (1+1) | `SessionOptions()` bez `enable_cpu_mem_arena=False`, bez `enable_mem_pattern=False`; sesja z pliku (`InferenceSession(path, ...)`); ORT zwykle trzyma model w pamięci dwukrotnie (proto + tensory) i arena nie oddaje pamięci systemowi (źródła w sekcji 10). Stałe wejście 320x320, więc arena powinna się ustabilizować po pierwszej klatce | tłumaczy, czemu +66-75 MB przy pliku 44,6 MB; stabilność po pierwszej klatce potwierdza log (plateau). Czy wyłączenie areny zmniejszy RSS o 10 czy o 30 MB - BRAK DANYCH | **HIPOTEZA** (mechanizm), **DOWÓD** (plateau) |
| D | **Drugi model (PEI/obce) tworzony i niszczony przy każdym druku** | `pei_detect_run`: gdy `pei_detector is None` -> odszyfrowanie `algo_pf.enc` (3 kopie) -> nowa sesja ORT; przy starcie wykrywania makaronu `self.pei_detector = None` (bez `gc.collect()`). Nasz moduł `ai-fixes` przywraca `M4050`, więc **przy włączonych "obcych przedmiotach" dzieje się to przed każdym drukiem** | wielokrotne tworzenie/niszczenie dużych obiektów to klasyczna przyczyna "zapadki" fragmentacji `malloc` (RSS po zwolnieniu zostaje wyższy) | **HIPOTEZA** (kod pewny, skutek nie) |
| E | **Kamera otwierana od nowa co ~2 s** | domyślnie `stream_addr0 = '/webcam/?action=stream'` kończy się na `stream` -> tryb `stream_has_cache`: w każdej iteracji `cv2.VideoCapture(url)` -> 1 odczyt -> `cap.release()`; każde otwarcie = nowe połączenie HTTP przez nginx do crowsnest/ustreamer + sondowanie strumienia przez FFmpeg | tysiące otwarć na godzinę druku. W OpenCV+FFmpeg są zgłoszenia "release nie zwalnia RAM"; opiekunowie twierdzą, że to zwykle utrzymywanie pamięci przez allocator, nie wyciek (sekcja 10). Na Q2 BRAK POMIARU | **HIPOTEZA** |
| F | **Fragmentacja `malloc` (glibc)** | proces ma 8 wątków; każdy wątek, który alokuje, może dostać własną arenę (do 8 x liczba rdzeni = 32); kopie klatek (~0,9 MB), bufory ORT, obrazy `cv2` powstają i giną w różnych wątkach; po pierwszym zwolnieniu dużego bloku glibc podnosi próg `mmap` (do 32 MB), więc kolejne ~MB-owe bloki idą na stertę i nie wracają do systemu | zgadza się z obserwacją "+-10 MB wahań" i "schodek bez powrotu". Nie ma `MALLOC_ARENA_MAX`, `malloc_trim` ani `MALLOC_TRIM_THRESHOLD_` w jednostce systemd (DOWÓD: tekst unitu) | **HIPOTEZA** |
| G | **Wątek umiera po pierwszym wyjątku** | `video_input_deal.run` i `detect_post_deal.run`, `printer_status_control.run` mają `try/except Exception` wokół całej pętli, który **tylko loguje i kończy wątek**; `DetectionDeal.detect_run` łapie wyłącznie `cv2.error` (np. `MemoryError` albo błąd ORT zabija wątek) | to nie jest wyciek, ale **tryb awarii przy braku pamięci**: AI może po cichu przestać działać do restartu usługi, a proces dalej zajmuje RAM | **WNIOSEK** z kodu (nie widziane na żywo) |
| H | `get_current_layer` / `find_current_layer` czyta cały plik G-code linia po linii, gdy pozycja w pliku zmieni się o > 600 B lub co 50 odczytów | duży plik G-code = duży ruch w cache stron i CPU; **ale funkcja nie jest wywoływana z pętli głównej** (stan warstwy idzie z subskrypcji Moonrakera) | brak wpływu na pamięć, o ile nikt jej nie woła; pojawia się w audycie 17.10 jako istniejąca | **WNIOSEK** (niski priorytet) |

Czego **nie** znalazłem: otwartych bez zamknięcia plików, niezamykanych websocketów (połączenie WebSocket jest zamykane przez `async with connect(...)`),
rosnących słowników po `detect_count`, ani żadnego miejsca zapisującego wiele klatek na warstwę w pamięci.

---

## 4. Co mówią dane z logów (pytanie 3)

Z archiwów: `QIDI_Q2_SPAGHETTI_LIVE_TEST_20261016`, `QIDI_Q2_AI_RESUME_LIVE_20261017` (linie `process mem` z logów samej aplikacji; skrypt
`memseries.py` złożył 234 unikalne próbki w 8 sesji). RSS wg `psutil` (**zawiera strony plików mapowanych, np. biblioteki - nie samą pamięć anonimową**).

| Sesja (data) | próbek | RSS start | szczyt | RSS na końcu okna | min. wolne w systemie | uwagi |
|---|---:|---:|---:|---:|---:|---|
| 16.10 14:28-14:43 | 44 | 102 | 187 | **173** | 121 | start AI o 14:37:39; po szczycie plateau 172,6 przez ~6 min |
| 16.10 15:00-15:11 | 34 | 102 | 190 | 175 | 119 | |
| 16.10 16:09-16:20 | 34 | 102 | 183 | 167 | 131 | |
| 16.10 16:29-16:39 | 30 | 101 | 183 | 170 | 117 | |
| 17.10 05:20-05:38 | 51 | 102 | 191 | 174 | 133 | |
| 17.10 17:14-17:26 | 33 | 98 | 182 | 166 | 151 | |

**DOWÓD:** we wszystkich sześciu oknach profil jest ten sam: ~100 MB -> szczyt 182-191 -> plateau 166-175 MB. W plateau (do 15 min, CPU ~99 %)
RSS **nie rośnie** (np. 14:40:51-14:43:41: 172,84 -> 172,57). Różnica szczyt-plateau (~15 MB) to prawdopodobnie przejściowe kopie z ładowania i inferencji.
Przy 21-sekundowym próbkowaniu szczyt krótszy niż ~20 s mógł nie zostać zauważony (patrz B).

**Inne punkty odniesienia (DOWÓD, odczyty z drukarki):**

| Kiedy | Wartość | Źródło |
|---|---|---|
| 23.10 spoczynek (10 min, 61 próbek) | `algo_app` **PSS 90,39 -> 90,45 MiB (+56 KiB)**, prywatna anonimowa 85,9 MiB, 8 wątków, 13-14 deskryptorów, `VmSize` 740 MiB, RSS HWM 135 MiB | `RAM_DETAIL_20261023/SUMMARY.json` |
| 23.10 | "świeże AI 98 MiB PSS, po jednej analizie 133,5 MiB; wcześniejszy proces 199,7 MiB" | `RAM_UPTIME_CHECK_20261025/RESULT_PL.md` |
| 25.10 (proces ma 36,8 h) | `algo_app` **PSS 189,16 MiB**, identyczne w dwóch próbkach | tamże |
| 16.10 pierwszy test | szczyt RSS drzewa procesów 196,7 MiB, minimum wolnej pamięci 97,8 MiB | `SPAGHETTI_LIVE_TEST/RESULT.md` |
| 22.11 (dane właściciela, `CLAUDE.local.md` i zlecenie) | w druku 205-217 MB (+-10), wolne 26-48 MB; po `systemctl stop algo_app` dostępne 47 -> 241 MB (zajęte 426 -> 223 MB) | zlecenie, `CLAUDE.local.md` |

**WNIOSEK:** `algo_app` w druku z pełnym AI to ok. **190-215 MB**, czyli **~40 % całego RAM-u (487 MB)** i jedyny element, który po wyłączeniu daje ~+190 MB
(to też dowód, że to on a nie Klipper/cache jest przyczyną niskiej wolnej pamięci).

**Czego dane NIE rozstrzygają (uczciwie):**
- Nie ma serii czasowej z długiego druku (> 1 h) - tylko ostatnia wartość od właściciela.
- Wartości 133 -> 189/199 MiB (23.10 vs 25.10) pochodzą z **różnych** procesów; nie wiadomo, czy to staranie się jednego procesu przez dni
  (wyciek/zapadka), czy po prostu "drugi model + więcej klatek". Sam raport z 25.10 mówi: "nie przypisano przyczyny". To jest najważniejsze pytanie
  do rozstrzygnięcia pomiarem w sekcji 8 (RSS po kolejnych drukach w jednym procesie).
- Zapisy wideo i konfiguracja z 22.11 (BRAK DANYCH): konfig z 16.10 miał `is_save_raw_video=True`, `is_save_layer_best_view=True`,
  `save_detect_pic_to_video=True`, ale ustawienia mogły się zmienić.

---

## 5. Skąd ~200 MB: budżet (WNIOSEK z powyższego)

| Składnik | Wielkość | Podstawa |
|---|---:|---|
| Python 3.9 + FastAPI/uvicorn/pydantic + numpy + OpenCV + ONNX Runtime załadowane, bez modelu | **~90-100 MB** (PSS 90, RSS 98-102) | 23.10, 16-17.10 |
| Model makaronu (plik 44,6 MB) po załadowaniu | **+66-75 MB** (RSS, 6 sesji); +35 MB wg PSS po pierwszej analizie 23.10 (wartości z różnych metod) | log 16-17.10, 23.10 |
| Model PEI/obce (jeśli włączony) | **~+17 MB** (dane właściciela), chwilowo | `CLAUDE.local.md` |
| Kopie klatek, wynik rysowania, 2-4 kodery mp4v, bufor `cv2`, pula wątków | rząd **10-30 MB** | rachunek z 3.1; BRAK POMIARU |
| **Razem** | **~190-215 MB** | zgadza się z 205-217 MB (22.11) |

Zatem **dominują: biblioteki (≈ połowa) i model (≈ jedna trzecia)**. Potencjalny zysk z "naprawy wycieków" jest mały, jeśli wycieku nie ma;
zysk z **nie ładowania/zwalniania modelu i z unikania szczytu przy ładowaniu** jest duży.

---

## 6. Reszta oprogramowania (pytanie 4, mniej szczegółowo)

| Element | Co sprawdziłem | Wynik | Status |
|---|---|---|---|
| **Klipper** (pliki QIDI w `work/stock/.../klippy`: `ai_func_manager`, `save_variables`, `smart_output_pin`, `virtual_sdcard`, `pause_resume`, `webhooks`, `mcu`, `serialhdl`...) | przejrzałem rozszerzenia QIDI pod kątem wątków, `Popen`, rosnących list | `ai_func_manager.py` (215 wierszy): same stałe słowniki, bez list; `save_variables.py`: wątek detekcji **zakomentowany**; brak `Popen`. W spoczynku PSS 36,6 MiB stabilnie (23.10: +14 KiB w 10 min) | DOWÓD (brak wzrostu w oknie 10 min); długi druk BRAK DANYCH |
| **Moonraker** | `data_store.py` (bufory) | `gcode_queue = deque(maxlen=gcode_store_size=1000)`, historia temperatur `deque(maxlen=1200)` - **ograniczone**. PSS 44,3 MiB stabilnie. Pełnej listy komponentów Moonrakera nie mamy na dysku (paczka ma tylko 9 zmienionych plików) | DOWÓD (bufory), BRAK DANYCH (reszta) |
| **timelapse (Moonraker)** | `timelapse.py` | ramki trafiają do `/tmp/timelapse/` (**domyślny `frame_path`; konfig drukarki BRAK DANYCH**), renderowanie `ffmpeg -preset ultrafast -threads 0 ... libx264` na **końcu druku**, wtedy `algo_app` nadal ma +70-115 MB. Jeśli `/tmp` byłby tmpfs, ramki rosłyby w RAM; w oknach z 18.10 i 23.10 `shmem` wynosił ~0,7 MB, co **sugeruje** że nie jest, ale w druku nie mierzono | WNIOSEK (nakładanie się z AI na końcu druku), BRAK DANYCH (mount) |
| **qidiclient** (ekran) | audyt `docs/QIDICLIENT_AUDIT.md`; PSS 14-25 MiB; 3 wyjścia SIGSEGV (coredump z `elf_core_dump` zgłosił `page allocation failure order:7` - alokacja 512 KiB ciągłego bloku przy niskiej pamięci) | wzrostu nie widać; problem to **brak ciągłych bloków** przy fragmentacji, nie wyciek | DOWÓD (odczyty) |
| **kamera (crowsnest/ustreamer), nginx** | przez `algo_app` co ~2 s otwierane jest nowe połączenie MJPEG (3.2 E) | koszt po stronie ustreamer: nowy klient co 2 s; pomiaru brak | BRAK DANYCH |
| **journald** | RSS 41 MB / PSS 27-28 MB (23.10) - **trzeci pod względem wielkości** proces. `algo_app` pisze `print()` i WARNING na stdout (idzie do dziennika) | możliwy udział w rozmiarze, nie mierzony | HIPOTEZA |
| **tailscaled** | PSS 26-28 MB (Go) | stały; to koszt funkcji, nie wyciek | DOWÓD (stabilny 50 h) |
| **Nasze usługi ekranu** (`q2_screen.py`, `q2_touch.py`) | przeczytane w całości | jednowątkowe `HTTPServer`; jedna klatka PNG w cache (~0,2 MB), brak list; chwilowo ~2 MB na obsługę żądania. RSS 13 MB + 11,5 MB (notatka z 22.11). **`MemoryMax=30M/25M` w ich unitach nie działa** (brak kontrolera pamięci) | DOWÓD (kod), koszt ciągły ~15-25 MB, gdy nikt nie patrzy |
| **Nasze powiadomienia ntfy** (`q2_notify_*.sh`, `q2_notify_eta.py`) | przeczytane w całości | słuchacz = `curl -sN` w pętli `sh` (kilka MB, stały); wysyłanie to krótkie procesy (`python3` tylko 3 razy na druk, ~8-10 MB chwilowo); plik tymczasowy zdjęcia w `/tmp` kasowany `trap ... EXIT` (zostaje tylko po SIGKILL). Zadania w tle (`... &`) bez `wait` - zombie `sh` bez pamięci, ewentualnie wpisy w tablicy procesów | DOWÓD (kod); koszt pomijalny |
| **Nasz moduł night-light** (`smart_output_pin.py`, `modules/dark-mode-light`) | przeczytany | **drobny wyciek obiektu timera:** `_q2_ai_back` zwraca `NEVER`, ale **nie wyrejestrowuje** timera (`unregister_timer`) - po każdym zakończeniu "trybu ciemnego" zostaje w `reactor._timers` jeden martwy obiekt (kilkaset bajtów). Rośnie tylko z liczbą wyłączeń światła w druku (praktycznie dziesiątki), więc bez znaczenia dla RAM, ale to jedyny znaleziony przeze mnie *prawdziwy* wyciek w naszym kodzie | DOWÓD (kod), wpływ znikomy |
| **Nasze moduły Klipper/Moonraker** (`webhooks-status-diff`, `reactor-timer-scan`, `gcode-history`, `print-cache-protection`...) | przejrzane teksty zmian | brak nowych struktur rosnących; `gcode-history` wręcz zmniejsza liczbę wpisów. `webhooks-status-diff` trzyma ostatni stan na klienta (jak oryginał) | DOWÓD (kod) |

Znane problemy "upstream" (Klipper, Moonraker): nie sprawdzałem wyczerpująco w sieci; to poza głównym zakresem. Dla ONNX Runtime, glibc i OpenCV zebrałem źródła w sekcji 10.

---

## 7. Rekomendacje (pytanie 5)

Zasada z `CLAUDE.local.md`: wszystko na drukarce **tylko za zgodą właściciela i poza drukiem**, jedna zmiana naraz, z pomiarem przed/po.

### 7.1 Do rozważenia (od najmniej do najbardziej ryzykownego)

| # | Pomysł | Zysk (oczekiwany) | Ryzyko | Zgoda? | Uwagi |
|---|---|---|---|---|---|
| 1 | **Najpierw pomiary** (sekcja 8) - w tym analiza istniejących logów `algo_app` z druku 22.11 | rozstrzyga, czy jest zapadka/wyciek | brak (tylko odczyt) | tak, na każdy odczyt z drukarki | **zrobić pierwsze** |
| 2 | **`OOMScoreAdjust`** w drop-inach systemd: `algo_app` +500..+800, `klipper` i `moonraker` -300..-500 (po sprawdzeniu, co mają teraz) | gdy dojdzie do OOM, ginie `algo_app` (wraca po 15 s), a nie Klipper w trakcie druku | niskie; cofnięcie = usunięcie pliku | tak | chroni przed **najgorszym skutkiem**, ale nie zmniejsza zużycia. Oom_kill = 0 w ostatnich oknach, więc to ubezpieczenie |
| 3 | **Ustawienia `malloc` w drop-inie `algo_app`**: `Environment=MALLOC_ARENA_MAX=2` (ew. + `MALLOC_TRIM_THRESHOLD_=131072`, `MALLOC_MMAP_THRESHOLD_=131072`) | **nieznany** (HIPOTEZA F); typowo od 0 do kilkunastu MB przy wielu wątkach | niskie (nieco wolniejsza alokacja); cofnięcie = usunięcie pliku | tak | bez zmiany kodu; sprawdzić A/B na dwóch podobnych drukach (patrz 8.E). Źródła mówią, że wynik bywa niewielki |
| 4 | **"AI wyłączone = `algo_app` zatrzymany"**: jeśli wszystkie trzy flagi AI (makaron, PEI, obce) są wyłączone na ekranie, zatrzymać usługę na czas druku i uruchomić po jego zakończeniu lub przy włączeniu AI | **+90-100 MB** (nie tylko model: całe 90 MB biblioteki), +7 % CPU | średnie: trzeba sprawdzić, czy ekran (`qidiclient`) lub nasze moduły nie oczekują portu 9010; ryzyko "AI zawsze wyłączone, bo usługa nie wstała" | tak | właściciel już zrobił to ręcznie 22.11 w druku (`systemctl stop`) i druk poszedł dalej - to **jedyny test, który mamy**. Wymaga małej usługi-nadzorcy |
| 5 | **Restart `algo_app` po druku** (np. 90-120 s po `complete/cancelled/standby`, tylko gdy nie ma nowego druku i RSS > ~130 MB) | oddaje 70-115 MB od razu po druku (przed renderem timelapse i dla kolejnego druku bez AI); usuwa ewentualną zapadkę (HIPOTEZA D/F) | niskie-średnie: kilkanaście sekund bez AI; musi odczekać aż nagrywarki zamkną pliki mp4 (zamykane w pętli co 2 s po zmianie stanu); nie wolno startować, gdy właśnie zaczyna się nowy druk | tak | **uwaga:** to leczy skutek (rozmiar po druku), nie zmniejsza zużycia *w trakcie* druku, bo model ładuje się znowu przy warstwie 2. Dawny wniosek z 25.10 "nie robić cyklicznych restartów" dotyczył spoczynku bez dowodu; **dowód z 22.11 (stop = +194 MB) jest nowy** |
| 6 | **Wyłączenie zapisu wideo/klatek** w konfiguracji (`is_save_raw_video`, `is_save_layer_best_view`, `save_detect_pic_to_video` = False) | HIPOTEZA: 5-20 MB (kodery mpeg4) + mniej zapisów na eMMC + mniej CPU | traci się nagrania (ekran może pokazywać wideo detekcji z `/home/qidi/video`); plik konfiguracyjny może zostać nadpisany przez QIDI | tak, **decyzja właściciela** (funkcja) | najpierw sprawdzić, co dziś jest włączone (8.G) |
| 7 | **Poprawka samego `main`** (jak MEDIUM8): (a) odszyfrowanie strumieniowe zamiast 3 kopii, (b) `enable_cpu_mem_arena=False`, `enable_mem_pattern=False`, (c) wywołanie `detector_release()` + `gc.collect()` + `malloc_trim(0)` po druku, (d) wyłapywanie wyjątków w `detect_run`, (e) po załadowaniu modelu nie trzymać zbędnych kopii | (a) usuwa szczyt **~+134 MB** przy ładowaniu; (b) HIPOTEZA 10-30 MB; (c) oddaje model po druku | **średnie-wysokie:** zmieniony `main` odrzucają zabezpieczenia pakietów 02/06; każda zmiana kodu wymaga testu w druku; błąd = AI nie działa lub proces pada w pętli (`Restart=always`) | tak | dopiero po 1-3 i tylko jeśli pomiary wskażą ładowanie modelu jako realny problem. Odszyfrowanego modelu **nie** trzymać w repo ani nie dystrybuować |
| 8 | **Usługi ekranu na żądanie** (aktywacja gniazdem systemd, wyjście po bezczynności) | ~15-25 MB RSS (PSS mniej) przez cały czas, gdy nikt nie patrzy | niskie; trochę kodu i testów w WSL | tak | zysk umiarkowany; **nie** ma sensu, dopóki algo_app zajmuje 100+ MB. Przy okazji: zmienić/usunąć mylące `MemoryMax=` w naszych unitach |

### 7.2 Co NIE ma sensu

- **Okresowy restart `algo_app` co N godzin bez względu na druk** - może trafić w druk; nie rozwiązuje problemu w czasie druku.
- **`echo 3 > /proc/sys/vm/drop_caches` / "czyszczenie cache"** - cache jest odzyskiwalny, a wyrzucenie go pogarsza zacinanie (kod programów trzeba czytać z eMMC).
- **`MemoryHigh/MemoryMax`, `ulimit -v`, cgroupy pamięci** - kernel nie ma kontrolera pamięci (DOWÓD), a limit adresów wirtualnych (VmSize 740 MB) zepsułby ładowanie bibliotek.
- **Swap/zram** - brak `CONFIG_SWAP` (patrz `docs/ZRAM_SWAP_Q2.md`).
- **Zmniejszanie `intra_op_num_threads`** - już 1.
- **Gonienie "wycieków" w naszych skryptach powiadomień/ekranu** - żaden nie rośnie; zysk pomijalny (poza ewentualnym "na żądanie" z 7.1.8).
- **Zmiana modelu na mniejszy/kwantowany bez testu jakości** - zmienia zachowanie detekcji (bezpieczeństwo), poza zakresem tego audytu.

---

## 8. Pomiary tylko do odczytu do wykonania później (pytanie 6)

**Nie wykonywałem żadnego z nich.** Każdy wymaga zgody i najlepiej wykonuje się go **poza** czasem, gdy ktoś inny pracuje na drukarce.
Polecenia dla PID `P` = `systemctl show -p MainPID --value algo_app` (jako root: `sudo -n`); wszystko to tylko `cat`/`ls`/`grep`/`awk`.

**A. Najtańszy i najważniejszy: log aplikacji z druku 22.11 (bez żadnej nowej pracy drukarki)**
```
ls -la /var/log/algo_app/                                  # ile plików, które z dzisiaj
grep -h "process mem" /var/log/algo_app/app_*.log | awk '{print $1, $2, $9, $12, $14}' | tail -400
grep -h -E "Loading model|load model end|init the pei foreign|release the model|开始打印|停止打印|暂停|恢复打印" /var/log/algo_app/app_*.log | cut -c1-110
```
Odpowiada na: kiedy dokładnie ładuje się model (warstwa), czy RSS rośnie w godzinie druku, ile razy ładowano drugi model, czy po końcu druku RSS spada (nie spadnie - 3.2 A).
Do tego `journalctl -u algo_app --since "2 days ago" | grep -c -i -E "Traceback|exited with exception"` - czy wątki giną (3.2 G).

**B. Stan procesu `algo_app` (spoczynek, początek druku, po załadowaniu modelu ~warstwa 3, 25/50/75 %, 5 min po końcu, początek następnego druku)**
```
grep -E "VmRSS|VmHWM|RssAnon|RssFile|RssShmem|VmSize|Threads|VmSwap" /proc/P/status
cat /proc/P/smaps_rollup                                   # Rss, Pss, Private_Dirty, Anonymous
ls /proc/P/fd | wc -l ; ls -l /proc/P/fd | grep -E "deleted|/tmp"      # deskryptory, pliki "(deleted)"
cat /proc/P/task/*/comm | sort | uniq -c                   # liczba i nazwy wątków
cat /proc/P/oom_score_adj /proc/P/oom_score
```
Interpretacja: `RssAnon` rośnie od druku do druku = zapadka/wyciek; `RssFile` duże = tylko mapowane biblioteki (odzyskiwalne).

**C. Gdzie jest pamięć w procesie (raz po załadowaniu modelu i raz 5 min po końcu druku)**
```
awk '/^[0-9a-f]+-[0-9a-f]+ /{name=$6; range=$1} /^Rss:/{r[name]+=$2} /^Private_Dirty:/{d[name]+=$2} END{for(n in r) print r[n], d[n], (n==""?"[anon]":n)}' /proc/P/smaps | sort -rn | head -25
pmap -x P | sort -k3 -n -r | head -30
```
Szukać: wiele regionów anonimowych ~64 MB (areny `malloc`), `[heap]`, `libonnxruntime.so`, `cv2.abi3.so`, `libavcodec*` (Rss pliki vs Dirty).

**D. System i jądro (w druku z AI i w druku bez AI, co ~5 min)**
```
grep -E "MemAvailable|MemFree|Cached|Buffers|Shmem|Mapped|AnonPages|Slab|SReclaimable|Dirty|Active\(file\)|Inactive\(file\)" /proc/meminfo
grep -E "pgmajfault|workingset_refault|workingset_activate|allocstall|pgscan_kswapd|pgsteal_kswapd|pgscan_direct|oom_kill|pgfault " /proc/vmstat
cat /proc/loadavg ; head -1 /proc/stat                      # iowait
findmnt -T /tmp ; findmnt -T /var/log ; findmnt -T /home/qidi ; df -h /tmp /var/log /home/qidi /dev/shm
ls -la /tmp | head -40 ; ls -la /tmp/timelapse | wc -l ; du -sh /tmp/timelapse /var/log/algo_app /home/qidi/video 2>/dev/null
```
Różnica `pgmajfault` i `workingset_refault_file` między próbkami (przyrost na minutę) mierzy "zacinanie" - bezpośrednio sprawdza hipotezę z `ZRAM_SWAP_Q2.md`.
`/tmp` pełne plików `tmp*` po ~44 MB = osierocone odszyfrowane modele (3.1).

**E. Ustawienia procesów (jednorazowo)**
```
systemctl show algo_app klipper moonraker -p MainPID -p OOMScoreAdjust -p Nice -p Environment -p MemoryCurrent
for p in $(pgrep -f "klippy|moonraker|ustreamer|nginx|qidiclient"); do echo $p $(cat /proc/$p/oom_score_adj) $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-60); done
cat /usr/local/bin/algo_app/configs/config.xml | grep -E "is_save|save_.*interval|video_stream|video_output_dir"      # BEZ sekcji z hasłem
```

**F. Doświadczenie A/B (dopiero po A-E i po zgodzie; wymaga druku)**
Dwa takie same małe wydruki z pełnym AI: jeden z obecnym stanem, drugi po dodaniu drop-inu z `MALLOC_ARENA_MAX=2` (sekcja 7.1.3). Porównać `RssAnon`
z B po warstwie 3 i po 30 min oraz `pgmajfault`/min. Różnica < 10 MB = bez znaczenia. Jedna zmiana naraz.

**G. Co faktycznie zapisuje** - `ls -la /home/qidi/video`, `grep video_ /var/log/algo_app/app_*.log | tail` (czy `VideoWriter` tworzy 2-4 pliki w druku).

**H. Zamknięcie pytania "czy ładowanie modelu daje szczyt ~+134 MB"** (bezpieczne tylko w stanie spoczynku, bez druku): zalogować `VmHWM` przed ładowaniem i po (zdarza się to w drukach, więc wystarczy odczyt `VmHWM` w punkcie B po załadowaniu modelu: HWM - RSS = wielkość przejściowego szczytu).

---

## 9. Rekomendacja końcowa

**Robić tylko X:**

1. **Teraz: nic nie zmieniać na drukarce.** Po zgodzie właściciela wykonać pomiary **A, B i D** (kilka odczytów, żadnego ryzyka); A można zrobić od ręki z logów już istniejących.
2. **Jeśli pomiary potwierdzą, że po załadowaniu modelu RSS jest płaskie** (jak w danych z 16-17.10), to **nie ma wycieku do naprawiania**, a jedyną realną dźwignią jest *nie trzymać AI w pamięci, gdy nie jest potrzebne* (7.1.4/7.1.5) oraz *ubezpieczenie* przed zabiciem Klippera (7.1.2). Wtedy zbudować mały, opcjonalny moduł z tymi dwiema rzeczami.
3. **Jeśli pomiary pokażą wzrost `RssAnon` od druku do druku** w jednym procesie: najpierw drop-in `malloc` (7.1.3), a dopiero potem - tylko jeśli to nie pomoże - poprawka `main` (7.1.7), w kolejności (a) odszyfrowanie strumieniowe, (c) zwalnianie modelu po druku.
4. **Nie robić:** cyklicznych restartów, czyszczenia cache, własnych "limitów pamięci" ani poprawiania skryptów powiadomień/ekranu pod kątem RAM.

**Dlaczego nie "napraw wycieki":** mimo starannego przeglądu kodu **nie znalazłem w `algo_app` żadnego wycieku w sensie programistycznym** (listy, kolejki, cache). Problem to *duży stały koszt* (biblioteki + model) i *brak oddawania* go po druku.

### Ryzyka tego audytu (czego mogłem nie zobaczyć)

- Mój dezasembler działa na bajtkodzie 3.9 i odtwarza wyrażenia, ale nie struktury `if/while`; nieczytelne pozostały fragmenty obsługi wyjątków (11 miejsc `<?>` w całości pliku). Nie widzę więc ewentualnych pętli ukrytych w tych fragmentach.
- **Biblioteki natywne (ORT, OpenCV, FFmpeg) mogą mieć własne wycieki**, których z kodu Pythona nie widać. Sekcja 3.2 E/F/C to hipotezy o ich zachowaniu.
- Dane z 16-17.10 dotyczą krótkich sesji (10-18 min) i **starszej konfiguracji** (przed naszymi poprawkami `ai-fixes`/`ai-libraries` w obecnej postaci); dane długiego druku mamy tylko jako liczby z `CLAUDE.local.md`.
- Pomiary RSS z logów obejmują strony plików (biblioteki); do ścisłego rachunku trzeba `RssAnon`/`smaps_rollup` (sekcja 8 B).

### Czego nie wiem (BRAK DANYCH)

- Seria czasowa `algo_app` z długiego druku (godziny) i czy po kolejnych drukach RSS rośnie w jednym procesie.
- Czy `/tmp` i `/var/log` na drukarce są tmpfs (pośrednio: nie, bo `shmem` 0,7 MB w oknach pomiarowych, ale nie w druku).
- Dokładne obecne `config.xml` (zapis wideo), wartość `oom_score_adj` Klippera/Moonrakera/algo_app, treść skryptu `tuning.sh` (czy zmienia `oom_score_adj`).
- Czy `qidiclient` albo coś innego oczekuje usługi `algo_app` na porcie 9010 (od tego zależy bezpieczeństwo pomysłu 7.1.4).
- Rzeczywisty rozmiar `algo_pf.enc` i szczytowe zużycie przy ładowaniu w pełnej aplikacji.
- Jak duży jest udział `journald` i `ustreamer` w okresie druku.

---

## 10. Źródła zewnętrzne (tylko czytanie, nic nie pobrano; wyniki wyszukiwania, nie potwierdzone u źródła)

- ONNX Runtime - arena CPU domyślnie włączona i nie oddaje pamięci systemowi; wyłączenie zmniejsza zużycie kosztem szybkości:
  [microsoft/onnxruntime#11627](https://github.com/microsoft/onnxruntime/issues/11627), [Unstructured-IO/unstructured-inference#481](https://github-users.yhajoa.workers.dev/Unstructured-IO/unstructured-inference/issues/481); zwalnianie sesji a pamięć hosta:
  [microsoft/onnxruntime#14466](https://github.com/microsoft/onnxruntime/issues/14466).
- glibc `malloc`: ograniczenie aren (`MALLOC_ARENA_MAX`) i `malloc_trim`, z zastrzeżeniami (wyniki bywają niewielkie, `malloc_trim` dla aren innych niż główna bywa niepełne):
  [bugs.python.org msg316359](https://bugs.python.org/msg316359), [sourceware bug 30769](https://sourceware.org/bugzilla/show_bug.cgi?id=30769),
  [discuss.python.org o ThreadPoolExecutor i glibc](https://discuss.python.org/t/memory-leak-when-using-concurrent-futures-threadpoolexecutor-with-glibc-but-possibly-not-with-jemalloc/108311).
- OpenCV `VideoCapture` + FFmpeg: zgłoszenia o niezwalnianiu RAM po `release()`; opiekunowie: zwykle pamięć trzymana przez allocator, nie wyciek:
  [forum.opencv.org/t/3660](https://forum.opencv.org/t/cv2-videocapture-release-does-not-free-ram-memory/3660), [forum.opencv.org/t/11650](https://forum.opencv.org/t/videocapture-memory-leak-or-feature/11650).

## Dodatek: jak powtórzyć rozpakowanie (bez drukarki)

Narzędzia leżą poza repo: `algo_app_tools` (folder narzędzi poza repozytorium)
(`pyi_extract.py` - rozpakowanie ELF PyInstallera, `pyz_dump.py` - moduły z PYZ, `py39dis.py` - dezasembler/pseudo-źródło, `memseries.py` - serie `process mem` z logów,
`dis\*.txt` - wynik dla wszystkich 21 modułów `src` + `main`). Uruchamiać `python -I` z katalogu innego niż rozpakowany (zasada: obcy kod/dane nigdy w bieżącym katalogu).
