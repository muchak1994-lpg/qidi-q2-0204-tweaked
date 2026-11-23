# Audyt programu ekranu QIDI Q2 (qidiclient, firmware 01.01.02.04) - "co gdzie jak"

Stan: 2026-11-22. Wersja robocza, nie zatwierdzona, niewysłana na GitHub.
Plik analizowany: oryginalny `qidiclient` z paczki 02.04 (`work/stock/files/home/qidi/QIDI_Client/bin/qidiclient`,
ARM64, 90 275 456 B, md5 `efcece0533ac4e6d3fc62ad76a88bb2e`, stripped; w środku napis wersji `01.01.02.04`).
Narzędzia: Ghidra 12.2 (projekt `tools\ghidra_proj_qidiclient`), skrypty `tools\ghscripts` (StrRefs, Decomp),
oraz lista tekstów z binarki. Nic nie zmieniano na drukarce, nic nie czytano z żywej drukarki.

**Oznaczenia dowodów:**
- **[D]** dowód - widoczny wprost w kodzie/tekstach binarki albo w plikach Moonrakera/Klippera z paczki QIDI.
- **[W]** wniosek - logicznie wynika z kodu, ale bez uruchomienia na drukarce.
- **[H]** hipoteza - domysł, do sprawdzenia.
- **[S]** zapis z symulatora ekranu (`q2-screen-sim`, firmware **03.02**, nie 02.04) - zachowanie bardzo podobne, ale to inna wersja.

Adresy funkcji to adresy wirtualne Ghidry (VA); offset w pliku = VA - 0x400000 (jak w `CLAUDE.local.md`).
Nazwy `FUN_xxxxxxxx` to nazwy z Ghidry (program jest bez symboli); nazwy klas/stron pochodzą z napisów RTTI i `Page_*`.

---

## 0. Budowa programu w skrócie [D]

