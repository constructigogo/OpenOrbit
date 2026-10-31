"""Gelişmiş kipin dil modeli sağlayıcısı: dahili yerel model (llm_sunucu: llama-server + Qwen3 4B) ya da kullanıcının seçtiği bir
sağlayıcı (OpenAI, Anthropic, Gemini, DeepSeek ...; bilgisayardaki Ollama, LM Studio ya da başka bir OpenAI uyumlu sunucu).

Seçim tek ve genel: save/llm/saglayici.json {secili, saglayicilar: {kimlik: {anahtar, adres, model}}}. Anahtarlar bot paketlerine
girmez; panel onları yalnız maskeli gösterir. Uzak istemci Sunucu ile aynı arayüzü sunar (baslat, sor, durdur): Beyin ikisini ayırt
etmez. Dahili model yalnız İngilizce konuşur (Türkçede zayıf); öteki sağlayıcılarla botlar kendi dillerinde konuşur (cok_dilli).

JSON yanıt: OpenAI uyumlularda önce response_format json_schema, sağlayıcı reddederse json_object, o da olmazsa şema yalnız istemde;
inilen basamak istemcide kalır. Sağlayıcının tanımadığı parametre (temperature, max_tokens ...) 400 verirse o parametre bırakılıp
yeniden sorulur. Anthropic kendi Messages API'siyle (output_config.format) çağrılır.
"""
import json, os, re, threading, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yollar as YOL

YEREL = 'yerel'
# kimlik -> ad, tür ('openai' uyumlu ya da 'anthropic'), varsayılan adres ve model, anahtar gerekir mi, bilgisayarda mı çalışır
SAGLAYICILAR = {
    YEREL: dict(ad='Dahili yerel model (Qwen3 4B)', tur='dahili', adres='', model='', anahtar=False, yerel=True),
    'openai': dict(ad='OpenAI', tur='openai', adres='https://api.openai.com/v1', model='gpt-4.1-mini', anahtar=True, yerel=False),
    'anthropic': dict(ad='Anthropic Claude', tur='anthropic', adres='https://api.anthropic.com/v1', model='claude-haiku-5-5',
                      anahtar=True, yerel=False),
    'gemini': dict(ad='Google Gemini', tur='openai', adres='https://generativelanguage.googleapis.com/v1beta/openai',
                   model='gemini-2.5-flash', anahtar=True, yerel=False),
    'deepseek': dict(ad='DeepSeek', tur='openai', adres='https://api.deepseek.com/v1', model='deepseek-chat', anahtar=True, yerel=False),
    'openrouter': dict(ad='OpenRouter', tur='openai', adres='https://openrouter.ai/api/v1', model='openai/gpt-4.1-mini', anahtar=True,
                       yerel=False),
    'groq': dict(ad='Groq', tur='openai', adres='https://api.groq.com/openai/v1', model='llama-3.3-70b-versatile', anahtar=True,
                 yerel=False),
    'mistral': dict(ad='Mistral', tur='openai', adres='https://api.mistral.ai/v1', model='mistral-small-latest', anahtar=True,
                    yerel=False),
    'xai': dict(ad='xAI Grok', tur='openai', adres='https://api.x.ai/v1', model='grok-3-mini', anahtar=True, yerel=False),
    'ollama': dict(ad='Ollama', tur='openai', adres='http://127.0.0.1:11434/v1', model='qwen3:8b', anahtar=False, yerel=True),
    'lmstudio': dict(ad='LM Studio', tur='openai', adres='http://127.0.0.1:1234/v1', model='', anahtar=False, yerel=True),
    'ozel': dict(ad='Özel (OpenAI uyumlu)', tur='openai', adres='http://127.0.0.1:8080/v1', model='', anahtar=False, yerel=True),
}
_THINK = re.compile(r'<think>.*?</think>\s*', re.S)
_KILIT = threading.Lock()


class SaglayiciHatasi(RuntimeError):
    """Kullanıcıya gösterilen hata (anahtar yanlış, model yok, sunucu kapalı ...)."""


def _yol():
    return os.path.join(YOL.SAVE, 'llm', 'saglayici.json')


