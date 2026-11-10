# Powrót: odinstalowanie, ponowne wgranie 02.04 albo pełny reflash

[English](RECOVERY.md) · **Polski**

> **Nigdy nie używaj aktualizacji online z ekranu („Check for updates” → Update), jeśli chcesz korzystać z tego projektu.**
> Wgrywa ona najnowszy firmware QIDI (01.01.03.x lub nowszy). Firmware QIDI nie da się cofnąć, więc nie wrócisz już
> do 01.01.02.04 – a ten projekt działa tylko na 01.01.02.04. Jedyną drogą powrotu byłby wtedy pełny reflash eMMC (opcja 3).

Wybierz najlżejszą opcję, która rozwiązuje problem.

| Opcja | Kiedy | Co tracisz |
|---|---|---|
| 1. `install.py uninstall` | Chcesz z powrotem fabryczne 02.04, drukarka działa | nic – kalibracja zostaje |
| 2. Ponowne wgranie oficjalnej paczki 02.04 z USB | Coś jest zepsute, a opcja 1 nie wystarcza | nic z plików QIDI; pliki dodane przez projekt zostają, dopóki nie zrobisz opcji 1 |
| 3. Pełny reflash eMMC, potem aktualizacje do 02.04 | System nie startuje albo chcesz naprawdę czystą drukarkę | wszystko na drukarce: kalibrację, ustawienia, pliki, historię |

## Opcja 1 – odinstalowanie (zalecana)

Na komputerze, w folderze projektu:

```
py tools/install.py uninstall --host IP_DRUKARKI
```

Instalator korzysta z kopii, którą `install` zapisał w `backups/` na komputerze: każdy podmieniony plik wraca do
oryginału QIDI, dodane przez nas pliki są usuwane, czynności modułów są cofane (zdjęta blokada folderu pobierania,
usługi jak przedtem), a usługi się restartują. W `printer.cfg` i makrach wycinane są tylko nasze zmiany, więc kalibracja
zapisana po instalacji zostaje. Plik, który sam zmieniłeś po instalacji, zostaje nietknięty i jest wypisany.

Plik z nowym adresem MAC też jest usuwany; po następnym restarcie drukarka zachowuje się jak fabryczna.

## Opcja 2 – ponowne wgranie oficjalnej paczki 01.01.02.04 z USB

QIDI pozwala wgrać **tę samą** wersję jeszcze raz. Wszystkie pliki QIDI z paczki wracają do oryginałów.

1. Jeśli możesz, najpierw zrób opcję 1 (zdejmuje blokadę folderu pobierania, która mogłaby przeszkodzić aktualizacji).
2. Sformatuj pendrive (FAT32). W jego głównym katalogu utwórz folder `QD_Update`.
3. Włóż do niego oficjalną paczkę **bez rozpakowywania**:
   `USB:\QD_Update\QD_Q2_01.01.02.04_20260804_Release.zip`
   (`py tools/firmware.py fetch` już ją pobrał do `downloads/`, SHA-256
   `92308ee19ddd49b3e8229118a4950d6f0dec993a5e99709e4c88f7e22b89092e`).
4. Włóż pendrive i postępuj według komunikatu aktualizacji QIDI. Nie wyłączaj drukarki (ani Boxa QIDI, jeśli go masz),
   dopóki się nie skończy.
5. Potem zrób poziomowanie stołu i input shaping, jak zaleca QIDI.

## Opcja 3 – pełny reflash, potem aktualizacje **tylko do 01.01.02.04**

Po reflashu eMMC drukarka startuje z firmware **1.0.x** (tekst poradników mówi o 1.0.0, ale ich zrzuty ekranu i aktualny obraz to 1.0.1). Wiki QIDI każe aktualizować dokładnie w tej kolejności,
bo pominięcie kroku może (rzadko) uszkodzić płytkę SOC:

**1.0.x → 1.1.1 → 01.01.02.01 → 01.01.02.04** – i na tym koniec. Bez aktualizacji online.

