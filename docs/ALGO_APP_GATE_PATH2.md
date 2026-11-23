# Bramka jasności dla `algo_app` - droga 2: kod wewnątrz procesu przez `cv2` (2026-11-22)

Moduł opcjonalny `algo-app-gate` (`--with algo-app-gate`, `"default": false`, kolejność 153). **Nie zmienia ani jednego pliku QIDI ani OpenCV, `main` zostaje oryginalny.**
Napisany **bez żadnego kontaktu z drukarką** (zero SSH, curl, Moonrakera). Wszystko poniżej oznaczone **DOWÓD** zostało uruchomione na laptopie; **NIE SPRAWDZONE** = wymaga drukarki.
Folder `ai-lab`, modele i klatki są poza repozytorium; w tym pliku i w kodzie nie ma żadnego klucza ani hasła do modeli, ani kodu QIDI.

## 1. Po co (jedno zdanie)

W ciemności (światło komory wyłączone) model makaronu daje fałszywy "makaron" na ok. 3 % klatek (czyta diody głowicy jako makaron; `docs/AI_MODELS_AUDIT.md` 10.5). Moduł podmienia
taką klatkę - zanim zobaczy ją którykolwiek model - na jednolitą szarą (19), a każdą jasną klatkę zostawia **bez zmian, tym samym obiektem**.

## 2. Jak kod trafia do procesu `algo_app` (część A)

### 2.1 Co ustaliłem (DOWÓD z plików, nie z drukarki)

| Fakt | Źródło |
|---|---|
| W archiwum PYZ w `main` **nie ma żadnego modułu `cv2`** (0 z 2180). Pakiet `cv2` jest więc czytany z dysku: `/usr/local/bin/algo_app/_internal/cv2/` | rozpakowanie `main` (`pyz` TOC), `main.py` zaczyna się od `import cv2` |
| Pliki Pythona `cv2/__init__.py`, `config.py`, `config-3.py`, `load_config_py3.py`, `version.py`... **dostarcza firmware QIDI 01.01.02.04**, nie nasz moduł. Nasz `ai-libraries` dokłada tylko `cv2.abi3.so` i wtyczkę Qt (`sources.json`) | `QIDI_Q2_FIRMWARE_DIFF_20261021` (rootfs 02.04); `modules/ai-libraries/sources.json` |
| Te pliki są **bajt w bajt** takie jak w kole `opencv-python 4.12.0.88` (np. `__init__.py` SHA-256 `936bd94c5a5debf0212fc751af79d3a163652f3e850259df2159db6aa3ed8ad8`) - sprawdzone na kole w `downloads/sources/` | porównanie sum |
| Loader OpenCV (`cv2/__init__.py`, funkcja `bootstrap()`): wykonuje `config.py`, potem pierwszy z `config-3.9.py` / `config-3.py`, **potem** ładuje natywne `cv2.abi3.so` i kopiuje jego symbole do pakietu, a **na samym końcu** importuje jako `cv2.<nazwa>` **każdy podfolder** pakietu, którego nazwa nie zaczyna się od `_` ani `python-` (`__collect_extra_submodules`) | czytany kod `__init__.py` |

### 2.2 Wybrana metoda: nowy folder `cv2/q2gate/` (jeden plik `__init__.py`)

`/usr/local/bin/algo_app/_internal/cv2/q2gate/__init__.py` jest zwykłym **nowym plikiem** modułu. OpenCV sam go zaimportuje na końcu `import cv2`, czyli:
po zbudowaniu `cv2.VideoCapture`, przed pierwszą kamerą aplikacji (`import cv2` jest pierwszym importem w `main.py`; `VideoInputDeal` tworzy kamerę dopiero później).

Dlaczego to najlepsze z możliwych:

