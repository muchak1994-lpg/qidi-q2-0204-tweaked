# Audyt kodu Boksa QIDI (firmware 02.04 drukarki Q2) - "co gdzie jak"

Data: 2026-11-22. Tylko analiza plików z paczki QIDI, nic nie uruchamiane na drukarce, Boksa nie ma, więc **nic z tego nie jest
sprawdzone na sprzęcie**. Każdy wniosek ma oznaczenie:

- **[DOWÓD]** - widać to wprost w kodzie lub w napisach skompilowanego pliku (podaję funkcję/napis).
- **[HIPOTEZA]** - wniosek z układu kodu lub z cudzego opisu (Valve Oil dotyczy Max 4 / Plus 5, nie Q2), do sprawdzenia z Boksem.
- **[BRAK]** - w kodzie Q2 tego nie ma (zgłoszenie dotyczy innego kodu).

## 1. Z czego składa się Boks w oprogramowaniu Q2

Pliki w `/home/qidi/klipper/klippy/extras/` (skompilowane Cythonem do `.so`, bez źródeł):

| Plik | Rozmiar | Rola (wg nazw funkcji i napisów) |
| --- | --- | --- |
| `box_extras.so` | 3,8 MB | Główna logika Boksa "pierwszej generacji": hub (`b_endstop`), czujnik w głowicy (`e_endstop`), bufor, polecenia G-code (`E_LOAD`, `E_UNLOAD`, `E_BOX`, `RELOAD_ALL`, `AUTO_RELOAD_FILAMENT`, `BOX_PRINT_START`, `TRY_RESUME_PRINT`, `INIT_RFID_READ`, `INIT_MAPPING_VALUE`, `ENABLE_BOX_DRY` ...), zmiana narzędzia (`TOOL_CHANGE_START/END`), suszenie. |
| `box_stepper.so` | 2,8 MB | Jedna sekcja `[box_stepper slotN]` = jedna szpula: `EXTRUDER_LOAD`, `SLOT_UNLOAD`, `SLOT_RFID_READ`, ruchy z endstopem (`do_home`, `drip_move`), automatyczna wymiana po końcu filamentu (`switch_next_slot`). |
| `multi_color_controller.so` | 7,4 MB | **Nowa warstwa** "kontroler wielokolorowy": klasy `LocalAdapter` i **`RemoteAdapter`**, kolejka kroków `TaskQueueManager` (kroki `EXT_HEAT/CUT/UNLOAD/LOAD/WIPE/BITE`, `BOX_HEAT/CUT/UNLOAD/LOAD/EJECT/WIPE`), baza filamentów `MaterialDatabase`, polecenia `MULTI_COLOR_*`, `QUERY_MULTI_COLOR`. |
| `box_autofeed.so`, `box_detect.so`, `box_rfid.so` | 2,0 / 1,7 / 0,6 MB | Autopodawanie (czujnik graniczny A), wykrywanie płytek Boksa po USB (`box_detect` pilnuje `/dev/serial/by-id` i przepisuje `box.cfg`, potem prosi o restart), czytnik RFID. |
| `box_config.py`, `box_heater_fan.py` | małe | Jedyne **czytelne** pliki Pythona (dlatego tylko tu mamy łatki). |

**[DOWÓD]** `box_extras.so`, `box_stepper.so` i `multi_color_controller.so` są **bajt w bajt takie same** w 02.04 i 03.02
(takie same sumy SHA-256). Wszystko poniżej dotyczy więc obu wersji; różnią się tylko makra w `gcode_macro.cfg` (np. 03.02 wywołuje
`INIT_RFID_READ` w `PRINTER_INIT`, 02.04 nie - patrz pkt 3.7).

### Najważniejsze odkrycie: kod "Boksa 2" już tu jest

