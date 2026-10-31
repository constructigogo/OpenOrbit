"""Galaksi Kapıları: üretici (enerji, çekiliş, parça, çarpan) ve kapı koşusu (oyuncunun kuralları ve tabloları: kapi.py,
data/kapilar.json).

  enerji    bonus kutularından ve ödüllerden (resource_extra-energy) gelir; yoksa çekiliş başına 100 U (kapıcı ve zengin botlar)
  çekiliş   olasılıklar oyunun: cephane 67, Xenomit 12, kupon 3, parça 13, Nano Hull 4, günlük diski 1; Alpha/Beta/Gamma'nın
            parçası üçünden birine; kopya parça çarpanı artırır (en çok 5), oyunun "kopya eksiğe" payıyla
  koşu      kapı kurulunca bot (gücü yetiyorsa) kapı haritasına geçer (senin haritandan kalkar); süre ve başarı dalgaların
            uzaylılarından: toplam can / botun hasarı, alınan hasar / botun canı x can hakkı. Başarırsa kapının ödülü ve
            uzaylılarının öldürme ödülleri; başaramazsa kapı (parçalarıyla) kaybolur. Kronos parçası öteki kapılardan.
Durum bot.k['kapi'] = {'parca': {kapı: adet}, 'kurulu': [kapı …], 'carpan': n, 'kronos': adet}.
"""
import json, math, os, random

from . import katalog as K

D = json.load(open(os.path.join(K.HERE, 'data', 'kapilar.json'), encoding='utf8'))
KAPI = D['kapilar']
ABG = ('alpha', 'beta', 'gamma')
SIRA = ('alpha', 'beta', 'gamma', 'lambda', 'hades', 'delta', 'epsilon', 'kappa', 'zeta', 'streuner')
ENERJI = 'resource_extra-energy'
OLASILIK = {c: w for c, w in D['olasilik']}            # 1 cephane, 2 kaynak, 3 kupon, 4 parça, 5 özel, 6 log
_zorluk = {}


def durum(bot):
    return bot.k.setdefault('kapi', {'parca': {}, 'kurulu': [], 'carpan': 0, 'kronos': 0})


def stok(bot):
    from . import silah as SL
    return SL.stok(bot)


def zorluk(kapi):
    """Kapının dalgaları -> ([(dalganın toplam can+kalkanı, aynı anda vuranların saniyede hasarı)], öldürme ödülleri)."""
    if kapi in _zorluk:
        return _zorluk[kapi]
    import ast
    dalgalar = KAPI[kapi].get('dalgalar') or []
    if isinstance(dalgalar, str):
        dalgalar = ast.literal_eval(dalgalar)
    out, odul = [], {}
    for d in dalgalar:
        ehp = dps = 0.0
        for u in d.get('uzaylilar', []):
            n = u.get('adet', 1)
            ehp += n * (u.get('hp', 0) + u.get('kalkan', 0))
            dps += min(n, 2) * u.get('hasar', 0) * K.SAVAS['npc_isabet'] * 0.6 / K.NPC_ARALIK  # oyuncu tek tek çeker, menzilden kaçar
            for k, v in (u.get('odul') or {}).items():
                odul[k] = odul.get(k, 0) + v * n
        out.append((ehp, dps))
    _zorluk[kapi] = (out, odul)
    return _zorluk[kapi]


def tahmin(bot, kapi):
    """Koşu tahmini -> (süre sn, beklenen ölüm sayısı). Kapıda oyuncular en iyi cephanesini kullanır (stoktaki en güçlü x2-x4);
    dalga arasında kalkan dolar ve onarılır."""
    from . import silah as SL
    dalgalar, _ = zorluk(kapi)
    d = bot.deger()
    s = SL.stok(bot)
    carp = max([SL.carpan(c) for c in ('ammunition_laser_ucb-100', SL.MCB50, SL.MCB25, SL.LCB) if s.get(c, 0) > 1000] or [1])
    dps = max(1.0, d['dps'] * carp * 1.15)                 # roketler
    sure = olum = 0.0
    for ehp, gelen in dalgalar:
        t = ehp / dps
        sure += t
        olum += t * gelen / max(1.0, d['ehp'] * 3)
    return sure, olum


# ------------------------------------------------------------------------------------------------------------ üretici
def cekilis(bot, kapi, n):
    """n çekiliş (önce enerji, sonra 100 U) -> yapılan."""
    st = durum(bot)
    s = stok(bot)
    yapilan = 0
    for _ in range(n):
        if s.get(ENERJI, 0) > 0:
            s[ENERJI] -= 1
        elif not bot.ode('U', D['enerji_fiyati'] * bot.oa.carpan('magaza_fiyat')):
            break
        yapilan += 1
        _cek(bot, st, kapi)
        if kapi in st['kurulu'] or (kapi in ABG and all(k in st['kurulu'] for k in ABG)):
            break
    if s.get(ENERJI) == 0:
        s.pop(ENERJI, None)
    if yapilan:
        bot.ist('kapi_cekilis', yapilan)
    return yapilan