| Rozważone | Wynik |
|---|---|
| **Dopisać linie do `cv2/__init__.py`** | to plik firmware; wymaga edycji z `stock_sha256`, każda różnica sumy = instalator odmawia; odwrócenie to kolejna edycja. Odrzucone |
| `config.py` / `config-3.py` / nowy `config-3.9.py` | **złe miejsce w czasie**: wykonują się *przed* załadowaniem natywnego `cv2` - `VideoCapture` jeszcze nie istnieje. Nowy `config-3.9.py` dodatkowo **zastępuje** `config-3.py` (loader bierze pierwszy istniejący). Odrzucone |
| `sitecustomize` / `.pth` / `usercustomize` | PyInstaller nie przetwarza `site`. Nie działa |
| **Folder-podmoduł `cv2/q2gate/`** | oficjalny, udokumentowany w kodzie loadera mechanizm; **zero edycji cudzych plików**; uruchamia się dokładnie wtedy, gdy trzeba; usuwa się go jedną komendą |

Dopasowanie do instalatora - **bez żadnego rozszerzenia instalatora**: zwykły wpis `"source"` (jak `algo-app-recycle`), właściciel `root:root 644` z `default_owner`, katalog tworzy `install -D`/`mkdir -p`,
`"restart": ["algo_app"]`. Odinstalowanie (`do_uninstall`, `do_uninstall_stock`) kasuje plik (`rm -f`). **Jedyna rzecz, której instalator nie robi: nie usuwa katalogu.** Po odinstalowaniu zostaje `cv2/q2gate/__pycache__/`
(Python tworzy go przy pierwszym imporcie jako root). To **nieszkodliwe** (pusty folder = pakiet-przestrzeń nazw bez kodu; sprawdzone, patrz 3.1) - ale jeśli ma być czysto:
`sudo rm -rf /usr/local/bin/algo_app/_internal/cv2/q2gate`. (Ewentualne drobne rozszerzenie instalatora: po `rm -f` pliku "nowego" dodać `rmdir -p` pustych rodziców; **nie robiłem**, bo to nie moje pliki.)

### 2.3 Co hak robi

* `cv2.VideoCapture` jest podmieniane na **klasę-opakowanie** (zawiera prawdziwy obiekt i deleguje metody; to NIE jest podklasa). Podklasa `cv2.VideoCapture` w OpenCV 4.12 na drukarce (aarch64) kończy proces: `free(): invalid pointer` / SEGV przy zwolnieniu obiektu (zmierzone 22.11.2026 na drukarce: zwykły obiekt - bez awarii, podklasa - awaria 5 z 5; pierwsza wersja tego modułu była podklasą i usługa `algo_app` restartowała się co kilkanaście sekund).
* `read()` i `retrieve()`: wywołują oryginał i patrzą na wynik `(ok, klatka)`.
  * klatka 8-bitowa ze średnią szarością **< 22,0** -> nowa tablica tego samego kształtu i typu, wszystkie piksele = **19**;
  * w każdym innym przypadku (jasna, `ok == False`, `None`, inny typ danych, pusta, nie tablica) **zwracany jest ten sam obiekt wyniku** - bez kopii.
* Średnia szarość: wagi OpenCV `BGR2GRAY` (0,114 / 0,587 / 0,299) liczone **na liczbach całkowitych**, żeby jednolita klatka 22 dała dokładnie 22,0 (granica ostra: 22,0 nie jest "< 22"), na **siatce co 4. piksela** (640x480 -> 160x120 = 19 200 punktów, bez kopii klatki, bez bufora).
* Konfiguracja: zmienne środowiskowe (czytane raz, przy starcie) i opcjonalny plik `/etc/q2-algo-gate.conf` (**nie instalowany przez moduł**, robi go ręcznie właściciel; czytany co 30 s, więc przełącznik działa **bez restartu**): `off`, `threshold=22 fill=19 log_every=300`.
  `Q2_GATE=off` w środowisku usługi = moduł wcale nie dotyka `cv2`. Złe wartości są ignorowane.
