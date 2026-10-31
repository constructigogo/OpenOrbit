"""Klan yönetimi (kullanıcı isteği 2026-10-31): bot klan lideri (ve hakkı olan subaylar) klanı gerçek bir lider gibi yönetir. Hepsi
oyunun klan istekleriyle (klan.Klan.handle), oyuncunun klan penceresinden yapabildiği her şey:
  rütbeler       kuruluşta 3-4 rütbe (botun dilinde) ve hakları; üyelere rol: kıdem, liderin ilişkisi, seviye, katkı
  açıklama       kuruluşta ve klanın kimliği değişince (PvP'ye döndü, istasyon kurdu, doldu); arada tazelenir
  duyuru         savaş, ittifak, saldırmazlık, barış, ödeme, haftalık hedef (klan haberleri); savaşta toplu posta
  vergi          bütçe ihtiyacına göre %0-5 (önceden doğrudan %3-8 yazılıyordu: sınır klan.AZAMI_VERGI)
  bütçe          kasanın payları k['butce'] {ksi, odeme, savas} (kalanı yedek): istasyonu yoksa KSİ, savaştaysa savaş
  ödeme          haftada bir, dönemin en çok vergi veren üyelerine kasadan (klan.odeme_siniri ve %10 kesintiyle)
  üye çıkarma    liderin kin duyduğu ya da uzun süre katkısız üye
  liderlik devri hevesini yitiren lider en güvendiği subaya bırakır; tek kişi kalan eski klan dağılır
Kurallı karar toplum.klan_isleri'nden (yonet); Gelişmiş kipte ajan aynı işleri araçlarla yapar (araclar.py: klan_*). İşlerin son
anları klanın kaydında k['yonetim'] (klanlar.json'a da yazılır)."""
import os, random, time

import klan as KL
from . import konusma as KN
from . import toplum as T

GUN = 86400
KAT_HAKLARI = (                                   # rütbe katmanı -> hakları (0 subay ... 3 acemi)
    ['hiremember', 'firemember', 'news', 'roundmail', 'battle_station_build', 'battle_station_replace_module',
     'battle_station_deflector'],
    ['hiremember', 'news', 'battle_station_replace_module'],
    [],
    [])
ARALIK = {'rutbe': 600, 'rol': 3 * 3600, 'aciklama': 3600, 'duyuru': 900, 'vergi': 6 * 3600, 'butce': 6 * 3600, 'odeme': 7 * GUN,
          'cikar': 12 * 3600, 'devir': 12 * 3600, 'hedef': 5 * GUN}


LOGO_KLASORU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'panel', 'arayuz', 'gorsel', 'klan_logo')


def logolar():
    """Logo havuzu (Orders.md OP-017): panel/arayuz/gorsel/klan_logo/*.webp adları (uzantısız)."""
    try:
        return sorted(f[:-5] for f in os.listdir(LOGO_KLASORU) if f.endswith('.webp'))
    except OSError:
        return []


def logo_ver(k):
    """Logosuz bot klanına havuzdan rastgele, başka klanın kullanmadığı bir logo (klan dağılınca havuza döner) -> logo ya da None."""
    if k.get('logo'):
        return k['logo']
    with KL.LOCK:
        kullanilan = {c.get('logo') for c in KL.KLANLAR.values()}
        bos = [x for x in logolar() if x not in kullanilan]
        if bos:
            k['logo'] = random.choice(bos)
    return k.get('logo')


def kl_of(b):
    return KL.Klan(T.profil(b), log=lambda *_: None)


def basarili(out):
    return bool(out) and bool(out[0][1].get('success'))


def ham(b, durum):
    """Kalıbın üslupsuz hâli (rütbe adları: botun yazım üslubu "|" ayracını bozmasın)."""
    k = KN.KALIPLAR.get(durum) or {}
    satir = k.get(KN.dil(b)) or k.get('en')
    return b.r.choice(satir) if satir else None


def kayit(k):
    return k.setdefault('yonetim', {})


