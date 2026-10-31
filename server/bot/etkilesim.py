"""Oyuncunun bottan istekleri (grup, yardım, klan, arkadaşlık, "gel / neredesin"): kararı kişiliğe dayalı karar motoru verir,
eylemi araçlar (araclar.py) uygular, sohbet yalnız kararı botun ağzından söyler. Normal kipte kalıplar, Gelişmiş kipte dil modeli
söyler; ikisinde de söz ile eylem tutarlıdır (küçük model "olur" deyip daveti unutuyordu, "grup olalım"a harita ipucu veriyordu).

karar() -> {'niyet', 'kabul': True | False | None, 'eylem': (araç, argümanlar) | None, 'not': modele İngilizce yönerge,
            'kalip': (kalıp, alanlar) | None}. uygula() eylemi yapar.
Sözler (botun belleğinde, 5 dk / 1 sa): "inv me" diyen bot oyuncunun davetini kabul eder (toplum.karar_grup), "klanıma başvur"
diyen lider başvurusunu kabul eder (toplum.basvuru_karari).
"""
import re

import harita as H
from . import araclar as AR
from . import katalog as K

NIYETLER = ('grup', 'yardim', 'klan', 'arkadas', 'takip', 'duello', 'gorev', 'ozel', 'kapi')
KAPI_SEVIYE = (8, 12)                                    # kapı dolgusuna gelen en düşük seviye: ABG gibi kapılar; Hades, LoW, QZ
_ZOR_KAPI = re.compile(r'\b(hades|low|legends? of war|qz|quarantine|kronos|kuiper|lambda|kappa|zeta)\b', re.I)
DUELLO_HARITA = 16                                       # 4-4: herkesin girebildiği PvP haritası (buluşma yeri önerisi)
_NEREDE = re.compile(r"\b(where (are|r) (you|u)|where u at|wya|nerdesin|neredesin)\b", re.I)
_KLANIMA = re.compile(r"\b(join (my|our|us)|my clan|our clan|klan[ıi]ma|klan[ıi]m[ıi]za|bizim klan|benim klan)\b", re.I)
GRUP_SOZ_SN, KLAN_SOZ_SN = 300, 3600


def _kisi(ad):
    import topluluk as TP
    return TP.bul(ad=ad) if ad else None


def soz_ver(b, tur, ad, now, sure=None):
    b.__dict__.setdefault('sozler', {})[(tur, str(ad).lower())] = now + (sure or (GRUP_SOZ_SN if tur == 'grup' else KLAN_SOZ_SN))


def soz_var(b, tur, ad, now):
    t = b.__dict__.get('sozler', {}).get((tur, str(ad).lower()))
    return t is not None and now <= t


_EVET = re.compile(r"^\s*(y|ya|yes|yep|yup|yeah|sure|ok|okay|k|kk|why not|lets go|let'?s go|inv|inv me|go|evet|olur|tamam|tmm|"
                   r"tabi|tabii|hadi|gel)\b", re.I)
_HAYIR = re.compile(r"^\s*(no|nah|nope|not now|later|hay[ıi]r|yok|olmaz|sonra)\b", re.I)


def teklif_ver(b, tur, ad, now):
    """Bot oyuncuya kendiliğinden teklif etti ("gruplaşalım mı"): olumlu yanıt o isteğe dönüşür, söz de verilmiş olur."""
    b.__dict__.setdefault('teklifler', {})[str(ad).lower()] = (tur, now + 600)
    soz_ver(b, tur, ad, now, sure=600)


def teklif_cevabi(b, ad, metin, now):
    """Oyuncunun yanıtı botun açık teklifine olumlu mu -> teklifin niyeti ('grup' ...) ya da None. Olumsuzsa teklif düşer."""
    t = b.__dict__.get('teklifler', {}).get(str(ad).lower())
    if not t or now > t[1]:
        return None
    if _HAYIR.search(metin or ''):
        del b.teklifler[str(ad).lower()]
        return None
    if _EVET.search(metin or ''):
        del b.teklifler[str(ad).lower()]
        return t[0]
    return None


