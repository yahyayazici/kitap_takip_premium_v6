"""Panel asistanı — paylaşılan yanıt tipleri."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AsistanAction:
    type: str
    label: str
    url: str = ""
    value: str = ""

    def as_dict(self) -> dict[str, str]:
        data = {"type": self.type, "label": self.label}
        if self.url:
            data["url"] = self.url
        if self.value:
            data["value"] = self.value
        return data


@dataclass
class AsistanYanit:
    reply: str
    actions: list[AsistanAction] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    # Yapay zeka kullanılamadığında kullanıcıya gösterilen açıklama
    uyari: str = ""
    yapay_zeka: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = {
            "reply": self.reply,
            "actions": [a.as_dict() for a in self.actions],
            "suggestions": self.suggestions,
            "ai": self.yapay_zeka,
        }
        if self.uyari:
            data["uyari"] = self.uyari
        return data
