"""SQLAlchemy ORM models — MVP uses SQLite, V1 migrates to PostgreSQL."""

from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Fournisseur(Base):
    __tablename__ = "fournisseurs"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    mercuriales: Mapped[list[Mercuriale]] = relationship(
        back_populates="fournisseur", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Fournisseur {self.nom!r}>"


class Mercuriale(Base):
    """One price list from one supplier at one point in time."""

    __tablename__ = "mercuriales"

    id: Mapped[int] = mapped_column(primary_key=True)
    fournisseur_id: Mapped[int] = mapped_column(
        ForeignKey("fournisseurs.id"), nullable=False
    )
    date_tarif: Mapped[date] = mapped_column(Date, nullable=False)
    # Source format: xlsx, pdf, email
    source_format: Mapped[Optional[str]] = mapped_column(String(20))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    fournisseur: Mapped[Fournisseur] = relationship(back_populates="mercuriales")
    produits: Mapped[list[ProduitTarif]] = relationship(
        back_populates="mercuriale", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Mercuriale fournisseur={self.fournisseur_id} date={self.date_tarif}>"


class ProduitTarif(Base):
    """One product line in a mercuriale."""

    __tablename__ = "produits_tarif"

    id: Mapped[int] = mapped_column(primary_key=True)
    mercuriale_id: Mapped[int] = mapped_column(
        ForeignKey("mercuriales.id"), nullable=False
    )
    nom_produit: Mapped[str] = mapped_column(String(300), nullable=False)
    origine: Mapped[Optional[str]] = mapped_column(String(100))
    local: Mapped[bool] = mapped_column(Boolean, default=False)
    colisage: Mapped[Optional[float]] = mapped_column(Float)
    unite: Mapped[Optional[str]] = mapped_column(String(10))
    certification: Mapped[Optional[str]] = mapped_column(String(10))
    prix_colis_1_4: Mapped[Optional[float]] = mapped_column(Float)
    prix_colis_5_plus: Mapped[Optional[float]] = mapped_column(Float)
    pum: Mapped[Optional[float]] = mapped_column(Float)
    unite_pum: Mapped[Optional[str]] = mapped_column(String(10))
    # FL_FRAIS or EPICERIE
    categorie: Mapped[Optional[str]] = mapped_column(String(20))

    mercuriale: Mapped[Mercuriale] = relationship(back_populates="produits")


class Produit(Base):
    """Internal product catalogue — one row per Code Article from the ERP."""

    __tablename__ = "produits"

    code_article: Mapped[str] = mapped_column(String(50), primary_key=True)
    designation: Mapped[str] = mapped_column(String(300), nullable=False)
    famille: Mapped[Optional[str]] = mapped_column(String(100))
    fournisseur: Mapped[Optional[str]] = mapped_column(String(200))
    ref_fournis: Mapped[Optional[str]] = mapped_column(String(100))
    note: Mapped[Optional[str]] = mapped_column(String(500))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Produit {self.code_article!r} {self.designation!r}>"
