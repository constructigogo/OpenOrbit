"""Kapı koşusu: kurulu Galaksi Kapısına girer, dalgaları bitirir (bot/kapi.py). Kapıdayken bot kapı haritasındadır (senin
haritandan kalkar); süre ve başarı gücünden; bitince ödül ve üsse dönüş."""
from ..beyin import Hedef, hedef
from .. import kapi as KP
from .. import katalog as K
from .. import soyut as S


@hedef
class KapiKosusu(Hedef):
    ad = 'kapi'
    izin = 'kapi'
    en_az_sn = 3600 * 3          # kapıdayken başka işe geçmez

    def uygun(self, bot, b):
        return bot.seviye >= 10 and KP.kosulabilir(bot) is not None

    def puan(self, bot, b):
        return 0.9 + 0.4 * bot.o('hirs') + 0.2 * bot.o('rekabet') - 0.5 * bot.ruh['yorgunluk']

    def basla(self, bot, b):
        k = KP.kosulabilir(bot)
        basari, sure = KP.kosu_sonucu(bot, k, bot.r)
        bot.plan.update(kapi=k, basari=basari, bitis=b.now + sure, sure=sure)
        harita = KP.KAPI[k].get('harita')
        if harita:
            S.atla(bot, harita, b.y)                    # kapı haritası: senin haritandan kalkar
        bot.olay('kapiya_girdi', kapi=KP.KAPI[k]['ad'])

    def soyut(self, bot, dt, y):
        if bot.plan.get('bitti') or y.now < bot.plan.get('bitis', 0):
            return
        k = bot.plan.get('kapi')
        st = KP.durum(bot)
        if k in st['kurulu']:
            st['kurulu'].remove(k)
            st['parca'].pop(k, None)
        if k == 'kronos':
            st['kronos'] = 0
        if bot.plan.get('basari'):
            KP.odullendir(bot, k, y.hiz(bot))
            KP.sure_yaz(bot.k, k, bot.plan.get('sure') or 0)
        else:
            bot.ist('kapi_kayip')
            bot.olay('kapi_kaybetti', kapi=KP.KAPI[k]['ad'])
        S.atla(bot, K.ev(bot.firma), y)                 # kapının çıkışı: X-1
        bot.plan['bitti'] = True

    def somut(self, bot, g, w, now):
        return False

    def bitti(self, bot, b):
        return bot.plan.get('bitti', False)
