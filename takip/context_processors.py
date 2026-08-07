from config.branding import (
    PANEL_FOOTER,
    PANEL_MODULE_LABEL,
    PANEL_MODULES,
    PANEL_NAME,
    PANEL_ORG,
    PANEL_SHORT,
)
from takip.panel_permissions import panel_nav_groups, panel_nav_items, rol_etiketi
from takip.yonetim_nav import yonetim_nav_groups
from takip.ogretmen_service import (
    kullanici_ogretmen_mi,
    ogretmen_hocasi_for_user,
    ogretmen_paneli_kullanicisi_mi,
)
from takip.talebe_panel_service import (
    kullanici_talebe_mi,
    talebe_hesabi_for_user,
)
from takip.veli_service import kullanici_veli_mi, veli_hesabi_for_user
from takip.asistan_service import asistan_kullanilabilir


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

    if is_veli:
        module_label = "Veli Paneli"
        rol_etiketi_text = "Veli"
    elif is_talebe:
        module_label = "Talebe Paneli"
        rol_etiketi_text = "Talebe"
    elif is_ogretmen:
        module_label = "Öğretmen Paneli"
        rol_etiketi_text = "Öğretmen"
    else:
        module_label = PANEL_MODULE_LABEL
        rol_etiketi_text = rol_etiketi(user) if user.is_authenticated else ""

    return {
        "panel_name": PANEL_NAME,
        "panel_short": PANEL_SHORT,
        "panel_module_label": module_label,
        "panel_org": PANEL_ORG,
        "panel_footer": PANEL_FOOTER,
        "panel_modules": PANEL_MODULES,
        "panel_nav": nav,
        "panel_nav_groups": nav_groups,
        "panel_rol_etiketi": rol_etiketi_text,
        "veli_kullanicisi": is_veli,
        "veli": veli_hesabi_for_user(user) if is_veli else None,
        "talebe_kullanicisi": is_talebe,
        "talebe_hesap": talebe_hesap,
        "talebe": talebe_hesap.talebe if talebe_hesap else None,
        "ogretmen_kullanicisi": is_ogretmen,
        "ogretmen_hoca": ogretmen_hocasi_for_user(user) if is_ogretmen else None,
        "yonetim_nav_groups": yonetim_nav_groups(),
        "asistan_aktif": asistan_kullanilabilir(user) if user.is_authenticated else False,
    }
