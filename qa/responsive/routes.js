/**
 * Route catalog — paths from takip/urls.py + takip/yonetim_urls.py.
 * role: which storageState to use (personel covers yönetim-capable staff).
 */
const ROUTES = [
  // Dashboards
  { id: "personel-dashboard", path: "/panel/", role: "personel", smoke: true },
  { id: "yonetim-dashboard", path: "/yonetim/", role: "personel" },
  { id: "ogretmen-dashboard", path: "/ogretmen-panel/", role: "ogretmen" },
  { id: "veli-dashboard", path: "/veli/", role: "veli" },
  { id: "talebe-dashboard", path: "/talebe/", role: "talebe" },

  // Core modules (personel / yetkili)
  { id: "dini-ders", path: "/dini-ders/", role: "personel", smoke: true },
  { id: "etut-plan", path: "/etut-plani/", role: "personel", smoke: true },
  { id: "dershane-program", path: "/dershane-programi/", role: "personel", smoke: true },
  { id: "namaz-yoklama", path: "/namaz-yoklama/", role: "personel" },
  { id: "rehberlik", path: "/rehberlik/", role: "personel" },
  { id: "temizlik", path: "/temizlik/", role: "personel" },
  { id: "yemekcilik", path: "/yemekcilik/", role: "personel" },
  { id: "imam-muezzin", path: "/imam-muezzin/", role: "personel" },
  { id: "soru-takip", path: "/soru-takip/", role: "personel" },
  { id: "finans", path: "/finans/", role: "personel" },
  { id: "mezunlar", path: "/mezunlar/", role: "personel" },
  { id: "disiplin", path: "/disiplin/", role: "personel" },

  // Lists / reports / announcements
  { id: "talebe-listesi", path: "/talebeler/", role: "personel" },
  { id: "kitap-listesi", path: "/kitaplar/", role: "personel" },
  { id: "raporlar", path: "/raporlar/", role: "personel" },
  { id: "ktt-listesi", path: "/ktt/", role: "personel" },
  { id: "denemeler", path: "/denemeler/", role: "personel" },
  { id: "programlar", path: "/programlar/", role: "personel" },
  { id: "bildirimler", path: "/panel/bildirimler/", role: "personel" },
  { id: "yonetim-duyurular", path: "/yonetim/duyurular/", role: "personel" },

  // Forms (GET render only — no submit)
  { id: "kitap-ekle", path: "/kitap-ekle/", role: "personel" },
  { id: "sinav-ekle", path: "/sinav-ekle/", role: "personel" },
  { id: "etut-plan-yonetim", path: "/etut-plani/yonetim/", role: "personel" },

  // Role panels (extra)
  { id: "veli-duyurular", path: "/veli/duyurular/", role: "veli" },
  { id: "talebe-profil", path: "/talebe/profil/", role: "talebe" },
  { id: "ogretmen-ders-programi", path: "/ogretmen-panel/ders-programi/", role: "ogretmen" },
];

const VIEWPORTS = [
  { name: "phone-390", width: 390, height: 844, group: "mobile" },
  { name: "phone-430", width: 430, height: 932, group: "mobile" },
  { name: "tablet-768", width: 768, height: 1024, group: "tablet" },
  { name: "tablet-900", width: 900, height: 1200, group: "tablet" },
  { name: "laptop-1366", width: 1366, height: 768, group: "desktop" },
  { name: "desktop-1440", width: 1440, height: 900, group: "desktop" },
  { name: "desktop-1920", width: 1920, height: 1080, group: "desktop" },
];

function getRoutes({ smokeOnly = false } = {}) {
  if (smokeOnly || process.env.QA_SMOKE === "1") {
    return ROUTES.filter((r) => r.smoke);
  }
  return ROUTES;
}

module.exports = { ROUTES, VIEWPORTS, getRoutes };
