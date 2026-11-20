# Powiadomienia na telefon (ntfy) - projekt

Status: do zatwierdzenia przez właściciela. Nic z tego jeszcze nie zbudowano.

## Po co (słowa właściciela)

Gdy drukarka drukuje bez niego, ma dostawać wiadomość na telefon o tym, co ważne, i móc z telefonu wznowić druk po
pauzie, bez logowania się do Fluidd. Żona nie ma Telegrama, a zakładanie konta z numerem telefonu jest niemile widziane.
Wiadomości mają pokazywać te same czasy, co ekran drukarki.

## Co ma przychodzić

1. **Start** - dopiero gdy zacznie się pierwsza warstwa (nie przy nagrzewaniu).
2. **Co 25%** - krótko: ile minęło, o której skończy, ile zostało.
3. **Koniec** - od razu "Druk skończony". Jeśli timelapse był włączony w tym druku (flaga `enable` zapamiętana na starcie) i
   Moonraker ma `autorender`, **druga wiadomość z filmem `.mp4` jako załącznikiem** (2-4 MB u właściciela, z miniaturą `.jpg`), gdy
   render się skończy. Gotowość filmu: `sh` sprawdza folder `timelapse` co kilkanaście sekund, aż pojawi się nowy `.mp4`
   (u właściciela ok. 1 min po końcu druku); po ok. 10 min bez filmu wiadomość "film niegotowy". Timelapse wyłączony albo druk
   anulowany/przerwany: jedna wiadomość na końcu, bez filmu. Limity ntfy.sh dla załącznika (ok. 15 MB, kilka godzin) do potwierdzenia w dokumentacji.
4. **Błędy i pauzy** - AI (makaron, obcy przedmiot), brak filamentu, błąd/shutdown Klippera lub MCU, anulowanie.
   Brak prądu: wiadomość dopiero po powrocie zasilania ("wykryto zanik zasilania, druk do wznowienia"). Przy braku prądu
   drukarka nie może nic wysłać, to ograniczenie sprzętowe.
5. **Pauza = przyciski "Wznów" i "Anuluj"** w powiadomieniu, plus zdjęcie z kamery, żeby było widać, co się dzieje.

Zmiany koloru: **świadomie nie** (przy druku zmieniającym kolor co 5 warstw byłoby to co kilka sekund).

## Cele, nie-cele, anty-cele

- Cel: działa dla każdego użytkownika projektu, także bez konta i bez numeru telefonu; domyślnie wyłączone (opt-in w instalatorze).
- Nie-cel: Telegram (może później jako dodatkowy odbiorca jednostronny), zdalny start druku, podgląd kamery na żywo, M600.
- Anty-cel: cokolwiek, co zjada pamięć drukarki (wolne ok. 85 MB, `algo_app` ma ok. 207 MB), albo pozwala komuś obcemu sterować drukarką.

## Wybrane podejście

**A. ntfy** (wybór właściciela). Dlaczego nie inne: Telegram `/resume` wymaga na drukarce bota odpytującego serwery w pętli
(skrypt Pythona, ok. 15-25 MB) i konta z numerem telefonu u każdego; e-mail wymaga hasła do skrzynki na drukarce.

## Architektura

Wysyłanie przez zwykłe `curl` na kanał ntfy (publiczny `ntfy.sh` lub własny serwer: adres jest ustawieniem).

| Zdarzenie | Skąd wykrywane | Jak wysyłane |
|---|---|---|
| start 1. warstwy, 25/50/75%, pauza (z powodem), koniec, anulowanie | Klipper: małe makro-zegar co 15 s (jak nasza notatka timelapse) czyta `print_stats`, `display_status` (M73), `pause_resume` | `gcode_shell_command` -> skrypt `sh` + `curl` |
| błąd / shutdown Klippera, utrata MCU | Moonraker: `[notifier]` z zdarzeniem `error` (Klipper w shutdown nie wykona makra) | `apprise` (`ntfy://...`) z `click`/załącznikiem |
| powód pauzy AI | zmienna `qdc_ai_error_code` (zapisuje ją `algo_app`) | w treści pauzy |
| brak filamentu | stan czujnika filamentu przy pauzie | w treści pauzy |
| zanik zasilania | start Klippera + znacznik wznowienia po zaniku (moduł `power-loss-resume-homing`) | wiadomość po starcie |
| przyciski z telefonu | drugi, tajny kanał "komend" | **słuchacz**: usługa systemd z `curl -sN .../raw` w pętli `sh`, wywołuje lokalnie `POST /printer/print/resume` lub `/cancel`; tylko gdy drukarka jest w pauzie; ok. 2-4 MB |

