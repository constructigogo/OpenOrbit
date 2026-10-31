"""Botlar ve yönetici (yonetici_modu.py; kullanıcı isteği 2026-10-30): yöneticiyi tanırlar, sohbetteki uyarısına uyarlar, onu görünce
tepki verirler.

Uyarı: yöneticinin oda mesajı ya da fısıltısı uyarı sözcüğü içeriyorsa (sekiz dilde: "stop", "warning", "kes", "yeter", "hör auf" …)
konusu sözcüklerden: sohbet (spam, küfür, büyük harf), pvp (öldürme, acemi avlama, kamp), kutu (kargo kutusu, ganimet çalma); konusu
yoksa genel (sohbet ve PvP, kısa). Uyarılan botlar: adı geçenler; adı geçen yoksa kanalı dinleyenler. Etkisi süreli (tekrarlandıkça
iki katı, en çok 8 katı):
  sohbet  30 dk   konuşma çoğu kez susar (yalnız yanıtlar), hakarete karşılık yok
  pvp     4 sa    oyuncuya ve bota saldırmaz, PvP avına çıkmaz
  kutu    24 sa   başkasının kargo kutusunu almaz
Adı geçen bot kısaca özür diler (Gelişmiş kipte dil modeli: sistem istemi ve persona notu; değilse kalıp). Hafızasında yöneticiyle
"uyarildim" olayı. Yöneticiyi selamlayana karşılık verirler; haritada yönetici görünce biri firma sohbetinde söyler (harita başına
YORUM_SN'de bir).
"""
import re, time, unicodedata

import harita as H
import yonetici_modu as YM
from . import ad_uslup as AU
from . import konusma as KN

SURE_DK = {'sohbet': 30, 'pvp': 240, 'kutu': 1440}
GENEL = {'sohbet': 30, 'pvp': 60}
YORUM_SN = 900
GORUS = 1600


def _katla(s):
    s = str(s or '').lower().replace('ı', 'i').replace('ß', 'ss').replace('ł', 'l')
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def _ifade(kokler):
    return re.compile(r'(?<!\w)(%s)' % '|'.join(re.escape(_katla(k)) for k in sorted(kokler, key=len, reverse=True)))


# güçlü sözcük tek başına uyarıdır; zayıf olan ("dont", "yapma", "pare") ancak bir konu sözcüğüyle (yöneticinin sıradan sohbeti,
# "dont worry guys", kimseyi cezalandırmasın)
GUCLU = _ifade([
    'warn', 'ban', 'mute', 'rules', 'last time', 'cut it out', 'not allowed', 'uyari', 'uyariyorum', 'son kez', 'kural', 'sustur',
    'yasak', 'verwarn', 'regel', 'advertencia', 'regla', 'avertissement', 'regle', 'interdit', 'ostrzez', 'zasad', 'aviso', 'regra',
    'proibido', 'предупрежд', 'правил', 'бан', 'нельзя'])
ZAYIF = _ifade([
    'stop', 'quit', 'dont', "don't", 'do not', 'no more', 'behave', 'enough', 'kes', 'yapma', 'yapmayin', 'birak', 'durdur', 'yeter',
    'dikkat edin', 'etme', 'etmeyin', 'olmaz', 'calmayin', 'almayin', 'saldirmayin', 'oldurmeyin', 'yazmayin', 'atmayin', 'hor auf', 'hoer auf', 'hort auf', 'lass das', 'stopp', 'deja', 'dejen', 'basta', 'arrete', 'przestan', 'dosc',
    'pare', 'parem', 'chega', 'прекрат', 'хватит', 'стоп'])
KONU = {
    'sohbet': _ifade(['spam', 'flood', 'caps', 'insult', 'swear', 'curs', 'toxic', 'rude', 'offensive', 'language', 'chat', 'kufur',
                      'hakaret', 'buyuk harf', 'kaba', 'argo', 'sohbet', 'beleidig', 'schimpf', 'flame', 'insult', 'groser', 'grossier',
                      'obraz', 'wyzwisk', 'xing', 'спам', 'флуд', 'мат', 'оскорб', 'капс', 'чат']),
    'pvp': _ifade(['kill', 'attack', 'grief', 'camp', 'newbie', 'noob', 'low level', 'lowbie', 'gank', 'pk', 'oldur', 'saldir', 'kesme',
                   'yeni oyuncu', 'acemi', 'dusuk seviye', 'avla', 'kamp', 'tot', 'angreif', 'neuling', 'anfanger', 'matar', 'atacar',
                   'novato', 'campear', 'tuer', 'attaqu', 'debutant', 'zabija', 'atak', 'nowi', 'nowicjusz', 'kampi', 'campar',
                   'убива', 'атак', 'нович', 'кемп']),
    'kutu': _ifade(['box', 'cargo', 'loot', 'steal', 'kutu', 'kargo', 'ganimet', 'cal', 'kiste', 'beute', 'klau', 'stehl', 'caja',
                    'botin', 'robar', 'caisse', 'butin', 'vol', 'skrzyn', 'lup', 'krad', 'caixa', 'saque', 'roub', 'ящик', 'карго',
                    'лут', 'ворова', 'краж']),
}


def konular(metin):
    """Uyarı mı -> konuları (boşsa uyarı değil; konusu yoksa {'genel'})."""
    k = _katla(metin)
    kon = {ad for ad, ifade in KONU.items() if ifade.search(k)}
    if GUCLU.search(k):
        return kon or {'genel'}
    return kon if ZAYIF.search(k) else set()


