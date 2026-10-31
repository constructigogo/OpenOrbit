"""Yerel dil modeli: llama.cpp'nin llama-server'ı (OpenAI uyumlu /v1/chat/completions) ve Qwen3 4B Q4_K_M.

Kurulumu panel yapar (panel/llm_kurulum.py: save/llm/); burada süreç başlatma, sağlık denetimi ve çağrı var (oyun sunucusu da panelin
"Test et" düğmesi de bunu kullanır). Qwen3'ün düşünme kipi kapalı: istemde /no_think ve chat_template_kwargs.enable_thinking=false
(düşünürse yanıt saniyeler sürer); yanıtta yine de <think> kalırsa atılır. Paralel yuvalar (-np) sunucunun kendi toplu işlemesidir:
aynı anda gelen istekler tek geçişte hesaplanır.
"""
import json, os, re, socket, subprocess, sys, threading, time
from urllib.request import Request, urlopen

import yollar as YOL

MODEL_DOSYA = 'Qwen3-4B-Q4_K_M.gguf'
BAGLAM = 8192
VARSAYILAN_PORT = 8095
_THINK = re.compile(r'<think>.*?</think>\s*', re.S)


def klasor():
    return os.path.join(YOL.SAVE, 'llm')


def kurulum():
    """Kurulumun kaydı {sunucu, model, test_ok, ...} ya da None."""
    try:
        with open(os.path.join(klasor(), 'kurulum.json'), encoding='utf8') as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    if not (d.get('sunucu') and os.path.isfile(d['sunucu']) and os.path.isfile(os.path.join(klasor(), MODEL_DOSYA))):
        return None
    return d


def bos_port(tercih=VARSAYILAN_PORT):
    for p in [tercih] + list(range(tercih + 1, tercih + 20)):
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError('boş port yok')


class Sunucu:
    """llama-server süreci. baslat() sağlık denetimi geçince döner (ya da RuntimeError)."""

    def __init__(self, yuva=4, log=print):
        self.yuva, self.log = max(1, int(yuva)), log
        self.proc = None
        self.port = None
        self.hazir = False
        self.ad = 'Qwen3 4B'
        self.kullanim = {'istek': 0, 'girdi': 0, 'onbellek': 0, 'cikti': 0}     # token sayımı (llm_saglayici.Uzak ile aynı)

    def baslat(self, bekle_sn=180):
        k = kurulum()
        if k is None:
            raise RuntimeError('dil modeli kurulu değil')
        self.port = bos_port()
        cmd = [k['sunucu'], '-m', os.path.join(klasor(), MODEL_DOSYA), '--host', '127.0.0.1', '--port', str(self.port),
               '-c', str(BAGLAM * self.yuva // 2), '-np', str(self.yuva), '-ngl', '99', '--jinja', '--no-webui']
        kw = {}
        if sys.platform == 'win32':
            kw['creationflags'] = 0x08000000                 # CREATE_NO_WINDOW
        gunluk = open(os.path.join(YOL.LOGS, 'llm_sunucu.log'), 'ab')
        self.proc = subprocess.Popen(cmd, stdout=gunluk, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     cwd=os.path.dirname(k['sunucu']), **kw)
        son = time.time() + bekle_sn
        while time.time() < son:
            if self.proc.poll() is not None:
                raise RuntimeError('llama-server kapandı (çıkış %s; günlük: logs/llm_sunucu.log)' % self.proc.returncode)
            try:
                with urlopen('http://127.0.0.1:%d/health' % self.port, timeout=2) as r:
                    if r.status == 200 and json.loads(r.read() or b'{}').get('status', 'ok') == 'ok':
                        self.hazir = True
                        return self
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        self.durdur()
        raise RuntimeError('llama-server %d sn içinde hazır olmadı' % bekle_sn)

    def durdur(self):
        self.hazir = False
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def sor(self, sistem, kullanici, sema=None, en_cok=220, sicaklik=0.8, zaman=60):
        """Tek çağrı -> (metin ya da JSON nesnesi, süre sn). sema verilirse yanıt o JSON şemasına uyar (llama-server dilbilgisi)."""
        govde = {'messages': [{'role': 'system', 'content': sistem}, {'role': 'user', 'content': '/no_think\n' + kullanici}],
                 'max_tokens': en_cok, 'temperature': sicaklik, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0,
                 'presence_penalty': 1.0, 'chat_template_kwargs': {'enable_thinking': False}}     # Qwen3 düşünmesiz kip önerisi
        if sema is not None:
            govde['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'yanit', 'schema': sema, 'strict': True}}
        t0 = time.time()
        req = Request('http://127.0.0.1:%d/v1/chat/completions' % self.port, data=json.dumps(govde).encode('utf8'),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=zaman) as r:
            d = json.loads(r.read())
        u, k = d.get('usage') or {}, self.kullanim
        k['istek'] += 1
        k['girdi'] += int(u.get('prompt_tokens') or 0)
        k['onbellek'] += int((u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0)
        k['cikti'] += int(u.get('completion_tokens') or 0)
        metin = _THINK.sub('', d['choices'][0]['message'].get('content') or '').strip()
        if sema is not None:                     # ilk geçerli JSON nesnesi (model bazen ardına ikincisini yazıyor)
            i = metin.find('{')
            metin = json.JSONDecoder().raw_decode(metin[i if i >= 0 else 0:])[0]
        return metin, time.time() - t0


def test(log=print):
    """Panelin "Test et" düğmesi: sunucuyu aç, kısa bir soru sor, kapat -> {ok, sure, yanit, hiz}."""
    s = Sunucu(yuva=1, log=log)
    t0 = time.time()
    try:
        s.baslat()
        acilis = time.time() - t0
        yanit, sure = s.sor('Sen bir uzay oyununda pilotsun. Kısa yanıt ver.',
                            'Bir arkadaşın "selam, nasılsın?" yazdı. JSON ver: cevap alanına kısa bir Türkçe yanıt, durum alanına "TAMAM".',
                            sema={'type': 'object', 'properties': {'cevap': {'type': 'string'}, 'durum': {'type': 'string'}},
                                  'required': ['cevap', 'durum']}, en_cok=80)
        ok = isinstance(yanit, dict) and 'TAMAM' in str(yanit.get('durum', '')).upper()
        return {'ok': ok, 'acilis_sn': round(acilis, 1), 'sure_sn': round(sure, 2), 'yanit': yanit.get('cevap') if isinstance(yanit, dict) else str(yanit)}
    finally:
        s.durdur()
