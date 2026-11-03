# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

OpenOrbit is an offline private server for the original DarkOrbit Unity client 1.1.116, plus a desktop panel that runs it.
It is pure Python 3.10+ and uses only the standard library (`pyproject.toml` has no dependencies). The only optional extra
is `capstone`, needed by `tools/il2cpp/` for porting the protocol to a new client. The client lives in a sibling folder,
`../DarkOrbit_Version1.1.116/`. Never modify it, and never run its `DarkorbitLauncher.exe`, which can update it from the
official servers.

## Commands

- Panel (the normal entry point): double-click `OpenOrbit Panel.pyw`, or run `python "OpenOrbit Panel.pyw"`. It runs
  `server/panel/panel.py` at 127.0.0.1:8077 inside an Edge/Chrome app window. Pass `--no-window` to skip opening the
  window (`--pencere-yok` still works). A second launch only reopens the window.
- Servers without the panel (developer fallback): `python -I server/launcher.py [game options]`. It starts `web.py` and
  `game.py`, then the client.
- Run a single server: `python -I server/game.py <log_dir> [--profile=<path>] [--settings=<path>] [--control] [--invulnerable] …`
  or `python -I server/web.py <log_dir> [--profile=<path>]`. The docstring at the top of each file lists every flag.
- Tests use **unittest** (no pytest config). Run them from the repo root:
  `python -m unittest discover -s tests -v`. To run one test, add `-k <name_substring>`.
  The suite is only the fork's 6 save-lock tests in `tests/test_orbitbot_locks.py`. They are fast and bind no ports.
  Upstream ships no tests.