def vakti(k, is_, now, aralik=None):
    """İşin vakti geldiyse (ve şimdi işaretler) -> True."""
    y = kayit(k)
    son = y.get(is_, 0)
    if now - son < (aralik if aralik is not None else ARALIK[is_]):
        return False
    y[is_] = now
    return True


def uye_bul(k, ad):
    """Üye (ad küçük harf, kayıt) ya da (None, None): adı ya da görünen adı eşleşir."""
    s = str(ad or '').strip().lower()
    for a, u in k['uyeler'].items():
        if s in (a, str(u.get('ad', '')).lower()):
            return a, u
    return None, None


def rutbe_bul(k, ad):
    s = str(ad or '').strip().lower()
    return next((r for r in k['rutbeler'] if r['ad'].lower() == s), None)


def kidem_gun(u, now):
    try:
        return (now - time.mktime(time.strptime(u.get('katilma', ''), '%Y-%m-%d %H:%M:%S'))) / GUN
    except (ValueError, OverflowError):
        return 0.0


def bilgi_ozeti(k, kim=None):
    """Klanın durumu (ajanın gözlemi): üyeler ve rütbeleri, kasa, vergi, bütçe, diplomasi, başvurular."""
    now = time.time()
    rut = {r['id']: r['ad'] for r in k['rutbeler']}
    uy = sorted(k['uyeler'].items(), key=lambda au: (au[0] != k['lider'], -int(au[1].get('seviye', 1))))
    satir = ['Clan [%s] %s, leader %s, %d members, treasury %s credits, tax %d%%.' % (
        k['etiket'], k['ad'], (k['uyeler'].get(k['lider']) or {}).get('ad', k['lider']), len(k['uyeler']), '{:,}'.format(int(k['kasa'])),
        int(k.get('vergi') or 0))]
    b = k.get('butce') or {}
    if b:
        satir.append('Budget shares of the treasury: station %d%%, payouts %d%%, war %d%%, the rest is reserve.' % (
            100 * b.get('ksi', 0), 100 * b.get('odeme', 0), 100 * b.get('savas', 0)))
    satir.append('Ranks: %s.' % (', '.join('%s (%s)' % (r['ad'], ', '.join(r['haklar']) or 'no rights') for r in k['rutbeler'])
                                 or 'none yet'))
    satir.append('Members: %s.' % '; '.join('%s (lvl %s, %s, %d days%s)' % (
        u.get('ad', a), u.get('seviye', 1), 'leader' if a == k['lider'] else rut.get(u.get('rutbe', 0), 'no rank'), kidem_gun(u, now),
        ', paid %s tax this week' % '{:,}'.format(int(u['katki_donem'])) if u.get('katki_donem') else '') for a, u in uy[:20]))
    dip = {1: 'alliance', 2: 'non-aggression pact', 3: 'war'}
    d = [dip.get(x['tur'], '?') + ' with ' + str((KL.KLANLAR.get(x['klan']) or {}).get('ad', x.get('ad', '?'))) for x in k['diplomasi']]
    if d:
        satir.append('Diplomacy: %s.' % ', '.join(d))
    gelen = [r for r in k.get('diplo_istek', []) if r['kime'] == k['id']]
    if gelen:
        satir.append('Diplomacy offers waiting for your answer: %s.' % ', '.join('%s from %s' % (
            {0: 'peace', 1: 'alliance', 2: 'non-aggression'}.get(r['tur'], '?'), (KL.KLANLAR.get(r['kimden']) or {}).get('ad', '?'))
            for r in gelen))
    if k.get('basvurular'):
        satir.append('Applications: %s.' % ', '.join(str(x.get('ad')) for x in k['basvurular'][:8]))
    satir.append('Description: %s' % (' '.join(str(k.get('aciklama') or '').split())[:200] or '(empty)'))
    return '\n'.join(satir)