* Log: logger `app.q2gate` (dziecko loggera `app` aplikacji, więc linie idą do `/var/log/algo_app/app_*.log`; do dziennika systemd trafiają też, jeśli usługa działa z `-l info` (domyślne w `main`; **NIE SPRAWDZONE**, jak jest uruchomiona usługa)): jedna linia `q2gate: active ...` przy tworzeniu pierwszej kamery (tuż po starcie usługi, niezależnie od druku),
  potem `q2gate: dark frame replaced ... (N so far, mean grey ...)` dla pierwszej ciemnej klatki i co 300. Jasne klatki nie logują nic.
* Odporność: cały kod bramki w `try/except Exception`; błąd = zwrócenie oryginalnej klatki, **jedno** ostrzeżenie w logu; po 20 błędach bramka wyłącza się do restartu usługi. Błąd samego `cv2` (np. `OSError` z kamery) **nie jest połykany**. Import dwa razy (np. `reload`, dwie nazwy modułu) nie owija drugi raz.
* Pamięć/CPU: nic nie jest trzymane między klatkami (test: żadna tablica w obiekcie bramki, klatki znikają przez `weakref`). Chwilowo +0,9 MB tylko dla ciemnej klatki (nowa tablica, oryginał zwalnia aplikacja). Koszt jednej oceny: ok. **50 µs** na laptopie x86
  (na Cortex-A35 szacunkowo 10-20x więcej, czyli ułamek milisekundy raz na ok. 2 s; **NIE SPRAWDZONE** na drukarce).

### 2.4 Dlaczego 19 i 22 (wybór wartości z klatek labu)

Na 1026 prawdziwych klatkach (978 z druku Kaercher + 48 z pustej płyty): ciemne (676): średnia szarość **17,0-19,36** (mediana 19,1); jasne (350): **>= 23,57** (zwykle 40-97). Odstęp 4,2. Próg 22 leży 2,6 nad ciemnymi i 1,6 pod najciemniejszą jasną.
Tło ciemnych klatek jest **neutralne**: mediana każdego kanału B, G, R = 19 w każdej z 676 klatek (zakres 17-19), średnia pikseli tła (<= 40) 19,01. Stąd **wypełnienie 19 we wszystkich kanałach** (to samo, co "tło ciemnej klatki", tylko bez diody). Klatki 17,0-17,1 (tuż po zgaszeniu światła) też są poniżej progu.

Dokładność siatki co 4. piksela (porównanie z pełną średnią na 1026 klatkach): odchyłka max **0,63**, średnia 0,07, p99 0,50, **0 błędnych decyzji** (siatka co 2.: max 0,17; co 8.: 1,8). Przy odstępie 4,2 to wystarcza; zwiększenie gęstości nic nie zmienia w decyzji.

## 3. Testy

`tests/test_algo_gate.py` (unittest, 36 testów; pisane **przed** kodem - pierwsze uruchomienie: 34 błędy + 1 niepowodzenie, bo modułu nie było). Wynik: **Windows 36/36 OK; WSL 36/36 OK (1 pominięty: prawdziwy loader OpenCV, bo WSL ma tylko pakiet apt bez `__init__.py`)**.
Sprawdzają m.in.: ciemna klatka -> jednolita (kształt, typ, oryginał nietknięty); jasna -> **ten sam obiekt** i ta sama krotka; granica (22 jasna, 21 ciemna, 22 z jednym pikselem 21 ciemna); wagi szarości (zielony 40 jasny, czerwony 60 ciemny); szare 2D, BGRA, 1-kanałowe, 1x1, puste, uint16/float32 (bez zmian), widok nieciągły, 1080p;
`ok=False` przechodzi; wyjątek w bramce -> oryginał + **jedno** ostrzeżenie; 20 błędów -> wyłączona na stałe; wyjątek kamery nie jest połykany; brak `cv2` / zepsuty `cv2` nie wywala importu; import dwa razy; przełączniki (env, plik, odświeżanie co 30 s, zła wartość); logowanie (jedna linia `active`, 1., 4., 8. ciemna klatka, jasne nie logują);
zapas pamięci; zapasowa nakładka; źródło zgodne ze składnią Pythona 3.9 (`ast.parse(feature_version=(3, 9))`), nagłówek SPDX, czysty ASCII, brak `import cv2` po nazwie; `module.json` (id, kolejność, `default: false`, jeden plik, brak `edits`); `build.build` przyjmuje moduł.
**Prawdziwy loader OpenCV** (test na Windows, `opencv-python 5.1.0`): kopia pakietu + nasz folder -> `import cv2` ładuje `cv2.q2gate`, `VideoCapture` jest owinięty, a z `Q2_GATE=off` nie jest. **DOWÓD.**