**[DOWÓD]** `multi_color_controller` ma dwa tryby: `LOCAL` (Boks sterowany przez Klippera, jak dotąd) i `REMOTE`.
Opis klasy w kodzie: "远程模式适配器 - 与第二代盒子通信" (= "adapter trybu zdalnego - komunikacja z pudełkiem drugiej generacji").
Tryb zdalny: osobny wątek komunikacyjny przez port szeregowy (`/dev/ttyACM*`, funkcja `_find_box_port`, `test_serial`), polecenia i
odpowiedzi w **JSON** (`protocol_version`, `command_queue`, `command_response`), ping `{"cmd":"ping"}` -> `pong`, heartbeat
(`_send_heartbeat`), zdarzenia (`_handle_event`: m.in. "断料事件" = brak filamentu, "材料加载完成", "盒子错误"), pomiar temperatur i
suszenia po stronie Boksa. Komendy konfiguracji: `MULTI_COLOR_CONFIG MODE=... PORT=... BAUDRATE=...` (tryb nie zmienia się,
gdy kontroler jest połączony: napis "无法在连接状态下切换模式").

Co z tego wynika dla właściciela:

- **[DOWÓD]** Obsługa "drugiego Boksa" jest w firmware 02.04 i 03.02 (ten sam plik). Czy zadziała na Boksie 2 - nie wiadomo
  (protokół i firmware samego pudełka są po stronie QIDI; płytka Boksa 2 ma mieć własny program).
- **[HIPOTEZA]** Boks 2 będzie widoczny jako port `/dev/ttyACM*`, a nie jako płytki `mcu_box1..4` po USB. Wtedy nasze moduły
  `box-homing-timeout` i `box-heater-keepalive` (oba oparte na nazwach `mcu_box*` / `heater_box*`) **nie będą działać** na Boksie 2,
  bo tam nie ma Klipperowych płytek ani grzałek Boksa (suszenie robi samo pudełko).
- **[HIPOTEZA]** Wiele zgłoszeń z listy Valve Oil (Max 4 / Plus 5, Boksy USB) dotyczy kodu `box_extras`/`box_stepper` (tryb LOCAL).
  Przy Boksie 2 liczy się raczej `RemoteAdapter` - nikt jeszcze nie opisał jego błędów.
- Domyślny tryb po instalacji **nieznany** (sekcja `[multi_color_controller]` w `printer.cfg` jest pusta; domyślną wartość ustawia
  kod). Przy pierwszym podłączeniu Boksa: `QUERY_MULTI_COLOR` w konsoli Fluidd (tylko odczyt) pokaże tryb, stan i błędy.

## 2. Jak to zbadano (żeby dało się powtórzyć)

1. Z paczki `QD_Q2_01.01.02.04_20260804_Release_NA` (plik `.deb`, część `data.tar.xz`) wyjęto pliki `.so` i makra.
2. Cython zapisuje napisy skompresowane (zlib) w jednym bloku plus tablica długości (uint32). Po rozpakowaniu i pocięciu według
   tablicy dostaje się komplet napisów: komunikaty, skrypty G-code, nazwy atrybutów. Indeks `__pyx_string_tab[N]` z dekompilatora
   wskazuje wtedy konkretny napis (sprawdzone na `box_extras` i `box_stepper`: `delayed_init_rfid` wychodzi czytelnie jako
   "jeśli idle_timeout.printing_time == 0 -> `INIT_RFID_READ`").
3. Ghidra 12.2 (osobny projekt `tools\ghidra_proj_box`, nic w cudzych projektach nie ruszono): import trzech modułów, dekompilacja
   funkcji, podmiana indeksów na napisy, "skrót" funkcji = kolejność odwołań do napisów i numery linii źródła `.pyx`.
4. **Ograniczenie:** to jest odczyt skompilowanego Pythona, nie źródło. Kolejność odwołań pokazuje *co funkcja dotyka*, nie zawsze
   *w jakim warunku*. Dla `multi_color_controller` dekoder napisów dał nieczytelne skróty dla części funkcji (wspólne napisy mieszają
   się) - tam opieram się tylko na jednoznacznych napisach i nazwach funkcji.

## 3. Pozycje z listy

### 3.1 Trzy zostające timery po każdym załadowaniu ("load-cell") - **[BRAK] w opisanej postaci, ale jest podobny podejrzany wzorzec**

- **[DOWÓD]** W kodzie Boksa Q2 nie ma żadnego odwołania do load-cell/wagi. Valve Oil opisuje timery "z kontroli load-cell po
  załadowaniu do dyszy" - tego mechanizmu tu nie znaleziono.
