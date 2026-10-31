"""Rütbe, sayaçlar ve kayıtlar (yol haritası Aşama 3). Veri data/rutbe.json (tools/rutbe.py: uzaylı ve gemi puanları resmi
sunucunun Hall of Fame ayrıntılarından, gemi türleri istemcinin game.xml'inden, rütbeler ve formül wiki'den).

Profilde:
  sayaclar        öldürülen uzaylılar (tür başına), öldürülen oyuncu gemileri, ölümler (düşman, radyasyon, öteki), görevler
  rutbe           günlük rütbe hesabı {gun, puan, gecmis: {gün: {puan, ep, onur}}} (haftalık/aylık sıralama farkları için)
  seyir_defteri   LogbookDataCommand kayıtları (yeni önce, en çok KAYIT_SINIRI)
  hesap_gecmisi   BalanceInfoCommand kayıtları (yeni önce)

İstemci (1.1.114, araştırma: istemcinin kodu):
  - rütbe 1-21 (rang_N, gemi etiketinde rankN simgesi), 6000 yönetici, 5000 simgesi. Oyun sırasında güncelleyen mesaj yok:
    ShipInitializationCommand.dailyRank ile (giriş, harita değişimi; oyun sırasında dunya.badge_refresh). Gerçek oyunda günde bir
    hesaplanır; burada eşik geçilince hemen (live_rank).
  - Hall of Fame: HallOfFameTopRequest {type: TopReqType} -> HallOfFameTopDataListCommand. 17 "Rütben" sayfası (myRankingPoints:
    formülün parçaları; pages npcPointsDetails / playerPointsDetails: points x value), 18/19 ana sayfa (en iyi pilotlar/klanlar),
    4-7 EP, 8-11 onur, 0-3 ve 16 kullanıcı (rütbe puanı), 12-15 klan; HallOfFamePagesRequest {type 1-3, page} -> HallOfFamePages;
    HallOfFameDataListRequest {requested} -> etkinlik sıralamaları (etkinlik yok: boş).
  - Seyir defteri: LogbookDataListRequest {startIndex: 0'dan sayfa} -> 12'şer kayıt; infoText istemcide çevrilir
    (kill_npcID_<kimlik>, experience_points_<n>, honour_points_<n>, received_item, killed_by_npc_<kimlik>, killed_by_radiation …).
  - Hesap geçmişi: BalanceInfoListRequest {page: 1'den} -> amountType GOLD/PEARL _PLUS/_MINUS, description istemcinin anahtarı
    (bonus_abschussAlien, quest_won, buy_BATTERY_id …; internalInfo eşya, infoText adet).
Yerel uyarlama: rütbe puan eşiklerine göre; Hall of Fame listelerinde sunucudaki oyuncular (tek oyunculuda yalnız oyuncu; çoklu
istemci ve arkadaş sunucusunda bütün bağlı oyuncular: her istemci aynı listeyi görür), klan listelerinde sunucunun klanları (klan.py;
puanı üyelerin rütbe puanlarının toplamı).
"""
import json, math, os, threading, time
import veri as VERI

HERE = os.path.dirname(os.path.abspath(__file__))
R = VERI.yukle('rutbe.json')            # Dünya Editörü: formül ve eşikler
F = R['formul']
KAYIT_SINIRI = 500
DEFTER_SAYFA = 12                  # istemcinin sayfa boyu
HESAP_SAYFA = 50                   # resmî sunucu kaydı (2026-10-25): sayfa başına 50 satır
NPC_SAYFA = 250                    # kayıttaki npcPointsDetails sayfaları
TOP = {'exp': (4, 5, 6, 7), 'onur': (8, 9, 10, 11), 'puan': (0, 1, 2, 3, 16), 'klan': (12, 13, 14, 15, 19)}
TOP_WEEK, TOP_CLIMB, TOP_MONTH = (2, 6, 10), (3, 7, 11), (16,)
ORE_NAMES = {0: 'PROMETIUM', 1: 'ENDURIUM', 2: 'TERBIUM', 3: 'XENOMIT', 4: 'PROMETID', 5: 'DURANIUM', 6: 'PROMERIUM', 7: 'SEPROM',
             8: 'PALLADIUM'}