Czasy: **ten sam wzór co ekran**: `minęło x (100-P)/P` (P = postęp M73), rozpoznany w programie ekranu dla P > 50%.
**Otwarte:** poniżej 50% ekran używa tablicy `T[warstwa]`, której źródła jeszcze nie znamy. Wiadomość "25%" może więc
przez jakiś czas pokazywać inny czas niż ekran. Do rozstrzygnięcia po zrzutach ekranu przy następnym druku.

Pauza z przyciskami i zdjęciem: jedna wiadomość `curl` z nagłówkami `Actions` (dwa przyciski `http` wysyłające na kanał komend),
`Filename` i zdjęciem z kamery (`curl -T`). Telefon sam wysyła kliknięcie na internet, więc **Tailscale na telefonie nie jest potrzebny**.

## Bezpieczeństwo i prywatność

- Dwa kanały o długich losowych nazwach (generuje instalator, nie ma ich w repozytorium, są w pliku konfiguracyjnym na drukarce
  i w kopii na PC). Kto zna nazwę kanału komend, może wznowić lub anulować druk. Przyciski wysyłają tylko `resume`/`cancel`, nic innego.
- Wiadomości (nazwa pliku, postęp, zdjęcie z kamery) przechodzą przez serwer ntfy. Dla własnej prywatności można wskazać własny serwer.
- Zdalne "Wznów" bez patrzenia bywa ryzykowne (brak filamentu, zator): dlatego zdjęcie przy pauzie.
- Link do timelapse prowadzi do drukarki: działa w sieci domowej albo przy Tailscale. Poza nią przycisk nie otworzy filmu.

## Zasoby

Zegar Klippera co 15 s (kilka obliczeń szablonu), krótkie `sh`/`curl` przy zdarzeniach, słuchacz ok. 2-4 MB. Bez Pythona w pętli.

## Instalator i testy

- Nowy moduł (np. `phone-notifications`), opcja `--notify ask|yes|no` (domyślnie pyta na końcu, jak Tailscale i profile Orki).
- Instalator pyta o serwer (domyślnie `ntfy.sh`), generuje kanały, pokazuje je do wpisania w aplikacji ntfy, wysyła wiadomość testową.
- Cofnięcie: usunięcie plików i wyłączenie usługi (jak inne moduły).
- Test bez druku: wiadomość testowa. Test na druku (właściciel przy drukarce): start, 25/50/75%, pauza + "Wznów", koniec.
  Zanik prądu: tylko na życzenie właściciela.

## Do ustalenia przez budowniczego (kontrola przed planem)

1. Nazwa czujnika filamentu i jak odróżnić pauzę z braku filamentu od pauzy AI i od pauzy ręcznej.
2. Jak QIDI zapisuje znacznik "wznowienie po zaniku prądu" (do wykrycia przy starcie).
3. Adres zdjęcia z kamery (`snapshoturl` w timelapse) i czy `gcode_shell_command` jest już skonfigurowany w QIDI, czy trzeba dodać.
4. Skąd wziąć nazwę gotowego pliku timelapse i moment jego powstania (renderowanie trwa po końcu druku): druga wiadomość po wyrenderowaniu, albo link do folderu.
5. Składnia nagłówka `Actions` w ntfy dla przycisków `http` (wersja serwera).
6. Czy `curl` na drukarce ma HTTPS bez certyfikatów (sprawdzono: łączy się z `ntfy.sh`, kod 200).
