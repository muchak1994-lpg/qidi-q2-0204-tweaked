# Audyt modeli AI w `algo_app` (QIDI Q2, firmware 01.01.02.04) - czy da się je poprawić? (2026-11-22)

Napisany **bez żadnego kontaktu z drukarką** (zero SSH, Moonrakera, Fluidd, Klippera; druk trwał).
Źródła: oficjalna paczka QIDI 02.04 już leżąca na dysku (`work/stock/data.tar.xz`), kod `algo_app` odczytany wcześniej (folder notatek, patrz koniec),
oraz archiwum wcześniejszych prób z października (`QIDI_Q2_historia_do_20261110.zip`: ok. 50 folderów o foreign/spaghetti). Niczego w repo nie zmieniłem.

**Oznaczenia:** **DOWÓD** = widziane w pliku modelu / kodzie / zapisanym wyniku (źródło podane). **WNIOSEK** = wynika z dowodów, ale nikt nie sprawdził wprost.
**HIPOTEZA** = prawdopodobne, niesprawdzone. **BRAK DANYCH** = nie wiemy.

---

## 0. Streszczenie dla właściciela

1. **Oba modele da się otworzyć i opisać w całości.** Plik `algo.enc` (makaron) to sieć **YOLOv8s** (wykrywanie, 11 mln wag, 44,6 MB), `algo_pf.enc`
   (płyta/obce przedmioty) to maleńka sieć **YOLOv8n-cls** (klasyfikacja całego obrazu, 1,4 mln wag, 5,8 MB). Szyfrowanie to zwykłe AES z 8-znakowym hasłem
   wpisanym w program (nie przepisuję go tu). Obie sieci mają jawne metadane (data, wersja narzędzia, klasy). **DOWÓD** (odczyt plików). (sekcja 1)
2. **Kluczowe odkrycie: aplikacja potrafi wczytać własny, NIEzaszyfrowany model**, wystarczy plik `.onnx` w katalogu `weights/` i dwa wpisy w `config.xml`
   (`model_name`, `model_pf_name`). Nie trzeba ruszać programu `main` ani szyfrować. **DOWÓD** (kod `DetectionDeal`: szyfrowanie tylko gdy nazwa kończy się `.enc`). (sekcja 4b)
3. **Wykrywanie "obcego przedmiotu" NIE jest wykrywaniem przedmiotu.** To **klasyfikacja całego zdjęcia** na 4 klasy (`noodle`, `nopei`, `normal`, `onlypei`);
   za "obcy przedmiot" kod uznaje dowolne zdjęcie, na którym wygrywa `normal` albo `noodle` z wynikiem > 0,5. Model **nie zna położenia** niczego na obrazie,
   więc nie odróżni głowicy od przedmiotu. **DOWÓD** (kod `pei_box_draw` + budowa modelu). (sekcja 3)
4. **Ten klasyfikator myli się także na pustej płycie, bez żadnej głowicy w roli winnego.** W październiku na 25 zapisanych zdjęciach pustej płyty dał **7 fałszywych
   alarmów (28 %)**; jedno takie zdjęcie dało alarm 100 razy z 100 (wynik jest powtarzalny, nie losowy), a przy jednej wysokości stołu (Z50) alarm był 3 razy na 3.
   Zasłonięcie głowicy na tym zdjęciu alarmu NIE usunęło. **DOWÓD** (zapisane wyniki z 17-22.10).
5. **Czy dzisiejszy alarm to była głowica?** Nie umiem tego rozstrzygnąć bez zdjęcia z tamtej chwili. Log z 22.11 pokazuje alarm od jednej klatki ok. 4 s po starcie kontroli (14:46) i brak alarmu
   w drugiej kontroli 5 min później, ale bez klasy ani wyniku. Dane z października tej hipotezy nie potwierdzają dla zbadanego zdjęcia; głowica w środku stołu nie była nigdy testowana.
   **BRAK DANYCH** - w sekcji 7 jest, co dokładnie pobrać z drukarki. Natomiast **fałszywy makaron w ciemności jest potwierdzony logiem** (6 trafień 0,51-0,66, wszystkie w ciemności, żadne w świetle).
6. **Makaron:** pauza wymaga **10 klatek z wykryciem (MEDIUM)** zebranych w całym druku (licznik nie maleje, resetuje się tylko przy starcie druku), klatka co ok. 8-9 s.
   Model był trenowany do jasnego filamentu na złotej płycie przy włączonym świetle (opis QIDI); brak jakiejkolwiek bramki jasności w kodzie, więc w ciemności
   wynik jest nieprzewidywalny. **DOWÓD / WNIOSEK** (sekcja 2, 3.4).
7. **Co jest warte zrobienia:** (a) **najpierw laboratorium na laptopie** (te same modele, zapisane zdjęcia, bez drukarki), bo prawie wszystkie pytania da się tam rozstrzygnąć;
   (b) **własny, mały klasyfikator "obce przedmioty"** wytrenowany na zdjęciach z Twojej kamery - tani, wymienialny przez `config.xml`, bez łatania `main`;
   (c) makaronu **nie ruszać** (model dobry w swojej dziedzinie, ponowny trening to tygodnie pracy i ryzyko dla bezpieczeństwa); tylko logika/bramki, jeśli dane pokażą potrzebę.
8. **Uczciwie:** nie uruchomiłem żadnego modelu na obrazach (na tym koncie nie ma numpy/onnxruntime, a instalacja = pobieranie plików, o co nie pytałem). Wszystkie liczby o
   skuteczności pochodzą z zapisanych wyników z października. Nikt nie zmierzył skuteczności na dużym, niezależnym zbiorze zdjęć.
9. **Prawo:** nie wolno wkładać do repozytorium plików modeli, ani odszyfrowanych, ani kodu QIDI. Narzędzia działające na pliku użytkownika - tak (jak dziś instalator). Własne wytrenowane modele
   z własnych zdjęć można publikować, ale trening w narzędziu Ultralytics oznacza licencję AGPL-3.0 (zgodną z GPL-3.0 tego projektu). To nie jest porada prawna. (sekcja 5)
10. **Pierwszy krok po zgodzie:** sprawdzić 4 rzeczy na drukarce tylko do odczytu (sekcja 7) i na laptopie postawić "stanowisko testowe" (sekcja 6, krok 2).

---

## 1. Jakie modele są i jak je odczytałem (zakres 1)

Pliki wyjąłem z oficjalnej paczki 02.04 (`work/stock/data.tar.xz`, ta sama, którą instalator pobiera z serwera QIDI) do katalogu tymczasowego sesji, odszyfrowałem kopię
i przeczytałem strukturę własnym, 150-liniowym czytnikiem formatu ONNX (bez bibliotek). Odszyfrowane kopie **skasowałem** na koniec pracy. Skrypty: folder notatek `ai_models_tools\`.

| | **Model "makaron"** | **Model "płyta / obce przedmioty"** |
|---|---|---|
| Plik na drukarce | `/usr/local/bin/algo_app/weights/algo.enc` (44 576 416 B, SHA256 `90c03041...ad2`) | `.../weights/algo_pf.enc` (5 775 664 B, SHA256 `e2b51b30...c2dc`) |
| Format po odszyfrowaniu | ONNX (ir 8, opset 15), PyTorch 1.12 | ONNX (ir 7, opset 12), PyTorch 1.12 |
| Architektura | **YOLOv8s-detect** (szerokości warstw 32-64-128-256-512; 64 konwolucje; 11 134 211 liczb FP32) | **YOLOv8n-cls** (szerokości 16-32...; 26 konwolucji; 1 440 004 liczb FP32; klasyfikator 1280 -> 4) |
| Wejście | `[1,3,320,320]` FP32, RGB, /255 | `[1,3,256,256]` FP32, RGB, /255 |
| Wyjście | `[1,10,2100]` = 4 liczby ramki + 6 wyników klas, dla 2100 miejsc (40x40 + 20x20 + 10x10 siatek) | `[1,4]` = cztery prawdopodobieństwa (softmax) |
| Klasy | 0 `mil`, 1 `mod`, 2 `ser`, 3 `sim`, 4 `com`, 5 `pri` | 0 `noodle`, 1 `nopei`, 2 `normal`, 3 `onlypei` |
| Metadane eksportu | "Ultralytics `best_s_q2_256_192_250819`", wersja narzędzia **8.3.170**, data **2025-08-19**, licencja zapisana: **AGPL-3.0** | "Ultralytics YOLOv8n-cls ... trained on ./dataset", **8.3.170**, data **2025-09-27**, AGPL-3.0 |
| Rozmiar w RAM po załadowaniu | **+66-75 MB** (pomiary z audytu pamięci) | ok. +17 MB (dane właściciela) |

**DOWÓD** dla całej tabeli: odczyt plików po odszyfrowaniu (`onnxinfo.py`). Metadane są w samych plikach.

**Znaczenie klas modelu makaronu:**
- Klasy 0, 1, 2 (`mil`, `mod`, `ser`) = makaron o rosnącej "wadze" (kod liczy je z mnożnikami 1, 2, 3). Nazwy to skróty; "mild / moderate / serious" to **HIPOTEZA** (nazwy dosłownie nie są objaśnione).
- Klasa 5 (`pri`) = **głowica drukarki**: kod funkcji `remove_class_printer_regions` bierze `class_id == 5` jako "class_printer" i wycina te obszary przy porównywaniu warstw. **DOWÓD** (kod).
- Klasy 3 i 4 (`sim`, `com`) - model je wykrywa, ale **kod ich nigdy nie używa** do żadnej decyzji. Do czego służą (może "podobne do makaronu", "wspólne elementy"?) - **BRAK DANYCH**.
  Test z 16.10 na zwykłej klatce Q2: `com` 0,84 i `pri` 0,93, makaron 0,003 - czyli `com` występuje w normalnej scenie. **DOWÓD** (zapisany wynik).
- Domyślna lista 20 nazw w kodzie (`mil, mod, ser, sim, com, pri, pei, pei_features1-3, no_pei...infill..support`) zaczyna się dokładnie od tych 6 - **WNIOSEK**: starszy model miał 20 klas
  (makaron + rozpoznawanie płyty PEI + wypełnienie/podpory), obecny to wersja okrojona do 6.

**Ślad po porzuconym, starszym sposobie wykrywania obcych przedmiotów:** w programie leży niewywoływany kod `foreign_check.py` (klasyczne przetwarzanie obrazu: kontury, kolory, rozmycie)
i `draw_foreign_check` (wielokąt wyznaczony z wykrytych "cech PEI" starego 20-klasowego modelu). Żadna aktywna ścieżka go nie woła. **DOWÓD** (przeszukanie wszystkich modułów).

**Szyfrowanie (DOWÓD, kod `DetectionDeal.decrypt_weight`):** pierwsze 16 bajtów pliku = wektor IV, reszta = AES-CBC, dopełnienie PKCS7; klucz = 8-znakowy tekst wpisany w klasie `DetectionDeal`, dopełniony zerami do 32 bajtów.
Odszyfrowanie działa w pamięci w trzech kopiach, wynik trafia do pliku tymczasowego, po wczytaniu przez ONNX Runtime plik jest kasowany (szczegóły: audyt pamięci, sekcja 3.2 B).
Zabezpieczenie jest słabe (klucz leży w programie), ale to **nie jest przeszkoda techniczna** dla własnych modeli (sekcja 4b).

---

## 2. Cały potok decyzji (zakres 2)

```
kamera (ustreamer, MJPEG 640x480) --co ok. 2 s: otwórz, 1 klatka, zamknij--> video_input_deal
   |  (tryb "makaron": co ok. 2 s; tryb "kontrola obcych": co 1 s przez 15 s po komendzie /set_homing_state)
   v