Pozostałe pliki testowe w projekcie: żadnego nie zmieniałem; cały zestaw `tests/test_*.py` (każdy osobno) przechodzi na Windows i w WSL (stan z końca pracy, razem z cudzymi plikami drogi 1 obecnymi wtedy w katalogu).

### 3.1 Test z prawdziwym plikiem `__init__.py` z firmware QIDI (ręczny, WSL) - DOWÓD

Drzewo `cv2/` zbudowane z **plików loadera dostarczonych w firmware 02.04** (`__init__.py`, `config*.py`, `misc`, `utils`, `mat_wrapper`, `data`; bez `typing`/`gapi`, które wymagają natywnego 4.12) + natywny `cv2` z WSL + nasz folder:
`import cv2` -> `cv2.q2gate` załadowany, `VideoCapture` owinięty; klatka ciemna z sekwencji obrazów -> jednolite 19 (średnia 19,0), jasne bez zmian; `Q2_GATE=off` -> `q2gate` załadowany, ale `VideoCapture` nietknięty;
po skasowaniu `__init__.py` z folderu (zostaje `__pycache__`, jak po odinstalowaniu) -> `import cv2` działa normalnie, `VideoCapture` nietknięty; bez folderu wcale -> jak oryginał.

## 4. Test offline na modelach (część C)

Skrypt (poza repo, scratchpad sesji) czyta klatki przez **prawdziwe** `cv2.VideoCapture` (sekwencja obrazów, dekoder FFmpeg jak strumień kamery) **dwa razy**: klasą oryginalną i klasą po instalacji bramki;
na obu wynikach uruchamia oba modele labu (odszyfrowane kopie w `ai-lab/models`, nie ruszałem hasła), obróbka jak `algo_app` (zwężenie do 320x320 / 256x256, BGR->RGB, /255, CHW), próg 0,50 (MEDIUM), NMS IoU 0,2.
WSL, onnxruntime 1.23, opencv 4.10 (na drukarce ORT 1.19.2, OpenCV 4.12 - liczby mogą się nieznacznie różnić).

| | 978 klatek druku Kaercher | 48 klatek pustej płyty |
|---|---:|---:|
| klatki ciemne (średnia < 22 po pełnej średniej) / jasne | 652 / 326 | 24 / 24 |
| decyzja bramki (siatka) inna niż po pełnej średniej | **0** | **0** |
| ciemne podmienione na jednolite 19 (kształt i typ jak oryginał) | **652 / 652** | **24 / 24** |
| jasne **bajt w bajt identyczne** z oryginalnym odczytem | **326 / 326** | **24 / 24** |
| ciemne: wynik makaronu > 0,50 **bez** bramki -> **z** bramką | **20 -> 0** (maks. 0,64 -> 0,00) | 0 -> 0 |
| ciemne: "obcy przedmiot" (`normal` lub `noodle` > 0,5) bez -> z bramką | 0 -> 0 (`onlypei` na bramkowanych = 1,00) | 0 -> 0 (1,00) |
| jasne: makaron > 0,50 bez -> z bramką | 0 -> 0 | 0 -> 0 |
| jasne: "obcy" bez -> z bramką (bez zmiany, jak powinno) | 322 -> 322 | 2 -> 2 |
| błędy bramki / liczniki | 0 błędów, 676 ciemnych z 1026 | |