def _cek(bot, st, kapi):
    from . import silah as SL
    r = bot.r
    cat = r.choices(list(OLASILIK), weights=list(OLASILIK.values()))[0]
    if cat == 4:
        k = r.choice([x for x in ABG if x not in st['kurulu']] or [kapi]) if kapi in ABG else kapi
        toplam = KAPI[k]['parca']
        var = st['parca'].get(k, 0)
        eksik = (toplam - var) / toplam
        yeni = r.random() < eksik + (1 - eksik) * 0.5 or st['carpan'] >= D['azami_carpan']
        if yeni:
            kazan = 1 + (st['carpan'] if st['carpan'] >= D['azami_carpan'] else 0)
            st['carpan'] = 0 if kazan > 1 else st['carpan']
            st['parca'][k] = min(toplam, var + kazan)
            if st['parca'][k] >= toplam and k not in st['kurulu']:
                st['kurulu'].append(k)
                bot.olay('kapi_kuruldu', kapi=KAPI[k]['ad'])
        else:
            st['carpan'] = min(D['azami_carpan'], st['carpan'] + 1)
        return
    if cat == 1:
        loot, _, adet = r.choice(D['cephane'])
        SL.ekle(bot, loot, adet)
    elif cat == 2:
        bot.k.setdefault('kargo', {})
        bot.k['kargo']['3'] = bot.k['kargo'].get('3', 0) + r.randint(*D['xenomit'])
    elif cat == 3:
        stok(bot)['resource_jumpvoucher'] = stok(bot).get('resource_jumpvoucher', 0) + 1
    elif cat == 6:
        stok(bot)['resource_logfile'] = stok(bot).get('resource_logfile', 0) + 1


def hedef_kapi(bot):
    """Parça toplanacak kapı: kurulmamış ve botun tahminen geçebileceği ilk kapı (oyuncuların sırası: ABG, sonra öteki)."""
    st = durum(bot)
    for k in SIRA:
        if k in st['kurulu'] or KAPI[k].get('uretilmez'):
            continue
        sure, olum = tahmin(bot, k)
        if olum < KAPI[k]['can'] * 1.5:
            return k
    return None


def uretici(bot):
    """Karar anında: enerjisi varsa çeker; kapıcı ve zengin bot uridyumla da (izin 'kapi', 10. seviyeden)."""
    if not bot.izin.get('kapi', True) or bot.seviye < 10:
        return 0
    k = hedef_kapi(bot)
    if not k:
        return 0
    n = stok(bot).get(ENERJI, 0)
    t = bot.o('tutumluluk')
    if bot.o('hirs') + bot.o('rekabet') > 1.1 and bot.k['uridyum'] > D['enerji_fiyati'] * 300 * (1 + 2 * t):
        n += int(bot.k['uridyum'] * 0.15 // D['enerji_fiyati'])
    return cekilis(bot, k, min(n, 200)) if n else 0


# ------------------------------------------------------------------------------------------------------------ koşu
def kosu_sonucu(bot, kapi, rng=random):
    """Koşunun sonucu -> (başardı mı, süre sn)."""
    sure, olum = tahmin(bot, kapi)
    olum = rng.gauss(olum, 0.3 * olum + 0.2)
    return olum < KAPI[kapi]['can'], sure * rng.uniform(1.1, 1.6) + 120


def odullendir(bot, kapi, hiz=1.0):
    """Kapının tamamlama ödülü ve uzaylılarının öldürme ödülleri; Kronos parçası."""
    from . import silah as SL
    o = KAPI[kapi].get('odul') or {}
    if isinstance(o, str):
        import ast
        o = ast.literal_eval(o)
    _, uz = zorluk(kapi)
    bot.odul('gorev', hiz, ep=o.get('ep', 0) + uz.get('ep', 0), onur=o.get('onur', 0) + uz.get('onur', 0),
             uridyum=o.get('uridyum', 0) + uz.get('uridyum', 0), kredi=uz.get('kredi', 0))
    for loot, n in (o.get('cephane') or {}).items():
        SL.ekle(bot, loot, n)
    if o.get('xenomit'):
        bot.k.setdefault('kargo', {})
        bot.k['kargo']['3'] = bot.k['kargo'].get('3', 0) + o['xenomit']
    s = stok(bot)
    for loot, n in (('resource_logfile', o.get('log_disk', 0)), ('resource_jumpvoucher', o.get('kupon', 0)),
                    ('resource_booty-key', (o.get('ganimet') or {}).get('yesil_anahtar', 0))):
        if n:
            s[loot] = s.get(loot, 0) + n
    st = durum(bot)
    if kapi != 'kronos':
        st['kronos'] = min(KAPI['kronos']['parca'], st['kronos'] + 1)
        if st['kronos'] >= KAPI['kronos']['parca'] and 'kronos' not in st['kurulu']:
            st['kurulu'].append('kronos')
    if kapi not in st.setdefault('tamam', []):
        st['tamam'].append(kapi)                      # kapı halkası (gorunum.halkalar)
    bot.ist('kapi_tamam')
    bot.olay('kapi_tamam', kapi=KAPI[kapi]['ad'])


def sure_yaz(kayit, key, sn):
    """Kapının tamamlanma süresi (istatistik; oyuncu isteği 2026-10-30) -> kayit['kapi_sureleri'][key] {en_iyi, son, sayi} (sn)."""
    d = kayit.setdefault('kapi_sureleri', {}).setdefault(key, {'en_iyi': 0, 'son': 0, 'sayi': 0})
    sn = int(max(1, sn))
    d.update(son=sn, sayi=d['sayi'] + 1, en_iyi=min(d['en_iyi'], sn) if d['en_iyi'] else sn)
    return d


def kosulabilir(bot):
    """Kurulu ve geçilebilir kapı ya da None."""
    st = durum(bot)
    for k in st['kurulu']:
        if tahmin(bot, k)[1] < KAPI[k]['can']:
            return k
    return None