DetectionDeal  (jeden wątek, jeden rdzeń)
   - makaron: model algo.enc -> wynik [1,10,2100] -> filtr conf_thres -> NMS -> klatka z ramkami
   - obce/płyta: model algo_pf.enc -> 4 prawdopodobieństwa -> reguły progów (pei_box_draw)
   v
DetectPosDeal  (liczniki) --> SAVE_VARIABLE qdc_ai_error_code "noodle=N status=1 time=..." / "foreign=N status=1 ..."  (przez Moonraker)
   v
ekran QIDI (qidiclient) czyta qdc_ai_error_code --> natywne PAUSE + okno z przyciskami
```

### 2.1 Pobranie i przygotowanie klatki

| Krok | Co robi kod | Status |
|---|---|---|
| Źródło | `http://127.0.0.1/webcam/?action=stream`, rozdzielczość **640x480** (zapisane klatki testowe) | DOWÓD |
| Odczyt | w trybie "stream" każdy obieg: `VideoCapture(url)` -> `read()` -> `release()`; pętla ma `sleep(2)` (makaron) lub `sleep(1)` (kontrola obcych) | DOWÓD |
| Przycięcie obszaru | **brak** - cała klatka idzie do modelu (ustawienie `valid_area_start` jest wczytywane, ale nigdzie niewykorzystane) | DOWÓD |
| Skalowanie | `cv2.resize` całego obrazu 640x480 do **320x320** (makaron) lub **256x256** (obce) **bez zachowania proporcji** (ściśnięcie 4:3 -> 1:1); BGR->RGB; dzielenie przez 255; kolejność CHW | DOWÓD (kod + bytecode zapisany 22.10) |
| Jasność / światło | **brak** jakiejkolwiek kontroli jasności w aktywnej ścieżce (kontrola średniej jasności istnieje tylko w nieużywanym `foreign_check.py`) | DOWÓD |
| Wstrzymanie pracy | AI czeka, gdy: druk jeszcze nie na warstwie >= `start_layer` (2), druk wstrzymany, temperatura procesora >= 80 °C (`cpu_temperature` w `config.xml`) | DOWÓD |

Częstość: licznik klatek rósł **co ok. 8-9 s** w druku z pełnym AI (test 16.10, jeden rdzeń ~99 % zajęty). **DOWÓD** (zapisany pomiar). Procesor to Rockchip RK3308 (4 rdzenie
Cortex-A35, bez akceleratora AI; `docs/ZRAM_SWAP_Q2.md`), usługa przypięta do jednego rdzenia (`CPUAffinity=3`, `Nice=19`).

### 2.2 Makaron - od wyniku modelu do pauzy

1. Wynik `[1,10,2100]` -> dla każdego z 2100 miejsc bierze się największy z 6 wyników klas; zostają te powyżej **`conf_thres`**; potem NMS osobno dla każdej klasy z **`iou_thres`**. **DOWÓD** (`process_output`).
2. Czułość (zdarzenie z `save_variables.noodle_sensitivity_level`, ustawiane przez ekran): **DOWÓD** (`MoonrakerSubscribe.from_customer_configs`):

   | Poziom | `conf_thres` (próg jednej klatki) | `conf_count` (próg alarmu) |
   |---|---:|---:|
   | HIGH | 0,43 | 5 |
   | **MEDIUM** | **0,50** | **10** |
   | LOW | 0,58 | 15 |

   W `config.xml` (stan fabryczny) stoi 0,48 i IoU 0,2; po pierwszej wiadomości z ustawieniem czułości próg jest nadpisywany. IoU zostaje 0,2 (czułość go nie zmienia). Programowa wersja z paczki 02.04
   ma w MEDIUM liczbę 10; **w październiku testowano własną wersję `main` z liczbą 8** (zapisano "zaakceptowany MEDIUM 0,50/8") - **czy jest teraz na drukarce: BRAK DANYCH** (sprawdza to suma SHA256 pliku `main`, sekcja 7).
   W kodzie czułości `conf_count` jest ustawiane dwa razy, a `count_count` ani razu - wygląda na pomyłkę QIDI przy kopiowaniu (**HIPOTEZA**, bez skutku: `count_pause`/`conf_pause` w `config.xml` = False).
3. **Wynik klatki** `S = suma po ramkach: wynik x waga`, gdzie waga = 1 dla `mil`, 2 dla `mod`, 3 dla `ser`; klasy 3, 4, 5 nie liczą się. Klatka jest "dodatnia", gdy `S > 0`. **DOWÓD** (`detections_frame_scores`).
4. **Liczniki** (cały druk): `total_detect_find_count` = ile klatek było dodatnich, `total_conf_count` = suma `S`. **Alarm (`status=1`), gdy liczba klatek >= N LUB suma >= N** (N z tabeli).
   - Liczniki **nie maleją** z czasem i nie wymagają kolejnych klatek; zerują się **tylko przy starcie druku**. Pauza czyści tylko "opublikowany" wynik, ale nie liczniki w programie. **DOWÓD** (kod + test jednostkowy z 16.10: "5 dodatnich przeplatanych zerami dało alarm w 9. iteracji").
   - **WNIOSEK:** w długim druku rzadkie, pojedyncze fałszywe wykrycia (np. jedno na 20 min) w końcu dojdą do 10. Po wznowieniu po alarmie liczniki nadal są >= N, więc **następna dodatnia klatka znowu natychmiast wywoła alarm**.
5. Wysłanie: `SAVE_VARIABLE VARIABLE=qdc_ai_error_code VALUE='"noodle=<licznik> status=<0/1> time=<unix>"'` przez Moonraker, z limitem czasu 3 s (znane przekroczenia, ale wartości dochodzą). **DOWÓD** (kod + test 16.10).
6. Pauza: gdy `status=1`, **native `PAUSE W=1` pojawiło się ok. 2,6 s później** (HIGH, 16.10). **Komendy `SET_AI_DETECT_RESULT` nikt nie wysłał** - to jawny, ale nieużywany uchwyt w Klipperze; faktycznym odbiorcą
   zapisu jest najpewniej ekran (`qidiclient`, czyta `qdc_ai_error_code`) - **WNIOSEK** (tak zapisano w październiku, kod ekranu nie był śledzony do końca). `algo_app` sam nie pauzuje (`count_pause`/`conf_pause` = False).
7. Wykrywanie przesunięcia modelu ("model shift", porównanie warstw z wycięciem głowicy `pri`) jest w kodzie, ale `is_md_check` = False i **nic w aplikacji go nie włącza** (nie ma obsługi takiego ustawienia).
   **WNIOSEK:** przełącznik "model shift/collapse" na ekranie nie jest podpięty do tej aplikacji w tej wersji.

### 2.3 "Obce przedmioty" i "płyta PEI" - od wyniku modelu do pauzy

1. Uruchomienie: kontrola zaczyna się, gdy aplikacja dostanie flagę "homing" (`POST /set_homing_state` - **nasz** moduł `ai-fixes` ją wysyła w nowym `M4050`; fabrycznie QIDI wyłączyło `M4050`
   wprost w kodzie, komentarz: "obecnie dla wszystkich modeli 4050 trzeba anulować"). Wtedy przez **15 s** (stała) aplikacja czyta klatkę co ~1 s i uruchamia klasyfikator. **DOWÓD**.
2. Reguły po klasyfikacji (kod `pei_box_draw`, kolejność): **DOWÓD**

   | Najwyższa klasa | Warunek | Skutek |
   |---|---|---|
   | `nopei` | wynik > 0,98 | brak płyty PEI (flaga `no_pei`) |
   | `onlypei` | wynik > 0,98 | "jest płyta PEI" (`has_pei`) |
   | `normal` | wynik > **0,5** | **`foreign` = 1 (obcy przedmiot)** |
   | `noodle` | wynik > **0,5** | **`foreign` = 1** |
   | (druga reguła `onlypei` -> `no_foreign`) | nieosiągalna | martwy kod |

   Czyli "pusta płyta" jest uznawana tylko przy `onlypei` > 0,98 (reguła zbyt ostra, w praktyce prawie nigdy), a **wszystko, co klasyfikator nazwie `normal` albo `noodle` z wynikiem > 0,5, jest "obcym przedmiotem"**.
3. Liczniki i alarm: każda dodatnia klatka dodaje do `foreign_count` i od razu wysyła `foreign=<licznik> status=1` - **jedna klatka wystarcza**. W naszym `ai-fixes` pierwsza dodatnia klatka
   w oknie 20 s wstrzymuje start druku (z przyciskami Wznów/Anuluj). **DOWÓD** (kod algo_app + `modules/ai-fixes`). Nie ma głosowania ani porównania z "pustą płytą".
4. Pomiar na żywo (23.10): prawdziwa tacka na płycie -> alarm po ok. 4 s, okno QDC_500_005_005_001 pokazało się na ekranie, Continue i Stop zadziałały. **DOWÓD** (zapis z 23.10).

---

## 3. Fałszywe alarmy (zakres 3)

### 3.1 Dlaczego głowica (albo cokolwiek) może zostać uznana za "obcy przedmiot"

