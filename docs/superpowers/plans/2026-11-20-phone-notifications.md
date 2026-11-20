# Powiadomienia na telefon (ntfy) - plan wykonania

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opt-in moduł, który wysyła z drukarki powiadomienia ntfy (start, 25/50/75%, pauza, koniec, błędy) i przyjmuje z telefonu komendy "Wznów", "Anuluj" i "Pokaż timelapse".

**Architecture:** Zegar w Klipperze (`delayed_gcode` co 15 s) wykrywa zdarzenia i woła skrypt `sh` + `curl` przez `gcode_shell_command`. Błędy/shutdown wysyła Moonraker (`[notifier]`, bo Klipper w shutdown nic nie zrobi). Usługa systemd z pętlą `curl -sN .../raw` słucha drugiego kanału i wywołuje lokalne API Moonrakera.

**Tech Stack:** POSIX `sh`, `curl`, Klipper Jinja, Moonraker `notifier` + `apprise 1.3.0` (jest na drukarce), Python 3 (instalator, testy), WSL/Linux do testów skryptów `sh`.

**Spec:** `docs/superpowers/specs/2026-11-20-phone-notifications-design.md`

## Global Constraints

- Domyślnie **wyłączone**; instalator pyta na końcu (`--notify ask|yes|no`), jak `--tailscale`.
- Nazwy komend/makr Klippera: prefiks `_TWEAKED_`/`TWEAKED_`, nigdy litera+cyfra na początku (pilnuje `tests/test_command_names.py`).
- Nazwy kanałów i adres serwera **nie trafiają** do repozytorium, logów instalatora ani wydruku testów (jak hasła). Konfiguracja tylko w `/home/qidi/printer_data/config/q2_notify.conf` (tryb 600, właściciel `qidi`) i w kopii na PC (`backups/`).
- Zasoby drukarki: bez procesu Pythona w pętli; słuchacz = `sh` + `curl`; zegar Klippera bez zapisów na dysk.
- Komendy z telefonu: tylko `resume`, `cancel` (tylko w stanie `paused`) i `video <nazwa>`; wszystko inne jest ignorowane.
- Wiadomości po angielsku. Czas "ile zostało": wzór ekranu `minęło * (100-P) / P`, P = `display_status.progress*100`.
- Nic się nie wysyła na GitHub bez "wyślij" właściciela.

## Review Focus

1. Nazwa pliku z spacją, polską literą, `|`, cudzysłowem (np. `Wieża 12mm "v2".gcode.3mf`): wiadomość i komenda `video` nie mogą się rozjechać ani wstrzyknąć polecenia.
2. Brak internetu / `ntfy.sh` nie odpowiada: `curl` z limitem czasu w tle, Klipper i druk nie mogą czekać.
3. Restart Klippera w trakcie druku lub wznowienie po zaniku prądu: kamienie 25/50/75% już minięte nie wysyłają się ponownie.
4. Ta sama komenda `resume` dostarczona dwa razy (ponowne połączenie słuchacza): drugi raz nic nie robi.
5. `video ../../etc/passwd`, `video /x`, `video a.mp4;reboot`: odrzucone, bez wywołania czegokolwiek.
6. Pauza z `M0`/`M25` w G-code, z ekranu, z Fluidd i z AI: każda daje wiadomość z właściwym powodem i **żadna nie rusza grzania** (stół/komora zostają, jak w stocku).

---

### Task 1: Konfiguracja i skrypt wysyłający

**Files:**
- Create: `modules/phone-notifications/files/q2_notify_send.sh`
- Test: `tests/test_notify_send.py` (uruchamia skrypt przez `sh`, pomija się na Windowsie jak `test_linked_home`)