Uwagi uczciwie: (1) 20 trafień zamiast 21 z `AI_MODELS_AUDIT.md`, bo tu klatki dekoduje FFmpeg (jak strumień), a tam `imread`; średnie obu dekoderów różnią się do 1,0 (to nie zmienia podziału ciemne/jasne). (2) Alarmy "obcy" na **jasnych** klatkach druku (322) to znany, bez znaczenia wynik
(wydruk na płycie); bramka ich nie zmienia - i **ma nie zmieniać**. (3) Na klatkach ciemnych bramka usuwa wszystkie trafienia makaronu, ale **czułość na prawdziwy makaron w ciemności nie była i nie jest mierzona** (brak takich klatek).
(4) Model "obcych" na jednolitej klatce daje `onlypei` 1,00 (= "czysta płyta PEI"), czyli nie wywołuje alarmu; ten sam wynik, co dla prawdziwych ciemnych klatek.

## 5. Instalacja i sprawdzenie na drukarce (NIE wykonywane - robi sesja główna, poza drukiem, za zgodą)

```
py tools/install.py install --host <adres drukarki> --with algo-app-gate
```
Instalator pokaże `new .../_internal/cv2/q2gate/__init__.py  (algo-app-gate)` i zrestartuje `algo_app`. Sprawdzenie (jako root, `sudo -n`):

```
systemctl is-active algo_app                       # active
journalctl -u algo_app -n 40 --no-pager | grep -i "q2gate\|Traceback"     # ostrzeżenia q2gate (WARNING) i ew. Traceback: nie powinno ich być
grep -h "q2gate" /var/log/algo_app/app_*.log | tail -5
```
Spodziewana linia kilka sekund po starcie: `... - app.q2gate - INFO - q2gate: active - frames with a mean grey value below 22.0 become a uniform 19 (every 300-th dark frame is logged)`.
W ciemnym druku: `q2gate: dark frame replaced by a uniform 19 (1 so far, mean grey 19.x, N frames seen)`. **Brak linii `active`** po restarcie = hak się nie załadował (patrz ryzyko 1). Wyłączenie bez restartu: `echo off | sudo tee /etc/q2-algo-gate.conf` (do 30 s), z powrotem: `sudo rm /etc/q2-algo-gate.conf`.
Usunięcie tylko tego modułu: `sudo rm -rf /usr/local/bin/algo_app/_internal/cv2/q2gate && sudo systemctl restart algo_app` (albo zwykły `uninstall` z kopii).

## 6. Co jest udowodnione, a co nie

**DOWÓD (uruchomione offline):** logika bramki (36 testów); wybór wartości z 1026 klatek; wynik na obu modelach (tabela wyżej); aktywacja przez **prawdziwy** loader OpenCV 5.1.0 (Windows) i przez **prawdziwe pliki loadera z firmware 02.04** (WSL);
`cv2.VideoCapture` da się dziedziczyć w OpenCV 4.10 i 5.1 (testowane); czysty zapis (bez zmian cudzych plików) i brak śladów po usunięciu pliku.

**NIE SPRAWDZONE na drukarce (założenia):**
1. że w zamrożonej aplikacji PyInstallera `importlib.import_module("cv2.q2gate")` znajduje folder na dysku (powinien: tak samo ładują się `cv2.misc`, `cv2.utils`, `cv2.mat_wrapper`, które też są plikami na dysku; w PYZ nie ma żadnego modułu `cv2`);
2. że OpenCV 4.12 na aarch64 pozwala dziedziczyć `VideoCapture` (ten sam generator wiązań co 4.10/5.1; w razie niepowodzenia działa zapasowa nakładka, przetestowana na zapieczętowanej klasie);
3. rzeczywisty koszt CPU na Cortex-A35 i wpływ na pamięć (spodziewane ułamki procenta i ~0 MB);
4. że ciemne klatki ze **strumienia MJPEG** mają średnią ~19 jak klatki zapisane (lab: klatki timelapse = pliki JPEG; dekoder strumienia ten sam FFmpeg, ale zapis i strumień to nie to samo źródło);
5. zachowanie z włączonym M4050 (patrz ryzyko 3).