- **DOWÓD:** klasyfikator widzi **całe ściśnięte zdjęcie** i wybiera jedną z 4 etykiet. Nie ma ramek, masek, obszarów ani odniesienia do "pustej płyty tej drukarki". Nie wie, gdzie jest głowica ani czym jest.
- **DOWÓD:** `onlypei` (= wzorzec "czysta płyta") musi wygrać; wszystko inne, co przypomina `normal` > 0,5, daje alarm. Czyli zdjęcie, które *wygląda inaczej niż zdjęcia treningowe czystej płyty* (inna wysokość stołu,
  inne światło, głowica w innym miejscu, inna płyta, odbicie), może dać alarm bez żadnego przedmiotu.
- **HIPOTEZA (nie sprawdzona):** ściśnięcie 640x480 -> 256x256 może różnić się od tego, co model widział w treningu (standard Ultralytics dla klasyfikacji: skalowanie krótszego boku + wycinek ze środka, który
  obcina boki zdjęcia). Prawdziwe przekształcenia treningowe QIDI nie są znane. To tani test na laptopie (sekcja 6).

### 3.2 Co faktycznie zmierzono w październiku (wszystko na zapisanych zdjęciach, bez drukarki)

| Próba | Wynik | Źródło |
|---|---|---|
| Próg 0,5 (fabryczny), 25 zdjęć **pustej** płyty | **7 fałszywych alarmów** | `FOREIGN_THRESHOLD_REPLAY_20261017` |
| to samo, 13 zdjęć tacki/pudełka, 6 zdjęć makaronu | 13/13 i 6/6 wykryte | tamże |
| próg 0,8 / 0,9 / 0,95 / 0,98 | puste: 3 / 1 / 0 / 0 fałszywych; tacka: 13 / 13 / 9 / 8 z 13; makaron: 4 / 3 / 2 / 2 z 6 | tamże |
| Próg 0,55 | **bez żadnej zmiany** (wyniki są daleko od progu) | `FOREIGN_THRESHOLD55_20261022` |
| Jedno puste zdjęcie, 100 razy | **100/100 alarm**, wynik `normal` 0,896 za każdym razem (powtarzalny, nie losowy) | `FOREIGN_REPEAT100_20261022` |
| Pusta płyta, głowica zaparkowana X85/Y287,5, stół Z80 / Z50 / Z20 | alarmów **0/3, 3/3, 3/3** (przy Z80 po powtórzeniu znów 0/3) | `FOREIGN_POSE_LIVE_20261017` |
| Wysokość stołu 20-80 mm, głowica X15/Y260, po 2 zdjęcia | 1 alarm na 10 (Z20), żadne zdjęcie nie przekroczyło 0,98 `onlypei` | `FOREIGN_HEIGHT_SWEEP_20261016` |
| Zakrycie obszaru głowicy (średni kolor / rozmycie) na pustym zdjęciu Z50 | wynik `normal` 0,896 -> **0,956 / 0,914** (alarm zostaje) | `FOREIGN_OCCLUSION_20261022` |
| Zamaskowanie całej górnej połowy obrazu | puste: 7/19 -> 0/19, tacka 13/13 zostaje, **ale makaron 6/6 -> 0/6** | tamże |
| Kadr prawie w całości zasłonięty głowicą | model zwrócił `onlypei` **0,99999** (czyli "czysta płyta" - błąd w drugą stronę) | `FOREIGN_IMAGE_MATRIX_20261017` |
| Cienki kwadrat 10x10 mm, 3 zdjęcia | **0/3 wykrytych** przy każdym progu | `FOREIGN_THRESHOLD_REPLAY` |

**Wniosek z tych danych (WNIOSEK):**
- Klasyfikator ma wysoki odsetek fałszywych alarmów na pustej płycie (7/25 na tym zbiorze; zbiór mały i skorelowany - nie wolno z niego liczyć ogólnego odsetka) i **te alarmy są systematyczne**
  (to samo zdjęcie daje zawsze to samo), zależą od wysokości stołu/ujęcia.
- **Głowica nie była sprawcą w zbadanym przypadku** (zakrycie jej nie pomogło), a kadr z głowicą na pół obrazu dał wynik odwrotny (brak alarmu). **Nie wiadomo**, co dzieje się, gdy głowica stoi **w środku** płyty -
  takiego zdjęcia w zapisach nie ma.
- Podniesienie progu zmniejsza fałszywe alarmy kosztem utraty prawdziwych (0,95: 0 fałszywych, ale 4/13 tacek i 4/6 makaronu gubi). To zamiana jednego błędu na drugi.
- Samo "głosowanie kilku klatek" **prawie nic nie da**, bo błąd jest powtarzalny: przy Z50 wszystkie 3 klatki z rzędu były fałszywie dodatnie. Pomaga tylko przeciw losowemu szumowi.

### 3.3 Dzisiejszy alarm "obcy przedmiot na środku stołu" - co wiemy

- **Fakty z logu `algo_app` z 22.11 (odczyt zrobiła główna sesja, ja ich nie widziałem w oryginale):** 14:45:59 start sprawdzania; **14:46:03 `[Foreign Check]: foreign_count=1`** (czyli
  **pierwsza lub jedna z pierwszych klatek, ok. 4 s po starcie**, jedna klatka wystarczyła); 14:46:04 `M4050: foreign object detected; waiting for Stop/Continue` (`foreign=1 status=1`);
  14:46:31 przekroczenie czasu przy wysyłaniu wyniku (znany błąd 3 s). Drugie sprawdzenie o 14:51:17: `no positive detection; continuing`. Właściciel: na stole prawdopodobnie była tylko głowica.
  **W logu nie ma klasy, wyniku ani położenia** - z samego logu nie wiadomo, co model uznał za przedmiot. **DOWÓD** (relacja głównej sesji z logu).
- **Co z tego wynika (WNIOSEK):** pierwsze sprawdzenie dało alarm od razu, drugie (po 5 min, prawdopodobnie przy innym ustawieniu głowicy/stołu/światła - tego nie wiem) nie dało nic. To pasuje do
  wyniku z października, że klasyfikator reaguje na **ujęcie** (pozycję, wysokość, światło), a nie na przedmiot; nie dowodzi jednak, że sprawcą była głowica.
  Rozstrzygnęłoby to jedno zdjęcie z 14:46 (brak) albo porównanie położenia głowicy z `klippy.log` z tych dwóch minut (sekcja 7, pkt 5).
- Możliwe wyjaśnienia (**wszystkie HIPOTEZY**):
  1. systematyczny fałszywy alarm klasyfikatora dla danej wysokości stołu / pozycji głowicy / światła (najlepiej udokumentowany w danych);
  2. głowica zaparkowana tam, gdzie klasyfikator jej nie zna. Kontrola w naszym `ai-fixes` odbywa się **przed pierwszą komendą pliku, bez ruchu** - głowica stoi, gdzie została po poprzedniej pracy
     (po końcu druku: okolice X90/Y270, wg zapisu 23.10), a po ręcznych ruchach / pauzie może stać wszędzie;
     (Dopisek 26.11.2026: nowsza wersja `ai-fixes` przed kontrolą odsuwa głowicę do tylnego prawego rogu; opis powyżej dotyczy wersji z tego audytu.)
  3. prawdziwy mały przedmiot (np. kawałek filamentu, nalot) - nie można wykluczyć.
- Co dokładnie pobrać z drukarki, żeby to rozstrzygnąć (tylko odczyt): sekcja 7.

### 3.4 Fałszywy makaron w ciemności

- **DOWÓD:** brak bramki jasności; model był trenowany do określonych warunków (opis QIDI: **jasny filament, złota płyta PEI, włączone światło komory**, strona wiki Q2, zacytowana w notatkach z 16.10).
- **DOWÓD (właściciel, 2026-11-20):** w ciemności `algo_app` nadal liczy i zgłasza makaron; nasz `dark-mode-light` jedynie blokuje po stronie Klippera pauzę.
- **DOWÓD (log z 22.11, relacja głównej sesji):** 4 wykrycia makaronu między 16:12:42 a 16:17:03 (wyniki 0,51 / 0,66 / 0,63 / 0,59, MEDIUM, próg 0,5) oraz 2 po restarcie usługi (16:47:29 i 16:48:10),
  **wszystkie w ciemności, w świetle ani jednego**. Wyniki leżą tuż nad progiem (0,51-0,66), a przy 8-9 s na klatkę 6 pozytywów to niewielki ułamek klatek - przy MEDIUM (10) nie doszło do alarmu;
  przy HIGH (5 klatek) pierwsze 4 + kolejne dałyby alarm. **WNIOSEK:** w ciemności model nie "widzi makaronu", tylko daje słabe, rozproszone trafienia; **sama bramka jasności (N1)** usunęłaby je wszystkie,
  a podniesienie progu do ok. 0,7 też (ale kosztem czułości w świetle, bez zbioru testowego niezalecane).
- **WNIOSEK:** w ciemnym obrazie z kamery (szum, ewentualnie podczerwień) sieć widzi coś spoza swojego rozkładu danych; wynik jest nieprzewidywalny. To jest **luka w logice** (brak sprawdzenia, czy obraz nadaje się do oceny), nie "psucie się" modelu.
- Przy okazji: wyłączenie liczenia w ciemności **oszczędziłoby rdzeń procesora** (obecnie liczy na próżno). Sposób bez łatania `main`: patrz 4a-N1.

### 3.5 Inne zauważone słabości (WNIOSEK z kodu)

- Pętla przy włączonym `min_occluded_frame` (ustawienie "bierz klatkę z najmniej zasłoniętą kamerą") wygląda na **niedokończoną**: gdy poprzednia klatka nie została jeszcze odebrana przez wątek wykrywania
  (a to trwa ok. 8 s) i głowica "nie jest dalej niż poprzednio", pętla wraca na początek **bez snu** - czyli może kręcić się z pełnym zajęciem rdzenia, na którym pracuje też model.
  Domyślnie wyłączona (False). Nie włączać bez testu. **WNIOSEK** (odczyt bytecode, nie uruchomione).
- Podział wątków: pojedynczy wyjątek (np. brak pamięci) kończy wątek wykrywania po cichu - AI przestaje działać do restartu usługi (audyt pamięci 3.2 G).
- Model foreign nie dostaje ani informacji o wysokości stołu, ani o pozycji głowicy, ani o stanie światła - choć te trzy wielkości **są znane** Klipperowi.

---

