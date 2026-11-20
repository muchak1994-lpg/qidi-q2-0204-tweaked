# Akcelerometr głowicy: ~390 zamiast 1600 próbek na sekundę

[English](TOOLHEAD_ACCELEROMETER.md)

Firmware głowicy QIDI (THR 02.02.01.08) nie ma poprawki Klippera
[6269dda](https://github.com/Klipper3d/klipper/commit/6269dda56bb7c08263153b18715d08e2d964bcab) (obsługa kolejki
FIFO w LIS2DW). Przez to akcelerometr daje około 390 próbek na sekundę zamiast 1600
([QIDI_Q2 #39](https://github.com/QIDITECH/QIDI_Q2/issues/39)), a kalibracja Input Shapera widzi tylko część drgań.

## Sprawdzenie (tylko odczyt): moduł `thr-accel-check`

Na końcu instalacji instalator mówi o tym błędzie i pyta, czy sprawdzić Twoją drukarkę (Enter = tak, `n` = nie;
`--toolhead yes|no` odpowiada z góry). Sprawdzenie uruchamia raz `TWEAKED_THR_CHECK SAVE=1`, wypisuje wynik i mówi,
czy masz ten błąd. Zapisuje też na PC kopię bootloadera i firmware głowicy (`backups/toolhead-<bootloader>-<firmware>/`),
a z drukarki ją usuwa. Sam możesz to uruchomić w konsoli Fluidd w każdej chwili, np. po aktualizacji QIDI:

- `TWEAKED_THR_CHECK`: mierzy akcelerometr przez 2 s i odczytuje bootloader oraz firmware głowicy przez
  `debug_read` Klippera. To tylko odczyt pamięci, do głowicy nic nie jest zapisywane. Rozpoznaje znane wersje
  i mówi, czy znane narzędzie da radę wgrać poprawkę przy tym zestawie.
- `TWEAKED_THR_CHECK SAVE=1`: dodatkowo zapisuje oba w `config/q2_thr_backup/`, skąd ściągniesz je przez Fluidd.

Komenda nie zadziała w trakcie druku ani pauzy.

## Co znaczy wynik

- **1200 próbek na sekundę lub więcej: błędu nie ma.** Nic nie trzeba robić.
- **Około 390: błąd jest.** Nic nie jest wymagane - drukarka drukuje jak dotąd. Cierpi tylko kalibracja Input Shapera
  (widzi część drgań). Naprawa jest opcjonalna.
- **Cokolwiek innego albo firmware nieznany sprawdzeniu:** nie flashuj. Zachowaj kopię, którą zrobiło sprawdzenie.

## Poprawka jest ręczna i opcjonalna - na własne ryzyko

> **Zastrzeżenie.** Wgranie firmware do głowicy może zostawić ją niesprawną. Robisz to w całości na własne ryzyko;
> projekt, jego autorzy i QIDI nie ponoszą za to odpowiedzialności. To nie jest część instalatora.

Poprawka zmienia firmware głowicy. Ten projekt **nie** robi tego za Ciebie: instalator nigdy nie flashuje głowicy.
Niżej jest opis, jak zrobić to ręcznie, krok po kroku, z komputera z Windows.

### Na czym to sprawdzono

Jedna Q2, 18.11.2026: firmware drukarki 01.01.02.04, bootloader `31f8344d`, oryginalny firmware głowicy `1d34b4b0`
(THR 02.02.01.08), zastąpiony przez `9d2360ba`. Akcelerometr 387 próbek na sekundę przed, 1602 po (1603 według
`TWEAKED_THR_CHECK` 20.11.2026). Po wszystkim ponowna kalibracja Input Shapera.

Uczciwie:

- Komendy flashowania niżej (snapshot, probe, transfer, verify) są tymi, które uruchomiono 18.11.2026, z folderu
  w `/home/qidi`. Ta instrukcja używa zamiast tego `/tmp` (użytkownik `mks` nie może pisać w `/home/qidi`),
  a komend PowerShell nie uruchamiano dokładnie w tej postaci.
- Krok z łatką powtórzono 20.11.2026 na PC, z oryginalnego firmware odczytanego 18.11: wynik jest bajt w bajt tym
  obrazem, który wtedy wgrano (`9d2360ba`).
- Powrót do oryginalnego firmware **nie** był testowany.

### Narzędzia (nie są częścią tego projektu)

- Narzędzie do flashowania z [Valve Oil](https://github.com/thelegendtubaguy/Valve-Oil) autorstwa thelegendtubaguy
  (GPL-3.0), commit `ffb3029` - wersja użyta 18.11. Rozmawia z bootloaderem głowicy, odmawia przy firmware
  i bootloaderach, których nie zna, i ma pod ręką oryginalny firmware, żeby go przywrócić, gdy zapis się nie uda.
- `lis2dw_patch.py` z [rayaanatif/qidi-q2-accelerometer-fix](https://github.com/rayaanatif/qidi-q2-accelerometer-fix)
  (GPL-3.0), commit `0e64967`. Robi poprawiony firmware z **Twojego własnego** oryginału (firmware QIDI nie jest
  tu udostępniany). Sam niczego nie flashuje.

Używaj dokładnie tych wersji: sumy SHA-256 niżej są sprawdzone z GitHubem (20.11.2026). Jeśli suma się różni,
przerwij.

### Zanim zaczniesz

- **Żaden druk nie trwa, grzałki wyłączone, drukarka stoi.** Stabilny prąd, Ty przy drukarce, ok. 30 minut.
- W kroku 9 nie wyłączaj drukarki i nie zamykaj okna PowerShell.
- Jeśli w trakcie zapisu firmware padnie prąd, głowica może zostać bez działającego firmware. Bootloader nie jest
  ruszany, więc naprawa powinna być możliwa, ale nie jest to gwarantowane.
- Narzędzie w tej wersji zna tylko bootloader `31f8344d`. Bootloader `a21a3019` (spotykany po aktualizacji do
  01.01.03.02) zna dopiero Valve Oil od v26.11.15.1 - ta instrukcja go nie obejmuje. Valve Oil jest robiony pod
  QIDI Max 4, a jego autor wspiera Q2 tylko w ograniczonym zakresie.
- Potrzebujesz: Pythona projektu (`py`, tego samego, którego używa `install.bat`), komend `ssh` i `scp` wbudowanych
  w Windows oraz logowania SSH użytkownika drukarki `mks` (tego samego, którego używa instalator).
- W każdej komendzie zamień `PRINTER` na adres drukarki (ekran - ustawienia sieci). Każda komenda `ssh` może
  zapytać o hasło `mks` (dwa razy, gdy pyta też `sudo`). Rób kroki po kolei i porównuj każdy wynik z oczekiwanym.
  **Przy pierwszej niezgodności: przerwij**, uruchom usługi z powrotem (krok 4) i zachowaj wszystko, co zapisałeś.

### 1. Sprawdź, czy masz błąd i właściwy firmware

W konsoli Fluidd: `TWEAKED_THR_CHECK`. Idź dalej tylko wtedy, gdy wypisze wszystkie trzy:

- `Accelerometer: ... samples/s instead of about 1600`, z liczbą około 390 (błąd);
- `A manual, optional fix exists for this bootloader and firmware`;
- `Toolhead firmware: ... QIDI THR 02.02.01.08 (original) (1d34b4b0)` oraz `Bootloader: ... (31f8344d)`.

### 2. Pobierz narzędzia na PC

W PowerShell:

```powershell
mkdir $HOME\q2-thr
cd $HOME\q2-thr
Invoke-WebRequest -Uri https://github.com/thelegendtubaguy/Valve-Oil/archive/ffb302997910b0a02ac8a18b6e23274109d208f2.zip -OutFile flasher.zip
Expand-Archive flasher.zip -DestinationPath .
Rename-Item Valve-Oil-ffb302997910b0a02ac8a18b6e23274109d208f2 flasher
Invoke-WebRequest -Uri https://raw.githubusercontent.com/rayaanatif/qidi-q2-accelerometer-fix/0e649671c9d56b7dc7200c0b8311265821082574/tools/lis2dw_patch.py -OutFile lis2dw_patch.py
Get-FileHash flasher\scripts\flash_thr_firmware.py, flasher\scripts\thr_bootloaders.py, flasher\firmware\max4-thr-lis2dw-fifo-v1.json, lis2dw_patch.py
```

Oczekiwane (Windows pisze wielkimi literami, to bez znaczenia):

```
B68E3032BD22CB441F01648EC20DCFC8FE58CD822F9AE7CB81CCA5679D9C6F0B  flash_thr_firmware.py
1169DA4CC843D6BF67FA0D11ED8A46D4B0D7F69095EA8D46F007141AB0923918  thr_bootloaders.py
8619820DE91730A37BE0E67DD66D38B2671C01B1B7508A032C5EC11F417CD5E1  max4-thr-lis2dw-fifo-v1.json
016C11B1A57FC9F01914A8B04EB61CFEE642D3DEC09E678C5A29D935F7AE9DF4  lis2dw_patch.py
```

Wszystkie dalsze komendy na PC uruchamiaj w tym folderze (`cd $HOME\q2-thr`).

### 3. Skopiuj narzędzie do flashowania na drukarkę

```powershell
ssh mks@PRINTER 'mkdir -p /tmp/q2_thr_tools'
scp -r flasher\scripts flasher\firmware mks@PRINTER:/tmp/q2_thr_tools/
ssh mks@PRINTER 'cd /tmp/q2_thr_tools && sha256sum scripts/*.py firmware/*.json'
```

Drukarka musi wypisać te same trzy sumy co w kroku 2 (małymi literami).

### 4. Zatrzymaj Klippera i program ekranu

Korzystają z linii szeregowej głowicy; narzędzie odmówi pracy, dopóki działają. Ekran i Fluidd zgasną.

```powershell
ssh -t mks@PRINTER 'sudo systemctl stop qidi-client.service && sudo systemctl stop klipper.service; systemctl is-active klipper.service qidi-client.service'
```

Oczekiwane na końcu: dwa razy `inactive`. **Żeby uruchomić je z powrotem** (w każdej chwili, gdy przerywasz,
i w kroku 11):

```powershell
ssh -t mks@PRINTER 'sudo systemctl start klipper.service; sleep 5; sudo systemctl start qidi-client.service; systemctl is-active klipper.service qidi-client.service'
```

### 5. Odczytaj oryginalny firmware (tylko odczyt)

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-before --printer-idle-confirmed; echo EXIT_CODE=$?; sudo chown -R mks dist'
```

Oczekiwane: `"application_sha256": "1d34b4b0..."`, `"bootloader_sha256": "31f8344d..."` i `EXIT_CODE=0`.
`EXIT_CODE=3` oznacza bootloader, którego to narzędzie nie zna: przerwij.

### 6. Skopiuj tę kopię na PC

```powershell
scp -r mks@PRINTER:/tmp/q2_thr_tools/dist/thr-before .
Get-FileHash thr-before\application.bin, thr-before\bootloader.bin
```

Oczekiwane: `1D34B4B0...` i `31F8344D...`. Jeśli sprawdzenie uruchomił instalator, ten sam `application.bin` jest
też w projekcie w `backups\toolhead-31f8344d-1d34b4b0\` - jego suma musi być taka sama. Zachowaj `thr-before`:
to Twoja droga powrotu.

### 7. Sprawdź połączenie z bootloaderem (nic nie kasuje)

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py probe --backup-dir dist/thr-before --reset --printer-idle-confirmed; echo EXIT_CODE=$?'
```

Oczekiwane: `"bootloader_reply": "0102"`, `"erase_requested": false`, `EXIT_CODE=0`. Odczekaj 15 sekund i sprawdź,
że nic się nie zmieniło:

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-after-probe --printer-idle-confirmed; echo EXIT_CODE=$?'
```

Oczekiwane: te same dwie sumy co w kroku 5 i `EXIT_CODE=0`.

### 8. Zrób poprawiony firmware ze swojego oryginału

```powershell
py lis2dw_patch.py patch thr-before\application.bin QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin
Get-FileHash QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin
```

Oczekiwane: `template B at 0xbfa` i suma `9D2360BA47EBD720DBEF07A0A4EBAF26004360BCA090997D7B4A118C41460AC9`.
Niczego innego narzędzie do flashowania nie przyjmie. Skopiuj go na drukarkę i sprawdź tam:

```powershell
scp QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin mks@PRINTER:/tmp/q2_thr_tools/dist/
ssh mks@PRINTER 'sha256sum /tmp/q2_thr_tools/dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin'
```

### 9. Wgraj go - jedyny krok, który zmienia głowicę

Zostań przy drukarce, nie ruszaj zasilania, nie zamykaj okna do końca.

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py transfer --image dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin --backup-dir dist/thr-before --reset --recover-to-stock --printer-idle-confirmed --confirm-write; echo EXIT_CODE=$?'
```

- `EXIT_CODE=0`: głowica przyjęła poprawiony firmware. Idź dalej.
- `EXIT_CODE=4`: zapis się nie udał i narzędzie przywróciło oryginał. Zrób krok 10 z
  `--image dist/thr-before/application.bin`, żeby to potwierdzić, potem krok 11.
- `EXIT_CODE=1` albo `5`: **nie powtarzaj i nie uruchamiaj usług.** Zostaw drukarkę włączoną, zachowaj okno
  i jego treść, poproś o pomoc (zgłoszenie w Valve Oil albo accelerometer-fix, z `thr-before` i tym wynikiem).

### 10. Odczytaj z powrotem i sprawdź

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sleep 15 && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-after --printer-idle-confirmed; echo SNAP_EXIT=$?; sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py verify --image dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin --backup-dir dist/thr-after --original-backup-dir dist/thr-before; echo VERIFY_EXIT=$?; sudo chown -R mks dist'
scp -r mks@PRINTER:/tmp/q2_thr_tools/dist/thr-after .
```

Oczekiwane: `"verified": true`, suma firmware `9d2360ba...`, suma bootloadera bez zmian (`31f8344d...`),
`SNAP_EXIT=0` i `VERIFY_EXIT=0`.

### 11. Uruchom drukarkę z powrotem

Komenda „żeby uruchomić je z powrotem” z kroku 4. Oczekiwane: dwa razy `active`, a Fluidd pokazuje Klippera
gotowego, bez błędów. Poprawka zostaje po wyłączeniu drukarki.

### 12. Zmierz jeszcze raz

W konsoli Fluidd: `TWEAKED_THR_CHECK`. Oczekiwane: około 1600 próbek na sekundę i `Toolhead firmware: ... with the
LIS2DW FIFO fix (accelerometer-fix v1) (9d2360ba)`. Potem `SHAPER_CALIBRATE` (drukarka bazuje osie i przez kilka
minut głośno wibruje) i `SAVE_CONFIG`: wcześniejsze wartości Input Shapera wyliczyły się z zepsutej częstotliwości.

### 13. Posprzątaj drukarkę

Kopie są na PC (`thr-before`, `thr-after`), więc na drukarce nic nie musi zostać:

```powershell
ssh -t mks@PRINTER 'sudo rm -rf /tmp/q2_thr_tools'
```

`/tmp` w Q2 leży na zwykłym dysku, więc restart go nie czyści. Folder `$HOME\q2-thr` zachowaj na PC.

### Powrót do oryginalnego firmware (nie testowany)

To samo narzędzie przyjmuje oryginał zapisany w kroku 6. Skopiuj z powrotem narzędzie i kopię (krok 3, potem
`scp -r thr-before mks@PRINTER:/tmp/q2_thr_tools/dist/`), zatrzymaj usługi (krok 4), a potem:

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py transfer --image dist/thr-before/application.bin --backup-dir dist/thr-before --reset --recover-to-stock --printer-idle-confirmed --confirm-write; echo EXIT_CODE=$?'
```

Potem krok 10 z `--image dist/thr-before/application.bin` i nowym `--output-dir` (np. `dist/thr-back`), krok 11
i krok 13. Oficjalna paczka 01.01.02.04 zawiera ten sam oryginalny firmware
(`QD_Q2_THR_02.02.01.08_20260303.bin`, `1d34b4b0`); czy ponowne wgranie tej aktualizacji przepisuje głowicę,
nie było testowane.

### Po aktualizacji QIDI

Aktualizacja z nowym firmware głowicy nadpisuje poprawkę. Po niej uruchom znowu `TWEAKED_THR_CHECK`; przy innym
bootloaderze albo firmware nie korzystaj z tej instrukcji.