## 7. Ryzyka i ograniczenia

1. **Hak się nie załaduje** (np. inny układ pakietu po aktualizacji QIDI): skutek = **zero zmian** w pracy AI (jak bez modułu), brak linii `active` w logu. Bezpieczny kierunek porażki.
2. **Skutek uboczny:** własny obraz usługi (`/capture`, `history_frames`, jej nagrania `ori/det/layer`) w ciemności to szara plansza, nie obraz z diodami. Timelapse Moonrakera jest niezależny (nietknięty). To różni drogę 2 od bramki tylko na wejściu modelu.
3. **Kontrola obcych (M4050)** w ciemności: dostaje jednolitą klatkę = "czysta płyta" (nie ma alarmu). Wg `ai-fixes` M4050 włącza światło, więc klatki są jasne (63-97) i bramka ich nie rusza; chwilowe ciemne klatki tuż po włączeniu światła staną się "pustą płytą" zamiast losowej. Czy model w ciemności w ogóle widział prawdziwy przedmiot - **nie mamy takich klatek**.
4. **Sztywny próg 22** (jedna kamera, jedno oświetlenie, 1026 klatek). Bardzo ciemna scena przy włączonym świetle (czarny filament + czarna płyta?) mogłaby dać średnią < 22 -> AI jej nie oceni (w praktyce płyta PEI jest jasna: najciemniejsza jasna klatka z wydrukiem miała 23,6, pusta płyta 50+). Próg i wypełnienie zmienia się plikiem `/etc/q2-algo-gate.conf`.
5. Po odinstalowaniu zostaje pusty `q2gate/__pycache__/` (nieszkodliwe; patrz 2.2).
6. Użycie dwóch bramek naraz (ta + przebudowany `main` drogi 1) jest bezpieczne, ale bez sensu przy porównaniu; **porównywać osobno**.

## 8. Czego właściciel może się spodziewać w porównaniu z przebudowanym `main` (droga 1)

* Ten sam efekt na wejściu modelu makaronu (ciemne klatki nie dają trafień), jeśli droga 1 bramkuje tak samo; różni się miejsce: tu **przy odczycie z kamery** (wpływa też na `/capture` i nagrania usługi), tam przy wejściu modelu.
* Droga 2: `main` pozostaje oryginałem (suma kontrolna jak dotąd), wyłączana plikiem bez restartu, usuwana jednym `rm`; zależy od mechanizmu loadera OpenCV (stabilny od lat, plik 02.04 = koło 4.12.0.88). Droga 1: zmienia `main`; ryzyko "zabezpieczeń pakietów" i każda aktualizacja QIDI trzeba przepakować.
* Oba rozwiązania **nie zmieniają** liczby klatek ani czasu modelu; droga 2 dodaje ułamek ms na klatkę.

## 9. Część D: drugi krok - ładowanie modelu bez potrójnej kopii i zwalnianie po druku