## 4. Czy modele da się poprawić (zakres 4)

### 4a. BEZ zmiany modelu

| # | Pomysł | Dotyczy | Gdzie się go robi | Co daje (stan wiedzy) | Ryzyko / koszt |
|---|---|---|---|---|---|
| F1 | **Wymagać >= 2 dodatnich klatek** w oknie kontroli zamiast 1 | obce | nasz `ai-fixes` (Klipper), bez ruszania `main` | usuwa tylko losowy szum; **systematycznych** błędów (patrz 3.2) nie usunie | niskie; 30 linii; łatwe do cofnięcia |
| F2 | **Podnieść próg** `normal/noodle` z 0,5 np. do 0,9 | obce | tylko przez łatę `main` (stała w kodzie) | puste: 7 -> 1 z 25, ale gubi 3 z 6 makaronów jako "obce" (dane z 17.10) | średnie: zmiana `main` odrzucana przez zabezpieczenia, brak wiarygodnego zbioru testowego |
| F3 | **Kalibracja "pustej płyty" właściciela**: zapisać wynik klasyfikatora dla *jego* pustej płyty w pozycji kontroli i alarmować dopiero po wzroście o delta | obce | wymaga dostępu do wyników klas - API `/detection_res` podaje tylko liczniki; trzeba własnego uruchomienia modelu lub łaty | dopasowuje się do jego kamery/płyty/światła; największa szansa z opcji "bez modelu" | średnie; trzeba uruchamiać model drugi raz (+ ok. 17 MB RAM) albo łatać `main`; wymaga stałej pozycji kontroli |
| F4 | Pomijać kontrolę, gdy znane położenie głowicy (z Klippera) wchodzi w pole widzenia kamery | obce | Klipper (nasz moduł): znamy XYZ; **trzeba skalibrować, które XYZ zasłaniają kadr** | usuwa jedną z hipotez; nie usuwa błędów typu "Z50" | niskie-średnie; kalibracja ręczna (kilka zdjęć) |
| F5 | **Klasyczna kontrola obrazu** (różnica względem wzorcowego zdjęcia pustej płyty, kontury) zamiast sieci - jak porzucone `foreign_check.py` QIDI | obce | osobna mała usługa/skrypt (cv2+numpy już są na drukarce dzięki `ai-libraries`) | tania, wyjaśnialna, dopasowana do jednej drukarki; wrażliwa na światło, zmianę płyty, cień | średnie; wymaga "nauczenia" pustej płyty i stałej pozycji |
| F6 | Maskowanie górnej połowy obrazu | obce | łata `main` | **odrzucić:** zeruje fałszywe alarmy, ale też zeruje wykrywanie makaronu (dane 22.10) | - |
| N1 | **Bramka jasności**: nie oceniać klatek, gdy średnia jasność < próg, lub gdy lampa wyłączona | makaron | (a) łata `main` (kilka linii przed `detect_objects`); (b) bez łatania: nasz `dark-mode-light` mógłby wyłączać `enable_noodle_detection` na czas ciemności (wtedy `algo_app` w ogóle nie liczy: `is_detect_flag` = False) | usuwa fałszywy makaron w ciemności i oszczędza rdzeń; (b) zmienia też widoczny na ekranie przełącznik, więc trzeba przywracać stan | (a) średnie-wysokie (łatanie bytecode); (b) niskie-średnie, ale to zapis ustawień ekranu - wymaga testu |
| N2 | Okno czasowe zamiast liczników "na cały druk" (np. N dodatnich w ostatnich K minutach) i zerowanie po wznowieniu | makaron | łata `main` (logika w `detect_post_deal.run`) | mniej alarmów z rzadkich pojedynczych błędów, brak natychmiastowego ponownego alarmu po wznowieniu | wysokie: zmiana **logiki** w bytecode bez źródła; łatwiej przez przepisanie modułu (patrz 4c) |
| N3 | Ignorować wykrycia makaronu, których ramka pokrywa się z ramką `pri` (głowica) | makaron | łata `main` | **HIPOTEZA:** może usuwać fałszywe wykrycia na głowicy/kablach; bez danych nie wiem, czy takie występują | wysokie; najpierw dane (czy fałszywe ramki leżą na głowicy) |
| N4 | Własne wartości progów (zamiast 3 stałych) | makaron | łata `main` albo własna wersja modułu `moonraker_subscribe` | tak samo jak w październiku (MEDIUM 0,50/8) | średnie; bez wiarygodnego zbioru testowego "na ślepo" |
| C1 | Zmiana `min_occluded_frame` w `config.xml` na True | makaron | tylko plik konfiguracji | **nie robić:** patrz 3.5 (możliwa pętla bez snu) | wysokie bez testu |

Uwaga ogólna (**WNIOSEK**): prawie wszystkie wersje "bez zmiany modelu" potrzebują tego samego: **zbioru zdjęć z Twojej kamery z podanym "prawdziwym" wynikiem** (puste / przedmiot / makaron / ciemno). Bez niego każdy próg i każda reguła
to zgadywanie, a wcześniejszy zbiór (48 zdjęć z kilku scen) jest za mały i za skorelowany, żeby cokolwiek rozstrzygać (sam raport z 22.10 tak napisał).

### 4b. Wymiana lub douczenie modelu

**Co jest techniczną możliwością (DOWÓD, kod `DetectionDeal` + `PEIDetector` + `ConfigHandler`):**
- Nazwy plików modeli czyta `config.xml`: `<model_name>` (domyślnie `algo.enc`) i `<model_pf_name>` (domyślnie `algo_pf.enc`).
- Odszyfrowanie wykonuje się **tylko gdy nazwa kończy się `.enc`**; inna nazwa (np. `algo_pf_custom.onnx`) jest wczytywana wprost przez ONNX Runtime. Zgodnie z kodem plik nie jest wtedy kasowany.
- Rozdzielczość wejścia program odczytuje **z samego modelu** (nie jest wpisana na stałe), więc inny rozmiar (np. 224 lub 192x256 dla klasyfikatora) działa bez zmian w kodzie.
- Wymagany "kontrakt": **obce** - wyjście `[1,4]` w kolejności klas `noodle, nopei, normal, onlypei` (nazwy z kodu, nie z pliku); **makaron** - format YOLOv8 `[1, 4+klasy, N]`, klasy 0-2 = makaron (wagi 1/2/3), 5 = głowica.
- Uruchomienie nowego modelu wymaga **restartu usługi `algo_app`** (model ładuje się raz, przy pierwszej klatce); to jedyna "łata" po stronie drukarki: plik + 2 linie w `config.xml`. **Nie trzeba ruszać pliku `main`.**
  (Że `config.xml` się nie nadpisze samo: aktualizacje QIDI są u nas zablokowane; `POST /config` zapisuje ten plik, ale nazwy modeli nie są zmieniane na gorącą.)

**Wariant "obce przedmioty" - własny klasyfikator (polecany):**
- Mały model (YOLOv8n-cls ma 1,4 mln wag, ~5,8 MB; liczba operacji na zdjęcie rzędu pół miliarda - z pamięci, nie sprawdzone; na RK3308 dziś kilka sekund na klatkę - **HIPOTEZA** z czasu "ok. 4 s do alarmu" w teście 23.10, który obejmuje też odczyt klatki i komunikację).
- Można wytrenować **na laptopie z kartą RTX 3070 Ti** (zapisano w `HARDWARE.json`, sprzęt właściciela) w kilkanaście minut - kilka godzin na zbiorze rzędu tysięcy zdjęć (szacunek z raportu z 22.10, nie pomiar).
- Co wolno zmienić: **definicję klas**. Zamiast 4 klas z reguł o dziwnych progach - np. 2-3 klasy: `pusta`, `przedmiot`, `nie_do_oceny` (głowica zasłania, ciemno). **Wtedy zmienia się też kod interpretacji wyniku (`pei_box_draw`) - czyli łata `main`**. Jeśli
  zachowamy cztery klasy i ich kolejność, wystarczy sam plik modelu (`normal` = przedmiot, `onlypei` = czysta płyta).
- Co potrzebne: **dane** (sekcja 4c), narzędzie treningowe, eksport do ONNX (opset 12-17, wejście stałe, wyjście softmax lub - jeśli zostawimy łatę - surowe logity).
- Zalety: małe, szybkie do przetrenowania i oceny, wymienialne plikiem; wady: bez własnych danych **nie będzie lepsze** od modelu QIDI (QIDI uczyło prawdopodobnie na tysiącach zdjęć z wielu drukarek i jest dobre na swoim "szerokim" rozkładzie).

**Wariant "makaron" - nie polecam teraz:**
- Własny model wykrywania makaronu wymaga **oznaczonych ramkami zdjęć prawdziwych porażek** z kamery Q2 (setki-tysiące). Takiego zbioru nie ma; zdjęcia z internetu (Obico, Prusa) pochodzą z innych kamer i QIDI nie wykryło na nich nic (test 16.10, wynik 0 na 2 zdjęciach) - to
  samo zjawisko zadziała na odwrót.
- **Douczenie istniejącego modelu** (fine-tuning z `algo.enc`): mamy tylko plik ONNX bez checkpointu treningowego; warstwy są złożone (normalizacja wchłonięta w konwolucje), więc potrzebna jest konwersja ONNX -> PyTorch z dowodem zgodności wyjść przed jakimkolwiek treningiem
  (raport z 22.10: "nie gwarantować prostego `train(original.enc)`"). Praca: dni, wynik niepewny.
- **Tylko zmniejszenie** (żeby oszczędzić RAM/CPU): (i) kwantyzacja INT8 modelu QIDI - plik ~11 MB, RAM mniej o kilkadziesiąt MB, szybkość na A35 **nieznana** (brak instrukcji iloczynu skalarnego INT8 w tym rdzeniu - HIPOTEZA, że przyspieszenie będzie małe lub żadne);
  (ii) destylacja do YOLOv8n @320 (3 mln wag, ok. 3x mniej obliczeń z dokumentacji Ultralytics - z pamięci) - wymaga zbioru zdjęć i ręcznej oceny jakości. Obie opcje to **bezpieczeństwo druku**: każdy spadek czułości trzeba wykazać testem.

### 4c. Czego potrzeba (dane, narzędzia, zgodność, wydajność)

