"""Discord Rich Presence (Panel sayfası > Discord Rich Presence): oyuncunun Discord profilinde oyunun anlık hâli.

Panel açık Discord istemcisine yerel IPC'yle bağlanır (Windows: \\\\.\\pipe\\discord-ipc-N; Linux ve macOS: $XDG_RUNTIME_DIR,
$TMPDIR ya da /tmp altında discord-ipc-N soketi; Flatpak ve Snap Discord'unun klasörleri de denenir). Ek paket gerekmez.
Durum oyun sunucusunun canlı durum dosyasından (canli_durum.py) okunur; oyuncu Panel sayfasında neyin görüneceğini seçer
(yapilandirma.py rp_* anahtarları). Görseller uygulamanın Developer Portal'daki Rich Presence varlıkları (Orders.md OP-018; adları
teslim dosyalarınınki); panelin önizlemesi aynı adlarla arayuz/gorsel/discord/*.webp.

Discord etkinlik güncellemesini 20 saniyede 5 kez sınırlar: yalnız değişince ve en sık ARALIK_SN'de bir gönderilir.
"""
import json, os, socket, struct, threading, time, uuid

UYGULAMA = '1565840028163248218'
LOGO = 'oo_rp_logo'
ROZET = 'oo_rp_badge_%s_r2'                    # firma amblemi (küçük görsel)
GITHUB = 'https://github.com/kaanumay/OpenOrbit'
ARALIK_SN = 15
FIRMA = {1: 'mmo', 2: 'eic', 3: 'vru'}


def bolge(harita, kapi):
    """Haritanın büyük görseli: firmanın bölgesi, ortak savaş bölgesi (4-X), üst haritalar (5-X, BL), kapılar."""
    n = str(harita or '')
    if kapi:
        b = 'gate'
    elif len(n) >= 3 and n[1] == '-' and n[0] in '12345':
        b = {'1': 'mmo', '2': 'eic', '3': 'vru', '4': 'battle', '5': 'upper'}[n[0]]
    else:
        b = 'upper' if n.startswith('BL') else 'gate'
    return 'oo_rp_region_' + b


def gemi_adi(loot):
    return str(loot or '').replace('ship_', '', 1).replace('_', ' ').title() or None


def etkinlik(canli, ayar, _, durum):
    """Panelin durumu -> SET_ACTIVITY'nin etkinliği (None: gösterilecek bir şey yok). Önizleme de bunu gösterir.
    canli: canli_durum.json (oyun sunucusu açıksa); durum: 'oyunda' | 'arkadas' (arkadaşın sunucusunda) | 'giris' | 'baslatiliyor'
    | 'panel'."""
    a = lambda k: ayar.get('rp_' + k)
    if durum != 'oyunda' or not canli:
        if durum == 'panel' and not a('panelde'):
            return None
        ust, alt = {'giris': (_('Giriş ekranında'), _('Uzaya çıkmak üzere')), 'baslatiliyor': (_('Oyun başlatılıyor…'), _('Uzaya çıkmak üzere')),
                    'arkadas': (_('Arkadaşının sunucusunda'), _('Birlikte oynuyor'))}.get(durum, (_('Panelde'), _('Oyuna hazırlanıyor')))
        e = {'details': ust, 'state': alt,
             'assets': {'large_image': LOGO, 'large_text': 'OpenOrbit'}}
    else:
        pl, gm, kn, dw = canli.get('pilot', {}), canli.get('gemi', {}), canli.get('konum', {}), canli.get('dunya') or {}
        ust = [('[%s] ' % pl['klan'] if a('klan') and pl.get('klan') else '') + ((pl.get('ad') or '') if a('pilot') else '')]
        if a('gemi') and gemi_adi(gm.get('ad')):
            ust.append(gemi_adi(gm['ad']))
        if a('seviye'):
            ust.append(_('Seviye %s', pl.get('seviye', 1)))
        kapi = dw.get('kapi')
        if not a('durum'):
            hal = None
        elif dw.get('olu'):
            hal = _('Gemisi parçalandı')
        elif kapi:
            hal = ' · '.join(str(x) for x in (kapi.get('ad'), kapi.get('dalga')) if x)
        elif dw.get('savasta'):
            hal = _('Savaşta: %s', dw['hedef']) if dw.get('hedef') else _('Savaşta')
        elif dw.get('guvenli'):
            hal = _('Güvenli bölgede')
        else:
            hal = _('Uzayda uçuyor')
        alt = [x for x in (kn.get('harita') if a('harita') else None, hal) if x]
        firma = FIRMA.get(pl.get('firma'))
        e = {'details': ' · '.join(x.strip() for x in ust if x.strip()) or _('Uzayda'),
             'state': ' · '.join(alt) or _('Oyunda'),
             'assets': {'large_image': bolge(kn.get('harita'), kapi) if a('harita') else LOGO,
                        'large_text': (_('%s haritası', kn['harita']) if a('harita') and kn.get('harita') else 'OpenOrbit')}}
        if a('firma') and firma:
            e['assets'].update(small_image=ROZET % firma, small_text=firma.upper())
        if a('sure') and canli.get('oturum_bas'):
            e['timestamps'] = {'start': int(canli['oturum_bas'])}
        ark = canli.get('arkadas')
        if a('grup') and ark and ark.get('misafirler'):
            e['party'] = {'id': 'openorbit-%s' % (pl.get('ad') or 'host'), 'size': [len(ark['misafirler']) + 1, ark['en_cok'] + 1]}
    e.update(details_url=GITHUB, state_url=GITHUB)       # kartın yazıları ve görselleri tıklanınca GitHub sayfası
    e['assets'].update({k + '_url': GITHUB for k in ('large', 'small') if k + '_image' in e['assets']})
    if a('butonlar'):
        e['buttons'] = [{'label': _("Discord'a katıl")[:32], 'url': 'https://discord.com/invite/openorbit'},
                        {'label': _('OpenOrbit (GitHub)')[:32], 'url': GITHUB}]
    for k in ('details', 'state'):                     # Discord: 2-128 karakter
        e[k] = e[k][:128].ljust(2)
    return e


