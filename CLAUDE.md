# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

OpenOrbit is an offline private server for the original DarkOrbit Unity client 1.1.116, plus a desktop panel that runs it.
It is pure Python 3.10+ and uses only the standard library (`pyproject.toml` has no dependencies). The only optional extra
is `capstone`, needed by `tools/il2cpp/` for porting the protocol to a new client. The client lives in a sibling folder,
`../DarkOrbit_Version1.1.116/`. Never modify it, and never run its `DarkorbitLauncher.exe`, which can update it from the
official servers.

## Commands

- Panel (the normal entry point): double-click `OpenOrbit Panel.pyw`, or run `python "OpenOrbit Panel.pyw"`. It runs
  `server/panel/panel.py` at 127.0.0.1:8077 inside an Edge/Chrome app window. Pass `--pencere-yok` to skip opening the
  window. A second launch only reopens the window.
- Servers without the panel (developer fallback): `python -I server/baslat.py [game options]`. It starts `web.py` and
  `game.py`, then the client.
- Run a single server: `python -I server/game.py <log_dir> [--profil=<path>] [--ayarlar=<path>] [--kontrol] [--dokunulmaz] …`
  or `python -I server/web.py <log_dir> [--profil=<path>]`. The docstring at the top of each file lists every flag.
- Tests use **unittest** (no pytest config). Run them from the repo root:
  `python -m unittest discover -s tests -v`. To run one test, add `-k <name_substring>`.
  The suite is only the fork's 6 save-lock tests in `tests/test_orbitbot_kilitleri.py`. They are fast and bind no ports.
  Upstream ships no tests.