| Potrzeba | Stan / uwagi |
|---|---|
| **Dane (obce)** | min. kilkaset zdjęć *pustej* płyty (różne wysokości stołu, pozycje głowicy, światło, rodzaje płyt, pory dnia), kilkaset z przedmiotami (różne rozmiary/kolory, także małe), "nie do oceny" (głowica zasłania, ciemno). Źródła u właściciela: nagrania `ori` w `/home/qidi/video` (1 klatka co 30 s), nasze notatki z `FOREIGN_*` (ok. 50 zdjęć), dedykowane serie z kamery (skrypt `watch_camera.py` z października). Etykietowanie: foldery "klasa" (szybkie, godziny). Niezależne **sceny testowe** (nie klatki z tej samej serii). |
| **Dane (makaron)** | oznaczenia ramkami, setki-tysiące zdjęć porażek przy włączonym świetle; **brak** - to jest główny powód, by nie ruszać tego modelu. |
| **Narzędzia** | PyTorch + Ultralytics (AGPL) lub torchvision/timm (BSD/Apache); `onnx`, `onnxruntime` do weryfikacji; opcjonalnie `onnxruntime.quantization`. Na laptopie dostępne: RTX 3070 Ti, i7-12700H (z `HARDWARE.json` w październiku). Na tym koncie Windows **brak** numpy/onnxruntime - instalacja = pobieranie plików, wymaga zgody (sekcja 6, krok 2). |
| **Zgodność z ONNX Runtime 1.19.2 / aarch64** | **WNIOSEK** z pamięci o dokumentacji (nie sprawdzone w sieci): ORT 1.19 obsługuje opset do ok. 21; modele QIDI mają opset 12 i 15, więc eksport w opset 12-17 jest bezpieczny. Unikać operatorów spoza podstawowych (Conv, SiLU = Sigmoid+Mul, Resize, Softmax, Gemm). Wersję z `ai-libraries` na drukarce (opencv 4.12, numpy 2.0.2, ORT 1.19.2) znamy z testów. |
| **Wydajność** | Cortex-A35, jeden rdzeń, **8-9 s na klatkę** dla YOLOv8s@320 (DOWÓD pomiar). Każdy nowy model: nie wolniejszy niż obecny, dla obcych liczy się czas w oknie 15 s. Pomiar na drukarce tylko po druku i za zgodą. |
| **Pamięć** | budżet ok. 100-170 MB w druku dla całego `algo_app`; nowy klasyfikator obcych ~ +5-17 MB (ładowany tylko w oknie kontroli); nowy model makaronu musiałby być nie większy niż obecny (+66-75 MB). Trzeba mierzyć `RssAnon`, nie samego RSS (audyt pamięci, 8B). |
| **Test akceptacji** | **zbiór testowy z Twojej kamery** + porównanie z modelem QIDI na tych samych zdjęciach (fałszywe alarmy, wykrycia, "nie do oceny") + test na drukarce: kilka kontroli przed drukiem z pustą płytą i z przedmiotem; makaron: wyłącznie z prawdziwymi resztkami (jak w październiku). |

---

## 5. Strona prawna i praktyczna (zakres 4, cd.)

**Nie jest to porada prawna** - opis zasad, które projekt już stosuje, i ryzyk, które widać.

- **Repozytorium jest publiczne (GPL-3.0) i obiecuje: "brak plików QIDI poza krótkimi liniami zastępowanych zmian"** (README). Dlatego: **żadnych plików modeli** (ani `.enc`, ani odszyfrowanych, ani skwantowanych/zdestylowanych z nich),
  żadnych odszyfrowanych wag, **żadnego klucza** w repo ani w dokumentach, żadnych wycinków kodu QIDI. Zgodne z obecną praktyką instalatora: pliki QIDI pobiera użytkownik z serwera QIDI i obrabia **na swoim komputerze**.
- **Narzędzia działające na pliku użytkownika** (np. "odszyfruj mój `algo_pf.enc` do analizy", "skwantuj model, który ja mam", "porównaj mój model z moim własnym") - spójne z zasadami projektu, o ile wynik zostaje na komputerze użytkownika.
  Odszyfrowanie z kluczem wbudowanym w program QIDI to osobna kwestia (interoperacyjność/badanie własnego sprzętu): **nie potrzebujemy** go do zastosowania **własnego** modelu (nie trzeba szyfrować, sekcja 4b), a potrzebujemy tylko do porównań i kwantyzacji
  modelu QIDI. Można to zrobić jako opcjonalne narzędzie dla użytkownika, bez dołączania klucza do repo (klucz czytany z jego własnego pliku `main`). Warto rozważyć, czy tego wprost chcemy.
- **Licencje wytrenowanych modeli:** QIDI trenowało sieci narzędziem Ultralytics (AGPL-3.0; zapisane w metadanych) - dla nas to ich sprawa, my nie redystrybuujemy. Jeśli **my** wytrenujemy model Ultralytics na własnych zdjęciach, AGPL obejmie narzędzie i wynik;
  AGPL-3.0 jest zgodne z GPL-3.0 (można łączyć w jednym projekcie GPL-3.0) - wymaga ujawnienia źródeł treningu (skryptów), nie danych. Bezpieczniejsza dla ludzi, którzy chcą swoje modele rozwijać dalej: inne narzędzie (torchvision/timm, BSD/Apache 2.0).
- **Zdjęcia treningowe** to wnętrze drukarki; mogą zawierać domowe otoczenie (okno, ludzie przy drukarce). Przed publikacją zbioru (np. do wspólnego treningu) trzeba je sprawdzić. **Domyślnie: zbiór prywatny.**
- **Dziedziczenie błędów:** model zdestylowany z modelu QIDI (pseudo-etykiety) powtórzy jego błędy i będzie "pochodną" jego wyników - ryzyko prawne i merytoryczne; **nie polecam** jako pierwszego wyboru.

---

## 6. Rekomendacja: co robić po kolei (zakres 5)

| # | Krok | Praca | Ryzyko | Na drukarce? |
|---|---|---|---|---|
| 1 | **Zebrać dowody dzisiejszego alarmu**: odczyt logów i pozycji głowicy (sekcja 7). Rozstrzyga hipotezy z 3.3. | 15 min (główna sesja) | brak (tylko odczyt) | tak, tylko odczyt, za zgodą |
| 2 | **Stanowisko testowe na laptopie**: skrypt `tools/ai_eval.py` (w repo bez modeli): wczytuje **własne** `algo.enc` i `algo_pf.enc` z paczki użytkownika, uruchamia dokładnie ten sam preprocessing i reguły co `algo_app` na folderze zdjęć i drukuje wyniki. Potrzebuje `numpy`, `opencv`, `onnxruntime` (na Windows Python 3.15 trzeba sprawdzić, czy są pakiety) - **instalacja wymaga zgody właściciela** | 0,5-1 dzień | niskie (tylko laptop) | nie |
| 3 | **Szybkie testy offline bez trenowania** na stosie zdjęć z października (48 + nowe): (a) skalowanie "ściśnięte" vs "z zachowaniem proporcji + środek" (HIPOTEZA z 3.1); (b) wynik klasyfikatora na zdjęciach z głowicą w różnych miejscach (potrzeba kilku nowych zdjęć); (c) rozkład wyników (nie tylko flaga) dla pustej płyty | 0,5 dnia | niskie | nie (nowe zdjęcia: tylko po druku/za zgodą) |
| 4 | **Zbierać dane przy zwykłych drukach**: z nagrań `ori` + zrzuty co kilka minut (bez ingerencji w druk); etykietowanie własne (foldery). Cel: 200 pustych, 100 z przedmiotem, 100 "do oceny", 100 ciemnych | 1-2 tygodnie zwykłej pracy, 2-4 h etykietowania | niskie | tak, ale to tylko odczyt zdjęć (jak dziś robi `algo_app`) |
| 5 | **Decyzja po danych:** (A) wystarczą reguły (F1, F4, może N1) - mały moduł w Klipperze, bez ruszania modeli; (B) własny klasyfikator "obce" (sekcja 4b) wgrany przez `config.xml` (plik + restart `algo_app`); (C) nic nie zmieniać, tylko udokumentować, że kontrola obcych bywa zawodna i zostawić **Wznów** jako szybką drogę | - | - | - |
| 6 | **Wdrożenie wybranego wariantu**: ostrożnie, jedna zmiana naraz; przed: test na zbiorze (krok 2-4) z porównaniem do QIDI; po: kilka kontroli przed drukiem z pustą płytą i z przedmiotem; pomiar pamięci/CPU (wg audytu pamięci 8) | 1-3 dni (B), 0,5-1 dnia (A) | średnie | tak, tylko po druku, tylko za zgodą |
| 7 | **Makaron**: nic nie zmieniać w modelu. Ewentualnie wariant N1 (bramka jasności przez `enable_noodle_detection`) - dopiero gdy będzie zbiór ciemnych klatek pokazujący, że problem występuje w pewnych (nie tylko skrajnych) warunkach | 0,5 dnia | niskie-średnie | tak, test po druku |

**Czy warto?** (opinia, nie fakt) **Tak, w ograniczonym zakresie.** Najlepszy stosunek zysku do ryzyka: *własny, tani w treningu i wymianie klasyfikator "obce przedmioty"*, bo (1) obecny jest wyraźnie zawodny na pustej płycie
(DOWÓD 7/25), (2) jest mały i szybki, (3) wymienia się plikiem i dwiema liniami `config.xml`, (4) skutek błędu jest łagodny (przy fałszywym alarmie wystarczy dotknąć **Wznów**; błąd w drugą stronę = tylko brak ostrzeżenia, jak dziś przy cienkich elementach).
**Nie warto** teraz ruszać modelu makaronu: jest dobry w swojej dziedzinie (wykrył prawdziwy makaron w teście HIGH), a jego pomyłki (ciemność) naprawia się logiką, nie nowym modelem.

Zastrzeżenie: **bez zbioru danych z Twojej kamery nie obiecuję poprawy** - sam eksperyment z modelem to najpierw ocena (kroki 2-3), dopiero potem trening.

---

## 7. Co sprawdzić na żywo (tylko odczyt, po zgodzie, najlepiej gdy drukarka nie drukuje)

Wszystko dla głównej sesji; ja niczego nie robiłem na drukarce. Polecenia zakładają, że `P` to PID usługi, a wszystko idzie przez `sudo -n` (zgodnie z zasadami projektu).

