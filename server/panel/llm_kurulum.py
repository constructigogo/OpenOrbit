"""Gelişmiş bot kipinin dil modeli kurulumu (Botlar sayfası > Gelişmiş kip): llama.cpp'nin llama-server'ı ve Qwen3 4B Q4_K_M.

save/llm/ altına iner: llama-<sürüm>/ (sunucu), Qwen3-4B-Q4_K_M.gguf (model, ~2,5 GB; yarım kalırsa kaldığı yerden sürer),
kurulum.json (sunucunun yolu, özetler, testin sonucu). İki dosyanın SHA-256'sı indirilirken doğrulanır. "Test et" sunucuyu açıp
kısa bir soru sorar (bot/llm_sunucu.test); yanıt gelince kurulum tamamdır. Durum: yok, indiriliyor, kuruluyor, kurulu, hazir (test
geçti), hata, durdu.
"""
import hashlib, json, os, platform, shutil, sys, tarfile, threading, time, zipfile

import yollar as YOL
from dil import t as _
from indirme import HttpFile, IndirmeHatasi, Iptal

SURUM = 'b11981'
_GH = 'https://github.com/ggml-org/llama.cpp/releases/download/%s/' % SURUM
SUNUCULAR = {   # platform -> arşiv (Vulkan: NVIDIA, AMD ve Intel ekran kartlarında; yoksa işlemcide çalışır)
    'win-x64': dict(url=_GH + 'llama-%s-bin-win-vulkan-x64.zip' % SURUM, boyut=37346388,
                    sha256='29419511baa97ccb001111a24de4a9e1d62251075749e2a8be56219b51dc21ce'),
    'linux-x64': dict(url=_GH + 'llama-%s-bin-ubuntu-vulkan-x64.tar.gz' % SURUM, boyut=35475421,
                      sha256='5fca386f7256e496cfd1edefe63c00082267e1394c6136b6946a2d70003d3666'),
    'mac-arm64': dict(url=_GH + 'llama-%s-bin-macos-arm64.tar.gz' % SURUM, boyut=16463687,
                      sha256='c5827eba94fe4eb9068a82eab5c25a943dbd2022efe5144d1af817e8b396b45a'),
    'mac-x64': dict(url=_GH + 'llama-%s-bin-macos-x64.tar.gz' % SURUM, boyut=12208100,
                    sha256='0d9e5c5bbeca9beda692e4a46560e83b2385dc79683bd949126b10e34c2ca7ce'),
}
MODEL = dict(ad='Qwen3-4B-Q4_K_M.gguf', url='https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf',
             boyut=2497280256, sha256='7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5')
PARCA = 1 << 20
EN_AZ_BELLEK_GB = 8


def platform_anahtari():
    m = platform.machine().lower()
    if sys.platform == 'win32':
        return 'win-x64' if m in ('amd64', 'x86_64') else None
    if sys.platform == 'darwin':
        return 'mac-arm64' if m in ('arm64', 'aarch64') else 'mac-x64'
    return 'linux-x64' if m in ('x86_64', 'amd64') else None


def bellek_gb():
    """Toplam bellek (GB) ya da None."""
    try:
        if sys.platform == 'win32':
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong), ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 2 ** 30, 1)
        return round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2 ** 30, 1)
    except (OSError, ValueError, AttributeError):
        return None