def _sonuc(niyet, kabul, not_, kalip=None, eylem=None):
    return {'niyet': niyet, 'kabul': kabul, 'not': not_, 'kalip': kalip, 'eylem': eylem}


def karar(y, b, niyet, ad, kim, harita, metin, now, posta=False):
    """posta: istek postayla geldi (yanıt dakikalar sonra; grup için hemen davet değil, söz)."""
    if niyet == 'grup':
        return _grup(y, b, ad, kim, now, posta)
    if niyet == 'gorev':
        k = _grup(y, b, ad, kim, now, posta)          # görev yardımı = gruplanmak: grubun öldürdüğü uzaylı herkesin görevine sayılır
        k['niyet'] = 'gorev'
        k['not'] = 'He asks for help with his quest; in a group every kill counts for everyone\'s quest. ' + k['not']
        return k
    if niyet == 'duello':
        return _duello(y, b, ad, kim, harita, now)
    if niyet == 'kapi':
        return _kapi(y, b, ad, kim, now, metin)
    if niyet == 'ozel':
        return _ozel(y, b, ad, kim, now)
    if niyet == 'takip':
        return _takip(y, b, ad, kim, harita, metin, now)
    if niyet == 'arkadas':
        return _arkadas(y, b, ad, kim, now)
    if niyet == 'klan':
        return _klan(y, b, ad, kim, metin, now)
    return None


# ------------------------------------------------------------------------------------------------------------ grup
def _grup(y, b, ad, kim, now, posta=False):
    import grup as GR
    from . import toplum
    if not y.izin('grup'):
        return _sonuc('grup', False, 'You decided to DECLINE (you play solo). Say no in your own words.', ('cevap_hayir', {}))
    o = _kisi(ad)
    ouid = o.uid if o is not None else int(kim.get('id') or 0)
    bg, og = GR.grubu(b.uid), (GR.grubu(ouid) if ouid else None)
    if bg is not None and ouid in bg.uyeler:
        return _sonuc('grup', None, 'You are ALREADY in a group with him: no invite needed, just answer as his teammate.')
    lider_benim = bg is not None and bg.lider == b.uid and len(bg.uyeler) < GR.EN_COK
    if bg is not None and not (lider_benim and og is None):
        return _sonuc('grup', False, 'You are already in another group, so you DECLINE. Say so in your own words.',
                      ('zaten_grupta', {}))
    if not toplum.karar_grup(y, b, ad, ouid, now):
        return _sonuc('grup', False, 'You decided to DECLINE (busy or not in the mood). Say no in your own words, maybe a short '
                                     'reason.', ('cevap_hayir', {}))
    if posta:
        soz_ver(b, 'grup', ad, now, sure=6 * 3600)       # postada: davet onun, oyunda karşılaşınca kabul eder
        return _sonuc('grup', True, 'You decided to ACCEPT: tell him to invite you (or whisper you) when you are both online, you '
                                    'will join his group.', ('inv_me', {}))
    if og is not None or o is None or o.oturum is None:
        soz_ver(b, 'grup', ad, now)                      # o gruptaysa (ya da çevrimdışı) davet onundur: gelince kabul eder
        return _sonuc('grup', True, 'You decided to ACCEPT, but HE has to invite you (he is already in a group or offline): tell '
                                    'him to send you an invite (inv me) and you will join.', ('inv_me', {}))
    return _sonuc('grup', True, 'You decided to ACCEPT: you are sending him a group invite right now. Say yes in your own words '
                                '(he should accept your invite).', ('davet_attim', {}), ('grup_davet', {'ad': ad}))


