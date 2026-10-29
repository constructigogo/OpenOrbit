"""Panel ile OrbitBot'un ortak kayıt kilitleri: her kayıt klasöründe panel.lock (panelin kullandığı kayıt) ve orbitbot.lock (botun).
Kilit JSON'dur: pid, since (epoch sn) ve bilgi alanları; yalnız okunabiliyorsa ve pid'i yaşıyorsa geçerlidir (çöken sürecin kilidi sayılmaz).
Sunucuya ya da istemciye giden hiçbir şeye dokunmaz."""
import json, os, threading, time

PANEL_KILIDI = 'panel.lock'
BOT_KILIDI = 'orbitbot.lock'
ARALIK_SN = 2


def pid_yasiyor(pid):
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
            kod = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(kod))) and kod.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _oku(yol):
    try:
        with open(yol, encoding='utf-8') as f:
            veri = json.load(f)
    except (OSError, ValueError):
        return None
    return veri if isinstance(veri, dict) else None


def bot_kullaniyor(slot_dir):
    """Kayıt klasöründe canlı bir orbitbot.lock var mı."""
    veri = _oku(os.path.join(slot_dir, BOT_KILIDI))
    return bool(veri) and pid_yasiyor(veri.get('pid'))


def _yaz(yol, veri):
    gecici = yol + '.%d.tmp' % os.getpid()
    with open(gecici, 'w', encoding='utf-8') as f:
        json.dump(veri, f)
    os.replace(gecici, yol)


def panel_kilitleri(kayitlar_dir, kullanilan):
    """kullanilan: kayıt -> {'ne': 'oyna'|'katil'|'host'|'ek'|'editor', 'adres': 'host:port' ya da None}. Bu kayıtlara panel.lock
    yazılır (ilk yazılışın 'since'i korunur); bu sürecin öteki kayıtlardaki panel.lock'ları kaldırılır."""
    pid = os.getpid()
    try:
        adlar = os.listdir(kayitlar_dir)
    except OSError:
        return
    for ad in adlar:
        klasor = os.path.join(kayitlar_dir, ad)
        yol = os.path.join(klasor, PANEL_KILIDI)
        if not os.path.isdir(klasor):
            continue
        eski = _oku(yol)
        benim = bool(eski) and eski.get('pid') == pid
        try:
            if ad in kullanilan:
                k = kullanilan[ad]
                since = eski.get('since') if benim and isinstance(eski.get('since'), (int, float)) else int(time.time())
                veri = {'pid': pid, 'since': since, 'ne': k.get('ne'), 'adres': k.get('adres')}
                if not benim or any(eski.get(a) != veri[a] for a in ('ne', 'adres')):
                    _yaz(yol, veri)
            elif benim:
                os.remove(yol)
        except OSError:
            pass


def kullanilanlar(yon, ark, cok):
    """Panelin şu an kullandığı kayıtlar: oyun/host (yon), katıldığı sunucudaki kayıt (ark), ek istemciler (cok)."""
    k = {}
    for slot in cok.canli():
        k[slot] = {'ne': 'ek', 'adres': None}
    if yon.running() and yon.slot:
        k[yon.slot] = {'ne': 'host' if yon.arkadas else 'oyna', 'adres': None}
    if ark.aktif() and ark.m.get('kayit'):
        k[ark.m['kayit']] = {'ne': 'katil', 'adres': ark.m.get('adres')}
    return k


def baslat(kayitlar_dir, yon, ark, cok, log=None):
    """Kilitleri ARALIK_SN'de bir tazeleyen arka plan iş parçacığı."""
    def dongu():
        while True:
            try:
                panel_kilitleri(kayitlar_dir, kullanilanlar(yon, ark, cok))
            except Exception as e:
                if log:
                    log('kayıt kilitleri hatası: %s' % e)
            time.sleep(ARALIK_SN)
    threading.Thread(target=dongu, daemon=True).start()


def kaldir(kayitlar_dir):
    """Panel çıkarken bu sürecin tüm panel.lock'larını kaldırır."""
    panel_kilitleri(kayitlar_dir, {})
