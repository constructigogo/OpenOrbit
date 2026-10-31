"""Yönetici modu (panelin Oyun ayarları > Yönetici; oyuncu isteği 2026-10-30): oyuncu oyunda yönetici olarak görünür.

İstemcide (canlı test 2026-10-30):
  - ShipInitializationCommand / ShipCreateCommand dailyRank 6000: adın önünde yönetici rozeti (sarı A; wiki "Administrator") ve
    istemci oyuncuyu Hero.Admin sayar (GM konsolu penceresi, gm_konsol.py). Rütbe 22 rozet çizmez.
  - Yönetici gemileri istemcinin gemi listesinde: ship_admin (ADMIN_SHIP; game.xml'de UFO uzaylısının modeli de bu), ship_police,
    ship_g-admincloak ve Goliath'ın tasarımı ship_goliath_design_admincloak. Görünüm typeId'den: değerler oyuncunun gemisinin.
  - Sohbet: gönderenin role alanı ChatUserVo türlerinden (Frida ile okunan statik alanlar): chatter, dev, customerServiceLead,
    customerService, admin, mod, system, cmd. Yönetici "admin" (istemcinin AdministratorMessageColor'u).
Kurallar: yönetici rütbe sistemine, Şeref Salonu listelerine ve şirketteki sıraya girmez (rutbe.py); izleyici ayarı açıksa uzaylılar
ve botlar ona saldırmaz, hasar almaz (dunya.py, bot/govde.py). Botlar yöneticiyi tanır: saldırmaz, sohbetteki uyarısına uyar
(bot/yonetici_uyari.py), görünce tepki verir. Arkadaş sunucusunda yalnız sunucunun oyuncusu (misafir değil).
"""
import ayar as AY

ROZET = 6000                    # istemcinin yönetici rütbesi (gm_konsol.ADMIN_RANK ile aynı)
GEMILER = (None, 'ship_admin', 'ship_police', 'ship_g-admincloak', 'ship_goliath_design_admincloak')
SOHBET_ROLU = 'admin'


def _host():
    import topluluk as TP
    g = TP.OYUN
    return g.PROFIL if g is not None else None


def acik(profil=None):
    """Yönetici modu açık mı (profil verilirse: o profil yönetici mi: yalnız sunucunun oyuncusu; misafir ve çoklu istemcinin ek
    oyuncuları değil; sunucu kurulmadan, ör. testte, profilin kendisi)."""
    if not AY.get('yonetici_modu'):
        return False
    if profil is None:
        return True
    host = _host()
    return getattr(profil, 'misafir', None) is None and (host is None or profil is host)


def gemi(profil=None):
    """Yönetici gemisinin görünümü (typeId) ya da None (kendi gemisi)."""
    if not acik(profil):
        return None
    return GEMILER[min(len(GEMILER) - 1, max(0, int(AY.get('yonetici_gemisi') or 0)))]


def izleyici(profil=None):
    """Dokunulmaz izleyici: uzaylılar ve botlar saldırmaz, hasar almaz."""
    return acik(profil) and bool(AY.get('yonetici_izleyici'))


def sohbet_rolu(profil=None, varsayilan='chatter'):
    return SOHBET_ROLU if acik(profil) and AY.get('yonetici_sohbet') else varsayilan


def ad():
    """Yöneticinin pilot adı (sunucunun oyuncusu) ya da None."""
    host = _host()
    return str(host.d['pilot'].get('userName', '')) if acik() and host is not None else None


def mi(ad_=None, profil=None, uid=None):
    """Bu pilot yönetici mi (ad, profil ya da kimlik ile)."""
    host = _host()
    if not acik() or host is None:
        return False
    if profil is not None:
        return profil is host
    if uid is not None:
        return uid == host.user_id
    return ad_ is not None and str(ad_).lower() == str(host.d['pilot'].get('userName', '')).lower()
