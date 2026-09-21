"""Akıllı Tahta Dosya Merkezi — yönetici kontrolleri.

Tahta hesabı oluşturma/düzenleme/şifre değiştirme/oturum sonlandırma ve
işlem geçmişi (audit trail). Hepsi ``manage_accounts`` iznine bağlıdır —
sadece idareci/ic_mesul/egitim_mesul (veya süper kullanıcı) erişebilir.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from takip.akilli_tahta_models import AkilliTahtaHesap, AkilliTahtaIslemKaydi
from takip.akilli_tahta_service import hesabin_oturumlarini_sonlandir, islem_kaydet
from takip.akilli_tahta_yonetim_forms import (
    AkilliTahtaHesapDuzenleForm,
    AkilliTahtaHesapOlusturForm,
    SifreDegistirForm,
)
from takip.permissions.decorators import require_permission


@login_required
@require_permission("akilli_tahta", "manage_accounts")
def hesap_listesi(request):
    hesaplar = AkilliTahtaHesap.objects.select_related("user").order_by("sinif_seviyesi")
    return render(request, "akilli_tahta/yonetim/hesap_listesi.html", {"hesaplar": hesaplar})


@login_required
@require_permission("akilli_tahta", "manage_accounts")
def hesap_olustur(request):
    if request.method == "POST":
        form = AkilliTahtaHesapOlusturForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            hesap = form.save(commit=False)
            hesap.user = user
            hesap.olusturan = request.user
            hesap.save()
            islem_kaydet(request.user, "hesap_olustur", hesap=hesap, detay=user.username)
            messages.success(request, f"“{user.username}” akıllı tahta hesabı oluşturuldu.")
            return redirect("akilli_tahta_yonetim:hesap_listesi")
    else:
        form = AkilliTahtaHesapOlusturForm()

    return render(request, "akilli_tahta/yonetim/hesap_form.html", {"form": form, "duzenleme": False})


@login_required
@require_permission("akilli_tahta", "manage_accounts")
def hesap_duzenle(request, pk):
    hesap = get_object_or_404(AkilliTahtaHesap, pk=pk)
    if request.method == "POST":
        form = AkilliTahtaHesapDuzenleForm(request.POST, instance=hesap)
        if form.is_valid():
            onceki_aktif = hesap.aktif
            guncel = form.save(commit=False)
            guncel.user.is_active = guncel.aktif
            guncel.user.save(update_fields=["is_active"])
            guncel.save()
            if onceki_aktif and not guncel.aktif:
                hesabin_oturumlarini_sonlandir(guncel)
            islem_kaydet(
                request.user,
                "hesap_duzenle",
                hesap=guncel,
                detay=f"aktif={guncel.aktif}",
            )
            messages.success(request, f"“{hesap.user.username}” hesabı güncellendi.")
            return redirect("akilli_tahta_yonetim:hesap_listesi")
    else:
        form = AkilliTahtaHesapDuzenleForm(instance=hesap)

    return render(
        request,
        "akilli_tahta/yonetim/hesap_form.html",
        {"form": form, "duzenleme": True, "hesap": hesap},
    )


@login_required
@require_permission("akilli_tahta", "manage_accounts")
def hesap_sifre_degistir(request, pk):
    hesap = get_object_or_404(AkilliTahtaHesap, pk=pk)
    if request.method == "POST":
        form = SifreDegistirForm(request.POST)
        if form.is_valid():
            hesap.user.set_password(form.cleaned_data["password"])
            hesap.user.save(update_fields=["password"])
            kapatilan = hesabin_oturumlarini_sonlandir(hesap)
            islem_kaydet(
                request.user,
                "hesap_sifre_degistir",
                hesap=hesap,
                detay=f"{kapatilan} oturum kapatıldı",
            )
            messages.success(
                request,
                f"“{hesap.user.username}” şifresi değiştirildi ve tüm oturumları kapatıldı.",
            )
            return redirect("akilli_tahta_yonetim:hesap_listesi")
    else:
        form = SifreDegistirForm()

    return render(
        request, "akilli_tahta/yonetim/sifre_form.html", {"form": form, "hesap": hesap}
    )


@login_required
@require_POST
@require_permission("akilli_tahta", "manage_accounts")
def hesap_oturumlari_sonlandir(request, pk):
    hesap = get_object_or_404(AkilliTahtaHesap, pk=pk)
    kapatilan = hesabin_oturumlarini_sonlandir(hesap)
    islem_kaydet(
        request.user, "oturum_sonlandir", hesap=hesap, detay=f"{kapatilan} oturum kapatıldı"
    )
    messages.success(request, f"“{hesap.user.username}” için {kapatilan} oturum kapatıldı.")
    return redirect("akilli_tahta_yonetim:hesap_listesi")


@login_required
@require_permission("akilli_tahta", "manage_accounts")
def islem_gecmisi(request):
    kayitlar = (
        AkilliTahtaIslemKaydi.objects.select_related("kullanici", "dosya", "hesap")
        .order_by("-olusturulma")[:300]
    )
    return render(request, "akilli_tahta/yonetim/islem_gecmisi.html", {"kayitlar": kayitlar})
