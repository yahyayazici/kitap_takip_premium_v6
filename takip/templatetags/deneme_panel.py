"""Deneme, Etüt Kontrol ve Deneme Kontrol tek panel sekmesi."""

from django import template

from takip.deneme_kontrol_service import deneme_kontrol_erisimi_var
from takip.panel_permissions import deneme_modulu_erisimi_var

register = template.Library()


@register.inclusion_tag("partials/deneme_panel_switch.html", takes_context=True)
def deneme_panel_switch(context, sekme):
    user = context["request"].user
    modul = deneme_modulu_erisimi_var(user) or user.is_staff
    sekmeler = []
    if deneme_kontrol_erisimi_var(user):
        sekmeler.append(("kontrol", "Deneme Kontrol", "ogretmen_deneme_kontrol_merkezi"))
    if modul:
        sekmeler.append(("takip", "Etüt Kontrol", "etut_kontrol_panel"))
        sekmeler.append(("denemeler", "Denemeler", "deneme_listesi"))
    return {"sekmeler": sekmeler if len(sekmeler) > 1 else [], "sekme": sekme}
