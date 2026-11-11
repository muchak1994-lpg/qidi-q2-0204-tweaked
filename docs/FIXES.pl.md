# Co naprawiają moduły

[English](FIXES.md) · **Polski**

Każdy moduł to mała, osobna zmiana względem oryginalnych plików QIDI 01.01.02.04. Wszystkie działają na
drukarce autora; „przetestowane” poniżej oznacza konkretny test fizyczny ponad zwykłe używanie.
Lista: `py tools/build.py --list`; pominięcie modułu: `--skip MODUŁ`.

Źródła w nawiasach: **QIDI #nn** = zgłoszenie w [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/issues),
**Klipper** = przeniesiona poprawka z oficjalnego Klippera.

## Program ekranu

| Moduł | Problem w fabrycznym 02.04 | Co robi moduł |
|---|---|---|
| `screen-program` | Program ekranu potrafi się wysypać przy rzadkich zdarzeniach z MCU/głowicy, a jego historia druków potrafi się rozjechać. | Przebudowuje program ekranu na Twoim komputerze z programu QIDI 02.04 i kodu kolejki z oficjalnego programu QIDI 03.02, dodaje synchronizację historii i wpis wersji. Każdy etap sprawdzany sumą SHA-256. |
| `update-check-off` | Okienko „nowy firmware” namawia do aktualizacji online, która na zawsze zastąpiłaby 02.04. | Wyłącza sprawdzanie aktualizacji (jeden bajt w programie ekranu). |
| `firmware-download-guard` | Drukarka może w tle pobrać paczkę aktualizacji. | Folder pobierania tylko do odczytu (flaga immutable). Cofnięcie: `uninstall`. |
| `dark-mode-light` | Wyłączenie światła w trakcie druku jest cofane przez ekran i wykrywanie spaghetti. | **Dark mode:** wyłączenie światła w trakcie druku = światło i wykrywanie spaghetti wyłączone do końca druku. Dotknięcie ekranu daje chwilowe światło; włączenie światła kończy tryb (wykrywanie wraca po 60 s). Przetestowane. |
| `screen-drying-layout` | Na stronie suszenia czas oraz temperatury stołu i komory nachodzą na listę kroków (angielskie napisy łamią się na dwie linie). | Układa te trzy wartości w jednej linii pod krokami (jedenaście wartości położenia w programie ekranu). Sprawdzone na ekranie. |
| `screen-drying-start-button` | Po restarcie programu ekranu w trakcie suszenia przycisk Start na stronie suszenia zostaje szary (wyłączony) po końcu suszenia. | Po końcu suszenia przycisk Start jest sprawdzany ponownie regułą QIDI (wyłączony tylko wtedy, gdy drukarka jest zajęta). Niezależnie od tego, jak suszenie się kończy (Stop na ekranie, stop z Fluidda, koniec czasu), ekran pokazuje stronę ustawień suszenia; w oryginale Stop na ekranie przenosił na stronę główną. Sprawdzone: restart w trakcie suszenia, koniec suszenia, start z ekranu + Stop na ekranie, start + stop z Fluidda, strzałka wstecz potem. |
| `screen-drying-countdown-roundup` | Pozostały czas suszenia jest zaokrąglany w dół: 5-minutowe suszenie zaczyna od 04min, a przez całą ostatnią minutę pokazuje 00min. | Zaokrąglanie w górę: 05min ... 01min; powyżej godziny pełne godziny w górę. Sprawdzone na ekranie (07min na starcie 7-minutowego suszenia, 05min, 01min). Po upływie czasu moduł suszenia QIDI potrafi wyłączyć się dopiero po kilku minutach; ekran pokazuje wtedy 00min. |
| `screen-drying-autoshow` | Po starcie suszenia z Fluidda ekran zostaje na bieżącej stronie (i ciemny, jeśli spał). | Ekran budzi się jak po jednym dotknięciu (podświetlenie, światło w komorze, potem sam zasypia) i otwiera stronę suszenia. Budzi się też po końcu suszenia. Sprawdzone: start poleceniami Fluidda przy uśpionym ekranie, koniec suszenia przy uśpionym ekranie. |

## Klipper (ruch, grzałki, czujniki)

