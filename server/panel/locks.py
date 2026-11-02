"""Save locks shared by the panel and OrbitBot: in each save slot folder, panel.lock (the slot the panel uses) and orbitbot.lock (the bot's).
A lock is JSON: pid, since (epoch seconds) and info fields. It counts only if it can be read and its pid is alive (a crashed process's
lock does not count). Touches nothing that goes to the server or the client.

OrbitBot (../OrbitBot) checks that this file exists to know the panel honours its locks: don't rename or move it."""
import json, os, re, threading, time

PANEL_LOCK = 'panel.lock'
BOT_LOCK = 'orbitbot.lock'
INTERVAL_SEC = 2


def pid_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def bot_using(slot_dir):
    """Is there a live orbitbot.lock in the slot folder."""
    data = _read(os.path.join(slot_dir, BOT_LOCK))
    return bool(data) and pid_alive(data.get('pid'))


def bot_slot(saves_dir, slot):
    """bot_using by slot id: False for an invalid id (so SAV.in_use never raises)."""
    if not slot or not isinstance(slot, str) or not re.fullmatch(r'[a-z0-9_]{1,40}', slot):
        return False
    return bot_using(os.path.join(saves_dir, slot))


def _write(path, data):
    tmp = path + '.%d.tmp' % os.getpid()
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(tmp, path)


def panel_locks(saves_dir, used):
    """used: slot -> {'what': 'play'|'join'|'host'|'extra', 'address': 'host:port' or None}. panel.lock is written in those slots (the
    first write's 'since' is kept); this process's panel.lock in the other slots is removed."""
    pid = os.getpid()
    try:
        names = os.listdir(saves_dir)
    except OSError:
        return
    for name in names:
        folder = os.path.join(saves_dir, name)
        path = os.path.join(folder, PANEL_LOCK)
        if not os.path.isdir(folder):
            continue
        old = _read(path)
        mine = bool(old) and old.get('pid') == pid
        try:
            if name in used:
                u = used[name]
                since = old.get('since') if mine and isinstance(old.get('since'), (int, float)) else int(time.time())
                data = {'pid': pid, 'since': since, 'what': u.get('what'), 'address': u.get('address')}
                if not mine or any(old.get(k) != data[k] for k in ('what', 'address')):
                    _write(path, data)
            elif mine:
                os.remove(path)
        except OSError:
            pass


def used_slots(manager, friend, multi):
    """The slots the panel uses right now: the game / Host (manager), the slot on the friend's server it joined (friend), extra clients
    (multi)."""
    u = {}
    for slot in multi.live():
        u[slot] = {'what': 'extra', 'address': None}
    if manager.running() and manager.slot:
        u[manager.slot] = {'what': 'host' if manager.friend else 'play', 'address': None}
    if friend.active() and friend.m.get('record'):
        u[friend.m['record']] = {'what': 'join', 'address': friend.m.get('address')}
    return u


def start(saves_dir, manager, friend, multi, log=None):
    """Background thread that refreshes the locks every INTERVAL_SEC."""
    def loop():
        while True:
            try:
                panel_locks(saves_dir, used_slots(manager, friend, multi))
            except Exception as e:
                if log:
                    log('save locks error: %s' % e)
            time.sleep(INTERVAL_SEC)
    threading.Thread(target=loop, daemon=True).start()


def remove(saves_dir):
    """Removes all of this process's panel.lock files when the panel exits."""
    panel_locks(saves_dir, {})
