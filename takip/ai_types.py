"""Yapay zeka analiz — paylaşılan tipler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AiAnalizBolum:
    baslik: str
    icerik: str
    ton: str = "notr"


@dataclass
class AiAnalizSonuc:
    baslik: str
    tur: str
    bolumler: list[AiAnalizBolum] = field(default_factory=list)
    yapay_zeka: bool = False
    uyari: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def tam_metin(self) -> str:
        parcalar = [f"{b.baslik}\n{b.icerik}" for b in self.bolumler if b.icerik.strip()]
        return "\n\n".join(parcalar)

    def as_dict(self) -> dict[str, Any]:
        return {
            "baslik": self.baslik,
            "tur": self.tur,
            "yapay_zeka": self.yapay_zeka,
            "uyari": self.uyari,
            "meta": self.meta,
            "bolumler": [
                {"baslik": b.baslik, "icerik": b.icerik, "ton": b.ton}
                for b in self.bolumler
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AiAnalizSonuc:
        bolumler = [
            AiAnalizBolum(
                baslik=b.get("baslik", ""),
                icerik=b.get("icerik", ""),
                ton=b.get("ton", "notr"),
            )
            for b in data.get("bolumler", [])
        ]
        return cls(
            baslik=data.get("baslik", ""),
            tur=data.get("tur", ""),
            bolumler=bolumler,
            yapay_zeka=bool(data.get("yapay_zeka")),
            uyari=data.get("uyari", ""),
            meta=data.get("meta") or {},
        )