# ------------------------------------------------------------------------------------------------------------ kapı dolgusu
def _kapi(y, b, ad, kim, now, metin=''):
    """"Need fillers for Hades": seviyesi yeten, isteyen bot "inv me" der ve söz verir (davet onun: gruba alınca kapıya
    seninle girer, govde.kapi_tick). Kapıda değilken grup kurulur; oyuncu kapıya girince gruptaki botlar da gelir."""
    if not (y.izin('kapi_dolgu') and y.izin('grup')):
        return _sonuc('kapi', False, 'You decided NOT to join (busy). Say no in your own words.', ('cevap_hayir', {}))
    if b.seviye < KAPI_SEVIYE[bool(_ZOR_KAPI.search(metin or ''))]:
        return _sonuc('kapi', False, 'Your ship is too weak for that gate: say so in your own words.', ('gelemem', {}))
    if b.hedef is not None and b.hedef.ad in ('kapi', 'mod', 'duello'):
        return _sonuc('kapi', False, 'You are busy in your own gate/event now: say so.', ('cevap_hayir', {}))
    fac = int(kim.get('factionId') or 0)
    p = 0.3 + 0.35 * b.o('sosyallik') + 0.35 * b.o('hirs') + 0.6 * b.hafiza.iliski(ad, now) - 0.3 * b.ruh['yorgunluk']
    if fac and fac != b.firma:
        p -= 0.6
    if b.r.random() >= p:
        return _sonuc('kapi', False, 'You decided NOT to join his gate. Say it in your own words.', ('cevap_hayir', {}))
    soz_ver(b, 'grup', ad, now, sure=1200)                # davet edince kabul eder
    return _sonuc('kapi', True, 'You ACCEPT to fill his gate: tell him to invite you (inv me), you will jump in with him.',
                  ('inv_me', {}))


# ------------------------------------------------------------------------------------------------------------ özel mesaj
def _ozel(y, b, ad, kim, now):
    """"Bana PM at": istekli bot yanıtını kanala değil fısıltıyla yazar ('fisilti': sohbet ve LLM yolları buna bakar)."""
    if not y.izin('sohbet'):
        return None
    fac = int(kim.get('factionId') or 0)
    p = 0.3 + 0.5 * b.o('sosyallik') + 0.3 * b.o('yardimseverlik') + 0.6 * b.hafiza.iliski(ad, now) - (0.3 if fac and fac != b.firma
                                                                                                        else 0)
    if b.r.random() >= p:
        return None
    k = _sonuc('ozel', True, 'He asked someone to send him a private message: you WHISPER him now (this line goes to him '
                              'privately): a short opener like asking what he needs.', ('pm_cevap', {}))
    k['fisilti'] = True
    return k


# ------------------------------------------------------------------------------------------------------------ düello
def _duello(y, b, ad, kim, harita, now):
    """Meydan okumaya karşılık: başka firmadan, saldırgan ve rekabetçi, gücü yeten bot kabul eder; buluşma onun haritası (bot
    oraya girebiliyorsa) ya da adı geçen harita, değilse 4-4. Aynı firmadan bot düello yapmaz (firmasına saldıramaz)."""
    fac = int(kim.get('factionId') or 0)
    if fac == b.firma:
        return _sonuc('duello', False, 'He is in YOUR company: you cannot fight your own company, say so (or joke about it).',
                      ('duello_ayni', {}))
    if not (y.izin('pvp') and y.izin('oyuncuya_saldir')):
        return _sonuc('duello', False, 'You decided NOT to fight him now. Say it in your own words.', ('duello_ret', {}))
    o = _kisi(ad)
    if o is None or o.oturum is None:
        return None
    plv = int(o.profil.d['pilot'].get('level', 1))
    p = 0.05 + 0.5 * b.o('saldirganlik') + 0.25 * b.o('rekabet') + 0.3 * b.ruh['ofke'] - 0.5 * b.hafiza.iliski(ad, now) \
        - 0.07 * max(0, plv - b.seviye) + 0.03 * max(0, b.seviye - plv)
    if b.hedef is not None and b.hedef.ad in ('gorev', 'mod', 'kapi', 'grup'):
        p -= 0.25
    if b.r.random() >= p:
        return _sonuc('duello', False, 'You decided NOT to fight him (busy or not worth it). Answer in character: a short taunt '
                                       'or a lazy no.', ('duello_ret', {}))
    adaylar = [AR._harita(harita) if harita else None, int(o.profil.d['konum'].get('mapId', 0)), DUELLO_HARITA]
    m = next((m for m in adaylar if m and m in K.HARITALAR and K.girebilir(m, b.firma, b.seviye)
              and K.yol(b.harita, m, b.firma, b.seviye)), None)
    if m is None:
        return _sonuc('duello', False, 'You would fight him but you cannot reach him (level too low): say so.', ('gelemem', {}))
    return _sonuc('duello', True, 'You ACCEPT the fight: you are flying to %s to find and attack him. Say it in your own words '
                                  '(a short confident line naming %s).' % (H.name(m), H.name(m)),
                  ('duello_kabul', {'harita': H.name(m)}), ('duello', {'ad': ad, 'harita': H.name(m)}))


