"""Kayıt editörü (karakter editörü; panel ayrı süreçte çalıştırır, sunucu modüllerini panelin sürecine yüklememek için).

Editör kaydın taslağında çalışır (kayitlar.py: <yuva>/duzenleme.json); takma, çıkarma, gemi etkinleştirme, tasarım, config temizleme
ve aktarma oyunun kendi hangar kodundan geçer (magaza.Magaza.handle: istemcinin istekleriyle aynı kurallar), eşya ve gemi vermek
oyunun ödül yolundan (magaza.reward). Adetler (cephane, cevher, kaynak, booster), seviyeler (pilot, dron, P.E.T., eşya yükseltmesi)
doğrudan profilde değişir.

  python -I kayit_editoru.py oku <profil.json> [<asıl profil.json>]
      editörün görünümü; asıl profil verilirse ondan farkların özeti
  python -I kayit_editoru.py uygula <profil.json> <işlemler JSON> [<asıl profil.json>]
      işlemleri sırayla uygula, kaydet -> görünüm (işlemler: ISLEMLER)
  python -I kayit_editoru.py bilgi
      her eşyanın ipucu satırları (değerler, bonuslar, gemiler, yükseltme, satış; bilgi())
  python -I kayit_editoru.py katalog
      eklenebilecek eşyalar: [lootId, kategori, gemi yuvası, P.E.T. yuvası, drona takılır mı]
Çıktı: son satırda JSON {'ok': true, ...} ya da {'ok': false, 'hata': '...', 'kalip': ..., 'arg': [...]} (profil_araci.py gibi).
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
sys.path.insert(0, SERVER)
sys.path.insert(0, HERE)
import profil_araci as PA        # noqa: E402


def _(s):
    """Çevrilecek metin işareti: panel iletiyi kendi dilinde kurar (kayitlar.run_tool, dil.py; test_panel_dil.py toplar)."""
    return s


FIRMALAR = (1, 2, 3)
# oyunun ret nedenleri (BaseKey adı ya da magaza.NEDENLER anahtarı) -> panelin iletisi
RETLER = {
    'error_can_not_equip_to_slot': _('Bu eşya bu yuvaya takılamaz: oyunun kuralları izin vermiyor (gemiye uygunluk, yuva türü ya da config sınırı).'),
    'special_generic_hint': _("Bu ekstradan bu config'te zaten var."),
    'drone_slotCPUinUse': _("Yuva CPU'su kullanımda: önce ekstra yuvalarını boşalt."),
    'pet_gear_requirement': _("P.E.T.'in seviyesi bu eşya için yetmiyor."),
    'dse_ship_not_exist': _('Gemi bulunamadı.'),
    'pet_zaten': _("Bu eşya P.E.T.'te zaten takılı."),
    'pet_dolu': _("P.E.T.'te bu eşya için boş yuva yok."),
    'baska_gemi': _('Bu eşya başka bir gemide takılı: önce oradan çıkar.'),
    'ayni_top': _('Gemide bu türden bir top zaten takılı.'),
    'qfc_gemi': _('Bu Quantum Fluid Core başka bir gemiye bağlı.'),
    'ayni_qfc': _('Gemide bu türden bir Quantum Fluid Core zaten takılı.'),
    'tek_yuva_cpu': _("Bir config'e yalnız bir Slot CPU takılabilir."),
    'ayni_modul': _('Bir gemiye her türden (hasar, can, kalkan, özel) yalnız bir modül takılabilir.'),
}
HOME_MAP = PA.HOME_MAP
CEPHANE = (('ammunition_laser_', 'lazer'), ('ammunition_rocketlauncher_', 'roketatar'), ('ammunition_rocket_', 'roket'),
           ('ammunition_mine_', 'mayin'), ('ammunition_specialammo_', 'ozel'), ('ammunition_', 'diger'))
# katalog kategorileri: (kimlik, istemcinin eşya sınıfları, lootId önekleri); sıra seçim penceresindeki sıra
KATEGORILER = (
    ('gemi', ('ShipType',), ()), ('tasarim', ('ShipDesignType',), ()), ('lazer', ('LaserType',), ('equipment_weapon_laser_',)),
    ('roketatar', ('HellstormLauncherType',), ('equipment_weapon_rocketlauncher_',)),
    ('jenerator', ('ShieldType', 'EngineType'), ('equipment_generator_',)),
    ('ekstra', ('CPUType', 'ExtraType', 'HardwareType', 'RobotType', 'TechType'), ('equipment_extra_',)),
    ('modul', ('ShipUpgradeType', 'QuantumFluidCoreType'), ('equipment_shipupgrade_', 'equipment_core_')),
    ('agir', ('CannonType', 'CannonShieldType', 'DriveType', 'LensType'), ('equipment_cannon', 'equipment_lens_', 'equipment_drive')),
    ('dron', ('DroneType', 'DroneFormationType', 'DroneDesignType', 'DroneCustomizationType'), ('drone_',)),
    ('pet', ('PetGearType', 'AIProtocolType', 'PetCustomizationType', 'PetType'), ('equipment_petgear_', 'equipment_aiprotocol_', 'pet_')),
    ('cephane', ('AmmunitionType',), ('ammunition_',)), ('booster', (), ('booster_',)),
    ('kaynak', ('OreType', 'ItemType', 'SynthesisResourceType'), ('resource_',)), ('paket', (), ('package_', 'deal_')),
)


def _ist():
    return PA._load('istemci_esyalari.json').get('esyalar') or {}


def kategori(loot, ist=None):
    ist = _ist() if ist is None else ist
    sinif = (ist.get(loot) or {}).get('sinif')
    if loot.startswith('booster_'):                    # istemcide ExtraType
        return 'booster'
    for k, siniflar, onekler in KATEGORILER:
        if sinif in siniflar or loot.startswith(onekler):
            return k
    return 'diger'


def katalog():
    import magaza as MG
    import pet as PETM
    ist = _ist()
    return {'esyalar': sorted([l, kategori(l, ist), MG.slot_of(l), PETM.slot_for(l), bool(MG.drone_ok(l) or l in MG.DESIGNS)]
                              for l in PA.known_loots()),
            'kategoriler': [k for k, _s, _o in KATEGORILER] + ['diger']}


# ------------------------------------------------------------------ eşya bilgisi (panelin ipucu)
# sunucunun bonus anahtarı -> istemcinin nitelik adı (metinler_<dil>.json "n": panel o dilde yazar)
NITELIK_ADI = {'lazer': 'dmg_laser', 'roket': 'dmg_rockets', 'can': 'hitpoints', 'kalkan': 'shield', 'hiz': 'speed', 'ep': 'experience',
               'onur': 'honour', 'kacinma': 'evasion', 'npc': 'dmg_npc', 'pvp': 'dmg_pvp', 'lazer_isabet': 'hitchance_laser',
               'roket_isabet': 'hitchance_rocket', 'kalkan_delme': 'shield_penetration'}
BOOSTER_ADI = {'DAMAGE': 'damage', 'HITPOINTS': 'hitpoints', 'SHIELD': 'shield', 'EXPERIENCE_POINTS': 'experience', 'HONOUR_POINTS': 'honour'}


def bilgi():
    """Her eşyanın ipucu satırları (istemcinin ve sunucunun eşya verisinden). lootId -> {
      dg: [[etiket, değer, biçim]]   biçim: n sayı, p yüzde (kesir), x kat, sn saniye, dk dakika, sa saat; etiket panelin metni
      m: [[nitelik, kesir]]          istemcinin nitelik adıyla bonus (modül, tasarım, gemi, formasyon, booster)
      gm: [gemi lootId]              modülün geçtiği gemiler (kararsızda öncelikli gemiler)
      up: [yüzde, azami, tür]        yükseltme (Assembly): seviye başına bonus
      sat: kredi                     satış değeri
      yv: {yuva: sayı}               geminin ve dronun yuvaları
      ph: {yer tutucu: değer}        açıklamadaki %HOURS%, %BOOSTERVALUE% …
      tk: [SHIP, PET, DRONE]         takılabildiği yerler}"""
    import magaza as MG
    import gemi_modul as GM
    import parcacik as PC
    import qfc as QF
    import pet as PETM
    import yukseltme as YK
    import booster as BOOSTER
    E, ist, out = MG.ESYA, _ist(), {}

    def row(l):
        return out.setdefault(l, {})

    def dg(l, etiket, v, bicim='n'):
        if v is not None:
            row(l).setdefault('dg', []).append([etiket, v, bicim])

    def bonus(l, b):
        for k, v in (b or {}).items():
            if k in NITELIK_ADI and v:
                row(l).setdefault('m', []).append([NITELIK_ADI[k], v])
    for l, v in ist.items():
        if l.startswith(('shipId_', 'paymentItem_')):
            continue
        if v.get('satis'):
            row(l)['sat'] = int(v['satis'])
        if v.get('takilir'):
            row(l)['tk'] = v['takilir']
        up = [u for u in v.get('yukseltme', []) if u.get('yuzde')]
        if up and YK.max_level(l):
            row(l)['up'] = [[u['yuzde'] / 100.0, YK.max_level(l), u['tur']] for u in up]
        if v.get('sinif') in ('ShipType', 'ShipDesignType'):
            gr = E['gemiler'].get(l) or E['gemiler'].get(l.split('_design_')[0]) or {}
            dg(l, 'can', v.get('can') or gr.get('hp'))
            dg(l, 'hiz', v.get('hiz') or gr.get('temel_hiz'))
            dg(l, 'kargo', v.get('kargo') or gr.get('kargo'))
            row(l)['yv'] = {k: n for k, n in (v.get('yuvalar') or {}).items() if n}
            bonus(l, gr.get('bonus'))
            bonus(l, (E.get('tasarimlar', {}).get(l) or {}).get('bonus'))
        if l in E['dronlar']:
            row(l)['yv'] = {'default': E['dronlar'][l]['yuva']}
    for l, v in E['lazerler'].items():
        dg(l, 'hasar', v.get('hasar'))
        dg(l, 'pvp_hasar', v.get('pvp_hasar'))
    for l, v in E['kalkan_jeneratorleri'].items():
        dg(l, 'kalkan', v.get('kalkan'))
        dg(l, 'emme', v.get('emme'), 'p')
    for l, v in E['hiz_jeneratorleri'].items():
        dg(l, 'hiz', v.get('hiz'))
    for l, v in E['lazer_cephane'].items():
        dg(l, 'lazer_carpan', v.get('carpan'), 'x')
    for l, v in E['roketler'].items():
        if isinstance(v, dict):
            dg(l, 'hasar', v.get('hasar'))
            dg(l, 'isabet', v.get('isabet'), 'p')
    for l, v in E['onarim_robotlari'].items():
        dg(l, 'tam_onarim', v.get('tam_onarim_sn'), 'sn')
        dg(l, 'dakikada_can', v.get('dakikada_hp'))
    for l, v in E['ekstralar'].items():
        if not isinstance(v, dict):
            continue
        dg(l, 'hak', v.get('hak'))
        dg(l, 'ek_yuva', v.get('ek_yuva'))
        dg(l, 'bekleme', v.get('bekleme_sn'), 'sn')
        dg(l, 'kargo_carpan', v.get('kargo_carpan'), 'x')
    for l, v in E['formasyonlar'].items():
        bonus(l, {k: x for k, x in v.items() if k != 'id'})
    for l, v in E['dron_tasarimlari'].items():
        if isinstance(v, dict):
            bonus(l, v.get('takim'))
            dg(l, 'dron_kalkan', v.get('dron_kalkan'), 'p')
            dg(l, 'dron_lazer', (v.get('takim') or {}).get('dron_lazer'), 'p')
    saat = E['boosterlar'].get('saat', {})
    for l in list(E['boosterlar']['turler']) + list(BOOSTER.ALIAS):
        etki = BOOSTER.B['turler'].get(l) or {}
        for k, x in etki.items():
            if k in BOOSTER_ADI:
                row(l).setdefault('m', []).append([BOOSTER_ADI[k], x / 100.0])
            else:
                dg(l, 'booster_' + k.lower(), x / 100.0, 'p')
        h = saat.get(l) or BOOSTER.B['sure_sn'] / 3600          # mağaza boosterının süresi (booster.add)
        dg(l, 'sure', h, 'sa')
        if etki:
            row(l)['ph'] = {'HOURS': '%g' % h, 'BOOSTERVALUE': next(iter(etki.values()))}
    for l, v in GM.M.items():
        if 'kararsiz' in v:
            kz = v['kararsiz']
            row(l)['gm'] = kz.get('tercih', [])
            dg(l, 'en_az', kz.get('en_az'), 'p')
            a = kz['aralik']
            dg(l, 'deger_araligi', '%d-%d%%' % tuple(a['buyuk']) + (' / %d-%d%%' % tuple(a['kucuk']) if a.get('kucuk') else ''), 't')
            dg(l, 'yeniden_cekme', kz['restabilize']['hak'])
        else:
            row(l)['gm'] = v.get('gemiler', [])
            bonus(l, v.get('etkiler'))
    for l, v in PC.CANNONS.items():
        dg(l, 'taban_hasar', v.get('taban'))
        dg(l, 'element', v.get('element'), 'e')
        dg(l, 'ek_nitelik', v.get('ek'))
        dg(l, 'yeniden_cekme', PC.rerolls(l))
    for l, v in PC.SHIELDS.items():
        dg(l, 'savunma', v.get('savunma'))
        dg(l, 'element', v.get('element'), 'e')
        dg(l, 'ek_nitelik', v.get('ek'))
        dg(l, 'yeniden_cekme', PC.rerolls(l))
    for l, v in PC.DRIVES.items():
        dg(l, 'hasar', v.get('hasar'))
        dg(l, 'atis', v.get('atis'))
    for l, v in PC.LENSES.items():
        dg(l, 'savunma', v.get('savunma'))
    for l, v in QF.TYPES.items():
        dg(l, 'kalite', v.get('kalite'))
        dg(l, 'deger_araligi', '%g-%g%%' % tuple(v['aralik']), 't')
        dg(l, 'azami_seviye', QF.MAX_LV)
    for l, v in PETM.GEARS.items():
        for k, et in (('menzil', 'menzil'), ('sure_sn', 'sure_sn'), ('bekleme_sn', 'bekleme')):
            if isinstance(v.get(k), list):
                dg(l, et, ' / '.join(str(x) for x in v[k]), 't')
    for l, v in PETM.PROTOCOLS.items():
        for k, x in v.items():
            if isinstance(x, list) and k != 'fiyat' and all(isinstance(y, (int, float)) for y in x):
                dg(l, 'seviye_bonus', ' / '.join('%g%%' % (y * 100) for y in x), 't')
                row(l)['ph'] = {'amount': '%g' % (x[0] * 100)}
    return {'esyalar': out}


# ------------------------------------------------------------------ profil ve mağaza
def ac(path):
    """Profil ve oyunun mağazası (hangar kuralları, ödül yolu; profil_araci.ver gibi)."""
    import kapi as KAPI
    import yeni_sistemler as YS
    from profil import Profil
    from magaza import Magaza
    notes = []
    pr = Profil(PA._load('giris.json').get('tohum'), path)
    m = Magaza(pr, PA._load('yanitlar.json'), notes.append)
    m.kapilar = KAPI.Kapilar(pr, notes.append)
    m.yeni = YS.YeniSistemler(pr, m, notes.append)
    return pr, m


def seviyeler():
    return PA._load('seviyeler.json').get('seviyeler') or [[1, 0]]


def seviye_of(ep):
    lv = 1
    for level, need in seviyeler():
        if ep >= need:
            lv = level
    return lv


def _esya(p, i):
    """Takılı ya da envanterdeki eşyanın kısa kaydı: kimlik, lootId, P.E.T. seviyesi (seviyeli dişli ve protokolde), yükseltme seviyesi."""
    import pet as PETM
    l = p.d['esyalar'].get(str(i))
    if not l:
        return None
    out = {'id': int(i), 'lootId': l}
    up = p.d.get('yukseltme_seviye', {}).get(str(i))
    if PETM.has_levels(l):
        out['seviye'] = p.item_level(i)
    if up:
        out['yukseltme'] = int(up)
    r = rng_kaydi(p, i, l)
    if r:
        out['rng'] = r
    return out


# ------------------------------------------------------------------ rastgele nitelikli eşyalar
def rng_turu(l):
    """Eşyanın rastgele nitelik türü: modul (kararsız modül), pc (parçacık topu, kırıcı, sürücü, mercek), qfc ya da None."""
    import gemi_modul as GM
    import parcacik as PC
    import qfc as QF
    return 'modul' if GM.unstable(l) else 'pc' if PC.is_item(l) else 'qfc' if l in QF.TYPES else None


def rng_havuz(l):
    """Düzenleme penceresinin seçenekleri: nitelik adları, birim (kesir ya da yüzde), değer sınırı, hak sınırı, yıldız sınırı."""
    import gemi_modul as GM
    import parcacik as PC
    import qfc as QF
    t = rng_turu(l)
    if t == 'modul':
        a = GM.M[l]['kararsiz']['aralik']
        return {'nitelik': list(GM.IKINCIL), 'birim': 'kesir', 'azami_nitelik': 3, 'hak': GM.restab(l)['hak'],
                'aralik': [a['buyuk'][0], (a.get('kucuk') or a['buyuk'])[1]], 'tercih': GM.M[l]['kararsiz'].get('tercih', [])}
    if t == 'pc':
        if l in PC.DRIVES or l in PC.LENSES:
            pool = {k: v for k, v in PC.D['nitelikler']['surucu'].items() if not k.startswith('_')}
            return {'nitelik': sorted(pool), 'birim': 'yuzde', 'azami_nitelik': len(PC.D['kilit']['seviyeler']), 'hak': 0,
                    'aralik': [min(v[0] for v in pool.values()), max(v[1] for v in pool.values())]}
        pool, tier = PC.pool(l), PC.tier(l)
        return {'nitelik': sorted(pool), 'birim': 'yuzde', 'azami_nitelik': len(pool), 'hak': PC.rerolls(l),
                'aralik': [min(v[tier][0] for v in pool.values()), max(v[tier][1] for v in pool.values())],
                'yildiz': len(PC.C['yildiz']) - 1 if l in PC.CANNONS else 0}
    if t == 'qfc':
        k = QF.kind(l)
        (lo, hi), _, top = QF.ranges(l)
        return {'nitelik': sorted(set(QF.D['ilk_nitelik'][k]) | set(QF.D['ek_nitelik'][k])), 'birim': 'yuzde', 'aralik': [lo, round(top, 2)],
                'azami_nitelik': QF.D['azami_nitelik'], 'azami_seviye': QF.MAX_LV}
    return None


def rng_kaydi(p, i, l):
    """Örneğin rastgele nitelikleri (henüz çekilmediyse yalnız tür: düzenleyince çekilir)."""
    t = rng_turu(l)
    if not t:
        return None
    key = {'modul': 'kararsiz', 'pc': 'parcacik', 'qfc': 'qfc'}[t]
    rec = p.d.get(key, {}).get(str(i))
    out = {'tur': t}
    if rec:
        out.update(nitelik=rec.get('nitelik') or rec.get('nitelikler') or [], hak=rec.get('hak'), gemiler=rec.get('gemiler'),
                   gemi=rec.get('gemi'), seviye=rec.get('seviye'), yildiz=rec.get('yildiz'))
    return {k: v for k, v in out.items() if v is not None}


def istatistik(pr):
    """İstatistik sekmesi (salt okunur; oyuncu isteği 2026-10-30): rütbe puanının parçaları, uzaylı ve oyuncu öldürmeleri, ölümler,
    kapılar (tamamlama ve süreler: kapi.sure_yaz), modların en iyileri."""
    import rutbe as RT
    import kapi as KP
    c = RT.counters(pr)
    npc = sorted(([RT.R['npc_puan'].get(k, {}).get('ad', '#' + k).strip(), int(n), RT.R['npc_puan'].get(k, {}).get('puan', 0)]
                  for k, n in c['npc'].items() if n), key=lambda x: -x[1])
    oyuncu = sorted(([RT.R['gemi_puan'].get(k, {}).get('ad', k.replace('ship_', '')), int(n)] for k, n in c['oyuncu'].items() if n),
                    key=lambda x: -x[1])
    kd = (pr.d.get('kapilar') or {}).get('kapilar') or {}
    sure = pr.d.get('kapi_sureleri') or {}
    kapilar = [{'anahtar': k, 'ad': KP.KAPI[k]['ad'], 'tamam': int((kd.get(k) or {}).get('tamam', 0)), **(sure.get(k) or {})}
               for k in KP.KAPI if (kd.get(k) or {}).get('tamam') or k in sure]
    pve = pr.d.get('pve') or {}
    return {'puan': RT.breakdown(pr), 'npc': npc, 'oyuncu': oyuncu,
            'olum': {'dusman': c['olum_dusman'], 'radyasyon': c['olum_radyasyon'], 'diger': c['olum_diger']},
            'gorev': c['gorev'], 'dost': c['dost'], 'kapilar': kapilar,
            'modlar': {'ebl': int((pve.get('ebl') or {}).get('en_iyi', 0)), 'labirent': int((pr.d.get('labirent') or {}).get('avlar', 0)),
                       'mimesis': int(max((pr.d.get('mimesis') or {}).get('seferler') or [0]))},
            'oynama_sn': int(pr.d.get('oynama_sn') or 0)}


def gorunum(pr, m, asil=None):
    import magaza as MG
    import pet as PETM
    import yukseltme as YK
    import harita as H
    p, pl = pr, pr.d['pilot']
    lv_tab = seviyeler()
    lv = pl.get('level', 1)
    sonraki = next((need for l, need in lv_tab if l == lv + 1), None)
    taban = next((need for l, need in lv_tab if l == lv), 0)
    takili = p.hangar_map()
    yukseltme_azami = {}

    def azami(l):
        if l not in yukseltme_azami:
            yukseltme_azami[l] = YK.max_level(l)
        return yukseltme_azami[l]

    gemiler = []
    for sid, g in p.d['gemiler'].items():
        yuvalar = [y for _p, y in MG.SLOTS if m.capacity(y, sid) > 0]
        konfigler, dronlar, pet = {}, {}, {}
        for cid in sorted(g['konfigler']):
            cfg = p.config(cid, sid)
            konfigler[cid] = {y: {'kapasite': m.capacity(y, sid, cid), 'esyalar': [e for e in (_esya(p, i) for i in cfg.get(y, [])) if e]}
                              for y in yuvalar}
            dcfg = p.drone_config(cid, sid)
            dronlar[cid] = {str(x['kimlik']): {'esyalar': [e for e in (_esya(p, i) for i in dcfg.get(str(x['kimlik']), [])) if e],
                                               'tasarim': _esya(p, p.drone_design_id(x, 'design', cid, sid)),
                                               'gorunum': _esya(p, p.drone_design_id(x, 'visual', cid, sid))}
                            for x in p.d['dronlar']}
            if m.pet.owned:
                pc = m.pet.config(cid, sid)
                pet[cid] = {y: {'kapasite': m.pet.open_slots(y), 'esyalar': [e for e in (_esya(p, i) for i in pc.get(y, [])) if e]}
                            for y in PETM.ALL_SLOTS}
        row = p.ship_row(sid)
        st = m.stats(sid)
        hasar = sum(MG.ESYA['lazerler'].get(l, {}).get('hasar', 0) for l in p.loadout(sid).get('laser', []))
        gemiler.append({'id': sid, 'lootId': g['lootId'], 'tasarim': g.get('tasarim'), 'gorunum': p.ship_look(sid), 'aktif': sid == p.d['aktif_gemi'],
                        'favori': bool(g.get('favori')), 'aktif_konfig': str(g['aktif_konfig']), 'yuvalar': yuvalar, 'konfigler': konfigler,
                        'dronlar': dronlar, 'pet': pet or None, 'tasarimlar': m.designs(sid),
                        'konum': g.get('konum'), 'kayitli': bool(g.get('kayitli_konfig')),
                        'deger': {'can': st.get('hp_max') or row.get('hp'), 'kalkan': st.get('shield_max'), 'hiz': st.get('display'),
                                  'kargo': row.get('kargo'), 'hasar': hasar, 'lazer': st.get('lasers')}})
    gemiler.sort(key=lambda x: (not x['aktif'], not x['favori'], int(x['id'])))

    def hedefler(l):
        h = (['ship'] if MG.slot_of(l) else []) + (['drone'] if MG.drone_ok(l) or l in MG.DESIGNS else [])
        return h + (['pet'] if PETM.slot_for(l) else [])
    envanter = []
    for i, l in p.d['esyalar'].items():
        if int(i) in takili or l.startswith(('drone_', 'ship_')):
            continue
        e = _esya(p, i)
        e.update(hedefler=hedefler(l), yuva=MG.slot_of(l) or PETM.slot_for(l) or ('tasarim' if l in MG.DESIGNS else 'diger'),
                 pet_yuva=PETM.slot_for(l), heat=bool(PETM.heat_slot_ok(l)), azami=azami(l))
        envanter.append(e)
    for g in gemiler:                                  # takılı eşyaların yükseltme sınırı (seviye penceresi)
        for c in list(g['konfigler'].values()) + [d for per in g['dronlar'].values() for d in per.values()] + list((g['pet'] or {}).values()):
            for e in c['esyalar'] if 'esyalar' in c else []:
                e['azami'] = azami(e['lootId'])
    ds = []
    for x in p.d['dronlar']:
        info = MG.DRONES.get(x['lootId'], {})
        ds.append({'id': x['kimlik'], 'lootId': x['lootId'], 'seviye': x.get('seviye', 1), 'puan': x.get('puan', 0),
                   'yukseltme': int(x.get('yukseltme', 0)), 'yukseltme_azami': YK.max_level(x['lootId']) or 16,
                   'kapasite': info.get('yuva', 1), 'tek': bool(info.get('tek'))})
    petd = m.pet.d if m.pet.owned else None
    pet = None
    if petd:
        pet = {'ad': petd.get('ad'), 'seviye': petd.get('seviye', 0), 'ep': petd.get('ep', 0), 'yakit': int(petd.get('yakit', 0)),
               'yakit_azami': PETM.PET['azami_yakit'], 'azami_seviye': len(PETM.PET['seviyeler']) - 1, 'yikik': bool(petd.get('yikik')),
               'yuva': {y: m.pet.open_slots(y) for y in PETM.SLOTS}, 'yuva_azami': dict(PETM.PET['azami_yuva']),
               'heat': m.pet.heat_lv()}
    cephane = [[l, int(n), next((t for pre, t in CEPHANE if l.startswith(pre)), 'diger')] for l, n in sorted(p.d.get('cephane', {}).items())]
    madenler = {m_['oreType']['typeValue']: m_['count'] for m_ in p.d.get('madenler', [])}
    cevherler = [[int(t), loot, int(madenler.get(int(t), 0))] for t, loot in sorted(MG.ESYA['cevherler']['turler'].items(), key=lambda kv: int(kv[0]))]
    simdi = time.time()
    boosterlar = [[l, int(max(0, (b.get('bitis') or 0) - simdi) + (b.get('kalan') or 0))] for l, b in sorted(p.d.get('boosterlar', {}).items())]
    k = p.d.get('konum', {})
    gorevler = p.d.get('gorevler', {})
    out = {
        'pilot': {'ad': pl.get('userName'), 'firma': pl.get('factionId'), 'seviye': lv, 'ep': pl.get('ep', 0), 'seviye_taban': taban,
                  'seviye_sonraki': sonraki, 'azami_seviye': lv_tab[-1][0], 'onur': pl.get('honourPoints', 0), 'kredi': pl.get('credits', 0),
                  'uridyum': pl.get('uridium', 0), 'premium': bool(pl.get('premium')), 'klan': pl.get('clanTag') or '',
                  'rutbe': (p.d.get('rutbe') or {}).get('rutbe'), 'banka': p.d.get('banka', 0), 'oynama_sn': int(p.d.get('oynama_sn') or 0),
                  'olusturma': p.d.get('olusturma'), 'yetenek_puan': (p.d.get('yetenekler') or {}).get('puan', 0)},
        'durum': {'can': int(p.d['gemi'].get('hitPoints', 0)), 'can_azami': p.d['gemi'].get('hitMax', 0),
                  'kalkan': int(p.d['gemi'].get('shield', 0)), 'kalkan_azami': p.d['gemi'].get('shieldMax', 0),
                  'harita': k.get('mapId'), 'harita_ad': H.name(k.get('mapId', 0)), 'ana_harita': H.name(HOME_MAP.get(pl.get('factionId'), 5)),
                  'kargo': p.cargo_used(), 'kargo_azami': p.d['gemi'].get('cargoSpaceMax', 0)},
        'gemiler': gemiler, 'aktif_gemi': p.d['aktif_gemi'], 'dronlar': ds, 'dron_azami': MG.ESYA['dron_azami'],
        'dron_seviyeleri': [x['puan'] for x in MG.LEVELS], 'pet': pet, 'pet_yuvalari': list(PETM.ALL_SLOTS),
        'envanter': envanter, 'cephane': cephane, 'cevherler': cevherler,
        'kaynaklar': [[l, int(n)] for l, n in sorted(p.d.get('diger_esyalar', {}).items()) if isinstance(n, (int, float))],
        'boosterlar': boosterlar,
        'gorevler': {'aktif': len(gorevler.get('aktif', {})), 'tamam': len(gorevler.get('tamam', []))},
        # hakla çalışan CPU'lar (Jump CPU, Cloak …): lootId -> [kalan, bir dolumun hakkı]; hak lootId başına (ekstra.py)
        'haklar': {l: [int(p.d.get('ekstra_haklari', {}).get(l, MG.EK.X[l]['hak'])), MG.EK.X[l]['hak']]
                   for l in sorted(set(p.d['esyalar'].values())) if 'hak' in MG.EK.X.get(l, {})},
        'havuzlar': {l: rng_havuz(l) for l in sorted(set(p.d['esyalar'].values())) if rng_turu(l)},
        'tum_gemiler': sorted(MG.ESYA['gemiler']),
        'istatistik': istatistik(p),
    }
    if asil:
        out['fark'] = fark(asil, p.d)
    return out


# ------------------------------------------------------------------ fark özeti (taslak ile asıl kayıt)
def _yerlesim(d):
    """Takılı eşyaların yeri: (gemi, config, bölüm, eşya) kümesi."""
    out = set()
    for sid, s in d.get('gemiler', {}).items():
        for key in ('konfigler', 'dron_konfig', 'pet_konfig'):
            for cid, cfg in s.get(key, {}).items():
                for slot, ids in cfg.items():
                    out |= {(sid, cid, key, slot, i) for i in ids}
        for cid, cfg in s.get('dron_tasarim', {}).items():
            for did, per in cfg.items():
                out |= {(sid, cid, 'tasarim', did, i) for i in per.values() if i}
    return out


def fark(a, b):
    """Asıl kayıttan (a) taslağa (b) değişenler: alanlar [ad, eski, yeni], eklenen/çıkan eşya (lootId -> adet), adet farkları
    [lootId, eski, yeni], donanım (yeri değişen eşya sayısı), gemiler, dronlar."""
    pa, pb = a.get('pilot', {}), b.get('pilot', {})
    alanlar = [[k, pa.get(f), pb.get(f)] for k, f in (('ad', 'userName'), ('firma', 'factionId'), ('seviye', 'level'), ('ep', 'ep'),
                                                     ('kredi', 'credits'), ('uridyum', 'uridium'), ('onur', 'honourPoints'),
                                                     ('premium', 'premium')) if pa.get(f) != pb.get(f)]
    if a.get('aktif_gemi') != b.get('aktif_gemi'):
        alanlar.append(['aktif_gemi', a['gemiler'].get(a.get('aktif_gemi'), {}).get('lootId'),
                        b['gemiler'].get(b.get('aktif_gemi'), {}).get('lootId')])
    if a.get('konum', {}).get('mapId') != b.get('konum', {}).get('mapId'):
        import harita as H
        alanlar.append(['harita', H.name(a.get('konum', {}).get('mapId', 0)), H.name(b.get('konum', {}).get('mapId', 0))])
    if int(a.get('gemi', {}).get('hitPoints', 0)) != int(b.get('gemi', {}).get('hitPoints', 0)):
        alanlar.append(['can', int(a['gemi'].get('hitPoints', 0)), int(b['gemi'].get('hitPoints', 0))])
    say = lambda d: {l: sum(1 for x in d.values() if x == l) for l in set(d.values())}
    ea, eb = say(a.get('esyalar', {})), say(b.get('esyalar', {}))
    ga = say({k: s['lootId'] for k, s in a.get('gemiler', {}).items()})
    gb = say({k: s['lootId'] for k, s in b.get('gemiler', {}).items()})
    da = say({str(x['kimlik']): x['lootId'] for x in a.get('dronlar', [])})
    db = say({str(x['kimlik']): x['lootId'] for x in b.get('dronlar', [])})
    eklenen, cikan = {}, {}
    for x, y in ((ea, eb), (ga, gb), (da, db)):
        for l in set(x) | set(y):
            n = y.get(l, 0) - x.get(l, 0)
            if n > 0:
                eklenen[l] = eklenen.get(l, 0) + n
            elif n < 0:
                cikan[l] = cikan.get(l, 0) - n
    adetler = []
    for key in ('cephane', 'diger_esyalar'):
        xa, xb = a.get(key, {}), b.get(key, {})
        adetler += [[l, int(xa.get(l, 0)), int(xb.get(l, 0))] for l in sorted(set(xa) | set(xb))
                    if isinstance(xa.get(l, 0), (int, float)) and isinstance(xb.get(l, 0), (int, float)) and int(xa.get(l, 0)) != int(xb.get(l, 0))]
    import magaza as MG
    ma = {m['oreType']['typeValue']: m['count'] for m in a.get('madenler', [])}
    mb = {m['oreType']['typeValue']: m['count'] for m in b.get('madenler', [])}
    adetler += [[MG.ORES.get(t, str(t)), int(ma.get(t, 0)), int(mb.get(t, 0))] for t in sorted(set(ma) | set(mb)) if ma.get(t, 0) != mb.get(t, 0)]
    ba, bb = a.get('boosterlar', {}), b.get('boosterlar', {})
    boost = sorted(l for l in set(ba) | set(bb) if ba.get(l) != bb.get(l))
    seviye = []
    xa = {x['kimlik']: x for x in a.get('dronlar', [])}
    for x in b.get('dronlar', []):
        y = xa.get(x['kimlik'])
        if y and (y.get('seviye'), y.get('yukseltme', 0)) != (x.get('seviye'), x.get('yukseltme', 0)):
            seviye.append(x['lootId'])
    ua, ub = a.get('yukseltme_seviye', {}), b.get('yukseltme_seviye', {})
    seviye += [b['esyalar'][i] for i in set(ua) | set(ub) if ua.get(i, 0) != ub.get(i, 0) and i in b.get('esyalar', {})]
    for key in ('kararsiz', 'parcacik', 'qfc'):                    # rastgele nitelikler (düzenleme penceresi)
        ra, rb = a.get(key, {}), b.get(key, {})
        seviye += [b['esyalar'][i] for i in rb if ra.get(i) and ra[i] != rb[i] and i in b.get('esyalar', {})]
    ha, hb = a.get('ekstra_haklari', {}), b.get('ekstra_haklari', {})
    adetler += [[l, int(ha.get(l, 0)), int(hb[l])] for l in sorted(hb) if ha.get(l) != hb[l]]
    pet_of = lambda d:{k: (d.get('pet') or {}).get(k) for k in ('ad', 'seviye', 'ep', 'yakit', 'yikik', 'yuva')}
    if pet_of(a) != pet_of(b):
        seviye.append('pet')
    pa_, pb_ = _yerlesim(a), _yerlesim(b)
    donanim = len({t[-1] for t in pa_ ^ pb_})
    return {'alanlar': alanlar, 'eklenen': eklenen, 'cikan': cikan, 'adetler': adetler, 'boosterlar': boost, 'seviyeler': seviye,
            'donanim': donanim,
            'sayi': len(alanlar) + len(eklenen) + len(cikan) + len(adetler) + len(boost) + len(seviye) + (1 if donanim else 0)}


# ------------------------------------------------------------------ işlemler
def _int(v, lo, hi):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Sayı bekleniyordu: %s', str(v))


def _sonuc(msgs, ad):
    """Oyunun yanıt komutundan başarı ya da ret nedeni (BaseKey adı)."""
    import magaza as MG
    cmd = next((x[1] for x in msgs or [] if isinstance(x, tuple) and x[0] == ad), None) or {}
    ok = (cmd.get('resultId') if 'resultId' in cmd else cmd.get('result')) == 1
    if not ok:
        e = cmd.get('errorMessage') or cmd.get('description') or {}
        if e.get('type') == 1:                         # ham metin: magaza.neden (istemcinin dili yok: İngilizcesi)
            key = next((k for k, (en, _tr) in MG.NEDENLER.items() if en == e.get('stringBasekey')), e.get('stringBasekey'))
        else:
            key = {v: k for k, v in MG.BASEKEY.items()}.get(e.get('enumBaseKey'))
        if key in RETLER:
            raise ValueError(RETLER[key])
        raise ValueError('Oyun bu işleme izin vermedi: %s', key or '?')


def op_pilot(pr, m, o):
    pl = pr.d['pilot']
    if 'ad' in o:
        import re
        name = str(o['ad']).strip()
        if not re.fullmatch(r'[\w\-\.\[\]\(\) ]{3,20}', name, re.UNICODE):
            raise ValueError('Pilot adı 3-20 karakter olmalı.')
        pl['userName'] = name
    for key, field, lo, hi in (('kredi', 'credits', 0, 10 ** 12), ('uridyum', 'uridium', 0, 10 ** 12),
                               ('onur', 'honourPoints', -10 ** 12, 10 ** 12)):
        if key in o:
            pl[field] = _int(o[key], lo, hi)
    if 'seviye' in o:                                  # seviye: EP o seviyenin eşiği (oyun da seviyeyi EP'den hesaplar)
        pl['level'], pl['ep'] = PA.level_ep(_int(o['seviye'], 1, 10 ** 3))
    if 'ep' in o:
        pl['ep'] = _int(o['ep'], 0, 2 ** 62)
        pl['level'] = seviye_of(pl['ep'])
    if 'premium' in o:
        pl['premium'] = bool(o['premium'])
    if 'firma' in o and int(o['firma']) != pl.get('factionId'):
        f = int(o['firma'])
        if f not in FIRMALAR:
            raise ValueError('Firma seçin (MMO, EIC ya da VRU).')
        pl['factionId'] = f
        ana_us(pr)                                     # öbür firmanın haritasında kalmasın
    pr.dirty = True


def ana_us(pr):
    mid = HOME_MAP.get(pr.d['pilot'].get('factionId'), 5)
    pos = PA.station_pos(mid)
    if not pos:
        raise ValueError('Ana istasyonun konumu bulunamadı.')
    pr.d['konum'] = {'mapId': mid, 'x': pos[0], 'y': pos[1]}
    for s in pr.d['gemiler'].values():                 # gemilerin bekledikleri yer de (etkinleştirince oraya gidilirdi)
        s.pop('konum', None)
    pr.dirty = True


def op_ver(pr, m, o):
    """Eşya ver (oyunun ödül yolu); tak verilirse ({gemi, konfig, hedef, dron, kume}) yeni eşyalar oraya takılır (ödül yolu boş yuvası
    olan etkin gemiye takmış olabilir: önce oradan iner). Hedefin yuvası dolunca kalanlar envanterde kalır."""
    known = PA.known_loots()
    tak = o.get('tak')
    for loot, n in o.get('esyalar') or []:
        loot = str(loot)
        if loot not in known and not loot.startswith(('ammunition_', 'resource_', 'ship_', 'drone_', 'booster_')):
            raise ValueError('Bilinmeyen eşya: %s', loot)
        if '_design_' not in loot and any(s['lootId'] == loot for s in pr.d['gemiler'].values()):
            raise ValueError('Bu gemi zaten hangarda: %s', loot)        # oyunda her gemiden bir tane (ödül yolu atlar)
        before = set(pr.d['esyalar'])
        m.reward(loot, _int(n, 1, 10 ** 9))
        if not tak:
            continue
        yeni = [int(i) for i, l in pr.d['esyalar'].items() if i not in before and l == loot]
        busy, aktif = pr.equipped_ids(), pr.ship()
        for k, i in enumerate(yeni):
            if i in busy:
                m.handle('HangarShipMoveItemsRequest', {'items': [i], 'source': 'ship', 'destination': 'inventory', 'droneId': 0, 'slotSet': '',
                                                        'configId': int(aktif['aktif_konfig']), 'hangarId': aktif['hangarId']})
            try:
                op_tasi(pr, m, dict(tak, yon='tak', esya=i))
            except ValueError:
                if not k:                              # hiçbiri takılamadıysa oyunun nedeni
                    raise
                break


def op_tasi(pr, m, o):
    sid = str(o.get('gemi'))
    if sid not in pr.d['gemiler']:
        raise ValueError('Gemi bulunamadı.')
    tak, hedef = o.get('yon') == 'tak', o.get('hedef') if o.get('hedef') in ('ship', 'drone', 'pet') else 'ship'
    f = {'items': [int(i) for i in (o.get('esyalar') or [o.get('esya')])], 'source': 'inventory' if tak else hedef,
         'destination': hedef if tak else 'inventory', 'configId': int(o.get('konfig') or 1), 'hangarId': pr.ship(sid)['hangarId'],
         'droneId': int(o.get('dron') or 0), 'slotSet': 'default' if hedef == 'drone' else 'heat' if o.get('kume') == 'heat' else ''}
    _sonuc(m.handle('HangarShipMoveItemsRequest', f), 'HangarShipMoveItemsCommand')


def op_sil(pr, m, o):
    """Takılı olmayan eşyaları sil (satmadan)."""
    busy = pr.equipped_ids()
    for i in o.get('esyalar') or []:
        i = int(i)
        if i in busy:
            raise ValueError('Takılı eşya silinemez: önce çıkar.')
        pr.d['esyalar'].pop(str(i), None)
        for k in ('esya_seviye', 'yukseltme_seviye'):
            pr.d.get(k, {}).pop(str(i), None)
    pr.dirty = True


def op_etkin_gemi(pr, m, o):
    msgs, _changed = m.activate({'shipId': str(o.get('gemi'))}, in_station=True, travel=True)
    _sonuc(msgs, 'HangarShipActivateShipCommand')


def op_konfig(pr, m, o):
    sid = str(o.get('gemi') or pr.d['aktif_gemi'])
    ship = pr.ship(sid)
    n = str(_int(o.get('konfig'), 1, 2))
    if n in ship['konfigler']:
        ship['aktif_konfig'] = int(n)
        pr.sync_ekipman()
        m.apply_stats()
        pr.dirty = True


def op_tasarim(pr, m, o):
    msgs, _reload = m.change_model({'shipId': str(o.get('gemi')), 'lootId': str(o.get('lootId') or '')})
    _sonuc(msgs, 'HangarShipChangeShipModelCommand')


def op_favori(pr, m, o):
    _sonuc(m.handle('HangarShipFavouriteRequest', {'shipId': str(o.get('gemi')), 'favourite': bool(o.get('favori'))}),
           'HangarShipFavouriteCommand')


def op_temizle(pr, m, o):
    _sonuc(m.handle('HangarShipClearConfigRequest', {'wipe': 0, 'configId': int(o.get('konfig') or 1), 'shipId': str(o.get('gemi'))}),
           'HangarShipClearConfigCommand')


def op_aktar(pr, m, o):
    _sonuc(m.handle('HangarShipImportConfigRequest', {'originShipId': str(o.get('gemi')), 'targetShipId': str(o.get('hedef'))}),
           'HangarShipImportConfigCommand')


def op_gemi_sil(pr, m, o):
    """Gemiyi hangardan kaldır; üstündeki donanım envantere iner (takılılık gemilerin config'lerinden hesaplanır)."""
    sid = str(o.get('gemi'))
    if sid not in pr.d['gemiler']:
        raise ValueError('Gemi bulunamadı.')
    if sid == pr.d['aktif_gemi']:
        raise ValueError('Etkin gemi kaldırılamaz: önce başka bir gemiyi etkin yap.')
    del pr.d['gemiler'][sid]
    pr.dirty = True


def op_dron(pr, m, o):
    import magaza as MG
    x = pr.drone(o.get('dron') or 0)
    if not x:
        raise ValueError('Dron bulunamadı.')
    if 'seviye' in o:                                  # seviye ve puanı: seviyenin eşiği
        x['seviye'] = _int(o['seviye'], 1, len(MG.LEVELS))
        x['puan'] = max(MG.LEVELS[x['seviye'] - 1]['puan'], min(int(x.get('puan', 0)),
                        MG.LEVELS[x['seviye']]['puan'] - 1 if x['seviye'] < len(MG.LEVELS) else 10 ** 9))
    if 'yukseltme' in o:
        import yukseltme as YK
        x['yukseltme'] = _int(o['yukseltme'], 0, YK.max_level(x['lootId']) or 16)
    pr.sync_ekipman()
    pr.dirty = True


def op_dron_sil(pr, m, o):
    """Dronu kaldır (satmadan): her gemide üstündeki eşyalar ve tasarımları envantere iner."""
    x = pr.drone(o.get('dron') or 0)
    if not x:
        raise ValueError('Dron bulunamadı.')
    for s in pr.d['gemiler'].values():
        for c in s.get('dron_konfig', {}).values():
            c.pop(str(x['kimlik']), None)
        for c in s.get('dron_tasarim', {}).values():
            c.pop(str(x['kimlik']), None)
    pr.d['dronlar'].remove(x)
    pr.sync_ekipman()
    pr.dirty = True


def op_esya_seviye(pr, m, o):
    """Eşyanın yükseltme seviyesi (Assembly: 0 = yükseltilmemiş) ya da P.E.T. dişlisinin / protokolünün seviyesi (1-4)."""
    import yukseltme as YK
    import pet as PETM
    i = str(int(o.get('esya') or 0))
    loot = pr.d['esyalar'].get(i)
    if not loot:
        raise ValueError('Eşya bulunamadı.')
    if 'yukseltme' in o:
        n = _int(o['yukseltme'], 0, YK.max_level(loot))
        lv = pr.d.setdefault('yukseltme_seviye', {})
        if n:
            lv[i] = n
        else:
            lv.pop(i, None)
    if 'seviye' in o and PETM.has_levels(loot):
        n = _int(o['seviye'], 1, 4)
        lv = pr.d.setdefault('esya_seviye', {})
        if n > 1:
            lv[i] = n
        else:
            lv.pop(i, None)
    pr.sync_ekipman()
    m.apply_stats()
    pr.dirty = True


def op_cephane(pr, m, o):
    c = pr.d.setdefault('cephane', {})
    for loot, n in (o.get('adetler') or {}).items():
        if not str(loot).startswith('ammunition_'):
            raise ValueError('Bilinmeyen eşya: %s', loot)
        c[loot] = _int(n, 0, 10 ** 12)
        pr.item_id(loot)                              # istemcinin sayaç kimliği (yeni cephane türü)
    pr.dirty = True


def op_cevher(pr, m, o):
    cur = {mm['oreType']['typeValue']: mm['count'] for mm in pr.d.get('madenler', [])}
    for t, n in (o.get('adetler') or {}).items():
        cur[int(t)] = _int(n, 0, 10 ** 9)
    pr.d['madenler'] = [{'_': 'OreCountModule', 'oreType': {'_': 'OreTypeModule', 'typeValue': t}, 'count': n}
                        for t, n in sorted(cur.items()) if n > 0]
    pr.sync_cargo()
    pr.dirty = True


def op_kaynak(pr, m, o):
    d = pr.d.setdefault('diger_esyalar', {})
    for loot, n in (o.get('adetler') or {}).items():
        if not str(loot).startswith('resource_'):
            raise ValueError('Bilinmeyen eşya: %s', loot)
        n = _int(n, 0, 10 ** 12)
        if n:
            d[loot] = n
        else:
            d.pop(loot, None)
    pr.dirty = True


def op_booster(pr, m, o):
    """Booster süresi (saniye): uzaylıdan düşen booster gibi saklanır (çevrimdışı durur); 0 kaldırır."""
    import booster as BOOSTER
    b = pr.d.setdefault('boosterlar', {})
    for loot, sn in (o.get('sureler') or {}).items():
        if not BOOSTER.is_booster(loot):
            raise ValueError('Bilinmeyen eşya: %s', loot)
        sn = _int(sn, 0, 10 ** 8)
        if sn:
            b[loot] = {'bitis': 0, 'kalan': float(sn)}
        else:
            b.pop(loot, None)
    m.apply_stats()
    pr.dirty = True


def op_pet(pr, m, o):
    import pet as PETM
    if o.get('ver') and not m.pet.owned:
        m.grant_pet(str(o.get('ad') or ''))
    d = pr.d.get('pet')
    if not d:
        raise ValueError('Bu kayıtta P.E.T. yok.')
    if 'ad' in o and str(o['ad']).strip():
        d['ad'] = str(o['ad']).strip()[:24]
    if 'seviye' in o:
        d['seviye'] = _int(o['seviye'], 0, len(PETM.PET['seviyeler']) - 1)
        d['ep'] = PETM.PET['seviyeler'][d['seviye']]['ep']
    if 'yakit' in o:
        d['yakit'] = _int(o['yakit'], 0, PETM.PET['azami_yakit'])
    for y, n in (o.get('yuva') or {}).items():
        if y in PETM.SLOTS:
            d.setdefault('yuva', {})[y] = _int(n, 0, PETM.PET['azami_yuva'].get(y, 0))
    if o.get('onar'):
        d['yikik'] = False
        d['can'] = m.pet.hp_max()
    pr.dirty = True


def op_rng(pr, m, o):
    """Rastgele nitelikli eşyanın kaydı: nitelikler [[ad, değer]] (havuzdan, tekrarsız; modülde kesir, ötekilerde yüzde), modülün
    gemileri, QFC'nin bağlı gemisi ve seviyesi, yeniden çekme hakkı, topun yıldızı. Kayıt yoksa önce oyundaki gibi çekilir."""
    import gemi_modul as GM
    import parcacik as PC
    i = str(int(o.get('esya') or 0))
    loot = pr.d['esyalar'].get(i)
    t = loot and rng_turu(loot)
    if not t:
        raise ValueError('Bu eşyanın düzenlenecek rastgele niteliği yok.')
    hv = rng_havuz(loot)
    if t == 'modul':
        rec = GM.state(pr, i)
    elif t == 'pc':
        rec = PC.ensure(pr, i)
    else:
        rec = pr.d.setdefault('qfc', {}).setdefault(i, {'gemi': pr.ship()['lootId'], 'seviye': 1, 'nitelikler': []})
    if 'nitelik' in o:
        ns = [[str(a), v] for a, v in o['nitelik'] or []]
        names = [a for a, _v in ns]
        if not ns or len(ns) > hv['azami_nitelik'] or len(set(names)) != len(names) or any(a not in hv['nitelik'] for a in names):
            raise ValueError('Nitelikler geçersiz: havuzdan, tekrarsız ve en çok %s tane.', str(hv['azami_nitelik']))
        try:
            vals = [max(0.0, min(1.0 if hv['birim'] == 'kesir' else 1000.0, float(v))) for _a, v in ns]
        except (TypeError, ValueError):
            raise ValueError('Sayı bekleniyordu: %s', str([v for _a, v in ns]))
        rec['nitelikler' if t == 'qfc' else 'nitelik'] = [[a, round(v, 4)] for a, v in zip(names, vals)]
    if 'gemiler' in o and t == 'modul':
        gs = sorted({str(g) for g in o['gemiler'] or []})
        if not gs or any(g not in GM.all_ships() for g in gs):
            raise ValueError('Gemi seçin.')
        rec['gemiler'] = gs
    if 'gemi' in o and t == 'qfc':
        if str(o['gemi']) not in GM.all_ships():
            raise ValueError('Gemi seçin.')
        rec['gemi'] = str(o['gemi'])
    if 'seviye' in o and t == 'qfc':
        rec['seviye'] = _int(o['seviye'], 1, hv['azami_seviye'])
    if 'hak' in o and hv.get('hak') is not None and t != 'qfc':
        rec['hak'] = _int(o['hak'], 0, hv['hak'])
    if 'yildiz' in o and hv.get('yildiz'):
        rec['yildiz'] = _int(o['yildiz'], 0, hv['yildiz'])
    pr.sync_ekipman()
    m.apply_stats()
    pr.dirty = True


def op_cpu_hak(pr, m, o):
    """Hakla çalışan CPU'nun kalan hakkı (ekstra_haklari; lootId başına, oyunda yeniden doldurulur)."""
    import magaza as MG
    loot = str(o.get('lootId') or '')
    if 'hak' not in MG.EK.X.get(loot, {}):
        raise ValueError('Bilinmeyen eşya: %s', loot)
    pr.d.setdefault('ekstra_haklari', {})[loot] = _int(o.get('hak'), 0, 10 ** 6)
    pr.dirty = True


def op_onar(pr, m, o):
    g = pr.d['gemi']
    g['hitPoints'], g['shield'] = g.get('hitMax', g.get('hitPoints', 1)), g.get('shieldMax', g.get('shield', 0))
    g['nanoHull'] = 0
    pr.dirty = True


def op_ana_us(pr, m, o):
    ana_us(pr)


def op_sifirla(pr, m, o):
    PA.sifirla_d(pr.d, [x for x in o.get('bolumler') or [] if x])
    pr.dirty = True


def op_tuslar(pr, m, o):
    import kayitlar as KAY
    pr.d['tus_atamalari'] = KAY.default_key_bindings()
    pr.dirty = True


ISLEMLER = {'pilot': op_pilot, 'ver': op_ver, 'tasi': op_tasi, 'sil': op_sil, 'etkin_gemi': op_etkin_gemi, 'konfig': op_konfig,
            'tasarim': op_tasarim, 'favori': op_favori, 'temizle': op_temizle, 'aktar': op_aktar, 'gemi_sil': op_gemi_sil, 'dron': op_dron,
            'dron_sil': op_dron_sil, 'esya_seviye': op_esya_seviye, 'cephane': op_cephane, 'cevher': op_cevher, 'kaynak': op_kaynak,
            'booster': op_booster, 'pet': op_pet, 'onar': op_onar, 'ana_us': op_ana_us, 'tuslar': op_tuslar, 'sifirla': op_sifirla,
            'rng': op_rng, 'cpu_hak': op_cpu_hak}


def uygula(path, ops, asil=None):
    pr, m = ac(path)
    for o in ops:
        fn = ISLEMLER.get(o.get('islem'))
        if not fn:
            raise ValueError('Bilinmeyen işlem: %s', str(o.get('islem')))
        fn(pr, m, o)
    pr.sync_ekipman()
    pr.save(force=True)
    return gorunum(*ac(path), asil=_oku(asil))


def _oku(path):
    if not path:
        return None
    with open(path, encoding='utf8') as fh:
        return json.load(fh)


def main(argv):
    if argv[:1] == ['oku'] and len(argv) in (2, 3):
        return gorunum(*ac(argv[1]), asil=_oku(argv[2] if len(argv) > 2 else None))
    if argv[:1] == ['uygula'] and len(argv) in (3, 4):
        return uygula(argv[1], json.loads(argv[2]), argv[3] if len(argv) > 3 else None)
    if argv[:1] == ['katalog'] and len(argv) == 1:
        return katalog()
    if argv[:1] == ['bilgi'] and len(argv) == 1:
        return bilgi()
    raise ValueError('kullanım: kayit_editoru.py oku <yol> [asıl] | uygula <yol> <json> [asıl] | katalog')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf8')
    try:
        out = main(sys.argv[1:])
        print(json.dumps(dict(out, ok=True), ensure_ascii=False))
    except Exception as e:
        kalip = e.args[0] if isinstance(e, ValueError) and e.args and isinstance(e.args[0], str) else None
        msg = (kalip % e.args[1:] if len(e.args) > 1 else kalip) if kalip else str(e)
        print(json.dumps({'ok': False, 'hata': '%s: %s' % (type(e).__name__, msg), 'kalip': kalip, 'arg': [str(a) for a in e.args[1:]]},
                         ensure_ascii=False))