| Moduł | Problem | Poprawka |
|---|---|---|
| `fuzzy-skin-extrusion` | „Akumulator” ekstrudera QIDI pomija drobne ruchy E i liczy E podwójnie w fuzzy skin w trybie **wytłaczania**: dziury i kropki. | Zostawia wartości E ze slicera bez zmian. Przetestowane wydrukiem fuzzy. |
| `hotend-fan-hysteresis` | Wentylator hotendu przełącza się przy 50 °C bez histerezy, a ponowne grzanie przy pracującym wentylatorze może dać fałszywy alarm. | Dodaje histerezę i zamyka lukę w nadzorze. Przetestowane. |
| `box-heater-keepalive` | Grzałki Boxa QIDI suszące w trakcie druku potrafią zatrzymać Klippera błędem „max_duration” (QIDI #34). | Sygnał podtrzymania wysyłany wcześniej, tylko dla grzałek Boxa; limit bezpieczeństwa bez zmian. Zgłoszona poprawka: 8000+ zmian filamentu bez wyłączenia. |
| `box-fixes` | Ustawienia grzałek Boxa są niewidoczne dla sprawdzania konfiguracji Klippera (QIDI #23). | Rejestruje je jak pozostałe ustawienia grzałek. |
| `mcu-ack-timeout` | Po utracie połączenia z MCU Klipper może się zawiesić zamiast zgłosić błąd. | Czytelny błąd „No communication with MCU” (Klipper). |
| `serialqueue-fixes` | Przy błędzie startu kolejki portu szeregowego nie są zamykane potoki ani zwalniana pamięć. | Poprawne sprzątanie (Klipper). |
| `pressure-advance-history` | Wyciek pamięci przy resecie ekstrudera. | Zwalnia starą historię pressure advance (Klipper). |
| `stepcompress-far` | Krok daleko w przyszłości może zostać zapisany za końcem kolejki kroków. | Klipper PR #7421 (Kevin O'Connor). |
| `tmc-direction-event` | Literówka w nazwie zdarzenia: sterowniki TMC nie dowiadują się o zmianie kierunku silnika. | Poprawna nazwa zdarzenia. |
| `z-offset-persistence` | Tymczasowe offsety Z ustawiane przez makra QIDI mogą zapisać się jak Twój offset Z. | Tymczasowe offsety są oznaczane i nie zapisują się. |
| `save-variables-atomic` | Zanik prądu w trakcie zapisu ustawień może zostawić pusty plik ustawień; Klipper może potem nie wstać. | Zapis do pliku tymczasowego i podmiana (atomowo); identyczna treść nie jest przepisywana. |
| `external-slot16-literal` | Po ładowaniu z zewnętrznej szpuli QIDI zapisuje `slot16`, czego zapis ustawień nie przyjmuje. | Przyjmuje dokładnie tę wartość. |
| `ai-fixes` | Pauza, wznowienie lub anulowanie w trakcie czekania na kontrolę obcych obiektów AI psuje stan druku; komunikaty AI mają popsute znaki. | Komendy działają poprawnie w trakcie kontroli; kodowanie tekstu naprawione. Sama kontrola zostaje taka, jak ją zrobiło QIDI (można ją wyłączyć na ekranie); patrz *AI kamery* niżej. |
| `console-english` | Część komunikatów w konsoli jest po chińsku. | Komunikaty po angielsku. |

## Makra i konfiguracja

Twoja kalibracja (blok `#*# SAVE_CONFIG`) zostaje: w Twoich plikach zmieniane są tylko te linie.

| Moduł | Co się zmienia |
|---|---|
| `idle-timeout-drying` | Czas bezczynności 12 h → 5 min (grzałki off), osobne komunikaty „pauza” / „bezczynność”, silniki off; suszenie w komorze dalej działa. Start suszenia odrzucany, jeśli stół nie jest opuszczony (Z ≥ 190); sygnał dźwiękowy (jak po końcu druku), gdy suszenie skończy się samo. |
| `resume-after-heating` | Po pauzie przepłukanie czeka, aż dysza znów będzie gorąca. |
| `park-rear-right` | Po druku lub zatrzymaniu głowica staje z tyłu po prawej, żeby kamera widziała stół. |
| `external-filament-load-finish` | Po ładowaniu zewnętrznego filamentu: wentylator i grzałka off. |
| `end-guard` | Grzałka komory i wentylatory off na koniec druku i po suszeniu. Przetestowane. |
| `filament-wipe` | Dodatkowe makro przepłukania i wytarcia (`FILAMENT_WIPE`); nie zastępuje makra QIDI. |
| `screws-tilt` | Pomoc przy regulacji śrub stołu. |
| `mcu-temperatures` | Przybliżone temperatury płyty głównej / elektroniki widoczne we Fluiddzie. |

## Moonraker i Fluidd

| Moduł | Co się zmienia |
|---|---|
| `print-cache-protection` | Dwa starty druku w tej samej chwili nie psują już pamięci podręcznej druku; ekran pokazuje informacje o pliku (miniatura, czas). |
| `3mf-cache` | Metadane i miniatury 3MF wyciągane raz na plik, a nie przy każdym zapytaniu. |
| `orca-object-height` | Wysokość obiektu i liczba warstw z metadanych slicera, a nie z ruchów parkowania w G-code. |
| `emmc-info` | Fluidd pokazuje prawdziwe dane eMMC. |
| `gcode-history` | Wielolinijkowa komenda w konsoli zostaje jednym wpisem historii. |
| `timelapse-capture-recovery` | Jedna nieudana klatka timelapse nie zatrzymuje całego timelapse. |
| `fluidd-fixes` | Fluidd: nazwy plików i folderów ze spacjami / znakami specjalnymi, postęp wysyłania/pobierania osobno dla każdego pliku, przyciski działające w pauzie, temperatura SoC, zajętość dysku, rozsądny czas do końca na starcie druku, informacje o serwerze zachowane przy resecie Klippera, ukryte okna przy rozłączeniu. |
| `send-and-print-guard` | Pilnuje, żeby „Upload & Print” we Fluiddzie działał (sprawdza przy starcie i co noc). |
| `fluidd-drying-button` | Pozycja „Suszenie filamentu” na końcu lewego panelu nawigacji Fluidda (telefon i komputer). Otwiera okno z nastawami z ekranu drukarki (15 rodzajów filamentu, temperatura stołu do 100 °C, czas 1-24 h) i wysyła te same polecenia co ekran (`prepare_filament_dry`, `SET_FILAMENT_DRY`). Plik programu Fluidda nie jest zmieniany. Start jest szary, dopóki stół nie jest opuszczony, Stop jest szary, gdy nic się nie suszy. Przetestowane: opuszczenie stołu, start, pozostały czas, stop. |

## System

| Moduł | Co się zmienia |
|---|---|
| `ethernet-mac` | Własny, stały adres MAC Ethernetu od pierwszej chwili startu (QIDI #28). Generowany dla każdej drukarki; działa po restarcie. |
| `klipper-priority` | Klipper dostaje procesor pierwszy (Nice -10). |
| `restart-on-exit` | Klipper i Moonraker wstają same także po zwykłym wyjściu. |
| `legacy-qidilink-cleanup` | Wyłączone stare usługi zdalne QIDILink / FRP. |
| `journal-retention` | **Domyślnie wyłączony** (`--with journal-retention`): logi systemowe 7 dni, do 2 GB, do diagnostyki. |

## AI kamery

> **Co tu znaczy „naprawione”:** w fabrycznym 02.04 AI kamery w ogóle nie działa (programowi brakuje bibliotek,
> a przebieg druku sypie się wokół kontroli). Te moduły sprawiają, że AI **działa jako funkcja**, dokładnie tak,
> jak zaprojektowało je QIDI. **Nie** zmieniają ani nie douczają modelu wykrywania QIDI. To, jak dobrze wykrywa
> (spaghetti, obce obiekty), zależy od modelu QIDI i od wielu warunków – światła, położenia kamery, koloru
> filamentu, powierzchni stołu – i może się różnić od wydruku do wydruku.

| Moduł | Co się zmienia |
|---|---|
| `ai-libraries` | 02.04 ma program AI bez 153 plików bibliotek Pythona, których potrzebuje. Są pobierane z PyPI i Debiana (numpy, onnxruntime, opencv, pycryptodome, psutil, pydantic-core, websockets, chardet, moduły Pythona 3.9), każdy sprawdzany SHA-256. Do tego ustawienie wykrywania MEDIUM8 w programie AI i autostart AI. |

## Profile OrcaSlicer (na komputerze)

Patrz README: profile drukarek „(Tweaked)” z podnoszeniem Z „Normalne” i wyłączaniem wentylatora komory na końcu oraz procesy timelapse `[TL]`.

## Czego nie ma

- Stare parkowanie do timelapse / uniesienie przy zdjęciu / czekanie przy powrocie: wycofane, parkowanie robi OrcaSlicer.
- Wybór narożnika i parkowanie po stronie drukarki: z OrcaSlicer niepotrzebne.
- Poprawki Boxa dodajemy tylko dla problemów, które ludzie faktycznie zgłosili (GitHub / Reddit).
