from django import forms

from takip.forms import StyledModelForm
from takip.ss_deneme_models import SozelSayisalDeneme


class SozelSayisalDenemeForm(StyledModelForm):
    class Meta:
        model = SozelSayisalDeneme
        fields = [
            "ad",
            "sinav_tarihi",
            "soru_formati",
            "sinif_seviyesi",
            "aciklama",
            "veliye_goster",
            "etut_hocasi",
        ]
        widgets = {
            "sinav_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, admin_modu=False, liste_modu=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not admin_modu:
            self.fields.pop("etut_hocasi", None)
        if liste_modu:
            self.fields.pop("sinif_seviyesi", None)
        if not admin_modu:
            self.fields.pop("veliye_goster", None)
        self.fields["soru_formati"].label = "Soru formatı"
        self.fields["ad"].widget.attrs["placeholder"] = "Örn. 7. Sınıf 3. Deneme"
