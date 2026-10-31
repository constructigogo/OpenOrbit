"""Botların anı defteri (Gelişmiş kip, güçlü sağlayıcı: llm.GUCLU): kişilerle yaşanan önemli olaylar kısa notlar olarak, kayıtta kalıcı.

Generative Agents (Park ve ark. 2023) düzeni: anı akışı (önem x tazelikle seçilir), kişi başına izlenim (yansıma) ve anılardan doğan
sonuçlar (takip). Kayıtta:
  k['anilar']   [{t, kim, ozet, tur, duygu (-1..1), onem (1-3), n, takip}]; ozet modele giden İngilizce not ("Kaan shot me down on 2-4")
  k['izlenim']  {kim_kucuk: {ad, metin, t}}: kişi hakkında yoğun kanı (konuşma özetiyle model günceller)
takip: {amac (soz | intikam | tesekkur | rekabet | merak), vade (an), arac (yok | takip_et | grup_davet | duello | yardima_git), harita,
bitti}. Vakti gelen ve iki taraf da çevrimiçiyse llm.Beyin botun ağzından konuyu açar, aracı çalıştırır (vadesi_gelenler).

Kaynaklar: oyunun olayları (Hafiza.olay -> olaydan, şablonla; yalnız gerçek oyuncularla), konuşma sonunda modelin özeti (llm._ani_ozet)
ve botlar arası dedikodu (duydum). Botlarla bot arasındaki olaylar anı olmaz (çok olur, oyuncu görmez).
"""
import time

EN_COK = 60                      # bot başına anı (en az değerli olan düşer)
BIRLESTIR_SN = 1800              # aynı kişiyle aynı türden olay bu süre içinde tekrarlanırsa sayılır ("x3")
GECERLI_SN = 6 * 3600            # takibin vadesi geçince bu kadar bekler (kişi çevrimiçi olmadıysa unutulur)
AMACLAR = ('soz', 'intikam', 'tesekkur', 'rekabet', 'merak')
TAKIP_ARACLARI = ('yok', 'takip_et', 'grup_davet', 'duello', 'yardima_git')

# oyun olayı -> (not, tür, duygu, önem); {ad} oyuncu
SABLON = {
    'oldurdu_beni': ('{ad} shot me down', 'savas', -0.6, 2),
    'oldurdum': ('I shot down {ad}', 'savas', 0.2, 1),
    'yardim_etti': ('{ad} came to help me', 'yardim', 0.6, 2),
    'yardim_ettim': ('I flew over to help {ad}', 'yardim', 0.3, 1),
    'grup': ('grouped up with {ad}', 'grup', 0.3, 1),
    'hakaret': ('{ad} insulted me', 'hakaret', -0.4, 1),
    'meydan': ('{ad} challenged me to a duel', 'savas', 0.0, 2),
    'arkadas': ('became friends with {ad}', 'dost', 0.6, 2),
    'klan': ('{ad} and I ended up in the same clan', 'dost', 0.4, 2),
}


def anilar(b):
    return b.k.setdefault('anilar', [])


def izlenimler(b):
    return b.k.setdefault('izlenim', {})


def _deger(a, now):
    """Anının ağırlığı: önem x tazelik (yarı ömür bir gün; tekrar eden olay biraz daha ağır)."""
    return a['onem'] * (1 + 0.15 * min(5, a.get('n', 1) - 1)) * 0.5 ** (max(0, now - a['t']) / 86400)


def ekle(b, kim, ozet, tur='not', duygu=0.0, onem=1, now=None, takip=None, birlestir=True):
    """Anı ekle; aynı kişiyle aynı türden yakın olay sayılır. -> anı."""
    now = now if now is not None else time.time()
    la = anilar(b)
    k = str(kim).lower()
    if birlestir:
        for a in reversed(la):
            if a['kim'].lower() == k and a['tur'] == tur and a['ozet'] == ozet and now - a['t'] < BIRLESTIR_SN:
                a['n'] = a.get('n', 1) + 1
                a['t'] = now
                if takip and not a.get('takip'):
                    a['takip'] = takip
                return a
    a = {'t': now, 'kim': str(kim), 'ozet': str(ozet)[:200], 'tur': tur, 'duygu': round(max(-1.0, min(1.0, float(duygu))), 2),
         'onem': max(1, min(3, int(onem))), 'n': 1, 'takip': takip}
    la.append(a)
    if len(la) > EN_COK:
        acik = [x for x in la if x.get('takip') and not x['takip'].get('bitti')]
        aday = [x for x in la if x not in acik] or la
        la.remove(min(aday, key=lambda x: _deger(x, now)))
    return a


