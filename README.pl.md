# QIDI Q2 02.04 Tweaked

[English](README.md) · **Polski**

Społecznościowe poprawki i drobne ulepszenia dla drukarki 3D **QIDI Q2** z firmware **01.01.02.04** — i tylko z tą wersją.

> **Projekt nieoficjalny.** Niezwiązany z QIDI Technology, nieautoryzowany i niewspierany przez QIDI. Używasz na własne ryzyko. Miej pod ręką oficjalną paczkę firmware, żeby zawsze móc wrócić do wersji fabrycznej.

> **Stan: 1.2.0.** Wszystkie moduły budują się z oficjalnych paczek i zgadzają co do bajtu z przetestowaną drukarką; każdy moduł został zainstalowany (i zaktualizowany) tym instalatorem na drukarce autora, instalator jest testowany bez drukarki, na symulowanej drukarce, a pełna instalacja przeszła na świeżo zreflashowanej drukarce (14.11.2026). Zobacz [docs/ROADMAP.md](docs/ROADMAP.md).

## Co naprawia

71 małych modułów: program ekranu (kolejka druku z 03.02, bez okienka aktualizacji, dark mode światła,
poprawki suszenia filamentu), poprawki Klippera (powtórzenia pomiaru siatki, bazowanie, fuzzy skin, wentylator
hotendu, grzałki i próg wentylatorów Boxa QIDI, błędy MCU, bezpieczny zapis ustawień i inne, kilka z oficjalnego
Klippera), makra (strażnik bazowania Z, temperatura ładowania po cieplejszym filamencie, suszenie z Fluidda),
poprawki Moonrakera i Fluidda, stały MAC Ethernetu oraz brakujące biblioteki AI kamery.
**Pełna lista z problemem, który rozwiązuje każdy moduł: [docs/FIXES.pl.md](docs/FIXES.pl.md).**

## Zasady

- **Tylko 02.04.** Każda zmiana jest sprawdzana względem dokładnych plików 01.01.02.04 (SHA-256). Na innej wersji instalator odmawia działania.
- **Aktualizacje firmware zostają zablokowane.** Poprawki są robione pod 02.04; automatyczna aktualizacja po cichu by je zastąpiła. Blokada jest częścią paczki, a nie opcją.
- **W repozytorium nie ma plików QIDI** (tylko krótkie linijki, które nasze zmiany zastępują). Instalator sam pobiera oficjalną paczkę 01.01.02.04 z publicznego serwera QIDI, sprawdza jej sumę kontrolną i nanosi zmiany na Twoim komputerze.
- **Kopie na komputerze, na drukarce nic po nas nie zostaje.** Przed każdą zmianą oryginalne pliki drukarki są zapisywane na Twoim komputerze, więc każdy moduł da się cofnąć. Pliki tymczasowe na drukarce są usuwane po instalacji.
- **Dodajemy, nigdy nie podmieniamy — także na komputerze.** Profile OrcaSlicer są dodawane obok Twoich; profil, który już masz, nigdy nie zostaje nadpisany.
- **Bezpieczeństwo sieci jest po Twojej stronie.** Trzymaj drukarkę w zaufanej sieci, nie wystawiaj jej do internetu.

## Wymagania

- QIDI Q2 z firmware **01.01.02.04**, widoczna w sieci lokalnej.
- Komputer (Windows, macOS lub Linux) z **Pythonem 3.9 lub nowszym** (na Windows: z python.org lub Microsoft Store; działa polecenie `py`).
- Do profili: OrcaSlicer, w której choć raz dodano drukarkę QIDI Q2.

## Zanim zaczniesz

> **Nie używaj aktualizacji online z ekranu.** Wgrywa najnowszy firmware QIDI, którego nie da się cofnąć –
> stracisz drogę powrotu do 01.01.02.04 i ten projekt. Aktualizuj tylko offline (pendrive) i tylko do 01.01.02.04.
> Zobacz [docs/RECOVERY.pl.md](docs/RECOVERY.pl.md).

- Drukarka nic nie robi: nie drukuje, nie jest w pauzie, grzałki wyłączone.
- Znasz jej adres IP (ekran → ustawienia sieci) i hasło SSH użytkownika `mks`.
- Na komputerze otwórz terminal w tym folderze (Windows: w Eksploratorze wpisz `cmd` w pasku adresu i naciśnij Enter).

