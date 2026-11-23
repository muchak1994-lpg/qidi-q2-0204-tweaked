# OrcaSlicer 2.5.2 (21.11.2026) - co się zmieniło i co to znaczy dla Q2

Raport z 22.11.2026. Niczego nie pobrano ani nie zainstalowano;
źródła czytane przez API GitHuba (release notes `v2.5.2`, `v2.5.1`, `v2.5.0`, porównanie tagów
`v2.5.1...v2.5.2`: 44 commity, 187 plików) oraz surowe pliki profili z tagów.
Oznaczenia: **[DOWÓD]** = jest w release notes / diffie (podany PR lub commit), **[HIPOTEZA]** = mój wniosek.

## 1. Ogólnie: co jest w 2.5.2

To wydanie naprawcze na bazie 2.5.1 (które wyszło 14.11). Jedna nowa funkcja, reszta to poprawki. [DOWÓD: release notes]

- **Nowa funkcja:** "Prime volume" dla każdego filamentu (strona Multimaterial filamentu) przy wieży czyszczącej Type 1
  (PR [17424](https://github.com/OrcaSlicer/OrcaSlicer/pull/17424)). Szczegóły w pkt 3.
- **Awarie (crashe):** krótkie, nieprostoliniowe pasy wypełnienia (17599, 17600), pusta pierwsza warstwa z wieżą (17565),
  OpenGL nie startuje (17441), filament przypisany do nieistniejącej dyszy (17476).
- **Slicing / jakość:** "Only one wall on top surfaces" + top surface expansion (17597), mniej drobnych ruchów
  w wygładzonym wypełnieniu przy bardzo drobnej rozdzielczości (**17630, patrz pkt 3**), Tree Hybrid przy brzegu stołu
  (17700), punkt startu skirt zapisywany w projekcie (17457), test max flowrate (17699), komentarz czasu pierwszej
  warstwy w G-code (**17328, pkt 3**).
- **Import / narzędzia:** STEP z brakującymi ścianami (17720), rozmieszczanie części prawie na szerokość stołu
  (17416, dotyczy 32 profili z szerokością linii w %), Measure/Assemble dla skalowanych obiektów, Cut, Texture, pasek narzędzi.
- **System:** Wayland/AppImage, VirtualGL, linki "Open in OrcaSlicer" na macOS, wtyczki (Windows), budowanie ze źródeł
  (pinning wxWidgets), zakładka Device ładuje stronę drukarki dopiero po otwarciu (17580).
- **Profile (cała sekcja):** tylko Prusa CORE One (kolejność prędkości na zwisach), Snapmaker U1 (rozstaw prętów),
  AnkerMake M5/M5C (czas wydruku). **Zero zmian w Qidi**, zero w OrcaFilamentLibrary. [DOWÓD: w liście 187 zmienionych plików
  pod `resources/profiles/` są tylko Anker, Prusa, Snapmaker.]

## 2. Czy coś z tego dotyczy naszych profili

Krótko: **nic nie wymaga naprawy**, jedna rzecz warta uwagi (prime volume). Szczegółowo:

| Nasz element | Upstream 2.5.2 | Wniosek |
|---|---|---|
| Profile `inherits` (nazwy systemowe Q2: `0.20mm Standard @Qidi Q2`, `Qidi Q2 0.4 nozzle` itd.) | Pliki Qidi niezmienione między 2.5.1 a 2.5.2; `Qidi.json` ma wersję `02.04.00.21` w obu tagach (w 2.5.0 było `.20`) | Nazwy się nie zmieniły, nasze `inherits` nadal trafiają. [DOWÓD] |
| Filamenty "(Tweaked)" (`inherits: "<nazwa> @System"`, M106 P3) | OrcaFilamentLibrary bez zmian w 2.5.2 | Bez kolizji. [DOWÓD: brak plików w diffie] Niesprawdzone: czy 2.5.1 ruszyło bibliotekę - patrz niżej. |
| Wentylator komory (`activate_air_filtration`, `during_print_exhaust_fan_speed`, `complete_print_exhaust_fan_speed`) | Upstream nic nie zmienił w tych polach | Nadal nasza własna poprawka, której upstream nie ma. [HIPOTEZA: stan upstream dla filamentów Q2 nie był dziś porównywany filament po filamencie] |
| Wieża `[TL]`: `enable_prime_tower=1`, `prime_tower_width=35`, `wipe_tower_no_sparse_layers=0`, `timelapse_type=1` | Upstream `fdm_process_qidi_common` już ma dokładnie: wieża 1, szerokość 35, no_sparse 0 | Trzy z czterech pól w `[TL]` są duplikatem upstream (nieszkodliwe). Jedyna realna różnica `[TL]` to `timelapse_type=1`. [DOWÓD: pliki z tagu v2.5.2] |
| Maszyna "(Tweaked)": `z_hop_types`, `machine_end_gcode` (dodany `SET_PRINT_MAIN_STATUS ...` i `M106 P3 S0`) | G-code końcowy Q2 niezmieniony w 2.5.2 | Nasz end G-code nadal bazuje na tym samym. [DOWÓD: brak zmian w pliku maszyny] |
| Pole `version: "2.4.0.19"` we wszystkich naszych plikach | Nowe Orki mają 2.5.x | Prawdopodobnie Orka je wczytuje jak dotąd (wg notatek profile działały na Orce 2.6-dev właściciela). [HIPOTEZA - nie sprawdzone w 2.5.2 GUI] |
| `tools/orca_profiles.py` (użytkownik `default`/konto, `OrcaSlicer.conf` "filaments") | W release notes 2.5.2 nic o strukturze folderu użytkownika | Bez kolizji. [HIPOTEZA] |

**Rzecz warta uwagi - Prime volume (PR 17424).** Q2 używa `wipe_tower_type: type1` (plik `fdm_q_common.json` w v2.5.2),
czyli tego samego typu wieży co Bambu. Wniosek [DOWÓD z PR + profilu]: w 2.5.2 filament dla Q2 ma nowe pola
`filament_prime_volume` (strona Multimaterial), a procesowe "Prime volume" jest wyszarzone. W 2.5.0-2.5.1 wieża Type 1 czytała
wartość z filamentu, ale nic tego nie pokazywało. Czyli: **nasze profile nic nie ustawiają, więc wieża dla Q2 liczy się jak dotąd**
("projekty tną jak wcześniej, dopóki nie zmienisz wartości" - release notes). Zysk: właściciel może zmniejszyć wieżę
przy zmianie filamentu (np. 30 -> 10 mm³ obcięło wieżę H2D z 3,26 m do 1,95 m) - przydatne przy `[TL]` (wieża tylko po to, by timelapse
działał). [HIPOTEZA: że da się tak zmniejszyć wieżę `[TL]` bez problemu z jakością - nie testowane; "Zasada jedna zmiana naraz".]
Ta sama sprawa dotyka wprost naszej notatki "wieża czyszcząca w `[TL]` może być za cienka" - ale to inny problem (szerokość/brim), nie objętość.

## 3. Co dotyka Q2 wprost

1. **Wygładzone wypełnienie i Q2 (PR [17630](https://github.com/OrcaSlicer/OrcaSlicer/pull/17630), commit `8eb8230a`, autor ianalexis).**
   [DOWÓD: opis PR] Autor opisuje na prawdziwym Q2, że przy "Sparse infill smooth factor" i **rozdzielczości G-code 0** Klipper
   miał do zaplanowania >1000 ruchów/s i Q2 kilka razy stawał na wypełnieniu (wygładzanie zrobiło 656 tys. ruchów zamiast 42 tys.);
   poprawka obcina podział rogu do 0,005 mm. **Dotyczy tylko profili z `resolution` = 0 (cztery profile systemowe w całej Orce)**.
   Profile Q2 mają `resolution: 0.012` ([DOWÓD: `fdm_process_qidi_common.json`, v2.5.2]; nasze profile pola nie nadpisują) - **G-code z naszych profili się nie zmienia.**
   Przy 0,005 mm lub grubszej "G-code się nie zmienia" (cytat z PR). Uwaga praktyczna: ten sam objaw (stawanie głowicy) mógłby wystąpić,
   gdyby ktoś ustawił rozdzielczość 0 - na Q2 nie ustawiać. [HIPOTEZA: że "Fluidd/ekran" pokazałby to jako pauzy wypełnienia.]

2. **Komentarz "estimated first layer printing time" w G-code (PR [17328](https://github.com/OrcaSlicer/OrcaSlicer/pull/17328), commit `a6433c4e`).**
   [DOWÓD: release notes] Do 2.5.1 ten komentarz podawał czas G-code startowego (przy `PRINT_START` makro ~0), w 2.5.2 daje czas
   pierwszej warstwy, "taką samą wartość jak zapisana w 3MF". Wpływ na nas: **nasza notatka o ekranie QIDI czyta `prediction` z `Metadata/slice_info.config`
   w 3mf, nie ten komentarz** - więc ETA ekranu tym nie jest ruszone. [DOWÓD: grep po `first layer printing time` w `modules/`, `tools/`, `tests/` nie ma trafień, więc nasz kod nie czyta tego komentarza.
   HIPOTEZA: Moonraker/Fluidd na drukarce mógłby go czytać (metadata.py Moonrakera) - nie sprawdzałem.] W 2.5.2 **nie ma żadnej zmiany w liczeniu
   całkowitego czasu druku ani w `prediction`/`slice_info.config`** [DOWÓD: brak w release notes i w 44 commitach]. Czyli zaniżanie
   czasu przez Orkę (1h0m44 vs prawdziwe 1h6m11) zostaje - nie jest to poprawione w 2.5.2.

3. **Timelapse - PR właściciela [17390](https://github.com/OrcaSlicer/OrcaSlicer/pull/17390).**
   [DOWÓD: API GitHuba, 22.11] Nadal **otwarty**, nie zmergowany, więc **nie ma go w 2.5.2** (ostatnia aktywność 18.11). Powiązane otwarte:
   #14051 "Enable smooth timelapse selector from printer profiles" (tego samego tematu). Nasz `[TL]` nadal jest sposobem na użycie Smooth
   (`timelapse_type=1`) bez PR. Do zrobienia przy okazji: dopisać do PR zrzuty przed/po z 2.5.2 (lista rzeczy z CLAUDE.local.md pkt 10) -
   test na 2.5.2 byłby dobrym punktem odniesienia. Profil Q2 upstream nadal ma `is_support_timelapse: 1` i gałąź `{if timelapse_type == 1}` w `layer_change_gcode`
   [DOWÓD: plik maszyny v2.5.2].

4. **Profile Q2 w 2.5.0 / 2.5.1 (kontekst, bo właściciel mógł nie zauważyć zmian z 2.5.0):**
   - 2.5.0: nazwy plików G-code po filamencie faktycznie drukowanym, nie z slotu 1 (PR 16922, wszystkie Q2/Q2C procesy);
     wybór płyty (plate type) dla Q2/Q2C/X-Max 4 (PR 16734); drukarka pokazuje sloty Boksa przy wysyłaniu druku (PR 16723; wymaga
     "Use printer agents instead of print hosts" w Preferences > Developer); synchronizacja filamentów z Boksa po nowych firmware'ach (16679);
     taby Device/Calibration dla Qidi (17162).
   - 2.5.1: port w adresie hosta Moonraker/Qidi (np. `192.168.1.50:7125`) nie ginie po pierwszym połączeniu; sync filamentów z drukarki nie wybiera presetu innego materiału;
     konfiguracja Qidi nie "wraca" jako aktualizacja (17449); modele stołu/dyszy (17348, wersja Qidi 02.04.00.21).
   - 2.5.2: **brak** zmian specyficznych dla Qidi poza komentarzem w opisie PR 17630.
   Te punkty wskazują, że **Orka już wysyła do Q2 zmienione G-code/nazwy**; żadnego z nich nie testowałem na drukarce.

5. **Firmware 02.04 / Box / `Moving out of range`.** [DOWÓD] W release notes 2.5.2 (i 2.5.1) **nie ma** wpisu o "Move out of range" ani
   o zmianie obszaru druku/`bed_exclude_area` Q2; plik maszyny Q2 w v2.5.2 ma `printable_area 270x270`, `printable_height 256`, `bed_exclude_area 0x0,11x0,11x16,0x16`
   (to samo co wcześniej, według diffa - brak zmian). Nierozwiązany błąd z 07.11 (3x "Move out of range") nie jest
   adresowany w 2.5.2. [HIPOTEZA: przyczyna mogła leżeć w G-code startowym `G0 X... Y...` z `first_layer_print_min` + 80 -
   to nie było sprawdzane dziś.] Box: PR 16723/16679 (2.5.0) - nic nowego w 2.5.2; `is_support_multi_box: 0` dla Q2 bez zmian.

6. **Nie dotyczy Q2:** zmiany Prusa CORE One, Snapmaker U1, Anker, Wayland, macOS - pomijam.

## Czego nie sprawdziłem (uczciwie)

- Nie instalowałem 2.5.2, nie wczytywałem naszych profili w nowej Orce, nie slicowałem. Wszystko wyżej to czytanie diffa/API.
- Nie porównywałem filament po filamencie biblioteki OrcaFilamentLibrary 2.5.1 z 2.5.0 (tylko 2.5.1 -> 2.5.2: bez zmian).
- Nie sprawdzałem, czy PR 17630 był testowany na Q2 właściciela (autor to ianalexis, nie właściciel).
- Wiersz poleceń 2.6-dev (ta wersja właściciela) to osobna linia niż 2.5.x - zmiany 2.5.2 mogą jeszcze nie być w jego buildzie; sprawdzić wersję.

## Co zrobić u nas (po ważności; nic nie wykonane)

1. **(średnie)** Zainstalować 2.5.2 u właściciela dopiero po jego zgodzie; po instalacji uruchomić `py tools/orca_profiles.py status` i sprawdzić w GUI,
   czy profile `(Tweaked)` i `[TL]` się wczytują i czy `Prime volume` wyszarzone/pole filamentu pojawia się dla Q2.
2. **(niskie, opcjonalne)** Rozważyć w `[TL]` zmniejszenie `Prime volume` filamentów (np. 30 -> 10-15 mm³) przez wieżę mniej marnującą filament - tylko po teście wydrukiem, jedna zmiana naraz; jeśli się sprawdzi, dopisać do generatora `tools/orca_filaments.py` pole `filament_prime_volume` (wymagałoby decyzji, bo dziś generator ustawia tylko wentylator komory).
3. **(niskie)** Uprzątnąć `[TL]`: pola `enable_prime_tower`, `prime_tower_width`, `wipe_tower_no_sparse_layers` są już domyślne w upstream; zostawić tylko `timelapse_type`. Zmiana tylko kosmetyczna, bez zysku - proponuję NIE ruszać.
4. **(niskie)** Dopisać do PR 17390 test na 2.5.2 (zrzuty przed/po), bo to najnowsze wydanie, o które maintainerzy się oprą.
5. **(informacja)** Nie dodawać `resolution: 0` ani gładkiego wypełnienia z rozdzielczością 0 w naszych profilach Q2 - to dokładnie scenariusz, który zatrzymywał głowicę (17630 łata to dopiero w 2.5.2).
6. **(informacja)** Zaniżony czas prediction z Orki to nadal stan upstream - nasze poprawki ETA (Fluidd, ntfy) zostają potrzebne.
