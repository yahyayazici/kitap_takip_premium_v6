from django import forms
from django.contrib.auth.models import User
from django.db import transaction

from .models import EtutHocasi, SinifSube, Talebe


class SinifSubeForm(forms.ModelForm):
    class Meta:
        model = SinifSube
        fields = ["sinif", "sube", "aktif"]
        widgets = {
            "sinif": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Örn. 3, 4, 5, Hazırlık",
                }
            ),
            "sube": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Örn. A, B, C",
                }
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }


class EtutHocasiForm(forms.ModelForm):
    kullanici_adi = forms.CharField(
        label="Kullanıcı adı",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "cs-input",
                "placeholder": "Örn. yahya.yazici",
                "autocomplete": "off",
            }
        ),
    )

    sifre = forms.CharField(
        label="Şifre",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "cs-input",
                "placeholder": "Yeni personelde zorunludur",
                "autocomplete": "new-password",
            },
            render_value=False,
        ),
        help_text=(
            "Yeni personelde en az 8 karakter girin. "
            "Düzenlemede boş bırakırsanız şifre değişmez."
        ),
    )

    class Meta:
        model = EtutHocasi
        fields = [
            "ad_soyad",
            "sorumlu_sinif_subeler",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Ad ve soyad",
                }
            ),
            "sorumlu_sinif_subeler": forms.CheckboxSelectMultiple(),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sorumlu_sinif_subeler"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        if self.instance and self.instance.pk:
            self.fields["kullanici_adi"].initial = (
                self.instance.user.username
            )

    def clean_kullanici_adi(self):
        kullanici_adi = (
            self.cleaned_data["kullanici_adi"]
            .strip()
            .lower()
        )

        sorgu = User.objects.filter(
            username__iexact=kullanici_adi
        )

        if self.instance and self.instance.pk:
            sorgu = sorgu.exclude(
                pk=self.instance.user_id
            )

        if sorgu.exists():
            raise forms.ValidationError(
                "Bu kullanıcı adı zaten kullanılıyor."
            )

        return kullanici_adi

    def clean_sifre(self):
        sifre = self.cleaned_data.get("sifre", "")

        if not self.instance.pk and not sifre:
            raise forms.ValidationError(
                "Yeni personel için şifre zorunludur."
            )

        if sifre and len(sifre) < 8:
            raise forms.ValidationError(
                "Şifre en az 8 karakter olmalıdır."
            )

        return sifre

    @transaction.atomic
    def save(self, commit=True):
        personel = super().save(commit=False)

        kullanici_adi = self.cleaned_data["kullanici_adi"]
        sifre = self.cleaned_data.get("sifre")

        if personel.pk:
            user = personel.user
        else:
            user = User()

        user.username = kullanici_adi
        user.first_name = personel.ad_soyad
        user.is_active = personel.aktif
        user.is_staff = True

        if sifre:
            user.set_password(sifre)

        user.save()
        personel.user = user

        if commit:
            personel.save()
            self.save_m2m()

        return personel


class TalebeForm(forms.ModelForm):
    class Meta:
        model = Talebe
        fields = [
            "ad_soyad",
            "talebe_no",
            "sinif_sube",
            "etut_hocasi",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Talebenin adını ve soyadını yazın",
                }
            ),
            "talebe_no": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Talebe numarası",
                }
            ),
            "sinif_sube": forms.RadioSelect(),
            "etut_hocasi": forms.Select(
                attrs={"class": "cs-input"}
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sinif_sube"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        self.fields["etut_hocasi"].queryset = (
            EtutHocasi.objects.filter(aktif=True)
            .prefetch_related("sorumlu_sinif_subeler")
            .order_by("ad_soyad")
        )