**Interfaces:**
- Produces: plik konfiguracji `KEY=value` (`NTFY_SERVER`, `EVENTS_TOPIC`, `CMD_TOPIC`, `ENABLED`), ścieżka z `Q2_NOTIFY_CONF` (domyślnie `/home/qidi/printer_data/config/q2_notify.conf`), `curl` z `Q2_NOTIFY_CURL` (domyślnie `curl`).
- Produces: `q2_notify_send.sh <title> <message> [--prio N] [--tags T] [--click URL] [--attach FILE] [--action LABEL=BODY]...` (przycisk = `http, LABEL, $NTFY_SERVER/$CMD_TOPIC, method=POST, body=BODY, clear=true`).
- Produces: `q2_notify_send.sh --tsv "<title>	<message>	<prio>	<tags>	<click>	<attach>	<action1>	<action2>"` - to samo, ale jako jeden argument z polami rozdzielonymi tabulatorem (puste pole = brak). Tak woła go Klipper (Task 2): `gcode_shell_command` rozbija linię po spacjach, więc spacje i `|` w nazwie pliku musiałyby się rozjechać.

- [ ] **Step 1: test `test_publishes_to_events_topic_with_headers`** - sztuczny `curl` zapisuje argumenty do pliku; asercje: URL = `NTFY_SERVER/EVENTS_TOPIC`, nagłówki `Title`, `Priority`, `Tags`, treść wiadomości w `-d`.
- [ ] **Step 2: test `test_action_buttons_header`** - dwie `--action` dają jeden nagłówek `Actions: http, Resume, <url>, method=POST, body=resume, clear=true; http, Cancel, ...`. Składnię nagłówka potwierdzić w dokumentacji ntfy (WebFetch) i ewentualnie poprawić test.
- [ ] **Step 3: test `test_attach_uses_put_with_filename`** - `--attach plik.jpg` wysyła plik (`-T`, nagłówek `Filename`).
- [ ] **Step 4: test `test_tsv_mode_matches_positional_mode`** (te same nagłówki i treść, także dla tytułu ze spacją i `|`) oraz **`test_disabled_or_missing_conf_sends_nothing`** (`ENABLED=0` lub brak pliku: kod wyjścia 0, `curl` niewywołany) oraz **`test_title_with_quotes_pipe_and_unicode_is_passed_intact`** (Review Focus 1).
- [ ] **Step 5: test `test_curl_has_max_time`** - w argumentach jest `--max-time 15` (Review Focus 2).
- [ ] **Step 6: Implement `q2_notify_send.sh`** - czyta konfigurację bez `source`-owania obcego kodu (parsowanie `KEY=value` linia po linii), buduje wywołanie `curl -sS --max-time 15`. Uruchom wszystkie testy z kroków 1-5, mają przejść (`wsl.exe -e python3 tests/test_notify_send.py`).
- [ ] **Step 7: Commit** `git add modules/phone-notifications tests/test_notify_send.py && git commit -m "phone-notifications: sender script"`

### Task 2: Zegar w Klipperze i powiadomienie o pauzie z powodem (PRIORYTET)