**Stan 23.11.2026:** hak 1 + hak 2 (ładowanie porcjami) są napisane jako osobny moduł opcjonalny `algo-app-stream-decrypt` (`modules/algo-app-stream-decrypt/`, testy `tests/test_algo_stream_decrypt.py`, 26 testów na atrapie szyfru CBC i - gdy jest pakiet `cryptography` - na prawdziwym AES). Moduł jest oddzielony od bramki jasności (własny folder `cv2/q2stream/`, własny wyłącznik `Q2_STREAM_DECRYPT=off`); gdy cokolwiek pójdzie źle, robotę robi oryginalna metoda QIDI. **NIE zainstalowany na drukarce, NIE zmierzony na drukarce.** Hak 3 (zwalnianie modelu po druku bez restartu) jest napisany w tym samym module (osobny wyłącznik `Q2_STREAM_RELEASE=off`; wątek na obiekt `DetectionDeal`, 120 s bezczynności drukarki, ponowne sprawdzenie tuż przed, `detector_release()` QIDI + `gc.collect()` + `malloc_trim`), przetestowany offline na atrapach z fałszywym zegarem, **NIE zainstalowany**. Odstępstwa od opisu niżej: zwalnia tylko model makaronu (model obcych przedmiotów zostaje, ok. 17 MB, żeby nie ścigać się z kontrolą M4050); gdy obiekt drukarki nie wygląda jak oczekiwany, nigdy nie zwalnia; po 5 nieudanych próbach przestaje. `algo-app-recycle` robi dziś to samo restartem usługi.
Odstępstwo od opisu niżej: hak 1 w wersji (a) - wyszukiwarka `sys.meta_path` z opakowanym ładowaczem, który przed uruchomieniem modułu oddaje oryginalny ładowacz (moduł nie zostaje z naszym ładowaczem). Odcisk zgodności: dokładne nazwy zmiennych lokalnych i wymagane nazwy użyte w metodzie (bez dokładnego porównania `co_names`, żeby drobna różnica kolejności nie wyłączała poprawki bez powodu).

Źródło: dezasemblacja `DetectionDeal` (`algo_app_tools/dis/src__detection_deal.txt`); klucz szyfrowania to stała ustawiana w `DetectionDeal.__init__` (`self.encryption_key`) - **nasz kod ma go czytać z `self`, nigdy nie zapisywać w pliku**.

**Co dziś robi QIDI (DOWÓD z kodu):** `decrypt_weight(self, encrypted_path)`: `iv = f.read(16)`, `ciphertext = f.read()` (44,6 MB), `padded = cipher.decrypt(ciphertext)` (44,6 MB), `plaintext = unpad(padded, 16)` (kolejne 44,6 MB), zapis do `NamedTemporaryFile(delete=False)`, zwraca ścieżkę; wołające kasują plik po załadowaniu sesji ONNX.
`detector_release()` istnieje i **nikt jej nie woła**; `pei_detector` jest tylko zerowany bez `gc.collect()`. Model ładuje się, gdy `self.detector is None` **oraz** `printer.is_printing_begin` (warstwa >= 2) - czyli dopóki nie ma druku, wątek `detect_run` w ogóle nie dotyka detektora.

**Hak 1 - moment zaczepienia.** Nasz kod działa za wcześnie (przy `import cv2`, zanim powstanie `src.detection_deal`). Dwie drogi, polecam pierwszą:
(a) `importlib.abc.MetaPathFinder` wstawiony na początek `sys.meta_path`: dla `src.detection_deal` prosi dalsze finder'y (PyInstaller `FrozenImporter`) o `spec`, owija `spec.loader.exec_module` tak, by po wykonaniu modułu wywołać `patch(module)`; brak wyścigu, bo `exec_module` kończy się przed użyciem klasy;
(b) wątek-demon, który co 0,2 s sprawdza `sys.modules.get("src.detection_deal")` i łata po pojawieniu się (maks. 2 min). Prostszy, ale ma teoretyczne okno wyścigu (pierwsze użycie `decrypt_weight` następuje dopiero w druku/M4050, więc praktycznie bezpieczne).
**Odcisk zgodności:** przed podmianą porównać `DetectionDeal.decrypt_weight.__code__.co_varnames` i `co_names` z oczekiwanymi (`self, encrypted_path, key, f_in, iv, ciphertext, cipher, padded_plaintext, plaintext, temp_model`; wywołania `AES.new`, `unpad`, `tempfile.NamedTemporaryFile`); przy jakiejkolwiek różnicy **nie łatać** i zalogować ostrzeżenie (aktualizacja QIDI = brak szkody).