- **[DOWÓD]** Gdzie rejestruje się timery (`register_timer`):
  - `box_extras.__init__`: `b_endstop_timer`, `e_endstop_timer` (po jednym, stałe; ładowania je tylko przestawiają `update_timer` na teraz/NEVER - nie tworzą nowych).
  - `box_extras.handle_connect`: 3 timery jednorazowe (`delayed_init_error_raw`, `delayed_init_rfid` x2).
  - `box_stepper.__init__`: `led_timer` na każdy slot (stały).
  - `cmd_ENABLE_BOX_DRY`: timer suszenia (jest `unregister_timer` w `cmd_DISABLE_BOX_DRY`).
- **[DOWÓD]** Dwie funkcje **tworzą nowy timer przy każdym zdarzeniu czujnika, a stary tylko "parkują" na NEVER bez `unregister_timer`**:
  `b_button_callback` (czujnik w hubie przy druku: `_auto_reload_e_pos_timer`) i `buffer_button_callback` (czujnik bufora przy druku:
  `_buffer_response_timer`). Układ wywołań w kodzie: `update_timer(stary, NEVER)` ... `register_timer(nowy, NOW)`. Stary timer zostaje
  w reaktorze. `unregister_timer` robią tylko `runout_button_callback`, `cmd_SLOT_UNLOAD`, `slot_load`, `cmd_EXTRUDER_LOAD` i to
  tylko dla `buffer_response_timer` (bieżącego).