| Krok | Paczka (oficjalna) | SHA-256 | Jak włożyć na pendrive |
|---|---|---|---|
| 1.0.x → 1.1.1 | `Q2_V1.1.1.zip` z [wydań QIDI na GitHubie](https://github.com/QIDITECH/QIDI_Q2/releases/tag/Q2_V1.1.1) | `4c7d0f5b52d1a780f3e02b92bea6c7b751690c2b4da529eafd2ceb662241ecb7` | **rozpakuj**; trzy pliki `QD_Q2_MCU`, `QD_Q2_SOC_V1.1.1_…`, `QD_Q2_THR` do `USB:\QD_Update\` |
| 1.1.1 → 01.01.02.01 | [`QD_Q2_01.01.02.01_20260601_Release.zip`](https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.02.01/ikintbwrsx/QD_Q2_01.01.02.01_20260601_Release.zip) | `ee9010a4aafb7ab6fab0c6f7843b6b064c7e490e8a8dc1aa542d211d5f6ea31e` | **bez rozpakowywania** do `USB:\QD_Update\` |
| 01.01.02.01 → 01.01.02.04 | [`QD_Q2_01.01.02.04_20260804_Release.zip`](https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.02.04/nrpolyn8hx/QD_Q2_01.01.02.04_20260804_Release.zip) | `92308ee19ddd49b3e8229118a4950d6f0dec993a5e99709e4c88f7e22b89092e` | **bez rozpakowywania** do `USB:\QD_Update\` |

Na pendrive trzymaj pliki tylko **jednego** kroku naraz; po każdej aktualizacji sprawdź wersję na ekranie.
Paczki kończące się na `NA` to firmware międzynarodowy (międzynarodowa aplikacja QIDI Maker), `CN` – chiński.

Fabryczny obraz eMMC jest podlinkowany na stronie wiki QIDI
[Flash System Image (eMMC)](https://wiki.qidi3d.com/en/Memo/flash-emmc) („QIDI Q2 Image for eMMC”).
Dwa sposoby wgrania:

- sposób QIDI (ta strona wiki): moduł eMMC wyjęty z drukarki, adapter eMMC + czytnik kart USB, balenaEtcher lub Rufus;
- przez port USB-C SOC na płycie głównej programem RKDevTool (Rockchip), bez wyjmowania modułu:
  [poradnik społeczności](https://github.com/qidi-community/q2-wiki/blob/main/content/stock-firmware-flash/README.md).

Obie strony kończą się „zaktualizuj do najnowszego firmware” / „Online Update” – **tu tego nie rób**; trzymaj się
kolejności poniżej i zatrzymaj na 01.01.02.04. Obraz sprawdzony z tym projektem:

| Plik | Rozmiar | SHA-256 |
|---|---|---|
| `KLP_IMG_QD_Q2_V1.0.1_20250505_Release.7z` (w środku `KLP_IMG_QD_Q2_V1.0.1_20250505_Release.img`, 5,66 GB) | 1 900 160 385 bajtów | `3eb6aa08d55054db19a20ef80d85eaf9297efe307ae5cfa7cc7fba4eb2e366e7` |

Jeśli masz obraz z innego źródła, przed wgraniem porównaj jego SHA-256 z tym. Ten obraz startuje od 1.0.1;
kolejność jest ta sama (1.0.x → 1.1.1 → 01.01.02.01 → 01.01.02.04). Projekt nie dostarcza obrazu ani narzędzi
do wgrywania.

Po dojściu do 01.01.02.04: poziomowanie stołu i input shaping, potem `py tools/printer.py check`
i ponownie `py tools/install.py install`.

### Przed reflashem zgraj z drukarki

Reflash kasuje wszystko. Najpierw skopiuj na komputer (Fluidd → Konfiguracja pozwala pobierać pliki):

- `printer.cfg` – blok na końcu (`#*# SAVE_CONFIG`) to Twój input shaper, siatka stołu i offset Z;
  można potem przepisać te wartości zamiast kalibrować od nowa;
- `saved_variables.cfg`, `box.cfg` (Box QIDI), `crowsnest.conf` (kamera), `moonraker.conf`;
- pliki G-code i timelapse'y, które chcesz zachować;
- własne klucze SSH i inne zmiany zrobione przez Ciebie.

## Masz już 01.01.03.x?

QIDI nie wspiera cofania, a ten projekt **nie testował** żadnej drogi w dół. Dwie relacje społeczności:

- **„Qidi Restore”** – autor opisuje powrót z 01.01.03.01 do 01.01.02.04 **bez reflasha eMMC**, łącznie
  z firmware pozostałych płyt, i deklaruje przywrócenie tak sześciu Q2:
  [wątek na Reddicie](https://www.reddit.com/r/QidiTech3D/comments/1xdff0k/firmware_01010301_for_the_q2_is_broken_fix_your/).
  Przeczytaj cały wątek; na własne ryzyko.
- W przeciwnym razie: pełny reflash (opcja 3), potem aktualizacje tylko do 01.01.02.04.

Firmware płyty głównej i głowicy jest takie samo w 01.01.02.04 i 01.01.03.02 (MCU 02.01.01.09,
THR 02.02.01.08, Box 02.03.01.13); 01.01.03.02 dodaje tylko obrazy nowych akcesoriów (Box RS485, bufor).

## Po każdym powrocie: sprawdź wersje kontrolerów

Na ekranie (system / informacje o wersji) dla 01.01.02.04 powinno być:
**MCU 02.01.01.09** i **THR 02.02.01.08** (Box 02.03.01.13, jeśli masz).
Po powrocie do starszej wersji niektórzy dostawali „MCU protocol error” i musieli jeszcze raz zaktualizować
firmware kontrolera
([przykład](https://www.reddit.com/r/QidiTech3D/comments/1txj48b/how_to_revert_qidi_q2_to_v111_if_youre_like_me/)).
Ponowne wgranie oficjalnej paczki 01.01.02.04 z pendrive'a (opcja 2) wgrywa te wersje jeszcze raz.

Źródła: [wiki QIDI – aktualizacja firmware Q2](https://wiki.qidi3d.com/en/Q2/firmware-update),
[QIDI wiki – flash eMMC](https://wiki.qidi3d.com/en/Memo/flash-emmc), [qidi-community q2-wiki – stock firmware flash](https://github.com/qidi-community/q2-wiki/blob/main/content/stock-firmware-flash/README.md),
[pobieranie firmware QIDI](https://www.qidimaker.com/en/downloads/firmware/Q2),
[wydania QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/releases).