# ------------------------------------------------------------------------------------------------------------ takip
def _takip(y, b, ad, kim, harita, metin, now):
    burada = H.name(b.harita)
    if _NEREDE.search(metin or ''):
        return _sonuc('takip', None, 'He asks where you are: you are on %s. Tell him (just the map, no status report).' % burada,
                      ('nerede', {'harita': burada}))
    o = _kisi(ad)
    m = AR._harita(harita) if harita else (int(o.profil.d['konum'].get('mapId', 0)) if o is not None else None)
    if not m or m not in K.HARITALAR:
        return _sonuc('takip', None, 'He wants you to come but you do not know where he is: ask him which map.')
    if m == b.harita:
        return _sonuc('takip', True, 'You are already on %s too: say so (he can find you there).' % burada,
                      ('nerede', {'harita': burada}))
    if not K.girebilir(m, b.firma, b.seviye) or not K.yol(b.harita, m, b.firma, b.seviye):
        return _sonuc('takip', False, 'You CANNOT go to %s (your level is too low or it is enemy land): say so.' % H.name(m),
                      ('gelemem', {}))
    from . import toplum
    fac = int(kim.get('factionId') or 0)
    p = 0.2 + 0.5 * b.o('yardimseverlik') + 0.6 * b.hafiza.iliski(ad, now) - 0.3 * b.ruh['yorgunluk']
    if fac and fac != b.firma:
        p -= 0.6
    if b.hedef is not None and b.hedef.ad in ('gorev', 'mod', 'kapi'):
        p -= 0.2
    if _grupta(b, ad):
        p += 0.4                                         # grup arkadaşı çağırıyor
    if b.r.random() >= p:
        return _sonuc('takip', False, 'You decided NOT to come (busy with your own thing). Say it in your own words.',
                      ('cevap_hayir', {}))
    return _sonuc('takip', True, 'You decided to COME: you are flying to %s now. Say it in your own words.' % H.name(m),
                  ('geliyorum', {'harita': H.name(m)}), ('npc_avla', {'harita': H.name(m)}))


def _grupta(b, ad):
    import grup as GR
    o = _kisi(ad)
    g = GR.grubu(b.uid)
    return g is not None and o is not None and o.uid in g.uyeler