- **[HIPOTEZA]** To może dawać ten sam skutek co u Valve Oil (rosnąca liczba timerów -> wolniejszy Klipper -> "Communication timeout
  during homing"), ale: nie wiadomo, jak często czujnik bufora przeskakuje w czasie druku, ani czy stary timer faktycznie nie jest
  zwalniany gdzie indziej (kolejność odwołań nie mówi o gałęziach `if`). Waga problemu nieznana.
- **Naprawa naszym modułem:** możliwa tylko **pomiarowo** na razie: mały moduł-Python (`klippy/extras`, nie ruszający Boksa),
  który co minutę zapisuje do `klippy.log` liczbę timerów reaktora (`len(reactor._timers)`) i polecenie `TWEAKED_TIMER_COUNT`.
  Dopiero po zmierzeniu na prawdziwym Boksie (np. po 50 zmianach narzędzia) warto robić czyszczenie (np. wyrejestrowanie timerów
  zaparkowanych na NEVER, ale ostrożnie: QIDI sam ich nie wyrejestrowuje i niektóre są ponownie używane). Binarki nie łatamy.
- **Ryzyko:** pomiar - minimalne (odczyt); czyszczenie reaktora - średnie (zły timer = utrata funkcji, np. auto-wymiana filamentu).

### 3.2 Podtrzymanie grzałki Boksa i utrata łączności - mamy `box-heater-keepalive` - **[DOWÓD] mechanizm, [HIPOTEZA] zasięg**

- **[DOWÓD]** Nasza łatka jest w czytelnym `heaters.py` (nazwa grzałki zawiera `heater_box`), nie w skompilowanym kodzie. Skompilowany kod
  tylko ustawia temperatury (`SET_HEATER_TEMPERATURE HEATER=heater_box<N> TARGET=...`, `heating_handler`, `RUN_STEPPER`).
- **[HIPOTEZA]** Dotyczy tylko Boksów USB (tryb LOCAL). W trybie REMOTE (Boks 2) grzałkami steruje samo pudełko - łatka nie ma tam nic do roboty.
- Reszta "utraty łączności" (Klipper nie reaguje na `Lost communication with MCU 'mcu_boxN'`, czujniki grzałek po shutdownie) to zachowanie
  rdzenia Klippera/QIDI, nie `box_extras` - nie badano.

### 3.3 Shutdown przy nieznanym filamencie - **[HIPOTEZA]**

- **[DOWÓD]** `box_extras` czyta `officiall_filas_list.cfg` (ConfigParser, ścieżka `/home/mks/printer_data/config/...`) i ma komunikat
  "officiall_filas_list file error."; `multi_color_controller.MaterialDatabase` ma `get_fila_dict/get_vendor_val/get_color_val` i
  komunikat "Failed to parse material config". Plik ma 51 sekcji `[filaN]` (typ, temperatury min/max, temperatury Boksa).
- **[HIPOTEZA]** Nie widać, czy brak identyfikatora filamentu w tym pliku kończy się wyjątkiem i shutdownem (jak u Valve Oil), czy jest
  obsłużony. Nie ustalono z samego odczytu.
- **Naprawa:** jeśli się potwierdzi, da się ją zrobić **danymi**, bez patchowania: dopisać brakujące filamenty do
  `officiall_filas_list.cfg` (plik czytelny, nasz moduł mógłby go uzupełniać o filamenty z naszych profili Orki). Ryzyko niskie
  (zła sekcja = zły zakres temperatur dla tego filamentu).

### 3.4 Zawieszenie `FLOW_STOP` - **[BRAK] w tym firmware**

- **[DOWÓD]** Napisu `FLOW_STOP` nie ma w żadnym z trzech modułów (02.04 ani 03.02). Kolejka kroków (`TaskQueueManager`) ma `reset`, `stop` i
  `active_step_locked`, ale nie to polecenie. Zgłoszenie Valve Oil dotyczy innej wersji kodu (Max 4). Nic do naprawiania, dopóki
  QIDI nie dołoży tego w nowszym firmware.

### 3.5 Filament uwięziony między hubem a głowicą - **[HIPOTEZA]**

- **[DOWÓD]** Po nieudanym ładowaniu `slot_load` / `cmd_EXTRUDER_LOAD` zapisują `retry_step` (`slot_load1_N`, `EXTRUDER_LOAD1_N` ...) i kody błędów
  QDE_004_001/006/008 ("Extruder unloading failure. Extruder unload again: EXTRUDER_UNLOAD SLOT=%s").
  Czyli QIDI przewiduje ponowienie ręczne (`TRY_MOVE_AGAIN` -> `cmd_RETRY`, komunikat "No step to retry").
- **[HIPOTEZA]** Czy `SLOT_UNLOAD` wyciąga filament z odcinka między hubem a głowicą (gdy czujnik huba już nie widzi filamentu), nie wynika z odczytu.
- **Naprawa makrem:** niepewna (potrzebna znajomość czujników; ruch silnika slotu to `RUN_STEPPER`, które jest gotowym poleceniem).
  Nie proponuję bez Boksa.

### 3.6 Eject i bazowanie głowicy - **[DOWÓD] że kod to robi w jednej gałęzi, [HIPOTEZA] kiedy**

- **[DOWÓD]** `button_box_unload` (polecenie `E_BOX`, wysuw ze slotu) w jednej z gałęzi uruchamia `_CG28 / MOVE_TO_TRASH / M400`, potem
  `cmd_EXTRUDER_UNLOAD`, potem `cmd_SLOT_UNLOAD`. Ta gałąź jest warunkowana wskazaniem czujnika filamentu głowicy i tym, czy ten slot jest
  tym wczytanym (`filament_present` i porównanie z zapisanym slotem). Gdy filament **nie** jest w głowicy, widać drugą gałąź bez `_CG28`.
  Wygląda więc na to, że na Q2 bazowanie przy ejectcie jest uzasadnione (trzeba wyciągnąć filament z głowicy przy gorącej dyszy w
  koszu), inaczej niż w opisie Valve Oil. Pewności brak.
- **[DOWÓD]** `_CG28` w 02.04 to makro: `G28` (wszystko, razem z Z), jeśli nie zbazowano xyz. Używa go też `CUT_FILAMENT`,
  `button_extruder_load/unload`, `TRY_RESUME_PRINT`, `M604`, `M4030...` - pewne ryzyko znane z PLUS4 #134: po dłuższym postoju (silniki
  wyłączone) wczytanie filamentu bazuje Z przy wydruku jeszcze na płycie.