- Translations: `python server/panel/lang.py <code>` lists the panel strings still missing for that language.
- Protocol port to a new client: `python -I tools/il2cpp/protocol_update.py …` (the panel's Client page runs it).

## Architecture

The panel is a process manager. `server/panel/processes.py` spawns each server as its own windowless `python -I`
subprocess and writes its output to `server/logs/<name>_console.log`.

| Process / port | Role |
| --- | --- |
| `panel/panel.py` 8077 | Local web UI (`panel/ui/index.html` + JS) and JSON `/api/...` (needs the `X-Panel-Token` header) |
| `web.py` 8090, 80 (+ dummy 843/9339/8082) | Fakes the client's web login (`links.php`, `login.php`, `maps.php`, unityApi) |
| `game.py` 8081 | The game server: TCP libcom protocol, one `Session` per connection, `on_packet` dispatch |
| `chat.py` 7771 | Chat, runs inside the game process |
| `control.py` 8099 | Live-test control channel, only with `--control`. JSON lines `{command, ...}`: trace, inject requests, run `py` in-process |
| `panel_channel.py` 8098 | The panel's in-game Shop/Hangar/Skylab/Auction. Requests are replayed through `on_packet`, so game rules apply |
| `payment.py` 127.0.0.1:443 | Catches the client's real-money "Buy" buttons and opens the in-game shop |

- **`server/` is a flat script directory, not a package.** Modules do `sys.path.insert(0, HERE)` and import siblings by
  bare name (`import protocol as P`, `import paths as PTH`). Keep server code stdlib-only.
- **Protocol:** `server/protocol.py` is the runtime codec: framing, LZ4 "DOB3"/"DOL4" downstream compression,
  `encode_message`/`messages`. It is driven by `server/data/protocol_read.json` and `protocol.json`, which are extracted
  from the client's IL2CPP code by `tools/il2cpp/read_spec.py` and `tools/il2cpp/protocol.py`. Two different files are
  named `protocol.py`: don't confuse them. `legacy_protocol.py` is the legacy Flash-era text protocol (`0|LM|ST|…`), still
  carried inside `LegacyModule`. Generated protocol versions go in `server/data/protocols/`, which is gitignored.
- **Game:** `game.py` is the entry point and the session logic. `world.py` (the largest file) is the per-connection map
  world: NPCs, AI, combat, boxes and ores; `alien.py` holds the aliens' abilities and `map_links.py` the maps, gates and
  level limits. Feature systems (galaxy gates `galaxy_gates.py`, events `event_*.py`, shop `shop.py`, quests `quest.py`,
  Skylab, Assembly, clans, PET, …) are one module each. `server/bot/` holds the in-server bot players ("Bots (Beta)", packs
  in `save/bots/`, passed in via `OO_BOT`). Those are separate from the external OrbitBot.
- **Profile = protocol:** `player_profile.py` keeps field names identical to the protocol's, so the profile turns directly
  into login messages. The game autosaves `profile.json` every 10 s and also on the `--stop-file=<file>` stop signal.
- **Data and worlds:** static game data is in `server/data/*.json`, plus the client's `spacemap-config.xml` and
  `maps-config.xml`. `game_data.py` overlays the selected World Editor world (`save/worlds/<id>.json`, JSON-Pointer patches,
  `{"$delete": true}` deletes, picked via `OO_WORLD`). Only files marked live reload while the game runs. Settings are in
  `settings.py`, where `SCHEMA` is the single definition the panel UI is built from. Each setting's `apply_mode` says when
  it takes effect: instantly, on map change, on login, or on restart.
- **Paths** (`paths.py`): `server/save/slots/<slot>/{profile.json, slot.json, settings.json, web_settings.json,
  edit_base.json, backups/}`, `server/save/panel.json` (the `active_save` key is the active slot), `server/logs/`.
  `OO_SAVE_DIR` and `OO_LOG_DIR` override the save and log dirs; tests use these. `server/save/` and `server/logs/` are
  gitignored user data.
- **Save format v3 and migration** (`save_migration.py`, `server/migration_map.json`): the code base and the saves were
  Turkish until 2026-11-01. Importing `paths.py` runs `save_migration.ensure(SAVE, DATA)`: a v1/v2 save tree
  (`save/kayitlar/<slot>/profil.json`, `kayit.json`, `yedek/oto_*`, Turkish keys and values) is backed up to
  `save/v1_backup_*.zip`, then moved and rewritten to v3 (`format.json` stamps it), under a lock; the personal templates and
  `data/protokol/` in `server/data` move too. **Every process that imports `paths`, even indirectly** (`quest`, `ranks`,
  `multiplayer`, `panel/client.py` …), **migrates the real `server/save` unless `OO_SAVE_DIR` points elsewhere.** A failure
  is kept in `paths.MIGRATION_ERROR` and stops the servers. `migration_map.json` is the one table of old -> new keys.
- **Multiplayer** (`multiplayer.py`): `game.py --multiplayer`, configured through the `OO_MULTIPLAYER` JSON env var
  (`{guest, password, max_count, key, code, address, local}`, kept off the command line on purpose).
  - **Host** (`panel/friends.py`): 8081 and 7771 listen on all interfaces.
  - **Join:** only a local `web.py --remote=<host:8081>` runs, with no local game server. A guest's save lives only in the
    host's memory and is long-polled back to the guest's own slot.
  - **Multi-client** (`panel/multi_client.py`): same mode, localhost only, no guests. Extra local saves are added via
    `/local/add`.
  - Normal maps are shared through `shared_maps.py`. Gates and event maps are per player.
- **The guest/admin HTTP API runs on the game port 8081 itself.** `game.handle` sniffs the first bytes
  (`multiplayer.is_http`: `GET `/`POST`/`HEAD` versus a length prefix). There is no separate HTTP port. The guest paths
  kept their Turkish names (`/misafir/bilgi|giris|profil|cikis`), and so did `/misafir/bilgi`'s `sunucu` and `protokol`
  (old panels negotiate with them); every body field is English.
- **Updater** (`panel/updater.py`): it tracks `kaanumay/OpenOrbit` `main`. A git checkout is updated only by
  `fetch` + `merge --ff-only`. On any other branch, or with local changes, it does nothing except notify.
  `server/surum.txt` (name kept for old updaters) is filled by `export-subst` in ZIP downloads.
- **Client plugin:** `server/panel/plugin/` is a BepInEx 6 C# plugin. The built `OpenOrbitPatch.dll` is committed.

## Gotchas

- **The module docstrings are the design docs** (English since the rename). Read them first. On this Windows console, set
  `PYTHONIOENCODING=utf-8` before printing them. Docstrings cite `belgeler/*.md`, `tools/*.py` data builders and
  `recording/` tools. None of these exist in the repo, so don't go looking for them.
- **Panel UI strings are written in English and wrapped in `_()`.** The English text is the key in
  `server/panel/ui/<code>.json` (de, es, fr, pl, pt, ru, tr; there is no `en.json`). A new string needs entries in
  all 7 files. Missing ones fall back to English.
- **Never write a slot's `profile.json` while that slot is in use**, because the server's autosave overwrites it. The
  panel blocks this through `SAV.in_use`, which in this fork also counts a live `orbitbot.lock`. Edits to a running game
  go through `panel_channel.py`. The character editor works on the `edit_base.json` draft.
- **The game client protocol is fixed by client 1.1.116.** `protocol.CLIENT_HASH` and the extracted specs must match the
  client. Don't hand-edit `protocol_read.json` without regenerating or reviewing it against `tools/il2cpp`.
- **Never run OpenOrbit Python against the real saves by accident.** Set `OO_SAVE_DIR`/`OO_LOG_DIR` to a temp dir (or
  disable `save_migration.ensure`) in any script that imports server modules; see "Save format v3" above.

## This fork and OrbitBot

Remotes: `origin` = constructigogo/OpenOrbit (the fork), `upstream` = kaanumay/OpenOrbit.
- The fork's `main` is upstream `main` plus the OrbitBot lock commits: `server/panel/locks.py`, the hooks in
  `panel.py` (`LCK.bot_slot` in `SAV.in_use` and before launch, extra client, join and restart; `LCK.start` in `main`,
  `LCK.remove` at shutdown), one string in the 7 `ui/*.json` files, and `tests/`. Before 2026-11-02 the module was
  `kilitler.py` with Turkish names.
- `main` is published, so upstream updates arrive by **merging**, not rebasing: `git fetch upstream`,
  `git merge upstream/main`, `git push origin main`. The panel's git updater fetches `origin main` (the fork) and only
  fast-forwards, so it never pulls upstream directly. Keep the fork diff small, since `panel.py` is the conflict hotspot
  (a big upstream rewrite of it: take theirs and re-apply the hooks).

The sibling project `../OrbitBot` (headless bot in C#, a separate repo) depends on these. Don't change them blindly:
- **Files it reads at runtime** (no Python import; the C# port reimplements the codec and map rules):
  - `server/data/protocol_read.json` (message spec) and `server/data/spacemap-config.xml` (map name lines).
  - Travel: `server/data/maps-config.xml` (gates) and `server/data/map_layout.json` (`maps.<id>`: `portals`, `arrival`
    (`"random"` or a spot), `portal_safe`: a map's gate safe-zone radius, and `safe`: its own safe zones, e.g. 5-2's
    pirate base).
  - Quests: `server/data/quests.json` and `quest_extras.json` (`quests`, `max_quests`; per quest `name`, `level`, `kinds`,
    `previous`, `root`, `rewards`, `duration_sec`, `pool.type`, `failed[].type`, `event`, `challenge`), `npc.json` (alien
    spawns: `types.<t>.npc_id`/`name`/`maps`, `maps.<id>.npc[].tip`), `levels.json` (`levels`), plus `gates.json` and
    `event_gates.json` (`gates.<k>.maps`, `name`).
  - Collecting: `server/data/items.json` (`ores`: `kinds`, `prices`, `maps`) and `npc.json`'s cargo and pick-up keys (each
    alien's `cargo` and `extra_reward`, `bonus_boxes`/`bonus_box_4x`, `combat.harvest_distance`, `combat.box_sight`).
    A malformed `items.json` stops every bot.
  - Kiting: `npc.json` (each alien type's `name`, `speed`, `range` and `aggressive`, and the `combat` constants
    `laser_range`, `npc_range`, `npc_fixed_range`) and `items.json` (`lasers`: each laser's `range`). A missing file or key
    reads as empty or the default.
  - Per-alien settings (the Plan tab's Kill, Ammo and Use SAB per alien): `npc.json` `maps.<id>.npc[].tip` -> `types.<tip>.name`
    (the aliens listed for a map, keyed by the full decorated name `world.py` sends as `userName`) and `items.json`
    `laser_ammo` keys (the Ammo list; SAB-50 and the `spacecup_group-*` ammo left out). The reference generator reads the
    single-line `AUTO_AMMO = [...]` in `server/world.py` with a regex (no import): keep it one line.
  - The `CLIENT_HASH = '<32 hex>'` line in `server/protocol.py` and the `SUPPORTED = '<x.y.z>'` line in
    `server/panel/client.py`, both read with a regex: keep them single-line string assignments.
  - `server/data/protocols/version.txt`: the local client version is `client.supported()` rebuilt in C#.
  - Ported by hand, so a change here needs the C# port updated: `protocol.py`'s `FIXES` table, value transforms, the
    `_super` key, framing and LZ4 block format; `map_links`' name parsing, `company()`, `NO_DMZ_MAPS`,
    `DMZ_AFTER_JUMP_SEC`, `EXTRA_NAMES`, `GATES`/`EXTRA_GATES` (keys `target`, `company`, `only_company`, `arrival`, `fee`,
    `low`), `map_size()`, `level_required()` (setting `no_level_limit`), `GATE_PEACE_RADIUS` (with `map_layout`'s
    `gate_peace_radius()` and `safe_zones()`), `giver_dmz()` and `GIVER_PEACE_RADIUS` (the safe zones the bot's kiter keeps
    out of, with `world.in_peace`'s station and layout zones); `quest`'s resolver (`Quests.resolve`, `maps_for`) and
    constants; the pick-up, harvest and ore-sale rules in `world.py` (ranges, view range, own home station only) and
    `player_profile.py`'s `CARGO_ORES`; and the kiting rules: an alien's firing range (`range`, else `npc_range`, else
    `npc_fixed_range` when `speed <= 0`), the laser range (`combat.laser_range` x `lasers.range_factor(ship lasers + drone
    lasers)`, as `world.laser_range`; the bot ignores the Momentum/Stockpile bonus), the engaged alien's chase and fire in
    `world.py` (it re-plans once a second while farther than `min(450, keep + 150)`, flying to `keep` from the hero turned
    by its spread, `near` and `keep` scaled by `min(1, multiplier('npc_range'))`; it fires while the hero is inside its
    range; its damage is flushed at the next whole second, a rocket's lands about 0.8 s after launch), and
    `alien.low_health`'s flee (a low-health alien flies to the edge or corner point farthest from the hero, then parks);
    the ammo rules: `world.menu_action` (an `ammunition_laser_*` select with `actionType` 0 only selects, `1` can start a
    quick-slot attack; it is ignored for the item already selected or a count of 0, and answered by `MenuItemStatusCommand`
    for the old and the new item), `world.ammo_out`/`other_ammo` (with `autoChangeAmmo`, on by default, the server switches
    by itself in `AUTO_AMMO` order, then the other laser ammo by name; otherwise `0|W|L|0|1` with other ammo in hand, bare
    `0|W|L` with none) and `player_profile.use_ammo` (a salvo spends one per ship and drone laser, so a count above 0 but
    short of that passes the select yet can't fire; the bot then gives that ammo up until the next map load). SAB-50
    (`laser_ammo` `multiplier` 0) does no hull damage: the bot never falls back onto it.
  - Protocol fields the C# port parses for kiting: `AttributeShipSpeedUpdateCommand.newSpeed` (the hero's speed),
    `AttackLaserRunCommand` `attackerId`/`targetId` and `AttackHitCommand`'s attacker and victim (who shoots the hero, and
    from how far), and the legacy rocket-launch line `0|v|<launcher>|<target>|...` (`alien.py`). Changing that line's
    field order silently stops the bot's reach learning.
  - For the ammo: the `MenuItemStatusCommand`s nested in the login's `MenuInitializationCommand` (`patch_template` fills
    them) and the later `MenuItemStatusCommand`s, fields `menuItemId`, `selected` and `counterValue` of the
    `ammunition_laser_*` items, and the legacy `0|W|L|0|1` / `0|W|L` lines. It sends `MenuActionRequest {menuItemId,
    actionType: 0, sourceType: 1}` to select a laser ammo, and once more on a normal stop to select the save's join-time
    ammo again (`selected.laser` is saved in the profile).
  - Ship setup (the Plan tab's config and drone formation for roaming, fighting and fleeing): `items.json` `formations`
    (`<loot>.id`, the protocol id), `formation_rules.<loot>.min_drones` and `combat_items.formation` (`cooldown_sec`,
    `cooldown_group`). It switches config with the legacy `LegacyModule {message: "S|CFG|<n>|<heroId>"}`, without the session
    key (`game.py` -> `shop.switch_config`), and reads `0|S|CFG|<n>` as the switch and `0|A|STM|config_change_failed_time` as
    the refusal inside `CONFIG_COOLDOWN_SEC`. It changes formation with `MenuActionRequest {menuItemId: drone_formation_*,
    actionType: 0, sourceType: 1}` and reads `DroneFormationChangeCommand {uid, selectedFormationId}` and the
    `MenuItemCooldownGroupTimerCommand` of the formation group (`cooldownType.typeValue`, `timerState.timerStateValue` 2,
    `maxTime` in ms). A refused formation is silent, so the bot itself never asks for one the save doesn't own or has too few
    drones for. On a normal stop it switches back to the join-time config and formation.
- **Reference generator** `OrbitBot/tools/golden/make_golden.py` (`python -I`) imports `protocol`, `map_links`,
  `settings`, `lasers` and `quest` and loads `server/panel/client.py` by path, with `server/` and `server/panel/` on
  `sys.path`. `quest` and `client` reach `paths.py`, so the generator disables `save_migration.ensure` and sets
  `OO_SAVE_DIR`/`OO_LOG_DIR` to a temp dir first: keep `save_migration` importable on its own (stdlib, no OpenOrbit
  imports) and the other modules free of import side effects beyond reading data files. It reads `server/shop.py`'s
  `CONFIG_COOLDOWN_SEC = <number>` line with a regex (keep it a single-line number at the start of a line) and hashes
  `shop.py` and `client_items.json` for the ship setup reference. After each upstream merge, rerun
  it in OrbitBot: failing reference tests there mean the C# port needs updating.
- **HTTP on 8081:**
  - `/misafir/bilgi`: OrbitBot reads `protokol`, `guest`, `max_count`, `place`, `password` and `client`. It refuses to
    join when `client` is present and differs from its local `supported()` label, the same rule as the panel's JOIN.
  - `/misafir/giris` (`{version, password, key, address, profile}` -> `{session, uid, version, ongoing}`),
    `/misafir/profil` (long poll, query `session, key, version, wait` -> `{version, connected, finished, profile}`) and
    `/misafir/cikis`. Refusals are `{error, message, text, args}`; OrbitBot maps the `error` codes to its own texts.
  - `multiplayer.PROTOCOL` (2) must equal OrbitBot's `GuestApi.Protocol`.
- **Its end-to-end tool** starts `python -I server/game.py <logs> --multiplayer --profile= --settings= --stop-file=`
  (and `--control`) with `OO_SAVE_DIR`, `OO_LOG_DIR` and `OO_MULTIPLAYER` (`{key, guest, address, password, max_count}`)
  on copied v3 saves. Its scenarios send `{command: "py", code}` to `control.py` (answer `{done, result: {value}}`), and the
  snippets rely on `G.CO.GUESTS`, a session's `world`/`profile`/`quest`/`shop`, `world.hurt_hero`, `in_peace`,
  `peace_circle`, `next_setting`, `hero_death`, `ore_fields`, `shop.stats`/`apply_stats`, `ITEMS['speed_diff']`,
  `Quests.accept`/`status`/`NOT_STARTED`, an NPC's `mover`, `effect`, `ab['flee']['state']`, and the settings keys
  `player_damage` and `player_damage_pve`.
- **Save format (v3):**
  - `profile.json`: `pilot.{userName, level, factionId, userId, ep}`, `ship.typeId`, `position.mapId`, `equipment.laser`
    and `drone_equipment` (`[[level, [loot ids]]]`: the kiter's laser range), `gates.voucher`, `quests.{active, done,
    period}`, `selected.laser` (the join-time laser ammo, until the server's menu says); for the ship setup `formations`
    (owned), `formation` (protocol id), `drones` (counted), `items` (id -> loot id) and the active ship's `active_config`,
    `configs.<n>.laser`/`extra` and `drone_config.<n>.<drone>` (lasers `equipment_weapon_laser_*`, repair robots
    `equipment_extra_repbot_*`).
  - `slot.json`: `name`.
  - `backups/auto_YYYYmmdd_HHMMSS.json` backups and `backups/notes.json`.
  - `panel.json`: `active_save`, `backup_count`.
- **Locks** (`locks.py`): `panel.lock` (`{pid, since, what, address}`, `what` play/host/join/extra) and `orbitbot.lock`
  (`{address, pid, since}`) in each slot folder. Each counts only while its pid is alive. The panel rewrites its locks
  atomically every 2 s and removes them on exit. OrbitBot reads `panel.lock`'s `address` and `what` to detect the user's
  own session.
- **OrbitBot detects lock support by checking that `server/panel/locks.py` exists.** Renaming or moving it silently
  disables the integration.