# ------------------------------------------------------------------------------------------------------------ arkadaşlık
def _arkadas(y, b, ad, kim, now):
    import rehber as RH
    from . import toplum
    if not y.izin('arkadas'):
        return _sonuc('arkadas', False, 'You decided to DECLINE. Say no in your own words.', ('cevap_hayir', {}))
    r = RH.kayit(toplum.profil(b))
    if RH._var(r.get('arkadas', []), ad):
        return _sonuc('arkadas', None, 'You are already friends with him: say so.')
    p = 0.25 + 0.5 * b.o('sosyallik') + 0.7 * b.hafiza.iliski(ad, now)
    fac = int(kim.get('factionId') or 0)
    if fac and fac != b.firma:
        p -= 0.3
    if b.r.random() >= p:
        return _sonuc('arkadas', False, 'You decided NOT to add him (you barely know him). Say it in your own words, not rude.',
                      ('cevap_hayir', {}))
    arac = 'arkadas_kabul' if RH._var(r.get('gelen', []), ad) else 'arkadas_ekle'
    return _sonuc('arkadas', True, 'You decided YES: you %s now. Say it in your own words.' % (
        'accept his friend request' if arac == 'arkadas_kabul' else 'send him a friend request'),
        ('arkadas_tamam', {}), (arac, {'ad': ad}))


# ------------------------------------------------------------------------------------------------------------ klan
def _klan(y, b, ad, kim, metin, now):
    import klan as KL
    from . import toplum
    bk = KL.klani(toplum.profil(b))
    o = _kisi(ad)
    ok = KL.klani(o.profil) if o is not None else None
    if ok is not None and _KLANIMA.search(metin or ''):   # "klanıma gel": başvurur mu
        if bk is not None:
            return _sonuc('klan', False, 'You are already in the clan [%s] %s and stay loyal: decline in your own words.' % (
                bk['etiket'], bk['ad']), ('klan_uye', {'etiket': bk['etiket'], 'lider': bk['lider']}))
        if not y.izin('klan') or toplum.klan_firmasi(ok) not in (0, b.firma):
            return _sonuc('klan', False, 'You decided NOT to join his clan. Say it in your own words.', ('cevap_hayir', {}))
        p = 0.15 + 0.4 * b.o('sosyallik') + 0.7 * b.hafiza.iliski(ad, now) - 0.03 * max(0, b.seviye - int(
            o.profil.d['pilot'].get('level', 1)) - 4)
        if b.r.random() >= p:
            return _sonuc('klan', False, 'You decided NOT to join his clan (not now). Say it in your own words.', ('cevap_hayir', {}))
        return _sonuc('klan', True, 'You decided to JOIN his clan [%s]: you are sending an application now. Say it in your own words.'
                      % ok['etiket'], ('klana_basvurdum', {}), ('klana_basvur', {'klan': ok['etiket']}))
    if bk is None:
        return _sonuc('klan', None, 'You are not in any clan yourself: say so (maybe you are looking too).', ('klan_yok', {}))
    if bk['lider'] == b.ad.lower():
        soz_ver(b, 'klan', ad, now)                       # başvurursa kabul eder
        return _sonuc('klan', True, 'You LEAD the clan [%s] %s and you are recruiting: tell him to apply, you will accept him.' % (
            bk['etiket'], bk['ad']), ('klan_basvur', {'etiket': bk['etiket']}))
    lider = bk['uyeler'].get(bk['lider'], {}).get('ad') or bk['lider']
    return _sonuc('klan', None, 'You are a member of [%s] %s (leader: %s): tell him he can apply there.' % (
        bk['etiket'], bk['ad'], lider), ('klan_uye', {'etiket': bk['etiket'], 'lider': lider}))


# ------------------------------------------------------------------------------------------------------------ uygulama
def uygula(y, b, k, gecikme=0.0):
    """Kararın eylemi (varsa) -> araç sonucu. gecikme: yanıtını yazdıktan sonra yapar ("sure" yazıp sonra davet atar; davet
    yanıttan önce gelmesin); sohbet motorunun eylem sırasına girer."""
    if not k or not k.get('eylem'):
        return None
    if gecikme > 0 and hasattr(y, 'eylemler'):
        y.eylemler.append((y.now + gecikme, b, k['eylem']))
        return None
    return AR.cagir(y, b, *k['eylem'])
