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

Poprawka zmienia firmware głowicy. Ten projekt **nie** robi tego za Ciebie. Zrobiono to na jednej Q2 18.11.2026
według [rayaanatif/qidi-q2-accelerometer-fix](https://github.com/rayaanatif/qidi-q2-accelerometer-fix):

- firmware drukarki 01.01.02.04, bootloader `31f8344d`;
- oryginalny firmware `1d34b4b0`, po poprawce `9d2360ba`;
- akcelerometr 387 Hz przed, 1602 Hz po;
- po wszystkim ponowna kalibracja Input Shapera.

Rób to krok po kroku według tamtej instrukcji. Zanim zaczniesz:

- Jeśli w trakcie zapisu firmware padnie prąd, głowica może zostać bez działającego firmware. Bootloader nie jest
  ruszany, więc naprawa powinna być możliwa, ale nie jest to gwarantowane.
- Narzędzie przypięte w instrukcji zna tylko bootloader `31f8344d`. Bootloader `a21a3019` (spotykany po
  aktualizacji do 01.01.03.02) zna dopiero [Valve Oil](https://github.com/thelegendtubaguy/Valve-Oil) od
  v26.11.15.1. Valve Oil jest robiony pod QIDI Max 4, a jego autor wspiera Q2 tylko w ograniczonym zakresie.
- Aktualizacja QIDI z nowym firmware głowicy nadpisuje poprawkę. Po takiej aktualizacji sprawdź jeszcze raz.
- Po poprawce zrób ponownie `SHAPER_CALIBRATE`, potem `SAVE_CONFIG`. Wcześniejsze wartości wyliczyły się z
  zepsutej częstotliwości próbkowania.