- **Naprawa makrem (możliwa):** podmienić `_CG28` tak, by przy niezbazowanych osiach bazowało tylko `G28 X Y` (to wszystko, czego
  potrzebuje `MOVE_TO_TRASH`). Wymaga decyzji właściciela (to zmiana ruchu przy każdym ładowaniu/wyładowaniu filamentu, także bez
  Boksa) i testu na drukarce. Ryzyko: średnie (ruch XY bez znanego Z; dysza mogłaby zahaczyć o wysoki wydruk na płycie).

### 3.7 `INIT_RFID_READ` przy starcie - **[BRAK] w 02.04; w 03.02 [HIPOTEZA]**

- **[DOWÓD]** W makrach 02.04 `PRINTER_INIT` (0,2 s po starcie) robi tylko silniki Z/TMC, `BED_MESH_CLEAR` i `DISABLE_ALL_SENSOR`;
  `INIT_RFID_READ` nie jest wołane z makr w ogóle. Odczyt startowy robi sam `box_extras` przez timer `delayed_init_rfid`, który ma
  zabezpieczenie: wykonuje się tylko gdy drukarka nie drukuje (`idle_timeout.printing_time == 0`) i wg zmiennej `can_run_init_read`.
- **[HIPOTEZA]** Błąd Valve Oil (`'NoneType' object has no attribute 'allVariables'`) dotyczy makra startowego Max 4. W 03.02 makro wołające
  to polecenie jest (wg wcześniejszego przeglądu), a plik Boksa jest ten sam - tam ryzyko może istnieć. W 02.04: nic do zrobienia.

### 3.8 Zablokowane ładowania ("Unable to recognize loaded filament") - **[DOWÓD] źródło komunikatu, [HIPOTEZA] pętla**

- **[DOWÓD]** Komunikat `Code:QDE_004_021 Unable to recognize loaded filament` i `can not recognize the loaded filament` występują w
  `button_extruder_load`, `cmd_TRY_RESUME_PRINT`, `cmd_RESUME_PRINT_1`, `cmd_BOX_PRINT_START`. Warunek: stan czujnika huba (`b_endstop_state`)
  jest "załadowane", a zapisany `last_load_slot` to `slot16` (zewnętrzna szpula) albo pusty. Czyli niespójność między czujnikiem a
  zapisaną zmienną.
- **[HIPOTEZA]** To ten sam objaw co u Valve Oil (filament przy hubie, żaden slot nie zapisany jako wczytany). Ręczny obejście istnieje w
  zapisanych zmiennych (`last_load_slot`).
- **Naprawa makrem:** niepewna - odpowiedni stan trzeba zdefiniować na Boksie. Nie proponuję bez sprzętu.

### 3.9 `EXT_WIPE failed` - **[BRAK] w napisach**

- **[DOWÓD]** `EXT_WIPE` jest tylko nazwą kroku w `TaskQueueManager._check_step_finished` (obok `BOX_WIPE`). Komunikatu "Step EXT_WIPE failed.
  Pausing flow." (ani "Pausing flow") w kodzie nie ma, więc zachowanie opisane u Valve Oil może być zrobione inaczej. Nie badano
  logiki warunku końca kroku (`_check_step_finished`).

### 3.10 Start druku na narzędziu bez slotu - **[HIPOTEZA] silna**

- **[DOWÓD]** `cmd_BOX_PRINT_START` pobiera numer slotu z `value_tN` (mapowanie narzędzie -> slot) i robi `lookup_object('box_stepper slot' + numer)`
  bez widocznego sprawdzenia, czy taka sekcja istnieje. Klipper dla nieistniejącej sekcji zgłasza `Unknown config object`, a polecenie
  w środku makra `PRINT_START` kończy się błędem (u Valve Oil: shutdown po nagrzewaniu, sondowaniu i siatce).
- **[HIPOTEZA]** Dopuszczalne tylko przy Boksie z mniej niż 4 slotami i wydruku z T4, albo narzędzie przypisane do zewnętrznej szpuli.
- **Naprawa makrem (możliwa):** w `PRINT_START` przed `BOX_PRINT_START` sprawdzić `printer['box_stepper ' ~ slot]` (slot z
  `save_variables.variables['value_t' ~ N]`) i przy braku zgłosić błąd **przed** nagrzewaniem (zamiast po). Ryzyko niskie,
  jeśli tylko dodaje wczesne sprawdzenie i przerywa (nie zmienia reszty). Nazwy zmiennych `value_tN` trzeba potwierdzić z
  prawdziwego `saved_variables.cfg` Boksa.

