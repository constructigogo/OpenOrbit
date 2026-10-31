"""Satış: kargo dolunca kendi istasyonuna (X-1 ya da X-8) dönüp cevherleri rafineriye satmak (oyunda ticaret yalnız istasyonda).

Ne zaman dolu sayıldığı kişiliğe bağlı: sabırlı ve tutumlu oyuncu ağzına kadar doldurur, aceleci yarısında döner. Somutta gemi
istasyona uçar, yanına varınca satar; soyutta istasyon haritasına varınca satar.
"""
import math

from ..beyin import Hedef, hedef
from .. import katalog as K
from .. import soyut as S

SATIS_MESAFE = 600


def esik(bot):
    """Kargonun bu kadarı dolunca satmaya döner."""
    return min(1.0, 0.55 + 0.3 * bot.o('sabir') + 0.15 * bot.o('tutumluluk'))


def en_yakin_istasyon(bot):
    """Satış haritalarından yolu en kısa olanı."""
    return min(K.satis_haritalari(bot.firma), key=lambda m: len(K.yol(bot.harita, m, bot.firma, bot.seviye) or range(99)))


def tehlike(bot, g, w, now):
    """Dolu kargoyla eve dönerken dövüşe döner mi: bir oyuncu ya da bot vuruyorsa ya da can yarının altındaysa. Uzaylıların
    tacizini umursamaz, uçmaya devam eder (canlı test 2026-10-29: 2-1'de saldırgan uzaylılar sırayla vurdukça istasyona hiç
    varamıyordu)."""
    son = [u for u, t in g.saldiran.items() if now - t < 6]
    if any(u not in w.npcs or w.npcs[u].bot is not None for u in son):
        return True
    d = bot.deger()
    return bool(son) and (g.hp + g.shield) / max(1, d['can'] + d['kalkan']) < 0.5


@hedef
class Satis(Hedef):
    ad = 'satis'
    izin = 'kargo'
    en_az_sn = 30

    def uygun(self, bot, b):
        return bot.kargo_dolu() >= esik(bot)

    def puan(self, bot, b):
        return 0.6 + 1.2 * min(1.0, bot.kargo_dolu()) + 0.2 * bot.o('tutumluluk')

    def basla(self, bot, b):
        from .. import ekstra as EK
        if EK.kullan(bot, EK.HM7):                       # HM-7: istasyona gitmeden, olduğu yerde satar (100 hak)
            bot.kargo_sat()
            bot.plan['bitti'] = True
            return
        bot.plan['harita'] = en_yakin_istasyon(bot)
        S.git(bot, bot.plan['harita'], b.y, b.now)

    def soyut(self, bot, dt, y):
        if S.yolculuk(bot, y):
            return
        if bot.harita == bot.plan.get('harita'):
            bot.kargo_sat()
            bot.plan['bitti'] = True
        else:
            if not S.git(bot, bot.plan.get('harita') or en_yakin_istasyon(bot), y):
                bot.plan['bitti'] = True                 # istasyona yol yok: vazgeçer (sonsuza dek denemez)

    def somut(self, bot, g, w, now):
        if bot.yolda or bot.harita != bot.plan.get('harita') or tehlike(bot, g, w, now):
            return False                                  # portala uçar ya da oyuncuya/tehlikeye karşılık verir (govde)
        from .. import govde as BG
        s = w.station
        if not s:
            bot.kargo_sat()
            bot.plan['bitti'] = True
            return True
        nx, ny = g.mover.pos(now)
        if math.hypot(s['posX'] - nx, s['posY'] - ny) > SATIS_MESAFE:
            BG._rota(w, g, s['posX'], s['posY'], now, esik=300)
            return True
        bot.kargo_sat()
        bot.plan['bitti'] = True
        return True

    def bitti(self, bot, b):
        return bot.plan.get('bitti', False)