class Baglanti:
    """Discord istemcisinin IPC'si: el sıkışma, sonra kare (işlem kodu, uzunluk, JSON) gönderip yanıtı okuma."""

    def __init__(self):
        self.f = None

    def _adaylar(self):
        if os.name == 'nt':
            return [r'\\.\pipe\discord-ipc-%d' % i for i in range(10)]
        kokler = [os.environ.get(k) for k in ('XDG_RUNTIME_DIR', 'TMPDIR', 'TMP', 'TEMP')] + ['/tmp']
        kokler = [k for k in kokler if k]
        kokler += [os.path.join(k, s) for k in kokler for s in ('app/com.discordapp.Discord', 'app/com.discordapp.DiscordCanary',
                                                                  'snap.discord', 'snap.discord-canary')]
        return [os.path.join(k, 'discord-ipc-%d' % i) for k in kokler for i in range(10)]

    def ac(self):
        for yol in self._adaylar():
            try:
                if os.name == 'nt':
                    f = open(yol, 'r+b', buffering=0)
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect(yol)
                    f = s.makefile('rwb', buffering=0)
            except OSError:
                continue
            self.f = f
            try:
                op, d = self.istek(0, {'v': 1, 'client_id': UYGULAMA})
                if d.get('evt') == 'READY':
                    return True
            except (OSError, ValueError, struct.error):
                pass
            self.kapat()
        return False

    def istek(self, op, d):
        data = json.dumps(d).encode('utf8')
        self.f.write(struct.pack('<II', op, len(data)) + data)
        bas = self._oku(8)
        op, n = struct.unpack('<II', bas)
        return op, json.loads(self._oku(n).decode('utf8'))

    def _oku(self, n):
        out = b''
        while len(out) < n:
            k = self.f.read(n - len(out))
            if not k:
                raise OSError('discord kapandı')
            out += k
        return out

    def etkinlik(self, e):
        op, d = self.istek(1, {'cmd': 'SET_ACTIVITY', 'args': {'pid': os.getpid(), 'activity': e}, 'nonce': str(uuid.uuid4())})
        if op == 2 or d.get('evt') == 'ERROR':
            raise ValueError((d.get('data') or {}).get('message') or 'SET_ACTIVITY')

    def kapat(self):
        try:
            if self.f:
                self.f.close()
        except OSError:
            pass
        self.f = None


class Sunum:
    """Arka planda: ayar açıkken Discord'a bağlanır, etkinliği değişince gönderir; kapanınca etkinliği temizler."""

    def __init__(self, ayar, kaynak, t, log=print):
        self.ayar, self.kaynak, self.t, self.log = ayar, kaynak, t, log       # kaynak: () -> (canli, durum)
        self.b = Baglanti()
        self.son = None                         # Discord'a en son giden etkinlik
        self.son_an = 0.0
        self.deneme = 0.0
        self.durum = 'kapali'                   # kapali | discord_yok | bagli | hata
        self.hata = None
        self.uyan = threading.Event()

    def baslat(self):
        threading.Thread(target=self._dongu, daemon=True).start()

    def onizleme(self):
        canli, durum = self.kaynak()
        return etkinlik(canli, self.ayar, self.t, durum)

    def _dongu(self):
        while True:
            self.uyan.wait(5)
            self.uyan.clear()
            try:
                self._adim()
            except Exception as e:
                self.log('discord rich presence: %r' % e)
                self.b.kapat()
                self.durum, self.hata, self.son = 'hata', str(e), None

    def _adim(self):
        if not self.ayar.get('discord_rp'):
            if self.b.f:
                try:
                    self.b.etkinlik(None)
                finally:
                    self.b.kapat()
            self.durum, self.son = 'kapali', None
            return
        if not self.b.f:
            if time.monotonic() - self.deneme < 30 and self.durum in ('discord_yok', 'hata'):
                return
            self.deneme = time.monotonic()
            if not self.b.ac():
                self.durum = 'discord_yok'
                return
            self.son, self.hata = None, None
            self.log('discord rich presence: bağlandı')
        self.durum = 'bagli'
        e = self.onizleme()
        if e == self.son or time.monotonic() - self.son_an < ARALIK_SN:
            return
        try:
            self.b.etkinlik(e)
        except OSError:
            self.b.kapat()
            self.durum = 'discord_yok'
            return
        self.son, self.son_an = e, time.monotonic()
