from config.branding import (
    PANEL_FOOTER,
    PANEL_MOBILE_SHORT,
    PANEL_MODULE_LABEL,
    PANEL_MODULES,
    PANEL_NAME,
    PANEL_ORG,
    PANEL_SHORT,
)
from takip.panel_permissions import panel_nav_groups, panel_nav_items, rol_etiketi
from takip.yonetim_nav import yonetim_nav_groups
from takip.ogretmen_service import (
    ogretmen_brans_etiketi,
    ogretmen_hocasi_for_user,
    ogretmen_paneli_kullanicisi_mi,
)
from takip.talebe_panel_service import (
    kullanici_talebe_mi,
    talebe_hesabi_for_user,
)
from takip.veli_service import (
    kullanici_veli_mi,
    veli_hesabi_for_user,
    veli_talebe_ozet_etiketi,
)
from takip.asistan_service import asistan_kullanilabilir
from takip.ai_gateway import ai_platform_aktif_mi
from takip.ai_permissions import kurum_ai_erisebilir


def panel_branding(request):
    user = request.user
    is_veli = kullanici_veli_mi(user) if user.is_authenticated else False
    is_talebe = kullanici_talebe_mi(user) if user.is_authenticated else False
    is_ogretmen = ogretmen_paneli_kullanicisi_mi(user) if user.is_authenticated else False
    ozel_panel = is_veli or is_talebe or is_ogretmen
    nav = [] if ozel_panel else (panel_nav_items(user) if user.is_authenticated else [])
    nav_groups = [] if ozel_panel else (
        panel_nav_groups(user) if user.is_authenticated else []
    )

    talebe_hesap = talebe_hesabi_for_user(user) if is_talebe else None
    veli_hesap = veli_hesabi_for_user(user) if is_veli else None
    ogretmen_hoca = ogretmen_hocasi_for_user(user) if is_ogretmen else None

    if is_veli:
        module_label = "Veli Paneli"
        rol_etiketi_text = "Veli"
        user_display_name = (
            veli_hesap.ad_soyad if veli_hesap else (user.get_full_name() or user.username)
        )
        user_subtitle = veli_talebe_ozet_etiketi(veli_hesap)
    elif is_talebe:
        module_label = "Talebe Paneli"
        rol_etiketi_text = "Talebe"
        user_display_name = user.get_full_name() or user.username
        user_subtitle = (
            talebe_hesap.talebe.ad_soyad if talebe_hesap and talebe_hesap.talebe_id else "Talebe"
        )
    elif is_ogretmen:
        module_label = "Öğretmen Paneli"
        rol_etiketi_text = "Öğretmen"
        user_display_name = (
            ogretmen_hoca.ad_soyad
            if ogretmen_hoca
            else (user.get_full_name() or user.username)
        )
        user_subtitle = ogretmen_brans_etiketi(ogretmen_hoca)
    else:
        module_label = PANEL_MODULE_LABEL
        rol_etiketi_text = rol_etiketi(user) if user.is_authenticated else ""
        user_display_name = user.get_full_name() or user.username if user.is_authenticated else ""
        user_subtitle = rol_etiketi_text

    bildirim_okunmamis = 0
    if user.is_authenticated:
        try:
            from takip.bildirim_service import okunmamis_sayisi

            bildirim_okunmamis = okunmamis_sayisi(user)
        except Exception:
            bildirim_okunmamis = 0

    return {
        "panel_name": PANEL_NAME,
        "panel_short": PANEL_SHORT,
        "panel_mobile_short": PANEL_MOBILE_SHORT,
        "panel_module_label": module_label,
        "panel_org": PANEL_ORG,
        "panel_footer": PANEL_FOOTER,
        "panel_modules": PANEL_MODULES,
        "panel_nav": nav,
        "panel_nav_groups": nav_groups,
        "panel_rol_etiketi": rol_etiketi_text,
        "panel_user_name": user_display_name,
        "panel_user_subtitle": user_subtitle,
        "veli_kullanicisi": is_veli,
        "veli": veli_hesap,
        "talebe_kullanicisi": is_talebe,
        "talebe_hesap": talebe_hesap,
        "talebe": talebe_hesap.talebe if talebe_hesap else None,
        "ogretmen_kullanicisi": is_ogretmen,
        "ogretmen_hoca": ogretmen_hoca,
        "yonetim_nav_groups": yonetim_nav_groups(),
        "asistan_aktif": asistan_kullanilabilir(user) if user.is_authenticated else False,
        "ai_platform_aktif": ai_platform_aktif_mi() and user.is_authenticated,
        "ai_kurum_erisim": kurum_ai_erisebilir(user) if user.is_authenticated else False,
        "bildirim_okunmamis": bildirim_okunmamis,
    }
