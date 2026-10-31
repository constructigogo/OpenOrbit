"""Klan emirleri (oyuncu isteği 2026-10-31): klanındaki botlara klan sohbetinden (ya da fısıltıyla) iş verirsin, gerçek bir klan gibi.

  odak    "everyone farm / do quests / go pvp / do gates / sell ore", "herkes görev yapsın"   -> o işe 2 saat ağırlık (beyin niyeti)
  git     "defend 4-4", "3 of you go to 2-4", "herkes 4-5'e"                               -> o haritaya gider, düşmanla dövüşür
  gel     "come help me", "regroup", "recall", "yanıma gelin"                              -> senin haritana gelir
  us      "defend our base / cbs / station"                                                -> klanın istasyonunun haritası (cbs.py)
  al      "get lf-3", "buy iris", "sg3n-b02 alın"                                          -> onu biriktirip alır (alisveris birikim)
  gemi    "use goliath", "fly vengeance", "goliath'a geçin"                               -> o gemiyi biriktirir, alınca uçar; zevki o olur
  yapi    "full shield", "full speed", "balanced"                                          -> jeneratörleri kalkana/hıza dağıtır (kalkan_payi)
  dur     "stop", "dismissed", "serbest"                                                   -> emirler kalkar
"N of you" / "3 kişi" sayısı: en sadık N bot. Uyma olasılığı sadakat, sana ilişki ve liderlik (lider sensen) ile; yorgun bot
reddedebilir. Yanıt kısa kalıp (emir_tamam, emir_ret, geliyorum). İzin 'klan_emir'.
"""
import re

import harita as H
from . import beyin as B
from . import katalog as K
from . import konusma as KN

ODAK_SN = 7200
GIT_SN = 1800
US_SN = 3600
_SAYI_SOZ = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'bir': 1, 'iki': 2, 'üç': 3, 'uc': 3, 'dört': 4, 'dort': 4,
             'beş': 5, 'bes': 5}
_SAYI = re.compile(r'\b(\d{1,2}|one|two|three|four|five|bir|iki|üç|uc|dört|dort|beş|bes)\s+(of\s+)?(you|u|ya|guys|kişi\w*|kisi\w*|'
                   r'tane\w*|biriniz|kişiniz)\b', re.I)
_DUR = re.compile(r"\b(stop|dismissed|as you were|at ease|carry on|free now|cancel|nevermind|serbest|bırakın|birakin|dağılın|"
                  r"dagilin|iptal)\b", re.I)
_GEL = re.compile(r"\b(come (to me|here|back|help)|help me|regroup|recall|rally|back to me|to me|bana gel\w*|yan[ıi]ma gel\w*|"
                  r"gelin|toplan\w*|yard[ıi]m edin)\b", re.I)
_SAVUN = re.compile(r'\b(defend|protect|guard|hold|savun\w*|koru\w*|go to|go|head to|move to|git\w*|gidin|gelin)\b', re.I)
_US = re.compile(r'\b(base|cbs|station|battle ?station|[üu]s(s[üu]m[üu]z|[üu]m[üu]z|s[üu])?|istasyon\w*)\b', re.I)
_ODAK = (('kapi', re.compile(r'\b(gates?|gg|galaxy gates?|kap[ıi]\w*|alpha|beta|gamma|delta|epsilon|zeta|kappa|lambda|kuiper|'
                             r'hades)\b', re.I)),
         ('gorev', re.compile(r'\b(quests?|missions?|g[öo]rev\w*)\b', re.I)),
         ('pvp', re.compile(r'\b(pvp|hunt\w*|enem(y|ies)|kill (players|enemies)|d[üu][şs]man\w*|avla\w*)\b', re.I)),
         ('satis', re.compile(r'\b(sell\w*|ore|cargo|cevher\w*|kargo\w*)\b', re.I)),
         ('mod', re.compile(r'\b(events?|etkinli\w*)\b', re.I)),
         ('kasilma', re.compile(r'\b(farm\w*|grind\w*|npcs?|aliens?|uzayl[ıi]\w*|kas[ıi]n|kas[ıi]l\w*|kasma\w*)\b', re.I)))