def ayar():
    """{secili, saglayicilar: {kimlik: {anahtar, adres, model}}} (dosya yoksa dahili model)."""
    try:
        with open(_yol(), encoding='utf8') as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    if d.get('secili') not in SAGLAYICILAR:
        d['secili'] = YEREL
    d['saglayicilar'] = {k: v for k, v in (d.get('saglayicilar') or {}).items() if k in SAGLAYICILAR and isinstance(v, dict)}
    return d


def secili():
    """Seçili sağlayıcının tam ayarı {kimlik, tur, adres, model, anahtar}."""
    d = ayar()
    return tam(d['secili'], d['saglayicilar'].get(d['secili']) or {})


def tam(kimlik, a):
    s = SAGLAYICILAR[kimlik]
    return {'kimlik': kimlik, 'tur': s['tur'], 'adres': (a.get('adres') or s['adres']).rstrip('/'),
            'model': a.get('model') or s['model'], 'anahtar': a.get('anahtar') or ''}


def cok_dilli(kimlik=None):
    """Botlar kendi dillerinde konuşabilir mi (dahili Qwen3 4B yalnız İngilizce)."""
    return (kimlik or ayar()['secili']) != YEREL


def maske(anahtar):
    return ('…' + anahtar[-4:]) if len(anahtar or '') > 8 else ('•••' if anahtar else '')


def durum():
    """Panelin görünümü: seçili sağlayıcı, her sağlayıcının adresi, modeli ve maskeli anahtarı."""
    d = ayar()
    out = []
    for k, s in SAGLAYICILAR.items():
        a = d['saglayicilar'].get(k) or {}
        out.append({'kimlik': k, 'ad': s['ad'], 'tur': s['tur'], 'anahtar_gerekir': s['anahtar'], 'yerel': s['yerel'],
                    'adres': a.get('adres') or s['adres'], 'model': a.get('model') or s['model'],
                    'varsayilan_adres': s['adres'], 'anahtar': maske(a.get('anahtar') or ''), 'anahtar_var': bool(a.get('anahtar'))})
    return {'secili': d['secili'], 'cok_dilli': cok_dilli(d['secili']), 'liste': out}


def kaydet(kimlik, adres=None, model=None, anahtar=None, sec=True):
    """Sağlayıcının ayarını yaz; anahtar None ya da boşsa eskisi kalır ('-' siler)."""
    if kimlik not in SAGLAYICILAR:
        raise SaglayiciHatasi('Bilinmeyen sağlayıcı.')
    if adres is not None:
        adres = str(adres).strip()
    if adres and not re.fullmatch(r'https?://[^\s]+', adres):
        raise SaglayiciHatasi('Adres http:// ya da https:// ile başlamalı.')
    with _KILIT:
        d = ayar()
        a = dict(d['saglayicilar'].get(kimlik) or {})
        if adres is not None:
            a['adres'] = adres
        if model is not None:
            a['model'] = str(model).strip()[:200]
        if anahtar == '-':
            a.pop('anahtar', None)
        elif anahtar:
            a['anahtar'] = str(anahtar).strip()
        d['saglayicilar'][kimlik] = a
        if sec:
            d['secili'] = kimlik
        os.makedirs(os.path.dirname(_yol()), exist_ok=True)
        gecici = _yol() + '.tmp'
        with open(gecici, 'w', encoding='utf8') as fh:
            json.dump(d, fh, indent=1, ensure_ascii=False)
        os.replace(gecici, _yol())
    return durum()


# ------------------------------------------------------------------------------------------------------------ HTTP
def _basliklar(c):
    h = {'Content-Type': 'application/json', 'User-Agent': 'OpenOrbit'}
    if c['tur'] == 'anthropic':
        h.update({'x-api-key': c['anahtar'], 'anthropic-version': '2023-06-01'})
    elif c['anahtar']:
        h['Authorization'] = 'Bearer ' + c['anahtar']
    if c['kimlik'] == 'openrouter':
        h.update({'HTTP-Referer': 'https://github.com/OpenOrbit', 'X-Title': 'OpenOrbit'})
    return h


def _istek(c, yol, govde=None, zaman=60):
    req = Request(c['adres'] + yol, data=None if govde is None else json.dumps(govde).encode('utf8'), headers=_basliklar(c),
                  method='GET' if govde is None else 'POST')
    with urlopen(req, timeout=zaman) as r:
        return json.loads(r.read() or b'{}')