# ------------------------------------------------------------------------------------------------------------ işler
def rutbeleri_kur(b, k, kl):
    """Rütbesiz klana 3-4 rütbe (adları botun dilinde, bir takım halinde) ve katmanlarının hakları."""
    if k['rutbeler']:
        return False
    adlar = [a.strip() for a in (ham(b, 'klan_rutbeler') or 'Officer|Veteran|Member|Recruit').split('|') if a.strip()][:4]
    if len(adlar) < 4:
        adlar += ['Member', 'Recruit'][len(adlar) - 2:]
    katlar = [0, 1, 2, 3]
    if b.r.random() < 0.35:                               # kimi lider kıdemli rütbesi açmaz
        katlar.remove(1)
    elif b.r.random() < 0.3:
        katlar.remove(3)
    kat = kayit(k).setdefault('rutbe_kat', {})
    duzen = []
    for i in katlar:
        out = kl.handle('ClanNewRankRequest', {'newRank': adlar[i]})
        r = rutbe_bul(k, adlar[i])
        if basarili(out) and r is not None:
            kat[str(r['id'])] = i
            duzen.append({'rankId': r['id'], 'rankName': r['ad'], 'rights': KAT_HAKLARI[i]})
    if duzen:
        kl.handle('EditClanRanksRequest', {'ranks': duzen})
        b.olay('klan_rutbe', ad=', '.join(d['rankName'] for d in duzen))
    return bool(duzen)


def _kat_rutbesi(k, kat):
    """Katmana (ya da yoksa altındaki en yakın katmana) uyan rütbenin kimliği; hiç yoksa 0."""
    kk = {int(i): int(v) for i, v in (kayit(k).get('rutbe_kat') or {}).items() if any(r['id'] == int(i) for r in k['rutbeler'])}
    for t in range(kat, 4):
        r = next((i for i, v in kk.items() if v == t), None)
        if r is not None:
            return r
    return 0


