"""Sohbet moderatörleri (oyuncu isteği 2026-10-31): paketin ayarlarında açılır; sabırlı, yardımsever, sadık birkaç bot moderatördür
(sohbette rolü "mod": istemci moderatör rengiyle çizer). Kurallar panelde açılıp kapanır: BÜYÜK HARF, sel (aynı satır ya da çok hızlı),
hakaret ve zararlı söz, reklam/bağlantı. Kuralı çiğneyen (insan ya da bot; yönetici ve moderatörler hariç) önce uyarılır, 30 dk
içinde yine çiğnerse sustur_dk susturulur, yasak_esik susturmadan sonra yasak_saat global ve firma sohbetinden yasaklanır. Kararı
ancak çevrimiçi bir moderatör verir (gerçek sunucudaki gibi; kimse yoksa sohbet serbest), birkaç saniye sonra kanala yazar.
Susturulanın global/firma mesajı sohbet sunucusunda düşer (sohbet.Sohbet.engel), kendisine kalan süre sistem mesajıyla bildirilir.
"""
import math
import re
import time

from . import konusma as KN

KURALLAR = ('buyuk', 'sel', 'hakaret', 'reklam')
ETIKET = 'CM'                    # moderatörün sohbette ve gemisinin üstünde gösterilen etiketi (klanlar alamaz: klan.ayrilmis)
SOHBET_ROLU = 'mod'              # istemci yamasıyla kendi renginde (panel/eklenti/Yamalar.cs ModeratorRengi); admin rolü etiketi gizlerdi
UYARI_SN = 1800                  # uyarıdan sonra bu süre içindeki ikinci ihlal susturur
_BAGLANTI = re.compile(r'(https?://|www\.|discord\.gg|\b[\w-]+\.(com|net|org|gg|io|ru|tr|de)\b)', re.I)
KANALLAR = ('global', 'firma')
BILDIRIM = {'tr': 'Susturuldun: {0} dk kaldı.', 'en': 'You are muted: {0} min left.', 'de': 'Du bist stummgeschaltet: noch {0} Min.',
            'es': 'Estás silenciado: quedan {0} min.', 'fr': 'Tu es muet : encore {0} min.', 'pl': 'Jesteś wyciszony: zostało {0} min.',
            'pt': 'Você está silenciado: faltam {0} min.', 'ru': 'Вы заглушены: осталось {0} мин.'}


def acik(y):
    return bool(y.ayar('moderator', False)) and y.izin('sohbet')


def sec(y):
    """Moderatörleri seç (kalıcı: aynı paket hep aynı botları): sabır, yardımseverlik ve sadakati en yüksek, saldırganlığı düşük."""
    for b in y.botlar:
        b.moderator = False
    if not acik(y):
        return []
    n = int(y.ayar('mod_sayisi', 2) or 1)
    puan = lambda b: b.o('sabir') + b.o('yardimseverlik') + b.o('sadakat') - b.o('saldirganlik') + 0.001 * (b.uid % 97)
    out = sorted(y.botlar, key=puan, reverse=True)[:n]
    for b in out:
        b.moderator = True
    return out


def _kayit(y, ad):
    return y.__dict__.setdefault('mod_kayit', {}).setdefault(str(ad).lower(), {'uyari': 0, 'uyari_t': 0, 'susturma': 0, 'bitis': 0,
                                                                               'yasak': False, 'son': []})


def ihlal(y, ad, msg, now):
    """Mesaj hangi kuralı çiğniyor -> kural ya da None (açık kurallardan ilki). Sel için kişinin son mesajlarını tutar."""
    k = _kayit(y, ad)
    k['son'] = [x for x in k['son'] if now - x[0] < 60] + [(now, str(msg).strip().lower())]
    harf = [c for c in str(msg) if c.isalpha()]
    if y.ayar('kural_reklam', True) and _BAGLANTI.search(msg):
        return 'reklam'
    if y.ayar('kural_hakaret', True):
        from . import llm as LLM
        if LLM.zararli(msg) or KN.niyet(msg)[0] == 'hakaret':
            return 'hakaret'
    if y.ayar('kural_sel', True) and (sum(1 for t, m in k['son'] if m == k['son'][-1][1]) >= 3
                                       or sum(1 for t, m in k['son'] if now - t < 10) >= 5):
        return 'sel'
    if y.ayar('kural_buyuk', True) and len(harf) >= 8 and sum(c.isupper() for c in harf) / len(harf) > 0.7:
        return 'buyuk'
    return None