_YAPI = (('kalkan', re.compile(r'\b(full|all|max)\s*(shields?|shd|kalkan)|\b(tam|full)\s*kalkan', re.I)),
         ('hiz', re.compile(r'\b(full|all|max)\s*(speed|spd|h[ıi]z)|\b(tam|full)\s*h[ıi]z', re.I)),
         ('denge', re.compile(r'\b(balanced|half|hybrid|dengeli|yar[ıi] yar[ıi]ya)\b', re.I)))
_GEMI_FIIL = re.compile(r'\b(use|fly|switch|ride|change to|kullan\w*|u[çc]un|ge[çc]in|binin)\b', re.I)
_AL = re.compile(r'\b(get|buy|equip|grab|save (up )?for|al[ıi]n|alsın|biriktir\w*|tak[ıi]n)\b', re.I)
YAPI_PAYI = {'kalkan': 0.95, 'hiz': 0.3, 'denge': 0.6}


def _esyalar():
    """Kısa ad -> loot: "lf-3", "sg3n-b02", "iris", "goliath" (tasarımsız gemiler)."""
    out = {}
    for grup in ('lazerler', 'kalkan_jeneratorleri', 'hiz_jeneratorleri', 'dronlar'):
        for loot in K.ESYA[grup]:
            out.setdefault(loot.rsplit('_', 1)[-1].lower(), loot)
    for loot in K.gemiler():
        out.setdefault(loot[len('ship_'):].lower(), loot)
    return out


_ESYA = None


def esya_bul(metin):
    global _ESYA
    if _ESYA is None:
        _ESYA = _esyalar()
        _ESYA['rx'] = re.compile(r'(?<![\w-])(%s)(?![\w-])' % '|'.join(re.escape(k) for k in sorted(_ESYA, key=len, reverse=True)), re.I)
    m = _ESYA['rx'].search(metin)
    return _ESYA[m.group(1).lower()] if m else None


def coz(metin):
    """Klan emri -> {'tur', 'harita'?, 'hedef'?, 'esya'?, 'yapi'?, 'sayi'?} ya da None (emir değil: olağan sohbet)."""
    s = str(metin or '')
    if s.rstrip().endswith('?'):
        return None                                      # soru emir değil ("gates?" "kim kapı yapar?")
    m = _SAYI.search(s)
    sayi = (int(m.group(1)) if m.group(1).isdigit() else _SAYI_SOZ.get(m.group(1).lower())) if m else None
    e = {'sayi': sayi} if sayi else {}
    hm = KN.HARITA.search(s)
    harita = ('%s-%s' % (hm.group(1), hm.group(2).upper() if hm.group(2).isalpha() else hm.group(2))) if hm else None
    if _DUR.search(s):
        return dict(e, tur='dur')
    for ad, rx in _YAPI:
        if rx.search(s):
            return dict(e, tur='yapi', yapi=ad)
    esya = esya_bul(s) if _AL.search(s) or _GEMI_FIIL.search(s) else None     # "nice goliath" emir değil
    if esya:
        return dict(e, tur='gemi' if esya.startswith('ship_') else 'al', esya=esya)
    if _SAVUN.search(s) and _US.search(s) and not harita:
        return dict(e, tur='us')
    if _GEL.search(s) and not harita:
        return dict(e, tur='gel')
    if harita and (_SAVUN.search(s) or _GEL.search(s) or re.search(r"\b(everyone|all|herkes|hepiniz)\b", s, re.I)):
        return dict(e, tur='git', harita=harita)
    if re.search(r'\b(focus|everyone|all|go|let\'?s|herkes|hepiniz|odaklan\w*|yap[ıi]n|gidin)\b', s, re.I):
        for ad, rx in _ODAK:
            if rx.search(s):
                return dict(e, tur='odak', hedef=ad)
    return None


def us_haritasi(profil):
    """Klanın kurulu (ya da kurulmakta olan) istasyonunun haritası ya da None."""
    import cbs as CB
    import klan as KL
    k = KL.klani(profil)
    for kaynak in (CB.ortak(), profil):
        if kaynak is None:
            continue
        for aid, a in ((kaynak.d.get('cbs') or {}).get('asteroitler') or {}).items():
            if (isinstance(a, dict) and a.get('sahip') != 'rakip' and a.get('durum') in ('kurulu', 'kurma')
                    and a.get('klan') in (None, (k or {}).get('id'))):
                ast = CB.AST.get(int(aid))
                if ast:
                    return int(ast['harita'])
    return None