1. **Czy w dzisiejszym druku foreign pochodził z klatki z głowicą w środku?**
   ```
   grep -h -E "Foreign Check|find gcode homing|gcode homing end|pei and foreign|pei foreign detect reset|noodle=|foreign=|detect_updated timeout" /var/log/algo_app/app_*.log | tail -120
   ```
   Daje: ile klatek było dodatnich i o której godzinie; porównać z czasem startu pliku w historii Moonrakera (znacznik czasu zdarzenia).
2. **Zdjęcia, na których oparto decyzję:** `GET http://127.0.0.1:9010/history_frames?type=foreign` (do 3 ostatnich klatek uznanych za obce, JPEG w base64) oraz `GET http://127.0.0.1:9010/capture`. **Uwaga:** historia klatek obcych jest czyszczona
   na początku następnego druku, więc zadziała tylko gdy sprawdzenie poprzedzi nowy start; jeśli dziś już ruszył kolejny druk - dane z tamtego alarmu są stracone, ale **na przyszłość** wystarczy pobrać obie rzeczy zaraz po pojawieniu się okna "obcy przedmiot" (przed klikaniem Wznów/Anuluj) - małe żądania odczytu, nie przerywają kontroli.
3. **Które `main` stoi na drukarce:** `sha256sum /usr/local/bin/algo_app/main` - stock: `7361bea6...d115` (MEDIUM = liczba 10); październikowy wariant MEDIUM = 8: SHA `7a28cb98...293c` (według zapisów z 23.10). Do tego `grep -E "noodle_sensitivity_level|conf_thres" /var/log/algo_app/app_*.log | tail`.
4. **Aktualny `config.xml` bez sekcji z hasłem:** `grep -E "is_|min_occluded|conf_thres|iou_thres|model_|class_vis|save_" /usr/local/bin/algo_app/configs/config.xml` (czy ktoś włączył zapis wideo, `min_occluded_frame`, itp.).
5. **Pozycja głowicy i stołu w chwili kontroli:** z `klippy.log` linie wokół `M4050: inspecting current camera view` (nasz komunikat) oraz zapisana pozycja po końcu poprzedniego druku (`toolhead` z historii).
6. **Dla ciemności (jeśli właściciel chce zbadać):** w logu `algo_app` linie `检测到炒面` (znaczniki czasu) z okresu, gdy światło było wyłączone - ile pozytywów i jaki `分数` (wynik).

Do przyszłych testów na żywo (po druku, za zgodą): zrobić 5-10 zdjęć pustej płyty w trzech wysokościach stołu i trzech pozycjach głowicy (**w tym głowica w środku**), zapisać `/capture` i od razu **klasyfikator** (przez stanowisko z kroku 2), żeby ostatecznie rozstrzygnąć, czy głowica w środku daje `normal`.

---

## 8. Czego nie wiem / ograniczenia tego audytu

- **BRAK DANYCH:** czy dzisiejszy alarm to głowica (sekcja 3.3); jakie przekształcenia obrazu stosowano przy treningu QIDI; liczebność i skład ich zbioru; co dokładnie oznaczają klasy `sim` i `com`;
  jak dokładnie ekran (`qidiclient`) przechodzi od `qdc_ai_error_code` do `PAUSE W=1` (nie śledziłem kodu ekranu do końca); czy teraz na drukarce stoi stockowy `main` czy wersja z 8.
- **Nie uruchamiałem modeli.** Na tym koncie Windows nie ma numpy/onnxruntime; instalacja to pobieranie plików (wymaga zgody). Wszystkie liczby skuteczności pochodzą z zapisów z października, wykonanych przez poprzednią sesję
  na jej zbiorze (48 zdjęć, skorelowanych scen, nie próba losowa).
- Struktura modeli: odczyt własnym czytnikiem plików ONNX (nie biblioteką `onnx`); zgodność metadanych potwierdza też raport z 22.10 (`FOREIGN_MODEL_STRUCTURE`), który użył `onnxruntime`.
- Interpretacja nazw klas `mil/mod/ser/sim/com/pri` to **HIPOTEZA** poza `pri` (dowód w kodzie: `class_printer`).
- Dane o prędkościach (8-9 s/klatkę) pochodzą z jednego testu (16.10) na starszej konfiguracji; czasy YOLOv8n i kwantyzacji są szacunkiem, nie pomiarem.
- Dane o FLOPs YOLOv8n/s i o wsparciu opsetów ORT to **z pamięci**, nie sprawdzone w sieci.
- Zmiany z ostatnich tygodni na drukarce (moduły `algo-app-malloc`, `algo-app-oom-priority`) nie były przedmiotem audytu.

---

## 9. Kolejne kroki (lista)

1. Główna sesja: **odczyt z drukarki** z sekcji 7 (pkt 1, 3, 4; pkt 2 przy najbliższym alarmie) - po zgodzie i poza drukiem.
2. Zgoda właściciela na **instalację narzędzi na laptopie** (numpy, opencv, onnxruntime, ew. PyTorch+Ultralytics) - albo decyzja "nie instalujemy".
3. Napisać `tools/ai_eval.py` (stanowisko testowe bez modeli w repo), uruchomić na zdjęciach z października; testy 3a-3c.
4. Zdecydować z właścicielem o polityce "kontrola obcych": ostrzeżenie czy pauza; ew. wersja z F1 (>= 2 klatki) i F4 (głowica zasłania - pomiń) w `ai-fixes`.
5. Rozpocząć zbieranie zdjęć (nagrania `ori`, zrzuty), etykietowanie w folderach.
6. Po ocenie: (A) reguły w Klipperze, (B) własny klasyfikator przez `config.xml`, albo (C) nic; makaron bez zmian modelu.
7. Odrębnie, niskim priorytetem: bramka jasności w ciemności (N1), pytanie o `sim`/`com`, sprawdzenie kodu ekranu `qidiclient` (przejście `qdc_ai_error_code` -> PAUSE).

Narzędzia z tego audytu: `ai_models_tools` (folder narzędzi poza repozytorium)
(`decrypt.py` - odszyfrowanie kopii do analizy, `onnxinfo.py` - czytnik struktury ONNX; uruchamiać `python -I`, katalog roboczy inny niż rozpakowane dane; modeli tam nie ma).

## 10. Wyniki z laboratorium (22.11, laptop; bez dostępu do drukarki)

Stanowisko: folder `ai-lab` **poza repozytorium** (obok folderu projektu); w nim własne kopie obu modeli (odszyfrowane z paczki 02.04 użytkownika), skrypty
i wyniki. Nic stąd nie trafia do gita, klucza nie zapisano w żadnym pliku. Uruchamianie w WSL (Python 3.14, onnxruntime **1.23** - na drukarce jest 1.19.2, więc liczby mogą się
nieznacznie różnić; na Windows/Python 3.15 onnxruntime nie ma pakietu). Przetwarzanie jak w `algo_app`: cały obraz ściśnięty do 320x320 (makaron) / 256x256 (obce), BGR->RGB, /255, CHW;
makaron: najlepsza klasa na kotwicę > próg, NMS na klasę z IoU 0,2, waga klas 1/2/3. **DOWÓD** (uruchomione, wyniki w `ai-lab/results/`).

**Co uruchomiono i co sprawdziłem (DOWÓD):**
- Wejścia i wyjścia z onnxruntime zgodne z opisem w sekcji 1: makaron `[1,3,320,320] -> [1,10,2100]`, obce `[1,3,256,256] -> [1,4]` (klasyfikator zwraca już prawdopodobieństwa).
- Kontrola potoku makaronu: klasa głowicy (`pri`) dostaje 0,91-0,95 na klatkach z widoczną głowicą (0,55 na ciemnej klatce 10, 0,01 na prześwietlonej 14), czyli odczyt wyjścia i NMS działają.

**Jakie obrazy istnieją (BRAK DANYCH w większej skali):** na tym komputerze jest tylko **16 klatek z kamery drukarki (640x480)**, wszystkie z listopadowych testów (`QIDI_Q2_CLAUDE_TAKEOVER_20261106/...`,
`work/ui/cam1.jpg`). Obejrzałem je ręcznie: 6 pustych płyt w normalnym świetle (2, 3, 8, 12, 13, 15; w 8 i 15 głowica jest na środku), 7 klatek z przedmiotem lub ręką (0, 1, 4, 5, 6, 7, 9), 1 ciemna (10),
1 prześwietlona (14), 1 zbliżenie obiektywu (11). **Nie ma ani jednej klatki z makaronem, ani z ciemnego trybu z prawdziwej kamery.** Zdjęcia z telefonu w `.codex-attachments` (71 plików, 1280x960)
to nie klatki z kamery drukarki - nie użyłem ich.

### 10.1 Klasyfikator "obce przedmioty" (normalne światło, 16 klatek)

| Klatki | Wynik | Ocena |
|---|---|---|
| Puste płyty w normalnym świetle (6) | **0/6 fałszywych alarmów**; największe `normal` 0,31 (klatka 2: początek testu, `onlypei` 0,66) | DOWÓD (mała próba) |
| Głowica na środku, pusta (klatki 8, 15) | **bez alarmu** (`normal` 0,15 i 0,17; klatka 15 ma `noodle` 0,37) | DOWÓD (2 klatki) |
| Przedmiot/ręka na płycie (0, 1, 4, 5, 6, 7, 9) | **alarm w 7/7** (`normal` 0,76-1,00) | DOWÓD - poprawnie |
| Prześwietlona klatka (14) | **fałszywy alarm** (`normal` 0,53 / `noodle` 0,47) | DOWÓD |
| Ciemna (10), zbliżenie (11) | bez alarmu (`onlypei` 0,99 / 1,00) | DOWÓD |

**WNIOSEK:** na tych klatkach klasyfikator działa lepiej, niż wynikało z październikowych pomiarów (tam 7/25 pustych płyt dawało alarm). Nie mogę potwierdzić ani obalić hipotezy, że 22.11 o 14:46 alarm spowodowała głowica
na środku: dwie moje klatki z głowicą na środku nie dały alarmu, ale to **2 klatki**, a październik pokazał, że wynik zależy od konkretnej klatki (stały błąd, nie losowy). Potrzebna klatka z alarmu (sekcja 7).
(Wcześniejsza uwaga, że klasyfikator jest "kruchy na szum w ciemności", opierała się na symulacji, która okazała się błędna - patrz 10.5: na prawdziwych ciemnych klatkach klasyfikator obcych dał **0 alarmów**.
Prześwietlenie (klatka 14) i położenie głowicy nadal mogą go mylić.)

### 10.2 Detektor makaronu: normalne światło kontra ciemność