Decyzja właściciela 2026-11-20: pauza jest pierwszym i najważniejszym powiadomieniem. Pauza w stocku QIDI wyłącza dyszę (`M104 S0`),
a stół i komorę zostawia grzane; tego **nie zmieniamy** (PR QIDITECH/QIDI_Q2#11 odrzucony dla projektu), liczy się uratowanie wydruku.

**Files:**
- Create: `modules/phone-notifications/files/q2_notify.cfg` (trafia do `klipper-macros-qd/`, wczytywane przez wildcard include)
- Modify: `modules/phone-notifications/module.json` (edycje makr `M0` i `M25` w `gcode_macro.cfg`, wzór: `modules/z-offset-persistence`, `base: printer`)
- Test: `tests/test_notify_macros.py` (renderuje szablony `jinja2` jak Klipper: `{%`/`%}` blokowe, `{`/`}` zmienne; pomija się, gdy `jinja2` nie jest zainstalowane)

**Interfaces:**
- Consumes: `q2_notify_send.sh --tsv` z Task 1.
- Produces: `[gcode_shell_command q2_notify]` (`command: sh /home/qidi/q2-notify/q2_notify_send.sh`), `[gcode_macro _TWEAKED_NOTIFY]` ze stanem (`variable_paused_sent: 0`, `variable_reason: ''`, `variable_next: 25`, `variable_started: 0`, `variable_tl_on: 0`), `[delayed_gcode _TWEAKED_NOTIFY_TICK]` (`initial_duration: 15`, wywołuje samo siebie co 15 s). Makra `M0`/`M25` ustawiają `reason` na `M0`/`M25` przed wywołaniem `PAUSE`.
- Powody pauzy i ich pierwszeństwo: `AI spaghetti` (zmienna `qdc_ai_error_code` zaczyna się od `noodle=`), `AI foreign object` (`foreign=`), `filament runout` (czujnik filamentu pokazuje brak), `M0/M25 in G-code` (ustawione przez edytowane makra), `manual` (reszta).
- Pauza wysyła `Print paused: <powód>` z przyciskami `resume`/`cancel` i zdjęciem z `http://127.0.0.1/webcam/?action=snapshot` (`/tmp/q2_notify_snap.jpg`, usuwane po wysłaniu; błąd pobrania zdjęcia nie blokuje wiadomości).

- [ ] **Step 1: recon na drukarce (zapisać w komentarzu `q2_notify.cfg`)** - nazwa czujnika filamentu (`[filament_switch_sensor ...]` w `printer.cfg`); czy po pauzie AI `qdc_ai_error_code` ma `noodle=`/`foreign=`; czy `PAUSE` z ekranu i z Fluidd idzie przez to samo makro `PAUSE` (w stocku `M0` i `M25` wołają `PAUSE`).
- [ ] **Step 2: test `test_pause_reason_each_of_five`** - pięć zestawów danych wejściowych (AI makaron, AI obcy przedmiot, brak filamentu, `M0`/`M25`, ręczna), pięć tekstów; test `test_pause_sent_once_and_again_after_resume`.
- [ ] **Step 3: test `test_pause_does_not_touch_heaters`** - wyrenderowany wynik ticka nie zawiera `M104`, `M140`, `M141` ani `SET_HEATER_TEMPERATURE`.
- [ ] **Step 4: test `test_eta_matches_printer_screen`** - `elapsed=2434`, `P=57` -> `"30 min"` (ekran: -30m o 09:45:09 na druku 1h1m); makro `_TWEAKED_NOTIFY_ETA(elapsed, P)` zwraca tekst `"<H>h <M>m"` lub `"<M> min"`.
- [ ] **Step 5: Implement `q2_notify.cfg` i edycje `M0`/`M25`** - argumenty skryptu jako jedna linia z polami rozdzielonymi tabulatorem (nazwa pliku może zawierać spację i `|`, tabulatora nie). Testy z kroków 2-4 mają przejść (`wsl.exe -e python3 tests/test_notify_macros.py`).
- [ ] **Step 6: Commit** `git commit -m "phone-notifications: klipper tick and pause notification with reason"`

### Task 3: Start, 25/50/75%, koniec, anulowanie

**Files:**
- Modify: `modules/phone-notifications/files/q2_notify.cfg`
- Test: `tests/test_notify_macros.py`

**Interfaces:**
- Consumes: tick i `_TWEAKED_NOTIFY_ETA` z Task 2.
- Produces: wiadomości `Print started` (pierwsza warstwa), `Print 25%/50%/75%: elapsed <T>, done at <HH:MM>, <T> left`, `Print finished`, `Print cancelled`.

- [ ] **Step 1: test `test_start_sent_once_at_first_layer`** - `print_stats.state='printing'`, `info.current_layer=1` -> jedno `RUN_SHELL_COMMAND CMD=q2_notify` z `Print started`; `current_layer=0` (nagrzewanie) -> nic; drugi tick -> nic.
- [ ] **Step 2: testy `test_milestones_25_50_75_once_each` i `test_milestones_already_passed_are_not_resent`** (pierwszy tick widzi P=60 -> `next` ustawione na 75, bez wysyłania 25 i 50; Review Focus 3).
- [ ] **Step 3: test `test_complete_and_cancelled`** - `state='complete'` -> `Print finished`; `'cancelled'` -> `Print cancelled`, bez przycisku timelapse; wysłane raz, stan zerowany po wyjściu ze stanu druku.
- [ ] **Step 4: Implement w `q2_notify.cfg`, testy, Commit.**

### Task 4: Słuchacz komend

**Files:**
- Create: `modules/phone-notifications/files/q2_notify_listen.sh`, `modules/phone-notifications/files/q2-notify-listen.service`
- Test: `tests/test_notify_listen.py` (sztuczny `curl`, sztuczny strumień linii; pomija się na Windowsie)

**Interfaces:**
- Consumes: konfiguracja z Task 1.
- Produces: `q2_notify_listen.sh` czyta linie z `curl -sN $NTFY_SERVER/$CMD_TOPIC/raw`, obsługuje `resume`, `cancel` (tylko gdy `print_stats.state` = `paused`; `POST http://127.0.0.1:7125/printer/print/resume|cancel`) i `video <nazwa>` (wywołuje `q2_notify_video.sh`). Po zerwaniu połączenia ponawia po 10 s. Usługa `Restart=always`, `Nice=10`.

- [ ] **Step 1: testy** `test_resume_only_when_paused`, `test_resume_twice_second_is_noop` (Review Focus 4), `test_unknown_and_malformed_lines_ignored`, `test_video_rejects_path_tricks` (`../../etc/passwd`, `/x`, `a.mp4;reboot`, spacja i `$()` - Review Focus 5), `test_reconnects_after_stream_ends`.
- [ ] **Step 2: Implement** skrypt i plik usługi; walidacja nazwy `video` wzorcem `^[A-Za-z0-9._ -]+$` (bez `/`, `..`).
- [ ] **Step 3: Uruchom testy, Commit.**

### Task 5: Film timelapse po kliknięciu

**Files:**
- Create: `modules/phone-notifications/files/q2_notify_video.sh`
- Modify: `modules/phone-notifications/files/q2_notify.cfg` (przycisk `video <nazwa pliku wydruku>` przy "Print finished", tylko gdy `tl_on`)
- Test: `tests/test_notify_video.py`, `tests/test_notify_macros.py`

**Interfaces:**
- Produces: `q2_notify_video.sh <nazwa wydruku>` szuka w `Q2_TIMELAPSE_DIR` (domyślnie `/home/qidi/printer_data/timelapse`) najnowszego `timelapse_<nazwa wydruku>_*.mp4`. Gotowy: wysyła `.mp4` (i `.jpg` obok) jako załącznik. Brak: wysyła `Timelapse is rendering, video follows`, sprawdza co `Q2_VIDEO_POLL` s (domyślnie 15) do `Q2_VIDEO_TIMEOUT` (domyślnie 600), potem `Timelapse not ready`.
- `tl_on` jest ustawiane w ticku przy pierwszej warstwie z `printer['gcode_macro TIMELAPSE_TAKE_FRAME'].enable`.

- [ ] **Step 1: testy** `test_ready_video_is_attached`, `test_waits_then_sends_when_file_appears`, `test_timeout_sends_not_ready`, `test_picks_newest_matching_file`, `test_finish_message_has_button_only_when_timelapse_on` (w testach makr).
- [ ] **Step 2: Implement; Step 3: testy, Commit.**

### Task 6: Błędy i shutdown (Moonraker) oraz zanik prądu

**Files:**
- Create: `modules/phone-notifications/files/q2_notify_moonraker.conf` (szablon `[notifier q2_ntfy]`, `events: error`, `url: ntfy://...` wypełnia instalator)
- Modify: `modules/phone-notifications/files/q2_notify.cfg` (start Klippera po zaniku prądu)
- Test: `tests/test_notify_setup.py` (Task 7), `tests/test_notify_macros.py`

**Interfaces:**
- Produces: instalator dopisuje do `moonraker.conf` linię `[include q2_notify_moonraker.conf]` (wzór: edycja `trusted_clients` w `tools/tailscale_setup.py`, plik niezmieniany, gdy linia już jest); komunikat `Power loss detected, print can be resumed` po starcie Klippera.

- [ ] **Step 1: recon** - jak QIDI oznacza wznowienie po zaniku prądu (zmienna w `saved_variables.cfg` lub plik; zapisać w komentarzu `q2_notify.cfg`), i czy Moonraker na drukarce czyta `[include]` w `moonraker.conf`.
- [ ] **Step 2: test `test_power_loss_message_once_after_start`** w testach makr.
- [ ] **Step 3: Implement; Commit.**

### Task 7: Instalator i moduł

**Files:**
- Create: `tools/notify_setup.py`, `modules/phone-notifications/module.json`, `tests/test_notify_setup.py`
- Modify: `tools/install.py` (opcja `--notify ask|yes|no`, wywołanie po Tailscale i Orce)

**Interfaces:**
- Produces: `notify_offer(p, mode="ask", read=input, secrets_fn=secrets.token_urlsafe) -> bool` (tworzy konfigurację z dwoma losowymi kanałami, serwer domyślnie `https://ntfy.sh`, pyta o własny; pokazuje kanały do wpisania w aplikacji; wysyła wiadomość testową; zapis do `backups/` z kopią konfiguracji). `remove_notify(p)` dla `uninstall` (usuwa konfigurację, wyłącza usługę, usuwa linię `[include ...]`).

- [ ] **Step 1: testy** (wzór `tests/test_tailscale.py`): `test_mode_no_does_nothing`, `test_topics_are_random_and_not_in_log_output`, `test_config_written_with_mode_600`, `test_include_line_added_once`, `test_uninstall_removes_everything_it_added`, `test_custom_server_is_used`.
- [ ] **Step 2: Implement `tools/notify_setup.py`, `module.json`** (pliki z Task 1-6; akcje `daemon-reload`, `enable --now q2-notify-listen.service`, restart `klipper` i `moonraker`), **wiring w `install.py`**.
- [ ] **Step 3:** `python tools/build.py --update-lock`, wszystkie `tests/test_*.py` na Windows i w WSL (`for t in tests/test_*.py; do python3 $t; done`) mają przejść.
- [ ] **Step 4: Commit.**

### Task 8: Dokumentacja i test na drukarce (z właścicielem)

**Files:**
- Modify: `docs/FIXES.md`, `docs/FIXES.pl.md` (wiersz `phone-notifications`), `CHANGELOG.md` (Unreleased), `README.md` (jedna linia o opcji)

- [ ] **Step 1:** dopisać wiersz i wpis (tekst: moduł opcjonalny; wiadomości przez serwer ntfy; kto zna kanał komend, może wznowić/anulować druk).
- [ ] **Step 2 (tylko za zgodą, nie w trakcie druku):** `py tools/install.py install --host <adres> --notify yes`, wiadomość testowa dociera na telefon. Zapisać wynik.
- [ ] **Step 3 (właściciel przy drukarce 07:00-20:00, pusta płyta, filament):** mały wydruk z timelapse: start po 1. warstwie, 25/50/75%, **pauza 1-2 h** z wiadomością o powodzie, wznowienie przyciskiem "Wznów" z telefonu, koniec z przyciskiem "Pokaż timelapse", film dociera. Ocenić łączenie warstw po długiej pauzie (stół i komora grzane, dysza wyłączona).
- [ ] **Step 4 (przy tym samym teście):** sprawdzić, czy pierwsze czyszczenie dyszy w `RESUME_PRINT` (przed `M109`, na zimnej dyszy) czemuś szkodzi: obserwować `MOVE_TO_TRASH` i pięć przejazdów X 115/98 na zimnej dyszy. Z odczytu stockowego kodu 02.04 wynika, że kolejność jest taka (czyszczenie, potem `M109`, potem wyciśnięcie `E150`), więc kolejność jest potwierdzona, do sprawdzenia zostają skutki. Wynik i odchyłki od ekranu poniżej 50% zapisać w `CLAUDE.local.md`.
- [ ] **Step 5: Commit** (push dopiero po "wyślij").
