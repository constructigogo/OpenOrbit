"""Gerçek oyuncu adları: dostats.info (oyuncu isteği 2026-10-31). Panelde ad kaynağı "DOStats" seçilince kadro adları gerçek
sunuculardaki oyuncuların adlarından alınır (dilin sunucularından: tr -> Turkey 3/4/5 ...); adların sonundaki [KLAN] etiketleri bot
klanlarının etiket havuzu olur. Sayfalar sunucu tarafında çizilen tablolar: /rank-changes, /hall-of-fame, /hall-of-gates
(?server=<kod>&gate=<kapı>); oyuncu bağlantısı <a href="/player/<kimlik>">ad</a>. Önbellek save/botlar/_dostats.json (7 gün).
"""
import html
import json
import os
import re
import time
import urllib.request

ADRES = 'https://dostats.info'
SUNUCULAR = {'tr': ('tr3', 'tr4', 'tr5'), 'de': ('de2', 'de4'), 'pl': ('pl3',), 'ru': ('ru1', 'ru5'), 'es': ('es1', 'mx1'),
             'fr': ('fr1',), 'pt': ('int2', 'int6'), 'en': ('int1', 'int5', 'int7', 'int11', 'int14', 'gbl3', 'gbl4', 'gbl6', 'us2')}
SAYFALAR = ('/rank-changes?server=%s', '/hall-of-fame?server=%s', '/hall-of-gates?server=%s&gate=Hades',
            '/hall-of-gates?server=%s&gate=Kappa')
ONBELLEK_SN = 7 * 86400
_OYUNCU = re.compile(r'<a[^>]+href="/player/[^"]+"[^>]*>(.*?)</a>', re.S)
_ETIKET = re.compile(r'\[([^\[\]]{1,4})\]$')


def ayikla(sayfa):
    """Sayfanın HTML'i -> oyuncu adları (sırayla, tekrarsız)."""
    out = []
    for a in _OYUNCU.findall(sayfa):
        ad = html.unescape(re.sub(r'<[^>]+>', '', a)).strip()
        if ad and ad not in out:
            out.append(ad)
    return out


def _indir(yol, zaman_asimi=15):
    rq = urllib.request.Request(ADRES + yol, headers={'User-Agent': 'Mozilla/5.0 (OpenOrbit bot names)'})
    with urllib.request.urlopen(rq, timeout=zaman_asimi) as f:
        return f.read().decode('utf8', 'replace')


def _onbellek_yolu():
    import yollar as YOL
    return os.path.join(YOL.SAVE, 'botlar', '_dostats.json')


def adlar(diller, indir=None):
    """{dil: [ad]} (önbellekten ya da siteden; indir verilirse önbelleksiz, testler). Ulaşılamayan sayfa atlanır; hiç ad gelmezse
    OSError."""
    from .kisilik import AD_DESEN
    yol = _onbellek_yolu() if indir is None else None
    kayit = {}
    if yol:
        try:
            with open(yol, encoding='utf8') as f:
                kayit = json.load(f)
        except (OSError, ValueError):
            kayit = {}
    out, degisti, hata = {}, False, None
    for dil in diller:
        if dil not in SUNUCULAR:
            continue
        x = kayit.get(dil)
        if not x or time.time() - x.get('t', 0) > ONBELLEK_SN:
            liste = []
            for s in SUNUCULAR[dil][:1 if len(diller) > 1 else None]:      # karışık: dil başına bir sunucu (panel beklemesin)
                for sayfa in SAYFALAR:
                    try:
                        liste += [a for a in ayikla((indir or _indir)(sayfa % s)) if a not in liste]
                    except (OSError, ValueError) as e:
                        hata = e
            if liste:
                x = kayit[dil] = {'t': time.time(), 'adlar': liste}
                degisti = True
        if x:
            out[dil] = [a for a in x['adlar'] if AD_DESEN.match(a)]
    if degisti and yol:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol + '.tmp', 'w', encoding='utf8') as f:
            json.dump(kayit, f, ensure_ascii=False)
        os.replace(yol + '.tmp', yol)
    if not any(out.values()):
        raise OSError('dostats.info: %s' % (hata or 'ad yok'))
    return out


def etiketler(havuz):
    """Adların sonundaki klan etiketleri ("SILNY[DZL]" -> "DZL"), oyunun etiket kuralına uyanlar."""
    out = []
    for liste in havuz.values():
        for a in liste:
            m = _ETIKET.search(a)
            t = m.group(1).strip() if m else ''
            if t and all(c.isalnum() or c in '-_.!?*+' for c in t) and t not in out:
                out.append(t)
    return out