# Aylık sıralama (darkorbitwiki events/monthly-ranking; istemci hof_rank_month_info_popup): ilk 50'ye Champion Token (Assembly'nin
# şampiyon tasarımları) ve unvan: 1. 100 + General of the Month; 2-5. 80, 6-10. 60, 11-25. 40, 26-50. 20 + Acclaimed Pilot.
# Tek oyunculu uyarlama: sıra yok, oyuncunun sanal derecesi rütbesinden (en üst rütbe 1.; ondan 1-3 aşağısı 2-5., 4-6 aşağısı 6-10.,
# 7-10 aşağısı 11-25., 11-15 aşağısı 26-50.; daha aşağısı ilk 50 dışı: jeton ve unvan yok). Etkin geçen ay (puan arttı) aranır.
# Kademe: (en üst rütbeden en çok kaç rütbe aşağıda, jeton, unvan, başarım olayı: basarim.SERVER_SIDE)
CHAMPION, CHAMPION_MAX = 'resource_collectable_champion-token', 100
MONTHLY = ((0, 100, 'title_monthlyranking-general', 'monthly_general'), (3, 80, 'title_monthlyranking-pilot', 'monthly_pilot'),
           (6, 60, 'title_monthlyranking-pilot', 'monthly_pilot'), (10, 40, 'title_monthlyranking-pilot', 'monthly_pilot'),
           (15, 20, 'title_monthlyranking-pilot', 'monthly_pilot'))


def stamp(t=None):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) + '.0'


def today(t=None):
    return time.strftime('%Y-%m-%d', time.localtime(t))


# ------------------------------------------------------------ sayaçlar
def counters(p):
    c = p.d.setdefault('sayaclar', {})
    done = len((p.d.get('gorevler') or {}).get('tamam', []))          # sayaçlardan önce bitirilen görevler de sayılır
    for k, v in (('npc', {}), ('oyuncu', {}), ('olum_dusman', 0), ('olum_radyasyon', 0), ('olum_diger', 0), ('gorev', done),
                 ('dost', 0), ('phoenix', 0)):
        c.setdefault(k, v)
    return c


def event(p, kind, **kw):
    """Oyun olayları (profil.ach; başarımlarla aynı olaylar) -> sayaçlar."""
    if kind not in ('kill', 'death', 'quest'):
        return
    with p.lock:
        c = counters(p)
        if kind == 'kill' and kw.get('avatar', 'NPC') == 'NPC' and kw.get('npc') is not None:
            c['npc'][str(kw['npc'])] = c['npc'].get(str(kw['npc']), 0) + 1
        elif kind == 'kill' and kw.get('avatar') == 'PLAYER':           # bot oyuncular (Aşama 11)
            c['oyuncu'][kw.get('gemi', '')] = c['oyuncu'].get(kw.get('gemi', ''), 0) + 1
        elif kind == 'death':
            k = {'RADIATION': 'olum_radyasyon', 'NPC': 'olum_dusman', 'PLAYER': 'olum_dusman'}.get(kw.get('neden'), 'olum_diger')
            c[k] += 1
        elif kind == 'quest':
            c['gorev'] += 1
        p.dirty = True