**UWAGA - ten podpunkt jest częściowo OBALONY przez prawdziwe dane (10.5).** Napisałem go, zanim miałem klatki z prawdziwego ciemnego trybu. Symulacja "szum + wzmocnienie" **nie oddaje** prawdziwej ciemności
(prawdziwe ciemne klatki są prawie jednolicie szare i prawie bez szumu), więc jej tabela i wnioski poniżej **nie obowiązują**; zostawiam je tylko jako zapis błędnej hipotezy. Obowiązują wyniki z 10.5.

Dwa warianty "ciemności" (obie to **symulacja**, nie prawdziwa kamera - HIPOTEZA, że oddaje ciemny tryb; **obalona w 10.5**):

1. **Samo przyciemnienie** (jasność x 0,5 / 0,3 / 0,2 / 0,1): na wszystkich 16 klatkach wynik makaronu to **0,00** (żadnej ramki klas `mil`/`mod`/`ser` powyżej 0,2). DOWÓD. Samo przyciemnienie więc **nie** tłumaczy
   dzisiejszych trafień.
2. **Przyciemnienie + szum + automatyczne wzmocnienie** (tak robi kamera w ciemności: sygnał mały, szum duży, potem wzmocnienie jasności), 15 klatek x 5 losowych szumów:

   | Warunek (jasność, szum, wzmocnienie) | klatki dodatnie przy progu 0,43 / **0,50** / 0,58 | fałszywe alarmy "obcych" na pustych płytach |
   |---|---|---|
   | normalne światło | 0/75, 0/75, 0/75 | 0/30 |
   | 0,3 / 2 / 3,3 | 0/75, 0/75, 0/75 | 0/30 |
   | 0,2 / 4 / 5 | 26/75, **21/75**, 17/75 | **13/30** |
   | 0,1 / 3 / 6 | 33/75, **30/75**, 26/75 | 0/30 |
   | 0,1 / 6 / 6 | 10/75, 4/75, 0/75 | 0/30 |
   | 0,05 / 3 / 6 | 26/75, 12/75, 2/75 | 0/30 |

   Wyniki makaronu w tym wariancie to 0,3-0,7. Zbieżność z zakresem z logu (0,51-0,66) była **przypadkowa**: prawdziwy mechanizm jest inny (10.5). Wniosek "model daje trafienia na zaszumionym, wzmocnionym obrazie"
   **nie utrzymał się** - prawdziwe ciemne klatki nie są zaszumione.
3. (Pierwotnie: "bramka jasności/szumu nie sprawdzona, brak danych".) **Sprawdzona w 10.5:** prosta bramka po średniej jasności klatki rozdziela prawdziwą ciemność od światła bez żadnego błędu. Miara szumu
   rozdziela gorzej (3 klatki światła błędnie odrzucone).

### 10.3 Rekomendacja dot. małego własnego klasyfikatora obcych przedmiotów

- **Na razie nie trenować.** Mam 16 klatek i żadnej oznaczonej serii; model własny bez kilkuset własnych zdjęć (pusta płyta w jasności dzień/noc, głowica w różnych miejscach, prawdziwe obce przedmioty) byłby zgadywaniem.
- **Tańszy pierwszy krok (efekt bez nowego modelu) - teraz poparty prawdziwymi danymi (10.5):** **bramka jasności** (nie liczyć klatki makaronu, gdy średnia jasność klatki < ok. 22 z 255). Na 978 prawdziwych klatkach
  usuwa wszystkie 21 trafień > 0,50 i nie odrzuca żadnej jasnej klatki. Moduł `dark-mode-light` blokuje dziś tylko pauzę; brakuje bramki po stronie liczenia (wymaga zmiany w kodzie `algo_app` lub
  w wiadomości, którą wysyła do Klippera - sposób wdrożenia do wyboru, nie sprawdzany).
- **Jeśli dane pokażą, że klasyfikator myli się systematycznie** (np. na głowicy na środku): mały własny klasyfikator (np. YOLOv8n-cls lub mały MobileNet, wejście 224-256, 4 klasy jak teraz) jest **wykonalny**: podmiana to
  plik `.onnx` + wpis w `config.xml` bez łatania `main` (sekcja 4b); pamięć i czas klatki podobne do dzisiejszych. Wysiłek: zebranie i oznaczenie ~500-1000 klatek (główny koszt, kilka dni z przerwami na druki),
  trening na laptopie bez GPU kilka godzin, test offline w tym laboratorium, dopiero potem test na drukarce po druku i za zgodą właściciela.
- Kolejność, którą bym zalecał: (1) zebrać dane, (2) policzyć w laboratorium, co dokładnie myli stary model, (3) dopiero wtedy decydować: próg/bramka, czy nowy model.

### 10.4 Czego brakuje do dalszych pomiarów (do pobrania z drukarki, tylko odczyt, po zgodzie, gdy nie drukuje)

| Plik / dane | Po co |
|---|---|
| ~~Klatki z kamery w ciemnym trybie~~ **MAMY** (978 klatek z 22.11, 10.5) | zrobione; zostaje pytanie, czy inne drukarki/oświetlenie dają tę samą jasność ciemnej klatki (ok. 19) |
| Klatki z alarmu "obcy przedmiot" (`GET /history_frames?type=foreign`, zaraz po alarmie, przed Wznów/Anuluj) i `GET /capture` w tej samej chwili | czy alarm 22.11 14:46 to głowica; stała pomyłka czy losowa |
| Pliki wideo detekcji (mp4) lub zapisane klatki w katalogu wideo drukarki (`/home/qidi/video` - **nazwę katalogu trzeba potwierdzić**, nie sprawdzałem) | więcej klatek, w tym z makaronem, jeśli kiedyś był |
| Puste płyty w różnym świetle i głowica w 5-6 miejscach (po 10-20 klatek przez `/capture`, gdy drukarka stoi) | zestaw testowy "pusta płyta / głowica" |
| Klatki z prawdziwym makaronem (np. po nieudanym wydruku, kilka ujęć) | jedyna klatka "dodatnia" dla detektora makaronu; dziś nie mam żadnej (mogę mierzyć tylko fałszywe alarmy, nie czułość) |
| Suma SHA256 pliku `main` i flagi z `config.xml` na drukarce (sekcja 7) | czy kod na drukarce to ten sam, który czytałem |

**Ograniczenia tej sekcji:** 16 klatek z listopadowych testów + 978 klatek z jednego druku (22.11) z jednej kamery; wersja onnxruntime inna niż na drukarce; czułość detektora makaronu (czy wykrywa prawdziwy makaron)
**nie była mierzona**, bo brak klatek z makaronem; pustej płyty w ciemności i głowicy na środku w ciemności nie ma w danych (na każdej klatce z 22.11 stoi wydruk).

### 10.5 Prawdziwe dane: 978 klatek z druku Kaercher (22.11, 15:25-20:00)

Źródło: katalog `ai-lab/frames_timelapse_20261122` (klatki timelapse 640x480, skopiowane przez sesję główną za zgodą właściciela; czas = czas zapisu pliku). Wyniki per klatka: `ai-lab/results/timelapse_scores.csv`.
Na każdej klatce stoi wydruk (**brak pustej płyty, brak prawdziwego makaronu, brak klatki z alarmu obcych**). Oba modele uruchomione dokładnie jak wyżej. **DOWÓD** (policzone), o ile nie napisano inaczej.

**Podział na światło i ciemność - po prawdziwej jasności, nie po godzinach.** Średnia jasność klatki (0-255) ma dwa wyraźnie oddzielone skupiska:

| Klasa | Klatek | Średnia jasność | Szum (filtr górnoprzepustowy) |
|---|---:|---|---|
| **Ciemna** (średnia < 22) | **652** | **19,06-19,36** (mediana 19,1), czyli prawie stała | **0,15-1,17** (prawie jednolita plansza) |
| **Jasna** (średnia >= 22) | **326** | 23,6-222,9 (zwykle 42-58) | 0,9-13,2 (zwykle 8-13) |

Okna czasowe z logu (ciemny tryb 16:12-16:48 i od 18:30) zgadzają się z jasnością z dwoma niuansami: 46 klatek leży w oknie "ciemnym", ale jest jasnych (światło było chwilami włączone), a 6 klatek 16:08-16:11
jest ciemnych przed oknem z logu (WNIOSEK: światło chwilami włączało się w oknie ciemnego trybu, np. do zdjęcia timelapse; przyczyny nie sprawdzałem). Do liczenia użyłem **jasności**, bo to ona jest tym, co widzi model.

**Prawdziwa ciemna klatka to prawie jednolita ciemnoszara plansza z jedną małą, jasną zieloną plamą** (u góry, ok. 350-800 pikseli jasnych; obejrzane ręcznie: `ai-lab/results/dark_sheet.jpg`).
**Nie jest to obraz zaszumiony ani wzmocniony** - symulacja z 10.2 była błędna w tym punkcie.

**Detektor makaronu (klasy `mil`/`mod`/`ser`, jak `algo_app`):**

| Klasa | Klatek | Dodatnie przy progu 0,43 | **0,50 (MEDIUM)** | 0,58 | największy wynik |
|---|---:|---:|---:|---:|---:|
| Ciemna | 652 | 33 (5,1 %) | **21 (3,2 %)** | 3 (0,5 %) | 0,64 |
| Jasna | 326 | **0** | **0** | **0** | 0,00 |

- **3,2 % w ciemności przy progu MEDIUM zgadza się z logiem (ok. 2-3 %)**, a w jasności jest zero. **DOWÓD**, że dzisiejsze trafienia 0,51-0,66 to artefakt ciemnych klatek, nie makaron.
- Trafienia są w skupiskach (16:10-16:19, 16:33-16:47, 18:33-18:36, 19:58-19:59), zgodnie z logiem; wszystkie na klatkach o średniej jasności 19,08-19,32. Wynik rośnie ze średnią jasnością klatki
  (korelacja 0,57 w ciemności): im trochę jaśniej (większa plama), tym większa szansa trafienia (nie trafia nic poniżej średniej 19,08).