def susturulu(y, ad, now=None):
    """Kalan susturma/yasak süresi (sn) ya da 0."""
    k = y.__dict__.get('mod_kayit', {}).get(str(ad).lower())
    return max(0.0, k['bitis'] - (now or time.time())) if k else 0.0


def denetle(y, ad, msg, kanal, now, rol='chatter'):
    """Global/firma sohbetindeki satır (insanın ya da botun): kural çiğnendiyse çevrimiçi bir moderatör yaptırımı uygular ->
    yaptırım ('uyari' | 'sustur' | 'yasak') ya da None."""
    if not acik(y) or kanal not in KANALLAR or rol in ('admin', 'mod', 'system'):
        return None
    b = y.ada.get(str(ad).lower())
    if b is not None and getattr(b, 'moderator', False):
        return None
    import yonetici_modu as YM
    if b is None and YM.mi(ad_=ad):
        return None
    kural = ihlal(y, ad, msg, now)
    modlar = [m for m in y.botlar if getattr(m, 'moderator', False) and m.cevrimici]
    if kural is None or not modlar:
        return None
    m = max(modlar, key=lambda m: m.o('sabir') * m.r.random())
    k = _kayit(y, ad)
    if k['bitis'] > now:
        return None                                       # zaten susturulu (satırı zaten düştü)
    if now - k['uyari_t'] > UYARI_SN:
        k['uyari'] = 0
    gecikme = m.r.uniform(2, 8)
    if k['uyari'] == 0:
        k['uyari'], k['uyari_t'] = 1, now
        y.konus(m, kanal, KN.kalip(m, 'mod_uyari_' + kural, ad=ad), now=now + gecikme, oncelik=True)
        return 'uyari'
    k['uyari'] = 0
    k['susturma'] += 1
    if k['susturma'] >= int(y.ayar('yasak_esik', 3) or 3):
        saat = int(y.ayar('yasak_saat', 24) or 24)
        k['bitis'], k['yasak'], k['susturma'] = now + saat * 3600, True, 0
        y.konus(m, kanal, KN.kalip(m, 'mod_yasak', ad=ad, saat=saat), now=now + gecikme, oncelik=True)
        return 'yasak'
    dk = int(y.ayar('sustur_dk', 10) or 10)
    k['bitis'], k['yasak'] = now + dk * 60, False
    y.konus(m, kanal, KN.kalip(m, 'mod_sustur', ad=ad, dk=dk), now=now + gecikme, oncelik=True)
    if b is not None:
        b.hafiza.olay(m.ad, 'hakaret', now)               # susturulan bot moderatöre biraz kırgın
    return 'sustur'


def engel(y, user, path, dil=None):
    """Sohbet sunucusundan (sohbet iş parçacığı): insanın global/firma mesajı düşsün mü -> oyuncuya bildirim metni ya da None."""
    if not acik(y) or not (path.startswith('/room/global/') or path.startswith('/room/faction/')):
        return None
    kalan = susturulu(y, user.get('userId', ''))
    if kalan <= 0:
        return None
    return BILDIRIM.get(dil or 'en', BILDIRIM['en']).format(max(1, math.ceil(kalan / 60)))


def kurallari_hatirlat(y, now):
    """Arada (45-90 dk) bir moderatör globalde kuralları hatırlatır."""
    if not acik(y) or now < y.__dict__.get('_mod_hatirlat', 0):
        return
    ilk = '_mod_hatirlat' not in y.__dict__
    y._mod_hatirlat = now + (600 if ilk else 2700 + 2700 * (hash(int(now)) % 100) / 100)
    if ilk:
        return
    modlar = [m for m in y.botlar if getattr(m, 'moderator', False) and m.cevrimici]
    if modlar:
        m = modlar[int(now) % len(modlar)]
        y.konus(m, 'global', KN.kalip(m, 'mod_kurallar'), now=now)