## Instalacja

**Windows, najprościej:** kliknij dwa razy `install.bat`. Zapyta o adres IP drukarki i przejdzie przez pięć
kroków poniżej, zatrzymując się przy pierwszym problemie. Hasło SSH wpiszesz kilka razy; nigdzie nie jest zapisywane.

**Ręcznie** (dowolny system):

```
py -m pip install -r requirements.txt          (raz: paramiko do SSH, capstone do budowy ekranu)
py tools/firmware.py fetch                     (pobiera i sprawdza oficjalną paczkę 02.04)
py tools/printer.py check --host IP_DRUKARKI   (tylko odczyt: czy to 02.04, co jest zmienione)
py tools/install.py plan --host IP_DRUKARKI    (tylko odczyt: co się zmieni)
py tools/install.py install --host IP_DRUKARKI (kopia na komputerze, potem instalacja; pyta o „yes”)
```

- Pierwsze budowanie pobiera też oficjalną paczkę QIDI 01.01.03.02 (ok. 245 MB; przenosimy z niej tylko kod
  kolejki druku) oraz biblioteki AI z PyPI i Debiana (ok. 100 MB). Wszystko jest sprawdzane sumami SHA-256.
- Instalator zatrzymuje się **zanim cokolwiek zmieni**, jeśli firmware to nie 01.01.02.04, drukarka jest zajęta
  albo któryś plik nie jest ani oryginałem QIDI, ani naszą wersją.
- Twoja kalibracja w `printer.cfg` zostaje: zmieniane są tylko nasze linie.
- Kopia trafia do `backups/` na komputerze. Zachowaj ten folder.
- Moduł można pominąć opcją `--skip MODUŁ` (lista: `py tools/build.py --list`).
- Poprawka adresu MAC działa po następnym restarcie drukarki.

### Sprawdzenie akcelerometru głowicy (tylko odczyt)

