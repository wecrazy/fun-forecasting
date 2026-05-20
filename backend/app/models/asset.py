"""
models/asset.py — Asset catalogue ORM model.
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    asset_type: Mapped[str] = mapped_column(String(16))  # "crypto" | "stock"
    currency_native: Mapped[str] = mapped_column(String(8), default="usd")

    def __repr__(self) -> str:
        return f"<Asset id={self.id} name={self.name}>"