class HttpHatasi(SaglayiciHatasi):
    def __init__(self, kod, metin):
        self.kod, self.metin = kod, metin
        super().__init__(_insan_hatasi(kod, metin))


def _insan_hatasi(kod, metin):
    """Sağlayıcının hata iletisi (dilden bağımsız: panel her dilde gösterir; iletiler çoğunlukla İngilizce)."""
    try:
        e = json.loads(metin)
        e = e[0] if isinstance(e, list) and e else e
        m = (e.get('error') or {}) if isinstance(e, dict) else {}
        m = m.get('message') if isinstance(m, dict) else (m or e.get('message'))
    except (ValueError, AttributeError):
        m = None
    m = ' '.join(str(m or metin or '').split())[:240]
    return 'HTTP %d: %s' % (kod, m) if m else 'HTTP %d' % kod


def _cagir(c, yol, govde=None, zaman=60):
    try:
        return _istek(c, yol, govde, zaman)
    except HTTPError as e:
        try:
            metin = e.read().decode('utf8', 'replace')
        except OSError:
            metin = ''
        raise HttpHatasi(e.code, metin) from None
    except (URLError, OSError) as e:
        raise SaglayiciHatasi('%s: %s' % (c['adres'], getattr(e, 'reason', e))) from None


def modeller(kimlik, adres=None, anahtar=None):
    """Sağlayıcının modelleri (/models). Anahtar verilmezse kayıtlıdır."""
    if kimlik not in SAGLAYICILAR or kimlik == YEREL:
        raise SaglayiciHatasi('Bilinmeyen sağlayıcı.')
    a = dict(ayar()['saglayicilar'].get(kimlik) or {})
    if adres:
        a['adres'] = adres
    if anahtar:
        a['anahtar'] = anahtar
    c = tam(kimlik, a)
    d = _cagir(c, '/models' + ('?limit=100' if c['tur'] == 'anthropic' else ''), zaman=20)
    liste = d.get('data') if isinstance(d, dict) else d
    adlar = [str(m.get('id') or m.get('name') or '') for m in liste or [] if isinstance(m, dict)]
    return sorted({re.sub(r'^models/', '', x) for x in adlar if x})


# ------------------------------------------------------------------------------------------------------------ istemci
def _anthropic_sema(s):
    """Anthropic yapılandırılmış çıktısının kabul ettiği şema: nesnelerde additionalProperties false; uzunluk ve adet sınırları atılır
    (istemdeki "kısa" yönergesi ve llm.py'nin süzgeci sınırlar)."""
    if isinstance(s, dict):
        out = {k: _anthropic_sema(v) for k, v in s.items() if k not in ('maxLength', 'minLength', 'maxItems', 'minItems')}
        if out.get('type') == 'object':
            out['additionalProperties'] = False
        return out
    if isinstance(s, list):
        return [_anthropic_sema(x) for x in s]
    return s


def _json(metin):
    """Yanıttaki ilk JSON nesnesi (``` çiti, önündeki laf ya da ardındaki ikinci nesne atılır)."""
    metin = _THINK.sub('', metin or '')
    i = metin.find('{')
    if i < 0:
        raise ValueError('yanıtta JSON yok')
    d = json.JSONDecoder(strict=False).raw_decode(metin[i:])[0]       # strict=False: metin içinde ham satır sonu
    if not isinstance(d, dict):
        raise ValueError('yanıt JSON nesnesi değil')
    return d