def etkin(b, konu, now=None):
    """Bot bu konuda yöneticinin uyarısı altında mı."""
    u = b.k.get('uyari') or {}
    return (now or time.time()) < u.get(konu, 0)


def uyar(b, kon, now, ad=''):
    """Uyarıyı uygula (süreler tekrarla uzar) -> uygulanan konular."""
    u = b.k.setdefault('uyari', {})
    u['sayi'] = n = int(u.get('sayi', 0)) + 1 if now - u.get('son', 0) < 86400 else 1
    u['son'] = now
    kat = min(8, 2 ** (n - 1))
    sureler = {}
    for k in kon:
        sureler.update(GENEL if k == 'genel' else {k: SURE_DK[k]})
    for k, dk in sureler.items():
        u[k] = max(u.get(k, 0), now + dk * 60 * kat)
    if ad:
        b.hafiza.olay(ad, 'uyarildim', now)
    b.olay('yonetici_uyardi', now, konu=','.join(sorted(sureler)))
    b.ruh.it(moral=-0.05)
    return set(sureler)


def notu(b, now=None):
    """Persona notu (Gelişmiş kip): yöneticinin süren uyarısı."""
    now = now or time.time()
    u = b.k.get('uyari') or {}
    acik = [k for k in SURE_DK if now < u.get(k, 0)]
    if not acik:
        return ''
    ne = {'sohbet': 'spamming or rude chat', 'pvp': 'attacking or killing other pilots', 'kutu': "taking other pilots' cargo boxes"}
    return ' The game master warned him about %s %d min ago: he obeys and avoids it.' % (
        ' and '.join(ne[k] for k in acik), max(1, int((now - u.get('son', now)) // 60)))


def sistem_notu():
    """Sistem istemine (llm.py, ajan.py): yönetici varken; yoksa boş (önbellek bozulmaz)."""
    ad = YM.ad()
    if not ad:
        return ''
    return ('\n\nGAME MASTER: %s is a game administrator (GM) of this server: admin badge on the ship, admin colour in chat, may fly '
            'an admin ship (a UFO). Everyone knows it. Be polite to the GM, never insult, threaten or attack them, never argue with '
            'their decisions. When the GM warns about conduct (spam, insults, caps, killing new players, camping, taking others\' '
            'loot), the warned pilot apologizes briefly and stops; others may comment but never mock the warning. Asking the GM for '
            'free items or bans only as an obvious joke. Seeing the GM in space is a small event worth a remark.' % ad)


def isle(m, g, now):
    """Sohbet motorunun gelen mesajı (SohbetMotoru.sohbet_isle): yöneticinin uyarısı ya da selamı -> işlendi mi (True: yanıtlar
    burada ya da dil modelinde, kalıplara gitmez)."""
    if g[0] == 'fisilti':
        _, b, msg, kim = g
        dinleyen, anilan, kanal = [b], [b], None
    else:
        _, yol, msg, kim = g
        from .sohbet_motoru import kanal_adi
        kanal = kanal_adi(yol)
        if kanal is None:
            return False
        dinleyen = m.dinleyenler(kanal, kim)
        anilan = [b for b in dinleyen if AU.anildi_mi(b.ad, msg)]
    ad = kim.get('userId', '')
    if not YM.mi(ad_=ad):
        return False
    kon = konular(msg)
    if kon:
        hedef = anilan or dinleyen
        for b in hedef:
            uyar(b, kon, now, ad)
        if m.llm is not None and m.llm.hazir:
            return False                                 # dil modeli yanıtlar (persona notu ve sistem istemi)
        for b in (anilan or [x for x in hedef if x.r.random() < 0.15])[:2]:
            m.konus(b, kanal or 'fisilti', KN.kalip(b, 'yonetici_ozur', ad=ad), alici=ad if kanal is None else None, now=now,
                    oncelik=True)
        return True
    tur, _ = KN.niyet(msg)
    if tur == 'selam' and kanal is not None and not anilan and (m.llm is None or not m.llm.hazir):
        for b in [b for b in dinleyen if b.r.random() < 0.5 + 0.4 * b.o('sosyallik')][:3]:
            m.konus(b, kanal, KN.kalip(b, 'yonetici_selam', ad=ad), now=now, oncelik=True)
        return True
    return False


def gorus_tick(y, now):
    """Haritada yönetici: yakınındaki bir bot firma sohbetinde söyler (harita başına YORUM_SN'de bir)."""
    if not YM.acik():
        return
    son = y.__dict__.setdefault('_gm_yorum', {})
    for w in list(y.dunyalar):
        if not getattr(w, 'running', False) or not YM.mi(profil=w.p) or now - son.get(w.map_id, 0) < YORUM_SN:
            continue
        hx, hy = w.hero_pos(now)
        yakin = [n.bot for n in list(w.npcs.values()) if n.bot is not None and n.alive and
                 ((n.mover.pos(now)[0] - hx) ** 2 + (n.mover.pos(now)[1] - hy) ** 2) ** 0.5 < GORUS]
        if not yakin:
            continue
        son[w.map_id] = now
        b = max(yakin, key=lambda b: b.o('konuskanlik') * b.r.random())
        b.olay('yonetici_gordu', now, harita=H.name(w.map_id))
        y.konus(b, 'firma', KN.kalip(b, 'yonetici_gordu', harita=H.name(w.map_id)), now=now)