# ------------------------------------------------------------ rütbe puanı
def days_registered(p, now=None):
    try:
        t0 = time.mktime(time.strptime(p.d.get('olusturma', ''), '%Y-%m-%d %H:%M:%S'))
    except ValueError:
        return 0
    return max(0, int(((now or time.time()) - t0) // 86400))


def ship_type(p):
    return R['gemi_turu'].get(p.ship()['lootId'], 0)        # tabloda olmayan (klasik olmayan) gemi 0 (gerçek kayıt: Sentinel 0)


def user_score(p):
    """Şeref Salonu 'En iyi kullanıcı' puanı: TP / 1000 + Şeref / 100 (resmî forum 127509; gerçek kayıt 416.032.909 TP, 27.810 ŞP -> 416.311)."""
    pl = p.d['pilot']
    return int(pl.get('ep', 0) / 1000 + pl.get('honourPoints', 0) / 100)


def user_score_since(p, days, now=None):
    return int(_since(p, 'ep', days, now) / 1000 + _since(p, 'onur', days, now) / 100)


def npc_points(p):
    return sum(R['npc_puan'].get(k, {}).get('puan', 0) * n for k, n in counters(p)['npc'].items())


def player_points(p):
    return sum(R['gemi_puan'].get(k, {}).get('puan', 0) * n for k, n in counters(p)['oyuncu'].items())


def breakdown(p, now=None):
    """HallOfFameRankingPoints alanları (rütbe puanı formülünün parçaları, wiki) + rankPoints."""
    c, pl = counters(p), p.d['pilot']
    parts = dict(ExperiencePoints=int(pl.get('ep', 0)), honorPoints=int(pl.get('honourPoints', 0)), playerShotPoints=player_points(p),
                 yourLevel=int(pl.get('level', 1)), daysSinceRegistration=days_registered(p, now), yourShipType=ship_type(p),
                 npcShotPoints=npc_points(p), missionsCompleted=c['gorev'], friendlyPlayersDestroyed=c['dost'],
                 DestroyedByEnemies=c['olum_dusman'], DestroyedByRadiationZone=c['olum_radyasyon'], phoenixDestroyed=c['phoenix'])
    pts = (parts['ExperiencePoints'] * F['ep'] + parts['honorPoints'] * F['onur'] + parts['playerShotPoints'] * F['oyuncu']
           + parts['yourLevel'] * F['seviye'] + parts['daysSinceRegistration'] * F['gun'] + parts['yourShipType'] * F['gemi']
           + parts['npcShotPoints'] * F['npc'] + parts['missionsCompleted'] * F['gorev'] + parts['friendlyPlayersDestroyed'] * F['dost']
           + parts['DestroyedByEnemies'] * F['olum_dusman'] + parts['DestroyedByRadiationZone'] * F['olum_radyasyon']
           + parts['phoenixDestroyed'] * F['phoenix'])
    parts['rankPoints'] = max(0, int(pts))
    return parts


def rank_for(points):
    """Rütbe puanından rütbe (1-21; tek oyunculu eşikler, rutbe.json esikler)."""
    return max(i + 1 for i, t in enumerate(R['esikler']) if points >= t)


# ------------------------------------------------------------ şirket sırası (bot oyuncular)
# Gerçek sistem (darkorbitwiki guides/ranks; rutbe.json rutbeler): rütbe şirketteki sıraya göre, Chief General 1, General 2, Basic
# General 3, Chief Colonel 5, Colonel 20 kişi; kalanlar yüzdeyle (Basic Colonel %1 ... Basic Space Pilot %20). Dünyada bot paketi
# varken bu sıra kullanılır (oyuncu isteği 2026-10-30); eşikler tavan olarak kalır: küçük bir şirkette (paket başına onlarca bot)
# az puanlı pilotlar general olmasın. Bot yokken eskisi gibi yalnız eşikler.
SIRA_SN = 30
_SIRA = {}                        # firma -> (zaman, [(puan, kimlik)])
_YEREL = threading.local()        # hesap sürerken: topluluk.hepsi() botların profilini günceller, o da rütbeyi sorar


def _botlar():
    from bot import yonetici as YN
    y = YN.AKTIF
    return y.botlar if y is not None and y.botlar else None


def _sirket(firma, now):
    """Şirketin pilotları [(rütbe puanı, kimlik)]: kayıtlı botlar ve sunucunun oyuncuları (SIRA_SN önbellekli)."""
    t = _SIRA.get(firma)
    if getattr(_YEREL, 'icinde', False):
        return t[1] if t else []                  # iç içe çağrı (canlı test 2026-10-30: sonsuz özyineleme): eski liste
    if t and now - t[0] < SIRA_SN:
        return t[1]
    _YEREL.icinde = True
    try:
        out = _sirket_kur(firma, now)
    finally:
        _YEREL.icinde = False
    _SIRA[firma] = (now, out)
    return out


def _sirket_kur(firma, now):
    import topluluk as TP
    from bot import toplum as TB
    import yonetici_modu as YM
    botlar = {b.uid: b for b in _botlar() or ()}
    out = [(TB.puan(b), uid) for uid, b in botlar.items() if b.firma == firma and b.kayitli]
    for uid, k in TP.hepsi().items():
        if uid not in botlar and int(k.profil.d['pilot'].get('factionId') or 0) == firma and not YM.mi(profil=k.profil):
            out.append((breakdown(k.profil, now)['rankPoints'], uid))
    return out


def sira_rutbesi(sira, n):
    """Şirketin n pilotu arasında sira'ncının (0: en çok puanlı) rütbesi: önce sabit sayılı rütbeler (21'den aşağı), sonra kalanlar
    yüzdeleriyle (16'dan aşağı; yüzdelerin dışında kalan en alt rütbe)."""
    sabit = 0
    for r in reversed(R['rutbeler']):
        if r['tur'] == 'fixedPlayersPerCompany':
            sabit += r['deger']
            if sira < sabit:
                return r['rutbe']
    q, c = 100.0 * (sira - sabit + 1) / max(1, n - sabit), 0.0
    for r in reversed(R['rutbeler']):
        if r['tur'] == 'percentOfCompany':
            c += r['deger']
            if q <= c + 1e-9:
                return r['rutbe']
    return 1


def sirket_rutbesi(uid, firma, puan, now=None):
    """Botlar varken şirketteki sıradan rütbe (uid'nin kendi kaydı yerine güncel puanı) -> rütbe ya da None (bot yok)."""
    if _botlar() is None or not firma:
        return None
    now = now or time.time()
    others = [x for x in _sirket(firma, now) if x[1] != uid]
    return sira_rutbesi(sum(1 for x in others if (x[0], -x[1]) > (puan, -uid)), len(others) + 1)      # eşitlikte önce kayıtlı (küçük kimlik)


def gecilecek_puan(p, rank, now=None):
    """Botlar varken rank rütbesine çıkmak için geçilmesi gereken şirket pilotunun puanı (o rütbedeki en alt sıradaki) ya da None."""
    if _botlar() is None:
        return None
    now = now or time.time()
    others = sorted((x for x in _sirket(int(p.d['pilot'].get('factionId') or 0), now) if x[1] != p.user_id), reverse=True)
    n = len(others) + 1
    k = max((i for i in range(n) if sira_rutbesi(i, n) >= rank), default=-1)
    return others[k][0] if 0 <= k < len(others) else None


def rank_of(p, points, now=None):
    """Oyuncunun rütbesi: eşiklere göre; botlar varken şirketteki sırası da (ikisinin küçüğü)."""
    r = rank_for(points)
    s = sirket_rutbesi(p.user_id, int(p.d['pilot'].get('factionId') or 0), points, now)
    return r if s is None else min(r, s)


def daily_rank(p, now=None, force=False):
    """Günde bir (giriş ve harita değişiminde bakılır): rütbe hesaplanır, pilot.dailyRank'e yazılır -> yeni rütbe ya da None."""
    import yonetici_modu as YM
    if YM.acik(p):
        return None                     # yönetici rütbe sistemine girmez (rozeti profil.ship_init verir)
    day = today(now)
    st = p.d.setdefault('rutbe', {})
    if st.get('gun') == day and not force:
        return None
    b = breakdown(p, now)
    rank = rank_of(p, b['rankPoints'], now)
    icon = rank_icon(p, rank)
    prev, prev_rank = st.get('ay'), st.get('rutbe') or 1
    monthly = bool(prev and prev != day[:7] and active_month(st.get('gecmis', {}), prev))
    with p.lock:
        st.update(gun=day, puan=b['rankPoints'], rutbe=rank, ay=day[:7])
        hist = st.setdefault('gecmis', {})
        hist[day] = dict(puan=b['rankPoints'], ep=int(p.d['pilot'].get('ep', 0)), onur=int(p.d['pilot'].get('honourPoints', 0)))
        for old in sorted(hist)[:-40]:
            del hist[old]
        p.d['pilot']['dailyRank'] = icon           # ShipInitializationCommand.dailyRank (profil.PILOT_FIELDS)
        p.dirty = True
    tier = next((t for t in MONTHLY if len(R['esikler']) - prev_rank <= t[0]), None) if monthly else None
    if tier:
        _, tokens, title, kind = tier
        p.ach(kind)                                 # başarım: General of the Month / Acclaimed Pilot sayacı (basarim.SERVER_SIDE)
        p.add_resource(CHAMPION, tokens)
        grant_title(p, title)
    return icon


def grant_title(p, key):
    """Aylık sıralama unvanı: başarım penceresinde seçilir (tabloda olmayan etkinlik unvanı; basarim.title_id sabit kimlik verir)."""
    import basarim as BSM
    BSM.title_id(key)
    st = BSM.state(p)
    if key not in st['unvanlar']:
        with p.lock:
            st['unvanlar'].append(key)
            p.dirty = True


def rank_icon(p, rank):
    """Gemideki rütbe simgesi: rütbe, onur -500 ve altındaysa kanun dışı simgesi."""
    return R['kanun_disi']['simge'] if p.d['pilot'].get('honourPoints', 0) <= R['kanun_disi']['onur'] else rank


def live_rank(p, now=None):
    """Rütbe puanı değişince (uzaylı, EP, onur, görev) rütbe hemen: eşiği geçen oyuncu o anda yükselir (kullanıcı bildirimi
    2026-10-24: puan yetse de rütbe ertesi güne dek değişmiyordu; gerçek oyunda rütbe günde bir, şirketteki sıraya göre verilir,
    tek oyunculuda sıra yok). Günlük kayıt (geçmiş, aylık ödül) daily_rank'te kalır. -> (eski, yeni) ya da None."""
    import yonetici_modu as YM
    if YM.acik(p):
        return None                     # yönetici: rütbe değişmez, "rütbe atladın" yok
    pl = p.d['pilot']
    rank = rank_of(p, breakdown(p, now)['rankPoints'], now)
    icon, old = rank_icon(p, rank), pl.get('dailyRank', 1)
    if icon == old:
        return None
    with p.lock:
        pl['dailyRank'] = icon
        p.d.setdefault('rutbe', {})['rutbe'] = rank
        p.dirty = True
    return old, icon


def active_month(hist, month):
    """Ay içinde rütbe puanı arttı mı (günlük kayıtlardan)."""
    inside = [hist[d]['puan'] for d in sorted(hist) if d.startswith(month)]
    before = [hist[d]['puan'] for d in sorted(hist) if d < month]
    return bool(inside) and max(inside) > (before[-1] if before else 0)


def _since(p, field, days, now=None):
    """Son N günde artış (günlük kayıtlardan; en eski kayıt daha yeniyse ondan)."""
    hist = p.d.get('rutbe', {}).get('gecmis', {})
    cur = breakdown(p, now)['rankPoints'] if field == 'puan' else int(p.d['pilot'].get('ep' if field == 'ep' else 'honourPoints', 0))
    limit = today((now or time.time()) - days * 86400)
    olds = [d for d in sorted(hist) if d <= limit] or sorted(hist)[:1]
    return max(0, cur - hist[olds[-1]][field]) if olds else cur


# ------------------------------------------------------------ Hall of Fame
def _row(p, rank, points, value):
    return {'_': 'HallOfFameDataCommand', 'userId': p.user_id, 'rank': rank, 'time': '', 'points': int(points),
            'value': int(value), 'userName': p.d['pilot'].get('userName', '')}


def _zero_points():
    return {'_': 'HallOfFameRankingPoints', **{k: 0 for k in (
        'honorPoints', 'belowRanking', 'belowPoints', 'missionsCompleted', 'friendlyPlayersDestroyed', 'ExperiencePoints',
        'aboveRanking', 'DestroyedByEnemies', 'npcShotPoints', 'DestroyedByRadiationZone', 'yourRanking', 'yourLevel',
        'daysSinceRegistration', 'yourShipType', 'rankPoints', 'playerShotPoints', 'abovePoints', 'phoenixDestroyed')},
        'shipsCategoryName': ''}


def ranking_points(p, now=None):
    """Rütben sayfası: formülün parçaları, rütbe (yourRanking: rang_N), bir üst rütbe için gereken puan (abovePoints) ve bir alt
    rütbenin puanı (belowPoints: eşiği). İstemci (UIHallOfFameSystem.UpdateDailyRankForServer) "hof_your_rank_below" metnini
    ("The rank directly below yours is that of rang_<yourRanking-1>. Space pilots with this rank have approx. belowPoints rank
    points.") yourRanking 2-20 iken, 1'de "hof_rank_lowest", 21'de "hof_rank_highest" kurar; aboveRanking/belowRanking'i okumaz. Kurduğu
    satırı pencereye koymayıp hep "hof_rank_lowest" yazıyor: istemcinin BepInEx eklentisi (panel/eklenti/Yamalar.cs RutbePenceresi)."""
    b = breakdown(p, now)
    rank = rank_of(p, b['rankPoints'], now)
    nxt = R['esikler'][rank] if rank < len(R['esikler']) else b['rankPoints']
    rakip = gecilecek_puan(p, rank + 1, now) if rank < len(R['esikler']) else None
    if rakip is not None:
        nxt = max(nxt, int(rakip) + 1)                  # şirkette o rütbenin sınırındaki pilotu geçmek gerek
    loot = p.ship()['lootId']
    out = _zero_points()
    out.update(b, yourRanking=rank, aboveRanking=min(rank + 1, 21), abovePoints=max(0, nxt - b['rankPoints']),
               belowRanking=max(rank - 1, 1), belowPoints=R['esikler'][rank - 2] if rank > 1 else 0,
               shipsCategoryName=R['gemi_puan'].get(loot, {}).get('ad', loot.replace('ship_', '').title()))
    return out


def _page(page_type, rows, total=1, cur=1):
    return {'_': 'HallOfFamePages', 'pageType': page_type, 'myList': [], 'dataList': rows, 'type': 0, 'pageSize': NPC_SAYFA,
            'currentPage': cur, 'totalPage': total}


def oyuncular(p):
    """Hall of Fame'e girenler: sunucudaki oyuncuların profilleri (tek oyunculuda yalnız oyuncu; sunucuda olmayan profil tek başına)."""
    import topluluk as TP
    import yonetici_modu as YM
    lst = [k.profil for k in TP.hepsi().values() if not YM.mi(profil=k.profil)]       # yönetici listelerde yok
    return lst if any(x is p for x in lst) or YM.mi(profil=p) else [p]


def _sorted(p, value):
    """Oyuncular değere göre (büyükten; eşitte ada göre) -> [(profil, değer)]."""
    return sorted(((x, value(x)) for x in oyuncular(p)), key=lambda xv: (-xv[1], str(xv[0].d['pilot'].get('userName', '')).lower()))


def _ranked(p, value, extra=None):
    """-> (bütün satırlar, oyuncunun satırı). extra(x, v): satırın value'su (verilmezse değerin kendisi)."""
    rows, mine = [], []
    for i, (x, v) in enumerate(_sorted(p, value)):
        row = _row(x, i + 1, v, extra(x, v) if extra else v)
        rows.append(row)
        if x is p:
            mine = [row]
    return rows, mine


def hof_sira(p, now=None):
    """Pilot kartının sırası: sunucudaki oyuncular arasında rütbe puanına göre."""
    _, mine = _ranked(p, user_score)
    return mine[0]['rank'] if mine else 1


def hof_top(p, f, now=None):
    t = int(f.get('type') or 0)
    out = dict(myRankingPoints=_zero_points(), type=t, allRankList=[], pages=[], myRankList=[])
    if t == 17:
        c = counters(p)
        npc = [{'_': 'HallOfFameDataCommand', 'userId': int(k), 'rank': 0, 'time': '', 'points': v['puan'],
                'value': c['npc'].get(k, 0), 'userName': v['ad']} for k, v in sorted(R['npc_puan'].items(), key=lambda kv: int(kv[0]))]
        pages = [npc[i:i + NPC_SAYFA] for i in range(0, len(npc), NPC_SAYFA)]
        ships = [{'_': 'HallOfFameDataCommand', 'userId': 0, 'rank': 0, 'time': '', 'points': v['puan'], 'value': c['oyuncu'].get(k, 0),
                  'userName': v['ad']} for k, v in R['gemi_puan'].items()]
        out.update(myRankingPoints=ranking_points(p, now),
                   pages=[_page('npcPointsDetails', pg, len(pages), i + 1) for i, pg in enumerate(pages)] + [_page('playerPointsDetails', ships)])
    elif t == 18:                                                    # ana sayfa: puan, ad, sıra; value firma simgesi
        rows, mine = _ranked(p, user_score, lambda x, v: x.d['pilot'].get('factionId', 0))
        out.update(allRankList=rows[:50], myRankList=mine)
    elif t in TOP['klan']:        # sunucunun klanları (klan.py): üyelerin en iyi kullanıcı puanları (forum 127471); gerçek kayıt: points 0,
        #                             value klan puanı
        import klan as KL
        span = {14: 7, 15: 7}.get(t)                                 # 14 haftalık, 15 yükselenler (kullanıcıdaki 2/3 gibi)
        if span:
            who = {KL.ad(x): x for x in oyuncular(p)}
            with KL.LOCK:
                lst = sorted(((k, sum(user_score_since(who[a], span, now) for a in k['uyeler'] if a in who)) for k in KL.KLANLAR.values()),
                             key=lambda kv: (-kv[1], kv[0]['id']))
        else:
            lst = KL.siralama()
        own = KL.klani(p)
        rows, mine = [], []
        for i, (k, v) in enumerate(lst):
            row = dict(_row(p, i + 1, 0, v), userId=k['id'], userName='[%s] %s' % (k['etiket'], k['ad']))
            rows.append(row)
            if k is own:
                mine = [row]
        out.update(allRankList=rows[:50], myRankList=mine)
    else:
        field = 'ep' if t in TOP['exp'] else 'onur' if t in TOP['onur'] else 'puan'

        def value(x):
            days = 7 if t in TOP_WEEK + TOP_CLIMB else 30 if t in TOP_MONTH else None
            if field == 'puan':                                          # En iyi kullanıcı: TP/1000 + ŞP/100 (forum 127509)
                return user_score_since(x, days, now) if days else user_score(x)
            if days:
                return _since(x, field, days, now)
            return int(x.d['pilot'].get('ep' if field == 'ep' else 'honourPoints', 0))
        rows, mine = _ranked(p, value)
        out.update(allRankList=rows[:50], myRankList=mine)
    return [('HallOfFameTopDataListCommand', out)]


def hof_pages(p, f, now=None):
    """HallOfFamePagesRequest {type 1 kullanıcı, 2 EP, 3 onur; page} -> HallOfFamePages (satır: sıra, ad, puan, rütbe)."""
    t = int(f.get('type') or 1)
    value = (user_score if t == 1 else (lambda x: int(x.d['pilot'].get('ep', 0))) if t == 2
             else (lambda x: int(x.d['pilot'].get('honourPoints', 0))))
    rows, mine = _ranked(p, value, lambda x, v: x.d['pilot'].get('dailyRank', 1))
    size = 50
    total = max(1, (len(rows) + size - 1) // size)
    page = min(max(1, int(f.get('page') or 1)), total)
    return [('HallOfFamePages', dict(pageType='', myList=mine, dataList=rows[(page - 1) * size:page * size], type=t, pageSize=size,
                                     currentPage=page, totalPage=total))]


def _runs(p, n):
    return sum(sorted((p.d.get('mimesis') or {}).get('seferler', []), reverse=True)[:n])


HOF_EVENTS = {2: lambda p: (p.d.get('labirent') or {}).get('avlar', 0),                   # FrozenLabyrinth: Synk avları
              3: lambda p: ((p.d.get('pve') or {}).get('ebl') or {}).get('en_iyi', 0),     # EternalGate: Eternal Black Light dalgası
              4: lambda p: _runs(p, 10),                                                   # MimesisMutiny: en iyi 10 sefer (mimesis.total)
              5: lambda p: _runs(p, 1),                                                    # PayloadEscort: en iyi sefer
              6: lambda p: min(((p.d.get('dunya_patronu') or {}).get('etkinlik') or {}).get('hasar', 0), 2 ** 31 - 1)}  # PublicWorldBoss: hasar


def _ebl_time(p):
    t = ((p.d.get('pve') or {}).get('ebl') or {}).get('en_iyi_an')
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(t) / 1000.0)) if t else ''


HOF_TIMES = {3: _ebl_time}          # Time sütunu: en ileri dalganın zamanı (boş görünüyordu; canlı test H76)


def hof_events(p, f):
    """HallOfFameDataListRequest {requested: istemcinin HallOfFameType'ı}: etkinlik sıralamaları. Frozen Labyrinth (Synk avları),
    Eternal Gate (Eternal Black Light'ın en ileri dalgası), Mimesis Mutiny (en iyi 10 seferin toplamı), Payload Escort (en iyi sefer)
    ve World Boss (etkinlik boyu hasar) listelerinde sunucudaki oyuncular (puanı olanlar); Galactic Strife boş."""
    t = int(f.get('requested') or 0)
    rows, mine = [], []
    for x, v in _sorted(p, HOF_EVENTS.get(t, lambda x: 0)):
        if not v:
            continue
        row = dict(_row(x, len(rows) + 1, v, v), time=HOF_TIMES.get(t, lambda x: '')(x))
        rows.append(row)
        if x is p:
            mine = [row]
    return [('HallOfFameDataListCommand', dict(dataList=rows[:50], type=t, pages=[], myList=mine))]


# ------------------------------------------------------------ seyir defteri
def note(p, info_text, info='', count=0, args='{}', quest=0, done=0, t=None):
    """Seyir defterine kayıt (yeni en üstte)."""
    with p.lock:
        lst = p.d.setdefault('seyir_defteri', [])
        lst.insert(0, dict(quest=quest, info=info, args=args, count=int(count), insertDate=stamp(t), questDone=done, infoText=info_text))
        del lst[KAYIT_SINIRI:]
        p.dirty = True


def note_kill(p, npc_id, ep, onur):
    """Uzaylı öldürme: istemcide alt alta "… imha ettin", "XXX TP kazandın", "XXX Şeref Puanı kazandın" (kayıttaki sıra)."""
    if onur:
        note(p, 'honour_points_%d' % onur)
    if ep:
        note(p, 'experience_points_%d' % ep)
    note(p, 'kill_npcID_%s' % npc_id)


def logbook(p, f):
    """LogbookDataListRequest {startIndex: sayfa (0'dan)} -> LogbookDataListCommand (12'şer)."""
    lst = p.d.get('seyir_defteri', [])
    page = max(0, int(f.get('startIndex') or 0))
    rows = [dict(e, _='LogbookDataCommand') for e in lst[page * DEFTER_SAYFA:(page + 1) * DEFTER_SAYFA]]
    return [('LogbookDataListCommand', dict(startIndex=page, total=len(lst), list=rows))]


# ------------------------------------------------------------ hesap geçmişi
CUR = {'kredi': 'GOLD', 'credits': 'GOLD', 'uridyum': 'PEARL', 'uridium': 'PEARL'}


def money(p, cur, amount, description, internal='', qty=0, t=None):
    """Para hareketi kaydı: cur kredi/uridyum (ya da credits/uridium), amount eksiyse harcama."""
    amount = int(amount)
    if not amount or cur not in CUR:
        return
    with p.lock:
        lst = p.d.setdefault('hesap_gecmisi', [])
        lst.insert(0, dict(internalInfo=internal, insertDate=stamp(t), amountType='%s_%s' % (CUR[cur], 'PLUS' if amount > 0 else 'MINUS'),
                           amount=abs(amount), infoText=int(qty), description=description, userId=p.d['pilot'].get('userId', 0)))
        del lst[KAYIT_SINIRI:]
        p.dirty = True
    if amount < 0 and CUR[cur] == 'PEARL':
        # tek oyunculu: uridyum harcamak Pass'lerin "Make a payment" görevini (RECHARGE_AMOUNT) ilerletir; gerçek oyunda ödeme
        # (kullanıcı bildirimi 2026-10-25: Galaxy Trade 0/1 kalıyordu). Uridium Bank'tan alım da sayılır (game.py)
        p.ach('recharge')


# Eski kayıtların açıklamaları -> istemcinin doğru gösterdiği anahtar (canlı test H27; kontrol kanalıyla tek tek denendi):
# _id'li buy_* metinlerinde %ITEMNAME%/%AMOUNT% ham kalıyor, _id'siz olanlar "(adet)" ekliyor (kayıttaki "buy_BATTERY" gibi).
# İstemcide karşılığı olmayan anahtar "Extra purchased" görünüyordu (kazançta da).
DESC_FIX = {'buy_BATTERY_id': 'buy_BATTERY', 'buy_MINES_id': 'buy_MINES', 'buy_EMP_id': 'buy_EMP', 'buy_ROCKET_id': 'buy_ROCKET',
            'buy_LASER_id': 'buy_LASER', 'buy_ROCKETLAUNCHER_id': 'buy_ROCKETLAUNCHER', 'buy_ROBOT_id': 'buy_ROBOT',
            'buy_CPU_id': 'buy_CPU', 'log_purchased_drone_formation_id': 'buy_SPECIAL', 'buy_DRONE_id': 'buy_DRONE',
            'buy_BOOSTER_id': 'buy_BOOSTER', 'buy_ORE_id': 'buy_ORE', 'buy_SPECIAL_id': 'buy_SPECIAL',
            'auction_book_back_money': 'auction_bookMoneyBack', 'uridium_bank': 'title_uridium_bank',
            'payout': 'clan_hl_auszahlungen', 'gg_reward': 'galaxy_gate_done', 'captain_roster_full': 'aktion_system_back'}


def balance(p, f):
    """BalanceInfoListRequest {page: 1'den} -> BalanceInfoListCommand."""
    lst = p.d.get('hesap_gecmisi', [])
    pages = max(1, math.ceil(len(lst) / HESAP_SAYFA))
    page = min(max(1, int(f.get('page') or 1)), pages)
    rows = [dict(e, _='BalanceInfoCommand', description=DESC_FIX.get(e.get('description'), e.get('description')))
            for e in lst[(page - 1) * HESAP_SAYFA:page * HESAP_SAYFA]]
    return [('BalanceInfoListCommand', dict(page=page, pageCount=pages, list=rows))]


def buy_desc(loot):
    """Satın almanın hesap geçmişindeki açıklaması (istemcinin buy_* anahtarları; adet infoText'ten "(5)" olarak eklenir)."""
    if loot.startswith('ammunition_laser_'):
        return 'buy_BATTERY'
    if loot.startswith('ammunition_mine_'):
        return 'buy_MINES'
    if loot.startswith('ammunition_specialammo_emp'):
        return 'buy_EMP'
    if loot.startswith(('ammunition_rocket', 'ammunition_specialammo_')):
        return 'buy_ROCKET'
    if loot.startswith('equipment_weapon_laser_'):
        return 'buy_LASER'
    if loot.startswith('equipment_weapon_rocketlauncher_'):
        return 'buy_ROCKETLAUNCHER'
    if loot.startswith('equipment_generator_'):
        return 'buy_GENERATOR'
    if loot.startswith('equipment_extra_repbot'):
        return 'buy_ROBOT'
    if loot.startswith('equipment_extra_cpu_'):
        return 'buy_CPU'
    if loot.startswith('drone_formation_'):
        return 'buy_SPECIAL'
    if loot.startswith('drone_'):
        return 'buy_DRONE'
    if loot.startswith('booster_'):
        return 'buy_BOOSTER'
    if loot.startswith('resource_ore_'):
        return 'buy_ORE'
    if '_design_' in loot:
        return 'buy_SHIPMODEL'
    if loot.startswith('ship_'):
        return 'buy_SHIP'
    return 'buy_SPECIAL'


def sell_desc(loot):
    if loot.startswith('ammunition_laser_'):
        return 'sell_batteries'
    if loot.startswith(('ammunition_rocket', 'ammunition_mine_', 'ammunition_specialammo_')):
        return 'sell_rockets'
    if loot.startswith('equipment_weapon_laser_'):
        return 'sell_laser'
    if loot.startswith('equipment_weapon_rocketlauncher_'):
        return 'sell_rocketlauncher'
    if loot.startswith('equipment_generator_'):
        return 'sell_generator'
    if loot.startswith('equipment_extra_repbot'):
        return 'sell_robot'
    if loot.startswith('drone_designs_'):
        return 'sell_drone_designs_%s' % loot.split('_')[-1]
    if loot.startswith('drone_'):
        return 'sell_drone'
    return 'sell_special'


def ore_desc(ore_type):
    return 'sellOre_%s' % ORE_NAMES.get(int(ore_type), str(ore_type))