### 3.11 SAVE_VARIABLE czekające na sprawdzenie startowe Boksa - **[HIPOTEZA], ale znaleziono coś innego**

- Nie znaleziono mechanizmu "czekania na sprawdzenie startowe".
- **[DOWÓD] (nowe):** `box_extras.save_variable` **nie używa** `SAVE_VARIABLE`: sam wczytuje `allVariables`, buduje `ConfigParser`, zapisuje cały
  plik `saved_variables.cfg` przez `open(filename, 'w')` i woła `loadVariables()`. Dla każdej zmiennej osobno.
  Wniosek: nasza łatka `save-variables-atomic` (poprawia `save_variables.py`) **nie obejmuje tej ścieżki** - zapisy Boksa nadal skracają plik
  przed zapisem (ryzyko pustego pliku przy zaniku prądu w tym momencie) i nadal są pełnym przepisaniem.
- **[DOWÓD]** Makro `PRINT_START` w 02.04 zapisuje 16 razy `SAVE_VARIABLE runout_i` z `G4 P100` po każdym (ponad 1,6 s samego czekania, plus 16 pełnych
  przepisań pliku) oraz kilka dalszych zapisów.
- **Naprawa makrem (możliwa, mała):** w `PRINT_START` pisać `runout_i` tylko gdy wartość różni się od 0 i zdjąć `G4 P100`. Ryzyko niskie.
  Zapisów wewnątrz skompilowanego kodu (`box_extras.save_variable`) nie da się przechwycić bez łatania binarki (można tylko
  zmniejszyć liczbę wywołań).

### 3.12 Mapowanie narzędzie -> slot przecieka do następnego druku (Valve Oil #78) - **[DOWÓD] mechanizm, naprawa możliwa**

- **[DOWÓD]** Mapowanie to zmienne `value_t<N>` w `saved_variables.cfg`. Zapisuje je: ekran (`qidiclient` zawiera `value_t` 18 razy), polecenie
  `INIT_MAPPING_VALUE` (`box_extras.cmd_INIT_MAPPING_VALUE`: dla każdego narzędzia zapisuje `value_t<i>` na domyślny slot) i, wg wcześniejszych notatek,
  wymiana po końcu filamentu. Odczytują: `TOOL_CHANGE_START`, `CUT_FILAMENT`, `BOX_PRINT_START`.
- **[DOWÓD]** Makra 02.04 (`PRINT_END`, `CANCEL_PRINT`) **nie** resetują mapowania i nie wołają `INIT_MAPPING_VALUE`; w całych makrach nie ma tego
  polecenia. Nikt go więc nie wywołuje po druku. W `multi_color_controller` jest `LocalAdapter.init_mapping` -> `INIT_MAPPING_VALUE`, wołane przez
  `MULTI_COLOR_INIT_MAPPING` (kto je woła: nie ustalono; ekran go nie zawiera pod tą nazwą).