**Hak 2 - nowe `decrypt_weight` (bez potrójnej kopii).** Ta sama sygnatura i wynik (ścieżka pliku tymczasowego, kasowana przez wołającego). Algorytm: otwórz plik, `iv = read(16)`, utwórz `AES.new(self.encryption_key..., MODE_CBC, iv)` tak samo jak oryginał (klucz uzupełniony do 32 bajtów), czytaj i deszyfruj **porcjami po 1 MiB (wielokrotność 16)**,
zapisuj od razu do pliku tymczasowego; **ostatnią porcję zatrzymaj**, usuń z niej dopełnienie PKCS#7 (`unpad`) dopiero na końcu. CBC pozwala deszyfrować strumieniowo, bo każdy blok zależy tylko od poprzedniego bloku szyfrogramu (obiekt `cipher` utrzymuje stan między wywołaniami `decrypt`).
Szczyt RAM z ~3 x 44,6 MB (WNIOSEK z kodu: ok. +134 MB) spada do ~1-2 MiB + plik; wynik **identyczny** bajt w bajt (test: odszyfruj oba sposoby na losowych danych własnego klucza testowego i porównaj; na modelach QIDI porównać sumę SHA-256 pliku wyjściowego z oryginalną funkcją **lokalnie, w WSL**, bez zapisywania wyniku w repo).
ONNX Runtime nadal wczytuje plik 44,6 MB do pamięci przy tworzeniu sesji (to osobny koszt, +66-75 MB po załadowaniu wg audytu).

**Hak 3 - zwolnienie po druku.** Wątek-demon (jeden), który zna instancję `DetectionDeal` (przechwycić w owiniętym `__init__` jako `weakref`) i `inst.printer` (`PrinterStatusControl`: `is_printing`, `is_printing_begin`, `is_paused()`):
gdy `is_printing` jest `False` **nieprzerwanie od >= 120 s** (próbkowanie co 5 s; tak samo jak `algo-app-recycle`) i `inst.detector is not None` (lub `inst.pei_detector is not None`) -> ponowne sprawdzenie warunku tuż przed -> `inst.detector_release()` (bierze `__session_lock`, więc poczeka na trwającą inferencję; robi `release_model`, `detector = None`, `gc.collect()`),
`inst.pei_detector = None`, `gc.collect()` i **`ctypes.CDLL("libc.so.6").malloc_trim(0)`** (glibc sam nie odda areny). Następny druk załaduje model znowu przy warstwie 2 (jak dziś po restarcie usługi).
Warunek 120 s wystarcza, bo od startu druku do warstwy 2 mija wiele minut, a model ładuje się tylko przy `is_printing_begin`; w najgorszym razie zerujemy świeżo załadowany model i ładuje się po raz drugi (strata czasu, nie błąd).

**Opcjonalnie (osobno, osobny pomiar A/B):** `onnxruntime.SessionOptions` podmienione na podklasę z `enable_cpu_mem_arena = False` i `enable_mem_pattern = False` (hipoteza z `ALGO_APP_MEMORY_AUDIT.md` 3.2 C: 10-30 MB; koszt: nieco wolniejsza inferencja).

**Co to daje (WNIOSEK, NIEZMIERZONE):** usuwa chwilowy szczyt ~+134 MB przy ładowaniu (najgorsza chwila dla Klippera przy 26-48 MB wolnych) i oddaje model między drukami bez restartu usługi; **nie zmniejsza** zużycia w trakcie druku (model nadal ładuje się raz na druk).
**Ryzyka:** kruchość wobec aktualizacji QIDI (odcisk kodu to łagodzi); wątki (`detect_run` czyta `self.detector` bez blokady, stąd warunek 120 s i `__session_lock`); `malloc_trim` nie gwarantuje zwrotu; żadnych modeli ani klucza w repo; test jednostkowy tylko na własnych danych testowych.
**Testy do napisania najpierw:** równość wyjścia nowego i starego odszyfrowania (losowe dane, rozmiary 0 / 15 / 16 / 17 bajtów / 1 MiB +- 1 / 44,6 MB); `unpad` przy złym dopełnieniu = ten sam wyjątek; odcisk odrzuca zmienioną funkcję; wątek zwalniający nie rusza modelu w druku/pauzie; podwójne łatanie.