- **Co dokładnie wyzwala trafienie:** na wszystkich 10 sprawdzonych klatkach z trafieniem **zamalowanie samej zielonej plamy kolorem tła daje wynik 0,00** (przed: 0,50-0,64), a całkowicie jednolita klatka też daje 0,00.
  **WNIOSEK:** model uznaje jasną zieloną plamę na pustej ciemnej klatce za "makaron". **Czym jest plama: diody samej głowicy** (zielona, czasem też czerwona; fakt podany przez właściciela, **nie moje ustalenie**;
  dane z pustej płyty w 10.6 to potwierdzają: plama jest na klatkach bez żadnego wydruku). Fałszywy "makaron" w ciemności to więc odczytanie diody głowicy jako makaronu.

**Bramka po jasności/szumie (do rozdzielenia ciemności od światła):**

| Reguła "pomiń klatkę, gdy..." | pominięte klatki | usuwa trafień > 0,50 (z 21) | jasnych klatek pominiętych błędnie |
|---|---:|---:|---:|
| średnia jasność < 22 | 652 | **21** | **0** |
| średnia jasność < 25 | 653 | 21 | 1 |
| szum < 2 | 654 | 21 | 2 |
| szum < 3 | 655 | 21 | 3 |

**WNIOSEK:** najprostsza reguła ("średnia jasność klatki < ok. 22") rozdziela ciemność od światła bez błędu na tych danych; odstęp między grupami jest wąski (19,4 do 23,6), więc próg 21-22 jest sensowny, ale
**uwaga:** to dane z jednej kamery i jednego oświetlenia, a pojedyncza jasna klatka ma 23,6 (przejście), więc zapas nie jest duży. Sensowniejsze niż sztywna liczba byłoby porównanie z klatką odniesienia
(wynik "tryb ciemny włączony" jest i tak znany Klipperowi - moduł `dark-mode-light` wie, kiedy światło jest wyłączone).

**Klasyfikator obcych przedmiotów (na tych samych klatkach):**

| Klasa | Klatek | Alarm "obcy" (`normal` lub `noodle` > 0,5) | Uwagi |
|---|---:|---|---|
| Ciemna | 652 | **0** (0 %) | wszystkie 652 = `onlypei` > 0,98 ("jest płyta PEI") |
| Jasna | 326 | 322 (98,8 %) | `normal` mediana 0,95; bez alarmu tylko 4 klatki (16:10:47, 19:19:47, 19:53:18, 20:00:08 - przejścia światło/ciemność lub prześwietlenie) |

Na jasnych klatkach "alarm" jest **oczekiwany i nic nie znaczy**: na płycie stoi wydruk, a klasyfikator nie odróżnia wydruku od obcego przedmiotu (to klasyfikator całej klatki, nie detektor - sekcja 2.3);
w prawdziwym druku nie ma on więc znaczenia po rozpoczęciu druku, tylko **przed** drukiem (płyta pusta), gdzie działa M4050. **W ciemności klasyfikator obcych nie alarmuje wcale** (na tych klatkach),
a alarm 22.11 o 14:46 był przed początkiem tych klatek (15:25), więc nie wiem, czy świeciło światło - ten przypadek nadal jest nierozstrzygnięty. Z tych danych **nie da się** ocenić fałszywych alarmów na pustej płycie (jej nie ma) ani wpływu głowicy na środku.

**Co to zmienia w wcześniejszych wnioskach:**
- Sekcja 3.4 i streszczenie w sekcji 0 (bramka jasności N1 usuwa fałszywy makaron w ciemności): **potwierdzone na prawdziwych danych** (21/21 usuniętych, 0 błędnie pominiętych jasnych).
- Symulacja z 10.2 (szum + wzmocnienie) i jej wniosek "klasyfikator kruchy na szum w ciemności": **obalone**.
- Rekomendacja o niepotrzebnym własnym modelu dla makaronu: nie zmienia się. Dla tego błędu wystarczy bramka; nowy model nie jest potrzebny.

### 10.6 Prawdziwa pusta płyta: 48 klatek, głowica w 8 miejscach (22.11, ok. 21:00)

Źródło: `ai-lab/frames_empty_plate_20261122` (właściciel potwierdził, że płyta jest pusta). 8 pozycji głowicy (nazwy `p<n>_x<X>_y<Y>_z<Z>_<dark|light>_<k>`), po 3 klatki przy wyłączonym świetle (ciemno) i włączonym (jasno),
razem 24 ciemne + 24 jasne. Wyniki per klatka: `ai-lab/results/empty_plate_scores.csv`. **DOWÓD** (policzone), o ile nie napisano inaczej.

**Klasyfikator obcych przedmiotów na prawdziwie pustej płycie (reguła QIDI: `normal` lub `noodle` > 0,5):**

| Światło | Klatek | Fałszywe alarmy | Największe `normal` | Największe `noodle` |
|---|---:|---:|---:|---:|
| Ciemno | 24 | **0** (0 %) | 0,00 (wszystkie `onlypei` = 1,00) | 0,00 |
| Jasno | 24 | **1** (4,2 %) | **0,57** | 0,36 |
| Razem | 48 | 1 (2,1 %) | | |

Jedyny alarm: pozycja 5 (głowica w tylnym lewym rogu, X30 Y240 Z40), **pierwsza** klatka po włączeniu światła (`normal` 0,57). Najbliższe progu: pozycja 6 (tylny prawy róg) 0,49, pozycja 1 (środek, Z20) 0,42.

| Pozycja głowicy | `normal` w 3 klatkach jasnych | Alarm |
|---|---|---|
| 1: środek (135,135), Z20 | 0,42 / 0,12 / 0,08 | nie |
| 2: środek (135,135), Z150 | 0,08 / 0,11 / 0,05 | nie |
| 3: lewy przód (30,30), Z40 | 0,26 / 0,07 / 0,05 | nie |
| 4: prawy przód (240,30), Z40 (głowicy nie widać w kadrze) | 0,00 / 0,00 / 0,00 | nie |
| 5: lewy tył (30,240), Z40 | **0,57** / 0,23 / 0,23 | **tak (1 z 3)** |
| 6: prawy tył (240,240), Z40 | 0,49 / 0,30 / 0,25 | nie (blisko) |
| 7: tył środek (135,240), Z100 | 0,17 / 0,12 / 0,15 | nie |
| 8: przód środek (135,30), Z100 | 0,00 / 0,00 / 0,00 | nie |

**Odpowiedzi na pytania:**
- **Głowica na środku (podejrzenie właściciela co do 14:46):** przy Z20 i Z150 w sumie **0/6 alarmów**. Najwyższe 0,42 (Z20, pierwsza klatka po włączeniu światła). **Hipoteza "głowica na środku wywołuje alarm" nie jest poparta**
  tymi klatkami, ale 3 klatki na pozycję to mało, a alarm 22.11 mógł dotyczyć jeszcze innego położenia głowicy (w logu go nie ma).
- **Zależność od pozycji:** największe wartości `normal` dają pozycje **na tyle płyty i w rogach** (5, 6) oraz środek przy Z20; pozycje przednie (4, 8) mają ~0. WNIOSEK (8 pozycji, bardzo mała próba).
- **Pierwsza klatka po włączeniu światła jest najgorsza:** średnia jasność pierwszej jasnej klatki w pozycji to 63-97, a następnych 50-70 (kamera dopiero dobiera ekspozycję), i to pierwsze klatki mają najwyższe `normal`
  (0,57 / 0,49 / 0,42 / 0,26; następne 0,05-0,30). **WNIOSEK z tych danych.** To zbiega się z wcześniejszym wynikiem, że prześwietlona klatka (14 z 16 klatek, średnia 208) daje `normal` 0,53.
  **HIPOTEZA dla alarmu 22.11 14:46:** kontrola obcych (M4050) włącza światło i od razu czyta klatki; alarm z **jednej klatki ok. 4 s po starcie** pasuje do "pierwszej klatki po włączeniu światła z nieustabilizowaną
  ekspozycją". Nie udowodnione (brak klatki z tego alarmu); do sprawdzenia: opóźnienie (np. 3-5 s) przed pierwszą klatką kontroli albo ponowne sprawdzenie, zanim pauza nastąpi.

**Detektor makaronu na tych klatkach:** **0/48** (wynik 0,00 w każdej), także na 24 ciemnych klatkach z diodą głowicy w różnych miejscach kadru (położenie plamy: m.in. (444,66), (209,71), (420,105), (522,99), (291,23);
na pozycjach 4 i 6 diody w ogóle nie widać). **Nie odtworzyłem więc fałszywego makaronu na pustej płycie**, a **wpływu pozycji diody nie umiem ocenić**: przy ~3 % trafień na klatkę (10.5) w 24 klatkach spodziewałbym się ok. 0-1 trafienia,
więc brak trafień nic nie dowodzi. Plamy są tu mniejsze (60-420 pikseli jasnych) niż w klatkach z wydrukiem; różnica w wielkości plamy między klatkami z trafieniem i bez (10.5) nie była wyraźna, więc **czynnika decydującego
o trafieniu nie ustaliłem**. Klasa głowicy (`pri`) jest w ciemności zawsze 0,00 (model w ogóle nie rozpoznaje głowicy po samych diodach), w świetle 0,84-0,94 (poza pozycją 4, gdzie głowicy nie widać).

**Bramka jasności (średnia < 22) na tych klatkach:** ciemne klatki mają średnią **17,0-19,2**, jasne **50,0-96,5**. Reguła "średnia < 22" łapie **24/24 ciemne** i **0/24 jasnych** (odstęp większy niż w klatkach z wydrukiem). Trzy
klatki mają 17,0-17,1 (pierwsze po wyłączeniu światła, kamera jeszcze dobiera ekspozycję) - też poniżej progu. Razem z 10.5: ciemne 17,0-19,4, jasne >= 23,6 (jedno przejście) - próg ok. 21-22 potwierdzony na 1026 klatkach.

**Co z tego wynika (WNIOSEK):**
1. Klasyfikator obcych na **prawdziwie pustej płycie** myli się rzadko (1/48), ale **nie jest zerowy**; błąd jest związany z jasnością (pierwsze klatki po włączeniu światła) i, możliwe, z położeniem głowicy z tyłu.
2. Ciemność z diodami głowicy **nie** daje fałszywego "obcego" (0/24), więc bramka jasności dla obcych niepotrzebna; potrzebna dla makaronu (10.5).
3. Tani środek na alarm obcych bez zmiany modelu: **poczekać na ustabilizowanie ekspozycji** po włączeniu światła, zanim kontrola zacznie czytać klatki (do sprawdzenia, jak M4050/`ai-fixes` włącza światło). To wymaga
   testu na drukarce (po druku, za zgodą), więc na razie to hipoteza.
