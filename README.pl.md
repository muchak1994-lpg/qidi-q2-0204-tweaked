# QIDI Q2 02.04 Tweaked

[English](README.md) · **Polski**

Społecznościowe poprawki i drobne ulepszenia dla drukarki 3D **QIDI Q2** z firmware **01.01.02.04** — i tylko z tą wersją.

> **Projekt nieoficjalny.** Niezwiązany z QIDI Technology, nieautoryzowany i niewspierany przez QIDI. Używasz na własne ryzyko. Miej pod ręką oficjalną paczkę firmware, żeby zawsze móc wrócić do wersji fabrycznej.

> **Stan: kandydat do wydania.** Wszystkie moduły budują się z oficjalnych paczek i zgadzają co do bajtu z przetestowaną drukarką; instalator jest przetestowany na symulowanej drukarce i w trybie odczytu na prawdziwej. Ostatni test przed pierwszym wydaniem: pełna instalacja na świeżo zreflashowanej drukarce. Zobacz [docs/ROADMAP.md](docs/ROADMAP.md).

## Co naprawia

40 małych modułów: program ekranu (kolejka druku z 03.02, bez okienka aktualizacji, dark mode światła),
poprawki Klippera (fuzzy skin, wentylator hotendu, grzałki Boxa QIDI, błędy MCU, bezpieczny zapis ustawień i inne),
makra, poprawki Moonrakera i Fluidda, stały MAC Ethernetu oraz brakujące biblioteki AI kamery.
**Pełna lista z problemem, który rozwiązuje każdy moduł: [docs/FIXES.pl.md](docs/FIXES.pl.md).**

## Zasady

- **Tylko 02.04.** Każda zmiana jest sprawdzana względem dokładnych plików 01.01.02.04 (SHA-256). Na innej wersji instalator odmawia działania.
- **Aktualizacje firmware zostają zablokowane.** Poprawki są robione pod 02.04; automatyczna aktualizacja po cichu by je zastąpiła. Blokada jest częścią paczki, a nie opcją.
- **W repozytorium nie ma kodu QIDI.** Instalator sam pobiera oficjalną paczkę 01.01.02.04 z publicznego serwera QIDI, sprawdza jej sumę kontrolną i nanosi zmiany na Twoim komputerze.
- **Kopie na komputerze, na drukarce nic po nas nie zostaje.** Przed każdą zmianą oryginalne pliki drukarki są zapisywane na Twoim komputerze, więc każdy moduł da się cofnąć. Pliki tymczasowe na drukarce są usuwane po instalacji.
- **Dodajemy, nigdy nie podmieniamy — także na komputerze.** Profile OrcaSlicer są dodawane obok Twoich; profil, który już masz, nigdy nie zostaje nadpisany.
- **Bezpieczeństwo sieci jest po Twojej stronie.** Trzymaj drukarkę w zaufanej sieci, nie wystawiaj jej do internetu.

## Wymagania

- QIDI Q2 z firmware **01.01.02.04**, widoczna w sieci lokalnej.
- Komputer (Windows, macOS lub Linux) z **Pythonem 3.8 lub nowszym** (na Windows: z python.org lub Microsoft Store; działa polecenie `py`).
- Do profili: OrcaSlicer, w której choć raz dodano drukarkę QIDI Q2.

## Zanim zaczniesz

> **Nie używaj aktualizacji online z ekranu.** Wgrywa najnowszy firmware QIDI, którego nie da się cofnąć –
> stracisz drogę powrotu do 01.01.02.04 i ten projekt. Aktualizuj tylko offline (pendrive) i tylko do 01.01.02.04.
> Zobacz [docs/RECOVERY.pl.md](docs/RECOVERY.pl.md).

- Drukarka nic nie robi: nie drukuje, nie jest w pauzie, grzałki wyłączone.
- Znasz jej adres IP (ekran → ustawienia sieci) i hasło SSH użytkownika `mks`.
- Na komputerze otwórz terminal w tym folderze (Windows: w Eksploratorze wpisz `cmd` w pasku adresu i naciśnij Enter).

## Instalacja

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

## Powrót

```
py tools/install.py uninstall --host IP_DRUKARKI
```

Wszystko wraca z kopii na komputerze; kalibracja zapisana w międzyczasie zostaje. Inne drogi powrotu (ponowne
wgranie 02.04 z pendrive'a, pełny reflash z właściwą kolejnością aktualizacji): [docs/RECOVERY.pl.md](docs/RECOVERY.pl.md).

## Profile OrcaSlicer

Co dostajesz:

| Profil | Co zmienia względem profilu QIDI dla Q2 |
|---|---|
| `Qidi Q2 0.2 / 0.4 / 0.6 / 0.8 nozzle (Tweaked)` (drukarki) | Końcowy G-code, który gasi też wentylator obiegu komory; podnoszenie Z **Normalne** zamiast Auto (Auto podnosi spiralą nad modelem i potrafi zostawić kolce). |
| `[TL] ...` (22 profile procesu, po jednym na każdy profil QIDI Q2) | Timelapse **płynny**: głowica do każdego zdjęcia odjeżdża do tyłu, z wieżą 35 mm. Gdy nie nagrywasz timelapse, wybierz proces **bez** `[TL]` — odjazdy wydłużają każdą warstwę. |

Instalacja (OrcaSlicer musi być zamknięta):

```
py tools/orca_profiles.py install            # pokazuje, co doda
py tools/orca_profiles.py install --apply    # dodaje profile
py tools/orca_profiles.py status
py tools/orca_profiles.py uninstall --apply  # usuwa tylko to, co dodał, jeśli niezmienione
```

Na macOS/Linux zamiast `py` wpisz `python3`. Jeśli jesteś zalogowany do konta Orki, folder profili ma nazwę numeru konta zamiast `default`; narzędzie zapyta, którego użyć.

Profile **nie zawierają adresu drukarki ani klucza API** — połączenie ustaw sam w OrcaSlicer (ołówek przy drukarce → Połączenie).

## Licencja

Kod w tym repozytorium jest na licencji [GNU GPL v3.0](LICENSE). Pliki w `orca-profiles/` pochodzą od profili QIDI dołączonych do OrcaSlicer — zobacz [orca-profiles/NOTICE.md](orca-profiles/NOTICE.md).

QIDI, QIDI Q2 i powiązane nazwy są znakami towarowymi ich właścicieli i służą tu tylko do wskazania, dla jakiej drukarki jest ten projekt.