def ne_zaman(dt):
    dt = max(0, dt)
    if dt < 120:
        return 'just now'
    if dt < 3600:
        return '%d min ago' % (dt // 60)
    if dt < 86400:
        return '%d h ago' % (dt // 3600)
    return '%d days ago' % (dt // 86400)


def _satir(a, now):
    return '%s (%s%s)' % (a['ozet'], ne_zaman(now - a['t']), ', x%d' % a['n'] if a.get('n', 1) > 1 else '')


def hatirla(b, kim, now, n=6):
    """Kişiyle en değerli n anı, eskiden yeniye."""
    k = str(kim).lower()
    la = [a for a in anilar(b) if a['kim'].lower() == k]
    return sorted(sorted(la, key=lambda a: -_deger(a, now))[:n], key=lambda a: a['t'])


def metin(b, kim, now):
    """İsteme: kişi hakkındaki izlenim ve anılar (yoksa '')."""
    out = ''
    iz = izlenimler(b).get(str(kim).lower())
    if iz and iz.get('metin'):
        out += ' Your impression of %s: %s.' % (iz['ad'], iz['metin'].rstrip('.'))
    la = hatirla(b, kim, now)
    if la:
        out += ' Your memories with %s: %s.' % (la[-1]['kim'], '; '.join(_satir(a, now) for a in la))
    acik = [a['takip'] for a in la if a.get('takip') and not a['takip'].get('bitti')]
    if acik:
        out += ' Still pending with him: %s.' % ', '.join(AMAC_AD[t['amac']] for t in acik)
    return out


AMAC_AD = {'soz': 'a plan you agreed on', 'intikam': 'you want revenge', 'tesekkur': 'you owe him thanks', 'rekabet': 'a rivalry',
           'merak': 'something you wanted to ask him'}


def onemli(b, now, n=3, insanlar=None):
    """Botun en değerli anıları (kişi fark etmeksizin; insanlar verilirse yalnız onlarla)."""
    la = [a for a in anilar(b) if insanlar is None or a['kim'].lower() in insanlar]
    return sorted(la, key=lambda a: -_deger(a, now))[:n]


def izlenim_yaz(b, kim, metin_, now):
    if metin_ and str(metin_).strip():
        izlenimler(b)[str(kim).lower()] = {'ad': str(kim), 'metin': str(metin_).strip()[:240], 't': now}


def takip_kur(amac, now, dakika=10, arac='yok', harita=''):
    if amac not in AMACLAR:
        return None
    return {'amac': amac, 'vade': now + max(1, min(240, int(dakika or 10))) * 60, 'arac': arac if arac in TAKIP_ARACLARI else 'yok',
            'harita': str(harita or '')[:8], 'bitti': False}


# ------------------------------------------------------------------------------------------------------------ oyun olayları
def insan_mi(y, ad):
    """Gerçek oyuncu mu (bot ya da uzaylı değil)."""
    if not ad or str(ad).lower() in getattr(y, 'ada', {}):
        return False
    try:
        import topluluk as TP
        return TP.bul(ad=ad) is not None
    except Exception:
        return False


def olaydan(y, b, ad, tur, now=None):
    """Hafiza.olay'ın kancası: oyuncuyla yaşanan önemli olay anı olur; bazıları sonuç doğurur (intikam, teşekkür)."""
    from . import llm
    if not llm.GUCLU or tur not in SABLON or not insan_mi(y, ad):
        return None
    now = now if now is not None else y.now
    ozet, t, duygu, onem = SABLON[tur]
    a = ekle(b, ad, ozet.format(ad=ad), t, duygu, onem, now)
    if a.get('takip'):
        return a
    if tur == 'oldurdu_beni' and a['n'] >= 2 and b.o('saldirganlik') > 0.45 and _firma(ad) not in (0, b.firma) and b.izin.get('pvp', True):
        a['takip'] = takip_kur('intikam', now, b.r.uniform(3, 15), 'duello')             # iki kez vurduysa: intikam
    elif tur == 'yardim_etti' and b.r.random() < 0.4 + 0.5 * b.o('sosyallik'):
        a['takip'] = takip_kur('tesekkur', now, b.r.uniform(2, 8))
    elif tur == 'hakaret' and a['n'] >= 2 and b.o('rekabet') > 0.5:
        a['takip'] = takip_kur('rekabet', now, b.r.uniform(5, 30))
    return a


def _firma(ad):
    try:
        import topluluk as TP
        k = TP.bul(ad=ad)
        return int(k.profil.d['pilot'].get('factionId', 0)) if k is not None else 0
    except Exception:
        return 0


def vadesi_gelenler(y, now, cevrimici):
    """[(bot, anı)]: vakti gelmiş, bitmemiş takipler (bot ve kişi çevrimiçi). Süresi çok geçenler bitti sayılır."""
    out = []
    for b in y.botlar:
        for a in anilar(b):
            t = a.get('takip')
            if not t or t.get('bitti') or now < t['vade']:
                continue
            if now - t['vade'] > GECERLI_SN:
                t['bitti'] = True                         # fırsat kaçtı
                continue
            if b.cevrimici and b.olu_bitis <= now and a['kim'].lower() in cevrimici:
                out.append((b, a))
    return out


# ------------------------------------------------------------------------------------------------------------ dedikodu
def dedikodu_sec(b, now, r):
    """Botların kendi sohbetinde anlatılacak bir oyuncu anısı (önemli, bir günden taze) ya da None."""
    la = [a for a in anilar(b) if a['onem'] >= 2 and now - a['t'] < 86400 and a['tur'] != 'duydum']
    return r.choice(la) if la else None


def duydu(dinleyen, anlatan, a, now):
    """Dedikoduyu duyan bot: kişiye ilişkisi hafifçe değişir, düşük önemli "duydum" anısı."""
    dinleyen.hafiza.olay(a['kim'], 'dedikodu_iyi' if a['duygu'] > 0.1 else 'dedikodu_kotu' if a['duygu'] < -0.1 else 'sohbet', now)
    ekle(dinleyen, a['kim'], 'heard from %s: %s' % (anlatan.ad, a['ozet']), 'duydum', a['duygu'] * 0.5, 1, now)