def uyar_mi(b, ad, lider, now):
    p = 0.45 + 0.4 * b.o('sadakat') + 0.4 * b.hafiza.iliski(ad, now) + (0.15 if lider else 0) - 0.25 * b.ruh['yorgunluk']
    return b.r.random() < p


def uygula(y, b, e, ad, kisi, now):
    """Bir botta emir -> (kalıp, alanlar). Uymadıysa ('emir_ret', {})."""
    tur = e['tur']
    if tur == 'dur':
        b.k['niyet'] = None
        b.k.pop('emir', None)
        b.sonraki_karar = now
        return 'emir_tamam', {}
    if tur == 'yapi':
        b.k['yapi'] = e['yapi']
        b.ekip_degisti()
        return 'emir_tamam', {}
    if tur in ('al', 'gemi'):
        if b.k['ekip'].get('gemi') == e['esya']:
            return 'emir_tamam', {}
        b.k['birikim'] = e['esya']                      # alışveriş yalnız onu biriktirir (alisveris.aday)
        b._adaylar = None
        if tur == 'gemi':
            aile = e['esya'][len('ship_'):].split('-')[0]
            b.k['kisilik']['zevk'] = aile               # bundan sonra o gemi ailesini sever
        b.k['emir'] = {'tur': tur, 'esya': e['esya'], 'kim': ad, 't': now}
        return 'emir_tamam', {}
    if tur == 'odak':
        B.zorla(b, e['hedef'], plan={}, pay=1.3, sure=ODAK_SN, now=now)
        b.k['emir'] = {'tur': 'odak', 'hedef': e['hedef'], 'kim': ad, 't': now}
        return 'emir_tamam', {}
    m = None
    if tur == 'git':
        from .araclar import _harita
        m = _harita(e['harita'])
    elif tur == 'gel':
        m = int(kisi.profil.d['konum'].get('mapId', 0)) if kisi is not None else None
    elif tur == 'us':
        m = us_haritasi(kisi.profil) if kisi is not None else None
        if m is None:
            return 'emir_us_yok', {}
    if not m or m not in K.HARITALAR or not K.girebilir(m, b.firma, b.seviye) or not K.yol(b.harita, m, b.firma, b.seviye):
        return 'gelemem', {}
    B.zorla(b, 'yardim', plan={'harita': int(m), 'ad': ad}, pay=1.6, sure=US_SN if tur == 'us' else GIT_SN, now=now)
    b.hafiza.olay(ad, 'yardim_ettim', now)
    return 'geliyorum', {'harita': H.name(m)}


def isle(y, kanal, msg, kim, dinleyen, now):
    """Sohbet motorundan: klan kanalındaki (ya da bota fısıltıdaki) mesaj klan emriyse uygular ve yanıtlatır -> işlendi mi."""
    if not y.izin('klan_emir') or kanal not in ('klan', 'fisilti'):
        return False
    e = coz(msg)
    if e is None:
        return False
    import klan as KL
    import topluluk as TP
    ad = kim.get('userId', '')
    kisi = TP.bul(ad=ad)
    kl = KL.klani(kisi.profil) if kisi is not None else None
    if kl is None or ad.lower() in y.ada:
        return False
    uyeler = [b for b in dinleyen if b.k.get('klan') == kl['id'] and b.cevrimici and b.olu_bitis <= now]
    if not uyeler:
        return False
    lider = kl['lider'] == ad.lower()
    sira = sorted(uyeler, key=lambda b: -(b.o('sadakat') + b.hafiza.iliski(ad, now)) * b.r.uniform(0.8, 1.2))
    kabul = 0
    for i, b in enumerate(sira):
        if e.get('sayi') and kabul >= e['sayi']:
            break
        if e['tur'] == 'dur' or uyar_mi(b, ad, lider, now):
            kalip, alan = uygula(y, b, e, ad, kisi, now)
            kabul += kalip != 'gelemem'
        else:
            kalip, alan = 'emir_ret', {}
        if i < 4 or kalip == 'geliyorum':                 # herkes yazmaz: ilk birkaçı ve yola çıkanlar
            y.konus(b, 'fisilti' if kanal == 'fisilti' else 'klan', KN.kalip(b, kalip, **alan), alici=ad if kanal == 'fisilti' else None,
                    now=now + b.r.uniform(0.5, 3) * (i + 1), oncelik=True)
    y.log('   botlar: klan emri %s: %s -> %d/%d bot' % (ad, e, kabul, len(uyeler)))
    return True