- Translations: `python server/panel/dil.py <code>` lists the panel strings still missing for that language.
- Protocol port to a new client: `python -I tools/il2cpp/protokol_guncelle.py …` (the panel's Client page runs it).

## Architecture

The panel is a process manager. `server/panel/surecler.py` spawns each server as its own windowless `python -I`
subprocess and writes its output to `server/logs/<name>_konsol.log`.

| Process / port | Role |
| --- | --- |
| `panel/panel.py` 8077 | Local web UI (`panel/arayuz/index.html` + JS) and JSON `/api/...` (needs the `X-Panel-Belirteci` token header) |
| `web.py` 8090, 80 (+ dummy 843/9339/8082) | Fakes the client's web login (`links.php`, `login.php`, `maps.php`, unityApi) |
| `game.py` 8081 | The game server: TCP libcom protocol, one `Session` per connection, `on_packet` dispatch |
| `sohbet.py` 7771 | Chat, runs inside the game process |
| `kontrol.py` 8099 | Live-test control channel, only with `--kontrol`. JSON lines: trace, inject requests, run `py` in-process |
| `panel_kanali.py` 8098 | The panel's in-game Shop/Hangar/Skylab/Auction. Requests are replayed through `on_packet`, so game rules apply |
| `odeme.py` 127.0.0.1:443 | Catches the client's real-money "Buy" buttons and opens the in-game shop |

- **`server/` is a flat script directory, not a package.** Modules do `sys.path.insert(0, HERE)` and import siblings by
  bare name (`import protocol as P`, `import yollar as YOL`). Keep server code stdlib-only.
- **Protocol:** `server/protocol.py` is the runtime codec: framing, LZ4 "DOB3"/"DOL4" downstream compression,
  `encode_message`/`messages`. It is driven by `server/data/protocol_read.json` and `protocol.json`, which are extracted
  from the client's IL2CPP code by `tools/il2cpp/read_spec.py` and `tools/il2cpp/protocol.py`. Two different files are
  named `protocol.py`: don't confuse them. `eski_protokol.py` is the legacy Flash-era text protocol (`0|LM|ST|…`), still
  carried inside `LegacyModule`. Generated protocol versions go in `server/data/protokol/`, which is gitignored.
- **Game:** `game.py` is the entry point and the session logic. `dunya.py` (the largest file) is the per-connection map
  world: NPCs, AI, combat, boxes and ores. Feature systems (gates `kapi.py`, events `etkinlik_*.py`, shop `magaza.py`,
  quests `gorev.py`, Skylab, Assembly, clans, PET, …) are one module each. `server/bot/` holds the in-server bot players
  ("Botlar (Beta)", packs in `save/botlar/`, passed in via `DO_BOT`). Those are separate from the external OrbitBot.
- **Profile = protocol:** `profil.py` keeps field names identical to the protocol's, so the profile turns directly into
  login messages. The game autosaves `profil.json` every 10 s and also on the `--durdur=<file>` stop signal.
- **Data and worlds:** static game data is in `server/data/*.json`, plus the client's `spacemap-config.xml` and
  `maps-config.xml`. `veri.py` overlays the selected World Editor world (`save/dunyalar/<id>.json`, JSON-Pointer patches,
  `{"$sil": true}` deletes, picked via `DO_DUNYA`). Only files marked live reload while the game runs. Settings are in
  `ayar.py`, where `SCHEMA` is the single definition the panel UI is built from. Each setting's `uygulama` field says when
  it takes effect: instantly, on map change, on login, or on restart.
- **Paths** (`yollar.py`): `server/save/kayitlar/<slot>/{profil.json, kayit.json, web_ayarlari.json, duzenleme.json, yedek/}`,
  `server/save/panel.json` (the `aktif_kayit` key is the active slot), `server/logs/`. `DO_KAYIT_KLASORU` and
  `DO_GUNLUK_KLASORU` override the save and log dirs; tests use these. `server/save/` and `server/logs/` are gitignored
  user data.
- **Multiplayer** (`cok_oyunculu.py`): `game.py --cok-oyunculu`, configured through the `DO_COK_OYUNCULU` JSON env var
  (kept off the command line on purpose).
  - **Host** (`panel/arkadas.py`): 8081 and 7771 listen on all interfaces.
  - **Join:** only a local `web.py --uzak=<host:8081>` runs, with no local game server. A guest's save lives only in the
    host's memory and is long-polled back to the guest's own slot.
  - **Multi-client** (`panel/coklu.py`): same mode, localhost only, no guests. Extra local saves are added via `/yerel/ekle`.
  - Normal maps are shared through `ortak_harita.py`. Gates and event maps are per player.
- **The guest/admin HTTP API runs on the game port 8081 itself.** `game.handle` sniffs the first bytes
  (`cok_oyunculu.http_mi`: `GET `/`POST`/`HEAD` versus a length prefix). There is no separate HTTP port.
- **Updater** (`panel/guncelleme.py`): it tracks `kaanumay/OpenOrbit` `main`. A git checkout is updated only by
  `fetch` + `merge --ff-only`. On any other branch, or with local changes, it does nothing except notify.
  `server/surum.txt` is filled by `export-subst` in ZIP downloads.
- **Client plugin:** `server/panel/eklenti/` is a BepInEx 6 C# plugin. The built `OpenOrbitYama.dll` is committed.

## Gotchas

- **The module docstrings are the design docs, written in Turkish.** Read them first. On this Windows console, set
  `PYTHONIOENCODING=utf-8` before printing them. Docstrings cite `belgeler/*.md`, `test/canli.py`,
  `tools/bot_benzetim.py` and `tools/sablon_paylas.py`. None of these exist in the repo, so don't go looking for them.
- **Panel UI strings are written in Turkish and wrapped in `_()`.** The Turkish text is the key in
  `server/panel/arayuz/<code>.json` (de, en, es, fr, pl, pt, ru; there is no `tr.json`). A new string needs entries in
  all 7 files. Missing ones fall back to English.
- **Never write a slot's `profil.json` while that slot is in use**, because the server's autosave overwrites it. The
  panel blocks this through `KAY.in_use`, which in this fork also counts a live `orbitbot.lock`. Edits to a running game
  go through `panel_kanali.py`. The character editor works on the `duzenleme.json` draft.
- **The game client protocol is fixed by client 1.1.116.** `protocol.CLIENT_HASH` and the extracted specs must match the
  client. Don't hand-edit `protocol_read.json` without regenerating or reviewing it against `tools/il2cpp`.

## This fork and OrbitBot

Remotes: `origin` = constructigogo/OpenOrbit (the fork), `upstream` = kaanumay/OpenOrbit.
- The fork's `main` is upstream `main` plus the OrbitBot lock commits: `server/panel/kilitler.py`, the hooks in
  `panel.py`, 7 `arayuz/*.json` strings, and `tests/`.
- `main` is published, so upstream updates arrive by **merging**, not rebasing: `git fetch upstream`,
  `git merge upstream/main`, `git push origin main`. The panel's git updater fetches `origin main` (the fork) and only
  fast-forwards, so it never pulls upstream directly. Keep the fork diff small, since `panel.py` is the conflict hotspot.

The sibling project `../OrbitBot` (headless bot in C#, a separate repo) depends on these. Don't change them blindly:
- **Files it reads at runtime** (no Python import; the C# port reimplements the codec and map rules):
  - `server/data/protocol_read.json` (message spec) and `server/data/spacemap-config.xml` (map name lines).
  - Travel: `server/data/maps-config.xml` (gates) and `server/data/harita_duzeni.json` (map layout).
  - Quests: `server/data/gorevler.json`, `gorev_ekleri.json`, `npc.json` (alien spawns) and `seviyeler.json` (levels).
  - Collecting: `server/data/esyalar.json` (`cevherler`: ore fields, types and prices) and `npc.json`'s cargo and
    pick-up keys (each alien's `kargo` and `ek_odul`, `bonus_kutu`/`bonus_kutu_4x`, `toplama_mesafe`, `kutu_gorus`).
    A malformed `esyalar.json` stops every bot.
  - The `CLIENT_HASH = '<32 hex>'` line in `server/protocol.py` and the `DESTEKLENEN = '<x.y.z>'` line in
    `server/panel/istemci.py`, both read with a regex: keep them single-line string assignments.
  - `server/data/protokol/surum.txt`: the local client version is `istemci.supported()` rebuilt in C#.
  - Ported by hand, so a change here needs the C# port updated: `protocol.py`'s `FIXES` table, value transforms,
    framing and LZ4 block format; `harita`'s name parsing, `company()`, `NO_DMZ_MAPS`, `DMZ_AFTER_JUMP_SN`,
    `EXTRA_NAMES`, `GATES`, `map_size()` and `level_required()`; `gorev`'s quest resolver and constants; the pick-up,
    harvest and ore-sale rules in `dunya.py` (ranges, view range, own home station only) and `profil.py`'s `CARGO_ORES`.
- **Reference generator** `OrbitBot/tools/golden/make_golden.py` (`python -I`) imports `protocol`, `harita`, `ayar` and
  `gorev` and loads `server/panel/istemci.py` by path, with `server/` and `server/panel/` on `sys.path`. Keep these
  modules import-safe, with no import side effects and stdlib only (`harita_duzeni`, `veri`, and `gorev`'s and
  `istemci.py`'s own imports included). After each upstream merge, rerun it in OrbitBot: failing reference tests there
  mean the C# port needs updating.
- **HTTP on 8081:**
  - `/misafir/bilgi`: OrbitBot reads `protokol`, `misafir`, `en_cok`, `yer`, `sifre` and `istemci`. It refuses to join
    when `istemci` is present and differs from its local `supported()` label, the same rule as the panel's JOIN.
  - `/misafir/giris`, `/misafir/profil` (long poll) and `/misafir/cikis`.
  - `cok_oyunculu.PROTOKOL` (1) must equal OrbitBot's `GuestApi.Protokol`.
- **Its end-to-end tool** starts `python -I server/game.py <logs> --cok-oyunculu --profil= --ayarlar= --durdur=` with
  `DO_KAYIT_KLASORU`, `DO_GUNLUK_KLASORU` and `DO_COK_OYUNCULU` (`{misafir, sifre, en_cok}`) on copied saves.
- **Save format:**
  - `profil.json`: `pilot.{userName, level, factionId, userId}`, `gemi.typeId`, `konum.mapId`.
  - `kayit.json`: `ad`.
  - `yedek/oto_YYYYmmdd_HHMMSS.json` backups and `yedek/notlar.json`.
  - `panel.json`: `aktif_kayit`.
- **Locks** (`kilitler.py`): `panel.lock` (`{pid, since, ne, adres}`) and `orbitbot.lock` (`{address, pid, since}`) in
  each slot folder. Each counts only while its pid is alive. The panel rewrites its locks atomically every 2 s and removes them on exit.
  OrbitBot reads `panel.lock`'s `adres` to detect the user's own session.
- **OrbitBot detects lock support by checking that `server/panel/kilitler.py` exists.** Renaming or moving it silently
  disables the integration.

## Turkish glossary (recurring identifiers)

kayit/kayitlar = save/saves · yuva = save slot · yedek = backup · ayar(lar) = settings · profil = player profile ·
harita = map · dunya = map world (`dunya.py`) **or** World Editor overlay (`dunyalar/`, `veri.py`) · veri = data ·
yama = patch · uzayli = alien/NPC · kapi = gate · etkinlik = event · gorev = quest · magaza = shop · sohbet = chat ·
istemci = client · sunucu = server · surec = process · oturum = session · anahtar = key · sifre = password ·
surum = version · misafir = guest · arkadas = friend (Host/Join) · cok_oyunculu = friend/multi-session server mode ·
coklu = multi-client · yerel = local · kilit = lock · guncelleme = update · gunluk = log **or** daily (`gunluk_odul`) ·
eski = legacy · tohum = seed · taslak = draft · eklenti = plugin · arayuz = UI · dil = language · baslat/durdur = start/stop ·
yonetici = manager · firma = company (faction) · canli = live · hata = error · yollar = paths