- **Naprawa makrem (możliwa, mała):** na końcu `PRINT_END` i `CANCEL_PRINT` (nie na początku - zgodnie z wnioskami z Valve Oil #78) dodać
  `{% if box_count >= 1 and enable_box == 1 and printer["box_extras"] %} INIT_MAPPING_VALUE {% endif %}`.
  **[HIPOTEZA]** że `INIT_MAPPING_VALUE` resetuje wszystko do `slotN` bez skutków ubocznych - trzeba to zobaczyć na Boksie
  (odczytać `saved_variables.cfg` przed i po). Ryzyko: niskie-średnie (zły reset = złe przypisanie przy następnym druku z ekranu,
  ale ekran i tak ustawia mapowanie przed startem).

### 3.13 Spoolman per slot - **[BRAK] w kodzie Boksa, [HIPOTEZA] co do wykonalności**

- **[DOWÓD]** W trzech modułach nie ma napisu Spoolman. Boks zapisuje stan w zmiennych: `last_load_slot`, `filament_slotN`, `vendor_slotN`,
  `color_slotN`, `slot_sync`, `extrude_state`. Dane o tym, który slot jest wczytany, są więc w `saved_variables.cfg` i w statusie `box_extras`.
- **[HIPOTEZA]** Spoolman per slot dałoby się zrobić poza kodem Boksa: komponent Moonrakera/macro ustawiający aktywną szpulę na podstawie
  `last_load_slot` i zmiennej slotu->id szpuli. Wymaga Boksa do testu. Największe ryzyko: reaguje na `SAVE_VARIABLE` o wielkich literach
  (PLUS4 #121) - patrz `save-variables-atomic`.

### 3.14 Edycja listy filamentów Boksa we Fluidd - **[DOWÓD] gdzie leżą dane**

- **[DOWÓD]** Dane slotu to zmienne `filament_slotN`, `vendor_slotN`, `color_slotN` (`box_stepper.switch_next_slot` odczytuje je i wymaga ich do automatycznej
  wymiany po końcu filamentu: bez nich komunikat QDE_004_018 "No filament specified, %s cannot be automatically replaced"). Lista dostępnych
  filamentów to `officiall_filas_list.cfg` (51 pozycji).
- **[HIPOTEZA]** Naprawa to praca w JavaScript Fluidd (karta Boksa, projekt Greg-LFT), a nie w Klipperze - znane niezgodności formatu
  zapisu (liczby kontra `QFA02`) są opisane w wcześniejszym przeglądzie. Do zrobienia dopiero z Boksem.

## 4. Inne rzeczy zauważone przy okazji

- **[DOWÓD]** Wszystkie komunikaty QIDI mają kody `QDE_004_001 ... 026` (słownik w `box_stepper`/`box_extras`): ładowanie slotu, wyładowanie, brak slotu zamiennego,
  "Please check if your PTFE Tube is bent" (QDE_004_019), "Detected wrapping filament" (bufor, QDE_004_013) itd. Przydadzą się do rozpoznawania przyczyn w logach.
- **[DOWÓD]** Wibracyjne "potrząsanie głowicą" (`shake_toolhead`, `shake_for_load/unload_toolhead`, ruchy `G1 X0 Y200 F30000` ...) jest wpisane w `box_stepper` na stałe
  - to wcześniejsze skrypty G-code z predkością 30000 mm/min; przy limitach Q2 (zakres Y do 287,5) nie sprawdzano, czy mieszczą się w zakresie.

## 5. Co proponuję zrobić i w jakiej kolejności (do decyzji właściciela)

Wszystko poniżej jest **po zakupie Boksa**, niczego nie trzeba robić teraz, a nic z tego nie zostało zainstalowane ani sprawdzone:

1. Przy pierwszym podłączeniu Boksa (bez druku): `QUERY_MULTI_COLOR` w konsoli Fluidd i przejrzenie `klippy.log` - czy Boks 2 jest w trybie LOCAL czy REMOTE (rozstrzyga, które nasze moduły mają sens).
2. Moduł pomiarowy liczby timerów reaktora (3.1) - tylko log.
3. Małe poprawki makr (3.10, 3.11, 3.12) - dopiero z próbą na Boksie, każda osobno ("jedna zmiana naraz").
4. `_CG28` bez Z (3.6) - osobna decyzja właściciela (zmienia zachowanie także bez Boksa).
5. Uzupełnianie `officiall_filas_list.cfg` o filamenty z naszych profili (3.3), gdy ktoś zgłosi problem z nieznanym filamentem.

Niczego nie podejmujemy w skompilowanych modułach (łatanie binarek): ryzyko uszkodzenia przy zmianie firmware i brak testu.

## 6. Narzędzia i pliki robocze

Poza repozytorium (katalog roboczy sesji): rozpakowane `.so` z 02.04, skrypty dekodujące napisy Cythona, zrzuty dekompilacji. Projekt Ghidry:
`ghidra_proj_box` (projekt Ghidry poza repozytorium) (osobny, nie `ghidra_proj`). Zrzuty nie są w repozytorium (duże, wyprowadzone z plików QIDI).