class Uzak:
    """Seçili uzak ya da bilgisayardaki sağlayıcı (Sunucu'nun arayüzü)."""

    def __init__(self, c, log=print):
        self.c, self.log = c, log
        self.ad = '%s · %s' % (SAGLAYICILAR[c['kimlik']]['ad'], c['model'] or '?')
        self.port = None
        self.hazir = False
        self.json_kip = 'sema'              # sema -> nesne -> istem (sağlayıcı reddettikçe)
        self.atla = set()                   # sağlayıcının tanımadığı parametreler
        self.bekle = 0.0                    # 429'dan sonra bu ana dek istek yok (işler kalıplara düşer)
        self.kullanim = {'istek': 0, 'girdi': 0, 'onbellek': 0, 'cikti': 0}     # token sayımı (önbellekten gelen girdi ayrı)

    def baslat(self, bekle_sn=None):
        if SAGLAYICILAR[self.c['kimlik']]['anahtar'] and not self.c['anahtar']:
            raise SaglayiciHatasi('API anahtarı girilmemiş.')
        if not self.c['model']:
            raise SaglayiciHatasi('Model seçilmemiş.')
        try:                                # bağlantı ve anahtar denetimi: HTTP hatası durdurur, modelin tek bozuk yanıtı durdurmaz
            self.sor('Reply with JSON.', 'Say hi.', sema={'type': 'object', 'properties': {'cevap': {'type': 'string'}},
                                                          'required': ['cevap']}, en_cok=40, zaman=60)
        except ValueError as e:
            self.log('   botlar: sağlayıcının deneme yanıtı bozuk (%s), yine de açılıyor' % e)
        self.hazir = True
        return self

    def durdur(self):
        self.hazir = False

    def sor(self, sistem, kullanici, sema=None, en_cok=220, sicaklik=0.8, zaman=60):
        """Tek çağrı -> (metin ya da JSON nesnesi, süre sn)."""
        if time.time() < self.bekle:
            raise SaglayiciHatasi('istek sınırı: bekleniyor')
        t0 = time.time()
        for _ in range(4):                  # her 400'de bir parametre ya da JSON basamağı düşer
            try:
                metin = (self._anthropic if self.c['tur'] == 'anthropic' else self._openai)(sistem, kullanici, sema, en_cok, sicaklik,
                                                                                            zaman)
                break
            except HttpHatasi as e:
                if e.kod == 429:
                    self.bekle = time.time() + 20
                    raise
                if e.kod != 400 or not self._uyarla(e.metin, sema):
                    raise
        else:
            raise SaglayiciHatasi('sağlayıcı isteği kabul etmedi')
        return (_json(metin) if sema is not None else _THINK.sub('', metin).strip()), time.time() - t0

    def _uyarla(self, metin, sema):
        """400 yanıtına göre isteği değiştir -> yeniden denenebilir mi."""
        m = metin.lower()
        if self.c['tur'] == 'anthropic' and 'effort' in m and 'output_config' not in self.atla:
            self.atla.add('output_config')          # eski model: effort yok (şema da istemde)
            self.json_kip = 'istem'
            return True
        for p in ('temperature', 'top_p', 'max_tokens', 'max_completion_tokens'):
            if p in m and p not in self.atla:
                self.atla.add(p)
                self.log('   botlar: sağlayıcı %s kabul etmiyor, onsuz soruluyor' % p)
                return True
        if sema is not None and self.json_kip != 'istem' and re.search(r'response_format|json_schema|json_object|output_config|'
                                                                       r'schema|format', m):
            self.json_kip = 'nesne' if self.json_kip == 'sema' and self.c['tur'] == 'openai' else 'istem'
            self.log('   botlar: sağlayıcı JSON şemasını kabul etmiyor, JSON kipi: %s' % self.json_kip)
            return True
        return False

    def _say(self, girdi, onbellek, cikti):
        k = self.kullanim
        k['istek'] += 1
        k['girdi'] += int(girdi or 0)
        k['onbellek'] += int(onbellek or 0)
        k['cikti'] += int(cikti or 0)

    @staticmethod
    def _istem_semasi(sistem, sema):
        # şema sistem isteminde (değişken kullanıcı metninin önünde): sağlayıcının önek önbelleğine girer
        return '%s\n\nReply with only one JSON object (no other text) that follows this JSON schema:\n%s' % (
            sistem, json.dumps(sema, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _mesajlar(kullanici):
        """Kullanıcı metni ya da çok turlu konuşma [{role, content}] (ajanın adımları: önek her adımda aynı kalır, önbelleğe girer)."""
        return list(kullanici) if isinstance(kullanici, list) else [{'role': 'user', 'content': kullanici}]

    def _openai(self, sistem, kullanici, sema, en_cok, sicaklik, zaman):
        if sema is not None and self.json_kip != 'sema':
            sistem = self._istem_semasi(sistem, sema)
        # sınır geniş: düşünen modeller düşünceyi de bu sınırdan harcar (yalnız üretilen kadar ödenir; Qwen3 1024'te kesiliyordu)
        govde = {'model': self.c['model'], 'messages': [{'role': 'system', 'content': sistem}] + self._mesajlar(kullanici),
                 'temperature': sicaklik, 'max_tokens': max(en_cok * 8, 4096)}
        if self.c['kimlik'] == 'openai' or 'max_tokens' in self.atla:
            govde['max_completion_tokens'] = govde.pop('max_tokens')
        for p in self.atla:
            govde.pop(p, None)
        if sema is not None and self.json_kip == 'sema':
            govde['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'yanit', 'schema': sema, 'strict': False}}
        elif sema is not None and self.json_kip == 'nesne':
            govde['response_format'] = {'type': 'json_object'}
        d = _cagir(self.c, '/chat/completions', govde, zaman)
        u = d.get('usage') or {}
        self._say(u.get('prompt_tokens', 0), u.get('prompt_cache_hit_tokens')              # DeepSeek
                  or (u.get('prompt_tokens_details') or {}).get('cached_tokens', 0), u.get('completion_tokens', 0))   # OpenAI uyumlu
        ch = (d.get('choices') or [{}])[0]
        metin = (ch.get('message') or {}).get('content') or ''
        if not metin.strip():
            raise ValueError('boş yanıt (%s)' % ch.get('finish_reason'))
        return metin

    def _anthropic(self, sistem, kullanici, sema, en_cok, sicaklik, zaman):
        if sema is not None and self.json_kip != 'sema':
            sistem = self._istem_semasi(sistem, sema)
        govde = {'model': self.c['model'], 'max_tokens': max(en_cok * 8, 2048), 'system': sistem,
                 'messages': self._mesajlar(kullanici), 'cache_control': {'type': 'ephemeral'}}   # önek önbelleği (sistem + adımlar)
        oc = {'effort': 'low'}              # sohbet satırı: derin düşünme gerekmez (gecikme ve maliyet)
        if sema is not None and self.json_kip == 'sema':
            oc['format'] = {'type': 'json_schema', 'schema': _anthropic_sema(sema)}
        govde['output_config'] = oc
        if 'output_config' in self.atla:
            govde.pop('output_config')
        d = _cagir(self.c, '/messages', govde, zaman)
        u = d.get('usage') or {}
        self._say(u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0),
                  u.get('cache_read_input_tokens', 0), u.get('output_tokens', 0))
        if d.get('stop_reason') == 'refusal':
            raise ValueError('model yanıtlamayı reddetti')
        metin = ''.join(b.get('text', '') for b in d.get('content') or [] if b.get('type') == 'text')
        if not metin.strip():
            raise ValueError('boş yanıt (%s)' % d.get('stop_reason'))
        return metin


def istemci(yuva=4, log=print):
    """Seçili sağlayıcının istemcisi: dahili model için llm_sunucu.Sunucu, öteki her sağlayıcı için Uzak."""
    c = secili()
    if c['kimlik'] == YEREL:
        from . import llm_sunucu as LS
        return LS.Sunucu(yuva, log)
    return Uzak(c, log)


def test(log=print):
    """Panelin "Test et" düğmesi (uzak sağlayıcı): kısa bir soru, botların seçilen dilde konuşabildiği de görülsün -> {ok, sure, yanit}."""
    c = secili()
    s = Uzak(c, log)
    t0 = time.time()
    s.baslat()
    acilis = time.time() - t0
    yanit, sure = s.sor('You are a pilot in a space game. Answer briefly.',
                        'A friend wrote "selam, nasılsın?". Give JSON: in cevap a short reply in Turkish, in durum the word "TAMAM".',
                        sema={'type': 'object', 'properties': {'cevap': {'type': 'string'}, 'durum': {'type': 'string'}},
                              'required': ['cevap', 'durum']}, en_cok=80)
    ok = 'TAMAM' in str(yanit.get('durum', '')).upper()
    return {'ok': ok, 'acilis_sn': round(acilis, 1), 'sure_sn': round(sure, 2), 'yanit': yanit.get('cevap'), 'saglayici': s.ad}