Firmware głowicy Q2 od QIDI ma znany błąd: akcelerometr daje około 390 próbek na sekundę zamiast 1600
([QIDI_Q2 #39](https://github.com/QIDITECH/QIDI_Q2/issues/39)), a większość drukarek Q2 go ma. Na końcu instalacji
instalator pyta, czy sprawdzić Twoją (`--toolhead yes|no` odpowiada z góry). Sprawdzenie tylko czyta pamięć głowicy,
mówi, czy masz ten błąd i co zalecamy, i zapisuje na PC kopię firmware głowicy. Nic nie jest flashowane: opcjonalna
ręczna poprawka jest opisana w [docs/TOOLHEAD_ACCELEROMETER.pl.md](docs/TOOLHEAD_ACCELEROMETER.pl.md) i robisz ją na
własne ryzyko.

### Dostęp zdalny (opcjonalny Tailscale)

Chmura QIDI nie obsługuje drukarek na 02.04, więc aplikacja QIDI nie połączy się z drukarką spoza domu.
Na końcu instalacji instalator proponuje **Tailscale** (darmowy, tailscale.com): Fluidd, wysyłanie z OrcaSlicera
i kamera z każdego miejsca, prywatnie - drukarkę widzą tylko urządzenia zalogowane na Twoje konto Tailscale.
Enter (tak) albo `n`. Instalator pobiera na komputer oficjalną wersję przypiętą w projekcie i sprawdza jej sumę SHA-256; zajmuje ok. 40 MB
pamięci drukarki. Moonraker dostaje adresy Tailscale jako zaufane (jak sieć domowa), inaczej Fluidd i Orca
dostałyby błąd 401. Link do logowania jest pokazywany tylko w oknie, nigdy w logu - nie udostępniaj go. Instalator może od razu pokazać link do logowania albo zalogujesz się później (uruchom
instalator jeszcze raz albo przez SSH: `sudo tailscale up --accept-dns=false --hostname=qidi-q2`).
`--tailscale yes|no` odpowiada na pytanie z góry. Odinstalowanie usuwa Tailscale, jeśli dodał go instalator.

## Powrót

```
py tools/install.py uninstall --host IP_DRUKARKI
```

Wszystko wraca z kopii na komputerze (ze wszystkich uruchomień instalatora dla tej drukarki, więc zachowaj cały
folder `backups` i aktualizuj z tego samego folderu projektu); kalibracja zapisana w międzyczasie zostaje.
Zgubiłeś folder `backups` albo zmieniłeś komputer? `py tools/install.py uninstall --from-stock --host IP_DRUKARKI`
przywraca zamiast tego oryginały QIDI z oficjalnej paczki.

**Inne modyfikacje na drukarce?** Instalator przyjmuje tylko pliki będące oryginałami QIDI 01.01.02.04 albo
naszą wersją. Jeśli masz inne poprawki, najpierw wgraj 01.01.02.04 z pendrive'a
([docs/RECOVERY.pl.md](docs/RECOVERY.pl.md), opcja 2), potem uruchom instalator.

**Aktualizacja do nowszego wydania** tego projektu: pobierz je i uruchom `install` jeszcze raz – nasze
wcześniejsze wersje plików są rozpoznawane i podmieniane (z nową kopią). Zmiany: [CHANGELOG.md](CHANGELOG.md). Inne drogi powrotu (ponowne
wgranie 02.04 z pendrive'a, pełny reflash z właściwą kolejnością aktualizacji): [docs/RECOVERY.pl.md](docs/RECOVERY.pl.md).

## Profile OrcaSlicer

Co dostajesz:

| Profil | Co zmienia względem profilu QIDI dla Q2 |
|---|---|
| `Qidi Q2 0.2 / 0.4 / 0.6 / 0.8 nozzle (Tweaked)` (drukarki) | Końcowy G-code, który gasi też wentylator obiegu komory; podnoszenie Z **Normalne** zamiast Auto (Auto podnosi spiralą nad modelem i potrafi zostawić kolce). |
| `[TL] ...` (22 profile procesu, po jednym na każdy profil QIDI Q2) | Timelapse **płynny**: głowica do każdego zdjęcia odjeżdża do tyłu, z wieżą 35 mm. Gdy nie nagrywasz timelapse, wybierz proces **bez** `[TL]` — odjazdy wydłużają każdą warstwę. |
| `<filament> (Tweaked)` (filamenty) | Wentylator komory według materiału — niżej. Dodawane dla filamentów włączonych w twojej Orce; pozostałe możesz zaimportować. |

Instalator (`install.bat` / `tools/install.py install`) na końcu pyta, czy dodać je na komputerze, na którym działa
(`--orca yes|no`, żeby odpowiedzieć z góry). Albo ręcznie (OrcaSlicer musi być zamknięta):

```
py tools/orca_profiles.py install            # pokazuje, co doda
py tools/orca_profiles.py install --apply    # dodaje profile
py tools/orca_profiles.py status
py tools/orca_profiles.py uninstall --apply  # usuwa tylko to, co dodał, jeśli niezmienione
```

Na macOS/Linux zamiast `py` wpisz `python3`. Jeśli jesteś zalogowany do konta Orki, folder profili ma nazwę numeru konta zamiast `default`; narzędzie zapyta, którego użyć.

Profile **nie zawierają adresu drukarki ani klucza API** — połączenie ustaw sam w OrcaSlicer (ołówek przy drukarce → Połączenie).

### Profile drukarek: wentylator komory według materiału

Profile filamentów QIDI dla Q2 włączają wentylator obiegu komory (M106 P3) podczas druku dla PLA, PETG, TPU i nylonu;
ogólna biblioteka filamentów OrcaSlicer (SUNLU, eSUN, Polymaker, ... `@System`) zostawia go wyłączonego dla każdego
materiału. Profile drukarek projektu `Qidi Q2 ... (Tweaked)` ustawiają go za ciebie: raz, przed pierwszą warstwą
(`before_layer_change_gcode`, w profilu QIDI puste), według typu pierwszego filamentu. Wybierasz więc zwykłe filamenty
z biblioteki, a wentylator idzie za materiałem:

| Materiał | Podczas druku | Po druku |
|---|---|---|
| PLA (PLA+, Silk, Matte, PLA-CF, ...), TPU | 100% | 0% |
| PETG (PETG-CF, PCTG, PET-CF) | 75% | 0% |
| Nylon (PA, PA-CF, PA-GF, PPA) | 25% – trochę wymiany powietrza, komora zostaje ciepła | 0% |
| ABS, ASA, PC | 0% – jak QIDI: te trzymają ciepło w komorze | 0% |

QIDI daje 100% dla PETG i nylonu; 75% i 25% to wybór tego projektu. Inne materiały (PP, PVA, HIPS, ...) nie mają
linii z wentylatorem. Sprawdzone przez pocięcie w OrcaSlicer 2.5.2 (PLA S255, PETG S191, PA S64, ABS nic, raz przed
warstwą 1); na drukarce jeszcze nie sprawdzone. Liczy się tylko pierwszy filament: wielokolorowy druk z Boxem idzie
według pierwszego.

Wcześniejsze wersje (1.2.0 i starsze) dodawały zamiast tego kopię `(Tweaked)` każdego filamentu. Przejście: zamknij
OrcaSlicer, uruchom `py tools/orca_profiles.py uninstall --apply` (usuwa niezmienione kopie i stare profile drukarek,
po kopii w zip w `backups/`), potem `py tools/orca_profiles.py install --apply`. OrcaSlicer przepisuje profile drukarek
przy synchronizacji konta; przepisany profil liczy się jak twój i zostaje - wtedy usuń tę drukarkę `(Tweaked)` w
OrcaSlicer przed instalacją albo wklej wartość `before_layer_change_gcode` z `orca-profiles/machine/<drukarka>.json` w
własnym G-code drukarki → „G-code przed zmianą warstwy”.

## Licencja i źródła

Kod w tym repozytorium jest na licencji [GNU GPL v3.0](LICENSE). Źródło każdej poprawki jest wskazane w
[docs/FIXES.pl.md](docs/FIXES.pl.md). Podziękowania dla:

- [Klipper](https://github.com/Klipper3d/klipper) - Kevin O'Connor i współautorzy (GPL-3.0): kilka przeniesionych poprawek.
- [Valve-Oil](https://github.com/thelegendtubaguy/Valve-Oil) - thelegendtubaguy (GPL-3.0): poprawka powtórzeń pomiaru, taka sama jak u nich dla Max 4 / Plus 5, oraz optymalizacje timerów i wysyłania statusu w Klipperze (dostosowane do 02.04).
- [n3oney](https://github.com/qidi-community/q2-wiki/tree/main/content/randomize-probing) (wiki Q2 qidi-community): pomysł losowego punktu bazowania Z, żeby rozłożyć zużycie płyty.
- AFSFigueiredo ([QIDI #34](https://github.com/QIDITECH/QIDI_Q2/issues/34)): poprawka podtrzymania grzałek Boxa, przetestowana na ponad 8000 zmian filamentu.
- ValitovTimur ([QIDI #23](https://github.com/QIDITECH/QIDI_Q2/issues/23)): analiza błędu „Min or 0” grzałki Boxa i poprawka, którą wdraża `box-fixes`.
- ololonly ([QIDI #25](https://github.com/QIDITECH/QIDI_Q2/issues/25)): zgłoszenie i analiza, z których powstał `box-fan-threshold`.
- QIDI: kolejka druku, zapasowe DNS i scalanie statusu w Moonrakerze pochodzą z własnego firmware QIDI 01.01.03.02.
- Wcześniejsza praca: **Codex** (asystent AI firmy OpenAI, u nas pieszczotliwie „Stefan”, a.k.a. „wujek Codex”), który zbudował z autorem pierwsze moduły i poprawki.
- Zbudowane razem z **Claude** (asystent AI firmy Anthropic), który analizował kod QIDI, napisał i przetestował większość zmian razem z autorem na jego drukarce. Pliki w `orca-profiles/` pochodzą od profili QIDI dołączonych do OrcaSlicer — zobacz [orca-profiles/NOTICE.md](orca-profiles/NOTICE.md).

QIDI, QIDI Q2 i powiązane nazwy są znakami towarowymi ich właścicieli i służą tu tylko do wskazania, dla jakiej drukarki jest ten projekt.
