"""Ortak form widget yardımcıları."""

from __future__ import annotations

from django import forms

CHIP_ATTRS = {"class": "choice-chip-grid"}
CHIP_WIDE_ATTRS = {"class": "choice-chip-grid choice-chip-grid--wide"}


class ChipCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Çoklu seçim — chip grid görünümü."""

    def __init__(self, attrs=None, *, wide: bool = False):
        base = dict(CHIP_WIDE_ATTRS if wide else CHIP_ATTRS)
        if attrs:
            extra = attrs.get("class", "")
            base["class"] = f"{base['class']} {extra}".strip()
            for k, v in attrs.items():
                if k != "class":
                    base[k] = v
        super().__init__(attrs=base)
