from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(100), default="")
    target_accounts: Mapped[list["CustomerTargetAccount"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(100), default="")
    orders: Mapped[list["Order"]] = relationship(back_populates="supplier")


class CompanyAccount(Base, TimestampMixin):
    __tablename__ = "company_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    bank_name: Mapped[str] = mapped_column(String(120))
    account_no: Mapped[str] = mapped_column(String(120))
    primary_currency: Mapped[str] = mapped_column(String(8))
    orders: Mapped[list["Order"]] = relationship(back_populates="company_account")
    exchange_records: Mapped[list["ExchangeRecord"]] = relationship(back_populates="company_account")


class CustomerTargetAccount(Base, TimestampMixin):
    __tablename__ = "customer_target_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    account_name: Mapped[str] = mapped_column(String(120))
    bank_name: Mapped[str] = mapped_column(String(120))
    account_no: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(8))
    holder_name: Mapped[str] = mapped_column(String(120))
    customer: Mapped["Customer"] = relationship(back_populates="target_accounts")
    orders: Mapped[list["Order"]] = relationship(back_populates="target_account")


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_type: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    company_account_id: Mapped[int] = mapped_column(ForeignKey("company_accounts.id"))
    target_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customer_target_accounts.id"), nullable=True
    )
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    deposit_currency: Mapped[str] = mapped_column(String(8))
    payout_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    payout_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text, default="")
    customer: Mapped["Customer"] = relationship(back_populates="orders")
    supplier: Mapped[Optional["Supplier"]] = relationship(back_populates="orders")
    company_account: Mapped["CompanyAccount"] = relationship(back_populates="orders")
    target_account: Mapped[Optional["CustomerTargetAccount"]] = relationship(back_populates="orders")
    status_logs: Mapped[list["OrderStatusLog"]] = relationship(back_populates="order")
    ledger_entries: Mapped[list["AccountBalanceLedger"]] = relationship(back_populates="order")


class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    order: Mapped["Order"] = relationship(back_populates="status_logs")


class ExchangeRate(Base, TimestampMixin):
    __tablename__ = "exchange_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(8), unique=True)
    rate_to_aud_base: Mapped[Decimal] = mapped_column(Numeric(18, 6))


class ExchangeRecord(Base):
    __tablename__ = "exchange_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_account_id: Mapped[int] = mapped_column(ForeignKey("company_accounts.id"))
    source_currency: Mapped[str] = mapped_column(String(8))
    source_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    target_currency: Mapped[str] = mapped_column(String(8))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    company_account: Mapped["CompanyAccount"] = relationship(back_populates="exchange_records")


class AccountBalanceLedger(Base):
    __tablename__ = "account_balance_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_account_id: Mapped[int] = mapped_column(ForeignKey("company_accounts.id"))
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    entry_kind: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(8))
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reference_note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    order: Mapped[Optional["Order"]] = relationship(back_populates="ledger_entries")