class LlmKurulum:
    def __init__(self, log=print, opener=None):
        self.log, self.opener = log, opener
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.d = self._bos('yok')
        self.ornekler = []
        self.t = {'durum': 'yok'}

    @staticmethod
    def _bos(durum):
        return {'durum': durum, 'calisiyor': False, 'alinan': 0, 'toplam': 0, 'hiz': 0, 'kalan_sn': None, 'hata': None, 'parca': None}

    def klasor(self):
        return os.path.join(YOL.SAVE, 'llm')

    def kayit(self):
        try:
            with open(os.path.join(self.klasor(), 'kurulum.json'), encoding='utf8') as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            return None
        ok = d.get('surum') == SURUM and d.get('model') == MODEL['sha256'] and os.path.isfile(d.get('sunucu') or '') \
            and os.path.isfile(os.path.join(self.klasor(), MODEL['ad']))
        return d if ok else None

    def state(self):
        with self.lock:
            d = json.loads(json.dumps(self.d))
            t = dict(self.t)
        k = self.kayit()
        if not d['calisiyor'] and k:
            d['durum'] = 'hazir' if k.get('test_ok') else 'kurulu'
        if not d['calisiyor'] and not k and d['durum'] in ('yok', 'kurulu', 'hazir'):
            d['durum'] = 'yok'
            p = os.path.join(self.klasor(), MODEL['ad'] + '.part')
            d['yarim'] = os.path.getsize(p) if os.path.isfile(p) else 0
        pk = platform_anahtari()
        d.update(test=t, boyut=MODEL['boyut'] + (SUNUCULAR[pk]['boyut'] if pk else 0), platform=pk, destekli=bool(pk),
                 bellek_gb=bellek_gb(), en_az_bellek_gb=EN_AZ_BELLEK_GB, cekirdek=os.cpu_count(), model=MODEL['ad'], surum=SURUM,
                 son_test=k.get('test') if k else None)
        return d

    def running(self):
        with self.lock:
            return self.d['calisiyor'] or self.t.get('durum') == 'calisiyor'

    # ------------------------------------------------------------ kurulum
    def start(self):
        with self.lock:
            if not self.d['calisiyor'] and not self.kayit():
                pk = platform_anahtari()
                if not pk:
                    raise IndirmeHatasi(_('Bu bilgisayarın işlemcisi için hazır dil modeli sunucusu yok.'))
                self.stop.clear()
                self.d = dict(self._bos('indiriliyor'), calisiyor=True, toplam=MODEL['boyut'] + SUNUCULAR[pk]['boyut'])
                self.ornekler = []
                threading.Thread(target=self._run, args=(pk,), daemon=True).start()
        return self.state()

    def cancel(self):
        self.stop.set()
        return self.state()

    def sil(self):
        if self.running():
            raise IndirmeHatasi(_('Kurulum ya da test sürüyor.'))
        shutil.rmtree(self.klasor(), ignore_errors=True)
        with self.lock:
            self.d, self.t = self._bos('yok'), {'durum': 'yok'}
        return self.state()

    def _say(self, n):
        now = time.monotonic()
        with self.lock:
            self.d['alinan'] += n
            self.ornekler.append((now, self.d['alinan']))
            while len(self.ornekler) > 2 and now - self.ornekler[0][0] > 8:
                self.ornekler.pop(0)
            t0, b0 = self.ornekler[0]
            if now - t0 >= 1:
                self.d['hiz'] = int((self.d['alinan'] - b0) / (now - t0))
                kalan = max(0, self.d['toplam'] - self.d['alinan'])
                self.d['kalan_sn'] = int(kalan / self.d['hiz']) if self.d['hiz'] > 0 else None

    def _indir(self, url, hedef, boyut, sha):
        """Dosyayı hedefe (yarım .part'tan sürerek) indir, SHA-256'yı doğrula."""
        part = hedef + '.part'
        oz = hashlib.sha256()
        var = os.path.getsize(part) if os.path.isfile(part) else 0
        if var > boyut:
            os.remove(part)
            var = 0
        if var:
            with open(part, 'rb') as fh:
                while True:
                    b = fh.read(PARCA * 8)
                    if not b:
                        break
                    oz.update(b)
            self._say(var)
        kw = {'opener': self.opener} if self.opener else {}
        f = HttpFile(url, self.stop, self._say, **kw)
        try:
            if f.size != boyut:
                raise IndirmeHatasi(_('İndirilen dosyanın boyu beklenenden farklı: yeniden dene.'))
            f.seek(var)
            with open(part, 'ab') as out:
                while f.tell() < f.size:
                    b = f.read(PARCA)
                    if not b:
                        break
                    oz.update(b)
                    out.write(b)
        finally:
            f.close()
        if oz.hexdigest() != sha:
            os.remove(part)
            raise IndirmeHatasi(_('%s beklenen dosya değil (SHA-256 tutmadı): yeniden dene.', os.path.basename(hedef)))
        os.replace(part, hedef)

    def _run(self, pk):
        k = self.klasor()
        try:
            os.makedirs(k, exist_ok=True)
            bos = shutil.disk_usage(k).free
            gerek = MODEL['boyut'] * 1.1 + 300 * 2 ** 20
            if bos < gerek:
                raise IndirmeHatasi(_('Diskte yer yetmiyor: %.1f GB gerekli, %.1f GB boş.', gerek / 2 ** 30, bos / 2 ** 30))
            s = SUNUCULAR[pk]
            arsiv = os.path.join(k, os.path.basename(s['url']))
            self.log('dil modeli sunucusu indiriliyor: %s' % s['url'])
            with self.lock:
                self.d['parca'] = 'llama-server'
            if not os.path.isfile(arsiv):
                self._indir(s['url'], arsiv, s['boyut'], s['sha256'])
            else:
                self._say(s['boyut'])
            with self.lock:
                self.d['parca'] = MODEL['ad']
            model = os.path.join(k, MODEL['ad'])
            if not os.path.isfile(model):
                self.log('dil modeli indiriliyor: %s' % MODEL['url'])
                self._indir(MODEL['url'], model, MODEL['boyut'], MODEL['sha256'])
            else:
                self._say(MODEL['boyut'])
            with self.lock:
                self.d.update(durum='kuruluyor', parca=None)
            hedef = os.path.join(k, 'llama-' + SURUM)
            if os.path.isdir(hedef):
                shutil.rmtree(hedef)
            if arsiv.endswith('.zip'):
                with zipfile.ZipFile(arsiv) as z:
                    for n in z.namelist():
                        from indirme import safe_path
                        safe_path(hedef, n)
                    z.extractall(hedef)
            else:
                with tarfile.open(arsiv) as tf:
                    for m in tf.getmembers():
                        if m.name.startswith('/') or '..' in m.name.split('/'):
                            raise IndirmeHatasi(_('Arşivde geçersiz yol: %s', m.name))
                    tf.extractall(hedef)
            ad = 'llama-server.exe' if sys.platform == 'win32' else 'llama-server'
            sunucu = next((os.path.join(r, ad) for r, _d, fs in os.walk(hedef) if ad in fs), None)
            if not sunucu:
                raise IndirmeHatasi(_('Arşivde %s yok.', ad))
            if sys.platform != 'win32':
                os.chmod(sunucu, 0o755)
            os.remove(arsiv)
            with open(os.path.join(k, 'kurulum.json'), 'w', encoding='utf8') as fh:
                json.dump({'surum': SURUM, 'sunucu': sunucu, 'model': MODEL['sha256'], 'test_ok': False,
                           'zaman': time.strftime('%Y-%m-%d %H:%M:%S')}, fh, indent=1)
            with self.lock:
                self.d.update(durum='kurulu', alinan=self.d['toplam'], kalan_sn=0)
            self.log('dil modeli kuruldu: %s' % sunucu)
        except Iptal:
            with self.lock:
                self.d['durum'] = 'durdu'
        except IndirmeHatasi as e:
            with self.lock:
                self.d.update(durum='hata', hata=str(e))
            self.log('dil modeli kurulamadı: %s' % e)
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
            with self.lock:
                self.d.update(durum='hata', hata=_('Dosya yazılamadı ya da arşiv bozuk: %s', e))
            self.log('dil modeli kurulamadı: %r' % e)
        finally:
            with self.lock:
                self.d['calisiyor'], self.d['hiz'], self.d['parca'] = False, 0, None

    # ------------------------------------------------------------ test
    def test(self):
        with self.lock:
            if self.t.get('durum') == 'calisiyor':
                return self.state()
            if not self.kayit():
                raise IndirmeHatasi(_('Önce dil modelini kur.'))
            self.t = {'durum': 'calisiyor', 'bas': time.time()}
        threading.Thread(target=self._test, daemon=True).start()
        return self.state()

    def test_uzak(self):
        """Seçili uzak sağlayıcının testi (bot/llm_saglayici.test): kısa bir soru, Türkçe yanıt."""
        from bot import llm_saglayici as SG
        c = SG.secili()
        if SG.SAGLAYICILAR[c['kimlik']]['anahtar'] and not c['anahtar']:
            raise IndirmeHatasi(_('Önce API anahtarını gir.'))
        if not c['model']:
            raise IndirmeHatasi(_('Önce bir model seç.'))
        with self.lock:
            if self.t.get('durum') == 'calisiyor':
                return self.state()
            self.t = {'durum': 'calisiyor', 'bas': time.time(), 'saglayici': c['kimlik']}
        threading.Thread(target=self._test_uzak, args=(c['kimlik'],), daemon=True).start()
        return self.state()

    def _test_uzak(self, kimlik):
        from bot import llm_saglayici as SG
        try:
            r = SG.test(self.log)
            with self.lock:
                self.t = dict(r, durum='ok' if r['ok'] else 'hata', saglayici=kimlik,
                              hata=None if r['ok'] else _('Model beklenen yanıtı vermedi.'))
            self.log('dil modeli sağlayıcı testi: %s' % r)
        except Exception as e:
            with self.lock:
                self.t = {'durum': 'hata', 'hata': str(e), 'saglayici': kimlik}
            self.log('dil modeli sağlayıcı testi başarısız: %r' % e)

    def _test(self):
        from bot import llm_sunucu as LS
        try:
            r = LS.test(self.log)
            k = self.kayit() or {}
            k.update(test_ok=bool(r['ok']), test=dict(r, zaman=time.strftime('%Y-%m-%d %H:%M:%S')))
            with open(os.path.join(self.klasor(), 'kurulum.json'), 'w', encoding='utf8') as fh:
                json.dump(k, fh, indent=1, ensure_ascii=False)
            with self.lock:
                self.t = dict(r, durum='ok' if r['ok'] else 'hata', hata=None if r['ok'] else _('Model beklenen yanıtı vermedi.'))
            self.log('dil modeli testi: %s' % r)
        except Exception as e:
            with self.lock:
                self.t = {'durum': 'hata', 'hata': str(e)}
            self.log('dil modeli testi başarısız: %r' % e)
