"""Botların dilleri: bot/diller/<kod>.json (her dil ayrı dosya; yeni dil için bir dosya eklemek yeter).

Bir dil dosyası:
  kod, ad (dilin kendi adı), agirlik ("karışık" kadroda o dilden bot payı)
  adlar      parcalar {liste: [...]} ve desenler [[ağırlık, desen]]: desende {liste}, {liste_k} (küçük harf), {a|b} (iki listeden),
             {liste?} (yarı yarıya boş), {leet:liste}. Adlar oyunun ad kuralına uyar (Latin harf, rakam, _ . -).
  kaliplar   durum -> satırlar (Normal kipin sohbeti; konusma.kalip). Alanlar: {ad} {harita} {seviye} {gemi} {etiket} {klan}
             {lider} {kim} {esya}.
  kisaltma   [[sözcük, kısaltma]] (botun üslubu), ascii {harf: yerine} ve ascii_oran (oyuncuların aksan düşürmesi)
  niyet      niyet -> sözcükler: oyuncunun o dildeki mesajının niyeti (konusma.niyet; tr/en'inkiler konusma'daki ifadelerde)
  tepki      kutlama, veda, donus, yoklama -> ifadeler ve oyun -> oyun sözcükleri: Gelişmiş kipte mesajın türü (llm.mesaj_turu;
             en'inkiler llm.TURLER)
  zararli    kendine zarar, ölüm dileği, ağır hakaret ifadeleri (düzenli ifade olabilir): model satırı bunlardan biriyse susar
             (llm.zararli; en'inkiler llm._ZARARLI). Aksansız yazılmış biçimleri de tutar (karşılaştırma aksanları düşürür).
"""
import json, os

KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'diller')
SIRA = ('tr', 'en', 'de', 'es', 'fr', 'pl', 'pt', 'ru')        # panelin sırası (panelin dilleriyle aynı)


def _yukle():
    out = {}
    for f in sorted(os.listdir(KLASOR)):
        if f.endswith('.json'):
            with open(os.path.join(KLASOR, f), encoding='utf8') as h:
                d = json.load(h)
            out[d['kod']] = d
    return out


DILLER = _yukle()
KODLAR = tuple(k for k in SIRA if k in DILLER) + tuple(sorted(k for k in DILLER if k not in SIRA))


def karisik_sec(r):
    """'Karışık' kadroda bir dil: dosyaların ağırlığına göre."""
    return r.choices(KODLAR, weights=[DILLER[k].get('agirlik', 5) for k in KODLAR])[0]