def rolleri_dagit(y, b, k, kl, now):
    """Üyelere rol: subaylar (üyenin yaklaşık 1/8'i) liderin en güvendikleri arasından, kıdemliler birkaç günlük ve katkılılar,
    yeniler acemi. Her turda en çok üç değişiklik (bir anda herkes terfi etmesin)."""
    if not kayit(k).get('rutbe_kat'):
        return 0
    ort = sum(int(u.get('seviye', 1)) for u in k['uyeler'].values()) / max(1, len(k['uyeler']))
    puan = []
    for a, u in k['uyeler'].items():
        if a == k['lider']:
            continue
        gun = kidem_gun(u, now)
        rel = b.hafiza.iliski(u.get('ad', a), now)
        p = 0.45 * min(1.0, gun / 14.0) + 0.35 * rel + 0.2 * max(-1.0, min(1.0, (int(u.get('seviye', 1)) - ort) / 6.0))
        puan.append((p + (0.1 if u.get('katki_donem') else 0), gun, rel, a, u))
    puan.sort(key=lambda x: -x[0])
    subay = max(1, len(puan) // 8)
    degisen = 0
    for i, (p, gun, rel, a, u) in enumerate(puan):
        kat = 0 if i < subay and gun >= 2 and rel >= 0.1 else 1 if gun >= 5 and p >= 0.35 else 2 if gun >= 1 else 3
        rid = _kat_rutbesi(k, kat)
        if rid and int(u.get('rutbe', 0)) != rid:
            if basarili(kl.handle('EditClanMemberRequest', {'rankId': rid, 'memberId': int(u.get('uid', 0))})):
                degisen += 1
                if degisen >= 3:
                    break
    return degisen


def aciklama_yaz(b, k, kl, now, zorla=False):
    """Klanın açıklaması: odağı (PvP, PvE, istasyon), kuralı, alım (en düşük seviye ya da dolu). Klanın kimliği değişince yeniden."""
    from . import klan_us as KU
    pvp = b.o('saldirganlik') > 0.6 or any(d['tur'] == 3 for d in k['diplomasi'])
    ksi = KU.istasyonlari(k)
    dolu = len(k['uyeler']) >= KL.AZAMI_UYE - 2
    imza = [pvp, bool(ksi), dolu]
    y = kayit(k)
    if not zorla and y.get('aciklama_imza') == imza and now - y.get('aciklama_t', 0) < b.r.uniform(4, 9) * GUN:
        return False
    ort = sum(int(u.get('seviye', 1)) for u in k['uyeler'].values()) / max(1, len(k['uyeler']))
    parcalar = [KN.kalip(b, 'klan_aciklama_odak_pvp' if pvp else 'klan_aciklama_odak_pve', klan=k['ad'], etiket=k['etiket'])]
    if ksi:
        parcalar.append(KN.kalip(b, 'klan_aciklama_odak_ksi', istasyon=ksi[0]))
    if b.r.random() < 0.8:
        parcalar.append(KN.kalip(b, 'klan_aciklama_kural'))
    parcalar.append(KN.kalip(b, 'klan_aciklama_dolu') if dolu else KN.kalip(b, 'klan_aciklama_alim', seviye=max(1, int(ort * 0.6))))
    metin = '\n'.join(p for p in parcalar if p)
    if not metin or not basarili(kl.handle('ChangeClanDescriptionRequest', {'desc': metin[:2000]})):
        return False
    y.update(aciklama_imza=imza, aciklama_t=now)
    b.olay('klan_aciklama', now)
    return True


def duyur(b, kl, durum, **f):
    """Klan haberi (kalıptan) -> yazıldı mı."""
    metin = KN.kalip(b, durum, **f)
    return bool(metin) and basarili(kl.handle('ClanAddNewsRequest', {'newsMessage': metin}))


def toplu_posta(b, kl, durum, **f):
    konu, metin = KN.kalip(b, durum + '_konu', **f), KN.kalip(b, durum, **f)
    return bool(konu and metin) and basarili(kl.handle('ClanSendAllMessageRequest', {'subject': konu[:50], 'msgText': metin}))


def olaylari_duyur(y, b, k, kl, now):
    """Diplomasideki yenilikler (savaş, ittifak, saldırmazlık, biten savaş) haber olur; savaş başlayınca üyelere toplu posta."""
    yk = kayit(k)
    gordu = yk.setdefault('diplo_gordu', {})
    simdi = {str(d['id']): d for d in k['diplomasi']}
    ilk = not gordu and 'diplo_ilk' not in yk
    yk['diplo_ilk'] = True
    for i, d in simdi.items():
        if i in gordu or ilk:
            continue
        ad = (KL.KLANLAR.get(d['klan']) or {}).get('ad', d.get('ad', '?'))
        durum = {1: 'klan_duyuru_ittifak', 2: 'klan_duyuru_saldirmazlik', 3: 'klan_duyuru_savas'}.get(d['tur'])
        if durum and duyur(b, kl, durum, klan=ad) and d['tur'] == 3 and KL.hak(b.profil, 'roundmail'):
            toplu_posta(b, kl, 'klan_posta_savas', klan=ad)
    for i, d in gordu.items():
        if i not in simdi and d.get('tur') == 3:
            duyur(b, kl, 'klan_duyuru_baris', klan=d.get('ad', '?'))
    yk['diplo_gordu'] = {i: {'tur': d['tur'], 'ad': (KL.KLANLAR.get(d['klan']) or {}).get('ad', d.get('ad', '?'))}
                         for i, d in simdi.items()}


def butce_ayarla(b, k, now, ksi=None, odeme=None, savas=None):
    """Kasanın payları (0-1; toplamı en çok 0,9, kalanı yedek). Verilmeyenleri durum ve kişilik belirler: istasyonu yoksa KSİ
    payı yüksek, savaştaysa savaş; cömert ve az hırslı lider üyelerine daha çok dağıtır."""
    from . import klan_us as KU
    savasta = any(d['tur'] == 3 for d in k['diplomasi'])
    if ksi is None:
        ksi = (0.55 if not KU.istasyonlari(k) else 0.3) * (0.7 + 0.6 * b.o('hirs')) if KU.acik() else 0.0
    if savas is None:
        savas = 0.25 if savasta else 0.12 if b.o('saldirganlik') > 0.6 else 0.04
    if odeme is None:
        odeme = 0.06 + 0.2 * b.o('sosyallik') * (1 - 0.6 * b.o('hirs'))
    pay = {'ksi': max(0.0, float(ksi)), 'odeme': max(0.0, float(odeme)), 'savas': max(0.0, float(savas))}
    top = sum(pay.values())
    if top > 0.9:
        pay = {a: v * 0.9 / top for a, v in pay.items()}
    with KL.LOCK:
        k['butce'] = {a: round(v, 3) for a, v in pay.items()}
    return k['butce']


def harcanabilir(k, alan):
    """Bütçenin o alana ayırdığı kredi (kasanın payı)."""
    return int(k['kasa'] * float((k.get('butce') or {}).get(alan, 0)))


def vergi_ayarla(b, k, kl, now, oran=None):
    """Vergi %0-5 (istekle; hakkı yoksa olmaz): hırslı lider yüksek tutar; bütçenin hedefine (istasyon) para yetmiyorsa artırır,
    kasa çok dolunca indirir."""
    from . import klan_us as KU
    if oran is None:
        oran = 1 + round(3 * b.o('hirs'))
        if KU.acik() and KU.ihtiyac(k) > k['kasa']:
            oran += 1
        if k['kasa'] > 50000000:
            oran -= 2
    oran = max(0, min(KL.AZAMI_VERGI, int(oran)))
    if int(k.get('vergi') or 0) == oran:
        return True
    return basarili(kl.handle('ChangeClanTaxRequest', {'tax': oran}))


def odeme_yap(b, k, kl, now):
    """Haftalık ödeme: bütçenin ödeme payı, dönemde en çok vergi veren (en çok 3) üyeye katkısıyla orantılı; dönem sıfırlanır.
    Hiç katkısı olmayan üyenin katkısız sayacı artar (üye çıkarmada)."""
    havuz = harcanabilir(k, 'odeme')
    katki = sorted(((int(u.get('katki_donem', 0)), a, u) for a, u in k['uyeler'].items() if u.get('katki_donem')), key=lambda x: -x[0])[:3]
    odenen = []
    if havuz >= 100000 and katki:
        top = sum(x[0] for x in katki)
        for kat, a, u in katki:
            miktar = min(int(havuz * kat / top), KL.odeme_siniri(u, now))
            if miktar >= 10000 and basarili(kl.handle('PayoutClanRequest', {'amount': miktar, 'payoutUserId': int(u.get('uid', 0)),
                                                                           'reason': 'top contributor'})):
                odenen.append(u.get('ad', a))
    with KL.LOCK:
        for a, u in k['uyeler'].items():
            u['katkisiz'] = 0 if u.get('katki_donem') else int(u.get('katkisiz', 0)) + 1
            u['katki_donem'] = 0
    if odenen:
        duyur(b, kl, 'klan_duyuru_odeme', adlar=', '.join(odenen))
        b.olay('klan_odeme', now, adlar=odenen)
    return odenen


def cikar(y, b, k, kl, now, ad=None):
    """Üye çıkarma: verilen üye ya da liderin kin duyduğu / üç haftadır katkısız (bot) üye; turda en çok bir."""
    if ad is None:
        aday = None
        for a, u in k['uyeler'].items():
            if a == k['lider']:
                continue
            rel = b.hafiza.iliski(u.get('ad', a), now)
            if rel <= -0.45 or (int(u.get('katkisiz', 0)) >= 3 and a in y.ada and kidem_gun(u, now) > 21):
                aday = a
                break
        if aday is None or b.r.random() > 0.5:
            return None
        ad = aday
    a, u = uye_bul(k, ad)
    if u is None or not basarili(kl.handle('DeleteClanMemberRequest', {'removeUserID': int(u.get('uid', 0))})):
        return None
    o = y.ada.get(a)
    if o is not None:
        o.k['klan'] = None
        T.guncelle(o)
    b.olay('klandan_cikardi', now, ad=u.get('ad', a))
    return u.get('ad', a)


def devret(y, b, k, kl, now, ad=None):
    """Liderliği bırakma: verilen üyeye ya da en güvendiği subaya (yoksa en kıdemli üyeye). Kendiliğinden çok nadir: hevesi
    kaçan, az hırslı lider."""
    if ad is None:
        if len(k['uyeler']) < 3 or b.r.random() > 0.02 * (1.2 - b.o('hirs')) * (0.5 + b.ruh['yorgunluk']):
            return None
        subay = {r for r, v in (kayit(k).get('rutbe_kat') or {}).items() if v == 0}
        adaylar = [(str(u.get('rutbe', 0)) in subay, b.hafiza.iliski(u.get('ad', a), now), kidem_gun(u, now), a)
                   for a, u in k['uyeler'].items() if a != k['lider']]
        if not adaylar:
            return None
        ad = max(adaylar)[3]
    a, u = uye_bul(k, ad)
    if u is None or a == k['lider'] or not basarili(kl.handle('ChangeClanLeaderRequest', {'newLeaderId': int(u.get('uid', 0))})):
        return None
    b.olay('liderligi_birakti', now, ad=u.get('ad', a))
    return u.get('ad', a)


def dagit(y, b, k, kl, now):
    """Bir haftadır tek kişi kalan klanı lideri dağıtır (nadir)."""
    if len(k['uyeler']) > 1 or kidem_gun(k['uyeler'].get(k['lider']) or {}, now) < 7 or b.r.random() > 0.1:
        return False
    if not basarili(kl.handle('DeleteClanRequest', {})):
        return False
    b.k['klan'] = None
    T.guncelle(b)
    b.olay('klani_dagitti', now, klan=k['ad'])
    return True


def haftalik_hedef(b, k, kl, now):
    """Bütçenin odağına göre haftanın hedefi haber olur (istasyon için para, kasma, PvP)."""
    from . import klan_us as KU
    butce = k.get('butce') or {}
    if KU.acik() and butce.get('ksi', 0) >= max(butce.get('savas', 0), 0.3) and not KU.istasyonlari(k):
        return duyur(b, kl, 'klan_duyuru_hedef_ksi')
    if butce.get('savas', 0) >= 0.2:
        return duyur(b, kl, 'klan_duyuru_hedef_pvp')
    return duyur(b, kl, 'klan_duyuru_hedef_kas')


def yonet(y, b, k, kl, now):
    """Kurallı yönetim (toplum.klan_isleri'nden, sosyal turda): her iş kendi aralığıyla; lider her şeyi, subay haklarınca."""
    lider = k['lider'] == b.ad.lower()
    if not lider and (not kl.hak('news', k) or k['lider'] not in y.ada):
        return                                            # oyuncunun klanında subay bot klanı yönetmez (lider sensin)
    if lider:
        if vakti(k, 'rutbe', now):
            rutbeleri_kur(b, k, kl)
            if not k.get('logo') and logo_ver(k):
                KL.degisti(k)                             # logo klanlar.json'a (panelin Klanlar sekmesi)
        if vakti(k, 'rol', now):
            rolleri_dagit(y, b, k, kl, now)
        if vakti(k, 'aciklama', now):
            aciklama_yaz(b, k, kl, now)
        if vakti(k, 'butce', now) or not k.get('butce'):
            butce_ayarla(b, k, now)
        if vakti(k, 'vergi', now):
            vergi_ayarla(b, k, kl, now)
        if vakti(k, 'odeme', now) and kidem_gun(k['uyeler'].get(k['lider']) or {}, now) >= 6:
            odeme_yap(b, k, kl, now)
        if vakti(k, 'cikar', now):
            cikar(y, b, k, kl, now)
        if vakti(k, 'devir', now) and (devret(y, b, k, kl, now) or dagit(y, b, k, kl, now)):
            return
    from . import klan_us as KU
    KU.yonet(y, b, k, kl, now)                            # Klan Savaş İstasyonu: yarış, gelişme, savunma (kurma hakkıyla)
    if vakti(k, 'duyuru', now):
        olaylari_duyur(y, b, k, kl, now)
    if vakti(k, 'hedef', now, ARALIK['hedef'] * b.r.uniform(0.8, 1.4)):
        haftalik_hedef(b, k, kl, now)