- C++, grafika **LVGL** (ekran 3,97", katalog źródeł w napisach: `/builds/qidi/3dprinter_m4/qidiclient/ui/draw_ui/QD_Q2/3.97_inch/draw_page_*.cpp`).
- Wątek główny `FUN_005b8e30` (to nasz "main/init"): inicjuje LVGL, **framebuffer** (`FUN_00765cc0`), **dotyk** (`FUN_007661c0`),
  ustawia podświetlenie na 200 (`FUN_006dcff0(200)`), potem uruchamia wątki i czeka na gotowość.
- Wzorzec **Observer + Singleton** (`Observer`, `Singleton<…>`, `notify_*` jako nazwy zdarzeń): dane z Moonrakera wpadają do
  `PrinterDataManager`, który rozgłasza zdarzenia do stron (np. `print_state`, `webhooks_state_message`, `cloud_status_changed`).
- Biblioteki wewnątrz: websocketpp + boost.asio, nlohmann::json, spdlog, curl, libudev, wpa_supplicant (WiFi), sdbus-cpp (D-Bus), stb_image.
- Logi: `/root/qidi-client/qidi-client.log` (spdlog), konsola ma też zwykłe `std::cout` (np. `Send gcode: …`).

## 1. Skąd program bierze dane

### 1.1 Moonraker przez WebSocket [D]
- Adres `127.0.0.1`, ścieżka `/websocket` (napisy; port prawdopodobnie 7125, [H] - liczby nie sprawdzałem).
- Protokół JSON-RPC 2.0. Wywoływane metody (lista napisów, obszar ~94524): `server.connection.identify`, `printer.info`,
  `printer.objects.list/query/subscribe`, `printer.gcode.script`, `printer.print.start/pause/resume/cancel/power_off_print`,
  `server.files.*`, `server.database.*` (w tym `server.database.config.select/update/delete` - to rozszerzenie QIDI),
  `server.history.*`, `server.job_queue.*`, `machine.update.*`, `machine.timelapse.get_settings`,
  `server.moonraker_status.subscribe`, `printer.connection.send_event_to_all`, `machine.reboot/shutdown`, `machine.services.restart`.
- Odbierane powiadomienia (obsługa w `FUN_006bf8d0`, VA 0x6bf8d0): `notify_gcode_response`, `notify_status_update`,
  `notify_klippy_ready/shutdown/disconnected`, `notify_filelist_changed`, `notify_update_response`, `notify_history_changed`,
  `notify_power_changed`, `notify_mqtt_change`, `notify_moonraker_status_update`.
- **Subskrypcja obiektów Klippera** - tabela w `FUN_006c2f50` (VA 0x6c2f50): `extruder`, `heater_bed`, `heater_generic chamber`,
  `gcode_move`, `toolhead`, `fan*` (cooling_fan, board_fan, chamber_circulation_fan, auxiliary_cooling_fan, chamber_fan, hotend_fan),
  `print_stats`, `print_stats_manager`, `display_status`, `idle_timeout`, `webhooks`, `bed_mesh`, `probe`,
  `output_pin caselight`/`polar_cooler`, `filament_switch_sensor`, `temperature_sensor Chamber_Thermal_Protection_Sensor`,
  `heater_temp_a/b_box1`, `box_extras`, `box_stepper`, `heater_generic heater_box`, `aht20_f`, `multi_color_controller`,
  `exclude_object`, `virtual_sdcard`, `z_tilt`, `mcu THR`, `closed_loop x/y`, `firmware_retraction`, **`save_variables`**
  (z polami `qdc_ai_error_code`, `enable_box`, `box_count`, `filament_slotN`/`color_slotN`/`vendor_slotN`, `value_tN`,
  `enable_noodle_detection`, `noodle_sensitivity_level`, `enable_model_shift/collapse_detection` itd.).
- **Baza Moonrakera (rozszerzenie QIDI)**: ustawienia ekranu siedzą w `server.database.config.*` pod kluczami
  `general.language`, `general.sound`, `general.sleep_time`, `general.chamber_light`, `general.indicator_light`, `general.video`,
  `general.lan_mode(_live)`, `general.wlan`, `general.expert_mode`, `general.startup_guide`, **`general.screen_state`**,
  `ai.noodle_detection`, `ai.sensitivity`, `ai.spool_detection`, `ai.foreign_object_detection`, `ai.bed_detection`,
  `printing.cache`, `printing.polar_cooler`, `user.*`, `nozzle.type/diameter`, `update.close_loop_hd_version`, `gongfudou_mqtt.*`.
  Handler zmian: `FUN_006b32e4` (VA 0x6b32e4) - emituje zdarzenia `*_config_updated`.

### 1.2 Program jest też serwerem JSON-RPC [D]
`FUN_006c14b4` (VA 0x6c14b4): na tym samym WebSockecie odpowiada na metody `qidiclient.files.list`, `qidiclient.files.stats`,
`qidiclient.config.offical_filament_list`, `qidiclient.crypto.aes_decrypt_hex` (+ warianty `api.qidiclient.*`) i `get_all_error_list`.
Czyli inne usługi (Moonraker QIDI, aplikacja AI) mogą pytać ekran o listę plików z miniaturami, statystyki, listę filamentów QIDI
(plik `/home/qidi/printer_data/config/officiall_filas_list.cfg`) i odszyfrowanie AES (klucz wbudowany w binarkę - nie przepisuję go tutaj).

### 1.3 D-Bus [D]
Nazwy: `org.qidi.qidi_client` (`/org/qidi/qidi_client`), `org.qidi.moonraker`, `org.qidi.klipper`, `org.qidi.signal`; klasa `DBusWorker`,
metody `Execute`, "unified polling loop". Używane do restartów usług i sygnałów systemowych ([W] - treść wiadomości nie czytana).
`org.qidi.signal` ma 3 odwołania: `FUN_00484460`, `FUN_004b9db0`.

### 1.4 Pliki i polecenia systemowe [D]
- Pliki G-code: `/home/qidi/printer_data/gcodes/`, USB: `/home/qidi/printer_data/gcodes/USB/`, cache miniatur `/home/qidi/printer_data/.cache/`,
  `.thumbs/`, `.temp`; inotify-monitor plików (`FileMonitor`), parser 3mf (`Metadata/slice_info.config`, `plate_N`, miniatury `thumbnail_*`).
- Konfiguracje: `printer.cfg`, `gcode_macro.cfg`, `box.cfg`, `MCU_ID.cfg` (program **sam generuje/kopiuje** fragmenty konfiguracji Boksa
  i aktualizacji - patrz niżej), `motion_accuracy_calibration.json`.
- Sprzęt: `/dev/fb0`, `/dev/input/event0`, `/sys/class/backlight/backlight/brightness`, `/dev/serial/by-id/*` (rozpoznanie MCU/THR/BOX
  po nazwach `usb-Klipper_*`), `/proc/net/dev`, `/proc/net/wireless`, `/proc/uptime`, `/proc/mounts`, udev (USB).
- Polecenia powłoki: `systemctl restart klipper|moonraker|qidi-client`, `ip route`, `ping -c 20` (test sieci), `mount/umount`,
  `mkfs.vfat/exfat/ext4` (format USB), `dpkg -i …dosfstools…`, `ntpdate -u`, `find /root/qidi-client -name "qidi-client_*.log" -mtime +7 -delete`.
- Sieć: UDP broadcast (odkrywanie "mkswifi"), WiFi przez wpa_supplicant (`SET_NETWORK`, `ENABLE_NETWORK`, `SCAN_RESULTS`),
  SSE do chmury, HTTPS do `api.qidimaker.com(.cn)`, `download.*.qidi3dprinter.com` (aktualizacje, wiązanie konta, raporty urządzenia
  `/community/v1/device/status/report`, wideo AI `/backend/v1/ai/video/new/upload`), tunel FRP (`/root/Frp/frpc.json`), MQTT.
  Tryb LAN blokuje te żądania (napis "Request blocked by URL filter (LAN mode)").
  **Uwaga prywatność:** `/community/v1/device/status/report` wysyła numer seryjny, MAC, IP i wersję firmware do chmury QIDI [D: nazwy pól]; kiedy dokładnie - [H].

## 2. Dotyk, uśpienie i wybudzanie ekranu

### 2.1 Dotyk [D]
`FUN_007661c0` (VA 0x7661c0) wywołuje `FUN_00766130("/dev/input/event0")`: `open(path, 0x902)` (RDWR|NOCTTY|NONBLOCK), potem `fcntl(...)`.
Zdarzenia evdev czytane przez sterownik wejścia LVGL (zarejestrowany w `FUN_005b8e30`). Zgodne z naszym modułem `printer-screen-touch`
(zdarzenia zapisywane do tego samego pliku przez usługę) - patrz `CLAUDE.local.md`.

### 2.2 Ekran (framebuffer) [D]
`FUN_00765cc0` (VA 0x765cc0): `open("/dev/fb0", O_RDWR)`, `ioctl(FBIOBLANK=0x4611, 0)` (odblokowanie), `FBIOGET_FSCREENINFO (0x4602)`,
`FBIOGET_VSCREENINFO (0x4600)`, `mmap` całego bufora. Rysowanie bezpośrednio do pamięci - stąd działa podgląd z `/dev/fb0`.

### 2.3 Podświetlenie i uśpienie [D+W]
- `FUN_006dcff0(n)` (VA 0x6dcff0): zapisuje liczbę `n` do `/sys/class/backlight/backlight/brightness` (komunikat błędu "Failed to open brightness file").
  Wartości widziane: **200** przy starcie (w `FUN_005b8e30`), **255 (0xff)** przy wybudzeniu, **0** przy uśpieniu.
- **Wybudzenie** `FUN_005b6604` (VA 0x5b6604): [D] woła `FUN_006a2fe0` (zapis `screen_state`), `FUN_00700ba4(0)`, jasność 0xff, odrysowanie LVGL.
- **Uśpienie** `FUN_005ba054` (VA 0x5ba054): [D] woła `FUN_006a2fe0`, jasność **0**, wyłącza wyświetlacz LVGL; zawiera też licznik z
  zaciemnionymi warunkami (obfuskacja) uruchamiający dodatkowe wątki co jakiś czas [W - cel nieznany, wygląda na okresowe zadania tła].
- **`general.screen_state`**: `FUN_006a2fe0` (VA 0x6a2fe0) trzyma wartość w polu obiektu (+0x1294) i wysyła ją do bazy Moonrakera
  (`general`/`screen_state`) przez `server.database.config.update` [D]. Wartości: **1 = ekran włączony, 0 = uśpiony** [S: w symulatorze
  zapis `1` po starcie, `0` po 5 min bezczynności razem z jasnością 0] [W dla 02.04].
- Moonraker (plik `moonraker/components/database.py`, linie ~1203-1235 [D, paczka QIDI]): zmiana `general.chamber_light` lub
  `general.screen_state` uruchamia w Klipperze **`SMART_STATUS MODE=<światło> SCREEN=<stan>`**. `screen_state` NIE jest zapisywany do pliku
  konfiguracji (pominięte w `update_value_from_config`), domyślnie "1" (linia ~117).
  To jest jedyne, co ekran "mówi" Klipperowi o uśpieniu - **dotyk i popupy nie budzą ekranu same z siebie** (zgodnie z notatką z `CLAUDE.local.md`;
  tutaj potwierdzone od strony kodu uśpienia/wybudzenia, ale bez prześledzenia wszystkich wywołań `FUN_005b6604`).
- Czas do uśpienia: `general.sleep_time` (minuty; w symulatorze najkrótszy wybór = 5). Napisy: "Automatic Sleep", `sleeptime_config_updated`.
- [S] W symulatorze wybudzenie przychodzi też z "linii konsoli Klippera" `q2_wake_screen` (pomysł z 03.02; w napisach 02.04 **nie ma** takiego tekstu - [D: brak w liście napisów]).
  Czyli w 02.04 wybudzenie programowe z zewnątrz jest możliwe tylko przez dotyk albo przez zmianę `screen_state`/`sleep_time` [H - nie testowane].

## 3. Ekrany (strony) i komunikaty

### 3.1 Strony LVGL [D] (nazwy `Page_*` z napisów)
Nawigacja boczna (5 ikon): **Home, Control, Filament, Setting, Message** (`Page_Home/Control/Filament/Setting/Message`).
Pozostałe: `Page_Printing`, `Page_Preview`, `Page_File`, `Page_Usb_Store`, `Page_Set_Cool/Extruder/Move/Speed/Filament`, `Page_Exclude_Object`,
`Page_Filament_Handling`, `Page_Filament_Drying`, `Page_Filament_Drying_Handling`, `Page_Prepare_Drying`, `Page_Box_Drying`, `Page_Box_Option`,
`Page_Ams` (ekran Boksa), `Page_Printing_Option`, `Page_Config_Setting`, `Page_Function`, `Page_Device`, `Page_Toolbox`, `Page_Firmware`,
`Page_Offline_Update`, `Page_Update_Instruction`, `Page_Network`, `Page_Network_Test`, `Page_Lan_Mode`, `Page_Account`, `Page_Select_Region`,
`Page_Calibration`, `Page_Calibration_Handling`, `Page_Platform_Calibration`, `Page_Auto_Leveling`, `Page_Input_Shaping`, `Page_Bed_Mesh`,
`Page_Self_Check`, `Page_Self_Check_Handling`, `Page_Startup_*` (Language, Region, Wifi, Binding, Remove, Start, Calibration_Handling, Self_Check(_Handling)),
`Page_Show_PNG`. Przełączanie: `FUN_` w `lvgl_ui.cpp` ("page to -> {}", "Current page: %s").

Okna popup (`draw_page_popup.cpp`): wybór temperatury (extruder/stół/komora/Box), 4 wentylatory + polar cooler, Z-offset (0,01/0,05 mm),
`CompletePop` (koniec druku: czas, filament, "Print again", "report AI problems", "quality guide"), popup błędu (`error_popup`), ostrzeżenia
(`warning_icon`), `update_popup`, `info_popup`, "sure to cancel print".

### 3.2 Skąd biorą się komunikaty błędów [D, ważne]
1. **Zdarzenie `ui_assistant_message_update`** przychodzące przez Moonrakera: ramka `printer.connection.send_event_to_all` z
   `{"event":"ui_assistant_message_update","data":{"event":"add|update|remove","results":{...}}}`. [S: zapis z symulatora, pole
   `results`: `error_code`, `error_message`, `error_popup` (bool), `error_type`, `error_weight`, `prossess_message` (sic), `timestamp`].
   Parser: `FUN_006ac920` (VA 0x6ac920, zdarzenia "update"/"remove") i `FUN_006ad270` (VA 0x6ad270, odpowiedź "GetAll"/lista).
   Nadawca w 02.04: **nie ustalony** (nie jest nim stockowy Klipper ani Moonraker - w ich kodzie nie ma `ui_assistant`/`QDC_`; [H] usługa
   QIDI: `algo_app` albo moduł chmury/MQTT). Przykład z symulatora: kod `QDC_400_004_010_001` = "MQTT connection error".
2. **15 obsługiwanych kodów `QDC_*`** (klasy `QDC_..._Handler`, rejestrowane przez `ErrorHandlerRegistrar`, plik treści
   `/home/qidi/QIDI_Client/resource/qidi_client_error/<KOD>/0.json` - teksty w 10 językach, pola `message_translation`,
   `prossess_msg_translation`, `error_qr_code_path`, `main_pic`, `left_text`, `right_text`, `popup_stlye`, `is_model`):
   `QDC_100_005_000_001`, `QDC_100_005_005_001` (= "New firmware version available", przycisk wiedzie do strony `/home`/Firmware),
   `QDC_100_005_015_001`, `QDC_200_001_005_001/002/003`, `QDC_200_001_010_001`, `QDC_300_001_010_001/002`, `QDC_300_005_005_001`,
   `QDC_400_004_005_001`, `QDC_400_004_010_001` (MQTT), `QDC_400_005_015_001`, `QDC_500_005_005_001/002`.
   Znaczenia pozostałych **nie znam** [brak]: w paczce 02.04 jest tylko `QDC_100_005_005_001/0.json`, reszta jest u QIDI generowana/pobierana
   (do sprawdzenia na drukarce: `ls /home/qidi/QIDI_Client/resource/qidi_client_error/`). Układ kodu `QDC_<A>_<B>_<C>_<D>` ([H] A = kategoria 1-5, C = poziom/waga 0/5/10/15).
3. **Komunikaty AI z `save_variables`**: `FUN_006c2f50` subskrybuje `save_variables`; pole `qdc_ai_error_code` zawiera tekst typu
   `noodle=5 status=0 time=...` albo `foreign=1 status=1 time=...` [D: format w kodzie Klippera `save_variables.py` i w tekstach ekranu]. Strona Home
   (`draw_page_home.cpp`) reaguje na tokeny `noodle_detected` / `foreign_object_detected` (napisy `noodle`, `foreign`) i pokazuje okno
   "AI" z raportem (`ai_report_msg`, `report`, przycisk "report AI monitor problems"). [W: dokładne warunki - nieprześledzone.]
4. **Zdarzenia Klippera**: `webhooks.state_message` -> `klippererror`/`moonrakererror` (strona Startup/Home); stały tekst "Lost communication with MCU",
   "Heater extruder not heating at expected rate", "Move queue overflow", "Unknown exception caught" są **rozpoznawane po treści** `state_message`
   [D: napisy w `draw_page_home.cpp`] i przekładane na komunikat z poradą (`QDC_100_005_005_001`... itd. [H]).
5. **`power_outage_interaction`** (`FUN_00524f04`, VA 0x524f04): okno z przyciskami `cancel` / `confirm` o wznowieniu po zaniku zasilania; napis
   `not_power_off_print_msg`. Sterowane stanem `print_stats` (`interrupted`) [W].
6. **Odpowiedzi G-code (`notify_gcode_response`)** - ekran **NIE** wyświetla ich jako popupów. `FUN_006afa04` (VA 0x6afa04) szuka tylko
   kilku wzorców [D+W]: wyniki PID ("PID parameters" -> zdarzenie `pid_finished`), "File opened:" (nazwa pliku), "Done printing file" ->
   `print_complete`, oraz wartość `…(mV)` (regex `(-?\d+\.?\d*)(?=\(mV\))`) -> `weight_result` (ważenie stołu przy kalibracji). Zwykłe
   `RESPOND TYPE=error` z makr **prawdopodobnie nie robi popupu** [W: z kodu tego jednego handlera; nie sprawdzone na żywo] i trafia tylko do konsoli Fluidd. Żeby na ekranie pojawił się komunikat, trzeba przejść
   drogą z punktu 2.1 (zdarzenie `ui_assistant_message_update`) albo `save_variables` (3).
7. Komunikaty stanu druku: `ui_loading_pausing/resuming/cancelling`, kroki przygotowania ("tool head reset", "change filament", "flush filament",
   "clear nozzle", "z tilt adjust", "wait bed/chamber temp", "auto bed adjust" - tekst `ui_step_*` z `print_stats_manager.sub_status`).

### 3.3 Obliczanie czasu do końca
Już ustalone w `CLAUDE.local.md` (`FUN_0055e090`): nie powtarzam.

## 4. Co program wysyła do Klippera / Moonrakera

### 4.1 Stałe polecenia G-code (z napisów, [D])
`SET_PRINT_MAIN_STATUS MAIN_STATUS=ready`, `SET_PRINT_SUB_STATUS SUB_STATUS=<x>` (np. `bit_filamenting`), `SDCARD_RESET_FILE`, `TRY_MOVE_AGAIN`,
`RESUME`, `FIRMWARE_RESTART`, `SAVE_CONFIG`, `G28 X Y`, `G1 Z10 F600`, `SET_KINEMATIC_POSITION X/Y/Z=150` (obejście bazowania przy kalibracji),
`SET_GCODE_OFFSET Z_ADJUST=<v> MOVE=1`, `M104/M109/M140/M190/M141/M191 S<t>` (grzanie), `M106 S`, `M106 P2/P3/P4 S` (wentylatory),
`M221 S` (przepływ), `M603 S`, `M604 T` (QIDI: filament/slot), `M4029 S`, `M901 R0` / `M901 R0 S1` (QIDI),
`EXCLUDE_OBJECT NAME=<x>` (drukuje na konsolę "Send gcode: ..." - `FUN_006605e0`, VA 0x6605e0),
`SET_PIN PIN=<x> VALUE=`, `LED_ON`, `LED_oFF` (literówka w oryginale), `NEOPIXEL_ENABLE ENABLE=0|1`,
`SAVE_VARIABLE VARIABLE=beep VALUE=0|1`, `SAVE_VARIABLE VARIABLE=enable_box|enable_polar_cooler|box_drying_roll_enable|filament_slotN|color_slotN|vendor_slotN|value_t VALUE=…`,
Box: `ENABLE_BOX_DRY BOX=<n> TEMP=<t>`, `DISABLE_BOX_DRY`, `SET_FILAMENT_DRY END_TIME=… BED_TEMP=… CHAMBER_TEMP=…`, `SET_HEATER_TEMPERATURE HEATER=heater_box TARGET=…`,
`RFID_READ SLOT=slotN`, `MULTI_COLOR_LOAD|UNLOAD|BOX_UNLOAD SLOT=slotN`, `prepare_filament_dry`, `move_screw`.
Wzór nazw: program szuka też słów `restart_klipper`, `restart_firmware` (przyciski w oknie błędu `ErrorMsgState`).
**Brak** w napisach: `M4050` (wykrywanie obcych przedmiotów robi Klipper/`ai_func_manager.py`, nie ekran), `PAUSE`/`CANCEL_PRINT` jako G-code
(pauza/wznowienie/anulowanie idą metodami JSON-RPC `printer.print.pause/resume/cancel`).

### 4.2 JSON-RPC [D]
`printer.gcode.script` (G-code wyżej), `printer.print.start/pause/resume/cancel/power_off_print`, `server.database.config.update` (ustawienia i
`screen_state`), `server.job_queue.*`, `machine.timelapse` (`/machine/timelapse/settings?enabled=`), `machine.services.restart`,
`printer.emergency_stop`, `machine.reboot/shutdown`, `/printer/frp/update`.

### 4.3 Własne działania na plikach [D]
Aktualizacje online/offline (`/home/qidi/download/online_update.zip`, `USB/QD_Update/QD_Q2_*.zip`, `QD_Mandatory_Update.zip`): ekran **sam rozpakowuje**
paczkę, **kopiuje `printer.cfg` i `gcode_macro.cfg` do `.bak`**, nadpisuje je, flashuje MCU/THR/BOX/silniki zamknięte (closed loop) i restartuje usługi.
Przed `klipperrestart` wyłącza grzałki i czeka aż ostygną (timeout, potem restartuje mimo to). Formatowanie USB, eksport logów na USB
(`QD_logs.zip`), przywracanie ustawień fabrycznych (`restore_factory_settings`).

## 5. Znane problemy i pomysły na moduły

1. **Przypadek "ekran nie wie o pauzie/zdarzeniu z naszych skryptów":** ekran ignoruje `RESPOND` (p. 3.2.6). Nasze komunikaty (ntfy) idą więc obok ekranu.
   Pomysł [H]: moduł wysyłający `printer.connection.send_event_to_all` z `ui_assistant_message_update` (własny kod błędu spośród 15 znanych, żeby ekran
   miał gotowy JSON), np. powiadomienie na ekranie przy końcu suszenia. Wymaga ustalenia nadawcy i działania `error_popup` - test na zywo.
2. **Tekst `qdc_ai_error_code` jest pojedynczy** (jedno pole w `save_variables`): kolejne zdarzenie nadpisuje poprzednie [W] - możliwe zgubienie
   alertu, jeśli dwa przyjdą szybko.
3. **Tryb uśpienia** zapisuje `screen_state` do Moonrakera przy każdej zmianie [D]; `SMART_STATUS` w Klipperze steruje z niego światłem [D]. Gdyby
   ekran padł uśpiony, światło zostanie według ostatniego `SCREEN=`. Pomysł [H]: moduł "wybudź ekran na pauzie/błędzie" przez zapis `screen_state=1`
   (nie testowane, może nie wybudzić samego panelu - sam panel budzi tylko dotyk/`FUN_005b6604`).
4. **Aktualizacja z ekranu nadpisuje `printer.cfg` i `gcode_macro.cfg`** (kopia `.bak` tylko jedna): nasze moduły zmieniające te pliki znikną po
   aktualizacji z ekranu [D: kod kopiowania]. Zalecenie: nie klikać Update (zgodnie z zasadami projektu) - i dopisać ostrzeżenie w README.
5. **Pamięć:** LVGL + obrazy + parser 3mf trzymają dużo RAM-u (sam plik 90 MB); to ten sam proces co `algo_app`? - nie, osobny. [H: wpływ podglądu ekranu na pamięć
   nie zmierzony - brak testu podczas druku.]
6. **Raport do chmury** (`/community/v1/device/status/report`) wysyła numer seryjny/MAC/IP/wersję [D: pola]. Przy włączonym trybie LAN żądania są blokowane
   [D: napis]. Warto opisać w README (prywatność).
7. **Format/rozpakowywanie na USB, `mkfs`** z poziomu ekranu: działa jako root - ryzyko dla użytkownika, który wybierze zły nośnik [W].
8. **Ekran jest klientem Moonrakera z pełnymi uprawnieniami** (JSON-RPC bez tokenu na 127.0.0.1) - nasze moduły mogą go "słuchać" przez ten sam
   WebSocket (`server.connection.identify`), by np. wykrywać stany wcześniej niż przez Fluidd [W].
9. **Pomysł:** moduł "audyt ekranu" (tylko odczyt): skrypt zapisujący, które strony `Page_*` były otwarte w czasie druku [H, wymaga dostępu do logu
   `qidi-client.log` - jest w `/root/qidi-client/`, root-only].

## 6. Czego NIE ustaliłem (uczciwie)

- Nadawcy zdarzeń `ui_assistant_message_update` w 02.04, znaczenia 14 z 15 kodów `QDC_*`, treści ich JSON-ów.
- Pełnej listy wartości `screen_state` poza 0/1 i wszystkich miejsc wywołujących wybudzenie (`FUN_005b6604`) i uśpienie (`FUN_005ba054`).
- Dokładnych warunków pokazania okna AI (noodle/foreign) i przycisków `restart_klipper`/`restart_firmware`.
- Zawartości wiadomości D-Bus (`org.qidi.signal`).
- Nic z tego nie było uruchamiane na drukarce; pytania o zachowanie na żywo to hipotezy.

## 7. Jak odtworzyć (narzędzia)

```
# import (raz): analyzeHeadless <projekt> qc -import in\qidiclient   (JDK 25, GHIDRA_USER_HOME=C:\ghsettings)
# odwołania do tekstów:   -process qidiclient -noanalysis -scriptPath tools\ghscripts -postScript StrRefs.java <fragment>...
# dekompilacja funkcji:   ... -postScript Decomp.java <VA hex bez 0x>...
```
Uwaga (Git Bash): nie podawać argumentów zaczynających się od `/` (np. `/dev/fb0`) - Git zamienia je na ścieżki Windows; użyć `dev/fb0`
albo `MSYS_NO_PATHCONV=1`. Wyniki surowe i lista tekstów: `tools\ghidra_proj_qidiclient\{strings.txt,dec*.txt}` (poza repozytorium).
