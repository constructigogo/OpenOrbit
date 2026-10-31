"""Grup: bir gruba girince liderin (ya da gruptaki oyuncunun) haritasına gidip yanında avlanmak; liderin saldırdığına saldırır.
Kabul toplum.davetler'de (niyet olarak bu hedef güçlenir); bağlılık sürdükçe (niyet süresi) seçilir, sonra bot sıkılıp ayrılabilir."""
import math

from ..beyin import Hedef, hedef
from .. import katalog as K
from .. import soyut as S


def lider(bot):
    """Gruptaki takip edilecek kişi (insan oyuncu önce, yoksa lider) -> topluluk.Kisi ya da None."""
    import grup as GR
    import topluluk as TP
    g = GR.grubu(bot.uid)
    if g is None:
        return None
    kisiler = TP.hepsi()
    uyeler = [kisiler.get(u) for u in g.uyeler if u != bot.uid]
    uyeler = [k for k in uyeler if k is not None and k.oturum is not None]
    insan = [k for k in uyeler if k.uid < 1800000000 or k.uid >= 1900000000]
    return (insan or [kisiler.get(g.lider)] or [None])[0] if (insan or uyeler) else None


@hedef
class Grup(Hedef):
    ad = 'grup'
    izin = 'grup'
    en_az_sn = 300

    def uygun(self, bot, b):
        return lider(bot) is not None

    def puan(self, bot, b):
        return 0.5 + 0.4 * bot.o('sosyallik') + 0.3 * bot.o('sadakat')

    def basla(self, bot, b):
        self._yonel(bot, b.y, b.now)

    def _yonel(self, bot, y, now=None):
        k = lider(bot)
        if k is None:
            bot.plan['bitti'] = True
            return
        m = int(k.profil.d['konum'].get('mapId', bot.harita))
        bot.plan.update(lider=k.uid, harita=m)
        if m in K.HARITALAR and K.girebilir(m, bot.firma, bot.seviye):
            S.git(bot, m, y, now)

    def soyut(self, bot, dt, y):
        if S.yolculuk(bot, y):
            return
        k = lider(bot)
        if k is None:
            bot.plan['bitti'] = True
            return
        if int(k.profil.d['konum'].get('mapId', 0)) != bot.harita:
            self._yonel(bot, y)
            return
        S.kas(bot, dt, y)

    def somut(self, bot, g, w, now):
        """Liderin yanında kal; lider bu dünyanın kahramanıysa ve saldırıyorsa onun hedefine saldır."""
        uid = bot.plan.get('lider')
        if uid != w.hid or w.hero_dead:
            return False
        if w.attacking and w.target in w.npcs and w.npcs[w.target].bot is None:
            g.hedef = w.target
        from .. import govde as G
        if g.hedef is None and G.kapi_dunyasi(w):        # kapı dolgusu: kahramana en yakın uzaylıya (dalgayı birlikte temizler)
            hx, hy = w.hero_pos(now)
            yakin = [(math.hypot(hx - p[0], hy - p[1]), u) for u, m in list(w.npcs.items())
                     if m.bot is None and m.alive for p in (m.mover.pos(now),)]
            yakin = [x for x in yakin if x[0] < 2200]
            if yakin:
                g.hedef = min(yakin)[1]
        hx, hy = w.hero_pos(now)
        nx, ny = g.mover.pos(now)
        if g.hedef is None and math.hypot(hx - nx, hy - ny) > 700:
            from .. import govde as G
            G._git(w, g, hx + bot.r.uniform(-300, 300), hy + bot.r.uniform(-300, 300), now)
            return True
        return False

    def bitti(self, bot, b):
        return bot.plan.get('bitti', False) or lider(bot) is None
