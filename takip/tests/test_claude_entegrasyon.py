"""Claude API entegrasyonu — gerçek SDK, sahte HTTP katmanı (ağ erişimi yok).

Anthropic SDK'sı gerçek haliyle kullanılır; yalnızca HTTP taşıma katmanı sahte olduğu için
istek gövdeleri (model, beta başlığı, JSON şeması, araç döngüsü) birebir doğrulanır.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from takip import claude_client
from takip.ai_gateway import ORTAK_ANALIZ_KURALLARI, ai_json_istek
from takip.ai_models import AiUretimKaydi
from takip.models import EtutHocasi, SinifSube, Talebe

TEST_ANAHTAR = "sk-ant-test-gizli-anahtar-123"


def _mesaj(content, stop_reason="end_turn"):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 80},
    }


def _metin(text, stop_reason="end_turn"):
    return _mesaj([{"type": "text", "text": text}], stop_reason)


class SahteClaude:
    """Sıradaki yanıtları döndüren ve gelen istekleri kaydeden HTTP taşıma katmanı."""

    def __init__(self):
        self.yanitlar: list = []
        self.istekler: list[httpx2.Request] = []

    def ekle(self, yanit):
        self.yanitlar.append(yanit)

    def govde(self, i=-1) -> dict:
        return json.loads(self.istekler[i].content.decode("utf-8"))

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.istekler.append(request)
        if not self.yanitlar:
            raise AssertionError("Beklenmeyen Claude isteği")
        yanit = self.yanitlar.pop(0)
        if isinstance(yanit, Exception):
            raise yanit
        if isinstance(yanit, tuple):
            durum, govde = yanit
            return httpx2.Response(durum, json=govde, headers={"request-id": "req_test"})
        return httpx2.Response(200, json=yanit, headers={"request-id": "req_test"})


@override_settings(
    ANTHROPIC_API_KEY=TEST_ANAHTAR,
    AI_ASSISTANT_ENABLED=True,
    AI_PLATFORM_ENABLED=True,
    AI_RET_YEDEK=True,
)
class ClaudeTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.sahte = SahteClaude()
        claude_client._client = anthropic.Anthropic(
            api_key=TEST_ANAHTAR,
            max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self.sahte)),
        )
        self.admin = User.objects.create_superuser("ai_admin", "ai@example.com", "test-pass")
        self.sinif = SinifSube.objects.create(sinif="5", sube="A")
        hoca_user = User.objects.create_user("ai-hoca", password="x")
        self.hoca = EtutHocasi.objects.create(ad_soyad="Etüt Hocası Test", user=hoca_user, aktif=True)
        self.hoca.sorumlu_sinif_subeler.add(self.sinif)
        self.talebe = Talebe.objects.create(
            ad_soyad="Yusuf Emre Test",
            sinif_sube=self.sinif,
            etut_hocasi=self.hoca,
            dini_ders_hocasi=self.hoca,
            tc_kimlik="10000000146",
        )

    def tearDown(self):
        claude_client._client = None


class ClaudeIstemciTests(ClaudeTestBase):
    @override_settings(ANTHROPIC_API_KEY="")
    def test_anahtar_yoksa_istek_yapilmaz(self):
        sonuc = claude_client.claude_istek(
            gorev="analiz", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100
        )
        self.assertEqual(sonuc.hata, "yapilandirilmamis")
        self.assertEqual(self.sahte.istekler, [])

    def test_analiz_istegi_sema_model_ve_beta_basligi(self):
        self.sahte.ekle(
            _metin(json.dumps({"ozet": "Özet metni", "dayanaklar": "• net: 40", "belirsizlikler": "Yok."}))
        )
        sonuc = ai_json_istek(system="Sistem", user_prompt="VERİ: {}", alanlar=["ozet"])
        self.assertTrue(sonuc.ok)
        self.assertEqual(sonuc.veri["ozet"], "Özet metni")

        istek = self.sahte.istekler[0]
        self.assertEqual(istek.headers["x-api-key"], TEST_ANAHTAR)
        self.assertIn("server-side-fallback-2026-07-01", istek.headers.get("anthropic-beta", ""))
        govde = self.sahte.govde()
        self.assertEqual(govde["model"], "claude-opus-5-5")
        self.assertEqual(govde["fallbacks"], "default")
        self.assertNotIn("temperature", govde)
        self.assertNotIn("thinking", govde)
        self.assertEqual(govde["output_config"]["effort"], "medium")
        sema = govde["output_config"]["format"]["schema"]
        self.assertEqual(sorted(sema["required"]), ["belirsizlikler", "dayanaklar", "ozet"])
        self.assertFalse(sema["additionalProperties"])
        self.assertIn(ORTAK_ANALIZ_KURALLARI.strip()[:40], govde["system"])

    def test_serbest_uretim_dusuk_effort_ve_semasiz(self):
        from takip.ai_gateway import ai_json_uret

        self.sahte.ekle(_metin('Plan: {"plans": [1, 2]}'))
        veri = ai_json_uret(system="Yalnızca JSON", user_prompt="plan", temperature=0.4, max_tokens=1000)
        self.assertEqual(veri, {"plans": [1, 2]})
        govde = self.sahte.govde()
        self.assertEqual(govde["output_config"], {"effort": "low"})
        self.assertEqual(govde["max_tokens"], 1000 + 3000)
        self.assertNotIn("Ortak analiz kuralları", govde["system"])

    @override_settings(AI_RET_YEDEK=False)
    def test_ret_yedegi_kapatilabilir(self):
        self.sahte.ekle(_metin("{}"))
        claude_client.claude_istek(
            gorev="analiz", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100
        )
        self.assertNotIn("fallbacks", self.sahte.govde())
        self.assertNotIn("server-side-fallback", self.sahte.istekler[0].headers.get("anthropic-beta", ""))

    def test_hata_kodlari_kullanici_mesajina_cevrilir(self):
        durumlar = [
            ((429, {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}}), "kota"),
            ((401, {"type": "error", "error": {"type": "authentication_error", "message": "x"}}), "yetki"),
            ((529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}), "sunucu"),
            ((404, {"type": "error", "error": {"type": "not_found_error", "message": "x"}}), "model"),
            (httpx2.ReadTimeout("zaman"), "zaman_asimi"),
            (httpx2.ConnectError("yok"), "baglanti"),
        ]
        for yanit, beklenen in durumlar:
            with self.subTest(beklenen=beklenen):
                self.sahte.ekle(yanit)
                sonuc = claude_client.claude_istek(
                    gorev="sohbet",
                    system="s",
                    messages=[{"role": "user", "content": "x"}],
                    max_tokens=100,
                    max_retries=0,
                )
                self.assertEqual(sonuc.hata, beklenen)
                self.assertTrue(sonuc.mesaj)

    def test_asiri_yukte_bir_kez_yeniden_dener(self):
        self.sahte.ekle((529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}))
        self.sahte.ekle(_metin("tamam"))
        sonuc = claude_client.claude_istek(
            gorev="sohbet", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100
        )
        self.assertTrue(sonuc.ok)
        self.assertEqual(len(self.sahte.istekler), 2)

    def test_zaman_asiminda_yeniden_denemez(self):
        self.sahte.ekle(httpx2.ReadTimeout("zaman"))
        sonuc = claude_client.claude_istek(
            gorev="analiz", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100
        )
        self.assertEqual(sonuc.hata, "zaman_asimi")
        self.assertEqual(len(self.sahte.istekler), 1)

    def test_ret_ve_kesilme_durumlari(self):
        self.sahte.ekle(_mesaj([], "refusal"))
        self.assertEqual(
            claude_client.claude_istek(
                gorev="analiz", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100
            ).hata,
            "ret",
        )
        self.sahte.ekle(_metin('{"ozet": "yarım', "max_tokens"))
        sonuc = ai_json_istek(system="s", user_prompt="x", alanlar=["ozet"])
        self.assertIsNone(sonuc.veri)
        self.assertIn("çıktı sınırına", sonuc.hata_mesaji)

    @override_settings(AI_MAX_GIRDI_KARAKTER=50)
    def test_girdi_siniri_asilinca_istek_gonderilmez(self):
        sonuc = ai_json_istek(system="s", user_prompt="x" * 100, alanlar=["ozet"])
        self.assertIsNone(sonuc.veri)
        self.assertIn("çok büyük", sonuc.hata_mesaji)
        self.assertEqual(self.sahte.istekler, [])

    def test_loglarda_anahtar_ve_icerik_yok(self):
        self.sahte.ekle((400, {"type": "error", "error": {"type": "invalid_request_error", "message": "x"}}))
        self.sahte.ekle(_metin("tamam"))
        with self.assertLogs("takip.claude_client", level="INFO") as kayit:
            for _ in range(2):
                claude_client.claude_istek(
                    gorev="sohbet",
                    system="s",
                    messages=[{"role": "user", "content": "Yusuf Emre Test hakkında"}],
                    max_tokens=100,
                )
        tum = "\n".join(kayit.output)
        self.assertNotIn(TEST_ANAHTAR, tum)
        self.assertNotIn("Yusuf Emre", tum)
        self.assertIn("req_test", tum)


class AnalizTests(ClaudeTestBase):
    def test_gelisim_zekasi_dayanak_ve_belirsizlik_bolumleri(self):
        from takip.ai_service import gelisim_zekasi_analizi

        self.sahte.ekle(
            _metin(
                json.dumps(
                    {
                        "ozet": "Veri yetersiz: deneme kaydı yok.",
                        "guclu_yonler": "Veri yetersiz.",
                        "gelisim_alanlari": "Veri yetersiz.",
                        "risk_sinyalleri": "Veriyle desteklenen risk sinyali yok.",
                        "mudahale_onerileri": "• Önce deneme ve soru kaydı girilmeli.",
                        "veli_mesaji": "Takip verisi birikince paylaşılacak.",
                        "dayanaklar": "• denemeler: kayıt yok",
                        "belirsizlikler": "• denemeler ve ktt boş",
                    },
                    ensure_ascii=False,
                )
            )
        )
        sonuc = gelisim_zekasi_analizi(self.admin, self.talebe, yenile=True)
        self.assertTrue(sonuc.yapay_zeka)
        basliklar = [b.baslik for b in sonuc.bolumler]
        self.assertIn("Dayanaklar (Kullanılan Veriler)", basliklar)
        self.assertIn("Belirsizlikler ve Eksik Veri", basliklar)

        istem = self.sahte.govde()["messages"][0]["content"]
        self.assertIn("rapor_tarihi", istem)
        self.assertIn('"eksik_alanlar"', istem)
        self.assertIn("denemeler", istem)  # boş deneme listesi eksik alan olarak işaretlenir
        self.assertIn("Yusuf Emre Test", istem)

    def test_api_hatasinda_uyari_gosterilir_ve_onbellege_yazilmaz(self):
        from takip.ai_service import kurum_zekasi_ozet

        self.sahte.ekle((429, {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}}))
        sonuc = kurum_zekasi_ozet(self.admin, yenile=True)
        self.assertFalse(sonuc.yapay_zeka)
        self.assertIn("istek sınırına", sonuc.uyari)
        self.assertTrue(sonuc.bolumler)
        self.assertFalse(AiUretimKaydi.objects.filter(tur="kurum_zekasi").exists())

    def test_basarili_analiz_onbellekten_gelir(self):
        from takip.ai_service import kurum_zekasi_ozet

        self.sahte.ekle(
            _metin(
                json.dumps(
                    {
                        "kurum_ozeti": "1 talebe.",
                        "oncelikli_talebeler": "Yok.",
                        "sinif_analizi": "5/A: 1",
                        "mudahale_onerileri": "• Kayıt girişi",
                        "dayanaklar": "• talebe_sayisi: 1",
                        "belirsizlikler": "Az veri.",
                    }
                )
            )
        )
        ilk = kurum_zekasi_ozet(self.admin)
        ikinci = kurum_zekasi_ozet(self.admin)
        self.assertTrue(ilk.yapay_zeka and ikinci.yapay_zeka)
        self.assertEqual(len(self.sahte.istekler), 1)

    @override_settings(AI_YENILE_GUNLUK_LIMIT=1)
    def test_yenile_siniri(self):
        from takip.ai_service import kurum_zekasi_ozet

        govde = {
            "kurum_ozeti": "a",
            "oncelikli_talebeler": "b",
            "sinif_analizi": "c",
            "mudahale_onerileri": "d",
            "dayanaklar": "e",
            "belirsizlikler": "f",
        }
        self.sahte.ekle(_metin(json.dumps(govde)))
        kurum_zekasi_ozet(self.admin, yenile=True)
        sonuc = kurum_zekasi_ozet(self.admin, yenile=True)
        self.assertEqual(len(self.sahte.istekler), 1)
        self.assertIn("yenileme sınırına", sonuc.uyari)

    def test_kurum_soru_icgorusu_gercek_veri_gonderir(self):
        from takip.ai_service import soru_takip_insight

        self.sahte.ekle(
            _metin(json.dumps({"ozet": "a", "trend": "b", "oneri": "c", "dayanaklar": "d", "belirsizlikler": "e"}))
        )
        soru_takip_insight(self.admin, None, yenile=True)
        istem = self.sahte.govde()["messages"][0]["content"]
        self.assertIn("son_30_gun", istem)
        self.assertIn("ders_bazinda_30_gun", istem)

    def test_ktt_analizi_ayni_veri_icin_onbellekten(self):
        from takip.ktt_analiz_llm import ktt_analiz_llm_uret

        govde = {
            "ozet": "Ortalama 60.",
            "olcum_bulgulari": "a",
            "pedagojik_yorum": "b",
            "risk_ve_firsatlar": "c",
            "mudahale_onerileri": "d",
            "veli_iletisimi": "e",
            "dayanaklar": "f",
            "belirsizlikler": "g",
        }
        self.sahte.ekle(_metin(json.dumps(govde)))
        payload = {"sinav": {"ad": "Kesirler KTT"}, "istatistik": {"ortalama": 60}}
        bolumler, hata = ktt_analiz_llm_uret(payload, tur="sinav_grup")
        self.assertEqual(hata, "")
        self.assertEqual(bolumler["belirsizlikler"], "g")
        tekrar, _ = ktt_analiz_llm_uret(payload, tur="sinav_grup")
        self.assertEqual(tekrar, bolumler)
        self.assertEqual(len(self.sahte.istekler), 1)

    def test_ktt_hata_mesaji_doner(self):
        from takip.ktt_analiz_llm import ktt_analiz_llm_uret

        self.sahte.ekle(httpx2.ReadTimeout("zaman"))
        bolumler, hata = ktt_analiz_llm_uret({"x": 1}, tur="rapor_grup")
        self.assertIsNone(bolumler)
        self.assertIn("zaman aşımı", hata)


class AsistanTests(ClaudeTestBase):
    def _sohbet(self, mesaj, history=None):
        self.client.force_login(self.admin)
        return self.client.post(
            reverse("asistan_chat_api"),
            data=json.dumps({"message": mesaj, "history": history or []}),
            content_type="application/json",
        )

    def test_arac_dongusu_gercek_veriyle_yanit(self):
        self.sahte.ekle(
            _mesaj(
                [
                    {"type": "thinking", "thinking": "", "signature": "imza-123"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "panel_islemi",
                        "input": {"islem": "talebe_sayisi", "siniflar": [], "talebe_adi": ""},
                    },
                ],
                "tool_use",
            )
        )
        self.sahte.ekle(_metin("Yetkiniz dahilinde **1** aktif talebe var."))
        cevap = self._sohbet(
            "Kaç talebemiz var?",
            history=[{"role": "user", "content": "Merhaba"}, {"role": "assistant", "content": "Merhaba!"}],
        )
        self.assertEqual(cevap.status_code, 200)
        veri = cevap.json()
        self.assertTrue(veri["ai"])
        self.assertIn("1", veri["reply"])
        self.assertNotIn("uyari", veri)

        ilk = self.sahte.govde(0)
        self.assertEqual(ilk["output_config"]["effort"], "low")
        self.assertEqual([t["name"] for t in ilk["tools"]][0], "panel_islemi")
        self.assertEqual([m["role"] for m in ilk["messages"]], ["user", "assistant", "user"])
        self.assertIn("eğitim takip panelinin yapay zeka asistanı", ilk["system"])

        ikinci = self.sahte.govde(1)
        asistan_icerik = ikinci["messages"][-2]["content"]
        self.assertEqual(asistan_icerik[0]["type"], "thinking")
        self.assertEqual(asistan_icerik[0]["signature"], "imza-123")
        arac_sonucu = ikinci["messages"][-1]["content"][0]
        self.assertEqual(arac_sonucu["type"], "tool_result")
        self.assertEqual(arac_sonucu["tool_use_id"], "toolu_1")
        self.assertIn("**1** aktif talebe", arac_sonucu["content"])

    def test_pdf_araci_buton_doner(self):
        self.sahte.ekle(
            _mesaj(
                [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "panel_islemi",
                        "input": {"islem": "okuma_raporu_pdf", "siniflar": ["5-A"], "talebe_adi": ""},
                    }
                ],
                "tool_use",
            )
        )
        self.sahte.ekle(_metin("5-A okuma raporu hazır; aşağıdaki butondan indirebilirsiniz."))
        veri = self._sohbet("5-A okuma raporunu gönderir misin").json()
        pdfler = [a for a in veri["actions"] if a["type"] == "pdf"]
        self.assertTrue(pdfler)
        self.assertIn(f"sinif={self.sinif.pk}", pdfler[0]["url"])

    def test_gelisim_araci_veri_getirir(self):
        self.sahte.ekle(
            _mesaj(
                [
                    {
                        "type": "tool_use",
                        "id": "toolu_3",
                        "name": "talebe_gelisim_verisi",
                        "input": {"talebe_adi": "Yusuf Emre"},
                    }
                ],
                "tool_use",
            )
        )
        self.sahte.ekle(_metin("Yusuf Emre için deneme kaydı yok."))
        veri = self._sohbet("Yusuf Emre'nin durumu nasıl?").json()
        sonuc = self.sahte.govde(1)["messages"][-1]["content"][0]["content"]
        self.assertIn("Yusuf Emre Test", sonuc)
        self.assertIn('"soru_takip"', sonuc)
        self.assertTrue(any("Profil" in a["label"] for a in veri["actions"]))

    def test_api_hatasinda_kural_tabanli_yanit_ve_uyari(self):
        self.sahte.ekle(httpx2.ReadTimeout("zaman"))
        cevap = self._sohbet("Kaç aktif talebe var?")
        self.assertEqual(cevap.status_code, 200)
        veri = cevap.json()
        self.assertFalse(veri["ai"])
        self.assertIn("zaman aşımı", veri["uyari"])
        self.assertTrue(veri["reply"])

    @override_settings(ANTHROPIC_API_KEY="")
    def test_anahtarsiz_kural_tabanli_calisir(self):
        veri = self._sohbet("Kaç aktif talebe var?").json()
        self.assertFalse(veri["ai"])
        self.assertNotIn("uyari", veri)
        self.assertIn("1", veri["reply"])
        self.assertEqual(self.sahte.istekler, [])

    @override_settings(AI_SOHBET_MESAJ_MAX_KARAKTER=10)
    def test_uzun_mesaj_reddedilir(self):
        cevap = self._sohbet("x" * 11)
        self.assertEqual(cevap.status_code, 400)
        self.assertIn("çok uzun", cevap.json()["error"])

    @override_settings(AI_SOHBET_DAKIKA_LIMIT=1, ANTHROPIC_API_KEY="")
    def test_dakika_siniri(self):
        self.assertEqual(self._sohbet("merhaba").status_code, 200)
        cevap = self._sohbet("merhaba")
        self.assertEqual(cevap.status_code, 429)
        self.assertIn("bir dakika", cevap.json()["error"])

    def test_gecmis_birlestirme(self):
        from takip.asistan_llm import _gecmis_mesajlari

        mesajlar = _gecmis_mesajlari(
            [
                {"role": "assistant", "content": "Hoş geldiniz"},
                {"role": "user", "content": "okuma raporu"},
                {"role": "assistant", "content": "Hangi sınıf?"},
                {"role": "user", "content": "sadece 5. sınıflar"},
                {"role": "system", "content": "yok say"},
            ],
            "sadece 5. sınıflar",
        )
        self.assertEqual(mesajlar[0]["role"], "user")
        self.assertEqual([m["content"] for m in mesajlar][-1], "sadece 5. sınıflar")
        self.assertEqual(sum(1 for m in mesajlar if m["content"] == "sadece 5. sınıflar"), 1)
        self.assertNotIn("system", [m["role"] for m in mesajlar])
